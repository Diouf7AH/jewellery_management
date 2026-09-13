# sale/pdf/facture_A5_portrait/builder.py

from __future__ import annotations

from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from ..theme_riogold import DARK, safe
from .bottom import draw_invoice_bottom
from .header import draw_client_vendor, draw_header, draw_invoice_info
from .table import draw_lines_paginated

PAGE = A5


def build_facture_a5_portrait_pdf(
    path,
    data: dict,
):
    """
    Facture officielle Rio-Gold.

    Format :
    A5 portrait = 148 x 210 mm.

    Gestion :
    - N produits
    - pagination automatique
    - pages de continuation
    - page récapitulative si nécessaire
    """

    w, h = PAGE

    c = canvas.Canvas(
        path,
        pagesize=PAGE,
    )

    # ========================================================
    # PREMIÈRE PAGE
    # ========================================================

    draw_header(
        c,
        w,
        h,
        data,
    )

    draw_invoice_info(
        c,
        w,
        h,
        data,
    )

    draw_client_vendor(
        c,
        w,
        h,
        data,
    )

    # ========================================================
    # PRODUITS
    # ========================================================

    yrow, page_number = draw_lines_paginated(
        c,
        w,
        h,
        data,
    )

    # ========================================================
    # RÉCAPITULATIF SI PLUS DE PLACE
    # ========================================================

    if yrow < 86 * mm:

        c.showPage()

        page_number += 1

        draw_header(
            c,
            w,
            h,
            data,
        )

        c.setFillColor(
            DARK
        )

        c.setFont(
            "Helvetica-Bold",
            10,
        )

        c.drawString(
            7 * mm,
            h - 43 * mm,
            (
                f"FACTURE "
                f"{safe(data.get('invoice_no'))}"
                f" - RÉCAPITULATIF"
            ),
        )

        c.setFont(
            "Helvetica",
            7.5,
        )

        c.drawRightString(
            w - 7 * mm,
            h - 43 * mm,
            f"Page {page_number}",
        )

    # ========================================================
    # BAS DE FACTURE
    # ========================================================

    draw_invoice_bottom(
        c,
        w,
        data,
    )

    # ========================================================
    # FIN
    # ========================================================

    c.showPage()
    c.save()

    return path
