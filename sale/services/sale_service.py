# sale/services/sale_service.py

from __future__ import annotations

from decimal import Decimal
from typing import Dict

from django.core.exceptions import ValidationError
from django.db import transaction

from purchase.models import ProduitLine
from sale.models import Client, Facture, Vente, VenteProduit
from sale.services.sale_context_service import \
    resolve_vendor_and_bijouterie_for_sale
from sale.services.vendor_stock_service import ensure_vendor_stock_available
from sale.utils import ZERO
from store.models import MarquePurete

# =============================================================
# HELPERS
# =============================================================


def dec(v):
    try:
        if v in [None, "", "null"]:
            return ZERO

        return Decimal(str(v))

    except (TypeError, ValueError, ArithmeticError):
        return ZERO


# =============================================================
# CLIENT AU PAIEMENT
# =============================================================


def upsert_client_for_payment(
    *,
    facture,
    client_data: dict,
):
    if not facture.vente:
        raise ValidationError({
            "facture": (
                "Aucune vente associée à cette facture."
            )
        })

    nom = (
        client_data.get("nom")
        or ""
    ).strip()

    prenom = (
        client_data.get("prenom")
        or ""
    ).strip()

    telephone = (
        client_data.get("telephone")
        or ""
    ).strip()

    if not nom or not prenom:
        raise ValidationError({
            "client": (
                "nom et prenom sont obligatoires "
                "au paiement."
            )
        })

    vente = facture.vente
    client = getattr(
        vente,
        "client",
        None,
    )

    existing_by_phone = None

    if telephone:
        existing_by_phone = (
            Client.objects
            .filter(
                telephone=telephone,
            )
            .first()
        )

    # ---------------------------------------------------------
    # Vente ayant déjà un client
    # ---------------------------------------------------------

    if client:

        if (
            existing_by_phone
            and existing_by_phone.id != client.id
        ):
            raise ValidationError({
                "telephone": (
                    "Ce téléphone est déjà utilisé "
                    "par un autre client : "
                    f"{existing_by_phone.full_name}"
                )
            })

        changed_fields = []

        if client.nom != nom:
            client.nom = nom
            changed_fields.append("nom")

        if client.prenom != prenom:
            client.prenom = prenom
            changed_fields.append("prenom")

        if (
            telephone
            and client.telephone != telephone
        ):
            client.telephone = telephone
            changed_fields.append("telephone")

        if changed_fields:
            client.save(
                update_fields=changed_fields,
            )

        return client

    # ---------------------------------------------------------
    # Client existant retrouvé par téléphone
    # ---------------------------------------------------------

    if existing_by_phone:

        vente.client = existing_by_phone

        vente.save(
            update_fields=["client"],
        )

        return existing_by_phone

    # ---------------------------------------------------------
    # Nouveau client
    # ---------------------------------------------------------

    client = Client.objects.create(
        nom=nom,
        prenom=prenom,
        telephone=telephone or None,
    )

    vente.client = client

    vente.save(
        update_fields=["client"],
    )

    return client


# =============================================================
# CRÉATION VENTE
# =============================================================


@transaction.atomic
def create_sale_one_vendor(
    *,
    user,
    role: str,
    payload: Dict,
) -> tuple[Vente, Facture, int]:
    """
    Création d'une vente PROFORMA pour un seul vendeur.

    IMPORTANT :

    - chaque ligne identifie une ProduitLine précise ;
    - ProduitLine est la source de vérité ;
    - le Produit est obtenu via produit_line.produit ;
    - aucune sélection FIFO ;
    - aucune consommation du stock ici ;
    - seule la disponibilité VendorStock est vérifiée ;
    - la consommation réelle intervient après paiement ;
    - le prix/gramme est figé dans VenteProduit ;
    - le pourcentage occasion est figé dans VenteProduit ;
    - la TVA est figée dans Facture.
    """

    client_in = payload.get("client") or {}
    items = payload.get("produits") or []

    if not items:
        raise ValidationError({
            "produits": (
                "Au moins une ProduitLine est requise."
            )
        })

    # =========================================================
    # 1. AGRÉGATION PAR PRODUIT_LINE
    # =========================================================

    grouped = {}

    for item in items:

        produit_line_id = item.get(
            "produit_line_id"
        )

        if not produit_line_id:
            raise ValidationError({
                "produit_line_id": (
                    "Champ requis."
                )
            })

        try:
            plid = int(produit_line_id)

        except (TypeError, ValueError):
            raise ValidationError({
                "produit_line_id": (
                    "Doit être un entier."
                )
            })

        try:
            qty = int(
                item.get("quantite") or 0
            )

        except (TypeError, ValueError):
            raise ValidationError({
                f"produit_line_{plid}": (
                    "Quantité invalide."
                )
            })

        if qty <= 0:
            raise ValidationError({
                f"produit_line_{plid}": (
                    "La quantité doit être "
                    "supérieure ou égale à 1."
                )
            })

        prix_vente = dec(
            item.get("prix_vente_grammes")
        )

        remise = dec(
            item.get("remise")
        )

        autres = dec(
            item.get("autres")
        )

        if remise < ZERO:
            raise ValidationError({
                f"produit_line_{plid}": (
                    "La remise ne peut pas "
                    "être négative."
                )
            })

        if autres < ZERO:
            raise ValidationError({
                f"produit_line_{plid}": (
                    "Le montant 'autres' ne peut "
                    "pas être négatif."
                )
            })

        if plid not in grouped:
            grouped[plid] = {
                "quantite": 0,
                "prix_vente_grammes": prix_vente,
                "remise": remise,
                "autres": autres,
            }

        else:
            # Une même ProduitLine ne doit pas avoir
            # plusieurs prix différents.
            prix_existant = grouped[
                plid
            ]["prix_vente_grammes"]

            if (
                prix_vente > ZERO
                and prix_existant > ZERO
                and prix_vente != prix_existant
            ):
                raise ValidationError({
                    f"produit_line_{plid}": (
                        "Une même ProduitLine ne peut pas "
                        "avoir plusieurs prix de vente "
                        "dans la même vente."
                    )
                })

            if (
                prix_existant <= ZERO
                and prix_vente > ZERO
            ):
                grouped[
                    plid
                ]["prix_vente_grammes"] = prix_vente

            # Remise/autres sont des montants de ligne.
            # Si la même PL apparaît plusieurs fois,
            # on les cumule.
            grouped[plid]["remise"] += remise
            grouped[plid]["autres"] += autres

        grouped[plid]["quantite"] += qty

    # =========================================================
    # 2. RÉSOLUTION VENDEUR + BIJOUTERIE
    # =========================================================

    vendor, bijouterie = (
        resolve_vendor_and_bijouterie_for_sale(
            role=role,
            user=user,
            vendor_email=payload.get(
                "vendor_email"
            ),
        )
    )

    if not vendor:
        raise ValidationError({
            "vendor": (
                "Le vendeur est obligatoire."
            )
        })

    if not bijouterie:
        raise ValidationError({
            "bijouterie": (
                "La bijouterie est obligatoire."
            )
        })

    if vendor.bijouterie_id != bijouterie.id:
        raise ValidationError({
            "vendor": (
                "Le vendeur n'appartient pas "
                "à la bijouterie sélectionnée."
            )
        })

    if not vendor.is_active_staff:
        raise ValidationError({
            "vendor": (
                "Ce vendeur est désactivé."
            )
        })

    # =========================================================
    # 3. CLIENT OPTIONNEL
    # =========================================================

    nom = (
        client_in.get("nom")
        or ""
    ).strip()

    prenom = (
        client_in.get("prenom")
        or ""
    ).strip()

    tel = (
        client_in.get("telephone")
        or ""
    ).strip()

    client = None

    if nom and prenom:

        lookup = (
            {
                "telephone": tel,
            }
            if tel
            else {
                "nom": nom,
                "prenom": prenom,
            }
        )

        client, _ = Client.objects.get_or_create(
            defaults={
                "nom": nom,
                "prenom": prenom,
                "telephone": tel or None,
            },
            **lookup,
        )

    elif any([
        nom,
        prenom,
        tel,
    ]):
        raise ValidationError({
            "client": (
                "nom et prenom sont obligatoires."
            )
        })

    # =========================================================
    # 4. PRÉCHARGEMENT PRODUIT_LINES
    # =========================================================

    produit_line_ids = list(
        grouped.keys()
    )

    produit_lines_qs = (
        ProduitLine.objects
        .select_related(
            "produit",
            "produit__marque",
            "produit__purete",
            "produit__categorie",
            "produit__modele",
            "lot",
        )
        .filter(
            id__in=produit_line_ids,
        )
    )

    produit_lines = {
        produit_line.id: produit_line
        for produit_line
        in produit_lines_qs
    }

    missing = [
        plid
        for plid in produit_line_ids
        if plid not in produit_lines
    ]

    if missing:
        raise ValidationError({
            "produits": (
                "ProduitLine introuvable(s) : "
                f"{missing}"
            )
        })

    # =========================================================
    # 5. VALIDATION PRODUIT_LINES
    # =========================================================

    for plid, produit_line in produit_lines.items():

        if not produit_line.produit_id:
            raise ValidationError({
                f"produit_line_{plid}": (
                    "Cette ProduitLine n'est associée "
                    "à aucun produit."
                )
            })

        if not produit_line.lot_id:
            raise ValidationError({
                f"produit_line_{plid}": (
                    "Cette ProduitLine n'est associée "
                    "à aucun lot."
                )
            })

    # =========================================================
    # 6. TARIFS MARQUE / PURETÉ
    # =========================================================

    pairs = {
        (
            produit_line.produit.marque_id,
            produit_line.produit.purete_id,
        )
        for produit_line
        in produit_lines.values()
        if (
            produit_line.produit.marque_id
            and produit_line.produit.purete_id
        )
    }

    tarifs = {}

    if pairs:

        marques = {
            marque_id
            for marque_id, _ in pairs
        }

        puretes = {
            purete_id
            for _, purete_id in pairs
        }

        mp_qs = MarquePurete.objects.filter(
            marque_id__in=marques,
            purete_id__in=puretes,
        )

        for mp in mp_qs:
            tarifs[
                (
                    mp.marque_id,
                    mp.purete_id,
                )
            ] = Decimal(
                str(mp.prix)
            )

    # =========================================================
    # 7. VÉRIFICATION STOCK VENDEUR EXACT
    #
    # IMPORTANT :
    # - ProduitLine exacte
    # - pas de FIFO
    # - aucune consommation ici
    # =========================================================

    for plid, data_item in grouped.items():

        produit_line = produit_lines[
            plid
        ]

        qte = data_item["quantite"]

        ensure_vendor_stock_available(
            vendor=vendor,
            bijouterie=bijouterie,
            produit_line=produit_line,
            quantite=qte,
        )

    # =========================================================
    # 8. CRÉATION VENTE
    # =========================================================

    vente = Vente.objects.create(
        client=client,
        created_by=user,
        bijouterie=bijouterie,
        vendor=vendor,
    )

    # =========================================================
    # 9. CRÉATION VENTE_PRODUIT
    # =========================================================

    for plid, data_item in grouped.items():

        produit_line = produit_lines[
            plid
        ]

        produit = produit_line.produit

        qte = data_item[
            "quantite"
        ]

        prix_vente = data_item[
            "prix_vente_grammes"
        ]

        # -----------------------------------------------------
        # Prix gramme
        # -----------------------------------------------------

        if (
            prix_vente is None
            or prix_vente <= ZERO
        ):
            prix_vente = tarifs.get(
                (
                    produit.marque_id,
                    produit.purete_id,
                )
            )

            if (
                prix_vente is None
                or prix_vente <= ZERO
            ):
                raise ValidationError({
                    f"produit_line_{plid}": (
                        "Tarif manquant pour "
                        f"{produit.nom}."
                    )
                })

        # -----------------------------------------------------
        # Snapshot réduction occasion
        # -----------------------------------------------------

        if getattr(
            produit,
            "etat",
            None,
        ) == "O":

            pourcentage_occasion = Decimal(
                str(
                    produit.pourcentage_occasion
                    or ZERO
                )
            )

        else:
            pourcentage_occasion = ZERO

        # -----------------------------------------------------
        # Création ligne
        #
        # IMPORTANT :
        # aucun champ produit=...
        # ProduitLine est la source de vérité.
        # -----------------------------------------------------

        VenteProduit.objects.create(
            vente=vente,
            produit_line=produit_line,
            vendor=vendor,
            quantite=qte,
            prix_vente_grammes=prix_vente,
            remise=data_item["remise"],
            autres=data_item["autres"],
            pourcentage_occasion=(
                pourcentage_occasion
            ),
        )

    # =========================================================
    # 10. RECALCUL MONTANT VENTE
    # =========================================================

    vente.mettre_a_jour_montant_total()

    # =========================================================
    # 11. SNAPSHOT TVA
    # =========================================================

    apply_tva = bool(
        getattr(
            bijouterie,
            "appliquer_tva",
            False,
        )
    )

    if apply_tva:

        taux_tva = Decimal(
            str(
                getattr(
                    bijouterie,
                    "taux_tva",
                    ZERO,
                )
                or ZERO
            )
        )

    else:
        taux_tva = ZERO

    # =========================================================
    # 12. CRÉATION FACTURE PROFORMA
    # =========================================================

    facture = Facture.objects.create(
        vente=vente,
        bijouterie=bijouterie,
        montant_ht=(
            vente.montant_total
            or ZERO
        ),
        appliquer_tva=apply_tva,
        taux_tva=taux_tva,
        status=Facture.STAT_NON_PAYE,
        type_facture=Facture.TYPE_PROFORMA,
    )

    return vente, facture, 0


# =============================================================
# VALIDATION FACTURE PAYABLE
# =============================================================


def validate_facture_payable(facture):
    """
    Vérifie que la facture peut encore être payée.
    """

    if facture.status == facture.STAT_PAYE:
        raise ValidationError(
            "Cette facture est déjà totalement payée."
        )

    if facture.type_facture == facture.TYPE_PROFORMA:
        return

    if facture.type_facture in {
        facture.TYPE_FACTURE,
        facture.TYPE_ACOMPTE,
        facture.TYPE_FINALE,
    }:
        return

    raise ValidationError(
        "Type de facture non pris en charge "
        "pour le paiement."
    )
    

