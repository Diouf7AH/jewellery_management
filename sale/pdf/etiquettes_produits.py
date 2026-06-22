from io import BytesIO

from reportlab.graphics.barcode import code128
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def build_etiquettes_produits_pdf(produit_lines):
    buffer = BytesIO()

    # Format étiquette bague
    width = 30 * mm
    height = 12 * mm

    p = canvas.Canvas(buffer, pagesize=(width, height))

    for line in produit_lines:
        produit = line.produit

        for _ in range(line.quantite):
            sku = produit.sku or f"P-{produit.id}"
            poids = produit.poids or ""
            purete = str(produit.purete) if produit.purete else ""

            p.setFont("Helvetica-Bold", 5)
            p.drawCentredString(width / 2, height - 2 * mm, "RIO GOLD")

            p.setFont("Helvetica", 4.5)
            p.drawString(2 * mm, height - 4 * mm, f"{purete} - {poids}g")
            p.drawString(2 * mm, height - 6 * mm, sku[:20])

            barcode = code128.Code128(
                sku,
                barHeight=4 * mm,
                barWidth=0.18 * mm,
            )
            barcode.drawOn(p, 2 * mm, 1 * mm)

            p.showPage()

    p.save()
    buffer.seek(0)
    return buffer

