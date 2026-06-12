# sale/services/confirm_service.py
from __future__ import annotations

from typing import Dict, List

from django.core.exceptions import ValidationError
from django.db import transaction

from purchase.models import ProduitLine
from sale.models import Facture, VenteProduit
from sale.services.inventory_audit_service import create_sale_out_consumption
from sale.services.vendor_stock_service import consume_vendor_stock


@transaction.atomic
def confirm_sale_out_from_vendor(*, facture: Facture, by_user) -> dict:
    """
    Consomme le stock vendeur (FIFO) + crée les mouvements SALE_OUT
    uniquement quand la facture devient PAYÉE.

    Idempotence :
    - si facture.stock_consumed = True -> ne refait rien
    - create_sale_out_consumption gère aussi les doublons
    """
    facture = (
        Facture.objects
        .select_for_update()
        .select_related("vente", "bijouterie")
        .get(pk=facture.pk)
    )

    vente = facture.vente
    if not vente:
        raise ValidationError("Facture sans vente liée.")

    if facture.status != Facture.STAT_PAYE:
        raise ValidationError("Stock : consommation autorisée uniquement quand la facture est PAYÉE.")

    if facture.stock_consumed:
        return {"created": 0, "already": 0, "lines_done": 0}

    created = 0
    already = 0
    lines_done = 0

    lignes = (
        VenteProduit.objects
        .select_related("produit", "vendor")
        .filter(vente_id=vente.id)
        .order_by("id")
    )

    all_pl_ids: List[int] = []
    consumptions_by_lp: Dict[int, List[dict]] = {}

    # 1) Consommer le stock FIFO
    for lp in lignes:
        if not lp.vendor_id:
            raise ValidationError(f"Ligne vente {lp.id}: vendor manquant.")
        if not lp.produit_id:
            raise ValidationError(f"Ligne vente {lp.id}: produit manquant.")

        qte = int(lp.quantite or 0)
        if qte <= 0:
            raise ValidationError(f"Ligne vente {lp.id}: quantité invalide.")

        consumptions = consume_vendor_stock(
            vendor=lp.vendor,
            bijouterie=facture.bijouterie,
            produit=lp.produit,
            quantite=qte,
        )

        consumptions_by_lp[lp.id] = consumptions
        all_pl_ids.extend([m["produit_line_id"] for m in consumptions])

    # Rien à faire
    if not consumptions_by_lp:
        facture.stock_consumed = True
        facture.save(update_fields=["stock_consumed"])
        return {"created": 0, "already": 0, "lines_done": 0}

    # 2) Charger les ProduitLine
    pl_map = {
        pl.id: pl
        for pl in ProduitLine.objects.select_related("lot").filter(id__in=set(all_pl_ids))
    }

    # 3) Créer les mouvements SALE_OUT
    for lp in lignes:
        consumptions = consumptions_by_lp.get(lp.id)
        if not consumptions:
            continue

        for m in consumptions:
            pl = pl_map.get(m["produit_line_id"])
            if not pl:
                raise ValidationError(f"ProduitLine introuvable: {m['produit_line_id']}")

            ok = create_sale_out_consumption(
                facture=facture,
                vente=vente,
                vente_ligne=lp,
                produit_line=pl,
                qty=int(m["qty"]),
                by_user=by_user,
            )

            if ok:
                created += 1
            else:
                already += 1

        lines_done += 1

    # 4) Marquer facture consommée
    facture.stock_consumed = True
    facture.save(update_fields=["stock_consumed"])

    return {
        "created": created,
        "already": already,
        "lines_done": lines_done,
    }
    
    

