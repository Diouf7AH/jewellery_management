# sale/pdf/facture_A5_paysage.py

from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from io import BytesIO

import qrcode
from django.conf import settings
from reportlab.lib.pagesizes import A5, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .theme_riogold import (DARK, GOLD, LINE, MID, MUTED, WHITE, money_fcfa,
                            safe)

# ============================================================
# FORMAT
# ============================================================

# A5 paysage = 210 x 148 mm
PAGE = landscape(A5)


# ============================================================
# HELPERS
# ============================================================

def _dec(v, default=Decimal("0")):
    try:
        if v in (None, ""):
            return default

        return Decimal(str(v))

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):
        return default


def _int(v, default=0):
    try:
        if v in (None, ""):
            return default

        return int(v)

    except Exception:
        return default


def _truncate(
    text: str,
    max_len: int,
) -> str:
    text = safe(text)

    if len(text) <= max_len:
        return text

    return (
        text[: max_len - 1]
        + "…"
    )


def _doc_type_label(value: str) -> str:
    value = (
        value
        or ""
    ).strip().upper()

    return {
        "PROFORMA": "FACTURE PROFORMA",
        "FACTURE": "FACTURE",
        "ACOMPTE": "FACTURE D’ACOMPTE",
        "FINALE": "FACTURE FINALE",
    }.get(
        value,
        "FACTURE",
    )


def _etat_label(value) -> str:
    value = (
        safe(value)
        .strip()
        .upper()
    )

    if value in {
        "N",
        "NEUF",
    }:
        return "Neuf"

    if value in {
        "O",
        "OCCASION",
    }:
        return "Occasion"

    return safe(value)


# ============================================================
# QR CODE
# ============================================================

def _make_invoice_qr_reader(
    numero_facture,
):
    """
    Génère le QR Code entièrement en mémoire.
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

    img = qr.make_image(
        fill_color="black",
        back_color="white",
    )

    img.save(
        buffer,
        format="PNG",
    )

    buffer.seek(0)

    return ImageReader(
        buffer
    )


# ============================================================
# HEADER
# ============================================================

def _draw_page_header(
    c,
    w,
    h,
    data,
):

    # --------------------------------------------------------
    # Fond
    # --------------------------------------------------------

    c.setFillColor(WHITE)

    c.rect(
        0,
        0,
        w,
        h,
        stroke=0,
        fill=1,
    )

    # --------------------------------------------------------
    # Logo
    # --------------------------------------------------------

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
            h - 31 * mm,
            width=30 * mm,
            height=25 * mm,
            preserveAspectRatio=True,
            mask="auto",
        )

    # --------------------------------------------------------
    # Bijouterie
    # --------------------------------------------------------

    left_x = 38 * mm

    c.setFillColor(GOLD)

    c.setFont(
        "Helvetica-Bold",
        13,
    )

    c.drawString(
        left_x,
        h - 10 * mm,
        _truncate(
            (
                f"Bijouterie "
                f"{data.get('shop_name') or 'Rio Gold'}"
            ),
            35,
        ),
    )

    c.setStrokeColor(GOLD)
    c.setLineWidth(1)

    c.line(
        left_x,
        h - 13 * mm,
        92 * mm,
        h - 13 * mm,
    )

    # --------------------------------------------------------
    # Infos magasin
    # --------------------------------------------------------

    c.setFillColor(DARK)

    c.setFont(
        "Helvetica",
        8.5,
    )

    y_info = (
        h - 18 * mm
    )

    if data.get(
        "shop_phone"
    ):
        c.drawString(
            left_x,
            y_info,
            _truncate(
                (
                    f"Tél : (+221) "
                    f"{data.get('shop_phone')}"
                ),
                38,
            ),
        )

        y_info -= 4.3 * mm

    if data.get(
        "shop_address"
    ):
        c.drawString(
            left_x,
            y_info,
            _truncate(
                (
                    f"Adresse : "
                    f"{data.get('shop_address')}"
                ),
                38,
            ),
        )

        y_info -= 4.3 * mm

    if data.get(
        "shop_ninea"
    ):
        c.drawString(
            left_x,
            y_info,
            _truncate(
                (
                    f"NINEA : "
                    f"{data.get('shop_ninea')}"
                ),
                38,
            ),
        )

    # --------------------------------------------------------
    # Bloc client
    # --------------------------------------------------------

    client_x = 98 * mm
    client_y = h - 31 * mm

    client_w = 52 * mm
    client_h = 23 * mm

    c.setStrokeColor(LINE)
    c.setLineWidth(0.7)

    c.roundRect(
        client_x,
        client_y,
        client_w,
        client_h,
        2 * mm,
        stroke=1,
        fill=0,
    )

    c.setFillColor(GOLD)

    c.setFont(
        "Helvetica-Bold",
        9,
    )

    c.drawCentredString(
        client_x + client_w / 2,
        client_y + 17 * mm,
        "CLIENT",
    )

    c.setFillColor(DARK)

    c.setFont(
        "Helvetica-Bold",
        9,
    )

    c.drawCentredString(
        client_x + client_w / 2,
        client_y + 11.5 * mm,
        _truncate(
            (
                data.get("client_name")
                or "Client non renseigné"
            ),
            25,
        ),
    )

    c.setFont(
        "Helvetica",
        8,
    )

    if data.get(
        "client_phone"
    ):
        c.drawCentredString(
            client_x + client_w / 2,
            client_y + 6.5 * mm,
            _truncate(
                (
                    f"Tél : "
                    f"{data.get('client_phone')}"
                ),
                27,
            ),
        )

    if data.get(
        "client_address"
    ):
        c.drawCentredString(
            client_x + client_w / 2,
            client_y + 2.8 * mm,
            _truncate(
                (
                    f"Adresse : "
                    f"{data.get('client_address')}"
                ),
                28,
            ),
        )

    # --------------------------------------------------------
    # Bloc facture
    # --------------------------------------------------------

    right_x = (
        w - 8 * mm
    )

    doc_type = _doc_type_label(
        data.get(
            "invoice_type"
        )
    )

    c.setFillColor(DARK)

    c.setFont(
        "Helvetica-Bold",
        16,
    )

    c.drawRightString(
        right_x,
        h - 10 * mm,
        doc_type,
    )

    c.setFont(
        "Helvetica-Bold",
        9,
    )

    c.drawRightString(
        right_x,
        h - 18 * mm,
        (
            f"N° "
            f"{safe(data.get('invoice_no'))}"
        ),
    )

    c.setFont(
        "Helvetica",
        8.5,
    )

    c.drawRightString(
        right_x,
        h - 24 * mm,
        (
            f"Date : "
            f"{safe(data.get('date'))}"
        ),
    )

    if data.get(
        "sale_no"
    ):
        c.drawRightString(
            right_x,
            h - 29 * mm,
            (
                f"Vente : "
                f"{safe(data.get('sale_no'))}"
            ),
        )


# ============================================================
# TABLE HEADER
# ============================================================

def _draw_table_header(
    c,
    left,
    right,
    y_top,
):
    """
    DÉSIGNATION | POIDS | QTÉ | PRIX/G | TOTAL
    """

    header_h = (
        8 * mm
    )

    c.setFillColor(GOLD)

    c.roundRect(
        left,
        y_top - header_h,
        right - left,
        header_h,
        2 * mm,
        stroke=0,
        fill=1,
    )

    c.setFillColor(WHITE)

    c.setFont(
        "Helvetica-Bold",
        8.5,
    )

    cols = {
        "n":
            left + 4 * mm,

        "label":
            left + 11 * mm,

        "poids":
            left + 105 * mm,

        "qty":
            left + 124 * mm,

        "prix_gramme":
            left + 158 * mm,

        "total":
            right - 3 * mm,
    }

    y = (
        y_top - 5.5 * mm
    )

    c.drawString(
        cols["n"],
        y,
        "#",
    )

    c.drawString(
        cols["label"],
        y,
        "DÉSIGNATION",
    )

    c.drawRightString(
        cols["poids"],
        y,
        "POIDS",
    )

    c.drawRightString(
        cols["qty"],
        y,
        "QTÉ",
    )

    c.drawRightString(
        cols["prix_gramme"],
        y,
        "PRIX/G",
    )

    c.drawRightString(
        cols["total"],
        y,
        "TOTAL",
    )

    return cols


# ============================================================
# TABLE LINES
# ============================================================

def _draw_lines(
    c,
    left,
    right,
    y_top,
    data,
):
    """
    Exemple :

    DÉSIGNATION       POIDS   QTÉ   PRIX/G       TOTAL
    Alliance simple   2.50g    1    5 000 FCFA   12 500 FCFA
    18K • Neuf

    Occasion :

    Alliance simple   2.50g    1    5 000 FCFA   11 250 FCFA
    18K • Occasion • Réduction -10 %
    """

    cols = _draw_table_header(
        c,
        left,
        right,
        y_top,
    )

    yrow = (
        y_top - 13 * mm
    )

    lines = (
        data.get("lines")
        or []
    )

    max_rows = 0

    for i, li in enumerate(
        lines,
        start=1,
    ):

        # Garder la place pour les totaux
        if yrow < 69 * mm:
            break

        max_rows += 1

        # ----------------------------------------------------
        # Données
        # ----------------------------------------------------

        label = safe(
            li.get("label")
            or ""
        )

        poids = safe(
            li.get("poids")
            or ""
        )

        qty = _int(
            li.get("qty")
        )

        prix_gramme = _dec(
            li.get(
                "prix_gramme"
            )
        )

        total = _dec(
            li.get(
                "total"
            )
        )

        purete = safe(
            li.get("purete")
            or ""
        )

        etat = _etat_label(
            li.get(
                "etat"
            )
        )

        pourcentage_occasion = _dec(
            li.get(
                "pourcentage_occasion"
            )
        )

        reduction_occasion = _dec(
            li.get(
                "reduction_occasion"
            )
        )

        # ----------------------------------------------------
        # Détails
        # ----------------------------------------------------

        details = []

        if purete:
            details.append(
                purete
            )

        if pourcentage_occasion > 0:

            pourcentage_txt = (
                str(
                    int(
                        pourcentage_occasion
                    )
                )
                if (
                    pourcentage_occasion
                    == pourcentage_occasion.to_integral()
                )
                else str(
                    pourcentage_occasion
                )
            )

            details.append(
                "Occasion"
            )

            details.append(
                (
                    f"Réduction "
                    f"-{pourcentage_txt}%"
                )
            )

        elif etat:

            details.append(
                etat
            )

        detail_txt = (
            " • ".join(
                details
            )
        )

        has_detail = bool(
            detail_txt
        )

        row_h = (
            9 * mm
            if has_detail
            else 7 * mm
        )

        # ----------------------------------------------------
        # Fond alterné
        # ----------------------------------------------------

        if i % 2 == 0:

            c.setFillColor(
                MID
            )

            c.rect(
                left,
                yrow - 4.5 * mm,
                right - left,
                row_h,
                stroke=0,
                fill=1,
            )

        # ----------------------------------------------------
        # Ligne principale
        # ----------------------------------------------------

        c.setFillColor(
            DARK
        )

        c.setFont(
            "Helvetica",
            8.5,
        )

        # Numéro
        c.drawString(
            cols["n"],
            yrow,
            str(i),
        )

        # Désignation
        c.drawString(
            cols["label"],
            yrow,
            _truncate(
                label,
                39,
            ),
        )

        # Poids
        poids_txt = (
            f"{poids} g"
            if poids
            else "-"
        )

        c.drawRightString(
            cols["poids"],
            yrow,
            poids_txt,
        )

        # Quantité
        c.drawRightString(
            cols["qty"],
            yrow,
            str(qty),
        )

        # Prix / gramme
        c.drawRightString(
            cols["prix_gramme"],
            yrow,
            money_fcfa(
                prix_gramme
            ),
        )

        # Total
        c.setFont(
            "Helvetica-Bold",
            8.5,
        )

        c.drawRightString(
            cols["total"],
            yrow,
            money_fcfa(
                total
            ),
        )

        # ----------------------------------------------------
        # Pureté / état / réduction occasion
        # ----------------------------------------------------

        if detail_txt:

            c.setFillColor(
                MUTED
            )

            c.setFont(
                "Helvetica-Oblique",
                6.8,
            )

            c.drawString(
                cols["label"],
                yrow - 3.2 * mm,
                _truncate(
                    detail_txt,
                    55,
                ),
            )

        # ----------------------------------------------------
        # Montant réduction
        # ----------------------------------------------------

        if (
            pourcentage_occasion > 0
            and reduction_occasion > 0
        ):

            c.setFillColor(
                MUTED
            )

            c.setFont(
                "Helvetica-Oblique",
                6.3,
            )

            c.drawRightString(
                cols["prix_gramme"],
                yrow - 3.2 * mm,
                (
                    f"-"
                    f"{money_fcfa(reduction_occasion)}"
                ),
            )

        # ----------------------------------------------------
        # Séparateur
        # ----------------------------------------------------

        c.setStrokeColor(
            LINE
        )

        c.setLineWidth(
            0.3
        )

        c.line(
            left,
            yrow - 5 * mm,
            right,
            yrow - 5 * mm,
        )

        yrow -= row_h

    # --------------------------------------------------------
    # Trop de lignes
    # --------------------------------------------------------

    if len(lines) > max_rows:

        c.setFillColor(
            MUTED
        )

        c.setFont(
            "Helvetica-Oblique",
            6.5,
        )

        c.drawString(
            left,
            67 * mm,
            (
                f"... "
                f"{len(lines) - max_rows} "
                f"ligne(s) supplémentaire(s)"
            ),
        )


# ============================================================
# CONDITIONS
# ============================================================

def _draw_conditions_box(
    c,
    x,
    y,
):

    box_w = (
        62 * mm
    )

    box_h = (
        25 * mm
    )

    c.setStrokeColor(
        LINE
    )

    c.setLineWidth(
        0.6
    )

    c.roundRect(
        x,
        y,
        box_w,
        box_h,
        2 * mm,
        stroke=1,
        fill=0,
    )

    c.setFillColor(
        GOLD
    )

    c.setFont(
        "Helvetica-Bold",
        9,
    )

    c.drawString(
        x + 4 * mm,
        y + box_h - 6 * mm,
        "CONDITIONS",
    )

    c.setStrokeColor(
        GOLD
    )

    c.setLineWidth(
        0.6
    )

    c.line(
        x + 4 * mm,
        y + box_h - 8 * mm,
        x + box_w - 4 * mm,
        y + box_h - 8 * mm,
    )

    c.setFillColor(
        DARK
    )

    c.setFont(
        "Helvetica",
        7.5,
    )

    c.drawString(
        x + 4 * mm,
        y + 9 * mm,
        (
            "Marchandises ni reprises "
            "ni échangées."
        ),
    )

    c.drawString(
        x + 4 * mm,
        y + 5 * mm,
        (
            "Vérifiez vos articles "
            "avant de partir."
        ),
    )


# ============================================================
# TOTALS
# ============================================================

def _draw_totals_box(
    c,
    x,
    y,
    data,
):

    box_w = (
        80 * mm
    )

    box_h = (
        44 * mm
    )

    c.setStrokeColor(
        GOLD
    )

    c.setLineWidth(
        0.8
    )

    c.roundRect(
        x,
        y,
        box_w,
        box_h,
        2.5 * mm,
        stroke=1,
        fill=0,
    )

    taux_tva = (
        data.get(
            "taux_tva"
        )
    )

    tva_label = (
        "TVA NON APPLIQUÉE"
        if taux_tva is None
        else (
            f"TVA "
            f"({taux_tva}%)"
        )
    )

    remaining_amount = _dec(
        data.get(
            "remaining_amount"
        )
    )

    rows = [
        (
            "TOTAL HT",
            data.get(
                "total_ht"
            ),
            False,
        ),
        (
            tva_label,
            data.get(
                "montant_tva"
            )
            or 0,
            False,
        ),
        (
            "TOTAL TTC",
            data.get(
                "total_ttc"
            ),
            True,
        ),
        (
            "MONTANT PAYÉ",
            data.get(
                "amount_paid"
            ),
            False,
        ),
    ]

    if remaining_amount > 0:

        rows.append(
            (
                "RESTE À PAYER",
                remaining_amount,
                True,
            )
        )

    yrow = (
        y + box_h - 7 * mm
    )

    for (
        label,
        amount,
        highlight,
    ) in rows:

        if highlight:

            c.setFillColor(
                MID
            )

            c.roundRect(
                x + 2 * mm,
                yrow - 3 * mm,
                box_w - 4 * mm,
                6 * mm,
                1 * mm,
                stroke=0,
                fill=1,
            )

        c.setFillColor(
            GOLD
            if highlight
            else DARK
        )

        c.setFont(
            (
                "Helvetica-Bold"
                if highlight
                else "Helvetica"
            ),
            9.5,
        )

        c.drawString(
            x + 5 * mm,
            yrow,
            label,
        )

        c.setFont(
            (
                "Helvetica-Bold"
                if highlight
                else "Helvetica"
            ),
            9.5,
        )

        c.drawRightString(
            x + box_w - 5 * mm,
            yrow,
            money_fcfa(
                _dec(amount)
            ),
        )

        yrow -= (
            6.7 * mm
        )

    # --------------------------------------------------------
    # Mode paiement
    # --------------------------------------------------------

    payment_mode = safe(
        data.get(
            "payment_mode"
        )
        or ""
    )

    if payment_mode:

        c.setFillColor(
            DARK
        )

        c.setFont(
            "Helvetica-Bold",
            7.5,
        )

        c.drawString(
            x + 5 * mm,
            y + 3 * mm,
            _truncate(
                (
                    f"Paiement : "
                    f"{payment_mode}"
                ),
                43,
            ),
        )


# ============================================================
# QR
# ============================================================

def _draw_qr_box(
    c,
    x,
    y,
    data,
):

    numero_facture = (
        data.get(
            "invoice_no"
        )
    )

    if not numero_facture:
        return

    qr_image = (
        _make_invoice_qr_reader(
            numero_facture
        )
    )

    qr_size = (
        27 * mm
    )

    c.drawImage(
        qr_image,
        x,
        y,
        width=qr_size,
        height=qr_size,
        preserveAspectRatio=True,
        mask="auto",
    )

    c.setFillColor(
        DARK
    )

    c.setFont(
        "Helvetica",
        6,
    )

    c.drawCentredString(
        x + qr_size / 2,
        y - 2.5 * mm,
        "Vérification facture",
    )


# ============================================================
# FOOTER
# ============================================================

def _draw_footer_note(
    c,
    w,
    data,
):

    c.setStrokeColor(
        GOLD
    )

    c.setLineWidth(
        0.6
    )

    c.line(
        8 * mm,
        12 * mm,
        w - 8 * mm,
        12 * mm,
    )

    c.setFillColor(
        GOLD
    )

    c.setFont(
        "Helvetica-BoldOblique",
        8.5,
    )

    c.drawCentredString(
        w / 2,
        7.5 * mm,
        (
            data.get(
                "thanks"
            )
            or "Merci pour votre confiance."
        ),
    )

    c.setFillColor(
        DARK
    )

    c.setFont(
        "Helvetica",
        7,
    )

    c.drawCentredString(
        w / 2,
        3.8 * mm,
        (
            data.get(
                "footer_note"
            )
            or (
                "Bijouterie Rio-Gold "
                "- L'excellence en or."
            )
        ),
    )


# ============================================================
# BUILD PDF
# ============================================================

def build_facture_a5_paysage_pdf(
    path,
    data: dict,
):

    w, h = PAGE

    c = canvas.Canvas(
        path,
        pagesize=PAGE,
    )

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    _draw_page_header(
        c,
        w,
        h,
        data,
    )

    # --------------------------------------------------------
    # Tableau
    # --------------------------------------------------------

    left = (
        7 * mm
    )

    right = (
        w - 7 * mm
    )

    y_table_top = (
        h - 38 * mm
    )

    _draw_lines(
        c,
        left,
        right,
        y_table_top,
        data,
    )

    # --------------------------------------------------------
    # Bas de page
    # --------------------------------------------------------

    bottom_y = (
        18 * mm
    )

    _draw_conditions_box(
        c,
        7 * mm,
        bottom_y,
    )

    _draw_totals_box(
        c,
        73 * mm,
        bottom_y,
        data,
    )

    _draw_qr_box(
        c,
        w - 35 * mm,
        bottom_y + 8 * mm,
        data,
    )

    # --------------------------------------------------------
    # Footer
    # --------------------------------------------------------

    _draw_footer_note(
        c,
        w,
        data,
    )

    # --------------------------------------------------------
    # Fin
    # --------------------------------------------------------

    c.showPage()

    c.save()

    return path

