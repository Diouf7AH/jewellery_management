# sale/pdf/facture_A5_portrait/table.py

from __future__ import annotations

from reportlab.lib.units import mm

from ..theme_riogold import (DARK, GOLD, LINE, MID, MUTED, WHITE, money_fcfa,
                             safe)
from .header import draw_header
from .helpers import dec, etat_label, format_purete, to_int, truncate

# ============================================================
# EN-TÊTE TABLEAU
# ============================================================

def draw_table_header(
    c,
    left,
    right,
    y_top,
):
    """
    Colonnes :
    # | DÉSIGNATION | POIDS | QTÉ | PRIX/G | TOTAL
    """

    header_h = 8 * mm

    c.setFillColor(GOLD)

    c.roundRect(
        left,
        y_top - header_h,
        right - left,
        header_h,
        1.5 * mm,
        stroke=0,
        fill=1,
    )

    c.setFillColor(WHITE)

    c.setFont(
        "Helvetica-Bold",
        7,
    )

    cols = {
        "num": (
            left + 4 * mm
        ),

        "label": (
            left + 11 * mm
        ),

        "poids": (
            left + 69 * mm
        ),

        "qty": (
            left + 83 * mm
        ),

        "prix_gramme": (
            left + 108 * mm
        ),

        "total": (
            right - 2 * mm
        ),
    }

    y = (
        y_top - 5.4 * mm
    )

    # #
    c.drawCentredString(
        cols["num"],
        y,
        "#",
    )

    # DÉSIGNATION
    c.drawString(
        cols["label"],
        y,
        "DÉSIGNATION",
    )

    # POIDS
    c.drawRightString(
        cols["poids"],
        y,
        "POIDS",
    )

    # QTÉ
    c.drawRightString(
        cols["qty"],
        y,
        "QTÉ",
    )

    # PRIX/G
    c.drawRightString(
        cols["prix_gramme"],
        y,
        "PRIX/G",
    )

    # TOTAL
    c.drawRightString(
        cols["total"],
        y,
        "TOTAL",
    )

    return cols


# ============================================================
# UNE LIGNE PRODUIT
# ============================================================

def draw_product_row(
    c,
    cols,
    left,
    right,
    yrow,
    index,
    line,
):
    """
    Dessine une ligne produit.
    """

    # ========================================================
    # DONNÉES
    # ========================================================

    label = safe(
        line.get("label")
        or ""
    )

    poids = safe(
        line.get("poids")
        or ""
    )

    qty = to_int(
        line.get("qty")
    )

    prix_gramme = dec(
        line.get(
            "prix_gramme"
        )
    )

    total = dec(
        line.get(
            "total"
        )
    )

    purete = format_purete(
        line.get(
            "purete"
        )
    )

    etat = etat_label(
        line.get(
            "etat"
        )
    )

    pourcentage = dec(
        line.get(
            "pourcentage_occasion"
        )
    )

    reduction = dec(
        line.get(
            "reduction_occasion"
        )
    )

    # ========================================================
    # DÉTAIL PRODUIT
    # ========================================================

    details = []

    if purete:
        details.append(
            purete
        )

    if pourcentage > 0:

        details.append(
            "Occasion"
        )

        if (
            pourcentage
            == pourcentage.to_integral()
        ):
            pourcentage_txt = str(
                int(pourcentage)
            )

        else:
            pourcentage_txt = str(
                pourcentage
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
        " • ".join(details)
    )

    # ========================================================
    # HAUTEUR
    # ========================================================

    if detail_txt:
        row_h = 9 * mm

    else:
        row_h = 7 * mm

    # ========================================================
    # FOND ALTERNÉ
    # ========================================================

    if index % 2 == 0:

        c.setFillColor(
            MID
        )

        c.rect(
            left,
            yrow - 4.7 * mm,
            right - left,
            row_h,
            stroke=0,
            fill=1,
        )

    # ========================================================
    # NUMÉRO
    # ========================================================

    c.setFillColor(
        DARK
    )

    c.setFont(
        "Helvetica",
        7,
    )

    c.drawCentredString(
        cols["num"],
        yrow,
        str(index),
    )

    # ========================================================
    # DÉSIGNATION
    # ========================================================

    c.setFont(
        "Helvetica-Bold",
        7.4,
    )

    c.drawString(
        cols["label"],
        yrow,
        truncate(
            label,
            27,
        ),
    )

    # ========================================================
    # POIDS
    # ========================================================

    c.setFont(
        "Helvetica",
        7.2,
    )

    if poids:
        poids_txt = (
            f"{poids} g"
        )

    else:
        poids_txt = "-"

    c.drawRightString(
        cols["poids"],
        yrow,
        poids_txt,
    )

    # ========================================================
    # QUANTITÉ
    # ========================================================

    c.drawRightString(
        cols["qty"],
        yrow,
        str(qty),
    )

    # ========================================================
    # PRIX / GRAMME
    # ========================================================

    c.drawRightString(
        cols["prix_gramme"],
        yrow,
        money_fcfa(
            prix_gramme
        ),
    )

    # ========================================================
    # TOTAL
    # ========================================================

    c.setFont(
        "Helvetica-Bold",
        7.2,
    )

    c.drawRightString(
        cols["total"],
        yrow,
        money_fcfa(
            total
        ),
    )

    # ========================================================
    # PURETÉ / ÉTAT / OCCASION
    # ========================================================

    if detail_txt:

        c.setFillColor(
            DARK
        )

        c.setFont(
            "Helvetica",
            6.2,
        )

        c.drawString(
            cols["label"],
            yrow - 3.2 * mm,
            truncate(
                detail_txt,
                38,
            ),
        )

    # ========================================================
    # MONTANT RÉDUCTION
    # ========================================================

    if (
        pourcentage > 0
        and reduction > 0
    ):

        c.setFillColor(
            MUTED
        )

        c.setFont(
            "Helvetica-Oblique",
            5.7,
        )

        c.drawRightString(
            cols["prix_gramme"],
            yrow - 3.2 * mm,
            (
                f"-"
                f"{money_fcfa(reduction)}"
            ),
        )

    # ========================================================
    # SÉPARATEUR
    # ========================================================

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

    return row_h


# ============================================================
# PAGINATION AUTOMATIQUE
# ============================================================

def draw_lines_paginated(
    c,
    w,
    h,
    data,
):
    """
    Dessine tous les produits.

    Gestion :
    - 1 produit
    - 7 produits
    - 20 produits
    - N produits

    Si la page est pleine :
    - nouvelle page
    - header Rio-Gold
    - FACTURE ... - SUITE
    - nouvel en-tête tableau
    - continuation des produits

    Retourne :
        yrow final,
        numéro de page final
    """

    lines = (
        data.get("lines")
        or []
    )

    left = (
        7 * mm
    )

    right = (
        w - 7 * mm
    )

    # ========================================================
    # PREMIÈRE PAGE
    # ========================================================

    y_table_top = (
        h - 88 * mm
    )

    # On réserve le bas de la première page
    # pour QR / totaux / conditions.
    y_min = (
        83 * mm
    )

    cols = draw_table_header(
        c,
        left,
        right,
        y_table_top,
    )

    yrow = (
        y_table_top
        - 13 * mm
    )

    page_number = 1

    # ========================================================
    # TOUS LES PRODUITS
    # ========================================================

    for index, line in enumerate(
        lines,
        start=1,
    ):

        # ----------------------------------------------------
        # Calcul hauteur avant dessin
        # ----------------------------------------------------

        purete = safe(
            line.get("purete")
            or ""
        )

        etat = safe(
            line.get("etat")
            or ""
        )

        pourcentage = dec(
            line.get(
                "pourcentage_occasion"
            )
        )

        has_detail = bool(
            purete
            or etat
            or pourcentage > 0
        )

        if has_detail:
            row_h = 9 * mm

        else:
            row_h = 7 * mm

        # ====================================================
        # NOUVELLE PAGE
        # ====================================================

        if (
            yrow - row_h
            < y_min
        ):

            c.showPage()

            page_number += 1

            # -----------------------------------------------
            # HEADER
            # -----------------------------------------------

            draw_header(
                c,
                w,
                h,
                data,
            )

            # -----------------------------------------------
            # FACTURE - SUITE
            # -----------------------------------------------

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
                    f" - SUITE"
                ),
            )

            c.setFont(
                "Helvetica",
                7.5,
            )

            c.drawRightString(
                w - 7 * mm,
                h - 43 * mm,
                (
                    f"Page "
                    f"{page_number}"
                ),
            )

            # -----------------------------------------------
            # NOUVEAU TABLEAU
            # -----------------------------------------------

            y_table_top = (
                h - 55 * mm
            )

            cols = draw_table_header(
                c,
                left,
                right,
                y_table_top,
            )

            yrow = (
                y_table_top
                - 13 * mm
            )

            # Sur les pages suivantes,
            # presque toute la page peut être utilisée.
            y_min = (
                28 * mm
            )

        # ====================================================
        # DESSIN PRODUIT
        # ====================================================

        actual_h = draw_product_row(
            c,
            cols,
            left,
            right,
            yrow,
            index,
            line,
        )

        yrow -= (
            actual_h
        )

    # ========================================================
    # RETOUR
    # ========================================================

    return (
        yrow,
        page_number,
    )
    
    