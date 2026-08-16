# staff/services.py
from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from backend.roles import (ROLE_ADMIN, ROLE_BUYER, ROLE_CASHIER, ROLE_MANAGER,
                           ROLE_VENDOR, get_role_name)
from staff.models import Buyer, Cashier, Manager
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
    ROLE_ADMIN: {
        ROLE_MANAGER,
        ROLE_VENDOR,
        ROLE_CASHIER,
        ROLE_BUYER,
    },

    ROLE_MANAGER: {
        ROLE_VENDOR,
        ROLE_CASHIER,
    },
}


def _get_existing_staff_flags(user):
    """
    Vérifie si l'utilisateur possède déjà un profil staff.
    """
    return {
        ROLE_MANAGER: (
            Manager.objects
            .select_for_update()
            .filter(user_id=user.id)
            .exists()
        ),

        ROLE_VENDOR: (
            Vendor.objects
            .select_for_update()
            .filter(user_id=user.id)
            .exists()
        ),

        ROLE_CASHIER: (
            Cashier.objects
            .select_for_update()
            .filter(user_id=user.id)
            .exists()
        ),

        ROLE_BUYER: (
            Buyer.objects
            .select_for_update()
            .filter(user_id=user.id)
            .exists()
        ),
    }


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
    - admin : manager, vendor, cashier, buyer ;
    - manager : vendor, cashier ;
    - un utilisateur ne peut avoir qu'un seul profil staff ;
    - manager : plusieurs bijouteries ;
    - vendor, cashier, buyer : une seule bijouterie.
    """

    bijouteries = bijouteries or []

    target_role = (
        target_role or ""
    ).strip().lower()

    email = (
        email or ""
    ).strip().lower()

    if not email:
        raise ValueError("Email requis.")

    caller_role = get_role_name(caller_user)

    if caller_role not in ALLOWED_BY_CALLER:
        raise PermissionError(
            "Accès réservé aux rôles admin et manager."
        )

    if target_role not in ALLOWED_BY_CALLER[caller_role]:
        raise PermissionError(
            f"Un {caller_role} ne peut pas créer "
            f"un staff de type {target_role}."
        )

    Model = ROLE_MODEL_MAP.get(target_role)

    if Model is None:
        raise ValueError("Type de staff invalide.")

    user = (
        User.objects
        .select_for_update()
        .filter(email__iexact=email)
        .first()
    )

    if user is None:
        raise ValueError(
            "Aucun utilisateur trouvé avec cet email. "
            "L'utilisateur doit d'abord créer son compte."
        )

    if not user.is_email_verified:
        raise ValueError(
            "L'utilisateur doit confirmer son email "
            "avant d'être affecté comme staff."
        )

    if not user.is_active:
        raise ValueError(
            "Le compte utilisateur n'est pas actif."
        )

    if getattr(user, "is_superuser", False):
        raise ValueError(
            "Un super administrateur ne peut pas "
            "être transformé en staff."
        )

    existing_role = get_role_name(user)

    if existing_role == ROLE_ADMIN:
        raise ValueError(
            "Un utilisateur admin ne peut pas "
            "être transformé en staff."
        )

    existing_staff = _get_existing_staff_flags(user)

    if any(existing_staff.values()):
        raise ValueError(
            "Cet utilisateur possède déjà un profil staff."
        )

    try:
        if target_role == ROLE_MANAGER:
            if not bijouteries:
                raise ValueError(
                    "Le manager doit être rattaché "
                    "à au moins une bijouterie."
                )

            staff = Manager.objects.create(
                user=user,
                verifie=True,
            )

            staff.bijouteries.set(bijouteries)

        else:
            if bijouterie is None:
                raise ValueError(
                    "La bijouterie est obligatoire pour "
                    "vendor, cashier et buyer."
                )

            if caller_role == ROLE_MANAGER:
                caller_manager = (
                    Manager.objects
                    .prefetch_related("bijouteries")
                    .filter(
                        user=caller_user,
                        verifie=True,
                    )
                    .first()
                )

                if caller_manager is None:
                    raise PermissionError(
                        "Profil manager introuvable."
                    )

                manager_has_access = (
                    caller_manager.bijouteries
                    .filter(pk=bijouterie.pk)
                    .exists()
                )

                if not manager_has_access:
                    raise PermissionError(
                        "Un manager ne peut créer un staff "
                        "que dans ses propres bijouteries."
                    )

            staff = Model.objects.create(
                user=user,
                bijouterie=bijouterie,
                verifie=True,
            )

    except IntegrityError as exc:
        raise ValueError(
            "Conflit d'intégrité lors de la création "
            "du profil staff."
        ) from exc

    role_obj, _ = Role.objects.get_or_create(
        role=target_role,
    )

    user.user_role = role_obj
    user.save(update_fields=["user_role"])

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
    Met à jour un profil staff.

    La désactivation agit uniquement sur le profil staff.
    Le compte utilisateur reste actif.
    """

    caller_role = get_role_name(caller_user)

    if caller_role not in {
        ROLE_ADMIN,
        ROLE_MANAGER,
    }:
        raise PermissionError(
            "Accès réservé aux rôles admin et manager."
        )

    target_role = (
        target_role or ""
    ).strip().lower()

    Model = ROLE_MODEL_MAP.get(target_role)

    if Model is None:
        raise ValueError("Rôle invalide.")

    if verifie is False:
        raison_clean = (
            raison_desactivation or ""
        ).strip()

        if not raison_clean:
            raise ValueError(
                "La raison de désactivation est obligatoire."
            )

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
        raise ValueError("Staff introuvable.")

    if caller_role == ROLE_MANAGER:
        caller_manager = (
            Manager.objects
            .prefetch_related("bijouteries")
            .filter(
                user=caller_user,
                verifie=True,
            )
            .first()
        )

        if caller_manager is None:
            raise PermissionError(
                "Profil manager introuvable."
            )

        if target_role == ROLE_MANAGER:
            raise PermissionError(
                "Un manager ne peut pas modifier "
                "un autre manager."
            )

        if not staff.bijouterie_id:
            raise PermissionError(
                "Le staff ciblé n'est rattaché "
                "à aucune bijouterie."
            )

        manager_has_access = (
            caller_manager.bijouteries
            .filter(pk=staff.bijouterie_id)
            .exists()
        )

        if not manager_has_access:
            raise PermissionError(
                "Vous ne pouvez modifier que les staff "
                "de vos bijouteries."
            )

        if bijouterie is not None:
            manager_has_new_access = (
                caller_manager.bijouteries
                .filter(pk=bijouterie.pk)
                .exists()
            )

            if not manager_has_new_access:
                raise PermissionError(
                    "Un manager ne peut affecter un staff "
                    "qu'à ses propres bijouteries."
                )

    user = staff.user

    user_fields = []

    if email is not None and user is not None:
        new_email = email.strip().lower()

        if not new_email:
            raise ValueError(
                "L'adresse email ne peut pas être vide."
            )

        if user.email != new_email:
            exists = (
                User.objects
                .exclude(pk=user.pk)
                .filter(email__iexact=new_email)
                .exists()
            )

            if exists:
                raise ValueError(
                    "Cet email est déjà utilisé."
                )

            user.email = new_email
            user_fields.append("email")

    if (
        first_name is not None
        and user is not None
        and user.first_name != first_name
    ):
        user.first_name = first_name
        user_fields.append("first_name")

    if (
        last_name is not None
        and user is not None
        and user.last_name != last_name
    ):
        user.last_name = last_name
        user_fields.append("last_name")

    if user_fields:
        user.save(update_fields=user_fields)

    staff_fields = []

    if target_role == ROLE_MANAGER:
        if bijouteries is not None:
            if not bijouteries:
                raise ValueError(
                    "Le manager doit conserver au moins "
                    "une bijouterie."
                )

            staff.bijouteries.set(bijouteries)

    else:
        if (
            bijouterie is not None
            and staff.bijouterie_id != bijouterie.pk
        ):
            staff.bijouterie = bijouterie
            staff_fields.append("bijouterie")

    if staff_fields:
        staff.save(update_fields=staff_fields)

    if verifie is False and staff.verifie:
        staff.desactiver(
            by_user=caller_user,
            raison=raison_desactivation or "",
        )

    elif verifie is True and not staff.verifie:
        staff.reactiver()

    elif (
        verifie is False
        and not staff.verifie
        and raison_desactivation is not None
    ):
        raison_clean = raison_desactivation.strip()

        if (
            raison_clean
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
def promote_user_to_admin(
    *,
    caller_user,
    email: str,
):
    caller_role = get_role_name(caller_user)

    if caller_role != ROLE_ADMIN:
        raise PermissionError(
            "Seul un administrateur peut promouvoir "
            "un utilisateur en administrateur."
        )

    email = (email or "").strip().lower()

    user = (
        User.objects
        .select_for_update()
        .filter(email__iexact=email)
        .first()
    )

    if user is None:
        raise ValueError(
            "Utilisateur introuvable."
        )

    if not user.is_active:
        raise ValueError(
            "Le compte utilisateur n'est pas actif."
        )

    existing_staff = _get_existing_staff_flags(user)

    if any(existing_staff.values()):
        raise ValueError(
            "Cet utilisateur possède déjà un profil staff."
        )

    role_obj, _ = Role.objects.get_or_create(
        role=ROLE_ADMIN,
    )

    user.user_role = role_obj
    user.save(
        update_fields=[
            "user_role",
        ]
    )

    return user