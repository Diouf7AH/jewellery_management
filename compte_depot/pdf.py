from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.http import HttpResponse
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

TICKET_WIDTH = 80 * mm
TICKET_HEIGHT = 200 * mm
LEFT = 6 * mm
RIGHT = TICKET_WIDTH - 6 * mm
LINE_HEIGHT = 4.5 * mm


def _safe_str(value):
    return "" if value is None else str(value)


def _money(value):
    try:
        d = Decimal(str(value or "0"))
        d = d.quantize(Decimal("0.01"))
        s = f"{d:,.2f}".replace(",", " ")
        if s.endswith(".00"):
            s = s[:-3]
        return f"{s} FCFA"
    except (InvalidOperation, ValueError, TypeError):
        return f"{value} FCFA"


def _fit(text, max_len=32):
    text = _safe_str(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _draw_left_right(p, y, left_text, right_text, font="Helvetica", size=9):
    left_text = _safe_str(left_text)
    right_text = _safe_str(right_text)

    p.setFont(font, size)
    p.drawString(LEFT, y, _fit(left_text, 18))

    w = p.stringWidth(right_text, font, size)
    x_right = max(LEFT + 80, RIGHT - w)
    p.drawString(x_right, y, right_text)


def _draw_separator(p, y):
    p.setFont("Helvetica", 8)
    p.drawString(LEFT, y, "-" * 38)


def generate_transaction_ticket_80mm_pdf(tx, organisation_name="COMPTE DEPOT"):
    """
    Génère un reçu ticket 80mm pour une transaction CompteDepotTransaction.
    """
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=(TICKET_WIDTH, TICKET_HEIGHT))

    y = TICKET_HEIGHT - 8 * mm

    client = getattr(tx.compte, "client", None)
    client_nom = ""
    if client:
        nom = getattr(client, "nom", "") or ""
        prenom = getattr(client, "prenom", "") or ""
        client_nom = f"{prenom} {nom}".strip()

    agent = "-"
    if tx.user:
        agent = getattr(tx.user, "get_full_name", lambda: "")() or getattr(tx.user, "username", "") or getattr(tx.user, "email", "") or str(tx.user)

    p.setTitle(f"recu_transaction_{tx.id}")

    p.setFont("Helvetica-Bold", 11)
    p.drawCentredString(TICKET_WIDTH / 2, y, _fit(organisation_name, 28))
    y -= LINE_HEIGHT

    p.setFont("Helvetica-Bold", 10)
    p.drawCentredString(TICKET_WIDTH / 2, y, "RECU DE TRANSACTION")
    y -= LINE_HEIGHT

    p.setFont("Helvetica", 8)
    p.drawCentredString(TICKET_WIDTH / 2, y, _safe_str(tx.date_transaction.strftime("%d/%m/%Y %H:%M")))
    y -= LINE_HEIGHT

    _draw_separator(p, y)
    y -= LINE_HEIGHT

    _draw_left_right(p, y, "Reference", _safe_str(tx.reference or f"TX-{tx.id}"))
    y -= LINE_HEIGHT

    _draw_left_right(p, y, "Compte", _safe_str(tx.compte.numero_compte))
    y -= LINE_HEIGHT

    _draw_left_right(p, y, "Client", _fit(client_nom or "Client inconnu", 20))
    y -= LINE_HEIGHT

    _draw_left_right(p, y, "Telephone", _safe_str(getattr(client, "telephone", "") or "-"))
    y -= LINE_HEIGHT

    _draw_left_right(p, y, "Type", _safe_str(tx.get_type_transaction_display()))
    y -= LINE_HEIGHT

    _draw_separator(p, y)
    y -= LINE_HEIGHT

    _draw_left_right(p, y, "Montant", _money(tx.montant), font="Helvetica-Bold", size=10)
    y -= LINE_HEIGHT

    _draw_left_right(p, y, "Solde avant", _money(tx.solde_avant))
    y -= LINE_HEIGHT

    _draw_left_right(p, y, "Solde apres", _money(tx.solde_apres), font="Helvetica-Bold", size=9)
    y -= LINE_HEIGHT

    _draw_left_right(p, y, "Statut", _safe_str(tx.get_statut_display()))
    y -= LINE_HEIGHT

    _draw_left_right(p, y, "Agent", _fit(agent, 20))
    y -= LINE_HEIGHT

    if tx.commentaire:
        _draw_separator(p, y)
        y -= LINE_HEIGHT

        p.setFont("Helvetica-Bold", 9)
        p.drawString(LEFT, y, "Commentaire")
        y -= LINE_HEIGHT

        p.setFont("Helvetica", 8)
        commentaire = _safe_str(tx.commentaire)
        chunk_size = 34
        for i in range(0, len(commentaire), chunk_size):
            p.drawString(LEFT, y, commentaire[i:i + chunk_size])
            y -= 4 * mm
            if y < 15 * mm:
                p.showPage()
                y = TICKET_HEIGHT - 10 * mm
                p.setFont("Helvetica", 8)

    y -= 2 * mm
    _draw_separator(p, y)
    y -= LINE_HEIGHT

    p.setFont("Helvetica-Oblique", 8)
    p.drawCentredString(TICKET_WIDTH / 2, y, "Merci pour votre confiance")
    y -= LINE_HEIGHT

    p.setFont("Helvetica", 7)
    p.drawCentredString(TICKET_WIDTH / 2, y, "Document genere automatiquement")

    p.showPage()
    p.save()

    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="recu_transaction_{tx.id}.pdf"'
    return response

