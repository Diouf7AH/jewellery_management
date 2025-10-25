from collections import defaultdict

from django.db import transaction
from django.db.models import F

from purchase.models import ProduitLine
from stock.models import Stock, VendorStock
from store.models import Bijouterie
from vendor.models import Vendor


@transaction.atomic
def transfer_reserve_to_bijouterie(*, bijouterie_id:int, mouvements:list[dict], note:str=""):
    """
    mouvements: [{"produit_line_id": int, "quantite": int}, ...]
    Déplace la quantité depuis Réserve (bijouterie=None) vers bijouterie_id.
    """
    # 0) Bijouterie existe ?
    bijouterie = Bijouterie.objects.select_for_update().get(id=bijouterie_id)

    # 1) Regrouper si doublons sur la même ligne
    wanted = defaultdict(int)
    for mv in mouvements:
        wanted[int(mv["produit_line_id"])] += int(mv["quantite"])

    # 2) Lock des lignes concernées
    lignes = (ProduitLine.objects
              .select_for_update()
              .filter(id__in=wanted.keys())
              .select_related("lot", "produit"))
    found_ids = {pl.id for pl in lignes}
    missing = set(wanted.keys()) - found_ids
    if missing:
        raise ValueError(f"Lignes introuvables: {sorted(list(missing))}")

    results = []
    for pl in lignes:
        qty = wanted[pl.id]

        # Réserve
        stock_res = (Stock.objects
                     .select_for_update()
                     .filter(produit_line=pl, bijouterie__isnull=True)
                     .first())
        if not stock_res:
            # si la ligne n'a pas encore de stock en Réserve
            raise ValueError(f"Réserve inexistante pour la ligne {pl.id}")

        if (stock_res.quantite_disponible or 0) < qty:
            raise ValueError(f"Quantité insuffisante en Réserve pour la ligne {pl.id} (demande {qty}, dispo {stock_res.quantite_disponible})")

        # Destination
        stock_dst = (Stock.objects
                     .select_for_update()
                     .filter(produit_line=pl, bijouterie=bijouterie)
                     .first())
        if not stock_dst:
            stock_dst = Stock.objects.create(
                produit_line=pl, bijouterie=bijouterie,
                quantite_allouee=0, quantite_disponible=0
            )

        # Mouvement: Réserve --
        stock_res.quantite_allouee = (stock_res.quantite_allouee or 0) - qty
        stock_res.quantite_disponible = (stock_res.quantite_disponible or 0) - qty
        if stock_res.quantite_allouee < 0 or stock_res.quantite_disponible < 0:
            raise ValueError(f"Incohérence sur Réserve (ligne {pl.id})")
        stock_res.save(update_fields=["quantite_allouee", "quantite_disponible"])

        # Mouvement: Destination ++
        stock_dst.quantite_allouee = (stock_dst.quantite_allouee or 0) + qty
        stock_dst.quantite_disponible = (stock_dst.quantite_disponible or 0) + qty
        stock_dst.save(update_fields=["quantite_allouee", "quantite_disponible"])

        results.append({
            "produit_line_id": pl.id,
            "transfere": qty,
            "reserve_disponible": stock_res.quantite_disponible,
            "bijouterie_disponible": stock_dst.quantite_disponible,
        })

    # (Optionnel) journaliser 'note' dans un modèle MouvementStock si tu en as un.
    return {
        "bijouterie_id": bijouterie.id,
        "bijouterie_nom": bijouterie.nom,
        "lignes": results,
        "note": note or "",
    }



# -----------------------Bijouterie To vendeur------------------------
@transaction.atomic
def transfer_bijouterie_to_vendor(*, vendor_id:int, mouvements:list[dict], note:str=""):
    vendor = Vendor.objects.select_related("bijouterie").select_for_update().get(id=vendor_id)
    bijouterie = vendor.bijouterie

    # regrouper les demandes
    wanted = defaultdict(int)
    for mv in mouvements:
        wanted[int(mv["produit_line_id"])] += int(mv["quantite"])

    # lock des lignes
    lignes = (ProduitLine.objects
              .select_for_update()
              .filter(id__in=wanted.keys())
              .select_related("produit", "lot"))
    found_ids = {pl.id for pl in lignes}
    missing = set(wanted.keys()) - found_ids
    if missing:
        raise ValueError(f"Lignes introuvables: {sorted(list(missing))}")

    results = []
    for pl in lignes:
        qty = wanted[pl.id]

        # Source = stock de la bijouterie du vendeur
        stock_src = (Stock.objects
                     .select_for_update()
                     .filter(produit_line=pl, bijouterie=bijouterie)
                     .first())
        if not stock_src:
            raise ValueError(f"Aucun stock en bijouterie '{bijouterie.nom}' pour la ligne {pl.id}")

        if (stock_src.quantite_disponible or 0) < qty:
            raise ValueError(
                f"Insuffisant en bijouterie '{bijouterie.nom}' pour la ligne {pl.id} "
                f"(demande {qty}, dispo {stock_src.quantite_disponible})"
            )

        # Destination = VendorStock (peut ne pas exister au premier transfert)
        vstock = (VendorStock.objects
                  .select_for_update()
                  .filter(produit_line=pl, vendor=vendor)
                  .first())
        if not vstock:
            vstock = VendorStock.objects.create(
                produit_line=pl, vendor=vendor,
                quantite_allouee=0, quantite_disponible=0
            )

        # Mouvement: Bijouterie --
        stock_src.quantite_allouee = (stock_src.quantite_allouee or 0) - qty
        stock_src.quantite_disponible = (stock_src.quantite_disponible or 0) - qty
        if stock_src.quantite_allouee < 0 or stock_src.quantite_disponible < 0:
            raise ValueError(f"Incohérence sur bijouterie '{bijouterie.nom}' (ligne {pl.id})")
        stock_src.save(update_fields=["quantite_allouee", "quantite_disponible"])

        # Mouvement: Vendeur ++
        vstock.quantite_allouee = (vstock.quantite_allouee or 0) + qty
        vstock.quantite_disponible = (vstock.quantite_disponible or 0) + qty
        vstock.save(update_fields=["quantite_allouee", "quantite_disponible"])

        results.append({
            "produit_line_id": pl.id,
            "transfere": qty,
            "bijouterie_disponible": stock_src.quantite_disponible,
            "vendor_disponible": vstock.quantite_disponible,
        })

    # TODO: journaliser 'note' si tu as un modèle de mouvements
    return {
        "vendor_id": vendor.id,
        "vendeur_nom": vendor.nom,
        "bijouterie_id": bijouterie.id,
        "bijouterie_nom": bijouterie.nom,
        "lignes": results,
        "note": note or "",
    }
# ------------------End Bijouterie to vendeur------------------------