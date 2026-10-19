from __future__ import annotations

from decimal import Decimal, InvalidOperation


def validate_pdf_amount(
    value,
    field_name: str,
    *,
    allow_negative: bool = False,
) -> Decimal:

    if value is None or value == "":
        raise ValueError(
            f"Le montant '{field_name}' est manquant."
        )

    try:
        montant = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(
            f"Le montant '{field_name}' est invalide."
        ) from exc

    if not montant.is_finite():
        raise ValueError(
            f"Le montant '{field_name}' doit être fini."
        )

    if not allow_negative and montant < 0:
        raise ValueError(
            f"Le montant '{field_name}' ne peut pas être négatif."
        )

    return montant

