# sale/services/facture_pdf_service.py
from io import BytesIO

from django.core.files.base import ContentFile

from sale.pdf.facture_A5_paysage import build_facture_a5_paysage_pdf
from sale.services.facture_pdf_data_service import build_facture_pdf_data


def generate_facture_pdf(facture):
    """
    Génère et stocke la facture PDF officielle.
    Retourne l'URL du PDF.
    """

    # ✅ 1. éviter double génération
    if facture.facture_pdf:
        try:
            return facture.facture_pdf.url
        except Exception:
            pass

    # ✅ 2. construire data
    data = build_facture_pdf_data(facture)

    buffer = BytesIO()

    try:
        # ✅ 3. génération PDF
        build_facture_a5_paysage_pdf(buffer, data)

        filename = f"facture_{facture.numero_facture}.pdf"

        # ✅ 4. sauvegarde
        facture.facture_pdf.save(
            filename,
            ContentFile(buffer.getvalue()),
            save=True,
        )

    finally:
        buffer.close()

    # ✅ 5. retour URL
    try:
        return facture.facture_pdf.url
    except Exception:
        return None
    
    
