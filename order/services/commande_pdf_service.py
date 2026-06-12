from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from django.utils import timezone
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

ZERO = Decimal("0.00")


def _safe(value, default="-"):
    return default if value in (None, "", []) else str(value)


def generate_bon_commande_pdf(*, commande):
    buffer = BytesIO()
    page_size = landscape(A4)
    width, height = page_size

    p = canvas.Canvas(buffer, pagesize=page_size)

    left = 12 * mm
    right = width - 12 * mm
    top = height - 10 * mm
    y = top
    row_h = 8 * mm

    def draw_text(x, y_pos, text, size=10, bold=False):
        p.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        p.drawString(x, y_pos, _safe(text, ""))

    def draw_line(y_pos):
        p.line(left, y_pos, right, y_pos)

    draw_text(left, y, "BON DE COMMANDE", size=16, bold=True)
    y -= 8 * mm

    client_nom = getattr(commande.client, "full_name", None) or (
        f"{getattr(commande.client, 'prenom', '')} {getattr(commande.client, 'nom', '')}".strip()
    )
    vendeur_username = getattr(getattr(commande.vendor, "user", None), "username", "-")
    bijouterie_nom = getattr(commande.bijouterie, "nom", "-")

    draw_text(left, y, f"N° commande : {commande.numero_commande}", bold=True)
    draw_text(95 * mm, y, f"Date commande : {timezone.localtime(commande.date_commande).strftime('%d/%m/%Y %H:%M')}")
    draw_text(190 * mm, y, f"Statut : {commande.get_statut_display()}")
    y -= 6 * mm

    draw_text(left, y, f"Client : {client_nom}")
    draw_text(95 * mm, y, f"Téléphone : {_safe(getattr(commande.client, 'telephone', None))}")
    draw_text(190 * mm, y, f"Boutique : {bijouterie_nom}")
    y -= 6 * mm

    draw_text(left, y, f"Vendeur : {vendeur_username}")
    draw_text(95 * mm, y, f"Date début : {_safe(commande.date_debut)}")
    draw_text(190 * mm, y, f"Date fin prévue : {_safe(commande.date_fin_prevue)}")
    y -= 8 * mm

    draw_text(left, y, "DÉTAILS DE LA COMMANDE", size=12, bold=True)
    y -= 6 * mm

    cols = {
        "num": left,
        "modele": left + 10 * mm,
        "purete": left + 70 * mm,
        "taille": left + 100 * mm,
        "qte": left + 125 * mm,
        "poids": left + 145 * mm,
        "prix_g": left + 170 * mm,
        "total": left + 210 * mm,
        "desc": left + 245 * mm,
    }

    draw_line(y + 2 * mm)
    draw_text(cols["num"], y - 2, "#", bold=True)
    draw_text(cols["modele"], y - 2, "Modèle", bold=True)
    draw_text(cols["purete"], y - 2, "Pureté", bold=True)
    draw_text(cols["taille"], y - 2, "Taille", bold=True)
    draw_text(cols["qte"], y - 2, "Qté", bold=True)
    draw_text(cols["poids"], y - 2, "Poids(g)", bold=True)
    draw_text(cols["prix_g"], y - 2, "Prix/g", bold=True)
    draw_text(cols["total"], y - 2, "Total", bold=True)
    draw_text(cols["desc"], y - 2, "Description", bold=True)
    y -= row_h
    draw_line(y + 2 * mm)

    for idx, ligne in enumerate(commande.lignes.all(), start=1):
        if y < 20 * mm:
            p.showPage()
            y = top

        draw_text(cols["num"], y, idx)
        draw_text(cols["modele"], y, ligne.nom_modele)
        draw_text(cols["purete"], y, getattr(ligne.purete, "nom", "-"))
        draw_text(cols["taille"], y, ligne.taille or "-")
        draw_text(cols["qte"], y, ligne.quantite)
        draw_text(cols["poids"], y, ligne.poids)
        draw_text(cols["prix_g"], y, ligne.prix_gramme)
        draw_text(cols["total"], y, ligne.sous_total)
        draw_text(cols["desc"], y, (ligne.description or "")[:35])
        y -= row_h

    draw_line(y + 3 * mm)
    y -= 4 * mm

    acompte_min = getattr(commande, "acompte_minimum_requis", ZERO)
    total_paye = getattr(commande, "total_paye_global", ZERO)
    reste = getattr(commande, "reste_global", ZERO)

    draw_text(left, y, "RÉCAPITULATIF", size=12, bold=True)
    y -= 7 * mm

    draw_text(left, y, f"Montant total commande : {commande.montant_total} FCFA", bold=True)
    draw_text(105 * mm, y, f"Acompte minimum requis : {acompte_min} FCFA")
    draw_text(205 * mm, y, f"Total payé : {total_paye} FCFA")
    y -= 6 * mm

    draw_text(left, y, f"Reste à payer : {reste} FCFA", bold=True)
    y -= 10 * mm

    if commande.notes_client:
        draw_text(left, y, f"Notes client : {commande.notes_client}")
        y -= 6 * mm

    if commande.notes_internes:
        draw_text(left, y, f"Notes internes : {commande.notes_internes}")
        y -= 6 * mm

    y -= 8 * mm
    draw_text(left, y, "Signature client", bold=True)
    draw_text(120 * mm, y, "Signature vendeur", bold=True)
    draw_text(220 * mm, y, "Cachet boutique", bold=True)

    p.showPage()
    p.save()

    pdf_content = buffer.getvalue()
    buffer.close()
    return pdf_content


