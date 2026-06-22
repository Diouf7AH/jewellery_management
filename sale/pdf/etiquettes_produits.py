from io import BytesIO

from reportlab.graphics.barcode import code128
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def build_etiquettes_produits_pdf(produit_lines):
    buffer = BytesIO()

    # Etiquette bague T30x25
    width = 30 * mm
    height = 25 * mm

    p = canvas.Canvas(buffer, pagesize=(width, height))

    for line in produit_lines:
        produit = line.produit

        for _ in range(line.quantite):

            purete = str(produit.purete) if produit.purete else ""
            poids = produit.poids or ""
            sku = produit.sku or f"P-{produit.id}"

            # RIO GOLD
            p.setFont("Helvetica-Bold", 7)
            p.drawCentredString(
                width / 2,
                height - 4 * mm,
                "RIO GOLD"
            )

            # Pureté
            p.setFont("Helvetica", 6)
            p.drawCentredString(
                width / 2,
                height - 9 * mm,
                purete,
            )

            # Poids
            p.drawCentredString(
                width / 2,
                height - 14 * mm,
                f"{poids} g",
            )

            # Code barre
            barcode = code128.Code128(
                sku,
                barHeight=7 * mm,
                barWidth=0.25 * mm,
            )

            barcode.drawOn(
                p,
                2 * mm,
                3 * mm,
            )

            # SKU sous le code barre
            p.setFont("Helvetica", 5)
            p.drawCentredString(
                width / 2,
                1.5 * mm,
                sku,
            )

            p.showPage()

    p.save()
    buffer.seek(0)

    return buffer

