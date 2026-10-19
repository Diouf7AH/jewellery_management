# sale/pdf/facture_A5_portrait/theme.py

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from django.conf import settings
from reportlab.lib import colors

from sale.services.facture_pdf_data_service import validate_pdf_amount
from sale.services.pdf_amount_validation import validate_pdf_amount

# ============================================================
# 1. COULEURS RIO-GOLD
# ============================================================

BLACK = colors.black
WHITE = colors.white

DARK = colors.HexColor("#2B2B2B")
MID = colors.HexColor("#EAEAEA")
LINE = colors.HexColor("#D0D0D0")
MUTED = colors.HexColor("#6B6B6B")

GOLD = colors.HexColor("#D4AF37")


# ============================================================
# 2. UTILITAIRES TEXTE
# ============================================================

def safe(value) -> str:
    """
    Convertit une valeur en chaîne de caractères.

    Exemples :
        None       -> ""
        150000     -> "150000"
        "Rio-Gold" -> "Rio-Gold"
    """

    if value is None:
        return ""

    return str(value)


# ============================================================
# 3. FORMATAGE DES MONTANTS FCFA
# ============================================================
def money_fcfa(value) -> str:
    montant = validate_pdf_amount(
        value,
        "montant_affichage",
    )

    montant = montant.quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    return f"{montant:,.0f}".replace(",", " ") + " FCFA"

# ============================================================
# 4. OUTILS GRAPHIQUES REPORTLAB
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

    Paramètres :
        c      : Canvas ReportLab
        x, y   : Position
        w, h   : Dimensions
        fill   : Couleur de remplissage
        radius : Rayon des coins

    L'état graphique du canvas est restauré
    après le dessin.
    """

    if w <= 0 or h <= 0:
        return

    radius = max(
        0,
        min(
            radius,
            w / 2,
            h / 2,
        ),
    )

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
# 5. GESTION DES LOGOS
# ============================================================

def _logo_path(
    filename: str,
) -> Optional[str]:
    """
    Recherche un logo dans :

        MEDIA_ROOT/logo/

    Sécurité :
        - Nom de fichier simple uniquement.
        - Aucun chemin absolu.
        - Aucun chemin parent.
        - Le fichier doit exister.
        - Le fichier doit être régulier.

    Retour :
        Chemin absolu du logo si trouvé.
        None sinon.
    """

    media_root = getattr(
        settings,
        "MEDIA_ROOT",
        None,
    )

    if not media_root:
        return None

    if not filename:
        return None

    filename = str(filename)

    # Refuser les chemins comportant des séparateurs
    # ou des références au dossier parent.
    if (
        filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
    ):
        return None

    try:
        logo_dir = (
            Path(media_root)
            / "logo"
        ).resolve()

        logo_path = (
            logo_dir
            / filename
        ).resolve()

        # Empêcher la sortie du dossier logo.
        if logo_path.parent != logo_dir:
            return None

        if not logo_path.is_file():
            return None

        return str(logo_path)

    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
    ):
        return None


# ============================================================
# 6. LOGO DORÉ
# ============================================================

def get_logo_gold() -> Optional[str]:
    """
    Retourne le chemin du logo doré.

    Fichier :
        MEDIA_ROOT/logo/gold_logo.png
    """

    return _logo_path(
        "gold_logo.png"
    )


# ============================================================
# 7. LOGO NOIR
# ============================================================

def get_logo_noir() -> Optional[str]:
    """
    Retourne le chemin du logo noir.

    Fichier :
        MEDIA_ROOT/logo/logo_noir.png
    """

    return _logo_path(
        "logo_noir.png"
    )


# ============================================================
# 8. LOGO BLANC
# ============================================================

def get_logo_blanc() -> Optional[str]:
    """
    Retourne le chemin du logo blanc.

    Fichier :
        MEDIA_ROOT/logo/logo_blanc.png
    """

    return _logo_path(
        "logo_blanc.png"
    )


# ============================================================
# 9. EXPORTS
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

