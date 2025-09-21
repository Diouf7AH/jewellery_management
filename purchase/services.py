from decimal import Decimal
from django.db import transaction
from django.db.models import F, Sum
from django.shortcuts import get_object_or_404
from store.models import Produit, Bijouterie
from stock.models import Stock
from purchase.models import Achat, AchatProduit, Fournisseur
from inventory.models import MovementType, Bucket
from inventory.services import log_move

ZERO = Decimal("0.00")

def _reservation_key(pid: int) -> str:
    return f"RES-{pid}"

def _inc_stock(pid: int, bid, qty: int) -> None:
    if bid is None:
        st, _ = Stock.objects.select_for_update().get_or_create(
            produit_id=pid, bijouterie=None, reservation_key=_reservation_key(pid),
            defaults={"quantite": 0, "is_reserved": True},
        )
        Stock.objects.filter(pk=st.pk).update(quantite=F("quantite")+qty, is_reserved=True)
    else:
        get_object_or_404(Bijouterie, pk=bid)
        st, _ = Stock.objects.select_for_update().get_or_create(
            produit_id=pid, bijouterie_id=bid, defaults={"quantite": 0, "is_reserved": False},
        )
        Stock.objects.filter(pk=st.pk).update(quantite=F("quantite")+qty, is_reserved=False)

def _dec_auto(pid: int, qty: int):
    if qty <= 0: return
    # réservé
    res = Stock.objects.select_for_update().filter(
        produit_id=pid, bijouterie__isnull=True, reservation_key=_reservation_key(pid)
    ).first()
    if res:
        take = min(res.quantite, qty)
        if take > 0:
            Stock.objects.filter(pk=res.pk).update(quantite=F("quantite")-take)
            qty -= take
    if qty <= 0: return
    # bijouteries
    for b in Stock.objects.select_for_update().filter(
        produit_id=pid, bijouterie__isnull=False, quantite__gt=0
    ).order_by("bijouterie_id"):
        if qty <= 0: break
        take = min(b.quantite, qty)
        if take > 0:
            Stock.objects.filter(pk=b.pk).update(quantite=F("quantite")-take)
            qty -= take
    if qty > 0:
        raise ValueError(f"Stock global insuffisant pour produit={pid} (reste {qty}).")

@transaction.atomic
def create_purchase(payload, user):
    # fournisseur
    fz = payload["fournisseur"]
    fournisseur, _ = Fournisseur.objects.get_or_create(
        telephone=fz["telephone"],
        defaults={"nom": fz["nom"], "prenom": fz["prenom"], "address": fz.get("address", "")},
    )
    achat = Achat.objects.create(fournisseur=fournisseur)
    default_bij = payload.get("bijouterie_id")

    for item in payload["produits"]:
        p: Produit = item["produit"]; pid = p.id
        qte = int(item["quantite"]); pu = item["prix_achat_gramme"]; tax = item.get("tax", ZERO)
        ligne = AchatProduit.objects.create(
            achat=achat, produit=p, quantite=qte, prix_achat_gramme=pu, tax=tax, fournisseur=fournisseur
        )
        affs = item.get("affectations")
        if affs:
            tot = sum(int(a["quantite"]) for a in affs)
            if tot > qte: raise ValueError("Somme des affectations > quantité")
            for a in affs:
                bid = int(a["bijouterie_id"]); qa = int(a["quantite"])
                _inc_stock(pid, bid, qa)
                log_move(
                    produit=p, qty=qa, movement_type=MovementType.PURCHASE_IN,
                    src_bucket=Bucket.EXTERNAL, dst_bucket=Bucket.BIJOUTERIE, dst_bijouterie_id=bid,
                    unit_cost=pu, achat=achat, achat_ligne=ligne, user=user, reason="Réception achat"
                )
            reste = qte - tot
            if reste > 0:
                _inc_stock(pid, None, reste)
                log_move(
                    produit=p, qty=reste, movement_type=MovementType.PURCHASE_IN,
                    src_bucket=Bucket.EXTERNAL, dst_bucket=Bucket.RESERVED,
                    unit_cost=pu, achat=achat, achat_ligne=ligne, user=user, reason="Réception achat (réservé)"
                )
        else:
            line_bij = item.get("bijouterie_id", default_bij)
            if line_bij in (None, "", 0):
                _inc_stock(pid, None, qte)
                log_move(
                    produit=p, qty=qte, movement_type=MovementType.PURCHASE_IN,
                    src_bucket=Bucket.EXTERNAL, dst_bucket=Bucket.RESERVED,
                    unit_cost=pu, achat=achat, achat_ligne=ligne, user=user, reason="Réception achat (réservé)"
                )
            else:
                bid = int(line_bij)
                _inc_stock(pid, bid, qte)
                log_move(
                    produit=p, qty=qte, movement_type=MovementType.PURCHASE_IN,
                    src_bucket=Bucket.EXTERNAL, dst_bucket=Bucket.BIJOUTERIE, dst_bijouterie_id=bid,
                    unit_cost=pu, achat=achat, achat_ligne=ligne, user=user, reason="Réception achat"
                )

    achat.update_total(save=True)
    # post_purchase_entry(achat, user=user)
    return achat

@transaction.atomic
def rebase_purchase(achat: Achat, payload, reverse_alloc, user):
    # 1) retirer ancien stock + mouvements CANCEL_PURCHASE
    lignes = (AchatProduit.objects.filter(achat=achat)
            .values("produit_id").annotate(total=Sum("quantite")))
    qty_by_prod = {r["produit_id"]: int(r["total"] or 0) for r in lignes}

    if reverse_alloc:
        for item in reverse_alloc:
            pid = int(item["produit_id"]); p = get_object_or_404(Produit, pk=pid)
            if pid not in qty_by_prod: raise ValueError("Produit hors achat")
            if sum(int(a["quantite"]) for a in item.get("allocations", [])) != qty_by_prod[pid]:
                raise ValueError("Somme allocations != quantité achat")
            for a in item["allocations"]:
                bid = a.get("bijouterie_id", None); q = int(a["quantite"])
                # décrément exact
                if bid in (None, "", 0):
                    _dec_auto(pid, q)  # ou une version ‘exact réservée’ si tu veux être strict
                    src_bkt, src_bij = Bucket.RESERVED, None
                else:
                    _dec_auto(pid, q)  # idem : fais une version exact si nécessaire
                    src_bkt, src_bij = Bucket.BIJOUTERIE, int(bid)
                log_move(
                    produit=p, qty=q, movement_type=MovementType.CANCEL_PURCHASE,
                    src_bucket=src_bkt, src_bijouterie_id=src_bij, dst_bucket=Bucket.EXTERNAL,
                    unit_cost=None, achat=achat, achat_ligne=None, user=user, reason="Rebase achat : retrait ancien stock"
                )
    else:
        for pid, total in qty_by_prod.items():
            p = get_object_or_404(Produit, pk=pid)
            _dec_auto(pid, total)
            # on ne sait pas de quel bucket exact => on peut logger 1 mouvement réservé + n mouvements bijouterie selon ta propre logique

    # 2) extourne compta + purge lignes
    # reverse_purchase_entry(achat, user=user)
    AchatProduit.objects.filter(achat=achat).delete()

    # 3) recréer comme un create
    achat = create_purchase(payload, user)  # réutiliser la même logique
    return achat
