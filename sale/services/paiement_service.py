# sale/services/payment_service.py

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.db.models import F, Sum

from backend.roles import ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER, get_role_name
from backend.utils.helpers import user_can_access_bijouterie
from compte_depot.models import CompteDepot
from compte_depot.services.depot_retrait_services import effectuer_retrait
from sale.models import (Facture, ModePaiement, Paiement, PaiementLigne, Vente,
                         VenteAutre, VenteProduit)
from sale.services.facture_hash_service import generate_facture_hash
from sale.services.facture_pdf_service import generate_facture_pdf
from sale.services.facture_qr_service import generate_facture_qr
from sale.services.montant_service import ZERO, money
from sale.services.sale_service import (upsert_client_for_payment,
                                        validate_facture_payable)
from staff.models import Cashier

logger = logging.getLogger(__name__)

ROLES_ENCAISSEMENT = frozenset({
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_CASHIER,
})


# ============================================================
# 1. HELPERS MONÉTAIRES
# ============================================================

def _money(value, field="montant") -> Decimal:
    """
    Convertit et arrondit un montant.

    Refuse les valeurs absentes, vides,
    non numériques ou non finies.
    """

    if value is None or value == "":
        raise ValidationError({
            field: "Montant obligatoire."
        })

    return money(value, field=field)


def _calculer_solde(
    *,
    montant_total,
    montant_deja_paye=ZERO,
    nouveau_paiement=ZERO,
):
    total = _money(
        montant_total,
        "montant_total",
    )
    deja_paye = _money(
        montant_deja_paye,
        "montant_deja_paye",
    )
    nouveau = _money(
        nouveau_paiement,
        "nouveau_paiement",
    )

    if (
        total < ZERO
        or deja_paye < ZERO
        or nouveau < ZERO
    ):
        raise ValidationError({
            "paiement": "Montants négatifs interdits."
        })

    total_paye = _money(
        deja_paye + nouveau,
        "total_paye",
    )

    if total_paye > total:
        raise ValidationError({
            "paiement": (
                "Le paiement dépasse le montant dû."
            )
        })

    return {
        "montant_total": total,
        "total_paye": total_paye,
        "reste_a_payer": _money(
            total - total_paye,
            "reste_a_payer",
        ),
    }


# ============================================================
# 2. AUTORISATIONS
# ============================================================

def _validate_user_and_cashier(
    user,
    bijouterie,
):
    """
    Vérifie les droits d'encaissement.

    Admin :
        toutes les bijouteries autorisées.

    Manager :
        ses bijouteries, profil vérifié.

    Cashier :
        sa bijouterie, profil vérifié.

    Retourne le profil caissier ou None.
    """

    if (
        user is None
        or not getattr(
            user,
            "is_authenticated",
            False,
        )
        or not getattr(
            user,
            "is_active",
            False,
        )
    ):
        raise ValidationError({
            "user": (
                "Utilisateur non authentifié ou inactif."
            )
        })

    role = get_role_name(user)

    if role not in ROLES_ENCAISSEMENT:
        raise ValidationError({
            "permission": (
                "Vous n'êtes pas autorisé à encaisser."
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

    if role == ROLE_ADMIN:
        return None

    if role == ROLE_MANAGER:
        manager = getattr(
            user,
            "staff_manager_profile",
            None,
        )

        if (
            manager is None
            or not manager.verifie
        ):
            raise ValidationError({
                "manager": (
                    "Profil manager introuvable "
                    "ou désactivé."
                )
            })

        if not manager.bijouteries.filter(
            pk=bijouterie.pk
        ).exists():
            raise ValidationError({
                "manager": (
                    "Bijouterie non autorisée."
                )
            })

        return None

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
            "cashier": (
                "Profil caissier non vérifié "
                "ou désactivé."
            )
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
# 3. IDENTIFICATION DE LA VENTE
# ============================================================

def _resolve_sale(
    *,
    numero_facture=None,
    numero_vente=None,
):
    """
    Bijoux ou mixte :
        numero_facture obligatoire.

    Prestations uniquement :
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

    if numero_facture:
        try:
            facture_initiale = (
                Facture.objects
                .get(
                    numero_facture__iexact=numero_facture
                )
            )
        except Facture.DoesNotExist as exc:
            raise ValidationError({
                "numero_facture": "Facture introuvable."
            }) from exc

        except Facture.MultipleObjectsReturned as exc:
            raise ValidationError({
                "numero_facture": (
                    "Numéro de facture non unique."
                )
            }) from exc

        if not facture_initiale.vente_id:
            raise ValidationError({
                "facture": (
                    "Cette facture ne possède pas de vente."
                )
            })

        # Ordre de verrouillage : Vente puis Facture.
        vente = (
            Vente.objects
            .select_for_update()
            .select_related("bijouterie")
            .get(pk=facture_initiale.vente_id)
        )

        facture = (
            Facture.objects
            .select_for_update()
            .get(pk=facture_initiale.pk)
        )

        if facture.vente_id != vente.pk:
            raise ValidationError({
                "facture": "Association facture/vente invalide."
            })

        if facture.bijouterie_id != vente.bijouterie_id:
            raise ValidationError({
                "facture": (
                    "Bijouteries de la vente "
                    "et de la facture différentes."
                )
            })

        if not VenteProduit.objects.filter(
            vente_id=vente.pk
        ).exists():
            raise ValidationError({
                "facture": (
                    "Une facture doit correspondre "
                    "à une vente de bijoux ou mixte."
                )
            })

        return vente, facture

    try:
        vente = (
            Vente.objects
            .select_for_update()
            .select_related("bijouterie")
            .get(
                numero_vente__iexact=numero_vente
            )
        )
    except Vente.DoesNotExist as exc:
        raise ValidationError({
            "numero_vente": "Vente introuvable."
        }) from exc

    except Vente.MultipleObjectsReturned as exc:
        raise ValidationError({
            "numero_vente": "Numéro de vente non unique."
        }) from exc

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
                "Cette vente ne contient aucune prestation."
            )
        })

    if Facture.objects.filter(
        vente_id=vente.pk
    ).exists():
        raise ValidationError({
            "numero_vente": (
                "Cette vente possède une facture."
            )
        })

    return vente, None


# ============================================================
# 4. RESTE À PAYER
# ============================================================

def _reste_a_payer(
    vente,
    facture,
):
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

    return _calculer_solde(
        montant_total=total_vente,
        montant_deja_paye=total_paye,
    )["reste_a_payer"]


# ============================================================
# 5. VALIDATION DES MODES DE PAIEMENT
# ============================================================

def _prepare_lines(
    lignes_data,
    *,
    prestation_uniquement=False,
):
    """
    Prestations :
        exactement un mode par opération.

    Factures :
        plusieurs modes possibles.

    Un mode ne peut pas être répété
    dans une même opération.
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

    if (
        prestation_uniquement
        and len(lignes_data) != 1
    ):
        raise ValidationError({
            "lignes": (
                "Une prestation accepte exactement "
                "un mode de paiement par opération."
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
            item.get("mode_paiement")
            or item.get("mode")
            or ""
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
        except ModePaiement.DoesNotExist as exc:
            raise ValidationError({
                "lignes": (
                    f"Ligne {index} : "
                    f"mode '{code}' introuvable ou inactif."
                )
            }) from exc

        if mode.pk in modes_utilises:
            raise ValidationError({
                "lignes": (
                    "Un mode ne peut pas être répété "
                    "dans le même paiement."
                )
            })

        modes_utilises.add(mode.pk)

        montant = _money(
            item.get(
                "montant_paye",
                item.get("montant"),
            ),
            f"lignes[{index}].montant_paye",
        )

        if montant <= ZERO:
            raise ValidationError({
                "lignes": (
                    f"Ligne {index} : "
                    "montant strictement positif obligatoire."
                )
            })

        reference = str(
            item.get("reference") or ""
        ).strip()

        provider_reference = str(
            item.get("provider_reference") or ""
        ).strip()

        numero_compte = str(
            item.get("numero_compte_depot")
            or item.get("numero_compte")
            or ""
        ).strip()

        if (
            mode.necessite_reference
            and not reference
            and not provider_reference
        ):
            raise ValidationError({
                "lignes": (
                    f"Ligne {index} : référence obligatoire."
                )
            })

        if mode.est_mode_depot:
            if not numero_compte:
                raise ValidationError({
                    "lignes": (
                        f"Ligne {index} : "
                        "numero_compte_depot obligatoire."
                    )
                })
        elif numero_compte:
            raise ValidationError({
                "lignes": (
                    "Le numéro de compte dépôt est réservé "
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

    return prepared, _money(
        total,
        "total_paiement",
    )


# ============================================================
# 6. VÉRIFICATION DES COMPTES DÉPÔTS
# ============================================================

def _prepare_deposit_accounts(
    *,
    prepared,
    vente,
):
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
                "pour utiliser un compte dépôt."
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
        except CompteDepot.DoesNotExist as exc:
            raise ValidationError({
                "numero_compte": (
                    f"Compte dépôt '{numero}' introuvable."
                )
            }) from exc

        if compte.client_id != vente.client_id:
            raise ValidationError({
                "numero_compte": (
                    "Le compte dépôt n'appartient pas "
                    "au client de la vente."
                )
            })

        # Dans le modèle actuel, le rattachement
        # du compte passe par ClientDepot.bijouterie.
        if (
            compte.client.bijouterie_id
            != vente.bijouterie_id
        ):
            raise ValidationError({
                "numero_compte": (
                    "Le compte dépôt appartient "
                    "à une autre bijouterie."
                )
            })

        comptes[numero] = compte

    montants_par_compte = defaultdict(
        lambda: ZERO
    )

    for item in prepared:
        if item["mode"].est_mode_depot:
            montants_par_compte[
                item["numero_compte"]
            ] += item["montant"]

    for numero, montant in montants_par_compte.items():
        disponible = _money(
            comptes[numero].solde,
            "solde",
        )

        if disponible < montant:
            raise ValidationError({
                "compte_depot": (
                    f"Solde insuffisant pour {numero}. "
                    f"Disponible : {disponible} FCFA. "
                    f"Demandé : {montant} FCFA."
                )
            })

    return comptes


# ============================================================
# 7. CRÉATION DES LIGNES DE PAIEMENT
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
# 8. DOCUMENTS DE FACTURE
# ============================================================

def _generate_final_invoice(
    facture_id,
):
    """
    Génère les documents après commit.

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
            "Échec génération facture %s",
            facture_id,
        )


# ============================================================
# 9. IDEMPOTENCE
# ============================================================

def _normaliser_cle_idempotence(value):
    if value is None or not str(value).strip():
        raise ValidationError({
            "idempotency_key": (
                "Clé UUID obligatoire."
            )
        })

    try:
        return uuid.UUID(str(value))
    except (
        TypeError,
        ValueError,
        AttributeError,
    ) as exc:
        raise ValidationError({
            "idempotency_key": "UUID invalide."
        }) from exc


def _empreinte_paiement(
    *,
    vente,
    facture,
    prepared,
    client_data,
):
    lignes = sorted(
        (
            {
                "mode": item["mode"].code,
                "montant": str(item["montant"]),
                "reference": item["reference"],
                "provider_reference": (
                    item["provider_reference"]
                ),
                "numero_compte": item["numero_compte"],
            }
            for item in prepared
        ),
        key=lambda x: (
            x["mode"],
            x["numero_compte"],
            x["montant"],
            x["reference"],
            x["provider_reference"],
        ),
    )

    contenu = {
        "vente_id": vente.pk,
        "facture_id": (
            facture.pk if facture else None
        ),
        "lignes": lignes,
        "client_data": client_data,
    }

    payload = json.dumps(
        contenu,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        cls=DjangoJSONEncoder,
    )

    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()


# ============================================================
# 10. SERVICE PRINCIPAL
# ============================================================

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
    Encaisse une vente Rio-Gold.

    Bijoux / mixte :
        facture obligatoire ;
        paiement multimode autorisé.

    Prestations :
        paiement direct ;
        exactement un mode par opération ;
        aucune facture créée.

    Stock bijoux :
        déjà consommé à la création de vente.

    Idempotence :
        une même clé et une même demande
        ne produisent qu'un seul paiement.
    """

    # --------------------------------------------------------
    # 1. CLÉ D'IDEMPOTENCE
    # --------------------------------------------------------

    cle = _normaliser_cle_idempotence(
        idempotency_key
    )

    if connection.vendor != "postgresql":
        raise ValidationError({
            "database": (
                "Le service d'encaissement exige "
                "PostgreSQL pour ses verrous."
            )
        })

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT pg_advisory_xact_lock(
                hashtextextended(%s, 0)
            )
            """,
            [str(cle)],
        )

    # --------------------------------------------------------
    # 2. VENTE / FACTURE
    # --------------------------------------------------------

    vente, facture = _resolve_sale(
        numero_facture=numero_facture,
        numero_vente=numero_vente,
    )

    if vente.is_cancelled:
        raise ValidationError({
            "vente": (
                "Vente annulée : encaissement interdit."
            )
        })

    # --------------------------------------------------------
    # 3. PERMISSIONS
    # --------------------------------------------------------

    cashier = _validate_user_and_cashier(
        user,
        vente.bijouterie,
    )

    # --------------------------------------------------------
    # 4. VALIDATION DES LIGNES
    # --------------------------------------------------------

    prepared, total_paiement = _prepare_lines(
        lignes_data,
        prestation_uniquement=(facture is None),
    )

    # --------------------------------------------------------
    # 5. EMPREINTE ET REJEU
    # --------------------------------------------------------

    empreinte = _empreinte_paiement(
        vente=vente,
        facture=facture,
        prepared=prepared,
        client_data=client_data,
    )

    existant = (
        Paiement.objects
        .filter(idempotency_key=cle)
        .first()
    )

    if existant is not None:
        if (
            existant.created_by_id != user.pk
            or existant.vente_id != vente.pk
            or existant.facture_id != (
                facture.pk if facture else None
            )
            or existant.request_fingerprint != empreinte
        ):
            raise ValidationError({
                "idempotency_key": (
                    "Clé déjà utilisée pour "
                    "une autre demande."
                )
            })

        if existant.response_snapshot is None:
            raise ValidationError({
                "idempotency_key": (
                    "Paiement existant sans "
                    "résultat enregistré."
                )
            })

        return dict(existant.response_snapshot)

    # --------------------------------------------------------
    # 6. VALIDATION DE LA FACTURE
    # --------------------------------------------------------

    if facture is not None:
        validate_facture_payable(facture)

        # Le stock doit déjà être consommé
        # lors de la création de vente.
        if not facture.stock_consumed:
            raise ValidationError({
                "stock": (
                    "La consommation du stock "
                    "de cette vente n'est pas confirmée."
                )
            })

    # --------------------------------------------------------
    # 7. CLIENT
    # --------------------------------------------------------

    if client_data is not None:
        upsert_client_for_payment(
            vente=vente,
            facture=facture,
            client_data=client_data,
        )

        vente.refresh_from_db()

    # --------------------------------------------------------
    # 8. SOLDE AVANT PAIEMENT
    # --------------------------------------------------------

    reste_avant = _reste_a_payer(
        vente,
        facture,
    )

    if reste_avant <= ZERO:
        raise ValidationError({
            "paiement": (
                "Cette vente est déjà entièrement payée."
            )
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

    solde = _calculer_solde(
        montant_total=reste_avant,
        nouveau_paiement=total_paiement,
    )

    reste_apres = solde["reste_a_payer"]

    # --------------------------------------------------------
    # 9. COMPTES DÉPÔTS
    # --------------------------------------------------------

    comptes = _prepare_deposit_accounts(
        prepared=prepared,
        vente=vente,
    )

    # --------------------------------------------------------
    # 10. CRÉATION DU PAIEMENT
    # --------------------------------------------------------

    paiement = Paiement.objects.create(
        vente=vente,
        facture=facture,
        created_by=user,
        cashier=cashier,
        idempotency_key=cle,
        request_fingerprint=empreinte,
    )

    # --------------------------------------------------------
    # 11. LIGNES ET DÉBITS
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 12. RECONTRÔLE DU SOLDE
    # --------------------------------------------------------

    facture_payee = False

    if facture is None:
        reste_recalcule = _reste_a_payer(
            vente,
            None,
        )

        if reste_recalcule != reste_apres:
            raise ValidationError({
                "paiement": (
                    "Incohérence du solde "
                    "après encaissement."
                )
            })

    else:
        Facture.recompute_facture_status(
            facture
        )

        facture.refresh_from_db()

        reste_recalcule = _reste_a_payer(
            vente,
            facture,
        )

        if reste_recalcule != reste_apres:
            raise ValidationError({
                "paiement": (
                    "Incohérence du solde de facture."
                )
            })

        if facture.status == Facture.STAT_PAYE:
            if reste_apres != ZERO:
                raise ValidationError({
                    "facture": (
                        "Facture marquée payée "
                        "avec un solde non nul."
                    )
                })

            facture_payee = True

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

            facture_pk = facture.pk

            transaction.on_commit(
                lambda pk=facture_pk: (
                    _generate_final_invoice(pk)
                ),
                robust=True,
            )

        elif reste_apres == ZERO:
            raise ValidationError({
                "facture": (
                    "Solde nul mais facture "
                    "non marquée payée."
                )
            })

    # --------------------------------------------------------
    # 13. TYPE DE VENTE
    # --------------------------------------------------------

    if facture is None:
        type_vente = "prestation"

    elif VenteAutre.objects.filter(
        vente_id=vente.pk
    ).exists():
        type_vente = "mixte"

    else:
        type_vente = "bijoux"

    # --------------------------------------------------------
    # 14. RÉSULTAT
    # --------------------------------------------------------

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
        "paiement_complet": (
            reste_apres == ZERO
        ),
        "facture_payee": facture_payee,
        "stock_result": None,
        "depot_transaction_ids": (
            depot_transactions
        ),
        "lignes": [
            {
                "id": ligne.pk,
                "mode": ligne.mode_paiement.code,
                "montant": str(
                    ligne.montant_paye
                ),
            }
            for ligne in lignes
        ],
        "recu_paiement_id": None,
        "facture_pdf_url": None,
    }

    # --------------------------------------------------------
    # 15. SNAPSHOT IDEMPOTENT
    # --------------------------------------------------------

    paiement.response_snapshot = json.loads(
        json.dumps(
            resultat,
            cls=DjangoJSONEncoder,
            ensure_ascii=False,
        )
    )

    paiement.save(
        update_fields=["response_snapshot"]
    )

    return paiement.response_snapshot

