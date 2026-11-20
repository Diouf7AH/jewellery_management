# reparation/services/ticket_reparation_A5.py

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from django.core.exceptions import ValidationError
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (HRFlowable, KeepTogether, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

# ============================================================
# CONFIGURATION
# ============================================================

PAGE_WIDTH, PAGE_HEIGHT = A5

MARGE_GAUCHE = 12 * mm
MARGE_DROITE = 12 * mm
MARGE_HAUT = 12 * mm
MARGE_BAS = 12 * mm

LARGEUR_CONTENU = (
    PAGE_WIDTH - MARGE_GAUCHE - MARGE_DROITE
)

COULEUR_PRINCIPALE = colors.HexColor("#17212B")
COULEUR_SECONDAIRE = colors.HexColor("#555555")
COULEUR_BORDURE = colors.HexColor("#D7DCE0")
COULEUR_FOND = colors.HexColor("#F3F5F7")


# ============================================================
# HELPERS
# ============================================================

def _texte(valeur, defaut="-"):
    if valeur is None:
        return defaut

    valeur = str(valeur).strip()

    return valeur if valeur else defaut


def _html(valeur, defaut="-"):
    return escape(_texte(valeur, defaut))


def _montant(valeur):
    montant = Decimal(str(valeur or "0"))

    return f"{montant:,.2f}".replace(",", " ") + " FCFA"


def _poids(valeur):
    if valeur is None:
        return "-"

    return f"{Decimal(str(valeur)):.3f} g"


def _date(valeur):
    if not valeur:
        return "-"

    if timezone.is_aware(valeur):
        valeur = timezone.localtime(valeur)

    return valeur.strftime("%d/%m/%Y %H:%M")


def _nom_client(client):
    if client is None:
        return "-"

    nom = _texte(getattr(client, "nom", ""), "")
    prenom = _texte(getattr(client, "prenom", ""), "")

    nom_complet = f"{prenom} {nom}".strip()

    return nom_complet or "-"


def _telephone_bijouterie(bijouterie):
    champs = (
        "telephone_portable_1",
        "telephone_portable_2",
        "telephone_fix",
    )

    for champ in champs:
        valeur = getattr(bijouterie, champ, None)

        if valeur:
            return str(valeur)

    return "-"


# ============================================================
# STYLES
# ============================================================

def _creer_styles():

    return {
        "titre": ParagraphStyle(
            name="RG_Titre_A5",
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            alignment=TA_CENTER,
            textColor=COULEUR_PRINCIPALE,
            spaceAfter=4,
        ),

        "sous_titre": ParagraphStyle(
            name="RG_SousTitre_A5",
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            alignment=TA_CENTER,
            textColor=COULEUR_PRINCIPALE,
            spaceAfter=8,
        ),

        "centre": ParagraphStyle(
            name="RG_Centre_A5",
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            alignment=TA_CENTER,
        ),

        "normal": ParagraphStyle(
            name="RG_Normal_A5",
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            alignment=TA_LEFT,
            spaceAfter=3,
        ),

        "petit": ParagraphStyle(
            name="RG_Petit_A5",
            fontName="Helvetica",
            fontSize=7,
            leading=10,
            alignment=TA_LEFT,
            spaceAfter=2,
        ),

        "section": ParagraphStyle(
            name="RG_Section_A5",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=COULEUR_PRINCIPALE,
            spaceBefore=7,
            spaceAfter=5,
        ),

        "total": ParagraphStyle(
            name="RG_Total_A5",
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            alignment=TA_RIGHT,
        ),
    }


# ============================================================
# TABLEAU INFORMATIONS
# ============================================================

def _tableau_informations(lignes, styles):

    donnees = []

    for libelle, valeur in lignes:

        donnees.append([
            Paragraph(
                f"<b>{_html(libelle)}</b>",
                styles["normal"],
            ),
            Paragraph(
                _html(valeur),
                styles["normal"],
            ),
        ])

    tableau = Table(
        donnees,
        colWidths=[
            LARGEUR_CONTENU * 0.35,
            LARGEUR_CONTENU * 0.65,
        ],
        hAlign="LEFT",
    )

    tableau.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (0, -1), (-1, -1),
             0.4, COULEUR_BORDURE),
        ])
    )

    return tableau


# ============================================================
# BLOC D'UN BIJOU
# ============================================================

def _bloc_bijou(bijou, numero, styles):

    elements = []

    elements.append(
        Paragraph(
            f"BIJOU N° {numero}",
            styles["section"],
        )
    )

    informations = [
        ("Type de bijou", getattr(bijou, "type_bijou", None)),
        (
            "Description",
            getattr(bijou, "description_bijou", None),
        ),
        ("Poids", _poids(getattr(bijou, "poids", None))),
        ("Pureté", getattr(bijou, "purete", None)),
        (
            "État à la réception",
            getattr(bijou, "etat_reception", None),
        ),
        (
            "Travail demandé",
            getattr(bijou, "travail_demande", None),
        ),
        (
            "Prix de réparation",
            _montant(
                getattr(bijou, "prix_reparation", None)
            ),
        ),
    ]

    elements.append(
        _tableau_informations(
            informations,
            styles,
        )
    )

    elements.append(Spacer(1, 4 * mm))

    return KeepTogether(elements)


# ============================================================
# GÉNÉRATION DU TICKET A5
# ============================================================

def generer_ticket_depot_pdf(reparation) -> bytes:
    """
    Génère le ticket de dépôt de réparation au format A5.

    Le ticket contient :
    - Informations de la bijouterie.
    - Informations du client.
    - Numéro du dossier.
    - Date du dépôt.
    - Date prévue de récupération.
    - Tous les bijoux déposés.
    - État des bijoux à la réception.
    - Travaux demandés.
    - Prix de réparation de chaque bijou.
    - Montant total convenu.
    - Emplacements de signature.

    Aucun paiement n'est enregistré.
    Aucun objet Vente, VenteAutre ou Facture n'est créé.

    Retour :
        bytes : contenu du PDF.
    """

    # --------------------------------------------------------
    # 1. Vérifier la réparation
    # --------------------------------------------------------

    if reparation is None:
        raise ValidationError(
            "La réparation est introuvable."
        )

    bijoux = list(
        reparation.bijoux.all().order_by(
            "numero_ligne",
            "pk",
        )
    )

    if not bijoux:
        raise ValidationError(
            "Impossible de générer le ticket : "
            "aucun bijou n'est enregistré."
        )

    # Vérification du montant total
    reparation.verifier_total_bijoux()

    # --------------------------------------------------------
    # 2. Préparer le PDF
    # --------------------------------------------------------

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A5,
        rightMargin=MARGE_DROITE,
        leftMargin=MARGE_GAUCHE,
        topMargin=MARGE_HAUT,
        bottomMargin=MARGE_BAS,
        title=(
            "Ticket de dépôt - "
            f"{reparation.numero_reparation}"
        ),
        author="Rio-Gold",
    )

    styles = _creer_styles()

    elements = []

    # --------------------------------------------------------
    # 3. En-tête bijouterie
    # --------------------------------------------------------

    bijouterie = reparation.bijouterie
    client = reparation.client

    elements.append(
        Paragraph(
            _html(
                getattr(bijouterie, "nom", "RIO-GOLD")
            ),
            styles["titre"],
        )
    )

    elements.append(
        Paragraph(
            "TICKET DE DÉPÔT DE RÉPARATION",
            styles["sous_titre"],
        )
    )

    elements.append(
        Paragraph(
            "Téléphone : "
            + _html(_telephone_bijouterie(bijouterie)),
            styles["centre"],
        )
    )

    elements.append(Spacer(1, 4 * mm))

    elements.append(
        HRFlowable(
            width="100%",
            thickness=0.8,
            color=COULEUR_PRINCIPALE,
        )
    )

    elements.append(Spacer(1, 3 * mm))

    # --------------------------------------------------------
    # 4. Informations du dossier
    # --------------------------------------------------------

    elements.append(
        Paragraph(
            "INFORMATIONS DU DOSSIER",
            styles["section"],
        )
    )

    elements.append(
        _tableau_informations(
            [
                (
                    "N° réparation",
                    reparation.numero_reparation,
                ),
                (
                    "Date de dépôt",
                    _date(reparation.date_depot),
                ),
                (
                    "Date prévue",
                    _date(reparation.date_prevue),
                ),
                (
                    "Nombre de bijoux",
                    len(bijoux),
                ),
            ],
            styles,
        )
    )

    # --------------------------------------------------------
    # 5. Informations du client
    # --------------------------------------------------------

    elements.append(
        Paragraph(
            "INFORMATIONS DU CLIENT",
            styles["section"],
        )
    )

    elements.append(
        _tableau_informations(
            [
                (
                    "Nom complet",
                    _nom_client(client),
                ),
                (
                    "Téléphone",
                    getattr(client, "telephone", None),
                ),
            ],
            styles,
        )
    )

    # --------------------------------------------------------
    # 6. Détails des bijoux
    # --------------------------------------------------------

    elements.append(
        Paragraph(
            "BIJOUX DÉPOSÉS",
            styles["section"],
        )
    )

    for index, bijou in enumerate(bijoux, start=1):

        numero = (
            getattr(bijou, "numero_ligne", None)
            or index
        )

        elements.append(
            _bloc_bijou(
                bijou,
                numero,
                styles,
            )
        )

    # --------------------------------------------------------
    # 7. Montant total convenu
    # --------------------------------------------------------

    elements.append(
        HRFlowable(
            width="100%",
            thickness=0.8,
            color=COULEUR_PRINCIPALE,
        )
    )

    elements.append(Spacer(1, 3 * mm))

    elements.append(
        Paragraph(
            "MONTANT TOTAL CONVENU : "
            + _html(
                _montant(reparation.prix_convenu)
            ),
            styles["total"],
        )
    )

    elements.append(Spacer(1, 5 * mm))

    # --------------------------------------------------------
    # 8. Informations importantes
    # --------------------------------------------------------

    elements.append(
        Paragraph(
            "CONDITIONS DE DÉPÔT",
            styles["section"],
        )
    )

    conditions = [
        "Ce document confirme la réception des bijoux "
        "décrits ci-dessus.",

        "La date prévue de récupération est indicative.",

        "Le paiement intégral de la réparation est "
        "obligatoire avant la restitution des bijoux.",

        "Ce ticket de dépôt ne constitue pas "
        "un reçu de paiement.",
    ]

    for condition in conditions:

        elements.append(
            Paragraph(
                "• " + _html(condition),
                styles["petit"],
            )
        )

    elements.append(Spacer(1, 9 * mm))

    # --------------------------------------------------------
    # 9. Signatures
    # --------------------------------------------------------

    signatures = Table(
        [
            [
                Paragraph(
                    "<b>Signature du client</b>",
                    styles["centre"],
                ),
                Paragraph(
                    "<b>Signature de la bijouterie</b>",
                    styles["centre"],
                ),
            ],
            ["", ""],
        ],
        colWidths=[
            LARGEUR_CONTENU / 2,
            LARGEUR_CONTENU / 2,
        ],
        rowHeights=[
            10 * mm,
            17 * mm,
        ],
    )

    signatures.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 1), (0, 1),
             0.6, COULEUR_SECONDAIRE),
            ("LINEBELOW", (1, 1), (1, 1),
             0.6, COULEUR_SECONDAIRE),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ])
    )

    elements.append(signatures)

    elements.append(Spacer(1, 5 * mm))

    elements.append(
        Paragraph(
            "Merci de votre confiance.",
            styles["centre"],
        )
    )

    # --------------------------------------------------------
    # 10. Construire le PDF
    # --------------------------------------------------------

    document.build(elements)

    pdf = buffer.getvalue()

    buffer.close()

    return pdf
