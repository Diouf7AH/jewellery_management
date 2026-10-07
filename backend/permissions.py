# backend/permissions.py

from __future__ import annotations

from rest_framework.permissions import BasePermission

from backend.bijouteries import user_has_bijouterie_access
from backend.roles import (ROLE_ADMIN, ROLE_BUYER, ROLE_CASHIER, ROLE_MANAGER,
                           ROLE_VENDOR, get_role_name, has_role)

# ============================================================
# Helpers internes
# ============================================================


def _verified(profile) -> bool:
    """
    Retourne True uniquement si le profil staff existe
    et est actif/vérifié.
    """
    return bool(
        profile
        and getattr(profile, "verifie", False)
    )


def _user_is_authenticated(user) -> bool:
    """
    Vérifie que le compte utilisateur est authentifié
    et actif.
    """
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
    )


def _role_is(user, *roles: str) -> bool:
    """
    Vérifie que l'utilisateur est authentifié/actif
    et possède l'un des rôles demandés.
    """
    if not _user_is_authenticated(user):
        return False

    return has_role(user, *roles)


def _manager_profile(user):
    profile = getattr(
        user,
        "staff_manager_profile",
        None,
    )

    return profile if _verified(profile) else None


def _vendor_profile(user):
    profile = getattr(
        user,
        "staff_vendor_profile",
        None,
    )

    return profile if _verified(profile) else None


def _cashier_profile(user):
    profile = getattr(
        user,
        "staff_cashier_profile",
        None,
    )

    return profile if _verified(profile) else None


def _buyer_profile(user):
    profile = getattr(
        user,
        "staff_buyer_profile",
        None,
    )

    return profile if _verified(profile) else None


# ============================================================
# Permissions simples
# ============================================================


class IsAdmin(BasePermission):
    """
    Administrateur uniquement.
    """

    message = "Accès réservé aux administrateurs."

    def has_permission(self, request, view):
        return _role_is(
            request.user,
            ROLE_ADMIN,
        )


class IsManager(BasePermission):
    """
    Manager actif/vérifié uniquement.
    """

    message = "Accès réservé au rôle manager."

    def has_permission(self, request, view):
        user = request.user

        if not _role_is(
            user,
            ROLE_MANAGER,
        ):
            return False

        return bool(
            _manager_profile(user)
        )



class IsVendor(BasePermission):
    """
    Vendeur actif/vérifié et rattaché
    à une bijouterie.
    """

    message = "Accès réservé au rôle vendeur."

    def has_permission(self, request, view):
        user = request.user

        if not _role_is(
            user,
            ROLE_VENDOR,
        ):
            return False

        vendor = _vendor_profile(user)

        return bool(
            vendor
            and getattr(
                vendor,
                "bijouterie_id",
                None,
            )
        )

class IsCashierOnly(BasePermission):
    """
    Caissier actif/vérifié et rattaché
    à une bijouterie.
    """

    message = "Accès réservé au rôle caissier."

    def has_permission(self, request, view):
        user = request.user

        if not _role_is(
            user,
            ROLE_CASHIER,
        ):
            return False

        cashier = _cashier_profile(user)

        return bool(
            cashier
            and getattr(
                cashier,
                "bijouterie_id",
                None,
            )
        )


class IsBuyer(BasePermission):
    """
    Responsable rachat actif/vérifié.
    """

    message = "Accès réservé au responsable des rachats."

    def has_permission(self, request, view):
        user = request.user

        if not _role_is(
            user,
            ROLE_BUYER,
        ):
            return False

        return bool(
            _buyer_profile(user)
        )


# ============================================================
# Permissions combinées
# ============================================================


class IsAdminOrManager(BasePermission):
    """
    Admin ou manager actif/vérifié.
    """

    message = "Accès réservé aux rôles admin ou manager."

    def has_permission(self, request, view):
        user = request.user

        if not _user_is_authenticated(user):
            return False

        role = get_role_name(user)

        if role == ROLE_ADMIN:
            return True

        if role == ROLE_MANAGER:
            return bool(
                _manager_profile(user)
            )

        return False


class IsAdminManagerVendor(BasePermission):
    """
    Admin, manager ou vendeur.
    Les profils staff doivent être actifs/vérifiés.
    """

    message = (
        "Accès réservé aux rôles "
        "admin, manager ou vendeur."
    )

    def has_permission(self, request, view):
        user = request.user

        if not _user_is_authenticated(user):
            return False

        role = get_role_name(user)

        if role == ROLE_ADMIN:
            return True

        if role == ROLE_MANAGER:
            return bool(
                _manager_profile(user)
            )

        if role == ROLE_VENDOR:
            vendor = _vendor_profile(user)

            return bool(
                vendor
                and getattr(
                    vendor,
                    "bijouterie_id",
                    None,
                )
            )

        return False



class IsAdminOrManagerOrVendor(IsAdminManagerVendor):
    """
    Alias compatible avec les anciennes vues.

    Autorise :
    - ADMIN
    - MANAGER actif/vérifié
    - VENDOR actif/vérifié et rattaché à une bijouterie
    """

    message = (
        "Accès réservé aux rôles "
        "admin, manager ou vendeur."
    )


class IsAdminManagerVendorCashier(BasePermission):
    """
    Admin, manager, vendeur ou caissier.
    Les profils staff doivent être actifs/vérifiés.
    """

    message = (
        "Accès réservé aux rôles admin, manager, "
        "vendeur ou caissier."
    )

    def has_permission(self, request, view):
        user = request.user

        if not _user_is_authenticated(user):
            return False

        role = get_role_name(user)

        if role == ROLE_ADMIN:
            return True

        if role == ROLE_MANAGER:
            return bool(
                _manager_profile(user)
            )

        if role == ROLE_VENDOR:
            vendor = _vendor_profile(user)

            return bool(
                vendor
                and getattr(
                    vendor,
                    "bijouterie_id",
                    None,
                )
            )

        if role == ROLE_CASHIER:
            cashier = _cashier_profile(user)

            return bool(
                cashier
                and getattr(
                    cashier,
                    "bijouterie_id",
                    None,
                )
            )

        return False


class IsAdminManagerBuyer(BasePermission):
    """
    Admin, manager ou responsable rachat.
    """

    message = (
        "Accès réservé aux rôles admin, manager "
        "ou responsable rachat."
    )

    def has_permission(self, request, view):
        user = request.user

        if not _user_is_authenticated(user):
            return False

        role = get_role_name(user)

        if role == ROLE_ADMIN:
            return True

        if role == ROLE_MANAGER:
            return bool(
                _manager_profile(user)
            )

        if role == ROLE_BUYER:
            return bool(
                _buyer_profile(user)
            )

        return False


# ============================================================
# Permissions métier - Vente
# ============================================================


class CanCreateSale(BasePermission):
    """
    Autorise la création d'une vente.

    ADMIN
        Autorisé.

    MANAGER
        Autorisé si profil manager actif/vérifié.

    VENDOR
        Autorisé si profil vendeur actif/vérifié
        et rattaché à une bijouterie.

    CASHIER / BUYER
        Non autorisés.
    """

    message = "Vous n'êtes pas autorisé à créer une vente."

    def has_permission(self, request, view):
        user = request.user

        if not _user_is_authenticated(user):
            return False

        role = get_role_name(user)

        # ----------------------------------------------------
        # ADMIN
        # ----------------------------------------------------

        if role == ROLE_ADMIN:
            return True

        # ----------------------------------------------------
        # MANAGER
        # ----------------------------------------------------

        if role == ROLE_MANAGER:
            return bool(
                _manager_profile(user)
            )

        # ----------------------------------------------------
        # VENDOR
        # ----------------------------------------------------

        if role == ROLE_VENDOR:
            vendor = _vendor_profile(user)

            return bool(
                vendor
                and getattr(
                    vendor,
                    "bijouterie_id",
                    None,
                )
            )

        return False


# ============================================================
# Permissions métier - Paiement facture
# ============================================================


class CanProcessInvoicePayment(BasePermission):
    """
    Autorise l'encaissement d'une facture.

    ADMIN
        Autorisé.

    MANAGER
        Autorisé si profil manager actif/vérifié.

    CASHIER
        Autorisé si profil caissier actif/vérifié
        et rattaché à une bijouterie.

    VENDOR / BUYER
        Non autorisés.
    """

    message = (
        "Vous n'êtes pas autorisé "
        "à enregistrer un paiement."
    )

    def has_permission(self, request, view):
        user = request.user

        if not _user_is_authenticated(user):
            return False

        role = get_role_name(user)

        # ----------------------------------------------------
        # ADMIN
        # ----------------------------------------------------

        if role == ROLE_ADMIN:
            return True

        # ----------------------------------------------------
        # MANAGER
        # ----------------------------------------------------

        if role == ROLE_MANAGER:
            return bool(
                _manager_profile(user)
            )

        # ----------------------------------------------------
        # CASHIER
        # ----------------------------------------------------

        if role == ROLE_CASHIER:
            cashier = _cashier_profile(user)

            return bool(
                cashier
                and getattr(
                    cashier,
                    "bijouterie_id",
                    None,
                )
            )

        return False


# ============================================================
# Permission générique par bijouterie
# ============================================================


class HasBijouterieAccess(BasePermission):
    """
    Permission objet permettant de vérifier qu'un utilisateur
    possède l'accès à la bijouterie portée par l'objet.

    La vue peut définir :

        bijouterie_field = "bijouterie_id"

    ou par exemple :

        bijouterie_field = "vente.bijouterie_id"
    """

    message = (
        "Vous n'avez pas accès à cette bijouterie."
    )

    def has_permission(self, request, view):
        return _user_is_authenticated(
            request.user
        )

    def has_object_permission(
        self,
        request,
        view,
        obj,
    ):
        field = getattr(
            view,
            "bijouterie_field",
            "bijouterie_id",
        )

        value = obj

        for part in field.split("."):
            value = getattr(
                value,
                part,
                None,
            )

            if value is None:
                return False

        return user_has_bijouterie_access(
            request.user,
            value,
        )
        


class IsSameBijouterieOrAdmin(BasePermission):
    """
    Autorise :

    - ADMIN :
        accès à toutes les bijouteries.

    - autres rôles autorisés par la vue :
        accès uniquement aux objets appartenant
        à une bijouterie à laquelle l'utilisateur
        a accès.

    Cette permission est principalement une
    permission objet.

    La vue peut définir :

        bijouterie_field = "bijouterie_id"

    ou :

        bijouterie_field = "bijouterie"

    ou encore :

        bijouterie_field = "stock.bijouterie_id"
    """

    message = (
        "Vous n'êtes pas autorisé à accéder "
        "aux données de cette bijouterie."
    )

    def has_permission(self, request, view):
        """
        À ce niveau on vérifie seulement que
        l'utilisateur est authentifié et actif.

        La permission métier principale
        (ex: IsAdminManagerBuyer) détermine
        quels rôles sont autorisés.
        """

        return _user_is_authenticated(
            request.user
        )

    def has_object_permission(
        self,
        request,
        view,
        obj,
    ):
        user = request.user

        if not _user_is_authenticated(user):
            return False

        role = get_role_name(user)

        # ====================================================
        # ADMIN
        # ====================================================

        if role == ROLE_ADMIN:
            return True

        # ====================================================
        # Récupération bijouterie de l'objet
        # ====================================================

        field = getattr(
            view,
            "bijouterie_field",
            "bijouterie_id",
        )

        value = obj

        for part in field.split("."):
            value = getattr(
                value,
                part,
                None,
            )

            if value is None:
                return False

        # ----------------------------------------------------
        # Le champ peut retourner :
        #
        #   bijouterie_id -> int
        #
        # ou :
        #
        #   bijouterie -> instance Bijouterie
        # ----------------------------------------------------

        bijouterie_id = getattr(
            value,
            "id",
            value,
        )

        if not bijouterie_id:
            return False

        return user_has_bijouterie_access(
            user,
            bijouterie_id,
        )
        