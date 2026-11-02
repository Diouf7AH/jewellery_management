from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from sale.models import (Facture, ModePaiement, Paiement, PaiementLigne, Vente,
                         VenteAutre, VenteProduit)

ZERO = Decimal("0.00")
TWOPLACES = Decimal("0.01")


@transaction.atomic
def enregistrer_paiement_direct_prestation(
    *,
    vente,
    lignes,
    utilisateur,
):
    """
    Paiement direct d'une vente contenant
    uniquement des prestations.

    Règles :
    - Aucune facture ni proforma.
    - Un seul mode par opération.
    - Paiement partiel ou total.
    - Plusieurs paiements successifs possibles.
    - Vérification du reste à payer.
    - Validation du mode et de la référence.
    - Dépôt client refusé tant que son débit
      transactionnel n'est pas intégré.
    - Aucun mouvement de stock.

    Retourne le Paiement créé.
    """

    # ====================================================
    # 1. VERROUILLAGE DE LA VENTE
    # ====================================================

    vente = (
        Vente.objects
        .select_for_update()
        .filter(pk=vente.pk)
        .first()
    )

    if vente is None:
        raise ValidationError({
            "vente": "Vente introuvable."
        })

    if vente.is_cancelled:
        raise ValidationError({
            "vente": "Cette vente est annulée."
        })

    # ====================================================
    # 2. VÉRIFICATION DU TYPE DE VENTE
    # ====================================================

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
                "Le paiement doit passer "
                "par une facture."
            )
        })

    if Facture.objects.filter(
        vente_id=vente.pk
    ).exists():
        raise ValidationError({
            "vente": (
                "Une facture existe déjà pour "
                "cette vente. Le paiement direct "
                "est interdit."
            )
        })

    # ====================================================
    # 3. UNE SEULE LIGNE DE PAIEMENT
    # ====================================================

    if not isinstance(lignes, (list, tuple)) or len(lignes) != 1:
        raise ValidationError({
            "lignes": (
                "Le paiement d'une prestation "
                "doit contenir exactement "
                "un seul mode de paiement."
            )
        })

    ligne = lignes[0]

    try:
        mode_id = int(
            ligne["mode_paiement_id"]
        )

        montant = Decimal(
            str(ligne["montant_paye"])
        )

        if not montant.is_finite():
            raise ValueError("Montant non fini.")

        if montant != montant.quantize(TWOPLACES):
            raise ValueError(
                "Le montant doit avoir "
                "au maximum deux décimales."
            )

        montant = montant.quantize(TWOPLACES)

    except (
        KeyError,
        TypeError,
        ValueError,
        InvalidOperation,
    ):
        raise ValidationError({
            "lignes": (
                "Données de paiement invalides."
            )
        })

    if mode_id <= 0:
        raise ValidationError({
            "mode_paiement": (
                "Identifiant du mode invalide."
            )
        })

    if montant <= ZERO:
        raise ValidationError({
            "montant_paye": (
                "Le montant doit être "
                "strictement positif."
            )
        })

    reference = (
        ligne.get("reference") or ""
    ).strip()

    numero_compte_depot = (
        ligne.get("numero_compte_depot") or ""
    ).strip()

    # ====================================================
    # 4. VÉRIFICATION DU MONTANT DE LA PRESTATION
    # ====================================================

    montant_total = (
        vente.montant_total or ZERO
    )

    if montant_total <= ZERO:
        raise ValidationError({
            "vente": (
                "Le montant total de la prestation "
                "doit être supérieur à zéro."
            )
        })

    # ====================================================
    # 5. CALCUL DU TOTAL DÉJÀ PAYÉ
    # ====================================================

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

    reste_avant = montant_total - total_deja_paye

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

    # ====================================================
    # 6. RÉCUPÉRATION DU MODE DE PAIEMENT
    # ====================================================

    mode = ModePaiement.objects.filter(
        pk=mode_id,
        active=True,
    ).first()

    if mode is None:
        raise ValidationError({
            "mode_paiement": (
                "Mode de paiement introuvable "
                "ou désactivé."
            )
        })

    # ====================================================
    # 7. VALIDATION DE LA RÉFÉRENCE
    # ====================================================

    if mode.necessite_reference and not reference:
        raise ValidationError({
            "reference": (
                f"Une référence est obligatoire "
                f"pour le mode '{mode.nom}'."
            )
        })

    # ====================================================
    # 8. VALIDATION DU COMPTE DÉPÔT
    # ====================================================

    if mode.est_mode_depot:

        if not numero_compte_depot:
            raise ValidationError({
                "numero_compte_depot": (
                    "Le numéro de compte dépôt "
                    "est obligatoire."
                )
            })

        # Sécurité :
        # Ne jamais enregistrer un paiement par dépôt
        # sans débiter réellement le compte client.
        #
        # Il reste à raccorder ici le service de débit
        # existant, avec :
        # - recherche du compte par numéro
        # - vérification du propriétaire
        # - verrouillage du compte
        # - contrôle du solde
        # - création du retrait
        # - récupération de la transaction

        raise ValidationError({
            "numero_compte_depot": (
                "Le paiement par dépôt client "
                "n'est pas encore raccordé "
                "au service de débit du compte."
            )
        })

    if numero_compte_depot:
        raise ValidationError({
            "numero_compte_depot": (
                "Ce champ est réservé au "
                "paiement par dépôt client."
            )
        })

    # ====================================================
    # 9. CRÉATION DU PAIEMENT
    # ====================================================

    try:
        paiement = Paiement.objects.create(
            vente=vente,
            facture=None,
            created_by=utilisateur,
        )

    except DjangoValidationError as exc:
        raise ValidationError(
            getattr(exc, "message_dict", None)
            or exc.messages
        )

    # ====================================================
    # 10. CRÉATION DE L'UNIQUE LIGNE
    # ====================================================

    objet_ligne = PaiementLigne(
        paiement=paiement,
        mode_paiement=mode,
        montant_paye=montant,
        reference=reference,
        compte_depot=None,
        transaction_depot=None,
    )

    try:
        # save() déclenche les validations
        # définies dans le modèle.
        objet_ligne.save()

    except DjangoValidationError as exc:
        raise ValidationError(
            getattr(exc, "message_dict", None)
            or exc.messages
        )

    # ====================================================
    # 11. RETOUR
    # ====================================================

    return paiement

