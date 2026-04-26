# staff/services.py
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from backend.permissions import (ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER,
                                 ROLE_VENDOR)
from staff.models import Cashier, Manager
from userauths.models import Role
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


def _get_or_raise_roles():
    role_manager = Role.objects.filter(role=ROLE_MANAGER).first()
    role_vendor = Role.objects.filter(role=ROLE_VENDOR).first()
    role_cashier = Role.objects.filter(role=ROLE_CASHIER).first()

    if not all([role_manager, role_vendor, role_cashier]):
        raise ValueError("Les rôles manager/vendor/cashier n'existent pas en base.")

    return {
        ROLE_MANAGER: role_manager,
        ROLE_VENDOR: role_vendor,
        ROLE_CASHIER: role_cashier,
    }


def _get_existing_staff_flags(user):
    return {
        ROLE_MANAGER: Manager.objects.select_for_update().filter(user_id=user.id).exists(),
        ROLE_VENDOR: Vendor.objects.select_for_update().filter(user_id=user.id).exists(),
        ROLE_CASHIER: Cashier.objects.select_for_update().filter(user_id=user.id).exists(),
    }


@transaction.atomic
def create_staff_member(
    *,
    caller_user,
    target_role: str,
    email: str,
    bijouterie,
    password: str | None = None,
    first_name: str = "",
    last_name: str = "",
    verifie: bool = True,
    raison_desactivation: str | None = None,
):
    caller_role = getattr(getattr(caller_user, "user_role", None), "role", None)

    if caller_role not in ALLOWED_BY_CALLER:
        raise PermissionError("Accès réservé aux rôles admin et manager.")

    if target_role not in ALLOWED_BY_CALLER[caller_role]:
        raise PermissionError(f"Un {caller_role} ne peut pas créer un staff de type {target_role}.")

    if caller_role == ROLE_MANAGER:
        caller_manager = (
            Manager.objects
            .select_related("bijouterie")
            .filter(user=caller_user)
            .first()
        )
        caller_bj_id = getattr(getattr(caller_manager, "bijouterie", None), "id", None)
        if not caller_bj_id or caller_bj_id != bijouterie.id:
            raise PermissionError("Un manager ne peut créer un staff que dans sa propre bijouterie.")

    role_map = _get_or_raise_roles()
    Model = ROLE_MODEL_MAP[target_role]

    email = email.strip().lower()
    user = User.objects.select_for_update().filter(email__iexact=email).first()
    created_user = False

    if user is None:
        user = User(
            email=email,
            first_name=first_name or "",
            last_name=last_name or "",
            is_active=True,
        )
        user.set_password(password)
        user.user_role = role_map[target_role]
        user.save()
        created_user = True
    else:
        existing_role = getattr(getattr(user, "user_role", None), "role", None)

        if existing_role == ROLE_ADMIN:
            raise ValueError("Un utilisateur admin ne peut pas être transformé en staff.")

        existing_staff = _get_existing_staff_flags(user)
        if any(existing_staff.values()):
            raise ValueError("Ce user a déjà un profil staff (manager/vendor/cashier).")

        user.user_role = role_map[target_role]

        changed = ["user_role"]
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            changed.append("first_name")
        if last_name and user.last_name != last_name:
            user.last_name = last_name
            changed.append("last_name")

        user.save(update_fields=changed)

    try:
        staff = Model.objects.create(
            user=user,
            bijouterie=bijouterie,
            verifie=verifie,
            raison_desactivation=raison_desactivation,
        )
    except IntegrityError:
        raise ValueError("Conflit d'intégrité à la création du profil staff.")

    return StaffCreationResult(
        staff_type=target_role,
        staff=staff,
        user=user,
        created_user=created_user,
    )
    
    

# Update staff member
@dataclass
class StaffUpdateResult:
    staff_type: str
    staff: object
    user: object


ROLE_MODEL_MAP = {
    ROLE_MANAGER: Manager,
    ROLE_VENDOR: Vendor,
    ROLE_CASHIER: Cashier,
}


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
    verifie: bool | None = None,
    raison_desactivation: str | None = None,
):
    caller_role = getattr(getattr(caller_user, "user_role", None), "role", None)

    if caller_role not in (ROLE_ADMIN, ROLE_MANAGER):
        raise PermissionError("Accès réservé aux rôles admin et manager.")

    Model = ROLE_MODEL_MAP.get(target_role)
    if not Model:
        raise ValueError("Rôle invalide.")

    staff = (
        Model.objects
        .select_for_update()
        .select_related("user", "bijouterie")
        .filter(pk=staff_id)
        .first()
    )
    if not staff:
        raise ValueError("Staff introuvable.")

    # ---------- restrictions manager ----------
    if caller_role == ROLE_MANAGER:
        caller_manager = (
            Manager.objects
            .select_related("bijouterie")
            .filter(user=caller_user)
            .first()
        )
        caller_bj_id = getattr(getattr(caller_manager, "bijouterie", None), "id", None)

        if target_role == ROLE_MANAGER:
            raise PermissionError("Un manager ne peut pas modifier un autre manager.")

        if not caller_bj_id or staff.bijouterie_id != caller_bj_id:
            raise PermissionError("Vous ne pouvez modifier que les staff de votre bijouterie.")

        if bijouterie is not None and bijouterie.id != caller_bj_id:
            raise PermissionError("Un manager ne peut affecter un staff qu'à sa propre bijouterie.")

    user = staff.user
    user_fields = []
    staff_fields = []

    # ---------- user ----------
    if email is not None and user and user.email != email:
        user.email = email
        user_fields.append("email")

    if first_name is not None and user and user.first_name != first_name:
        user.first_name = first_name
        user_fields.append("first_name")

    if last_name is not None and user and user.last_name != last_name:
        user.last_name = last_name
        user_fields.append("last_name")

    if user_fields:
        user.save(update_fields=user_fields)

    # ---------- staff ----------
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
    
    
