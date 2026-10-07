# from weasyprint import HTML
# import weasyprint
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from io import BytesIO
from uuid import UUID

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
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from openpyxl import Workbook
from openpyxl.styles import Font, numbers
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
from sale.serializers import (CancelProformaVenteSerializer,
                              FactureListSerializer,
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

# Adapte ce chemin à l'emplacement réel du fichier.

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

    permission_classes = [CanCreateSale]
    http_method_names = ["post", "options"]

    # =========================================================
    # VENDEUR CONNECTÉ
    # =========================================================

    def _get_vendor_for_user(self, user):
        return (
            Vendor.objects
            .select_related(
                "bijouterie",
                "user",
            )
            .filter(
                user=user,
                verifie=True,
            )
            .first()
        )

    # =========================================================
    # VÉRIFICATION STOCK VENDEUR EXACT
    # =========================================================

    def _ensure_produit_line_in_vendor_stock(
        self,
        *,
        user,
        role,
        produit_line,
    ):
        """
        Pour un vendeur connecté, vérifie que la ProduitLine
        scannée lui est réellement affectée et qu'il reste
        au moins une unité disponible.

        Aucun FIFO.
        Aucun fallback vers une autre ProduitLine.
        """

        if role != ROLE_VENDOR:
            return

        vendor = self._get_vendor_for_user(
            user
        )

        if not vendor:
            raise ValidationError({
                "vendor": (
                    "Profil vendeur introuvable."
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

            produit = produit_line.produit

            identifiant = (
                getattr(
                    produit_line,
                    "uuid",
                    None,
                )
                or produit_line.pk
            )

            raise ValidationError({
                "produit_line": (
                    f"Le produit '{produit.nom}' "
                    f"(ProduitLine {identifiant}) "
                    "n'est plus disponible dans "
                    "le stock de ce vendeur."
                )
            })

    # =========================================================
    # RÉSOLUTION PRODUIT_LINE
    # =========================================================

    def _resolve_produit_line_id(
        self,
        item,
        *,
        user,
        role,
    ):
        """
        Résout obligatoirement une ProduitLine précise.

        Entrées acceptées :

        - produit_line_id
        - QR de ProduitLine
        - UUID de ProduitLine

        La vente ne résout plus directement un Produit.
        """

        produit_line_id = item.get(
            "produit_line_id"
        )

        qr = (
            item.get("qr")
            or item.get("qr_code")
        )

        produit_line = None

        # =====================================================
        # 1. ID ProduitLine
        # =====================================================

        if produit_line_id:

            try:
                produit_line_id = int(
                    produit_line_id
                )

            except (TypeError, ValueError):
                raise ValidationError({
                    "produit_line_id": (
                        "Identifiant ProduitLine invalide."
                    )
                })

            produit_line = (
                ProduitLine.objects
                .select_related(
                    "produit",
                    "lot",
                )
                .filter(
                    id=produit_line_id,
                )
                .first()
            )

        # =====================================================
        # 2. QR / UUID ProduitLine
        # =====================================================

        else:

            scan_value = qr

            if scan_value:

                scan_value = (
                    str(scan_value)
                    .replace("\n", "")
                    .replace("\r", "")
                    .strip()
                )

                # ---------------------------------------------
                # Formats acceptés :
                #
                # PL:<uuid>
                # <uuid>
                # ---------------------------------------------

                if scan_value.startswith("PL:"):
                    raw_uuid = (
                        scan_value
                        .removeprefix("PL:")
                        .strip()
                    )

                else:
                    raw_uuid = scan_value

                try:
                    produit_line_uuid = UUID(
                        raw_uuid
                    )

                except (
                    ValueError,
                    TypeError,
                    AttributeError,
                ):
                    raise ValidationError({
                        "produit_line": (
                            "Le QR code contient un UUID "
                            "ProduitLine invalide."
                        )
                    })

                produit_line = (
                    ProduitLine.objects
                    .select_related(
                        "produit",
                        "lot",
                    )
                    .filter(
                        uuid=produit_line_uuid,
                    )
                    .first()
                )

        # =====================================================
        # 3. OBLIGATOIRE
        # =====================================================

        if not produit_line:
            raise ValidationError({
                "produit_line": (
                    "ProduitLine introuvable "
                    "ou code invalide."
                )
            })

        # =====================================================
        # 4. COHÉRENCE ProduitLine
        # =====================================================

        if not produit_line.produit_id:
            raise ValidationError({
                "produit_line": (
                    "Cette ProduitLine n'est associée "
                    "à aucun produit."
                )
            })

        if not produit_line.lot_id:
            raise ValidationError({
                "produit_line": (
                    "Cette ProduitLine n'est associée "
                    "à aucun lot."
                )
            })

        # =====================================================
        # 5. STOCK VENDEUR
        # =====================================================

        self._ensure_produit_line_in_vendor_stock(
            user=user,
            role=role,
            produit_line=produit_line,
        )

        return produit_line.id

    # =========================================================
    # NORMALISATION PRODUITS
    # =========================================================

    def _normalize_produits(
        self,
        produits,
        *,
        user,
        role,
    ):
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

            # ---------------------------------------------
            # Anciennes clés supprimées
            # ---------------------------------------------

            item.pop(
                "produit_id",
                None,
            )

            item.pop(
                "sku",
                None,
            )

            item.pop(
                "qr",
                None,
            )

            item.pop(
                "qr_code",
                None,
            )

            normalized.append(
                item
            )

        return normalized

    # =========================================================
    # SWAGGER
    # =========================================================

    @swagger_auto_schema(
        operation_summary=(
            "Créer une vente (1 vendeur) "
            "+ facture PROFORMA "
            "(stock non consommé)"
        ),
        request_body=VenteCreateInSerializer,
        responses={
            201: openapi.Response("Créé"),
            400: "Erreur validation",
            403: "Accès refusé",
        },
        tags=["Ventes"],
    )

    # =========================================================
    # POST
    # =========================================================

    @transaction.atomic
    def post(self, request):

        # =====================================================
        # 1. VALIDATION PAYLOAD
        # =====================================================

        serializer = VenteCreateInSerializer(
            data=request.data,
            context={
                "request": request,
            },
        )

        serializer.is_valid(
            raise_exception=True
        )

        validated = (
            serializer.validated_data
        )

        role = (
            get_role_name(
                request.user
            )
            or ""
        ).lower().strip()

        # =====================================================
        # 2. NORMALISATION ProduitLine
        # =====================================================

        try:

            produits_normalized = (
                self._normalize_produits(
                    validated["produits"],
                    user=request.user,
                    role=role,
                )
            )

        except ValidationError as e:

            detail = (
                getattr(
                    e,
                    "message_dict",
                    None,
                )
                or getattr(
                    e,
                    "messages",
                    None,
                )
                or str(e)
            )

            return Response(
                {
                    "detail": detail,
                },
                status=(
                    status.HTTP_400_BAD_REQUEST
                ),
            )

        payload = {
            "client": (
                validated.get("client")
                or {}
            ),
            "produits": (
                produits_normalized
            ),
        }

        # =====================================================
        # 3. ADMIN / MANAGER : VENDEUR CIBLE
        # =====================================================

        if role in {
            ROLE_ADMIN,
            ROLE_MANAGER,
        }:

            vendor_email = (
                validated.get(
                    "vendor_email"
                )
                or ""
            ).strip()

            if not vendor_email:

                return Response(
                    {
                        "detail": (
                            "vendor_email est requis "
                            "pour admin/manager."
                        )
                    },
                    status=(
                        status.HTTP_400_BAD_REQUEST
                    ),
                )

            vendor = (
                Vendor.objects
                .select_related(
                    "bijouterie",
                    "user",
                )
                .filter(
                    user__email__iexact=(
                        vendor_email
                    ),
                    verifie=True,
                )
                .first()
            )

            if not vendor:

                return Response(
                    {
                        "detail": (
                            "Vendeur introuvable pour "
                            "ce vendor_email."
                        )
                    },
                    status=(
                        status.HTTP_400_BAD_REQUEST
                    ),
                )

            # =================================================
            # MANAGER : CONTRÔLE BIJOUTERIE
            # =================================================

            if role == ROLE_MANAGER:

                manager_profile = getattr(
                    request.user,
                    "staff_manager_profile",
                    None,
                )

                if (
                    not manager_profile
                    or (
                        hasattr(
                            manager_profile,
                            "verifie",
                        )
                        and not manager_profile.verifie
                    )
                ):

                    return Response(
                        {
                            "detail": (
                                "Profil manager invalide."
                            )
                        },
                        status=(
                            status.HTTP_403_FORBIDDEN
                        ),
                    )

                if not (
                    manager_profile
                    .bijouteries
                    .filter(
                        id=vendor.bijouterie_id
                    )
                    .exists()
                ):

                    return Response(
                        {
                            "detail": (
                                "⛔ Vous ne pouvez pas "
                                "créer une vente pour un "
                                "vendeur hors de vos "
                                "bijouteries."
                            )
                        },
                        status=(
                            status.HTTP_403_FORBIDDEN
                        ),
                    )

            payload[
                "vendor_email"
            ] = vendor_email

        # =====================================================
        # 4. CRÉATION VENTE + PROFORMA
        # =====================================================

        try:

            (
                vente,
                facture,
                audit_created,
            ) = create_sale_one_vendor(
                user=request.user,
                role=role,
                payload=payload,
            )

        except ValidationError as e:

            detail = (
                getattr(
                    e,
                    "message_dict",
                    None,
                )
                or getattr(
                    e,
                    "messages",
                    None,
                )
                or str(e)
            )

            return Response(
                {
                    "detail": detail,
                },
                status=(
                    status.HTTP_400_BAD_REQUEST
                ),
            )

        # =====================================================
        # 5. LIGNES RÉPONSE
        # =====================================================

        lignes = []

        vente_lignes = (
            vente.lignes
            .select_related(
                "produit_line",
                "produit_line__produit",
                "produit_line__lot",
            )
            .all()
        )

        for ligne in vente_lignes:

            produit_line = (
                ligne.produit_line
            )

            produit = (
                produit_line.produit
            )

            pourcentage_occasion = Decimal(
                str(
                    ligne.pourcentage_occasion
                    or "0.00"
                )
            )

            montant_ht = Decimal(
                str(
                    ligne.montant_ht
                    or "0.00"
                )
            )

            reduction_occasion = (
                montant_ht
                * pourcentage_occasion
                / Decimal("100")
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            lignes.append({

                # -----------------------------------------
                # Ligne vente
                # -----------------------------------------

                "ligne_id": ligne.id,

                # -----------------------------------------
                # ProduitLine = source de vérité
                # -----------------------------------------

                "produit_line_id": (
                    produit_line.id
                ),

                "produit_line_uuid": str(
                    produit_line.uuid
                ),

                # -----------------------------------------
                # Produit dérivé de ProduitLine
                # -----------------------------------------

                "produit_id": (
                    produit.id
                ),

                "produit_nom": getattr(
                    produit,
                    "nom",
                    None,
                ),

                "sku": getattr(
                    produit,
                    "sku",
                    None,
                ),

                "etat": getattr(
                    produit,
                    "etat",
                    None,
                ),

                # -----------------------------------------
                # Quantité / prix
                # -----------------------------------------

                "quantite": (
                    ligne.quantite
                ),

                "prix_vente_grammes": str(
                    ligne.prix_vente_grammes
                ),

                # -----------------------------------------
                # Brut
                # -----------------------------------------

                "montant_ht": str(
                    ligne.montant_ht
                ),

                # -----------------------------------------
                # Occasion
                # -----------------------------------------

                "pourcentage_occasion": str(
                    pourcentage_occasion
                ),

                "reduction_occasion": str(
                    reduction_occasion
                ),

                # -----------------------------------------
                # Remise / autres
                # -----------------------------------------

                "remise": str(
                    ligne.remise
                    or Decimal("0.00")
                ),

                "autres": str(
                    ligne.autres
                    or Decimal("0.00")
                ),

                # -----------------------------------------
                # Total ligne avant TVA facture
                # -----------------------------------------

                "montant_total": str(
                    ligne.montant_total
                    or Decimal("0.00")
                ),
            })

        # =====================================================
        # 6. CLIENT
        # =====================================================

        client = getattr(
            vente,
            "client",
            None,
        )

        # =====================================================
        # 7. RESPONSE
        # =====================================================

        return Response(
            {
                "message": (
                    "Vente créée avec succès."
                ),

                "vente_id": vente.id,

                "numero_vente": (
                    vente.numero_vente
                ),

                "facture": {
                    "facture_id": (
                        facture.id
                    ),

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

                    "taux_tva": str(
                        facture.taux_tva
                    ),

                    "montant_tva": str(
                        facture.montant_tva
                    ),

                    "montant_total": str(
                        facture.montant_total
                    ),
                },

                "audit_created": bool(
                    audit_created
                ),

                "bijouterie": {
                    "id": (
                        facture.bijouterie_id
                    ),

                    "nom": getattr(
                        facture.bijouterie,
                        "nom",
                        None,
                    ),
                },

                "client": {
                    "id": (
                        client.id
                        if client
                        else None
                    ),

                    "nom": (
                        getattr(
                            client,
                            "nom",
                            None,
                        )
                        if client
                        else None
                    ),

                    "prenom": (
                        getattr(
                            client,
                            "prenom",
                            None,
                        )
                        if client
                        else None
                    ),

                    "telephone": (
                        getattr(
                            client,
                            "telephone",
                            None,
                        )
                        if client
                        else None
                    ),
                },

                "lignes": lignes,
            },
            status=(
                status.HTTP_201_CREATED
            ),
        )
        


class VenteListAPIView(APIView):

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Lister les ventes",
        operation_description="""
Liste les ventes selon le rôle connecté.

Règles :
- admin : voit toutes les ventes
- manager : voit les ventes de ses bijouteries
- vendor : voit seulement ses propres ventes
- cashier : voit les ventes de sa bijouterie

La liste est limitée aux ventes de l’année en cours.

Filtres disponibles :
- numero_vente
- client_q
- vendor_id
- status_facture
- page
- page_size
        """,
        manual_parameters=[
            openapi.Parameter(
                "numero_vente",
                openapi.IN_QUERY,
                description="Recherche par numéro de vente",
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
                "vendor_id",
                openapi.IN_QUERY,
                description="Filtrer par vendeur",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "status_facture",
                openapi.IN_QUERY,
                description=(
                    "Statut facture : "
                    "non_paye, partiel ou paye"
                ),
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
                description="Nombre d’éléments par page",
                type=openapi.TYPE_INTEGER,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Liste des ventes",
            ),
            400: "Erreur de filtre",
            403: "Accès refusé",
        },
        tags=["Ventes"],
    )
    def get(self, request):

        user = request.user

        role = (
            get_role_name(user)
            or ""
        ).lower().strip()

        # =====================================================
        # 1. RÔLES AUTORISÉS
        # =====================================================

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
        # 2. PROFIL VENDEUR CONNECTÉ
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
                and getattr(
                    my_vendor,
                    "verifie",
                    False,
                )
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
                "lignes",
                "lignes__produit_line",
                "lignes__produit_line__produit",
                "lignes__produit_line__lot",
                "lignes__vendor",
                "lignes__vendor__user",
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
        # 4. VENDEUR : UNIQUEMENT SES VENTES
        # =====================================================

        if role == ROLE_VENDOR:
            qs = qs.filter(
                vendor_id=my_vendor.id,
            )

        # =====================================================
        # 5. ANNÉE EN COURS
        # =====================================================

        today = timezone.localdate()

        start_date = timezone.make_aware(
            datetime(
                today.year,
                1,
                1,
            ),
            timezone.get_current_timezone(),
        )

        qs = qs.filter(
            created_at__gte=start_date,
        )

        # =====================================================
        # 6. FILTRE NUMÉRO DE VENTE
        # =====================================================

        numero_vente = (
            request.query_params
            .get(
                "numero_vente",
                "",
            )
            .strip()
        )

        if numero_vente:
            qs = qs.filter(
                numero_vente__icontains=numero_vente,
            )

        # =====================================================
        # 7. FILTRE CLIENT
        # =====================================================

        client_q = (
            request.query_params
            .get(
                "client_q",
                "",
            )
            .strip()
        )

        if client_q:
            qs = qs.filter(
                Q(
                    client__nom__icontains=client_q
                )
                |
                Q(
                    client__prenom__icontains=client_q
                )
                |
                Q(
                    client__telephone__icontains=client_q
                )
            )

        # =====================================================
        # 8. FILTRE VENDEUR
        # =====================================================

        vendor_id_raw = (
            request.query_params.get(
                "vendor_id"
            )
        )

        if vendor_id_raw not in {
            None,
            "",
        }:

            try:
                vendor_id = int(
                    vendor_id_raw
                )

            except (
                TypeError,
                ValueError,
            ):
                return error_response(
                    code="INVALID_VENDOR_ID",
                    message=(
                        "vendor_id doit être "
                        "un entier positif."
                    ),
                )

            if vendor_id <= 0:
                return error_response(
                    code="INVALID_VENDOR_ID",
                    message=(
                        "vendor_id doit être "
                        "un entier positif."
                    ),
                )

            # -------------------------------------------------
            # Un vendeur ne peut demander les ventes
            # d'un autre vendeur.
            # -------------------------------------------------

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
                vendor_id=vendor_id,
            )

        # =====================================================
        # 9. FILTRE STATUT FACTURE
        # =====================================================

        status_facture = (
            request.query_params
            .get(
                "status_facture",
                "",
            )
            .strip()
        )

        allowed_invoice_statuses = {
            Facture.STAT_NON_PAYE,
            Facture.STAT_PARTIEL,
            Facture.STAT_PAYE,
        }

        if status_facture:

            if (
                status_facture
                not in allowed_invoice_statuses
            ):
                return error_response(
                    code="INVALID_INVOICE_STATUS",
                    message=(
                        "status_facture invalide. "
                        "Utiliser non_paye, "
                        "partiel ou paye."
                    ),
                )

            qs = qs.filter(
                facture_vente__status=status_facture,
            )

        # =====================================================
        # 10. PAGINATION
        # =====================================================

        def parse_positive_int(
            name: str,
            default: int,
        ) -> int:

            raw_value = (
                request.query_params.get(
                    name
                )
            )

            if raw_value in {
                None,
                "",
            }:
                return default

            try:
                value = int(
                    raw_value
                )

            except (
                TypeError,
                ValueError,
            ):
                return default

            return max(
                1,
                value,
            )

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
                    "results": [],
                },
                status=status.HTTP_200_OK,
            )

        # =====================================================
        # 12. PAGE
        # =====================================================

        try:
            page_obj = paginator.page(
                page
            )

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
        # 14. RESPONSE
        # =====================================================

        return Response(
            {
                "count": paginator.count,
                "page": page_obj.number,
                "page_size": page_size,
                "num_pages": paginator.num_pages,
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )
        


class ListFacturesAPayerView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        role = (
            get_role_name(user)
            or ""
        ).lower().strip()

        # =====================================================
        # 1. CONTRÔLE RÔLE
        # =====================================================

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
                "paiements",

                # ---------------------------------------------
                # Lignes de vente
                # ---------------------------------------------
                "vente__lignes",
                "vente__lignes__vendor",
                "vente__lignes__vendor__user",

                # ---------------------------------------------
                # ProduitLine = source de vérité
                # ---------------------------------------------
                "vente__lignes__produit_line",
                "vente__lignes__produit_line__lot",

                # ---------------------------------------------
                # Produit dérivé de ProduitLine
                # ---------------------------------------------
                "vente__lignes__produit_line__produit",
                "vente__lignes__produit_line__produit__categorie",
                "vente__lignes__produit_line__produit__marque",
                "vente__lignes__produit_line__produit__purete",
                "vente__lignes__produit_line__produit__modele",
            )
            .filter(
                status__in=[
                    Facture.STAT_NON_PAYE,
                    Facture.STAT_PARTIEL,
                ]
            )
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
        # 4. VENDEUR : UNIQUEMENT SES PROPRES FACTURES
        # =====================================================

        if role == ROLE_VENDOR:

            vendor = getattr(
                user,
                "staff_vendor_profile",
                None,
            )

            if not (
                vendor
                and getattr(
                    vendor,
                    "verifie",
                    False,
                )
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
                vente__vendor_id=vendor.id,
            )

        # =====================================================
        # 5. ANNÉE EN COURS
        # =====================================================

        today = timezone.localdate()

        start_date = timezone.make_aware(
            datetime(
                today.year,
                1,
                1,
            ),
            timezone.get_current_timezone(),
        )

        qs = qs.filter(
            date_creation__gte=start_date,
        )

        # =====================================================
        # 6. FILTRE NUMÉRO FACTURE
        # =====================================================

        numero = (
            request.query_params
            .get(
                "numero_facture",
                "",
            )
            .strip()
        )

        if numero:
            qs = qs.filter(
                numero_facture__icontains=numero,
            )

        # =====================================================
        # 7. FILTRE CLIENT
        # =====================================================

        client_q = (
            request.query_params
            .get(
                "client_q",
                "",
            )
            .strip()
        )

        if client_q:
            qs = qs.filter(
                Q(
                    vente__client__nom__icontains=client_q
                )
                |
                Q(
                    vente__client__prenom__icontains=client_q
                )
                |
                Q(
                    vente__client__telephone__icontains=client_q
                )
            )

        # =====================================================
        # 8. FILTRE MODE DE PAIEMENT
        # =====================================================

        payment_mode = (
            request.query_params
            .get(
                "payment_mode",
                "",
            )
            .strip()
        )

        if payment_mode:
            qs = (
                qs
                .filter(
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
            value = request.query_params.get(
                name
            )

            if value in {
                None,
                "",
            }:
                return default

            try:
                value = int(value)

            except (
                TypeError,
                ValueError,
            ):
                return default

            return max(
                1,
                value,
            )

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
                    "results": [],
                },
                status=status.HTTP_200_OK,
            )

        # =====================================================
        # 12. PAGE
        # =====================================================

        try:
            page_obj = paginator.page(
                page
            )

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
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )
        


class ListFacturePayeesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        role = (
            get_role_name(user)
            or ""
        ).lower().strip()

        # =====================================================
        # 1. CONTRÔLE RÔLE
        # =====================================================

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

        # =====================================================
        # 2. PROFIL VENDEUR CONNECTÉ
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
                and getattr(
                    my_vendor,
                    "verifie",
                    False,
                )
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
            Facture.objects
            .select_related(
                "bijouterie",
                "vente",
                "vente__client",
                "vente__vendor",
                "vente__vendor__user",
            )
            .prefetch_related(
                "paiements",

                # ---------------------------------------------
                # Ligne de vente / vendeur
                # ---------------------------------------------
                "vente__lignes",
                "vente__lignes__vendor",
                "vente__lignes__vendor__user",

                # ---------------------------------------------
                # ProduitLine = source de vérité
                # ---------------------------------------------
                "vente__lignes__produit_line",
                "vente__lignes__produit_line__lot",

                # ---------------------------------------------
                # Produit dérivé de ProduitLine
                # ---------------------------------------------
                "vente__lignes__produit_line__produit",
                "vente__lignes__produit_line__produit__categorie",
                "vente__lignes__produit_line__produit__marque",
                "vente__lignes__produit_line__produit__purete",
                "vente__lignes__produit_line__produit__modele",
            )
            .filter(
                status=Facture.STAT_PAYE,
            )
        )

        # =====================================================
        # 4. SCOPE BIJOUTERIE
        # =====================================================

        qs = qs.filter(
            scope_bijouterie_q(
                user,
                field="bijouterie_id",
            )
        )

        # =====================================================
        # 5. VENDEUR : UNIQUEMENT SES PROPRES FACTURES
        # =====================================================

        if role == ROLE_VENDOR:
            qs = qs.filter(
                vente__vendor_id=my_vendor.id,
            )

        # =====================================================
        # 6. ANNÉE EN COURS
        # =====================================================

        today = timezone.localdate()

        start_date = timezone.make_aware(
            datetime(
                today.year,
                1,
                1,
            ),
            timezone.get_current_timezone(),
        )

        qs = qs.filter(
            date_creation__gte=start_date,
        )

        # =====================================================
        # 7. FILTRE NUMÉRO FACTURE
        # =====================================================

        numero = (
            request.query_params
            .get(
                "numero_facture",
                "",
            )
            .strip()
        )

        if numero:
            qs = qs.filter(
                numero_facture__icontains=numero,
            )

        # =====================================================
        # 8. FILTRE VENDEUR
        # =====================================================

        vendor_id_raw = (
            request.query_params.get(
                "vendor_id"
            )
        )

        if vendor_id_raw not in {
            None,
            "",
        }:
            try:
                vendor_id = int(
                    vendor_id_raw
                )

            except (
                TypeError,
                ValueError,
            ):
                return error_response(
                    code="INVALID_VENDOR_ID",
                    message=(
                        "vendor_id doit être "
                        "un entier positif."
                    ),
                )

            if vendor_id <= 0:
                return error_response(
                    code="INVALID_VENDOR_ID",
                    message=(
                        "vendor_id doit être "
                        "un entier positif."
                    ),
                )

            # =================================================
            # VENDEUR : IL NE PEUT FILTRER QUE LUI-MÊME
            # =================================================

            if (
                role == ROLE_VENDOR
                and vendor_id != my_vendor.id
            ):
                return error_response(
                    code="VENDOR_SCOPE_FORBIDDEN",
                    message=(
                        "Un vendeur ne peut filtrer "
                        "que ses propres factures."
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )

            # =================================================
            # MANAGER : VENDEUR DANS SES BIJOUTERIES
            # =================================================

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
                    return error_response(
                        code="INVALID_MANAGER_PROFILE",
                        message="Profil manager invalide.",
                        status_code=status.HTTP_403_FORBIDDEN,
                    )

                vendor_allowed = (
                    manager_profile
                    .bijouteries
                    .filter(
                        vendors__id=vendor_id
                    )
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

            # =================================================
            # FILTRE VENDEUR
            #
            # Une vente possède déjà son vendeur principal.
            # Il n'est donc plus nécessaire d'utiliser
            # Exists(VenteProduit...).
            # =================================================

            qs = qs.filter(
                vente__vendor_id=vendor_id,
            )

        # =====================================================
        # 9. FILTRE CLIENT
        # =====================================================

        client_q = (
            request.query_params
            .get(
                "client_q",
                "",
            )
            .strip()
        )

        if client_q:
            qs = qs.filter(
                Q(
                    vente__client__nom__icontains=client_q
                )
                |
                Q(
                    vente__client__prenom__icontains=client_q
                )
                |
                Q(
                    vente__client__telephone__icontains=client_q
                )
            )

        # =====================================================
        # 10. FILTRE MODE DE PAIEMENT
        # =====================================================

        payment_mode = (
            request.query_params
            .get(
                "payment_mode",
                "",
            )
            .strip()
        )

        if payment_mode:
            qs = (
                qs
                .filter(
                    paiements__lignes__mode_paiement__code__iexact=(
                        payment_mode
                    )
                )
                .distinct()
            )

        # =====================================================
        # 11. TRI
        # =====================================================

        qs = qs.order_by(
            "-date_creation",
            "-id",
        )

        # =====================================================
        # 12. PAGINATION
        # =====================================================

        def parse_positive_int(
            name: str,
            default: int,
        ) -> int:
            value = request.query_params.get(
                name
            )

            if value in {
                None,
                "",
            }:
                return default

            try:
                value = int(value)

            except (
                TypeError,
                ValueError,
            ):
                return default

            return max(
                1,
                value,
            )

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
        # 13. AUCUN RÉSULTAT
        # =====================================================

        if paginator.count == 0:
            return Response(
                {
                    "count": 0,
                    "page": 1,
                    "page_size": page_size,
                    "num_pages": 0,
                    "results": [],
                },
                status=status.HTTP_200_OK,
            )

        # =====================================================
        # 14. PAGE
        # =====================================================

        try:
            page_obj = paginator.page(
                page
            )

        except EmptyPage:
            page_obj = paginator.page(
                paginator.num_pages
            )

        # =====================================================
        # 15. SERIALIZATION
        # =====================================================

        serializer = FactureListSerializer(
            page_obj.object_list,
            many=True,
        )

        # =====================================================
        # 16. RESPONSE
        # =====================================================

        return Response(
            {
                "count": paginator.count,
                "page": page_obj.number,
                "page_size": page_size,
                "num_pages": paginator.num_pages,
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )
        


class PaiementFactureMultiModeView(APIView):

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
        operation_summary="Paiement facture multi-mode",
        operation_description="""
Permet au manager ou au caissier d'encaisser une facture.

### Règles
- Seuls le manager et le caissier peuvent effectuer un paiement.
- L'utilisateur doit avoir accès à la bijouterie de la facture.
- La facture doit être encore payable.
- Un montant doit être strictement supérieur à zéro.
- Le cumul du paiement ne peut pas dépasser le reste à payer.
- Un même mode de paiement ne peut apparaître qu'une seule fois.
- Les modes nécessitant une référence doivent recevoir une référence.
- Pour `depot`, `numero_compte` est obligatoire.
- Le compte dépôt doit exister.
- Le compte dépôt doit appartenir à la même bijouterie.
- Le solde du compte dépôt doit être suffisant.
- Le retrait dépôt est effectué avec verrouillage transactionnel.
- Lorsque la facture est totalement payée, le stock vendeur est consommé.
- Le PDF définitif est généré uniquement lorsque la facture est payée.
        """,
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=[
                "numero_facture",
                "lignes",
            ],
            properties={
                "numero_facture": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    example="FAC-20260902-0003",
                ),
                "client": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "nom": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            example="Diop",
                        ),
                        "prenom": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            example="Awa",
                        ),
                        "telephone": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            example="770000000",
                        ),
                    },
                ),
                "lignes": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        required=[
                            "mode",
                            "montant",
                        ],
                        properties={
                            "mode": openapi.Schema(
                                type=openapi.TYPE_STRING,
                                example="cash",
                                description=(
                                    "Code du mode : cash, wave, "
                                    "orange_money, tpe, depot..."
                                ),
                            ),
                            "montant": openapi.Schema(
                                type=openapi.TYPE_NUMBER,
                                example=10000,
                            ),
                            "numero_compte": openapi.Schema(
                                type=openapi.TYPE_STRING,
                                example="DEP-2026-00045",
                                description=(
                                    "Obligatoire uniquement pour "
                                    "le mode compte dépôt."
                                ),
                            ),
                            "reference": openapi.Schema(
                                type=openapi.TYPE_STRING,
                                example="WAVE-123456",
                            ),
                            "provider_reference": openapi.Schema(
                                type=openapi.TYPE_STRING,
                                example="AUTH-458796",
                            ),
                        },
                    ),
                ),
            },
        ),
        responses={
            201: openapi.Response(
                description="Paiement effectué avec succès."
            ),
            400: openapi.Response(
                description=(
                    "Erreur de validation ou "
                    "solde insuffisant."
                )
            ),
            403: openapi.Response(
                description="Accès refusé."
            ),
            404: openapi.Response(
                description=(
                    "Facture ou compte introuvable."
                )
            ),
        },
        tags=["Paiements"],
    )
    @transaction.atomic
    def post(self, request):

        # =====================================================
        # 1. RÔLE
        # =====================================================

        user = request.user

        role = (
            get_role_name(user)
            or ""
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

        # =====================================================
        # 2. DONNÉES ENTRANTES
        # =====================================================

        numero_facture = str(
            request.data.get(
                "numero_facture"
            )
            or ""
        ).strip()

        client_data = (
            request.data.get("client")
            or {}
        )

        lignes_data = (
            request.data.get("lignes")
            or []
        )

        if not numero_facture:
            return error_response(
                code="NUMERO_FACTURE_REQUIRED",
                message=(
                    "Le numéro de facture est obligatoire."
                ),
            )

        if (
            not isinstance(lignes_data, list)
            or not lignes_data
        ):
            return error_response(
                code="PAYMENT_LINES_REQUIRED",
                message=(
                    "Au moins une ligne de paiement "
                    "est obligatoire."
                ),
            )

        # =====================================================
        # 3. FACTURE + VERROU
        # =====================================================

        facture = (
            Facture.objects
            .select_for_update()
            .select_related(
                "vente",
                "vente__client",
                "vente__vendor",
                "bijouterie",
            )
            .prefetch_related(
                "paiements__lignes",
            )
            .filter(
                numero_facture__iexact=numero_facture,
            )
            .first()
        )

        if not facture:
            return error_response(
                code="FACTURE_NOT_FOUND",
                message=(
                    f"Facture introuvable : "
                    f"{numero_facture}."
                ),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # =====================================================
        # 4. SCOPE BIJOUTERIE
        # =====================================================

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

        # =====================================================
        # 5. FACTURE PAYABLE
        # =====================================================

        try:
            validate_facture_payable(
                facture
            )

        except DjangoValidationError as exc:
            return error_response(
                code="FACTURE_NOT_PAYABLE",
                message=(
                    "Cette facture ne peut pas "
                    "être encaissée."
                ),
                details=(
                    self._validation_error_detail(exc)
                ),
            )

        if facture.status == Facture.STAT_PAYE:
            return error_response(
                code="FACTURE_ALREADY_PAID",
                message="Cette facture est déjà payée.",
            )

        reste_a_payer = Decimal(
            str(
                facture.reste_a_payer
                or "0.00"
            )
        )

        if reste_a_payer <= Decimal("0.00"):
            return error_response(
                code="NOTHING_TO_PAY",
                message=(
                    "Cette facture ne présente "
                    "aucun reste à payer."
                ),
            )

        # =====================================================
        # 6. CLIENT
        # =====================================================

        try:
            client = upsert_client_for_payment(
                facture=facture,
                client_data=client_data,
            )

        except DjangoValidationError as exc:
            return error_response(
                code="CLIENT_INVALID",
                message=(
                    "Les informations du client "
                    "sont invalides."
                ),
                details=(
                    self._validation_error_detail(exc)
                ),
            )

        # =====================================================
        # 7. NORMALISATION DES LIGNES
        # =====================================================

        normalized_lignes = []

        total_paiement = Decimal(
            "0.00"
        )

        modes_utilises = set()

        for index, raw_item in enumerate(
            lignes_data,
            start=1,
        ):

            if not isinstance(raw_item, dict):
                return error_response(
                    code="INVALID_PAYMENT_LINE",
                    message=(
                        f"La ligne de paiement "
                        f"{index} est invalide."
                    ),
                )

            # =================================================
            # MODE
            # =================================================

            mode_code = str(
                raw_item.get("mode")
                or ""
            ).lower().strip()

            if not mode_code:
                return error_response(
                    code="PAYMENT_MODE_REQUIRED",
                    message=(
                        "Le mode de paiement est "
                        f"obligatoire à la ligne {index}."
                    ),
                )

            if mode_code in modes_utilises:
                return error_response(
                    code="DUPLICATE_PAYMENT_MODE",
                    message=(
                        f"Le mode '{mode_code}' est "
                        "présent plusieurs fois. "
                        "Regroupez les montants."
                    ),
                    details={
                        "mode": mode_code,
                    },
                )

            modes_utilises.add(
                mode_code
            )

            # =================================================
            # MONTANT
            # =================================================

            try:
                montant = Decimal(
                    str(
                        raw_item.get("montant")
                        or "0"
                    )
                )

            except (
                InvalidOperation,
                TypeError,
                ValueError,
            ):
                return error_response(
                    code="INVALID_AMOUNT",
                    message=(
                        f"Montant invalide à "
                        f"la ligne {index}."
                    ),
                )

            if montant <= Decimal("0.00"):
                return error_response(
                    code="AMOUNT_MUST_BE_POSITIVE",
                    message=(
                        f"Le montant de la ligne "
                        f"{index} doit être "
                        "supérieur à zéro."
                    ),
                )

            # =================================================
            # MODE ACTIF
            # =================================================

            mode_obj = (
                ModePaiement.objects
                .filter(
                    code__iexact=mode_code,
                    active=True,
                )
                .first()
            )

            if not mode_obj:
                return error_response(
                    code="INVALID_PAYMENT_MODE",
                    message=(
                        "Mode de paiement invalide "
                        f"ou inactif : {mode_code}."
                    ),
                    details={
                        "mode": mode_code,
                    },
                )

            # =================================================
            # RÉFÉRENCES
            # =================================================

            reference = str(
                raw_item.get("reference")
                or ""
            ).strip()

            provider_reference = str(
                raw_item.get(
                    "provider_reference"
                )
                or ""
            ).strip()

            if (
                mode_obj.necessite_reference
                and not reference
                and not provider_reference
            ):
                return error_response(
                    code="PAYMENT_REFERENCE_REQUIRED",
                    message=(
                        "Une référence est obligatoire "
                        f"pour le mode '{mode_obj.nom}'."
                    ),
                    details={
                        "mode": mode_obj.code,
                    },
                )

            numero_compte = str(
                raw_item.get(
                    "numero_compte"
                )
                or ""
            ).strip()

            compte = None

            # =================================================
            # COMPTE DÉPÔT
            # =================================================

            if mode_obj.est_mode_depot:

                if not numero_compte:
                    return error_response(
                        code="DEPOT_ACCOUNT_REQUIRED",
                        message=(
                            "Le numéro de compte dépôt "
                            "est obligatoire."
                        ),
                    )

                compte = (
                    CompteDepot.objects
                    .select_for_update()
                    .select_related(
                        "client",
                        "client__bijouterie",
                    )
                    .filter(
                        numero_compte__iexact=(
                            numero_compte
                        )
                    )
                    .first()
                )

                if not compte:
                    return error_response(
                        code="DEPOT_ACCOUNT_NOT_FOUND",
                        message=(
                            "Aucun compte dépôt trouvé "
                            "avec le numéro "
                            f"{numero_compte}."
                        ),
                        status_code=(
                            status.HTTP_404_NOT_FOUND
                        ),
                        details={
                            "numero_compte": (
                                numero_compte
                            ),
                        },
                    )

                if not compte.client_id:
                    return error_response(
                        code=(
                            "DEPOT_ACCOUNT_WITHOUT_CLIENT"
                        ),
                        message=(
                            "Ce compte dépôt n'est "
                            "associé à aucun client."
                        ),
                        details={
                            "numero_compte": (
                                numero_compte
                            ),
                        },
                    )

                # =============================================
                # BIJOUTERIE DU COMPTE
                # =============================================

                compte_bijouterie_id = getattr(
                    compte.client,
                    "bijouterie_id",
                    None,
                )

                if (
                    compte_bijouterie_id
                    and compte_bijouterie_id
                    != facture.bijouterie_id
                ):
                    return error_response(
                        code=(
                            "DEPOT_ACCOUNT_OUT_OF_SCOPE"
                        ),
                        message=(
                            "Ce compte dépôt appartient "
                            "à une autre bijouterie."
                        ),
                        status_code=(
                            status.HTTP_403_FORBIDDEN
                        ),
                        details={
                            "numero_compte": (
                                numero_compte
                            ),
                        },
                    )

                # =============================================
                # SOLDE
                # =============================================

                solde_disponible = Decimal(
                    str(
                        compte.solde
                        or "0.00"
                    )
                )

                if montant > solde_disponible:

                    montant_manquant = (
                        montant
                        - solde_disponible
                    )

                    return error_response(
                        code=(
                            "SOLDE_COMPTE_DEPOT_INSUFFISANT"
                        ),
                        message=(
                            "Solde insuffisant sur "
                            "le compte dépôt."
                        ),
                        details={
                            "numero_compte": (
                                compte.numero_compte
                            ),
                            "solde_disponible": str(
                                solde_disponible
                            ),
                            "montant_demande": str(
                                montant
                            ),
                            "montant_manquant": str(
                                montant_manquant
                            ),
                        },
                    )

            else:

                # =============================================
                # numero_compte interdit hors mode dépôt
                # =============================================

                if numero_compte:
                    return error_response(
                        code=(
                            "DEPOT_ACCOUNT_NOT_ALLOWED"
                        ),
                        message=(
                            "numero_compte est réservé "
                            "au mode compte dépôt."
                        ),
                        details={
                            "mode": mode_obj.code,
                        },
                    )

            # =================================================
            # NORMALISATION
            # =================================================

            total_paiement += montant

            normalized_lignes.append(
                {
                    "mode_obj": mode_obj,
                    "mode": mode_obj.code,
                    "montant": montant,
                    "reference": (
                        reference
                        or None
                    ),
                    "provider_reference": (
                        provider_reference
                        or None
                    ),
                    "numero_compte": (
                        numero_compte
                        or None
                    ),
                    "compte": compte,
                }
            )

        # =====================================================
        # 8. TOTAL VS RESTE À PAYER
        # =====================================================

        if total_paiement > reste_a_payer:

            depassement = (
                total_paiement
                - reste_a_payer
            )

            return error_response(
                code="PAYMENT_EXCEEDS_BALANCE",
                message=(
                    "Le montant reçu dépasse "
                    "le reste à payer."
                ),
                details={
                    "reste_a_payer": str(
                        reste_a_payer
                    ),
                    "montant_recu": str(
                        total_paiement
                    ),
                    "depassement": str(
                        depassement
                    ),
                },
            )

        # =====================================================
        # 9. CAISSIER
        # =====================================================

        cashier = None

        if role == ROLE_CASHIER:

            cashier = (
                Cashier.objects
                .select_related(
                    "bijouterie",
                    "user",
                )
                .filter(
                    user=user,
                    verifie=True,
                )
                .first()
            )

            if not cashier:
                return error_response(
                    code="CASHIER_PROFILE_INVALID",
                    message=(
                        "Profil caissier introuvable "
                        "ou désactivé."
                    ),
                    status_code=(
                        status.HTTP_403_FORBIDDEN
                    ),
                )

            if (
                cashier.bijouterie_id
                != facture.bijouterie_id
            ):
                return error_response(
                    code="CASHIER_OUT_OF_SCOPE",
                    message=(
                        "Cette facture n'appartient "
                        "pas à la bijouterie "
                        "du caissier."
                    ),
                    status_code=(
                        status.HTTP_403_FORBIDDEN
                    ),
                )

        # =====================================================
        # 10. CRÉATION PAIEMENT
        # =====================================================

        paiement = Paiement.objects.create(
            facture=facture,
            created_by=user,
            cashier=cashier,
        )

        lignes_creees = []

        # =====================================================
        # 11. LIGNES + RETRAIT COMPTE DÉPÔT
        # =====================================================

        for item in normalized_lignes:

            mode_obj = item[
                "mode_obj"
            ]

            # =================================================
            # COMPTE DÉPÔT
            # =================================================

            if mode_obj.est_mode_depot:

                compte = item[
                    "compte"
                ]

                # ---------------------------------------------
                # Le compte a déjà été verrouillé par
                # select_for_update().
                # ---------------------------------------------

                compte.refresh_from_db()

                solde_disponible = Decimal(
                    str(
                        compte.solde
                        or "0.00"
                    )
                )

                if (
                    item["montant"]
                    > solde_disponible
                ):
                    transaction.set_rollback(
                        True
                    )

                    return error_response(
                        code=(
                            "SOLDE_COMPTE_DEPOT_INSUFFISANT"
                        ),
                        message=(
                            "Le solde du compte dépôt "
                            "a changé et est devenu "
                            "insuffisant."
                        ),
                        details={
                            "numero_compte": (
                                compte.numero_compte
                            ),
                            "solde_disponible": str(
                                solde_disponible
                            ),
                            "montant_demande": str(
                                item["montant"]
                            ),
                        },
                    )

                try:
                    tx = effectuer_retrait(
                        compte_id=compte.id,
                        montant=item["montant"],
                        user=user,
                        reference=(
                            "FACTURE-"
                            f"{facture.numero_facture}"
                        ),
                        commentaire=(
                            "Paiement facture "
                            f"{facture.numero_facture}"
                        ),
                    )

                except DjangoValidationError as exc:

                    transaction.set_rollback(
                        True
                    )

                    return error_response(
                        code="DEPOT_WITHDRAWAL_FAILED",
                        message=(
                            "Le retrait du compte dépôt "
                            "a échoué."
                        ),
                        details=(
                            self
                            ._validation_error_detail(
                                exc
                            )
                        ),
                    )

                ligne = (
                    PaiementLigne.objects.create(
                        paiement=paiement,
                        mode_paiement=mode_obj,
                        montant_paye=(
                            item["montant"]
                        ),
                        reference=(
                            "COMPTE_DEPOT-"
                            f"{compte.numero_compte}"
                        ),
                        compte_depot=compte,
                        transaction_depot=tx,
                    )
                )

                transaction.on_commit(
                    lambda tx=tx: (
                        send_compte_depot_facture_notification(
                            tx
                        )
                    )
                )

            # =================================================
            # AUTRES MODES
            # =================================================

            else:

                ligne = (
                    PaiementLigne.objects.create(
                        paiement=paiement,
                        mode_paiement=mode_obj,
                        montant_paye=(
                            item["montant"]
                        ),
                        reference=(
                            item["reference"]
                        ),
                        provider_reference=(
                            item[
                                "provider_reference"
                            ]
                        ),
                    )
                )

            lignes_creees.append(
                ligne
            )

        # =====================================================
        # 12. STATUT FACTURE
        # =====================================================

        Facture.recompute_facture_status(
            facture
        )

        facture.refresh_from_db()

        # =====================================================
        # 13. PROFORMA -> FACTURE
        # =====================================================

        if (
            facture.type_facture
            == Facture.TYPE_PROFORMA
            and facture.status
            == Facture.STAT_PAYE
        ):
            facture.type_facture = (
                Facture.TYPE_FACTURE
            )

            facture.save(
                update_fields=[
                    "type_facture",
                ]
            )

        # =====================================================
        # 14. STOCK VENDEUR
        # =====================================================
        #
        # confirm_sale_out_from_vendor() doit maintenant
        # travailler uniquement avec :
        #
        # VenteProduit.produit_line
        #
        # puis :
        #
        # consume_vendor_stock(
        #     vendor=...,
        #     bijouterie=...,
        #     produit_line=ligne.produit_line,
        #     quantite=ligne.quantite,
        # )
        #
        # Aucun FIFO.
        # Aucun fallback par Produit.
        # =====================================================

        audit = {
            "created": 0,
            "already": 0,
            "lines_done": 0,
        }

        if (
            facture.status
            == Facture.STAT_PAYE
            and not facture.stock_consumed
        ):
            try:
                audit = (
                    confirm_sale_out_from_vendor(
                        facture=facture,
                        by_user=user,
                    )
                )

                facture.refresh_from_db()

            except DjangoValidationError as exc:

                transaction.set_rollback(
                    True
                )

                return error_response(
                    code="STOCK_CONSUMPTION_FAILED",
                    message=(
                        "La consommation du stock "
                        "vendeur a échoué."
                    ),
                    details=(
                        self
                        ._validation_error_detail(
                            exc
                        )
                    ),
                )

        # =====================================================
        # 15. PDF FINAL
        # =====================================================

        facture_pdf_url = None

        if facture.status == Facture.STAT_PAYE:

            if not facture.facture_pdf:

                if not facture.integrity_hash:
                    generate_facture_hash(
                        facture
                    )

                if not facture.qr_code_image:
                    generate_facture_qr(
                        facture
                    )

                generate_facture_pdf(
                    facture
                )

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

            except Exception:
                facture_pdf_url = None

            # =================================================
            # VERROUILLAGE FACTURE
            # =================================================

            if not facture.is_locked:

                facture.is_locked = True
                facture.locked_at = (
                    timezone.now()
                )

                facture.save(
                    update_fields=[
                        "is_locked",
                        "locked_at",
                    ]
                )

        # =====================================================
        # 16. URL FACTURE
        # =====================================================

        facture_download_url = (
            request.build_absolute_uri(
                reverse(
                    "facture-a5-paysage",
                    kwargs={
                        "numero_facture": (
                            facture.numero_facture
                        )
                    },
                )
            )
        )

        # =====================================================
        # 17. RÉPONSE
        # =====================================================

        return Response(
            {
                "status": "success",
                "message": (
                    "Paiement effectué avec succès."
                ),

                "paiement_id": paiement.id,

                "vente": {
                    "id": (
                        facture.vente_id
                        if facture.vente
                        else None
                    ),

                    "numero_vente": (
                        facture.vente.numero_vente
                        if facture.vente
                        else None
                    ),

                    "montant_total": (
                        str(
                            facture
                            .vente
                            .montant_total
                        )
                        if facture.vente
                        else "0.00"
                    ),
                },

                "facture": {
                    "id": facture.id,

                    "numero_facture": (
                        facture.numero_facture
                    ),

                    "type_facture": (
                        facture.type_facture
                    ),

                    "status": (
                        facture.status
                    ),

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
                    "id": (
                        client.id
                        if client
                        else None
                    ),

                    "nom": (
                        getattr(
                            client,
                            "nom",
                            None,
                        )
                        if client
                        else None
                    ),

                    "prenom": (
                        getattr(
                            client,
                            "prenom",
                            None,
                        )
                        if client
                        else None
                    ),

                    "telephone": (
                        getattr(
                            client,
                            "telephone",
                            None,
                        )
                        if client
                        else None
                    ),
                },

                "lignes": [
                    {
                        "id": ligne.id,

                        "mode_paiement": (
                            ligne
                            .mode_paiement
                            .code
                        ),

                        "montant_paye": str(
                            ligne.montant_paye
                        ),

                        "reference": (
                            ligne.reference
                        ),

                        "provider_reference": (
                            ligne
                            .provider_reference
                        ),

                        "numero_compte": (
                            ligne
                            .compte_depot
                            .numero_compte
                            if ligne.compte_depot_id
                            else None
                        ),
                    }
                    for ligne
                    in lignes_creees
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

# -------------------END PaiementFactureView-------------------


# PDF

def _can_access_facture(user, facture: Facture) -> bool:
    """
    Vérifie si l'utilisateur peut accéder à une facture.

    Règles :
    - admin   : accès à toutes les factures ;
    - manager : accès aux factures de ses bijouteries ;
    - cashier : accès aux factures de sa bijouterie ;
    - vendor  : accès uniquement aux factures de ses propres ventes.
    """

    if not user or not getattr(user, "is_authenticated", False):
        return False

    if not facture or not facture.bijouterie_id:
        return False

    role = (
        get_role_name(user)
        or ""
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
                manager_profile,
                "verifie",
                False,
            )
        ):
            return False

        return (
            manager_profile
            .bijouteries
            .filter(
                id=facture.bijouterie_id,
            )
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
                cashier_profile,
                "verifie",
                False,
            )
        ):
            return False

        cashier_bijouterie_id = getattr(
            cashier_profile,
            "bijouterie_id",
            None,
        )

        return (
            cashier_bijouterie_id
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
                vendor_profile,
                "verifie",
                False,
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

        # Sécurité supplémentaire :
        # la vente et le vendeur doivent appartenir
        # à la même bijouterie que la facture.
        if (
            vente.bijouterie_id
            != facture.bijouterie_id
        ):
            return False

        if (
            vendor_profile.bijouterie_id
            != facture.bijouterie_id
        ):
            return False

        # Le vendeur ne peut consulter que
        # les factures de ses propres ventes.
        return (
            vente.vendor_id
            == vendor_profile.id
        )

    # =====================================================
    # AUTRE RÔLE
    # =====================================================

    return False

class TicketProforma58mmView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary=(
            "Télécharger le ticket PROFORMA 58mm pour POS"
        ),
        operation_description="""
Génère un ticket PROFORMA au format ESC/POS 58mm.

### Utilisation

- Sans `debug` :
  retourne un fichier `.bin` destiné à l'imprimante thermique POS.

- Avec `?debug=1` :
  retourne une représentation texte lisible du ticket.

### Exemple

`/api/factures/FAC-20260509-0001/ticket-proforma-58mm/`

### Debug

`/api/factures/FAC-20260509-0001/ticket-proforma-58mm/?debug=1`
        """,
        manual_parameters=[
            openapi.Parameter(
                name="numero_facture",
                in_=openapi.IN_PATH,
                description="Numéro de la facture proforma",
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
                description="Ticket PROFORMA généré avec succès."
            ),
            400: "Aucune vente associée à cette facture.",
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
        # 1. FACTURE
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
                numero_facture__iexact=numero_facture,
            )
            .first()
        )

        if not facture:
            return error_response(
                code="FACTURE_NOT_FOUND",
                message=(
                    f"Facture introuvable : "
                    f"{numero_facture}."
                ),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # =====================================================
        # 2. PERMISSION
        # =====================================================

        if not _can_access_facture(
            request.user,
            facture,
        ):
            return error_response(
                code="FACTURE_ACCESS_DENIED",
                message=(
                    "Accès refusé à cette facture."
                ),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # 3. VENTE
        # =====================================================

        if not facture.vente_id:
            return error_response(
                code="FACTURE_WITHOUT_SALE",
                message=(
                    "Aucune vente associée "
                    "à cette facture."
                ),
            )

        # =====================================================
        # 4. TYPE DE FACTURE
        # =====================================================
        #
        # Cet endpoint est destiné au ticket PROFORMA.
        # On évite donc de générer ce ticket pour une facture
        # définitive déjà convertie.
        # =====================================================

        if (
            facture.type_facture
            != Facture.TYPE_PROFORMA
        ):
            return error_response(
                code="FACTURE_NOT_PROFORMA",
                message=(
                    "Cette facture n'est plus "
                    "une facture proforma."
                ),
            )

        # =====================================================
        # 5. BIJOUTERIE
        # =====================================================

        bijouterie = facture.bijouterie

        if not bijouterie:
            return error_response(
                code="FACTURE_WITHOUT_STORE",
                message=(
                    "Aucune bijouterie n'est associée "
                    "à cette facture."
                ),
            )

        shop_name = (
            getattr(
                bijouterie,
                "nom",
                None,
            )
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
        # 6. DATE LOCALE
        # =====================================================

        date_creation = facture.date_creation

        if date_creation:
            if timezone.is_aware(
                date_creation
            ):
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
        # 7. STATUT
        # =====================================================

        if (
            facture.status
            == Facture.STAT_NON_PAYE
        ):
            statut_txt = "NON PAYE"

        elif (
            facture.status
            == Facture.STAT_PARTIEL
        ):
            statut_txt = "PARTIEL"

        elif (
            facture.status
            == Facture.STAT_PAYE
        ):
            statut_txt = "PAYE"

        else:
            statut_txt = str(
                facture.status
                or ""
            ).upper()

        # =====================================================
        # 8. MONTANT À PAYER
        # =====================================================

        montant_a_payer = Decimal(
            str(
                facture.reste_a_payer
                or "0.00"
            )
        )

        # =====================================================
        # 9. MODE DEBUG
        # =====================================================

        if (
            request.query_params.get(
                "debug"
            )
            == "1"
        ):

            debug_text = (
                f"{shop_name.upper()}\n"
            )

            if shop_phone:
                debug_text += (
                    f"Tel: {shop_phone}\n"
                )

            debug_text += (
                f"{'-' * 42}\n"
                f"FACTURE PROFORMA    "
                f"N° {facture.numero_facture}\n"
                f"{'-' * 42}\n"
                f"DATE : {date_day_txt}"
                f"              "
                f"{time_txt}\n"
                f"ETAT : {statut_txt}\n"
                f"{'-' * 42}\n"
                f"MONTANT A PAYER\n"
                f"{montant_a_payer} FCFA\n"
                f"{'-' * 42}\n"
                f"Ticket PROFORMA a regler en caisse.\n"
                f"Merci pour votre confiance !"
            )

            return HttpResponse(
                debug_text,
                content_type=(
                    "text/plain; charset=utf-8"
                ),
            )

        # =====================================================
        # 10. GÉNÉRATION ESC/POS
        # =====================================================

        try:
            escpos_bytes = (
                build_escpos_ticket_proforma_58mm(
                    shop_name=shop_name,
                    shop_phone=shop_phone,
                    numero_facture=(
                        facture.numero_facture
                    ),
                    date_txt=date_txt,
                    montant_a_payer=(
                        montant_a_payer
                    ),
                    statut_txt=statut_txt,
                    note=(
                        "Ticket PROFORMA "
                        "a regler en caisse."
                    ),
                )
            )

        except Exception as exc:
            return error_response(
                code="PROFORMA_TICKET_GENERATION_FAILED",
                message=(
                    "Erreur lors de la génération "
                    "du ticket proforma."
                ),
                status_code=(
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
                details=str(exc),
            )

        # =====================================================
        # 11. VALIDATION DU RÉSULTAT
        # =====================================================

        if not escpos_bytes:
            return error_response(
                code="EMPTY_PROFORMA_TICKET",
                message=(
                    "Le ticket proforma généré "
                    "est vide."
                ),
                status_code=(
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
            )

        # =====================================================
        # 12. RÉPONSE POS
        # =====================================================

        response = HttpResponse(
            escpos_bytes,
            content_type="application/octet-stream",
        )

        response[
            "Content-Disposition"
        ] = (
            'inline; filename="'
            'ticket_proforma_'
            f'{facture.numero_facture}.bin"'
        )

        response[
            "Content-Length"
        ] = str(
            len(escpos_bytes)
        )

        response[
            "Cache-Control"
        ] = "no-store"

        return response


class TicketPaiement80mmESCPosView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary=(
            "Télécharger le ticket de paiement 80mm pour POS"
        ),
        operation_description="""
Génère un reçu de paiement au format ESC/POS 80mm.

### Règles

- Le ticket est disponible uniquement si la facture est entièrement payée.
- Le ticket correspond au dernier paiement enregistré.
- Sans `debug` : retourne un fichier `.bin` pour imprimante thermique POS.
- Avec `?debug=1` : affiche le contenu lisible du ticket.

### Exemple

`/api/factures/FAC-20260509-0001/ticket-paiement-80mm/`

### Debug

`/api/factures/FAC-20260509-0001/ticket-paiement-80mm/?debug=1`
        """,
        manual_parameters=[
            openapi.Parameter(
                name="numero_facture",
                in_=openapi.IN_PATH,
                description="Numéro de la facture",
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
                    "Ticket de paiement généré avec succès. "
                    "Retourne un fichier .bin ou du texte "
                    "si debug=1."
                )
            ),
            400: (
                "Facture non entièrement payée "
                "ou aucun paiement trouvé."
            ),
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
        # 1. FACTURE
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
                numero_facture__iexact=numero_facture,
            )
            .first()
        )

        if not facture:
            return error_response(
                code="FACTURE_NOT_FOUND",
                message=(
                    f"Facture introuvable : "
                    f"{numero_facture}."
                ),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # =====================================================
        # 2. PERMISSION
        # =====================================================

        if not _can_access_facture(
            request.user,
            facture,
        ):
            return error_response(
                code="FACTURE_ACCESS_DENIED",
                message=(
                    "Accès refusé à cette facture."
                ),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # 3. FACTURE ENTIÈREMENT PAYÉE
        # =====================================================

        reste_a_payer = Decimal(
            str(
                facture.reste_a_payer
                or "0.00"
            )
        )

        if (
            facture.status != Facture.STAT_PAYE
            or reste_a_payer > Decimal("0.00")
        ):
            return error_response(
                code="FACTURE_NOT_FULLY_PAID",
                message=(
                    "Le ticket de paiement 80mm "
                    "ne peut être imprimé que si "
                    "la facture est entièrement payée."
                ),
                details={
                    "status_facture": facture.status,
                    "reste_a_payer": str(
                        reste_a_payer
                    ),
                },
            )

        # =====================================================
        # 4. DERNIER PAIEMENT
        # =====================================================

        paiement = (
            Paiement.objects
            .filter(
                facture=facture,
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

        if not paiement:
            return error_response(
                code="PAYMENT_NOT_FOUND",
                message=(
                    "Aucun paiement trouvé "
                    "pour cette facture."
                ),
            )

        # =====================================================
        # 5. BIJOUTERIE
        # =====================================================

        bijouterie = facture.bijouterie

        if not bijouterie:
            return error_response(
                code="FACTURE_WITHOUT_STORE",
                message=(
                    "Aucune bijouterie n'est associée "
                    "à cette facture."
                ),
            )

        shop_name = (
            getattr(
                bijouterie,
                "nom",
                None,
            )
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
        # 6. MONTANT DU PAIEMENT
        # =====================================================
        #
        # Ici on imprime le montant du paiement sélectionné,
        # donc uniquement les lignes de CE paiement.
        # =====================================================

        montant_paye = (
            paiement.lignes.aggregate(
                total=Sum(
                    "montant_paye"
                )
            )["total"]
            or Decimal("0.00")
        )

        montant_paye = Decimal(
            str(montant_paye)
        )

        if montant_paye <= Decimal("0.00"):
            return error_response(
                code="PAYMENT_WITHOUT_AMOUNT",
                message=(
                    "Le paiement sélectionné "
                    "ne contient aucun montant valide."
                ),
            )

        # =====================================================
        # 7. GÉNÉRATION ESC/POS
        # =====================================================

        try:
            escpos_bytes = (
                build_escpos_recu_paiement_80mm(
                    shop_name=shop_name,
                    shop_phone=shop_phone,
                    numero_facture=(
                        facture.numero_facture
                    ),
                    date_paiement=(
                        paiement.date_paiement
                    ),
                    montant_paye=montant_paye,

                    # La facture est totalement payée.
                    reste_a_payer=None,
                )
            )

        except Exception as exc:
            return error_response(
                code="PAYMENT_TICKET_GENERATION_FAILED",
                message=(
                    "Erreur lors de la génération "
                    "du ticket de paiement."
                ),
                status_code=(
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
                details=str(exc),
            )

        # =====================================================
        # 8. VALIDATION DU TICKET
        # =====================================================

        if not escpos_bytes:
            return error_response(
                code="EMPTY_PAYMENT_TICKET",
                message=(
                    "Le ticket de paiement généré "
                    "est vide."
                ),
                status_code=(
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
            )

        # =====================================================
        # 9. MODE DEBUG
        # =====================================================

        if (
            request.query_params.get("debug")
            == "1"
        ):
            try:
                debug_text = escpos_bytes.decode(
                    "cp1252",
                    errors="ignore",
                )

            except Exception as exc:
                return error_response(
                    code="PAYMENT_TICKET_DECODE_FAILED",
                    message=(
                        "Impossible de convertir "
                        "le ticket en texte."
                    ),
                    status_code=(
                        status.HTTP_500_INTERNAL_SERVER_ERROR
                    ),
                    details=str(exc),
                )

            return HttpResponse(
                debug_text,
                content_type=(
                    "text/plain; charset=utf-8"
                ),
            )

        # =====================================================
        # 10. RÉPONSE ESC/POS
        # =====================================================

        response = HttpResponse(
            escpos_bytes,
            content_type="application/octet-stream",
        )

        response[
            "Content-Disposition"
        ] = (
            'inline; filename="'
            'ticket_paiement_'
            f'{facture.numero_facture}.bin"'
        )

        response[
            "Content-Length"
        ] = str(
            len(escpos_bytes)
        )

        response[
            "Cache-Control"
        ] = "no-store"

        return response
    

# class FactureA5PortraitView(APIView):
class FactureA5paysageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(
        self,
        request,
        numero_facture: str,
    ):

        # =====================================================
        # 1. FACTURE
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
                # Lignes de vente
                # ---------------------------------------------
                "vente__lignes",

                # ---------------------------------------------
                # ProduitLine = source de vérité
                # ---------------------------------------------
                "vente__lignes__produit_line",
                "vente__lignes__produit_line__lot",

                # ---------------------------------------------
                # Produit dérivé de ProduitLine
                # ---------------------------------------------
                "vente__lignes__produit_line__produit",
                "vente__lignes__produit_line__produit__purete",
                "vente__lignes__produit_line__produit__marque",
                "vente__lignes__produit_line__produit__categorie",
                "vente__lignes__produit_line__produit__modele",

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

        if not facture:
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
                message=(
                    "Accès refusé à cette facture."
                ),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # 4. VENTE
        # =====================================================

        if not facture.vente_id:
            return error_response(
                code="FACTURE_WITHOUT_SALE",
                message=(
                    "Aucune vente n'est associée "
                    "à cette facture."
                ),
            )

        # =====================================================
        # 5. DONNÉES PDF
        # =====================================================

        try:
            data = build_facture_pdf_data(
                facture
            )

        except Exception as exc:
            return error_response(
                code="FACTURE_PDF_DATA_FAILED",
                message=(
                    "Erreur lors de la préparation "
                    "des données de la facture."
                ),
                status_code=(
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
                details=str(exc),
            )

        # =====================================================
        # 6. GÉNÉRATION PDF
        # =====================================================

        buffer = BytesIO()

        try:
            build_facture_a5_portrait_pdf(
                buffer,
                data,
            )

        except Exception as exc:
            buffer.close()

            return error_response(
                code="FACTURE_PDF_GENERATION_FAILED",
                message=(
                    "Erreur lors de la génération "
                    "du PDF de la facture."
                ),
                status_code=(
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
                details=str(exc),
            )

        # =====================================================
        # 7. POSITIONNEMENT DU BUFFER
        # =====================================================

        buffer.seek(0)

        # =====================================================
        # 8. NOM DU FICHIER
        # =====================================================

        filename = (
            f"facture_"
            f"{facture.numero_facture}"
            f".pdf"
        )

        # =====================================================
        # 9. RÉPONSE PDF
        # =====================================================

        return FileResponse(
            buffer,
            as_attachment=True,
            filename=filename,
            content_type="application/pdf",
        )
        

class ExportFacturesExcelView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # =====================================================
        # 1. RÔLE
        # =====================================================

        role = (
            get_role_name(user)
            or ""
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
        # 2. QUERYSET
        # =====================================================
        #
        # Aucun prefetch ProduitLine n'est nécessaire ici :
        # export_factures_excel() n'utilise pas les lignes
        # de vente ni les produits.
        # =====================================================

        factures = (
            Facture.objects
            .select_related(
                "vente",
                "vente__client",
                "vente__vendor",
                "vente__vendor__user",
                "bijouterie",
            )
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
        #
        # Un vendeur ne peut exporter que les factures
        # correspondant à ses propres ventes.
        # Le contrôle se fait sur Vente.vendor.
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
                    message=(
                        "Profil vendeur introuvable."
                    ),
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
        # 6. EXPORT EXCEL
        # =====================================================

        return export_factures_excel(
            factures
        )


class ExportComptableView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # =====================================================
        # 1. RÔLE
        # =====================================================

        role = (
            get_role_name(user)
            or ""
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
        # 2. FACTURES PAYÉES
        # =====================================================

        factures = (
            Facture.objects
            .filter(
                status=Facture.STAT_PAYE,
            )
            .select_related(
                "bijouterie",
                "vente",
                "vente__client",
                "vente__vendor",
                "vente__vendor__user",
            )
            .prefetch_related(
                "paiements",
                "paiements__lignes",
                "paiements__lignes__mode_paiement",
            )
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
        #
        # Un vendeur ne peut exporter que les factures
        # provenant de ses propres ventes.
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
                    message=(
                        "Profil vendeur introuvable."
                    ),
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

        except Exception as exc:
            return error_response(
                code="ACCOUNTING_EXPORT_FAILED",
                message=(
                    "Erreur lors de la génération "
                    "de l'export comptable."
                ),
                status_code=(
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
                details=str(exc),
            )

        # =====================================================
        # 7. RÉPONSE EXCEL
        # =====================================================

        response = HttpResponse(
            content_type=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            )
        )

        response[
            "Content-Disposition"
        ] = (
            'attachment; '
            'filename="comptabilite.xlsx"'
        )

        try:
            wb.save(response)

        except Exception as exc:
            return error_response(
                code="ACCOUNTING_EXPORT_SAVE_FAILED",
                message=(
                    "Erreur lors de la création "
                    "du fichier Excel comptable."
                ),
                status_code=(
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
                details=str(exc),
            )

        return response


# ==========================================================
# HELPERS corrigés pour serializers
# ==========================================================
def _get_facture_locked(vente):
    """
    Récupère et verrouille la facture associée à la vente.

    Cette fonction doit être appelée à l'intérieur
    d'une transaction.atomic().
    """

    facture_id = getattr(
        vente,
        "facture_vente_id",
        None,
    )

    if not facture_id:
        facture = getattr(
            vente,
            "facture_vente",
            None,
        )

        facture_id = getattr(
            facture,
            "id",
            None,
        )

    if not facture_id:
        return None

    return (
        Facture.objects
        .select_for_update()
        .select_related(
            "vente",
            "bijouterie",
        )
        .get(
            id=facture_id,
        )
    )


def _validate_before_payment(facture):
    """
    Autorise la modification uniquement avant tout paiement,
    avant consommation du stock et avant verrouillage.
    """

    if not facture:
        return None

    if facture.status != Facture.STAT_NON_PAYE:
        return error_response(
            "FACTURE_NOT_EDITABLE",
            (
                "Action impossible : "
                "la facture n'est plus non payée."
            ),
            status.HTTP_400_BAD_REQUEST,
        )

    total_paye = Decimal(
        str(
            facture.total_paye
            or "0.00"
        )
    )

    if total_paye > Decimal("0.00"):
        return error_response(
            "FACTURE_HAS_PAYMENT",
            (
                "Action impossible : "
                "un paiement existe déjà."
            ),
            status.HTTP_400_BAD_REQUEST,
        )

    if facture.stock_consumed:
        return error_response(
            "STOCK_ALREADY_CONSUMED",
            (
                "Action impossible : "
                "le stock est déjà consommé."
            ),
            status.HTTP_400_BAD_REQUEST,
        )

    if facture.is_locked:
        return error_response(
            "FACTURE_LOCKED",
            (
                "Action impossible : "
                "la facture est verrouillée."
            ),
            status.HTTP_400_BAD_REQUEST,
        )

    return None


def _resolve_vendor_for_update(
    data,
    request,
    vente,
    role,
):
    user = request.user

    # =====================================================
    # VENDOR
    # =====================================================

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
                "VENDOR_PROFILE_NOT_FOUND",
                (
                    "Vous n'êtes pas associé à "
                    "un compte vendeur actif."
                ),
                status.HTTP_404_NOT_FOUND,
            )

        if vente.vendor_id != vendor.id:
            return None, error_response(
                "NOT_YOUR_SALE",
                (
                    "Vous ne pouvez modifier que "
                    "vos propres ventes."
                ),
                status.HTTP_403_FORBIDDEN,
            )

        return vendor, None

    # =====================================================
    # ADMIN / MANAGER / AUTRE RÔLE AUTORISÉ
    # =====================================================

    vendor_email = (
        data.get("vendor_email")
        or request.query_params.get(
            "vendor_email"
        )
    )

    if vendor_email:
        vendor = (
            Vendor.objects
            .select_related(
                "user",
                "bijouterie",
            )
            .filter(
                user__email__iexact=(
                    str(vendor_email).strip()
                ),
                verifie=True,
            )
            .first()
        )

        if not vendor:
            return None, error_response(
                "VENDOR_NOT_FOUND",
                (
                    "Vendeur introuvable "
                    "ou désactivé."
                ),
                status.HTTP_404_NOT_FOUND,
            )

    else:
        vendor = vente.vendor

        if not vendor:
            return None, error_response(
                "VENDOR_NOT_FOUND",
                "Aucun vendeur associé à la vente.",
                status.HTTP_400_BAD_REQUEST,
            )

        if not getattr(
            vendor,
            "verifie",
            False,
        ):
            return None, error_response(
                "VENDOR_NOT_VERIFIED",
                "Le vendeur est désactivé.",
                status.HTTP_400_BAD_REQUEST,
            )

    # =====================================================
    # MANAGER SCOPE
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
                manager_profile,
                "verifie",
                False,
            )
        ):
            return None, error_response(
                "MANAGER_PROFILE_INVALID",
                (
                    "Profil manager introuvable "
                    "ou désactivé."
                ),
                status.HTTP_403_FORBIDDEN,
            )

        allowed = (
            manager_profile
            .bijouteries
            .filter(
                id=vendor.bijouterie_id,
            )
            .exists()
        )

        if not allowed:
            return None, error_response(
                "VENDOR_OUT_OF_SCOPE",
                (
                    "Ce vendeur n'appartient pas "
                    "à vos bijouteries."
                ),
                status.HTTP_403_FORBIDDEN,
            )

    return vendor, None


def _update_client_if_provided(
    data,
    vente,
):
    client_data = data.get("client")

    if not client_data:
        return None

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
        or None
    )

    if telephone:
        telephone = str(
            telephone
        ).strip()

        client, _ = (
            Client.objects
            .get_or_create(
                telephone=telephone,
                defaults={
                    "nom": nom,
                    "prenom": prenom,
                },
            )
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
                update_fields=update_fields,
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
            update_fields=["client"],
        )

    return None


def _resolve_produit_line_for_sale_item(item):
    """
    Résout la ProduitLine exacte d'une ligne de vente.

    La ProduitLine est désormais la source de vérité.

    Formats acceptés :
    - produit_line_id
    - qr / qr_code si le QR contient l'identifiant
      exact de la ProduitLine.

    On ne résout plus une vente par :
    - produit_id
    - SKU produit
    - slug produit

    car ces valeurs identifient un Produit générique,
    pas la ProduitLine exacte.
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

    # =====================================================
    # PRODUIT LINE ID
    # =====================================================

    if produit_line_id not in (
        None,
        "",
    ):
        try:
            produit_line_id = int(
                produit_line_id
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

        if produit_line_id <= 0:
            return None

        return (
            produit_line_qs
            .filter(
                id=produit_line_id,
            )
            .first()
        )

    # =====================================================
    # QR
    # =====================================================

    if qr:
        qr = str(qr).strip()

        # Format :
        #
        # PL:123
        #
        # Le QR représente directement la ProduitLine.

        if not qr.upper().startswith(
            "PL:"
        ):
            return None

        raw_id = qr.split(
            ":",
            1,
        )[1].strip()

        if not raw_id.isdigit():
            return None

        return (
            produit_line_qs
            .filter(
                id=int(raw_id),
            )
            .first()
        )

    return None


def _recalculate_facture_from_vente(
    facture,
    vente,
    vendor,
):
    """
    Recalcule la facture à partir du nouveau total
    de la vente.
    """

    if facture:
        facture.montant_ht = (
            vente.montant_total
        )

        facture.bijouterie = (
            vendor.bijouterie
        )

        facture.save(
            update_fields=[
                "montant_ht",
                "bijouterie",

                # Ces champs sont conservés ici si
                # Facture.save() recalcule effectivement
                # TVA et total.
                "taux_tva",
                "montant_tva",
                "montant_total",
            ]
        )

        return facture

    return Facture.objects.create(
        vente=vente,
        bijouterie=vendor.bijouterie,
        montant_ht=vente.montant_total,
    )

# ==========================================================
# 1. UPDATE VENTE AVANT PAIEMENT
# ==========================================================
class UpdateVenteProduitView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Modifier une vente avant paiement",
        operation_description="""
Modifie une vente avant paiement.

Important :
- Ne modifie pas le VendorStock.
- Ne crée pas de InventoryMovement.
- Le stock est consommé uniquement après paiement complet.
- Chaque article doit identifier une ProduitLine exacte.
- La modification est autorisée uniquement si la facture :
  - est NON PAYÉE ;
  - ne possède aucun paiement ;
  - n'est pas verrouillée ;
  - n'a pas encore consommé le stock.
        """,
        request_body=UpdateVenteProduitSerializer,
        responses={
            200: VenteDetailSerializer,
        },
        tags=["Ventes"],
    )
    @transaction.atomic
    def put(
        self,
        request,
        vente_id,
    ):
        user = request.user

        role = (
            get_role_name(user)
            or ""
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
                "ACCESS_DENIED",
                "Accès refusé.",
                status.HTTP_403_FORBIDDEN,
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
        # 3. VENTE + LOCK
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

        if not vente:
            return error_response(
                "VENTE_NOT_FOUND",
                "Vente introuvable.",
                status.HTTP_404_NOT_FOUND,
            )

        # =====================================================
        # 4. VENTE ANNULÉE
        # =====================================================

        if vente.is_cancelled:
            return error_response(
                "VENTE_CANCELLED",
                (
                    "Modification impossible : "
                    "cette vente est annulée."
                ),
                status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 5. FACTURE + LOCK
        # =====================================================

        facture = _get_facture_locked(
            vente
        )

        facture_error = _validate_before_payment(
            facture
        )

        if facture_error:
            return facture_error

        # =====================================================
        # 6. VENDEUR
        # =====================================================

        vendor, vendor_error = (
            _resolve_vendor_for_update(
                data,
                request,
                vente,
                role,
            )
        )

        if vendor_error:
            return vendor_error

        if not vendor:
            return error_response(
                "VENDOR_NOT_FOUND",
                "Vendeur introuvable.",
                status.HTTP_400_BAD_REQUEST,
            )

        if not getattr(
            vendor,
            "verifie",
            False,
        ):
            return error_response(
                "VENDOR_NOT_VERIFIED",
                (
                    "Le vendeur est désactivé "
                    "ou non vérifié."
                ),
                status.HTTP_400_BAD_REQUEST,
            )

        if not vendor.bijouterie_id:
            return error_response(
                "VENDOR_WITHOUT_STORE",
                (
                    "Le vendeur n'est rattaché "
                    "à aucune bijouterie."
                ),
                status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 7. PRODUITS
        # =====================================================

        produits_data = data.get(
            "produits"
        )

        if not produits_data:
            return error_response(
                "EMPTY_SALE_LINES",
                (
                    "La vente doit contenir "
                    "au moins un produit."
                ),
                status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 8. PRÉPARATION DES LIGNES
        # =====================================================
        #
        # On valide toutes les nouvelles lignes AVANT
        # de supprimer les anciennes.
        #
        # Aucun VendorStock n'est modifié ici.
        # =====================================================

        prepared_lines = []

        # Quantité totale demandée par ProduitLine.
        #
        # Cela évite :
        #
        # PL 47 -> quantité 1
        # PL 47 -> quantité 1
        #
        # alors que disponible = 1.
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

            except (
                TypeError,
                ValueError,
            ):
                return error_response(
                    "INVALID_QUANTITY",
                    (
                        f"Quantité invalide "
                        f"à la ligne {index}."
                    ),
                    status.HTTP_400_BAD_REQUEST,
                )

            if quantite <= 0:
                return error_response(
                    "INVALID_QUANTITY",
                    (
                        f"La quantité doit être "
                        f"supérieure ou égale à 1 "
                        f"à la ligne {index}."
                    ),
                    status.HTTP_400_BAD_REQUEST,
                )

            # -------------------------------------------------
            # PRODUIT LINE
            # -------------------------------------------------

            produit_line = (
                _resolve_produit_line_for_sale_item(
                    item
                )
            )

            if not produit_line:
                return error_response(
                    "PRODUIT_LINE_NOT_FOUND",
                    (
                        f"ProduitLine introuvable "
                        f"à la ligne {index}. "
                        f"Vérifiez produit_line_id "
                        f"ou le QR."
                    ),
                    status.HTTP_404_NOT_FOUND,
                )

            # -------------------------------------------------
            # PRODUIT
            # -------------------------------------------------

            produit = getattr(
                produit_line,
                "produit",
                None,
            )

            if not produit:
                return error_response(
                    "PRODUCT_NOT_FOUND",
                    (
                        f"Aucun produit n'est associé "
                        f"à la ProduitLine "
                        f"#{produit_line.id}."
                    ),
                    status.HTTP_400_BAD_REQUEST,
                )

            # -------------------------------------------------
            # LOT
            # -------------------------------------------------

            if not produit_line.lot_id:
                return error_response(
                    "PRODUIT_LINE_WITHOUT_LOT",
                    (
                        f"La ProduitLine "
                        f"#{produit_line.id} "
                        f"n'est associée à aucun lot."
                    ),
                    status.HTTP_400_BAD_REQUEST,
                )

            # -------------------------------------------------
            # QUANTITÉ CUMULÉE PAR PRODUIT LINE
            # -------------------------------------------------

            produit_line_id = (
                produit_line.id
            )

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
            # PRIX
            # -------------------------------------------------

            prix_vente_grammes = item.get(
                "prix_vente_grammes"
            )

            if prix_vente_grammes in {
                None,
                "",
                0,
                "0",
                "0.00",
            }:
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

                if prix_marque in {
                    None,
                    "",
                }:
                    return error_response(
                        "PRICE_NOT_FOUND",
                        (
                            f"Aucun prix disponible "
                            f"pour {produit.nom}."
                        ),
                        status.HTTP_400_BAD_REQUEST,
                    )

                try:
                    prix_vente_grammes = Decimal(
                        str(prix_marque)
                    )

                except (
                    InvalidOperation,
                    TypeError,
                    ValueError,
                ):
                    return error_response(
                        "INVALID_PRICE",
                        (
                            f"Prix invalide pour "
                            f"{produit.nom}."
                        ),
                        status.HTTP_400_BAD_REQUEST,
                    )

            else:
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
                        "INVALID_PRICE",
                        (
                            f"Prix invalide pour "
                            f"{produit.nom}."
                        ),
                        status.HTTP_400_BAD_REQUEST,
                    )

            if (
                prix_vente_grammes
                <= Decimal("0.00")
            ):
                return error_response(
                    "INVALID_PRICE",
                    (
                        f"Le prix de vente de "
                        f"{produit.nom} doit être "
                        f"supérieur à zéro."
                    ),
                    status.HTTP_400_BAD_REQUEST,
                )

            # -------------------------------------------------
            # REMISE
            # -------------------------------------------------

            try:
                remise = Decimal(
                    str(
                        item.get(
                            "remise",
                            "0.00",
                        )
                        or "0.00"
                    )
                )

            except (
                InvalidOperation,
                TypeError,
                ValueError,
            ):
                return error_response(
                    "INVALID_DISCOUNT",
                    (
                        f"Remise invalide "
                        f"à la ligne {index}."
                    ),
                    status.HTTP_400_BAD_REQUEST,
                )

            if remise < Decimal("0.00"):
                return error_response(
                    "INVALID_DISCOUNT",
                    (
                        f"La remise ne peut pas "
                        f"être négative "
                        f"à la ligne {index}."
                    ),
                    status.HTTP_400_BAD_REQUEST,
                )

            # -------------------------------------------------
            # AUTRES
            # -------------------------------------------------

            try:
                autres = Decimal(
                    str(
                        item.get(
                            "autres",
                            "0.00",
                        )
                        or "0.00"
                    )
                )

            except (
                InvalidOperation,
                TypeError,
                ValueError,
            ):
                return error_response(
                    "INVALID_OTHER_AMOUNT",
                    (
                        f"Montant 'autres' invalide "
                        f"à la ligne {index}."
                    ),
                    status.HTTP_400_BAD_REQUEST,
                )

            if autres < Decimal("0.00"):
                return error_response(
                    "INVALID_OTHER_AMOUNT",
                    (
                        f"Le montant 'autres' ne peut "
                        f"pas être négatif "
                        f"à la ligne {index}."
                    ),
                    status.HTTP_400_BAD_REQUEST,
                )

            # -------------------------------------------------
            # POURCENTAGE OCCASION
            # -------------------------------------------------

            try:
                pourcentage_occasion = Decimal(
                    str(
                        item.get(
                            "pourcentage_occasion",
                            "0.00",
                        )
                        or "0.00"
                    )
                )

            except (
                InvalidOperation,
                TypeError,
                ValueError,
            ):
                return error_response(
                    "INVALID_USED_PERCENTAGE",
                    (
                        f"Pourcentage occasion invalide "
                        f"à la ligne {index}."
                    ),
                    status.HTTP_400_BAD_REQUEST,
                )

            # -------------------------------------------------
            # LIGNE PRÉPARÉE
            # -------------------------------------------------

            prepared_lines.append(
                {
                    "produit_line": (
                        produit_line
                    ),
                    "quantite": quantite,
                    "prix_vente_grammes": (
                        prix_vente_grammes
                    ),
                    "remise": remise,
                    "autres": autres,
                    "pourcentage_occasion": (
                        pourcentage_occasion
                    ),
                }
            )

        # =====================================================
        # 9. DISPONIBILITÉ STOCK VENDEUR
        # =====================================================
        #
        # On vérifie maintenant la quantité CUMULÉE
        # demandée pour chaque ProduitLine.
        #
        # Cette étape ne consomme aucun stock.
        # =====================================================

        produit_lines_by_id = {
            prepared[
                "produit_line"
            ].id: prepared[
                "produit_line"
            ]
            for prepared in prepared_lines
        }

        for (
            produit_line_id,
            quantite_demandee,
        ) in requested_by_produit_line.items():

            produit_line = (
                produit_lines_by_id[
                    produit_line_id
                ]
            )

            try:
                ensure_vendor_stock_available(
                    vendor=vendor,
                    bijouterie=(
                        vendor.bijouterie
                    ),
                    produit_line=(
                        produit_line
                    ),
                    quantite=(
                        quantite_demandee
                    ),
                )

            except DjangoValidationError as exc:
                return error_response(
                    "VENDOR_STOCK_NOT_AVAILABLE",
                    (
                        f"Stock vendeur insuffisant "
                        f"ou indisponible pour la "
                        f"ProduitLine "
                        f"#{produit_line_id}."
                    ),
                    status.HTTP_400_BAD_REQUEST,
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
        # 10. CLIENT
        # =====================================================
        #
        # À partir d'ici toutes les nouvelles lignes
        # ont été validées.
        # =====================================================

        client_error = (
            _update_client_if_provided(
                data,
                vente,
            )
        )

        if client_error:
            return client_error

        # =====================================================
        # 11. VENDEUR / BIJOUTERIE
        # =====================================================

        vente.vendor = vendor
        vente.bijouterie = (
            vendor.bijouterie
        )

        vente.save(
            update_fields=[
                "vendor",
                "bijouterie",
            ]
        )

        # =====================================================
        # 12. LOCK ANCIENNES LIGNES
        # =====================================================

        old_lines = (
            VenteProduit.objects
            .select_for_update()
            .filter(
                vente=vente,
            )
        )

        # Force réellement l'acquisition des locks
        # avant suppression.
        list(
            old_lines.values_list(
                "id",
                flat=True,
            )
        )

        # =====================================================
        # 13. SUPPRESSION ANCIENNES LIGNES
        # =====================================================
        #
        # La vente n'est pas encore payée.
        # Aucun stock n'avait été consommé.
        # =====================================================

        old_lines.delete()

        # =====================================================
        # 14. CRÉATION NOUVELLES LIGNES
        # =====================================================

        try:
            for prepared in prepared_lines:
                VenteProduit.objects.create(
                    vente=vente,

                    # ProduitLine = source de vérité
                    produit_line=(
                        prepared[
                            "produit_line"
                        ]
                    ),

                    vendor=vendor,

                    quantite=(
                        prepared[
                            "quantite"
                        ]
                    ),

                    prix_vente_grammes=(
                        prepared[
                            "prix_vente_grammes"
                        ]
                    ),

                    remise=(
                        prepared[
                            "remise"
                        ]
                    ),

                    autres=(
                        prepared[
                            "autres"
                        ]
                    ),

                    pourcentage_occasion=(
                        prepared[
                            "pourcentage_occasion"
                        ]
                    ),
                )

        except DjangoValidationError as exc:
            transaction.set_rollback(
                True
            )

            return error_response(
                "SALE_LINE_INVALID",
                (
                    "Impossible de créer "
                    "une ligne de vente."
                ),
                status.HTTP_400_BAD_REQUEST,
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
        # 15. RECALCUL TOTAL VENTE
        # =====================================================

        vente.mettre_a_jour_montant_total()

        vente.refresh_from_db()

        # =====================================================
        # 16. RECALCUL FACTURE
        # =====================================================

        facture = (
            _recalculate_facture_from_vente(
                facture,
                vente,
                vendor,
            )
        )

        # =====================================================
        # 17. REFRESH FINAL
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

    @transaction.atomic
    def patch(
        self,
        request,
        vente_id,
    ):
        return self.put(
            request,
            vente_id,
        )
        


# ==========================================================
# 2. CANCEL PROFORMA
# ==========================================================
class CancelProformaVenteView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Annuler une vente non payée / proforma",
        operation_description="""
Annule une vente non payée ou proforma.

Important :
- Ne modifie pas le VendorStock.
- Ne crée aucun InventoryMovement.
- Ne restaure aucun stock, car le stock n'a pas encore été consommé.
- Marque uniquement la vente comme annulée.
- Verrouille la facture liée si elle existe.
- Refuse l'annulation si un paiement existe déjà.
- Refuse l'annulation si le stock a déjà été consommé.
        """,
        request_body=CancelProformaVenteSerializer,
        responses={
            200: "Vente annulée avec succès",
            400: "Vente déjà annulée ou facture non annulable",
            403: "Accès refusé",
            404: "Vente introuvable",
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
            get_role_name(user)
            or ""
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
                "ACCESS_DENIED",
                "Accès refusé.",
                status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # 2. VALIDATION PAYLOAD
        # =====================================================

        input_serializer = CancelProformaVenteSerializer(
            data=request.data,
        )

        input_serializer.is_valid(
            raise_exception=True,
        )

        data = input_serializer.validated_data

        # =====================================================
        # 3. VENTE + LOCK
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

        if not vente:
            return error_response(
                "VENTE_NOT_FOUND",
                "Vente introuvable.",
                status.HTTP_404_NOT_FOUND,
            )

        # =====================================================
        # 4. VENTE DÉJÀ ANNULÉE
        # =====================================================

        if vente.is_cancelled:
            return error_response(
                "VENTE_ALREADY_CANCELLED",
                "Cette vente est déjà annulée.",
                status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 5. FACTURE + LOCK
        # =====================================================

        facture = _get_facture_locked(
            vente
        )

        # =====================================================
        # 6. VALIDATION AVANT ANNULATION
        # =====================================================
        #
        # Vérifie notamment :
        #
        # - facture NON_PAYE
        # - aucun paiement
        # - stock non consommé
        # - facture non verrouillée
        #
        # Aucun contrôle supplémentaire sur status/total_paye
        # n'est donc nécessaire ici.
        # =====================================================

        facture_error = _validate_before_payment(
            facture
        )

        if facture_error:
            return facture_error

        # =====================================================
        # 7. CONTRÔLE VENDEUR / PÉRIMÈTRE
        # =====================================================
        #
        # Vendor :
        #     uniquement ses propres ventes.
        #
        # Manager :
        #     uniquement vendeur appartenant
        #     à ses bijouteries.
        #
        # Admin :
        #     autorisé.
        # =====================================================

        vendor, vendor_error = (
            _resolve_vendor_for_update(
                data,
                request,
                vente,
                role,
            )
        )

        if vendor_error:
            return vendor_error

        if not vendor:
            return error_response(
                "VENDOR_NOT_FOUND",
                (
                    "Aucun vendeur n'est associé "
                    "à cette vente."
                ),
                status.HTTP_400_BAD_REQUEST,
            )

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
        # 9. VERROUILLAGE DE LA FACTURE
        # =====================================================
        #
        # La facture est déjà verrouillée SQL grâce à
        # _get_facture_locked().
        #
        # Ici is_locked correspond au verrouillage métier.
        # =====================================================

        if facture:
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
        #
        # NE PAS appeler :
        #
        # ensure_vendor_stock_available()
        # consume_vendor_stock()
        # create_sale_out_consumption()
        #
        # NE PAS créer :
        #
        # InventoryMovement
        #
        # Une proforma n'a encore consommé aucun stock.
        # =====================================================

        # =====================================================
        # 11. REFRESH
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
# ==========================================================
# 3. RETOUR CLIENT SOUS 72H APRÈS PAIEMENT
# ==========================================================
class RetourVenteProduitView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Retour client sous 72h après paiement",
        operation_description="""
Retour client après paiement.

Conditions :
- facture payée ;
- stock déjà consommé ;
- délai maximum de 72h ;
- retour basé sur la VenteProduit et sa ProduitLine exacte ;
- remet le produit dans le stock bijouterie ;
- augmente Stock.en_stock ;
- augmente Stock.quantite_totale ;
- ne modifie pas VendorStock ;
- crée InventoryMovement RETURN_IN.
        """,
        request_body=RetourVenteProduitSerializer,
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
            get_role_name(user)
            or ""
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
                "ACCESS_DENIED",
                "Accès refusé.",
                status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # 2. PAYLOAD
        # =====================================================

        input_serializer = RetourVenteProduitSerializer(
            data=request.data,
        )

        input_serializer.is_valid(
            raise_exception=True,
        )

        data = input_serializer.validated_data

        # =====================================================
        # 3. VENTE + LOCK
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

        if not vente:
            return error_response(
                "VENTE_NOT_FOUND",
                "Vente introuvable.",
                status.HTTP_404_NOT_FOUND,
            )

        if vente.is_cancelled:
            return error_response(
                "VENTE_CANCELLED",
                (
                    "Retour impossible : "
                    "cette vente est annulée."
                ),
                status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 4. FACTURE + LOCK
        # =====================================================

        facture = _get_facture_locked(
            vente
        )

        if not facture:
            return error_response(
                "FACTURE_NOT_FOUND",
                (
                    "Retour impossible : "
                    "aucune facture liée."
                ),
                status.HTTP_404_NOT_FOUND,
            )

        # =====================================================
        # 5. FACTURE PAYÉE
        # =====================================================

        if facture.status != Facture.STAT_PAYE:
            return error_response(
                "FACTURE_NOT_PAID",
                (
                    "Retour impossible : "
                    "la facture n'est pas payée."
                ),
                status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 6. STOCK DÉJÀ CONSOMMÉ
        # =====================================================

        if not facture.stock_consumed:
            return error_response(
                "STOCK_NOT_CONSUMED",
                (
                    "Retour impossible : "
                    "le stock de la vente "
                    "n'a pas encore été consommé."
                ),
                status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 7. DÉLAI 72H
        # =====================================================

        reference_date = (
            vente.delivered_at
            or facture.date_creation
        )

        if not reference_date:
            return error_response(
                "RETURN_REFERENCE_DATE_NOT_FOUND",
                (
                    "Impossible de déterminer "
                    "la date de référence du retour."
                ),
                status.HTTP_400_BAD_REQUEST,
            )

        if (
            timezone.now()
            > reference_date + timedelta(hours=72)
        ):
            return error_response(
                "RETURN_DELAY_EXPIRED",
                (
                    "Retour impossible : "
                    "délai de 72h dépassé."
                ),
                status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 8. VENDEUR / PÉRIMÈTRE
        # =====================================================

        vendor, vendor_error = (
            _resolve_vendor_for_update(
                data,
                request,
                vente,
                role,
            )
        )

        if vendor_error:
            return vendor_error

        if not vendor:
            return error_response(
                "VENDOR_NOT_FOUND",
                (
                    "Aucun vendeur n'est associé "
                    "à cette vente."
                ),
                status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 9. RAISON
        # =====================================================

        reason = (
            data.get("reason")
            or "Retour client sous 72h"
        )

        reason = str(reason).strip()

        if not reason:
            reason = (
                "Retour client dans le délai "
                "de 72 heures."
            )

        # =====================================================
        # 10. PRODUITS À RETOURNER
        # =====================================================

        produits_retour = (
            data.get("produits")
            or []
        )

        # Si produits est vide :
        # retour de toutes les quantités encore retournables.
        #
        # Sinon :
        # retour partiel par vente_ligne_id.

        requested_by_line = {}

        for item in produits_retour:
            try:
                ligne_id = int(
                    item["vente_ligne_id"]
                )

                qty = int(
                    item["quantite"]
                )

            except (
                KeyError,
                TypeError,
                ValueError,
            ):
                return error_response(
                    "INVALID_RETURN_LINE",
                    (
                        "vente_ligne_id et quantite "
                        "doivent être valides."
                    ),
                    status.HTTP_400_BAD_REQUEST,
                )

            if ligne_id <= 0:
                return error_response(
                    "INVALID_SALE_LINE",
                    (
                        "vente_ligne_id "
                        "doit être valide."
                    ),
                    status.HTTP_400_BAD_REQUEST,
                )

            if qty <= 0:
                return error_response(
                    "INVALID_QTY",
                    (
                        "La quantité doit être "
                        "supérieure à zéro."
                    ),
                    status.HTTP_400_BAD_REQUEST,
                )

            requested_by_line[
                ligne_id
            ] = (
                requested_by_line.get(
                    ligne_id,
                    0,
                )
                + qty
            )

        # =====================================================
        # 11. VÉRIFIER QUE LES LIGNES APPARTIENNENT À LA VENTE
        # =====================================================

        if requested_by_line:
            existing_line_ids = set(
                VenteProduit.objects
                .filter(
                    vente=vente,
                    id__in=requested_by_line.keys(),
                )
                .values_list(
                    "id",
                    flat=True,
                )
            )

            unknown_line_ids = (
                set(requested_by_line.keys())
                - existing_line_ids
            )

            if unknown_line_ids:
                return error_response(
                    "SALE_LINE_NOT_FOUND",
                    (
                        "Certaines lignes ne font pas "
                        "partie de cette vente : "
                        f"{sorted(unknown_line_ids)}."
                    ),
                    status.HTTP_400_BAD_REQUEST,
                )

        # =====================================================
        # 12. SALE_OUT DE LA VENTE
        # =====================================================
        #
        # Chaque SALE_OUT contient désormais la ProduitLine
        # exacte consommée au paiement.
        # =====================================================

        sale_outs = (
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
            sale_outs = sale_outs.filter(
                vente_ligne_id__in=(
                    requested_by_line.keys()
                )
            )

        sale_outs = list(sale_outs)

        if not sale_outs:
            return error_response(
                "SALE_OUT_NOT_FOUND",
                (
                    "Aucun mouvement SALE_OUT "
                    "n'a été trouvé pour cette vente."
                ),
                status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 13. QUANTITÉS DÉJÀ RETOURNÉES
        # =====================================================
        #
        # Agrégation par :
        #
        # vente_ligne + ProduitLine
        #
        # puisque ProduitLine est maintenant la source
        # de vérité.
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
            ): int(
                row["total"]
                or 0
            )
            for row in returned_rows
        }

        # =====================================================
        # 14. QUANTITÉS SALE_OUT PAR LIGNE + PRODUITLINE
        # =====================================================

        sale_out_total = {}

        for move in sale_outs:
            if not move.vente_ligne_id:
                continue

            if not move.produit_line_id:
                return error_response(
                    "PRODUIT_LINE_NOT_FOUND",
                    (
                        "Un mouvement SALE_OUT "
                        "ne contient pas de ProduitLine."
                    ),
                    status.HTTP_400_BAD_REQUEST,
                )

            key = (
                move.vente_ligne_id,
                move.produit_line_id,
            )

            sale_out_total[key] = (
                sale_out_total.get(
                    key,
                    0,
                )
                + int(move.qty or 0)
            )

        # =====================================================
        # 15. CONSTRUIRE LES RETOURS À EFFECTUER
        # =====================================================

        returns_to_create = []

        remaining_requested = dict(
            requested_by_line
        )

        processed_keys = set()

        for move in sale_outs:
            if not move.vente_ligne_id:
                continue

            if not move.produit_line_id:
                continue

            key = (
                move.vente_ligne_id,
                move.produit_line_id,
            )

            # Plusieurs SALE_OUT peuvent théoriquement exister
            # pour la même combinaison.
            #
            # On traite la combinaison une seule fois.
            if key in processed_keys:
                continue

            processed_keys.add(key)

            ligne = move.vente_ligne

            sold_qty = int(
                sale_out_total.get(
                    key,
                    0,
                )
            )

            returned_qty = int(
                already_returned.get(
                    key,
                    0,
                )
            )

            returnable_qty = max(
                sold_qty - returned_qty,
                0,
            )

            if returnable_qty <= 0:
                continue

            # -------------------------------------------------
            # RETOUR PARTIEL DEMANDÉ
            # -------------------------------------------------

            if requested_by_line:
                wanted = int(
                    remaining_requested.get(
                        ligne.id,
                        0,
                    )
                )

                if wanted <= 0:
                    continue

                qty_to_return = min(
                    returnable_qty,
                    wanted,
                )

                remaining_requested[
                    ligne.id
                ] = (
                    wanted
                    - qty_to_return
                )

            # -------------------------------------------------
            # RETOUR COMPLET
            # -------------------------------------------------

            else:
                qty_to_return = (
                    returnable_qty
                )

            if qty_to_return <= 0:
                continue

            returns_to_create.append(
                {
                    "move": move,
                    "ligne": ligne,
                    "produit_line": (
                        move.produit_line
                    ),
                    "qty": qty_to_return,
                }
            )

        # =====================================================
        # 16. QUANTITÉ DEMANDÉE TROP ÉLEVÉE
        # =====================================================
        #
        # IMPORTANT :
        # on vérifie ceci AVANT de modifier Stock.
        # =====================================================

        if requested_by_line:
            not_returnable = {
                ligne_id: qty
                for (
                    ligne_id,
                    qty,
                ) in remaining_requested.items()
                if qty > 0
            }

            if not_returnable:
                return error_response(
                    "RETURN_QTY_TOO_HIGH",
                    (
                        "Quantité demandée supérieure "
                        "à la quantité encore "
                        "retournable : "
                        f"{not_returnable}"
                    ),
                    status.HTTP_400_BAD_REQUEST,
                )

        if not returns_to_create:
            return error_response(
                "NOTHING_TO_RETURN",
                (
                    "Aucune quantité retournable "
                    "trouvée."
                ),
                status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 17. EXÉCUTION DES RETOURS
        # =====================================================

        total_returned_now = 0
        details = []

        for return_data in returns_to_create:
            move = return_data["move"]
            ligne = return_data["ligne"]
            produit_line = (
                return_data[
                    "produit_line"
                ]
            )

            qty_to_return = int(
                return_data["qty"]
            )

            # -------------------------------------------------
            # BIJOUTERIE
            # -------------------------------------------------

            bijouterie_id = (
                vente.bijouterie_id
                or getattr(
                    move.vendor,
                    "bijouterie_id",
                    None,
                )
            )

            if not bijouterie_id:
                raise ValidationError(
                    {
                        "bijouterie": (
                            "Impossible de déterminer "
                            "la bijouterie du retour."
                        )
                    }
                )

            # -------------------------------------------------
            # LOT
            # -------------------------------------------------

            lot = getattr(
                produit_line,
                "lot",
                None,
            )

            if not lot:
                raise ValidationError(
                    {
                        "produit_line": (
                            f"La ProduitLine "
                            f"#{produit_line.id} "
                            f"n'est associée "
                            f"à aucun lot."
                        )
                    }
                )

            # -------------------------------------------------
            # STOCK BIJOUTERIE + LOCK
            # -------------------------------------------------

            stock_magasin, _ = (
                Stock.objects
                .select_for_update()
                .get_or_create(
                    produit_line=(
                        produit_line
                    ),
                    bijouterie_id=(
                        bijouterie_id
                    ),
                    defaults={
                        "en_stock": 0,
                        "quantite_totale": 0,
                    },
                )
            )

            # -------------------------------------------------
            # REMISE EN STOCK
            # -------------------------------------------------

            stock_updated = (
                Stock.objects
                .filter(
                    pk=stock_magasin.pk,
                )
                .update(
                    en_stock=(
                        F("en_stock")
                        + qty_to_return
                    ),
                    quantite_totale=(
                        F("quantite_totale")
                        + qty_to_return
                    ),
                    updated_at=timezone.now(),
                )
            )

            if stock_updated != 1:
                raise ValidationError(
                    {
                        "stock": (
                            "Impossible de remettre "
                            "le produit dans le stock "
                            "de la bijouterie."
                        )
                    }
                )

            # -------------------------------------------------
            # RETURN_IN
            # -------------------------------------------------

            log_move(
                produit=produit_line.produit,
                produit_line=produit_line,

                achat=lot.achat,
                lot=lot,

                movement_type=(
                    MovementType.RETURN_IN
                ),

                qty=qty_to_return,

                src_bucket=Bucket.EXTERNAL,
                dst_bucket=Bucket.BIJOUTERIE,

                dst_bijouterie_id=(
                    bijouterie_id
                ),

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
            # RÉSULTAT
            # -------------------------------------------------

            total_returned_now += (
                qty_to_return
            )

            details.append(
                {
                    "vente_ligne_id": (
                        ligne.id
                    ),
                    "produit_line_id": (
                        produit_line.id
                    ),
                    "produit_id": (
                        produit_line.produit_id
                    ),
                    "produit": getattr(
                        produit_line.produit,
                        "nom",
                        None,
                    ),
                    "lot_id": (
                        produit_line.lot_id
                    ),
                    "bijouterie_id": (
                        bijouterie_id
                    ),
                    "quantite_retournee": (
                        qty_to_return
                    ),
                }
            )

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
                "numero_vente": (
                    vente.numero_vente
                ),
                "facture": (
                    facture.numero_facture
                ),
                "quantite_totale_retournee": (
                    total_returned_now
                ),
                "details": details,
            },
            status=status.HTTP_200_OK,
        )