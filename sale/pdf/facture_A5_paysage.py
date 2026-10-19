# sale/pdf/facture_A5_portrait/theme.py

from __future__ import annotations

import os
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Optional

from django.conf import settings
from reportlab.lib import colors

# ============================================================
# COULEURS RIO-GOLD
# ============================================================

BLACK = colors.black
WHITE = colors.white

DARK = colors.HexColor("#2B2B2B")
MID = colors.HexColor("#EAEAEA")
LINE = colors.HexColor("#D0D0D0")
MUTED = colors.HexColor("#6B6B6B")

GOLD = colors.HexColor("#D4AF37")


# ============================================================
# UTILITAIRES TEXTE
# ============================================================

def safe(value) -> str:
    """
    Convertit une valeur en chaîne de caractères.
    """
    return "" if value is None else str(value)


# ============================================================
# FORMATAGE DES MONTANTS FCFA
# ============================================================

def money_fcfa(value) -> str:
    """
    Formate un montant en FCFA avec arrondi HALF_UP.

    Exemples :
        150000       -> 150 000 FCFA
        150000.50    -> 150 001 FCFA
        None         -> 0 FCFA
        ""           -> 0 FCFA
        "invalid"    -> 0 FCFA
    """
    try:
        montant = Decimal(
            str(value if value not in (None, "") else "0")
        )

        if not montant.is_finite():
            raise InvalidOperation

        montant = montant.quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )

    except (InvalidOperation, ValueError, TypeError):
        montant = Decimal("0")

    montant_formate = f"{montant:,.0f}".replace(",", " ")

    return f"{montant_formate} FCFA"


# ============================================================
# OUTILS GRAPHIQUES REPORTLAB
# ============================================================

def pill(
    c,
    x,
    y,
    w,
    h,
    fill,
    radius=3,
):
    """
    Dessine un rectangle arrondi rempli.
    """
    c.saveState()

    try:
        c.setFillColor(fill)

        c.roundRect(
            x,
            y,
            w,
            h,
            radius,
            stroke=0,
            fill=1,
        )
    finally:
        c.restoreState()


# ============================================================
# GESTION DES LOGOS
# ============================================================

def _logo_path(filename: str) -> Optional[str]:
    """
    Recherche un logo dans MEDIA_ROOT/logo/.
    Retourne None lorsque le fichier est absent.
    """
    media_root = getattr(settings, "MEDIA_ROOT", None)

    if not media_root:
        return None

    path = os.path.normpath(
        os.path.join(
            os.fspath(media_root),
            "logo",
            filename,
        )
    )

    return path if os.path.isfile(path) else None


def get_logo_gold() -> Optional[str]:
    """
    Retourne le chemin du logo doré.
    """
    return _logo_path("gold_logo.png")


def get_logo_noir() -> Optional[str]:
    """
    Retourne le chemin du logo noir.
    """
    return _logo_path("logo_noir.png")


def get_logo_blanc() -> Optional[str]:
    """
    Retourne le chemin du logo blanc.
    """
    return _logo_path("logo_blanc.png")


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    "BLACK",
    "WHITE",
    "DARK",
    "MID",
    "LINE",
    "MUTED",
    "GOLD",
    "safe",
    "money_fcfa",
    "pill",
    "get_logo_gold",
    "get_logo_noir",
    "get_logo_blanc",
]

