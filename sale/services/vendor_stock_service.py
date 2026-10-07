# sale/services/vendor_stock_service.py

from __future__ import annotations

from typing import Dict, List

from django.core.exceptions import ValidationError
from django.db.models import F

from stock.models import VendorStock

# =============================================================
# HELPERS
# =============================================================


def _validate_common(
    *,
    vendor,
    bijouterie,
    produit_line,
    quantite: int,
) -> int:
    """
    Validations communes pour les opérations
    sur le stock vendeur d'une ProduitLine précise.
    """

    try:
        q = int(quantite)

    except (TypeError, ValueError):
        raise ValidationError({
            "quantite": (
                "La quantité doit être un entier valide."
            )
        })

    if q <= 0:
        raise ValidationError({
            "quantite": (
                "La quantité doit être supérieure "
                "ou égale à 1."
            )
        })

    if not vendor:
        raise ValidationError({
            "vendor": (
                "Le vendeur est obligatoire."
            )
        })

    if not bijouterie:
        raise ValidationError({
            "bijouterie": (
                "La bijouterie est obligatoire."
            )
        })

    if not produit_line:
        raise ValidationError({
            "produit_line": (
                "La ProduitLine est obligatoire."
            )
        })

    # =========================================================
    # VENDEUR ↔ BIJOUTERIE
    # =========================================================

    if vendor.bijouterie_id != bijouterie.id:
        raise ValidationError({
            "vendor": (
                "Le vendeur n'appartient pas "
                "à la bijouterie sélectionnée."
            )
        })

    # =========================================================
    # PRODUIT_LINE
    # =========================================================

    if produit_line.produit_id is None:
        raise ValidationError({
            "produit_line": (
                "La ProduitLine n'est associée "
                "à aucun produit."
            )
        })

    if produit_line.lot_id is None:
        raise ValidationError({
            "produit_line": (
                "La ProduitLine n'est associée "
                "à aucun lot."
            )
        })

    return q


def _get_vendor_stock(
    *,
    vendor,
    bijouterie,
    produit_line,
    lock: bool = False,
):
    """
    Retourne le VendorStock correspondant exactement à :

        vendeur
        + bijouterie
        + ProduitLine

    Si lock=True, verrouille la ligne SQL avec
    select_for_update().

    À utiliser uniquement dans une transaction atomique
    lorsque lock=True.
    """

    qs = (
        VendorStock.objects
        .select_related(
            "produit_line",
            "produit_line__produit",
            "produit_line__lot",
        )
        .filter(
            vendor=vendor,
            bijouterie=bijouterie,
            produit_line=produit_line,
        )
    )

    if lock:
        qs = qs.select_for_update()

    vendor_stock = qs.first()

    if not vendor_stock:
        identifiant = (
            getattr(
                produit_line,
                "uuid",
                None,
            )
            or produit_line.pk
        )

        raise ValidationError({
            "stock": (
                "Aucun stock vendeur ne correspond "
                f"à la ProduitLine {identifiant}."
            )
        })

    return vendor_stock


def _available_quantity(
    vendor_stock,
) -> int:
    """
    Quantité encore disponible chez le vendeur.

    disponible =
        quantite_allouee
        - quantite_vendue
    """

    allouee = int(
        vendor_stock.quantite_allouee
        or 0
    )

    vendue = int(
        vendor_stock.quantite_vendue
        or 0
    )

    disponible = allouee - vendue

    return max(
        disponible,
        0,
    )


# =============================================================
# VÉRIFICATION DISPONIBILITÉ
# =============================================================


# def ensure_vendor_stock_available(
#     *,
#     vendor,
#     bijouterie,
#     produit_line,
#     quantite: int,
# ) -> int:
#     """
#     Vérifie que le vendeur possède suffisamment de stock
#     pour une ProduitLine précise.

#     IMPORTANT :
#     ---------------------------------------------------------
#     Cette fonction NE CONSOMME PAS le stock.

#     Elle est utilisée lors de la création de la vente /
#     PROFORMA.

#     Aucun FIFO.
#     Aucun changement de ProduitLine.
#     Aucun UPDATE VendorStock.

#     Retour :
#         quantité actuellement disponible.
#     """

#     q = _validate_common(
#         vendor=vendor,
#         bijouterie=bijouterie,
#         produit_line=produit_line,
#         quantite=quantite,
#     )

#     vendor_stock = _get_vendor_stock(
#         vendor=vendor,
#         bijouterie=bijouterie,
#         produit_line=produit_line,
#         lock=False,
#     )

#     disponible = _available_quantity(
#         vendor_stock
#     )

#     if disponible < q:

#         identifiant = (
#             getattr(
#                 produit_line,
#                 "uuid",
#                 None,
#             )
#             or produit_line.pk
#         )

#         produit = produit_line.produit

#         produit_nom = (
#             getattr(
#                 produit,
#                 "nom",
#                 None,
#             )
#             or f"Produit #{produit.pk}"
#         )

#         raise ValidationError({
#             "stock": (
#                 f"Stock vendeur insuffisant pour "
#                 f"'{produit_nom}' "
#                 f"(ProduitLine {identifiant}). "
#                 f"Disponible : {disponible}, "
#                 f"demandé : {q}."
#             )
#         })

#     return disponible

def ensure_vendor_stock_available(
    *,
    vendor,
    bijouterie,
    produit_line,
    quantite: int,
) -> int:
    """
    Vérifie que le vendeur possède suffisamment de stock
    disponible pour une ProduitLine exacte.

    Cette fonction :
    - ne modifie pas VendorStock ;
    - ne crée aucun InventoryMovement ;
    - ne consomme aucun stock ;
    - ne fait aucun FIFO ;
    - contrôle uniquement la disponibilité.

    Retourne :
        quantité actuellement disponible.

    Lève :
        ValidationError si le stock est insuffisant
        ou si les données sont incohérentes.
    """

    # =========================================================
    # 1. QUANTITÉ
    # =========================================================

    try:
        q = int(quantite)

    except (TypeError, ValueError):
        raise ValidationError(
            {
                "quantite": (
                    "La quantité doit être "
                    "un entier valide."
                )
            }
        )

    if q <= 0:
        raise ValidationError(
            {
                "quantite": (
                    "La quantité doit être "
                    "supérieure ou égale à 1."
                )
            }
        )

    # =========================================================
    # 2. VENDEUR
    # =========================================================

    if not vendor:
        raise ValidationError(
            {
                "vendor": (
                    "Le vendeur est obligatoire."
                )
            }
        )

    if not getattr(
        vendor,
        "verifie",
        False,
    ):
        raise ValidationError(
            {
                "vendor": (
                    "Le vendeur est désactivé "
                    "ou non vérifié."
                )
            }
        )

    # =========================================================
    # 3. BIJOUTERIE
    # =========================================================

    if not bijouterie:
        raise ValidationError(
            {
                "bijouterie": (
                    "La bijouterie est obligatoire."
                )
            }
        )

    if (
        vendor.bijouterie_id
        != bijouterie.id
    ):
        raise ValidationError(
            {
                "vendor": (
                    "Le vendeur n'appartient pas "
                    "à la bijouterie sélectionnée."
                )
            }
        )

    # =========================================================
    # 4. PRODUIT LINE
    # =========================================================

    if not produit_line:
        raise ValidationError(
            {
                "produit_line": (
                    "La ProduitLine est obligatoire."
                )
            }
        )

    if not produit_line.produit_id:
        raise ValidationError(
            {
                "produit_line": (
                    "La ProduitLine n'est associée "
                    "à aucun produit."
                )
            }
        )

    if not produit_line.lot_id:
        raise ValidationError(
            {
                "produit_line": (
                    "La ProduitLine n'est associée "
                    "à aucun lot."
                )
            }
        )

    # =========================================================
    # 5. STOCK VENDEUR EXACT
    # =========================================================
    #
    # IMPORTANT :
    #
    # On ne fait PAS :
    #
    # produit_line__produit=produit
    #
    # On recherche exactement :
    #
    # vendor + bijouterie + produit_line
    #
    # =========================================================

    vendor_stock = (
        VendorStock.objects
        .select_related(
            "vendor",
            "bijouterie",
            "produit_line",
            "produit_line__produit",
            "produit_line__lot",
        )
        .filter(
            vendor=vendor,
            bijouterie=bijouterie,
            produit_line=produit_line,
        )
        .first()
    )

    if not vendor_stock:
        produit = produit_line.produit

        produit_nom = (
            getattr(
                produit,
                "nom",
                None,
            )
            or f"Produit #{produit.pk}"
        )

        raise ValidationError(
            {
                "stock": (
                    f"Aucun stock vendeur disponible "
                    f"pour '{produit_nom}' "
                    f"(ProduitLine #{produit_line.pk})."
                )
            }
        )

    # =========================================================
    # 6. QUANTITÉ DISPONIBLE
    # =========================================================

    quantite_allouee = int(
        vendor_stock.quantite_allouee
        or 0
    )

    quantite_vendue = int(
        vendor_stock.quantite_vendue
        or 0
    )

    disponible = max(
        quantite_allouee
        - quantite_vendue,
        0,
    )

    # =========================================================
    # 7. CONTRÔLE
    # =========================================================

    if disponible < q:
        produit = produit_line.produit

        produit_nom = (
            getattr(
                produit,
                "nom",
                None,
            )
            or f"Produit #{produit.pk}"
        )

        raise ValidationError(
            {
                "stock": (
                    f"Stock vendeur insuffisant pour "
                    f"'{produit_nom}' "
                    f"(ProduitLine #{produit_line.pk}). "
                    f"Disponible : {disponible}, "
                    f"demandé : {q}."
                )
            }
        )

    # =========================================================
    # 8. RETOUR
    # =========================================================

    return disponible

# =============================================================
# CONSOMMATION STOCK VENDEUR
# =============================================================


def consume_vendor_stock(
    *,
    vendor,
    bijouterie,
    produit_line,
    quantite: int,
) -> List[Dict[str, int]]:
    """
    Consomme le stock vendeur correspondant exactement
    à la ProduitLine vendue.

    Cette fonction est appelée lors de la confirmation
    définitive de la vente après paiement.

    Effet :

        VendorStock.quantite_vendue += quantite

    IMPORTANT :
    ---------------------------------------------------------
    - ProduitLine exacte.
    - Aucun FIFO.
    - Aucun changement de lot.
    - Aucun fallback vers une autre ProduitLine.
    - La fonction doit être appelée depuis
      transaction.atomic().
    - select_for_update() protège contre les ventes
      concurrentes.

    Retour :

        [
            {
                "produit_line_id": 12,
                "qty": 1,
            }
        ]

    Le retour client ne doit jamais annuler cette
    consommation.

    Un retour utilise :

        RETURN_IN
        EXTERNAL -> BIJOUTERIE
    """

    q = _validate_common(
        vendor=vendor,
        bijouterie=bijouterie,
        produit_line=produit_line,
        quantite=quantite,
    )

    # =========================================================
    # LOCK VendorStock exact
    # =========================================================

    vendor_stock = _get_vendor_stock(
        vendor=vendor,
        bijouterie=bijouterie,
        produit_line=produit_line,
        lock=True,
    )

    # =========================================================
    # DISPONIBILITÉ
    # =========================================================

    disponible = _available_quantity(
        vendor_stock
    )

    if disponible < q:

        identifiant = (
            getattr(
                produit_line,
                "uuid",
                None,
            )
            or produit_line.pk
        )

        raise ValidationError({
            "stock": (
                "Stock vendeur insuffisant pour "
                f"la ProduitLine {identifiant}. "
                f"Disponible : {disponible}, "
                f"demandé : {q}."
            )
        })

    # =========================================================
    # UPDATE ATOMIQUE
    # =========================================================
    #
    # La condition :
    #
    # quantite_vendue <= quantite_allouee - q
    #
    # garantit qu'on ne peut jamais dépasser
    # la quantité allouée.
    # =========================================================

    updated = (
        VendorStock.objects
        .filter(
            pk=vendor_stock.pk,
            quantite_vendue__lte=(
                F("quantite_allouee") - q
            ),
        )
        .update(
            quantite_vendue=(
                F("quantite_vendue") + q
            )
        )
    )

    if updated != 1:
        raise ValidationError({
            "stock": (
                "Conflit lors de la consommation "
                "du stock vendeur. "
                "Veuillez réessayer."
            )
        })

    # =========================================================
    # RÉSULTAT
    # =========================================================

    return [
        {
            "produit_line_id": int(
                produit_line.pk
            ),
            "qty": q,
        }
    ]
    
    