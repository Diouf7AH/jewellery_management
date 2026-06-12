def resolve_bijouterie_for_user(user):
    from backend.roles import (ROLE_CASHIER, ROLE_MANAGER, ROLE_VENDOR,
                               get_role_name)

    role = get_role_name(user)

    # VENDOR
    if role == ROLE_VENDOR:
        vendor_profile = getattr(user, "staff_vendor_profile", None)

        if vendor_profile and vendor_profile.bijouterie:
            return vendor_profile.bijouterie

    # CASHIER
    if role == ROLE_CASHIER:
        cashier_profile = getattr(user, "staff_cashier_profile", None)

        if cashier_profile and cashier_profile.bijouterie:
            return cashier_profile.bijouterie

    # MANAGER
    if role == ROLE_MANAGER:
        manager_profile = getattr(user, "staff_manager_profile", None)

        if manager_profile:
            return manager_profile.bijouteries.first()

    return None


def user_can_access_bijouterie(user, bijouterie):
    from backend.roles import (ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER,
                               ROLE_VENDOR, get_role_name)

    role = get_role_name(user)

    if role == ROLE_ADMIN:
        return True

    if not bijouterie:
        return False

    if role == ROLE_CASHIER:
        cashier_profile = getattr(user, "staff_cashier_profile", None)
        return bool(cashier_profile and cashier_profile.bijouterie_id == bijouterie.id)

    if role == ROLE_VENDOR:
        vendor_profile = getattr(user, "staff_vendor_profile", None)
        return bool(vendor_profile and vendor_profile.bijouterie_id == bijouterie.id)

    if role == ROLE_MANAGER:
        manager_profile = getattr(user, "staff_manager_profile", None)
        return bool(
            manager_profile
            and manager_profile.bijouteries.filter(id=bijouterie.id).exists()
        )

    return False

