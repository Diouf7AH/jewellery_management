# sale/pdf/facture_A5_portrait/qr_utils.py

from __future__ import annotations

from io import BytesIO

import qrcode
from reportlab.lib.utils import ImageReader


def make_invoice_qr_reader(
    numero_facture,
):
    """
    Génère le QR code de la facture en mémoire.
    """

    buffer = BytesIO()

    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=2,
    )

    qr.add_data(
        numero_facture
    )

    qr.make(
        fit=True
    )

    image = qr.make_image(
        fill_color="black",
        back_color="white",
    )

    image.save(
        buffer,
        format="PNG",
    )

    buffer.seek(0)

    return ImageReader(
        buffer
    )
    