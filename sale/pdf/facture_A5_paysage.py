from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from io import BytesIO

import qrcode
from django.conf import settings
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .theme_riogold import (DARK, GOLD, LINE, MID, MUTED, WHITE, money_fcfa,
                            safe)

PAGE = A5


def _dec(v, default=Decimal("0")):
    try:
        if v in (None, ""):
            return default
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _int(v, default=0):
    try:
        if v in (None, ""):
            return default
        return int(v)
    except Exception:
        return default


def _truncate(text, max_len):
    text = safe(text)
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _etat_label(value):
    value = safe(value).strip().upper()

    if value in {"N", "NEUF"}:
        return "Neuf"

    if value in {"O", "OCCASION"}:
        return "Occasion"

    return safe(value)


def _make_invoice_qr_reader(numero_facture):
    buffer = BytesIO()

    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=2,
    )

    qr.add_data(numero_facture)
    qr.make(fit=True)

    img = qr.make_image(
        fill_color="black",
        back_color="white",
    )

    img.save(buffer, format="PNG")
    buffer.seek(0)

    return ImageReader(buffer)


def _draw_header(c, w, h, data):
    c.setFillColor(WHITE)
    c.rect(0, 0, w, h, stroke=0, fill=1)

    logo_path = os.path.join(
        settings.MEDIA_ROOT,
        "logo",
        "gold_logo.png",
    )

    if os.path.exists(logo_path):
        c.drawImage(
            logo_path,
            8 * mm,
            h - 30 * mm,
            width=27 * mm,
            height=23 * mm,
            preserveAspectRatio=True,
            mask="auto",
        )

    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 12)

    c.drawString(
        38 * mm,
        h - 12 * mm,
        _truncate(
            f"Bijouterie {data.get('shop_name') or 'Rio-Gold'}",
            30,
        ),
    )

    c.setStrokeColor(GOLD)
    c.setLineWidth(0.8)

    c.line(
        38 * mm,
        h - 15 * mm,
        w - 8 * mm,
        h - 15 * mm,
    )

    c.setFillColor(DARK)
    c.setFont("Helvetica", 8)

    y = h - 20 * mm

    if data.get("shop_phone"):
        c.drawString(
            38 * mm,
            y,
            f"Tél : (+221) {data.get('shop_phone')}",
        )
        y -= 4 * mm

    if data.get("shop_address"):
        c.drawString(
            38 * mm,
            y,
            f"Adresse : {data.get('shop_address')}",
        )
        y -= 4 * mm

    if data.get("shop_ninea"):
        c.drawString(
            38 * mm,
            y,
            f"NINEA : {data.get('shop_ninea')}",
        )


def _draw_invoice_info(c, w, h, data):
    top = h - 42 * mm

    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 16)

    c.drawString(
        8 * mm,
        top,
        "FACTURE",
    )

    c.setFont("Helvetica-Bold", 8.5)

    c.drawRightString(
        w - 8 * mm,
        top,
        f"N° {safe(data.get('invoice_no'))}",
    )

    c.setFont("Helvetica", 8)

    c.drawString(
        8 * mm,
        top - 6 * mm,
        "Date",
    )

    c.drawRightString(
        w - 8 * mm,
        top - 6 * mm,
        safe(data.get("date")),
    )

    c.setStrokeColor(LINE)
    c.line(
        8 * mm,
        top - 10 * mm,
        w - 8 * mm,
        top - 10 * mm,
    )


def _draw_client(c, w, h, data):
    y = h - 66 * mm

    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 9)

    c.drawString(
        8 * mm,
        y,
        "CLIENT",
    )

    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 9)

    c.drawString(
        8 * mm,
        y - 6 * mm,
        data.get("client_name")
        or "Client non renseigné",
    )

    c.setFont("Helvetica", 8)

    if data.get("client_phone"):
        c.drawString(
            8 * mm,
            y - 11 * mm,
            f"Tél : {data.get('client_phone')}",
        )

    if data.get("client_address"):
        c.drawString(
            8 * mm,
            y - 16 * mm,
            f"Adresse : {data.get('client_address')}",
        )


def _draw_table_header(c, left, right, y_top):
    header_h = 8 * mm

    c.setFillColor(GOLD)

    c.roundRect(
        left,
        y_top - header_h,
        right - left,
        header_h,
        2 * mm,
        stroke=0,
        fill=1,
    )

    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 7.3)

    cols = {
        "label": left + 2 * mm,
        "poids": left + 68 * mm,
        "qty": left + 84 * mm,
        "prix_gramme": left + 108 * mm,
        "total": right - 2 * mm,
    }

    y = y_top - 5.4 * mm

    c.drawString(
        cols["label"],
        y,
        "DÉSIGNATION",
    )

    c.drawRightString(
        cols["poids"],
        y,
        "POIDS",
    )

    c.drawRightString(
        cols["qty"],
        y,
        "QTÉ",
    )

    c.drawRightString(
        cols["prix_gramme"],
        y,
        "PRIX/G",
    )

    c.drawRightString(
        cols["total"],
        y,
        "TOTAL",
    )

    return cols


def _draw_lines(c, left, right, y_top, data):
    cols = _draw_table_header(
        c,
        left,
        right,
        y_top,
    )

    yrow = y_top - 13 * mm

    lines = data.get("lines") or []

    for i, li in enumerate(lines, start=1):
        if yrow < 82 * mm:
            break

        label = safe(
            li.get("label") or ""
        )

        poids = safe(
            li.get("poids") or ""
        )

        qty = _int(
            li.get("qty")
        )

        prix_gramme = _dec(
            li.get("prix_gramme")
        )

        total = _dec(
            li.get("total")
        )

        purete = safe(
            li.get("purete") or ""
        )

        etat = _etat_label(
            li.get("etat")
        )

        pourcentage = _dec(
            li.get("pourcentage_occasion")
        )

        details = []

        if purete:
            details.append(purete)

        if pourcentage > 0:
            details.append("Occasion")
            details.append(
                f"Réduction -{int(pourcentage)}%"
            )
        elif etat:
            details.append(etat)

        detail_txt = " • ".join(details)

        row_h = 9 * mm if detail_txt else 7 * mm

        if i % 2 == 0:
            c.setFillColor(MID)

            c.rect(
                left,
                yrow - 4.5 * mm,
                right - left,
                row_h,
                stroke=0,
                fill=1,
            )

        c.setFillColor(DARK)
        c.setFont("Helvetica", 7.4)

        c.drawString(
            cols["label"],
            yrow,
            _truncate(label, 27),
        )

        c.drawRightString(
            cols["poids"],
            yrow,
            f"{poids} g" if poids else "-",
        )

        c.drawRightString(
            cols["qty"],
            yrow,
            str(qty),
        )

        c.drawRightString(
            cols["prix_gramme"],
            yrow,
            money_fcfa(prix_gramme),
        )

        c.setFont("Helvetica-Bold", 7.4)

        c.drawRightString(
            cols["total"],
            yrow,
            money_fcfa(total),
        )

        if detail_txt:
            c.setFillColor(MUTED)
            c.setFont(
                "Helvetica-Oblique",
                6.2,
            )

            c.drawString(
                cols["label"],
                yrow - 3.2 * mm,
                _truncate(
                    detail_txt,
                    38,
                ),
            )

        c.setStrokeColor(LINE)
        c.setLineWidth(0.3)

        c.line(
            left,
            yrow - 5 * mm,
            right,
            yrow - 5 * mm,
        )

        yrow -= row_h


def _draw_totals(c, w, data):
    x = 74 * mm
    y = 45 * mm

    box_w = 65 * mm
    box_h = 38 * mm

    c.setStrokeColor(GOLD)
    c.setLineWidth(0.8)

    c.roundRect(
        x,
        y,
        box_w,
        box_h,
        2 * mm,
        stroke=1,
        fill=0,
    )

    rows = [
        (
            "TOTAL HT",
            data.get("total_ht"),
            False,
        ),
        (
            (
                "TVA NON APPLIQUÉE"
                if data.get("taux_tva") is None
                else f"TVA ({data.get('taux_tva')}%)"
            ),
            data.get("montant_tva") or 0,
            False,
        ),
        (
            "TOTAL TTC",
            data.get("total_ttc"),
            True,
        ),
        (
            "PAYÉ",
            data.get("amount_paid"),
            False,
        ),
    ]

    remaining = _dec(
        data.get("remaining_amount")
    )

    if remaining > 0:
        rows.append(
            (
                "RESTE",
                remaining,
                True,
            )
        )

    yy = y + box_h - 7 * mm

    for label, amount, highlight in rows:
        c.setFillColor(
            GOLD if highlight else DARK
        )

        c.setFont(
            "Helvetica-Bold"
            if highlight
            else "Helvetica",
            8.5,
        )

        c.drawString(
            x + 4 * mm,
            yy,
            label,
        )

        c.drawRightString(
            x + box_w - 4 * mm,
            yy,
            money_fcfa(
                _dec(amount)
            ),
        )

        yy -= 6.5 * mm


def _draw_conditions_qr(c, w, data):
    x = 8 * mm
    y = 45 * mm

    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 8.5)

    c.drawString(
        x,
        y + 23 * mm,
        "CONDITIONS",
    )

    c.setFillColor(DARK)
    c.setFont("Helvetica", 7)

    c.drawString(
        x,
        y + 16 * mm,
        "Marchandises ni reprises ni échangées.",
    )

    c.drawString(
        x,
        y + 11 * mm,
        "Vérifiez vos articles avant de partir.",
    )

    numero = data.get("invoice_no")

    if numero:
        qr = _make_invoice_qr_reader(
            numero
        )

        c.drawImage(
            qr,
            25 * mm,
            y - 1 * mm,
            width=26 * mm,
            height=26 * mm,
            preserveAspectRatio=True,
            mask="auto",
        )


def _draw_footer(c, w, data):
    c.setStrokeColor(GOLD)

    c.line(
        8 * mm,
        20 * mm,
        w - 8 * mm,
        20 * mm,
    )

    c.setFillColor(GOLD)

    c.setFont(
        "Helvetica-BoldOblique",
        8.5,
    )

    c.drawCentredString(
        w / 2,
        13 * mm,
        data.get("thanks")
        or "Merci pour votre confiance.",
    )

    c.setFillColor(DARK)
    c.setFont("Helvetica", 7)

    c.drawCentredString(
        w / 2,
        8 * mm,
        data.get("footer_note")
        or "Bijouterie Rio-Gold - L'excellence en or.",
    )


def build_facture_a5_portrait_pdf(
    path,
    data: dict,
):
    w, h = PAGE

    c = canvas.Canvas(
        path,
        pagesize=PAGE,
    )

    _draw_header(
        c,
        w,
        h,
        data,
    )

    _draw_invoice_info(
        c,
        w,
        h,
        data,
    )

    _draw_client(
        c,
        w,
        h,
        data,
    )

    left = 8 * mm
    right = w - 8 * mm

    y_table_top = h - 92 * mm

    _draw_lines(
        c,
        left,
        right,
        y_table_top,
        data,
    )

    _draw_conditions_qr(
        c,
        w,
        data,
    )

    _draw_totals(
        c,
        w,
        data,
    )

    _draw_footer(
        c,
        w,
        data,
    )

    c.showPage()
    c.save()

    return path

