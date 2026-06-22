from io import BytesIO

from reportlab.graphics.barcode import code128
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def build_etiquettes_produits_pdf(produit_lines):
    buffer = BytesIO()

    width = 50 * mm
    height = 30 * mm

    p = canvas.Canvas(buffer, pagesize=(width, height))

    for line in produit_lines:
        produit = line.produit

        for _ in range(line.quantite):
            sku = produit.sku or f"P-{produit.id}"
            nom = produit.nom or "Produit"
            poids = produit.poids or ""
            purete = str(produit.purete) if produit.purete else ""

            p.setFont("Helvetica-Bold", 8)
            p.drawCentredString(width / 2, height - 5 * mm, "RIO GOLD")

            p.setFont("Helvetica", 7)
            p.drawString(3 * mm, height - 10 * mm, nom[:28])
            p.drawString(3 * mm, height - 14 * mm, f"Pureté: {purete}  Poids: {poids}g")
            p.drawString(3 * mm, height - 18 * mm, f"SKU: {sku}")

            barcode = code128.Code128(
                sku,
                barHeight=8 * mm,
                barWidth=0.35 * mm,
            )
            barcode.drawOn(p, 5 * mm, 3 * mm)

            p.showPage()

    p.save()
    buffer.seek(0)
    return buffer


