# reparation/services/reparation_service.py

"""
Services métier des réparations Rio-Gold.

- Création d'un dossier avec un ou plusieurs bijoux
- Numérotation quotidienne par bijouterie
- Vérification des autorisations
- Vérification client / bijouterie
- Vérification du vendeur
- Calcul du montant total
- Suivi des travaux de chaque bijou
- Changement de statut

Le paiement et la restitution sont gérés séparément.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from backend.bijouteries import user_has_bijouterie_access
from backend.roles import (ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER, ROLE_VENDOR,
                           get_role_name)
from reparation.models import (PaiementReparation, Reparation, ReparationBijou,
                               ReparationCounter)
from sale.models import Client, ClientBijouterie
from sale.services.montant_service import money_strict
from store.models import Bijouterie
from vendor.models import Vendor

# ============================================================
# RÔLES AUTORISÉS
# ============================================================

ROLES_SUIVI = {
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_VENDOR,
}

ROLES_PAIEMENT = {
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_CASHIER,
}

ROLES_RESTITUTION = ROLES_PAIEMENT


# ============================================================
# AUTORISATIONS
# ============================================================

def verifier_permission_reparation(
    *,
    user,
    bijouterie,
    roles_autorises,
):
    """
    Vérifie :
    - authentification ;
    - activation du compte ;
    - rôle ;
    - accès à la bijouterie.
    """

    if (
        user is None
        or not user.is_authenticated
        or not user.is_active
    ):
        raise ValidationError({
            "permission": "Authentification obligatoire."
        })

    if bijouterie is None or bijouterie.pk is None:
        raise ValidationError({
            "bijouterie": "Bijouterie obligatoire."
        })

    role = get_role_name(user)

    if role not in roles_autorises:
        raise ValidationError({
            "permission": (
                "Votre rôle ne permet pas cette opération."
            )
        })

    if not user_has_bijouterie_access(
        user,
        bijouterie.pk,
    ):
        raise ValidationError({
            "permission": (
                "Accès à cette bijouterie interdit."
            )
        })


# ============================================================
# ASSOCIATION CLIENT / BIJOUTERIE
# ============================================================

def _verifier_association_client(
    *,
    client,
    bijouterie,
):
    """
    Le client doit être associé à la bijouterie
    après vérification de son identité.
    """

    if (
        client is None
        or client.pk is None
        or bijouterie is None
        or bijouterie.pk is None
    ):
        raise ValidationError({
            "client": "Client ou bijouterie invalide."
        })

    existe = ClientBijouterie.objects.filter(
        client_id=client.pk,
        bijouterie_id=bijouterie.pk,
    ).exists()

    if not existe:
        raise ValidationError({
            "client": (
                "Client non associé à cette bijouterie. "
                "Vérifiez son identité avant l'association."
            )
        })


# ============================================================
# VALIDATION DES BIJOUX
# ============================================================

def _preparer_bijoux(bijoux_data):
    """
    Valide les bijoux et calcule leur montant total.

    Le total est toujours recalculé côté serveur.
    """

    if not isinstance(bijoux_data, (list, tuple)):
        raise ValidationError({
            "bijoux": "Une liste de bijoux est obligatoire."
        })

    if not bijoux_data:
        raise ValidationError({
            "bijoux": "Ajoutez au moins un bijou."
        })

    bijoux_prepares = []
    montant_total = Decimal("0.00")

    champs_obligatoires = (
        "type_bijou",
        "description_bijou",
        "etat_reception",
        "travail_demande",
    )

    for numero_ligne, donnees in enumerate(
        bijoux_data,
        start=1,
    ):
        if not isinstance(donnees, dict):
            raise ValidationError({
                "bijoux": (
                    f"Bijou {numero_ligne} : "
                    "les données sont invalides."
                )
            })

        valeurs = {}

        for champ in champs_obligatoires:
            valeur = donnees.get(champ)

            if (
                not isinstance(valeur, str)
                or not valeur.strip()
            ):
                raise ValidationError({
                    "bijoux": (
                        f"Bijou {numero_ligne} : "
                        f"le champ {champ} est obligatoire."
                    )
                })

            valeurs[champ] = valeur.strip()

        if len(valeurs["type_bijou"]) > 100:
            raise ValidationError({
                "bijoux": (
                    f"Bijou {numero_ligne} : "
                    "type_bijou dépasse 100 caractères."
                )
            })

        purete = donnees.get("purete") or ""

        if not isinstance(purete, str):
            raise ValidationError({
                "bijoux": (
                    f"Bijou {numero_ligne} : "
                    "purete doit être une chaîne."
                )
            })

        purete = purete.strip()

        if len(purete) > 30:
            raise ValidationError({
                "bijoux": (
                    f"Bijou {numero_ligne} : "
                    "purete dépasse 30 caractères."
                )
            })

        poids = donnees.get("poids")

        if poids in (None, ""):
            poids = None
        else:
            try:
                poids = Decimal(str(poids))
            except (ValueError, TypeError, ArithmeticError):
                raise ValidationError({
                    "bijoux": (
                        f"Bijou {numero_ligne} : "
                        "poids invalide."
                    )
                })

            if not poids.is_finite() or poids <= 0:
                raise ValidationError({
                    "bijoux": (
                        f"Bijou {numero_ligne} : "
                        "le poids doit être positif."
                    )
                })

            if (
                poids.as_tuple().exponent < -3
                or poids >= Decimal("1000000000")
            ):
                raise ValidationError({
                    "bijoux": (
                        f"Bijou {numero_ligne} : "
                        "poids hors format autorisé."
                    )
                })

        prix = money_strict(
            donnees.get("prix_reparation"),
            field=f"bijoux[{numero_ligne}].prix_reparation",
        )

        if prix <= 0:
            raise ValidationError({
                "bijoux": (
                    f"Bijou {numero_ligne} : "
                    "le prix doit être positif."
                )
            })

        if prix >= Decimal("1000000000000"):
            raise ValidationError({
                "bijoux": (
                    f"Bijou {numero_ligne} : "
                    "prix hors format autorisé."
                )
            })

        montant_total += prix

        bijoux_prepares.append({
            "numero_ligne": numero_ligne,
            "type_bijou": valeurs["type_bijou"],
            "description_bijou": valeurs[
                "description_bijou"
            ],
            "poids": poids,
            "purete": purete,
            "etat_reception": valeurs["etat_reception"],
            "travail_demande": valeurs["travail_demande"],
            "travail_effectue": "",
            "prix_reparation": prix,
        })

    if montant_total <= 0:
        raise ValidationError({
            "bijoux": "Le montant total doit être positif."
        })

    if montant_total >= Decimal("1000000000000"):
        raise ValidationError({
            "bijoux": (
                "Le montant total dépasse "
                "la capacité du champ prix_convenu."
            )
        })

    return bijoux_prepares, montant_total


# ============================================================
# CRÉATION D'UNE RÉPARATION
# ============================================================

@transaction.atomic
def creer_reparation(
    *,
    bijouterie_id,
    client_id,
    vendeur_id,
    bijoux_data,
    date_prevue=None,
    user=None,
):
    """
    Crée un dossier et tous ses bijoux.

    Le montant est calculé à partir des bijoux.

    Toutes les opérations sont atomiques.
    """

    # --------------------------------------------------------
    # 1. Bijouterie
    # --------------------------------------------------------

    try:
        bijouterie = Bijouterie.objects.get(
            pk=bijouterie_id
        )
    except Bijouterie.DoesNotExist:
        raise ValidationError({
            "bijouterie_id": "Bijouterie introuvable."
        })

    # --------------------------------------------------------
    # 2. Permissions
    # --------------------------------------------------------

    verifier_permission_reparation(
        user=user,
        bijouterie=bijouterie,
        roles_autorises=ROLES_SUIVI,
    )

    # --------------------------------------------------------
    # 3. Client
    # --------------------------------------------------------

    try:
        client = Client.objects.get(pk=client_id)
    except Client.DoesNotExist:
        raise ValidationError({
            "client_id": "Client introuvable."
        })

    _verifier_association_client(
        client=client,
        bijouterie=bijouterie,
    )

    # --------------------------------------------------------
    # 4. Vendeur
    # --------------------------------------------------------

    try:
        vendeur = (
            Vendor.objects
            .select_related("user")
            .get(pk=vendeur_id)
        )
    except Vendor.DoesNotExist:
        raise ValidationError({
            "vendeur_id": "Vendeur introuvable."
        })

    if vendeur.bijouterie_id != bijouterie.pk:
        raise ValidationError({
            "vendeur_id": (
                "Le vendeur n'appartient pas "
                "à cette bijouterie."
            )
        })

    if not vendeur.verifie or not vendeur.user.is_active:
        raise ValidationError({
            "vendeur_id": (
                "Vendeur désactivé ou non vérifié."
            )
        })

    # --------------------------------------------------------
    # 5. Préparer les bijoux
    # --------------------------------------------------------

    bijoux_prepares, montant_total = _preparer_bijoux(
        bijoux_data
    )

    # --------------------------------------------------------
    # 6. Numérotation atomique
    # --------------------------------------------------------

    Bijouterie.objects.select_for_update().get(
        pk=bijouterie.pk
    )

    jour = timezone.localdate()

    compteur, _ = ReparationCounter.objects.get_or_create(
        bijouterie=bijouterie,
        jour=jour,
        defaults={"derniere_valeur": 0},
    )

    compteur = (
        ReparationCounter.objects
        .select_for_update()
        .get(pk=compteur.pk)
    )

    compteur.derniere_valeur += 1

    compteur.save(
        update_fields=["derniere_valeur"]
    )

    numero = (
        f"REP-{jour:%Y%m%d}-"
        f"{compteur.derniere_valeur:04d}-"
        f"{bijouterie.pk}"
    )

    # --------------------------------------------------------
    # 7. Créer le dossier
    # --------------------------------------------------------

    reparation = Reparation(
        numero_reparation=numero,
        bijouterie=bijouterie,
        client=client,
        vendeur=vendeur,
        prix_convenu=montant_total,
        date_prevue=date_prevue,
        statut=Reparation.Statut.EN_ATTENTE,
    )

    reparation.save()

    # --------------------------------------------------------
    # 8. Créer chaque bijou
    # --------------------------------------------------------

    for donnees in bijoux_prepares:
        bijou = ReparationBijou(
            reparation=reparation,
            **donnees,
        )

        # save() appelle full_clean() dans le modèle.
        bijou.save()

    # --------------------------------------------------------
    # 9. Vérifier le montant total
    # --------------------------------------------------------

    reparation.verifier_total_bijoux()

    return reparation


# ============================================================
# TRANSITIONS AUTORISÉES
# ============================================================

TRANSITIONS_REPARATION = {
    Reparation.Statut.EN_ATTENTE: {
        Reparation.Statut.EN_COURS,
        Reparation.Statut.ANNULE,
    },
    Reparation.Statut.EN_COURS: {
        Reparation.Statut.PRET,
        Reparation.Statut.ANNULE,
    },
    Reparation.Statut.PRET: set(),
    Reparation.Statut.RESTITUE: set(),
    Reparation.Statut.ANNULE: set(),
}


# ============================================================
# ENREGISTREMENT DES TRAVAUX EFFECTUÉS
# ============================================================

@transaction.atomic
def enregistrer_travaux_reparation(
    *,
    reparation_id,
    bijouterie_id,
    bijoux_data,
    user,
):
    """
    Enregistre le travail effectué sur chaque bijou.

    bijoux_data = [
        {
            "bijou_id": 10,
            "travail_effectue": "Fermoir remplacé"
        },
        ...
    ]
    """

    try:
        reparation = (
            Reparation.objects
            .select_for_update()
            .select_related("bijouterie")
            .get(
                pk=reparation_id,
                bijouterie_id=bijouterie_id,
            )
        )
    except Reparation.DoesNotExist:
        raise ValidationError({
            "reparation": (
                "Réparation introuvable "
                "dans cette bijouterie."
            )
        })

    verifier_permission_reparation(
        user=user,
        bijouterie=reparation.bijouterie,
        roles_autorises=ROLES_SUIVI,
    )

    if reparation.statut != Reparation.Statut.EN_COURS:
        raise ValidationError({
            "statut": (
                "Les travaux ne peuvent être enregistrés "
                "que lorsque la réparation est en cours."
            )
        })

    if PaiementReparation.objects.filter(
        reparation_id=reparation.pk
    ).exists():
        raise ValidationError({
            "reparation": (
                "Impossible de modifier les travaux "
                "après paiement."
            )
        })

    if not isinstance(bijoux_data, (list, tuple)) or not bijoux_data:
        raise ValidationError({
            "bijoux": "Une liste non vide est obligatoire."
        })

    ids = []

    for ligne in bijoux_data:
        if not isinstance(ligne, dict):
            raise ValidationError({
                "bijoux": "Données de travaux invalides."
            })

        bijou_id = ligne.get("bijou_id")
        travail = ligne.get("travail_effectue")

        if (
            type(bijou_id) is not int
            or bijou_id <= 0
            or not isinstance(travail, str)
            or not travail.strip()
        ):
            raise ValidationError({
                "bijoux": (
                    "Chaque ligne doit contenir "
                    "bijou_id et travail_effectue."
                )
            })

        ids.append(bijou_id)

    if len(ids) != len(set(ids)):
        raise ValidationError({
            "bijoux": "Un bijou apparaît plusieurs fois."
        })

    bijoux = {
        bijou.pk: bijou
        for bijou in (
            ReparationBijou.objects
            .select_for_update()
            .filter(
                reparation_id=reparation.pk,
                pk__in=ids,
            )
        )
    }

    if len(bijoux) != len(ids):
        raise ValidationError({
            "bijoux": (
                "Un ou plusieurs bijoux n'appartiennent "
                "pas à cette réparation."
            )
        })

    for ligne in bijoux_data:
        bijou = bijoux[ligne["bijou_id"]]
        bijou.travail_effectue = (
            ligne["travail_effectue"].strip()
        )
        bijou.save(update_fields=["travail_effectue"])

    return reparation


# ============================================================
# CHANGEMENT DE STATUT
# ============================================================

@transaction.atomic
def changer_statut_reparation(
    *,
    reparation_id,
    bijouterie_id,
    nouveau_statut,
    user,
):
    """
    Transitions :
    EN_ATTENTE -> EN_COURS
    EN_ATTENTE -> ANNULE
    EN_COURS -> PRET
    EN_COURS -> ANNULE

    La restitution est gérée séparément.
    """

    try:
        reparation = (
            Reparation.objects
            .select_for_update()
            .select_related("bijouterie")
            .get(
                pk=reparation_id,
                bijouterie_id=bijouterie_id,
            )
        )
    except Reparation.DoesNotExist:
        raise ValidationError({
            "reparation": (
                "Réparation introuvable "
                "dans cette bijouterie."
            )
        })

    verifier_permission_reparation(
        user=user,
        bijouterie=reparation.bijouterie,
        roles_autorises=ROLES_SUIVI,
    )

    transitions = TRANSITIONS_REPARATION.get(
        reparation.statut,
        set(),
    )

    if nouveau_statut not in transitions:
        raise ValidationError({
            "statut": (
                f"Transition interdite : "
                f"{reparation.statut} -> {nouveau_statut}."
            )
        })

    if PaiementReparation.objects.filter(
        reparation_id=reparation.pk
    ).exists():
        raise ValidationError({
            "reparation": (
                "Une réparation payée ne peut plus "
                "changer de statut par ce service."
            )
        })

    if nouveau_statut == Reparation.Statut.PRET:
        reparation.verifier_total_bijoux()

        bijoux = list(
            ReparationBijou.objects
            .select_for_update()
            .filter(reparation_id=reparation.pk)
        )

        bijoux_incomplets = [
            bijou.numero_ligne
            for bijou in bijoux
            if not bijou.travail_effectue.strip()
        ]

        if bijoux_incomplets:
            raise ValidationError({
                "bijoux": (
                    "Le travail effectué doit être "
                    "renseigné pour chaque bijou. "
                    f"Lignes incomplètes : "
                    f"{bijoux_incomplets}."
                )
            })

    reparation.statut = nouveau_statut

    reparation.save(
        update_fields=["statut"]
    )

    return reparation


