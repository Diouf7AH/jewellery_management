# reparation/services/ticket_de_restitution.py

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from io import BytesIO
from xml.sax.saxutils import escape

from django.core.exceptions import ValidationError
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (HRFlowable, KeepTogether, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

# ============================================================
# CONFIGURATION DU TICKET THERMIQUE
# ============================================================

LARGEUR_PAPIER = 80 * mm

MARGE_GAUCHE = 4 * mm
MARGE_DROITE = 4 * mm
MARGE_HAUT = 4 * mm
MARGE_BAS = 5 * mm

LARGEUR_CONTENU = (
    LARGEUR_PAPIER
    - MARGE_GAUCHE
    - MARGE_DROITE
)

NOIR = colors.black
GRIS = colors.HexColor("#555555")
BORDURE = colors.HexColor("#999999")

ZERO = Decimal("0.00")


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


def _decimal(valeur):
    try:
        montant = Decimal(str(valeur))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(
            "Un montant du reçu est invalide."
        )

    if not montant.is_finite():
        raise ValidationError(
            "Un montant du reçu est invalide."
        )

    return montant


def _montant(valeur):
    montant = _decimal(valeur)

    return (
        f"{montant:,.2f}"
        .replace(",", " ")
        + " FCFA"
    )


def _poids(valeur):
    if valeur is None:
        return "-"

    return f"{_decimal(valeur):.3f} g"


def _date(valeur):
    if not valeur:
        return "-"

    if timezone.is_aware(valeur):
        valeur = timezone.localtime(valeur)

    return valeur.strftime("%d/%m/%Y %H:%M")


def _nom_client(client):
    if client is None:
        return "-"

    prenom = _texte(
        getattr(client, "prenom", None),
        "",
    )

    nom = _texte(
        getattr(client, "nom", None),
        "",
    )

    resultat = f"{prenom} {nom}".strip()

    return resultat or "-"


def _nom_utilisateur(user):
    if user is None:
        return "-"

    if hasattr(user, "get_full_name"):
        nom = user.get_full_name()

        if nom:
            return nom

    return _texte(
        getattr(user, "username", None)
        or getattr(user, "email", None)
    )


def _telephone_bijouterie(bijouterie):
    champs = (
        "telephone_portable_1",
        "telephone_portable_2",
        "telephone_fix",
    )

    for champ in champs:
        valeur = getattr(
            bijouterie,
            champ,
            None,
        )

        if valeur:
            return str(valeur)

    return "-"


def _libelle_mode_paiement(mode):
    if mode is None:
        return "-"

    for champ in ("nom", "libelle", "name"):
        valeur = getattr(mode, champ, None)

        if valeur:
            return str(valeur)

    return _texte(
        getattr(mode, "code", None)
    ).replace("_", " ").title()


# ============================================================
# STYLES DU TICKET
# ============================================================

def _creer_styles():

    return {
        "enseigne": ParagraphStyle(
            name="RG80_Enseigne",
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=15,
            alignment=TA_CENTER,
            textColor=NOIR,
        ),

        "titre": ParagraphStyle(
            name="RG80_Titre",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
            spaceAfter=4,
        ),

        "centre": ParagraphStyle(
            name="RG80_Centre",
            fontName="Helvetica",
            fontSize=7,
            leading=10,
            alignment=TA_CENTER,
        ),

        "normal": ParagraphStyle(
            name="RG80_Normal",
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            alignment=TA_LEFT,
        ),

        "petit": ParagraphStyle(
            name="RG80_Petit",
            fontName="Helvetica",
            fontSize=6.5,
            leading=9,
            alignment=TA_LEFT,
        ),

        "section": ParagraphStyle(
            name="RG80_Section",
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            spaceBefore=4,
            spaceAfter=3,
        ),

        "total": ParagraphStyle(
            name="RG80_Total",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            alignment=TA_RIGHT,
        ),

        "statut": ParagraphStyle(
            name="RG80_Statut",
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            alignment=TA_CENTER,
        ),
    }


# ============================================================
# LIGNE D'INFORMATION
# ============================================================

def _ligne_info(libelle, valeur, styles):

    return Table(
        [[
            Paragraph(
                f"<b>{_html(libelle)}</b>",
                styles["normal"],
            ),
            Paragraph(
                _html(valeur),
                styles["normal"],
            ),
        ]],
        colWidths=[
            LARGEUR_CONTENU * 0.38,
            LARGEUR_CONTENU * 0.62,
        ],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]),
    )


# ============================================================
# DÉTAIL D'UN BIJOU
# ============================================================

def _bloc_bijou(bijou, numero, styles):

    elements = []

    elements.append(
        Paragraph(
            f"<b>BIJOU N° {numero}</b>",
            styles["normal"],
        )
    )

    elements.append(
        Paragraph(
            "Type : "
            + _html(
                getattr(bijou, "type_bijou", None)
            ),
            styles["petit"],
        )
    )

    elements.append(
        Paragraph(
            "Description : "
            + _html(
                getattr(
                    bijou,
                    "description_bijou",
                    None,
                )
            ),
            styles["petit"],
        )
    )

    elements.append(
        Paragraph(
            "Poids : "
            + _html(
                _poids(
                    getattr(bijou, "poids", None)
                )
            )
            + " | Pureté : "
            + _html(
                getattr(bijou, "purete", None)
            ),
            styles["petit"],
        )
    )

    travail = (
        getattr(
            bijou,
            "travail_effectue",
            None,
        )
        or getattr(
            bijou,
            "travail_demande",
            None,
        )
    )

    elements.append(
        Paragraph(
            "Travail : " + _html(travail),
            styles["petit"],
        )
    )

    elements.append(
        Paragraph(
            "<b>Prix : "
            + _html(
                _montant(
                    getattr(
                        bijou,
                        "prix_reparation",
                        ZERO,
                    )
                )
            )
            + "</b>",
            styles["normal"],
        )
    )

    elements.append(Spacer(1, 2 * mm))

    return KeepTogether(elements)


# ============================================================
# VÉRIFICATION DU PAIEMENT
# ============================================================

def _verifier_paiement(reparation):

    if reparation is None:
        raise ValidationError(
            "La réparation est introuvable."
        )

    try:
        paiement = reparation.paiement
    except (
        AttributeError,
        reparation._meta.get_field(
            "paiement"
        ).related_model.DoesNotExist,
    ):
        raise ValidationError(
            "Aucun paiement n'est enregistré "
            "pour cette réparation."
        )

    if paiement is None:
        raise ValidationError(
            "Aucun paiement n'est enregistré."
        )

    total = _decimal(
        reparation.prix_convenu
    )

    montant_paye = _decimal(
        paiement.montant_paye
    )

    if total <= ZERO:
        raise ValidationError(
            "Le montant total de la réparation "
            "doit être supérieur à zéro."
        )

    if montant_paye != total:
        raise ValidationError(
            "Le reçu est indisponible : "
            "le paiement n'est pas intégral."
        )

    return paiement


# ============================================================
# CONSTRUCTION DU CONTENU
# ============================================================

def _construire_elements(
    reparation,
    paiement,
    bijoux,
    styles,
):

    elements = []

    bijouterie = reparation.bijouterie
    client = reparation.client

    # --------------------------------------------------------
    # 1. EN-TÊTE
    # --------------------------------------------------------

    elements.append(
        Paragraph(
            _html(
                getattr(
                    bijouterie,
                    "nom",
                    "RIO-GOLD",
                )
            ),
            styles["enseigne"],
        )
    )

    elements.append(
        Paragraph(
            "REÇU DE PAIEMENT",
            styles["titre"],
        )
    )

    elements.append(
        Paragraph(
            "RÉPARATION DE BIJOUX",
            styles["centre"],
        )
    )

    elements.append(
        Paragraph(
            "Tél : "
            + _html(
                _telephone_bijouterie(
                    bijouterie
                )
            ),
            styles["centre"],
        )
    )

    elements.append(Spacer(1, 2 * mm))

    elements.append(
        HRFlowable(
            width="100%",
            thickness=0.7,
            color=NOIR,
        )
    )

    elements.append(Spacer(1, 2 * mm))

    # --------------------------------------------------------
    # 2. INFORMATIONS DU DOSSIER
    # --------------------------------------------------------

    informations = [
        (
            "N° réparation",
            reparation.numero_reparation,
        ),
        (
            "Date paiement",
            _date(paiement.date_paiement),
        ),
        (
            "Client",
            _nom_client(client),
        ),
        (
            "Téléphone",
            getattr(
                client,
                "telephone",
                None,
            ),
        ),
        (
            "Nombre bijoux",
            len(bijoux),
        ),
    ]

    for libelle, valeur in informations:
        elements.append(
            _ligne_info(
                libelle,
                valeur,
                styles,
            )
        )

    elements.append(Spacer(1, 2 * mm))

    elements.append(
        HRFlowable(
            width="100%",
            thickness=0.5,
            color=BORDURE,
        )
    )

    # --------------------------------------------------------
    # 3. DÉTAILS DES BIJOUX
    # --------------------------------------------------------

    elements.append(
        Paragraph(
            "DÉTAILS DES RÉPARATIONS",
            styles["section"],
        )
    )

    for index, bijou in enumerate(
        bijoux,
        start=1,
    ):

        numero = (
            getattr(
                bijou,
                "numero_ligne",
                None,
            )
            or index
        )

        elements.append(
            _bloc_bijou(
                bijou,
                numero,
                styles,
            )
        )

    elements.append(
        HRFlowable(
            width="100%",
            thickness=0.7,
            color=NOIR,
        )
    )

    elements.append(Spacer(1, 3 * mm))

    # --------------------------------------------------------
    # 4. PAIEMENT
    # --------------------------------------------------------

    elements.append(
        Paragraph(
            "TOTAL PAYÉ : "
            + _html(
                _montant(
                    paiement.montant_paye
                )
            ),
            styles["total"],
        )
    )

    elements.append(Spacer(1, 2 * mm))

    paiement_infos = [
        (
            "Mode",
            _libelle_mode_paiement(
                paiement.mode_paiement
            ),
        ),
        (
            "Référence",
            paiement.reference,
        ),
        (
            "Reste à payer",
            _montant(ZERO),
        ),
    ]

    if paiement.compte_depot_id:
        paiement_infos.append(
            (
                "Compte dépôt",
                paiement.compte_depot.numero_compte,
            )
        )

    for libelle, valeur in paiement_infos:
        elements.append(
            _ligne_info(
                libelle,
                valeur,
                styles,
            )
        )

    elements.append(Spacer(1, 3 * mm))

    elements.append(
        Paragraph(
            "PAIEMENT INTÉGRAL EFFECTUÉ",
            styles["statut"],
        )
    )

    # --------------------------------------------------------
    # 5. RESTITUTION PHYSIQUE
    # --------------------------------------------------------

    est_restituee = (
        reparation.statut
        == reparation.Statut.RESTITUE
    )

    elements.append(Spacer(1, 3 * mm))

    elements.append(
        HRFlowable(
            width="100%",
            thickness=0.5,
            color=BORDURE,
        )
    )

    elements.append(Spacer(1, 2 * mm))

    if est_restituee:

        elements.append(
            Paragraph(
                "BIJOUX RESTITUÉS AU CLIENT",
                styles["statut"],
            )
        )

        elements.append(
            _ligne_info(
                "Date restitution",
                _date(
                    reparation.date_restitution
                ),
                styles,
            )
        )

        elements.append(
            _ligne_info(
                "Remis par",
                _nom_utilisateur(
                    reparation.restitue_par
                ),
                styles,
            )
        )

    else:

        elements.append(
            Paragraph(
                "BIJOUX NON ENCORE RESTITUÉS",
                styles["statut"],
            )
        )

        elements.append(
            Paragraph(
                "Ce document confirme le paiement "
                "intégral de la réparation. "
                "Il ne constitue pas une preuve "
                "de remise physique des bijoux.",
                styles["petit"],
            )
        )

    # --------------------------------------------------------
    # 6. PIED DE PAGE
    # --------------------------------------------------------

    elements.append(Spacer(1, 4 * mm))

    elements.append(
        HRFlowable(
            width="100%",
            thickness=0.7,
            color=NOIR,
        )
    )

    elements.append(Spacer(1, 3 * mm))

    elements.append(
        Paragraph(
            "Merci de votre confiance.",
            styles["centre"],
        )
    )

    return elements


# ============================================================
# GÉNÉRATION DU REÇU THERMIQUE 80 MM
# ============================================================

def generer_recu_paiement_reparation_pdf(
    reparation,
) -> bytes:
    """
    Génère le reçu thermique PDF 80 mm.

    Le reçu est disponible après paiement intégral,
    même lorsque la réparation est encore PRET.

    Si la restitution physique a été confirmée,
    le ticket indique également sa date.

    Aucune modification en base de données.
    """

    # --------------------------------------------------------
    # 1. Vérifier le paiement
    # --------------------------------------------------------

    paiement = _verifier_paiement(
        reparation
    )

    # --------------------------------------------------------
    # 2. Charger les bijoux
    # --------------------------------------------------------

    bijoux = list(
        reparation.bijoux.all().order_by(
            "numero_ligne",
            "pk",
        )
    )

    if not bijoux:
        raise ValidationError(
            "Aucun bijou n'est associé "
            "à cette réparation."
        )

    reparation.verifier_total_bijoux()

    # --------------------------------------------------------
    # 3. Préparer le contenu
    # --------------------------------------------------------

    styles = _creer_styles()

    elements = _construire_elements(
        reparation,
        paiement,
        bijoux,
        styles,
    )

    # --------------------------------------------------------
    # 4. Calculer la hauteur du ticket
    # --------------------------------------------------------

    largeur = LARGEUR_CONTENU

    hauteur_contenu = 0

    for element in elements:

        _, hauteur = element.wrap(
            largeur,
            2000 * mm,
        )

        hauteur_contenu += hauteur

        hauteur_contenu += (
            element.getSpaceBefore()
            + element.getSpaceAfter()
        )

    hauteur_page = (
        hauteur_contenu
        + MARGE_HAUT
        + MARGE_BAS
        + 12 * mm
    )

    # --------------------------------------------------------
    # 5. Générer le PDF
    # --------------------------------------------------------

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=(
            LARGEUR_PAPIER,
            hauteur_page,
        ),
        rightMargin=MARGE_DROITE,
        leftMargin=MARGE_GAUCHE,
        topMargin=MARGE_HAUT,
        bottomMargin=MARGE_BAS,
        title=(
            "Reçu de paiement - "
            f"{reparation.numero_reparation}"
        ),
        author="Rio-Gold",
    )

    document.build(elements)

    pdf = buffer.getvalue()

    buffer.close()

    return pdf


