from __future__ import annotations

from django.db.models import Q, QuerySet

from backend.bijouteries import get_user_bijouteries
from backend.roles import (ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER, ROLE_VENDOR,
                           get_role_name)

# ============================================================
# Helpers internes
# ============================================================

def _empty_scope_q() -> Q:
    """
    Retourne un filtre qui ne correspond à aucun objet.
    """
    return Q(pk__in=[])


def _normalize_scope_field(field: str) -> str:
    """
    Normalise le chemin Django utilisé pour filtrer
    selon la bijouterie.
    """
    normalized = str(field or "").strip()

    if not normalized:
        raise ValueError(
            "Le champ de filtrage de la bijouterie "
            "est obligatoire."
        )

    return normalized


def _active_authenticated_user(user) -> bool:
    """
    Vérifie que l'utilisateur existe,
    est authentifié et actif.
    """
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
    )


# ============================================================
# Scope générique par bijouterie
# ============================================================

def scope_bijouterie_q(
    user,
    field: str = "bijouterie_id",
) -> Q:
    """
    Retourne un objet Q limitant les résultats
    aux bijouteries accessibles.

    ADMIN : toutes les bijouteries.
    MANAGER : ses bijouteries.
    VENDOR : sa bijouterie.
    CASHIER : sa bijouterie.
    BUYER : sa bijouterie.

    Aucun accès : aucun résultat.
    """

    field = _normalize_scope_field(field)

    # Sécurité : aucun accès pour un compte inactif
    # ou non authentifié.
    if not _active_authenticated_user(user):
        return _empty_scope_q()

    role = get_role_name(user)

    if role is None:
        return _empty_scope_q()

    # ADMIN : accès global uniquement si
    # le compte est authentifié et actif.
    if role == ROLE_ADMIN:
        return Q()

    # Autres rôles : périmètre des bijouteries.
    bijouterie_ids = (
        get_user_bijouteries(user)
        .values_list("pk", flat=True)
    )

    return Q(
        **{
            f"{field}__in": bijouterie_ids,
        }
    )


# ============================================================
# Application du scope à un QuerySet
# ============================================================

def scope_queryset_by_bijouterie(
    queryset: QuerySet,
    *,
    user,
    field: str = "bijouterie_id",
) -> QuerySet:
    """
    Filtre un queryset selon les bijouteries
    accessibles par l'utilisateur.
    """

    if queryset is None:
        raise ValueError(
            "Le queryset est obligatoire."
        )

    field = _normalize_scope_field(field)

    return queryset.filter(
        scope_bijouterie_q(
            user,
            field=field,
        )
    ).distinct()


# ============================================================
# Scope spécifique aux ventes
# ============================================================

def scope_vente_queryset(
    queryset: QuerySet,
    *,
    user,
    bijouterie_field: str = "bijouterie_id",
    vendor_field: str = "vendor_id",
) -> QuerySet:
    """
    Applique les règles de visibilité des ventes.

    ADMIN : toutes les ventes.
    MANAGER : ventes de ses bijouteries.
    VENDOR : uniquement ses propres ventes.
    CASHIER : ventes de sa bijouterie.
    BUYER : aucune vente.
    """

    if queryset is None:
        raise ValueError(
            "Le queryset est obligatoire."
        )

    bijouterie_field = _normalize_scope_field(
        bijouterie_field
    )

    vendor_field = str(
        vendor_field or ""
    ).strip()

    if not vendor_field:
        raise ValueError(
            "Le champ vendeur est obligatoire."
        )

    if not _active_authenticated_user(user):
        return queryset.none()

    role = get_role_name(user)

    if role not in {
        ROLE_ADMIN,
        ROLE_MANAGER,
        ROLE_VENDOR,
        ROLE_CASHIER,
    }:
        return queryset.none()

    scoped_queryset = scope_queryset_by_bijouterie(
        queryset,
        user=user,
        field=bijouterie_field,
    )

    # Le vendeur voit uniquement ses propres ventes.
    if role == ROLE_VENDOR:
        vendor = getattr(
            user,
            "staff_vendor_profile",
            None,
        )

        if not (
            vendor
            and getattr(vendor, "verifie", False)
            and getattr(vendor, "bijouterie_id", None)
        ):
            return queryset.none()

        vendor_id = getattr(
            vendor,
            "pk",
            None,
        )

        if not vendor_id:
            return queryset.none()

        return scoped_queryset.filter(
            **{
                vendor_field: vendor_id,
            }
        ).distinct()

    return scoped_queryset


# ============================================================
# QuerySet Mixin générique
# ============================================================

class BijouterieScopedQuerysetMixin:
    """
    Limite automatiquement le queryset aux
    bijouteries accessibles.

    Compatible avec les vues génériques DRF
    et les ViewSets utilisant get_queryset().
    """

    scope_field = "bijouterie_id"

    def get_scope_field(self) -> str:
        return _normalize_scope_field(
            getattr(
                self,
                "scope_field",
                "",
            )
        )

    def get_queryset(self):
        queryset = super().get_queryset()

        if queryset is None:
            raise AssertionError(
                f"{self.__class__.__name__}.get_queryset() "
                "a retourné None."
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

        return scope_queryset_by_bijouterie(
            queryset,
            user=user,
            field=self.get_scope_field(),
        )


# ============================================================
# QuerySet Mixin spécifique aux ventes
# ============================================================

class VenteScopedQuerysetMixin:
    """
    Applique automatiquement les règles
    de visibilité des ventes.

    ADMIN : toutes les ventes.
    MANAGER : ventes de ses bijouteries.
    VENDOR : ses propres ventes.
    CASHIER : ventes de sa bijouterie.
    BUYER : aucune vente.
    """

    scope_bijouterie_field = "bijouterie_id"
    scope_vendor_field = "vendor_id"

    def get_queryset(self):
        queryset = super().get_queryset()

        if queryset is None:
            raise AssertionError(
                f"{self.__class__.__name__}.get_queryset() "
                "a retourné None."
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

        return scope_vente_queryset(
            queryset,
            user=user,
            bijouterie_field=self.scope_bijouterie_field,
            vendor_field=self.scope_vendor_field,
        )
