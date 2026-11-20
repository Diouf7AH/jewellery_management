# sale/services/comptable_export_service.py

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from sale.models import Facture, PaiementLigne

ZERO = Decimal("0.00")
CENTIME = Decimal("0.01")


# À valider avec le plan comptable SYSCOHADA
# effectivement utilisé par Rio-Gold.
COMPTES = {
    "client": "411",
    "vente": "701",
    "tva_collectee": "4431",
    "frais_factures": None,
}

# Les comptes Wave / Orange Money / banque doivent
# être confirmés par le comptable de l'entreprise.
COMPTES_PAIEMENT = {
    "cash": "571",
    "especes": "571",
    "wave": None,
    "orange_money": None,
    "bank": None,
    "banque": None,
    "cheque": None,
    "depot_client": None,
}


# ============================================================
# 1. VALIDATION MONÉTAIRE
# ============================================================

def _montant(value, champ: str) -> Decimal:
    """
    Valide un montant comptable non négatif.
    """

    if value is None or isinstance(value, bool):
        raise ValidationError({
            champ: "Montant invalide."
        })

    try:
        montant = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({
            champ: "Montant non numérique."
        }) from exc

    if not montant.is_finite() or montant < ZERO:
        raise ValidationError({
            champ: "Montant négatif ou non fini."
        })

    try:
        normalise = montant.quantize(CENTIME)
    except InvalidOperation as exc:
        raise ValidationError({
            champ: "Montant hors limites."
        }) from exc

    if montant != normalise:
        raise ValidationError({
            champ: "Deux décimales maximum."
        })

    return normalise


def _date_comptable(value):
    """
    Retourne une date compatible avec Excel.
    """

    if value is None:
        raise ValidationError({
            "date": "Date comptable obligatoire."
        })

    if timezone.is_aware(value):
        value = timezone.localtime(value)

    return value.date()


# ============================================================
# 2. ÉCRITURE COMPTABLE
# ============================================================

def _ajouter_ecriture(
    ws,
    *,
    date,
    journal,
    piece,
    compte,
    libelle,
    debit=ZERO,
    credit=ZERO,
):
    debit = _montant(debit, "debit")
    credit = _montant(credit, "credit")

    if not compte:
        raise ValidationError({
            "compte": (
                f"Compte comptable manquant : {libelle}."
            )
        })

    if debit > ZERO and credit > ZERO:
        raise ValidationError({
            "ecriture": (
                "Une ligne ne peut pas avoir "
                "simultanément un débit et un crédit."
            )
        })

    if debit == ZERO and credit == ZERO:
        return

    ws.append([
        date,
        journal,
        str(piece),
        str(compte),
        libelle,
        debit,
        credit,
    ])


def _verifier_equilibre(
    *,
    piece,
    total_debit,
    total_credit,
):
    if total_debit != total_credit:
        raise ValidationError({
            "comptabilite": (
                f"Écriture déséquilibrée pour {piece} : "
                f"débit={total_debit}, "
                f"crédit={total_credit}."
            )
        })


# ============================================================
# 3. COMPTE DU MODE DE PAIEMENT
# ============================================================

def _compte_mode_paiement(mode):
    """
    Identifie le compte comptable du règlement.

    Ne remplace jamais un compte inconnu
    par le compte caisse.
    """

    code = str(
        getattr(mode, "code", "") or ""
    ).strip().lower()

    if not code:
        raise ValidationError({
            "mode_paiement": (
                "Code du mode de paiement manquant."
            )
        })

    compte = COMPTES_PAIEMENT.get(code)

    if not compte:
        raise ValidationError({
            "mode_paiement": (
                f"Aucun compte comptable configuré "
                f"pour le mode '{code}'."
            )
        })

    return compte


# ============================================================
# 4. EXPORT PRINCIPAL
# ============================================================

def export_comptable_factures(factures):
    """
    Exporte les factures définitives et leurs paiements.

    Exclusions :
        - factures proforma ;
        - ventes uniquement prestations ;
        - factures non définitives.

    Chaque facture produit :
        Débit 411 : total TTC
        Crédit ventes : montant HT
        Crédit TVA : TVA collectée
        Crédit frais : frais éventuels

    Chaque ligne de paiement produit :
        Débit compte de trésorerie
        Crédit 411 client

    Retour :
        Workbook OpenPyXL.

    Important :
        - les comptes doivent être validés ;
        - les paiements ne sont pas modifiés ;
        - aucune écriture n'est enregistrée en base.
    """

    wb = Workbook()
    ws = wb.active
    ws.title = "Journal"

    ws.append([
        "Date",
        "Journal",
        "Piece",
        "Compte",
        "Libelle",
        "Debit",
        "Credit",
    ])

    # Permet d'accepter un QuerySet Django.
    factures = factures.select_related(
        "vente",
        "bijouterie",
    ).prefetch_related(
        "paiements__lignes__mode_paiement",
    ) if hasattr(factures, "select_related") else factures

    for facture in factures:

        # ----------------------------------------------------
        # 1. FACTURES DÉFINITIVES UNIQUEMENT
        # ----------------------------------------------------

        if facture.type_facture != Facture.TYPE_FACTURE:
            continue

        if not facture.vente_id:
            raise ValidationError({
                "facture": "Vente associée manquante."
            })

        if (
            facture.bijouterie_id
            != facture.vente.bijouterie_id
        ):
            raise ValidationError({
                "facture": (
                    "Incohérence entre la facture "
                    "et sa bijouterie."
                )
            })

        numero = facture.numero_facture

        if not numero:
            raise ValidationError({
                "numero_facture": (
                    "Numéro de facture obligatoire."
                )
            })

        date_facture = _date_comptable(
            facture.date_creation
        )

        montant_ht = _montant(
            facture.montant_ht,
            "montant_ht",
        )

        montant_tva = _montant(
            facture.montant_tva,
            "montant_tva",
        )

        montant_total = _montant(
            facture.montant_total,
            "montant_total",
        )

        frais = _montant(
            getattr(
                facture,
                "frais_transaction",
                ZERO,
            ),
            "frais_transaction",
        )

        if (
            montant_ht + montant_tva + frais
            != montant_total
        ):
            raise ValidationError({
                "facture": (
                    f"Montants incohérents pour {numero}."
                )
            })

        # ----------------------------------------------------
        # 2. JOURNAL DES VENTES
        # ----------------------------------------------------

        debut = ws.max_row + 1

        _ajouter_ecriture(
            ws,
            date=date_facture,
            journal="VEN",
            piece=numero,
            compte=COMPTES["client"],
            libelle="Créance client",
            debit=montant_total,
        )

        _ajouter_ecriture(
            ws,
            date=date_facture,
            journal="VEN",
            piece=numero,
            compte=COMPTES["vente"],
            libelle="Vente de bijoux et prestations",
            credit=montant_ht,
        )

        if montant_tva > ZERO:
            _ajouter_ecriture(
                ws,
                date=date_facture,
                journal="VEN",
                piece=numero,
                compte=COMPTES["tva_collectee"],
                libelle="TVA collectée",
                credit=montant_tva,
            )

        if frais > ZERO:
            _ajouter_ecriture(
                ws,
                date=date_facture,
                journal="VEN",
                piece=numero,
                compte=COMPTES["frais_factures"],
                libelle="Frais facturés au client",
                credit=frais,
            )

        _verifier_equilibre(
            piece=numero,
            total_debit=montant_total,
            total_credit=(
                montant_ht + montant_tva + frais
            ),
        )

        # ----------------------------------------------------
        # 3. JOURNAL DES RÈGLEMENTS
        # ----------------------------------------------------

        for paiement in facture.paiements.all():

            date_paiement = _date_comptable(
                getattr(
                    paiement,
                    "date_paiement",
                    None,
                )
            )

            for ligne in paiement.lignes.all():

                montant = _montant(
                    ligne.montant_paye,
                    "montant_paye",
                )

                if montant == ZERO:
                    continue

                compte = _compte_mode_paiement(
                    ligne.mode_paiement
                )

                piece_paiement = (
                    f"{numero}-P{paiement.pk}"
                    f"-L{ligne.pk}"
                )

                _ajouter_ecriture(
                    ws,
                    date=date_paiement,
                    journal="REG",
                    piece=piece_paiement,
                    compte=compte,
                    libelle="Encaissement client",
                    debit=montant,
                )

                _ajouter_ecriture(
                    ws,
                    date=date_paiement,
                    journal="REG",
                    piece=piece_paiement,
                    compte=COMPTES["client"],
                    libelle="Règlement facture",
                    credit=montant,
                )

                _verifier_equilibre(
                    piece=piece_paiement,
                    total_debit=montant,
                    total_credit=montant,
                )

    # ========================================================
    # 5. MISE EN FORME
    # ========================================================

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    widths = [15, 12, 30, 15, 40, 20, 20]

    for index, width in enumerate(widths, start=1):
        letter = get_column_letter(index)
        ws.column_dimensions[letter].width = width

    for cell in ws[1]:
        cell.font = Font(
            bold=True,
            color="FFFFFF",
        )
        cell.fill = PatternFill(
            fill_type="solid",
            fgColor="17365D",
        )
        cell.alignment = Alignment(
            horizontal="center",
        )

    for row in ws.iter_rows(
        min_row=2,
        max_row=ws.max_row,
    ):
        row[0].number_format = "DD/MM/YYYY"

        for cell in (row[5], row[6]):
            cell.number_format = '#,##0.00'
            cell.alignment = Alignment(
                horizontal="right",
            )

    return wb

