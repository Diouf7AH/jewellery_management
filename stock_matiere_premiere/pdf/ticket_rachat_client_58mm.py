from decimal import ROUND_HALF_UP, Decimal

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

PAGE_WIDTH = 58 * mm
PAGE_HEIGHT = 170 * mm


def money(value):
    value = Decimal(value or 0).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{value:,}".replace(",", " ") + " FCFA"


def build_rachat_client_ticket_58mm(buffer, rachat):
    c = canvas.Canvas(buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))

    y = PAGE_HEIGHT - 8 * mm
    x = 4 * mm

    def text(line, size=8, bold=False, center=False):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        if center:
            c.drawCentredString(PAGE_WIDTH / 2, y, str(line))
        else:
            c.drawString(x, y, str(line))
        y -= 5 * mm

    def separator():
        nonlocal y
        c.line(x, y, PAGE_WIDTH - x, y)
        y -= 4 * mm

    text("BON DE RACHAT CLIENT", 10, True, True)
    separator()

    text(f"Ticket : {rachat.numero_ticket}", 8, True)
    text(f"Etat : En attente paiement", 8, True)
    text(f"Montant dû : {money(rachat.montant_total)}", 9, True)

    separator()

    text("Client", 8, True)
    text(str(rachat.client), 8)
    text(f"Adresse : {rachat.adresse_client}", 7)

    separator()

    text("Articles", 8, True)

    for item in rachat.items.all():
        text(f"- {item.description}", 7)
        text(f"  {item.matiere} / {item.purete} / {item.poids} g", 7)

    separator()

    text("Présenter ce ticket à la caisse", 7, True, True)
    text("pour paiement.", 7, True, True)

    c.showPage()
    c.save()
    

