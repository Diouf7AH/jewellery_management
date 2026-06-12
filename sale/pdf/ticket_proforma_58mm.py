
# sale/pdf/ticket_proforma_58mm.py
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from io import BytesIO
from typing import Optional

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def _to_decimal(x) -> Decimal:
    if x in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _money(x: Decimal | int | float | str | None) -> str:
    x = _to_decimal(x).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    s = f"{x:.0f}"
    parts = []
    while s:
        parts.append(s[-3:])
        s = s[:-3]
    return " ".join(reversed(parts)) + " FCFA"


def _fit_text(c, text: str, max_width: float, font_name: str, font_size: float) -> str:
    text = str(text or "")
    if c.stringWidth(text, font_name, font_size) <= max_width:
        return text

    suffix = "..."
    while text and c.stringWidth(text + suffix, font_name, font_size) > max_width:
        text = text[:-1]
    return text + suffix


def _wrap_text(c, text: str, max_width: float, font_name: str, font_size: float) -> list[str]:
    text = str(text or "").strip()
    if not text:
        return []

    words = text.split()
    lines = []
    current = ""

    for word in words:
        candidate = word if not current else f"{current} {word}"
        if c.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def build_ticket_proforma_58mm_pdf(
    *,
    shop_name: str = "Bijouterie Rio-Gold",
    shop_tel: str = "+221 77 806 05 05",
    numero_facture: str,
    date_txt: str,
    montant_a_payer: Decimal | int | float | str,
    statut_txt: str = "NON PAYÉE",
    note: Optional[str] = "Ticket PROFORMA - à régler en caisse",
) -> bytes:
    """
    Ticket PROFORMA 58mm (PDF).
    Retourne le PDF en bytes.
    """

    shop_name = str(shop_name or "Bijouterie Rio-Gold").strip()
    shop_tel = str(shop_tel or "").strip()
    numero_facture = str(numero_facture or "").strip()
    date_txt = str(date_txt or "").strip()
    statut_txt = str(statut_txt or "NON PAYÉE").strip()
    note = str(note).strip() if note else None

    width = 58 * mm

    base_h_mm = 65
    note_extra_lines = 0
    if note:
        tmp_bio = BytesIO()
        tmp_canvas = canvas.Canvas(tmp_bio, pagesize=(width, 100 * mm))
        note_lines = _wrap_text(tmp_canvas, note, width - 8 * mm, "Helvetica", 7.8)
        note_extra_lines = max(0, len(note_lines) - 1)

    height = (base_h_mm + note_extra_lines * 4) * mm

    bio = BytesIO()
    c = canvas.Canvas(bio, pagesize=(width, height))

    x_left = 4 * mm
    x_right = width - 4 * mm
    y = height - 6 * mm

    def hr():
        nonlocal y
        c.setLineWidth(0.6)
        c.line(x_left, y, x_right, y)
        y -= 3 * mm

    c.setFont("Helvetica-Bold", 11)
    header_name = _fit_text(c, shop_name.upper(), width - 8 * mm, "Helvetica-Bold", 11)
    c.drawCentredString(width / 2, y, header_name)
    y -= 6 * mm

    if shop_tel:
        c.setFont("Helvetica", 8.5)
        tel_text = _fit_text(c, f"Tél: {shop_tel}", width - 8 * mm, "Helvetica", 8.5)
        c.drawCentredString(width / 2, y, tel_text)
        y -= 5 * mm

    hr()

    c.setFont("Helvetica-Bold", 9.2)
    c.drawCentredString(width / 2, y, "FACTURE PROFORMA")
    y -= 5 * mm

    c.setFont("Helvetica", 8.5)
    c.drawString(x_left, y, "N°:")
    c.drawRightString(x_right, y, _fit_text(c, numero_facture, 34 * mm, "Helvetica", 8.5))
    y -= 5 * mm

    c.drawString(x_left, y, "Date:")
    c.drawRightString(x_right, y, _fit_text(c, date_txt, 34 * mm, "Helvetica", 8.5))
    y -= 5 * mm

    c.drawString(x_left, y, "État:")
    c.drawRightString(x_right, y, _fit_text(c, statut_txt, 34 * mm, "Helvetica", 8.5))
    y -= 6 * mm

    hr()

    c.setFont("Helvetica-Bold", 8.5)
    c.drawCentredString(width / 2, y, "MONTANT À PAYER")
    y -= 6 * mm

    c.setFont("Helvetica-Bold", 14)
    montant_txt = _fit_text(c, _money(montant_a_payer), width - 8 * mm, "Helvetica-Bold", 14)
    c.drawCentredString(width / 2, y, montant_txt)
    y -= 9 * mm

    hr()

    if note:
        c.setFont("Helvetica", 7.8)
        lines = _wrap_text(c, note, width - 8 * mm, "Helvetica", 7.8)
        for line in lines:
            c.drawCentredString(width / 2, y, line)
            y -= 4 * mm
        y -= 2 * mm

    c.setFont("Helvetica", 7.5)
    c.drawCentredString(width / 2, y, "Merci pour votre confiance")

    c.showPage()
    c.save()
    bio.seek(0)
    return bio.getvalue()


    
    
