# from __future__ import annotations

# from typing import Any, Dict, List

# from django.core.exceptions import ValidationError
# from django.db import transaction
# from django.db.models import F
# from django.utils import timezone

# from inventory.models import Bucket, InventoryMovement, MovementType
# from purchase.models import ProduitLine
# from stock.models import Stock, VendorStock
# from vendor.models import Vendor


# @transaction.atomic
# def transfer_reserve_to_vendor(*, vendor_email: str, lignes: List[Dict[str, Any]], note: str, user) -> Dict[str, Any]:
#     """
#     Réserve -> Vendeur (direct)
#     - Stock réserve: quantite_disponible -= qte
#     - VendorStock: quantite_allouee += qte   (bijouterie = vendor.bijouterie)
#     - InventoryMovement: VENDOR_ASSIGN par ligne (lot traçable)
#     """
#     vendor = (
#         Vendor.objects
#         .select_related("bijouterie", "user")
#         .filter(user__email=vendor_email)
#         .first()
#     )
#     if not vendor:
#         raise ValidationError("Vendeur introuvable (vendor_email).")

#     if not vendor.bijouterie_id:
#         raise ValidationError("Ce vendeur n'est rattaché à aucune bijouterie.")

#     # Normaliser / regrouper si doublons de ProduitLine dans le payload
#     grouped: Dict[int, int] = {}
#     for it in lignes:
#         pl_id = int(it["produit_line_id"])
#         qte = int(it["quantite"])
#         grouped[pl_id] = grouped.get(pl_id, 0) + qte

#     pl_ids = list(grouped.keys())

#     # Charger ProduitLine + lot (pour audit) + lock rows de stock réserve
#     # On lock Stock (réserve) ligne par ligne pour éviter surconsommation concurrence
#     reserve_qs = (
#         Stock.objects
#         .select_for_update()
#         .select_related("produit_line", "produit_line__lot", "produit_line__produit")
#         .filter(produit_line_id__in=pl_ids, is_reserve=True)
#     )
#     reserve_map = {st.produit_line_id: st for st in reserve_qs}

#     missing_reserve = [pl_id for pl_id in pl_ids if pl_id not in reserve_map]
#     if missing_reserve:
#         raise ValidationError(f"Pas de ligne réserve Stock pour ProduitLine: {missing_reserve}")

#     # Précharger VendorStock existants (lock aussi)
#     vs_qs = (
#         VendorStock.objects
#         .select_for_update()
#         .filter(
#             vendor_id=vendor.id,
#             bijouterie_id=vendor.bijouterie_id,
#             produit_line_id__in=pl_ids,
#         )
#     )
#     vs_map = {vs.produit_line_id: vs for vs in vs_qs}

#     out_lines = []
#     movements_created = 0

#     for pl_id, qte in grouped.items():
#         st = reserve_map[pl_id]
#         if qte <= 0:
#             continue

#         if (st.quantite_disponible or 0) < qte:
#             pnom = getattr(st.produit_line.produit, "nom", str(st.produit_line.produit_id))
#             raise ValidationError(
#                 f"Réserve insuffisante pour PL={pl_id} ({pnom}). "
#                 f"Dispo={st.quantite_disponible}, demandé={qte}."
#             )

#         # Décrément réserve
#         updated = (
#             Stock.objects
#             .filter(pk=st.pk, quantite_disponible__gte=qte)
#             .update(quantite_disponible=F("quantite_disponible") - qte)
#         )
#         if not updated:
#             raise ValidationError("Conflit de stock réserve détecté, réessayez.")

#         # Incrément VendorStock (create si absent)
#         vs = vs_map.get(pl_id)
#         if not vs:
#             vs = VendorStock.objects.create(
#                 produit_line_id=pl_id,
#                 vendor_id=vendor.id,
#                 bijouterie_id=vendor.bijouterie_id,
#                 quantite_allouee=0,
#                 quantite_vendue=0,
#             )
#             vs_map[pl_id] = vs

#         VendorStock.objects.filter(pk=vs.pk).update(quantite_allouee=F("quantite_allouee") + qte)

#         # Audit mouvement (VENDOR_ASSIGN) — lot obligatoire pour FIFO / traçabilité
#         pl = st.produit_line  # déjà select_related lot + produit
#         InventoryMovement.objects.create(
#             produit_id=pl.produit_id,
#             produit_line_id=pl.id,        # ✅ AJOUT ICI
#             movement_type=MovementType.VENDOR_ASSIGN,
#             qty=int(qte),
#             unit_cost=None,
#             lot_id=pl.lot_id,             # ✅ AJOUT ICI (ou laissé tel quel)
#             reason=(note or "").strip() or f"Affectation réserve → vendeur {vendor.id}",
#             src_bucket=Bucket.RESERVED,
#             src_bijouterie=None,
#             dst_bucket=Bucket.BIJOUTERIE,
#             dst_bijouterie_id=vendor.bijouterie_id,
#             vendor_id=vendor.id,
#             occurred_at=timezone.now(),
#             created_by=user,
#         )
#         movements_created += 1

#         # Reload petites valeurs utiles (sans requery lourd)
#         st_after = Stock.objects.only("quantite_disponible").get(pk=st.pk)
#         vs_after = VendorStock.objects.only("quantite_allouee", "quantite_vendue").get(pk=vs.pk)

#         out_lines.append({
#             "produit_line_id": pl_id,
#             "transfere": qte,
#             "reserve_disponible": int(st_after.quantite_disponible or 0),
#             "vendor_allouee": int(vs_after.quantite_allouee or 0),
#             "vendor_vendue": int(vs_after.quantite_vendue or 0),
#             "vendor_disponible": int((vs_after.quantite_allouee or 0) - (vs_after.quantite_vendue or 0)),
#         })

#     return {
#         "vendor_id": vendor.id,
#         "vendor_email": getattr(vendor.user, "email", None),
#         "bijouterie_id": vendor.bijouterie_id,
#         "bijouterie_nom": getattr(vendor.bijouterie, "nom", None),
#         "lignes": out_lines,
#         "note": note or "",
#         "movements_created": movements_created,
#     }


# from __future__ import annotations

# from typing import Any, Dict, List

# from django.core.exceptions import ValidationError
# from django.db import IntegrityError, transaction
# from django.db.models import F
# from django.utils import timezone

# from inventory.models import Bucket, InventoryMovement, MovementType
# from stock.models import Stock, VendorStock
# from vendor.models import Vendor


# @transaction.atomic
# def transfer_reserve_to_vendor(
#     *,
#     vendor_email: str,
#     lignes: List[Dict[str, Any]],
#     note: str = "",
#     user=None,
# ) -> Dict[str, Any]:
#     """
#     Réserve -> Vendeur (direct)

#     Hypothèses (Option 1) :
#     - Stock contient : en_stock + quantite_disponible
#     - La réserve est Stock(is_reserve=True, bijouterie=None)
#     - VendorStock contient : quantite_allouee, quantite_vendue (dispo vendeur = allouee - vendue)

#     Effets :
#     - Stock réserve : en_stock -= qte ET quantite_disponible -= qte
#     - VendorStock   : quantite_allouee += qte (bijouterie = vendor.bijouterie)
#     - InventoryMovement : VENDOR_ASSIGN par ligne (traçable par lot / produit_line)
#       src: RESERVED  -> dst: VENDOR
#     """
#     # --------- 1) Charger vendeur ----------
#     vendor = (
#         Vendor.objects.select_related("bijouterie", "user")
#         .filter(user__email=vendor_email)
#         .first()
#     )
#     if not vendor:
#         raise ValidationError("Vendeur introuvable (vendor_email).")
#     if not vendor.bijouterie_id:
#         raise ValidationError("Ce vendeur n'est rattaché à aucune bijouterie.")

#     # --------- 2) Normaliser + regrouper lignes ----------
#     if not lignes:
#         raise ValidationError({"lignes": "Au moins une ligne est requise."})

#     grouped: Dict[int, int] = {}
#     for i, it in enumerate(lignes):
#         try:
#             pl_id = int(it["produit_line_id"])
#             qte = int(it["quantite"])
#         except Exception:
#             raise ValidationError({f"lignes[{i}]": "produit_line_id et quantite sont requis (int)."})

#         if pl_id <= 0:
#             raise ValidationError({f"lignes[{i}].produit_line_id": "Invalide."})
#         if qte <= 0:
#             raise ValidationError({f"lignes[{i}].quantite": "Doit être >= 1."})

#         grouped[pl_id] = grouped.get(pl_id, 0) + qte

#     pl_ids = list(grouped.keys())

#     # --------- 3) Lock Stock réserve ----------
#     reserve_qs = (
#         Stock.objects.select_for_update()
#         .select_related("produit_line", "produit_line__lot", "produit_line__produit")
#         .filter(produit_line_id__in=pl_ids,
#                 is_reserve=True,
#                 bijouterie__isnull=True,   # ✅ ici
#                 )
#     )
#     reserve_map = {st.produit_line_id: st for st in reserve_qs}

#     missing_reserve = [pl_id for pl_id in pl_ids if pl_id not in reserve_map]
#     if missing_reserve:
#         raise ValidationError(f"Pas de Stock réserve pour ProduitLine: {missing_reserve}")

#     # --------- 4) Lock VendorStock existants ----------
#     vs_qs = (
#         VendorStock.objects.select_for_update()
#         .filter(
#             vendor_id=vendor.id,
#             bijouterie_id=vendor.bijouterie_id,
#             produit_line_id__in=pl_ids,
#         )
#     )
#     vs_map = {vs.produit_line_id: vs for vs in vs_qs}

#     out_lines: List[Dict[str, Any]] = []
#     movements_created = 0
#     now = timezone.now()
#     note_clean = (note or "").strip()

#     # --------- 5) Appliquer transferts ----------
#     for pl_id, qte in grouped.items():
#         st = reserve_map[pl_id]

#         dispo = int(st.quantite_disponible or 0)
#         en_stock = int(st.en_stock or 0)

#         if dispo < qte or en_stock < qte:
#             pnom = getattr(st.produit_line.produit, "nom", str(st.produit_line.produit_id))
#             raise ValidationError(
#                 f"Réserve insuffisante pour PL={pl_id} ({pnom}). "
#                 f"Dispo={dispo}, EnStock={en_stock}, demandé={qte}."
#             )

#         # 5.1) Décrément réserve (safe concurrence)
#         updated = (
#             Stock.objects.filter(
#                 pk=st.pk,
#                 is_reserve=True,
#                 bijouterie__isnull=True,   # ✅ ici
#                 quantite_disponible__gte=qte,
#                 en_stock__gte=qte,
#             )
#             .update(
#                 en_stock=F("en_stock") - qte,
#                 quantite_disponible=F("quantite_disponible") - qte,
#                 updated_at=now,
#             )
#         )
#         if not updated:
#             raise ValidationError("Conflit de stock réserve détecté, réessayez.")

#         # 5.2) Incrément VendorStock (create si absent, safe concurrence)
#         vs = vs_map.get(pl_id)
#         if not vs:
#             try:
#                 vs = VendorStock.objects.create(
#                     produit_line_id=pl_id,
#                     vendor_id=vendor.id,
#                     bijouterie_id=vendor.bijouterie_id,
#                     quantite_allouee=0,
#                     quantite_vendue=0,
#                 )
#             except IntegrityError:
#                 vs = (
#                     VendorStock.objects.select_for_update()
#                     .get(
#                         produit_line_id=pl_id,
#                         vendor_id=vendor.id,
#                         bijouterie_id=vendor.bijouterie_id,
#                     )
#                 )
#             vs_map[pl_id] = vs

#         VendorStock.objects.filter(pk=vs.pk).update(
#             quantite_allouee=F("quantite_allouee") + qte
#         )

#         # 5.3) Audit mouvement : RESERVED -> VENDOR
#         pl = st.produit_line  # déjà select_related lot + produit
#         InventoryMovement.objects.create(
#             produit_id=pl.produit_id,
#             produit_line_id=pl.id,
#             lot_id=pl.lot_id,
#             movement_type=MovementType.VENDOR_ASSIGN,
#             qty=int(qte),
#             unit_cost=None,
#             reason=note_clean or f"Affectation réserve → vendeur {vendor.id}",
#             src_bucket=Bucket.RESERVED,
#             src_bijouterie=None,
#             dst_bucket=Bucket.BIJOUTERIE,          # ✅
#             dst_bijouterie_id=vendor.bijouterie_id,
#             vendor_id=vendor.id,
#             occurred_at=now,
#             created_by=user,
#         )
#         movements_created += 1

#     # --------- 6) Réponse (reload en 2 requêtes max) ----------
#     # Recharger stocks réserve (seulement les champs utiles)
#     st_after_qs = Stock.objects.filter(
#         Stock.objects.filter(
#             produit_line_id__in=pl_ids,
#             is_reserve=True,
#             bijouterie__isnull=True,   # ✅ ici
#         )
#     ).values("produit_line_id", "en_stock", "quantite_disponible")

#     st_after_map = {
#         row["produit_line_id"]: row for row in st_after_qs
#     }

#     vs_after_qs = VendorStock.objects.filter(
#         vendor_id=vendor.id,
#         bijouterie_id=vendor.bijouterie_id,
#         produit_line_id__in=pl_ids,
#     ).values("produit_line_id", "quantite_allouee", "quantite_vendue")

#     vs_after_map = {
#         row["produit_line_id"]: row for row in vs_after_qs
#     }

#     for pl_id, qte in grouped.items():
#         st_row = st_after_map.get(pl_id) or {}
#         vs_row = vs_after_map.get(pl_id) or {}

#         reserve_dispo = int(st_row.get("quantite_disponible") or 0)
#         reserve_en_stock = int(st_row.get("en_stock") or 0)

#         vendor_allouee = int(vs_row.get("quantite_allouee") or 0)
#         vendor_vendue = int(vs_row.get("quantite_vendue") or 0)

#         out_lines.append(
#             {
#                 "produit_line_id": pl_id,
#                 "transfere": int(qte),
#                 "reserve_en_stock": reserve_en_stock,
#                 "reserve_disponible": reserve_dispo,
#                 "vendor_allouee": vendor_allouee,
#                 "vendor_vendue": vendor_vendue,
#                 "vendor_disponible": max(0, vendor_allouee - vendor_vendue),
#             }
#         )

#     return {
#         "vendor_id": vendor.id,
#         "vendor_email": getattr(vendor.user, "email", None),
#         "bijouterie_id": vendor.bijouterie_id,
#         "bijouterie_nom": getattr(vendor.bijouterie, "nom", None),
#         "lignes": out_lines,
#         "note": note_clean,
#         "movements_created": movements_created,
#     }
    




# from __future__ import annotations

# from typing import Any, Dict, List

# from django.core.exceptions import ValidationError
# from django.db import IntegrityError, transaction
# from django.db.models import F
# from django.utils import timezone

# from inventory.models import Bucket, InventoryMovement, MovementType
# from stock.models import Stock, VendorStock
# from vendor.models import Vendor


# @transaction.atomic
# def transfer_reserve_to_vendor(
#     *,
#     vendor_email: str,
#     lignes: List[Dict[str, Any]],
#     note: str = "",
#     user=None,
# ) -> Dict[str, Any]:
#     """
#     Réserve -> Vendeur (direct)  [Option A]

#     Hypothèses:
#     - Stock contient : en_stock (reste réel) + quantite_disponible (plafond total)
#     - Réserve = Stock(is_reserve=True, bijouterie=NULL)
#     - VendorStock contient : quantite_allouee, quantite_vendue

#     Effets:
#     - Stock réserve : en_stock -= qte ET quantite_disponible -= qte
#     - VendorStock   : quantite_allouee += qte (bijouterie = vendor.bijouterie)
#     - InventoryMovement : VENDOR_ASSIGN par ligne
#       src: RESERVED -> dst: BIJOUTERIE (dst_bijouterie = vendor.bijouterie), + vendor_id
#       produit_line_id + lot_id obligatoires (FIFO / audit)
#     """

#     # ---------- 1) Charger vendeur ----------
#     vendor = (
#         Vendor.objects.select_related("bijouterie", "user")
#         .filter(user__email=vendor_email)
#         .first()
#     )
#     if not vendor:
#         raise ValidationError({"vendor_email": "Vendeur introuvable."})
#     if not vendor.bijouterie_id:
#         raise ValidationError({"vendor_email": "Ce vendeur n'est rattaché à aucune bijouterie."})

#     # ---------- 2) Normaliser + regrouper lignes ----------
#     if not lignes:
#         raise ValidationError({"lignes": "Au moins une ligne est requise."})

#     grouped: Dict[int, int] = {}
#     for i, it in enumerate(lignes):
#         if "produit_line_id" not in it or "quantite" not in it:
#             raise ValidationError({f"lignes[{i}]": "produit_line_id et quantite sont requis."})

#         try:
#             pl_id = int(it["produit_line_id"])
#             qte = int(it["quantite"])
#         except Exception:
#             raise ValidationError({f"lignes[{i}]": "produit_line_id et quantite doivent être des entiers."})

#         if pl_id <= 0:
#             raise ValidationError({f"lignes[{i}].produit_line_id": "Invalide."})
#         if qte <= 0:
#             raise ValidationError({f"lignes[{i}].quantite": "Doit être >= 1."})

#         grouped[pl_id] = grouped.get(pl_id, 0) + qte

#     pl_ids = list(grouped.keys())

#     # ---------- 3) Lock Stock réserve ----------
#     reserve_qs = (
#         Stock.objects.select_for_update()
#         .select_related("produit_line", "produit_line__lot", "produit_line__produit")
#         .filter(
#             produit_line_id__in=pl_ids,
#             is_reserve=True,
#             bijouterie__isnull=True,
#         )
#     )
#     reserve_map = {st.produit_line_id: st for st in reserve_qs}

#     missing = [pl_id for pl_id in pl_ids if pl_id not in reserve_map]
#     if missing:
#         raise ValidationError({"lignes": f"Pas de Stock réserve pour ProduitLine: {missing}"})

#     # ---------- 4) Lock VendorStock existants ----------
#     vs_qs = (
#         VendorStock.objects.select_for_update()
#         .filter(
#             vendor_id=vendor.id,
#             bijouterie_id=vendor.bijouterie_id,
#             produit_line_id__in=pl_ids,
#         )
#     )
#     vs_map = {vs.produit_line_id: vs for vs in vs_qs}

#     now = timezone.now()
#     note_clean = (note or "").strip()
#     out_lines: List[Dict[str, Any]] = []
#     movements_created = 0

#     # ---------- 5) Appliquer transferts ----------
#     for pl_id, qte in grouped.items():
#         st = reserve_map[pl_id]

#         dispo_plafond = int(st.quantite_disponible or 0)
#         dispo_reel = int(st.en_stock or 0)

#         if dispo_plafond < qte or dispo_reel < qte:
#             pnom = getattr(st.produit_line.produit, "nom", str(st.produit_line.produit_id))
#             raise ValidationError({
#                 "lignes": (
#                     f"Réserve insuffisante pour PL={pl_id} ({pnom}). "
#                     f"Plafond={dispo_plafond}, EnStock={dispo_reel}, demandé={qte}."
#                 )
#             })

#         # 5.1) Décrément réserve (safe concurrence)
#         updated = (
#             Stock.objects.filter(
#                 pk=st.pk,
#                 is_reserve=True,
#                 bijouterie__isnull=True,
#                 quantite_disponible__gte=qte,
#                 en_stock__gte=qte,
#             )
#             .update(
#                 en_stock=F("en_stock") - qte,
#                 quantite_disponible=F("quantite_disponible") - qte,
#             )
#         )
#         if not updated:
#             raise ValidationError({"detail": "Conflit de stock réserve détecté, réessayez."})

#         # 5.2) Incrément VendorStock (create si absent)
#         vs = vs_map.get(pl_id)
#         if not vs:
#             try:
#                 vs = VendorStock.objects.create(
#                     produit_line_id=pl_id,
#                     vendor_id=vendor.id,
#                     bijouterie_id=vendor.bijouterie_id,
#                     quantite_allouee=0,
#                     quantite_vendue=0,
#                 )
#             except IntegrityError:
#                 vs = (
#                     VendorStock.objects.select_for_update()
#                     .get(
#                         produit_line_id=pl_id,
#                         vendor_id=vendor.id,
#                         bijouterie_id=vendor.bijouterie_id,
#                     )
#                 )
#             vs_map[pl_id] = vs

#         VendorStock.objects.filter(pk=vs.pk).update(
#             quantite_allouee=F("quantite_allouee") + qte
#         )

#         # 5.3) Audit mouvement : RESERVED -> BIJOUTERIE (assigné à vendor)
#         pl = st.produit_line
#         InventoryMovement.objects.create(
#             produit_id=pl.produit_id,
#             produit_line_id=pl.id,
#             lot_id=pl.lot_id,
#             movement_type=MovementType.VENDOR_ASSIGN,
#             qty=int(qte),
#             unit_cost=None,
#             reason=note_clean or f"Affectation réserve → vendeur {vendor.id}",
#             src_bucket=Bucket.RESERVED,
#             src_bijouterie=None,
#             dst_bucket=Bucket.BIJOUTERIE,
#             dst_bijouterie_id=vendor.bijouterie_id,
#             vendor_id=vendor.id,
#             occurred_at=now,
#             created_by=user,
#         )
#         movements_created += 1

#     # ---------- 6) Reload (2 requêtes) ----------
#     st_after = {
#         row["produit_line_id"]: row
#         for row in Stock.objects.filter(
#             produit_line_id__in=pl_ids,
#             is_reserve=True,
#             bijouterie__isnull=True,
#         ).values("produit_line_id", "en_stock", "quantite_disponible")
#     }

#     vs_after = {
#         row["produit_line_id"]: row
#         for row in VendorStock.objects.filter(
#             vendor_id=vendor.id,
#             bijouterie_id=vendor.bijouterie_id,
#             produit_line_id__in=pl_ids,
#         ).values("produit_line_id", "quantite_allouee", "quantite_vendue")
#     }

#     for pl_id, qte in grouped.items():
#         st_row = st_after.get(pl_id, {})
#         vs_row = vs_after.get(pl_id, {})

#         reserve_plafond = int(st_row.get("quantite_disponible") or 0)
#         reserve_reel = int(st_row.get("en_stock") or 0)

#         vendor_allouee = int(vs_row.get("quantite_allouee") or 0)
#         vendor_vendue = int(vs_row.get("quantite_vendue") or 0)

#         out_lines.append({
#             "produit_line_id": int(pl_id),
#             "transfere": int(qte),
#             "reserve_en_stock": reserve_reel,
#             "reserve_disponible": reserve_plafond,
#             "vendor_allouee": vendor_allouee,
#             "vendor_vendue": vendor_vendue,
#             "vendor_disponible": max(0, vendor_allouee - vendor_vendue),
#         })

#     return {
#         "vendor_id": vendor.id,
#         "vendor_email": getattr(vendor.user, "email", None),
#         "bijouterie_id": vendor.bijouterie_id,
#         "bijouterie_nom": getattr(vendor.bijouterie, "nom", None),
#         "lignes": out_lines,
#         "note": note_clean,
#         "movements_created": movements_created,
#     }
    



from __future__ import annotations

from typing import Any, Dict, List

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from inventory.models import Bucket, InventoryMovement, MovementType
from stock.models import Stock, VendorStock
from vendor.models import Vendor


@transaction.atomic
def transfer_reserve_to_vendor(
    *,
    vendor_email: str,
    lignes: List[Dict[str, Any]],
    note: str = "",
    user=None,
) -> Dict[str, Any]:
    """
    Réserve -> Vendeur (direct)

    Stock (réserve):
      - quantite_totale : total présent dans ce bucket
      - en_stock        : disponible réel (doit rester <= quantite_totale)
      - réserve = bijouterie NULL (is_reserve auto)

    VendorStock:
      - quantite_allouee / quantite_vendue

    Effets:
      - Stock réserve : quantite_totale -= qte ET en_stock -= qte
      - VendorStock   : quantite_allouee += qte (bijouterie = vendor.bijouterie)
      - InventoryMovement : VENDOR_ASSIGN par ligne (lot requis)
        - src: RESERVED -> dst: BIJOUTERIE (dst_bijouterie = vendor.bijouterie)
        - lien FIFO : lot + achat_ligne(ProduitLine) si tu veux
    """

    # ---------- 1) Charger vendeur ----------
    vendor = (
        Vendor.objects.select_related("bijouterie", "user")
        .filter(user__email=vendor_email)
        .first()
    )
    if not vendor:
        raise ValidationError({"vendor_email": "Vendeur introuvable."})
    if not vendor.bijouterie_id:
        raise ValidationError({"vendor_email": "Ce vendeur n'est rattaché à aucune bijouterie."})

    # ---------- 2) Normaliser + regrouper lignes ----------
    if not lignes:
        raise ValidationError({"lignes": "Au moins une ligne est requise."})

    grouped: Dict[int, int] = {}
    for i, it in enumerate(lignes):
        if "produit_line_id" not in it or "quantite" not in it:
            raise ValidationError({f"lignes[{i}]": "produit_line_id et quantite sont requis."})

        try:
            pl_id = int(it["produit_line_id"])
            qte = int(it["quantite"])
        except Exception:
            raise ValidationError({f"lignes[{i}]": "produit_line_id et quantite doivent être des entiers."})

        if pl_id <= 0:
            raise ValidationError({f"lignes[{i}].produit_line_id": "Invalide."})
        if qte <= 0:
            raise ValidationError({f"lignes[{i}].quantite": "Doit être >= 1."})

        grouped[pl_id] = grouped.get(pl_id, 0) + qte

    pl_ids = list(grouped.keys())

    # ---------- 3) Lock Stock réserve ----------
    reserve_qs = (
        Stock.objects.select_for_update()
        .select_related("produit_line", "produit_line__lot", "produit_line__produit")
        .filter(
            produit_line_id__in=pl_ids,
            bijouterie__isnull=True,  # réserve
        )
    )
    reserve_map = {st.produit_line_id: st for st in reserve_qs}

    missing = [pl_id for pl_id in pl_ids if pl_id not in reserve_map]
    if missing:
        raise ValidationError({"lignes": f"Pas de Stock réserve pour ProduitLine: {missing}"})

    # ---------- 4) Lock VendorStock existants ----------
    vs_qs = (
        VendorStock.objects.select_for_update()
        .filter(
            vendor_id=vendor.id,
            bijouterie_id=vendor.bijouterie_id,
            produit_line_id__in=pl_ids,
        )
    )
    vs_map = {vs.produit_line_id: vs for vs in vs_qs}

    now = timezone.now()
    note_clean = (note or "").strip()
    movements_created = 0

    # ---------- 5) Appliquer transferts ----------
    for pl_id, qte in grouped.items():
        st = reserve_map[pl_id]
        pl = st.produit_line

        total_bucket = int(st.quantite_totale or 0)
        dispo_reel = int(st.en_stock or 0)

        if total_bucket < qte or dispo_reel < qte:
            pnom = getattr(pl.produit, "nom", str(pl.produit_id))
            raise ValidationError({
                "lignes": (
                    f"Réserve insuffisante pour PL={pl_id} ({pnom}). "
                    f"Total={total_bucket}, EnStock={dispo_reel}, demandé={qte}."
                )
            })

        # 5.1) Décrément réserve (concurrence-safe)
        updated = (
            Stock.objects.filter(
                pk=st.pk,
                bijouterie__isnull=True,
                quantite_totale__gte=qte,
                en_stock__gte=qte,
            )
            .update(
                quantite_totale=F("quantite_totale") - qte,
                en_stock=F("en_stock") - qte,
            )
        )
        if not updated:
            raise ValidationError({"detail": "Conflit de stock réserve détecté, réessayez."})

        # 5.2) Incrément VendorStock (create si absent)
        vs = vs_map.get(pl_id)
        if not vs:
            try:
                vs = VendorStock.objects.create(
                    produit_line_id=pl_id,
                    vendor_id=vendor.id,
                    bijouterie_id=vendor.bijouterie_id,
                    quantite_allouee=0,
                    quantite_vendue=0,
                )
            except IntegrityError:
                vs = (
                    VendorStock.objects.select_for_update()
                    .get(
                        produit_line_id=pl_id,
                        vendor_id=vendor.id,
                        bijouterie_id=vendor.bijouterie_id,
                    )
                )
            vs_map[pl_id] = vs

        VendorStock.objects.filter(pk=vs.pk).update(
            quantite_allouee=F("quantite_allouee") + qte
        )

        # 5.3) Audit mouvement
        InventoryMovement.objects.create(
            produit_id=pl.produit_id,
            produit_line_id=pl.id,          # ✅ obligatoire pour VENDOR_ASSIGN
            achat_ligne_id=pl.id,           # ✅ optionnel, utile pour référence achat
            movement_type=MovementType.VENDOR_ASSIGN,
            qty=int(qte),
            unit_cost=None,
            lot_id=pl.lot_id,               # ✅ obligatoire
            reason=note_clean or f"Affectation réserve → vendeur {vendor.id}",
            src_bucket=Bucket.RESERVED,
            src_bijouterie=None,
            dst_bucket=Bucket.BIJOUTERIE,
            dst_bijouterie_id=vendor.bijouterie_id,
            vendor_id=vendor.id,
            occurred_at=now,
            created_by=user,
        )
        movements_created += 1

    # ---------- 6) Reload (2 requêtes) ----------
    st_after = {
        row["produit_line_id"]: row
        for row in Stock.objects.filter(
            produit_line_id__in=pl_ids,
            bijouterie__isnull=True,
        ).values("produit_line_id", "en_stock", "quantite_totale")
    }

    vs_after = {
        row["produit_line_id"]: row
        for row in VendorStock.objects.filter(
            vendor_id=vendor.id,
            bijouterie_id=vendor.bijouterie_id,
            produit_line_id__in=pl_ids,
        ).values("produit_line_id", "quantite_allouee", "quantite_vendue")
    }

    out_lines: List[Dict[str, Any]] = []
    for pl_id, qte in grouped.items():
        st_row = st_after.get(pl_id, {})
        vs_row = vs_after.get(pl_id, {})

        reserve_total = int(st_row.get("quantite_totale") or 0)
        reserve_reel = int(st_row.get("en_stock") or 0)

        vendor_allouee = int(vs_row.get("quantite_allouee") or 0)
        vendor_vendue = int(vs_row.get("quantite_vendue") or 0)

        out_lines.append({
            "produit_line_id": int(pl_id),
            "transfere": int(qte),

            "reserve_quantite_totale": reserve_total,
            "reserve_en_stock": reserve_reel,

            "vendor_allouee": vendor_allouee,
            "vendor_vendue": vendor_vendue,
            "vendor_disponible": max(0, vendor_allouee - vendor_vendue),
        })

    return {
        "vendor_id": vendor.id,
        "vendor_email": getattr(vendor.user, "email", None),
        "bijouterie_id": vendor.bijouterie_id,
        "bijouterie_nom": getattr(vendor.bijouterie, "nom", None),
        "lignes": out_lines,
        "note": note_clean,
        "movements_created": movements_created,
    }
    





