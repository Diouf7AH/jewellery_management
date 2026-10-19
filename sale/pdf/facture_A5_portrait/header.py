# sale/pdf/facture_A5_portrait/header.py

from __future__ import annotations

from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth

from .helpers import truncate
from .theme import DARK, GOLD, LINE, WHITE, get_logo_gold, safe

# ============================================================
# HELPERS D'AFFICHAGE
# ============================================================

def _fit_text(text, font_name, font_size, max_width):
    """
    Réduit un texte à la largeur disponible dans le PDF.
    """
    text = safe(text).strip()

    if not text:
        return ""

    if max_width <= 0:
        return ""

    if stringWidth(text, font_name, font_size) <= max_width:
        return text

    suffix = "..."

    while text and stringWidth(
        text + suffix,
        font_name,
        font_size,
    ) > max_width:
        text = text[:-1]

    return text + suffix if text else ""


def _phone_display(value):
    """
    Affiche le numéro sans répéter l'indicatif +221.
    """
    phone = safe(value).strip()

    if not phone:
        return ""

    normalized = phone.replace(" ", "")

    if normalized.startswith(("+221", "00221")):
        return phone

    if normalized.startswith("221") and len(normalized) == 12:
        return f"+{normalized}"

    return f"(+221) {phone}"


# ============================================================
# HEADER BIJOUTERIE
# ============================================================

def draw_header(c, w, h, data):
    """
    Dessine :
    - fond blanc ;
    - logo Rio-Gold ;
    - nom de la bijouterie ;
    - téléphone ;
    - adresse ;
    - NINEA.
    """

    # --------------------------------------------------------
    # FOND
    # --------------------------------------------------------

    c.setFillColor(WHITE)

    c.rect(
        0,
        0,
        w,
        h,
        stroke=0,
        fill=1,
    )

    # --------------------------------------------------------
    # LOGO
    # --------------------------------------------------------

    logo_path = get_logo_gold()

    if logo_path:
        c.drawImage(
            logo_path,
            7 * mm,
            h - 33 * mm,
            width=29 * mm,
            height=27 * mm,
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )

    # --------------------------------------------------------
    # NOM BIJOUTERIE
    # --------------------------------------------------------

    info_x = 40 * mm
    right_x = w - 7 * mm

    shop_name = safe(
        data.get("shop_name") or "RIO-GOLD"
    ).strip()

    if shop_name.lower().startswith("bijouterie"):
        display_name = shop_name
    else:
        display_name = f"Bijouterie {shop_name}"

    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 13)

    c.drawString(
        info_x,
        h - 11 * mm,
        _fit_text(
            display_name,
            "Helvetica-Bold",
            13,
            right_x - info_x,
        ),
    )

    # --------------------------------------------------------
    # LIGNE DORÉE
    # --------------------------------------------------------

    c.setStrokeColor(GOLD)
    c.setLineWidth(0.9)

    c.line(
        info_x,
        h - 14 * mm,
        right_x,
        h - 14 * mm,
    )

    # --------------------------------------------------------
    # COORDONNÉES
    # --------------------------------------------------------

    y = h - 20 * mm

    c.setFillColor(DARK)

    shop_phone = _phone_display(
        data.get("shop_phone")
    )

    if shop_phone:
        c.setFont("Helvetica-Bold", 8)
        c.drawString(info_x, y, "Tél :")

        c.setFont("Helvetica", 8)
        c.drawString(
            info_x + 11 * mm,
            y,
            _fit_text(
                shop_phone,
                "Helvetica",
                8,
                right_x - (info_x + 11 * mm),
            ),
        )

        y -= 4.3 * mm

    shop_address = safe(
        data.get("shop_address")
    ).strip()

    if shop_address:
        c.setFont("Helvetica-Bold", 8)
        c.drawString(info_x, y, "Adresse :")

        c.setFont("Helvetica", 8)
        c.drawString(
            info_x + 15 * mm,
            y,
            _fit_text(
                shop_address,
                "Helvetica",
                8,
                right_x - (info_x + 15 * mm),
            ),
        )

        y -= 4.3 * mm

    shop_ninea = safe(
        data.get("shop_ninea")
    ).strip()

    if shop_ninea:
        c.setFont("Helvetica-Bold", 8)
        c.drawString(info_x, y, "NINEA :")

        c.setFont("Helvetica", 8)
        c.drawString(
            info_x + 14 * mm,
            y,
            _fit_text(
                shop_ninea,
                "Helvetica",
                8,
                right_x - (info_x + 14 * mm),
            ),
        )


# ============================================================
# INFORMATIONS FACTURE
# ============================================================

def draw_invoice_info(c, w, h, data):
    """
    Affiche :
    - type de facture ;
    - numéro ;
    - date ;
    - séparateur.
    """

    top = h - 43 * mm
    left_x = 7 * mm
    right_x = w - 7 * mm

    invoice_no = safe(
        data.get("invoice_no")
    ).strip()

    date_value = safe(
        data.get("date")
    ).strip()

    invoice_type = safe(
        data.get("invoice_type") or "FACTURE"
    ).strip().upper()

    if invoice_type not in {
        "FACTURE",
        "FACTURE PROFORMA",
    }:
        invoice_type = "FACTURE"

    # --------------------------------------------------------
    # TITRE
    # --------------------------------------------------------

    c.setFillColor(DARK)

    title_size = (
        13 if invoice_type == "FACTURE PROFORMA"
        else 17
    )

    c.setFont(
        "Helvetica-Bold",
        title_size,
    )

    c.drawString(
        left_x,
        top,
        invoice_type,
    )

    # --------------------------------------------------------
    # NUMÉRO
    # --------------------------------------------------------

    c.setFont("Helvetica-Bold", 9)

    c.drawRightString(
        right_x,
        top,
        _fit_text(
            f"N° {invoice_no}",
            "Helvetica-Bold",
            9,
            58 * mm,
        ),
    )

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    c.setFont("Helvetica-Bold", 8)

    c.drawString(
        left_x,
        top - 7 * mm,
        "Date",
    )

    c.setFont("Helvetica", 8)

    c.drawRightString(
        right_x,
        top - 7 * mm,
        date_value,
    )

    # --------------------------------------------------------
    # SÉPARATEUR
    # --------------------------------------------------------

    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)

    c.line(
        left_x,
        top - 10 * mm,
        right_x,
        top - 10 * mm,
    )


# ============================================================
# CLIENT + VENDEUR
# ============================================================

def draw_client_vendor(c, w, h, data):
    """
    Affiche les informations du client et du vendeur
    dans deux colonnes.
    """

    y_title = h - 63 * mm

    left_x = 7 * mm
    right_x = 82 * mm

    left_width = 69 * mm
    right_width = w - right_x - 7 * mm

    # --------------------------------------------------------
    # CLIENT
    # --------------------------------------------------------

    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 9.5)

    c.drawString(
        left_x,
        y_title,
        "CLIENT",
    )

    client_name = safe(
        data.get("client_name")
        or "Client non renseigné"
    )

    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 9)

    c.drawString(
        left_x,
        y_title - 6 * mm,
        _fit_text(
            client_name,
            "Helvetica-Bold",
            9,
            left_width,
        ),
    )

    client_phone = safe(
        data.get("client_phone")
    ).strip()

    c.setFont("Helvetica", 7.5)

    if client_phone:
        c.drawString(
            left_x,
            y_title - 11 * mm,
            _fit_text(
                f"Tél : {client_phone}",
                "Helvetica",
                7.5,
                left_width,
            ),
        )

    client_address = safe(
        data.get("client_address")
    ).strip()

    if client_address:
        c.drawString(
            left_x,
            y_title - 16 * mm,
            _fit_text(
                f"Adresse : {client_address}",
                "Helvetica",
                7.5,
                left_width,
            ),
        )

    # --------------------------------------------------------
    # VENDEUR
    # --------------------------------------------------------

    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 9.5)

    c.drawString(
        right_x,
        y_title,
        "VENDEUR",
    )

    vendor_name = safe(
        data.get("vendor") or "-"
    )

    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 9)

    c.drawString(
        right_x,
        y_title - 6 * mm,
        _fit_text(
            vendor_name,
            "Helvetica-Bold",
            9,
            right_width,
        ),
    )

    # --------------------------------------------------------
    # NUMÉRO DE VENTE
    # --------------------------------------------------------

    sale_no = safe(
        data.get("sale_no")
    ).strip()

    if sale_no:
        c.setFont("Helvetica", 7)

        c.drawString(
            right_x,
            y_title - 11 * mm,
            _fit_text(
                f"Vente : {sale_no}",
                "Helvetica",
                7,
                right_width,
            ),
        )


