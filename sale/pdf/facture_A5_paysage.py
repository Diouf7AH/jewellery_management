# sale/pdf/facture_A5_paysage.py
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from reportlab.lib.pagesizes import A5, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from .theme_riogold import (BLACK, DARK, GOLD, LINE, MID, MUTED, WHITE,
                            money_fcfa, pill, safe)

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
    except (ValueError, TypeError):
        try:
            return int(float(v))
        except Exception:
            return default


def _truncate(text: str, max_len: int) -> str:
    text = safe(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _doc_type_label(value: str) -> str:
    value = (value or "").strip().upper()
    mapping = {
        "PROFORMA": "FACTURE PROFORMA",
        "FACTURE": "FACTURE",
        "ACOMPTE": "FACTURE D’ACOMPTE",
        "FINALE": "FACTURE FINALE",
    }
    return mapping.get(value, "FACTURE")


def _draw_page_header(c, w, h, data):
    # fond global
    c.setFillColor(BLACK)
    c.rect(0, 0, w, h, stroke=0, fill=1)

    # bandeau header
    c.setFillColor(DARK)
    c.rect(0, h - 34 * mm, w, 34 * mm, stroke=0, fill=1)

    # bloc gauche : bijouterie
    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(
        10 * mm,
        h - 12 * mm,
        _truncate(data.get("shop_name") or "Bijouterie Rio-Gold", 34),
    )

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(
        10 * mm,
        h - 17 * mm,
        _truncate(data.get("shop_phone") or "", 36),
    )
    c.drawString(
        10 * mm,
        h - 21.5 * mm,
        _truncate(data.get("shop_ninea") or "", 36),
    )
    c.drawString(
        10 * mm,
        h - 26 * mm,
        _truncate(data.get("shop_address") or "", 48),
    )

    # bloc centre : client
    c.setFillColor(MID)
    pill(c, (w / 2) - 35 * mm, h - 29 * mm, 70 * mm, 18 * mm, fill=MID)

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawCentredString(w / 2, h - 15 * mm, "CLIENT")

    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(
        w / 2,
        h - 20.5 * mm,
        _truncate(data.get("client_name") or "Client non renseigné", 34),
    )

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    client_meta = " • ".join(
        [x for x in [safe(data.get("client_phone")), safe(data.get("client_address"))] if x]
    )
    c.drawCentredString(
        w / 2,
        h - 25 * mm,
        _truncate(client_meta, 42),
    )

    # bloc droit : facture
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 15)
    c.drawRightString(
        w - 10 * mm,
        h - 12 * mm,
        _truncate(_doc_type_label(data.get("document_type")), 22),
    )

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8.5)
    c.drawRightString(
        w - 10 * mm,
        h - 18 * mm,
        f"N° {safe(data.get('invoice_no'))}",
    )
    c.drawRightString(
        w - 10 * mm,
        h - 22.5 * mm,
        f"Date : {safe(data.get('date'))}",
    )

    if data.get("order_no"):
        c.drawRightString(
            w - 10 * mm,
            h - 27 * mm,
            _truncate(f"Commande : {safe(data.get('order_no'))}", 28),
        )


def _draw_sale_block(c, w, h, data):
    y = h - 42 * mm

    left_x = 10 * mm
    right_x = w - 100 * mm
    block_w = 90 * mm
    block_h = 16 * mm

    pill(c, left_x, y - block_h, block_w, block_h, fill=MID)
    pill(c, right_x, y - block_h, block_w, block_h, fill=MID)

    # gauche
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(left_x + 4 * mm, y - 5 * mm, "VENTE")

    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(
        left_x + 4 * mm,
        y - 10 * mm,
        _truncate(f"Vente : {safe(data.get('sale_no'))}", 28),
    )

    # droite
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(right_x + 4 * mm, y - 5 * mm, "EQUIPE")

    c.setFillColor(WHITE)
    c.setFont("Helvetica", 8.5)
    c.drawString(
        right_x + 4 * mm,
        y - 9.5 * mm,
        _truncate(f"Vendeur : {safe(data.get('vendor'))}", 30),
    )
    c.drawString(
        right_x + 4 * mm,
        y - 13.5 * mm,
        _truncate(f"Caissier : {safe(data.get('cashier'))}", 30),
    )

    return y - 22 * mm


def _draw_table_header(c, left, right, y_top):
    table_w = right - left

    c.setFillColor(DARK)
    c.roundRect(left, y_top - 10 * mm, table_w, 10 * mm, 3 * mm, stroke=0, fill=1)

    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 8.5)

    cols = {
        "n": left + 4 * mm,
        "label": left + 12 * mm,
        "qty": right - 58 * mm,
        "pu": right - 34 * mm,
        "ttc": right - 4 * mm,
    }

    c.drawString(cols["n"], y_top - 6.8 * mm, "#")
    c.drawString(cols["label"], y_top - 6.8 * mm, "Article")
    c.drawRightString(cols["qty"], y_top - 6.8 * mm, "Qté")
    c.drawRightString(cols["pu"], y_top - 6.8 * mm, "P.U")
    c.drawRightString(cols["ttc"], y_top - 6.8 * mm, "Total")

    return cols


def _draw_lines(c, left, right, y_top, data):
    cols = _draw_table_header(c, left, right, y_top)

    yrow = y_top - 16 * mm
    lines = data.get("lines") or []

    c.setFont("Helvetica", 8.5)

    max_rows = 0
    for i, li in enumerate(lines, start=1):
        li = li or {}

        if yrow < 40 * mm:
            break

        max_rows += 1

        # alternance gris
        if i % 2 == 0:
            c.setFillColor(MID)
            c.rect(left, yrow - 5 * mm, right - left, 7 * mm, stroke=0, fill=1)

        c.setFillColor(WHITE)
        c.drawString(cols["n"], yrow, str(i))

        label = _truncate(li.get("label") or "", 44)
        c.drawString(cols["label"], yrow, label)

        c.setFillColor(MUTED)
        c.drawRightString(cols["qty"], yrow, str(_int(li.get("qty"), 0)))
        c.drawRightString(cols["pu"], yrow, money_fcfa(_dec(li.get("pu"))))

        c.setFillColor(WHITE)
        c.drawRightString(cols["ttc"], yrow, money_fcfa(_dec(li.get("ttc"))))

        c.setStrokeColor(LINE)
        c.setLineWidth(0.35)
        c.line(left, yrow - 3 * mm, right, yrow - 3 * mm)

        yrow -= 8 * mm

    if len(lines) > max_rows:
        c.setFillColor(MUTED)
        c.setFont("Helvetica-Oblique", 7.5)
        c.drawString(
            left,
            36 * mm,
            f"... {len(lines) - max_rows} ligne(s) supplémentaire(s) non affichée(s)"
        )


def _draw_totals_box(c, right, data):
    box_w = 82 * mm
    box_h = 38 * mm
    bx = right - box_w
    by = 10 * mm

    pill(c, bx, by, box_w, box_h, fill=DARK, radius=3 * mm)

    taux_tva = _dec(data.get("taux_tva"), Decimal("0.00"))
    document_type = (data.get("document_type") or "").upper()

    c.setFont("Helvetica", 8.5)
    c.setFillColor(MUTED)
    c.drawString(bx + 6 * mm, by + 28 * mm, "Total HT")
    c.drawString(bx + 6 * mm, by + 22 * mm, f"Montant TVA ({taux_tva}%)")

    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(bx + 6 * mm, by + 16 * mm, "Total TTC")

    c.setFillColor(WHITE)
    c.setFont("Helvetica", 8.5)
    c.drawRightString(
        bx + box_w - 6 * mm,
        by + 28 * mm,
        money_fcfa(_dec(data.get("total_ht"))),
    )
    c.drawRightString(
        bx + box_w - 6 * mm,
        by + 22 * mm,
        money_fcfa(_dec(data.get("montant_tva"))),
    )

    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(
        bx + box_w - 6 * mm,
        by + 16 * mm,
        money_fcfa(_dec(data.get("total_ttc"))),
    )

    # partie paiements
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)

    if document_type == "ACOMPTE":
        c.drawString(bx + 6 * mm, by + 10 * mm, "Acompte versé")
        c.drawRightString(
            bx + box_w - 6 * mm,
            by + 10 * mm,
            money_fcfa(_dec(data.get("deposit_amount"))),
        )
        c.drawString(bx + 6 * mm, by + 5 * mm, "Reste à payer")
        c.drawRightString(
            bx + box_w - 6 * mm,
            by + 5 * mm,
            money_fcfa(_dec(data.get("remaining_amount"))),
        )

    elif document_type == "FINALE":
        c.drawString(bx + 6 * mm, by + 10 * mm, "Déjà payé")
        c.drawRightString(
            bx + box_w - 6 * mm,
            by + 10 * mm,
            money_fcfa(_dec(data.get("amount_paid"))),
        )
        c.drawString(bx + 6 * mm, by + 5 * mm, "Reste à payer")
        c.drawRightString(
            bx + box_w - 6 * mm,
            by + 5 * mm,
            money_fcfa(_dec(data.get("remaining_amount"))),
        )

    else:
        c.drawString(bx + 6 * mm, by + 10 * mm, "Total payé")
        c.drawRightString(
            bx + box_w - 6 * mm,
            by + 10 * mm,
            money_fcfa(_dec(data.get("amount_paid"))),
        )
        c.drawString(bx + 6 * mm, by + 5 * mm, "Reste à payer")
        c.drawRightString(
            bx + box_w - 6 * mm,
            by + 5 * mm,
            money_fcfa(_dec(data.get("remaining_amount"))),
        )


def _draw_footer_note(c, data):
    c.setFillColor(MUTED)
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(
        10 * mm,
        12 * mm,
        _truncate(data.get("thanks") or "Merci pour votre confiance.", 80),
    )

    footer_note = safe(data.get("footer_note"))
    if footer_note:
        c.drawString(
            10 * mm,
            8 * mm,
            _truncate(footer_note, 90),
        )


def build_facture_a5_paysage_pdf(path, data: dict):
    """
    path peut être :
    - un chemin fichier
    - un BytesIO

    data = {
        "shop_name": "...",
        "shop_phone": "...",
        "shop_ninea": "...",
        "shop_address": "...",
        "title": "FACTURE",
        "invoice_no": "...",
        "date": "...",
        "document_type": "PROFORMA|FACTURE|ACOMPTE|FINALE",
        "order_no": "...",
        "delivery_date": "...",
        "client_name": "...",
        "client_phone": "...",
        "client_address": "...",
        "vendor": "...",
        "cashier": "...",
        "sale_no": "...",
        "status": "...",
        "lines": [...],
        "total_ht": ...,
        "taux_tva": ...,
        "montant_tva": ...,
        "total_ttc": ...,
        "amount_paid": ...,
        "deposit_amount": ...,
        "remaining_amount": ...,
        "thanks": "...",
        "footer_note": "...",
    }
    """
    w, h = PAGE
    c = canvas.Canvas(path, pagesize=PAGE)

    _draw_page_header(c, w, h, data)

    y_table_top = _draw_sale_block(c, w, h, data)

    left = 10 * mm
    right = w - 10 * mm

    if data.get("qr_code_path"):
        c.drawImage(
            data["qr_code_path"],
            right - 35 * mm,
            10 * mm,
            width=25 * mm,
            height=25 * mm,
            preserveAspectRatio=True,
        )
        
    _draw_lines(c, left, right, y_table_top, data)
    _draw_totals_box(c, right, data)
    _draw_footer_note(c, data)

    c.showPage()
    c.save()
    return path


