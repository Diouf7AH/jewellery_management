from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import CommandeClient
from .commande_finance_service import create_facture_finale_for_commande
from .commande_history_service import add_commande_history


@transaction.atomic
def assigner_ouvrier_commande(*, commande, ouvrier, user=None, commentaire=""):
    if commande.statut not in [CommandeClient.STATUT_BROUILLON, CommandeClient.STATUT_EN_ATTENTE]:
        raise ValidationError(
            f"Impossible d'assigner un ouvrier depuis le statut {commande.statut}."
        )

    if not commande.acompte_regle:
        raise ValidationError(
            "Impossible d'assigner un ouvrier : acompte minimum non réglé."
        )

    old_statut = commande.statut
    commande.ouvrier = ouvrier
    commande.date_affectation_ouvrier = timezone.now()
    commande.statut = CommandeClient.STATUT_EN_PRODUCTION
    commande.updated_by = user
    commande.save()

    add_commande_history(
        commande=commande,
        ancien_statut=old_statut,
        nouveau_statut=commande.statut,
        commentaire=commentaire or "Commande affectée à un ouvrier et passée en production.",
        user=user,
    )
    return commande


@transaction.atomic
def terminer_commande(*, commande, user=None, date_depot_boutique=None, date_fin_reelle=None, commentaire=""):
    if commande.statut != CommandeClient.STATUT_EN_PRODUCTION:
        raise ValidationError("Seule une commande en production peut être terminée.")

    old_statut = commande.statut
    commande.statut = CommandeClient.STATUT_TERMINEE
    commande.date_depot_boutique = date_depot_boutique or timezone.now()
    commande.date_fin_reelle = date_fin_reelle or timezone.localdate()
    commande.updated_by = user
    commande.save()

    if commande.reste_global > 0 and not commande.factures.filter(type_facture="finale").exists():
        create_facture_finale_for_commande(commande=commande)

    add_commande_history(
        commande=commande,
        ancien_statut=old_statut,
        nouveau_statut=commande.statut,
        commentaire=commentaire or "Commande terminée et déposée à la boutique.",
        user=user,
    )
    return commande


@transaction.atomic
def livrer_commande(*, commande, user=None):
    if commande.statut != CommandeClient.STATUT_TERMINEE:
        raise ValidationError("Seule une commande terminée peut être livrée.")

    if commande.reste_global > 0:
        raise ValidationError("Impossible de livrer : le solde n'est pas entièrement réglé.")

    old_statut = commande.statut
    commande.statut = CommandeClient.STATUT_LIVREE
    commande.date_livraison = timezone.now()
    commande.updated_by = user
    commande.save()

    add_commande_history(
        commande=commande,
        ancien_statut=old_statut,
        nouveau_statut=commande.statut,
        commentaire="Commande livrée au client.",
        user=user,
    )
    return commande

