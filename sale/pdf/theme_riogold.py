# sale/pdf/theme_riogold.py

import os

from django.conf import settings
from reportlab.lib import colors

# =========================
# 🎨 COULEURS RIO-GOLD
# =========================

BLACK = colors.black
WHITE = colors.white

# Gris premium
DARK = colors.HexColor("#2B2B2B")       # gris foncé (remplace noir dur)
MID = colors.HexColor("#EAEAEA")        # gris clair
LINE = colors.HexColor("#D0D0D0")       # lignes tableau
MUTED = colors.HexColor("#6B6B6B")      # texte secondaire

# Couleur luxe
GOLD = colors.HexColor("#D4AF37")


# =========================
# 🧰 UTILS TEXTE
# =========================

def safe(value):
    return "" if value is None else str(value)


def money_fcfa(value):
    try:
        value = float(value or 0)
    except Exception:
        value = 0
    return f"{int(value):,}".replace(",", " ") + " FCFA"


# =========================
# 🧾 UI HELPERS
# =========================

def pill(c, x, y, w, h, fill, radius=3):
    c.setFillColor(fill)
    c.roundRect(x, y, w, h, radius, stroke=0, fill=1)


# =========================
# 🖼️ LOGO
# =========================

def _safe_path(*parts):
    return os.path.normpath(os.path.join(*parts))


def _file_exists(path):
    return bool(path and os.path.exists(path))


def get_logo_noir():
    path = _safe_path(settings.MEDIA_ROOT, "logo", "logo_noir.png")
    return path if _file_exists(path) else None


def get_logo_blanc():
    path = _safe_path(settings.MEDIA_ROOT, "logo", "logo_blanc.png")
    return path if _file_exists(path) else None



