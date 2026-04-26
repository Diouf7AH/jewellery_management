from collections import defaultdict
from typing import Dict, List

from django.core.exceptions import ValidationError
from django.db import models, transaction
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


# @transaction.atomic
# def transfer_reserve_to_bijouterie(
#     *, bijouterie_id: int, mouvements: list[dict], note: str = "", user=None
# ):
#     """
#     mouvements: [{"produit_line_id": int, "quantite": int} | {"produit_line_id": int, "transfere": int}, ...]

#     ERP-style (allocation boutique) :
#       - Réserve (bijouterie NULL) : disponible -= qty
#       - Bijouterie : allouee += qty   (stock affecté, non libre)
#       - Bijouterie : disponible ne bouge pas (reste 0)
#       - Log InventoryMovement(ALLOCATE) : RESERVED -> BIJOUTERIE
#     """

#     # 0) Lock bijouterie
#     bijouterie = Bijouterie.objects.select_for_update().get(id=bijouterie_id)

#     # 1) Regrouper les doublons dans l’input
#     wanted = defaultdict(int)
#     for mv in mouvements:
#         pl_id = int(mv["produit_line_id"])
#         qty = int(mv.get("quantite") or mv.get("transfere") or 0)
#         if qty <= 0:
#             raise ValueError(f"Quantité invalide pour produit_line_id={pl_id}: {qty}")
#         wanted[pl_id] += qty

#     # 2) Lock des ProduitLine concernées
#     lignes = (
#         ProduitLine.objects.select_for_update()
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

#         if stock_res.quantite_disponible < qty:
#             raise ValueError(
#                 f"Quantité insuffisante en Réserve pour la ligne {pl.id} "
#                 f"(demande {qty}, dispo {stock_res.quantite_disponible})"
#             )

#         # ➖ Réserve : disponible diminue
#         Stock.objects.filter(id=stock_res.id).update(
#             quantite_disponible=F("quantite_disponible") - qty
#         )
#         stock_res.refresh_from_db()

#         # --- 4) STOCK : DESTINATION = BIJOUTERIE ---
#         stock_dst, _ = (
#             Stock.objects
#             .select_for_update()
#             .get_or_create(
#                 produit_line=pl,
#                 bijouterie=bijouterie,
#                 defaults={
#                     "quantite_allouee": 0,
#                     "quantite_disponible": 0,
#                 },
#             )
#         )

#         # ✅ CORRECTION ERP : stock devient VENDABLE
#         Stock.objects.filter(id=stock_dst.id).update(
#             quantite_allouee=F("quantite_allouee") + qty,
#             quantite_disponible=F("quantite_disponible") + qty,
#         )
#         stock_dst.refresh_from_db()

#         # --- 5) INVENTORY MOVEMENT : ALLOCATE ---
#         InventoryMovement.objects.create(
#             produit=pl.produit,
#             movement_type=MovementType.ALLOCATE,
#             qty=qty,
#             lot=pl.lot,
#             achat=getattr(pl.lot, "achat", None),
#             src_bucket=Bucket.RESERVED,
#             dst_bucket=Bucket.BIJOUTERIE,
#             dst_bijouterie=bijouterie,
#             reason=note or "",
#             created_by=user if user and user.is_authenticated else None,
#         )

#         results.append({
#             "produit_line_id": pl.id,
#             "transfere": qty,
#             "reserve_disponible": stock_res.quantite_disponible,
#             "quantite_allouee_a_bijouterie": stock_dst.quantite_allouee,
#             "quantite_disponible_bijouterie": stock_dst.quantite_disponible,
#         })

#     return {
#         "bijouterie_id": bijouterie.id,
#         "bijouterie_nom": bijouterie.nom,
#         "lignes": results,
#         "note": note or "",
#     }

@transaction.atomic
def transfer_reserve_to_bijouterie_by_produit(
    *,
    bijouterie_id: int,
    lignes: List[dict],   # [{"produit_id": int, "transfere": int}]
    note: str = "",
    user=None,
) -> dict:
    bijouterie = Bijouterie.objects.select_for_update().get(id=bijouterie_id)

    # 1) regrouper doublons produit_id
    wanted = defaultdict(int)
    for row in lignes:
        pid = int(row["produit_id"])
        qty = int(row.get("transfere") or 0)
        if qty <= 0:
            raise ValueError(f"Quantité invalide pour produit_id={pid}: {qty}")
        wanted[pid] += qty

    results = []

    for produit_id, demande in wanted.items():
        qty_need = demande
        consommations = []
        produit_nom = None

        # 2) FIFO: ProduitLine du produit
        pls = (
            ProduitLine.objects.select_for_update()
            .filter(produit_id=produit_id)
            .select_related("lot", "produit")
            .order_by("lot__received_at", "id")
        )
        if not pls.exists():
            raise ValueError(f"Aucune ProduitLine trouvée pour produit_id={produit_id}")

        for pl in pls:
            if qty_need <= 0:
                break

            if produit_nom is None:
                produit_nom = getattr(pl.produit, "nom", None)

            # Stock réserve pour cette PL
            stock_res = (
                Stock.objects.select_for_update()
                .filter(produit_line=pl, bijouterie__isnull=True)
                .first()
            )
            if not stock_res or stock_res.quantite_disponible <= 0:
                continue

            take = min(qty_need, stock_res.quantite_disponible)

            # Stock destination (bijouterie) pour cette PL
            stock_dst, _ = Stock.objects.select_for_update().get_or_create(
                produit_line=pl,
                bijouterie=bijouterie,
                defaults={"quantite_allouee": 0, "quantite_disponible": 0},
            )

            # ✅ Réserve: dispo -= take ; allouée reste 0
            Stock.objects.filter(id=stock_res.id).update(
                quantite_allouee=0,
                quantite_disponible=F("quantite_disponible") - take,
                updated_at=timezone.now(),
            )

            # ✅ Bijouterie: allouée += take ; dispo inchangé (NON VENDABLE)
            Stock.objects.filter(id=stock_dst.id).update(
                quantite_allouee=F("quantite_allouee") + take,
                updated_at=timezone.now(),
            )

            # Mouvement inventory: ALLOCATE (RESERVED -> BIJOUTERIE)
            InventoryMovement.objects.create(
                produit=pl.produit,
                movement_type=MovementType.ALLOCATE,
                qty=take,
                lot=pl.lot,
                achat=getattr(pl.lot, "achat", None),
                src_bucket=Bucket.RESERVED,
                dst_bucket=Bucket.BIJOUTERIE,
                dst_bijouterie=bijouterie,
                reason=note or "Allocation Réserve → Bijouterie",
                created_by=user if user and user.is_authenticated else None,
                occurred_at=timezone.now(),
            )

            stock_res.refresh_from_db()
            stock_dst.refresh_from_db()

            consommations.append({
                "produit_line_id": pl.id,
                "lot_id": pl.lot_id,
                "numero_lot": getattr(pl.lot, "numero_lot", None),
                "qty": int(take),
                "reserve_disponible_apres": int(stock_res.quantite_disponible),
                "bijouterie_allouee_apres": int(stock_dst.quantite_allouee),
                "bijouterie_disponible_apres": int(stock_dst.quantite_disponible),  # reste 0
            })

            qty_need -= take

        if qty_need > 0:
            raise ValueError(f"Stock réserve insuffisant pour produit_id={produit_id}. Manque {qty_need}.")

        # Totaux (après transfert)
        reserve_total = (
            Stock.objects
            .filter(bijouterie__isnull=True, produit_line__produit_id=produit_id)
            .aggregate(total=models.Sum("quantite_disponible"))["total"] or 0
        )
        bij_allouee_total = (
            Stock.objects
            .filter(bijouterie_id=bijouterie_id, produit_line__produit_id=produit_id)
            .aggregate(total=models.Sum("quantite_allouee"))["total"] or 0
        )
        bij_dispo_total = (
            Stock.objects
            .filter(bijouterie_id=bijouterie_id, produit_line__produit_id=produit_id)
            .aggregate(total=models.Sum("quantite_disponible"))["total"] or 0
        )

        results.append({
            "produit_id": produit_id,
            "produit_nom": produit_nom,
            "demande": int(demande),
            "transfere": int(demande),
            "reserve_disponible_total": int(reserve_total),
            "bijouterie_allouee_total": int(bij_allouee_total),
            "bijouterie_disponible_total": int(bij_dispo_total),  # normalement 0 ici
            "consommations": consommations,
        })

    return {
        "bijouterie_id": bijouterie.id,
        "bijouterie_nom": bijouterie.nom,
        "lignes": results,
        "note": note or "",
    }
    


@transaction.atomic
def receive_bijouterie_stock_by_produit(
    *,
    bijouterie_id: int,
    lignes: List[dict],  # [{"produit_id": int, "quantite": int}]
    note: str = "",
    user=None,
) -> dict:
    bijouterie = Bijouterie.objects.select_for_update().get(id=bijouterie_id)

    wanted = defaultdict(int)
    for row in lignes:
        pid = int(row["produit_id"])
        qty = int(row.get("quantite") or 0)
        if qty <= 0:
            raise ValueError(f"Quantité invalide pour produit_id={pid}: {qty}")
        wanted[pid] += qty

    results = []

    for produit_id, demande in wanted.items():
        qty_need = demande
        produit_nom = None
        consommations = []

        # FIFO: mêmes ProduitLine, mais on consomme "allouée" en boutique
        pls = (
            ProduitLine.objects.select_for_update()
            .filter(produit_id=produit_id)
            .select_related("lot", "produit")
            .order_by("lot__received_at", "id")
        )
        if not pls.exists():
            raise ValueError(f"Aucune ProduitLine trouvée pour produit_id={produit_id}")

        for pl in pls:
            if qty_need <= 0:
                break

            if produit_nom is None:
                produit_nom = getattr(pl.produit, "nom", None)

            stock_bij = (
                Stock.objects.select_for_update()
                .filter(produit_line=pl, bijouterie_id=bijouterie_id)
                .first()
            )
            if not stock_bij or stock_bij.quantite_allouee <= 0:
                continue

            take = min(qty_need, stock_bij.quantite_allouee)

            # ✅ allouée -= take ; dispo += take
            Stock.objects.filter(id=stock_bij.id).update(
                quantite_allouee=F("quantite_allouee") - take,
                quantite_disponible=F("quantite_disponible") + take,
                updated_at=timezone.now(),
            )

            # Mouvement inventory: RECEIVE/PUTAWAY (interne)
            InventoryMovement.objects.create(
                produit=pl.produit,
                movement_type=getattr(MovementType, "RECEIVE", MovementType.ALLOCATE),  # fallback si pas encore
                qty=take,
                lot=pl.lot,
                achat=getattr(pl.lot, "achat", None),
                src_bucket=Bucket.BIJOUTERIE,
                src_bijouterie=bijouterie,
                dst_bucket=Bucket.BIJOUTERIE,
                dst_bijouterie=bijouterie,
                reason=note or "Réception boutique (allouée → disponible)",
                created_by=user if user and user.is_authenticated else None,
                occurred_at=timezone.now(),
            )

            stock_bij.refresh_from_db()

            consommations.append({
                "produit_line_id": pl.id,
                "lot_id": pl.lot_id,
                "numero_lot": getattr(pl.lot, "numero_lot", None),
                "qty": int(take),
                "bijouterie_allouee_apres": int(stock_bij.quantite_allouee),
                "bijouterie_disponible_apres": int(stock_bij.quantite_disponible),
            })

            qty_need -= take

        if qty_need > 0:
            raise ValueError(f"Allouée insuffisante en bijouterie pour produit_id={produit_id}. Manque {qty_need}.")

        # Totaux après
        bij_allouee_total = (
            Stock.objects.filter(bijouterie_id=bijouterie_id, produit_line__produit_id=produit_id)
            .aggregate(total=models.Sum("quantite_allouee"))["total"] or 0
        )
        bij_dispo_total = (
            Stock.objects.filter(bijouterie_id=bijouterie_id, produit_line__produit_id=produit_id)
            .aggregate(total=models.Sum("quantite_disponible"))["total"] or 0
        )

        results.append({
            "produit_id": produit_id,
            "produit_nom": produit_nom,
            "demande": int(demande),
            "recu": int(demande),
            "bijouterie_allouee_total": int(bij_allouee_total),
            "bijouterie_disponible_total": int(bij_dispo_total),
            "consommations": consommations,
        })

    return {
        "bijouterie_id": bijouterie.id,
        "bijouterie_nom": bijouterie.nom,
        "note": note or "",
        "lignes": results,
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

# @transaction.atomic
# def transfer_bijouterie_to_vendor(
#     *, vendor_id: int, mouvements: list[dict], note: str = "", user=None
# ):
#     # 🔐 On verrouille le vendeur + sa bijouterie
#     vendor = (
#         Vendor.objects
#         .select_related("bijouterie")
#         .select_for_update()
#         .get(id=vendor_id)
#     )
#     bijouterie = vendor.bijouterie

#     # ⚠️ Sécu : vendeur sans bijouterie
#     if not bijouterie:
#         raise ValidationError(f"Le vendeur #{vendor.id} n'est rattaché à aucune bijouterie.")

#     # --- Regrouper les demandes par ProduitLine ---
#     wanted = defaultdict(int)
#     for mv in mouvements:
#         pl_id = int(mv["produit_line_id"])
#         qty = int(mv["quantite"])
#         if qty <= 0:
#             raise ValidationError(f"Quantité invalide pour produit_line_id={pl_id}: {qty}")
#         wanted[pl_id] += qty

#     if not wanted:
#         raise ValidationError("Aucune ligne de mouvement fournie.")

#     # --- Lock des lignes ProduitLine ---
#     lignes = (
#         ProduitLine.objects
#         .select_for_update()
#         .filter(id__in=wanted.keys())
#         .select_related("produit", "lot")
#     )
#     found_ids = {pl.id for pl in lignes}
#     missing = set(wanted.keys()) - found_ids
#     if missing:
#         raise ValueError(f"Lignes introuvables: {sorted(list(missing))}")

#     results = []

#     for pl in lignes:
#         qty = wanted[pl.id]

#         # Source = stock de la bijouterie du vendeur
#         stock_src = (
#             Stock.objects
#             .select_for_update()
#             .filter(produit_line=pl, bijouterie=bijouterie)
#             .first()
#         )
#         if not stock_src:
#             raise ValueError(
#                 f"Aucun stock en bijouterie '{bijouterie.nom}' pour la ligne {pl.id}"
#             )

#         if (stock_src.quantite_disponible or 0) < qty:
#             raise ValueError(
#                 f"Insuffisant en bijouterie '{bijouterie.nom}' pour la ligne {pl.id} "
#                 f"(demande {qty}, dispo {stock_src.quantite_disponible})"
#             )

#         # Destination = VendorStock (peut ne pas exister au premier transfert)
#         vstock = (
#             VendorStock.objects
#             .select_for_update()
#             .filter(produit_line=pl, vendor=vendor)
#             .first()
#         )
#         if not vstock:
#             vstock = VendorStock.objects.create(
#                 produit_line=pl,
#                 vendor=vendor,
#                 quantite_allouee=0,
#                 quantite_vendue=0,
#             )

#         # --- Mouvement côté bijouterie ---
#         # ❗ On NE touche PLUS quantite_allouee ici (comme pour la réserve)
#         stock_src.quantite_disponible = (stock_src.quantite_disponible or 0) - qty
#         if stock_src.quantite_disponible < 0:
#             raise ValueError(
#                 f"Incohérence sur bijouterie '{bijouterie.nom}' (ligne {pl.id})"
#             )
#         stock_src.save(update_fields=["quantite_disponible"])

#         # --- Mouvement côté vendeur (on augmente seulement l’alloué) ---
#         vstock.quantite_allouee = (vstock.quantite_allouee or 0) + qty
#         vstock.save(update_fields=["quantite_allouee"])

#         # --- INVENTORY MOVEMENT : VENDOR_ASSIGN (log interne) ---
#         lot = getattr(pl, "lot", None)
#         achat = getattr(lot, "achat", None) if lot else None

#         InventoryMovement.objects.create(
#             produit=pl.produit,
#             movement_type=MovementType.VENDOR_ASSIGN,
#             qty=qty,
#             unit_cost=None,          # tu peux le renseigner si tu as le coût unitaire
#             lot=lot,
#             achat=achat,
#             achat_ligne=lot,
#             reason=note or "",
#             # Log interne : on garde la notion de bijouterie source
#             src_bucket=Bucket.BIJOUTERIE,
#             src_bijouterie=bijouterie,
#             dst_bucket=None,
#             dst_bijouterie=None,
#             facture=None,
#             vente=None,
#             vente_ligne=None,
#             occurred_at=timezone.now(),
#             created_by=user if user and user.is_authenticated else None,
#             vendor=vendor,
#         )

#         results.append({
#             "produit_line_id": pl.id,
#             "transfere": qty,
#             "bijouterie_disponible": stock_src.quantite_disponible,
#             "vendor_disponible": vstock.quantite_disponible,  # propriété read-only
#         })

#     return {
#         "vendor_id": vendor.id,
#         "vendeur_nom": getattr(vendor, "nom", "") or getattr(vendor, "full_name", "") or "",
#         "bijouterie_id": bijouterie.id,
#         "bijouterie_nom": bijouterie.nom,
#         "lignes": results,
#         "note": note or "",
#     }

# ----------------------Assigne--------------------
@transaction.atomic
def assign_bijouterie_to_vendor_fifo(
    *,
    bijouterie_id: int,
    vendor_id: int,
    lignes: List[dict],   # [{"produit_id": X, "quantite": Y}, ...]
    note: str = "",
    user=None,
) -> dict:
    vendor = (
        Vendor.objects.select_for_update()
        .filter(id=vendor_id, bijouterie_id=bijouterie_id)
        .first()
    )
    if not vendor:
        raise ValueError("Vendor introuvable (ou pas dans cette bijouterie).")

    # Regrouper input par produit_id
    wanted: Dict[int, int] = defaultdict(int)
    for row in lignes:
        pid = int(row["produit_id"])
        qty = int(row.get("quantite") or 0)
        if qty <= 0:
            raise ValueError("quantite doit être > 0.")
        wanted[pid] += qty

    out = []

    for produit_id, demande in wanted.items():
        qty_need = int(demande)
        consommations = []
        produit_nom = None

        # FIFO: ProduitLine du produit, triées par date de lot
        pls = (
            ProduitLine.objects
            .filter(produit_id=produit_id)
            .select_related("lot", "produit")
            .order_by("lot__received_at", "id")
        )

        for pl in pls:
            if qty_need <= 0:
                break

            if produit_nom is None:
                produit_nom = getattr(pl.produit, "nom", None)

            # Stock boutique de cette PL (doit être vendable boutique)
            stock_shop = (
                Stock.objects.select_for_update()
                .filter(produit_line_id=pl.id, bijouterie_id=bijouterie_id)
                .first()
            )
            if not stock_shop or stock_shop.quantite_disponible <= 0:
                continue

            take = min(qty_need, int(stock_shop.quantite_disponible))

            # 1) Boutique: dispo -= take  (allouée ne change pas)
            Stock.objects.filter(pk=stock_shop.pk).update(
                quantite_disponible=F("quantite_disponible") - take,
                updated_at=timezone.now(),
            )

            # 2) VendorStock: allouée += take
            vs, _ = VendorStock.objects.select_for_update().get_or_create(
                produit_line_id=pl.id,
                vendor_id=vendor.id,
                defaults={"quantite_allouee": 0, "quantite_vendue": 0},
            )
            VendorStock.objects.filter(pk=vs.pk).update(
                quantite_allouee=F("quantite_allouee") + take,
                updated_at=timezone.now(),
            )

            # 3) Mouvement audit: VENDOR_ASSIGN
            InventoryMovement.objects.create(
                produit=pl.produit,
                movement_type=MovementType.VENDOR_ASSIGN,
                qty=take,
                unit_cost=None,
                lot=pl.lot,
                reason=note or "Affectation boutique → vendeur",
                src_bucket=Bucket.BIJOUTERIE,
                src_bijouterie_id=bijouterie_id,
                dst_bucket=Bucket.BIJOUTERIE,
                dst_bijouterie_id=bijouterie_id,
                vendor=vendor,
                occurred_at=timezone.now(),
                created_by=user if getattr(user, "is_authenticated", False) else None,
            )

            consommations.append({
                "produit_line_id": pl.id,
                "lot_id": pl.lot_id,
                "numero_lot": getattr(pl.lot, "numero_lot", None),
                "qty": int(take),
            })

            qty_need -= take

        if qty_need > 0:
            raise ValueError(
                f"Stock boutique insuffisant pour produit_id={produit_id}. Manque {qty_need}."
            )

        # Totaux vendeur après affectation
        agg = VendorStock.objects.filter(
            vendor_id=vendor.id,
            produit_line__produit_id=produit_id,
        ).aggregate(
            allouee=models.Sum("quantite_allouee"),
            vendue=models.Sum("quantite_vendue"),
        )
        allouee = int(agg["allouee"] or 0)
        vendue = int(agg["vendue"] or 0)
        dispo = max(0, allouee - vendue)

        out.append({
            "produit_id": int(produit_id),
            "produit_nom": produit_nom,
            "demande": int(demande),
            "affecte": int(demande),
            "vendor_allouee_total": allouee,
            "vendor_vendue_total": vendue,
            "vendor_disponible_total": dispo,
            "consommations": consommations,
        })

    return {
        "bijouterie_id": int(bijouterie_id),
        "vendor_id": vendor.id,
        "vendor_nom": str(vendor),
        "note": note or "",
        "lignes": out,
    }
    
# ------------------End Bijouterie to vendeur------------------------