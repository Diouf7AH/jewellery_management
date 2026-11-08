# sale/services/sale_context_service.py

from decimal import Decimal

from django.core.exceptions import ValidationError

from backend.roles import ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR
from staff.models import Manager
from vendor.models import Vendor

ZERO = Decimal("0.00")


def dec(x) -> Decimal:
    if x is None:
        return ZERO

    if isinstance(x, str) and x.strip() == "":
        return ZERO

    try:
        return Decimal(str(x))
    except (ValueError, TypeError, ArithmeticError):
        raise ValidationError(
            f"Valeur décimale invalide: {x}"
        )


def _norm_email(s: str | None) -> str | None:
    if s is None:
        return None

    if not isinstance(s, str):
        raise ValidationError({
            "vendor_email": "L'email doit être une chaîne."
        })

    return s.strip().lower() or None


def resolve_vendor_and_bijouterie_for_sale(
    *,
    role: str,
    user,
    vendor_email: str | None = None,
):
    """
    Résout le vendeur et sa bijouterie.

    Utilisé par :
    - recherche SKU ;
    - scan QR ;
    - création de vente.

    VENDEUR :
        Son propre stock uniquement.

    MANAGER :
        vendor_email obligatoire.
        Vendeur appartenant à une bijouterie gérée.

    ADMIN :
        vendor_email obligatoire.
        Accès à toutes les bijouteries.

    Retourne :
        (vendor, bijouterie)
    """

    # =====================================================
    # 1. AUTHENTIFICATION
    # =====================================================

    if (
        user is None
        or not user.is_authenticated
        or not user.is_active
    ):
        raise ValidationError({
            "detail": (
                "Utilisateur non authentifié ou désactivé."
            )
        })

    role = (role or "").strip().lower()
    vendor_email = _norm_email(vendor_email)

    if role not in (
        ROLE_VENDOR,
        ROLE_MANAGER,
        ROLE_ADMIN,
    ):
        raise ValidationError({
            "detail": "Rôle non autorisé."
        })

    # =====================================================
    # 2. VENDEUR CONNECTÉ
    # =====================================================

    if role == ROLE_VENDOR:

        vendor = (
            Vendor.objects
            .select_related("bijouterie", "user")
            .filter(
                user=user,
                verifie=True,
                user__is_active=True,
            )
            .first()
        )

        if vendor is None:
            raise ValidationError({
                "detail": (
                    "Profil vendeur introuvable ou désactivé."
                )
            })

        if not vendor.bijouterie_id:
            raise ValidationError({
                "detail": "Vendeur sans bijouterie."
            })

        if (
            vendor_email
            and vendor.user.email.casefold()
            != vendor_email.casefold()
        ):
            raise ValidationError({
                "vendor_email": (
                    "Vous ne pouvez pas utiliser "
                    "le stock d'un autre vendeur."
                )
            })

        return vendor, vendor.bijouterie

    # =====================================================
    # 3. MANAGER / ADMIN : EMAIL OBLIGATOIRE
    # =====================================================

    if not vendor_email:
        raise ValidationError({
            "vendor_email": (
                "L'email du vendeur est obligatoire."
            )
        })

    # =====================================================
    # 4. VÉRIFICATION DU MANAGER
    # =====================================================

    manager = None

    if role == ROLE_MANAGER:

        manager = (
            Manager.objects
            .filter(
                user=user,
                verifie=True,
                user__is_active=True,
            )
            .first()
        )

        if manager is None:
            raise ValidationError({
                "detail": (
                    "Profil manager introuvable ou désactivé."
                )
            })

        if not manager.bijouteries.exists():
            raise ValidationError({
                "detail": (
                    "Aucune bijouterie assignée "
                    "à ce manager."
                )
            })

    # =====================================================
    # 5. RECHERCHE DU VENDEUR CIBLE
    # =====================================================

    vendor = (
        Vendor.objects
        .select_related("bijouterie", "user")
        .filter(
            user__email__iexact=vendor_email,
            verifie=True,
            user__is_active=True,
        )
        .first()
    )

    if vendor is None:
        raise ValidationError({
            "vendor_email": (
                "Vendeur introuvable ou désactivé."
            )
        })

    if not vendor.bijouterie_id:
        raise ValidationError({
            "vendor_email": (
                "Ce vendeur n'est rattaché "
                "à aucune bijouterie."
            )
        })

    # =====================================================
    # 6. CONTRÔLE DES BIJOUTERIES DU MANAGER
    # =====================================================

    if role == ROLE_MANAGER:

        if not manager.bijouteries.filter(
            pk=vendor.bijouterie_id
        ).exists():
            raise ValidationError({
                "vendor_email": (
                    "Ce vendeur n'appartient pas "
                    "à une bijouterie que vous gérez."
                )
            })

    # =====================================================
    # 7. RÉSULTAT
    # =====================================================

    return vendor, vendor.bijouterie

