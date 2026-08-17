# backend/permissions.py
from __future__ import annotations

from typing import Optional

from rest_framework.permissions import BasePermission

from backend.roles import (ROLE_ADMIN, ROLE_BUYER, ROLE_CASHIER, ROLE_MANAGER,
                           ROLE_VENDOR, get_role_name)


def _verified(profile) -> bool:
    """
    Retourne True uniquement lorsque le profil existe
    et possède verifie=True.
    """

    return bool(
        profile
        and getattr(profile, "verifie", False)
    )


def _manager_profile(user):
    """
    Retourne le profil manager vérifié.
    """

    profile = getattr(
        user,
        "staff_manager_profile",
        None,
    )

    return profile if _verified(profile) else None


def _vendor_profile(user):
    """
    Retourne le profil vendeur vérifié.
    """

    profile = getattr(
        user,
        "staff_vendor_profile",
        None,
    )

    return profile if _verified(profile) else None


def _cashier_profile(user):
    """
    Retourne le profil caissier vérifié.
    """

    profile = getattr(
        user,
        "staff_cashier_profile",
        None,
    )

    return profile if _verified(profile) else None


def _buyer_profile(user):
    """
    Retourne le profil responsable rachat vérifié.
    """

    profile = getattr(
        user,
        "staff_buyer_profile",
        None,
    )

    return profile if _verified(profile) else None


def _obj_bijouterie_id(obj) -> Optional[int]:
    """
    Essaie d'obtenir l'identifiant de la bijouterie
    depuis différents types d'objets.

    Compatible notamment avec :
    - Bijouterie ;
    - Vente ;
    - Facture ;
    - Paiement ;
    - VendorStock ;
    - InventoryMovement ;
    - objets liés à une vente ou une facture.
    """

    if obj is None:
        return None

    direct_id = getattr(
        obj,
        "bijouterie_id",
        None,
    )

    if direct_id:
        return direct_id

    bijouterie = getattr(
        obj,
        "bijouterie",
        None,
    )

    if bijouterie and getattr(
        bijouterie,
        "pk",
        None,
    ):
        return bijouterie.pk

    vente = getattr(
        obj,
        "vente",
        None,
    )

    if vente:
        vente_bijouterie_id = getattr(
            vente,
            "bijouterie_id",
            None,
        )

        if vente_bijouterie_id:
            return vente_bijouterie_id

    facture = getattr(
        obj,
        "facture",
        None,
    )

    if facture:
        facture_bijouterie_id = getattr(
            facture,
            "bijouterie_id",
            None,
        )

        if facture_bijouterie_id:
            return facture_bijouterie_id

        facture_vente = getattr(
            facture,
            "vente",
            None,
        )

        if facture_vente:
            facture_vente_bijouterie_id = getattr(
                facture_vente,
                "bijouterie_id",
                None,
            )

            if facture_vente_bijouterie_id:
                return facture_vente_bijouterie_id

    vendor = getattr(
        obj,
        "vendor",
        None,
    )

    if vendor:
        vendor_bijouterie_id = getattr(
            vendor,
            "bijouterie_id",
            None,
        )

        if vendor_bijouterie_id:
            return vendor_bijouterie_id

    src_bijouterie_id = getattr(
        obj,
        "src_bijouterie_id",
        None,
    )

    dst_bijouterie_id = getattr(
        obj,
        "dst_bijouterie_id",
        None,
    )

    if src_bijouterie_id and dst_bijouterie_id:
        if src_bijouterie_id == dst_bijouterie_id:
            return src_bijouterie_id

    return (
        src_bijouterie_id
        or dst_bijouterie_id
        or None
    )


def _obj_owner_user_id(obj) -> Optional[int]:
    """
    Essaie de retrouver l'utilisateur propriétaire
    d'un objet.

    Cette fonction est principalement utilisée pour
    limiter un vendeur à ses propres données.
    """

    if obj is None:
        return None

    direct_user_id = getattr(
        obj,
        "user_id",
        None,
    )

    if direct_user_id:
        return direct_user_id

    direct_user = getattr(
        obj,
        "user",
        None,
    )

    if direct_user and getattr(
        direct_user,
        "pk",
        None,
    ):
        return direct_user.pk

    vendor = getattr(
        obj,
        "vendor",
        None,
    )

    if vendor:
        vendor_user_id = getattr(
            vendor,
            "user_id",
            None,
        )

        if vendor_user_id:
            return vendor_user_id

        vendor_user = getattr(
            vendor,
            "user",
            None,
        )

        if vendor_user and getattr(
            vendor_user,
            "pk",
            None,
        ):
            return vendor_user.pk

    vente = getattr(
        obj,
        "vente",
        None,
    )

    if vente:
        vente_vendor = getattr(
            vente,
            "vendor",
            None,
        )

        if vente_vendor:
            vente_vendor_user_id = getattr(
                vente_vendor,
                "user_id",
                None,
            )

            if vente_vendor_user_id:
                return vente_vendor_user_id

            vente_vendor_user = getattr(
                vente_vendor,
                "user",
                None,
            )

            if vente_vendor_user and getattr(
                vente_vendor_user,
                "pk",
                None,
            ):
                return vente_vendor_user.pk

    facture = getattr(
        obj,
        "facture",
        None,
    )

    if facture:
        facture_vente = getattr(
            facture,
            "vente",
            None,
        )

        if facture_vente:
            facture_vendor = getattr(
                facture_vente,
                "vendor",
                None,
            )

            if facture_vendor:
                facture_vendor_user_id = getattr(
                    facture_vendor,
                    "user_id",
                    None,
                )

                if facture_vendor_user_id:
                    return facture_vendor_user_id

                facture_vendor_user = getattr(
                    facture_vendor,
                    "user",
                    None,
                )

                if facture_vendor_user and getattr(
                    facture_vendor_user,
                    "pk",
                    None,
                ):
                    return facture_vendor_user.pk

    return None


def _manager_has_bijouterie(
    user,
    bijouterie_id: int,
) -> bool:
    """
    Vérifie qu'un manager vérifié gère la bijouterie.
    """

    if not bijouterie_id:
        return False

    manager = _manager_profile(user)

    if manager is None:
        return False

    return manager.bijouteries.filter(
        pk=bijouterie_id
    ).exists()


def _user_is_authenticated(user) -> bool:
    """
    Vérifie proprement l'authentification.
    """

    return bool(
        user
        and getattr(user, "is_authenticated", False)
    )


# ============================================================
# Permissions simples
# ============================================================

def _role_is(
    user,
    *roles: str,
) -> bool:
    if not _user_is_authenticated(user):
        return False

    return get_role_name(user) in roles

# class IsAdminOnly(BasePermission):
#     """
#     Accès réservé à l'administrateur.
#     """

#     message = "Accès réservé au rôle admin."

#     def has_permission(self, request, view):
#         return _role_is(
#             request.user,
#             ROLE_ADMIN,
#         )

class IsAdmin(BasePermission):
    """
    Autorise uniquement les administrateurs.
    """

    message = "Accès réservé aux administrateurs."

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        return get_role_name(user) == ROLE_ADMIN


class IsManager(BasePermission):
    """
    Accès réservé au manager.
    """

    message = "Accès réservé au rôle manager."

    def has_permission(self, request, view):
        return _role_is(
            request.user,
            ROLE_MANAGER,
        )


class IsVendor(BasePermission):
    """
    Accès réservé au vendeur.
    """

    message = "Accès réservé au rôle vendeur."

    def has_permission(self, request, view):
        return _role_is(
            request.user,
            ROLE_VENDOR,
        )
        

class IsCashierOnly(BasePermission):
    """
    Accès strictement réservé au caissier.
    """

    message = "Accès réservé au rôle caissier."

    def has_permission(self, request, view):
        return _role_is(
            request.user,
            ROLE_CASHIER,
        )

class IsBuyer(BasePermission):
    """
    Accès réservé au responsable des rachats.
    """

    message = "Accès réservé au responsable des rachats."

    def has_permission(self, request, view):
        return _role_is(
            request.user,
            ROLE_BUYER,
        )


class IsAdminOrManager(BasePermission):
    """
    Accès réservé à l'admin ou au manager.
    """

    message = "Accès réservé aux rôles admin ou manager."

    def has_permission(self, request, view):
        return _role_is(
            request.user,
            ROLE_ADMIN,
            ROLE_MANAGER,
        )


class IsAdminManagerVendor(BasePermission):
    """
    Accès réservé à :
    - admin ;
    - manager ;
    - vendor.
    """

    message = (
        "Accès réservé aux rôles "
        "admin, manager ou vendeur."
    )

    def has_permission(self, request, view):
        return _role_is(
            request.user,
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_VENDOR,
        )

class IsAdminManagerVendorCashier(BasePermission):
    """
    Accès réservé à :
    - admin ;
    - manager ;
    - vendor ;
    - cashier.
    """

    message = (
        "Accès réservé aux rôles admin, manager, "
        "vendeur ou caissier."
    )

    def has_permission(self, request, view):
        return _role_is(
            request.user,
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_VENDOR,
            ROLE_CASHIER,
        )


class IsAdminManagerBuyer(BasePermission):
    """
    Accès réservé à :
    - admin ;
    - manager ;
    - buyer.
    """

    message = (
        "Accès réservé aux rôles admin, manager "
        "ou responsable rachat."
    )

    def has_permission(self, request, view):
        return _role_is(
            request.user,
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_BUYER,
        )
        

class CanCreateSale(BasePermission):
    """
    Autorise la création d'une vente à :
    - admin ;
    - manager ;
    - vendor.
    """

    message = (
        "Seuls admin, manager ou vendeur "
        "peuvent créer une vente."
    )

    def has_permission(self, request, view):
        return _role_is(
            request.user,
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_VENDOR,
        )
        

class CanProcessInvoicePayment(BasePermission):
    """
    Autorise le paiement d'une facture.

    Rôles autorisés :
    - manager ;
    - cashier.
    """

    message = (
        "Seuls le manager ou le caissier "
        "peuvent réaliser un paiement."
    )

    def has_permission(self, request, view):
        return _role_is(
            request.user,
            ROLE_MANAGER,
            ROLE_CASHIER,
        )
# ============================================================

# ============================================================
# Object-level : vendeur propriétaire
# ============================================================

class IsAdminOrManagerOrVendor(BasePermission):
    """
    Permission générale :

    - Admin :
        accès autorisé.

    - Manager :
        accès autorisé uniquement aux objets appartenant
        à ses bijouteries.

    - Vendor :
        accès autorisé uniquement aux objets qui lui
        appartiennent.

    Important :
    Cette permission ne filtre pas automatiquement
    les listes. Le queryset doit également être limité.
    """

    message = (
        "Accès réservé aux administrateurs, managers "
        "ou au vendeur propriétaire."
    )

    def has_permission(self, request, view):
        return _role_is(
            request.user,
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_VENDOR,
        )

    def has_object_permission(
        self,
        request,
        view,
        obj,
    ):
        role = get_role_name(request.user)

        if role == ROLE_ADMIN:
            return True

        if role == ROLE_MANAGER:
            bijouterie_id = _obj_bijouterie_id(obj)

            return bool(
                bijouterie_id
                and _manager_has_bijouterie(
                    request.user,
                    bijouterie_id,
                )
            )

        if role == ROLE_VENDOR:
            owner_user_id = _obj_owner_user_id(obj)

            return bool(
                owner_user_id
                and owner_user_id == request.user.id
            )

        return False


# ============================================================
# Object-level : scope bijouterie générique
# ============================================================

class IsSameBijouterieOrAdmin(BasePermission):
    """
    Autorise l'accès si l'objet appartient au périmètre
    de l'utilisateur.

    - Admin :
        toutes les bijouteries.

    - Manager :
        une des bijouteries gérées.

    - Vendor :
        sa bijouterie.

    - Cashier :
        sa bijouterie.

    - Buyer :
        sa bijouterie.

    Cette permission est générique et ne doit pas vérifier
    le propriétaire d'une Vente.
    """

    message = "Objet hors de votre périmètre de bijouterie."

    def has_permission(self, request, view):
        return _role_is(
            request.user,
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_VENDOR,
            ROLE_CASHIER,
            ROLE_BUYER,
        )

    def has_object_permission(
        self,
        request,
        view,
        obj,
    ):
        role = get_role_name(request.user)

        if role == ROLE_ADMIN:
            return True

        bijouterie_id = _obj_bijouterie_id(obj)

        if not bijouterie_id:
            return False

        if role == ROLE_MANAGER:
            return _manager_has_bijouterie(
                request.user,
                bijouterie_id,
            )

        if role == ROLE_VENDOR:
            vendor = _vendor_profile(
                request.user
            )

            return bool(
                vendor
                and vendor.bijouterie_id
                == bijouterie_id
            )

        if role == ROLE_CASHIER:
            cashier = _cashier_profile(
                request.user
            )

            return bool(
                cashier
                and cashier.bijouterie_id
                == bijouterie_id
            )

        if role == ROLE_BUYER:
            buyer = _buyer_profile(
                request.user
            )

            return bool(
                buyer
                and buyer.bijouterie_id
                == bijouterie_id
            )

        return False


# ============================================================
# Object-level : ventes
# ============================================================
class IsSameBijouterieForVenteOrAdmin(BasePermission):
    """
    Permission destinée aux objets Vente.

    Règles :
    - admin : toutes les ventes ;
    - manager : ventes de ses bijouteries ;
    - vendor : uniquement ses propres ventes ;
    - cashier : ventes de sa bijouterie ;
    - buyer : aucun accès.
    """

    message = "Vente hors de votre périmètre."

    def has_permission(self, request, view):
        return _role_is(
            request.user,
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_VENDOR,
            ROLE_CASHIER,
        )

    def has_object_permission(
        self,
        request,
        view,
        vente,
    ):
        role = get_role_name(request.user)

        if role == ROLE_ADMIN:
            return True

        bijouterie_id = getattr(
            vente,
            "bijouterie_id",
            None,
        )

        if not bijouterie_id:
            return False

        if role == ROLE_MANAGER:
            return _manager_has_bijouterie(
                request.user,
                bijouterie_id,
            )

        if role == ROLE_VENDOR:
            vendor = _vendor_profile(
                request.user
            )

            return bool(
                vendor
                and vendor.bijouterie_id == bijouterie_id
                and getattr(
                    vente,
                    "vendor_id",
                    None,
                ) == vendor.id
            )

        if role == ROLE_CASHIER:
            cashier = _cashier_profile(
                request.user
            )

            return bool(
                cashier
                and cashier.bijouterie_id == bijouterie_id
            )

        return False
    


