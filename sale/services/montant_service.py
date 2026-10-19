# sale/services/montant_service.py
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.exceptions import ValidationError

ZERO = Decimal("0.00")
CENTIME = Decimal("0.01")
CENT = CENTIME  # Alias facultatif, sans changement de comportement.
CENT_POUR_CENT = Decimal("100")


def decimal_value(value, *, field="montant") -> Decimal:
    """Convertit en Decimal fini, sans conversion via float ni arrondi."""
    if value is None or isinstance(value, bool) or (
        isinstance(value, str) and not value.strip()
    ):
        raise ValidationError({field: "Valeur numérique invalide."})
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({field: "Valeur numérique invalide."}) from exc
    if not result.is_finite():
        raise ValidationError({field: "La valeur doit être un nombre fini."})
    return result


def money(value, *, field="montant") -> Decimal:
    """Arrondit à 2 décimales (ROUND_HALF_UP), sans changer le signe."""
    result = decimal_value(value, field=field)
    try:
        return result.quantize(CENTIME, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValidationError({field: "Montant hors limites."}) from exc


def money_strict(value, field="montant") -> Decimal:
    """Montant de paiement >= 0, au maximum 2 décimales significatives.

    `field` accepte volontairement un argument positionnel pour rester compatible
    avec les appels existants `_money(value, "nom_du_champ")`.
    """
    result = decimal_value(value, field=field)
    if result < ZERO:
        raise ValidationError({field: "Le montant ne peut pas être négatif."})
    try:
        arrondi = result.quantize(CENTIME, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValidationError({field: "Montant hors limites."}) from exc
    if result != arrondi:
        raise ValidationError({field: "Deux décimales maximum sont autorisées."})
    return arrondi


def calculer_montants(
    *, montant_brut_ht, montant_reduction=ZERO, taux_tva=ZERO
) -> dict:
    """Calcule brut, réduction, net HT, TVA et total.

    `taux_tva` est exprimé en pourcentage : 18 signifie 18 %.
    Les montants sont arrondis à 2 décimales ; le taux n'est pas arrondi.
    """
    brut_initial = decimal_value(montant_brut_ht, field="montant_brut_ht")
    reduction_initiale = decimal_value(
        montant_reduction, field="montant_reduction"
    )
    taux = decimal_value(taux_tva, field="taux_tva")

    if brut_initial < ZERO:
        raise ValidationError({"montant_brut_ht": "Montant brut négatif."})
    if reduction_initiale < ZERO:
        raise ValidationError({"montant_reduction": "Réduction négative."})
    if reduction_initiale > brut_initial:
        raise ValidationError({
            "montant_reduction": "La réduction dépasse le montant brut."
        })
    if taux < ZERO:
        raise ValidationError({"taux_tva": "Taux TVA invalide."})

    brut = money(brut_initial, field="montant_brut_ht")
    reduction = money(reduction_initiale, field="montant_reduction")
    # Les arrondis HALF_UP préservent l'ordre des montants positifs.
    ht = money(brut - reduction, field="montant_ht")
    tva = money(ht * taux / CENT_POUR_CENT, field="montant_tva")
    total = money(ht + tva, field="montant_total")
    return {
        "montant_brut_ht": brut,
        "montant_reduction": reduction,
        "montant_ht": ht,
        "montant_tva": tva,
        "montant_total": total,
    }


def calculer_solde_paiement(
    *, montant_total, montant_deja_paye, nouveau_paiement=ZERO
) -> dict:
    """Valide le cumul encaissé et retourne les soldes avant/après paiement."""
    total = money_strict(montant_total, "montant_total")
    deja = money_strict(montant_deja_paye, "montant_deja_paye")
    nouveau = money_strict(nouveau_paiement, "nouveau_paiement")

    if deja > total:
        raise ValidationError({
            "montant_deja_paye": "Paiements supérieurs au total."
        })
    reste_avant = total - deja
    if nouveau > reste_avant:
        raise ValidationError({
            "nouveau_paiement": "Paiement supérieur au solde."
        })
    reste_apres = reste_avant - nouveau
    return {
        "montant_total": total,
        "montant_deja_paye": deja,
        "nouveau_paiement": nouveau,
        "total_paye": deja + nouveau,
        "reste_a_payer": reste_apres,
        "paiement_complet": reste_apres == ZERO,
    }
