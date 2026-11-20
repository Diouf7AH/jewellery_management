from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

from backend.roles import ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR, get_role_name
from staff.models import Manager
from vendor.models import Vendor

ZERO = Decimal("0.00")


# ============================================================
# 1. CONVERSION DÉCIMALE
# ============================================================

def dec(x) -> Decimal:
    """
    Convertit une valeur en Decimal.

    None ou chaîne vide -> ZERO.

    Refuse :
    - booléens ;
    - valeurs non numériques ;
    - NaN ;
    - Infinity.

    Note :
    Pour les montants financiers, utiliser de préférence
    sale.services.montant_service.
    """

    if x is None:
        return ZERO

    if isinstance(x, str) and not x.strip():
        return ZERO

    if isinstance(x, bool):
        raise ValidationError({
            "montant": "Valeur décimale invalide."
        })

    try:
        montant = Decimal(str(x))

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ) as exc:
        raise ValidationError({
            "montant": "Valeur décimale invalide."
        }) from exc

    if not montant.is_finite():
        raise ValidationError({
            "montant": "La valeur doit être un nombre fini."
        })

    return montant


# ============================================================
# 2. NORMALISATION EMAIL
# ============================================================

def _norm_email(s: str | None) -> str | None:
    """
    Normalise l'email du vendeur.

    - None -> None
    - chaîne vide -> None
    - suppression des espaces extérieurs
    - comparaison insensible à la casse
    """

    if s is None:
        return None

    if not isinstance(s, str):
        raise ValidationError({
            "vendor_email": (
                "L'email doit être une chaîne de caractères."
            )
        })

    return s.strip().casefold() or None


# ============================================================
# 3. RÉSOLUTION VENDEUR / BIJOUTERIE
# ============================================================

def resolve_vendor_and_bijouterie_for_sale(
    *,
    role: str,
    user,
    vendor_email: str | None = None,
):
    """
    Résout le vendeur et sa bijouterie.

    Utilisé pour :
    - recherche SKU ;
    - scan QR ;
    - création de vente.

    VENDEUR :
        Accès uniquement à son propre stock.
        vendor_email facultatif.
        Si fourni, il doit correspondre à son email.

    MANAGER :
        vendor_email obligatoire.
        Le vendeur doit appartenir à une bijouterie
        gérée par le manager connecté.

    ADMIN :
        vendor_email obligatoire.
        Peut sélectionner un vendeur actif et vérifié
        de n'importe quelle bijouterie.

    Sécurité :
        - utilisateur authentifié et actif ;
        - rôle réel vérifié côté Django ;
        - profil staff vérifié ;
        - vendeur cible actif ;
        - contrôle des bijouteries autorisées.

    Retour :
        tuple (vendor, bijouterie)
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
        raise ValidationError({
            "detail": (
                "Utilisateur non authentifié "
                "ou désactivé."
            )
        })

    # ========================================================
    # 2. RÔLE RÉEL
    # ========================================================

    role_reel = get_role_name(user)

    roles_autorises = {
        ROLE_VENDOR,
        ROLE_MANAGER,
        ROLE_ADMIN,
    }

    if role_reel not in roles_autorises:
        raise ValidationError({
            "detail": "Rôle non autorisé."
        })

    if not isinstance(role, str):
        raise ValidationError({
            "role": "Rôle invalide."
        })

    role_normalise = role.strip().lower()

    if role_normalise != role_reel:
        raise ValidationError({
            "role": (
                "Le rôle transmis ne correspond pas "
                "au rôle de l'utilisateur connecté."
            )
        })

    vendor_email = _norm_email(vendor_email)

    # ========================================================
    # 3. VENDEUR CONNECTÉ
    # ========================================================

    if role_reel == ROLE_VENDOR:

        try:
            vendor = (
                Vendor.objects
                .select_related(
                    "bijouterie",
                    "user",
                )
                .get(
                    user=user,
                    verifie=True,
                    user__is_active=True,
                )
            )

        except Vendor.DoesNotExist as exc:
            raise ValidationError({
                "detail": (
                    "Profil vendeur introuvable "
                    "ou désactivé."
                )
            }) from exc

        if not vendor.bijouterie_id:
            raise ValidationError({
                "detail": (
                    "Le vendeur n'est rattaché "
                    "à aucune bijouterie."
                )
            })

        # Le vendeur ne peut pas sélectionner
        # un autre vendeur.

        email_connecte = _norm_email(
            vendor.user.email
        )

        if (
            vendor_email is not None
            and vendor_email != email_connecte
        ):
            raise ValidationError({
                "vendor_email": (
                    "Vous ne pouvez pas utiliser "
                    "le stock d'un autre vendeur."
                )
            })

        return vendor, vendor.bijouterie

    # ========================================================
    # 4. MANAGER / ADMIN : EMAIL OBLIGATOIRE
    # ========================================================

    if not vendor_email:
        raise ValidationError({
            "vendor_email": (
                "L'email du vendeur est obligatoire "
                "pour un administrateur ou un manager."
            )
        })

    # ========================================================
    # 5. VÉRIFICATION DU MANAGER
    # ========================================================

    manager = None

    if role_reel == ROLE_MANAGER:

        try:
            manager = (
                Manager.objects
                .get(
                    user=user,
                    verifie=True,
                    user__is_active=True,
                )
            )

        except Manager.DoesNotExist as exc:
            raise ValidationError({
                "detail": (
                    "Profil manager introuvable "
                    "ou désactivé."
                )
            }) from exc

        if not manager.bijouteries.exists():
            raise ValidationError({
                "detail": (
                    "Aucune bijouterie assignée "
                    "à ce manager."
                )
            })

    # ========================================================
    # 6. RECHERCHE DU VENDEUR CIBLE
    # ========================================================

    try:
        vendor = (
            Vendor.objects
            .select_related(
                "bijouterie",
                "user",
            )
            .get(
                user__email__iexact=vendor_email,
                verifie=True,
                user__is_active=True,
            )
        )

    except Vendor.DoesNotExist as exc:
        raise ValidationError({
            "vendor_email": (
                "Vendeur introuvable ou désactivé."
            )
        }) from exc

    except Vendor.MultipleObjectsReturned as exc:
        raise ValidationError({
            "vendor_email": (
                "Plusieurs vendeurs correspondent "
                "à cet email. Vérifiez les comptes."
            )
        }) from exc

    # ========================================================
    # 7. VÉRIFICATION DE LA BIJOUTERIE DU VENDEUR
    # ========================================================

    if not vendor.bijouterie_id:
        raise ValidationError({
            "vendor_email": (
                "Ce vendeur n'est rattaché "
                "à aucune bijouterie."
            )
        })

    # ========================================================
    # 8. CONTRÔLE DES BIJOUTERIES DU MANAGER
    # ========================================================

    if role_reel == ROLE_MANAGER:

        acces_autorise = (
            manager.bijouteries
            .filter(
                pk=vendor.bijouterie_id
            )
            .exists()
        )

        if not acces_autorise:
            raise ValidationError({
                "vendor_email": (
                    "Ce vendeur n'appartient pas "
                    "à une bijouterie que vous gérez."
                )
            })

    # ========================================================
    # 9. RÉSULTAT
    # ========================================================

    return vendor, vendor.bijouterie


