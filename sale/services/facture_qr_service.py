# sale/services/facture_qr_service.py

from __future__ import annotations

import json
import re
from io import BytesIO

import qrcode
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from sale.models import Facture
from sale.services.facture_hash_service import verify_facture_hash

# ============================================================
# 1. URL DU QR CODE
# ============================================================

def _facture_qr_url(facture) -> str | None:
    """
    Retourne l'URL du QR code si disponible.

    Retourne None si le stockage ne fournit
    pas d'URL accessible.
    """

    if not facture.qr_code_image:
        return None

    try:
        return facture.qr_code_image.url

    except (
        ValueError,
        NotImplementedError,
        OSError,
    ):
        return None


# ============================================================
# 2. VALIDATION DE LA FACTURE
# ============================================================

def _valider_facture_pour_qr(
    facture: Facture,
) -> None:
    """
    Vérifie les conditions de génération
    du QR code officiel.
    """

    if facture.status != Facture.STAT_PAYE:
        raise ValidationError({
            "facture": (
                "Le QR code officiel nécessite "
                "une facture totalement payée."
            )
        })

    if facture.type_facture != Facture.TYPE_FACTURE:
        raise ValidationError({
            "facture": (
                "Le QR code officiel nécessite "
                "une facture définitive."
            )
        })

    if not facture.bijouterie_id:
        raise ValidationError({
            "bijouterie": (
                "La bijouterie de la facture "
                "est obligatoire."
            )
        })

    if not facture.date_creation:
        raise ValidationError({
            "date_creation": (
                "La date de création est obligatoire."
            )
        })

    if not facture.numero_facture:
        raise ValidationError({
            "numero_facture": (
                "Le numéro de facture est obligatoire."
            )
        })

    if not facture.integrity_hash:
        raise ValidationError({
            "integrity_hash": (
                "La signature HMAC-SHA256 doit être "
                "générée avant le QR code."
            )
        })

    if not verify_facture_hash(facture):
        raise ValidationError({
            "integrity_hash": (
                "La signature de la facture est invalide. "
                "Génération du QR code refusée."
            )
        })


# ============================================================
# 3. CONSTRUCTION DU CONTENU QR
# ============================================================

def _construire_payload_qr(
    facture: Facture,
) -> dict:
    """
    Construit le contenu JSON du QR code.

    Le QR contient :
        - numéro de facture ;
        - date de création ;
        - NINEA de la bijouterie ;
        - montant TTC ;
        - signature HMAC-SHA256.

    La clé secrète n'est jamais incluse.
    """

    date_creation = facture.date_creation

    if timezone.is_aware(date_creation):
        date_creation = timezone.localtime(
            date_creation
        )

    return {
        "invoice": str(
            facture.numero_facture
        ),

        "date": date_creation.strftime(
            "%Y-%m-%d"
        ),

        "ninea": str(
            getattr(
                facture.bijouterie,
                "ninea",
                "",
            ) or ""
        ),

        "ttc": str(
            facture.montant_total
        ),

        "hash": str(
            facture.integrity_hash
        ),
    }


# ============================================================
# 4. GÉNÉRATION PNG
# ============================================================

def _generer_png_qr(
    qr_content: str,
) -> bytes:
    """
    Génère un QR code PNG.

    Retourne le contenu binaire PNG.
    """

    qr = qrcode.QRCode(
        version=None,
        error_correction=(
            qrcode.constants.ERROR_CORRECT_M
        ),
        box_size=8,
        border=4,
    )

    qr.add_data(qr_content)

    qr.make(
        fit=True
    )

    image = qr.make_image(
        fill_color="black",
        back_color="white",
    )

    buffer = BytesIO()

    try:
        image.save(
            buffer,
            format="PNG",
        )

        png_content = buffer.getvalue()

    finally:
        buffer.close()

    if not png_content.startswith(
        b"\x89PNG\r\n\x1a\n"
    ):
        raise ValidationError({
            "qr_code_image": (
                "La génération du QR code a échoué."
            )
        })

    return png_content


# ============================================================
# 5. NOM DU FICHIER
# ============================================================

def _nom_fichier_qr(
    facture: Facture,
) -> str:
    """
    Génère un nom de fichier sécurisé.
    """

    numero = str(
        facture.numero_facture
        or facture.pk
    )

    numero_securise = re.sub(
        r"[^A-Za-z0-9_-]",
        "_",
        numero,
    )

    numero_securise = (
        numero_securise[:100]
        or str(facture.pk)
    )

    return (
        f"qr_{numero_securise}_{facture.pk}.png"
    )


# ============================================================
# 6. SERVICE PRINCIPAL
# ============================================================

@transaction.atomic
def generate_facture_qr(
    facture: Facture,
) -> str | None:
    """
    Génère le QR code officiel d'une facture.

    Conditions :
        - facture enregistrée ;
        - facture totalement payée ;
        - facture définitive ;
        - signature HMAC-SHA256 valide ;
        - bijouterie obligatoire.

    Règles :
        - un seul QR code par facture ;
        - aucune modification du stock ;
        - aucune modification des paiements ;
        - aucun remplacement automatique du QR existant.

    Retour :
        URL du QR code ou None.
    """

    # ========================================================
    # 1. VALIDATION DE L'IDENTIFIANT
    # ========================================================

    if (
        facture is None
        or getattr(facture, "pk", None) is None
    ):
        raise ValidationError({
            "facture": (
                "Une facture enregistrée "
                "est obligatoire."
            )
        })

    # ========================================================
    # 2. VERROUILLAGE SQL
    # ========================================================

    try:
        facture = (
            Facture.objects
            .select_for_update()
            .select_related(
                "vente",
                "vente__client",
                "bijouterie",
            )
            .get(
                pk=facture.pk
            )
        )

    except Facture.DoesNotExist as exc:
        raise ValidationError({
            "facture": (
                "Facture introuvable."
            )
        }) from exc

    # ========================================================
    # 3. VALIDATION DE LA FACTURE
    # ========================================================

    _valider_facture_pour_qr(
        facture
    )

    # ========================================================
    # 4. QR CODE EXISTANT
    # ========================================================

    if facture.qr_code_image:
        return _facture_qr_url(
            facture
        )

    # ========================================================
    # 5. DONNÉES DU QR CODE
    # ========================================================

    payload = _construire_payload_qr(
        facture
    )

    qr_content = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    # ========================================================
    # 6. GÉNÉRATION DE L'IMAGE
    # ========================================================

    png_content = _generer_png_qr(
        qr_content
    )

    # ========================================================
    # 7. NOM DU FICHIER
    # ========================================================

    filename = _nom_fichier_qr(
        facture
    )

    # ========================================================
    # 8. ENREGISTREMENT
    # ========================================================

    facture.qr_code_image.save(
        filename,
        ContentFile(png_content),
        save=False,
    )

    facture.save(
        update_fields=[
            "qr_code_image",
        ]
    )

    # ========================================================
    # 9. RETOUR
    # ========================================================

    return _facture_qr_url(
        facture
    )

