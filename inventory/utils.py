# inventory/utils.py

from __future__ import annotations

from datetime import date, datetime
from typing import Optional


def parse_int(value: Optional[str]) -> Optional[int]:
    """
    Convertit une chaîne en entier.

    Retourne None si la valeur est absente ou invalide.
    """

    if value in (None, "", "null", "None"):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_bool(value, default: bool = False) -> bool:
    """
    Convertit une valeur provenant des query params en booléen.
    """

    if value is None:
        return default

    return str(value).strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


def parse_date(value: Optional[str]) -> Optional[date]:
    """
    Convertit une date au format YYYY-MM-DD.
    """

    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    
