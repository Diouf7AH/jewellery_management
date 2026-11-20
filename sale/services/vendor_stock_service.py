# sale/services/vendor_stock_service.py

from __future__ import annotations

from typing import Dict, List

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from stock.models import VendorStock

# ============================================================
# 1. VALIDATION DES QUANTITÉS
# ============================================================

def _positive_quantity(value) -> int:
    """
    Accepte :
        - entier Python strictement positif ;
        - chaîne contenant un entier positif.

    Refuse :
        - booléens ;
        - flottants ;
        - fractions ;
        - zéro ;
        - nombres négatifs.
    """

    if isinstance(value, bool):
        raise ValidationError({
            "quantite": (
                "Un entier strictement positif "
                "est obligatoire."
            )
        })

    if isinstance(value, int):
        q = value

    elif (
        isinstance(value, str)
        and value.strip().isascii()
        and value.strip().isdecimal()
    ):
        q = int(value.strip())

    else:
        raise ValidationError({
            "quantite": (
                "Un entier strictement positif "
                "est obligatoire."
            )
        })

    if q <= 0:
        raise ValidationError({
            "quantite": (
                "La quantité doit être "
                "supérieure ou égale à 1."
            )
        })

    return q


# ============================================================
# 2. VALIDATION DES DONNÉES COMMUNES
# ============================================================

def _validate_common(
    *,
    vendor,
    bijouterie,
    produit_line,
    quantite: int,
) -> int:
    """
    Vérifie :
        - quantité positive ;
        - vendeur existant ;
        - vendeur vérifié ;
        - compte vendeur actif ;
        - bijouterie existante ;
        - vendeur rattaché à la bijouterie ;
        - ProduitLine existante ;
        - produit et lot renseignés ;
        - lot appartenant à la bijouterie.

    Ne modifie aucune donnée.
    """

    q = _positive_quantity(quantite)

    # --------------------------------------------------------
    # VENDEUR
    # --------------------------------------------------------

    if (
        vendor is None
        or getattr(vendor, "pk", None) is None
    ):
        raise ValidationError({
            "vendor": "Le vendeur est obligatoire."
        })

    if not getattr(vendor, "verifie", False):
        raise ValidationError({
            "vendor": (
                "Le vendeur est désactivé "
                "ou non vérifié."
            )
        })

    if not getattr(
        getattr(vendor, "user", None),
        "is_active",
        False,
    ):
        raise ValidationError({
            "vendor": (
                "Le compte utilisateur "
                "du vendeur est inactif."
            )
        })

    # --------------------------------------------------------
    # BIJOUTERIE
    # --------------------------------------------------------

    if (
        bijouterie is None
        or getattr(bijouterie, "pk", None) is None
    ):
        raise ValidationError({
            "bijouterie": (
                "La bijouterie est obligatoire."
            )
        })

    if vendor.bijouterie_id != bijouterie.pk:
        raise ValidationError({
            "vendor": (
                "Le vendeur n'appartient pas "
                "à cette bijouterie."
            )
        })

    # --------------------------------------------------------
    # PRODUITLINE
    # --------------------------------------------------------

    if (
        produit_line is None
        or getattr(produit_line, "pk", None) is None
    ):
        raise ValidationError({
            "produit_line": (
                "La ProduitLine est obligatoire."
            )
        })

    if (
        not produit_line.produit_id
        or not produit_line.lot_id
    ):
        raise ValidationError({
            "produit_line": (
                "La ProduitLine doit être liée "
                "à un produit et à un lot."
            )
        })

    # --------------------------------------------------------
    # CONTRÔLE DE LA BIJOUTERIE DU LOT
    # --------------------------------------------------------

    if (
        produit_line.lot.achat.bijouterie_id
        != bijouterie.pk
    ):
        raise ValidationError({
            "produit_line": (
                "Cette ligne de produit appartient "
                "à une autre bijouterie."
            )
        })

    return q


# ============================================================
# 3. RÉCUPÉRATION DU STOCK VENDEUR
# ============================================================

def _get_vendor_stock(
    *,
    vendor,
    bijouterie,
    produit_line,
    lock: bool = False,
) -> VendorStock:
    """
    Récupère le VendorStock exact.

    lock=True :
        verrouille la ligne en base.

    Refuse :
        - stock absent ;
        - plusieurs stocks correspondant
          à la même combinaison.
    """

    if (
        lock
        and not transaction.get_connection().in_atomic_block
    ):
        raise ValidationError({
            "stock": (
                "Le verrouillage nécessite "
                "une transaction atomique."
            )
        })

    qs = VendorStock.objects.filter(
        vendor=vendor,
        bijouterie=bijouterie,
        produit_line=produit_line,
    )

    if lock:
        qs = qs.select_for_update()

    try:
        return qs.get()

    except VendorStock.DoesNotExist as exc:
        raise ValidationError({
            "stock": (
                "Aucun stock vendeur pour "
                f"la ProduitLine {produit_line.pk}."
            )
        }) from exc

    except VendorStock.MultipleObjectsReturned as exc:
        raise ValidationError({
            "stock": (
                "Plusieurs VendorStock existent "
                "pour ce vendeur, cette bijouterie "
                "et cette ProduitLine. "
                "Corrigez les doublons."
            )
        }) from exc


# ============================================================
# 4. CALCUL DU STOCK DISPONIBLE
# ============================================================

def _available_quantity(
    vendor_stock: VendorStock,
) -> int:
    """
    Stock disponible vendeur :

        quantite_allouee - quantite_vendue

    Vérifie la cohérence des quantités.
    """

    allouee = int(
        vendor_stock.quantite_allouee or 0
    )

    vendue = int(
        vendor_stock.quantite_vendue or 0
    )

    if (
        allouee < 0
        or vendue < 0
        or vendue > allouee
    ):
        raise ValidationError({
            "stock": (
                "Quantités vendeur incohérentes : "
                "vérifiez l'allocation "
                "et les ventes."
            )
        })

    return allouee - vendue


# ============================================================
# 5. VÉRIFIER LA DISPONIBILITÉ
# ============================================================

def ensure_vendor_stock_available(
    *,
    vendor,
    bijouterie,
    produit_line,
    quantite: int,
) -> int:
    """
    Vérifie la disponibilité du stock vendeur.

    Ne modifie aucune quantité.

    Ne réserve pas le stock.

    Retourne :
        quantité disponible au moment
        de la vérification.

    La disponibilité doit être vérifiée
    à nouveau sous verrou lors
    de la consommation réelle.
    """

    q = _validate_common(
        vendor=vendor,
        bijouterie=bijouterie,
        produit_line=produit_line,
        quantite=quantite,
    )

    stock = _get_vendor_stock(
        vendor=vendor,
        bijouterie=bijouterie,
        produit_line=produit_line,
    )

    disponible = _available_quantity(stock)

    if disponible < q:
        raise ValidationError({
            "stock": (
                "Stock vendeur insuffisant "
                f"pour la ProduitLine {produit_line.pk}. "
                f"Disponible : {disponible}, "
                f"demandé : {q}."
            )
        })

    return disponible


# ============================================================
# 6. CONSOMMER LE STOCK VENDEUR
# ============================================================

@transaction.atomic
def consume_vendor_stock(
    *,
    vendor,
    bijouterie,
    produit_line,
    quantite: int,
) -> List[Dict[str, int]]:
    """
    Consomme le stock vendeur à la création
    de la vente.

    Fonctionnement :
        1. Valide les données.
        2. Verrouille le VendorStock.
        3. Vérifie la disponibilité.
        4. Incrémente quantite_vendue.
        5. Retourne les informations consommées.

    Important :
        - Ne modifie pas Stock magasin.
        - Ne modifie pas ProduitLine.quantite.
        - Ne crée pas InventoryMovement.
        - Ne doit pas être appelée au scan QR.
        - Ne doit pas être appelée au paiement.

    À utiliser dans la transaction globale
    de création de vente avec le mouvement
    InventoryMovement.SALE_OUT.
    """

    # --------------------------------------------------------
    # 1. VALIDATION
    # --------------------------------------------------------

    q = _validate_common(
        vendor=vendor,
        bijouterie=bijouterie,
        produit_line=produit_line,
        quantite=quantite,
    )

    # --------------------------------------------------------
    # 2. VERROUILLAGE DU STOCK
    # --------------------------------------------------------

    stock = _get_vendor_stock(
        vendor=vendor,
        bijouterie=bijouterie,
        produit_line=produit_line,
        lock=True,
    )

    # --------------------------------------------------------
    # 3. QUANTITÉ DISPONIBLE
    # --------------------------------------------------------

    disponible = _available_quantity(stock)

    if disponible < q:
        raise ValidationError({
            "stock": (
                "Stock vendeur insuffisant "
                f"pour la ProduitLine {produit_line.pk}. "
                f"Disponible : {disponible}, "
                f"demandé : {q}."
            )
        })

    # --------------------------------------------------------
    # 4. MISE À JOUR ATOMIQUE
    # --------------------------------------------------------

    updated = (
        VendorStock.objects
        .filter(
            pk=stock.pk,
            quantite_vendue__lte=(
                F("quantite_allouee") - q
            ),
        )
        .update(
            quantite_vendue=(
                F("quantite_vendue") + q
            )
        )
    )

    if updated != 1:
        raise ValidationError({
            "stock": (
                "Conflit de stock vendeur. "
                "Veuillez réessayer."
            )
        })

    # --------------------------------------------------------
    # 5. RÉSULTAT
    # --------------------------------------------------------

    return [
        {
            "produit_line_id": int(
                produit_line.pk
            ),
            "qty": q,
        }
    ]

