
# sale/services/payment_permission_service.py

from __future__ import annotations

from django.core.exceptions import PermissionDenied

from backend.bijouteries import user_has_bijouterie_access
from backend.roles import ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER, get_role_name

# ============================================================
# RÔLES AUTORISÉS À ENCAISSER
# ============================================================

ROLES_ENCAISSEMENT = frozenset({
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_CASHIER,
})


# ============================================================
# NORMALISATION DE LA BIJOUTERIE
# ============================================================

def _normaliser_bijouterie_id(
    bijouterie_id,
) -> int:
    """
    Accepte un identifiant entier positif
    ou une instance de Bijouterie.

    Refuse les booléens, flottants et
    identifiants invalides.
    """

    raw_id = getattr(
        bijouterie_id,
        "pk",
        bijouterie_id,
    )

    if isinstance(raw_id, bool):
        raise PermissionDenied(
            "Identifiant de bijouterie invalide."
        )

    if isinstance(raw_id, int):
        result = raw_id

    elif (
        isinstance(raw_id, str)
        and raw_id.strip().isascii()
        and raw_id.strip().isdecimal()
    ):
        result = int(raw_id.strip())

    else:
        raise PermissionDenied(
            "Identifiant de bijouterie invalide."
        )

    if result <= 0:
        raise PermissionDenied(
            "Identifiant de bijouterie invalide."
        )

    return result


# ============================================================
# PERMISSION D'ENCAISSEMENT
# ============================================================

def verifier_permission_encaissement(
    user,
    bijouterie_id,
):
    """
    Vérifie si l'utilisateur peut encaisser
    dans une bijouterie donnée.

    ADMIN :
        Toutes les bijouteries autorisées.

    MANAGER :
        Uniquement ses bijouteries.
        Profil vérifié obligatoire.

    CASHIER :
        Uniquement sa bijouterie.
        Profil vérifié obligatoire.

    VENDOR / BUYER :
        Encaissement interdit.

    Retour :
        - Profil caissier pour CASHIER.
        - None pour ADMIN ou MANAGER.

    Exception :
        PermissionDenied.
    """

    # ========================================================
    # 1. AUTHENTIFICATION
    # ========================================================

    if (
        user is None
        or not getattr(
            user,
            "is_authenticated",
            False,
        )
        or not getattr(
            user,
            "is_active",
            False,
        )
    ):
        raise PermissionDenied(
            "Utilisateur non authentifié ou inactif."
        )

    # ========================================================
    # 2. RÔLE EFFECTIF
    # ========================================================

    role = get_role_name(user)

    if role not in ROLES_ENCAISSEMENT:
        raise PermissionDenied(
            "Vous n'êtes pas autorisé à encaisser."
        )

    # ========================================================
    # 3. IDENTIFIANT DE BIJOUTERIE
    # ========================================================

    bijouterie_id = _normaliser_bijouterie_id(
        bijouterie_id
    )

    # ========================================================
    # 4. CONTRÔLE DU PÉRIMÈTRE
    # ========================================================

    if not user_has_bijouterie_access(
        user,
        bijouterie_id,
    ):
        raise PermissionDenied(
            "Vous n'avez pas accès à cette bijouterie."
        )

    # ========================================================
    # 5. ADMINISTRATEUR
    # ========================================================

    if role == ROLE_ADMIN:
        return None

    # ========================================================
    # 6. MANAGER
    # ========================================================

    if role == ROLE_MANAGER:

        manager = getattr(
            user,
            "staff_manager_profile",
            None,
        )

        if manager is None:
            raise PermissionDenied(
                "Profil manager introuvable."
            )

        if not getattr(
            manager,
            "verifie",
            False,
        ):
            raise PermissionDenied(
                "Profil manager non vérifié "
                "ou désactivé."
            )

        if not manager.bijouteries.filter(
            pk=bijouterie_id
        ).exists():
            raise PermissionDenied(
                "Ce manager n'est pas autorisé "
                "à encaisser dans cette bijouterie."
            )

        return None

    # ========================================================
    # 7. CAISSIER
    # ========================================================

    if role == ROLE_CASHIER:

        cashier = getattr(
            user,
            "staff_cashier_profile",
            None,
        )

        if cashier is None:
            raise PermissionDenied(
                "Profil caissier introuvable."
            )

        if not getattr(
            cashier,
            "verifie",
            False,
        ):
            raise PermissionDenied(
                "Profil caissier non vérifié "
                "ou désactivé."
            )

        if cashier.bijouterie_id != bijouterie_id:
            raise PermissionDenied(
                "Ce caissier n'est pas autorisé "
                "à encaisser dans cette bijouterie."
            )

        return cashier

    # ========================================================
    # 8. REFUS PAR DÉFAUT
    # ========================================================

    raise PermissionDenied(
        "Vous n'êtes pas autorisé à encaisser."
    )


