from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from io import BytesIO

import qrcode
from django.conf import settings
from reportlab.lib.pagesizes import A5, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .theme_riogold import (DARK, GOLD, LINE, MID, MUTED, WHITE, money_fcfa,
                            safe)

PAGE = landscape(A5)


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


def _truncate(text: str, max_len: int) -> str:
    text = safe(text)
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _doc_type_label(value: str) -> str:
    value = (value or "").strip().upper()
    return {
        "PROFORMA": "FACTURE PROFORMA",
        "FACTURE": "FACTURE",
        "ACOMPTE": "FACTURE D’ACOMPTE",
        "FINALE": "FACTURE FINALE",
    }.get(value, "FACTURE")


# def _make_invoice_qr(numero_facture: str):
#     qr_dir = os.path.join(settings.MEDIA_ROOT, "factures", "qr_temp")
#     os.makedirs(qr_dir, exist_ok=True)

#     path = os.path.join(qr_dir, f"qr_{numero_facture}.png")
#     qrcode.make(numero_facture).save(path)
#     return path
def _make_invoice_qr_reader(numero_facture):
    """
    Génère le QR Code entièrement en mémoire
    sans créer de fichier temporaire.
    """
    buffer = BytesIO()

    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=2,
    )

    qr.add_data(numero_facture)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    img.save(buffer, format="PNG")

    buffer.seek(0)

    return ImageReader(buffer)


def _draw_page_header(c, w, h, data):
    c.setFillColor(WHITE)
    c.rect(0, 0, w, h, stroke=0, fill=1)

    # Logo gold plus petit
    logo_path = os.path.join(settings.MEDIA_ROOT, "logo", "gold_logo.png")

    if os.path.exists(logo_path):
        c.drawImage(
            logo_path,
            1 * mm,
            h - 35 * mm,
            width=45 * mm,
            height=35 * mm,
            preserveAspectRatio=True,
            mask="auto",
        )

    # Bijouterie à gauche
    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(
        40 * mm,
        h - 11 * mm,
        _truncate(f"Bijouterie {data.get('shop_name') or 'Rio Gold'}", 40),
    )

    c.setStrokeColor(GOLD)
    c.setLineWidth(1.2)
    c.line(40 * mm, h - 15 * mm, 90 * mm, h - 15 * mm)

    c.setFillColor(DARK)
    c.setFont("Helvetica", 10)

    y_info = h - 21 * mm

    if data.get("shop_phone"):
        c.drawString(
            40 * mm,
            y_info,
            _truncate(f"Phone: (+221) {data.get('shop_phone')}", 40),
        )
        y_info -= 5 * mm

    if data.get("shop_address"):
        c.drawString(
            40 * mm,
            y_info,
            _truncate(f"Adresse: {data.get('shop_address')}", 40),
        )
        y_info -= 5 * mm

    if data.get("shop_ninea"):
        c.drawString(
            40 * mm,
            y_info,
            _truncate(f"NINEA: {data.get('shop_ninea')}", 40),
        )

    # Bloc client déplacé vers le centre pour éviter chevauchement
    client_x = 100 * mm
    client_y = h - 31 * mm
    client_w = 50 * mm
    client_h = 24 * mm

    c.setStrokeColor(LINE)
    c.roundRect(client_x, client_y, client_w, client_h, 3 * mm, stroke=1, fill=0)

    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(client_x + client_w / 2, client_y + 17.5 * mm, "CLIENT")

    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(
        client_x + client_w / 2,
        client_y + 11.5 * mm,
        _truncate(data.get("client_name") or "Client non renseigné", 24),
    )

    c.setFont("Helvetica", 10)

    if data.get("client_phone"):
        c.drawCentredString(
            client_x + client_w / 2,
            client_y + 6.5 * mm,
            _truncate(f"(+221) {data.get('client_phone')}", 24),
        )

    if data.get("client_address"):
        c.drawCentredString(
            client_x + client_w / 2,
            client_y + 2.5 * mm,
            _truncate(f"Adresse: {data.get('client_address')}", 28),
        )

    # Bloc facture à droite, sans TYPE
    right_x = w - 10 * mm

    # c.setFillColor(DARK)
    # c.setFont("Helvetica-Bold", 17)
    # c.drawRightString(right_x, h - 11 * mm, "FACTURE")
    
    doc_type = _doc_type_label(data.get("invoice_type"))

    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 15)
    c.drawRightString(
        right_x,
        h - 11 * mm,
        doc_type,
    )

    c.setFont("Helvetica", 10)
    c.drawRightString(
        right_x,
        h - 20 * mm,
        f"N° {safe(data.get('invoice_no'))}",
    )
    c.drawRightString(
        right_x,
        h - 26 * mm,
        f"Date : {safe(data.get('date'))}",
    )


def _draw_table_header(c, left, right, y_top):
    c.setFillColor(GOLD)
    c.roundRect(left, y_top - 10 * mm, right - left, 10 * mm, 2 * mm, stroke=0, fill=1)

    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 10)

    cols = {
        "n": left + 5 * mm,
        "label": left + 14 * mm,
        "qty": right - 60 * mm,
        "pu": right - 35 * mm,
        "ttc": right - 4 * mm,
    }

    c.drawString(cols["n"], y_top - 6.7 * mm, "#")
    c.drawString(cols["label"], y_top - 6.7 * mm, "DÉSIGNATION")
    c.drawRightString(cols["qty"], y_top - 6.7 * mm, "QTÉ")
    c.drawRightString(cols["pu"], y_top - 6.7 * mm, "P.U")
    c.drawRightString(cols["ttc"], y_top - 6.7 * mm, "TOTAL")
    return cols


def _draw_lines(c, left, right, y_top, data):
    cols = _draw_table_header(c, left, right, y_top)
    yrow = y_top - 16 * mm
    lines = data.get("lines") or []

    c.setFont("Helvetica", 10)

    max_rows = 0

    for i, li in enumerate(lines, start=1):
        if yrow < 76 * mm:
            break

        max_rows += 1

        if i % 2 == 0:
            c.setFillColor(MID)
            c.rect(left, yrow - 5 * mm, right - left, 7 * mm, stroke=0, fill=1)

        c.setFillColor(DARK)
        c.drawString(cols["n"], yrow, str(i))
        c.drawString(cols["label"], yrow, _truncate(li.get("label") or "", 42))
        c.drawRightString(cols["qty"], yrow, str(_int(li.get("qty"))))
        c.drawRightString(cols["pu"], yrow, money_fcfa(_dec(li.get("pu"))))
        c.drawRightString(cols["ttc"], yrow, money_fcfa(_dec(li.get("ttc"))))

        c.setStrokeColor(LINE)
        c.setLineWidth(0.25)
        c.line(left, yrow - 3 * mm, right, yrow - 3 * mm)

        yrow -= 8 * mm

    if len(lines) > max_rows:
        c.setFillColor(MUTED)
        c.setFont("Helvetica-Oblique", 7)
        c.drawString(
            left,
            72 * mm,
            f"... {len(lines) - max_rows} ligne(s) supplémentaire(s) non affichée(s)",
        )


# def _draw_conditions_box(c, x, y):
#     box_w = 60 * mm
#     box_h = 22 * mm

#     c.setStrokeColor(LINE)
#     c.roundRect(x, y, box_w, box_h, 3 * mm, stroke=1, fill=0)

#     c.setFillColor(GOLD)
#     c.setFont("Helvetica-Bold", 9)
#     c.drawString(x + 5 * mm, y + box_h - 7 * mm, "CONDITIONS")

#     c.setStrokeColor(GOLD)
#     c.setLineWidth(0.5)
#     c.line(x + 5 * mm, y + box_h - 10 * mm, x + box_w - 5 * mm, y + box_h - 10 * mm)

#     c.setFillColor(DARK)
#     c.setFont("Helvetica", 8.5)
#     c.drawString(x + 5 * mm, y + 7.5 * mm, "Marchandises ni reprises ni échangées")
    
#     c.setFillColor(DARK)
#     c.setFont("Helvetica", 8.5)
#     c.drawString(x + 5 * mm,y + 5 * mm,"Vérifiez vos articles avant de partir.")


def _draw_conditions_box(c, x, y):
    box_w = 60 * mm
    box_h = 22 * mm

    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x + 5 * mm, y + box_h - 7 * mm, "CONDITIONS")

    c.setStrokeColor(GOLD)
    c.setLineWidth(0.5)
    c.line(
        x + 5 * mm,
        y + box_h - 10 * mm,
        x + box_w - 5 * mm,
        y + box_h - 10 * mm
    )

    c.setFillColor(DARK)
    c.setFont("Helvetica", 8.5)
    c.drawString(
        x + 5 * mm,
        y + 7.5 * mm,
        "Marchandises ni reprises ni échangées"
    )

    c.drawString(
        x + 5 * mm,
        y + 5 * mm,
        "Vérifiez vos articles avant de partir."
    )

def _draw_qr_box(c, x, y, data):
    qr_image = _make_invoice_qr_reader(
        data.get("invoice_no")
    )

    c.drawImage(
        qr_image,
        x + 5 * mm,
        y + 8 * mm,
        width=24 * mm,
        height=24 * mm,
        preserveAspectRatio=True,
        mask="auto",
    )

    # c.setFillColor(DARK)
    # c.setFont("Helvetica", 8)
    # c.drawCentredString(
    #     x + box_w / 2,
    #     y + 3.5 * mm,
    #     _truncate(safe(data.get("invoice_no")), 26),
    # )


def _draw_totals_box(c, x, y, data):
    box_w = 78 * mm
    box_h = 42 * mm

    c.setStrokeColor(LINE)
    c.roundRect(x, y, box_w, box_h, 3 * mm, stroke=1, fill=0)

    tva_label = (
        "TVA NON APPLIQUÉE"
        if data.get("taux_tva") is None
        else f"TVA ({data.get('taux_tva')}%)"
    )

    remaining_amount = _dec(data.get("remaining_amount"))

    rows = [
        ("TOTAL HT", data.get("total_ht"), False),
        (tva_label, data.get("montant_tva") or 0, False),
        ("TOTAL TTC", data.get("total_ttc"), True),
        ("MONTANT PAYÉ", data.get("amount_paid"), False),
        # ("RESTE À PAYER", data.get("remaining_amount"), False),
    ]
    
    # ✅ Ajouter seulement si reste > 0
    if remaining_amount > 0:
        rows.append(
            ("RESTE À PAYER", remaining_amount, False)
        )

    yrow = y + box_h - 8 * mm

    for label, amount, highlight in rows:
        if highlight:
            c.setFillColor(MID)
            c.rect(x + 2 * mm, yrow - 3 * mm, box_w - 4 * mm, 6 * mm, stroke=0, fill=1)

        c.setFillColor(GOLD if highlight else DARK)
        c.setFont("Helvetica-Bold" if highlight else "Helvetica", 10)
        c.drawString(x + 5 * mm, yrow, label)

        c.drawRightString(x + box_w - 5 * mm, yrow, money_fcfa(_dec(amount)))
        yrow -= 7 * mm


def _draw_footer_note(c, w, data):
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.5)
    c.line(10 * mm, 13 * mm, w - 10 * mm, 13 * mm)

    c.setFillColor(GOLD)
    c.setFont("Helvetica-Oblique", 10)
    c.drawCentredString(
        w / 2,
        8 * mm,
        data.get("thanks") or "Merci pour votre confiance.",
    )

    c.setFillColor(DARK)
    c.setFont("Helvetica", 8.5)
    c.drawCentredString(
        w / 2,
        4 * mm,
        data.get("footer_note") or "À très bientôt Insha Allah.",
    )


def build_facture_a5_paysage_pdf(path, data: dict):
    w, h = PAGE
    c = canvas.Canvas(path, pagesize=PAGE)

    _draw_page_header(c, w, h, data)

    left = 10 * mm
    right = w - 10 * mm

    y_table_top = h - 47 * mm
    _draw_lines(c, left, right, y_table_top, data)

    # Bas de page bien séparé
    bottom_y = 24 * mm

    _draw_conditions_box(c, 10 * mm, bottom_y)
    _draw_totals_box(c, 82 * mm, bottom_y, data)
    _draw_qr_box(c, w - 38 * mm, bottom_y + 5 * mm, data)

    _draw_footer_note(c, w, data)

    c.showPage()
    c.save()
    return path

