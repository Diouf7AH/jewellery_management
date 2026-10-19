# services/qr_scan_service.py

from __future__ import annotations

from uuid import UUID

from rest_framework.exceptions import PermissionDenied, ValidationError

from backend.roles import ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR, get_role_name
from purchase.models import ProduitLine
from staff.models import Manager
from stock.models import VendorStock
from vendor.models import Vendor

# ============================================================
# 1. DÉCODER LE QR CODE
# ============================================================

def decode_etiquette_qr(qr_content: str) -> UUID:
    """
    Format attendu :
        PL:<uuid ProduitLine>
    """

    if not isinstance(qr_content, str):
        raise ValueError("Le QR Code doit être une chaîne.")

    code = qr_content.strip()

    if not code.startswith("PL:"):
        raise ValueError(
            "Format QR Code invalide. Préfixe PL: attendu."
        )

    try:
        return UUID(code[3:])

    except (ValueError, AttributeError) as exc:
        raise ValueError(
            "UUID de l'étiquette invalide."
        ) from exc


# ============================================================
# 2. IDENTIFIER LE VENDEUR ET VÉRIFIER LES PERMISSIONS
# ============================================================

def resolve_scan_vendor(user, vendor_email=None):
    """
    Vendeur :
        Accède uniquement à son propre stock.

    Manager :
        Fournit l'email du vendeur.
        Accède uniquement aux vendeurs de ses bijouteries.

    Admin :
        Fournit l'email du vendeur.
        Accès global si ROLE_ADMIN correspond à un
        administrateur global du système.

    Aucun mot de passe vendeur n'est nécessaire.
    """

    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentification requise.")

    role = get_role_name(user)

    if role not in (ROLE_VENDOR, ROLE_MANAGER, ROLE_ADMIN):
        raise PermissionDenied(
            "Vous n'êtes pas autorisé à scanner des bijoux."
        )

    if vendor_email is not None and not isinstance(vendor_email, str):
        raise ValidationError({
            "vendor_email": "L'email doit être une chaîne."
        })

    vendor_email = (vendor_email or "").strip()

    # --------------------------------------------------------
    # VENDEUR CONNECTÉ
    # --------------------------------------------------------

    if role == ROLE_VENDOR:

        vendor = (
            Vendor.objects
            .select_related("user", "bijouterie")
            .filter(
                user=user,
                verifie=True,
                user__is_active=True,
            )
            .first()
        )

        if vendor is None:
            raise PermissionDenied(
                "Profil vendeur introuvable ou désactivé."
            )

        if vendor_email and (
            vendor.user.email or ""
        ).casefold() != vendor_email.casefold():
            raise PermissionDenied(
                "Vous ne pouvez pas utiliser le stock "
                "d'un autre vendeur."
            )

        return vendor

    # --------------------------------------------------------
    # MANAGER / ADMIN : EMAIL OBLIGATOIRE
    # --------------------------------------------------------

    if not vendor_email:
        raise ValidationError({
            "vendor_email": "L'email du vendeur est obligatoire."
        })

    vendor = (
        Vendor.objects
        .select_related("user", "bijouterie")
        .filter(
            user__email__iexact=vendor_email,
            verifie=True,
            user__is_active=True,
        )
        .first()
    )

    if vendor is None:
        raise ValidationError({
            "vendor_email": "Vendeur introuvable ou désactivé."
        })

    # --------------------------------------------------------
    # MANAGER : VÉRIFIER LE RATTACHEMENT
    # --------------------------------------------------------

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
            raise PermissionDenied(
                "Profil manager introuvable ou désactivé."
            )

        if not manager.bijouteries.filter(
            pk=vendor.bijouterie_id
        ).exists():
            raise PermissionDenied(
                "Ce vendeur n'appartient pas "
                "à vos bijouteries."
            )

        return vendor

    # --------------------------------------------------------
    # ADMIN
    # --------------------------------------------------------

    # ========================================================
    # ADMIN : ACCÈS À TOUTES LES BIJOUTERIES
    # ========================================================

    if role == ROLE_ADMIN:
        return vendor


# ============================================================
# 3. RECHERCHER UN PRODUIT PAR QR CODE
# ============================================================

def rechercher_produit_par_qr(vendor, qr_content: str):
    """
    Retourne :
        ((produit_line, vendor_stock), None)
    ou :
        (None, code_erreur)

    Ne modifie aucune quantité.
    """

    qr_uuid = decode_etiquette_qr(qr_content)

    produit_line = (
        ProduitLine.objects
        .select_related(
            "lot",
            "produit",
            "produit__categorie",
            "produit__marque",
            "produit__purete",
            "produit__modele",
        )
        .filter(uuid=qr_uuid)
        .first()
    )

    if produit_line is None:
        return None, "PRODUIT_LINE_NOT_FOUND"

    vendor_stock = (
        VendorStock.objects
        .filter(
            vendor=vendor,
            bijouterie_id=vendor.bijouterie_id,
            produit_line=produit_line,
        )
        .first()
    )

    if vendor_stock is None:
        return None, "STOCK_NOT_ASSIGNED"

    return (produit_line, vendor_stock), None


