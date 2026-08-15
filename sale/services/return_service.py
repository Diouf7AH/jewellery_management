# sale/services/return_service.py

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Sum
from django.utils import timezone

from inventory.models import Bucket, InventoryMovement, MovementType
from sale.models import Facture, Vente
from stock.models import Stock

RETURN_DELAY_HOURS = 72


@transaction.atomic
def return_paid_sale_to_bijouterie(
    *,
    facture: Facture,
    return_lines: list[dict[str, Any]],
    user,
    reason: str = "",
) -> dict:
    """
    Retour physique d'une vente payée.

    Cycle :
        RETURN_IN
        EXTERNAL → BIJOUTERIE

    Effets :
        Stock.en_stock += quantité
        Stock.quantite_totale += quantité

    Ne modifie jamais :
        VendorStock.quantite_allouee
        VendorStock.quantite_vendue
    """

    facture = (
        Facture.objects
        .select_for_update()
        .select_related(
            "vente",
            "bijouterie",
        )
        .get(pk=facture.pk)
    )

    vente = facture.vente

    if not vente:
        raise ValidationError({
            "facture": "Cette facture n'est associée à aucune vente."
        })

    if facture.status != Facture.STAT_PAYE:
        raise ValidationError({
            "facture": (
                "Seule une facture entièrement payée "
                "peut faire l'objet d'un retour."
            )
        })

    if not getattr(facture, "stock_consumed", False):
        raise ValidationError({
            "facture": (
                "Le stock de cette facture n'a pas été consommé."
            )
        })

    # Utilise de préférence la date réelle du paiement.
    paid_at = (
        getattr(facture, "paid_at", None)
        or getattr(facture, "signed_at", None)
        or getattr(facture, "updated_at", None)
    )

    if not paid_at:
        raise ValidationError({
            "facture": "La date de paiement est introuvable."
        })

    deadline = paid_at + timedelta(hours=RETURN_DELAY_HOURS)

    if timezone.now() > deadline:
        raise ValidationError({
            "facture": (
                "Le délai de retour de 72 heures est dépassé."
            )
        })

    if not facture.bijouterie_id:
        raise ValidationError({
            "bijouterie": "La bijouterie de la facture est introuvable."
        })

    if not isinstance(return_lines, list) or not return_lines:
        raise ValidationError({
            "lignes": "Au moins une ligne de retour est obligatoire."
        })

    returned_qty = 0
    movements_created = 0
    output_lines = []

    for index, item in enumerate(return_lines):
        try:
            produit_line_id = int(item.get("produit_line_id"))
            qty = int(item.get("quantite"))
        except (TypeError, ValueError, AttributeError):
            raise ValidationError({
                f"lignes[{index}]": (
                    "produit_line_id et quantite doivent être valides."
                )
            })

        if qty <= 0:
            raise ValidationError({
                f"lignes[{index}].quantite": (
                    "La quantité doit être supérieure ou égale à 1."
                )
            })

        # IMPORTANT :
        # vérifier ici que cette ProduitLine a réellement été consommée
        # par un SALE_OUT appartenant à cette vente/facture.
        sold_movements = (
            InventoryMovement.objects
            .select_for_update()
            .filter(
                facture=facture,
                vente=vente,
                produit_line_id=produit_line_id,
                movement_type=MovementType.SALE_OUT,
                src_bucket=Bucket.VENDOR,
                dst_bucket=Bucket.EXTERNAL,
            )
        )

        sold_qty = sum(
            int(m.qty or 0)
            for m in sold_movements
        )

        already_returned_qty = (
            InventoryMovement.objects
            .filter(
                facture=facture,
                vente=vente,
                produit_line_id=produit_line_id,
                movement_type=MovementType.RETURN_IN,
                src_bucket=Bucket.EXTERNAL,
                dst_bucket=Bucket.BIJOUTERIE,
            )
            .aggregate(total=Sum("qty"))
            .get("total")
            or 0
        )

        available_to_return = (
            int(sold_qty)
            - int(already_returned_qty)
        )

        if qty > available_to_return:
            raise ValidationError({
                f"lignes[{index}].quantite": (
                    "Quantité retournée trop élevée. "
                    f"Vendu : {sold_qty}, "
                    f"déjà retourné : {already_returned_qty}, "
                    f"retournable : {available_to_return}."
                )
            })

        try:
            stock = (
                Stock.objects
                .select_for_update()
                .select_related(
                    "produit_line",
                    "produit_line__produit",
                    "produit_line__lot",
                )
                .get(
                    produit_line_id=produit_line_id,
                    bijouterie_id=facture.bijouterie_id,
                )
            )

        except Stock.DoesNotExist:
            raise ValidationError({
                f"lignes[{index}].produit_line_id": (
                    "Stock magasin introuvable pour cette ProduitLine."
                )
            })

        Stock.objects.filter(pk=stock.pk).update(
            en_stock=F("en_stock") + qty,
            quantite_totale=F("quantite_totale") + qty,
            updated_at=timezone.now(),
        )

        InventoryMovement.objects.create(
            produit_id=stock.produit_line.produit_id,
            produit_line_id=produit_line_id,

            movement_type=MovementType.RETURN_IN,
            qty=qty,

            src_bucket=Bucket.EXTERNAL,
            dst_bucket=Bucket.BIJOUTERIE,
            dst_bijouterie_id=facture.bijouterie_id,

            vendor_id=getattr(vente, "vendor_id", None),

            lot_id=stock.produit_line.lot_id,
            achat_id=stock.produit_line.lot.achat_id,

            vente=vente,
            facture=facture,

            reason=(
                reason.strip()
                or "Retour client dans le délai de 72 heures."
            ),

            occurred_at=timezone.now(),
            created_by=user,
        )

        returned_qty += qty
        movements_created += 1

        output_lines.append({
            "produit_line_id": produit_line_id,
            "quantite_retournee": qty,
        })

    return {
        "facture_id": facture.id,
        "numero_facture": facture.numero_facture,
        "vente_id": vente.id,
        "bijouterie_id": facture.bijouterie_id,
        "quantite_retournee": returned_qty,
        "movements_created": movements_created,
        "lignes": output_lines,
    }