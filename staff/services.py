# staff/services.py
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from backend.roles import (ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER, ROLE_VENDOR,
                           get_role_name)
from staff.models import Cashier, Manager
from vendor.models import Vendor

User = get_user_model()


@dataclass
class StaffCreationResult:
    staff_type: str
    staff: object
    user: object
    created_user: bool


ROLE_MODEL_MAP = {
    ROLE_MANAGER: Manager,
    ROLE_VENDOR: Vendor,
    ROLE_CASHIER: Cashier,
}

ALLOWED_BY_CALLER = {
    ROLE_ADMIN: {ROLE_MANAGER, ROLE_VENDOR, ROLE_CASHIER},
    ROLE_MANAGER: {ROLE_VENDOR, ROLE_CASHIER},
}


def _get_existing_staff_flags(user):
    return {
        ROLE_MANAGER: Manager.objects.select_for_update().filter(user_id=user.id).exists(),
        ROLE_VENDOR: Vendor.objects.select_for_update().filter(user_id=user.id).exists(),
        ROLE_CASHIER: Cashier.objects.select_for_update().filter(user_id=user.id).exists(),
    }

ROLE_MODEL_MAP = {
    ROLE_MANAGER: Manager,
    ROLE_VENDOR: Vendor,
    ROLE_CASHIER: Cashier,
}


# @transaction.atomic
# def create_staff_member(
#     *,
#     caller_user,
#     target_role: str,
#     email: str,
#     bijouterie=None,
#     bijouteries=None,
#     verifie: bool = True,
#     raison_desactivation: str | None = None,
# ):
#     bijouteries = bijouteries or []

#     caller_role = get_role_name(caller_user)

#     if caller_role not in ALLOWED_BY_CALLER:
#         raise PermissionError("Accès réservé aux rôles admin et manager.")

#     if target_role not in ALLOWED_BY_CALLER[caller_role]:
#         raise PermissionError(
#             f"Un {caller_role} ne peut pas créer un staff de type {target_role}."
#         )

#     if target_role not in ROLE_MODEL_MAP:
#         raise ValueError("Type de staff invalide.")

#     email = email.strip().lower()

#     user = User.objects.select_for_update().filter(email__iexact=email).first()

#     if user is None:
#         raise ValueError(
#             "Aucun utilisateur trouvé avec cet email. "
#             "L'utilisateur doit d'abord créer son compte."
#         )

#     if getattr(user, "is_superuser", False):
#         raise ValueError("Un super administrateur ne peut pas être transformé en staff.")

#     existing_role = get_role_name(user)

#     if existing_role == ROLE_ADMIN:
#         raise ValueError("Un utilisateur admin ne peut pas être transformé en staff.")

#     existing_staff = _get_existing_staff_flags(user)

#     if (
#         existing_staff[ROLE_MANAGER]
#         or existing_staff[ROLE_VENDOR]
#         or existing_staff[ROLE_CASHIER]
#     ):
#         raise ValueError(
#             "Cet utilisateur possède déjà un profil staff."
#         )

#     Model = ROLE_MODEL_MAP[target_role]

#     try:
#         if target_role == ROLE_MANAGER:
#             if not bijouteries:
#                 raise ValueError("Le manager doit être rattaché à au moins une bijouterie.")

#             staff = Manager.objects.create(
#                 user=user,
#                 verifie=verifie,
#                 raison_desactivation=raison_desactivation,
#             )

#             staff.bijouteries.set(bijouteries)

#         else:
#             if bijouterie is None:
#                 raise ValueError("La bijouterie est obligatoire pour vendor/cashier.")

#             if caller_role == ROLE_MANAGER:
#                 caller_manager = (
#                     Manager.objects
#                     .prefetch_related("bijouteries")
#                     .filter(
#                         user=caller_user,
#                         verifie=True,
#                     )
#                     .first()
#                 )

#                 if not caller_manager:
#                     raise PermissionError("Profil manager introuvable.")

#                 if not caller_manager.bijouteries.filter(id=bijouterie.id).exists():
#                     raise PermissionError(
#                         "Un manager ne peut créer un staff que dans ses propres bijouteries."
#                     )

#             staff = Model.objects.create(
#                 user=user,
#                 bijouterie=bijouterie,
#                 verifie=verifie,
#                 raison_desactivation=raison_desactivation,
#             )

#     except IntegrityError:
#         raise ValueError("Conflit d'intégrité à la création du profil staff.")

#     return StaffCreationResult(
#         staff_type=target_role,
#         staff=staff,
#         user=user,
#         created_user=False,
#     )


@transaction.atomic
def create_staff_member(
    *,
    caller_user,
    target_role: str,
    email: str,
    bijouterie=None,
    bijouteries=None,
    verifie: bool = True,
):
    bijouteries = bijouteries or []

    caller_role = get_role_name(caller_user)

    if caller_role not in ALLOWED_BY_CALLER:
        raise PermissionError("Accès réservé aux rôles admin et manager.")

    if target_role not in ALLOWED_BY_CALLER[caller_role]:
        raise PermissionError(
            f"Un {caller_role} ne peut pas créer un staff de type {target_role}."
        )

    if target_role not in ROLE_MODEL_MAP:
        raise ValueError("Type de staff invalide.")

    email = email.strip().lower()

    user = User.objects.select_for_update().filter(email__iexact=email).first()

    if user is None:
        raise ValueError(
            "Aucun utilisateur trouvé avec cet email. "
            "L'utilisateur doit d'abord créer son compte."
        )

    if getattr(user, "is_superuser", False):
        raise ValueError("Un super administrateur ne peut pas être transformé en staff.")

    existing_role = get_role_name(user)

    if existing_role == ROLE_ADMIN:
        raise ValueError("Un utilisateur admin ne peut pas être transformé en staff.")

    existing_staff = _get_existing_staff_flags(user)

    if (
        existing_staff[ROLE_MANAGER]
        or existing_staff[ROLE_VENDOR]
        or existing_staff[ROLE_CASHIER]
    ):
        raise ValueError("Cet utilisateur possède déjà un profil staff.")

    Model = ROLE_MODEL_MAP[target_role]

    try:
        if target_role == ROLE_MANAGER:
            if not bijouteries:
                raise ValueError("Le manager doit être rattaché à au moins une bijouterie.")

            staff = Manager.objects.create(
                user=user,
                verifie=verifie,
            )

            staff.bijouteries.set(bijouteries)

        else:
            if bijouterie is None:
                raise ValueError("La bijouterie est obligatoire pour vendor/cashier.")

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

                if not caller_manager:
                    raise PermissionError("Profil manager introuvable.")

                if not caller_manager.bijouteries.filter(id=bijouterie.id).exists():
                    raise PermissionError(
                        "Un manager ne peut créer un staff que dans ses propres bijouteries."
                    )

            staff = Model.objects.create(
                user=user,
                bijouterie=bijouterie,
                verifie=verifie,
            )

    except IntegrityError:
        raise ValueError("Conflit d'intégrité à la création du profil staff.")

    return StaffCreationResult(
        staff_type=target_role,
        staff=staff,
        user=user,
        created_user=False,
    )
    
    
# Update staff member
@dataclass
class StaffUpdateResult:
    staff_type: str
    staff: object
    user: object


# ROLE_MODEL_MAP = {
#     ROLE_MANAGER: Manager,
#     ROLE_VENDOR: Vendor,
#     ROLE_CASHIER: Cashier,
# }


# @transaction.atomic
# def update_staff_member(
#     *,
#     caller_user,
#     staff_id: int,
#     target_role: str,
#     email: str | None = None,
#     first_name: str | None = None,
#     last_name: str | None = None,
#     bijouterie=None,
#     bijouteries=None,
#     verifie: bool | None = None,
#     raison_desactivation: str | None = None,
# ):
#     bijouteries = bijouteries or []

#     caller_role = get_role_name(caller_user)

#     if caller_role not in (ROLE_ADMIN, ROLE_MANAGER):
#         raise PermissionError("Accès réservé aux rôles admin et manager.")

#     Model = ROLE_MODEL_MAP.get(target_role)
#     if not Model:
#         raise ValueError("Rôle invalide.")

#     qs = Model.objects.select_for_update().select_related("user")

#     if target_role == ROLE_MANAGER:
#         qs = qs.prefetch_related("bijouteries")
#     else:
#         qs = qs.select_related("bijouterie")

#     staff = qs.filter(pk=staff_id).first()

#     if not staff:
#         raise ValueError("Staff introuvable.")

#     if caller_role == ROLE_MANAGER:
#         caller_manager = (
#             Manager.objects
#             .prefetch_related("bijouteries")
#             .filter(user=caller_user)
#             .first()
#         )

#         if not caller_manager:
#             raise PermissionError("Profil manager introuvable.")

#         if target_role == ROLE_MANAGER:
#             raise PermissionError("Un manager ne peut pas modifier un autre manager.")

#         if not caller_manager.bijouteries.filter(id=staff.bijouterie_id).exists():
#             raise PermissionError("Vous ne pouvez modifier que les staff de vos bijouteries.")

#         if bijouterie is not None and not caller_manager.bijouteries.filter(id=bijouterie.id).exists():
#             raise PermissionError("Un manager ne peut affecter un staff qu'à ses propres bijouteries.")

#     user = staff.user
#     user_fields = []
#     staff_fields = []

#     if email is not None and user and user.email != email:
#         new_email = email.strip().lower()

#         if User.objects.exclude(pk=user.pk).filter(email__iexact=new_email).exists():
#             raise ValueError("Cet email est déjà utilisé.")

#         user.email = new_email
#         user.email = email.strip().lower()
        
#         user_fields.append("email")

#     if first_name is not None and user and user.first_name != first_name:
#         user.first_name = first_name
#         user_fields.append("first_name")

#     if last_name is not None and user and user.last_name != last_name:
#         user.last_name = last_name
#         user_fields.append("last_name")

#     if user_fields:
#         user.save(update_fields=user_fields)

#     if target_role == ROLE_MANAGER:
#         if bijouteries is not None:
#             staff.bijouteries.set(bijouteries)
#     else:
#         if bijouterie is not None and staff.bijouterie_id != getattr(bijouterie, "id", None):
#             staff.bijouterie = bijouterie
#             staff_fields.append("bijouterie")

#     if verifie is not None and staff.verifie != verifie:
#         staff.verifie = verifie
#         staff_fields.append("verifie")

#     if raison_desactivation is not None and staff.raison_desactivation != raison_desactivation:
#         staff.raison_desactivation = raison_desactivation
#         staff_fields.append("raison_desactivation")

#     if staff_fields:
#         staff.save(update_fields=staff_fields)

#     return StaffUpdateResult(
#         staff_type=target_role,
#         staff=staff,
#         user=user,
#     )
    


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
    caller_role = get_role_name(caller_user)

    if caller_role not in (ROLE_ADMIN, ROLE_MANAGER):
        raise PermissionError("Accès réservé aux rôles admin et manager.")

    if verifie is False and not raison_desactivation:
        raise ValueError("La raison de désactivation est obligatoire.")

    Model = ROLE_MODEL_MAP.get(target_role)
    if not Model:
        raise ValueError("Rôle invalide.")

    qs = Model.objects.select_for_update().select_related("user")

    if target_role == ROLE_MANAGER:
        qs = qs.prefetch_related("bijouteries")
    else:
        qs = qs.select_related("bijouterie")

    staff = qs.filter(pk=staff_id).first()

    if not staff:
        raise ValueError("Staff introuvable.")

    if caller_role == ROLE_MANAGER:
        caller_manager = (
            Manager.objects
            .prefetch_related("bijouteries")
            .filter(user=caller_user, verifie=True)
            .first()
        )

        if not caller_manager:
            raise PermissionError("Profil manager introuvable.")

        if target_role == ROLE_MANAGER:
            raise PermissionError("Un manager ne peut pas modifier un autre manager.")

        if not caller_manager.bijouteries.filter(id=staff.bijouterie_id).exists():
            raise PermissionError("Vous ne pouvez modifier que les staff de vos bijouteries.")

        if bijouterie is not None and not caller_manager.bijouteries.filter(id=bijouterie.id).exists():
            raise PermissionError("Un manager ne peut affecter un staff qu'à ses propres bijouteries.")

    user = staff.user
    user_fields = []
    staff_fields = []

    if email is not None and user:
        new_email = email.strip().lower()

        if user.email != new_email:
            if User.objects.exclude(pk=user.pk).filter(email__iexact=new_email).exists():
                raise ValueError("Cet email est déjà utilisé.")

            user.email = new_email
            user_fields.append("email")

    if first_name is not None and user and user.first_name != first_name:
        user.first_name = first_name
        user_fields.append("first_name")

    if last_name is not None and user and user.last_name != last_name:
        user.last_name = last_name
        user_fields.append("last_name")

    if user_fields:
        user.save(update_fields=user_fields)

    if target_role == ROLE_MANAGER:
        if bijouteries is not None:
            staff.bijouteries.set(bijouteries)
    else:
        if bijouterie is not None and staff.bijouterie_id != getattr(bijouterie, "id", None):
            staff.bijouterie = bijouterie
            staff_fields.append("bijouterie")

    if verifie is not None and staff.verifie != verifie:
        staff.verifie = verifie
        staff_fields.append("verifie")

    if raison_desactivation is not None and staff.raison_desactivation != raison_desactivation:
        staff.raison_desactivation = raison_desactivation
        staff_fields.append("raison_desactivation")

    if staff_fields:
        staff.save(update_fields=staff_fields)

    return StaffUpdateResult(
        staff_type=target_role,
        staff=staff,
        user=user,
    )
    


