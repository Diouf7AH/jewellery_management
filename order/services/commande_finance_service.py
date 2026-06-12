from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from sale.models import Facture, Paiement, PaiementLigne

ZERO = Decimal("0.00")


def dec(v):
    if v in (None, "", "null"):
        return ZERO
    return Decimal(str(v))


@transaction.atomic
def create_facture_acompte_for_commande(*, commande, montant):
    montant = dec(montant)
    if montant <= ZERO:
        raise ValidationError("Le montant de la facture d'acompte doit être > 0.")

    return Facture.objects.create(
        bijouterie=commande.bijouterie,
        commande_client=commande,
        montant_total=montant,
        type_facture=Facture.TYPE_ACOMPTE,
        status=Facture.STAT_NON_PAYE,
        vente=None,
    )


@transaction.atomic
def create_facture_finale_for_commande(*, commande):
    montant = dec(commande.reste_global)
    if montant <= ZERO:
        raise ValidationError("Aucun solde restant à facturer.")

    return Facture.objects.create(
        bijouterie=commande.bijouterie,
        commande_client=commande,
        montant_total=montant,
        type_facture=Facture.TYPE_FINALE,
        status=Facture.STAT_NON_PAYE,
        vente=None,
    )


@transaction.atomic
def register_facture_payment(*, facture, created_by, lignes):
    if not lignes:
        raise ValidationError("Au moins une ligne de paiement est obligatoire.")

    paiement = Paiement.objects.create(
        facture=facture,
        created_by=created_by,
    )

    for item in lignes:
        PaiementLigne.objects.create(
            paiement=paiement,
            montant_paye=dec(item["montant_paye"]),
            mode_paiement=item["mode_paiement"],
            reference=item.get("reference"),
            compte_depot=item.get("compte_depot"),
            transaction_depot=item.get("transaction_depot"),
        )

    Facture.recompute_facture_status(facture)
    facture.refresh_from_db()
    return paiement


