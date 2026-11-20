# sale/services/pdf_amount_validation.py

from __future__ import annotations

from decimal import Decimal, InvalidOperation

# ============================================================
# CONSTANTES
# ============================================================

CENTIME = Decimal("0.01")
ZERO = Decimal("0.00")


# ============================================================
# VALIDATION DES MONTANTS POUR PDF
# ============================================================

def validate_pdf_amount(
    value,
    field_name: str,
    *,
    allow_negative: bool = False,
) -> Decimal:
    """
    Valide un montant destiné à la génération PDF.

    Règles :
        - valeur obligatoire ;
        - booléens interdits ;
        - conversion Decimal ;
        - NaN et Infinity interdits ;
        - deux décimales maximum ;
        - aucun arrondi silencieux ;
        - montant négatif interdit par défaut ;
        - montant négatif autorisé si allow_negative=True.

    Exemples valides :
        15000
        "15000"
        "15000.5"
        "15000.50"
        Decimal("15000.50")

    Exemples invalides :
        None
        ""
        True
        "abc"
        "NaN"
        "Infinity"
        "15000.555"

    Retour :
        Decimal normalisé à deux décimales.

    Exception :
        ValueError.
    """

    # ========================================================
    # 1. VALIDATION DU NOM DU CHAMP
    # ========================================================

    if (
        not isinstance(field_name, str)
        or not field_name.strip()
    ):
        raise ValueError(
            "Le nom du champ est obligatoire."
        )

    field_name = field_name.strip()

    # ========================================================
    # 2. VALIDATION DE LA PRÉSENCE
    # ========================================================

    if (
        value is None
        or isinstance(value, bool)
        or (
            isinstance(value, str)
            and not value.strip()
        )
    ):
        raise ValueError(
            f"Le montant '{field_name}' "
            "est manquant ou invalide."
        )

    # ========================================================
    # 3. CONVERSION EN DECIMAL
    # ========================================================

    try:
        montant = Decimal(str(value))

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ) as exc:
        raise ValueError(
            f"Le montant '{field_name}' est invalide."
        ) from exc

    # ========================================================
    # 4. VÉRIFICATION DU NOMBRE FINI
    # ========================================================

    if not montant.is_finite():
        raise ValueError(
            f"Le montant '{field_name}' doit être fini."
        )

    # ========================================================
    # 5. VALIDATION DES MONTANTS NÉGATIFS
    # ========================================================

    if not allow_negative and montant < ZERO:
        raise ValueError(
            f"Le montant '{field_name}' "
            "ne peut pas être négatif."
        )

    # ========================================================
    # 6. VALIDATION DES DÉCIMALES
    # ========================================================

    try:
        montant_normalise = montant.quantize(
            CENTIME
        )

    except InvalidOperation as exc:
        raise ValueError(
            f"Le montant '{field_name}' "
            "est hors limites."
        ) from exc

    if montant != montant_normalise:
        raise ValueError(
            f"Le montant '{field_name}' "
            "ne peut pas dépasser deux décimales."
        )

    # ========================================================
    # 7. RETOUR
    # ========================================================

    return montant_normalise


