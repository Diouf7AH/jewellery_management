# sale/services/return_service.py

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from backend.roles import ROLE_ADMIN, ROLE_MANAGER, get_role_name
from backend.utils.helpers import user_can_access_bijouterie
from inventory.models import Bucket, InventoryMovement, MovementType
from sale.models import Facture, Vente
from stock.models import Stock

RETURN_DELAY_HOURS = 72


# ============================================================
# 1. VALIDATION DES PERMISSIONS
# ============================================================

def _validate_return_permission(*, user, bijouterie):
    """
    Autorise uniquement l'administrateur ou le manager
    ayant accès à la bijouterie.
    """

    if (
        user is None
        or not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
    ):
        raise ValidationError({
            "user": "Utilisateur actif et authentifié obligatoire."
        })

    role = get_role_name(user)

    if role not in (ROLE_ADMIN, ROLE_MANAGER):
        raise ValidationError({
            "permission": (
                "Seuls l'administrateur et le manager "
                "peuvent enregistrer un retour."
            )
        })

    if not user_can_access_bijouterie(user, bijouterie):
        raise ValidationError({
            "permission": (
                "Vous n'avez pas accès à cette bijouterie."
            )
        })


# ============================================================
# 2. VALIDATION DES ENTIERS
# ============================================================

def _positive_int(value, field):
    """
    Accepte un entier positif ou une chaîne décimale positive.

    Refuse :
    - booléens ;
    - nombres flottants ;
    - nombres négatifs ;
    - valeurs nulles ;
    - chaînes non numériques.
    """

    if isinstance(value, bool):
        raise ValidationError({
            field: "Un entier strictement positif est obligatoire."
        })

    if isinstance(value, int):
        result = value

    elif (
        isinstance(value, str)
        and value.strip().isascii()
        and value.strip().isdecimal()
    ):
        result = int(value.strip())

    else:
        raise ValidationError({
            field: "Un entier strictement positif est obligatoire."
        })

    if result <= 0:
        raise ValidationError({
            field: "La valeur doit être supérieure à zéro."
        })

    return result


# ============================================================
# 3. NORMALISATION DES LIGNES
# ============================================================

def _normaliser_lignes_retour(return_lines):
    """
    Valide les lignes et regroupe les ProduitLine identiques.
    """

    if not isinstance(return_lines, list) or not return_lines:
        raise ValidationError({
            "lignes": "Au moins une ligne de retour est obligatoire."
        })

    quantites = defaultdict(int)

    for index, item in enumerate(return_lines):
        if not isinstance(item, dict):
            raise ValidationError({
                f"lignes[{index}]": "Format de ligne invalide."
            })

        produit_line_id = _positive_int(
            item.get("produit_line_id"),
            f"lignes[{index}].produit_line_id",
        )

        quantite = _positive_int(
            item.get("quantite"),
            f"lignes[{index}].quantite",
        )

        quantites[produit_line_id] += quantite

    return [
        {
            "produit_line_id": produit_line_id,
            "quantite": quantite,
        }
        for produit_line_id, quantite in sorted(quantites.items())
    ]


# ============================================================
# 4. VALIDATION DU DÉLAI
# ============================================================

def _validate_return_deadline(facture):
    """
    Vérifie le délai de 72 heures à partir de la date
    réelle du paiement intégral.
    """

    paid_at = getattr(facture, "paid_at", None)

    if paid_at is None:
        raise ValidationError({
            "facture": (
                "La date du paiement intégral est introuvable. "
                "Le retour ne peut pas être autorisé."
            )
        })

    if timezone.is_naive(paid_at):
        raise ValidationError({
            "facture": "La date de paiement doit être horodatée."
        })

    deadline = paid_at + timedelta(
        hours=RETURN_DELAY_HOURS
    )

    if timezone.now() > deadline:
        raise ValidationError({
            "facture": (
                "Le délai de retour de 72 heures est dépassé."
            )
        })


# ============================================================
# 5. SERVICE PRINCIPAL
# ============================================================

@transaction.atomic
def return_paid_sale_to_bijouterie(
    *,
    facture: Facture,
    return_lines: list[dict[str, Any]],
    user,
    reason: str = "",
) -> dict:
    """
    Retour physique d'une vente de bijoux payée.

    Mouvement :
        RETURN_IN
        EXTERNAL -> BIJOUTERIE

    Effets :
        Stock.en_stock += quantité
        Stock.quantite_totale += quantité
        InventoryMovement RETURN_IN

    Ne modifie jamais :
        ProduitLine.quantite
        VendorStock.quantite_allouee
        VendorStock.quantite_vendue
        Facture.montant_total
        Paiement
        PaiementLigne

    Aucun remboursement n'est effectué.
    """

    # ========================================================
    # 1. VALIDATION DES PARAMÈTRES
    # ========================================================

    if facture is None or getattr(facture, "pk", None) is None:
        raise ValidationError({
            "facture": "Une facture enregistrée est obligatoire."
        })

    lignes_normalisees = _normaliser_lignes_retour(
        return_lines
    )

    if not isinstance(reason, str):
        raise ValidationError({
            "reason": "Le motif doit être une chaîne de caractères."
        })

    reason = reason.strip()

    if not reason:
        reason = "Retour client dans le délai de 72 heures."

    # ========================================================
    # 2. VERROUILLAGE DE LA VENTE PUIS DE LA FACTURE
    # ========================================================

    facture_reference = (
        Facture.objects
        .filter(pk=facture.pk)
        .values("vente_id")
        .first()
    )

    if facture_reference is None:
        raise ValidationError({
            "facture": "Facture introuvable."
        })

    vente_id = facture_reference["vente_id"]

    if not vente_id:
        raise ValidationError({
            "facture": "Cette facture n'est associée à aucune vente."
        })

    try:
        vente = (
            Vente.objects
            .select_for_update()
            .select_related("bijouterie")
            .get(pk=vente_id)
        )
    except Vente.DoesNotExist as exc:
        raise ValidationError({
            "vente": "Vente introuvable."
        }) from exc

    try:
        facture = (
            Facture.objects
            .select_for_update()
            .get(pk=facture.pk)
        )
    except Facture.DoesNotExist as exc:
        raise ValidationError({
            "facture": "Facture introuvable."
        }) from exc

    if facture.vente_id != vente.pk:
        raise ValidationError({
            "facture": "La facture n'appartient plus à cette vente."
        })

    if facture.bijouterie_id != vente.bijouterie_id:
        raise ValidationError({
            "facture": (
                "Incohérence entre la bijouterie "
                "de la facture et celle de la vente."
            )
        })

    if vente.is_cancelled:
        raise ValidationError({
            "vente": "Le retour d'une vente annulée est interdit."
        })

    # ========================================================
    # 3. PERMISSIONS
    # ========================================================

    _validate_return_permission(
        user=user,
        bijouterie=vente.bijouterie,
    )

    # ========================================================
    # 4. VÉRIFICATION DE LA FACTURE
    # ========================================================

    if facture.status != Facture.STAT_PAYE:
        raise ValidationError({
            "facture": (
                "Seule une facture entièrement payée "
                "peut faire l'objet d'un retour."
            )
        })

    if not getattr(facture, "stock_consumed", False):
        raise ValidationError({
            "facture": (
                "Le stock de cette facture n'a pas été consommé."
            )
        })

    _validate_return_deadline(facture)

    # ========================================================
    # 5. VERROUILLAGE DES STOCKS
    # ========================================================

    produit_line_ids = [
        item["produit_line_id"]
        for item in lignes_normalisees
    ]

    stocks = {
        stock.produit_line_id: stock
        for stock in (
            Stock.objects
            .select_for_update()
            .select_related(
                "produit_line",
                "produit_line__produit",
                "produit_line__lot",
            )
            .filter(
                produit_line_id__in=produit_line_ids,
                bijouterie_id=vente.bijouterie_id,
            )
            .order_by("pk")
        )
    }

    # ========================================================
    # 6. VÉRIFICATION DES QUANTITÉS RETOURNABLES
    # ========================================================

    lignes_validees = []

    for item in lignes_normalisees:
        produit_line_id = item["produit_line_id"]
        quantite = item["quantite"]

        stock = stocks.get(produit_line_id)

        if stock is None:
            raise ValidationError({
                "produit_line_id": (
                    f"Stock introuvable pour la ProduitLine "
                    f"{produit_line_id} dans cette bijouterie."
                )
            })

        sold_qty = (
            InventoryMovement.objects
            .filter(
                facture=facture,
                vente=vente,
                produit_line_id=produit_line_id,
                movement_type=MovementType.SALE_OUT,
                src_bucket=Bucket.VENDOR,
                dst_bucket=Bucket.EXTERNAL,
            )
            .aggregate(total=Sum("qty"))["total"]
            or 0
        )

        already_returned_qty = (
            InventoryMovement.objects
            .filter(
                facture=facture,
                vente=vente,
                produit_line_id=produit_line_id,
                movement_type=MovementType.RETURN_IN,
                src_bucket=Bucket.EXTERNAL,
                dst_bucket=Bucket.BIJOUTERIE,
            )
            .aggregate(total=Sum("qty"))["total"]
            or 0
        )

        available_to_return = (
            int(sold_qty) - int(already_returned_qty)
        )

        if available_to_return < 0:
            raise ValidationError({
                "stock": (
                    "Incohérence détectée dans l'historique "
                    "des mouvements de retour."
                )
            })

        if quantite > available_to_return:
            raise ValidationError({
                "quantite": (
                    f"ProduitLine {produit_line_id} : "
                    f"vendu {sold_qty}, "
                    f"déjà retourné {already_returned_qty}, "
                    f"retournable {available_to_return}, "
                    f"demandé {quantite}."
                )
            })

        lignes_validees.append({
            "stock": stock,
            "produit_line_id": produit_line_id,
            "quantite": quantite,
        })

    # ========================================================
    # 7. ENREGISTREMENT DES RETOURS
    # ========================================================

    returned_qty = 0
    movements_created = 0
    output_lines = []

    for item in lignes_validees:
        stock = item["stock"]
        produit_line_id = item["produit_line_id"]
        quantite = item["quantite"]

        # Réintégration physique au stock magasin.
        Stock.objects.filter(pk=stock.pk).update(
            en_stock=F("en_stock") + quantite,
            quantite_totale=F("quantite_totale") + quantite,
            updated_at=timezone.now(),
        )

        produit_line = stock.produit_line

        mouvement = InventoryMovement.objects.create(
            produit_id=produit_line.produit_id,
            produit_line_id=produit_line_id,

            movement_type=MovementType.RETURN_IN,
            qty=quantite,

            src_bucket=Bucket.EXTERNAL,
            dst_bucket=Bucket.BIJOUTERIE,
            dst_bijouterie_id=vente.bijouterie_id,

            vendor_id=getattr(vente, "vendor_id", None),

            lot_id=produit_line.lot_id,
            achat_id=produit_line.lot.achat_id,

            vente=vente,
            facture=facture,

            reason=reason,
            occurred_at=timezone.now(),
            created_by=user,
        )

        returned_qty += quantite
        movements_created += 1

        output_lines.append({
            "produit_line_id": produit_line_id,
            "quantite_retournee": quantite,
            "movement_id": mouvement.pk,
        })

    # ========================================================
    # 8. RÉSULTAT
    # ========================================================

    return {
        "success": True,
        "facture_id": facture.pk,
        "numero_facture": facture.numero_facture,
        "vente_id": vente.pk,
        "bijouterie_id": vente.bijouterie_id,
        "quantite_retournee": returned_qty,
        "movements_created": movements_created,
        "remboursement_effectue": False,
        "lignes": output_lines,
    }
    
    