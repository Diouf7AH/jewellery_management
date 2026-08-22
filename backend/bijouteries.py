# backend/bijouteries.py

from backend.roles import (ROLE_ADMIN, ROLE_BUYER, ROLE_CASHIER, ROLE_MANAGER,
                           ROLE_VENDOR, get_role_name)
from store.models import Bijouterie


def get_user_bijouteries(user):
    """
    Retourne les bijouteries accessibles par l'utilisateur.

    - admin   : toutes les bijouteries ;
    - manager : ses bijouteries ;
    - cashier : sa bijouterie ;
    - vendor  : sa bijouterie ;
    - buyer   : sa bijouterie.
    """

    if not user or not user.is_authenticated:
        return Bijouterie.objects.none()

    role = get_role_name(user)

    if role == ROLE_ADMIN:
        return Bijouterie.objects.all().order_by("nom")

    if role == ROLE_MANAGER:
        manager = getattr(
            user,
            "staff_manager_profile",
            None,
        )

        if (
            not manager
            or not getattr(manager, "verifie", False)
        ):
            return Bijouterie.objects.none()

        return manager.bijouteries.all().order_by("nom")

    if role == ROLE_CASHIER:
        cashier = getattr(
            user,
            "staff_cashier_profile",
            None,
        )

        if (
            not cashier
            or not getattr(cashier, "verifie", False)
            or not cashier.bijouterie_id
        ):
            return Bijouterie.objects.none()

        return Bijouterie.objects.filter(
            pk=cashier.bijouterie_id
        )

    if role == ROLE_VENDOR:
        vendor = getattr(
            user,
            "staff_vendor_profile",
            None,
        )

        if (
            not vendor
            or not getattr(vendor, "verifie", False)
            or not vendor.bijouterie_id
        ):
            return Bijouterie.objects.none()

        return Bijouterie.objects.filter(
            pk=vendor.bijouterie_id
        )

    if role == ROLE_BUYER:
        buyer = getattr(
            user,
            "staff_buyer_profile",
            None,
        )

        if (
            not buyer
            or not getattr(buyer, "verifie", False)
            or not buyer.bijouterie_id
        ):
            return Bijouterie.objects.none()

        return Bijouterie.objects.filter(
            pk=buyer.bijouterie_id
        )

    return Bijouterie.objects.none()

