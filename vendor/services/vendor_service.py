from __future__ import annotations

from vendor.models import Vendor


def get_connected_vendor(user) -> Vendor | None:
    """
    Retourne le profil Vendor actif associé
    à l'utilisateur connecté.

    Conditions :
    - utilisateur authentifié ;
    - compte utilisateur actif ;
    - profil Vendor existant ;
    - profil Vendor vérifié (verifie=True).

    Retourne None si une condition n'est pas respectée.
    """

    if user is None:
        return None

    if not getattr(user, "is_authenticated", False):
        return None

    if not getattr(user, "is_active", False):
        return None

    return (
        Vendor.objects
        .select_related(
            "user",
            "bijouterie",
        )
        .filter(
            user=user,
            verifie=True,
        )
        .first()
    )
