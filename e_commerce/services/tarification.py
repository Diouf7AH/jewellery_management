# e_commerce/services/tarification.py

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError

TWOPLACES = Decimal("0.01")
ZERO = Decimal("0.00")
CENT = Decimal("100")


def calculer_totaux_ecommerce(
    *,
    montant_ht,
    appliquer_tva,
    taux_tva,
    frais_transaction,
):
    montant_ht = Decimal(
        str(montant_ht or ZERO)
    ).quantize(
        TWOPLACES,
        rounding=ROUND_HALF_UP,
    )

    frais_transaction = Decimal(
        str(frais_transaction or ZERO)
    ).quantize(
        TWOPLACES,
        rounding=ROUND_HALF_UP,
    )

    # ============================================================
    # VALIDATIONS
    # ============================================================

    if montant_ht < ZERO:
        raise ValidationError(
            "Le montant HT ne peut pas être négatif."
        )

    if frais_transaction < ZERO:
        raise ValidationError(
            "Les frais de transaction "
            "ne peuvent pas être négatifs."
        )

    montant_tva = ZERO
    taux = ZERO

    # ============================================================
    # TVA
    # ============================================================

    if appliquer_tva:
        taux = Decimal(
            str(taux_tva or ZERO)
        ).quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )

        if taux < ZERO or taux > CENT:
            raise ValidationError(
                "Le taux de TVA doit être compris "
                "entre 0 et 100."
            )

        montant_tva = (
            montant_ht
            * taux
            / CENT
        ).quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )

    # ============================================================
    # MONTANT FINAL
    # ============================================================

    montant_a_payer = (
        montant_ht
        + montant_tva
        + frais_transaction
    ).quantize(
        TWOPLACES,
        rounding=ROUND_HALF_UP,
    )

    return {
        "montant_total": montant_ht,
        "montant_tva": montant_tva,
        "frais_transaction": frais_transaction,
        "montant_a_payer": montant_a_payer,
    }
    
    
