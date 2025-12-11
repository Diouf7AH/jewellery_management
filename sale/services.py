from decimal import Decimal

from django.core.exceptions import ValidationError
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
    Décrémente le stock vendeur pour un produit donné en FIFO par ProduitLine (lot).
    - décrémente VendorStock.quantite_disponible
    - décrémente ProduitLine.quantite_restante
    Retourne: liste de dicts {"pl_id": ..., "qte": ...}
    """
    remaining = int(quantite)
    if remaining <= 0:
        raise ValueError("Quantité à vendre doit être > 0")

    vstocks = (
        VendorStock.objects
        .select_for_update()
        .select_related("produit_line", "produit_line__lot")
        .filter(vendor=vendor, produit_line__produit=produit, quantite_disponible__gt=0)
        .order_by("produit_line__lot__received_at", "produit_line_id")
    )

    moves = []
    for vs in vstocks:
        if remaining == 0:
            break
        dispo = int(vs.quantite_disponible or 0)
        if dispo <= 0:
            continue
        take = min(dispo, remaining)

        # 1) décrémente la dispo vendeur (optimiste + verrou)
        updated_vs = VendorStock.objects.filter(pk=vs.pk, quantite_disponible__gte=take)\
                                        .update(quantite_disponible=F("quantite_disponible") - take)
        if not updated_vs:
            raise ValueError("Conflit de stock détecté, réessayez.")

        # 2) décrémente la quantité restante de la ProduitLine
        from purchase.models import ProduitLine
        updated_pl = ProduitLine.objects.filter(pk=vs.produit_line_id, quantite_restante__gte=take)\
                                        .update(quantite_restante=F("quantite_restante") - take)
        if not updated_pl:
            # rollback local VS pour rester cohérent
            VendorStock.objects.filter(pk=vs.pk).update(quantite_disponible=F("quantite_disponible") + take)
            raise ValueError("Stock de lot insuffisant (quantite_restante).")

        moves.append({"pl_id": vs.produit_line_id, "qte": take})
        remaining -= take

    if remaining > 0:
        raise ValueError(f"Stock vendeur insuffisant pour '{getattr(produit, 'nom', 'produit')}'. Manque {remaining}.")

    return moves


@transaction.atomic
def create_sale_out_movements_for_vente(vente, by_user) -> int:
    """
    Livraison d'une vente :
      - Vérifie facture payée & bijouterie présente
      - Idempotent par ligne : un seul SALE_OUT par vente_ligne (protégé par contrainte UNIQUE via sale_out_key)
      - Crée le mouvement d’abord, PUIS consomme le stock vendeur (via _consume_vendor_stock_for_product)
      - Marque la vente livrée si toutes les lignes ont leur SALE_OUT

    Retourne le nombre de mouvements créés à cet appel.
    """
    # 1) Verrou vente + dépendances
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

    lignes = list(v.produits.all())  # related_name des VenteProduit
    total_lignes = len(lignes)

    for li in lignes:
        if not li.produit_id or not li.quantite:
            continue
        if not li.vendor_id:
            raise ValidationError(f"La ligne {li.id} n'a pas de vendeur renseigné.")

        # 2) Essayer de créer le mouvement en premier (idempotence forte via UNIQUE sale_out_key)
        mouvement_cree = False
        try:
            InventoryMovement.objects.create(
                produit=li.produit,
                movement_type=MovementType.SALE_OUT,
                qty=li.quantite,
                unit_cost=None,  # à enrichir plus tard si tu veux un coût moyen
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
                vente_ligne=li,      # ← clé d’unicité indirecte via sale_out_key dans save()
                occurred_at=now,
                created_by=by_user,
                vendor=li.vendor,
            )
            mouvement_cree = True
            created += 1
        except IntegrityError:
            # Mouvement déjà créé par une autre transaction (idempotence)
            mouvement_cree = False

        # 3) Consommer le stock vendeur UNIQUEMENT si on vient de créer le mouvement
        if mouvement_cree:
            try:
                _consume_vendor_stock_for_product(
                    vendor=li.vendor,
                    produit=li.produit,
                    quantite=li.quantite,
                )
            except (ValidationError, ValueError) as e:
                prod_name = getattr(li.produit, "nom", li.produit_id)
                # On relance une ValidationError → transaction.atomic rollback :
                #   - le mouvement SALE_OUT
                #   - la conso stock partielle
                raise ValidationError(
                    f"Stock insuffisant pour '{prod_name}' chez ce vendeur au moment de la livraison: {e}"
                )

    # 4) Marquer livrée si TOUTES les lignes ont leur SALE_OUT
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
