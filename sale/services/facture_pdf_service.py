# sale/services/facture_pdf_service.py

from io import BytesIO

from django.core.files.base import ContentFile

from sale.pdf.facture_A5_portrait import build_facture_a5_portrait_pdf
from sale.services.facture_pdf_data_service import build_facture_pdf_data


def generate_facture_pdf(facture):
    """
    Génère et stocke la facture PDF officielle.

    Retourne l'URL du PDF.
    """

    # =========================================================
    # 1. PDF DÉJÀ EXISTANT
    # =========================================================

    if facture.facture_pdf:

        try:
            return facture.facture_pdf.url

        except Exception:
            pass

    # =========================================================
    # 2. DONNÉES CENTRALISÉES
    # =========================================================

    data = build_facture_pdf_data(
        facture
    )

    # =========================================================
    # 3. GÉNÉRATION
    # =========================================================

    buffer = BytesIO()

    try:

        build_facture_a5_portrait_pdf(
            buffer,
            data,
        )

        filename = (
            f"facture_"
            f"{facture.numero_facture}"
            f".pdf"
        )

        facture.facture_pdf.save(
            filename,
            ContentFile(
                buffer.getvalue()
            ),
            save=True,
        )

    finally:

        buffer.close()

    # =========================================================
    # 4. URL
    # =========================================================

    try:

        return facture.facture_pdf.url

    except Exception:

        return None
    
    

