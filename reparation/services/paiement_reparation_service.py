# reparation/services/paiement_reparation_service.py

"""
Encaissement des réparations Rio-Gold.

Règles :
- Aucun lien avec Vente, VenteAutre ou Facture.
- Paiement intégral uniquement.
- Exactement un mode de paiement.
- Réparation obligatoirement PRET.
- Total des bijoux vérifié avant encaissement.
- Aucun double paiement.
- Compte dépôt débité atomiquement.
- Rejeu idempotent par le même utilisateur.
- Restitution effectuée séparément.
"""

from __future__ import annotations

import hashlib
import json
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction

from compte_depot.models import CompteDepot
from compte_depot.services.depot_retrait_services import effectuer_retrait
from reparation.models import PaiementReparation, Reparation
from sale.models import ModePaiement
from sale.services.montant_service import money_strict
from sale.services.permissions_service import verifier_permission_encaissement

# ============================================================
# OUTILS DE VALIDATION
# ============================================================

def _texte(value, field):
    """Normalise une valeur textuelle."""

    if value is None:
        return ""

    if not isinstance(value, str):
        raise ValidationError({
            field: "Une chaîne de caractères est attendue."
        })

    return value.strip()


def _cle_uuid(value):
    """Valide et normalise la clé d'idempotence."""

    try:
        return uuid.UUID(str(value))

    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({
            "idempotency_key": (
                "Une clé UUID valide est obligatoire."
            )
        }) from exc


# ============================================================
# PRÉPARATION DE LA LIGNE DE PAIEMENT
# ============================================================

def _preparer_ligne(lignes_data):
    """
    Accepte exactement une ligne de paiement.

    Exemple :
    {
        "mode_paiement": "cash",
        "montant_paye": "25000.00",
        "reference": ""
    }
    """

    if (
        not isinstance(lignes_data, list)
        or len(lignes_data) != 1
        or not isinstance(lignes_data[0], dict)
    ):
        raise ValidationError({
            "lignes": (
                "Le paiement doit contenir exactement "
                "une seule ligne."
            )
        })

    ligne = lignes_data[0]

    code = _texte(
        ligne.get("mode_paiement", ligne.get("mode")),
        "mode_paiement",
    ).lower()

    if not code:
        raise ValidationError({
            "mode_paiement": "Mode de paiement obligatoire."
        })

    try:
        mode = ModePaiement.objects.get(
            code=code,
            active=True,
        )

    except ModePaiement.DoesNotExist as exc:
        raise ValidationError({
            "mode_paiement": (
                "Mode de paiement introuvable ou inactif."
            )
        }) from exc

    montant = money_strict(
        ligne.get("montant_paye", ligne.get("montant")),
        "montant_paye",
    )

    if montant <= 0:
        raise ValidationError({
            "montant_paye": (
                "Le montant doit être supérieur à zéro."
            )
        })

    reference = _texte(
        ligne.get("reference"),
        "reference",
    )

    provider_reference = _texte(
        ligne.get("provider_reference"),
        "provider_reference",
    )

    numero_compte = _texte(
        ligne.get(
            "numero_compte_depot",
            ligne.get("numero_compte"),
        ),
        "numero_compte_depot",
    )

    est_depot = mode.code == "depot"

    if bool(mode.est_mode_depot) != est_depot:
        raise ValidationError({
            "mode_paiement": (
                "Configuration incohérente du mode dépôt."
            )
        })

    # Une référence fournisseur peut être utilisée
    # comme référence principale.
    reference_finale = reference or provider_reference

    if (
        mode.necessite_reference
        and not reference_finale
    ):
        raise ValidationError({
            "reference": (
                "Une référence de paiement est obligatoire."
            )
        })

    if len(reference_finale) > 150:
        raise ValidationError({
            "reference": (
                "La référence ne doit pas dépasser "
                "150 caractères."
            )
        })

    if est_depot and not numero_compte:
        raise ValidationError({
            "numero_compte_depot": (
                "Le numéro de compte dépôt est obligatoire."
            )
        })

    if not est_depot and numero_compte:
        raise ValidationError({
            "numero_compte_depot": (
                "Le compte dépôt est réservé "
                "au mode de paiement dépôt."
            )
        })

    return {
        "mode": mode,
        "montant": montant,
        "reference": reference_finale,
        "numero_compte": numero_compte,
    }


# ============================================================
# EMPREINTE SHA256
# ============================================================

def _empreinte(
    *,
    reparation,
    mode,
    montant,
    reference,
    numero_compte,
):
    """
    Empreinte de la demande normalisée.

    Une même clé ne peut pas être utilisée
    pour une opération différente.
    """

    donnees = {
        "operation": "paiement_reparation",
        "reparation_id": reparation.pk,
        "bijouterie_id": reparation.bijouterie_id,
        "mode_paiement": mode.code,
        "montant": str(montant),
        "reference": reference,
        "numero_compte": numero_compte,
    }

    contenu = json.dumps(
        donnees,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        contenu.encode("utf-8")
    ).hexdigest()


# ============================================================
# PAIEMENT D'UNE RÉPARATION
# ============================================================

@transaction.atomic
def payer_reparation(
    *,
    reparation_id,
    bijouterie_id,
    user,
    lignes_data,
    idempotency_key,
):
    """
    Encaisse intégralement une réparation.

    Retourne un dictionnaire JSON-compatible.

    Une demande identique avec la même clé
    et le même utilisateur retourne
    la réponse initiale.

    Aucun ticket final n'est généré ici.
    """

    # --------------------------------------------------------
    # 1. Valider la clé d'idempotence
    # --------------------------------------------------------

    cle = _cle_uuid(idempotency_key)

    # --------------------------------------------------------
    # 2. Verrouiller le dossier
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
    # 3. Vérifier les permissions
    # --------------------------------------------------------

    verifier_permission_encaissement(
        user,
        reparation.bijouterie_id,
    )

    # --------------------------------------------------------
    # 4. Préparer le paiement
    # --------------------------------------------------------

    paiement_data = _preparer_ligne(lignes_data)

    mode = paiement_data["mode"]
    montant = paiement_data["montant"]
    reference = paiement_data["reference"]
    numero_compte = paiement_data["numero_compte"]

    # --------------------------------------------------------
    # 5. Vérifier le montant du dossier
    # --------------------------------------------------------

    prix = money_strict(
        reparation.prix_convenu,
        "prix_convenu",
    )

    if montant != prix:
        raise ValidationError({
            "montant_paye": (
                "Le paiement doit couvrir exactement "
                "le montant total de la réparation."
            )
        })

    # --------------------------------------------------------
    # 6. Calculer l'empreinte
    # --------------------------------------------------------

    empreinte = _empreinte(
        reparation=reparation,
        mode=mode,
        montant=montant,
        reference=reference,
        numero_compte=numero_compte,
    )

    # --------------------------------------------------------
    # 7. Vérifier l'idempotence
    # --------------------------------------------------------

    precedent = (
        PaiementReparation.objects
        .filter(idempotency_key=cle)
        .first()
    )

    if precedent is not None:

        if (
            precedent.reparation_id != reparation.pk
            or precedent.created_by_id != user.pk
            or precedent.request_fingerprint != empreinte
        ):
            raise ValidationError({
                "idempotency_key": (
                    "Cette clé a déjà été utilisée "
                    "pour une autre demande."
                )
            })

        if precedent.response_snapshot is None:
            raise ValidationError({
                "idempotency_key": (
                    "Le résultat initial du paiement "
                    "est indisponible."
                )
            })

        return dict(precedent.response_snapshot)

    # --------------------------------------------------------
    # 8. Empêcher un deuxième paiement
    # --------------------------------------------------------

    if PaiementReparation.objects.filter(
        reparation_id=reparation.pk
    ).exists():
        raise ValidationError({
            "paiement": (
                "Cette réparation est déjà payée."
            )
        })

    # --------------------------------------------------------
    # 9. Vérifier le statut
    # --------------------------------------------------------

    if reparation.statut != Reparation.Statut.PRET:
        raise ValidationError({
            "statut": (
                "La réparation doit être prête "
                "avant le paiement."
            )
        })

    # --------------------------------------------------------
    # 10. Vérifier tous les bijoux
    # --------------------------------------------------------

    reparation.verifier_total_bijoux()

    # --------------------------------------------------------
    # 11. Paiement par compte dépôt
    # --------------------------------------------------------

    compte = None
    retrait = None

    if mode.code == "depot":

        try:
            compte = (
                CompteDepot.objects
                .select_for_update()
                .select_related("client")
                .get(numero_compte=numero_compte)
            )

        except CompteDepot.DoesNotExist as exc:
            raise ValidationError({
                "numero_compte_depot": (
                    "Compte dépôt introuvable."
                )
            }) from exc

        # Le compte doit appartenir au client.
        if compte.client_id != reparation.client_id:
            raise ValidationError({
                "numero_compte_depot": (
                    "Ce compte dépôt n'appartient pas "
                    "au client de la réparation."
                )
            })

        # Contrôle de la bijouterie propriétaire.
        if (
            compte.client.bijouterie_id
            != reparation.bijouterie_id
        ):
            raise ValidationError({
                "numero_compte_depot": (
                    "Ce compte dépôt appartient "
                    "à une autre bijouterie."
                )
            })

        # Vérification préalable du solde.
        solde = money_strict(
            compte.solde,
            "solde",
        )

        if solde < montant:
            raise ValidationError({
                "numero_compte_depot": (
                    "Solde insuffisant."
                )
            })

        # Retrait atomique dans la même transaction.
        retrait = effectuer_retrait(
            compte_id=compte.pk,
            montant=montant,
            user=user,
            reference=(
                f"REPARATION-{reparation.numero_reparation}"
            ),
            commentaire=(
                f"Paiement réparation "
                f"{reparation.numero_reparation}"
            ),
        )

    # --------------------------------------------------------
    # 12. Référence finale
    # --------------------------------------------------------

    reference_finale = reference

    if compte is not None and not reference_finale:
        reference_finale = (
            f"COMPTE_DEPOT-{numero_compte}"
        )

    if len(reference_finale) > 150:
        raise ValidationError({
            "reference": (
                "La référence ne doit pas dépasser "
                "150 caractères."
            )
        })

    # --------------------------------------------------------
    # 13. Enregistrer le paiement
    # --------------------------------------------------------

    paiement = PaiementReparation(
        reparation=reparation,
        mode_paiement=mode,
        montant_paye=montant,
        compte_depot=compte,
        transaction_depot=retrait,
        reference=reference_finale,
        idempotency_key=cle,
        request_fingerprint=empreinte,
        created_by=user,
    )

    paiement.save()

    # --------------------------------------------------------
    # 14. Préparer la réponse
    # --------------------------------------------------------

    resultat = {
        "success": True,
        "paiement_id": paiement.pk,
        "numero_reparation": (
            reparation.numero_reparation
        ),
        "reparation_uuid": str(reparation.uuid),
        "montant_paiement": str(montant),
        "mode_paiement": mode.code,
        "paiement_complet": True,
        "reste_a_payer": "0.00",
        "statut_reparation": reparation.statut,
        "restitution_effectuee": False,
        "transaction_depot_id": (
            retrait.pk if retrait is not None else None
        ),
    }

    # --------------------------------------------------------
    # 15. Sauvegarder la réponse idempotente
    # --------------------------------------------------------

    paiement.response_snapshot = resultat

    paiement.save(
        update_fields=["response_snapshot"]
    )

    return dict(resultat)


