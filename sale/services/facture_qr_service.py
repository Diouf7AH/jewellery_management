# sale/services/facture_qr_service.py
# le qr_code du facture, avec les données sécurisées (hash) pour vérification ultérieure
import json
from io import BytesIO

import qrcode
from django.core.files.base import ContentFile


def generate_facture_qr(facture):
    """
    Génère QR code avec données sécurisées
    """

    payload = {
        "invoice": facture.numero_facture,
        "date": facture.date_creation.strftime("%Y-%m-%d"),
        "ninea": facture.bijouterie.ninea,
        "ttc": str(facture.montant_total),
        "hash": facture.integrity_hash,
    }

    qr = qrcode.make(json.dumps(payload))

    buffer = BytesIO()
    qr.save(buffer, format="PNG")

    filename = f"qr_{facture.numero_facture}.png"

    facture.qr_code_image.save(
        filename,
        ContentFile(buffer.getvalue()),
        save=True,
    )

    buffer.close()

    return facture.qr_code_image.url 


