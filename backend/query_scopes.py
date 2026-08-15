# backend/query_scopes.py

from __future__ import annotations

from django.db.models import Q, QuerySet

from backend.roles import (ROLE_ADMIN, ROLE_BUYER, ROLE_CASHIER, ROLE_MANAGER,
                           ROLE_VENDOR, get_role_name)

# ============================================================
# Helpers internes
# ============================================================

def _empty_scope_q() -> Q:
    """
    Retourne un filtre qui ne correspond à aucun objet.

    Utilisé lorsqu'un utilisateur :
    - n'a aucun rôle autorisé ;
    - possède un profil désactivé ;
    - n'est rattaché à aucune bijouterie.
    """

    return Q(pk__in=[])


def _is_verified(profile) -> bool:
    """
    Vérifie qu'un profil staff existe et possède verifie=True.
    """

    return bool(
        profile
        and getattr(profile, "verifie", False)
    )


def _single_bijouterie_scope(
    *,
    profile,
    field: str,
) -> Q:
    """
    Construit un filtre pour un profil rattaché
    à une seule bijouterie.

    Compatible avec :
    - vendor ;
    - cashier ;
    - buyer.
    """

    if not _is_verified(profile):
        return _empty_scope_q()

    bijouterie_id = getattr(
        profile,
        "bijouterie_id",
        None,
    )

    if not bijouterie_id:
        return _empty_scope_q()

    return Q(**{
        field: bijouterie_id,
    })


# ============================================================
# Q Scope
# ============================================================

def scope_bijouterie_q(
    user,
    field: str = "bijouterie_id",
) -> Q:
    """
    Retourne un objet Q permettant de filtrer un queryset
    selon les bijouteries accessibles par l'utilisateur.

    Paramètre field :
        chemin du champ représentant la bijouterie
        dans le queryset cible.

    Exemples :

        scope_bijouterie_q(
            request.user,
            field="bijouterie_id",
        )

        scope_bijouterie_q(
            request.user,
            field="vente__bijouterie_id",
        )

        scope_bijouterie_q(
            request.user,
            field="facture__vente__bijouterie_id",
        )

        scope_bijouterie_q(
            request.user,
            field="vendor__bijouterie_id",
        )

    Règles :

    Admin :
        aucun filtre, accès global.

    Manager :
        accès aux bijouteries présentes dans son ManyToMany.

    Vendor :
        accès à sa bijouterie unique.

    Cashier :
        accès à sa bijouterie unique.

    Buyer :
        accès à sa bijouterie unique.

    Autre rôle ou profil désactivé :
        queryset vide.
    """

    if not field:
        raise ValueError(
            "Le champ de filtrage de la bijouterie est obligatoire."
        )

    field = str(field).strip()

    if not field:
        raise ValueError(
            "Le champ de filtrage de la bijouterie est obligatoire."
        )

    role = get_role_name(user)

    # --------------------------------------------------------
    # Admin : accès global
    # --------------------------------------------------------

    if role == ROLE_ADMIN:
        return Q()

    # --------------------------------------------------------
    # Manager : plusieurs bijouteries
    # --------------------------------------------------------

    if role == ROLE_MANAGER:
        manager = getattr(
            user,
            "staff_manager_profile",
            None,
        )

        if not _is_verified(manager):
            return _empty_scope_q()

        bijouterie_ids = (
            manager.bijouteries
            .values_list(
                "pk",
                flat=True,
            )
        )

        return Q(**{
            f"{field}__in": bijouterie_ids,
        })

    # --------------------------------------------------------
    # Vendor : une bijouterie
    # --------------------------------------------------------

    if role == ROLE_VENDOR:
        vendor = getattr(
            user,
            "staff_vendor_profile",
            None,
        )

        return _single_bijouterie_scope(
            profile=vendor,
            field=field,
        )

    # --------------------------------------------------------
    # Cashier : une bijouterie
    # --------------------------------------------------------

    if role == ROLE_CASHIER:
        cashier = getattr(
            user,
            "staff_cashier_profile",
            None,
        )

        return _single_bijouterie_scope(
            profile=cashier,
            field=field,
        )

    # --------------------------------------------------------
    # Buyer : une bijouterie
    # --------------------------------------------------------

    if role == ROLE_BUYER:
        buyer = getattr(
            user,
            "staff_buyer_profile",
            None,
        )

        return _single_bijouterie_scope(
            profile=buyer,
            field=field,
        )

    return _empty_scope_q()

def scope_queryset_by_bijouterie(
    queryset: QuerySet,
    *,
    user,
    field: str = "bijouterie_id",
) -> QuerySet:
    """
    Applique le périmètre de bijouterie à un queryset.
    """

    if queryset is None:
        raise ValueError(
            "Le queryset est obligatoire."
        )

    return (
        queryset
        .filter(
            scope_bijouterie_q(
                user,
                field=field,
            )
        )
        .distinct()
    )


# ============================================================
# Queryset Mixin
# ============================================================

class BijouterieScopedQuerysetMixin:
    """
    Restreint automatiquement le queryset aux bijouteries
    accessibles par l'utilisateur connecté.

    Compatible avec :
    - ListAPIView ;
    - RetrieveAPIView ;
    - UpdateAPIView ;
    - DestroyAPIView ;
    - GenericAPIView ;
    - ModelViewSet ;
    - ReadOnlyModelViewSet.

    Non compatible directement avec APIView,
    car APIView ne possède pas get_queryset().

    Règles :
    - admin   : tout ;
    - manager : ses bijouteries ;
    - vendor  : sa bijouterie ;
    - cashier : sa bijouterie ;
    - buyer   : sa bijouterie.
    """

    scope_field = "bijouterie_id"

    def get_scope_field(self) -> str:
        """
        Retourne le chemin du champ utilisé pour le scope.

        Peut être surchargé dans une vue.
        """

        field = getattr(
            self,
            "scope_field",
            None,
        )

        if not field:
            raise ValueError(
                "scope_field doit être défini dans la vue."
            )

        field = str(field).strip()

        if not field:
            raise ValueError(
                "scope_field ne peut pas être vide."
            )

        return field

    def get_queryset(self):
        """
        Retourne le queryset limité aux bijouteries
        accessibles par l'utilisateur.
        """

        queryset = super().get_queryset()

        if queryset is None:
            raise AssertionError(
                (
                    f"{self.__class__.__name__}.get_queryset() "
                    "a retourné None."
                )
            )

        request = getattr(
            self,
            "request",
            None,
        )

        if request is None:
            return queryset.none()

        user = getattr(
            request,
            "user",
            None,
        )

        scope_field = self.get_scope_field()

        return (
            queryset
            .filter(
                scope_bijouterie_q(
                    user,
                    field=scope_field,
                )
            )
            .distinct()
        )