from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.db.models import F
from django.core.exceptions import ValidationError

from .models import CompteDepot, Transaction

def _q2(v: Decimal) -> Decimal:
    return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

@transaction.atomic
def effectuer_depot(compte_id: int, montant: Decimal, user=None) -> Transaction:
    montant = _q2(montant)
    if montant <= 0:
        raise ValidationError("Le montant du dépôt doit être strictement positif.")

    compte = CompteDepot.objects.select_for_update().get(pk=compte_id)
    # Mise à jour du solde sous verrou
    compte.solde = _q2(Decimal(compte.solde) + montant)
    compte.save(update_fields=["solde"])

    tx = Transaction.objects.create(
        compte=compte,
        type_transaction="Depot",
        montant=montant,
        user=user,
        statut="Terminé",
    )
    return tx

@transaction.atomic
def effectuer_retrait(compte_id: int, montant: Decimal, user=None) -> Transaction:
    montant = _q2(montant)
    if montant <= 0:
        raise ValidationError("Le montant du retrait doit être strictement positif.")

    compte = CompteDepot.objects.select_for_update().get(pk=compte_id)

    if Decimal(compte.solde) < montant:
        raise ValidationError("Solde insuffisant pour ce retrait.")

    compte.solde = _q2(Decimal(compte.solde) - montant)
    # Si tu veux interdire les soldes négatifs de façon stricte :
    if compte.solde < 0:
        raise ValidationError("Le solde ne peut pas devenir négatif.")
    compte.save(update_fields=["solde"])

    tx = Transaction.objects.create(
        compte=compte,
        type_transaction="Retrait",
        montant=montant,
        user=user,
        statut="Terminé",
    )
    return tx