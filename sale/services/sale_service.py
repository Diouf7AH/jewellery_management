# sale/services/sale_service.py
from __future__ import annotations

from decimal import Decimal
from typing import Dict

from django.core.exceptions import ValidationError
from django.db import transaction

from sale.models import Client, Facture, Vente, VenteProduit
from sale.services.sale_context_service import (
    dec, resolve_vendor_and_bijouterie_for_sale)
from sale.services.vendor_stock_service import ensure_vendor_stock_available
from sale.utils import ZERO
from store.models import MarquePurete, Produit


def upsert_client_for_payment(*, facture, client_data: dict):
    if not facture.vente:
        raise ValidationError({"facture": "Aucune vente associée à cette facture."})

    nom = (client_data.get("nom") or "").strip()
    prenom = (client_data.get("prenom") or "").strip()
    telephone = (client_data.get("telephone") or "").strip()

    if not nom or not prenom:
        raise ValidationError({"client": "nom et prenom sont obligatoires au paiement."})

    vente = facture.vente
    client = getattr(vente, "client", None)

    existing_by_phone = None
    if telephone:
        existing_by_phone = Client.objects.filter(telephone=telephone).first()

    if client:
        if existing_by_phone and existing_by_phone.id != client.id:
            raise ValidationError({
                "telephone": (
                    f"Ce téléphone est déjà utilisé par un autre client : "
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

        if telephone and client.telephone != telephone:
            client.telephone = telephone
            changed_fields.append("telephone")

        if changed_fields:
            client.save(update_fields=changed_fields)

        return client

    if existing_by_phone:
        vente.client = existing_by_phone
        vente.save(update_fields=["client"])
        return existing_by_phone

    client = Client.objects.create(
        nom=nom,
        prenom=prenom,
        telephone=telephone or None,
    )

    vente.client = client
    vente.save(update_fields=["client"])
    return client



def dec(v):
    try:
        if v in [None, "", "null"]:
            return ZERO
        return Decimal(str(v))
    except Exception:
        return ZERO


ZERO = Decimal("0.00")


@transaction.atomic
def create_sale_one_vendor(
    *,
    user,
    role: str,
    payload: Dict,
) -> tuple[Vente, Facture, int]:

    """
    Création vente PROFORMA pour un seul vendeur.

    Règles :
    - ne consomme PAS le stock ici ;
    - vérifie uniquement la disponibilité VendorStock ;
    - le stock sera consommé au paiement ;
    - le prix/gramme est figé dans VenteProduit ;
    - le pourcentage occasion est figé dans VenteProduit ;
    - la TVA est figée dans Facture.
    """

    client_in = payload.get("client") or {}
    items = payload.get("produits") or []

    if not items:
        raise ValidationError({
            "produits": "Au moins un produit est requis."
        })

    # =========================================================
    # 1. Agrégation produits
    # =========================================================

    grouped = {}

    for item in items:
        produit_id = item.get("produit_id")

        if not produit_id:
            raise ValidationError({
                "produit_id": "Champ requis."
            })

        try:
            pid = int(produit_id)
        except (TypeError, ValueError):
            raise ValidationError({
                "produit_id": "Doit être un entier."
            })

        try:
            qty = int(item.get("quantite") or 0)
        except (TypeError, ValueError):
            raise ValidationError({
                f"produit_{pid}": "Quantité invalide."
            })

        if qty <= 0:
            raise ValidationError({
                f"produit_{pid}": "Quantité invalide."
            })

        if pid not in grouped:
            grouped[pid] = {
                "quantite": 0,
                "prix_vente_grammes": dec(
                    item.get("prix_vente_grammes")
                ),
                "remise": dec(item.get("remise")) or ZERO,
                "autres": dec(item.get("autres")) or ZERO,
            }

        grouped[pid]["quantite"] += qty

    # =========================================================
    # 2. Résolution vendeur + bijouterie
    # =========================================================

    vendor, bijouterie = resolve_vendor_and_bijouterie_for_sale(
        role=role,
        user=user,
        vendor_email=payload.get("vendor_email"),
    )

    # =========================================================
    # 3. Client optionnel
    # =========================================================

    nom = (client_in.get("nom") or "").strip()
    prenom = (client_in.get("prenom") or "").strip()
    tel = (client_in.get("telephone") or "").strip()

    client = None

    if nom and prenom:
        lookup = (
            {"telephone": tel}
            if tel
            else {"nom": nom, "prenom": prenom}
        )

        client, _ = Client.objects.get_or_create(
            defaults={
                "nom": nom,
                "prenom": prenom,
                "telephone": tel or None,
            },
            **lookup,
        )

    elif any([nom, prenom, tel]):
        raise ValidationError({
            "client": "nom et prenom sont obligatoires."
        })

    # =========================================================
    # 4. Préchargement produits
    # =========================================================

    produit_ids = list(grouped.keys())

    produits_qs = (
        Produit.objects
        .select_related(
            "marque",
            "purete",
            "categorie",
            "modele",
        )
        .filter(id__in=produit_ids)
    )

    produits = {
        produit.id: produit
        for produit in produits_qs
    }

    missing = [
        pid
        for pid in produit_ids
        if pid not in produits
    ]

    if missing:
        raise ValidationError({
            "produits": f"Produits introuvables : {missing}"
        })

    # =========================================================
    # 5. Tarifs MarquePurete
    # =========================================================

    pairs = {
        (produit.marque_id, produit.purete_id)
        for produit in produits.values()
        if produit.marque_id and produit.purete_id
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
                (mp.marque_id, mp.purete_id)
            ] = Decimal(str(mp.prix))

    # =========================================================
    # 6. Vérification stock vendeur
    #
    # IMPORTANT :
    # aucune consommation ici
    # =========================================================

    for pid, data_item in grouped.items():
        produit = produits[pid]
        qte = data_item["quantite"]

        ensure_vendor_stock_available(
            vendor=vendor,
            bijouterie=bijouterie,
            produit=produit,
            quantite=qte,
        )

    # =========================================================
    # 7. Création Vente
    # =========================================================

    vente = Vente.objects.create(
        client=client,
        created_by=user,
        bijouterie=bijouterie,
        vendor=vendor,
    )

    # =========================================================
    # 8. Création lignes VenteProduit
    # =========================================================

    for pid, data_item in grouped.items():
        produit = produits[pid]
        qte = data_item["quantite"]

        prix_vente = data_item[
            "prix_vente_grammes"
        ]

        # -----------------------------------------------------
        # Prix gramme
        # -----------------------------------------------------

        if prix_vente is None or prix_vente <= ZERO:
            prix_vente = tarifs.get(
                (
                    produit.marque_id,
                    produit.purete_id,
                )
            )

            if prix_vente is None or prix_vente <= ZERO:
                raise ValidationError({
                    f"produit_{pid}": (
                        f"Tarif manquant pour "
                        f"{produit.nom}."
                    )
                })

        # -----------------------------------------------------
        # Snapshot pourcentage occasion
        # -----------------------------------------------------

        if getattr(produit, "etat", None) == "O":
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
        # VenteProduit.save() calcule montant_ht / montant_total
        # -----------------------------------------------------

        VenteProduit.objects.create(
            vente=vente,
            produit=produit,
            vendor=vendor,
            quantite=qte,
            prix_vente_grammes=prix_vente,
            remise=data_item["remise"],
            autres=data_item["autres"],
            pourcentage_occasion=pourcentage_occasion,
        )

    # =========================================================
    # 9. Recalcul montant Vente
    # =========================================================

    vente.mettre_a_jour_montant_total()

    # =========================================================
    # 10. Snapshot TVA
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
    # 11. Création facture PROFORMA
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


def validate_facture_payable(facture):
    """
    Vérifie que la facture peut encore être payée.
    """
    if facture.status == facture.STAT_PAYE:
        raise ValidationError("Cette facture est déjà totalement payée.")

    if facture.type_facture == facture.TYPE_PROFORMA:
        return

    if facture.type_facture in {
        facture.TYPE_FACTURE,
        facture.TYPE_ACOMPTE,
        facture.TYPE_FINALE,
    }:
        return

    raise ValidationError("Type de facture non pris en charge pour le paiement.")

