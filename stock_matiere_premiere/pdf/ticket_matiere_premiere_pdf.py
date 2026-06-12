from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO

from django.http import HttpResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def money(value):
    value = Decimal(str(value or "0")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{value:,}".replace(",", " ") + " FCFA"


def build_ticket_pdf_response(*, obj, title, personne_label, personne_value, adresse, items):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)

    width, height = A4
    y = height - 60

    p.setFont("Helvetica-Bold", 16)
    p.drawCentredString(width / 2, y, title)

    y -= 35
    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, y, f"N° ticket : {obj.numero_ticket}")

    y -= 20
    p.setFont("Helvetica", 10)
    p.drawString(50, y, f"Date : {obj.created_at.strftime('%d/%m/%Y %H:%M')}")
    y -= 18
    p.drawString(50, y, f"Bijouterie : {obj.bijouterie}")
    y -= 18
    p.drawString(50, y, f"{personne_label} : {personne_value}")
    y -= 18
    p.drawString(50, y, f"Adresse : {adresse}")
    y -= 18
    p.drawString(50, y, f"Mode paiement : {obj.mode_paiement}")
    y -= 18
    p.drawString(50, y, f"Statut paiement : {obj.payment_status}")

    y -= 35
    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, y, "Description")
    p.drawString(250, y, "Matière")
    p.drawString(330, y, "Pureté")
    p.drawString(430, y, "Poids")

    y -= 10
    p.line(50, y, 540, y)

    p.setFont("Helvetica", 10)
    y -= 20

    for item in items:
        if y < 80:
            p.showPage()
            y = height - 60

        p.drawString(50, y, str(item.description or "")[:30])
        p.drawString(250, y, str(item.matiere))
        p.drawString(330, y, str(item.purete))
        p.drawString(430, y, f"{item.poids} g")
        y -= 18

    y -= 20
    p.line(50, y, 540, y)
    y -= 25

    p.setFont("Helvetica-Bold", 13)
    p.drawString(50, y, f"Montant total à payer : {money(obj.montant_total)}")

    y -= 50
    p.setFont("Helvetica", 10)
    p.drawString(50, y, "Signature caisse : __________________________")
    p.drawString(320, y, "Signature client/fournisseur : ______________")

    p.showPage()
    p.save()

    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    filename = f"{obj.numero_ticket}.pdf"
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response

