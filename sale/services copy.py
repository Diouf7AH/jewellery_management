from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Sum
from django.utils import timezone

from inventory.models import Bucket, InventoryMovement, MovementType
from sale.models import Vente
from stock.models import VendorStock
from store.models import Produit
from vendor.models import Vendor

# @transaction.atomic
# def create_sale_out_movements_for_vente(vente, by_user) -> int:
#     """
#     Livraison d'une vente :
#       - Vérifie facture payée & bijouterie présente
#       - Idempotent par ligne : un seul SALE_OUT par vente_ligne (protégé par contrainte UNIQUE)
#       - Crée le mouvement d’abord (protège contre la course), PUIS décrémente le stock
#       - Marque la vente livrée si toutes les lignes ont leur SALE_OUT
#     Retourne le nombre de mouvements créés à cet appel.
#     """
#     # 1) Verrou vente + dépendances
#     v = (Vente.objects
#          .select_for_update()
#          .select_related("facture_vente", "facture_vente__bijouterie")
#          .prefetch_related("produits__produit", "produits__vendor")
#          .get(pk=vente.pk))

#     facture = getattr(v, "facture_vente", None)
#     if not facture:
#         raise ValidationError("Aucune facture liée à la vente.")
#     if getattr(facture, "status", None) != getattr(facture.__class__, "STAT_PAYE", "paye"):
#         raise ValidationError("La facture n’est pas payée.")
#     if not getattr(facture, "bijouterie_id", None):
#         raise ValidationError("La facture n’a pas de bijouterie (requis pour la sortie de stock).")

#     now = timezone.now()
#     created = 0

#     lignes = list(v.produits.all())  # VenteProduit
#     total_lignes = len(lignes)

#     for li in lignes:
#         if not li.produit_id or not li.quantite:
#             continue
#         if not li.vendor_id:
#             raise ValidationError(f"La ligne {li.id} n'a pas de vendeur renseigné.")

#         # 2) Essayer de créer le mouvement en premier (idempotence forte via UNIQUE)
#         mouvement_cree = False
#         try:
#             InventoryMovement.objects.create(
#                 produit=li.produit,
#                 movement_type=MovementType.SALE_OUT,
#                 qty=li.quantite,
#                 unit_cost=None,
#                 lot=None,
#                 reason=f"Livraison facture {facture.numero_facture} / vente {v.numero_vente or v.id}",
#                 src_bucket=Bucket.BIJOUTERIE,
#                 src_bijouterie=facture.bijouterie,
#                 dst_bucket=Bucket.EXTERNAL,
#                 dst_bijouterie=None,
#                 achat=None, achat_ligne=None,
#                 facture=facture,
#                 vente=v,
#                 vente_ligne=li,      # ← clé d’unicité (directe ou via sale_out_key)
#                 occurred_at=now,
#                 created_by=by_user,
#             )
#             mouvement_cree = True
#             created += 1
#         except IntegrityError:
#             # Mouvement déjà créé par une autre transaction (idempotence)
#             mouvement_cree = False

#         # 3) Décrémenter le stock uniquement si on vient de créer le mouvement
#         #    (sinon on risquerait une double décrémentation)
#         if mouvement_cree:
#             updated = (VendorStock.objects
#                     .filter(vendor_id=li.vendor_id, produit_id=li.produit_id, quantite__gte=li.quantite)
#                     .update(quantite=F("quantite") - li.quantite))
#             if not updated:
#                 # Pas assez de stock au moment de la livraison → rollback total (mouvement inclus)
#                 prod_name = getattr(li.produit, "nom", li.produit_id)
#                 raise ValidationError(f"Stock insuffisant pour '{prod_name}' chez ce vendeur au moment de la livraison.")

#     # 4) Marquer livrée si TOUTES les lignes ont leur SALE_OUT
#     nb_mouvements = (InventoryMovement.objects
#                     .filter(movement_type=MovementType.SALE_OUT, vente_ligne__vente_id=v.id)
#                     .count())
#     if nb_mouvements >= total_lignes and total_lignes > 0:
#         if hasattr(v, "marquer_livree") and callable(v.marquer_livree):
#             v.marquer_livree(by_user)
#         elif hasattr(v, "delivery_status") and hasattr(v.__class__, "DELIV_DELIVERED"):
#             v.delivery_status = v.__class__.DELIV_DELIVERED
#             v.save(update_fields=["delivery_status"])

#     return created


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
# def create_sale_out_movements_for_vente(vente, by_user) -> int:
#     v = (
#         Vente.objects
#         .select_for_update()
#         .select_related("facture_vente", "facture_vente__bijouterie")
#         .prefetch_related("produits__produit", "produits__vendor")
#         .get(pk=vente.pk)
#     )

#     facture = getattr(v, "facture_vente", None)
#     if not facture:
#         raise ValidationError("Aucune facture liée à la vente.")
#     if getattr(facture, "status", None) != getattr(facture.__class__, "STAT_PAYE", "paye"):
#         raise ValidationError("La facture n’est pas payée.")
#     if not getattr(facture, "bijouterie_id", None):
#         raise ValidationError("La facture n’a pas de bijouterie (requis pour la sortie de stock).")

#     now = timezone.now()
#     created = 0

#     # ✅ lignes valides seulement
#     lignes = [li for li in v.produits.all() if li.produit_id and li.quantite]
#     total_lignes = len(lignes)

#     for li in lignes:
#         if not li.vendor_id:
#             raise ValidationError(f"La ligne {li.id} n'a pas de vendeur renseigné.")

#         mouvement_cree = False
#         try:
#             InventoryMovement.objects.create(
#                 produit=li.produit,
#                 movement_type=MovementType.SALE_OUT,
#                 qty=li.quantite,
#                 unit_cost=None,
#                 lot=None,
#                 reason=(
#                     f"Livraison facture {facture.numero_facture} / "
#                     f"vente {getattr(v, 'numero_vente', v.id)} / ligne {li.id}"
#                 ),
#                 src_bucket=Bucket.BIJOUTERIE,
#                 src_bijouterie=facture.bijouterie,
#                 dst_bucket=Bucket.EXTERNAL,
#                 dst_bijouterie=None,
#                 achat=None,
#                 achat_ligne=None,
#                 facture=facture,
#                 vente=v,
#                 vente_ligne=li,
#                 occurred_at=now,
#                 created_by=by_user,
#                 vendor=li.vendor,
#             )
#             mouvement_cree = True
#             created += 1

#         except (IntegrityError, DjangoValidationError) as e:
#             # ✅ idempotence : SALE_OUT déjà créé → on ignore
#             msg = str(e)
#             if "sale_out" in msg.lower() or "sale out key" in msg.lower():
#                 mouvement_cree = False
#             else:
#                 raise

#         if mouvement_cree:
#             try:
#                 _consume_vendor_stock_for_product(
#                     vendor=li.vendor,
#                     produit=li.produit,
#                     quantite=li.quantite,
#                 )
#             except (ValidationError, ValueError) as e:
#                 prod_name = getattr(li.produit, "nom", li.produit_id)
#                 raise ValidationError(
#                     f"Stock insuffisant pour '{prod_name}' chez ce vendeur au moment de la livraison: {e}"
#                 )

#     nb_mouvements = (
#         InventoryMovement.objects
#         .filter(movement_type=MovementType.SALE_OUT, vente_ligne__vente_id=v.id)
#         .count()
#     )
#     if nb_mouvements >= total_lignes and total_lignes > 0:
#         if hasattr(v, "marquer_livree") and callable(v.marquer_livree):
#             v.marquer_livree(by_user)
#         elif hasattr(v, "delivery_status") and hasattr(v.__class__, "DELIV_DELIVERED"):
#             v.delivery_status = v.__class__.DELIV_DELIVERED
#             v.save(update_fields=["delivery_status"])

#     return created


@transaction.atomic
def create_sale_out_movements_for_vente(vente, by_user) -> int:
    v = (
        Vente.objects
        .select_for_update()
        .select_related("facture_vente", "facture_vente__bijouterie")
        .prefetch_related("produits__produit", "produits__vendor")
        .get(pk=vente.pk)
    )

    facture = getattr(v, "facture_vente", None)
    if not facture:
        raise ValidationError("Aucune facture liée à la vente.")
    if getattr(facture, "status", None) != getattr(facture.__class__, "STAT_PAYE", "paye"):
        raise ValidationError("La facture n’est pas payée.")
    if not getattr(facture, "bijouterie_id", None):
        raise ValidationError("La facture n’a pas de bijouterie (requis pour la sortie de stock).")

    now = timezone.now()
    created = 0

    lignes = [li for li in v.produits.all() if li.produit_id and li.quantite]
    total_lignes = len(lignes)

    for li in lignes:
        if not li.vendor_id:
            raise ValidationError(f"La ligne {li.id} n'a pas de vendeur renseigné.")

        # 1) créer ou récupérer le mouvement
        try:
            mvt = InventoryMovement.objects.create(
                produit=li.produit,
                movement_type=MovementType.SALE_OUT,
                qty=li.quantite,
                unit_cost=None,
                lot=None,
                reason=(
                    f"Livraison facture {facture.numero_facture} / "
                    f"vente {getattr(v, 'numero_vente', v.id)} / ligne {li.id}"
                ),
                src_bucket=Bucket.BIJOUTERIE,
                src_bijouterie=facture.bijouterie,
                dst_bucket=Bucket.EXTERNAL,
                dst_bijouterie=None,
                achat=None,
                achat_ligne=None,
                facture=facture,
                vente=v,
                vente_ligne=li,
                occurred_at=now,
                created_by=by_user,
                vendor=li.vendor,
            )
            created += 1

        except (IntegrityError, DjangoValidationError):
            mvt = InventoryMovement.objects.get(
                movement_type=MovementType.SALE_OUT,
                vente_ligne_id=li.id,
            )

        # 2) ✅ consommer stock si pas encore consommé
        if not mvt.stock_consumed:
            try:
                _consume_vendor_stock_for_product(
                    vendor=li.vendor,
                    produit=li.produit,
                    quantite=li.quantite,
                )
            except (ValidationError, ValueError) as e:
                prod_name = getattr(li.produit, "nom", li.produit_id)
                raise ValidationError(
                    f"Stock insuffisant pour '{prod_name}' chez ce vendeur au moment de la livraison: {e}"
                )
            mvt.stock_consumed = True
            mvt.save(update_fields=["stock_consumed"])

    nb_mouvements = (
        InventoryMovement.objects
        .filter(movement_type=MovementType.SALE_OUT, vente_ligne__vente_id=v.id)
        .count()
    )
    if nb_mouvements >= total_lignes and total_lignes > 0:
        if hasattr(v, "marquer_livree") and callable(v.marquer_livree):
            v.marquer_livree(by_user)
        elif hasattr(v, "delivery_status") and hasattr(v.__class__, "DELIV_DELIVERED"):
            v.delivery_status = v.__class__.DELIV_DELIVERED
            v.save(update_fields=["delivery_status"])

    return created

