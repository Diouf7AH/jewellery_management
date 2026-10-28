# sale/views.py
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from io import BytesIO
from uuid import UUID

from django.core.paginator import EmptyPage, Paginator
from django.db.models import (DecimalField, Exists, OuterRef, Prefetch, Q, Sum,
                              prefetch_related_objects)

logger = logging.getLogger(__name__)
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.paginator import EmptyPage, Paginator
from django.db import transaction
from django.db.models import (Count, DecimalField, Exists, ExpressionWrapper,
                              F, Min, OuterRef, Q, Sum, Value)
from django.db.models.functions import Coalesce
from django.http import FileResponse, HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.text import get_valid_filename
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import permissions, status
from rest_framework.exceptions import APIException
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.permissions import (CanCreateSale, CanProcessInvoicePayment,
                                 IsCashierOnly)
from backend.query_scopes import scope_bijouterie_q
from backend.renderers import UserRenderer
from backend.roles import (ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER, ROLE_VENDOR,
                           get_role_name)
from backend.utils.helpers import user_can_access_bijouterie
from compte_depot.models import (ClientDepot, CompteDepot,
                                 CompteDepotTransaction)
from compte_depot.notifications import send_compte_depot_facture_notification
from compte_depot.services import effectuer_retrait
from inventory.models import Bucket, InventoryMovement, MovementType
from inventory.services import log_move
from purchase.models import ProduitLine
from sale.models import (Client, Facture, ModePaiement, Paiement,
                         PaiementLigne, Vente, VenteProduit)
from sale.pdf.escpos_ticket_58mm import build_escpos_ticket_proforma_58mm
from sale.pdf.escpos_ticket_80mm import build_escpos_recu_paiement_80mm
from sale.pdf.facture_A5_portrait import build_facture_a5_portrait_pdf
from sale.pdf.facture_A5_portrait.builder import build_facture_a5_portrait_pdf
from sale.serializers import (CancelProformaVenteSerializer,
                              FactureListSerializer,
                              PaiementMultiModeSerializer,
                              RetourVenteProduitSerializer,
                              UpdateVenteProduitSerializer,
                              VenteCreateInSerializer, VenteDetailSerializer,
                              VenteListSerializer)
from sale.services.comptable_export_service import export_comptable_factures
from sale.services.confirm_service import confirm_sale_out_from_vendor
from sale.services.export.export_facture_excel import export_factures_excel
from sale.services.facture_hash_service import generate_facture_hash
from sale.services.facture_pdf_data_service import build_facture_pdf_data
from sale.services.facture_pdf_service import generate_facture_pdf
from sale.services.facture_qr_service import generate_facture_qr
from sale.services.sale_service import (create_sale_one_vendor,
                                        upsert_client_for_payment,
                                        validate_facture_payable)
from sale.services.vendor_stock_service import ensure_vendor_stock_available
from staff.models import Cashier
from stock.models import Stock, VendorStock
from vendor.models import Vendor

# ============================================================
# PYTHON STANDARD LIBRARY
# ============================================================



# ============================================================
# DJANGO
# ============================================================



# ============================================================
# DJANGO REST FRAMEWORK
# ============================================================



# ============================================================
# SWAGGER
# ============================================================



# ============================================================
# EXCEL
# ============================================================



# ============================================================
# BACKEND
# ============================================================



# ============================================================
# COMPTE DEPOT
# ============================================================



# ============================================================
# INVENTORY
# ============================================================



# ============================================================
# PURCHASE
# ============================================================



# ============================================================
# SALE MODELS
# ============================================================



# ============================================================
# SALE PDF
# ============================================================



# ============================================================
# SALE SERIALIZERS
# ============================================================



# ============================================================
# SALE SERVICES
# ============================================================



# ============================================================
# STAFF
# ============================================================



# ============================================================
# STOCK
# ============================================================



# ============================================================
# VENDOR
# ============================================================



# ============================================================
# CONSTANTES
# ============================================================

# DEFAULT_PAGE_SIZE = getattr(
#     settings,
#     "DEFAULT_PAGE_SIZE",
#     20,
# )

# MAX_PAGE_SIZE = getattr(
#     settings,
#     "MAX_PAGE_SIZE",
#     100,
# )


DEFAULT_PAGE_SIZE = getattr(
    settings,
    "DEFAULT_PAGE_SIZE",
    20,
)

MAX_PAGE_SIZE = getattr(
    settings,
    "MAX_PAGE_SIZE",
    100,
)

ZERO = Decimal("0.00")

# ============================================================
# RÉPONSES D'ERREUR STANDARDISÉES
# ============================================================

def error_response(
    code,
    message,
    status_code=status.HTTP_400_BAD_REQUEST,
    *,
    details=None,
):
    data = {
        "status": "error",
        "code": code,
        "message": message,
    }

    if details is not None:
        data["details"] = details

    return Response(
        data,
        status=status_code,
    )
    

class VenteProduitCreateView(APIView):
    """
    Création d'une vente pour un seul vendeur.

    TYPES :
    - Bijoux uniquement : proforma.
    - Prestations uniquement : sans facture.
    - Bijoux + prestations : proforma.

    IDENTIFICATION :
    - produit_line_id : recherche manuelle.
    - qr : recherche automatique.

    STOCK :
    - ProduitLine exacte.
    - Vérification VendorStock.
    - Aucun FIFO.
    - Aucun SALE_OUT à la création.

    PAIEMENT :
    - Bijoux / mixte : circuit facture.
    - Prestations seules : paiement direct avec reçu.
    """

    permission_classes = [CanCreateSale]
    http_method_names = ["post", "options"]

    # ========================================================
    # 1. VENDEUR CONNECTÉ
    # ========================================================

    def _get_vendor_for_user(self, user):
        return (
            Vendor.objects
            .select_related("bijouterie", "user")
            .filter(
                user=user,
                verifie=True,
            )
            .first()
        )

    # ========================================================
    # 2. VÉRIFICATION PRÉLIMINAIRE DU STOCK
    # ========================================================

    def _ensure_produit_line_in_vendor_stock(
        self,
        *,
        user,
        role,
        produit_line,
    ):
        """
        Vérifie que le bijou est présent dans le stock
        du vendeur connecté.

        Le service create_sale_one_vendor() vérifie
        ensuite la quantité totale sous verrou.
        """

        if role != ROLE_VENDOR:
            return

        vendor = self._get_vendor_for_user(user)

        if vendor is None:
            raise ValidationError({
                "vendor": (
                    "Profil vendeur introuvable "
                    "ou désactivé."
                )
            })

        exists = (
            VendorStock.objects
            .filter(
                vendor=vendor,
                bijouterie=vendor.bijouterie,
                produit_line=produit_line,
                quantite_allouee__gt=F(
                    "quantite_vendue"
                ),
            )
            .exists()
        )

        if not exists:
            raise ValidationError({
                "produit_line": (
                    "Ce bijou n'est pas disponible "
                    "dans le stock du vendeur."
                )
            })

    # ========================================================
    # 3. RECHERCHE MANUELLE OU QR CODE
    # ========================================================

    def _resolve_produit_line_id(
        self,
        item,
        *,
        user,
        role,
    ):
        """
        Retourne l'identifiant d'une ProduitLine.

        Recherche manuelle :
            produit_line_id

        Recherche automatique :
            qr = UUID
            qr = PL:<uuid>
        """

        produit_line_id = item.get("produit_line_id")
        qr = item.get("qr")

        if produit_line_id is not None and qr:
            raise ValidationError({
                "produit_line": (
                    "Fournissez produit_line_id ou qr, "
                    "pas les deux."
                )
            })

        if produit_line_id is None and not qr:
            raise ValidationError({
                "produit_line": (
                    "Vous devez fournir "
                    "produit_line_id ou qr."
                )
            })

        if produit_line_id is not None:

            try:
                produit_line_id = int(produit_line_id)
            except (TypeError, ValueError):
                raise ValidationError({
                    "produit_line_id": (
                        "Identifiant ProduitLine invalide."
                    )
                })

            if produit_line_id <= 0:
                raise ValidationError({
                    "produit_line_id": (
                        "L'identifiant doit être positif."
                    )
                })

            produit_line = (
                ProduitLine.objects
                .select_related("produit", "lot")
                .filter(pk=produit_line_id)
                .first()
            )

        else:

            scan_value = (
                str(qr)
                .replace("\n", "")
                .replace("\r", "")
                .strip()
            )

            if not scan_value.upper().startswith("PL:"):
                raise ValidationError({
                    "qr": "Le QR code doit commencer par PL:."
                })

            scan_value = scan_value[3:].strip()

            try:
                produit_line_uuid = UUID(scan_value)
            except (ValueError, TypeError, AttributeError):
                raise ValidationError({
                    "qr": (
                        "QR code invalide. "
                        "UUID ProduitLine attendu."
                    )
                })

            produit_line = (
                ProduitLine.objects
                .select_related("produit", "lot")
                .filter(uuid=produit_line_uuid)
                .first()
            )

        if produit_line is None:
            raise ValidationError({
                "produit_line": (
                    "ProduitLine introuvable."
                )
            })

        if not produit_line.produit_id:
            raise ValidationError({
                "produit_line": (
                    "Cette ProduitLine n'a aucun produit."
                )
            })

        if not produit_line.lot_id:
            raise ValidationError({
                "produit_line": (
                    "Cette ProduitLine n'a aucun lot."
                )
            })

        self._ensure_produit_line_in_vendor_stock(
            user=user,
            role=role,
            produit_line=produit_line,
        )

        return produit_line.pk

    # ========================================================
    # 4. NORMALISATION DES BIJOUX
    # ========================================================

    def _normalize_produits(
        self,
        produits,
        *,
        user,
        role,
    ):
        """
        Convertit les QR codes en produit_line_id.

        Le service de création reçoit uniquement
        des identifiants ProduitLine.
        """

        normalized = []

        for item in produits:

            item = dict(item)

            item["produit_line_id"] = (
                self._resolve_produit_line_id(
                    item,
                    user=user,
                    role=role,
                )
            )

            item.pop("qr", None)
            item.pop("produit_id", None)
            item.pop("sku", None)

            normalized.append(item)

        return normalized

    # ========================================================
    # 5. SWAGGER
    # ========================================================

    @swagger_auto_schema(
        operation_id="creer_vente_rio_gold",
        operation_summary=(
            "Créer une vente : bijoux, prestations ou mixte"
        ),
        operation_description="""
        Création d'une vente Rio-Gold pour un seul vendeur.

        IDENTIFICATION DES BIJOUX
        ------------------------
        Recherche manuelle :
        - produit_line_id : identifiant de ProduitLine.

        Recherche automatique :
        - qr : UUID de ProduitLine.
        - qr : PL:<uuid>.

        Un seul identifiant par bijou.

        TYPES DE VENTES
        ---------------
        1. Bijoux uniquement :
           création d'une facture proforma.

        2. Prestations uniquement :
           aucune facture, paiement direct avec reçu.

        3. Bijoux + prestations :
           création d'une facture proforma.

        RÉDUCTIONS
        ----------
        - Bijou neuf : remise fixe en FCFA.
        - Bijou occasion : pourcentage automatique
          depuis ProduitLine.pourcentage_occasion.

        STOCK
        -----
        - Vérification VendorStock.
        - Aucun FIFO.
        - Aucun SALE_OUT à la création.
        - Consommation après paiement intégral.

        AUTORISATIONS
        -------------
        - Vendeur : utilise son propre profil.
        - Admin / Manager : vendor_email obligatoire.
        - Manager : vendeur dans une bijouterie autorisée.
        """,
        request_body=VenteCreateInSerializer,
        responses={
            201: openapi.Response(
                description="Vente créée avec succès",
            ),
            400: openapi.Response(
                description="Erreur de validation",
            ),
            403: openapi.Response(
                description="Accès refusé",
            ),
        },
        tags=["Ventes"],
    )
    @transaction.atomic
    def post(self, request):

        # ====================================================
        # 6. VALIDATION DU PAYLOAD
        # ====================================================

        serializer = VenteCreateInSerializer(
            data=request.data,
            context={"request": request},
        )

        serializer.is_valid(raise_exception=True)

        validated = serializer.validated_data

        role = (
            get_role_name(request.user) or ""
        ).lower().strip()

        # ====================================================
        # 7. VENDEUR POUR ADMIN / MANAGER
        # ====================================================

        vendor_email = (
            validated.get("vendor_email") or ""
        ).strip()

        if role in {ROLE_ADMIN, ROLE_MANAGER}:

            if not vendor_email:
                return Response(
                    {
                        "detail": (
                            "vendor_email est obligatoire "
                            "pour admin/manager."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            vendor = (
                Vendor.objects
                .select_related("bijouterie", "user")
                .filter(
                    user__email__iexact=vendor_email,
                    verifie=True,
                )
                .first()
            )

            if vendor is None:
                return Response(
                    {
                        "detail": (
                            "Vendeur introuvable "
                            "ou désactivé."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if role == ROLE_MANAGER:

                manager_profile = getattr(
                    request.user,
                    "staff_manager_profile",
                    None,
                )

                if (
                    manager_profile is None
                    or not getattr(
                        manager_profile,
                        "verifie",
                        False,
                    )
                ):
                    return Response(
                        {
                            "detail": (
                                "Profil manager invalide "
                                "ou désactivé."
                            )
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

                if not (
                    manager_profile.bijouteries
                    .filter(pk=vendor.bijouterie_id)
                    .exists()
                ):
                    return Response(
                        {
                            "detail": (
                                "Ce vendeur n'appartient pas "
                                "à une bijouterie autorisée."
                            )
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

        # ====================================================
        # 8. PRODUITS ET PRESTATIONS
        # ====================================================

        produits_in = validated.get("produits") or []
        autres = validated.get("autres") or []

        if not produits_in and not autres:
            return Response(
                {
                    "detail": (
                        "La vente doit contenir au moins "
                        "un bijou ou une prestation."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ====================================================
        # 9. NORMALISATION PRODUITLINE
        # ====================================================

        try:
            produits_normalized = (
                self._normalize_produits(
                    produits_in,
                    user=request.user,
                    role=role,
                )
            )

        except ValidationError as exc:
            return Response(
                {
                    "detail": (
                        getattr(exc, "message_dict", None)
                        or getattr(exc, "messages", None)
                        or str(exc)
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ====================================================
        # 10. PAYLOAD SERVICE
        # ====================================================

        payload = {
            "vendor_email": (
                vendor_email
                if role in {ROLE_ADMIN, ROLE_MANAGER}
                else None
            ),
            "client": validated.get("client") or {},
            "produits": produits_normalized,
            "autres": autres,
        }

        # ====================================================
        # 11. CRÉATION DE LA VENTE
        # ====================================================

        try:
            vente, facture, audit_created = (
                create_sale_one_vendor(
                    user=request.user,
                    role=role,
                    payload=payload,
                )
            )

        except ValidationError as exc:
            return Response(
                {
                    "detail": (
                        getattr(exc, "message_dict", None)
                        or getattr(exc, "messages", None)
                        or str(exc)
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ====================================================
        # 12. TYPE DE VENTE
        # ====================================================

        contient_bijoux = bool(produits_normalized)
        contient_prestations = bool(autres)

        if contient_bijoux and contient_prestations:
            type_vente = "mixte"

        elif contient_bijoux:
            type_vente = "bijoux"

        else:
            type_vente = "prestations"

        paiement_direct = (
            type_vente == "prestations"
        )

        # ====================================================
        # 13. PRODUITS POUR LA RÉPONSE
        # ====================================================

        produits_response = []

        vente_lignes = (
            vente.lignes
            .select_related(
                "produit_line",
                "produit_line__produit",
            )
            .all()
        )

        for ligne in vente_lignes:

            produit_line = ligne.produit_line
            produit = produit_line.produit

            # Snapshot historique de la vente.
            etat = ligne.etat_vente

            pourcentage_occasion = Decimal(
                str(
                    ligne.pourcentage_occasion
                    or "0.00"
                )
            )

            montant_ht = Decimal(
                str(ligne.montant_ht or "0.00")
            )

            montant_reduction = Decimal(
                str(
                    ligne.montant_reduction
                    or "0.00"
                )
            )

            reduction_occasion = (
                montant_reduction
                if etat == "O"
                else Decimal("0.00")
            )

            produits_response.append({
                "ligne_id": ligne.pk,
                "produit_line_id": produit_line.pk,
                "produit_line_uuid": str(
                    produit_line.uuid
                ),
                "produit_id": produit.pk,
                "produit_nom": produit.nom,
                "sku": getattr(
                    produit,
                    "sku",
                    None,
                ),
                "etat": etat,
                "quantite": ligne.quantite,
                "poids_unitaire_vente": str(
                    ligne.poids_unitaire_vente
                ),
                "prix_vente_grammes": str(
                    ligne.prix_vente_grammes
                ),
                "montant_ht": str(montant_ht),
                "pourcentage_occasion": str(
                    pourcentage_occasion
                ),
                "reduction_occasion": str(
                    reduction_occasion
                ),
                "montant_reduction": str(
                    montant_reduction
                ),
                "remise": str(
                    ligne.remise
                    or Decimal("0.00")
                ),
                "montant_total": str(
                    ligne.montant_total
                    or Decimal("0.00")
                ),
            })

        # ====================================================
        # 14. PRESTATIONS POUR LA RÉPONSE
        # ====================================================

        autres_response = [
            {
                "id": autre.pk,
                "type_autre": autre.type_autre,
                "type_autre_label": (
                    autre.get_type_autre_display()
                ),
                "quantite": autre.quantite,
                "prix_unitaire": str(
                    autre.prix_unitaire
                ),
                "montant_total": str(
                    autre.montant_total
                ),
            }
            for autre in vente.autres.all()
        ]

        # ====================================================
        # 15. FACTURE OPTIONNELLE
        # ====================================================

        facture_response = None

        if facture is not None:

            facture_response = {
                "facture_id": facture.pk,
                "numero_facture": (
                    facture.numero_facture
                ),
                "type_facture": (
                    facture.type_facture
                ),
                "status_facture": (
                    facture.status
                ),
                "montant_ht": str(
                    facture.montant_ht
                ),
                "appliquer_tva": facture.appliquer_tva,
                "taux_tva": (
                    str(facture.taux_tva)
                    if facture.taux_tva is not None
                    else None
                ),
                "montant_tva": (
                    str(facture.montant_tva)
                    if facture.montant_tva is not None
                    else None
                ),
                "montant_total": str(
                    facture.montant_total
                ),
            }

        # ====================================================
        # 16. RÉPONSE FINALE
        # ====================================================

        client = vente.client
        bijouterie = vente.bijouterie

        return Response(
            {
                "message": (
                    "Prestation enregistrée. Paiement direct requis."
                    if paiement_direct
                    else "Vente créée avec proforma."
                ),
                "vente_id": vente.pk,
                "numero_vente": (
                    vente.numero_vente
                    if not paiement_direct
                    else None
                ),
                "numero_prestation": (
                    vente.numero_vente
                    if paiement_direct
                    else None
                ),
                "vente_id": vente.pk,
                "numero_vente": vente.numero_vente,
                "type_vente": type_vente,
                "paiement_direct": paiement_direct,
                "paiement_effectue": False,
                "recu_paiement": None,
                "montant_total_vente": str(
                    vente.montant_total
                    or Decimal("0.00")
                ),
                "facture": facture_response,
                "audit_created": bool(audit_created),
                "bijouterie": {
                    "id": bijouterie.pk,
                    "nom": bijouterie.nom,
                },
                "client": {
                    "id": (
                        client.pk
                        if client else None
                    ),
                    "nom": (
                        client.nom
                        if client else None
                    ),
                    "prenom": (
                        client.prenom
                        if client else None
                    ),
                    "telephone": (
                        client.telephone
                        if client else None
                    ),
                },
                "produits": produits_response,
                "autres": autres_response,
            },
            status=status.HTTP_201_CREATED,
        )


class VenteListAPIView(APIView):
    """
    Liste paginée des ventes Rio-Gold.

    Rôles :
    - admin : toutes les ventes accessibles
    - manager : ventes de ses bijouteries
    - vendor : uniquement ses ventes
    - cashier : ventes de sa bijouterie

    Comprend :
    - bijoux : vente.lignes
    - prestations : vente.autres
    """

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Lister les ventes",
        operation_description="""
Liste les ventes selon le rôle connecté.

Par défaut, affiche les ventes de l'année en cours.

Les ventes peuvent contenir :
- uniquement des bijoux ;
- uniquement des prestations ;
- des bijoux et des prestations.

Filtres disponibles :
- annee
- numero_vente
- client_q
- vendor_id
- status_facture
- page
- page_size
        """,
        manual_parameters=[
            openapi.Parameter(
                "annee",
                openapi.IN_QUERY,
                description="Année des ventes. Par défaut : année en cours.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "numero_vente",
                openapi.IN_QUERY,
                description="Recherche par numéro de vente",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "client_q",
                openapi.IN_QUERY,
                description="Recherche client par nom, prénom ou téléphone",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "vendor_id",
                openapi.IN_QUERY,
                description="Filtrer par vendeur",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "status_facture",
                openapi.IN_QUERY,
                description="Statut facture : non_paye, partiel ou paye",
                type=openapi.TYPE_STRING,
                enum=[
                    "non_paye",
                    "partiel",
                    "paye",
                ],
            ),
            openapi.Parameter(
                "page",
                openapi.IN_QUERY,
                description="Numéro de page",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "page_size",
                openapi.IN_QUERY,
                description="Nombre d'éléments par page",
                type=openapi.TYPE_INTEGER,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Liste des ventes"
            ),
            400: "Erreur de filtre",
            403: "Accès refusé",
        },
        tags=["Ventes"],
    )
    def get(self, request):

        # =====================================================
        # 1. UTILISATEUR ET RÔLE
        # =====================================================

        user = request.user

        role = (
            get_role_name(user) or ""
        ).lower().strip()

        allowed_roles = {
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_VENDOR,
            ROLE_CASHIER,
        }

        if role not in allowed_roles:
            return error_response(
                code="SALE_LIST_ACCESS_DENIED",
                message="Accès refusé.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # 2. PROFIL VENDEUR
        # =====================================================

        my_vendor = None

        if role == ROLE_VENDOR:

            my_vendor = getattr(
                user,
                "staff_vendor_profile",
                None,
            )

            if not (
                my_vendor
                and getattr(my_vendor, "verifie", False)
                and my_vendor.bijouterie_id
            ):
                return error_response(
                    code="INVALID_VENDOR_PROFILE",
                    message=(
                        "Profil vendeur introuvable, "
                        "non vérifié ou sans bijouterie."
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )

        # =====================================================
        # 3. QUERYSET DE BASE
        # =====================================================

        qs = (
            Vente.objects
            .select_related(
                "client",
                "vendor",
                "vendor__user",
                "bijouterie",
                "facture_vente",
            )
            .prefetch_related(
                # Bijoux
                "lignes",
                "lignes__produit_line",
                "lignes__produit_line__produit",
                "lignes__produit_line__lot",
                "lignes__vendor",
                "lignes__vendor__user",

                # Prestations et autres lignes
                "autres",
            )
            .filter(
                scope_bijouterie_q(
                    user,
                    field="bijouterie_id",
                )
            )
            .order_by(
                "-created_at",
                "-id",
            )
        )

        # =====================================================
        # 4. VENDEUR : SES VENTES UNIQUEMENT
        # =====================================================

        if role == ROLE_VENDOR:
            qs = qs.filter(
                vendor_id=my_vendor.id
            )

        # =====================================================
        # 5. FILTRE ANNÉE
        # =====================================================

        current_year = timezone.localdate().year

        annee_raw = (
            request.query_params.get("annee")
            or str(current_year)
        )

        try:
            annee = int(annee_raw)
        except (TypeError, ValueError):
            return error_response(
                code="INVALID_YEAR",
                message="annee doit être une année valide.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if annee < 2000 or annee > current_year:
            return error_response(
                code="INVALID_YEAR",
                message=(
                    f"annee doit être comprise entre "
                    f"2000 et {current_year}."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        qs = qs.filter(
            created_at__year=annee
        )

        # =====================================================
        # 6. FILTRE NUMÉRO DE VENTE
        # =====================================================

        numero_vente = (
            request.query_params.get(
                "numero_vente", ""
            ) or ""
        ).strip()

        if numero_vente:
            qs = qs.filter(
                numero_vente__icontains=numero_vente
            )

        # =====================================================
        # 7. FILTRE CLIENT
        # =====================================================

        client_q = (
            request.query_params.get(
                "client_q", ""
            ) or ""
        ).strip()

        if client_q:
            qs = qs.filter(
                Q(client__nom__icontains=client_q)
                | Q(client__prenom__icontains=client_q)
                | Q(client__telephone__icontains=client_q)
            )

        # =====================================================
        # 8. FILTRE VENDEUR
        # =====================================================

        vendor_id_raw = request.query_params.get(
            "vendor_id"
        )

        if vendor_id_raw not in (None, ""):

            try:
                vendor_id = int(vendor_id_raw)
            except (TypeError, ValueError):
                return error_response(
                    code="INVALID_VENDOR_ID",
                    message="vendor_id doit être un entier positif.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if vendor_id <= 0:
                return error_response(
                    code="INVALID_VENDOR_ID",
                    message="vendor_id doit être un entier positif.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if (
                role == ROLE_VENDOR
                and vendor_id != my_vendor.id
            ):
                return error_response(
                    code="VENDOR_SCOPE_FORBIDDEN",
                    message=(
                        "Un vendeur ne peut filtrer "
                        "que ses propres ventes."
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )

            qs = qs.filter(
                vendor_id=vendor_id
            )

        # =====================================================
        # 9. FILTRE STATUT FACTURE
        # =====================================================

        status_facture = (
            request.query_params.get(
                "status_facture", ""
            ) or ""
        ).strip()

        allowed_invoice_statuses = {
            Facture.STAT_NON_PAYE,
            Facture.STAT_PARTIEL,
            Facture.STAT_PAYE,
        }

        if status_facture:

            if status_facture not in allowed_invoice_statuses:
                return error_response(
                    code="INVALID_INVOICE_STATUS",
                    message=(
                        "status_facture invalide. "
                        "Utiliser non_paye, partiel ou paye."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            qs = qs.filter(
                facture_vente__status=status_facture
            )

        # =====================================================
        # 10. PAGINATION
        # =====================================================

        def parse_positive_int(
            name: str,
            default: int,
        ) -> int:

            raw_value = request.query_params.get(name)

            if raw_value in (None, ""):
                return default

            try:
                value = int(raw_value)
            except (TypeError, ValueError):
                return default

            return max(1, value)

        page = parse_positive_int(
            "page",
            1,
        )

        page_size = min(
            parse_positive_int(
                "page_size",
                20,
            ),
            100,
        )

        paginator = Paginator(
            qs,
            page_size,
        )

        # =====================================================
        # 11. AUCUN RÉSULTAT
        # =====================================================

        if paginator.count == 0:
            return Response(
                {
                    "count": 0,
                    "page": 1,
                    "page_size": page_size,
                    "num_pages": 0,
                    "annee": annee,
                    "results": [],
                },
                status=status.HTTP_200_OK,
            )

        # =====================================================
        # 12. PAGE
        # =====================================================

        try:
            page_obj = paginator.page(page)
        except EmptyPage:
            page_obj = paginator.page(
                paginator.num_pages
            )

        # =====================================================
        # 13. SERIALIZATION
        # =====================================================

        serializer = VenteListSerializer(
            page_obj.object_list,
            many=True,
        )

        # =====================================================
        # 14. RÉPONSE
        # =====================================================

        return Response(
            {
                "count": paginator.count,
                "page": page_obj.number,
                "page_size": page_size,
                "num_pages": paginator.num_pages,
                "annee": annee,
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class ListFacturesAPayerView(APIView):
    """
    Liste les factures non payées ou partiellement payées.

    Règles :
    - Admin : factures de son scope.
    - Manager : factures de ses bijouteries.
    - Vendor : factures de ses propres ventes.
    - Cashier : factures de sa bijouterie.

    Une facture est éligible uniquement si la vente
    contient au moins une ligne de bijou.

    Les ventes mixtes (bijoux + prestations)
    sont autorisées.
    """

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Lister les factures à payer",
        operation_description="""
Liste les factures non payées ou partiellement payées.

Règles :
- admin : factures autorisées par son scope
- manager : factures de ses bijouteries
- vendor : factures de ses propres ventes
- cashier : factures de sa bijouterie

Seules les ventes contenant au moins un bijou sont incluses.

Les ventes mixtes (bijoux + prestations) sont autorisées.
Les ventes contenant uniquement des prestations sont exclues.

Par défaut, les factures de l'année en cours sont affichées.

Filtres :
- annee
- numero_facture
- client_q
- payment_mode
- page
- page_size
        """,
        manual_parameters=[
            openapi.Parameter(
                "annee",
                openapi.IN_QUERY,
                description=(
                    "Année des factures. "
                    "Par défaut : année en cours."
                ),
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "numero_facture",
                openapi.IN_QUERY,
                description="Recherche par numéro de facture",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "client_q",
                openapi.IN_QUERY,
                description=(
                    "Recherche client par nom, prénom "
                    "ou téléphone"
                ),
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "payment_mode",
                openapi.IN_QUERY,
                description=(
                    "Filtrer par code du mode de paiement "
                    "(cash, wave, orange_money, etc.)"
                ),
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "page",
                openapi.IN_QUERY,
                description="Numéro de page",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "page_size",
                openapi.IN_QUERY,
                description="Nombre d'éléments par page",
                type=openapi.TYPE_INTEGER,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Liste des factures à payer"
            ),
            400: "Erreur de filtre",
            403: "Accès refusé",
        },
        tags=["Factures"],
    )
    def get(self, request):

        # =====================================================
        # 1. UTILISATEUR ET RÔLE
        # =====================================================

        user = request.user

        role = (
            get_role_name(user) or ""
        ).lower().strip()

        allowed_roles = {
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_VENDOR,
            ROLE_CASHIER,
        }

        if role not in allowed_roles:
            return error_response(
                code="INVOICE_LIST_ACCESS_DENIED",
                message="Accès refusé.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # 2. QUERYSET DE BASE
        # =====================================================

        qs = (
            Facture.objects
            .select_related(
                "bijouterie",
                "vente",
                "vente__client",
                "vente__vendor",
                "vente__vendor__user",
            )
            .prefetch_related(
                # Paiements
                "paiements",

                # Bijoux
                "vente__lignes",
                "vente__lignes__vendor",
                "vente__lignes__vendor__user",

                # ProduitLine : source de vérité
                "vente__lignes__produit_line",
                "vente__lignes__produit_line__lot",

                # Produit associé à ProduitLine
                "vente__lignes__produit_line__produit",
                "vente__lignes__produit_line__produit__categorie",
                "vente__lignes__produit_line__produit__marque",
                "vente__lignes__produit_line__produit__purete",
                "vente__lignes__produit_line__produit__modele",

                # Prestations et autres lignes
                "vente__autres",
            )
            .filter(
                status__in=[
                    Facture.STAT_NON_PAYE,
                    Facture.STAT_PARTIEL,
                ],
                # Au moins un bijou est obligatoire
                vente__lignes__isnull=False,
            )
            .distinct()
        )

        # =====================================================
        # 3. SCOPE BIJOUTERIE
        # =====================================================

        qs = qs.filter(
            scope_bijouterie_q(
                user,
                field="bijouterie_id",
            )
        )

        # =====================================================
        # 4. VENDEUR : UNIQUEMENT SES FACTURES
        # =====================================================

        if role == ROLE_VENDOR:

            vendor = getattr(
                user,
                "staff_vendor_profile",
                None,
            )

            if not (
                vendor
                and getattr(vendor, "verifie", False)
                and vendor.bijouterie_id
            ):
                return error_response(
                    code="INVALID_VENDOR_PROFILE",
                    message=(
                        "Profil vendeur introuvable, "
                        "non vérifié ou sans bijouterie."
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )

            qs = qs.filter(
                vente__vendor_id=vendor.id
            )

        # =====================================================
        # 5. FILTRE ANNÉE
        # =====================================================

        current_year = timezone.localdate().year

        annee_raw = (
            request.query_params.get("annee")
            or str(current_year)
        )

        try:
            annee = int(annee_raw)
        except (TypeError, ValueError):
            return error_response(
                code="INVALID_YEAR",
                message="annee doit être une année valide.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if annee < 2000 or annee > current_year:
            return error_response(
                code="INVALID_YEAR",
                message=(
                    f"annee doit être comprise entre "
                    f"2000 et {current_year}."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        qs = qs.filter(
            date_creation__year=annee
        )

        # =====================================================
        # 6. FILTRE NUMÉRO FACTURE
        # =====================================================

        numero = (
            request.query_params.get(
                "numero_facture", ""
            ) or ""
        ).strip()

        if numero:
            qs = qs.filter(
                numero_facture__icontains=numero
            )

        # =====================================================
        # 7. FILTRE CLIENT
        # =====================================================

        client_q = (
            request.query_params.get(
                "client_q", ""
            ) or ""
        ).strip()

        if client_q:
            qs = qs.filter(
                Q(
                    vente__client__nom__icontains=client_q
                )
                | Q(
                    vente__client__prenom__icontains=client_q
                )
                | Q(
                    vente__client__telephone__icontains=client_q
                )
            )

        # =====================================================
        # 8. FILTRE MODE DE PAIEMENT
        # =====================================================

        payment_mode = (
            request.query_params.get(
                "payment_mode", ""
            ) or ""
        ).strip()

        if payment_mode:
            qs = (
                qs.filter(
                    paiements__lignes__mode_paiement__code__iexact=(
                        payment_mode
                    )
                )
                .distinct()
            )

        # =====================================================
        # 9. TRI
        # =====================================================

        qs = qs.order_by(
            "-date_creation",
            "-id",
        )

        # =====================================================
        # 10. PAGINATION
        # =====================================================

        def parse_positive_int(
            name: str,
            default: int,
        ) -> int:

            value = request.query_params.get(name)

            if value in (None, ""):
                return default

            try:
                value = int(value)
            except (TypeError, ValueError):
                return default

            return max(1, value)

        page = parse_positive_int(
            "page",
            1,
        )

        page_size = min(
            parse_positive_int(
                "page_size",
                DEFAULT_PAGE_SIZE,
            ),
            MAX_PAGE_SIZE,
        )

        paginator = Paginator(
            qs,
            page_size,
        )

        # =====================================================
        # 11. AUCUN RÉSULTAT
        # =====================================================

        if paginator.count == 0:
            return Response(
                {
                    "count": 0,
                    "page": 1,
                    "page_size": page_size,
                    "num_pages": 0,
                    "annee": annee,
                    "results": [],
                },
                status=status.HTTP_200_OK,
            )

        # =====================================================
        # 12. PAGE
        # =====================================================

        try:
            page_obj = paginator.page(page)
        except EmptyPage:
            page_obj = paginator.page(
                paginator.num_pages
            )

        # =====================================================
        # 13. SERIALIZATION
        # =====================================================

        serializer = FactureListSerializer(
            page_obj.object_list,
            many=True,
        )

        # =====================================================
        # 14. RESPONSE
        # =====================================================

        return Response(
            {
                "count": paginator.count,
                "page": page_obj.number,
                "page_size": page_size,
                "num_pages": paginator.num_pages,
                "annee": annee,
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )
        


class ListFacturePayeesView(APIView):
    """
    Liste paginée des factures entièrement payées.

    Règles :
    - Admin : factures de son scope.
    - Manager : factures de ses bijouteries.
    - Vendor : uniquement ses propres ventes.
    - Cashier : factures de sa bijouterie.

    Exclut les ventes contenant uniquement
    des prestations.

    Optimisations :
    - EXISTS pour identifier les ventes avec bijoux.
    - Pagination avant préchargement des relations.
    - Agrégation des paiements sur la page.
    - Préchargement des bijoux de la page.
    """

    permission_classes = [IsAuthenticated]

    DEFAULT_PAGE_SIZE = 25
    MAX_PAGE_SIZE = 100

    @staticmethod
    def parse_positive_int(request, name, default):
        raw = request.query_params.get(name)

        if raw in (None, ""):
            return default

        try:
            value = int(raw)
        except (TypeError, ValueError):
            return default

        return max(1, value)

    @swagger_auto_schema(
        operation_summary="Lister les factures payées",
        operation_description=(
            "Liste paginée des factures payées. "
            "Filtrage par rôle et bijouterie. "
            "Les ventes de prestations seules sont exclues."
        ),
        manual_parameters=[
            openapi.Parameter(
                "annee",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                description="Année, par défaut année courante",
            ),
            openapi.Parameter(
                "numero_facture",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "vendor_id",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "client_q",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "payment_mode",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "page",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "page_size",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
            ),
        ],
        responses={
            200: "Liste des factures payées",
            400: "Erreur de filtre",
            403: "Accès refusé",
        },
        tags=["Factures"],
    )
    def get(self, request):

        # ====================================================
        # 1. UTILISATEUR ET RÔLE
        # ====================================================

        user = request.user

        role = (
            get_role_name(user) or ""
        ).lower().strip()

        allowed_roles = {
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_VENDOR,
            ROLE_CASHIER,
        }

        if role not in allowed_roles:
            return error_response(
                code="PAID_INVOICE_LIST_ACCESS_DENIED",
                message="Accès refusé.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # ====================================================
        # 2. PROFILS VÉRIFIÉS
        # ====================================================

        my_vendor = None
        manager_profile = None

        if role == ROLE_VENDOR:
            my_vendor = getattr(
                user,
                "staff_vendor_profile",
                None,
            )

            if not (
                my_vendor
                and my_vendor.verifie
                and my_vendor.bijouterie_id
            ):
                return error_response(
                    code="INVALID_VENDOR_PROFILE",
                    message="Profil vendeur invalide.",
                    status_code=status.HTTP_403_FORBIDDEN,
                )

        elif role == ROLE_MANAGER:
            manager_profile = getattr(
                user,
                "staff_manager_profile",
                None,
            )

            if not (
                manager_profile
                and manager_profile.verifie
            ):
                return error_response(
                    code="INVALID_MANAGER_PROFILE",
                    message="Profil manager invalide.",
                    status_code=status.HTTP_403_FORBIDDEN,
                )

        elif role == ROLE_CASHIER:
            cashier_profile = getattr(
                user,
                "staff_cashier_profile",
                None,
            )

            if not (
                cashier_profile
                and cashier_profile.verifie
                and cashier_profile.bijouterie_id
            ):
                return error_response(
                    code="INVALID_CASHIER_PROFILE",
                    message="Profil caissier invalide.",
                    status_code=status.HTTP_403_FORBIDDEN,
                )

        # ====================================================
        # 3. FACTURES PAYÉES AVEC BIJOUX
        # ====================================================

        ventes_avec_bijoux = VenteProduit.objects.filter(
            vente_id=OuterRef("vente_id"),
        )

        qs = (
            Facture.objects
            .filter(
                status=Facture.STAT_PAYE,
            )
            .alias(
                contient_bijoux=Exists(
                    ventes_avec_bijoux
                )
            )
            .filter(
                contient_bijoux=True,
            )
            .filter(
                scope_bijouterie_q(
                    user,
                    field="bijouterie_id",
                )
            )
        )

        # ====================================================
        # 4. SCOPE VENDEUR
        # ====================================================

        if role == ROLE_VENDOR:
            qs = qs.filter(
                vente__vendor_id=my_vendor.pk,
            )

        # ====================================================
        # 5. ANNÉE
        # ====================================================

        current_year = timezone.localdate().year

        annee_raw = (
            request.query_params.get("annee")
            or str(current_year)
        )

        try:
            annee = int(annee_raw)
        except (TypeError, ValueError):
            return error_response(
                code="INVALID_YEAR",
                message="annee doit être une année valide.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if annee < 2000 or annee > current_year:
            return error_response(
                code="INVALID_YEAR",
                message=(
                    f"annee doit être comprise entre "
                    f"2000 et {current_year}."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        qs = qs.filter(
            date_creation__year=annee,
        )

        # ====================================================
        # 6. NUMÉRO FACTURE
        # ====================================================

        numero = (
            request.query_params.get(
                "numero_facture", ""
            ) or ""
        ).strip()

        if numero:
            qs = qs.filter(
                numero_facture__icontains=numero,
            )

        # ====================================================
        # 7. VENDEUR
        # ====================================================

        vendor_id_raw = request.query_params.get(
            "vendor_id"
        )

        if vendor_id_raw not in (None, ""):

            try:
                vendor_id = int(vendor_id_raw)
            except (TypeError, ValueError):
                vendor_id = 0

            if vendor_id <= 0:
                return error_response(
                    code="INVALID_VENDOR_ID",
                    message="vendor_id doit être un entier positif.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if (
                role == ROLE_VENDOR
                and vendor_id != my_vendor.pk
            ):
                return error_response(
                    code="VENDOR_SCOPE_FORBIDDEN",
                    message=(
                        "Un vendeur ne peut filtrer "
                        "que ses propres factures."
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )

            if role == ROLE_MANAGER:
                vendor_allowed = (
                    manager_profile.bijouteries
                    .filter(vendors__id=vendor_id)
                    .exists()
                )

                if not vendor_allowed:
                    return error_response(
                        code="VENDOR_OUTSIDE_MANAGER_SCOPE",
                        message=(
                            "Ce vendeur est hors "
                            "de vos bijouteries."
                        ),
                        status_code=status.HTTP_403_FORBIDDEN,
                    )

            qs = qs.filter(
                vente__vendor_id=vendor_id,
            )

        # ====================================================
        # 8. CLIENT
        # ====================================================

        client_q = (
            request.query_params.get(
                "client_q", ""
            ) or ""
        ).strip()

        if client_q:
            qs = qs.filter(
                Q(
                    vente__client__nom__icontains=client_q
                )
                | Q(
                    vente__client__prenom__icontains=client_q
                )
                | Q(
                    vente__client__telephone__icontains=client_q
                )
            )

        # ====================================================
        # 9. MODE DE PAIEMENT
        # ====================================================

        payment_mode = (
            request.query_params.get(
                "payment_mode", ""
            ) or ""
        ).strip()

        if payment_mode:
            qs = qs.filter(
                paiements__lignes__mode_paiement__code__iexact=(
                    payment_mode
                )
            ).distinct()

        # ====================================================
        # 10. TRI ET PAGINATION
        # ====================================================

        qs = qs.order_by(
            "-date_creation",
            "-id",
        )

        page = self.parse_positive_int(
            request,
            "page",
            1,
        )

        page_size = min(
            self.parse_positive_int(
                request,
                "page_size",
                self.DEFAULT_PAGE_SIZE,
            ),
            self.MAX_PAGE_SIZE,
        )

        paginator = Paginator(
            qs,
            page_size,
        )

        if paginator.count == 0:
            return Response(
                {
                    "count": 0,
                    "page": 1,
                    "page_size": page_size,
                    "num_pages": 0,
                    "annee": annee,
                    "results": [],
                },
                status=status.HTTP_200_OK,
            )

        try:
            page_obj = paginator.page(page)
        except EmptyPage:
            page_obj = paginator.page(
                paginator.num_pages
            )

        factures = list(
            page_obj.object_list
        )

        # ====================================================
        # 11. PRÉCHARGEMENT APRÈS PAGINATION
        # ====================================================

        produits_qs = (
            VenteProduit.objects
            .select_related(
                "produit_line",
                "produit_line__lot",
                "produit_line__produit",
                "produit_line__produit__categorie",
                "produit_line__produit__marque",
                "produit_line__produit__purete",
                "produit_line__produit__modele",
                "vendor",
                "vendor__user",
            )
        )

        prefetch_related_objects(
            factures,
            "bijouterie",
            "vente__client",
            Prefetch(
                "vente__lignes",
                queryset=produits_qs,
            ),
        )

        # ====================================================
        # 12. AGRÉGATION DES PAIEMENTS DE LA PAGE
        # ====================================================

        facture_ids = [
            facture.pk
            for facture in factures
        ]

        totaux_paiements = {
            facture_id: Decimal("0.00")
            for facture_id in facture_ids
        }

        paiements_groupes = (
            PaiementLigne.objects
            .filter(
                paiement__facture_id__in=facture_ids
            )
            .values(
                "paiement__facture_id"
            )
            .annotate(
                total=Sum(
                    "montant_paye",
                    output_field=DecimalField(
                        max_digits=18,
                        decimal_places=2,
                    ),
                )
            )
        )

        for ligne in paiements_groupes:
            facture_id = ligne[
                "paiement__facture_id"
            ]

            totaux_paiements[facture_id] = (
                ligne["total"]
                or Decimal("0.00")
            )

        # ====================================================
        # 13. SERIALIZATION
        # ====================================================

        serializer = FactureListSerializer(
            factures,
            many=True,
            context={
                "request": request,
                "totaux_paiements": totaux_paiements,
            },
        )

        # ====================================================
        # 14. RÉPONSE ANGULAR
        # ====================================================

        return Response(
            {
                "count": paginator.count,
                "page": page_obj.number,
                "page_size": page_size,
                "num_pages": paginator.num_pages,
                "annee": annee,
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class PaiementFactureMultiModeView(APIView):
    """
    Encaissement multimode d'une facture Rio-Gold.

    - Manager ou caissier autorisé.
    - Vérification de la bijouterie.
    - Paiement partiel ou intégral.
    - Un mode une seule fois par requête.
    - Référence obligatoire selon le mode.
    - Compte dépôt recherché par client.telephone.
    - Client du dépôt récupéré automatiquement.
    - Retrait dépôt et paiement sous transaction.
    - Stock consommé après paiement intégral.
    - Conversion proforma en facture définitive.
    - Génération du hash, QR et PDF.
    """

    permission_classes = [
        IsAuthenticated,
        CanProcessInvoicePayment,
    ]

    @staticmethod
    def _validation_error_detail(exc):
        if hasattr(exc, "message_dict"):
            return exc.message_dict

        if hasattr(exc, "messages"):
            return exc.messages

        if hasattr(exc, "detail"):
            return exc.detail

        return str(exc)

    @swagger_auto_schema(
        operation_summary="Paiement facture multimode",
        operation_description=(
            "Paiement partiel ou intégral d'une facture "
            "par un manager ou un caissier. "
            "Le compte dépôt est recherché avec "
            "client.telephone. "
            "Les références des retraits sont générées "
            "automatiquement. La facture définitive "
            "et la consommation du stock interviennent "
            "après paiement intégral."
        ),
        request_body=PaiementMultiModeSerializer,
        responses={
            201: "Paiement effectué avec succès.",
            400: "Données invalides ou solde insuffisant.",
            403: "Accès refusé.",
            404: "Facture ou compte dépôt introuvable.",
        },
        tags=["Paiements"],
    )
    @transaction.atomic
    def post(self, request):

        # ====================================================
        # 1. AUTORISATION
        # ====================================================

        user = request.user

        role = (
            get_role_name(user) or ""
        ).lower().strip()

        if role not in {
            ROLE_MANAGER,
            ROLE_CASHIER,
        }:
            return error_response(
                code="ROLE_NOT_ALLOWED",
                message=(
                    "Seul le manager ou le caissier "
                    "peut réaliser un paiement."
                ),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # ====================================================
        # 2. VALIDATION DU JSON
        # ====================================================

        serializer = PaiementMultiModeSerializer(
            data=request.data,
            context={"request": request},
        )

        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        numero_facture = data["numero_facture"]
        client_data = data.get("client") or {}
        lignes_data = data["lignes"]

        total_paiement = data["total_paiement"]

        telephone_client = str(
            client_data.get("telephone") or ""
        ).strip()

        # ====================================================
        # 3. VERROUILLAGE DE LA FACTURE
        # ====================================================

        facture = (
            Facture.objects
            .select_for_update()
            .select_related(
                "vente",
                "vente__client",
                "vente__vendor",
                "bijouterie",
            )
            .filter(
                numero_facture__iexact=numero_facture
            )
            .first()
        )

        if facture is None:
            return error_response(
                code="FACTURE_NOT_FOUND",
                message="Facture introuvable.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # ====================================================
        # 4. ACCÈS À LA BIJOUTERIE
        # ====================================================

        if not user_can_access_bijouterie(
            user,
            facture.bijouterie,
        ):
            return error_response(
                code="FACTURE_OUT_OF_SCOPE",
                message=(
                    "Vous n'avez pas accès à la "
                    "bijouterie de cette facture."
                ),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # ====================================================
        # 5. FACTURE PAYABLE
        # ====================================================

        try:
            validate_facture_payable(facture)

        except DjangoValidationError as exc:
            return error_response(
                code="FACTURE_NOT_PAYABLE",
                message=(
                    "Cette facture ne peut pas "
                    "être encaissée."
                ),
                details=self._validation_error_detail(exc),
            )

        if facture.status == Facture.STAT_PAYE:
            return error_response(
                code="FACTURE_ALREADY_PAID",
                message="Cette facture est déjà payée.",
            )

        vente = facture.vente

        if vente is None:
            return error_response(
                code="SALE_NOT_FOUND",
                message="Aucune vente liée à la facture.",
            )

        if vente.bijouterie_id != facture.bijouterie_id:
            return error_response(
                code="SALE_SHOP_MISMATCH",
                message=(
                    "La vente et la facture "
                    "n'appartiennent pas à la "
                    "même bijouterie."
                ),
            )

        if not VenteProduit.objects.filter(
            vente_id=vente.pk
        ).exists():
            return error_response(
                code="SALE_WITHOUT_JEWELRY",
                message=(
                    "Le paiement par facture est réservé "
                    "aux ventes contenant des bijoux."
                ),
            )

        reste_a_payer = Decimal(
            str(facture.reste_a_payer or "0.00")
        )

        if reste_a_payer <= Decimal("0.00"):
            return error_response(
                code="NOTHING_TO_PAY",
                message="Aucun montant ne reste à payer.",
            )

        # ====================================================
        # 6. PROFIL CAISSIER
        # ====================================================

        cashier = None

        if role == ROLE_CASHIER:

            cashier = (
                Cashier.objects
                .select_related("bijouterie", "user")
                .filter(
                    user=user,
                    verifie=True,
                )
                .first()
            )

            if cashier is None:
                return error_response(
                    code="CASHIER_PROFILE_INVALID",
                    message=(
                        "Profil caissier introuvable "
                        "ou désactivé."
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )

            if cashier.bijouterie_id != facture.bijouterie_id:
                return error_response(
                    code="CASHIER_OUT_OF_SCOPE",
                    message=(
                        "Cette facture n'appartient pas "
                        "à la bijouterie du caissier."
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )

        # ====================================================
        # 7. CONTRÔLE DES LIGNES APRÈS VERROUILLAGE
        # ====================================================

        normalized_lignes = []
        modes_utilises = set()
        total_verifie = Decimal("0.00")

        # Recherche et verrouillage du compte dépôt
        # uniquement si une ligne utilise ce mode.
        compte_depot = None

        for index, item in enumerate(
            lignes_data,
            start=1,
        ):

            mode_code = str(
                item["mode"]
            ).lower().strip()

            montant = Decimal(
                str(item["montant"])
            )

            reference = item.get("reference")

            if mode_code in modes_utilises:
                return error_response(
                    code="DUPLICATE_PAYMENT_MODE",
                    message=(
                        f"Le mode '{mode_code}' "
                        "apparaît plusieurs fois."
                    ),
                )

            modes_utilises.add(mode_code)

            mode_obj = (
                ModePaiement.objects
                .filter(
                    code__iexact=mode_code,
                    active=True,
                )
                .first()
            )

            if mode_obj is None:
                return error_response(
                    code="INVALID_PAYMENT_MODE",
                    message=(
                        f"Mode invalide ou inactif : "
                        f"{mode_code}."
                    ),
                )

            if montant <= Decimal("0.00"):
                return error_response(
                    code="INVALID_AMOUNT",
                    message=(
                        f"Montant invalide "
                        f"à la ligne {index}."
                    ),
                )

            # ================================================
            # 7.1. RÉFÉRENCE DES MODES ORDINAIRES
            # ================================================

            if not mode_obj.est_mode_depot:

                if (
                    mode_obj.necessite_reference
                    and not reference
                ):
                    return error_response(
                        code="PAYMENT_REFERENCE_REQUIRED",
                        message=(
                            "Une référence est obligatoire "
                            f"pour le mode '{mode_obj.nom}'."
                        ),
                    )

                compte = None

            # ================================================
            # 7.2. COMPTE DÉPÔT PAR TÉLÉPHONE
            # ================================================

            else:

                if reference:
                    return error_response(
                        code="DEPOT_REFERENCE_NOT_ALLOWED",
                        message=(
                            "La référence du compte dépôt "
                            "est générée automatiquement."
                        ),
                    )

                if not telephone_client:
                    return error_response(
                        code="DEPOT_PHONE_REQUIRED",
                        message=(
                            "Le numéro de téléphone est "
                            "obligatoire pour le compte dépôt."
                        ),
                    )

                if compte_depot is None:

                    comptes = list(
                        CompteDepot.objects
                        .select_for_update()
                        .select_related(
                            "client",
                            "client__bijouterie",
                        )
                        .filter(
                            client__telephone=telephone_client,
                            client__bijouterie_id=(
                                facture.bijouterie_id
                            ),
                        )
                        .order_by("pk")[:2]
                    )

                    if not comptes:
                        return error_response(
                            code="DEPOT_ACCOUNT_NOT_FOUND",
                            message=(
                                "Aucun compte dépôt trouvé "
                                "pour ce numéro de téléphone."
                            ),
                            status_code=(
                                status.HTTP_404_NOT_FOUND
                            ),
                        )

                    if len(comptes) > 1:
                        return error_response(
                            code="DEPOT_ACCOUNT_AMBIGUOUS",
                            message=(
                                "Plusieurs comptes dépôts "
                                "correspondent à ce numéro."
                            ),
                        )

                    compte_depot = comptes[0]

                compte = compte_depot

                if not compte.client_id:
                    return error_response(
                        code="DEPOT_ACCOUNT_WITHOUT_CLIENT",
                        message=(
                            "Le compte dépôt n'est associé "
                            "à aucun client."
                        ),
                    )

                if (
                    compte.client.bijouterie_id
                    != facture.bijouterie_id
                ):
                    return error_response(
                        code="DEPOT_ACCOUNT_OUT_OF_SCOPE",
                        message=(
                            "Le compte dépôt n'appartient "
                            "pas à cette bijouterie."
                        ),
                        status_code=(
                            status.HTTP_403_FORBIDDEN
                        ),
                    )

                solde_disponible = Decimal(
                    str(compte.solde or "0.00")
                )

                if montant > solde_disponible:
                    return error_response(
                        code="SOLDE_COMPTE_DEPOT_INSUFFISANT",
                        message=(
                            "Solde du compte dépôt "
                            "insuffisant."
                        ),
                        details={
                            "solde_disponible": str(
                                solde_disponible
                            ),
                            "montant_demande": str(montant),
                        },
                    )

            total_verifie += montant

            normalized_lignes.append({
                "mode_obj": mode_obj,
                "montant": montant,
                "reference": reference,
                "compte": compte,
            })

        # ====================================================
        # 8. CONTRÔLE DU MONTANT TOTAL
        # ====================================================

        if total_verifie != total_paiement:
            return error_response(
                code="PAYMENT_TOTAL_MISMATCH",
                message=(
                    "Le montant total validé est "
                    "incohérent."
                ),
            )

        if total_paiement > reste_a_payer:
            return error_response(
                code="PAYMENT_EXCEEDS_BALANCE",
                message=(
                    "Le montant reçu dépasse "
                    "le reste à payer."
                ),
                details={
                    "reste_a_payer": str(reste_a_payer),
                    "montant_recu": str(total_paiement),
                    "depassement": str(
                        total_paiement - reste_a_payer
                    ),
                },
            )

        # ====================================================
        # 9. IDENTIFICATION DU CLIENT
        # ====================================================

        client_existant = vente.client

        if compte_depot is not None:

            # Le compte dépôt détermine le titulaire.
            client = compte_depot.client

            if (
                client_existant is not None
                and client_existant.pk != client.pk
            ):
                return error_response(
                    code="DEPOT_CLIENT_MISMATCH",
                    message=(
                        "Le compte dépôt n'appartient pas "
                        "au client de cette vente."
                    ),
                )

            # Vérifier les informations éventuellement
            # transmises en plus du téléphone.

            nom_saisi = str(
                client_data.get("nom") or ""
            ).strip()

            prenom_saisi = str(
                client_data.get("prenom") or ""
            ).strip()

            if nom_saisi and (
                nom_saisi.casefold()
                != str(client.nom or "").strip().casefold()
            ):
                return error_response(
                    code="DEPOT_CLIENT_MISMATCH",
                    message=(
                        "Le nom saisi ne correspond pas "
                        "au titulaire du compte dépôt."
                    ),
                )

            if prenom_saisi and (
                prenom_saisi.casefold()
                != str(client.prenom or "").strip().casefold()
            ):
                return error_response(
                    code="DEPOT_CLIENT_MISMATCH",
                    message=(
                        "Le prénom saisi ne correspond pas "
                        "au titulaire du compte dépôt."
                    ),
                )

        else:

            # Paiement ordinaire :
            # conserver le client existant ou
            # créer/mettre à jour selon le service.

            if client_data:

                try:
                    client = upsert_client_for_payment(
                        facture=facture,
                        client_data=client_data,
                    )

                except DjangoValidationError as exc:
                    transaction.set_rollback(True)

                    return error_response(
                        code="CLIENT_INVALID",
                        message=(
                            "Informations client invalides."
                        ),
                        details=(
                            self._validation_error_detail(exc)
                        ),
                    )

            else:
                client = client_existant

        # ====================================================
        # 9.1. VALIDATION FINALE DU CLIENT
        # ====================================================

        if client is None:
            transaction.set_rollback(True)

            return error_response(
                code="CLIENT_REQUIRED",
                message=(
                    "Le nom et le prénom du client "
                    "sont obligatoires au paiement."
                ),
            )

        if (
            not str(client.nom or "").strip()
            or not str(client.prenom or "").strip()
        ):
            transaction.set_rollback(True)

            return error_response(
                code="CLIENT_INCOMPLETE",
                message=(
                    "Le nom et le prénom du client "
                    "doivent être renseignés."
                ),
            )

        if vente.client_id != client.pk:
            vente.client = client
            vente.save(update_fields=["client"])

        # ====================================================
        # 10. CRÉATION DU PAIEMENT
        # ====================================================

        paiement = Paiement.objects.create(
            facture=facture,
            vente=vente,
            created_by=user,
            cashier=cashier,
        )

        lignes_creees = []

        # ====================================================
        # 11. CRÉATION DES LIGNES ET RETRAITS
        # ====================================================

        for item in normalized_lignes:

            mode_obj = item["mode_obj"]
            montant = item["montant"]
            reference = item["reference"]

            if mode_obj.est_mode_depot:

                compte = item["compte"]

                # Le compte a été verrouillé.
                # Nouvelle lecture avant le retrait.
                compte.refresh_from_db()

                solde_actuel = Decimal(
                    str(compte.solde or "0.00")
                )

                if montant > solde_actuel:
                    transaction.set_rollback(True)

                    return error_response(
                        code="SOLDE_COMPTE_DEPOT_INSUFFISANT",
                        message=(
                            "Le solde du compte dépôt "
                            "est devenu insuffisant."
                        ),
                    )

                # Référence interne unique au paiement.
                reference_retrait = (
                    f"FACTURE-{facture.numero_facture}"
                    f"-PAIEMENT-{paiement.pk}"
                )

                try:
                    tx = effectuer_retrait(
                        compte_id=compte.pk,
                        montant=montant,
                        user=user,
                        reference=reference_retrait,
                        commentaire=(
                            "Paiement de la facture "
                            f"{facture.numero_facture}"
                        ),
                    )

                except DjangoValidationError as exc:
                    transaction.set_rollback(True)

                    return error_response(
                        code="DEPOT_WITHDRAWAL_FAILED",
                        message=(
                            "Le retrait du compte dépôt "
                            "a échoué."
                        ),
                        details=(
                            self._validation_error_detail(exc)
                        ),
                    )

                # Référence automatiquement générée
                # et rattachée au retrait.
                reference_depot = (
                    f"COMPTE_DEPOT-{tx.pk}"
                )

                ligne = PaiementLigne.objects.create(
                    paiement=paiement,
                    mode_paiement=mode_obj,
                    montant_paye=montant,
                    reference=reference_depot,
                    compte_depot=compte,
                    transaction_depot=tx,
                )

                transaction.on_commit(
                    lambda tx=tx: (
                        send_compte_depot_facture_notification(tx)
                    )
                )

            else:

                ligne = PaiementLigne.objects.create(
                    paiement=paiement,
                    mode_paiement=mode_obj,
                    montant_paye=montant,
                    reference=reference,
                )

            lignes_creees.append(ligne)

        # ====================================================
        # 12. RECALCUL DU STATUT DE LA FACTURE
        # ====================================================

        Facture.recompute_facture_status(facture)

        facture.refresh_from_db()

        # ====================================================
        # 13. PROFORMA -> FACTURE DÉFINITIVE
        # ====================================================

        if (
            facture.type_facture == Facture.TYPE_PROFORMA
            and facture.status == Facture.STAT_PAYE
        ):
            facture.type_facture = Facture.TYPE_FACTURE

            facture.save(
                update_fields=["type_facture"]
            )

        # ====================================================
        # 14. CONSOMMATION DU STOCK VENDEUR
        # ====================================================

        audit = {
            "created": 0,
            "already": 0,
            "lines_done": 0,
        }

        if (
            facture.status == Facture.STAT_PAYE
            and not facture.stock_consumed
        ):

            try:
                audit = confirm_sale_out_from_vendor(
                    facture=facture,
                    by_user=user,
                )

                facture.refresh_from_db()

            except DjangoValidationError as exc:
                transaction.set_rollback(True)

                return error_response(
                    code="STOCK_CONSUMPTION_FAILED",
                    message=(
                        "La consommation du stock "
                        "vendeur a échoué."
                    ),
                    details=(
                        self._validation_error_detail(exc)
                    ),
                )

        # ====================================================
        # 15. GÉNÉRATION DE LA FACTURE PDF
        # ====================================================

        facture_pdf_url = None

        if facture.status == Facture.STAT_PAYE:

            if not facture.facture_pdf:

                if not facture.integrity_hash:
                    generate_facture_hash(facture)

                if not facture.qr_code_image:
                    generate_facture_qr(facture)

                generate_facture_pdf(facture)

                facture.refresh_from_db()

                if not facture.facture_pdf:
                    raise APIException(
                        "Erreur lors de la génération "
                        "du PDF de la facture."
                    )

            try:
                facture_pdf_url = (
                    request.build_absolute_uri(
                        facture.facture_pdf.url
                    )
                )

            except (AttributeError, ValueError):
                facture_pdf_url = None

        # ====================================================
        # 16. VERROUILLAGE DE LA FACTURE PAYÉE
        # ====================================================

        if facture.status == Facture.STAT_PAYE:

            if not facture.is_locked:

                facture.is_locked = True
                facture.locked_at = timezone.now()

                facture.save(
                    update_fields=[
                        "is_locked",
                        "locked_at",
                    ]
                )

        # ====================================================
        # 17. URL DE TÉLÉCHARGEMENT
        # ====================================================

        facture_download_url = request.build_absolute_uri(
            reverse(
                "facture-a5-portrait",
                kwargs={
                    "numero_facture": facture.numero_facture,
                },
            )
        )

        # ====================================================
        # 18. RÉPONSE HTTP 201
        # ====================================================

        return Response(
            {
                "status": "success",
                "message": (
                    "Paiement effectué avec succès."
                ),
                "paiement_id": paiement.pk,

                "vente": {
                    "id": vente.pk,
                    "numero_vente": vente.numero_vente,
                    "montant_total": str(
                        vente.montant_total
                    ),
                },

                "facture": {
                    "id": facture.pk,
                    "numero_facture": (
                        facture.numero_facture
                    ),
                    "type_facture": facture.type_facture,
                    "status": facture.status,
                    "montant_total": str(
                        facture.montant_total
                    ),
                    "total_paye": str(
                        facture.total_paye
                    ),
                    "reste_a_payer": str(
                        facture.reste_a_payer
                    ),
                    "stock_consumed": (
                        facture.stock_consumed
                    ),
                },

                "client": {
                    "id": client.pk,
                    "nom": client.nom,
                    "prenom": client.prenom,
                    "telephone": client.telephone,
                },

                "lignes": [
                    {
                        "id": ligne.pk,
                        "mode_paiement": (
                            ligne.mode_paiement.code
                        ),
                        "montant_paye": str(
                            ligne.montant_paye
                        ),
                        "reference": ligne.reference,
                        "provider_reference": (
                            ligne.provider_reference
                        ),
                        "numero_compte": (
                            ligne.compte_depot.numero_compte
                            if ligne.compte_depot_id
                            else None
                        ),
                    }
                    for ligne in lignes_creees
                ],

                "stock": audit,

                "facture_pdf_url": (
                    facture_pdf_url
                ),

                "facture_download_url": (
                    facture_download_url
                ),
            },
            status=status.HTTP_201_CREATED,
        )


# PDF
def _can_access_facture(user, facture: Facture) -> bool:
    """
    Vérifie les droits d'accès à une facture.

    Admin   : toutes les factures.
    Manager : factures de ses bijouteries.
    Cashier : factures de sa bijouterie.
    Vendor  : factures de ses propres ventes.
    """

    if not user or not getattr(
        user, "is_authenticated", False
    ):
        return False

    if not facture or not facture.bijouterie_id:
        return False

    role = (
        get_role_name(user) or ""
    ).lower().strip()

    # =====================================================
    # ADMIN
    # =====================================================

    if role == ROLE_ADMIN:
        return True

    # =====================================================
    # MANAGER
    # =====================================================

    if role == ROLE_MANAGER:

        manager_profile = getattr(
            user,
            "staff_manager_profile",
            None,
        )

        if not (
            manager_profile
            and getattr(
                manager_profile, "verifie", False
            )
        ):
            return False

        return (
            manager_profile.bijouteries
            .filter(id=facture.bijouterie_id)
            .exists()
        )

    # =====================================================
    # CASHIER
    # =====================================================

    if role == ROLE_CASHIER:

        cashier_profile = getattr(
            user,
            "staff_cashier_profile",
            None,
        )

        if not (
            cashier_profile
            and getattr(
                cashier_profile, "verifie", False
            )
        ):
            return False

        return (
            cashier_profile.bijouterie_id
            == facture.bijouterie_id
        )

    # =====================================================
    # VENDOR
    # =====================================================

    if role == ROLE_VENDOR:

        vendor_profile = getattr(
            user,
            "staff_vendor_profile",
            None,
        )

        if not (
            vendor_profile
            and getattr(
                vendor_profile, "verifie", False
            )
            and vendor_profile.bijouterie_id
        ):
            return False

        vente = getattr(
            facture,
            "vente",
            None,
        )

        if not vente:
            return False

        if vente.bijouterie_id != facture.bijouterie_id:
            return False

        if (
            vendor_profile.bijouterie_id
            != facture.bijouterie_id
        ):
            return False

        return vente.vendor_id == vendor_profile.id

    return False


class TicketProforma58mmView(APIView):
    """
    Génère un ticket PROFORMA ESC/POS 58 mm.

    Conditions :
    - Facture existante.
    - Utilisateur authentifié et autorisé.
    - Vente associée.
    - Vente contenant au moins un bijou.
    - Facture de type PROFORMA.
    - Bijouterie associée.

    Modes :
    - Normal : fichier .bin pour imprimante POS.
    - debug=1 : aperçu texte.

    Règles Rio-Gold :
    - Bijoux seuls : autorisé.
    - Bijoux + prestations : autorisé.
    - Prestations seules : interdit.
    - Facture définitive : interdit.
    """

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary=(
            "Télécharger le ticket PROFORMA 58 mm pour POS"
        ),
        operation_description=(
            "Génère un ticket PROFORMA au format ESC/POS 58 mm.\n\n"
            "Règles :\n"
            "- Bijoux uniquement : autorisé.\n"
            "- Bijoux + prestations : autorisé.\n"
            "- Prestations uniquement : interdit.\n"
            "- Facture définitive : interdit.\n\n"
            "Sans debug : fichier binaire ESC/POS.\n"
            "Avec ?debug=1 : aperçu texte lisible."
        ),
        manual_parameters=[
            openapi.Parameter(
                name="numero_facture",
                in_=openapi.IN_PATH,
                description="Numéro de la facture proforma.",
                type=openapi.TYPE_STRING,
                required=True,
                example="FAC-20260509-0001",
            ),
            openapi.Parameter(
                name="debug",
                in_=openapi.IN_QUERY,
                description=(
                    "Mettre 1 pour afficher le ticket "
                    "en texte lisible."
                ),
                type=openapi.TYPE_STRING,
                required=False,
                example="1",
            ),
        ],
        responses={
            200: openapi.Response(
                description=(
                    "Ticket PROFORMA généré avec succès."
                )
            ),
            400: "Facture ou vente non éligible.",
            403: "Accès refusé.",
            404: "Facture introuvable.",
            500: "Erreur lors de la génération du ticket.",
        },
        tags=["Tickets POS"],
    )
    def get(
        self,
        request,
        numero_facture: str,
    ):

        # =====================================================
        # 1. RECHERCHE DE LA FACTURE
        # =====================================================

        facture = (
            Facture.objects
            .select_related(
                "vente",
                "vente__client",
                "vente__vendor",
                "bijouterie",
            )
            .filter(
                numero_facture__iexact=numero_facture
            )
            .first()
        )

        if facture is None:
            return error_response(
                code="FACTURE_NOT_FOUND",
                message=(
                    f"Facture introuvable : {numero_facture}."
                ),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # =====================================================
        # 2. CONTRÔLE DES PERMISSIONS
        # =====================================================

        if not _can_access_facture(
            request.user,
            facture,
        ):
            return error_response(
                code="FACTURE_ACCESS_DENIED",
                message="Accès refusé à cette facture.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # 3. VÉRIFICATION DE LA VENTE
        # =====================================================

        if not facture.vente_id:
            return error_response(
                code="FACTURE_WITHOUT_SALE",
                message=(
                    "Aucune vente associée à cette facture."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        vente = facture.vente

        # =====================================================
        # 4. VÉRIFICATION DES BIJOUX
        # =====================================================

        if not vente.lignes.exists():
            return error_response(
                code="SALE_WITHOUT_JEWELRY",
                message=(
                    "Cette vente ne contient aucun bijou. "
                    "Le ticket proforma est interdit pour "
                    "les ventes composées uniquement de "
                    "prestations. Utilisez le reçu de paiement."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 5. TYPE DE FACTURE
        # =====================================================

        if facture.type_facture != Facture.TYPE_PROFORMA:
            return error_response(
                code="FACTURE_NOT_PROFORMA",
                message=(
                    "Cette facture n'est pas une proforma. "
                    "Le ticket proforma ne peut pas être généré."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 6. BIJOUTERIE
        # =====================================================

        bijouterie = facture.bijouterie

        if bijouterie is None:
            return error_response(
                code="FACTURE_WITHOUT_STORE",
                message=(
                    "Aucune bijouterie n'est associée "
                    "à cette facture."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        shop_name = (
            getattr(bijouterie, "nom", None)
            or "BIJOUTERIE RIO-GOLD"
        )

        shop_phone = (
            getattr(
                bijouterie,
                "telephone_portable_1",
                None,
            )
            or getattr(
                bijouterie,
                "telephone_portable_2",
                None,
            )
            or getattr(
                bijouterie,
                "telephone_fix",
                None,
            )
            or ""
        )

        # =====================================================
        # 7. DATE LOCALE
        # =====================================================

        date_creation = facture.date_creation

        if date_creation:

            if timezone.is_aware(date_creation):
                date_creation = timezone.localtime(
                    date_creation
                )

            date_txt = date_creation.strftime(
                "%d/%m/%Y %H:%M"
            )

            date_day_txt = date_creation.strftime(
                "%d/%m/%Y"
            )

            time_txt = date_creation.strftime(
                "%H:%M"
            )

        else:
            date_txt = ""
            date_day_txt = ""
            time_txt = ""

        # =====================================================
        # 8. STATUT DE LA FACTURE
        # =====================================================

        if facture.status == Facture.STAT_NON_PAYE:
            statut_txt = "NON PAYE"

        elif facture.status == Facture.STAT_PARTIEL:
            statut_txt = "PARTIEL"

        elif facture.status == Facture.STAT_PAYE:
            statut_txt = "PAYE"

        else:
            statut_txt = str(
                facture.status or ""
            ).upper()

        # =====================================================
        # 9. MONTANT RESTANT À PAYER
        # =====================================================

        montant_a_payer = Decimal(
            str(
                facture.reste_a_payer
                if facture.reste_a_payer is not None
                else "0.00"
            )
        )

        if not montant_a_payer.is_finite():
            return error_response(
                code="INVALID_INVOICE_BALANCE",
                message=(
                    "Le montant restant à payer "
                    "de cette facture est invalide."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if montant_a_payer < Decimal("0.00"):
            return error_response(
                code="INVALID_INVOICE_BALANCE",
                message=(
                    "Le montant restant à payer "
                    "ne peut pas être négatif."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 10. MODE DEBUG
        # =====================================================

        if request.query_params.get("debug") == "1":

            separator = "-" * 32

            debug_text = (
                f"{shop_name.upper()}\n"
            )

            if shop_phone:
                debug_text += (
                    f"Tel: {shop_phone}\n"
                )

            debug_text += (
                f"{separator}\n"
                f"FACTURE PROFORMA\n"
                f"N° {facture.numero_facture}\n"
                f"{separator}\n"
                f"DATE : {date_day_txt} {time_txt}\n"
                f"ETAT : {statut_txt}\n"
                f"{separator}\n"
                f"MONTANT A PAYER\n"
                f"{montant_a_payer:.2f} FCFA\n"
                f"{separator}\n"
                f"Ticket PROFORMA\n"
                f"A regler en caisse.\n"
                f"Merci pour votre confiance !\n"
            )

            response = HttpResponse(
                debug_text,
                content_type="text/plain; charset=utf-8",
            )

            response["Cache-Control"] = "no-store"

            response["X-Content-Type-Options"] = "nosniff"

            return response

        # =====================================================
        # 11. GÉNÉRATION DU TICKET ESC/POS
        # =====================================================

        try:
            escpos_bytes = (
                build_escpos_ticket_proforma_58mm(
                    shop_name=shop_name,
                    shop_phone=shop_phone,
                    numero_facture=facture.numero_facture,
                    date_txt=date_txt,
                    montant_a_payer=montant_a_payer,
                    statut_txt=statut_txt,
                    note=(
                        "Ticket PROFORMA "
                        "a regler en caisse."
                    ),
                )
            )

        except Exception:
            logger.exception(
                "Erreur de génération du ticket "
                "proforma ESC/POS 58 mm. "
                "Facture=%s",
                facture.numero_facture,
            )

            return error_response(
                code="PROFORMA_TICKET_GENERATION_FAILED",
                message=(
                    "Erreur lors de la génération "
                    "du ticket proforma."
                ),
                status_code=(
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
            )

        # =====================================================
        # 12. VALIDATION DU TICKET GÉNÉRÉ
        # =====================================================

        if not isinstance(
            escpos_bytes,
            (bytes, bytearray),
        ):
            logger.error(
                "Ticket ESC/POS non binaire. "
                "Facture=%s",
                facture.numero_facture,
            )

            return error_response(
                code="INVALID_PROFORMA_TICKET",
                message=(
                    "Le ticket proforma généré "
                    "n'est pas au format binaire."
                ),
                status_code=(
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
            )

        if not escpos_bytes:
            logger.error(
                "Ticket ESC/POS vide. Facture=%s",
                facture.numero_facture,
            )

            return error_response(
                code="EMPTY_PROFORMA_TICKET",
                message=(
                    "Le ticket proforma généré est vide."
                ),
                status_code=(
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
            )

        # =====================================================
        # 13. NOM DU FICHIER
        # =====================================================

        safe_numero_facture = get_valid_filename(
            str(facture.numero_facture)
        )

        filename = (
            f"ticket_proforma_"
            f"{safe_numero_facture}.bin"
        )

        # =====================================================
        # 14. RÉPONSE POUR IMPRIMANTE POS
        # =====================================================

        response = HttpResponse(
            bytes(escpos_bytes),
            content_type="application/octet-stream",
        )

        response["Content-Disposition"] = (
            f'inline; filename="{filename}"'
        )

        response["Content-Length"] = str(
            len(escpos_bytes)
        )

        response["Cache-Control"] = "no-store"

        response["X-Content-Type-Options"] = "nosniff"

        return response


class TicketPaiement80mmESCPosView(APIView):
    """
    Génère un reçu de paiement ESC/POS 80 mm.

    Règles :
    - Facture existante.
    - Utilisateur autorisé.
    - Vente contenant au moins un bijou.
    - Dernier paiement enregistré.
    - Paiement partiel ou complet accepté.
    - Montant du dernier paiement uniquement.
    - Reste à payer actuel de la facture.
    - Aucune modification financière ou de stock.

    Modes :
    - Normal : fichier .bin ESC/POS.
    - debug=1 : aperçu texte.

    Les ventes contenant uniquement des prestations
    utilisent le reçu de paiement direct, sans facture.
    """

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary=(
            "Télécharger le reçu de paiement ESC/POS 80 mm"
        ),
        operation_description=(
            "Génère le reçu du dernier paiement enregistré "
            "sur une facture.\n\n"
            "Règles :\n"
            "- Bijoux seuls ou bijoux + prestations.\n"
            "- Paiements partiels acceptés.\n"
            "- Paiements complets acceptés.\n"
            "- Montant du dernier paiement uniquement.\n"
            "- Reste à payer actuel de la facture.\n"
            "- Prestations seules : reçu direct sans facture.\n\n"
            "Sans debug : fichier ESC/POS .bin.\n"
            "Avec ?debug=1 : aperçu texte.\n\n"
            "Aucune modification financière ou de stock."
        ),
        manual_parameters=[
            openapi.Parameter(
                name="numero_facture",
                in_=openapi.IN_PATH,
                description="Numéro de la facture.",
                type=openapi.TYPE_STRING,
                required=True,
                example="FAC-20260509-0001",
            ),
            openapi.Parameter(
                name="debug",
                in_=openapi.IN_QUERY,
                description=(
                    "Mettre 1 pour afficher le reçu "
                    "en texte lisible."
                ),
                type=openapi.TYPE_STRING,
                required=False,
                example="1",
            ),
        ],
        responses={
            200: openapi.Response(
                description="Reçu de paiement généré."
            ),
            400: "Facture ou paiement non éligible.",
            403: "Accès refusé.",
            404: "Facture introuvable.",
            500: "Erreur de génération du ticket.",
        },
        tags=["Tickets POS"],
    )
    def get(
        self,
        request,
        numero_facture: str,
    ):

        # =====================================================
        # 1. RECHERCHE DE LA FACTURE
        # =====================================================

        facture = (
            Facture.objects
            .select_related(
                "vente",
                "vente__client",
                "vente__vendor",
                "bijouterie",
            )
            .filter(
                numero_facture__iexact=numero_facture
            )
            .first()
        )

        if facture is None:
            return error_response(
                code="FACTURE_NOT_FOUND",
                message=(
                    f"Facture introuvable : {numero_facture}."
                ),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # =====================================================
        # 2. CONTRÔLE DES PERMISSIONS
        # =====================================================

        if not _can_access_facture(
            request.user,
            facture,
        ):
            return error_response(
                code="FACTURE_ACCESS_DENIED",
                message="Accès refusé à cette facture.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # 3. VÉRIFICATION DE LA VENTE
        # =====================================================

        if not facture.vente_id:
            return error_response(
                code="FACTURE_WITHOUT_SALE",
                message=(
                    "Aucune vente n'est associée "
                    "à cette facture."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        vente = facture.vente

        if not vente.lignes.exists():
            return error_response(
                code="SALE_WITHOUT_JEWELRY",
                message=(
                    "Cette vente ne contient aucun bijou. "
                    "Les ventes de prestations seules "
                    "utilisent un reçu de paiement direct."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 4. COHÉRENCE BIJOUTERIE
        # =====================================================

        if (
            not facture.bijouterie_id
            or vente.bijouterie_id != facture.bijouterie_id
        ):
            return error_response(
                code="INVOICE_STORE_MISMATCH",
                message=(
                    "La bijouterie de la facture "
                    "est absente ou incohérente."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        bijouterie = facture.bijouterie

        shop_name = (
            getattr(bijouterie, "nom", None)
            or "RIO-GOLD"
        )

        shop_phone = (
            getattr(
                bijouterie,
                "telephone_portable_1",
                None,
            )
            or getattr(
                bijouterie,
                "telephone_portable_2",
                None,
            )
            or getattr(
                bijouterie,
                "telephone_fix",
                None,
            )
            or ""
        )

        # =====================================================
        # 5. DERNIER PAIEMENT
        # =====================================================

        paiement = (
            Paiement.objects
            .filter(
                facture_id=facture.pk,
            )
            .select_related(
                "facture",
                "cashier",
                "cashier__user",
                "created_by",
            )
            .prefetch_related(
                "lignes",
                "lignes__mode_paiement",
            )
            .order_by(
                "-date_paiement",
                "-id",
            )
            .first()
        )

        if paiement is None:
            return error_response(
                code="PAYMENT_NOT_FOUND",
                message=(
                    "Aucun paiement enregistré "
                    "pour cette facture."
                ),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # =====================================================
        # 6. MONTANT DU DERNIER PAIEMENT
        # =====================================================

        montant_paye = (
            paiement.lignes.aggregate(
                total=Sum("montant_paye")
            )["total"]
            or Decimal("0.00")
        )

        montant_paye = Decimal(
            str(montant_paye)
        )

        if (
            not montant_paye.is_finite()
            or montant_paye <= Decimal("0.00")
        ):
            return error_response(
                code="PAYMENT_WITHOUT_AMOUNT",
                message=(
                    "Le dernier paiement ne contient "
                    "aucun montant valide."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 7. RESTE À PAYER ACTUEL
        # =====================================================

        try:
            reste_a_payer = Decimal(
                str(
                    facture.reste_a_payer
                    if facture.reste_a_payer is not None
                    else "0.00"
                )
            )

        except (ValueError, TypeError, ArithmeticError):
            return error_response(
                code="INVALID_INVOICE_BALANCE",
                message=(
                    "Le solde de la facture est invalide."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if (
            not reste_a_payer.is_finite()
            or reste_a_payer < Decimal("0.00")
        ):
            return error_response(
                code="INVALID_INVOICE_BALANCE",
                message=(
                    "Le solde de la facture est invalide."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 8. MODE DEBUG
        # =====================================================

        if request.query_params.get("debug") == "1":

            date_paiement = paiement.date_paiement

            if (
                date_paiement
                and timezone.is_aware(date_paiement)
            ):
                date_paiement = timezone.localtime(
                    date_paiement
                )

            date_txt = (
                date_paiement.strftime("%d/%m/%Y %H:%M")
                if date_paiement
                else ""
            )

            separator = "-" * 42

            debug_text = (
                f"{shop_name}\n"
                f"Tel : {shop_phone}\n"
                f"{separator}\n"
                f"RECU DE PAIEMENT\n"
                f"Facture : {facture.numero_facture}\n"
                f"Paiement ID : {paiement.pk}\n"
                f"Date : {date_txt}\n"
                f"{separator}\n"
                f"Montant recu : {montant_paye:.2f} FCFA\n"
                f"Reste a payer : {reste_a_payer:.2f} FCFA\n"
                f"{separator}\n"
                f"Merci pour votre confiance !\n"
            )

            response = HttpResponse(
                debug_text,
                content_type="text/plain; charset=utf-8",
            )

            response["Cache-Control"] = "no-store"
            response["X-Content-Type-Options"] = "nosniff"

            return response

        # =====================================================
        # 9. GÉNÉRATION ESC/POS 80 MM
        # =====================================================

        try:
            escpos_bytes = build_escpos_recu_paiement_80mm(
                shop_name=shop_name,
                shop_phone=shop_phone,
                numero_facture=facture.numero_facture,
                date_paiement=paiement.date_paiement,
                montant_paye=montant_paye,
                reste_a_payer=reste_a_payer,
            )

        except Exception:
            logger.exception(
                "Erreur génération reçu ESC/POS 80 mm. "
                "Facture=%s Paiement=%s",
                facture.numero_facture,
                paiement.pk,
            )

            return error_response(
                code="PAYMENT_TICKET_GENERATION_FAILED",
                message=(
                    "Erreur lors de la génération "
                    "du ticket de paiement."
                ),
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # =====================================================
        # 10. VALIDATION DU FICHIER ESC/POS
        # =====================================================

        if not isinstance(
            escpos_bytes,
            (bytes, bytearray),
        ):
            logger.error(
                "Reçu ESC/POS non binaire. Paiement=%s",
                paiement.pk,
            )

            return error_response(
                code="INVALID_PAYMENT_TICKET",
                message=(
                    "Le ticket généré n'est pas "
                    "au format binaire."
                ),
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not escpos_bytes:
            return error_response(
                code="EMPTY_PAYMENT_TICKET",
                message="Le ticket de paiement généré est vide.",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # =====================================================
        # 11. NOM DU FICHIER
        # =====================================================

        safe_numero = get_valid_filename(
            str(facture.numero_facture)
        )

        filename = (
            f"ticket_paiement_{safe_numero}_"
            f"{paiement.pk}.bin"
        )

        # =====================================================
        # 12. RÉPONSE ESC/POS
        # =====================================================

        response = HttpResponse(
            bytes(escpos_bytes),
            content_type="application/octet-stream",
        )

        response["Content-Disposition"] = (
            f'inline; filename="{filename}"'
        )

        response["Content-Length"] = str(
            len(escpos_bytes)
        )

        response["Cache-Control"] = "no-store"
        response["X-Content-Type-Options"] = "nosniff"

        return response
    

class FactureA5PortraitView(APIView):
    """
    Téléchargement d'une facture PDF A5 portrait.

    Format :
    - A5 portrait : 148 x 210 mm.

    Règles métier Rio-Gold :
    - Bijoux uniquement : autorisé.
    - Bijoux + prestations : autorisé.
    - Prestations uniquement : interdit.
    - Facture proforma : autorisée.
    - Facture définitive : autorisée.

    Les montants sont fournis par :
    build_facture_pdf_data(facture).

    Cette vue ne modifie aucune donnée métier :
    - Aucun paiement.
    - Aucun mouvement de stock.
    - Aucune modification de facture.
    """

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary=(
            "Télécharger une facture PDF A5 portrait"
        ),
        operation_description="""
Télécharge une facture au format PDF A5 portrait.

Règles métier :

- Bijoux uniquement : autorisé.
- Bijoux + prestations : autorisé.
- Prestations uniquement : interdit.
- Facture proforma : autorisée.
- Facture définitive : autorisée.
- L'utilisateur doit avoir accès à la facture.

Les montants sont calculés par build_facture_pdf_data.

Aucune modification financière ou de stock.
        """,
        responses={
            200: openapi.Response(
                description=(
                    "Facture PDF A5 portrait générée avec succès."
                )
            ),
            400: "Facture ou vente non éligible.",
            403: "Accès refusé.",
            404: "Facture introuvable.",
            500: "Erreur lors de la génération PDF.",
        },
        tags=["Factures"],
    )
    def get(
        self,
        request,
        numero_facture: str,
    ):

        # =====================================================
        # 1. RECHERCHE DE LA FACTURE
        # =====================================================

        facture = (
            Facture.objects
            .select_related(
                "vente",
                "vente__client",
                "vente__vendor",
                "vente__vendor__user",
                "bijouterie",
            )
            .prefetch_related(
                # ---------------------------------------------
                # Bijoux
                # ---------------------------------------------
                "vente__lignes",

                # ProduitLine : source de vérité
                "vente__lignes__produit_line",
                "vente__lignes__produit_line__lot",

                # Produit associé à ProduitLine
                "vente__lignes__produit_line__produit",
                "vente__lignes__produit_line__produit__purete",
                "vente__lignes__produit_line__produit__marque",
                "vente__lignes__produit_line__produit__categorie",
                "vente__lignes__produit_line__produit__modele",

                # ---------------------------------------------
                # Prestations
                # ---------------------------------------------
                "vente__autres",

                # ---------------------------------------------
                # Paiements
                # ---------------------------------------------
                "paiements",
                "paiements__lignes",
                "paiements__lignes__mode_paiement",
            )
            .filter(
                numero_facture__iexact=numero_facture,
            )
            .first()
        )

        # =====================================================
        # 2. FACTURE INTROUVABLE
        # =====================================================

        if facture is None:
            return error_response(
                code="FACTURE_NOT_FOUND",
                message=(
                    f"Facture introuvable : "
                    f"{numero_facture}."
                ),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # =====================================================
        # 3. PERMISSION
        # =====================================================

        if not _can_access_facture(
            request.user,
            facture,
        ):
            return error_response(
                code="FACTURE_ACCESS_DENIED",
                message="Accès refusé à cette facture.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # 4. VENTE ASSOCIÉE
        # =====================================================

        if not facture.vente_id:
            return error_response(
                code="FACTURE_WITHOUT_SALE",
                message=(
                    "Aucune vente n'est associée "
                    "à cette facture."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        vente = facture.vente

        # =====================================================
        # 5. VÉRIFICATION DES BIJOUX
        # =====================================================

        # Les factures sont réservées aux ventes
        # contenant au moins un bijou.
        #
        # Les ventes uniquement composées de prestations
        # doivent produire un reçu de paiement.

        if not vente.lignes.exists():
            return error_response(
                code="SALE_WITHOUT_JEWELRY",
                message=(
                    "Impossible de générer une facture PDF : "
                    "cette vente ne contient aucun bijou. "
                    "Les ventes composées uniquement de "
                    "prestations doivent utiliser un reçu "
                    "de paiement."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 6. COHÉRENCE BIJOUTERIE
        # =====================================================

        if not facture.bijouterie_id:
            return error_response(
                code="FACTURE_WITHOUT_STORE",
                message=(
                    "Aucune bijouterie n'est associée "
                    "à cette facture."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if (
            vente.bijouterie_id
            != facture.bijouterie_id
        ):
            return error_response(
                code="INVOICE_STORE_MISMATCH",
                message=(
                    "La bijouterie de la vente ne correspond "
                    "pas à celle de la facture."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 7. TYPE DE FACTURE
        # =====================================================

        if facture.type_facture not in (
            Facture.TYPE_PROFORMA,
            Facture.TYPE_FACTURE,
        ):
            return error_response(
                code="INVALID_INVOICE_TYPE",
                message=(
                    "Seules les factures proforma "
                    "et définitives sont autorisées."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 8. PRÉPARATION DES DONNÉES PDF
        # =====================================================

        try:
            data = build_facture_pdf_data(
                facture
            )

        except ValueError as exc:
            logger.warning(
                "Données PDF invalides. Facture=%s : %s",
                facture.numero_facture,
                exc,
            )

            return error_response(
                code="FACTURE_PDF_DATA_INVALID",
                message=str(exc),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        except Exception:
            logger.exception(
                "Erreur de préparation des données PDF. "
                "Facture=%s",
                facture.numero_facture,
            )

            return error_response(
                code="FACTURE_PDF_DATA_FAILED",
                message=(
                    "Erreur lors de la préparation "
                    "des données de la facture."
                ),
                status_code=(
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
            )

        # =====================================================
        # 9. GÉNÉRATION PDF A5 PORTRAIT
        # =====================================================

        buffer = BytesIO()

        try:
            build_facture_a5_portrait_pdf(
                buffer,
                data,
            )

            # Vérifier qu'un PDF a été généré.
            if buffer.tell() == 0:
                raise ValueError(
                    "Le générateur a retourné un PDF vide."
                )

            buffer.seek(0)

            # Vérifier la signature PDF.
            if buffer.read(5) != b"%PDF-":
                raise ValueError(
                    "Le fichier généré n'est pas un PDF valide."
                )

            buffer.seek(0)

        except Exception:
            buffer.close()

            logger.exception(
                "Erreur de génération du PDF A5 portrait. "
                "Facture=%s",
                facture.numero_facture,
            )

            return error_response(
                code="FACTURE_PDF_GENERATION_FAILED",
                message=(
                    "Erreur lors de la génération "
                    "du PDF de la facture."
                ),
                status_code=(
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
            )

        # =====================================================
        # 10. NOM DU FICHIER
        # =====================================================

        safe_numero = get_valid_filename(
            str(facture.numero_facture)
        )

        if facture.type_facture == Facture.TYPE_PROFORMA:
            filename = (
                f"proforma_{safe_numero}.pdf"
            )
        else:
            filename = (
                f"facture_{safe_numero}.pdf"
            )

        # =====================================================
        # 11. RÉPONSE PDF
        # =====================================================

        response = FileResponse(
            buffer,
            as_attachment=True,
            filename=filename,
            content_type="application/pdf",
        )

        response["Cache-Control"] = "no-store"
        response["X-Content-Type-Options"] = "nosniff"

        return response

class ExportFacturesExcelView(APIView):
    """
    Export Excel des factures.

    Règles :
    - Admin : factures de son scope.
    - Manager : factures de ses bijouteries.
    - Vendor : factures de ses propres ventes.
    - Cashier : factures de sa bijouterie.

    Factures éligibles :
    - Bijoux uniquement.
    - Bijoux + prestations.

    Les ventes avec prestations uniquement
    sont exclues de l'export des factures.

    Aucun changement de stock, de paiement
    ou de données financières.
    """

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Exporter les factures en Excel",
        operation_description="""
Exporte les factures accessibles à l'utilisateur connecté.

Rôles autorisés :
- admin
- manager
- vendor
- cashier

Règles :
- Le scope bijouterie est appliqué.
- Le vendeur ne peut exporter que ses propres factures.
- Les factures de ventes contenant des bijoux sont incluses.
- Les ventes mixtes (bijoux + prestations) sont incluses.
- Les ventes avec prestations uniquement sont exclues.

L'export ne modifie aucune donnée métier.
        """,
        responses={
            200: openapi.Response(
                description="Fichier Excel généré avec succès."
            ),
            403: "Accès refusé.",
            500: "Erreur de génération Excel.",
        },
        tags=["Factures"],
    )
    def get(self, request):

        # =====================================================
        # 1. UTILISATEUR ET RÔLE
        # =====================================================

        user = request.user

        role = (
            get_role_name(user) or ""
        ).lower().strip()

        allowed_roles = {
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_VENDOR,
            ROLE_CASHIER,
        }

        if role not in allowed_roles:
            return error_response(
                code="FACTURE_EXPORT_ACCESS_DENIED",
                message=(
                    "Vous n'êtes pas autorisé "
                    "à exporter les factures."
                ),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # 2. QUERYSET DE BASE
        # =====================================================

        # Le générateur Excel existant travaille
        # sur les informations de facture et de vente.
        #
        # Aucun prefetch ProduitLine n'est nécessaire
        # si export_factures_excel() ne parcourt pas
        # les détails des produits.

        factures = (
            Facture.objects
            .select_related(
                "vente",
                "vente__client",
                "vente__vendor",
                "vente__vendor__user",
                "bijouterie",
            )
            .filter(
                # Exclure les factures sans vente.
                vente__isnull=False,

                # La vente doit contenir au moins un bijou.
                vente__lignes__isnull=False,
            )
            .distinct()
        )

        # =====================================================
        # 3. SCOPE BIJOUTERIE
        # =====================================================

        factures = factures.filter(
            scope_bijouterie_q(
                user,
                field="bijouterie_id",
            )
        )

        # =====================================================
        # 4. SCOPE VENDEUR
        # =====================================================

        if role == ROLE_VENDOR:

            vendor = getattr(
                user,
                "staff_vendor_profile",
                None,
            )

            if not vendor:
                return error_response(
                    code="VENDOR_PROFILE_NOT_FOUND",
                    message="Profil vendeur introuvable.",
                    status_code=status.HTTP_403_FORBIDDEN,
                )

            if not getattr(
                vendor,
                "verifie",
                False,
            ):
                return error_response(
                    code="VENDOR_NOT_VERIFIED",
                    message=(
                        "Le profil vendeur est désactivé "
                        "ou non vérifié."
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )

            if not vendor.bijouterie_id:
                return error_response(
                    code="VENDOR_WITHOUT_STORE",
                    message=(
                        "Le vendeur n'est rattaché "
                        "à aucune bijouterie."
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )

            # Le vendeur ne peut exporter que les
            # factures de ses propres ventes.
            factures = factures.filter(
                vente__vendor_id=vendor.id,
            )

        # =====================================================
        # 5. TRI
        # =====================================================

        factures = factures.order_by(
            "-date_creation",
            "-id",
        )

        # =====================================================
        # 6. EXPORT EXCEL
        # =====================================================

        try:
            return export_factures_excel(
                factures
            )

        except Exception:
            return error_response(
                code="FACTURE_EXCEL_EXPORT_FAILED",
                message=(
                    "Une erreur est survenue lors "
                    "de la génération du fichier Excel."
                ),
                status_code=(
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
            )

class ExportComptableView(APIView):
    """
    Export comptable Excel des factures entièrement payées.

    Règles :
    - Admin : factures accessibles selon son scope.
    - Manager : factures de ses bijouteries.
    - Cashier : factures de sa bijouterie.
    - Vendor : factures de ses propres ventes.

    Factures éligibles :
    - Ventes de bijoux.
    - Ventes mixtes : bijoux + prestations.

    Les ventes composées uniquement de prestations
    ne sont pas incluses dans cet export de factures.

    Aucun impact sur :
    - Stock
    - InventoryMovement
    - Paiement
    - Facture
    """

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Exporter les données comptables en Excel",
        operation_description="""
Exporte les données comptables des factures entièrement payées.

Règles :
- Seules les factures avec status=PAYE sont incluses.
- Les ventes contenant au moins un bijou sont éligibles.
- Les ventes mixtes (bijoux + prestations) sont autorisées.
- Les ventes avec prestations uniquement sont exclues.
- Le scope bijouterie est appliqué.
- Le vendeur ne peut exporter que ses propres factures.

L'export utilise le service export_comptable_factures().
Aucune donnée métier n'est modifiée.
        """,
        responses={
            200: openapi.Response(
                description="Fichier Excel comptable généré."
            ),
            403: "Accès refusé.",
            500: "Erreur de génération de l'export.",
        },
        tags=["Comptabilité"],
    )
    def get(self, request):

        # =====================================================
        # 1. UTILISATEUR ET RÔLE
        # =====================================================

        user = request.user

        role = (
            get_role_name(user) or ""
        ).lower().strip()

        allowed_roles = {
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_CASHIER,
            ROLE_VENDOR,
        }

        if role not in allowed_roles:
            return error_response(
                code="ACCOUNTING_EXPORT_ACCESS_DENIED",
                message=(
                    "Vous n'êtes pas autorisé "
                    "à exporter les données comptables."
                ),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # 2. QUERYSET DES FACTURES PAYÉES
        # =====================================================

        factures = (
            Facture.objects
            .filter(
                status=Facture.STAT_PAYE,

                # La facture doit avoir une vente.
                vente__isnull=False,

                # Au moins une ligne de bijou.
                vente__lignes__isnull=False,
            )
            .select_related(
                "bijouterie",
                "vente",
                "vente__client",
                "vente__vendor",
                "vente__vendor__user",
            )
            .prefetch_related(
                # Paiements
                "paiements",
                "paiements__lignes",
                "paiements__lignes__mode_paiement",
            )
            .distinct()
        )

        # =====================================================
        # 3. SCOPE BIJOUTERIE
        # =====================================================

        factures = factures.filter(
            scope_bijouterie_q(
                user,
                field="bijouterie_id",
            )
        )

        # =====================================================
        # 4. SCOPE VENDEUR
        # =====================================================

        if role == ROLE_VENDOR:

            vendor = getattr(
                user,
                "staff_vendor_profile",
                None,
            )

            if not vendor:
                return error_response(
                    code="VENDOR_PROFILE_NOT_FOUND",
                    message="Profil vendeur introuvable.",
                    status_code=status.HTTP_403_FORBIDDEN,
                )

            if not getattr(
                vendor,
                "verifie",
                False,
            ):
                return error_response(
                    code="VENDOR_NOT_VERIFIED",
                    message=(
                        "Le profil vendeur est désactivé "
                        "ou non vérifié."
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )

            if not vendor.bijouterie_id:
                return error_response(
                    code="VENDOR_WITHOUT_STORE",
                    message=(
                        "Le vendeur n'est rattaché "
                        "à aucune bijouterie."
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )

            factures = factures.filter(
                vente__vendor_id=vendor.id,
            )

        # =====================================================
        # 5. TRI
        # =====================================================

        factures = factures.order_by(
            "-date_creation",
            "-id",
        )

        # =====================================================
        # 6. GÉNÉRATION DU WORKBOOK
        # =====================================================

        try:
            wb = export_comptable_factures(
                factures
            )

        except Exception:
            return error_response(
                code="ACCOUNTING_EXPORT_FAILED",
                message=(
                    "Erreur lors de la génération "
                    "de l'export comptable."
                ),
                status_code=(
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
            )

        # =====================================================
        # 7. VALIDATION DU WORKBOOK
        # =====================================================

        if wb is None or not hasattr(wb, "save"):
            return error_response(
                code="INVALID_ACCOUNTING_WORKBOOK",
                message=(
                    "Le service d'export comptable "
                    "n'a pas retourné un classeur valide."
                ),
                status_code=(
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
            )

        # =====================================================
        # 8. CRÉATION DU FICHIER EXCEL
        # =====================================================

        buffer = BytesIO()

        try:
            wb.save(buffer)

            if buffer.tell() == 0:
                raise ValueError(
                    "Le fichier Excel généré est vide."
                )

            buffer.seek(0)

        except Exception:
            buffer.close()

            return error_response(
                code="ACCOUNTING_EXPORT_SAVE_FAILED",
                message=(
                    "Erreur lors de la création "
                    "du fichier Excel comptable."
                ),
                status_code=(
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
            )

        # =====================================================
        # 9. NOM DU FICHIER
        # =====================================================

        date_export = timezone.localdate().strftime(
            "%Y%m%d"
        )

        filename = (
            f"comptabilite_{date_export}.xlsx"
        )

        # =====================================================
        # 10. RÉPONSE EXCEL
        # =====================================================

        response = FileResponse(
            buffer,
            as_attachment=True,
            filename=filename,
            content_type=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            ),
        )

        response["Cache-Control"] = "no-store"

        return response


# ============================================================
# 1. RÉCUPÉRER ET VERROUILLER LA FACTURE
# ============================================================

def _get_facture_locked(vente):
    """
    Récupère la facture de la vente avec verrouillage SQL.

    À appeler exclusivement dans transaction.atomic().

    Une vente de prestations uniquement peut ne pas
    posséder de facture.
    """

    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError(
            "_get_facture_locked doit être appelé "
            "dans transaction.atomic()."
        )

    return (
        Facture.objects
        .select_for_update()
        .select_related(
            "vente",
            "bijouterie",
        )
        .filter(vente_id=vente.pk)
        .first()
    )


# ============================================================
# 2. VALIDATION AVANT MODIFICATION
# ============================================================

def _validate_before_payment(facture):
    """
    Une facture existante n'est modifiable que si :
    - elle est non payée ;
    - aucun montant n'a été payé ;
    - le stock n'est pas consommé ;
    - elle n'est pas verrouillée.

    Pour une vente sans facture, retourne None.

    Attention : le contrôle des paiements d'une vente
    sans facture doit être effectué séparément.
    """

    if facture is None:
        return None

    if facture.status != Facture.STAT_NON_PAYE:
        return error_response(
            code="FACTURE_NOT_EDITABLE",
            message=(
                "Action impossible : "
                "la facture n'est plus non payée."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    total_paye = Decimal(
        str(facture.total_paye or "0.00")
    )

    if total_paye > Decimal("0.00"):
        return error_response(
            code="FACTURE_HAS_PAYMENT",
            message=(
                "Action impossible : "
                "un paiement existe déjà."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if facture.stock_consumed:
        return error_response(
            code="STOCK_ALREADY_CONSUMED",
            message=(
                "Action impossible : "
                "le stock est déjà consommé."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if facture.is_locked:
        return error_response(
            code="FACTURE_LOCKED",
            message=(
                "Action impossible : "
                "la facture est verrouillée."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if facture.paiements.exists():
        return error_response(
            code="FACTURE_HAS_PAYMENT",
            message=(
                "Action impossible : "
                "des paiements sont déjà enregistrés "
                "pour cette facture."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return None


# ============================================================
# 3. RÉSOUDRE LE VENDEUR POUR MODIFICATION
# ============================================================

def _resolve_vendor_for_update(
    data,
    request,
    vente,
    role,
):
    """
    Résout le vendeur autorisé à intervenir sur la vente.

    Le vendeur connecté ne peut modifier que ses ventes.

    Admin et manager peuvent utiliser vendor_email,
    dans le respect des règles de périmètre.

    Le vendeur retenu doit appartenir à la même
    bijouterie que la vente.
    """

    user = request.user
    role = (role or "").lower().strip()

    allowed_roles = {
        ROLE_ADMIN,
        ROLE_MANAGER,
        ROLE_VENDOR,
    }

    if role not in allowed_roles:
        return None, error_response(
            code="SALE_UPDATE_ACCESS_DENIED",
            message=(
                "Vous n'êtes pas autorisé "
                "à modifier cette vente."
            ),
            status_code=status.HTTP_403_FORBIDDEN,
        )

    # ========================================================
    # VENDOR
    # ========================================================

    if role == ROLE_VENDOR:

        vendor = (
            Vendor.objects
            .select_related(
                "user",
                "bijouterie",
            )
            .filter(
                user=user,
                verifie=True,
            )
            .first()
        )

        if not vendor:
            return None, error_response(
                code="VENDOR_PROFILE_NOT_FOUND",
                message=(
                    "Vous n'êtes pas associé "
                    "à un compte vendeur actif."
                ),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if not vendor.bijouterie_id:
            return None, error_response(
                code="VENDOR_WITHOUT_STORE",
                message=(
                    "Le vendeur n'est rattaché "
                    "à aucune bijouterie."
                ),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if vente.vendor_id != vendor.id:
            return None, error_response(
                code="NOT_YOUR_SALE",
                message=(
                    "Vous ne pouvez modifier "
                    "que vos propres ventes."
                ),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if vente.bijouterie_id != vendor.bijouterie_id:
            return None, error_response(
                code="VENDOR_STORE_MISMATCH",
                message=(
                    "La vente et le vendeur "
                    "n'appartiennent pas "
                    "à la même bijouterie."
                ),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        return vendor, None

    # ========================================================
    # ADMIN / MANAGER
    # ========================================================

    if role == ROLE_MANAGER:

        manager_profile = getattr(
            user,
            "staff_manager_profile",
            None,
        )

        if not (
            manager_profile
            and getattr(
                manager_profile,
                "verifie",
                False,
            )
        ):
            return None, error_response(
                code="MANAGER_PROFILE_INVALID",
                message=(
                    "Profil manager introuvable "
                    "ou désactivé."
                ),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if not manager_profile.bijouteries.filter(
            id=vente.bijouterie_id
        ).exists():
            return None, error_response(
                code="SALE_OUT_OF_SCOPE",
                message=(
                    "Cette vente n'appartient pas "
                    "à vos bijouteries."
                ),
                status_code=status.HTTP_403_FORBIDDEN,
            )

    vendor_email = (
        data.get("vendor_email")
        or request.query_params.get("vendor_email")
    )

    if vendor_email:

        vendor = (
            Vendor.objects
            .select_related(
                "user",
                "bijouterie",
            )
            .filter(
                user__email__iexact=str(
                    vendor_email
                ).strip(),
                verifie=True,
            )
            .first()
        )

        if not vendor:
            return None, error_response(
                code="VENDOR_NOT_FOUND",
                message=(
                    "Vendeur introuvable "
                    "ou désactivé."
                ),
                status_code=status.HTTP_404_NOT_FOUND,
            )

    else:
        vendor = vente.vendor

        if not vendor:
            return None, error_response(
                code="VENDOR_NOT_FOUND",
                message=(
                    "Aucun vendeur associé à la vente."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if not getattr(vendor, "verifie", False):
            return None, error_response(
                code="VENDOR_NOT_VERIFIED",
                message="Le vendeur est désactivé.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

    if not vendor.bijouterie_id:
        return None, error_response(
            code="VENDOR_WITHOUT_STORE",
            message=(
                "Le vendeur n'est rattaché "
                "à aucune bijouterie."
            ),
            status_code=status.HTTP_403_FORBIDDEN,
        )

    # Empêche le transfert implicite d'une vente
    # vers une autre bijouterie.
    if vendor.bijouterie_id != vente.bijouterie_id:
        return None, error_response(
            code="VENDOR_STORE_MISMATCH",
            message=(
                "Le vendeur sélectionné "
                "n'appartient pas à la bijouterie "
                "de cette vente."
            ),
            status_code=status.HTTP_403_FORBIDDEN,
        )

    return vendor, None


# ============================================================
# 4. METTRE À JOUR LE CLIENT
# ============================================================

def _update_client_if_provided(
    data,
    vente,
):
    """
    Associe un client à la vente.

    Si un téléphone est fourni :
    - réutilise le client existant ;
    - ou crée un nouveau client.

    Sans téléphone :
    - crée un client distinct.

    Retourne None pour conserver le contrat existant.
    """

    if "client" not in data:
        return None

    client_data = data.get("client")

    if not client_data:
        return None

    nom = str(
        client_data.get("nom") or ""
    ).strip()

    prenom = str(
        client_data.get("prenom") or ""
    ).strip()

    telephone = str(
        client_data.get("telephone") or ""
    ).strip() or None

    if telephone:

        client, _ = Client.objects.get_or_create(
            telephone=telephone,
            defaults={
                "nom": nom,
                "prenom": prenom,
            },
        )

        update_fields = []

        if client.nom != nom:
            client.nom = nom
            update_fields.append("nom")

        if client.prenom != prenom:
            client.prenom = prenom
            update_fields.append("prenom")

        if update_fields:
            client.save(
                update_fields=update_fields
            )

    else:

        client = Client.objects.create(
            nom=nom,
            prenom=prenom,
            telephone=None,
        )

    if vente.client_id != client.id:

        vente.client = client

        vente.save(
            update_fields=["client"]
        )

    return None


# ============================================================
# 5. RÉSOUDRE LA PRODUITLINE EXACTE
# ============================================================

def _resolve_produit_line_for_sale_item(item):
    """
    Identifie la ProduitLine exacte.

    Formats autorisés :
    - produit_line_id
    - qr / qr_code au format PL:123

    Formats refusés :
    - produit_id
    - SKU générique
    - slug produit

    La résolution ne modifie pas le stock.
    """

    produit_line_id = item.get(
        "produit_line_id"
    )

    qr = (
        item.get("qr")
        or item.get("qr_code")
    )

    produit_line_qs = (
        ProduitLine.objects
        .select_related(
            "produit",
            "produit__marque",
            "produit__purete",
            "lot",
        )
    )

    # ========================================================
    # PRODUITLINE ID
    # ========================================================

    if produit_line_id not in (None, ""):

        try:
            produit_line_id = int(
                produit_line_id
            )

        except (TypeError, ValueError):
            return None

        if produit_line_id <= 0:
            return None

        return (
            produit_line_qs
            .filter(id=produit_line_id)
            .first()
        )

    # ========================================================
    # QR PRODUITLINE
    # ========================================================

    if qr:

        qr = str(qr).strip()

        if not qr.upper().startswith("PL:"):
            return None

        raw_id = qr.split(":", 1)[1].strip()

        if not raw_id.isdigit():
            return None

        produit_line_id = int(raw_id)

        if produit_line_id <= 0:
            return None

        return (
            produit_line_qs
            .filter(id=produit_line_id)
            .first()
        )

    return None


# ============================================================
# 6. RECALCULER OU CRÉER LA FACTURE
# ============================================================

def _recalculate_facture_from_vente(
    facture,
    vente,
    vendor,
):
    """
    Synchronise la facture avec le total de la vente.

    Bijoux uniquement :
        facture créée ou mise à jour.

    Bijoux + prestations :
        facture créée ou mise à jour.

    Prestations uniquement :
        aucune facture créée.

    Important :
    - vente.montant_total doit déjà être recalculé ;
    - ce montant doit inclure les bijoux et prestations ;
    - la fonction ne consomme aucun stock ;
    - la fonction doit être appelée dans transaction.atomic().
    """

    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError(
            "_recalculate_facture_from_vente "
            "doit être appelé dans transaction.atomic()."
        )

    if vendor.bijouterie_id != vente.bijouterie_id:
        raise ValueError(
            "Le vendeur et la vente doivent "
            "appartenir à la même bijouterie."
        )

    # ========================================================
    # CONTRÔLE DES LIGNES BIJOUX
    # ========================================================

    has_jewelry = vente.lignes.exists()

    # ========================================================
    # PRESTATIONS UNIQUEMENT
    # ========================================================

    if not has_jewelry:

        if facture is not None:
            raise ValueError(
                "Une facture existe déjà pour cette vente, "
                "mais elle ne contient plus de bijoux. "
                "La suppression ou l'annulation de cette "
                "facture doit être traitée explicitement."
            )

        return None

    # ========================================================
    # FACTURE EXISTANTE
    # ========================================================

    if facture is not None:

        validation_error = _validate_before_payment(
            facture
        )

        if validation_error is not None:
            raise ValueError(
                "Impossible de recalculer une facture "
                "déjà payée, verrouillée ou dont "
                "le stock est consommé."
            )

        facture.montant_ht = vente.montant_total
        facture.bijouterie = vendor.bijouterie

        # On conserve les champs calculés utilisés
        # dans le modèle Facture existant.
        #
        # Cela suppose que Facture.save() actualise
        # les montants TVA et TTC.

        facture.save(
            update_fields=[
                "montant_ht",
                "bijouterie",
                "taux_tva",
                "montant_tva",
                "montant_total",
            ]
        )

        return facture

    # ========================================================
    # CRÉATION D'UNE FACTURE
    # ========================================================

    facture = Facture.objects.create(
        vente=vente,
        bijouterie=vendor.bijouterie,
        montant_ht=vente.montant_total,
    )

    return facture



class UpdateVenteProduitView(APIView):
    """
    Modification des bijoux d'une vente avant paiement.

    Règles :
    - Admin, manager et vendeur autorisés.
    - Le vendeur ne modifie que ses ventes.
    - La vente ne doit pas être annulée.
    - La facture ne doit pas être payée ou verrouillée.
    - Aucun paiement ne doit exister.
    - Aucun stock ne doit être consommé.
    - Chaque bijou référence une ProduitLine exacte.
    - Le stock vendeur est vérifié mais jamais modifié.
    - Les prestations existantes sont conservées.
    """

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Modifier une vente avant paiement",
        operation_description="""
Modifie les bijoux d'une vente avant tout paiement.

Les produits envoyés remplacent les anciennes lignes
de bijoux de la vente.

Règles :
- Chaque produit doit identifier une ProduitLine exacte.
- La quantité cumulée est vérifiée par ProduitLine.
- Le stock vendeur doit être suffisant.
- Aucun VendorStock n'est modifié.
- Aucun InventoryMovement n'est créé.
- Le stock n'est consommé qu'après paiement complet.
- Les prestations existantes sont conservées.
- La facture est recalculée à partir du total de la vente.

PUT et PATCH ont ici le même comportement :
remplacement complet de la liste des bijoux.
        """,
        request_body=UpdateVenteProduitSerializer,
        responses={
            200: VenteDetailSerializer,
            400: "Données invalides ou vente non modifiable.",
            403: "Accès refusé.",
            404: "Vente ou produit introuvable.",
        },
        tags=["Ventes"],
    )
    @transaction.atomic
    def put(self, request, vente_id):

        user = request.user

        role = (
            get_role_name(user) or ""
        ).lower().strip()

        # =====================================================
        # 1. RÔLE
        # =====================================================

        if role not in {
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_VENDOR,
        }:
            return error_response(
                code="ACCESS_DENIED",
                message="Accès refusé.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # 2. VALIDATION PAYLOAD
        # =====================================================

        input_serializer = UpdateVenteProduitSerializer(
            data=request.data,
        )

        input_serializer.is_valid(
            raise_exception=True,
        )

        data = input_serializer.validated_data

        # =====================================================
        # 3. VENTE + VERROUILLAGE
        # =====================================================

        vente = (
            Vente.objects
            .select_for_update()
            .select_related(
                "vendor",
                "vendor__user",
                "vendor__bijouterie",
                "bijouterie",
                "client",
            )
            .filter(
                id=vente_id,
            )
            .first()
        )

        if vente is None:
            return error_response(
                code="VENTE_NOT_FOUND",
                message="Vente introuvable.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # =====================================================
        # 4. VENTE ANNULÉE
        # =====================================================

        if vente.is_cancelled:
            return error_response(
                code="VENTE_CANCELLED",
                message=(
                    "Modification impossible : "
                    "cette vente est annulée."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 5. FACTURE + VERROUILLAGE
        # =====================================================

        facture = _get_facture_locked(
            vente
        )

        facture_error = _validate_before_payment(
            facture
        )

        if facture_error is not None:
            return facture_error

        # =====================================================
        # 6. VENDEUR AUTORISÉ
        # =====================================================

        vendor, vendor_error = (
            _resolve_vendor_for_update(
                data,
                request,
                vente,
                role,
            )
        )

        if vendor_error is not None:
            return vendor_error

        if vendor is None:
            return error_response(
                code="VENDOR_NOT_FOUND",
                message="Vendeur introuvable.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if not getattr(
            vendor,
            "verifie",
            False,
        ):
            return error_response(
                code="VENDOR_NOT_VERIFIED",
                message=(
                    "Le vendeur est désactivé "
                    "ou non vérifié."
                ),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if not vendor.bijouterie_id:
            return error_response(
                code="VENDOR_WITHOUT_STORE",
                message=(
                    "Le vendeur n'est rattaché "
                    "à aucune bijouterie."
                ),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if vendor.bijouterie_id != vente.bijouterie_id:
            return error_response(
                code="VENDOR_STORE_MISMATCH",
                message=(
                    "Le vendeur sélectionné n'appartient "
                    "pas à la bijouterie de la vente."
                ),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # 7. PRODUITS
        # =====================================================

        produits_data = data.get(
            "produits"
        )

        if not produits_data:
            return error_response(
                code="EMPTY_SALE_LINES",
                message=(
                    "La vente doit contenir "
                    "au moins un bijou."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 8. PRÉPARATION DES NOUVELLES LIGNES
        # =====================================================

        prepared_lines = []

        requested_by_produit_line = {}

        for index, item in enumerate(
            produits_data,
            start=1,
        ):

            # -------------------------------------------------
            # QUANTITÉ
            # -------------------------------------------------

            try:
                quantite = int(
                    item.get(
                        "quantite",
                        1,
                    )
                )

            except (TypeError, ValueError):
                return error_response(
                    code="INVALID_QUANTITY",
                    message=(
                        f"Quantité invalide "
                        f"à la ligne {index}."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if quantite <= 0:
                return error_response(
                    code="INVALID_QUANTITY",
                    message=(
                        f"La quantité doit être supérieure "
                        f"ou égale à 1 à la ligne {index}."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            # -------------------------------------------------
            # PRODUITLINE EXACTE
            # -------------------------------------------------

            produit_line = (
                _resolve_produit_line_for_sale_item(
                    item
                )
            )

            if produit_line is None:
                return error_response(
                    code="PRODUIT_LINE_NOT_FOUND",
                    message=(
                        f"ProduitLine introuvable "
                        f"à la ligne {index}. "
                        f"Vérifiez produit_line_id ou le QR."
                    ),
                    status_code=status.HTTP_404_NOT_FOUND,
                )

            # -------------------------------------------------
            # PRODUIT
            # -------------------------------------------------

            produit = getattr(
                produit_line,
                "produit",
                None,
            )

            if produit is None:
                return error_response(
                    code="PRODUCT_NOT_FOUND",
                    message=(
                        f"Aucun produit n'est associé "
                        f"à la ProduitLine "
                        f"#{produit_line.id}."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            # -------------------------------------------------
            # LOT
            # -------------------------------------------------

            if not produit_line.lot_id:
                return error_response(
                    code="PRODUIT_LINE_WITHOUT_LOT",
                    message=(
                        f"La ProduitLine "
                        f"#{produit_line.id} "
                        f"n'est associée à aucun lot."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            # -------------------------------------------------
            # QUANTITÉ CUMULÉE
            # -------------------------------------------------

            produit_line_id = produit_line.id

            requested_by_produit_line[
                produit_line_id
            ] = (
                requested_by_produit_line.get(
                    produit_line_id,
                    0,
                )
                + quantite
            )

            # -------------------------------------------------
            # PRIX DE VENTE PAR GRAMME
            # -------------------------------------------------

            prix_vente_grammes = item.get(
                "prix_vente_grammes"
            )

            if prix_vente_grammes in (
                None,
                "",
                0,
                "0",
                "0.00",
            ):

                marque = getattr(
                    produit,
                    "marque",
                    None,
                )

                prix_marque = getattr(
                    marque,
                    "prix",
                    None,
                )

                if prix_marque in (None, ""):
                    return error_response(
                        code="PRICE_NOT_FOUND",
                        message=(
                            f"Aucun prix disponible "
                            f"pour {produit.nom}."
                        ),
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )

                prix_vente_grammes = prix_marque

            try:
                prix_vente_grammes = Decimal(
                    str(prix_vente_grammes)
                )

            except (
                InvalidOperation,
                TypeError,
                ValueError,
            ):
                return error_response(
                    code="INVALID_PRICE",
                    message=(
                        f"Prix invalide pour "
                        f"{produit.nom}."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if (
                not prix_vente_grammes.is_finite()
                or prix_vente_grammes <= Decimal("0.00")
            ):
                return error_response(
                    code="INVALID_PRICE",
                    message=(
                        f"Le prix de vente de "
                        f"{produit.nom} doit être "
                        f"supérieur à zéro."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            # -------------------------------------------------
            # REMISE
            # -------------------------------------------------

            try:
                remise = Decimal(
                    str(
                        item.get("remise")
                        or "0.00"
                    )
                )

            except (
                InvalidOperation,
                TypeError,
                ValueError,
            ):
                return error_response(
                    code="INVALID_DISCOUNT",
                    message=(
                        f"Remise invalide "
                        f"à la ligne {index}."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if (
                not remise.is_finite()
                or remise < Decimal("0.00")
            ):
                return error_response(
                    code="INVALID_DISCOUNT",
                    message=(
                        f"La remise doit être positive "
                        f"ou nulle à la ligne {index}."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            # -------------------------------------------------
            # AUTRES FRAIS SUR LA LIGNE BIJOU
            # -------------------------------------------------

            try:
                autres = Decimal(
                    str(
                        item.get("autres")
                        or "0.00"
                    )
                )

            except (
                InvalidOperation,
                TypeError,
                ValueError,
            ):
                return error_response(
                    code="INVALID_OTHER_AMOUNT",
                    message=(
                        f"Montant 'autres' invalide "
                        f"à la ligne {index}."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if (
                not autres.is_finite()
                or autres < Decimal("0.00")
            ):
                return error_response(
                    code="INVALID_OTHER_AMOUNT",
                    message=(
                        f"Le montant 'autres' ne peut "
                        f"pas être négatif "
                        f"à la ligne {index}."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            # -------------------------------------------------
            # REMISE OCCASION
            # -------------------------------------------------

            try:
                pourcentage_occasion = Decimal(
                    str(
                        item.get("pourcentage_occasion")
                        or "0.00"
                    )
                )

            except (
                InvalidOperation,
                TypeError,
                ValueError,
            ):
                return error_response(
                    code="INVALID_USED_PERCENTAGE",
                    message=(
                        f"Pourcentage occasion invalide "
                        f"à la ligne {index}."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if (
                not pourcentage_occasion.is_finite()
                or pourcentage_occasion < Decimal("0.00")
                or pourcentage_occasion > Decimal("100.00")
            ):
                return error_response(
                    code="INVALID_USED_PERCENTAGE",
                    message=(
                        f"Le pourcentage occasion doit "
                        f"être compris entre 0 et 100 "
                        f"à la ligne {index}."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            # -------------------------------------------------
            # LIGNE PRÉPARÉE
            # -------------------------------------------------

            prepared_lines.append(
                {
                    "produit_line": produit_line,
                    "quantite": quantite,
                    "prix_vente_grammes": (
                        prix_vente_grammes
                    ),
                    "remise": remise,
                    "autres": autres,
                    "pourcentage_occasion": pourcentage_occasion,
                }
            )

        # =====================================================
        # 9. VÉRIFICATION DU STOCK VENDEUR
        # =====================================================

        produit_lines_by_id = {
            prepared["produit_line"].id: (
                prepared["produit_line"]
            )
            for prepared in prepared_lines
        }

        for (
            produit_line_id,
            quantite_demandee,
        ) in requested_by_produit_line.items():

            produit_line = produit_lines_by_id[
                produit_line_id
            ]

            try:
                ensure_vendor_stock_available(
                    vendor=vendor,
                    bijouterie=vendor.bijouterie,
                    produit_line=produit_line,
                    quantite=quantite_demandee,
                )

            except DjangoValidationError as exc:
                return error_response(
                    code="VENDOR_STOCK_NOT_AVAILABLE",
                    message=(
                        f"Stock vendeur insuffisant "
                        f"ou indisponible pour la "
                        f"ProduitLine #{produit_line_id}."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                    details=(
                        getattr(
                            exc,
                            "message_dict",
                            None,
                        )
                        or getattr(
                            exc,
                            "messages",
                            None,
                        )
                        or str(exc)
                    ),
                )

        # =====================================================
        # 10. MISE À JOUR DU CLIENT
        # =====================================================

        client_error = (
            _update_client_if_provided(
                data,
                vente,
            )
        )

        if client_error is not None:
            transaction.set_rollback(True)
            return client_error

        # =====================================================
        # 11. VENDEUR ET BIJOUTERIE
        # =====================================================

        # La bijouterie de la vente est conservée.
        # Le changement de vendeur est limité
        # aux vendeurs de cette même bijouterie.

        vente.vendor = vendor

        vente.save(
            update_fields=["vendor"]
        )

        # =====================================================
        # 12. VERROUILLAGE DES ANCIENNES LIGNES
        # =====================================================

        old_lines = (
            VenteProduit.objects
            .select_for_update()
            .filter(
                vente=vente,
            )
        )

        # Force l'acquisition des verrous.
        list(
            old_lines.values_list(
                "id",
                flat=True,
            )
        )

        # =====================================================
        # 13. SUPPRESSION DES ANCIENNES LIGNES
        # =====================================================

        # Aucun stock n'a encore été consommé,
        # car la vente n'est pas payée.

        old_lines.delete()

        # =====================================================
        # 14. CRÉATION DES NOUVELLES LIGNES
        # =====================================================

        try:
            for prepared in prepared_lines:

                VenteProduit.objects.create(
                    vente=vente,
                    produit_line=(
                        prepared["produit_line"]
                    ),
                    vendor=vendor,
                    quantite=(
                        prepared["quantite"]
                    ),
                    prix_vente_grammes=(
                        prepared["prix_vente_grammes"]
                    ),
                    remise=prepared["remise"],
                    autres=prepared["autres"],
                    pourcentage_occasion=(
                        prepared["pourcentage_occasion"]
                    ),
                )

        except DjangoValidationError as exc:

            transaction.set_rollback(True)

            return error_response(
                code="SALE_LINE_INVALID",
                message=(
                    "Impossible de créer "
                    "une ligne de vente."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
                details=(
                    getattr(
                        exc,
                        "message_dict",
                        None,
                    )
                    or getattr(
                        exc,
                        "messages",
                        None,
                    )
                    or str(exc)
                ),
            )

        # =====================================================
        # 15. RECALCUL DU TOTAL DE LA VENTE
        # =====================================================

        vente.mettre_a_jour_montant_total()

        vente.refresh_from_db()

        # =====================================================
        # 16. RECALCUL DE LA FACTURE
        # =====================================================

        facture = (
            _recalculate_facture_from_vente(
                facture,
                vente,
                vendor,
            )
        )

        # =====================================================
        # 17. RAFRAÎCHISSEMENT FINAL
        # =====================================================

        vente.refresh_from_db()

        # =====================================================
        # 18. RÉPONSE
        # =====================================================

        return Response(
            VenteDetailSerializer(
                vente
            ).data,
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_summary=(
            "Modifier partiellement une vente avant paiement"
        ),
        operation_description=(
            "Même comportement que PUT : "
            "les lignes de bijoux sont entièrement remplacées."
        ),
        request_body=UpdateVenteProduitSerializer,
        responses={
            200: VenteDetailSerializer,
        },
        tags=["Ventes"],
    )
    def patch(
        self,
        request,
        vente_id,
    ):
        return self.put(
            request,
            vente_id,
        )

class CancelProformaVenteView(APIView):
    """
    Annulation d'une vente non payée ou proforma.

    Ventes prises en charge :
    - Bijoux uniquement.
    - Bijoux + prestations.
    - Prestations uniquement.

    Conditions :
    - Vente non annulée.
    - Aucun paiement enregistré.
    - Facture non payée, si elle existe.
    - Stock non consommé.
    - Facture non verrouillée.

    Effets :
    - Marque la vente comme annulée.
    - Verrouille la facture existante.
    - Ne modifie pas VendorStock.
    - Ne crée aucun InventoryMovement.
    - Ne restaure aucun stock.
    """

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary=(
            "Annuler une vente non payée / proforma"
        ),
        operation_description="""
Annule une vente avant tout paiement.

Types de ventes :
- Bijoux uniquement.
- Bijoux et prestations.
- Prestations uniquement.

Conditions :
- La vente ne doit pas déjà être annulée.
- Aucun paiement ne doit exister.
- La facture éventuelle doit être NON_PAYÉE.
- Le stock ne doit pas être consommé.
- La facture ne doit pas être verrouillée.

Opérations :
- Marque la vente comme annulée.
- Enregistre la date et l'utilisateur.
- Verrouille la facture si elle existe.
- Ne modifie pas VendorStock.
- Ne crée aucun InventoryMovement.
- Ne restaure aucun stock.

Rôles autorisés :
- Admin.
- Manager dans son périmètre.
- Vendeur propriétaire de la vente.
        """,
        request_body=CancelProformaVenteSerializer,
        responses={
            200: "Vente annulée avec succès.",
            400: "Vente non annulable.",
            403: "Accès refusé.",
            404: "Vente introuvable.",
        },
        tags=["Ventes"],
    )
    @transaction.atomic
    def post(
        self,
        request,
        vente_id,
    ):

        user = request.user

        role = (
            get_role_name(user) or ""
        ).lower().strip()

        # =====================================================
        # 1. CONTRÔLE DU RÔLE
        # =====================================================

        if role not in {
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_VENDOR,
        }:
            return error_response(
                code="ACCESS_DENIED",
                message="Accès refusé.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # 2. VALIDATION DU PAYLOAD
        # =====================================================

        input_serializer = CancelProformaVenteSerializer(
            data=request.data,
        )

        input_serializer.is_valid(
            raise_exception=True,
        )

        data = input_serializer.validated_data

        # =====================================================
        # 3. VENTE + VERROUILLAGE SQL
        # =====================================================

        vente = (
            Vente.objects
            .select_for_update()
            .select_related(
                "vendor",
                "vendor__user",
                "vendor__bijouterie",
                "bijouterie",
                "client",
            )
            .filter(
                id=vente_id,
            )
            .first()
        )

        if vente is None:
            return error_response(
                code="VENTE_NOT_FOUND",
                message="Vente introuvable.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # =====================================================
        # 4. VENTE DÉJÀ ANNULÉE
        # =====================================================

        if vente.is_cancelled:
            return error_response(
                code="VENTE_ALREADY_CANCELLED",
                message="Cette vente est déjà annulée.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 5. CONTRÔLE DU PÉRIMÈTRE
        # =====================================================

        # Pour une annulation, le vendeur de la vente
        # ne doit jamais être remplacé par vendor_email.
        #
        # On utilise donc uniquement le vendeur existant.

        vendor = vente.vendor

        if vendor is None:
            return error_response(
                code="VENDOR_NOT_FOUND",
                message=(
                    "Aucun vendeur n'est associé "
                    "à cette vente."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if not getattr(
            vendor,
            "verifie",
            False,
        ):
            return error_response(
                code="VENDOR_NOT_VERIFIED",
                message=(
                    "Le vendeur associé à la vente "
                    "est désactivé ou non vérifié."
                ),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if (
            not vendor.bijouterie_id
            or vendor.bijouterie_id != vente.bijouterie_id
        ):
            return error_response(
                code="VENDOR_STORE_MISMATCH",
                message=(
                    "Le vendeur n'appartient pas "
                    "à la bijouterie de cette vente."
                ),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # -----------------------------------------------------
        # VENDEUR : UNIQUEMENT SES PROPRES VENTES
        # -----------------------------------------------------

        if role == ROLE_VENDOR:

            vendor_profile = getattr(
                user,
                "staff_vendor_profile",
                None,
            )

            if not (
                vendor_profile
                and getattr(
                    vendor_profile,
                    "verifie",
                    False,
                )
            ):
                return error_response(
                    code="VENDOR_PROFILE_INVALID",
                    message=(
                        "Profil vendeur introuvable "
                        "ou désactivé."
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )

            if (
                vendor_profile.id != vente.vendor_id
                or vendor_profile.bijouterie_id
                != vente.bijouterie_id
            ):
                return error_response(
                    code="NOT_YOUR_SALE",
                    message=(
                        "Vous ne pouvez annuler "
                        "que vos propres ventes."
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )

        # -----------------------------------------------------
        # MANAGER : BIJOUTERIES AUTORISÉES
        # -----------------------------------------------------

        elif role == ROLE_MANAGER:

            manager_profile = getattr(
                user,
                "staff_manager_profile",
                None,
            )

            if not (
                manager_profile
                and getattr(
                    manager_profile,
                    "verifie",
                    False,
                )
            ):
                return error_response(
                    code="MANAGER_PROFILE_INVALID",
                    message=(
                        "Profil manager introuvable "
                        "ou désactivé."
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )

            allowed = (
                manager_profile.bijouteries
                .filter(
                    id=vente.bijouterie_id,
                )
                .exists()
            )

            if not allowed:
                return error_response(
                    code="SALE_OUT_OF_SCOPE",
                    message=(
                        "Cette vente n'appartient pas "
                        "à vos bijouteries."
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )

        # =====================================================
        # 6. FACTURE + VERROUILLAGE SQL
        # =====================================================

        facture = _get_facture_locked(
            vente
        )

        # =====================================================
        # 7. VALIDATION DE LA FACTURE
        # =====================================================

        # Si la facture existe :
        # - statut NON_PAYE
        # - total payé = 0
        # - aucun paiement
        # - stock non consommé
        # - facture non verrouillée

        facture_error = _validate_before_payment(
            facture
        )

        if facture_error is not None:
            return facture_error

        # =====================================================
        # 8. ANNULATION DE LA VENTE
        # =====================================================

        now = timezone.now()

        vente.is_cancelled = True
        vente.cancelled_at = now
        vente.cancelled_by = user

        vente.save(
            update_fields=[
                "is_cancelled",
                "cancelled_at",
                "cancelled_by",
            ]
        )

        # =====================================================
        # 9. VERROUILLAGE MÉTIER DE LA FACTURE
        # =====================================================

        if facture is not None:

            facture.is_locked = True
            facture.locked_at = now

            facture.save(
                update_fields=[
                    "is_locked",
                    "locked_at",
                ]
            )

        # =====================================================
        # 10. AUCUNE OPÉRATION DE STOCK
        # =====================================================

        # Ne pas appeler :
        #
        # ensure_vendor_stock_available()
        # consume_vendor_stock()
        # create_sale_out_consumption()
        #
        # Ne pas créer InventoryMovement.
        #
        # Le stock n'ayant pas été consommé,
        # aucune restauration n'est nécessaire.

        # =====================================================
        # 11. RAFRAÎCHISSEMENT FINAL
        # =====================================================

        vente.refresh_from_db()

        # =====================================================
        # 12. RÉPONSE
        # =====================================================

        return Response(
            {
                "status": "success",
                "code": "VENTE_PROFORMA_CANCELLED",
                "message": (
                    "Vente non payée annulée "
                    "avec succès."
                ),
                "reason": data.get("reason"),
                "vente": VenteDetailSerializer(
                    vente
                ).data,
            },
            status=status.HTTP_200_OK,
        )

class RetourVenteProduitView(APIView):
    """
    Retour client de bijoux sous 72 heures.

    Conditions :
    - Vente non annulée.
    - Facture entièrement payée.
    - Stock de la facture déjà consommé.
    - Délai de 72 heures respecté.
    - Retour basé sur VenteProduit et ProduitLine.
    - Quantité retournée <= quantité vendue
      moins les retours déjà enregistrés.

    Effets :
    - Augmente Stock.en_stock.
    - Augmente Stock.quantite_totale.
    - Ne modifie jamais VendorStock.
    - Crée InventoryMovement RETURN_IN.
    - Ne modifie pas les paiements ni la facture.

    Les prestations ne sont pas concernées.
    """

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Retour client sous 72h après paiement",
        operation_description="""
Enregistre le retour de bijoux après paiement complet.

Conditions :
- La facture doit être payée.
- Le stock doit déjà avoir été consommé.
- Le délai de 72 heures doit être respecté.
- Chaque retour est lié à la VenteProduit et à sa ProduitLine.
- Les quantités déjà retournées sont déduites.

Si produits est omis ou vide :
- Retourne toutes les quantités encore retournables.

Si produits est renseigné :
- Effectue un retour partiel par vente_ligne_id.

Le retour :
- Réintègre les bijoux dans le stock de la bijouterie.
- Ne modifie pas VendorStock.
- Crée un mouvement RETURN_IN.
- Ne modifie pas les prestations.
        """,
        request_body=RetourVenteProduitSerializer,
        responses={
            200: "Retour enregistré avec succès.",
            400: "Retour impossible ou quantité invalide.",
            403: "Accès refusé.",
            404: "Vente ou facture introuvable.",
        },
        tags=["Ventes"],
    )
    @transaction.atomic
    def post(self, request, vente_id):

        user = request.user
        role = (
            get_role_name(user) or ""
        ).lower().strip()

        # =====================================================
        # 1. RÔLE
        # =====================================================

        if role not in {
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_VENDOR,
        }:
            return error_response(
                code="ACCESS_DENIED",
                message="Accès refusé.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # 2. PAYLOAD
        # =====================================================

        input_serializer = RetourVenteProduitSerializer(
            data=request.data,
        )
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        # =====================================================
        # 3. VENTE + VERROUILLAGE
        # =====================================================

        vente = (
            Vente.objects
            .select_for_update()
            .select_related(
                "vendor",
                "vendor__user",
                "vendor__bijouterie",
                "bijouterie",
                "client",
            )
            .filter(id=vente_id)
            .first()
        )

        if vente is None:
            return error_response(
                code="VENTE_NOT_FOUND",
                message="Vente introuvable.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if vente.is_cancelled:
            return error_response(
                code="VENTE_CANCELLED",
                message=(
                    "Retour impossible : "
                    "cette vente est annulée."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 4. CONTRÔLE DU PÉRIMÈTRE
        # =====================================================

        vendor = vente.vendor

        if vendor is None:
            return error_response(
                code="VENDOR_NOT_FOUND",
                message=(
                    "Aucun vendeur n'est associé "
                    "à cette vente."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if (
            not vendor.bijouterie_id
            or vendor.bijouterie_id != vente.bijouterie_id
        ):
            return error_response(
                code="VENDOR_STORE_MISMATCH",
                message=(
                    "Le vendeur et la vente "
                    "n'appartiennent pas "
                    "à la même bijouterie."
                ),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if role == ROLE_VENDOR:
            profile = getattr(
                user,
                "staff_vendor_profile",
                None,
            )

            if not (
                profile
                and getattr(profile, "verifie", False)
                and profile.id == vente.vendor_id
                and profile.bijouterie_id == vente.bijouterie_id
            ):
                return error_response(
                    code="NOT_YOUR_SALE",
                    message=(
                        "Vous ne pouvez retourner "
                        "que les produits de vos ventes."
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )

        elif role == ROLE_MANAGER:
            profile = getattr(
                user,
                "staff_manager_profile",
                None,
            )

            if not (
                profile
                and getattr(profile, "verifie", False)
                and profile.bijouteries.filter(
                    id=vente.bijouterie_id
                ).exists()
            ):
                return error_response(
                    code="SALE_OUT_OF_SCOPE",
                    message=(
                        "Cette vente n'appartient pas "
                        "à vos bijouteries."
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )

        # =====================================================
        # 5. FACTURE + VERROUILLAGE
        # =====================================================

        facture = _get_facture_locked(vente)

        if facture is None:
            return error_response(
                code="FACTURE_NOT_FOUND",
                message=(
                    "Retour impossible : "
                    "aucune facture liée."
                ),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if facture.bijouterie_id != vente.bijouterie_id:
            return error_response(
                code="INVOICE_STORE_MISMATCH",
                message=(
                    "La facture et la vente "
                    "n'appartiennent pas "
                    "à la même bijouterie."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 6. FACTURE PAYÉE
        # =====================================================

        if facture.status != Facture.STAT_PAYE:
            return error_response(
                code="FACTURE_NOT_PAID",
                message=(
                    "Retour impossible : "
                    "la facture n'est pas payée."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 7. STOCK CONSOMMÉ
        # =====================================================

        if not facture.stock_consumed:
            return error_response(
                code="STOCK_NOT_CONSUMED",
                message=(
                    "Retour impossible : "
                    "le stock de la vente "
                    "n'a pas encore été consommé."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 8. DÉLAI DE 72 HEURES
        # =====================================================

        reference_date = (
            vente.delivered_at
            or facture.date_creation
        )

        if reference_date is None:
            return error_response(
                code="RETURN_REFERENCE_DATE_NOT_FOUND",
                message=(
                    "Impossible de déterminer "
                    "la date de référence du retour."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.now()

        if now < reference_date:
            return error_response(
                code="INVALID_RETURN_REFERENCE_DATE",
                message=(
                    "La date de référence du retour "
                    "est dans le futur."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if now > reference_date + timedelta(hours=72):
            return error_response(
                code="RETURN_DELAY_EXPIRED",
                message=(
                    "Retour impossible : "
                    "délai de 72 heures dépassé."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 9. RAISON
        # =====================================================

        reason = str(
            data.get("reason")
            or "Retour client sous 72h"
        ).strip()

        if not reason:
            reason = "Retour client sous 72h"

        # =====================================================
        # 10. PRODUITS À RETOURNER
        # =====================================================

        produits_retour = data.get("produits") or []
        requested_by_line = {}

        for item in produits_retour:
            try:
                ligne_id = int(item["vente_ligne_id"])
                qty = int(item["quantite"])
            except (KeyError, TypeError, ValueError):
                return error_response(
                    code="INVALID_RETURN_LINE",
                    message=(
                        "vente_ligne_id et quantite "
                        "doivent être valides."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if ligne_id <= 0 or qty <= 0:
                return error_response(
                    code="INVALID_RETURN_QUANTITY",
                    message=(
                        "La ligne et la quantité "
                        "doivent être supérieures à zéro."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            requested_by_line[ligne_id] = (
                requested_by_line.get(ligne_id, 0)
                + qty
            )

        # =====================================================
        # 11. LIGNES DE VENTE
        # =====================================================

        if requested_by_line:
            existing_line_ids = set(
                VenteProduit.objects
                .filter(
                    vente=vente,
                    id__in=requested_by_line.keys(),
                )
                .values_list("id", flat=True)
            )

            unknown_line_ids = (
                set(requested_by_line)
                - existing_line_ids
            )

            if unknown_line_ids:
                return error_response(
                    code="SALE_LINE_NOT_FOUND",
                    message=(
                        "Certaines lignes ne font pas "
                        "partie de cette vente."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                    details={
                        "ligne_ids": sorted(unknown_line_ids)
                    },
                )

        # =====================================================
        # 12. MOUVEMENTS SALE_OUT
        # =====================================================

        sale_outs_qs = (
            InventoryMovement.objects
            .select_for_update()
            .filter(
                vente=vente,
                facture=facture,
                movement_type=MovementType.SALE_OUT,
            )
            .select_related(
                "produit",
                "produit_line",
                "produit_line__produit",
                "produit_line__lot",
                "produit_line__lot__achat",
                "lot",
                "vendor",
                "vendor__bijouterie",
                "vente_ligne",
            )
            .order_by(
                "vente_ligne_id",
                "produit_line_id",
                "id",
            )
        )

        if requested_by_line:
            sale_outs_qs = sale_outs_qs.filter(
                vente_ligne_id__in=requested_by_line
            )

        sale_outs = list(sale_outs_qs)

        if not sale_outs:
            return error_response(
                code="SALE_OUT_NOT_FOUND",
                message=(
                    "Aucun mouvement SALE_OUT "
                    "n'a été trouvé pour cette vente."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 13. QUANTITÉS DÉJÀ RETOURNÉES
        # =====================================================

        returned_rows = (
            InventoryMovement.objects
            .filter(
                vente=vente,
                facture=facture,
                movement_type=MovementType.RETURN_IN,
            )
            .values(
                "vente_ligne_id",
                "produit_line_id",
            )
            .annotate(
                total=Sum("qty")
            )
        )

        already_returned = {
            (
                row["vente_ligne_id"],
                row["produit_line_id"],
            ): int(row["total"] or 0)
            for row in returned_rows
        }

        # =====================================================
        # 14. QUANTITÉS VENDUES
        # =====================================================

        sale_out_total = {}
        moves_by_key = {}

        for move in sale_outs:

            if not move.vente_ligne_id:
                return error_response(
                    code="SALE_LINE_MISSING",
                    message=(
                        "Un mouvement SALE_OUT "
                        "n'est associé à aucune ligne "
                        "de vente."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if not move.produit_line_id:
                return error_response(
                    code="PRODUIT_LINE_NOT_FOUND",
                    message=(
                        "Un mouvement SALE_OUT "
                        "ne contient pas de ProduitLine."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            key = (
                move.vente_ligne_id,
                move.produit_line_id,
            )

            sale_out_total[key] = (
                sale_out_total.get(key, 0)
                + int(move.qty or 0)
            )

            moves_by_key.setdefault(key, []).append(move)

        # =====================================================
        # 15. PRÉPARATION DES RETOURS
        # =====================================================

        returns_to_create = []
        remaining_requested = dict(requested_by_line)

        for key, moves in moves_by_key.items():

            ligne_id, produit_line_id = key

            sold_qty = sale_out_total[key]
            returned_qty = already_returned.get(key, 0)

            if returned_qty < 0 or returned_qty > sold_qty:
                return error_response(
                    code="INVALID_RETURN_HISTORY",
                    message=(
                        "Les quantités déjà retournées "
                        "sont incohérentes."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            returnable_qty = sold_qty - returned_qty

            if returnable_qty <= 0:
                continue

            if requested_by_line:
                wanted = remaining_requested.get(
                    ligne_id,
                    0,
                )

                if wanted <= 0:
                    continue

                qty_to_return = min(
                    returnable_qty,
                    wanted,
                )

                remaining_requested[ligne_id] = (
                    wanted - qty_to_return
                )

            else:
                qty_to_return = returnable_qty

            if qty_to_return <= 0:
                continue

            # Répartit le retour entre les SALE_OUT
            # sans attribuer à un mouvement plus
            # que sa quantité encore retournable.
            #
            # L'historique disponible est agrégé par
            # (vente_ligne, produit_line). La répartition
            # entre plusieurs SALE_OUT identiques est
            # donc déterministe, selon leur ID.

            remaining_qty = qty_to_return
            already_allocated = returned_qty

            for move in moves:

                move_qty = int(move.qty or 0)

                if move_qty <= 0:
                    continue

                consumed_by_previous_returns = min(
                    already_allocated,
                    move_qty,
                )

                already_allocated -= (
                    consumed_by_previous_returns
                )

                available_on_move = (
                    move_qty - consumed_by_previous_returns
                )

                if available_on_move <= 0:
                    continue

                allocated_qty = min(
                    available_on_move,
                    remaining_qty,
                )

                if allocated_qty > 0:
                    returns_to_create.append(
                        {
                            "move": move,
                            "ligne": move.vente_ligne,
                            "produit_line": move.produit_line,
                            "qty": allocated_qty,
                        }
                    )

                    remaining_qty -= allocated_qty

                if remaining_qty == 0:
                    break

            if remaining_qty != 0:
                return error_response(
                    code="RETURN_ALLOCATION_FAILED",
                    message=(
                        "Impossible de répartir "
                        "les quantités du retour."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        # =====================================================
        # 16. CONTRÔLE DES QUANTITÉS DEMANDÉES
        # =====================================================

        if requested_by_line:

            not_returnable = {
                ligne_id: qty
                for ligne_id, qty
                in remaining_requested.items()
                if qty > 0
            }

            if not_returnable:
                return error_response(
                    code="RETURN_QTY_TOO_HIGH",
                    message=(
                        "La quantité demandée dépasse "
                        "la quantité encore retournable."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                    details=not_returnable,
                )

        if not returns_to_create:
            return error_response(
                code="NOTHING_TO_RETURN",
                message=(
                    "Aucune quantité retournable "
                    "n'a été trouvée."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 17. EXÉCUTION DES RETOURS
        # =====================================================

        total_returned_now = 0
        details = []

        for return_data in returns_to_create:

            move = return_data["move"]
            ligne = return_data["ligne"]
            produit_line = return_data["produit_line"]
            qty_to_return = return_data["qty"]

            # -------------------------------------------------
            # BIJOUTERIE
            # -------------------------------------------------

            bijouterie_id = vente.bijouterie_id

            if not bijouterie_id:
                raise ValidationError({
                    "bijouterie": (
                        "Impossible de déterminer "
                        "la bijouterie du retour."
                    )
                })

            # -------------------------------------------------
            # LOT
            # -------------------------------------------------

            lot = produit_line.lot

            if lot is None:
                raise ValidationError({
                    "produit_line": (
                        f"La ProduitLine #{produit_line.id} "
                        f"n'est associée à aucun lot."
                    )
                })

            # -------------------------------------------------
            # STOCK BIJOUTERIE + LOCK
            # -------------------------------------------------

            stock_magasin, _ = (
                Stock.objects
                .get_or_create(
                    produit_line=produit_line,
                    bijouterie_id=bijouterie_id,
                    defaults={
                        "en_stock": 0,
                        "quantite_totale": 0,
                    },
                )
            )

            stock_magasin = (
                Stock.objects
                .select_for_update()
                .get(pk=stock_magasin.pk)
            )

            # -------------------------------------------------
            # REMISE EN STOCK
            # -------------------------------------------------

            updated = (
                Stock.objects
                .filter(pk=stock_magasin.pk)
                .update(
                    en_stock=(
                        F("en_stock") + qty_to_return
                    ),
                    quantite_totale=(
                        F("quantite_totale") + qty_to_return
                    ),
                    updated_at=timezone.now(),
                )
            )

            if updated != 1:
                raise ValidationError({
                    "stock": (
                        "Impossible de remettre "
                        "le produit dans le stock "
                        "de la bijouterie."
                    )
                })

            # -------------------------------------------------
            # MOUVEMENT RETURN_IN
            # -------------------------------------------------

            log_move(
                produit=produit_line.produit,
                produit_line=produit_line,
                achat=lot.achat,
                lot=lot,
                movement_type=MovementType.RETURN_IN,
                qty=qty_to_return,
                src_bucket=Bucket.EXTERNAL,
                dst_bucket=Bucket.BIJOUTERIE,
                dst_bijouterie_id=bijouterie_id,
                vendor=(
                    move.vendor
                    or vente.vendor
                ),
                vente=vente,
                vente_ligne=ligne,
                facture=facture,
                reason=reason,
                user=user,
            )

            # -------------------------------------------------
            # DÉTAIL
            # -------------------------------------------------

            total_returned_now += qty_to_return

            details.append({
                "vente_ligne_id": ligne.id,
                "produit_line_id": produit_line.id,
                "produit_id": produit_line.produit_id,
                "produit": getattr(
                    produit_line.produit,
                    "nom",
                    None,
                ),
                "lot_id": produit_line.lot_id,
                "bijouterie_id": bijouterie_id,
                "quantite_retournee": qty_to_return,
            })

        # =====================================================
        # 18. RÉPONSE
        # =====================================================

        return Response(
            {
                "status": "success",
                "code": "RETURN_IN_CREATED",
                "message": (
                    "Retour client enregistré "
                    "avec succès."
                ),
                "vente_id": vente.id,
                "numero_vente": vente.numero_vente,
                "facture": facture.numero_facture,
                "quantite_totale_retournee": (
                    total_returned_now
                ),
                "details": details,
            },
            status=status.HTTP_200_OK,
        )

