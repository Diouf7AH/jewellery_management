# inventory/services/inventory_audit_service.py

from __future__ import annotations

from django.core.exceptions import ValidationError

from inventory.models import Bucket, MovementType
from inventory.services.inventory_movement_service import (_normalize_qty,
                                                           log_move)

# ============================================================
# HELPERS
# ============================================================

def _validate_sale_relations(
    *,
    facture,
    vente,
    vente_ligne,
    produit_line,
):
    """
    Vérifie la cohérence des relations communes aux
    mouvements SALE_OUT et RETURN_IN.
    """

    if facture is None or facture.pk is None:
        raise ValidationError("facture requise.")

    if vente is None or vente.pk is None:
        raise ValidationError("vente requise.")

    if vente_ligne is None or vente_ligne.pk is None:
        raise ValidationError("vente_ligne requise.")

    if produit_line is None or produit_line.pk is None:
        raise ValidationError("produit_line requise.")

    if facture.vente_id != vente.pk:
        raise ValidationError(
            "La facture ne correspond pas à la vente."
        )

    if vente_ligne.vente_id != vente.pk:
        raise ValidationError(
            "La ligne de vente ne correspond pas à la vente."
        )

    if not vente_ligne.produit_id:
        raise ValidationError(
            "La ligne de vente ne possède pas de produit."
        )

    if not produit_line.produit_id:
        raise ValidationError(
            "La ProduitLine ne possède pas de produit."
        )

    if not produit_line.lot_id:
        raise ValidationError(
            "La ProduitLine doit être rattachée à un lot."
        )

    if produit_line.produit_id != vente_ligne.produit_id:
        raise ValidationError({
            "produit_line": (
                "La ProduitLine ne correspond pas "
                "au produit de la ligne de vente."
            )
        })

    if vente_ligne.produit_line_id != produit_line.pk:
        raise ValidationError({
            "produit_line": (
                "La ProduitLine du mouvement est différente "
                "de celle sélectionnée lors de la vente."
            )
        })

    vendor = (
        getattr(vente_ligne, "vendor", None)
        or getattr(vente, "vendor", None)
    )

    if vendor is None or vendor.pk is None:
        raise ValidationError(
            "Vendeur requis pour le mouvement."
        )

    if (
        vente.vendor_id
        and vendor.pk != vente.vendor_id
    ):
        raise ValidationError(
            "Le vendeur de la ligne est différent "
            "du vendeur de la vente."
        )

    if vendor.bijouterie_id != facture.bijouterie_id:
        raise ValidationError(
            "Le vendeur n'appartient pas "
            "à la bijouterie de la facture."
        )

    return vendor


# ============================================================
# SALE_OUT : VENDOR -> EXTERNAL
# ============================================================

def create_sale_out_consumption(
    *,
    facture,
    vente,
    vente_ligne,
    produit_line,
    qty: int,
    by_user,
) -> bool:
    """
    Enregistre le mouvement SALE_OUT d'une ProduitLine précise.

    IMPORTANT :
    - La facture doit être intégralement payée.
    - consume_vendor_stock() doit avoir réussi.
    - La fonction doit être appelée dans la même transaction
      atomique que consume_vendor_stock().
    - Aucun FIFO.
    - Aucun décrément de ProduitLine.quantite.
    - Aucun nouveau décrément de VendorStock ici.

    L'idempotence globale est gérée par
    confirm_sale_out_from_vendor() et les contraintes SQL.
    """

    q = _normalize_qty(qty)

    vendor = _validate_sale_relations(
        facture=facture,
        vente=vente,
        vente_ligne=vente_ligne,
        produit_line=produit_line,
    )

    if facture.status != facture.STAT_PAYE:
        raise ValidationError(
            "SALE_OUT interdit : la facture n'est pas payée."
        )

    log_move(
        produit=produit_line.produit,
        qty=q,
        movement_type=MovementType.SALE_OUT,
        src_bucket=Bucket.VENDOR,
        src_bijouterie_id=facture.bijouterie_id,
        dst_bucket=Bucket.EXTERNAL,
        dst_bijouterie_id=None,
        vendor=vendor,
        unit_cost=None,
        achat=None,
        produit_line=produit_line,
        lot=produit_line.lot,
        vente=vente,
        vente_ligne=vente_ligne,
        facture=facture,
        user=by_user,
        stock_consumed=True,
        reason=(
            f"SALE_OUT | "
            f"vente={vente.numero_vente} | "
            f"facture={facture.numero_facture} | "
            f"ligne={vente_ligne.pk} | "
            f"vendor={vendor.pk} | "
            f"pl={produit_line.pk} | "
            f"pl_uuid={produit_line.uuid} | "
            f"lot={produit_line.lot_id}"
        ),
        lock=True,
    )

    return True


# ============================================================
# RETURN_IN : EXTERNAL -> BIJOUTERIE
# ============================================================

def create_return_in_consumption(
    *,
    facture,
    vente,
    vente_ligne,
    produit_line,
    qty: int,
    by_user,
) -> bool:
    """
    Enregistre un mouvement RETURN_IN.

    Flux :
        EXTERNAL -> BIJOUTERIE

    Le retour ne remet pas automatiquement la quantité
    dans VendorStock.

    Le mouvement est uniquement une trace d'inventaire.
    La réintégration physique du stock doit être gérée
    séparément par le service métier de retour.
    """

    q = _normalize_qty(qty)

    vendor = _validate_sale_relations(
        facture=facture,
        vente=vente,
        vente_ligne=vente_ligne,
        produit_line=produit_line,
    )

    log_move(
        produit=produit_line.produit,
        qty=q,
        movement_type=MovementType.RETURN_IN,
        src_bucket=Bucket.EXTERNAL,
        src_bijouterie_id=None,
        dst_bucket=Bucket.BIJOUTERIE,
        dst_bijouterie_id=facture.bijouterie_id,
        vendor=vendor,
        unit_cost=None,
        achat=None,
        produit_line=produit_line,
        lot=produit_line.lot,
        vente=vente,
        vente_ligne=vente_ligne,
        facture=facture,
        user=by_user,
        stock_consumed=False,
        reason=(
            f"RETURN_IN | "
            f"vente={vente.numero_vente} | "
            f"facture={facture.numero_facture} | "
            f"ligne={vente_ligne.pk} | "
            f"vendor={vendor.pk} | "
            f"pl={produit_line.pk} | "
            f"lot={produit_line.lot_id}"
        ),
        lock=True,
    )

    return True
