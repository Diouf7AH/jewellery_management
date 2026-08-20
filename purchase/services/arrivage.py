from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from backend.roles import ROLE_ADMIN, ROLE_MANAGER, get_role_name
from inventory.models import Bucket, MovementType
from inventory.services import log_move
from purchase.models import Achat, Fournisseur, Lot, ProduitLine
from purchase.utils import generate_numero_lot
from stock.models import Stock
from store.models import Bijouterie, Produit


def resolve_arrivage_bijouterie(
    *,
    user,
    bijouterie_id=None,
) -> Bijouterie:
    """
    Résout la bijouterie de l'arrivage.

    Admin :
    - 1 seule bijouterie dans le système -> automatique ;
    - plusieurs -> bijouterie_id obligatoire.

    Manager :
    - 1 seule bijouterie affectée -> automatique ;
    - plusieurs -> bijouterie_id obligatoire.
    """

    role = get_role_name(user)

    if role == ROLE_ADMIN:
        accessibles = Bijouterie.objects.all()

    elif role == ROLE_MANAGER:
        manager = getattr(
            user,
            "staff_manager_profile",
            None,
        )

        if (
            not manager
            or not getattr(manager, "verifie", False)
        ):
            raise PermissionDenied(
                "Profil manager introuvable ou désactivé."
            )

        accessibles = manager.bijouteries.all()

    else:
        raise PermissionDenied(
            "Seuls les administrateurs et les managers "
            "peuvent créer un arrivage."
        )

    count = accessibles.count()

    if count == 0:
        raise ValidationError({
            "bijouterie_id": (
                "Aucune bijouterie accessible."
            )
        })

    if count == 1:
        return accessibles.first()

    if not bijouterie_id:
        raise ValidationError({
            "bijouterie_id": (
                "Plusieurs bijouteries sont accessibles. "
                "Veuillez sélectionner une bijouterie."
            )
        })

    try:
        bijouterie_id = int(bijouterie_id)
    except (TypeError, ValueError):
        raise ValidationError({
            "bijouterie_id": (
                "Identifiant de bijouterie invalide."
            )
        })

    bijouterie = accessibles.filter(
        pk=bijouterie_id
    ).first()

    if not bijouterie:
        raise ValidationError({
            "bijouterie_id": (
                "Bijouterie introuvable ou non accessible."
            )
        })

    return bijouterie


def resolve_arrivage_fournisseur(
    *,
    fournisseur_data: dict[str, Any],
) -> Fournisseur:
    """
    Téléphone = clé métier fournisseur.
    """

    telephone = (
        fournisseur_data.get("telephone")
        or ""
    ).strip()

    if not telephone:
        raise ValidationError({
            "fournisseur": {
                "telephone": (
                    "Le téléphone du fournisseur est obligatoire."
                )
            }
        })

    nom = (
        fournisseur_data.get("nom")
        or ""
    ).strip()

    if not nom:
        raise ValidationError({
            "fournisseur": {
                "nom": (
                    "Le nom du fournisseur est obligatoire."
                )
            }
        })

    fournisseur, _created = (
        Fournisseur.objects.update_or_create(
            telephone=telephone,
            defaults={
                "nom": nom,
                "prenom": (
                    fournisseur_data.get("prenom")
                    or ""
                ).strip(),
                "address": (
                    fournisseur_data.get("address")
                    or ""
                ).strip(),
            },
        )
    )

    return fournisseur


@transaction.atomic
def create_arrivage(
    *,
    user,
    validated_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Création complète d'un arrivage.

    Cycle :

        Achat
        ↓
        Lot
        ↓
        ProduitLine
        ↓
        Stock bijouterie
        ↓
        PURCHASE_IN

    Ne crée jamais :
    - VendorStock ;
    - réservation ;
    - VENDOR_ASSIGN ;
    - SALE_OUT.
    """

    lots_data = validated_data.get("lots") or []

    if not lots_data:
        raise ValidationError({
            "lots": (
                "Au moins un lot est requis."
            )
        })

    # =========================================================
    # 1. Bijouterie
    # =========================================================

    bijouterie = resolve_arrivage_bijouterie(
        user=user,
        bijouterie_id=validated_data.get(
            "bijouterie_id"
        ),
    )

    # =========================================================
    # 2. Fournisseur
    # =========================================================

    fournisseur = resolve_arrivage_fournisseur(
        fournisseur_data=validated_data[
            "fournisseur"
        ],
    )

    # =========================================================
    # 3. Produits
    # =========================================================

    produit_ids = {
        ligne["produit_id"]
        for lot_data in lots_data
        for ligne in lot_data["lignes"]
    }

    produits = (
        Produit.objects
        .filter(
            pk__in=produit_ids
        )
        .only(
            "id",
            "poids",
        )
    )

    produits_by_id = {
        produit.id: produit
        for produit in produits
    }

    missing_ids = (
        produit_ids
        - set(produits_by_id.keys())
    )

    if missing_ids:
        raise ValidationError({
            "lots": (
                "Produit(s) introuvable(s) : "
                f"{sorted(missing_ids)}."
            )
        })

    produits_sans_poids = [
        produit.id
        for produit in produits_by_id.values()
        if produit.poids is None
    ]

    if produits_sans_poids:
        raise ValidationError({
            "lots": (
                "Produit(s) sans poids renseigné : "
                f"{sorted(produits_sans_poids)}."
            )
        })

    # =========================================================
    # 4. Achat
    # =========================================================

    achat = Achat.objects.create(
        fournisseur=fournisseur,
        bijouterie=bijouterie,
        reference_commande=(
            validated_data.get(
                "reference_commande"
            )
            or ""
        ),
        description=(
            validated_data.get(
                "description"
            )
            or ""
        ),
        frais_transport=(
            validated_data.get(
                "frais_transport"
            )
            or Decimal("0.00")
        ),
        frais_douane=(
            validated_data.get(
                "frais_douane"
            )
            or Decimal("0.00")
        ),
        status=Achat.STATUS_CONFIRMED,
    )

    lots_created = []

    # =========================================================
    # 5. Lots + lignes + stock + mouvements
    # =========================================================

    for lot_data in lots_data:
        lot = Lot.objects.create(
            achat=achat,
            numero_lot=generate_numero_lot(),
            description=(
                lot_data.get(
                    "description"
                )
                or validated_data.get(
                    "description"
                )
                or ""
            ),
            received_at=(
                lot_data.get(
                    "received_at"
                )
                or timezone.now()
            ),
        )

        lots_created.append(lot)

        for ligne_data in lot_data["lignes"]:
            produit = produits_by_id[
                ligne_data["produit_id"]
            ]

            quantite = ligne_data["quantite"]

            prix_achat_gramme = (
                ligne_data["prix_achat_gramme"]
            )

            produit_line = (
                ProduitLine.objects.create(
                    lot=lot,
                    produit=produit,
                    quantite=quantite,
                    prix_achat_gramme=(
                        prix_achat_gramme
                    ),
                )
            )

            # =================================================
            # Stock magasin
            # =================================================

            Stock.objects.create(
                produit_line=produit_line,
                bijouterie=bijouterie,
                quantite_totale=quantite,
                en_stock=quantite,
            )

            # =================================================
            # Mouvement inventaire
            # =================================================

            log_move(
                produit=produit,
                qty=quantite,
                movement_type=(
                    MovementType.PURCHASE_IN
                ),
                src_bucket=Bucket.EXTERNAL,
                dst_bucket=Bucket.BIJOUTERIE,
                dst_bijouterie_id=(
                    bijouterie.id
                ),
                unit_cost=(
                    prix_achat_gramme
                ),
                achat=achat,
                produit_line=produit_line,
                lot=lot,
                user=user,
                reason=(
                    "Entrée fournisseur vers bijouterie"
                ),
            )

    # =========================================================
    # 6. Totaux achat
    # =========================================================

    achat.update_total(
        save=True
    )

    achat.refresh_from_db()

    return {
        "achat": achat,
        "lots": lots_created,
    }
    

