# sale/services/paiement_direct_prestation_service.py

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from compte_depot.models import CompteDepot
from compte_depot.services.depot_retrait_services import effectuer_retrait
from sale.models import (Facture, ModePaiement, Paiement, PaiementLigne, Vente,
                         VenteAutre, VenteProduit)
from sale.services.montant_service import ZERO, money
from sale.services.permissions_service import verifier_permission_encaissement

# ============================================================
# 1. HELPERS
# ============================================================

def _convertir_erreur_django(exc):
    """
    Convertit une ValidationError Django
    en ValidationError DRF.
    """

    return ValidationError(
        getattr(exc, "message_dict", None)
        or exc.messages
    )


def _valider_mode_id(value):
    """
    Valide un identifiant entier positif.
    """

    if isinstance(value, bool):
        raise ValidationError({
            "mode_paiement_id": "Identifiant invalide."
        })

    if isinstance(value, int):
        mode_id = value

    elif (
        isinstance(value, str)
        and value.strip().isascii()
        and value.strip().isdecimal()
    ):
        mode_id = int(value.strip())

    else:
        raise ValidationError({
            "mode_paiement_id": "Identifiant invalide."
        })

    if mode_id <= 0:
        raise ValidationError({
            "mode_paiement_id": (
                "L'identifiant doit être supérieur à zéro."
            )
        })

    return mode_id


def _texte_optionnel(value, field):
    """
    Normalise une chaîne facultative.
    """

    if value is None:
        return ""

    if not isinstance(value, str):
        raise ValidationError({
            field: (
                "Une chaîne de caractères est attendue."
            )
        })

    return value.strip()


def _montant_strict(value, field):
    """
    Convertit un montant en Decimal.

    Refuse une valeur absente ou vide.
    """

    if value is None or value == "":
        raise ValidationError({
            field: "Montant obligatoire."
        })

    try:
        montant = money(
            value,
            field=field,
        )
    except DjangoValidationError as exc:
        raise _convertir_erreur_django(exc) from exc

    return montant


# ============================================================
# 2. SERVICE PRINCIPAL
# ============================================================

@transaction.atomic
def enregistrer_paiement_direct_prestation(
    *,
    vente,
    lignes,
    utilisateur,
):
    """
    Enregistre un paiement direct d'une vente
    contenant uniquement des prestations.

    Règles :
        - aucune facture ;
        - aucune proforma ;
        - exactement une ligne de paiement ;
        - paiements partiels autorisés ;
        - paiements successifs autorisés ;
        - aucun dépassement du solde ;
        - débit atomique du compte dépôt ;
        - aucun mouvement de stock.

    Retour :
        instance Paiement.

    Important :
        l'encaissement externe éventuel
        doit être confirmé avant cet appel.
    """

    # ========================================================
    # 1. VALIDATION DE LA VENTE
    # ========================================================

    if (
        vente is None
        or getattr(vente, "pk", None) is None
    ):
        raise ValidationError({
            "vente": (
                "Une vente enregistrée est obligatoire."
            )
        })

    # ========================================================
    # 2. VALIDATION DE L'UTILISATEUR
    # ========================================================

    if (
        utilisateur is None
        or not getattr(
            utilisateur,
            "is_authenticated",
            False,
        )
        or not getattr(
            utilisateur,
            "is_active",
            False,
        )
    ):
        raise ValidationError({
            "utilisateur": (
                "Un utilisateur actif et authentifié "
                "est obligatoire."
            )
        })

    # ========================================================
    # 3. UNE SEULE LIGNE
    # ========================================================

    if (
        not isinstance(lignes, (list, tuple))
        or len(lignes) != 1
    ):
        raise ValidationError({
            "lignes": (
                "Le paiement d'une prestation doit "
                "contenir exactement une ligne."
            )
        })

    ligne = lignes[0]

    if not isinstance(ligne, dict):
        raise ValidationError({
            "lignes": (
                "Format de paiement invalide."
            )
        })

    if "mode_paiement_id" not in ligne:
        raise ValidationError({
            "mode_paiement_id": (
                "Ce champ est obligatoire."
            )
        })

    if "montant_paye" not in ligne:
        raise ValidationError({
            "montant_paye": (
                "Ce champ est obligatoire."
            )
        })

    # ========================================================
    # 4. VALIDATION DES CHAMPS
    # ========================================================

    mode_id = _valider_mode_id(
        ligne["mode_paiement_id"]
    )

    montant = _montant_strict(
        ligne["montant_paye"],
        "montant_paye",
    )

    if montant <= ZERO:
        raise ValidationError({
            "montant_paye": (
                "Le montant doit être strictement positif."
            )
        })

    reference = _texte_optionnel(
        ligne.get("reference"),
        "reference",
    )

    numero_compte_depot = _texte_optionnel(
        ligne.get("numero_compte_depot"),
        "numero_compte_depot",
    )

    # ========================================================
    # 5. VERROUILLAGE DE LA VENTE
    # ========================================================

    vente = (
        Vente.objects
        .select_for_update()
        .select_related("bijouterie")
        .filter(pk=vente.pk)
        .first()
    )

    if vente is None:
        raise ValidationError({
            "vente": "Vente introuvable."
        })

    if vente.is_cancelled:
        raise ValidationError({
            "vente": (
                "Cette vente est annulée."
            )
        })

    # ========================================================
    # 6. PERMISSIONS D'ENCAISSEMENT
    # ========================================================

    cashier = verifier_permission_encaissement(
        utilisateur,
        vente.bijouterie_id,
    )

    # ========================================================
    # 7. VENTE PRESTATIONS UNIQUEMENT
    # ========================================================

    if not VenteAutre.objects.filter(
        vente_id=vente.pk
    ).exists():
        raise ValidationError({
            "vente": (
                "Cette vente ne contient "
                "aucune prestation."
            )
        })

    if VenteProduit.objects.filter(
        vente_id=vente.pk
    ).exists():
        raise ValidationError({
            "vente": (
                "Cette vente contient des bijoux. "
                "Utilisez le paiement par facture."
            )
        })

    if Facture.objects.filter(
        vente_id=vente.pk
    ).exists():
        raise ValidationError({
            "vente": (
                "Une facture existe pour cette vente. "
                "Paiement direct interdit."
            )
        })

    # ========================================================
    # 8. MONTANT TOTAL
    # ========================================================

    montant_total = _montant_strict(
        vente.montant_total,
        "montant_total",
    )

    if montant_total <= ZERO:
        raise ValidationError({
            "montant_total": (
                "Le montant total doit être "
                "strictement positif."
            )
        })

    # ========================================================
    # 9. PAIEMENTS EXISTANTS
    # ========================================================

    total_deja_paye = (
        PaiementLigne.objects
        .filter(
            paiement__vente_id=vente.pk,
            paiement__facture__isnull=True,
        )
        .aggregate(
            total=Sum("montant_paye")
        )["total"]
        or ZERO
    )

    total_deja_paye = _montant_strict(
        total_deja_paye,
        "total_deja_paye",
    )

    reste_avant = _montant_strict(
        montant_total - total_deja_paye,
        "reste_a_payer",
    )

    if reste_avant <= ZERO:
        raise ValidationError({
            "vente": (
                "Cette prestation est déjà "
                "entièrement payée."
            )
        })

    if montant > reste_avant:
        raise ValidationError({
            "montant_paye": (
                f"Montant demandé : {montant:.2f} FCFA. "
                f"Reste à payer : {reste_avant:.2f} FCFA."
            )
        })

    # ========================================================
    # 10. MODE DE PAIEMENT
    # ========================================================

    mode = (
        ModePaiement.objects
        .filter(
            pk=mode_id,
            active=True,
        )
        .first()
    )

    if mode is None:
        raise ValidationError({
            "mode_paiement": (
                "Mode de paiement introuvable "
                "ou désactivé."
            )
        })

    if mode.necessite_reference and not reference:
        raise ValidationError({
            "reference": (
                f"Une référence est obligatoire "
                f"pour le mode '{mode.nom}'."
            )
        })

    # ========================================================
    # 11. COMPTE DÉPÔT
    # ========================================================

    compte = None

    if mode.est_mode_depot:

        if not numero_compte_depot:
            raise ValidationError({
                "numero_compte_depot": (
                    "Le numéro de compte dépôt "
                    "est obligatoire."
                )
            })

        if not vente.client_id:
            raise ValidationError({
                "client": (
                    "Un client doit être identifié "
                    "avant de payer par compte dépôt."
                )
            })

        compte = (
            CompteDepot.objects
            .select_for_update()
            .select_related("client")
            .filter(
                numero_compte=numero_compte_depot
            )
            .first()
        )

        if compte is None:
            raise ValidationError({
                "numero_compte_depot": (
                    "Compte dépôt introuvable."
                )
            })

        if compte.client_id != vente.client_id:
            raise ValidationError({
                "numero_compte_depot": (
                    "Ce compte dépôt n'appartient pas "
                    "au client de la vente."
                )
            })

        if (
            compte.client.bijouterie_id
            != vente.bijouterie_id
        ):
            raise ValidationError({
                "numero_compte_depot": (
                    "Ce compte dépôt appartient "
                    "à une autre bijouterie."
                )
            })

        solde_disponible = _montant_strict(
            compte.solde,
            "solde",
        )

        if solde_disponible < montant:
            raise ValidationError({
                "compte_depot": (
                    "Solde insuffisant. "
                    f"Disponible : {solde_disponible:.2f} FCFA. "
                    f"Demandé : {montant:.2f} FCFA."
                )
            })

    elif numero_compte_depot:
        raise ValidationError({
            "numero_compte_depot": (
                "Ce champ est réservé "
                "au paiement par compte dépôt."
            )
        })

    # ========================================================
    # 12. CRÉATION DU PAIEMENT
    # ========================================================

    try:
        paiement = Paiement(
            vente=vente,
            facture=None,
            created_by=utilisateur,
            cashier=cashier,
        )

        paiement.full_clean()
        paiement.save()

    except DjangoValidationError as exc:
        raise _convertir_erreur_django(exc) from exc

    # ========================================================
    # 13. DÉBIT DU COMPTE DÉPÔT
    # ========================================================

    transaction_depot = None

    if compte is not None:
        try:
            transaction_depot = effectuer_retrait(
                compte_id=compte.pk,
                montant=montant,
                user=utilisateur,
                reference=(
                    f"PAIEMENT-PREST-{paiement.pk}"
                ),
                commentaire=(
                    "Paiement direct prestation "
                    f"{vente.numero_vente}"
                ),
            )

        except DjangoValidationError as exc:
            raise _convertir_erreur_django(exc) from exc

    # ========================================================
    # 14. CRÉATION DE LA LIGNE
    # ========================================================

    try:
        objet_ligne = PaiementLigne(
            paiement=paiement,
            mode_paiement=mode,
            montant_paye=montant,
            reference=(
                f"COMPTE_DEPOT-{compte.numero_compte}"
                if compte is not None
                else reference
            ),
            compte_depot=compte,
            transaction_depot=transaction_depot,
        )

        objet_ligne.full_clean()
        objet_ligne.save()

    except DjangoValidationError as exc:
        raise _convertir_erreur_django(exc) from exc

    # ========================================================
    # 15. VÉRIFICATION DU SOLDE APRÈS PAIEMENT
    # ========================================================

    total_apres = (
        PaiementLigne.objects
        .filter(
            paiement__vente_id=vente.pk,
            paiement__facture__isnull=True,
        )
        .aggregate(
            total=Sum("montant_paye")
        )["total"]
        or ZERO
    )

    total_apres = _montant_strict(
        total_apres,
        "total_apres",
    )

    if total_apres != total_deja_paye + montant:
        raise ValidationError({
            "paiement": (
                "Incohérence du montant encaissé."
            )
        })

    if total_apres > montant_total:
        raise ValidationError({
            "paiement": (
                "Le total encaissé dépasse "
                "le montant de la prestation."
            )
        })

    # ========================================================
    # 16. RETOUR
    # ========================================================

    return paiement

