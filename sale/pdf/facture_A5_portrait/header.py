# sale/pdf/facture_A5_portrait/header.py

from __future__ import annotations

import os

from django.conf import settings
from reportlab.lib.units import mm

from ..theme_riogold import DARK, GOLD, LINE, WHITE, safe
from .helpers import truncate

# ============================================================
# HEADER BIJOUTERIE
# ============================================================

def draw_header(
    c,
    w,
    h,
    data,
):
    # Fond
    c.setFillColor(WHITE)

    c.rect(
        0,
        0,
        w,
        h,
        stroke=0,
        fill=1,
    )

    # ========================================================
    # LOGO
    # ========================================================

    logo_path = os.path.join(
        settings.MEDIA_ROOT,
        "logo",
        "gold_logo.png",
    )

    if os.path.exists(
        logo_path
    ):
        c.drawImage(
            logo_path,
            7 * mm,
            h - 33 * mm,
            width=29 * mm,
            height=27 * mm,
            preserveAspectRatio=True,
            mask="auto",
        )

    # ========================================================
    # BIJOUTERIE
    # ========================================================

    info_x = 40 * mm

    c.setFillColor(
        GOLD
    )

    c.setFont(
        "Helvetica-Bold",
        13,
    )

    shop_name = (
        data.get("shop_name")
        or "RIO-GOLD"
    )

    c.drawString(
        info_x,
        h - 11 * mm,
        truncate(
            f"Bijouterie {shop_name}",
            31,
        ),
    )

    # Ligne dorée
    c.setStrokeColor(
        GOLD
    )

    c.setLineWidth(
        0.9
    )

    c.line(
        info_x,
        h - 14 * mm,
        w - 7 * mm,
        h - 14 * mm,
    )

    # ========================================================
    # COORDONNÉES
    # ========================================================

    c.setFillColor(
        DARK
    )

    y = h - 20 * mm

    shop_phone = safe(
        data.get(
            "shop_phone"
        )
    )

    if shop_phone:

        c.setFont(
            "Helvetica-Bold",
            8,
        )

        c.drawString(
            info_x,
            y,
            "Tél :",
        )

        c.setFont(
            "Helvetica",
            8,
        )

        c.drawString(
            info_x + 11 * mm,
            y,
            f"(+221) {shop_phone}",
        )

        y -= 4.3 * mm

    shop_address = safe(
        data.get(
            "shop_address"
        )
    )

    if shop_address:

        c.setFont(
            "Helvetica-Bold",
            8,
        )

        c.drawString(
            info_x,
            y,
            "Adresse :",
        )

        c.setFont(
            "Helvetica",
            8,
        )

        c.drawString(
            info_x + 15 * mm,
            y,
            truncate(
                shop_address,
                35,
            ),
        )

        y -= 4.3 * mm

    shop_ninea = safe(
        data.get(
            "shop_ninea"
        )
    )

    if shop_ninea:

        c.setFont(
            "Helvetica-Bold",
            8,
        )

        c.drawString(
            info_x,
            y,
            "NINEA :",
        )

        c.setFont(
            "Helvetica",
            8,
        )

        c.drawString(
            info_x + 14 * mm,
            y,
            shop_ninea,
        )


# ============================================================
# FACTURE
# ============================================================

def draw_invoice_info(
    c,
    w,
    h,
    data,
):
    top = (
        h - 43 * mm
    )

    c.setFillColor(
        DARK
    )

    c.setFont(
        "Helvetica-Bold",
        17,
    )

    c.drawString(
        7 * mm,
        top,
        "FACTURE",
    )

    # Numéro facture
    c.setFont(
        "Helvetica-Bold",
        9,
    )

    c.drawRightString(
        w - 7 * mm,
        top,
        (
            f"N° "
            f"{safe(data.get('invoice_no'))}"
        ),
    )

    # Date
    c.setFont(
        "Helvetica-Bold",
        8,
    )

    c.drawString(
        7 * mm,
        top - 7 * mm,
        "Date",
    )

    c.setFont(
        "Helvetica",
        8,
    )

    c.drawRightString(
        w - 7 * mm,
        top - 7 * mm,
        safe(
            data.get("date")
        ),
    )

    # Séparateur
    c.setStrokeColor(
        LINE
    )

    c.setLineWidth(
        0.6
    )

    c.line(
        7 * mm,
        top - 10 * mm,
        w - 7 * mm,
        top - 10 * mm,
    )


# ============================================================
# CLIENT + VENDEUR
# ============================================================

def draw_client_vendor(
    c,
    w,
    h,
    data,
):
    y_title = (
        h - 63 * mm
    )

    left_x = (
        7 * mm
    )

    right_x = (
        82 * mm
    )

    # ========================================================
    # CLIENT
    # ========================================================

    c.setFillColor(
        GOLD
    )

    c.setFont(
        "Helvetica-Bold",
        9.5,
    )

    c.drawString(
        left_x,
        y_title,
        "CLIENT",
    )

    c.setFillColor(
        DARK
    )

    c.setFont(
        "Helvetica-Bold",
        9,
    )

    client_name = (
        data.get(
            "client_name"
        )
        or "Client non renseigné"
    )

    c.drawString(
        left_x,
        y_title - 6 * mm,
        truncate(
            client_name,
            28,
        ),
    )

    c.setFont(
        "Helvetica",
        7.5,
    )

    client_phone = safe(
        data.get(
            "client_phone"
        )
    )

    if client_phone:

        c.drawString(
            left_x,
            y_title - 11 * mm,
            f"Tél : {client_phone}",
        )

    client_address = safe(
        data.get(
            "client_address"
        )
    )

    if client_address:

        c.drawString(
            left_x,
            y_title - 16 * mm,
            truncate(
                (
                    f"Adresse : "
                    f"{client_address}"
                ),
                35,
            ),
        )

    # ========================================================
    # VENDEUR
    # ========================================================

    c.setFillColor(
        GOLD
    )

    c.setFont(
        "Helvetica-Bold",
        9.5,
    )

    c.drawString(
        right_x,
        y_title,
        "VENDEUR",
    )

    c.setFillColor(
        DARK
    )

    c.setFont(
        "Helvetica-Bold",
        9,
    )

    vendor_name = (
        data.get("vendor")
        or "-"
    )

    c.drawString(
        right_x,
        y_title - 6 * mm,
        truncate(
            vendor_name,
            24,
        ),
    )

    sale_no = safe(
        data.get(
            "sale_no"
        )
    )

    if sale_no:

        c.setFont(
            "Helvetica",
            7,
        )

        c.drawString(
            right_x,
            y_title - 11 * mm,
            truncate(
                f"Vente : {sale_no}",
                27,
            ),
        )
        
        