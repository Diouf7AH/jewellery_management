# sale/pdf/escpos_ticket_58mm.py

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Optional

from django.utils import timezone

# ============================================================
# CONFIGURATION POS 58 MM
# ============================================================

NORMAL_WIDTH = 32
CONDENSED_WIDTH = 42

LINE_NORMAL = "-" * NORMAL_WIDTH
LINE_CONDENSED = "-" * CONDENSED_WIDTH


# ============================================================
# COMMANDES ESC/POS
# ============================================================

INIT = b"\x1b@"

ALIGN_LEFT = b"\x1ba\x00"
ALIGN_CENTER = b"\x1ba\x01"

BOLD_ON = b"\x1bE\x01"
BOLD_OFF = b"\x1bE\x00"

FONT_A = b"\x1bM\x00"
NORMAL_SIZE = b"\x1d!\x00"

CONDENSED_ON = b"\x1b\x0f"
CONDENSED_OFF = b"\x12"

CUT_PARTIAL = b"\x1dV\x01"


# ============================================================
# HELPERS
# ============================================================

def _money(value) -> str:
    """
    Convertit un montant en FCFA.

    Exemple :
        12500.00 -> 12 500 FCFA
    """

    try:
        amount = Decimal(
            str(value if value is not None else "0")
        )

        if not amount.is_finite():
            raise ValueError("Montant non fini.")

        amount = amount.quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ) as exc:
        raise ValueError(
            "Montant du ticket invalide."
        ) from exc

    return (
        f"{amount:,.0f}".replace(",", " ")
        + " FCFA"
    )


def _clean_text(value) -> str:
    """
    Nettoie les caractères de contrôle afin
    de conserver une seule ligne imprimable.
    """

    text = str(
        value if value is not None else ""
    )

    text = " ".join(text.split())

    return "".join(
        char if ord(char) >= 32 else " "
        for char in text
    ).strip()


def _txt(value) -> bytes:
    """
    Encode une ligne en CP1252.

    Une utilisation de _txt() correspond
    à une ligne imprimée.
    """

    text = _clean_text(value)

    return (
        text + "\n"
    ).encode(
        "cp1252",
        errors="replace",
    )


def _fit(
    text: str,
    width: int,
) -> str:
    """
    Limite un texte à une largeur donnée.
    """

    if width <= 0:
        return ""

    text = _clean_text(text)

    if len(text) <= width:
        return text

    if width <= 3:
        return text[:width]

    return text[:width - 3] + "..."


def _left_right(
    left: str,
    right: str,
    width: int,
) -> str:
    """
    Affiche deux valeurs sur une seule ligne.

    Exemple :
    DATE : 23/09/2026             22:27
    """

    left = _clean_text(left)
    right = _clean_text(right)

    if width <= 0:
        return ""

    if not left:
        return _fit(right, width)

    if not right:
        return _fit(left, width)

    if len(right) >= width:
        return _fit(right, width)

    max_left = width - len(right) - 1

    left = _fit(
        left,
        max_left,
    )

    spaces = max(
        width - len(left) - len(right),
        1,
    )

    return (
        left
        + (" " * spaces)
        + right
    )


def _normalize_datetime(value):
    """
    Convertit une date en heure locale Django.

    Si aucune date n'est fournie,
    utilise la date actuelle.
    """

    if value is None:
        value = timezone.now()

    if not isinstance(value, datetime):
        raise ValueError(
            "La date fournie doit être un datetime."
        )

    if timezone.is_aware(value):
        return timezone.localtime(value)

    if timezone.is_aware(timezone.now()):
        value = timezone.make_aware(
            value,
            timezone.get_current_timezone(),
        )

        return timezone.localtime(value)

    return value


def _split_date_time(
    date_txt: Optional[str],
):
    """
    Exemple :
        23/09/2026 22:27

    Résultat :
        ("23/09/2026", "22:27")
    """

    value = _clean_text(date_txt)

    if not value:
        dt = _normalize_datetime(None)

        return (
            dt.strftime("%d/%m/%Y"),
            dt.strftime("%H:%M"),
        )

    parts = value.split()

    if len(parts) >= 2:
        return (
            parts[0],
            parts[1],
        )

    return (
        value,
        "",
    )


def _normalize_status(
    statut_txt: Optional[str],
) -> str:
    """
    Normalise les statuts.

    Exemples :
        Non payée -> NON PAYE
        Partiel   -> PARTIEL
        Payée     -> PAYE
    """

    statut = _clean_text(
        statut_txt or "NON PAYE"
    ).upper()

    replacements = {
        "É": "E",
        "È": "E",
        "Ê": "E",
        "À": "A",
        "Â": "A",
        "Ù": "U",
    }

    for old, new in replacements.items():
        statut = statut.replace(
            old,
            new,
        )

    if statut in {
        "NON PAYEE",
        "NON_PAYE",
        "NON_PAYEE",
        "NON PAYE",
    }:
        return "NON PAYE"

    if statut in {
        "PAYEE",
        "PAYE",
    }:
        return "PAYE"

    if statut in {
        "PARTIEL",
        "PARTIELLEMENT PAYE",
        "PARTIELLEMENT PAYEE",
    }:
        return "PARTIEL"

    return statut


# ============================================================
# GÉNÉRATION DU TICKET PROFORMA 58 MM
# ============================================================

def build_escpos_ticket_proforma_58mm(
    *,
    shop_name: str = "RIO-GOLD",
    shop_phone: Optional[str] = None,
    numero_facture: str,
    date_txt: Optional[str] = None,
    montant_a_payer=Decimal("0"),
    statut_txt: str = "NON PAYE",
    note: Optional[str] = (
        "Ticket PROFORMA a regler en caisse."
    ),
) -> bytes:
    """
    Génère un ticket PROFORMA ESC/POS 58 mm.

    Règles Rio-Gold :
    - Réservé aux ventes contenant des bijoux.
    - Aucune modification financière.
    - Aucun mouvement de stock.
    - Retourne des octets ESC/POS.

    Mise en page :
    - 32 caractères en mode normal.
    - 42 caractères en mode condensé.
    - Montant en FCFA.
    - Coupe partielle en fin de ticket.
    """

    # ========================================================
    # 1. VALIDATION DES DONNÉES
    # ========================================================

    numero_facture = _clean_text(
        numero_facture
    )

    if not numero_facture:
        raise ValueError(
            "Le numéro de facture est obligatoire."
        )

    shop_name = _clean_text(
        shop_name or "RIO-GOLD"
    )

    shop_phone = _clean_text(
        shop_phone
    )

    statut = _normalize_status(
        statut_txt
    )

    montant_txt = _money(
        montant_a_payer
    )

    # ========================================================
    # 2. DATE / HEURE
    # ========================================================

    date_only, heure_only = _split_date_time(
        date_txt
    )

    # ========================================================
    # 3. BUFFER ESC/POS
    # ========================================================

    out = bytearray()

    # ========================================================
    # 4. INITIALISATION
    # ========================================================

    out += INIT
    out += FONT_A
    out += NORMAL_SIZE
    out += ALIGN_CENTER

    # Marge haute
    out += b"\n\n"

    # ========================================================
    # 5. EN-TÊTE
    # ========================================================

    out += BOLD_ON

    out += _txt(
        _fit(
            shop_name.upper(),
            NORMAL_WIDTH,
        )
    )

    out += BOLD_OFF

    if shop_phone:
        out += _txt(
            _fit(
                f"Tel: {shop_phone}",
                NORMAL_WIDTH,
            )
        )

    out += _txt(
        LINE_NORMAL
    )

    # ========================================================
    # 6. INFORMATIONS FACTURE
    # ========================================================

    out += ALIGN_LEFT
    out += CONDENSED_ON

    # --------------------------------------------------------
    # FACTURE PROFORMA + NUMÉRO
    # --------------------------------------------------------

    out += BOLD_ON

    numero_txt = f"N° {numero_facture}"

    if (
        len("FACTURE PROFORMA")
        + len(numero_txt)
        + 1
        <= CONDENSED_WIDTH
    ):
        out += _txt(
            _left_right(
                "FACTURE PROFORMA",
                numero_txt,
                CONDENSED_WIDTH,
            )
        )
    else:
        # Conserve le numéro complet sur une ligne
        # distincte lorsqu'il est trop long.
        out += _txt(
            "FACTURE PROFORMA"
        )

        out += _txt(
            _fit(
                numero_txt,
                CONDENSED_WIDTH,
            )
        )

    # --------------------------------------------------------
    # SÉPARATEUR
    # --------------------------------------------------------

    out += BOLD_OFF

    out += _txt(
        LINE_CONDENSED
    )

    # --------------------------------------------------------
    # DATE + HEURE
    # --------------------------------------------------------

    out += _txt(
        _left_right(
            f"DATE : {date_only}",
            heure_only,
            CONDENSED_WIDTH,
        )
    )

    # --------------------------------------------------------
    # ÉTAT
    # --------------------------------------------------------

    out += BOLD_ON

    out += _txt(
        _fit(
            f"ETAT : {statut}",
            CONDENSED_WIDTH,
        )
    )

    out += BOLD_OFF

    # --------------------------------------------------------
    # SÉPARATEUR
    # --------------------------------------------------------

    out += _txt(
        LINE_CONDENSED
    )

    # ========================================================
    # 7. FIN MODE CONDENSÉ
    # ========================================================

    out += CONDENSED_OFF

    # ========================================================
    # 8. MONTANT À PAYER
    # ========================================================

    out += ALIGN_CENTER
    out += BOLD_ON

    out += _txt(
        "MONTANT A PAYER"
    )

    out += _txt(
        _fit(
            montant_txt,
            NORMAL_WIDTH,
        )
    )

    out += BOLD_OFF

    out += _txt(
        LINE_NORMAL
    )

    # ========================================================
    # 9. NOTE
    # ========================================================

    if note:
        out += ALIGN_CENTER
        out += CONDENSED_ON

        out += _txt(
            _fit(
                note,
                CONDENSED_WIDTH,
            )
        )

        out += CONDENSED_OFF

    # ========================================================
    # 10. MESSAGE DE REMERCIEMENT
    # ========================================================

    out += ALIGN_CENTER
    out += CONDENSED_ON
    out += BOLD_ON

    out += _txt(
        _fit(
            "Merci pour votre confiance !",
            CONDENSED_WIDTH,
        )
    )

    out += BOLD_OFF
    out += CONDENSED_OFF

    # ========================================================
    # 11. RESTAURATION DU MODE NORMAL
    # ========================================================

    out += NORMAL_SIZE
    out += ALIGN_LEFT

    # ========================================================
    # 12. MARGE BASSE
    # ========================================================

    out += b"\n\n\n\n"

    # ========================================================
    # 13. COUPE PARTIELLE
    # ========================================================

    out += CUT_PARTIAL

    # ========================================================
    # 14. RÉSULTAT
    # ========================================================

    return bytes(out)

