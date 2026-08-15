# stock/services/vendor_transfer.py
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from inventory.models import Bucket, InventoryMovement, MovementType
from stock.models import Stock, VendorStock
from vendor.models import Vendor


def _normalize_transfer_lines(
    lignes: Iterable[Dict[str, Any]],
) -> Dict[int, int]:
    """
    Valide et regroupe les lignes par ProduitLine.

    Exemple :
        [
            {"produit_line_id": 10, "quantite": 2},
            {"produit_line_id": 10, "quantite": 3},
        ]

    devient :
        {10: 5}
    """

    if not isinstance(lignes, (list, tuple)) or not lignes:
        raise ValidationError({
            "lignes": "Au moins une ligne d'affectation est requise."
        })

    grouped: Dict[int, int] = defaultdict(int)

    for index, item in enumerate(lignes):
        if not isinstance(item, dict):
            raise ValidationError({
                f"lignes[{index}]": (
                    "Chaque ligne doit être un objet."
                )
            })

        try:
            produit_line_id = int(
                item.get("produit_line_id")
            )
        except (TypeError, ValueError):
            raise ValidationError({
                f"lignes[{index}].produit_line_id": (
                    "produit_line_id doit être un entier valide."
                )
            })

        try:
            quantite = int(item.get("quantite"))
        except (TypeError, ValueError):
            raise ValidationError({
                f"lignes[{index}].quantite": (
                    "quantite doit être un entier valide."
                )
            })

        if produit_line_id <= 0:
            raise ValidationError({
                f"lignes[{index}].produit_line_id": (
                    "produit_line_id doit être supérieur à zéro."
                )
            })

        if quantite <= 0:
            raise ValidationError({
                f"lignes[{index}].quantite": (
                    "La quantité doit être supérieure "
                    "ou égale à 1."
                )
            })

        grouped[produit_line_id] += quantite

    # Ordre stable pour réduire les risques de deadlock.
    return dict(sorted(grouped.items()))


@transaction.atomic
def assign_stock_to_vendor(
    *,
    vendor_email: str,
    lignes: List[Dict[str, Any]],
    note: str = "",
    user=None,
) -> Dict[str, Any]:
    """
    Affecte du stock d'une bijouterie à un vendeur.

    Cycle :
        VENDOR_ASSIGN
        BIJOUTERIE → VENDOR

    Effets :
        Stock.en_stock -= quantité
        Stock.quantite_totale reste inchangée
        VendorStock.quantite_allouee += quantité
        InventoryMovement = VENDOR_ASSIGN

    Toutes les lignes sont traitées dans une transaction unique.

    Si une ligne échoue :
        - toutes les modifications Stock sont annulées ;
        - toutes les modifications VendorStock sont annulées ;
        - aucun mouvement n'est conservé.
    """

    vendor_email = str(vendor_email or "").strip()

    if not vendor_email:
        raise ValidationError({
            "vendor_email": (
                "L'adresse email du vendeur est obligatoire."
            )
        })

    grouped = _normalize_transfer_lines(lignes)
    produit_line_ids = list(grouped.keys())

    # ---------------------------------------------------------
    # 1. Verrouillage et validation du vendeur
    # ---------------------------------------------------------
    try:
        vendor = (
            Vendor.objects
            .select_for_update()
            .select_related(
                "bijouterie",
                "user",
            )
            .get(
                user__email__iexact=vendor_email,
                verifie=True,
            )
        )

    except Vendor.DoesNotExist:
        raise ValidationError({
            "vendor_email": (
                "Vendeur introuvable ou désactivé."
            )
        })

    except Vendor.MultipleObjectsReturned:
        raise ValidationError({
            "vendor_email": (
                "Plusieurs profils vendeur utilisent "
                "cette adresse email."
            )
        })

    if not vendor.bijouterie_id:
        raise ValidationError({
            "vendor_email": (
                "Ce vendeur n'est rattaché "
                "à aucune bijouterie."
            )
        })

    bijouterie_id = vendor.bijouterie_id

    # ---------------------------------------------------------
    # 2. Verrouillage des stocks magasin
    # ---------------------------------------------------------
    stocks = list(
        Stock.objects
        .select_for_update()
        .select_related(
            "bijouterie",
            "produit_line",
            "produit_line__lot",
            "produit_line__produit",
        )
        .filter(
            produit_line_id__in=produit_line_ids,
            bijouterie_id=bijouterie_id,
        )
        .order_by("produit_line_id")
    )

    stock_map = {
        stock.produit_line_id: stock
        for stock in stocks
    }

    # ---------------------------------------------------------
    # 3. Vérification des ProduitLine absentes
    # ---------------------------------------------------------
    missing = [
        produit_line_id
        for produit_line_id in produit_line_ids
        if produit_line_id not in stock_map
    ]

    if missing:
        raise ValidationError({
            "lignes": (
                "Aucun stock magasin trouvé pour les "
                "ProduitLine suivantes : "
                + ", ".join(map(str, missing))
            )
        })

    # ---------------------------------------------------------
    # 4. Validation de toutes les quantités avant modification
    # ---------------------------------------------------------
    stock_errors: List[Dict[str, Any]] = []

    for produit_line_id, quantite in grouped.items():
        stock = stock_map[produit_line_id]
        produit_line = stock.produit_line

        en_stock = int(stock.en_stock or 0)

        produit_nom = (
            getattr(
                produit_line.produit,
                "nom",
                None,
            )
            or getattr(
                produit_line.produit,
                "sku",
                None,
            )
            or str(produit_line.produit_id)
        )

        if en_stock < quantite:
            stock_errors.append({
                "produit_line_id": produit_line_id,
                "produit": produit_nom,
                "quantite_demandee": quantite,
                "en_stock": en_stock,
                "detail": "Stock magasin insuffisant.",
            })

    if stock_errors:
        raise ValidationError({
            "stocks": stock_errors
        })

    # ---------------------------------------------------------
    # 5. Verrouillage des stocks vendeur existants
    # ---------------------------------------------------------
    existing_vendor_stocks = list(
        VendorStock.objects
        .select_for_update()
        .filter(
            vendor_id=vendor.id,
            bijouterie_id=bijouterie_id,
            produit_line_id__in=produit_line_ids,
        )
        .order_by("produit_line_id")
    )

    vendor_stock_map = {
        vendor_stock.produit_line_id: vendor_stock
        for vendor_stock in existing_vendor_stocks
    }

    now = timezone.now()
    note_clean = str(note or "").strip()
    movements_created = 0

    # ---------------------------------------------------------
    # 6. Application des affectations
    # ---------------------------------------------------------
    for produit_line_id, quantite in grouped.items():
        stock = stock_map[produit_line_id]
        produit_line = stock.produit_line

        # Diminue uniquement le stock physiquement disponible
        # dans la bijouterie.
        #
        # Stock.quantite_totale reste inchangée.
        stock_updated = (
            Stock.objects
            .filter(
                pk=stock.pk,
                en_stock__gte=quantite,
            )
            .update(
                en_stock=F("en_stock") - quantite,
                updated_at=now,
            )
        )

        if stock_updated != 1:
            raise ValidationError({
                "detail": (
                    "Conflit ou insuffisance de stock magasin "
                    f"pour ProduitLine {produit_line_id}. "
                    "Veuillez réessayer."
                )
            })

        vendor_stock = vendor_stock_map.get(
            produit_line_id
        )

        if vendor_stock is None:
            try:
                vendor_stock = VendorStock.objects.create(
                    produit_line_id=produit_line_id,
                    vendor_id=vendor.id,
                    bijouterie_id=bijouterie_id,
                    quantite_allouee=0,
                    quantite_vendue=0,
                )

            except IntegrityError:
                # Une autre transaction peut avoir créé
                # la ligne entre-temps.
                vendor_stock = (
                    VendorStock.objects
                    .select_for_update()
                    .get(
                        produit_line_id=produit_line_id,
                        vendor_id=vendor.id,
                        bijouterie_id=bijouterie_id,
                    )
                )

            vendor_stock_map[
                produit_line_id
            ] = vendor_stock

        vendor_stock_updated = (
            VendorStock.objects
            .filter(pk=vendor_stock.pk)
            .update(
                quantite_allouee=(
                    F("quantite_allouee")
                    + quantite
                ),
                updated_at=now,
            )
        )

        if vendor_stock_updated != 1:
            raise ValidationError({
                "detail": (
                    "Impossible de mettre à jour le stock "
                    "du vendeur pour ProduitLine "
                    f"{produit_line_id}."
                )
            })

        # -----------------------------------------------------
        # 7. Journal du mouvement
        # -----------------------------------------------------
        InventoryMovement.objects.create(
            produit_id=produit_line.produit_id,
            produit_line_id=produit_line.id,

            movement_type=MovementType.VENDOR_ASSIGN,
            qty=quantite,
            unit_cost=None,

            lot_id=produit_line.lot_id,

            reason=(
                note_clean
                or f"Affectation bijouterie vers vendeur #{vendor.id}"
            ),

            src_bucket=Bucket.BIJOUTERIE,
            src_bijouterie_id=bijouterie_id,

            dst_bucket=Bucket.VENDOR,
            dst_bijouterie_id=bijouterie_id,

            vendor_id=vendor.id,

            occurred_at=now,
            created_by=user,
        )

        movements_created += 1

    # ---------------------------------------------------------
    # 8. Relecture des valeurs après les expressions F()
    # ---------------------------------------------------------
    stock_after = {
        row["produit_line_id"]: row
        for row in (
            Stock.objects
            .filter(
                produit_line_id__in=produit_line_ids,
                bijouterie_id=bijouterie_id,
            )
            .values(
                "produit_line_id",
                "en_stock",
                "quantite_totale",
            )
        )
    }

    vendor_stock_after = {
        row["produit_line_id"]: row
        for row in (
            VendorStock.objects
            .filter(
                vendor_id=vendor.id,
                bijouterie_id=bijouterie_id,
                produit_line_id__in=produit_line_ids,
            )
            .values(
                "produit_line_id",
                "quantite_allouee",
                "quantite_vendue",
            )
        )
    }

    # ---------------------------------------------------------
    # 9. Construction de la réponse
    # ---------------------------------------------------------
    output_lines: List[Dict[str, Any]] = []

    for produit_line_id, quantite in grouped.items():
        stock_row = stock_after.get(
            produit_line_id,
            {},
        )

        vendor_stock_row = vendor_stock_after.get(
            produit_line_id,
            {},
        )

        magasin_en_stock = int(
            stock_row.get("en_stock") or 0
        )

        magasin_quantite_totale = int(
            stock_row.get("quantite_totale") or 0
        )

        vendor_allouee = int(
            vendor_stock_row.get(
                "quantite_allouee"
            )
            or 0
        )

        vendor_vendue = int(
            vendor_stock_row.get(
                "quantite_vendue"
            )
            or 0
        )

        output_lines.append({
            "produit_line_id": produit_line_id,
            "quantite_affectee": quantite,

            "magasin_en_stock": magasin_en_stock,
            "magasin_quantite_totale": (
                magasin_quantite_totale
            ),

            "vendor_quantite_allouee": (
                vendor_allouee
            ),
            "vendor_quantite_vendue": (
                vendor_vendue
            ),
            "vendor_en_stock": max(
                0,
                vendor_allouee - vendor_vendue,
            ),
        })

    return {
        "vendor_id": vendor.id,
        "vendor_email": getattr(
            vendor.user,
            "email",
            None,
        ),

        "bijouterie_id": bijouterie_id,
        "bijouterie_nom": getattr(
            vendor.bijouterie,
            "nom",
            None,
        ),

        "nombre_lignes": len(output_lines),
        "quantite_totale_affectee": sum(
            grouped.values()
        ),

        "lignes": output_lines,
        "note": note_clean,
        "movements_created": movements_created,
    }
    
