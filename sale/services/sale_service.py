# sale/services/sale_service.py

"""
Services de création des ventes Rio-Gold.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict

from django.core.exceptions import ValidationError
from django.db import transaction

from purchase.models import ProduitLine
from sale.models import (Client, ClientBijouterie, Facture, Vente, VenteAutre,
                         VenteProduit)
from sale.services.client_bijouterie_service import verifier_client_associe
from sale.services.sale_context_service import \
    resolve_vendor_and_bijouterie_for_sale
from sale.services.vendor_stock_service import (consume_vendor_stock,
                                                ensure_vendor_stock_available)
from store.models import MarquePurete
from vendor.services.qr_scan_service import decode_etiquette_qr

ZERO = Decimal("0.00")
TWOPLACES = Decimal("0.01")

POURCENTAGES_OCCASION = {
    Decimal(str(x))
    for x in (5, 10, 15, 20, 25, 30)
}


# ============================================================
# 1. CONVERSION DÉCIMALE
# ============================================================

def sale_decimal(
    value,
    *,
    field="montant",
    default=ZERO,
) -> Decimal:

    if value is None:
        return default

    if isinstance(value, str) and not value.strip():
        return default

    if isinstance(value, bool):
        raise ValidationError({
            field: "Valeur décimale invalide."
        })

    try:
        result = Decimal(str(value))

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ) as exc:
        raise ValidationError({
            field: "Valeur décimale invalide."
        }) from exc

    if not result.is_finite():
        raise ValidationError({
            field: "La valeur doit être un nombre fini."
        })

    return result


# ============================================================
# 2. ENTIER STRICTEMENT POSITIF
# ============================================================

def sale_positive_int(
    value,
    *,
    field="quantite",
) -> int:

    if isinstance(value, bool):
        raise ValidationError({
            field: "Un entier positif est attendu."
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
            field: "Un entier positif est attendu."
        })

    if result <= 0:
        raise ValidationError({
            field: "La quantité doit être supérieure à zéro."
        })

    return result


# ============================================================
# 3. COMPATIBILITÉ DES IMPORTS EXISTANTS
# ============================================================

def dec(
    value,
    *,
    field="montant",
):
    return sale_decimal(
        value,
        field=field,
    )


def positive_int(
    value,
    *,
    field="quantite",
):
    return sale_positive_int(
        value,
        field=field,
    )


def money(value) -> Decimal:

    result = sale_decimal(value)

    try:
        return result.quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )

    except InvalidOperation as exc:
        raise ValidationError({
            "montant": "Montant hors limites."
        }) from exc


# ============================================================
# 4. CALCUL DES MONTANTS
# ============================================================

def calculer_montants(
    *,
    montant_brut_ht,
    montant_reduction=ZERO,
    taux_tva=ZERO,
):

    brut = money(montant_brut_ht)
    reduction = money(montant_reduction)

    taux = sale_decimal(
        taux_tva,
        field="taux_tva",
    )

    if brut < ZERO:
        raise ValidationError({
            "montant_brut_ht": "Montant brut négatif."
        })

    if reduction < ZERO or reduction > brut:
        raise ValidationError({
            "montant_reduction": "Réduction invalide."
        })

    if not ZERO <= taux <= Decimal("100.00"):
        raise ValidationError({
            "taux_tva": "Taux TVA invalide."
        })

    montant_ht = money(brut - reduction)

    montant_tva = money(
        montant_ht * taux / Decimal("100")
    )

    return {
        "montant_brut_ht": brut,
        "montant_reduction": reduction,
        "montant_ht": montant_ht,
        "montant_tva": montant_tva,
        "montant_total": money(
            montant_ht + montant_tva
        ),
    }


# ============================================================
# 5. CLIENT AU MOMENT DU PAIEMENT
# ============================================================

@transaction.atomic
def upsert_client_for_payment(
    *,
    client_data: dict,
    facture=None,
    vente=None,
):
    """
    Associe un client à une vente.

    - Ne fusionne jamais automatiquement les clients.
    - Ne modifie pas une fiche client existante.
    - Vérifie l'association client/bijouterie.
    - Verrouille la vente pendant l'opération.
    """

    if facture is not None:

        if (
            vente is not None
            and facture.vente_id != vente.pk
        ):
            raise ValidationError({
                "vente": (
                    "La vente ne correspond pas "
                    "à la facture."
                )
            })

        vente = facture.vente

    if vente is None:
        raise ValidationError({
            "vente": (
                "Une vente ou une facture "
                "est obligatoire."
            )
        })

    if not isinstance(client_data, dict):
        raise ValidationError({
            "client": "Un objet JSON est attendu."
        })

    try:
        vente = (
            Vente.objects
            .select_for_update()
            .select_related(
                "bijouterie",
                "client",
            )
            .get(pk=vente.pk)
        )

    except Vente.DoesNotExist as exc:
        raise ValidationError({
            "vente": "Vente introuvable."
        }) from exc

    bijouterie = vente.bijouterie
    client = vente.client

    nom = str(
        client_data.get("nom") or ""
    ).strip()

    prenom = str(
        client_data.get("prenom") or ""
    ).strip()

    telephone = str(
        client_data.get("telephone") or ""
    ).strip()

    # --------------------------------------------------------
    # CLIENT DÉJÀ ASSOCIÉ À LA VENTE
    # --------------------------------------------------------

    if client is not None:

        verifier_client_associe(
            client=client,
            bijouterie=bijouterie,
        )

        if (
            telephone
            and Client.objects.filter(
                telephone=telephone
            ).exclude(
                pk=client.pk
            ).exists()
        ):
            raise ValidationError({
                "telephone": (
                    "Ce téléphone appartient "
                    "à un autre client."
                )
            })

        return client

    # --------------------------------------------------------
    # CLIENT EXISTANT
    # --------------------------------------------------------

    client_id = client_data.get("id")

    if client_id not in (None, ""):

        client_id = sale_positive_int(
            client_id,
            field="client.id",
        )

        client = (
            Client.objects
            .filter(pk=client_id)
            .first()
        )

        if client is None:
            raise ValidationError({
                "client": "Client introuvable."
            })

        verifier_client_associe(
            client=client,
            bijouterie=bijouterie,
        )

    # --------------------------------------------------------
    # NOUVEAU CLIENT
    # --------------------------------------------------------

    else:

        if not nom or not prenom:
            raise ValidationError({
                "client": (
                    "Le nom et le prénom sont "
                    "obligatoires pour créer "
                    "une nouvelle fiche client."
                )
            })

        if (
            telephone
            and Client.objects.filter(
                telephone=telephone
            ).exists()
        ):
            raise ValidationError({
                "client": (
                    "Un client existe déjà avec "
                    "ce téléphone. Vérifiez son "
                    "identité et sélectionnez "
                    "sa fiche."
                )
            })

        client = Client.objects.create(
            nom=nom,
            prenom=prenom,
            telephone=telephone or None,
        )

        ClientBijouterie.objects.get_or_create(
            client=client,
            bijouterie=bijouterie,
        )

    vente.client = client

    vente.full_clean()

    vente.save(
        update_fields=["client"]
    )

    return client


# ============================================================
# 6. RECHERCHE PRODUITLINE PAR ID OU QR
# ============================================================

def resolve_produit_line_for_sale(
    item,
    *,
    index,
):
    """
    Résout une ProduitLine.

    Accepte :
        produit_line_id
    OU :
        qr = PL:<uuid>

    Ne modifie jamais le stock.
    """

    if not isinstance(item, dict):
        raise ValidationError({
            f"produits[{index}]": (
                "Un objet JSON est attendu."
            )
        })

    line_id = item.get("produit_line_id")
    qr = item.get("qr")

    has_id = line_id not in (None, "")
    has_qr = qr not in (None, "")

    if has_id == has_qr:
        raise ValidationError({
            f"produits[{index}]": (
                "Fournissez exactement "
                "produit_line_id ou qr."
            )
        })

    if has_id:

        pk = sale_positive_int(
            line_id,
            field=(
                f"produits[{index}].produit_line_id"
            ),
        )

        ligne = (
            ProduitLine.objects
            .filter(pk=pk)
            .first()
        )

    else:

        try:
            line_uuid = decode_etiquette_qr(qr)

        except (
            ValueError,
            TypeError,
            AttributeError,
        ) as exc:
            raise ValidationError({
                f"produits[{index}].qr": str(exc)
            }) from exc

        ligne = (
            ProduitLine.objects
            .filter(uuid=line_uuid)
            .first()
        )

    if ligne is None:
        raise ValidationError({
            f"produits[{index}]": (
                "Ligne de produit introuvable."
            )
        })

    return ligne


# ============================================================
# 7. CRÉATION D'UNE VENTE
# ============================================================

@transaction.atomic
def create_sale_one_vendor(
    *,
    user,
    role: str,
    payload: Dict,
) -> tuple[Vente, Facture | None, int]:
    """
    Crée une vente Rio-Gold.

    Bijoux seuls :
        Vente + VenteProduit + Facture proforma.

    Vente mixte :
        Vente + VenteProduit + VenteAutre
        + Facture proforma.

    Prestations seules :
        Vente + VenteAutre.
        Aucune facture.

    Stock :
        Consommation à la création de la vente.

    Retour :
        (vente, facture_ou_none, 0)
    """

    # ========================================================
    # 1. VALIDATION DU PAYLOAD
    # ========================================================

    if not isinstance(payload, dict):
        raise ValidationError({
            "payload": "Un objet JSON est attendu."
        })

    produits_in = payload.get("produits") or []
    autres_in = payload.get("autres") or []
    client_in = payload.get("client") or {}

    if not isinstance(produits_in, list):
        raise ValidationError({
            "produits": "Une liste est attendue."
        })

    if not isinstance(autres_in, list):
        raise ValidationError({
            "autres": "Une liste est attendue."
        })

    if not isinstance(client_in, dict):
        raise ValidationError({
            "client": "Un objet JSON est attendu."
        })

    if not produits_in and not autres_in:
        raise ValidationError({
            "vente": (
                "Au moins un bijou ou une prestation "
                "est obligatoire."
            )
        })

    # ========================================================
    # 2. VENDEUR ET BIJOUTERIE
    # ========================================================

    vendor, bijouterie = (
        resolve_vendor_and_bijouterie_for_sale(
            role=role,
            user=user,
            vendor_email=payload.get(
                "vendor_email"
            ),
        )
    )

    if (
        vendor is None
        or bijouterie is None
        or not vendor.verifie
    ):
        raise ValidationError({
            "vendor": (
                "Vendeur ou bijouterie introuvable "
                "ou désactivé."
            )
        })

    if vendor.bijouterie_id != bijouterie.pk:
        raise ValidationError({
            "bijouterie": (
                "Le vendeur appartient "
                "à une autre bijouterie."
            )
        })

    # ========================================================
    # 3. REGROUPEMENT DES BIJOUX
    # ========================================================

    grouped = {}

    for index, item in enumerate(produits_in):

        produit_line = resolve_produit_line_for_sale(
            item,
            index=index,
        )

        line_id = produit_line.pk

        quantite = sale_positive_int(
            item.get("quantite", 1),
            field=f"produits[{index}].quantite",
        )

        prix_vente = sale_decimal(
            item.get("prix_vente_grammes"),
            field=(
                f"produits[{index}]."
                "prix_vente_grammes"
            ),
        )

        remise = sale_decimal(
            item.get("remise"),
            field=f"produits[{index}].remise",
        )

        if prix_vente < ZERO or remise < ZERO:
            raise ValidationError({
                f"produits[{index}]": (
                    "Le prix et la remise "
                    "ne peuvent pas être négatifs."
                )
            })

        if line_id in grouped:

            previous = grouped[line_id]

            if (
                previous["prix_vente_grammes"]
                != prix_vente
                or previous["remise"] != remise
            ):
                raise ValidationError({
                    "produits": (
                        f"ProduitLine {line_id} "
                        "avec prix ou remises différents."
                    )
                })

            previous["quantite"] += quantite

        else:

            grouped[line_id] = {
                "quantite": quantite,
                "prix_vente_grammes": prix_vente,
                "remise": remise,
            }

    # ========================================================
    # 4. CHARGEMENT DES PRODUITLINE
    # ========================================================

    line_ids = list(grouped)

    produit_lines = {
        ligne.pk: ligne
        for ligne in (
            ProduitLine.objects
            .select_related(
                "produit",
                "produit__marque",
                "produit__purete",
                "lot",
                "lot__achat",
            )
            .filter(pk__in=line_ids)
        )
    }

    if len(produit_lines) != len(line_ids):
        raise ValidationError({
            "produits": (
                "Certaines lignes d'achat "
                "sont introuvables."
            )
        })

    # ========================================================
    # 5. TARIFS MARQUE / PURETÉ
    # ========================================================

    pairs = {
        (
            ligne.produit.marque_id,
            ligne.produit.purete_id,
        )
        for ligne in produit_lines.values()
        if (
            ligne.produit.marque_id
            and ligne.produit.purete_id
        )
    }

    tarifs = {}

    if pairs:

        for tarif in MarquePurete.objects.filter(
            marque_id__in={
                p[0] for p in pairs
            },
            purete_id__in={
                p[1] for p in pairs
            },
        ):

            key = (
                tarif.marque_id,
                tarif.purete_id,
            )

            if key in pairs:
                tarifs[key] = sale_decimal(
                    tarif.prix,
                    field="tarif",
                )

    # ========================================================
    # 6. PRÉPARATION DES BIJOUX
    # ========================================================

    lignes_preparees = []

    for line_id, data in grouped.items():

        produit_line = produit_lines[line_id]
        produit = produit_line.produit

        if not produit_line.lot_id:
            raise ValidationError({
                f"produit_line_{line_id}": (
                    "Lot manquant."
                )
            })

        if (
            produit_line.lot.achat.bijouterie_id
            != bijouterie.pk
        ):
            raise ValidationError({
                f"produit_line_{line_id}": (
                    "Ce bijou appartient "
                    "à une autre bijouterie."
                )
            })

        quantite = data["quantite"]
        prix_vente = data["prix_vente_grammes"]
        remise = data["remise"]

        if prix_vente <= ZERO:

            prix_vente = tarifs.get(
                (
                    produit.marque_id,
                    produit.purete_id,
                ),
                ZERO,
            )

        if prix_vente <= ZERO:
            raise ValidationError({
                f"produit_line_{line_id}": (
                    "Prix de vente au gramme manquant."
                )
            })

        poids = sale_decimal(
            produit_line.poids_unitaire_achat,
            field=(
                f"produit_line_{line_id}."
                "poids_unitaire_achat"
            ),
        )

        if poids <= ZERO:
            raise ValidationError({
                f"produit_line_{line_id}": (
                    "Le poids doit être "
                    "supérieur à zéro."
                )
            })

        pourcentage = sale_decimal(
            produit_line.pourcentage_occasion,
            field=(
                f"produit_line_{line_id}."
                "pourcentage_occasion"
            ),
        )

        # ----------------------------------------------------
        # BIJOU D'OCCASION
        # ----------------------------------------------------

        if produit_line.etat == "O":

            if (
                pourcentage
                not in POURCENTAGES_OCCASION
            ):
                raise ValidationError({
                    f"produit_line_{line_id}": (
                        "Pourcentage occasion invalide : "
                        "5, 10, 15, 20, 25 ou 30 %."
                    )
                })

            if remise != ZERO:
                raise ValidationError({
                    f"produit_line_{line_id}": (
                        "Remise fixe interdite "
                        "pour un bijou d'occasion."
                    )
                })

            remise = ZERO

        # ----------------------------------------------------
        # BIJOU NEUF
        # ----------------------------------------------------

        elif produit_line.etat == "N":

            if pourcentage != ZERO:
                raise ValidationError({
                    f"produit_line_{line_id}": (
                        "Un bijou neuf doit avoir "
                        "0 % d'occasion."
                    )
                })

        else:
            raise ValidationError({
                f"produit_line_{line_id}": (
                    "État du bijou invalide."
                )
            })

        montant_brut = money(
            prix_vente * poids * quantite
        )

        if remise > montant_brut:
            raise ValidationError({
                f"produit_line_{line_id}": (
                    "La remise dépasse "
                    "le montant brut."
                )
            })

        lignes_preparees.append({
            "produit_line": produit_line,
            "quantite": quantite,
            "prix_vente_grammes": prix_vente,
            "remise": remise,
        })

    # ========================================================
    # 7. PRÉPARATION DES PRESTATIONS
    # ========================================================

    types_autorises = {
        choice[0]
        for choice in VenteAutre.TYPE_CHOICES
    }

    prestations_preparees = []

    for index, item in enumerate(autres_in):

        if not isinstance(item, dict):
            raise ValidationError({
                f"autres[{index}]": (
                    "Un objet JSON est attendu."
                )
            })

        type_autre = item.get("type_autre")

        if type_autre not in types_autorises:
            raise ValidationError({
                f"autres[{index}].type_autre": (
                    "Type de prestation invalide."
                )
            })

        quantite = sale_positive_int(
            item.get("quantite", 1),
            field=f"autres[{index}].quantite",
        )

        prix_unitaire = sale_decimal(
            item.get("prix_unitaire"),
            field=f"autres[{index}].prix_unitaire",
        )

        if prix_unitaire < ZERO:
            raise ValidationError({
                f"autres[{index}].prix_unitaire": (
                    "Le prix ne peut pas être négatif."
                )
            })

        prestations_preparees.append({
            "type_autre": type_autre,
            "quantite": quantite,
            "prix_unitaire": prix_unitaire,
        })

    # ========================================================
    # 8. VÉRIFICATION DU STOCK VENDEUR
    # ========================================================

    # Contrôle préalable sans modification.
    # La disponibilité sera vérifiée à nouveau
    # sous verrou par consume_vendor_stock().

    for data in sorted(
        lignes_preparees,
        key=lambda x: x["produit_line"].pk,
    ):

        ensure_vendor_stock_available(
            vendor=vendor,
            bijouterie=bijouterie,
            produit_line=data["produit_line"],
            quantite=data["quantite"],
        )

    # ========================================================
    # 9. VÉRIFICATION DU CLIENT
    # ========================================================

    client = None

    client_id = client_in.get("id")

    if client_id not in (None, ""):

        client_id = sale_positive_int(
            client_id,
            field="client.id",
        )

        client = (
            Client.objects
            .filter(pk=client_id)
            .first()
        )

        if client is None:
            raise ValidationError({
                "client": "Client introuvable."
            })

        verifier_client_associe(
            client=client,
            bijouterie=bijouterie,
        )

    # Les prestations seules ne demandent pas
    # les informations du client à la création.
    # Elles seront demandées au paiement.

    if not lignes_preparees and client is not None:
        raise ValidationError({
            "client": (
                "Pour une vente contenant uniquement "
                "des prestations, le client est "
                "identifié au moment du paiement."
            )
        })

    # ========================================================
    # 10. CRÉATION DE LA VENTE
    # ========================================================

    vente = Vente(
        client=client,
        created_by=user,
        bijouterie=bijouterie,
        vendor=vendor,
    )

    vente.full_clean()

    vente.save(
        prefixe_operation=(
            "VENTE"
            if lignes_preparees
            else "PREST"
        )
    )

    # ========================================================
    # 11. CRÉATION DES BIJOUX ET CONSOMMATION DU STOCK
    # ========================================================

    for data in sorted(
        lignes_preparees,
        key=lambda x: x["produit_line"].pk,
    ):

        produit_line = data["produit_line"]
        quantite = data["quantite"]

        # Création de la ligne de vente.
        # VenteProduit.save() ne déduit pas le stock.

        VenteProduit.objects.create(
            vente=vente,
            produit_line=produit_line,
            vendor=vendor,
            quantite=quantite,
            prix_vente_grammes=(
                data["prix_vente_grammes"]
            ),
            remise=data["remise"],
        )

        # Consommation réelle du stock vendeur.
        # Le service utilise select_for_update()
        # et incrémente quantite_vendue.

        consume_vendor_stock(
            vendor=vendor,
            bijouterie=bijouterie,
            produit_line=produit_line,
            quantite=quantite,
        )

        # INTÉGRATION RESTANTE :
        # Enregistrer ici InventoryMovement.SALE_OUT
        # avec le modèle/service réel du projet.
        #
        # Ne pas créer un mouvement fictif :
        # il doit être sauvegardé en base dans
        # cette même transaction atomique.

    # ========================================================
    # 12. CRÉATION DES PRESTATIONS
    # ========================================================

    for data in prestations_preparees:

        VenteAutre.objects.create(
            vente=vente,
            **data,
        )

    # ========================================================
    # 13. RECALCUL DU TOTAL DE LA VENTE
    # ========================================================

    vente.mettre_a_jour_montant_total()

    vente.refresh_from_db()

    # ========================================================
    # 14. PRESTATIONS SEULES : AUCUNE FACTURE
    # ========================================================

    if not lignes_preparees:

        return vente, None, 0

    # ========================================================
    # 15. CONFIGURATION TVA
    # ========================================================

    appliquer_tva = bool(
        bijouterie.appliquer_tva
    )

    if appliquer_tva:

        if bijouterie.taux_tva is None:
            raise ValidationError({
                "taux_tva": (
                    "TVA activée mais aucun "
                    "taux configuré."
                )
            })

        taux_tva = sale_decimal(
            bijouterie.taux_tva,
            field="taux_tva",
        )

        if not ZERO <= taux_tva <= Decimal("100.00"):
            raise ValidationError({
                "taux_tva": (
                    "Le taux de TVA doit être "
                    "compris entre 0 et 100."
                )
            })

    else:
        taux_tva = ZERO

    # ========================================================
    # 16. CRÉATION DE LA FACTURE PROFORMA
    # ========================================================

    facture = Facture.objects.create(
        vente=vente,
        bijouterie=bijouterie,
        montant_ht=vente.montant_total or ZERO,
        appliquer_tva=appliquer_tva,
        taux_tva=taux_tva,
        status=Facture.STAT_NON_PAYE,
        type_facture=Facture.TYPE_PROFORMA,
        stock_consumed=True,
    )

    # ========================================================
    # 17. RÉSULTAT
    # ========================================================

    return vente, facture, 0


# ============================================================
# 8. VALIDATION FACTURE PAYABLE
# ============================================================

def validate_facture_payable(facture):
    """
    Vérifie qu'une facture peut recevoir
    un nouveau paiement.
    """

    if facture is None:
        raise ValidationError({
            "facture": "Facture obligatoire."
        })

    if facture.status == facture.STAT_PAYE:
        raise ValidationError(
            "Cette facture est déjà totalement payée."
        )

    types_autorises = {
        facture.TYPE_PROFORMA,
        facture.TYPE_FACTURE,
        facture.TYPE_ACOMPTE,
        facture.TYPE_FINALE,
    }

    if facture.type_facture not in types_autorises:
        raise ValidationError(
            "Type de facture non pris en charge "
            "pour le paiement."
        )

    return
