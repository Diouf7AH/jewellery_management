# sale/services/facture_hash_service.py

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.utils import timezone

from sale.models import Facture

# ============================================================
# 1. NORMALISATION DES MONTANTS
# ============================================================

def _montant_signature(value) -> str:
    """
    Normalise un montant pour la signature.

    Exemples :
        15000
        15000.0
        15000.00

    Résultat :
        "15000.00"

    La normalisation évite de produire
    des signatures différentes pour des
    représentations équivalentes.
    """

    try:
        montant = Decimal(str(value))

        if not montant.is_finite():
            raise InvalidOperation

        montant = montant.quantize(
            Decimal("0.01")
        )

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ) as exc:
        raise ValidationError({
            "montant_total": (
                "Montant de facture invalide."
            )
        }) from exc

    return format(montant, ".2f")


# ============================================================
# 2. CLÉ DE SIGNATURE
# ============================================================

def _get_signing_key() -> bytes:
    """
    Récupère la clé secrète HMAC.

    FACTURE_SIGNING_KEY doit être
    indépendante de SECRET_KEY Django.

    Ne jamais exposer cette clé dans :
        - Angular ;
        - les API ;
        - les QR codes ;
        - les PDF ;
        - les logs.
    """

    secret = getattr(
        settings,
        "FACTURE_SIGNING_KEY",
        None,
    )

    if not isinstance(secret, str) or not secret:
        raise ImproperlyConfigured(
            "FACTURE_SIGNING_KEY doit être "
            "configurée dans les paramètres Django."
        )

    if len(secret.encode("utf-8")) < 32:
        raise ImproperlyConfigured(
            "FACTURE_SIGNING_KEY doit contenir "
            "au moins 32 octets."
        )

    return secret.encode("utf-8")


# ============================================================
# 3. DONNÉES SIGNÉES
# ============================================================

def _facture_signature_payload(
    facture: Facture,
) -> dict:
    """
    Construit les données stables
    de la facture à signer.

    Important :
        Les informations signées doivent
        être figées après signature.

    Une modification des champs signés
    rendra la vérification invalide.
    """

    if facture is None or facture.pk is None:
        raise ValidationError({
            "facture": (
                "Une facture enregistrée est obligatoire."
            )
        })

    if facture.vente_id is None:
        raise ValidationError({
            "facture": (
                "La facture doit être associée "
                "à une vente."
            )
        })

    if facture.bijouterie_id is None:
        raise ValidationError({
            "bijouterie": (
                "La facture doit être associée "
                "à une bijouterie."
            )
        })

    if facture.date_creation is None:
        raise ValidationError({
            "date_creation": (
                "Date de création obligatoire."
            )
        })

    vente = facture.vente
    bijouterie = facture.bijouterie

    client = getattr(
        vente,
        "client",
        None,
    )

    client_nom = ""

    if client is not None:
        client_nom = str(
            getattr(
                client,
                "full_name",
                "",
            ) or ""
        ).strip()

    return {
        "numero_facture": str(
            facture.numero_facture
        ).strip(),

        "date_creation": (
            facture.date_creation.isoformat()
        ),

        "montant_total": _montant_signature(
            facture.montant_total
        ),

        "ninea": str(
            getattr(
                bijouterie,
                "ninea",
                "",
            ) or ""
        ).strip(),

        "client": client_nom,
    }


# ============================================================
# 4. CALCUL HMAC-SHA256
# ============================================================

def _calculer_signature(
    facture: Facture,
) -> str:
    """
    Calcule la signature HMAC-SHA256.

    Utilise :
        - une clé secrète serveur ;
        - un JSON canonique ;
        - SHA-256.

    Retourne une chaîne hexadécimale
    de 64 caractères.
    """

    secret = _get_signing_key()

    payload = json.dumps(
        _facture_signature_payload(facture),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    return hmac.new(
        secret,
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# ============================================================
# 5. GÉNÉRATION DE LA SIGNATURE
# ============================================================

@transaction.atomic
def generate_facture_hash(
    facture: Facture,
) -> str:
    """
    Génère la signature d'une facture définitive.

    Conditions :
        - facture enregistrée ;
        - facture entièrement payée ;
        - facture définitive ;
        - aucune signature existante.

    Protection :
        - verrouillage SQL ;
        - refus de remplacement ;
        - transaction atomique.

    Retourne :
        signature HMAC-SHA256.
    """

    # --------------------------------------------------------
    # 1. VALIDATION DE L'IDENTIFIANT
    # --------------------------------------------------------

    if (
        facture is None
        or getattr(facture, "pk", None) is None
    ):
        raise ValidationError({
            "facture": (
                "Une facture enregistrée est obligatoire."
            )
        })

    # --------------------------------------------------------
    # 2. VERROUILLAGE DE LA FACTURE
    # --------------------------------------------------------

    try:
        facture = (
            Facture.objects
            .select_for_update()
            .select_related(
                "vente",
                "vente__client",
                "bijouterie",
            )
            .get(pk=facture.pk)
        )

    except Facture.DoesNotExist as exc:
        raise ValidationError({
            "facture": "Facture introuvable."
        }) from exc

    # --------------------------------------------------------
    # 3. VÉRIFICATION DU STATUT
    # --------------------------------------------------------

    if facture.status != Facture.STAT_PAYE:
        raise ValidationError({
            "facture": (
                "La facture doit être totalement payée."
            )
        })

    if facture.type_facture != Facture.TYPE_FACTURE:
        raise ValidationError({
            "facture": (
                "La facture doit être définitive."
            )
        })

    # --------------------------------------------------------
    # 4. SIGNATURE DÉJÀ EXISTANTE
    # --------------------------------------------------------

    if facture.integrity_hash:
        raise ValidationError({
            "integrity_hash": (
                "Cette facture possède déjà "
                "une signature. "
                "Une nouvelle signature est interdite."
            )
        })

    # --------------------------------------------------------
    # 5. CALCUL DE LA SIGNATURE
    # --------------------------------------------------------

    signature = _calculer_signature(
        facture
    )

    # --------------------------------------------------------
    # 6. ENREGISTREMENT
    # --------------------------------------------------------

    facture.integrity_hash = signature
    facture.signed_at = timezone.now()

    facture.save(
        update_fields=[
            "integrity_hash",
            "signed_at",
        ]
    )

    return signature


# ============================================================
# 6. VÉRIFICATION DE LA SIGNATURE
# ============================================================

def verify_facture_hash(
    facture: Facture,
) -> bool:
    """
    Vérifie l'intégrité d'une facture.

    True :
        signature valide.

    False :
        signature absente, incorrecte,
        ou facture introuvable.

    Ne modifie aucune donnée.
    """

    if (
        facture is None
        or getattr(facture, "pk", None) is None
    ):
        return False

    try:
        facture = (
            Facture.objects
            .select_related(
                "vente",
                "vente__client",
                "bijouterie",
            )
            .get(pk=facture.pk)
        )

    except Facture.DoesNotExist:
        return False

    if not facture.integrity_hash:
        return False

    if facture.status != Facture.STAT_PAYE:
        return False

    if facture.type_facture != Facture.TYPE_FACTURE:
        return False

    if facture.signed_at is None:
        return False

    expected = _calculer_signature(
        facture
    )

    return hmac.compare_digest(
        str(facture.integrity_hash),
        expected,
    )

