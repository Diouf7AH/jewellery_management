from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import transaction

from backend.roles import (ROLE_ADMIN, ROLE_BUYER, ROLE_CASHIER, ROLE_MANAGER,
                           ROLE_VENDOR, get_role_name)
from staff.models import Buyer, Cashier, Manager
from store.models import Bijouterie
from userauths.models import Role
from vendor.models import Vendor

User = get_user_model()


@dataclass
class StaffCreationResult:
    staff_type: str
    staff: object
    user: object
    created_user: bool


@dataclass
class StaffUpdateResult:
    staff_type: str
    staff: object
    user: object


ROLE_MODEL_MAP = {
    ROLE_MANAGER: Manager,
    ROLE_VENDOR: Vendor,
    ROLE_CASHIER: Cashier,
    ROLE_BUYER: Buyer,
}

ALLOWED_BY_CALLER = {
    ROLE_ADMIN: {ROLE_MANAGER, ROLE_VENDOR, ROLE_CASHIER, ROLE_BUYER},
    ROLE_MANAGER: {ROLE_VENDOR, ROLE_CASHIER},
}


def _normalize_role(role) -> str:
    return str(role or "").strip().lower()


def _normalize_email(email) -> str:
    return str(email or "").strip().lower()


def _check_caller(caller_user, target_role: str):
    """Contrôle le rôle de l'appelant et l'accès au rôle cible."""
    if not getattr(caller_user, "is_authenticated", False):
        raise PermissionError("Authentification requise.")
    if not getattr(caller_user, "is_active", False):
        raise PermissionError("Votre compte utilisateur est désactivé.")

    caller_role = _normalize_role(get_role_name(caller_user))
    if caller_role not in ALLOWED_BY_CALLER:
        raise PermissionError("Accès réservé aux administrateurs et managers.")
    if target_role not in ROLE_MODEL_MAP:
        raise ValueError("Type de staff invalide.")
    if target_role not in ALLOWED_BY_CALLER[caller_role]:
        raise PermissionError(
            f"Un {caller_role} ne peut pas gérer un staff de type {target_role}."
        )

    if caller_role == ROLE_MANAGER:
        manager = (
            Manager.objects.select_related("user")
            .filter(user=caller_user, verifie=True)
            .first()
        )
        if manager is None or not manager.is_active_staff:
            raise PermissionError("Profil manager introuvable ou désactivé.")
        return caller_role, manager
    return caller_role, None


def _validate_bijouterie(bijouterie):
    if bijouterie is None:
        raise ValueError("La bijouterie est obligatoire.")
    pk = getattr(bijouterie, "pk", None)
    if pk is None or not Bijouterie.objects.filter(pk=pk).exists():
        raise ValueError("Bijouterie introuvable.")
    return bijouterie


def _validate_bijouteries(bijouteries):
    if bijouteries is None:
        raise ValueError("Au moins une bijouterie est obligatoire.")
    items = list(bijouteries)
    if not items:
        raise ValueError("Le manager doit avoir au moins une bijouterie.")
    ids = []
    for item in items:
        pk = getattr(item, "pk", None)
        if pk is None:
            raise ValueError("Une bijouterie fournie est invalide.")
        ids.append(pk)
    unique_ids = set(ids)
    queryset = Bijouterie.objects.filter(pk__in=unique_ids)
    if queryset.count() != len(unique_ids):
        raise ValueError("Une ou plusieurs bijouteries sont introuvables.")
    return list(Bijouterie.objects.filter(pk__in=unique_ids))


def _check_manager_scope(manager, bijouterie):
    if manager is None:
        return
    if bijouterie is None:
        raise PermissionError("Bijouterie obligatoire pour ce manager.")
    if not manager.bijouteries.filter(pk=bijouterie.pk).exists():
        raise PermissionError("Cette bijouterie est hors de votre périmètre.")


def _get_existing_staff_flags(user):
    """Vérifie aussi les profils désactivés ; l'utilisateur doit être verrouillé."""
    return {
        ROLE_MANAGER: Manager.objects.filter(user_id=user.pk).exists(),
        ROLE_VENDOR: Vendor.objects.filter(user_id=user.pk).exists(),
        ROLE_CASHIER: Cashier.objects.filter(user_id=user.pk).exists(),
        ROLE_BUYER: Buyer.objects.filter(user_id=user.pk).exists(),
    }


def _validate_target_user(user):
    if user is None:
        raise ValueError("Utilisateur introuvable.")
    if not user.is_active:
        raise ValueError("Le compte utilisateur est désactivé.")
    if not user.is_email_verified:
        raise ValueError("L'utilisateur doit confirmer son email.")
    if getattr(user, "is_superuser", False):
        raise ValueError("Un super administrateur ne peut pas être affecté comme staff.")


def _check_vendor_reassignment(staff, new_bijouterie):
    """Un transfert vendeur exige une procédure dédiée (stock et ventes)."""
    if staff.bijouterie_id != new_bijouterie.pk:
        raise ValueError(
            "Le changement de bijouterie d'un vendeur doit être effectué "
            "par une procédure de transfert dédiée."
        )

@transaction.atomic
def create_staff_member(
    *,
    caller_user,
    target_role: str,
    email: str,
    bijouterie=None,
    bijouteries=None,
):
    """
    Crée un profil staff pour un utilisateur existant.

    Règles :
    - L'utilisateur doit avoir confirmé son email.
    - Le compte utilisateur doit être actif.
    - Un utilisateur ne peut avoir qu'un profil staff.
    - Admin : manager, vendor, cashier, buyer.
    - Manager : vendor, cashier uniquement.
    - Manager : plusieurs bijouteries.
    - Autres profils : une seule bijouterie.
    - Le profil staff est créé avec verifie=True.
    """

    target_role = _normalize_role(target_role)
    email = _normalize_email(email)

    if not email:
        raise ValueError("Email requis.")

    # Vérifier les permissions du créateur.
    caller_role, caller_manager = _check_caller(
        caller_user,
        target_role,
    )

    Model = ROLE_MODEL_MAP[target_role]

    # Verrouiller l'utilisateur pour éviter
    # deux créations simultanées.
    user = (
        User.objects.select_for_update()
        .filter(email__iexact=email)
        .first()
    )

    # Vérifier l'existence, l'activation
    # et la confirmation de l'email.
    _validate_target_user(user)

    # Interdire la transformation d'un admin.
    if _normalize_role(get_role_name(user)) == ROLE_ADMIN:
        raise ValueError(
            "Un administrateur ne peut pas "
            "être transformé en staff."
        )

    # Vérifier tous les profils, même désactivés.
    existing_staff = _get_existing_staff_flags(user)

    if any(existing_staff.values()):
        raise ValueError(
            "Cet utilisateur possède déjà un profil staff."
        )

    # Création d'un manager.
    if target_role == ROLE_MANAGER:

        validated_bijouteries = _validate_bijouteries(
            bijouteries
        )

        staff = Manager.objects.create(
            user=user,
            verifie=True,
        )

        staff.bijouteries.set(
            validated_bijouteries
        )

    # Création vendor, cashier ou buyer.
    else:

        validated_bijouterie = _validate_bijouterie(
            bijouterie
        )

        if caller_role == ROLE_MANAGER:
            _check_manager_scope(
                caller_manager,
                validated_bijouterie,
            )

        staff = Model.objects.create(
            user=user,
            bijouterie=validated_bijouterie,
            verifie=True,
        )

    # Affecter le rôle au compte utilisateur.
    role_obj, _ = Role.objects.get_or_create(
        role=target_role
    )

    user.user_role = role_obj
    user.save(
        update_fields=["user_role"]
    )

    return StaffCreationResult(
        staff_type=target_role,
        staff=staff,
        user=user,
        created_user=False,
    )


@transaction.atomic
def update_staff_member(
    *,
    caller_user,
    staff_id: int,
    target_role: str,
    email: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    bijouterie=None,
    bijouteries=None,
    verifie: bool | None = None,
    raison_desactivation: str | None = None,
):
    """
    Modifie un profil staff existant.

    La désactivation du profil staff ne désactive
    jamais le compte utilisateur.
    """

    target_role = _normalize_role(target_role)

    caller_role, caller_manager = _check_caller(
        caller_user,
        target_role,
    )

    Model = ROLE_MODEL_MAP[target_role]

    # Validation du statut.
    if verifie is not None and type(verifie) is not bool:
        raise ValueError(
            "verifie doit être un booléen."
        )

    raison_clean = str(
        raison_desactivation or ""
    ).strip()

    if verifie is False and not raison_clean:
        raise ValueError(
            "La raison de désactivation est obligatoire."
        )

    # Récupération et verrouillage du staff.
    queryset = (
        Model.objects
        .select_for_update()
        .select_related("user")
    )

    if target_role == ROLE_MANAGER:
        queryset = queryset.prefetch_related(
            "bijouteries"
        )
    else:
        queryset = queryset.select_related(
            "bijouterie"
        )

    staff = queryset.filter(
        pk=staff_id
    ).first()

    if staff is None:
        raise ValueError(
            "Staff introuvable."
        )

    # Vérifier le périmètre du manager.
    if caller_role == ROLE_MANAGER:

        _check_manager_scope(
            caller_manager,
            staff.bijouterie,
        )

        if bijouterie is not None:
            validated_bijouterie = _validate_bijouterie(
                bijouterie
            )

            _check_manager_scope(
                caller_manager,
                validated_bijouterie,
            )

    # Verrouiller le compte utilisateur.
    user = (
        User.objects
        .select_for_update()
        .get(pk=staff.user_id)
    )

    # Email : modification interdite ici.
    if email is not None:

        new_email = _normalize_email(email)

        if new_email != _normalize_email(user.email):
            raise ValueError(
                "La modification de l'adresse email "
                "doit passer par une procédure "
                "de vérification dédiée."
            )

    # Modifier les informations personnelles.
    user_fields = []

    if (
        first_name is not None
        and user.first_name != first_name
    ):
        user.first_name = first_name
        user_fields.append("first_name")

    if (
        last_name is not None
        and user.last_name != last_name
    ):
        user.last_name = last_name
        user_fields.append("last_name")

    if user_fields:
        user.save(
            update_fields=user_fields
        )

    # Affectation des bijouteries.
    if target_role == ROLE_MANAGER:

        if bijouteries is not None:
            validated_bijouteries = _validate_bijouteries(
                bijouteries
            )

            staff.bijouteries.set(
                validated_bijouteries
            )

    elif bijouterie is not None:

        validated_bijouterie = _validate_bijouterie(
            bijouterie
        )

        if staff.bijouterie_id != validated_bijouterie.pk:

            if target_role == ROLE_VENDOR:
                _check_vendor_reassignment(
                    staff,
                    validated_bijouterie,
                )

            staff.bijouterie = validated_bijouterie

            staff.save(
                update_fields=[
                    "bijouterie",
                    "updated_at",
                ]
            )

    # Désactivation du profil staff.
    if verifie is False and staff.verifie:

        staff.desactiver(
            by_user=caller_user,
            raison=raison_clean,
        )

    # Réactivation du profil staff.
    elif verifie is True and not staff.verifie:

        staff.reactiver()

    # Modification de la raison si déjà désactivé.
    elif (
        verifie is False
        and not staff.verifie
        and raison_clean
        and staff.raison_desactivation != raison_clean
    ):

        staff.raison_desactivation = raison_clean

        staff.save(
            update_fields=[
                "raison_desactivation",
                "updated_at",
            ]
        )

    return StaffUpdateResult(
        staff_type=target_role,
        staff=staff,
        user=user,
    )

@transaction.atomic
def promote_user_to_admin(*, caller_user, email: str):
    """Seul un administrateur peut promouvoir un compte vérifié sans profil staff."""
    if not getattr(caller_user, "is_authenticated", False):
        raise PermissionError("Authentification requise.")
    if not getattr(caller_user, "is_active", False):
        raise PermissionError("Votre compte utilisateur est désactivé.")
    if _normalize_role(get_role_name(caller_user)) != ROLE_ADMIN:
        raise PermissionError("Seul un administrateur peut créer un autre administrateur.")

    email = _normalize_email(email)
    if not email:
        raise ValueError("Email requis.")
    user = User.objects.select_for_update().filter(email__iexact=email).first()
    _validate_target_user(user)
    if any(_get_existing_staff_flags(user).values()):
        raise ValueError("Cet utilisateur possède déjà un profil staff.")
    role_obj, _ = Role.objects.get_or_create(role=ROLE_ADMIN)
    user.user_role = role_obj
    user.save(update_fields=["user_role"])
    return user

