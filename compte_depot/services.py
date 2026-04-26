# compte_depot/services.py

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import CompteDepot, CompteDepotTransaction


def _money(value) -> Decimal:
    """
    Normalise un montant en Decimal avec 2 décimales.
    """
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@transaction.atomic
def effectuer_depot(compte_id, montant, user=None, reference=None, commentaire=None):
    montant = _money(montant)

    if montant <= 0:
        raise ValidationError("Le montant du dépôt doit être supérieur à 0.")

    minimum = _money(getattr(settings, "COMPTE_DEPOT_DEPOT_MINIMUM", 5000))

    if montant < minimum:
        raise ValidationError(f"Le dépôt minimum est {minimum} FCFA.")

    compte = CompteDepot.objects.select_for_update().get(pk=compte_id)

    solde_avant = _money(compte.solde)
    solde_apres = _money(solde_avant + montant)

    compte.solde = solde_apres
    compte.full_clean()
    compte.save(update_fields=["solde"])

    tx = CompteDepotTransaction.objects.create(
        compte=compte,
        type_transaction=CompteDepotTransaction.TYPE_DEPOT,
        montant=montant,
        user=user,
        statut=CompteDepotTransaction.STAT_TERMINE,
        reference=reference,
        commentaire=commentaire,
        solde_avant=solde_avant,
        solde_apres=solde_apres,
    )

    return tx



@transaction.atomic
def effectuer_retrait(compte_id, montant, user=None, reference=None, commentaire=None):
    """
    Effectue un retrait sur un compte dépôt.

    Règles :
    - montant > 0
    - montant >= minimum
    - montant multiple défini
    - solde suffisant
    """

    montant = _money(montant)

    if montant <= 0:
        raise ValidationError("Le montant du retrait doit être supérieur à 0.")

    minimum = _money(getattr(settings, "COMPTE_DEPOT_RETRAIT_MINIMUM", 5))
    multiple = _money(getattr(settings, "COMPTE_DEPOT_RETRAIT_MULTIPLE", 5))

    # 🔒 sécurité configuration
    if minimum <= 0:
        raise ValidationError("Configuration invalide : retrait minimum doit être > 0.")

    if multiple <= 0:
        raise ValidationError("Configuration invalide : multiple de retrait doit être > 0.")

    if minimum < multiple:
        raise ValidationError(
            "Configuration invalide : le minimum doit être ≥ au multiple."
        )

    # 🔒 règles métier
    if montant < minimum:
        raise ValidationError(f"Le retrait minimum est {minimum} FCFA.")

    if montant % multiple != 0:
        raise ValidationError(f"Le montant doit être un multiple de {multiple} FCFA.")

    compte = CompteDepot.objects.select_for_update().get(pk=compte_id)

    solde_avant = _money(compte.solde)

    if solde_avant < montant:
        raise ValidationError("Solde insuffisant pour effectuer ce retrait.")

    solde_apres = _money(solde_avant - montant)

    compte.solde = solde_apres
    compte.full_clean()
    compte.save(update_fields=["solde"])

    tx = CompteDepotTransaction.objects.create(
        compte=compte,
        type_transaction=CompteDepotTransaction.TYPE_RETRAIT,
        montant=montant,
        user=user,
        statut=CompteDepotTransaction.STAT_TERMINE,
        reference=reference,
        commentaire=commentaire,
        solde_avant=solde_avant,
        solde_apres=solde_apres,
    )

    return tx


