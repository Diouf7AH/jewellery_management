from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from inventory.models import Bucket, InventoryMovement, MovementType
from purchase.models import ProduitLine
from stock.models import Stock, VendorStock
from store.models import Bijouterie
from vendor.models import Vendor

# @transaction.atomic
# def transfer_reserve_to_bijouterie(
#     *, bijouterie_id: int, mouvements: list[dict], note: str = "", user=None
# ):
#     """
#     mouvements: [{"produit_line_id": int, "quantite": int}, ...]
#     Déplace la quantité depuis Réserve (bijouterie=None) vers bijouterie_id
#     + journalise un InventoryMovement(ALLOCATE) par ligne.
#     """
#     # 0) Bijouterie existe ?
#     bijouterie = (
#         Bijouterie.objects
#         .select_for_update()
#         .get(id=bijouterie_id)
#     )

#     # 1) Regrouper si doublons sur la même ligne
#     wanted = defaultdict(int)
#     for mv in mouvements:
#         pl_id = int(mv["produit_line_id"])
#         # on accepte "quantite" ou "transfere" selon ton serializer
#         qty = int(mv.get("quantite") or mv.get("transfere") or 0)
#         if qty <= 0:
#             raise ValueError(f"Quantité invalide pour produit_line_id={pl_id}: {qty}")
#         wanted[pl_id] += qty

#     # 2) Lock des ProduitLine concernées
#     lignes = (
#         ProduitLine.objects
#         .select_for_update()
#         .filter(id__in=wanted.keys())
#         .select_related("lot", "produit")
#     )
#     found_ids = {pl.id for pl in lignes}
#     missing = set(wanted.keys()) - found_ids
#     if missing:
#         raise ValueError(f"Lignes introuvables: {sorted(list(missing))}")

#     results = []

#     for pl in lignes:
#         qty = wanted[pl.id]

#         # --- 3) STOCK : RÉSERVE (bijouterie = NULL) ---
#         stock_res = (
#             Stock.objects
#             .select_for_update()
#             .filter(produit_line=pl, bijouterie__isnull=True)
#             .first()
#         )
#         if not stock_res:
#             raise ValueError(f"Réserve inexistante pour la ligne {pl.id}")

#         if (stock_res.quantite_disponible or 0) < qty:
#             raise ValueError(
#                 f"Quantité insuffisante en Réserve pour la ligne {pl.id} "
#                 f"(demande {qty}, dispo {stock_res.quantite_disponible})"
#             )

#         # ❗ On NE TOUCHE PAS à quantite_allouee en réserve
#         stock_res.quantite_disponible = (stock_res.quantite_disponible or 0) - qty
#         if stock_res.quantite_disponible < 0:
#             raise ValueError(f"Incohérence sur Réserve (ligne {pl.id})")
#         stock_res.save(update_fields=["quantite_disponible"])

#         # --- 4) STOCK : DESTINATION = BIJOUTERIE ---
#         stock_dst = (
#             Stock.objects
#             .select_for_update()
#             .filter(produit_line=pl, bijouterie=bijouterie)
#             .first()
#         )
#         if not stock_dst:
#             stock_dst = Stock.objects.create(
#                 produit_line=pl,
#                 bijouterie=bijouterie,
#                 quantite_allouee=0,
#                 quantite_disponible=0,
#             )

#         stock_dst.quantite_allouee = (stock_dst.quantite_allouee or 0) + qty
#         stock_dst.quantite_disponible = (stock_dst.quantite_disponible or 0) + qty
#         stock_dst.save(update_fields=["quantite_allouee", "quantite_disponible"])

#         # --- 5) INVENTORY MOVEMENT : ALLOCATE (RESERVED -> BIJOUTERIE) ---
#         lot = getattr(pl, "lot", None)
#         achat = getattr(lot, "achat", None) if lot else None

#         InventoryMovement.objects.create(
#             produit=pl.produit,
#             movement_type=MovementType.ALLOCATE,
#             qty=qty,
#             unit_cost=None,  # ou calcule si tu as l'info (ex: lot.prix_gramme_achat * poids)
#             lot=lot,
#             achat=achat,
#             achat_ligne=lot,  # si tu utilises ce champ comme "ligne d'achat = lot"
#             reason=note or "",
#             src_bucket=Bucket.RESERVED,
#             src_bijouterie=None,
#             dst_bucket=Bucket.BIJOUTERIE,
#             dst_bijouterie=bijouterie,
#             facture=None,
#             vente=None,
#             vente_ligne=None,
#             occurred_at=timezone.now(),
#             created_by=user if user and user.is_authenticated else None,
#             vendor=None,
#         )

#         results.append({
#             "produit_line_id": pl.id,
#             "transfere": qty,
#             "reserve_disponible": stock_res.quantite_disponible,
#             "bijouterie_disponible": stock_dst.quantite_disponible,
#         })

#     return {
#         "bijouterie_id": bijouterie.id,
#         "bijouterie_nom": bijouterie.nom,
#         "lignes": results,
#         "note": note or "",
#     }


@transaction.atomic
def transfer_reserve_to_bijouterie(
    *, bijouterie_id: int, mouvements: list[dict], note: str = "", user=None
):
    """
    mouvements: [{"produit_line_id": int, "quantite": int} | {"produit_line_id": int, "transfere": int}, ...]

    ERP-style (allocation boutique) :
      - Réserve (bijouterie NULL) : disponible -= qty
      - Bijouterie : allouee += qty   (stock affecté, non libre)
      - Bijouterie : disponible ne bouge pas (reste 0)
      - Log InventoryMovement(ALLOCATE) : RESERVED -> BIJOUTERIE
    """

    # 0) Lock bijouterie
    bijouterie = Bijouterie.objects.select_for_update().get(id=bijouterie_id)

    # 1) Regrouper les doublons dans l’input
    wanted = defaultdict(int)
    for mv in mouvements:
        pl_id = int(mv["produit_line_id"])
        qty = int(mv.get("quantite") or mv.get("transfere") or 0)
        if qty <= 0:
            raise ValueError(f"Quantité invalide pour produit_line_id={pl_id}: {qty}")
        wanted[pl_id] += qty

    # 2) Lock des ProduitLine concernées
    lignes = (
        ProduitLine.objects.select_for_update()
        .filter(id__in=wanted.keys())
        .select_related("lot", "produit")
    )
    found_ids = {pl.id for pl in lignes}
    missing = set(wanted.keys()) - found_ids
    if missing:
        raise ValueError(f"Lignes introuvables: {sorted(list(missing))}")

    results = []

    for pl in lignes:
        qty = wanted[pl.id]

        # --- 3) STOCK : RÉSERVE (bijouterie = NULL) ---
        stock_res = (
            Stock.objects
            .select_for_update()
            .filter(produit_line=pl, bijouterie__isnull=True)
            .first()
        )

        if not stock_res:
            raise ValueError(f"Réserve inexistante pour la ligne {pl.id}")

        if stock_res.quantite_disponible < qty:
            raise ValueError(
                f"Quantité insuffisante en Réserve pour la ligne {pl.id} "
                f"(demande {qty}, dispo {stock_res.quantite_disponible})"
            )

        # ➖ Réserve : disponible diminue
        Stock.objects.filter(id=stock_res.id).update(
            quantite_disponible=F("quantite_disponible") - qty
        )
        stock_res.refresh_from_db()

        # --- 4) STOCK : DESTINATION = BIJOUTERIE ---
        stock_dst, _ = (
            Stock.objects
            .select_for_update()
            .get_or_create(
                produit_line=pl,
                bijouterie=bijouterie,
                defaults={
                    "quantite_allouee": 0,
                    "quantite_disponible": 0,
                },
            )
        )

        # ✅ CORRECTION ERP : stock devient VENDABLE
        Stock.objects.filter(id=stock_dst.id).update(
            quantite_allouee=F("quantite_allouee") + qty,
            quantite_disponible=F("quantite_disponible") + qty,
        )
        stock_dst.refresh_from_db()

        # --- 5) INVENTORY MOVEMENT : ALLOCATE ---
        InventoryMovement.objects.create(
            produit=pl.produit,
            movement_type=MovementType.ALLOCATE,
            qty=qty,
            lot=pl.lot,
            achat=getattr(pl.lot, "achat", None),
            src_bucket=Bucket.RESERVED,
            dst_bucket=Bucket.BIJOUTERIE,
            dst_bijouterie=bijouterie,
            reason=note or "",
            created_by=user if user and user.is_authenticated else None,
        )

        results.append({
            "produit_line_id": pl.id,
            "transfere": qty,
            "reserve_disponible": stock_res.quantite_disponible,
            "quantite_allouee_a_bijouterie": stock_dst.quantite_allouee,
            "quantite_disponible_bijouterie": stock_dst.quantite_disponible,
        })

    return {
        "bijouterie_id": bijouterie.id,
        "bijouterie_nom": bijouterie.nom,
        "lignes": results,
        "note": note or "",
    }

# -----------------------Bijouterie To vendeur------------------------
# @transaction.atomic
# def transfer_bijouterie_to_vendor(*, vendor_id:int, mouvements:list[dict], note:str=""):
#     vendor = Vendor.objects.select_related("bijouterie").select_for_update().get(id=vendor_id)
#     bijouterie = vendor.bijouterie

#     # regrouper les demandes
#     wanted = defaultdict(int)
#     for mv in mouvements:
#         wanted[int(mv["produit_line_id"])] += int(mv["quantite"])

#     # lock des lignes
#     lignes = (ProduitLine.objects
#               .select_for_update()
#               .filter(id__in=wanted.keys())
#               .select_related("produit", "lot"))
#     found_ids = {pl.id for pl in lignes}
#     missing = set(wanted.keys()) - found_ids
#     if missing:
#         raise ValueError(f"Lignes introuvables: {sorted(list(missing))}")

#     results = []
#     for pl in lignes:
#         qty = wanted[pl.id]

#         # Source = stock de la bijouterie du vendeur
#         stock_src = (Stock.objects
#                      .select_for_update()
#                      .filter(produit_line=pl, bijouterie=bijouterie)
#                      .first())
#         if not stock_src:
#             raise ValueError(f"Aucun stock en bijouterie '{bijouterie.nom}' pour la ligne {pl.id}")

#         if (stock_src.quantite_disponible or 0) < qty:
#             raise ValueError(
#                 f"Insuffisant en bijouterie '{bijouterie.nom}' pour la ligne {pl.id} "
#                 f"(demande {qty}, dispo {stock_src.quantite_disponible})"
#             )

#         # Destination = VendorStock (peut ne pas exister au premier transfert)
#         vstock = (VendorStock.objects
#                   .select_for_update()
#                   .filter(produit_line=pl, vendor=vendor)
#                   .first())
#         if not vstock:
#             vstock = VendorStock.objects.create(
#                 produit_line=pl, vendor=vendor,
#                 quantite_allouee=0, quantite_disponible=0
#             )

#         # Mouvement: Bijouterie --
#         stock_src.quantite_allouee = (stock_src.quantite_allouee or 0) - qty
#         stock_src.quantite_disponible = (stock_src.quantite_disponible or 0) - qty
#         if stock_src.quantite_allouee < 0 or stock_src.quantite_disponible < 0:
#             raise ValueError(f"Incohérence sur bijouterie '{bijouterie.nom}' (ligne {pl.id})")
#         stock_src.save(update_fields=["quantite_allouee", "quantite_disponible"])

#         # Mouvement: Vendeur ++
#         vstock.quantite_allouee = (vstock.quantite_allouee or 0) + qty
#         vstock.quantite_disponible = (vstock.quantite_disponible or 0) + qty
#         vstock.save(update_fields=["quantite_allouee", "quantite_disponible"])

#         results.append({
#             "produit_line_id": pl.id,
#             "transfere": qty,
#             "bijouterie_disponible": stock_src.quantite_disponible,
#             "vendor_disponible": vstock.quantite_disponible,
#         })

#     # TODO: journaliser 'note' si tu as un modèle de mouvements
#     return {
#         "vendor_id": vendor.id,
#         "vendeur_nom": vendor.nom,
#         "bijouterie_id": bijouterie.id,
#         "bijouterie_nom": bijouterie.nom,
#         "lignes": results,
#         "note": note or "",
#     }

@transaction.atomic
def transfer_bijouterie_to_vendor(
    *, vendor_id: int, mouvements: list[dict], note: str = "", user=None
):
    # 🔐 On verrouille le vendeur + sa bijouterie
    vendor = (
        Vendor.objects
        .select_related("bijouterie")
        .select_for_update()
        .get(id=vendor_id)
    )
    bijouterie = vendor.bijouterie

    # ⚠️ Sécu : vendeur sans bijouterie
    if not bijouterie:
        raise ValidationError(f"Le vendeur #{vendor.id} n'est rattaché à aucune bijouterie.")

    # --- Regrouper les demandes par ProduitLine ---
    wanted = defaultdict(int)
    for mv in mouvements:
        pl_id = int(mv["produit_line_id"])
        qty = int(mv["quantite"])
        if qty <= 0:
            raise ValidationError(f"Quantité invalide pour produit_line_id={pl_id}: {qty}")
        wanted[pl_id] += qty

    if not wanted:
        raise ValidationError("Aucune ligne de mouvement fournie.")

    # --- Lock des lignes ProduitLine ---
    lignes = (
        ProduitLine.objects
        .select_for_update()
        .filter(id__in=wanted.keys())
        .select_related("produit", "lot")
    )
    found_ids = {pl.id for pl in lignes}
    missing = set(wanted.keys()) - found_ids
    if missing:
        raise ValueError(f"Lignes introuvables: {sorted(list(missing))}")

    results = []

    for pl in lignes:
        qty = wanted[pl.id]

        # Source = stock de la bijouterie du vendeur
        stock_src = (
            Stock.objects
            .select_for_update()
            .filter(produit_line=pl, bijouterie=bijouterie)
            .first()
        )
        if not stock_src:
            raise ValueError(
                f"Aucun stock en bijouterie '{bijouterie.nom}' pour la ligne {pl.id}"
            )

        if (stock_src.quantite_disponible or 0) < qty:
            raise ValueError(
                f"Insuffisant en bijouterie '{bijouterie.nom}' pour la ligne {pl.id} "
                f"(demande {qty}, dispo {stock_src.quantite_disponible})"
            )

        # Destination = VendorStock (peut ne pas exister au premier transfert)
        vstock = (
            VendorStock.objects
            .select_for_update()
            .filter(produit_line=pl, vendor=vendor)
            .first()
        )
        if not vstock:
            vstock = VendorStock.objects.create(
                produit_line=pl,
                vendor=vendor,
                quantite_allouee=0,
                quantite_vendue=0,
            )

        # --- Mouvement côté bijouterie ---
        # ❗ On NE touche PLUS quantite_allouee ici (comme pour la réserve)
        stock_src.quantite_disponible = (stock_src.quantite_disponible or 0) - qty
        if stock_src.quantite_disponible < 0:
            raise ValueError(
                f"Incohérence sur bijouterie '{bijouterie.nom}' (ligne {pl.id})"
            )
        stock_src.save(update_fields=["quantite_disponible"])

        # --- Mouvement côté vendeur (on augmente seulement l’alloué) ---
        vstock.quantite_allouee = (vstock.quantite_allouee or 0) + qty
        vstock.save(update_fields=["quantite_allouee"])

        # --- INVENTORY MOVEMENT : VENDOR_ASSIGN (log interne) ---
        lot = getattr(pl, "lot", None)
        achat = getattr(lot, "achat", None) if lot else None

        InventoryMovement.objects.create(
            produit=pl.produit,
            movement_type=MovementType.VENDOR_ASSIGN,
            qty=qty,
            unit_cost=None,          # tu peux le renseigner si tu as le coût unitaire
            lot=lot,
            achat=achat,
            achat_ligne=lot,
            reason=note or "",
            # Log interne : on garde la notion de bijouterie source
            src_bucket=Bucket.BIJOUTERIE,
            src_bijouterie=bijouterie,
            dst_bucket=None,
            dst_bijouterie=None,
            facture=None,
            vente=None,
            vente_ligne=None,
            occurred_at=timezone.now(),
            created_by=user if user and user.is_authenticated else None,
            vendor=vendor,
        )

        results.append({
            "produit_line_id": pl.id,
            "transfere": qty,
            "bijouterie_disponible": stock_src.quantite_disponible,
            "vendor_disponible": vstock.quantite_disponible,  # propriété read-only
        })

    return {
        "vendor_id": vendor.id,
        "vendeur_nom": getattr(vendor, "nom", "") or getattr(vendor, "full_name", "") or "",
        "bijouterie_id": bijouterie.id,
        "bijouterie_nom": bijouterie.nom,
        "lignes": results,
        "note": note or "",
    }
    
# ------------------End Bijouterie to vendeur------------------------