"""Services de création des ventes Rio-Gold."""
# sale/services/sale_service.py
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Dict
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction

from purchase.models import ProduitLine
from sale.models import Client, Facture, Vente, VenteAutre, VenteProduit
from sale.services.sale_context_service import \
    resolve_vendor_and_bijouterie_for_sale
from stock.models import VendorStock
from store.models import MarquePurete

ZERO = Decimal("0.00")

TWOPLACES = Decimal("0.01")

POURCENTAGES_OCCASION = {

    Decimal("5.00"),

    Decimal("10.00"),

    Decimal("15.00"),

    Decimal("20.00"),

    Decimal("25.00"),

    Decimal("30.00"),

}

# ============================================================

# HELPERS

# ============================================================

def sale_decimal(value, *, field="montant", default=ZERO):

    if value is None or value == "":

        return default

    try:

        result = Decimal(str(value))

    except (InvalidOperation, TypeError, ValueError):

        raise ValidationError({

            field: "Valeur décimale invalide."

        })

    if not result.is_finite():

        raise ValidationError({

            field: "La valeur doit être un nombre fini."

        })

    return result

def sale_positive_int(value, *, field="quantite"):

    if isinstance(value, bool):

        raise ValidationError({

            field: "Un entier positif est attendu."

        })

    try:

        result = int(str(value))

    except (TypeError, ValueError, OverflowError):

        raise ValidationError({

            field: "Un entier positif est attendu."

        })

    if result <= 0 or str(value).strip() != str(result):

        raise ValidationError({

            field: "Un entier positif est attendu."

        })

    return result

# Alias de compatibilité pour les imports existants.

def dec(value, *, field="montant"):

    return sale_decimal(value, field=field)

def positive_int(value, *, field="quantite"):

    return sale_positive_int(value, field=field)

def money(value):

    result = sale_decimal(value, field="montant")

    try:

        return result.quantize(

            TWOPLACES,

            rounding=ROUND_HALF_UP,

        )

    except InvalidOperation:

        raise ValidationError({

            "montant": "Montant hors limites."

        })

def calculer_montants(

    *,

    montant_brut_ht,

    montant_reduction=ZERO,

    taux_tva=ZERO,

):

    brut = money(montant_brut_ht)

    reduction = money(montant_reduction)

    taux = sale_decimal(taux_tva, field="taux_tva")

    if brut < ZERO:

        raise ValidationError({

            "montant_brut_ht": "Montant brut négatif."

        })

    if reduction < ZERO or reduction > brut:

        raise ValidationError({

            "montant_reduction": "Réduction invalide."

        })

    if taux < ZERO:

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

        "montant_total": money(montant_ht + montant_tva),

    }

# ============================================================

# CLIENT AU PAIEMENT

# ============================================================

def upsert_client_for_payment(

    *,

    client_data: dict,

    facture=None,

    vente=None,

):

    if facture is not None:

        if vente is not None and facture.vente_id != vente.pk:

            raise ValidationError({

                "vente": "La vente ne correspond pas à la facture."

            })

        vente = facture.vente

    if vente is None:

        raise ValidationError({

            "vente": "Une vente ou une facture est obligatoire."

        })

    if not isinstance(client_data, dict):

        raise ValidationError({

            "client": "Un objet est attendu."

        })

    nom = str(client_data.get("nom") or "").strip()

    prenom = str(client_data.get("prenom") or "").strip()

    telephone = str(client_data.get("telephone") or "").strip()

    if not nom or not prenom:

        raise ValidationError({

            "client": "nom et prenom sont obligatoires au paiement."

        })

    client = vente.client

    existing_by_phone = None

    if telephone:

        existing_by_phone = (

            Client.objects

            .filter(telephone=telephone)

            .first()

        )

    if client is not None:

        if (

            existing_by_phone is not None

            and existing_by_phone.pk != client.pk

        ):

            raise ValidationError({

                "telephone": "Ce téléphone appartient à un autre client."

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

    if existing_by_phone is not None:

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

# ============================================================

# RECHERCHE MANUELLE OU QR CODE

# ============================================================

def resolve_produit_line_for_sale(item, *, index):

    produit_line_id = item.get("produit_line_id")

    qr = item.get("qr")

    if produit_line_id is not None and qr:

        raise ValidationError({

            f"produits[{index}]": (

                "Fournissez produit_line_id ou qr, pas les deux."

            )

        })

    if produit_line_id is None and not qr:

        raise ValidationError({

            f"produits[{index}]": (

                "produit_line_id ou qr est obligatoire."

            )

        })

    if produit_line_id is not None:

        line_id = sale_positive_int(

            produit_line_id,

            field=f"produits[{index}].produit_line_id",

        )

        produit_line = (

            ProduitLine.objects

            .filter(pk=line_id)

            .first()

        )

    else:

        try:

            scan_value = str(qr).strip()

            if scan_value.upper().startswith("PL:"):
                scan_value = scan_value[3:].strip()

            line_uuid = UUID(scan_value)

        except (ValueError, TypeError, AttributeError):

            raise ValidationError({

                f"produits[{index}].qr": "UUID invalide."

            })

        produit_line = (

            ProduitLine.objects

            .filter(uuid=line_uuid)

            .first()

        )

    if produit_line is None:

        raise ValidationError({

            f"produits[{index}]": "ProduitLine introuvable."

        })

    return produit_line

# ============================================================

# CRÉATION DE VENTE

# ============================================================

@transaction.atomic

def create_sale_one_vendor(

    *,

    user,

    role: str,

    payload: Dict,

) -> tuple[Vente, Facture | None, int]:

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

            "client": "Un objet est attendu."

        })

    if not produits_in and not autres_in:

        raise ValidationError({

            "vente": "Au moins un bijou ou une prestation est obligatoire."

        })

    # 1. Vendeur et bijouterie

    vendor, bijouterie = resolve_vendor_and_bijouterie_for_sale(

        role=role,

        user=user,

        vendor_email=payload.get("vendor_email"),

    )

    if vendor is None or bijouterie is None:

        raise ValidationError({

            "vendor": "Vendeur ou bijouterie introuvable."

        })

    if not getattr(vendor, "verifie", False):

        raise ValidationError({

            "vendor": "Le vendeur est désactivé."

        })

    if vendor.bijouterie_id != bijouterie.pk:

        raise ValidationError({

            "bijouterie": "Le vendeur appartient à une autre bijouterie."

        })

    # 2. Regroupement des bijoux

    grouped = {}

    for index, item in enumerate(produits_in):

        if not isinstance(item, dict):

            raise ValidationError({

                f"produits[{index}]": "Un objet JSON est attendu."

            })

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

            field=f"produits[{index}].prix_vente_grammes",

        )

        remise = sale_decimal(

            item.get("remise"),

            field=f"produits[{index}].remise",

        )

        if prix_vente < ZERO or remise < ZERO:

            raise ValidationError({

                f"produits[{index}]": (

                    "Le prix et la remise ne peuvent pas être négatifs."

                )

            })

        if line_id in grouped:

            previous = grouped[line_id]

            if (

                previous["prix_vente_grammes"] != prix_vente

                or previous["remise"] != remise

            ):

                raise ValidationError({

                    "produits": (

                        f"ProduitLine {line_id} apparaît "

                        "avec des prix ou remises différents."

                    )

                })

            previous["quantite"] += quantite

        else:

            grouped[line_id] = {

                "quantite": quantite,

                "prix_vente_grammes": prix_vente,

                "remise": remise,

            }

    # 3. Chargement des lignes d'achat

    line_ids = list(grouped.keys())

    produit_lines = {

        ligne.pk: ligne

        for ligne in (

            ProduitLine.objects

            .select_related(

                "produit",

                "produit__marque",

                "produit__purete",

                "lot",

            )

            .filter(pk__in=line_ids)

        )

    }

    if len(produit_lines) != len(line_ids):

        raise ValidationError({

            "produits": "Certaines lignes d'achat sont introuvables."

        })

    # 4. Tarifs de vente

    pairs = {

        (ligne.produit.marque_id, ligne.produit.purete_id)

        for ligne in produit_lines.values()

        if ligne.produit.marque_id and ligne.produit.purete_id

    }

    tarifs = {}

    if pairs:

        marque_ids = {marque for marque, _ in pairs}

        purete_ids = {purete for _, purete in pairs}

        for tarif in MarquePurete.objects.filter(

            marque_id__in=marque_ids,

            purete_id__in=purete_ids,

        ):

            key = (tarif.marque_id, tarif.purete_id)

            if key in pairs:

                tarifs[key] = sale_decimal(

                    tarif.prix,

                    field="tarif",

                )

    # 5. Validation des bijoux

    lignes_preparees = []

    for line_id, data in grouped.items():

        produit_line = produit_lines[line_id]

        produit = produit_line.produit

        if not produit_line.lot_id:

            raise ValidationError({

                f"produit_line_{line_id}": "Lot manquant."

            })

        if produit_line.lot.achat.bijouterie_id != bijouterie.pk:

            raise ValidationError({

                f"produit_line_{line_id}": (

                    "Ce bijou appartient à une autre bijouterie."

                )

            })

        quantite = data["quantite"]

        prix_vente = data["prix_vente_grammes"]

        remise = data["remise"]

        if prix_vente <= ZERO:

            prix_vente = tarifs.get(

                (produit.marque_id, produit.purete_id),

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

            field=f"produit_line_{line_id}.poids_unitaire_achat",

        )

        if poids <= ZERO:

            raise ValidationError({

                f"produit_line_{line_id}": (

                    "Le poids doit être supérieur à zéro."

                )

            })

        pourcentage = sale_decimal(

            produit_line.pourcentage_occasion,

            field=f"produit_line_{line_id}.pourcentage_occasion",

        )

        if produit_line.etat == "O":

            if pourcentage not in POURCENTAGES_OCCASION:

                raise ValidationError({

                    f"produit_line_{line_id}": (

                        "Pourcentage occasion invalide : "

                        "5, 10, 15, 20, 25 ou 30 %."

                    )

                })

            if remise != ZERO:

                raise ValidationError({

                    f"produit_line_{line_id}": (

                        "Remise fixe interdite pour un bijou d'occasion."

                    )

                })

            remise = ZERO

        elif produit_line.etat == "N":

            if pourcentage != ZERO:

                raise ValidationError({

                    f"produit_line_{line_id}": (

                        "Un bijou neuf doit avoir 0 % d'occasion."

                    )

                })

        else:

            raise ValidationError({

                f"produit_line_{line_id}": "État du bijou invalide."

            })

        montant_brut = (

            prix_vente * poids * quantite

        ).quantize(

            TWOPLACES,

            rounding=ROUND_HALF_UP,

        )

        if remise > montant_brut:

            raise ValidationError({

                f"produit_line_{line_id}": (

                    "La remise dépasse le montant brut."

                )

            })

        lignes_preparees.append({

            "produit_line": produit_line,

            "quantite": quantite,

            "prix_vente_grammes": prix_vente,

            "remise": remise,

        })

    # 6. Validation des prestations

    prestations_preparees = []

    types_autorises = {

        choice[0] for choice in VenteAutre.TYPE_CHOICES

    }

    for index, item in enumerate(autres_in):

        if not isinstance(item, dict):

            raise ValidationError({

                f"autres[{index}]": "Un objet JSON est attendu."

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

    # 7. Stock vendeur : contrôle uniquement

    for data in sorted(

        lignes_preparees,

        key=lambda x: x["produit_line"].pk,

    ):

        produit_line = data["produit_line"]

        quantite = data["quantite"]

        stocks = list(

            VendorStock.objects

            .select_for_update()

            .filter(

                vendor=vendor,

                bijouterie=bijouterie,

                produit_line=produit_line,

            )

            .order_by("pk")

        )

        disponible = sum(

            (

                stock.quantite_allouee - stock.quantite_vendue

                for stock in stocks

            ),

            0,

        )

        if disponible < quantite:

            raise ValidationError({

                f"produit_line_{produit_line.pk}": (

                    f"Stock insuffisant. Demandé : {quantite}. "

                    f"Disponible : {disponible}."

                )

            })

    # 8. Client facultatif

    client = None

    client_id = client_in.get("id")

    if client_id not in (None, ""):

        client_id = sale_positive_int(

            client_id,

            field="client.id",

        )

        client = Client.objects.filter(pk=client_id).first()

        if client is None:

            raise ValidationError({

                "client": "Client introuvable."

            })

    # 9. Création de la vente

    vente = Vente.objects.create(

        client=client,

        created_by=user,

        bijouterie=bijouterie,

        vendor=vendor,

    )

    # 10. Création des bijoux

    # Les snapshots et montants sont calculés par VenteProduit.save().

    for data in lignes_preparees:

        VenteProduit.objects.create(

            vente=vente,

            produit_line=data["produit_line"],

            vendor=vendor,

            quantite=data["quantite"],

            prix_vente_grammes=data["prix_vente_grammes"],

            remise=data["remise"],

        )

    # 11. Création des prestations

    for data in prestations_preparees:

        VenteAutre.objects.create(

            vente=vente,

            type_autre=data["type_autre"],

            quantite=data["quantite"],

            prix_unitaire=data["prix_unitaire"],

        )

    # 12. Total de la vente

    vente.mettre_a_jour_montant_total()

    vente.refresh_from_db()

    # 13. Prestations seules : aucune facture

    if not lignes_preparees:

        return vente, None, 0

    # 14. TVA de la bijouterie

    # =========================================================
    # 14. TVA DE LA BIJOUTERIE
    # =========================================================

    appliquer_tva = bool(bijouterie.appliquer_tva)

    if appliquer_tva:
        if bijouterie.taux_tva is None:
            raise ValidationError({
                "taux_tva": (
                    "La TVA est activée pour cette bijouterie, "
                    "mais aucun taux n'est configuré."
                )
            })

        taux_tva = sale_decimal(
            bijouterie.taux_tva,
            field="taux_tva",
        )

        if not ZERO <= taux_tva <= Decimal("100.00"):
            raise ValidationError({
                "taux_tva": (
                    "Le taux de TVA doit être compris "
                    "entre 0 et 100."
                )
            })
    else:
        taux_tva = ZERO


    # 15. Facture proforma

    facture = Facture.objects.create(

        vente=vente,

        bijouterie=bijouterie,

        montant_ht=vente.montant_total or ZERO,

        appliquer_tva=appliquer_tva,

        taux_tva=taux_tva,

        status=Facture.STAT_NON_PAYE,

        type_facture=Facture.TYPE_PROFORMA,

    )

    return vente, facture, 0

# ============================================================

# VALIDATION FACTURE PAYABLE

# ============================================================

def validate_facture_payable(facture):

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

        "Type de facture non pris en charge pour le paiement."

    )
