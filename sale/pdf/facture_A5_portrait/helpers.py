# sale/pdf/facture_A5_portrait/helpers.py

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from ..theme_riogold import safe


def dec(value, default=Decimal("0")):
    try:
        if value in (None, ""):
            return default

        return Decimal(str(value))

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):
        return default


def to_int(value, default=0):
    try:
        if value in (None, ""):
            return default

        return int(value)

    except Exception:
        return default


def truncate(text, max_len):
    text = safe(text)

    if len(text) <= max_len:
        return text

    return (
        text[: max_len - 1]
        + "…"
    )


def etat_label(value):
    value = (
        safe(value)
        .strip()
        .upper()
    )

    if value in {
        "N",
        "NEUF",
    }:
        return "Neuf"

    if value in {
        "O",
        "OCCASION",
    }:
        return "Occasion"

    return safe(value)


def format_purete(value):
    value = safe(value).strip()

    return value or ""


def discount_total(data):
    """
    Total des réductions occasion de la facture.
    """

    total = Decimal("0")

    for line in data.get("lines") or []:

        total += dec(
            line.get(
                "reduction_occasion"
            )
        )

    return total

