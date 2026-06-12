# sale/services/sale_context_service.py
from decimal import Decimal

from django.core.exceptions import ValidationError

from backend.roles import ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR
from vendor.models import Vendor

ZERO = Decimal("0.00")


def dec(x) -> Decimal:
    if x is None:
        return ZERO
    if isinstance(x, str) and x.strip() == "":
        return ZERO
    try:
        return Decimal(str(x))
    except Exception:
        raise ValidationError(f"Valeur décimale invalide: {x}")


def _norm_email(s: str | None) -> str | None:
    s = (s or "").strip().lower()
    return s or None


def resolve_vendor_and_bijouterie_for_sale(*, role: str, user, vendor_email: str | None):
    """
    Source de vérité: le vendeur.
    - vendor  : vendeur connecté
    - manager : vendor_email requis + manager doit gérer la bijouterie du vendeur
    - admin   : vendor_email requis
    """
    role = (role or "").strip().lower()
    vendor_email = _norm_email(vendor_email)

    if role == ROLE_VENDOR:
        v = (
            Vendor.objects
            .select_related("bijouterie", "user")
            .filter(user=user)
            .first()
        )
        if not v:
            raise ValidationError({"detail": "Profil vendeur introuvable."})
        if hasattr(v, "verifie") and not v.verifie:
            raise ValidationError({"detail": "Vendeur désactivé (non vérifié)."})
        if not v.bijouterie_id:
            raise ValidationError({"detail": "Vendeur sans bijouterie."})
        return v, v.bijouterie

    if role == ROLE_MANAGER:
        if not vendor_email:
            raise ValidationError({"vendor_email": "vendor_email requis pour manager."})

        mgr = getattr(user, "staff_manager_profile", None)
        if not mgr or (hasattr(mgr, "verifie") and not mgr.verifie):
            raise ValidationError({"detail": "Profil manager introuvable ou désactivé."})

        if hasattr(mgr, "bijouteries") and not mgr.bijouteries.exists():
            raise ValidationError({"detail": "Aucune bijouterie assignée à ce manager."})

        v = (
            Vendor.objects
            .select_related("bijouterie", "user")
            .filter(user__email__iexact=vendor_email)
            .first()
        )
        if not v:
            raise ValidationError({"vendor_email": "Vendeur introuvable."})
        if hasattr(v, "verifie") and not v.verifie:
            raise ValidationError({"vendor_email": "Vendeur désactivé (non vérifié)."})
        if not v.bijouterie_id:
            raise ValidationError({"vendor_email": "Ce vendeur n’est rattaché à aucune bijouterie."})

        if hasattr(mgr, "bijouteries") and not mgr.bijouteries.filter(id=v.bijouterie_id).exists():
            raise ValidationError({"vendor_email": "Ce vendeur n’appartient pas à une bijouterie que vous gérez."})

        return v, v.bijouterie

    if role == ROLE_ADMIN:
        if not vendor_email:
            raise ValidationError({"vendor_email": "vendor_email requis pour admin."})

        v = (
            Vendor.objects
            .select_related("bijouterie", "user")
            .filter(user__email__iexact=vendor_email)
            .first()
        )
        if not v:
            raise ValidationError({"vendor_email": "Vendeur introuvable."})
        if hasattr(v, "verifie") and not v.verifie:
            raise ValidationError({"vendor_email": "Vendeur désactivé (non vérifié)."})
        if not v.bijouterie_id:
            raise ValidationError({"vendor_email": "Ce vendeur n’est rattaché à aucune bijouterie."})

        return v, v.bijouterie

    raise ValidationError({"detail": "Rôle non autorisé."})

    
    
    
