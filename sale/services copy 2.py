from django.core.exceptions import ValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from inventory.models import Bucket, InventoryMovement, MovementType
from sale.models import Vente
from stock.models import VendorStock
from store.models import Produit
from vendor.models import Vendor


def _consume_vendor_stock_for_product(*, vendor: Vendor, produit: Produit, quantite: int):
    """
    Consomme le stock vendeur (FIFO par ProduitLine) pour une livraison.
    - VendorStock: quantite_allouee, quantite_vendue
      disponible = quantite_allouee - quantite_vendue
    ✅ Ne touche PAS ProduitLine.quantite (quantité d'achat initiale).
    Retour: [{"pl_id": ..., "qte": ...}]
    """
    remaining = int(quantite or 0)
    if remaining <= 0:
        raise ValidationError("Quantité à vendre doit être > 0")

    vstocks = (
        VendorStock.objects
        .select_for_update()
        .select_related("produit_line", "produit_line__lot")
        .filter(
            vendor=vendor,
            produit_line__produit=produit,
            quantite_allouee__gt=F("quantite_vendue"),
        )
        .order_by("produit_line__lot__received_at", "produit_line_id")
    )

    moves = []
    for vs in vstocks:
        if remaining == 0:
            break

        dispo = int((vs.quantite_allouee or 0) - (vs.quantite_vendue or 0))
        if dispo <= 0:
            continue

        take = min(dispo, remaining)

        # ✅ consommer = augmenter quantite_vendue (atomique)
        updated_vs = (
            VendorStock.objects
            .filter(
                pk=vs.pk,
                quantite_allouee__gte=F("quantite_vendue") + take,
            )
            .update(quantite_vendue=F("quantite_vendue") + take)
        )
        if not updated_vs:
            raise ValidationError("Conflit de stock détecté, réessayez.")

        moves.append({"pl_id": vs.produit_line_id, "qte": take})
        remaining -= take

    if remaining > 0:
        raise ValidationError(
            f"Stock vendeur insuffisant pour '{getattr(produit, 'nom', 'produit')}'. Manque {remaining}."
        )

    return moves


# @transaction.atomic
# def sale_out_now_for_vente(vente, by_user) -> int:
#     """
#     Sortie stock immédiate à la création de vente.
#     - Idempotent par ligne via UniqueConstraint(sale_out_key)
#     - Mouvement d'abord, puis consommation VendorStock
#     """
#     v = (
#         Vente.objects
#         .select_for_update()
#         .select_related("facture_vente", "facture_vente__bijouterie")
#         .prefetch_related("produits__produit", "produits__vendor")
#         .get(pk=vente.pk)
#     )

#     facture = getattr(v, "facture_vente", None)
#     if not facture or not facture.bijouterie_id:
#         raise ValidationError("Facture/bijouterie requise pour SALE_OUT immédiat.")

#     now = timezone.now()
#     created = 0

#     lignes = [li for li in v.produits.all() if li.produit_id and li.quantite]
#     for li in lignes:
#         if not li.vendor_id:
#             raise ValidationError(f"Ligne {li.id}: vendeur manquant.")

#         # 1) Mouvement SALE_OUT (idempotent)
#         mouvement_cree = False
#         try:
#             InventoryMovement.objects.create(
#                 produit=li.produit,
#                 movement_type=MovementType.SALE_OUT,
#                 qty=li.quantite,
#                 unit_cost=None,
#                 lot=None,
#                 reason=f"Vente {getattr(v,'numero_vente',v.id)} / ligne {li.id}",
#                 src_bucket=Bucket.BIJOUTERIE,
#                 src_bijouterie=facture.bijouterie,
#                 dst_bucket=Bucket.EXTERNAL,
#                 dst_bijouterie=None,
#                 facture=facture,
#                 vente=v,
#                 vente_ligne=li,
#                 occurred_at=now,
#                 created_by=by_user,
#                 vendor=li.vendor,
#                 stock_consumed=False,  # on va le passer à True après conso
#             )
#             mouvement_cree = True
#             created += 1
#         except (IntegrityError, DjangoValidationError) as e:
#             # déjà existant => OK (idempotent)
#             msg = str(e).lower()
#             if "sale_out" in msg or "sale out key" in msg:
#                 mouvement_cree = False
#             else:
#                 raise

#         # 2) Consommer VendorStock uniquement si mouvement créé
#         if mouvement_cree:
#             _consume_vendor_stock_for_product(
#                 vendor=li.vendor,
#                 produit=li.produit,
#                 quantite=li.quantite,
#             )
#             # marquer le mouvement comme stock_consumed=True
#             InventoryMovement.objects.filter(
#                 movement_type=MovementType.SALE_OUT,
#                 vente_ligne_id=li.id,
#             ).update(stock_consumed=True)

#     # 3) Marquer vente livrée (si tu veux)
#     if hasattr(v, "marquer_livree") and callable(v.marquer_livree):
#         v.marquer_livree(by_user)
#     elif hasattr(v, "delivery_status") and hasattr(v.__class__, "DELIV_DELIVERED"):
#         v.delivery_status = v.__class__.DELIV_DELIVERED
#         v.save(update_fields=["delivery_status"])

#     return created


@transaction.atomic
def sale_out_now_for_vente(vente, by_user) -> int:
    """
    Sortie stock immédiate après création vente.
    - Crée InventoryMovement SALE_OUT par ligne (idempotent via sale_out_key = vente_ligne_id)
    - Puis consomme VendorStock (augmente quantite_vendue FIFO)
    """
    v = (
        Vente.objects
        .select_for_update()
        .select_related("facture_vente", "facture_vente__bijouterie")
        .prefetch_related("produits__produit", "produits__vendor")
        .get(pk=vente.pk)
    )

    facture = getattr(v, "facture_vente", None)
    if not facture or not facture.bijouterie_id:
        raise ValidationError("Facture/bijouterie requise pour SALE_OUT immédiat.")

    now = timezone.now()
    created = 0

    lignes = [li for li in v.produits.all() if li.produit_id and li.quantite]
    for li in lignes:
        if not li.vendor_id:
            raise ValidationError(f"Ligne {li.id}: vendeur manquant.")

        mouvement_cree = False
        try:
            InventoryMovement.objects.create(
                produit=li.produit,
                movement_type=MovementType.SALE_OUT,
                qty=li.quantite,
                unit_cost=None,
                lot=None,
                reason=f"Vente {getattr(v,'numero_vente',v.id)} / ligne {li.id}",
                src_bucket=Bucket.BIJOUTERIE,
                src_bijouterie=facture.bijouterie,
                dst_bucket=Bucket.EXTERNAL,
                dst_bijouterie=None,
                facture=facture,
                vente=v,
                vente_ligne=li,          # => sale_out_key auto dans save()
                occurred_at=now,
                created_by=by_user,
                vendor=li.vendor,
                stock_consumed=False,    # on mettra True après conso
            )
            mouvement_cree = True
            created += 1

        except (IntegrityError, DjangoValidationError) as e:
            # Idempotence : déjà créé
            msg = str(e).lower()
            if "sale_out" in msg or "sale out key" in msg:
                mouvement_cree = False
            else:
                raise

        # consommer seulement si mouvement créé
        if mouvement_cree:
            _consume_vendor_stock_for_product(
                vendor=li.vendor,
                produit=li.produit,
                quantite=li.quantite,
            )
            InventoryMovement.objects.filter(
                movement_type=MovementType.SALE_OUT,
                vente_ligne_id=li.id,
            ).update(stock_consumed=True)

    # optionnel: marquer livrée
    if hasattr(v, "marquer_livree") and callable(v.marquer_livree):
        v.marquer_livree(by_user)
    elif hasattr(v, "delivery_status") and hasattr(v.__class__, "DELIV_DELIVERED"):
        v.delivery_status = v.__class__.DELIV_DELIVERED
        v.save(update_fields=["delivery_status"])

    return created

# Service : restaurer stock vendeur (inverse de consume)

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import F
from rest_framework.exceptions import ValidationError


def _restore_vendor_stock_for_product(*, vendor: Vendor, produit: Produit, quantite: int):
    """
    Restaure le stock vendeur (inverse logique de la vente) :
    - diminue VendorStock.quantite_vendue (donc re-augmente dispo)
    - LIFO par lot (received_at DESC) pour éviter de casser le FIFO futur
    """
    remaining = int(quantite or 0)
    if remaining <= 0:
        return

    # 🔒 lock rows
    vstocks = (
        VendorStock.objects
        .select_for_update()
        .select_related("produit_line__lot")
        .filter(
            vendor=vendor,
            produit_line__produit=produit,
            quantite_vendue__gt=0,
        )
        .order_by("-produit_line__lot__received_at", "-produit_line_id")
    )

    for vs in vstocks:
        if remaining == 0:
            break

        sold = int(vs.quantite_vendue or 0)
        if sold <= 0:
            continue

        take = min(sold, remaining)

        updated = (
            VendorStock.objects
            .filter(pk=vs.pk, quantite_vendue__gte=take)
            .update(quantite_vendue=F("quantite_vendue") - take)
        )
        if not updated:
            raise ValidationError("Conflit de restauration stock vendeur, réessayez.")

        remaining -= take

    if remaining > 0:
        # si ça arrive => incohérence (tu annules + que vendu côté VendorStock)
        raise ValidationError(
            f"Restauration impossible : il manque {remaining} unités à 'dé-vendre' "
            f"pour le vendeur {vendor.id} sur '{getattr(produit,'nom',produit.id)}'."
        )
        

# Service : annuler vente = RETURN_IN + restore vendor stock

from django.db import transaction
from django.utils import timezone


@transaction.atomic
def cancel_vente_and_restore_stock(*, vente_id: int, by_user) -> dict:
    """
    Annule une vente (toutes les lignes):
    - Crée RETURN_IN par ligne (idempotent via check exist)
    - Restaure VendorStock.quantite_vendue
    - Marque vente/facture annulées si champs existent

    Retour: {"returned_movements": X, "restored": True}
    """
    v = (
        Vente.objects
        .select_for_update()
        .select_related("facture_vente", "facture_vente__bijouterie")
        .prefetch_related("produits__produit", "produits__vendor")
        .get(pk=vente_id)
    )

    facture = getattr(v, "facture_vente", None)
    if not facture or not getattr(facture, "bijouterie_id", None):
        raise ValidationError("Vente sans facture/bijouterie : annulation impossible.")

    # ✅ déjà annulée ? (idempotent)
    if getattr(v, "is_cancelled", False) is True:
        return {"returned_movements": 0, "restored": True, "already_cancelled": True}

    now = timezone.now()
    returned = 0

    lignes = [li for li in v.produits.all() if li.produit_id and li.quantite]
    for li in lignes:
        if not li.vendor_id:
            raise ValidationError(f"Ligne {li.id}: vendeur manquant.")

        # 🔁 Idempotence RETURN_IN : on ne recrée pas si déjà fait pour cette ligne
        already = InventoryMovement.objects.filter(
            movement_type=MovementType.RETURN_IN,
            vente_id=v.id,
            vente_ligne_id=li.id,
        ).exists()

        if not already:
            InventoryMovement.objects.create(
                produit=li.produit,
                movement_type=MovementType.RETURN_IN,
                qty=li.quantite,
                unit_cost=None,
                lot=None,
                reason=f"ANNULATION vente {getattr(v,'numero_vente',v.id)} / ligne {li.id}",
                src_bucket=Bucket.EXTERNAL,
                src_bijouterie=None,
                dst_bucket=Bucket.BIJOUTERIE,
                dst_bijouterie=facture.bijouterie,
                facture=facture,
                vente=v,
                vente_ligne=li,   # utile pour tracer (pas obligatoire par clean, mais ok)
                occurred_at=now,
                created_by=by_user,
                vendor=li.vendor,
            )
            returned += 1

        # ✅ Restaurer stock vendeur (même si RETURN_IN existait déjà => on doit éviter double restore)
        # Pour éviter double restore, on se base sur les SALE_OUT consommés
        # -> on restaure seulement si il existe un SALE_OUT "stock_consumed=True" et pas encore "unconsumed"
        sale_outs = InventoryMovement.objects.filter(
            movement_type=MovementType.SALE_OUT,
            vente_id=v.id,
            vente_ligne_id=li.id,
            stock_consumed=True,
        )

        if sale_outs.exists():
            _restore_vendor_stock_for_product(vendor=li.vendor, produit=li.produit, quantite=li.quantite)
            # marquer ces SALE_OUT comme "dé-consommés" pour idempotence
            sale_outs.update(stock_consumed=False)

    # ✅ Marquer vente annulée (si tu as un champ)
    if hasattr(v, "is_cancelled"):
        v.is_cancelled = True
        v.save(update_fields=["is_cancelled"])

    # ✅ Optionnel: marquer facture annulée si tu as un statut dédié
    if hasattr(facture, "STAT_ANNULEE") and hasattr(facture, "status"):
        facture.status = facture.STAT_ANNULEE
        facture.save(update_fields=["status"])

    return {"returned_movements": returned, "restored": True, "already_cancelled": False}