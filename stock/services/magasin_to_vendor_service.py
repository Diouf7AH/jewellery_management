from typing import Any, Dict, List

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from inventory.models import Bucket, InventoryMovement, MovementType
from stock.models import Stock, VendorStock
from vendor.models import Vendor


@transaction.atomic
def transfer_magasin_to_vendor(
    *,
    vendor_email: str,
    lignes: List[Dict[str, Any]],
    note: str = "",
    user=None,
) -> Dict[str, Any]:
    """
    Transfert Magasin/Bijouterie -> Vendeur.

    Effets :
    - Stock magasin : en_stock -= qte
    - Stock magasin : quantite_disponible -= qte
    - VendorStock : quantite_allouee += qte
    - InventoryMovement : VENDOR_ASSIGN
    """

    vendor = (
        Vendor.objects
        .select_related("bijouterie", "user")
        .filter(user__email__iexact=vendor_email)
        .first()
    )

    if not vendor:
        raise ValidationError({"vendor_email": "Vendeur introuvable."})

    if not vendor.bijouterie_id:
        raise ValidationError(
            {"vendor_email": "Ce vendeur n'est rattaché à aucune bijouterie."}
        )

    if not lignes:
        raise ValidationError({"lignes": "Au moins une ligne est requise."})

    grouped: Dict[int, int] = {}

    for i, item in enumerate(lignes):
        try:
            pl_id = int(item["produit_line_id"])
            qte = int(item["quantite"])
        except Exception:
            raise ValidationError(
                {f"lignes[{i}]": "produit_line_id et quantite doivent être des entiers."}
            )

        if pl_id <= 0:
            raise ValidationError({f"lignes[{i}].produit_line_id": "Invalide."})

        if qte <= 0:
            raise ValidationError({f"lignes[{i}].quantite": "Doit être >= 1."})

        grouped[pl_id] = grouped.get(pl_id, 0) + qte

    produit_line_ids = list(grouped.keys())

    stock_qs = (
        Stock.objects
        .select_for_update()
        .select_related(
            "produit_line",
            "produit_line__lot",
            "produit_line__produit",
            "bijouterie",
        )
        .filter(
            produit_line_id__in=produit_line_ids,
            bijouterie_id=vendor.bijouterie_id,
            is_reserve=False,
        )
    )

    stock_map = {stock.produit_line_id: stock for stock in stock_qs}

    missing = [pl_id for pl_id in produit_line_ids if pl_id not in stock_map]

    if missing:
        raise ValidationError(
            {"lignes": f"Pas de stock magasin pour ProduitLine: {missing}"}
        )

    vendor_stock_qs = (
        VendorStock.objects
        .select_for_update()
        .filter(
            vendor_id=vendor.id,
            bijouterie_id=vendor.bijouterie_id,
            produit_line_id__in=produit_line_ids,
        )
    )

    vendor_stock_map = {
        vendor_stock.produit_line_id: vendor_stock
        for vendor_stock in vendor_stock_qs
    }

    now = timezone.now()
    note_clean = (note or "").strip()
    movements_created = 0

    for pl_id, qte in grouped.items():
        stock = stock_map[pl_id]
        produit_line = stock.produit_line

        magasin_en_stock = int(stock.en_stock or 0)
        magasin_disponible = int(stock.quantite_disponible or 0)

        if magasin_en_stock < qte or magasin_disponible < qte:
            produit_nom = getattr(produit_line.produit, "nom", str(produit_line.produit_id))

            raise ValidationError({
                "lignes": (
                    f"Stock magasin insuffisant pour PL={pl_id} ({produit_nom}). "
                    f"En stock={magasin_en_stock}, "
                    f"Disponible={magasin_disponible}, "
                    f"demandé={qte}."
                )
            })

        updated = (
            Stock.objects
            .filter(
                pk=stock.pk,
                bijouterie_id=vendor.bijouterie_id,
                is_reserve=False,
                en_stock__gte=qte,
                quantite_disponible__gte=qte,
            )
            .update(
                en_stock=F("en_stock") - qte,
                quantite_disponible=F("quantite_disponible") - qte,
            )
        )

        if not updated:
            raise ValidationError(
                {"detail": "Conflit de stock magasin détecté, réessayez."}
            )

        vendor_stock = vendor_stock_map.get(pl_id)

        if not vendor_stock:
            try:
                vendor_stock = VendorStock.objects.create(
                    produit_line_id=pl_id,
                    vendor_id=vendor.id,
                    bijouterie_id=vendor.bijouterie_id,
                    quantite_allouee=0,
                    quantite_vendue=0,
                )
            except IntegrityError:
                vendor_stock = (
                    VendorStock.objects
                    .select_for_update()
                    .get(
                        produit_line_id=pl_id,
                        vendor_id=vendor.id,
                        bijouterie_id=vendor.bijouterie_id,
                    )
                )

            vendor_stock_map[pl_id] = vendor_stock

        VendorStock.objects.filter(pk=vendor_stock.pk).update(
            quantite_allouee=F("quantite_allouee") + qte
        )

        InventoryMovement.objects.create(
            produit_id=produit_line.produit_id,
            produit_line_id=produit_line.id,
            achat_ligne_id=produit_line.id,
            movement_type=MovementType.VENDOR_ASSIGN,
            qty=int(qte),
            unit_cost=None,
            lot_id=produit_line.lot_id,
            reason=note_clean or f"Affectation magasin → vendeur {vendor.id}",
            src_bucket=Bucket.BIJOUTERIE,
            src_bijouterie_id=vendor.bijouterie_id,
            dst_bucket=Bucket.VENDOR,
            dst_bijouterie_id=vendor.bijouterie_id,
            vendor_id=vendor.id,
            occurred_at=now,
            created_by=user,
        )

        movements_created += 1

    stock_after = {
        row["produit_line_id"]: row
        for row in Stock.objects.filter(
            produit_line_id__in=produit_line_ids,
            bijouterie_id=vendor.bijouterie_id,
            is_reserve=False,
        ).values(
            "produit_line_id",
            "en_stock",
            "quantite_disponible",
        )
    }

    vendor_stock_after = {
        row["produit_line_id"]: row
        for row in VendorStock.objects.filter(
            vendor_id=vendor.id,
            bijouterie_id=vendor.bijouterie_id,
            produit_line_id__in=produit_line_ids,
        ).values(
            "produit_line_id",
            "quantite_allouee",
            "quantite_vendue",
        )
    }

    out_lines: List[Dict[str, Any]] = []

    for pl_id, qte in grouped.items():
        stock_row = stock_after.get(pl_id, {})
        vendor_stock_row = vendor_stock_after.get(pl_id, {})

        magasin_en_stock = int(stock_row.get("en_stock") or 0)
        magasin_disponible = int(stock_row.get("quantite_disponible") or 0)

        vendor_allouee = int(vendor_stock_row.get("quantite_allouee") or 0)
        vendor_vendue = int(vendor_stock_row.get("quantite_vendue") or 0)

        out_lines.append({
            "produit_line_id": int(pl_id),
            "transfere": int(qte),

            "magasin_en_stock": magasin_en_stock,
            "magasin_disponible": magasin_disponible,

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
    
    