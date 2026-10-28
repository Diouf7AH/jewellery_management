# inventory/services/inventory_audit_service.py

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

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
    Vérifie la cohérence des relations communes
    aux mouvements SALE_OUT et RETURN_IN.

    Règles :
    - Facture, vente, ligne et ProduitLine obligatoires.
    - La facture appartient à la vente.
    - La ligne appartient à la vente.
    - La ProduitLine est celle sélectionnée à la vente.
    - La ProduitLine possède un produit et un lot.
    - Le vendeur appartient à la bonne bijouterie.
    """

    # ========================================================
    # 1. OBJETS OBLIGATOIRES
    # ========================================================

    if facture is None or facture.pk is None:
        raise ValidationError("facture requise.")

    if vente is None or vente.pk is None:
        raise ValidationError("vente requise.")

    if vente_ligne is None or vente_ligne.pk is None:
        raise ValidationError("vente_ligne requise.")

    if produit_line is None or produit_line.pk is None:
        raise ValidationError("produit_line requise.")

    # ========================================================
    # 2. FACTURE / VENTE
    # ========================================================

    if facture.vente_id != vente.pk:
        raise ValidationError(
            "La facture ne correspond pas à la vente."
        )

    if facture.bijouterie_id != vente.bijouterie_id:
        raise ValidationError(
            "La facture et la vente appartiennent "
            "à des bijouteries différentes."
        )

    # ========================================================
    # 3. LIGNE DE VENTE / VENTE
    # ========================================================

    if vente_ligne.vente_id != vente.pk:
        raise ValidationError(
            "La ligne de vente ne correspond pas "
            "à la vente."
        )

    # ========================================================
    # 4. PRODUITLINE OBLIGATOIRE
    # ========================================================

    if not vente_ligne.produit_line_id:
        raise ValidationError(
            "La ligne de vente ne possède "
            "pas de ProduitLine."
        )

    if not produit_line.produit_id:
        raise ValidationError(
            "La ProduitLine ne possède pas de produit."
        )

    if not produit_line.lot_id:
        raise ValidationError(
            "La ProduitLine doit être rattachée "
            "à un lot."
        )

    # ========================================================
    # 5. VÉRIFIER LA PRODUITLINE EXACTE
    # ========================================================

    if vente_ligne.produit_line_id != produit_line.pk:
        raise ValidationError({
            "produit_line": (
                "La ProduitLine du mouvement est différente "
                "de celle sélectionnée lors de la vente."
            )
        })

    # ========================================================
    # 6. VENDEUR
    # ========================================================

    vendor = (
        getattr(vente_ligne, "vendor", None)
        or getattr(vente, "vendor", None)
    )

    if vendor is None or vendor.pk is None:
        raise ValidationError(
            "Vendeur requis pour le mouvement."
        )

    # ========================================================
    # 7. VENDEUR DE LA VENTE
    # ========================================================

    if (
        vente.vendor_id
        and vendor.pk != vente.vendor_id
    ):
        raise ValidationError(
            "Le vendeur de la ligne est différent "
            "du vendeur de la vente."
        )

    # ========================================================
    # 8. VENDEUR / BIJOUTERIE
    # ========================================================

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
    Enregistre le mouvement SALE_OUT d'une ProduitLine exacte.

    Flux :
        VENDOR -> EXTERNAL

    Règles :
    - La facture doit être intégralement payée.
    - La vente doit appartenir à la facture.
    - La ProduitLine doit correspondre à la ligne vendue.
    - Le vendeur doit appartenir à la bijouterie.
    - Aucun FIFO.
    - Aucun changement de lot.
    - Aucun décrément de ProduitLine.quantite.
    - Aucun décrément supplémentaire de VendorStock.
    - Le mouvement SALE_OUT est verrouillé après création.
    - Un doublon SALE_OUT doit provoquer une erreur.

    IMPORTANT :
    Cette fonction doit être appelée dans la même
    transaction atomique que consume_vendor_stock().

    L'idempotence globale est gérée par
    confirm_sale_out_from_vendor().
    """

    # ========================================================
    # 1. TRANSACTION OBLIGATOIRE
    # ========================================================

    if not transaction.get_connection().in_atomic_block:
        raise ValidationError(
            "La création du mouvement SALE_OUT nécessite "
            "une transaction atomique."
        )

    # ========================================================
    # 2. QUANTITÉ
    # ========================================================

    q = _normalize_qty(qty)

    # ========================================================
    # 3. VALIDATION DES RELATIONS
    # ========================================================

    vendor = _validate_sale_relations(
        facture=facture,
        vente=vente,
        vente_ligne=vente_ligne,
        produit_line=produit_line,
    )

    # ========================================================
    # 4. FACTURE INTÉGRALEMENT PAYÉE
    # ========================================================

    if (
        facture.status != facture.STAT_PAYE
        or not facture.est_reglee()
    ):
        raise ValidationError(
            "SALE_OUT interdit : la facture doit être "
            "intégralement payée."
        )

    # ========================================================
    # 5. VÉRIFICATION DE LA BIJOUTERIE
    # ========================================================

    if vente.bijouterie_id != facture.bijouterie_id:
        raise ValidationError(
            "La vente n'appartient pas à la bijouterie "
            "de la facture."
        )

    if vendor.bijouterie_id != facture.bijouterie_id:
        raise ValidationError(
            "Le vendeur n'appartient pas à la bijouterie "
            "de la facture."
        )

    if (
        produit_line.lot.achat.bijouterie_id
        != facture.bijouterie_id
    ):
        raise ValidationError(
            "La ProduitLine n'appartient pas "
            "à cette bijouterie."
        )

    # ========================================================
    # 6. CRÉATION DU MOUVEMENT SALE_OUT
    # ========================================================

    movement = log_move(
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

    # ========================================================
    # 7. CONFIRMATION DE L'ENREGISTREMENT
    # ========================================================

    if movement.pk is None:
        raise ValidationError(
            "Le mouvement SALE_OUT n'a pas été enregistré."
        )

    # ========================================================
    # 8. CONFIRMATION
    # ========================================================

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
