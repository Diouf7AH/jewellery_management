# reparation/services/restitution_service.py

"""
Restitution des bijoux réparés — Rio-Gold.

Règles :
- Aucun encaissement pendant la restitution.
- Paiement intégral obligatoire.
- Un seul paiement par réparation.
- Vérification du retrait du compte dépôt.
- Réparation obligatoirement PRET.
- Restitution de tous les bijoux du dossier.
- Confirmation explicite de la remise physique.
- Aucune double restitution.
- Conservation du vendeur historique.
- Aucun lien avec Vente, VenteAutre ou Facture.

Le ticket thermique 80 mm est disponible
uniquement après restitution confirmée.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from compte_depot.models import CompteDepotTransaction
from reparation.models import PaiementReparation, Reparation
from reparation.services.reparation_service import (
    ROLES_RESTITUTION, verifier_permission_reparation)
from sale.services.montant_service import money_strict

# ============================================================
# VÉRIFICATION DU PAIEMENT INTÉGRAL
# ============================================================

def verifier_paiement_integral_reparation(
    *,
    reparation,
):
    """
    Vérifie le paiement complet du dossier.

    À appeler dans transaction.atomic()
    après verrouillage de la réparation.

    Retourne le paiement vérifié.
    """

    try:
        paiement = (
            PaiementReparation.objects
            .select_for_update()
            .select_related(
                "mode_paiement",
                "compte_depot",
                "transaction_depot",
            )
            .get(reparation_id=reparation.pk)
        )

    except PaiementReparation.DoesNotExist as exc:
        raise ValidationError({
            "paiement": (
                "Cette réparation n'est pas encore payée."
            )
        }) from exc

    # --------------------------------------------------------
    # 1. Vérifier le montant du dossier
    # --------------------------------------------------------

    prix = money_strict(
        reparation.prix_convenu,
        "prix_convenu",
    )

    montant = money_strict(
        paiement.montant_paye,
        "montant_paye",
    )

    if prix <= 0 or montant != prix:
        raise ValidationError({
            "paiement": (
                "Le paiement intégral de la réparation "
                "n'est pas confirmé."
            )
        })

    # --------------------------------------------------------
    # 2. Vérifier le mode de paiement
    # --------------------------------------------------------

    mode = paiement.mode_paiement

    est_depot = mode.code == "depot"

    if bool(mode.est_mode_depot) != est_depot:
        raise ValidationError({
            "paiement": (
                "Configuration incohérente "
                "du mode de paiement dépôt."
            )
        })

    # --------------------------------------------------------
    # 3. Paiement par compte dépôt
    # --------------------------------------------------------

    if est_depot:

        if (
            not paiement.compte_depot_id
            or not paiement.transaction_depot_id
        ):
            raise ValidationError({
                "paiement": (
                    "Le retrait du compte dépôt "
                    "n'est pas enregistré."
                )
            })

        compte = paiement.compte_depot
        retrait = paiement.transaction_depot

        # Le compte doit appartenir au client.
        if compte.client_id != reparation.client_id:
            raise ValidationError({
                "paiement": (
                    "Le compte dépôt ne correspond pas "
                    "au client de la réparation."
                )
            })

        # La transaction doit concerner ce compte.
        if retrait.compte_id != compte.pk:
            raise ValidationError({
                "paiement": (
                    "La transaction ne correspond pas "
                    "au compte dépôt."
                )
            })

        # Vérifier le type de transaction.
        if (
            retrait.type_transaction
            != CompteDepotTransaction.TYPE_RETRAIT
        ):
            raise ValidationError({
                "paiement": (
                    "La transaction doit être un retrait."
                )
            })

        # Vérifier que le retrait est terminé.
        if (
            retrait.statut
            != CompteDepotTransaction.STAT_TERMINE
        ):
            raise ValidationError({
                "paiement": (
                    "Le retrait du compte dépôt "
                    "n'est pas terminé."
                )
            })

        # Vérifier le montant retiré.
        montant_retrait = money_strict(
            retrait.montant,
            "montant_retrait",
        )

        if montant_retrait != montant:
            raise ValidationError({
                "paiement": (
                    "Le montant retiré ne correspond pas "
                    "au paiement de la réparation."
                )
            })

        # Vérifier les soldes historiques.
        solde_avant = money_strict(
            retrait.solde_avant,
            "solde_avant",
        )

        solde_apres = money_strict(
            retrait.solde_apres,
            "solde_apres",
        )

        if solde_avant - montant_retrait != solde_apres:
            raise ValidationError({
                "paiement": (
                    "Les soldes historiques du retrait "
                    "sont incohérents."
                )
            })

    # --------------------------------------------------------
    # 4. Autres modes de paiement
    # --------------------------------------------------------

    elif (
        paiement.compte_depot_id
        or paiement.transaction_depot_id
    ):
        raise ValidationError({
            "paiement": (
                "Un compte dépôt ne peut pas être lié "
                "à un autre mode de paiement."
            )
        })

    return paiement


# ============================================================
# RESTITUTION D'UNE RÉPARATION
# ============================================================

@transaction.atomic
def restituer_reparation(
    *,
    reparation_id,
    bijouterie_id,
    user,
    remise_confirmee=False,
):
    """
    Confirme la remise physique de tous les bijoux.

    Autorisations :
    - Admin
    - Manager
    - Caissier

    Aucun paiement n'est effectué ici.
    """

    # --------------------------------------------------------
    # 1. Verrouiller le dossier
    # --------------------------------------------------------

    try:
        reparation = (
            Reparation.objects
            .select_for_update()
            .select_related(
                "bijouterie",
                "client",
            )
            .get(
                pk=reparation_id,
                bijouterie_id=bijouterie_id,
            )
        )

    except Reparation.DoesNotExist as exc:
        raise ValidationError({
            "reparation": (
                "Réparation introuvable "
                "dans cette bijouterie."
            )
        }) from exc

    # --------------------------------------------------------
    # 2. Vérifier les permissions
    # --------------------------------------------------------

    verifier_permission_reparation(
        user=user,
        bijouterie=reparation.bijouterie,
        roles_autorises=ROLES_RESTITUTION,
    )

    # --------------------------------------------------------
    # 3. Vérifier le statut
    # --------------------------------------------------------

    if reparation.statut == Reparation.Statut.RESTITUE:
        raise ValidationError({
            "statut": (
                "Cette réparation a déjà été restituée."
            )
        })

    if reparation.statut != Reparation.Statut.PRET:
        raise ValidationError({
            "statut": (
                "Seule une réparation prête "
                "peut être restituée."
            )
        })

    # --------------------------------------------------------
    # 4. Empêcher une double restitution
    # --------------------------------------------------------

    if (
        reparation.date_restitution is not None
        or reparation.restitue_par_id is not None
    ):
        raise ValidationError({
            "reparation": (
                "Une restitution a déjà été enregistrée."
            )
        })

    # --------------------------------------------------------
    # 5. Vérifier tous les bijoux
    # --------------------------------------------------------

    reparation.verifier_total_bijoux()

    bijoux = list(
        reparation.bijoux
        .select_for_update()
        .order_by("numero_ligne")
    )

    bijoux_incomplets = [
        bijou.numero_ligne
        for bijou in bijoux
        if not bijou.travail_effectue.strip()
    ]

    if bijoux_incomplets:
        raise ValidationError({
            "bijoux": (
                "Le travail effectué est manquant "
                "pour les bijoux suivants : "
                f"{bijoux_incomplets}."
            )
        })

    # --------------------------------------------------------
    # 6. Vérifier le paiement intégral
    # --------------------------------------------------------

    paiement = verifier_paiement_integral_reparation(
        reparation=reparation,
    )

    # --------------------------------------------------------
    # 7. Confirmation physique obligatoire
    # --------------------------------------------------------

    if remise_confirmee is not True:
        raise ValidationError({
            "remise_confirmee": (
                "Confirmez la remise physique "
                "de tous les bijoux au client."
            )
        })

    # --------------------------------------------------------
    # 8. Enregistrer la restitution
    # --------------------------------------------------------

    reparation.statut = Reparation.Statut.RESTITUE

    reparation.date_restitution = timezone.now()

    reparation.restitue_par = user

    reparation.save(
        update_fields=[
            "statut",
            "date_restitution",
            "restitue_par",
        ]
    )

    # --------------------------------------------------------
    # 9. Réponse Angular
    # --------------------------------------------------------

    return {
        "success": True,
        "numero_reparation": (
            reparation.numero_reparation
        ),
        "reparation_uuid": str(reparation.uuid),
        "statut": reparation.statut,
        "nombre_bijoux": len(bijoux),
        "date_restitution": (
            reparation.date_restitution.isoformat()
        ),
        "restitue_par_id": user.pk,
        "paiement_id": paiement.pk,
        "montant_paye": str(paiement.montant_paye),
        "mode_paiement": paiement.mode_paiement.code,
        "paiement_complet": True,
        "remise_confirmee": True,
        "ticket_paiement_disponible": True,
    }


