from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections import defaultdict

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.db.models import Sum

from backend.roles import ROLE_CASHIER, ROLE_MANAGER, get_role_name
from backend.utils.helpers import user_can_access_bijouterie
from compte_depot.models import CompteDepot
from compte_depot.services import effectuer_retrait
from sale.models import (Facture, ModePaiement, Paiement, PaiementLigne, Vente,
                         VenteAutre, VenteProduit)
from sale.services.confirm_service import confirm_sale_out_from_vendor
from sale.services.facture_hash_service import generate_facture_hash
from sale.services.facture_pdf_service import generate_facture_pdf
from sale.services.facture_qr_service import generate_facture_qr
from sale.services.montant_service import (ZERO, calculer_solde_paiement,
                                           money_strict)
from sale.services.sale_service import (upsert_client_for_payment,
                                        validate_facture_payable)
from staff.models import Cashier

logger = logging.getLogger(__name__)
_money = money_strict
# ============================================================
# 2. HELPERS : AUTORISATIONS
# ============================================================
def _validate_user_and_cashier(user, bijouterie):
    """
    Vérifie :
    - authentification ;
    - rôle manager ou caissier ;
    - accès à la bijouterie ;
    - profil caissier actif et vérifié.
    Retourne le profil Cashier ou None pour le manager.
    """
    if not user or not user.is_authenticated:
        raise ValidationError({
            "user": "Authentification obligatoire."
        })
    role = get_role_name(user)
    if role not in (ROLE_MANAGER, ROLE_CASHIER):
        raise ValidationError({
            "permission": (
                "Seuls le manager et le caissier "
                "peuvent encaisser une vente."
            )
        })
    if not user_can_access_bijouterie(
        user,
        bijouterie,
    ):
        raise ValidationError({
            "permission": (
                "Vous n'avez pas accès à cette bijouterie."
            )
        })
    cashier = None
    if role == ROLE_CASHIER:
        cashier = (
            Cashier.objects
            .select_for_update()
            .filter(user=user)
            .first()
        )
        if cashier is None:
            raise ValidationError({
                "cashier": "Profil caissier introuvable."
            })
        if not cashier.verifie:
            raise ValidationError({
                "cashier": "Profil caissier non vérifié."
            })
        if not cashier.is_active_staff:
            raise ValidationError({
                "cashier": "Profil caissier désactivé."
            })
        if cashier.bijouterie_id != bijouterie.pk:
            raise ValidationError({
                "cashier": (
                    "Le caissier n'appartient pas "
                    "à cette bijouterie."
                )
            })
    return cashier
# ============================================================
# 3. HELPERS : IDENTIFICATION DE LA VENTE
# ============================================================
def _resolve_sale(
    *,
    numero_facture=None,
    numero_vente=None,
):
    """
    Identifie et verrouille la vente.
    Bijoux / mixte :
        numero_facture obligatoire.
    Prestations seules :
        numero_vente obligatoire.
    Retourne :
        (vente, facture)
    """
    numero_facture = str(
        numero_facture or ""
    ).strip()
    numero_vente = str(
        numero_vente or ""
    ).strip()
    if bool(numero_facture) == bool(numero_vente):
        raise ValidationError({
            "paiement": (
                "Fournir exclusivement numero_facture "
                "ou numero_vente."
            )
        })
    facture = None
    # --------------------------------------------------------
    # CAS 1 : BIJOUX OU VENTE MIXTE
    # --------------------------------------------------------
    if numero_facture:
        try:
            facture = (
                Facture.objects
                .select_related(
                    "vente",
                    "bijouterie",
                )
                .get(
                    numero_facture__iexact=numero_facture
                )
            )
        except Facture.DoesNotExist:
            raise ValidationError({
                "numero_facture": "Facture introuvable."
            })
        except Facture.MultipleObjectsReturned:
            raise ValidationError({
                "numero_facture": (
                    "Plusieurs factures portent ce numéro."
                )
            })
        if not facture.vente_id:
            raise ValidationError({
                "facture": (
                    "Cette facture n'est associée "
                    "à aucune vente."
                )
            })
        vente = (
            Vente.objects
            .select_for_update()
            .select_related("bijouterie")
            .get(pk=facture.vente_id)
        )
        # Verrouillage cohérent : Vente d'abord, Facture ensuite.
        facture = (
            Facture.objects
            .select_for_update()
            .get(pk=facture.pk)
        )
        if facture.vente_id != vente.pk:
            raise ValidationError({"facture": "La facture a changé de vente."})

        if not VenteProduit.objects.filter(
            vente_id=vente.pk
        ).exists():
            raise ValidationError({
                "facture": (
                    "Le paiement par facture est réservé "
                    "aux ventes de bijoux ou mixtes."
                )
            })
        if facture.bijouterie_id != vente.bijouterie_id:
            raise ValidationError({
                "facture": (
                    "Incohérence entre la bijouterie "
                    "de la facture et celle de la vente."
                )
            })
    # --------------------------------------------------------
    # CAS 2 : PRESTATIONS UNIQUEMENT
    # --------------------------------------------------------
    else:
        try:
            vente = (
                Vente.objects
                .select_for_update()
                .select_related("bijouterie")
                .get(
                    numero_vente__iexact=numero_vente
                )
            )
        except Vente.DoesNotExist:
            raise ValidationError({
                "numero_vente": "Vente introuvable."
            })
        except Vente.MultipleObjectsReturned:
            raise ValidationError({
                "numero_vente": (
                    "Plusieurs ventes portent ce numéro."
                )
            })
        if VenteProduit.objects.filter(
            vente_id=vente.pk
        ).exists():
            raise ValidationError({
                "numero_vente": (
                    "Cette vente contient des bijoux. "
                    "Utilisez numero_facture."
                )
            })
        if not VenteAutre.objects.filter(
            vente_id=vente.pk
        ).exists():
            raise ValidationError({
                "numero_vente": (
                    "Cette vente ne contient "
                    "aucune prestation."
                )
            })
        if Facture.objects.filter(
            vente_id=vente.pk
        ).exists():
            raise ValidationError({
                "numero_vente": (
                    "Cette vente possède une facture. "
                    "Utilisez numero_facture."
                )
            })
    return vente, facture
# ============================================================
# 4. HELPERS : RESTE À PAYER
# ============================================================
def _reste_a_payer(vente, facture):
    """
    Calcule le reste à payer.
    Bijoux / mixte :
        utilise facture.reste_a_payer.
    Prestations :
        montant vente - paiements directs.
    """
    if facture is not None:
        return _money(
            facture.reste_a_payer,
            "reste_a_payer",
        )
    total_vente = _money(
        vente.montant_total,
        "montant_total",
    )
    total_paye = (
        PaiementLigne.objects
        .filter(
            paiement__vente_id=vente.pk,
            paiement__facture__isnull=True,
        )
        .aggregate(
            total=Sum("montant_paye")
        )["total"]
    ) or ZERO
    total_paye = _money(
        total_paye,
        "total_paye",
    )
    solde = calculer_solde_paiement(
        montant_total=total_vente,
        montant_deja_paye=total_paye,
    )
    return solde["reste_a_payer"]
# ============================================================
# 5. HELPERS : VALIDATION DES MODES
# ============================================================
def _prepare_lines(lignes_data):
    """
    Valide toutes les lignes avant création du paiement.
    Règles :
    - liste non vide ;
    - mode actif ;
    - mode unique par paiement ;
    - montant positif ;
    - référence si nécessaire ;
    - numéro de compte pour dépôt.
    """
    if (
        not isinstance(lignes_data, list)
        or not lignes_data
    ):
        raise ValidationError({
            "lignes": (
                "Au moins une ligne de paiement "
                "est obligatoire."
            )
        })
    prepared = []
    modes_utilises = set()
    total = ZERO
    for index, item in enumerate(
        lignes_data,
        start=1,
    ):
        if not isinstance(item, dict):
            raise ValidationError({
                "lignes": (
                    f"Ligne {index} invalide."
                )
            })
        code = str(
            item.get("mode") or ""
        ).strip().lower()
        if not code:
            raise ValidationError({
                "lignes": (
                    f"Ligne {index} : mode obligatoire."
                )
            })
        try:
            mode = ModePaiement.objects.get(
                code=code,
                active=True,
            )
        except ModePaiement.DoesNotExist:
            raise ValidationError({
                "lignes": (
                    f"Ligne {index} : "
                    f"mode '{code}' introuvable ou inactif."
                )
            })
        if mode.pk in modes_utilises:
            raise ValidationError({
                "lignes": (
                    "Un mode de paiement ne peut pas "
                    "être répété dans le même paiement."
                )
            })
        modes_utilises.add(mode.pk)
        montant = _money(
            item.get("montant"),
            f"lignes[{index}].montant",
        )
        if montant <= ZERO:
            raise ValidationError({
                "lignes": (
                    f"Ligne {index} : "
                    "le montant doit être positif."
                )
            })
        reference = str(
            item.get("reference") or ""
        ).strip()
        provider_reference = str(
            item.get("provider_reference") or ""
        ).strip()
        numero_compte = str(
            item.get("numero_compte") or ""
        ).strip()
        if (
            mode.necessite_reference
            and not reference
            and not provider_reference
        ):
            raise ValidationError({
                "lignes": (
                    f"Ligne {index} : "
                    "référence obligatoire."
                )
            })
        if mode.est_mode_depot and not numero_compte:
            raise ValidationError({
                "lignes": (
                    f"Ligne {index} : "
                    "numero_compte obligatoire "
                    "pour un paiement par dépôt."
                )
            })
        if not mode.est_mode_depot and numero_compte:
            raise ValidationError({
                "lignes": (
                    f"Ligne {index} : "
                    "numero_compte est réservé "
                    "au paiement par dépôt."
                )
            })
        prepared.append({
            "mode": mode,
            "montant": montant,
            "reference": reference,
            "provider_reference": provider_reference,
            "numero_compte": numero_compte,
        })
        total += montant
    return prepared, total
# ============================================================
# 6. HELPERS : COMPTES DÉPÔTS
# ============================================================
def _prepare_deposit_accounts(
    *,
    prepared,
    vente,
):
    """
    Verrouille les comptes dépôts.
    Vérifie :
    - existence ;
    - appartenance au client ;
    - appartenance à la bijouterie si le champ existe ;
    - solde suffisant.
    Les comptes sont verrouillés dans un ordre stable.
    """
    numeros = sorted({
        item["numero_compte"]
        for item in prepared
        if item["mode"].est_mode_depot
    })
    if not numeros:
        return {}
    if not vente.client_id:
        raise ValidationError({
            "client": (
                "Un client est obligatoire "
                "pour payer par compte dépôt."
            )
        })
    comptes = {}
    for numero in numeros:
        try:
            compte = (
                CompteDepot.objects
                .select_for_update()
                .select_related("client")
                .get(numero_compte=numero)
            )
        except CompteDepot.DoesNotExist:
            raise ValidationError({
                "numero_compte": (
                    f"Compte dépôt '{numero}' introuvable."
                )
            })
        if compte.client_id != vente.client_id:
            raise ValidationError({
                "numero_compte": (
                    "Ce compte dépôt n'appartient pas "
                    "au client de la vente."
                )
            })
        if (
            compte.client is None
            or compte.client.bijouterie_id != vente.bijouterie_id
        ):
            raise ValidationError({
                "numero_compte": (
                    "Le compte dépôt appartient "
                    "à une autre bijouterie."
                )
            })
        comptes[numero] = compte
    _verifier_soldes_comptes(prepared, comptes)

    return comptes
def _verifier_soldes_comptes(
    prepared,
    comptes,
):
    """
    Vérifie le solde total demandé pour chaque compte.
    Les comptes doivent déjà être verrouillés avec
    select_for_update() dans la transaction courante.
    """
    montants_par_compte = defaultdict(
        lambda: ZERO
    )
    for item in prepared:
        # Adapter cette condition à la structure réelle
        # de _prepare_lines() si nécessaire.
        if not item["mode"].est_mode_depot:
            continue
        numero = item["numero_compte"]
        montants_par_compte[numero] += item["montant"]
    for numero, montant_total in montants_par_compte.items():
        compte = comptes[numero]
        solde_disponible = _money(
            compte.solde,
            "solde",
        )
        if solde_disponible < montant_total:
            raise ValidationError({
                "compte_depot": (
                    f"Solde insuffisant pour le compte "
                    f"{numero}. "
                    f"Disponible : {solde_disponible} FCFA. "
                    f"Demandé : {montant_total} FCFA."
                )
            })
# ============================================================
# 7. HELPERS : CRÉATION DES LIGNES
# ============================================================
def _create_payment_lines(
    *,
    paiement,
    prepared,
    comptes,
    vente,
    facture,
    user,
):
    """
    Crée les PaiementLigne.
    Pour le dépôt :
    - débite le compte avec effectuer_retrait() ;
    - associe la transaction au paiement.
    Toute erreur provoque le rollback.
    """
    lignes_creees = []
    depot_transactions = []
    for item in prepared:
        mode = item["mode"]
        if mode.est_mode_depot:
            compte = comptes[item["numero_compte"]]
            reference_operation = (
                f"FACTURE-{facture.numero_facture}"
                if facture is not None
                else f"VENTE-{vente.numero_vente}"
            )
            tx = effectuer_retrait(
                compte_id=compte.pk,
                montant=item["montant"],
                user=user,
                reference=reference_operation,
                commentaire=(
                    f"Paiement vente {vente.numero_vente}"
                ),
            )
            ligne = PaiementLigne.objects.create(
                paiement=paiement,
                mode_paiement=mode,
                montant_paye=item["montant"],
                reference=(
                    f"COMPTE_DEPOT-{compte.numero_compte}"
                ),
                compte_depot=compte,
                transaction_depot=tx,
            )
            depot_transactions.append(tx.pk)
        else:
            ligne = PaiementLigne.objects.create(
                paiement=paiement,
                mode_paiement=mode,
                montant_paye=item["montant"],
                reference=item["reference"],
                provider_reference=(
                    item["provider_reference"]
                ),
            )
        lignes_creees.append(ligne)
    return lignes_creees, depot_transactions
# ============================================================
# 8. HELPERS : DOCUMENTS DE FACTURE
# ============================================================
def _generate_final_invoice(facture_id):
    """
    Génère les documents de la facture après commit.
    Ordre :
    1. Hash ;
    2. QR code ;
    3. PDF.
    Les erreurs sont journalisées.
    """
    try:
        facture = (
            Facture.objects
            .select_related(
                "vente",
                "bijouterie",
            )
            .get(pk=facture_id)
        )
        if facture.status != Facture.STAT_PAYE:
            return
        if facture.type_facture != Facture.TYPE_FACTURE:
            return
        if not facture.integrity_hash:
            generate_facture_hash(facture)
        if not facture.qr_code_image:
            generate_facture_qr(facture)
        if not facture.facture_pdf:
            generate_facture_pdf(facture)
    except Exception:
        logger.exception(
            "Échec génération documents facture %s",
            facture_id,
        )
# ============================================================
# 9. SERVICE PRINCIPAL D'ENCAISSEMENT
# ============================================================
def _normaliser_cle_idempotence(value):
    if value is None or not str(value).strip():
        raise ValidationError({"idempotency_key": "Clé UUID obligatoire."})
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({"idempotency_key": "UUID invalide."}) from exc


def _empreinte_paiement(*, vente, facture, prepared, client_data):
    """Empreinte stable de la demande, indépendante de l'ordre des lignes."""
    lignes = sorted((
        {
            "mode": item["mode"].code,
            "montant": str(item["montant"]),
            "reference": item["reference"],
            "provider_reference": item["provider_reference"],
            "numero_compte": item["numero_compte"],
        }
        for item in prepared
    ), key=lambda x: (x["mode"], x["numero_compte"], x["montant"]))
    contenu = {
        "vente_id": vente.pk,
        "facture_id": facture.pk if facture else None,
        "lignes": lignes,
        "client_data": client_data,
    }
    payload = json.dumps(contenu, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, cls=DjangoJSONEncoder)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@transaction.atomic
def effectuer_paiement_vente(
    *,
    user,
    lignes_data,
    numero_facture=None,
    numero_vente=None,
    client_data=None,
    idempotency_key=None,
):
    """
    Encaisse une vente.
    BIJOUX :
        numero_facture obligatoire.
    PRESTATIONS :
        numero_vente obligatoire.
    MIXTE :
        numero_facture obligatoire.
    Supporte :
    - paiements partiels ;
    - paiements multimodes ;
    - comptes dépôts ;
    - consommation exacte du stock bijoux ;
    - génération différée de la facture finale.
    Retourne un dictionnaire exploitable par l'API.
    """
    # ========================================================
    # 1. IDENTIFIER LA VENTE ET LA FACTURE
    # ========================================================
    # Sérialise les demandes partageant une clé, même sur deux ventes.
    # PostgreSQL : verrou transactionnel, libéré automatiquement au commit.
    cle = _normaliser_cle_idempotence(idempotency_key)
    if connection.vendor != "postgresql":
        raise ValidationError({
            "database": "Encaissement idempotent : PostgreSQL requis."
        })
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                [str(cle)],
            )
    vente, facture = _resolve_sale(
        numero_facture=numero_facture,
        numero_vente=numero_vente,
    )
    if vente.is_cancelled:
        raise ValidationError({"vente": "Vente annulée : encaissement interdit."})
    # ========================================================
    # 2. VÉRIFIER LES DROITS
    # ========================================================
    cashier = _validate_user_and_cashier(
        user,
        vente.bijouterie,
    )
    # Le verrou de Vente est déjà détenu par _resolve_sale.
    # On vérifie le rejeu AVANT toute modification du client ou du dépôt.
    prepared, total_paiement = _prepare_lines(lignes_data)
    empreinte = _empreinte_paiement(
        vente=vente, facture=facture, prepared=prepared,
        client_data=client_data,
    )
    existant = Paiement.objects.filter(idempotency_key=cle).first()
    if existant is not None:
        if (existant.created_by_id != user.pk
                or existant.vente_id != vente.pk
                or existant.facture_id != (facture.pk if facture else None)
                or existant.request_fingerprint != empreinte):
            raise ValidationError({
                "idempotency_key": "Clé déjà utilisée pour une autre demande."
            })
        if existant.response_snapshot is None:
            raise ValidationError({
                "idempotency_key": "Paiement existant sans résultat enregistré."
            })
        return dict(existant.response_snapshot)

    # Contrôler l'état payable uniquement pour une NOUVELLE demande.
    # Un rejeu valide reste possible après paiement intégral.
    if facture is not None:
        validate_facture_payable(facture)

    if client_data is not None:
        upsert_client_for_payment(
            vente=vente, facture=facture, client_data=client_data,
        )
        vente.refresh_from_db()

    reste_avant = _reste_a_payer(vente, facture)
    if reste_avant <= ZERO:
        raise ValidationError({
            "paiement": "Cette vente est déjà entièrement payée."
        })
    if total_paiement > reste_avant:
        raise ValidationError({
            "paiement": (
                "Le montant demandé dépasse "
                "le reste à payer."
            ),
            "reste_a_payer": str(reste_avant),
            "montant_demande": str(total_paiement),
        })
    solde = calculer_solde_paiement(
        montant_total=reste_avant,
        montant_deja_paye=ZERO,
        nouveau_paiement=total_paiement,
    )
    reste_apres = solde["reste_a_payer"]
    # ========================================================
    # 6. VÉRIFIER LES COMPTES DÉPÔTS
    # ========================================================
    comptes = _prepare_deposit_accounts(
        prepared=prepared,
        vente=vente,
    )
    # Les soldes cumulés sont vérifiés dans _prepare_deposit_accounts.
    # ========================================================
    # 7. CRÉER LE PAIEMENT
    # ========================================================
    paiement = Paiement.objects.create(
        vente=vente,
        facture=facture,
        created_by=user,
        cashier=cashier,
        idempotency_key=cle,
        request_fingerprint=empreinte,
    )
    # ========================================================
    # 8. CRÉER LES LIGNES ET DÉBITER LES DÉPÔTS
    # ========================================================
    lignes, depot_transactions = (
        _create_payment_lines(
            paiement=paiement,
            prepared=prepared,
            comptes=comptes,
            vente=vente,
            facture=facture,
            user=user,
        )
    )
    # ========================================================
    # 9. METTRE À JOUR FACTURE ET STOCK
    # ========================================================
    stock_result = None
    facture_payee = False
    # Le solde attendu a déjà été calculé par montant_service.
    # Pour les prestations, _reste_a_payer lit les lignes enregistrées.
    if facture is None:
        reste_recalcule = _reste_a_payer(vente, facture)
        if reste_recalcule != reste_apres:
            raise ValidationError({"paiement": "Incohérence du solde après encaissement."})
    if facture is not None:
        Facture.recompute_facture_status(facture)
        facture.refresh_from_db()
        reste_recalcule = _reste_a_payer(vente, facture)
        if reste_recalcule != reste_apres:
            raise ValidationError({"paiement": "Incohérence du solde de facture après encaissement."})
        if facture.status == Facture.STAT_PAYE:
            if reste_apres != ZERO:
                raise ValidationError({
                    "facture": (
                        "Incohérence entre le statut "
                        "et le solde restant."
                    )
                })
            facture_payee = True
            # -----------------------------------------------
            # STOCK BIJOUX
            # -----------------------------------------------
            if not facture.stock_consumed:
                stock_result = (
                    confirm_sale_out_from_vendor(
                        facture=facture,
                        by_user=user,
                    )
                )
            # -----------------------------------------------
            # PROFORMA -> FACTURE DÉFINITIVE
            # -----------------------------------------------
            if (
                facture.type_facture
                == Facture.TYPE_PROFORMA
            ):
                facture.type_facture = (
                    Facture.TYPE_FACTURE
                )
                facture.save(
                    update_fields=["type_facture"]
                )
            facture.refresh_from_db()
            # -----------------------------------------------
            # HASH / QR / PDF APRÈS COMMIT
            # -----------------------------------------------
            facture_pk = facture.pk
            transaction.on_commit(
                lambda pk=facture_pk: (
                    _generate_final_invoice(pk)
                ),
                robust=True,
            )
        elif reste_apres == ZERO:
            raise ValidationError({
                "facture": "Solde nul mais facture non marquée payée."
            })
    # ========================================================
    # 10. TYPE DE VENTE
    # ========================================================
    if facture is None:
        type_vente = "prestation"
    elif VenteAutre.objects.filter(
        vente_id=vente.pk
    ).exists():
        type_vente = "mixte"
    else:
        type_vente = "bijoux"
    # ========================================================
    # 11. RÉSULTAT
    # ========================================================
    resultat = {
        "success": True,
        "paiement_id": paiement.pk,
        "numero_vente": vente.numero_vente,
        "numero_facture": (
            facture.numero_facture
            if facture is not None
            else None
        ),
        "type_vente": type_vente,
        "montant_paiement": str(total_paiement),
        "reste_avant": str(reste_avant),
        "reste_apres": str(reste_apres),
        "paiement_complet": reste_apres == ZERO,
        "facture_payee": facture_payee,
        "stock_result": stock_result,
        "depot_transaction_ids": depot_transactions,
        "lignes": [
            {
                "id": ligne.pk,
                "mode": ligne.mode_paiement.code,
                "montant": str(ligne.montant_paye),
            }
            for ligne in lignes
        ],
        # À raccorder au futur service de reçu.
        "recu_paiement_id": None,
        # Le PDF est généré après commit.
        "facture_pdf_url": None,
    }

    # Snapshot atomique : un rejeu rend la même réponse sans ré-encaisser.
    paiement.response_snapshot = json.loads(json.dumps(
        resultat, cls=DjangoJSONEncoder, ensure_ascii=False
    ))
    paiement.save(update_fields=["response_snapshot"])
    return paiement.response_snapshot
