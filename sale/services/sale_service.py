# sale/services/sale_service.py
from __future__ import annotations

from decimal import Decimal
from typing import Dict

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from purchase.models import ProduitLine
from sale.models import Client, Facture, Vente, VenteProduit
from sale.services.inventory_audit_service import create_return_in_consumption
from sale.services.sale_context_service import (
    dec, resolve_vendor_and_bijouterie_for_sale)
from sale.services.vendor_stock_service import (ensure_vendor_stock_available,
                                                restore_vendor_stock)
from sale.utils import ZERO
from store.models import MarquePurete, Produit


def upsert_client_for_payment(*, facture, client_data: dict):
    """
    Au paiement :
    - nom obligatoire
    - prenom obligatoire
    - telephone optionnel
    - met à jour le client lié à la vente si présent
    - sinon crée/récupère un client puis l'attache à la vente
    """
    if not facture.vente:
        raise ValidationError({"facture": "Aucune vente associée à cette facture."})

    nom = (client_data.get("nom") or "").strip()
    prenom = (client_data.get("prenom") or "").strip()
    telephone = (client_data.get("telephone") or "").strip()

    if not nom or not prenom:
        raise ValidationError({"client": "nom et prenom sont obligatoires au paiement."})

    vente = facture.vente
    client = getattr(vente, "client", None)

    if client:
        changed_fields = []

        if client.nom != nom:
            client.nom = nom
            changed_fields.append("nom")

        if client.prenom != prenom:
            client.prenom = prenom
            changed_fields.append("prenom")

        if telephone and client.telephone != telephone:
            client.telephone = telephone
            changed_fields.append("telephone")

        if changed_fields:
            client.save(update_fields=changed_fields)

        return client

    lookup = {"telephone": telephone} if telephone else {"nom": nom, "prenom": prenom}

    client, _ = Client.objects.get_or_create(
        defaults={
            "nom": nom,
            "prenom": prenom,
            "telephone": telephone or None,
        },
        **lookup,
    )

    vente.client = client
    vente.save(update_fields=["client"])
    return client


@transaction.atomic
def create_sale_one_vendor(*, user, role: str, payload: Dict) -> tuple[Vente, Facture, int]:
    """
    Création vente :
    - stock NON consommé ici
    - client optionnel
    - bijouterie = celle du vendeur
    - Vente.montant_total = total des lignes (HT métier)
    - Facture = HT + TVA + total TTC
    """
    client_in = payload.get("client") or {}
    items = payload.get("produits") or []

    if not items:
        raise ValidationError({"produits": "Au moins un produit est requis."})

    vendor, bijouterie = resolve_vendor_and_bijouterie_for_sale(
        role=role,
        user=user,
        vendor_email=payload.get("vendor_email"),
    )

    # --------------------------------------------------
    # Client optionnel
    # --------------------------------------------------
    nom = (client_in.get("nom") or "").strip()
    prenom = (client_in.get("prenom") or "").strip()
    tel = (client_in.get("telephone") or "").strip()

    client = None
    if nom and prenom:
        lookup = {"telephone": tel} if tel else {"nom": nom, "prenom": prenom}
        client, _ = Client.objects.get_or_create(
            defaults={"nom": nom, "prenom": prenom, "telephone": tel or None},
            **lookup,
        )
    elif any([nom, prenom, tel]):
        raise ValidationError({"client": "Si client est fourni, nom et prenom sont obligatoires."})

    # --------------------------------------------------
    # Préchargement produits
    # --------------------------------------------------
    produit_ids = []
    for i, item in enumerate(items):
        try:
            produit_ids.append(int(item["produit_id"]))
        except Exception:
            raise ValidationError({f"produits[{i}].produit_id": "Requis (int)."})

    produits_qs = (
        Produit.objects
        .select_related("marque", "purete")
        .filter(id__in=list(set(produit_ids)))
    )
    produits = {p.id: p for p in produits_qs}

    missing = [pid for pid in set(produit_ids) if pid not in produits]
    if missing:
        raise ValidationError({"produits": f"Produits introuvables: {missing}"})

    # --------------------------------------------------
    # Tarifs fallback marque/pureté
    # --------------------------------------------------
    pairs = {
        (p.marque_id, p.purete_id)
        for p in produits.values()
        if p.marque_id and p.purete_id
    }

    tarifs = {}
    if pairs:
        marques = [m for (m, _) in pairs]
        puretes = [r for (_, r) in pairs]

        for mp in MarquePurete.objects.filter(
            marque_id__in=marques,
            purete_id__in=puretes,
        ):
            tarifs[(mp.marque_id, mp.purete_id)] = Decimal(str(mp.prix))

    # --------------------------------------------------
    # Vérification stock vendeur sans consommation
    # --------------------------------------------------
    for i, item in enumerate(items):
        produit = produits[int(item["produit_id"])]
        qte = int(item.get("quantite") or 0)

        if qte <= 0:
            raise ValidationError({f"produits[{i}].quantite": "Doit être >= 1."})

        ensure_vendor_stock_available(
            vendor=vendor,
            bijouterie=bijouterie,
            produit=produit,
            quantite=qte,
        )

    # --------------------------------------------------
    # Création vente
    # --------------------------------------------------
    vente = Vente.objects.create(
        client=client,
        created_by=user,
        bijouterie=bijouterie,
        vendor=vendor,
    )

    # --------------------------------------------------
    # Création lignes
    # --------------------------------------------------
    for i, item in enumerate(items):
        produit = produits[int(item["produit_id"])]
        qte = int(item.get("quantite") or 0)

        prix_vente = dec(item.get("prix_vente_grammes"))
        if not prix_vente or prix_vente <= 0:
            prix_vente = tarifs.get((produit.marque_id, produit.purete_id))
            if not prix_vente or prix_vente <= 0:
                raise ValidationError({
                    f"produits[{i}].prix_vente_grammes": f"Tarif manquant pour {produit.nom}."
                })

        VenteProduit.objects.create(
            vente=vente,
            produit=produit,
            vendor=vendor,
            quantite=qte,
            prix_vente_grammes=prix_vente,
            remise=dec(item.get("remise")) or ZERO,
            autres=dec(item.get("autres")) or ZERO,
        )

    # Total de vente = total lignes
    vente.mettre_a_jour_montant_total()

    # --------------------------------------------------
    # Création facture PROFORMA
    # TVA copiée depuis la bijouterie
    # --------------------------------------------------
    facture = Facture.objects.create(
        vente=vente,
        bijouterie=bijouterie,
        montant_ht=vente.montant_total or Decimal("0.00"),
        appliquer_tva=bool(getattr(bijouterie, "appliquer_tva", True)),
        taux_tva=Decimal(str(getattr(bijouterie, "taux_tva", "0.00") or "0.00")),
        status=Facture.STAT_NON_PAYE,
        type_facture=Facture.TYPE_PROFORMA,
    )

    return vente, facture, 0


@transaction.atomic
def cancel_sale_restore_direct(*, user, vente: Vente, facture: Facture) -> dict:
    """
    Annule une vente et restaure le stock vendeur.
    """
    v = (
        Vente.objects
        .select_for_update()
        .prefetch_related("lignes", "lignes__produit", "lignes__vendor")
        .get(pk=vente.pk)
    )

    if getattr(v, "is_cancelled", False):
        return {"already_cancelled": True, "returned_movements": 0}

    if not facture or not getattr(facture, "bijouterie_id", None):
        raise ValidationError("Facture/bijouterie invalide pour restauration.")

    returned_movements = 0

    for lp in v.lignes.all():
        if not lp.produit_id or not lp.vendor_id:
            continue

        qty = int(lp.quantite or 0)
        if qty <= 0:
            continue

        restored = restore_vendor_stock(
            vendor=lp.vendor,
            produit=lp.produit,
            bijouterie=facture.bijouterie,
            quantite=qty,
        ) or []

        if not restored:
            continue

        pl_ids = list({
            int(m["produit_line_id"])
            for m in restored
            if m.get("produit_line_id")
        })

        if not pl_ids:
            continue

        pl_map = {
            pl.id: pl
            for pl in ProduitLine.objects
            .select_related("lot")
            .filter(id__in=pl_ids)
        }

        for m in restored:
            pl_id = m.get("produit_line_id")
            rqty = int(m.get("qty") or 0)

            if not pl_id or rqty <= 0:
                continue

            pl = pl_map.get(int(pl_id))
            if not pl or not pl.lot_id:
                continue

            create_return_in_consumption(
                facture=facture,
                vente=v,
                vente_ligne=lp,
                produit_line=pl,
                qty=rqty,
                by_user=user,
            )
            returned_movements += 1

    v.is_cancelled = True
    v.cancelled_at = timezone.now()
    v.cancelled_by = user
    v.save(update_fields=["is_cancelled", "cancelled_at", "cancelled_by"])

    return {
        "already_cancelled": False,
        "returned_movements": returned_movements,
    }


def validate_facture_payable(facture):
    """
    Vérifie que la facture peut encore être payée.
    """
    if facture.status == facture.STAT_PAYE:
        raise ValidationError("Cette facture est déjà totalement payée.")

    if facture.type_facture == facture.TYPE_PROFORMA:
        return

    if facture.type_facture in {
        facture.TYPE_FACTURE,
        facture.TYPE_ACOMPTE,
        facture.TYPE_FINALE,
    }:
        return

    raise ValidationError("Type de facture non pris en charge pour le paiement.")

