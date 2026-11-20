# sale/services/facture_pdf_service.py

from __future__ import annotations

import re
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction

from sale.models import Facture, VenteProduit
from sale.pdf.facture_A5_portrait import build_facture_a5_portrait_pdf
from sale.services.facture_hash_service import verify_facture_hash
from sale.services.facture_pdf_data_service import build_facture_pdf_data

# ============================================================
# 1. URL DU PDF
# ============================================================

def _facture_pdf_url(facture) -> str | None:
    """
    Retourne l'URL du PDF enregistré.

    Compatible avec les stockages Django
    locaux et distants.

    Retourne None lorsque le stockage
    ne fournit pas d'URL.
    """

    if not facture.facture_pdf:
        return None

    try:
        return facture.facture_pdf.url

    except (
        ValueError,
        NotImplementedError,
        OSError,
    ):
        return None


# ============================================================
# 2. VALIDATION DE LA FACTURE
# ============================================================

def _valider_facture_pdf(facture: Facture) -> None:
    """
    Vérifie les conditions de génération PDF.

    PROFORMA :
        - vente avec au moins un bijou ;
        - facture non entièrement payée.

    FACTURE DÉFINITIVE :
        - paiement intégral ;
        - signature HMAC valide ;
        - QR code officiel enregistré.
    """

    if not facture.vente_id:
        raise ValidationError({
            "vente": (
                "La facture doit être associée "
                "à une vente."
            )
        })

    if not facture.bijouterie_id:
        raise ValidationError({
            "bijouterie": (
                "La bijouterie est obligatoire."
            )
        })

    if (
        facture.bijouterie_id
        != facture.vente.bijouterie_id
    ):
        raise ValidationError({
            "bijouterie": (
                "La facture et la vente appartiennent "
                "à des bijouteries différentes."
            )
        })

    if not VenteProduit.objects.filter(
        vente_id=facture.vente_id
    ).exists():
        raise ValidationError({
            "vente": (
                "Impossible de générer une facture "
                "pour une vente contenant uniquement "
                "des prestations."
            )
        })

    # --------------------------------------------------------
    # PROFORMA
    # --------------------------------------------------------

    if facture.type_facture == Facture.TYPE_PROFORMA:

        if facture.status == Facture.STAT_PAYE:
            raise ValidationError({
                "facture": (
                    "Une facture totalement payée "
                    "ne doit plus être générée "
                    "en proforma."
                )
            })

        return

    # --------------------------------------------------------
    # FACTURE DÉFINITIVE
    # --------------------------------------------------------

    if facture.type_facture == Facture.TYPE_FACTURE:

        if facture.status != Facture.STAT_PAYE:
            raise ValidationError({
                "facture": (
                    "La facture définitive nécessite "
                    "un paiement intégral."
                )
            })

        if not facture.integrity_hash:
            raise ValidationError({
                "integrity_hash": (
                    "La signature HMAC-SHA256 "
                    "est obligatoire."
                )
            })

        if not verify_facture_hash(facture):
            raise ValidationError({
                "integrity_hash": (
                    "La signature de la facture "
                    "est invalide."
                )
            })

        if not facture.qr_code_image:
            raise ValidationError({
                "qr_code_image": (
                    "Le QR code officiel doit être "
                    "généré avant le PDF définitif."
                )
            })

        return

    # --------------------------------------------------------
    # AUTRES TYPES
    # --------------------------------------------------------

    raise ValidationError({
        "type_facture": (
            "Type de facture non autorisé "
            "pour le PDF A5."
        )
    })


# ============================================================
# 3. NOM DU FICHIER
# ============================================================

def _nom_fichier_pdf(facture: Facture) -> str:
    """
    Produit un nom de fichier sécurisé.

    Le nom distingue une proforma
    d'une facture définitive.
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

    if facture.type_facture == Facture.TYPE_PROFORMA:
        prefixe = "proforma"
    else:
        prefixe = "facture"

    return (
        f"{prefixe}_{numero_securise}_"
        f"{facture.pk}.pdf"
    )


# ============================================================
# 4. GÉNÉRATION DU PDF
# ============================================================

def _generer_pdf_a5(data: dict) -> bytes:
    """
    Génère le PDF A5 portrait en mémoire.

    Ne modifie aucune donnée Django.
    """

    buffer = BytesIO()

    try:
        build_facture_a5_portrait_pdf(
            buffer,
            data,
        )

        pdf_content = buffer.getvalue()

    finally:
        buffer.close()

    if not pdf_content:
        raise ValidationError({
            "facture_pdf": (
                "La génération du PDF a produit "
                "un document vide."
            )
        })

    if not pdf_content.startswith(b"%PDF-"):
        raise ValidationError({
            "facture_pdf": (
                "Le document généré n'est pas "
                "un fichier PDF valide."
            )
        })

    return pdf_content


# ============================================================
# 5. SERVICE PRINCIPAL
# ============================================================

@transaction.atomic
def generate_facture_pdf(
    facture: Facture,
) -> str | None:
    """
    Génère et stocke le PDF A5 portrait Rio-Gold.

    Règles :
        - facture enregistrée ;
        - vente contenant au moins un bijou ;
        - proforma ou facture définitive ;
        - validation HMAC pour facture définitive ;
        - QR officiel obligatoire pour facture définitive ;
        - aucun remplacement automatique ;
        - aucun changement de stock ou paiement.

    Retour :
        URL du PDF ou None.
    """

    # ========================================================
    # 1. IDENTIFIANT
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
                "vente__vendor",
                "vente__vendor__user",
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
    # 3. VALIDATION
    # ========================================================

    _valider_facture_pdf(
        facture
    )

    # ========================================================
    # 4. PDF DÉJÀ EXISTANT
    # ========================================================

    if facture.facture_pdf:
        return _facture_pdf_url(
            facture
        )

    # ========================================================
    # 5. DONNÉES CENTRALISÉES
    # ========================================================

    try:
        data = build_facture_pdf_data(
            facture
        )

    except ValueError as exc:
        raise ValidationError({
            "facture_pdf": str(exc)
        }) from exc

    # ========================================================
    # 6. GÉNÉRATION A5 PORTRAIT
    # ========================================================

    pdf_content = _generer_pdf_a5(
        data
    )

    # ========================================================
    # 7. NOM DU FICHIER
    # ========================================================

    filename = _nom_fichier_pdf(
        facture
    )

    # ========================================================
    # 8. STOCKAGE
    # ========================================================

    facture.facture_pdf.save(
        filename,
        ContentFile(pdf_content),
        save=False,
    )

    facture.save(
        update_fields=[
            "facture_pdf",
        ]
    )

    # ========================================================
    # 9. RETOUR
    # ========================================================

    return _facture_pdf_url(
        facture
    )


