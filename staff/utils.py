# # staff/utils.py

# from __future__ import annotations

# from backend.roles import (ROLE_ADMIN, ROLE_BUYER, ROLE_CASHIER, ROLE_MANAGER,
#                            ROLE_VENDOR, get_role_name)
# from store.models import Bijouterie


# def get_user_bijouterie_or_none(
#     user,
#     bijouterie_id: int | str | None = None,
# ):
#     """
#     Retourne une bijouterie accessible par l'utilisateur.

#     Vendor, cashier et buyer :
#     - retournent automatiquement leur bijouterie.

#     Manager :
#     - doit fournir bijouterie_id ;
#     - la bijouterie doit appartenir à son périmètre.

#     Admin :
#     - doit fournir bijouterie_id ;
#     - peut sélectionner toute bijouterie.
#     """

#     if not user or not getattr(
#         user,
#         "is_authenticated",
#         False,
#     ):
#         return None

#     role = get_role_name(user)

#     if role == ROLE_VENDOR:
#         profile = getattr(
#             user,
#             "staff_vendor_profile",
#             None,
#         )

#         if (
#             profile
#             and profile.verifie
#             and profile.bijouterie_id
#         ):
#             return profile.bijouterie

#         return None

#     if role == ROLE_CASHIER:
#         profile = getattr(
#             user,
#             "staff_cashier_profile",
#             None,
#         )

#         if (
#             profile
#             and profile.verifie
#             and profile.bijouterie_id
#         ):
#             return profile.bijouterie

#         return None

#     if role == ROLE_BUYER:
#         profile = getattr(
#             user,
#             "staff_buyer_profile",
#             None,
#         )

#         if (
#             profile
#             and profile.verifie
#             and profile.bijouterie_id
#         ):
#             return profile.bijouterie

#         return None

#     if bijouterie_id in {
#         None,
#         "",
#         "null",
#         "None",
#     }:
#         return None

#     try:
#         requested_id = int(bijouterie_id)
#     except (TypeError, ValueError):
#         return None

#     if requested_id <= 0:
#         return None

#     if role == ROLE_MANAGER:
#         profile = getattr(
#             user,
#             "staff_manager_profile",
#             None,
#         )

#         if not profile or not profile.verifie:
#             return None

#         return (
#             profile.bijouteries
#             .filter(pk=requested_id)
#             .first()
#         )

#     if role == ROLE_ADMIN:
#         return (
#             Bijouterie.objects
#             .filter(pk=requested_id)
#             .first()
#         )

#     return None

