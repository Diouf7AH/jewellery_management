from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from inventory.models import Bucket, InventoryMovement, MovementType
from sale.models import Client, Facture, Vente, VenteProduit
from sale.services.inventory_audit_service import (create_return_in,
                                                   create_sale_out)
from sale.services.vendor_stock_service import (consume_vendor_stock,
                                                restore_vendor_stock)
from sale.utils import ZERO, dec
from store.models import MarquePurete, Produit
from vendor.models import Vendor


def resolve_vendor_for_line(*, role, user, bijouterie, vendor_email=None) -> Vendor:
    from sale.utils import get_role_name  # éviter import circulaire
    if role == "vendor":
        v = getattr(user, "staff_vendor_profile", None)
        if not v:
            raise ValidationError("Profil vendeur introuvable.")
        if getattr(v, "bijouterie_id", None) != getattr(bijouterie, "id", None):
            raise ValidationError("Vendeur hors bijouterie.")
        return v

    if role == "manager":
        if not vendor_email:
            raise ValidationError("vendor_email requis pour manager.")
        v = Vendor.objects.select_related("bijouterie").filter(user__email=vendor_email).first()
        if not v:
            raise ValidationError("Vendeur introuvable (vendor_email).")
        if getattr(v, "bijouterie_id", None) != getattr(bijouterie, "id", None):
            raise ValidationError("Ce vendeur n’appartient pas à votre bijouterie.")
        return v

    raise ValidationError("Rôle non autorisé.")


@transaction.atomic
def create_sale_direct_stock(*, user, bijouterie, role, payload) -> tuple[Vente, Facture, int]:
    """
    Crée vente + lignes + facture, décrémente VendorStock direct,
    puis écrit audit SALE_OUT (InventoryMovement).
    Retourne (vente, facture, nb_sale_out_crees)
    """
    client_in = payload["client"]
    items = payload["produits"]

    tel = (client_in.get("telephone") or "").strip()
    lookup = {"telephone": tel} if tel else {"nom": client_in["nom"], "prenom": client_in["prenom"]}
    client, _ = Client.objects.get_or_create(
        defaults={"nom": client_in["nom"], "prenom": client_in["prenom"], "telephone": tel or None},
        **lookup,
    )

    slugs = [it["slug"] for it in items]
    produits_qs = Produit.objects.select_related("marque", "purete").filter(slug__in=slugs)
    produits = {p.slug: p for p in produits_qs}
    missing = [s for s in set(slugs) if s not in produits]
    if missing:
        raise ValidationError(f"Produits introuvables: {', '.join(missing)}")

    pairs = {(p.marque_id, p.purete_id) for p in produits.values() if p.marque_id and p.purete_id}
    tarifs = {
        (mp.marque_id, mp.purete_id): Decimal(str(mp.prix))
        for mp in MarquePurete.objects.filter(
            marque_id__in=[m for (m, _) in pairs],
            purete_id__in=[r for (_, r) in pairs],
        )
    }

    vente = Vente.objects.create(client=client, created_by=user, bijouterie=bijouterie)

    lignes = []
    for it in items:
        produit = produits[it["slug"]]
        qte = int(it.get("quantite") or 0)
        if qte <= 0:
            raise ValidationError("Quantité doit être ≥ 1.")

        vendor = resolve_vendor_for_line(
            role=role, user=user, bijouterie=bijouterie, vendor_email=it.get("vendor_email")
        )

        pvg = dec(it.get("prix_vente_grammes"))
        if not pvg or pvg <= 0:
            pvg = tarifs.get((produit.marque_id, produit.purete_id))
            if not pvg or pvg <= 0:
                raise ValidationError(f"Tarif manquant pour {produit.nom}.")

        lp = VenteProduit.objects.create(
            vente=vente,
            produit=produit,
            vendor=vendor,
            quantite=qte,
            prix_vente_grammes=pvg,
            remise=dec(it.get("remise")) or ZERO,
            autres=dec(it.get("autres")) or ZERO,
            tax=dec(it.get("tax")) or ZERO,
        )
        lignes.append(lp)

        # ✅ décrément stock direct
        consume_vendor_stock(vendor=vendor, produit=produit, quantite=qte)

    try:
        vente.mettre_a_jour_montant_total(base="ttc")
    except Exception:
        pass

    facture = Facture.objects.create(
        vente=vente,
        bijouterie=bijouterie,
        montant_total=vente.montant_total,
        status=Facture.STAT_NON_PAYE,
        type_facture=Facture.TYPE_PROFORMA,
        numero_facture=Facture.generer_numero_unique(bijouterie),
    )

    created_moves = 0
    for lp in lignes:
        if create_sale_out(facture=facture, vente=vente, ligne=lp, by_user=user):
            created_moves += 1

    return vente, facture, created_moves


# @transaction.atomic
# def cancel_sale_restore_direct(*, user, vente: Vente, facture: Facture) -> dict:
#     """
#     Annule une vente : restaure VendorStock + écrit RETURN_IN.
#     Idempotence simple: si RETURN_IN existe déjà pour la vente => already_cancelled.
#     """
#     from inventory.models import InventoryMovement, MovementType

#     already = InventoryMovement.objects.filter(vente=vente, movement_type=MovementType.RETURN_IN).exists()
#     if already:
#         return {"already_cancelled": True, "returned_movements": 0}

#     returned = 0
#     for lp in vente.produits.all():
#         if not lp.produit_id or not lp.vendor_id or not lp.quantite:
#             continue

#         restore_vendor_stock(vendor=lp.vendor, produit=lp.produit, quantite=lp.quantite)
#         create_return_in(facture=facture, vente=vente, ligne=lp, by_user=user)
#         returned += 1

#     return {"already_cancelled": False, "returned_movements": returned}

@transaction.atomic
def cancel_sale_restore_direct(*, user, vente: Vente, facture: Facture) -> dict:
    """
    Annule une vente : restaure VendorStock + écrit RETURN_IN (audit).
    Idempotent par ligne : si RETURN_IN existe déjà pour la ligne => skip.
    """

    # 🔒 verrou vente (évite double annulation simultanée)
    v = (
        Vente.objects
        .select_for_update()
        .prefetch_related("produits__produit", "produits__vendor")
        .get(pk=vente.pk)
    )

    returned = 0
    skipped = 0

    for lp in v.produits.all():
        if not lp.produit_id or not lp.vendor_id or not lp.quantite:
            continue

        # ✅ idempotence par ligne
        already_line = InventoryMovement.objects.filter(
            movement_type=MovementType.RETURN_IN,
            vente_id=v.id,
            vente_ligne_id=lp.id,
        ).exists()
        if already_line:
            skipped += 1
            continue

        # ✅ restaurer VendorStock
        restore_vendor_stock(
            vendor=lp.vendor,
            produit=lp.produit,
            quantite=int(lp.quantite),
        )

        # ✅ audit RETURN_IN
        create_return_in(
            facture=facture,
            vente=v,
            ligne=lp,
            by_user=user,
        )

        returned += 1

    already_cancelled = (returned == 0 and skipped > 0)
    return {
        "already_cancelled": already_cancelled,
        "returned_movements": returned,
        "skipped_lines": skipped,
    }