# services/qr_scan_service.py

from __future__ import annotations

from uuid import UUID

from rest_framework.exceptions import PermissionDenied, ValidationError

from backend.roles import ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR, get_role_name
from purchase.models import ProduitLine
from sale.services.sale_context_service import \
    resolve_vendor_and_bijouterie_for_sale
from staff.models import Manager
from stock.models import VendorStock
from vendor.models import Vendor
from vendor.services.qr_utils import decode_etiquette_qr

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
    Résout le vendeur autorisé pour le scan QR.

    Réutilise les permissions communes
    de Rio-Gold.
    """

    vendor, _ = resolve_vendor_and_bijouterie_for_sale(
        user=user,
        role=get_role_name(user),
        vendor_email=vendor_email,
    )

    return vendor

# ============================================================
# 3. RECHERCHER UN PRODUIT PAR QR CODE
# ============================================================
def rechercher_produit_par_qr(vendor, qr_content: str):
    """
    Recherche une ProduitLine par QR code.

    Retourne :
        ((produit_line, vendor_stock), None)

    Ou :
        (None, code_erreur)

    Ne modifie aucune quantité.
    """

    qr_uuid = decode_etiquette_qr(qr_content)

    produit_line = (
        ProduitLine.objects
        .select_related(
            "lot",
            "lot__achat",
            "produit",
            "produit__categorie",
            "produit__marque",
            "produit__purete",
            "produit__modele",
        )
        .filter(
            uuid=qr_uuid,
            lot__achat__bijouterie_id=vendor.bijouterie_id,
        )
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

    quantite_disponible = (
        vendor_stock.quantite_allouee
        - vendor_stock.quantite_vendue
    )

    if quantite_disponible <= 0:
        return None, "STOCK_INSUFFICIENT"

    return (produit_line, vendor_stock), None

