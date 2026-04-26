# backend/query_scopes.py
from django.db.models import Q

from backend.roles import (ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER, ROLE_VENDOR,
                           get_role_name)

# ============================================================
# 🔎 Q Scope (utilisable partout)
# ============================================================

def scope_bijouterie_q(user, field: str = "bijouterie_id") -> Q:
    """
    Retourne un Q() pour filtrer selon la bijouterie accessible.

    field = nom du champ FK bijouterie dans le queryset cible
    ex:
        - "bijouterie_id"
        - "vente__bijouterie_id"
        - "facture__bijouterie_id"
    """

    role = get_role_name(user)

    # Admin → pas de filtre
    if role == ROLE_ADMIN:
        return Q()

    # Manager → ManyToMany bijouteries
    if role == ROLE_MANAGER:
        mp = getattr(user, "staff_manager_profile", None)
        if mp and getattr(mp, "verifie", True):
            ids = mp.bijouteries.values_list("id", flat=True)
            return Q(**{f"{field}__in": ids})
        return Q(pk__in=[])

    # Vendor → 1 bijouterie
    if role == ROLE_VENDOR:
        vp = getattr(user, "staff_vendor_profile", None)
        bj_id = getattr(vp, "bijouterie_id", None) if vp and getattr(vp, "verifie", True) else None
        return Q(**{field: bj_id}) if bj_id else Q(pk__in=[])

    # Cashier → 1 bijouterie
    if role == ROLE_CASHIER:
        cp = getattr(user, "staff_cashier_profile", None)
        bj_id = getattr(cp, "bijouterie_id", None) if cp and getattr(cp, "verifie", True) else None
        return Q(**{field: bj_id}) if bj_id else Q(pk__in=[])

    # autre rôle → rien
    return Q(pk__in=[])


# ============================================================
# 🧩 Queryset Mixin (pour ListAPIView, ViewSet, etc.)
# ============================================================

class BijouterieScopedQuerysetMixin:
    """
    Mixin pour restreindre automatiquement un queryset
    selon la bijouterie accessible par l'utilisateur.

    Fonctionne avec:
        - admin   → tout
        - manager → ses bijouteries (ManyToMany)
        - vendor  → sa bijouterie
        - cashier → sa bijouterie

    ⚠️ Utilisable avec:
        - ListAPIView
        - GenericAPIView
        - ModelViewSet
        (PAS APIView)
    """

    scope_field = "bijouterie_id"  # override si besoin

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        return qs.filter(scope_bijouterie_q(user, field=self.scope_field))
    
    


