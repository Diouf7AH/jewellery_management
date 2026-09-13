# sale/pdf/facture_A5_portrait/bottom.py

from __future__ import annotations

from reportlab.lib.units import mm

from ..theme_riogold import DARK, GOLD, LINE, MUTED, WHITE, money_fcfa, safe
from .helpers import dec, discount_total, truncate
from .qr_utils import make_invoice_qr_reader


def draw_qr_verification(
    c,
    data,
):
    x = 7 * mm
    y = 47 * mm

    numero = safe(
        data.get("invoice_no")
    )

    if not numero:
        return

    qr_size = 25 * mm

    qr = make_invoice_qr_reader(
        numero
    )

    c.drawImage(
        qr,
        x,
        y,
        width=qr_size,
        height=qr_size,
        preserveAspectRatio=True,
        mask="auto",
    )

    text_x = (
        x
        + qr_size
        + 4 * mm
    )

    c.setFillColor(
        DARK
    )

    c.setFont(
        "Helvetica",
        6.8,
    )

    c.drawString(
        text_x,
        y + 19 * mm,
        "Scannez ce QR code",
    )

    c.drawString(
        text_x,
        y + 15 * mm,
        "pour vérifier l'authenticité",
    )

    c.drawString(
        text_x,
        y + 11 * mm,
        "de cette facture.",
    )

    c.setFont(
        "Helvetica-Bold",
        6.8,
    )

    c.drawString(
        text_x,
        y + 5 * mm,
        truncate(
            f"N° {numero}",
            25,
        ),
    )


def draw_totals(
    c,
    w,
    data,
):
    box_x = 81 * mm
    box_y = 48 * mm

    box_w = (
        w
        - box_x
        - 7 * mm
    )

    row_h = 8 * mm

    total_ht = dec(
        data.get(
            "total_ht"
        )
    )

    remise = discount_total(
        data
    )

    total_ttc = dec(
        data.get(
            "total_ttc"
        )
    )

    rows = [
        (
            "Total HT",
            total_ht,
            False,
        ),
        (
            "Remise",
            remise,
            False,
        ),
        (
            "Total TTC",
            total_ttc,
            True,
        ),
    ]

    amount_paid = dec(
        data.get(
            "amount_paid"
        )
    )

    remaining = dec(
        data.get(
            "remaining_amount"
        )
    )

    if amount_paid > 0:
        rows.append(
            (
                "Montant payé",
                amount_paid,
                False,
            )
        )

    if remaining > 0:
        rows.append(
            (
                "Reste à payer",
                remaining,
                True,
            )
        )

    box_h = (
        len(rows)
        * row_h
    )

    c.setStrokeColor(
        LINE
    )

    c.setLineWidth(
        0.5
    )

    c.rect(
        box_x,
        box_y,
        box_w,
        box_h,
        stroke=1,
        fill=0,
    )

    y = (
        box_y
        + box_h
        - row_h
    )

    for (
        label,
        amount,
        highlight,
    ) in rows:

        if highlight:
            c.setFillColor(
                GOLD
            )

            c.rect(
                box_x,
                y,
                box_w,
                row_h,
                stroke=0,
                fill=1,
            )

            c.setFillColor(
                WHITE
            )

        else:
            c.setFillColor(
                DARK
            )

        c.setFont(
            "Helvetica-Bold",
            7.5,
        )

        c.drawString(
            box_x + 4 * mm,
            y + 2.7 * mm,
            label,
        )

        c.drawRightString(
            box_x + box_w - 4 * mm,
            y + 2.7 * mm,
            money_fcfa(
                amount
            ),
        )

        c.setStrokeColor(
            LINE
        )

        c.setLineWidth(
            0.3
        )

        c.line(
            box_x,
            y,
            box_x + box_w,
            y,
        )

        y -= row_h

def draw_conditions(c):
    x = 7 * mm
    y = 32 * mm

    # ========================================================
    # TITRE
    # ========================================================

    c.setFillColor(GOLD)
    c.setFont(
        "Helvetica-Bold",
        8,
    )

    c.drawString(
        x,
        y,
        "CONDITIONS DE VENTE",
    )

    # ========================================================
    # CONDITIONS
    # ========================================================

    c.setFillColor(DARK)
    c.setFont(
        "Helvetica",
        6.8,
    )

    c.drawString(
        x + 3 * mm,
        y - 6 * mm,
        "• Articles ni repris ni échangés, sauf défaut constaté.",
    )

    c.drawString(
        x + 3 * mm,
        y - 10 * mm,
        "• Garantie commerciale : 72 h contre les défauts de fabrication.",
    )

    c.drawString(
        x + 3 * mm,
        y - 14 * mm,
        "• Hors usure normale, choc, casse et mauvaise utilisation.",
    )

    c.drawString(
        x + 3 * mm,
        y - 18 * mm,
        "• Vérifiez vos articles avant de partir.",
    )
    
    
def draw_signature_box(
    c,
    w,
):
    box_w = 48 * mm
    box_h = 18 * mm

    x = (
        w
        - box_w
        - 7 * mm
    )

    y = 19 * mm

    c.setFillColor(
        DARK
    )

    c.setFont(
        "Helvetica-Bold",
        7.3,
    )

    c.drawCentredString(
        x + box_w / 2,
        y + box_h + 4 * mm,
        "Signature & Cachet",
    )

    c.setStrokeColor(
        LINE
    )

    c.setLineWidth(
        0.6
    )

    c.roundRect(
        x,
        y,
        box_w,
        box_h,
        2 * mm,
        stroke=1,
        fill=0,
    )

    c.setFillColor(
        MUTED
    )

    c.setFont(
        "Helvetica-Bold",
        11,
    )

    c.drawCentredString(
        x + box_w / 2,
        y + 9 * mm,
        "RIO-GOLD",
    )

    c.setFont(
        "Helvetica",
        5.3,
    )

    c.drawCentredString(
        x + box_w / 2,
        y + 5 * mm,
        "BIJOUTERIE",
    )


def draw_footer(
    c,
    w,
):
    y = 7 * mm

    c.setStrokeColor(
        GOLD
    )

    c.setLineWidth(
        0.6
    )

    c.line(
        7 * mm,
        y,
        48 * mm,
        y,
    )

    c.line(
        w - 48 * mm,
        y,
        w - 7 * mm,
        y,
    )

    c.setFillColor(
        GOLD
    )

    c.setFont(
        "Helvetica-BoldOblique",
        7.2,
    )

    c.drawCentredString(
        w / 2,
        y - 1 * mm,
        "L'éclat de vos plus beaux moments",
    )


def draw_invoice_bottom(
    c,
    w,
    data,
):
    """
    Dessine tout le bas de la facture.
    """

    draw_qr_verification(
        c,
        data,
    )

    draw_totals(
        c,
        w,
        data,
    )

    draw_conditions(
        c,
    )

    draw_signature_box(
        c,
        w,
    )

    draw_footer(
        c,
        w,
    )
    
