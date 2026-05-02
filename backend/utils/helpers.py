def resolve_bijouterie_for_user(user):
    """
    Retourne la bijouterie liée à l'utilisateur selon son rôle.
    """

    from backend.roles import (ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER,
                               ROLE_VENDOR, get_role_name)

    role = get_role_name(user)

    # ADMIN → pas de restriction (tu peux retourner None)
    if role == ROLE_ADMIN:
        return None

    # VENDOR → 1 seule bijouterie
    if role == ROLE_VENDOR:
        vendor_profile = getattr(user, "staff_vendor_profile", None)
        if vendor_profile and vendor_profile.bijouterie:
            return vendor_profile.bijouterie
        return None

    # CASHIER → 1 seule bijouterie
    if role == ROLE_CASHIER:
        cashier_profile = getattr(user, "staff_cashier_profile", None)
        if cashier_profile and cashier_profile.bijouterie:
            return cashier_profile.bijouterie
        return None

    # MANAGER → plusieurs bijouteries
    if role == ROLE_MANAGER:
        manager_profile = getattr(user, "staff_manager_profile", None)

        if manager_profile and hasattr(manager_profile, "bijouteries"):
            # ici tu peux choisir :
            # 👉 soit la première
            return manager_profile.bijouteries.first()

            # 👉 soit lever une erreur si multiple
            # raise Exception("Manager a plusieurs bijouteries")

    return None