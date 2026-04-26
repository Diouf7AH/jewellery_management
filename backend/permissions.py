# backend/permissions.py
from __future__ import annotations

from typing import Optional

from rest_framework.permissions import BasePermission

from backend.roles import (ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER, ROLE_VENDOR,
                           get_role_name)

# ============================================================
# Helpers locaux
# ============================================================

def _verified(profile) -> bool:
    return bool(profile and getattr(profile, "verifie", True))


def _manager_profile(user):
    p = getattr(user, "staff_manager_profile", None)
    return p if _verified(p) else None


def _vendor_profile(user):
    p = getattr(user, "staff_vendor_profile", None)
    return p if _verified(p) else None


def _cashier_profile(user):
    p = getattr(user, "staff_cashier_profile", None)
    return p if _verified(p) else None


def _obj_bijouterie_id(obj) -> Optional[int]:
    """
    Essaie d'obtenir bijouterie_id depuis différents objets.
    Compatible avec Vente, Facture, Paiement, VendorStock, etc.
    """
    bj_id = getattr(obj, "bijouterie_id", None)
    if bj_id:
        return bj_id

    bj = getattr(obj, "bijouterie", None)
    if bj and getattr(bj, "id", None):
        return bj.id

    vente = getattr(obj, "vente", None)
    if vente and getattr(vente, "bijouterie_id", None):
        return vente.bijouterie_id

    facture = getattr(obj, "facture", None)
    if facture and getattr(facture, "bijouterie_id", None):
        return facture.bijouterie_id

    vendor = getattr(obj, "vendor", None)
    if vendor and getattr(vendor, "bijouterie_id", None):
        return vendor.bijouterie_id

    return None


def _obj_owner_user_id(obj) -> Optional[int]:
    """
    Essaie de retrouver le user propriétaire de l'objet.
    Utile pour limiter un vendor à ses propres données.
    """
    uid = getattr(obj, "user_id", None)
    if uid:
        return uid

    u = getattr(obj, "user", None)
    if u and getattr(u, "id", None):
        return u.id

    v = getattr(obj, "vendor", None)
    if v and getattr(v, "user_id", None):
        return v.user_id
    if v and getattr(getattr(v, "user", None), "id", None):
        return v.user.id

    vente = getattr(obj, "vente", None)
    if vente:
        vv = getattr(vente, "vendor", None)
        if vv and getattr(vv, "user_id", None):
            return vv.user_id
        if vv and getattr(getattr(vv, "user", None), "id", None):
            return vv.user.id

    facture = getattr(obj, "facture", None)
    if facture:
        vente = getattr(facture, "vente", None)
        if vente:
            vv = getattr(vente, "vendor", None)
            if vv and getattr(vv, "user_id", None):
                return vv.user_id
            if vv and getattr(getattr(vv, "user", None), "id", None):
                return vv.user.id

    return None


def _manager_has_bijouterie(user, bijouterie_id: int) -> bool:
    """
    Manager -> ManyToMany bijouteries
    """
    mp = _manager_profile(user)
    if not mp:
        return False
    return mp.bijouteries.filter(id=bijouterie_id).exists()


# ============================================================
# Permissions simples
# ============================================================

class IsAdmin(BasePermission):
    message = "Accès réservé au rôle admin."

    def has_permission(self, request, view):
        return get_role_name(request.user) == ROLE_ADMIN


class IsManager(BasePermission):
    message = "Accès réservé au rôle manager."

    def has_permission(self, request, view):
        return get_role_name(request.user) == ROLE_MANAGER


class IsVendor(BasePermission):
    message = "Accès réservé au rôle vendeur."

    def has_permission(self, request, view):
        return get_role_name(request.user) == ROLE_VENDOR


class IsCashierOnly(BasePermission):
    message = "Seul un caissier peut effectuer un paiement."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and get_role_name(user) == ROLE_CASHIER)


class IsAdminOrManager(BasePermission):
    message = "Accès réservé aux rôles admin/manager."

    def has_permission(self, request, view):
        return get_role_name(request.user) in {ROLE_ADMIN, ROLE_MANAGER}


class IsAdminManagerVendorCashier(BasePermission):
    message = "Accès réservé (admin/manager/vendor/cashier)."

    def has_permission(self, request, view):
        return get_role_name(request.user) in {
            ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR, ROLE_CASHIER
        }


class CanCreateSale(BasePermission):
    message = "Seuls admin, manager ou vendor peuvent créer une vente."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return get_role_name(user) in {ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR}


# ============================================================
# Object-level : ownership vendor
# ============================================================

class IsAdminOrManagerOrVendor(BasePermission):
    """
    - Admin/Manager : accès total
    - Vendor : uniquement si l'objet appartient à son user
    """
    message = "Accès réservé aux admin/manager ou au vendeur propriétaire."

    def has_permission(self, request, view):
        role = get_role_name(request.user)
        return role in {ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR}

    def has_object_permission(self, request, view, obj):
        role = get_role_name(request.user)

        if role in {ROLE_ADMIN, ROLE_MANAGER}:
            return True

        if role == ROLE_VENDOR:
            owner_user_id = _obj_owner_user_id(obj)
            return bool(owner_user_id and owner_user_id == request.user.id)

        return False


# ============================================================
# Object-level : scope bijouterie
# ============================================================

class IsSameBijouterieOrAdmin(BasePermission):
    """
    Autorise si l'objet est dans le scope bijouterie du user :
    - Admin   : toujours OK
    - Manager : obj.bijouterie_id ∈ manager.bijouteries
    - Vendor  : obj.bijouterie_id == vendor.bijouterie_id
    - Cashier : obj.bijouterie_id == cashier.bijouterie_id
    """
    message = "Objet hors de votre bijouterie."

    def has_permission(self, request, view):
        return get_role_name(request.user) in {
            ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR, ROLE_CASHIER
        }

    def has_object_permission(self, request, view, obj):
        role = get_role_name(request.user)

        if role == ROLE_ADMIN:
            return True

        obj_bj_id = _obj_bijouterie_id(obj)
        if not obj_bj_id:
            return False

        if role == ROLE_MANAGER:
            return _manager_has_bijouterie(request.user, obj_bj_id)

        if role == ROLE_VENDOR:
            vp = _vendor_profile(request.user)
            return bool(vp and vp.bijouterie_id == obj_bj_id)

        if role == ROLE_CASHIER:
            cp = _cashier_profile(request.user)
            return bool(cp and cp.bijouterie_id == obj_bj_id)

        return False


class IsSameBijouterieForVenteOrAdmin(BasePermission):
    """
    Variante optimisée pour Vente, où vente.bijouterie_id est direct.
    """
    message = "⛔ Vente hors de votre bijouterie."

    def has_permission(self, request, view):
        return get_role_name(request.user) in {
            ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR, ROLE_CASHIER
        }

    def has_object_permission(self, request, view, vente):
        role = get_role_name(request.user)

        if role == ROLE_ADMIN:
            return True

        vente_bj_id = getattr(vente, "bijouterie_id", None)
        if not vente_bj_id:
            return False

        if role == ROLE_MANAGER:
            return _manager_has_bijouterie(request.user, vente_bj_id)

        if role == ROLE_VENDOR:
            vp = _vendor_profile(request.user)
            return bool(vp and vp.bijouterie_id == vente_bj_id)

        if role == ROLE_CASHIER:
            cp = _cashier_profile(request.user)
            return bool(cp and cp.bijouterie_id == vente_bj_id)

        return False
    
    

