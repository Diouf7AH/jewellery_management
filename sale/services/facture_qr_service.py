# sale/services/facture_qr_service.py

import json
from io import BytesIO

import qrcode
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils import timezone


def generate_facture_qr(facture):
    """
    Génère le QR code d'une facture définitive.

    Contenu :
    - numéro de facture ;
    - date de création ;
    - NINEA ;
    - montant TTC ;
    - hash d'intégrité.

    Le hash doit être généré avant le QR code.
    """

    if facture is None or not facture.pk:
        raise ValidationError(
            "Une facture enregistrée est obligatoire."
        )

    if facture.status != facture.STAT_PAYE:
        raise ValidationError(
            "Le QR code officiel nécessite une facture payée."
        )

    if facture.type_facture != facture.TYPE_FACTURE:
        raise ValidationError(
            "Le QR code officiel nécessite une facture définitive."
        )

    if not facture.integrity_hash:
        raise ValidationError(
            "Le hash d'intégrité doit être généré avant le QR code."
        )

    if not facture.bijouterie_id:
        raise ValidationError(
            "La bijouterie de la facture est obligatoire."
        )

    date_creation = facture.date_creation

    if timezone.is_aware(date_creation):
        date_creation = timezone.localtime(date_creation)

    payload = {
        "invoice": facture.numero_facture,
        "date": date_creation.strftime("%Y-%m-%d"),
        "ninea": getattr(
            facture.bijouterie,
            "ninea",
            None,
        ),
        "ttc": str(facture.montant_total),
        "hash": facture.integrity_hash,
    }

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=4,
    )

    qr.add_data(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
        )
    )

    qr.make(fit=True)

    image = qr.make_image(
        fill_color="black",
        back_color="white",
    )

    buffer = BytesIO()

    try:
        image.save(
            buffer,
            format="PNG",
        )

        filename = (
            f"qr_{facture.numero_facture}.png"
        )

        facture.qr_code_image.save(
            filename,
            ContentFile(buffer.getvalue()),
            save=True,
        )

    finally:
        buffer.close()

    try:
        return facture.qr_code_image.url
    except (ValueError, NotImplementedError):
        return None
    
