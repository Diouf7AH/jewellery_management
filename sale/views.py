# from weasyprint import HTML
# import weasyprint
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO

from compte_depot.models import (ClientDepot, CompteDepot,
                                 CompteDepotTransaction)
from compte_depot.notifications import send_compte_depot_facture_notification
from compte_depot.services import effectuer_retrait
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.paginator import EmptyPage, Paginator
from django.db import transaction
from django.db.models import Count, Exists, F, OuterRef, Q, Sum
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from inventory.models import InventoryMovement
from inventory.services import log_move
from openpyxl import Workbook
from openpyxl.styles import Font, numbers
from purchase.models import ProduitLine
from rest_framework import permissions, status
from rest_framework.exceptions import APIException
from rest_framework.exceptions import ValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from sale.models import (Client, Facture,  # adapte le chemin si besoin
                         ModePaiement, Paiement, PaiementLigne, Vente,
                         VenteProduit)
from sale.pdf.escpos_ticket_58mm import build_escpos_ticket_proforma_58mm
from sale.pdf.escpos_ticket_80mm import build_escpos_recu_paiement_80mm
from sale.pdf.etiquettes_produits import build_etiquettes_produits_pdf
from sale.pdf.facture_A5_paysage import build_facture_a5_paysage_pdf
from sale.pdf.ticket_paiement_80mm import build_ticket_paiement_80mm_pdf
from sale.pdf.ticket_proforma_58mm import build_ticket_proforma_58mm_pdf
from sale.serializers import (CancelProformaVenteSerializer,
                              FactureListSerializer, FactureSerializer,
                              PaiementFactureMultiModeResponseSerializer,
                              PaiementMultiModeSerializer,
                              RetourVenteProduitSerializer,
                              UpdateVenteProduitSerializer,
                              VenteCreateInSerializer, VenteDetailSerializer,
                              VenteListSerializer)
from sale.services.comptable_export_service import export_comptable_factures
from sale.services.confirm_service import confirm_sale_out_from_vendor
from sale.services.export.export_facture_excel import export_factures_excel
from sale.services.facture_hash_service import generate_facture_hash
from sale.services.facture_pdf_service import generate_facture_pdf
from sale.services.facture_qr_service import generate_facture_qr
# from sale.services.receipt_service import generate_recu_paiement_pdf_bytes
from sale.services.sale_service import (cancel_sale_restore_direct,
                                        create_sale_one_vendor,
                                        upsert_client_for_payment,
                                        validate_facture_payable)
from staff.models import Cashier
from stock.models import VendorStock
from store.models import Bijouterie, MarquePurete, Produit
from vendor.models import Vendor

from backend.mixins import (GROUP_BY_CHOICES, ExportXlsxMixin,
                            aware_range_month, parse_month_or_default,
                            resolve_tz)
from backend.permissions import CanCreateSale, IsCashierOnly
from backend.query_scopes import scope_bijouterie_q
from backend.renderers import UserRenderer
from backend.roles import (ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER, ROLE_VENDOR,
                           get_role_name)

from .utils import ensure_role_and_bijouterie, user_bijouterie

DEFAULT_PAGE_SIZE = getattr(settings, "DEFAULT_PAGE_SIZE", 50)
MAX_PAGE_SIZE = getattr(settings, "MAX_PAGE_SIZE", 100)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class ProduitLineEtiquettesPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        produit_line_ids = request.data.get("produit_line_ids") or []

        if not produit_line_ids:
            return Response(
                {"detail": "produit_line_ids est requis."},
                status=400,
            )

        produit_lines = (
            ProduitLine.objects
            .select_related(
                "produit",
                "produit__purete",
                "produit__marque",
                "lot",
            )
            .filter(id__in=produit_line_ids)
        )

        if not produit_lines.exists():
            return Response(
                {"detail": "Aucune ligne produit trouvée."},
                status=404,
            )

        buffer = build_etiquettes_produits_pdf(produit_lines)

        return FileResponse(
            buffer,
            as_attachment=True,
            filename="etiquettes_produits.pdf",
            content_type="application/pdf",
        )


class VenteProduitCreateView(APIView):
    permission_classes = [CanCreateSale]
    http_method_names = ["post", "options"]

    def _resolve_produit_id(self, item):
        produit_id = item.get("produit_id")
        sku = item.get("sku")
        qr = item.get("qr") or item.get("qr_code")

        if produit_id:
            return produit_id

        if qr:
            qr = str(qr).strip()

            if qr.startswith("P:"):
                raw_id = qr.replace("P:", "").strip()

                if not raw_id.isdigit():
                    raise ValidationError({"qr": "QR invalide. Format attendu: P:15"})

                return int(raw_id)

            raise ValidationError({"qr": "QR invalide. Format attendu: P:15"})

        if sku:
            produit = Produit.objects.filter(sku__iexact=str(sku).strip()).first()

            if not produit:
                raise ValidationError({"sku": f"Produit introuvable pour SKU: {sku}"})

            return produit.id

        raise ValidationError({
            "produit": "Vous devez fournir produit_id, sku ou qr."
        })

    def _normalize_produits(self, produits):
        normalized = []

        for item in produits:
            item = dict(item)
            item["produit_id"] = self._resolve_produit_id(item)

            item.pop("sku", None)
            item.pop("qr", None)
            item.pop("qr_code", None)

            normalized.append(item)

        return normalized

    @swagger_auto_schema(
        operation_summary="Créer une vente (1 vendeur) + facture PROFORMA (stock non consommé)",
        request_body=VenteCreateInSerializer,
        responses={
            201: openapi.Response("Créé"),
            400: "Erreur validation",
            403: "Accès refusé",
        },
        tags=["Ventes"],
    )
    @transaction.atomic
    def post(self, request):
        serializer = VenteCreateInSerializer(
            data=request.data,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        role = (get_role_name(request.user) or "").lower().strip()

        try:
            produits_normalized = self._normalize_produits(validated["produits"])
        except ValidationError as e:
            detail = getattr(e, "message_dict", None) or getattr(e, "messages", None) or str(e)
            return Response(
                {"detail": detail},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = {
            "client": validated.get("client") or {},
            "produits": produits_normalized,
        }

        if role in {ROLE_ADMIN, ROLE_MANAGER}:
            vendor_email = (validated.get("vendor_email") or "").strip()

            if not vendor_email:
                return Response(
                    {"detail": "vendor_email est requis pour admin/manager."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            vendor = (
                Vendor.objects
                .select_related("bijouterie", "user")
                .filter(user__email__iexact=vendor_email)
                .first()
            )
            if not vendor:
                return Response(
                    {"detail": "Vendeur introuvable pour ce vendor_email."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if role == ROLE_MANAGER:
                manager_profile = getattr(request.user, "staff_manager_profile", None)

                if not manager_profile or (
                    hasattr(manager_profile, "verifie") and not manager_profile.verifie
                ):
                    return Response(
                        {"detail": "Profil manager invalide."},
                        status=status.HTTP_403_FORBIDDEN,
                    )

                if not manager_profile.bijouteries.filter(id=vendor.bijouterie_id).exists():
                    return Response(
                        {"detail": "⛔ Vous ne pouvez pas créer une vente pour un vendeur hors de vos bijouteries."},
                        status=status.HTTP_403_FORBIDDEN,
                    )

            payload["vendor_email"] = vendor_email

        try:
            vente, facture, audit_created = create_sale_one_vendor(
                user=request.user,
                role=role,
                payload=payload,
            )
        except ValidationError as e:
            detail = getattr(e, "message_dict", None) or getattr(e, "messages", None) or str(e)
            return Response(
                {"detail": detail},
                status=status.HTTP_400_BAD_REQUEST,
            )

        lignes = [
            {
                "ligne_id": ligne.id,
                "produit_id": ligne.produit_id,
                "produit_nom": getattr(ligne.produit, "nom", None),
                "quantite": ligne.quantite,
                "prix_vente_grammes": str(ligne.prix_vente_grammes),
                "montant_ht": str(ligne.montant_ht),
                "remise": str(ligne.remise or 0),
                "autres": str(ligne.autres or 0),
                "montant_total": str(ligne.montant_total or 0),
            }
            for ligne in vente.lignes.select_related("produit").all()
        ]

        client = getattr(vente, "client", None)

        return Response(
            {
                "message": "Vente créée avec succès.",
                "vente_id": vente.id,
                "numero_vente": vente.numero_vente,

                "facture": {
                    "facture_id": facture.id,
                    "numero_facture": facture.numero_facture,
                    "type_facture": facture.type_facture,
                    "status_facture": facture.status,
                    "montant_ht": str(facture.montant_ht),
                    "taux_tva": str(facture.taux_tva),
                    "montant_tva": str(facture.montant_tva),
                    "montant_total": str(facture.montant_total),
                },

                "audit_created": bool(audit_created),

                "bijouterie": {
                    "id": facture.bijouterie_id,
                    "nom": getattr(facture.bijouterie, "nom", None),
                },

                "client": {
                    "id": client.id if client else None,
                    "nom": getattr(client, "nom", None) if client else None,
                    "prenom": getattr(client, "prenom", None) if client else None,
                    "telephone": getattr(client, "telephone", None) if client else None,
                },

                "lignes": lignes,
            },
            status=status.HTTP_201_CREATED,
        )


def error_response(code, message, status_code=status.HTTP_400_BAD_REQUEST):
    return Response(
        {
            "status": "error",
            "code": code,
            "message": message,
        },
        status=status_code,
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
    - vendor : voit les ventes de sa bijouterie
    - cashier : voit les ventes de sa bijouterie

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
                description="Recherche client : nom, prénom ou téléphone",
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
                description="Statut facture : non_paye, partiel, paye",
                type=openapi.TYPE_STRING,
                enum=["non_paye", "partiel", "paye"],
            ),
            openapi.Parameter(
                "page",
                openapi.IN_QUERY,
                description="Page",
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
                examples={
                    "application/json": {
                        "count": 1,
                        "page": 1,
                        "page_size": 20,
                        "num_pages": 1,
                        "results": [
                            {
                                "id": 12,
                                "numero_vente": "VENTE-20260520-0001",
                                "created_at": "2026-05-20T12:30:00Z",
                                "montant_total": "150000.00",
                                "client": {
                                    "prenom": "Awa",
                                    "nom": "Diop",
                                    "telephone": "771234567"
                                },
                                "produits": [
                                    {
                                        "id": 30,
                                        "quantite": 2,
                                        "prix_vente_grammes": "25000.00",
                                        "remise": "0.00",
                                        "autres": "0.00",
                                        "montant_ht": "150000.00",
                                        "montant_total": "150000.00"
                                    }
                                ]
                            }
                        ]
                    }
                },
            ),
            400: "Erreur de filtre",
            403: "Accès refusé",
        },
        tags=["Ventes"],
    )
    def get(self, request):
        user = request.user
        role = (get_role_name(user) or "").lower().strip()

        if role not in {ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR, ROLE_CASHIER}:
            return Response({"detail": "⛔ Accès refusé."}, status=403)


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
                "lignes__produit",
                "lignes__vendor",
                "lignes__vendor__user",
            )
            .filter(scope_bijouterie_q(user, field="bijouterie_id"))
            .order_by("-created_at", "-id")
        )

        months = 36 if role == ROLE_ADMIN else 18
        min_date = timezone.now() - timedelta(days=months * 30)
        qs = qs.filter(created_at__gte=min_date)

        numero_vente = (request.query_params.get("numero_vente") or "").strip()
        if numero_vente:
            qs = qs.filter(numero_vente__icontains=numero_vente)

        client_q = (request.query_params.get("client_q") or "").strip()
        if client_q:
            qs = qs.filter(
                Q(client__nom__icontains=client_q) |
                Q(client__prenom__icontains=client_q) |
                Q(client__telephone__icontains=client_q)
            )

        vendor_id = request.query_params.get("vendor_id")
        if vendor_id:
            try:
                vendor_id = int(vendor_id)
            except ValueError:
                return Response({"vendor_id": "Doit être un entier."}, status=400)

            if role == ROLE_VENDOR:
                my_vendor = getattr(user, "staff_vendor_profile", None)
                if not my_vendor or my_vendor.id != vendor_id:
                    return Response(
                        {"detail": "Un vendeur ne peut filtrer que ses propres ventes."},
                        status=403,
                    )

            qs = qs.filter(vendor_id=vendor_id)

        status_facture = (request.query_params.get("status_facture") or "").strip()
        if status_facture:
            qs = qs.filter(facture_vente__status=status_facture)

        def to_int(name, default):
            try:
                return int(request.query_params.get(name, default))
            except Exception:
                return default

        page = max(1, to_int("page", 1))
        page_size = min(max(1, to_int("page_size", 20)), 100)

        paginator = Paginator(qs, page_size)

        if paginator.count == 0:
            return Response({
                "count": 0,
                "page": 1,
                "page_size": page_size,
                "num_pages": 0,
                "results": [],
            })

        try:
            page_obj = paginator.page(page)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)

        return Response({
            "count": paginator.count,
            "page": page_obj.number,
            "page_size": page_size,
            "num_pages": paginator.num_pages,
            "results": VenteListSerializer(page_obj.object_list, many=True).data,
        })



class ListFacturePayeesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        role = get_role_name(user)  # admin/manager/vendor/cashier

        if role not in {ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR, ROLE_CASHIER}:
            return Response({"detail": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

        qs = (
            Facture.objects
            .select_related("bijouterie", "vente", "vente__client")
            .prefetch_related(
                "paiements",
                "vente__lignes__vendor",
                "vente__lignes__produit",
                "vente__lignes__produit__categorie",
                "vente__lignes__produit__marque",
                "vente__lignes__produit__purete",
                "vente__lignes__produit__modele",
            )
            .filter(status=Facture.STAT_PAYE)
        )

        # ✅ scope bijouterie (admin=all, manager=M2M, vendor/cashier=1)
        qs = qs.filter(scope_bijouterie_q(user, field="bijouterie_id"))

        # ✅ fenêtre auto
        months = 36 if role == ROLE_ADMIN else 18
        min_datetime = timezone.now() - timedelta(days=months * 30)
        qs = qs.filter(date_creation__gte=min_datetime)

        # ✅ filtres
        numero = (request.query_params.get("numero_facture") or "").strip()
        if numero:
            qs = qs.filter(numero_facture__icontains=numero)

        vendor_id = request.query_params.get("vendor_id")
        if vendor_id:
            try:
                vendor_id_int = int(vendor_id)
            except ValueError:
                return Response({"vendor_id": "Doit être un entier."}, status=status.HTTP_400_BAD_REQUEST)

            # vendor ne filtre que lui-même
            if role == ROLE_VENDOR:
                my_vendor = getattr(user, "staff_vendor_profile", None)
                if not my_vendor or (hasattr(my_vendor, "verifie") and not my_vendor.verifie):
                    return Response({"detail": "Profil vendeur introuvable ou non vérifié."}, status=403)
                if vendor_id_int != my_vendor.id:
                    return Response({"detail": "Un vendeur ne peut filtrer que ses propres factures."}, status=403)

            # manager ne filtre que vendors de ses bijouteries
            if role == ROLE_MANAGER:
                mp = getattr(user, "staff_manager_profile", None)
                if not mp or (hasattr(mp, "verifie") and not mp.verifie):
                    return Response({"detail": "Profil manager invalide."}, status=403)
                if not mp.bijouteries.filter(vendors__id=vendor_id_int).exists():
                    return Response({"detail": "Vendeur hors de vos bijouteries."}, status=403)

            venteproduit_exists = VenteProduit.objects.filter(
                vente_id=OuterRef("vente_id"),
                vendor_id=vendor_id_int,
            )
            qs = qs.annotate(_has_vendor=Exists(venteproduit_exists)).filter(_has_vendor=True)

        client_q = (request.query_params.get("client_q") or "").strip()
        if client_q:
            qs = qs.filter(
                Q(vente__client__nom__icontains=client_q) |
                Q(vente__client__prenom__icontains=client_q) |
                Q(vente__client__telephone__icontains=client_q)
            )

        payment_mode = (request.query_params.get("payment_mode") or "").strip()
        if payment_mode:
            qs = qs.filter(
                paiements__lignes__mode_paiement__code__iexact=payment_mode
            ).distinct()

        qs = qs.order_by("-date_creation")

        # ✅ pagination safe
        def _int(name: str, default: int) -> int:
            val = request.query_params.get(name)
            if val in (None, ""):
                return default
            try:
                return int(val)
            except ValueError:
                return default

        page = max(1, _int("page", 1))
        page_size = max(1, min(_int("page_size", DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))

        paginator = Paginator(qs, page_size)

        if paginator.count == 0:
            return Response(
                {"count": 0, "page": 1, "page_size": page_size, "num_pages": 0, "results": []},
                status=200,
            )

        try:
            page_obj = paginator.page(page)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)

        return Response(
            {
                "count": paginator.count,
                "page": page_obj.number,
                "page_size": page_size,
                "num_pages": paginator.num_pages,
                "results": FactureListSerializer(page_obj.object_list, many=True).data,
            },
            status=200,
        )



DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

class ListFacturesAPayerView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        role = get_role_name(user)

        if role not in {ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR, ROLE_CASHIER}:
            return Response({"detail": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

        qs = (
            Facture.objects
            .select_related("bijouterie", "vente", "vente__client")
            .prefetch_related(
                "paiements",
                "vente__lignes__vendor",
                "vente__lignes__produit",
                "vente__lignes__produit__categorie",
                "vente__lignes__produit__marque",
                "vente__lignes__produit__purete",
                "vente__lignes__produit__modele",
            )
            .filter(
                status__in=[
                    Facture.STAT_NON_PAYE,
                    Facture.STAT_PARTIEL,
                ]
            )
        )

        # ✅ Scope bijouterie
        qs = qs.filter(scope_bijouterie_q(user, field="bijouterie_id"))

        # ✅ Fenêtre auto
        months = 36 if role == ROLE_ADMIN else 18
        min_datetime = timezone.now() - timedelta(days=months * 30)
        qs = qs.filter(date_creation__gte=min_datetime)

        # ✅ Filtres
        numero = (request.query_params.get("numero_facture") or "").strip()
        if numero:
            qs = qs.filter(numero_facture__icontains=numero)

        client_q = (request.query_params.get("client_q") or "").strip()
        if client_q:
            qs = qs.filter(
                Q(vente__client__nom__icontains=client_q) |
                Q(vente__client__prenom__icontains=client_q) |
                Q(vente__client__telephone__icontains=client_q)
            )

        # (optionnel) payment_mode -> DISTINCT nécessaire uniquement ici
        payment_mode = (request.query_params.get("payment_mode") or "").strip()
        if payment_mode:
            qs = qs.filter(paiements__mode_paiement__iexact=payment_mode).distinct()

        qs = qs.order_by("-date_creation")

        # ✅ Pagination safe
        def _int(name: str, default: int) -> int:
            val = request.query_params.get(name)
            if val in (None, ""):
                return default
            try:
                return int(val)
            except ValueError:
                return default

        page = max(1, _int("page", 1))
        page_size = max(1, min(_int("page_size", DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))

        paginator = Paginator(qs, page_size)

        if paginator.count == 0:
            return Response(
                {"count": 0, "page": 1, "page_size": page_size, "num_pages": 0, "results": []},
                status=status.HTTP_200_OK,
            )

        try:
            page_obj = paginator.page(page)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)

        return Response(
            {
                "count": paginator.count,
                "page": page_obj.number,
                "page_size": page_size,
                "num_pages": paginator.num_pages,
                "results": FactureListSerializer(page_obj.object_list, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


# class PaiementFactureMultiModeView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Paiement facture multi-mode",
#         operation_description="""
#         Permet de payer une facture avec un ou plusieurs modes de paiement.

#         Modes possibles :
#         - cash
#         - wave
#         - orange_money
#         - carte
#         - depot

#         Règles :
#         - Le cumul des modes de paiement ne doit pas dépasser le reste à payer.
#         - Si paiement partiel : statut facture = partiel.
#         - Si paiement complet : statut facture = payé.
#         - Si la facture est totalement payée, le stock vendeur est consommé.
#         - Si la facture est totalement payée, le PDF officiel est généré.
#         """,
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["numero_facture", "lignes"],
#             properties={
#                 "numero_facture": openapi.Schema(
#                     type=openapi.TYPE_STRING,
#                     example="FAC-20260512-0003",
#                 ),
#                 "client": openapi.Schema(
#                     type=openapi.TYPE_OBJECT,
#                     properties={
#                         "nom": openapi.Schema(type=openapi.TYPE_STRING, example="Diop"),
#                         "prenom": openapi.Schema(type=openapi.TYPE_STRING, example="Awa"),
#                         "telephone": openapi.Schema(type=openapi.TYPE_STRING, example="770000000"),
#                     },
#                 ),
#                 "lignes": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["mode", "montant"],
#                         properties={
#                             "mode": openapi.Schema(
#                                 type=openapi.TYPE_STRING,
#                                 example="cash",
#                                 description="Code du mode de paiement : cash, wave, orange_money, carte, depot",
#                             ),
#                             "montant": openapi.Schema(
#                                 type=openapi.TYPE_NUMBER,
#                                 example=10000,
#                             ),
#                             "reference": openapi.Schema(
#                                 type=openapi.TYPE_STRING,
#                                 example="WAVE-123456",
#                             ),
#                         },
#                     ),
#                 ),
#             },
#         ),
#         responses={
#             201: openapi.Response(
#                 description="Paiement effectué avec succès."
#             ),
#             400: "Erreur de validation.",
#             403: "Accès refusé.",
#             404: "Facture introuvable.",
#         },
#         tags=["Paiements"],
#     )
#     @transaction.atomic
#     def post(self, request):
#         numero_facture = str(request.data.get("numero_facture") or "").strip()
#         client_data = request.data.get("client") or {}
#         lignes_data = request.data.get("lignes") or []

#         if not numero_facture:
#             return Response({"detail": "numero_facture requis."}, status=400)

#         if not lignes_data:
#             return Response({"detail": "lignes requises."}, status=400)

#         facture = (
#             Facture.objects
#             .select_for_update()
#             .select_related("vente", "vente__client", "bijouterie")
#             .prefetch_related("paiements__lignes")
#             .filter(numero_facture__iexact=numero_facture)
#             .first()
#         )

#         if not facture:
#             return Response(
#                 {"detail": f"Facture introuvable avec le numéro : {numero_facture}"},
#                 status=404,
#             )

#         try:
#             validate_facture_payable(facture)
#         except DjangoValidationError as e:
#             return Response({"detail": getattr(e, "message", str(e))}, status=400)

#         try:
#             client = upsert_client_for_payment(
#                 facture=facture,
#                 client_data=client_data,
#             )
#         except DjangoValidationError as e:
#             return Response({"detail": getattr(e, "message", str(e))}, status=400)

#         total = Decimal("0.00")
#         normalized_lignes = []

#         for index, item in enumerate(lignes_data):
#             mode = str(item.get("mode") or "").strip()
#             reference = item.get("reference")

#             if not mode:
#                 return Response(
#                     {"detail": f"Le mode de paiement est obligatoire à la ligne {index + 1}."},
#                     status=400,
#                 )

#             try:
#                 montant = Decimal(str(item.get("montant") or "0"))
#             except (InvalidOperation, TypeError):
#                 return Response(
#                     {"detail": f"Montant invalide à la ligne {index + 1}."},
#                     status=400,
#                 )

#             if montant <= 0:
#                 return Response(
#                     {"detail": f"Le montant doit être supérieur à 0 à la ligne {index + 1}."},
#                     status=400,
#                 )

#             total += montant

#             normalized_lignes.append({
#                 "mode": mode,
#                 "montant": montant,
#                 "reference": reference,
#             })

#         if total > facture.reste_a_payer:
#             return Response(
#                 {
#                     "detail": "Le cumul des modes de paiement ne doit pas dépasser le reste à payer.",
#                     "reste_a_payer": str(facture.reste_a_payer),
#                     "montant_recu": str(total),
#                 },
#                 status=400,
#             )

#         cashier = Cashier.objects.filter(user=request.user).first()

#         paiement = Paiement.objects.create(
#             facture=facture,
#             created_by=request.user,
#             cashier=cashier,
#         )

#         lignes_creees = []

#         for item in normalized_lignes:
#             mode_obj = ModePaiement.objects.filter(
#                 code__iexact=item["mode"],
#                 active=True,
#             ).first()

#             if not mode_obj:
#                 transaction.set_rollback(True)
#                 return Response(
#                     {"detail": f"Mode de paiement invalide ou inactif : {item['mode']}"},
#                     status=400,
#                 )

#             ligne = PaiementLigne.objects.create(
#                 paiement=paiement,
#                 mode_paiement=mode_obj,
#                 montant_paye=item["montant"],
#                 reference=item.get("reference"),
#             )

#             lignes_creees.append(ligne)

#         Facture.recompute_facture_status(facture)
#         facture.refresh_from_db()

#         if facture.reste_a_payer <= Decimal("0.00") and facture.status != Facture.STAT_PAYE:
#             facture.status = Facture.STAT_PAYE
#             facture.save(update_fields=["status"])
#             facture.refresh_from_db()

#         if facture.type_facture == Facture.TYPE_PROFORMA:
#             facture.type_facture = Facture.TYPE_FACTURE
#             facture.save(update_fields=["type_facture"])

#         audit = {
#             "created": 0,
#             "already": 0,
#             "lines_done": 0,
#         }

#         if facture.status == Facture.STAT_PAYE and not facture.stock_consumed:
#             try:
#                 audit = confirm_sale_out_from_vendor(
#                     facture=facture,
#                     by_user=request.user,
#                 )
#                 facture.refresh_from_db()
#             except DjangoValidationError as e:
#                 transaction.set_rollback(True)
#                 return Response({"detail": getattr(e, "message", str(e))}, status=400)

#         facture_pdf_url = None

#         if facture.status == Facture.STAT_PAYE:
#             if not facture.facture_pdf:
#                 facture.refresh_from_db()

#                 if not facture.integrity_hash:
#                     generate_facture_hash(facture)

#                 if not facture.qr_code_image:
#                     generate_facture_qr(facture)

#                 facture_pdf_url = generate_facture_pdf(facture)

#                 facture.is_locked = True
#                 facture.locked_at = timezone.now()
#                 facture.save(update_fields=["is_locked", "locked_at"])
#             else:
#                 try:
#                     facture_pdf_url = facture.facture_pdf.url
#                 except Exception:
#                     facture_pdf_url = None

#         return Response(
#             {
#                 "message": "Paiement effectué avec succès.",
#                 "paiement_id": paiement.id,
#                 "facture": {
#                     "id": facture.id,
#                     "numero_facture": facture.numero_facture,
#                     "type_facture": facture.type_facture,
#                     "status": facture.status,
#                     "montant_total": str(facture.montant_total),
#                     "total_paye": str(facture.total_paye),
#                     "reste_a_payer": str(facture.reste_a_payer),
#                 },
#                 "client": {
#                     "id": client.id if client else None,
#                     "nom": getattr(client, "nom", None) if client else None,
#                     "prenom": getattr(client, "prenom", None) if client else None,
#                     "telephone": getattr(client, "telephone", None) if client else None,
#                 },
#                 "lignes": [
#                     {
#                         "id": ligne.id,
#                         "mode_paiement": ligne.mode_paiement.code,
#                         "montant_paye": str(ligne.montant_paye),
#                         "reference": ligne.reference,
#                     }
#                     for ligne in lignes_creees
#                 ],
#                 "stock": audit,
#                 "facture_pdf_url": facture_pdf_url,
#             },
#             status=201,
#         )



class PaiementFactureMultiModeView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Paiement facture multi-mode",
        operation_description="""
        Permet de payer une facture avec un ou plusieurs modes de paiement.

        Modes possibles :
        - cash
        - wave
        - orange_money
        - carte
        - depot

        Règles :
        - Le cumul des modes de paiement ne doit pas dépasser le reste à payer.
        - Si paiement partiel : statut facture = partiel.
        - Si paiement complet : statut facture = payé.
        - Si la facture est totalement payée, le stock vendeur est consommé.
        - Si la facture est totalement payée, le PDF officiel est généré.
        """,
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["numero_facture", "lignes"],
            properties={
                "numero_facture": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    example="FAC-20260512-0003",
                ),
                "client": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "nom": openapi.Schema(type=openapi.TYPE_STRING, example="Diop"),
                        "prenom": openapi.Schema(type=openapi.TYPE_STRING, example="Awa"),
                        # "numero_compte": openapi.Schema(type=openapi.TYPE_STRING, example="DEP-2026-00045", description="Obligatoire uniquement pour le mode depot"),
                        "telephone": openapi.Schema(type=openapi.TYPE_STRING, example="770000000"),
                    },
                ),
                "lignes": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        required=["mode", "montant"],
                        properties={
                            "mode": openapi.Schema(
                                type=openapi.TYPE_STRING,
                                example="cash",
                                description="Code du mode de paiement : cash, wave, orange_money, carte, depot",
                            ),
                            "montant": openapi.Schema(
                                type=openapi.TYPE_NUMBER,
                                example=10000,
                            ),
                            "numero_compte": openapi.Schema(
                                type=openapi.TYPE_STRING,
                                example="DEP-2026-00045",
                                description="Obligatoire uniquement pour le mode depot",
                            ),
                            "reference": openapi.Schema(
                                type=openapi.TYPE_STRING,
                                example="WAVE-123456",
                            ),
                            "banque": openapi.Schema(
                                type=openapi.TYPE_STRING,
                                example="CBAO",
                            ),

                            "numero_carte_masque": openapi.Schema(
                                type=openapi.TYPE_STRING,
                                example="**** **** **** 4589",
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
            400: "Erreur de validation.",
            403: "Accès refusé.",
            404: "Facture introuvable.",
        },
        tags=["Paiements"],
    )
    @transaction.atomic
    def post(self, request):
        numero_facture = str(request.data.get("numero_facture") or "").strip()
        client_data = request.data.get("client") or {}
        lignes_data = request.data.get("lignes") or []

        if not numero_facture:
            return Response({"detail": "numero_facture requis."}, status=400)

        if not lignes_data:
            return Response({"detail": "lignes requises."}, status=400)

        facture = (
            Facture.objects
            .select_for_update()
            .select_related("vente", "vente__client", "bijouterie")
            .prefetch_related("paiements__lignes")
            .filter(numero_facture__iexact=numero_facture)
            .first()
        )

        if not facture:
            return Response(
                {"detail": f"Facture introuvable avec le numéro : {numero_facture}"},
                status=404,
            )

        try:
            validate_facture_payable(facture)
        except DjangoValidationError as e:
            return Response({"detail": getattr(e, "message", str(e))}, status=400)

        try:
            client = upsert_client_for_payment(
                facture=facture,
                client_data=client_data,
            )
        except DjangoValidationError as e:
            return Response({"detail": getattr(e, "message", str(e))}, status=400)

        total = Decimal("0.00")
        normalized_lignes = []

        for index, item in enumerate(lignes_data):
            mode = str(item.get("mode") or "").strip()
            reference = item.get("reference")

            if not mode:
                return Response(
                    {"detail": f"Le mode de paiement est obligatoire à la ligne {index + 1}."},
                    status=400,
                )

            try:
                montant = Decimal(str(item.get("montant") or "0"))
            except (InvalidOperation, TypeError):
                return Response(
                    {"detail": f"Montant invalide à la ligne {index + 1}."},
                    status=400,
                )

            if montant <= 0:
                return Response(
                    {"detail": f"Le montant doit être supérieur à 0 à la ligne {index + 1}."},
                    status=400,
                )

            total += montant

            normalized_lignes.append({
                "mode": mode,
                "montant": montant,
                "reference": reference,
                "numero_compte": item.get("numero_compte"),

                "banque": item.get("banque"),
                "numero_carte_masque": item.get("numero_carte_masque"),
                "provider_reference": item.get("provider_reference"),
            })

        if total > facture.reste_a_payer:
            return Response(
                {
                    "detail": "Le cumul des modes de paiement ne doit pas dépasser le reste à payer.",
                    "reste_a_payer": str(facture.reste_a_payer),
                    "montant_recu": str(total),
                },
                status=400,
            )

        cashier = Cashier.objects.filter(user=request.user).first()

        paiement = Paiement.objects.create(
            facture=facture,
            created_by=request.user,
            cashier=cashier,
        )

        lignes_creees = []

        for item in normalized_lignes:
            mode_obj = ModePaiement.objects.filter(
                code__iexact=item["mode"],
                active=True,
            ).first()

            if not mode_obj:
                transaction.set_rollback(True)
                return Response(
                    {"detail": f"Mode de paiement invalide ou inactif : {item['mode']}"},
                    status=400,
                )

            # =========================
            # MODE COMPTE DÉPÔT
            # =========================
            if item["mode"].lower() == "depot":
                numero_compte = str(item.get("numero_compte") or "").strip()

                if not numero_compte:
                    transaction.set_rollback(True)
                    return Response(
                        {"detail": "Le numéro de compte dépôt est requis pour payer par compte dépôt."},
                        status=400,
                    )

                compte = (
                    CompteDepot.objects
                    .select_for_update()
                    .select_related("client")
                    .filter(numero_compte__iexact=numero_compte)
                    .first()
                )

                if not compte:
                    transaction.set_rollback(True)
                    return Response(
                        {"detail": f"Aucun compte dépôt trouvé pour ce numéro de compte : {numero_compte}"},
                        status=400,
                    )

                try:
                    tx = effectuer_retrait(
                        compte_id=compte.id,
                        montant=item["montant"],
                        user=request.user,
                        reference=f"FACTURE-{facture.numero_facture}",
                        commentaire=f"Paiement facture {facture.numero_facture}",
                    )
                except ValidationError as e:
                    transaction.set_rollback(True)
                    return Response(
                        {"detail": e.detail if hasattr(e, "detail") else str(e)},
                        status=400,
                    )

                send_compte_depot_facture_notification(tx)

                ligne = PaiementLigne.objects.create(
                    paiement=paiement,
                    mode_paiement=mode_obj,
                    montant_paye=item["montant"],
                    reference=f"COMPTE_DEPOT-{numero_compte}",
                    compte_depot=compte,
                    transaction_depot=tx,
                )

            # =========================
            # AUTRES MODES : CASH / WAVE / OM / CARTE
            # =========================
            else:
                ligne = PaiementLigne.objects.create(
                    paiement=paiement,
                    mode_paiement=mode_obj,
                    montant_paye=item["montant"],
                    reference=item.get("reference"),

                    banque=item.get("banque"),
                    numero_carte_masque=item.get("numero_carte_masque"),
                    provider_reference=item.get("provider_reference"),
                )

            lignes_creees.append(ligne)

        
        Facture.recompute_facture_status(facture)
        facture.refresh_from_db()

        if facture.type_facture == Facture.TYPE_PROFORMA and facture.status == Facture.STAT_PAYE:
            facture.type_facture = Facture.TYPE_FACTURE
            facture.save(update_fields=["type_facture"])

        audit = {
            "created": 0,
            "already": 0,
            "lines_done": 0,
        }

        if facture.status == Facture.STAT_PAYE and not facture.stock_consumed:
            try:
                audit = confirm_sale_out_from_vendor(
                    facture=facture,
                    by_user=request.user,
                )
                facture.refresh_from_db()
            except DjangoValidationError as e:
                transaction.set_rollback(True)
                return Response(
                    {"detail": getattr(e, "message", str(e))},
                    status=400,
                )
        
        
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
                        "Erreur lors de la génération du PDF de la facture."
                    )

            try:
                facture_pdf_url = request.build_absolute_uri(
                    facture.facture_pdf.url
                )
            except Exception:
                facture_pdf_url = None

            if not facture.is_locked:
                facture.is_locked = True
                facture.locked_at = timezone.now()
                facture.save(update_fields=["is_locked", "locked_at"])
                
        
        facture_download_url = request.build_absolute_uri(
            reverse(
                "facture-a5-paysage",
                kwargs={
                    "numero_facture": facture.numero_facture
                }
            )
        )

        return Response(
            {
                "message": "Paiement effectué avec succès.",
                "paiement_id": paiement.id,
                "vente": {
                    "id": facture.vente.id if facture.vente else None,
                    "numero_vente": (
                        facture.vente.numero_vente
                        if facture.vente else None
                    ),
                    "montant_total": (
                        str(facture.vente.montant_total)
                        if facture.vente else "0.00"
                    ),
                },

                "facture": {
                    "id": facture.id,
                    "numero_facture": facture.numero_facture,
                    "type_facture": facture.type_facture,
                    "status": facture.status,
                    "montant_total": str(facture.montant_total),
                    "total_paye": str(facture.total_paye),
                    "reste_a_payer": str(facture.reste_a_payer),
                },
                "client": {
                    "id": client.id if client else None,
                    "nom": getattr(client, "nom", None) if client else None,
                    "prenom": getattr(client, "prenom", None) if client else None,
                    "telephone": getattr(client, "telephone", None) if client else None,
                    # "numero_compte": (
                    #     compte_depot.numero_compte
                    #     if compte_depot else None
                    # ),
                },
                "lignes": [
                    {
                        "id": ligne.id,
                        "mode_paiement": ligne.mode_paiement.code,
                        "montant_paye": str(ligne.montant_paye),
                        "reference": ligne.reference,
                        "numero_compte": (
                            ligne.compte_depot.numero_compte
                            if ligne.compte_depot_id else None
                        ),
                    }
                    for ligne in lignes_creees
                ],
                "stock": audit,
                "facture_pdf_url": facture_pdf_url,
                "facture_download_url": facture_download_url,
            },
            status=201,
        )


# -------------------END PaiementFactureView-------------------


# PDF
def _can_access_facture(user, facture: Facture) -> bool:
    role = (get_role_name(user) or "").lower().strip()

    if role == ROLE_ADMIN:
        return True

    if role == ROLE_MANAGER:
        manager_profile = getattr(user, "staff_manager_profile", None)
        if not manager_profile or (hasattr(manager_profile, "verifie") and not manager_profile.verifie):
            return False
        return manager_profile.bijouteries.filter(id=facture.bijouterie_id).exists()

    if role == ROLE_CASHIER:
        cashier_profile = getattr(user, "staff_cashier_profile", None)
        if not cashier_profile or (hasattr(cashier_profile, "verifie") and not cashier_profile.verifie):
            return False
        return getattr(cashier_profile, "bijouterie_id", None) == facture.bijouterie_id

    if role == ROLE_VENDOR:
        vente = getattr(facture, "vente", None)
        if not vente:
            return False
        vendor_profile = getattr(user, "staff_vendor_profile", None)
        if not vendor_profile or (hasattr(vendor_profile, "verifie") and not vendor_profile.verifie):
            return False
        return vente.vendor_id == getattr(vendor_profile, "id", None)

    return False



class TicketProforma58mmView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Télécharger le ticket PROFORMA 58mm pour POS",
        operation_description="""
        Génère un ticket PROFORMA au format ESC/POS 58mm.

        Utilisation :
        - Sans debug : retourne un fichier `.bin` destiné à une imprimante thermique POS.
        - Avec `?debug=1` : retourne le contenu lisible en texte brut pour vérification dans le navigateur.

        Exemple :
        `/api/factures/FAC-20260509-0001/ticket-proforma-58mm/`

        Exemple debug :
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
                description="Mettre 1 pour afficher le ticket en texte lisible au lieu du fichier .bin",
                type=openapi.TYPE_STRING,
                required=False,
                example="1",
            ),
        ],
        responses={
            200: openapi.Response(
                description="Ticket PROFORMA généré avec succès. Retourne un fichier .bin ou du texte si debug=1."
            ),
            400: "Aucune vente associée à cette facture.",
            403: "Accès refusé.",
            404: "Facture introuvable.",
        },
        tags=["Tickets POS"],
    )

    def get(self, request, numero_facture: str):
        try:

            facture = get_object_or_404(
                Facture.objects.select_related(
                    "vente",
                    "bijouterie",
                    "vente__client",
                ),
                numero_facture__iexact=numero_facture,
            )

            if not _can_access_facture(request.user, facture):
                return Response(
                    {"detail": "⛔ Accès refusé à cette facture."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            if not facture.vente_id:
                return Response(
                    {"detail": "Aucune vente associée à cette facture."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            bijouterie = facture.bijouterie

            shop_name = (
                getattr(bijouterie, "nom", None)
                or "BIJOUTERIE RIO-GOLD"
            )

            shop_phone = (
                getattr(bijouterie, "telephone_portable_1", None)
                or getattr(bijouterie, "telephone_portable_2", None)
                or getattr(bijouterie, "telephone_fix", None)
                or ""
            )

            date_txt = facture.date_creation.strftime("%d/%m/%Y %H:%M")

            escpos_bytes = build_escpos_ticket_proforma_58mm(
                shop_name=shop_name,
                shop_phone=shop_phone,
                numero_facture=facture.numero_facture,
                date_txt=date_txt,
                montant_a_payer=facture.reste_a_payer,
                statut_txt=(
                    facture.get_status_display()
                    if hasattr(facture, "get_status_display")
                    else facture.status
                ),
                note="Ticket PROFORMA - à régler en caisse",
            )

            # ✅ Mode debug
            if request.query_params.get("debug") == "1":
                return HttpResponse(
                    escpos_bytes.decode("cp1252", errors="ignore"),
                    content_type="text/plain; charset=utf-8",
                )

            # ✅ Mode POS
            return HttpResponse(
                escpos_bytes,
                content_type="application/octet-stream",
                headers={
                    "Content-Disposition": (
                        f'inline; filename="ticket_proforma_{facture.numero_facture}.bin"'
                    )
                },
            )

        except Exception as e:
            return Response(
                {
                    "detail": "Erreur lors de la génération du ticket proforma.",
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# class TicketPaiement80mmESCPosView(APIView):
#     permission_classes = [IsAuthenticated]

#     def get(self, request, numero_facture: str):
#         facture = get_object_or_404(
#             Facture.objects.select_related(
#                 "vente",
#                 "bijouterie",
#                 "vente__client",
#             ),
#             numero_facture__iexact=numero_facture,
#         )

#         if not _can_access_facture(request.user, facture):
#             return Response(
#                 {"detail": "⛔ Accès refusé"},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         paiement = (
#             Paiement.objects
#             .filter(facture=facture)
#             .select_related("facture", "cashier", "created_by")
#             .prefetch_related("lignes__mode_paiement")
#             .order_by("-date_paiement", "-id")
#             .first()
#         )

#         if not paiement:
#             return Response(
#                 {"detail": "Aucun paiement trouvé"},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         bijouterie = facture.bijouterie

#         shop_name = getattr(bijouterie, "nom", None) or "RIO-GOLD"
#         shop_phone = (
#             getattr(bijouterie, "telephone_portable_1", None)
#             or getattr(bijouterie, "telephone_portable_2", None)
#             or getattr(bijouterie, "telephone_fix", None)
#             or ""
#         )

#         montant_paye = paiement.lignes.aggregate(
#             total=Sum("montant_paye")
#         )["total"] or Decimal("0.00")

#         escpos_bytes = build_escpos_recu_paiement_80mm(
#             shop_name=shop_name,
#             shop_phone=shop_phone,
#             numero_facture=facture.numero_facture,
#             date_paiement=paiement.date_paiement,
#             montant_paye=montant_paye,
#             reste_a_payer=facture.reste_a_payer,
#         )

#         return HttpResponse(
#             escpos_bytes,
#             content_type="application/octet-stream",
#             headers={
#                 "Content-Disposition": f'inline; filename="ticket_paiement_{facture.numero_facture}.bin"'
#             }
#         )



class TicketPaiement80mmESCPosView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Télécharger le ticket de paiement 80mm pour POS",
        operation_description="""
        Génère un reçu de paiement au format ESC/POS 80mm.

        - Sans `debug` : retourne un fichier `.bin` destiné à une imprimante thermique POS.
        - Avec `?debug=1` : affiche le contenu lisible du ticket dans le navigateur.

        Exemple :
        `/api/factures/FAC-20260509-0001/ticket-paiement-80mm/`

        Exemple debug :
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
                description="Mettre 1 pour afficher le ticket en texte lisible",
                type=openapi.TYPE_STRING,
                required=False,
                example="1",
            ),
        ],
        responses={
            200: openapi.Response(
                description="Ticket de paiement généré avec succès. Retourne un fichier .bin ou du texte si debug=1."
            ),
            400: "Facture non entièrement payée ou aucun paiement trouvé.",
            403: "Accès refusé.",
            404: "Facture introuvable.",
        },
        tags=["Tickets POS"],
    )
    def get(self, request, numero_facture: str):
        facture = get_object_or_404(
            Facture.objects.select_related(
                "vente",
                "bijouterie",
                "vente__client",
            ),
            numero_facture__iexact=numero_facture,
        )

        if not _can_access_facture(request.user, facture):
            return Response(
                {"detail": "⛔ Accès refusé"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # ✅ Ticket paiement 80mm seulement si facture totalement payée
        if facture.status != Facture.STAT_PAYE or facture.reste_a_payer > Decimal("0.00"):
            return Response(
                {
                    "detail": "Le ticket 80mm ne peut être imprimé que si la facture est entièrement payée.",
                    "status_facture": facture.status,
                    "reste_a_payer": str(facture.reste_a_payer),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        paiement = (
            Paiement.objects
            .filter(facture=facture)
            .select_related("facture", "cashier", "created_by")
            .prefetch_related("lignes__mode_paiement")
            .order_by("-date_paiement", "-id")
            .first()
        )

        if not paiement:
            return Response(
                {"detail": "Aucun paiement trouvé"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        bijouterie = facture.bijouterie

        shop_name = getattr(bijouterie, "nom", None) or "RIO-GOLD"

        shop_phone = (
            getattr(bijouterie, "telephone_portable_1", None)
            or getattr(bijouterie, "telephone_portable_2", None)
            or getattr(bijouterie, "telephone_fix", None)
            or ""
        )

        montant_paye = paiement.lignes.aggregate(
            total=Sum("montant_paye")
        )["total"] or Decimal("0.00")

        escpos_bytes = build_escpos_recu_paiement_80mm(
            shop_name=shop_name,
            shop_phone=shop_phone,
            numero_facture=facture.numero_facture,
            date_paiement=paiement.date_paiement,
            montant_paye=montant_paye,
            # reste_a_payer=facture.reste_a_payer,
            reste_a_payer=None,
        )

        if request.query_params.get("debug") == "1":
            return HttpResponse(
                escpos_bytes.decode("cp1252", errors="ignore"),
                content_type="text/plain; charset=utf-8",
            )

        return HttpResponse(
            escpos_bytes,
            content_type="application/octet-stream",
            headers={
                "Content-Disposition": (
                    f'inline; filename="ticket_paiement_{facture.numero_facture}.bin"'
                )
            },
        )

# class FactureA5PaysageView(APIView):
#     permission_classes = [IsAuthenticated]

#     def get(self, request, numero_facture: str):
#         facture = get_object_or_404(
#             Facture.objects.select_related("vente", "bijouterie", "vente__client"),
#             numero_facture__iexact=numero_facture,
#         )

#         if not _can_access_facture(request.user, facture):
#             return Response(
#                 {"detail": "⛔ Accès refusé à cette facture."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         pdf_buffer = build_facture_a5_paysage_pdf(facture=facture)

#         filename = f"facture_{facture.numero_facture}.pdf"
#         return FileResponse(pdf_buffer, as_attachment=False, filename=filename)


class FactureA5PaysageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, numero_facture: str):
        facture = get_object_or_404(
            Facture.objects
            .select_related(
                "vente",
                "vente__client",
                "bijouterie",
            )
            .prefetch_related(
                "vente__lignes__produit",
                "paiements",
            ),
            numero_facture__iexact=numero_facture,
        )

        if not _can_access_facture(request.user, facture):
            return Response(
                {"detail": "⛔ Accès refusé à cette facture."},
                status=status.HTTP_403_FORBIDDEN,
            )

        buffer = BytesIO()

        vente = facture.vente
        client = vente.client if vente else None
        bijouterie = facture.bijouterie

        lines = []

        if vente:
            for vp in vente.lignes.all():
                produit_nom = (
                    vp.produit.nom
                    if vp.produit else "Produit supprimé"
                )

                lines.append({
                    "label": produit_nom,
                    "qty": vp.quantite,
                    "pu": vp.prix_vente_grammes,
                    "ttc": vp.montant_total,
                })

        shop_phone = (
            getattr(bijouterie, "telephone_portable_1", None)
            or getattr(bijouterie, "telephone_portable_2", None)
            or getattr(bijouterie, "telephone_fix", None)
            or ""
        )

        data = {
            "shop_name": getattr(bijouterie, "nom", None) or "RIO GOLD",
            "shop_phone": shop_phone,
            "shop_ninea": getattr(bijouterie, "ninea", None) or "",
            "shop_address": getattr(bijouterie, "adresse", None) or "",

            "title": "FACTURE",
            "invoice_no": facture.numero_facture,
            "invoice_type": facture.type_facture,
            "qr_code_path": (
                facture.qr_code_image.path
                if getattr(facture, "qr_code_image", None)
                else None
            ),
            "date": facture.date_creation.strftime("%d/%m/%Y %H:%M"),
            # "document_type": facture.type_facture.upper(),

            "client_name": (
                f"{client.prenom} {client.nom}"
                if client else ""
            ),
            "client_phone": client.telephone if client else "",
            "client_address": "",

            "vendor": (
                str(vente.vendor)
                if vente and getattr(vente, "vendor", None)
                else ""
            ),
            "cashier": "",

            "sale_no": vente.numero_vente if vente else "",
            "status": facture.status,

            "lines": lines,

            "total_ht": facture.montant_ht,
            "taux_tva": facture.taux_tva,
            "montant_tva": facture.montant_tva,
            "total_ttc": facture.montant_total,

            "amount_paid": facture.total_paye,
            "deposit_amount": 0,
            "remaining_amount": facture.reste_a_payer,

            "thanks": "Merci pour votre confiance.",
            "footer_note": "A la prochaine visite insha Allah.",
        }

        build_facture_a5_paysage_pdf(buffer, data)

        buffer.seek(0)

        filename = f"facture_{facture.numero_facture}.pdf"

        response = FileResponse(
            buffer,
            as_attachment=True,
            filename=filename,
            content_type="application/pdf",
        )
        return response



class ExportFacturesExcelView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        factures = Facture.objects.all().select_related(
            "vente",
            "vente__client",
            "vente__vendor__user",
            "bijouterie",
        )
        return export_factures_excel(factures)



class ExportComptableView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        factures = Facture.objects.filter(status=Facture.STAT_PAYE).prefetch_related("paiements")
        wb = export_comptable_factures(factures)

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = 'attachment; filename="comptabilite.xlsx"'

        wb.save(response)
        return response




# class RecuPaiementPDFView(APIView):
#     permission_classes = [IsAuthenticated]

#     def get(self, request, paiement_id):
#         paiement = get_object_or_404(
#             Paiement.objects.select_related("facture", "facture__vente", "facture__bijouterie"),
#             pk=paiement_id
#         )

#         pdf_bytes = generate_recu_paiement_pdf_bytes(paiement=paiement)
#         response = HttpResponse(pdf_bytes, content_type="application/pdf")
#         response["Content-Disposition"] = f'inline; filename="recu_paiement_{paiement.id}.pdf"'
#         return response#         return response


# ==========================================================
# HELPERS corrigés pour serializers
# ==========================================================
def _get_facture_locked(vente):
    facture = getattr(vente, "facture_vente", None)
    if not facture:
        return None
    return Facture.objects.select_for_update().get(id=facture.id)

def _validate_before_payment(facture):
    if not facture:
        return None

    if facture.status != Facture.STAT_NON_PAYE:
        return error_response(
            "FACTURE_NOT_EDITABLE",
            "Action impossible : la facture n'est plus non payée.",
            status.HTTP_400_BAD_REQUEST,
        )

    if facture.total_paye > Decimal("0.00"):
        return error_response(
            "FACTURE_HAS_PAYMENT",
            "Action impossible : un paiement existe déjà.",
            status.HTTP_400_BAD_REQUEST,
        )

    if facture.stock_consumed:
        return error_response(
            "STOCK_ALREADY_CONSUMED",
            "Action impossible : le stock est déjà consommé.",
            status.HTTP_400_BAD_REQUEST,
        )

    if facture.is_locked:
        return error_response(
            "FACTURE_LOCKED",
            "Action impossible : la facture est verrouillée.",
            status.HTTP_400_BAD_REQUEST,
        )

    return None


def _resolve_vendor_for_update(data, request, vente, role):
    user = request.user

    if role == ROLE_VENDOR:
        vendor = Vendor.objects.select_related("user", "bijouterie").filter(user=user).first()

        if not vendor:
            return None, error_response(
                "VENDOR_PROFILE_NOT_FOUND",
                "Vous n'êtes pas associé à un compte vendeur.",
                status.HTTP_404_NOT_FOUND,
            )

        if vente.vendor_id != vendor.id:
            return None, error_response(
                "NOT_YOUR_SALE",
                "Vous ne pouvez modifier que vos propres ventes.",
                status.HTTP_403_FORBIDDEN,
            )

        return vendor, None

    vendor_email = data.get("vendor_email") or request.query_params.get("vendor_email")

    if vendor_email:
        vendor = Vendor.objects.select_related("user", "bijouterie").filter(
            user__email=vendor_email
        ).first()

        if not vendor:
            return None, error_response(
                "VENDOR_NOT_FOUND",
                "Vendeur introuvable.",
                status.HTTP_404_NOT_FOUND,
            )
    else:
        vendor = vente.vendor

    if role == ROLE_MANAGER:
        manager_profile = getattr(user, "staff_manager_profile", None)

        if manager_profile and hasattr(manager_profile, "bijouteries"):
            allowed = manager_profile.bijouteries.filter(id=vendor.bijouterie_id).exists()

            if not allowed:
                return None, error_response(
                    "VENDOR_OUT_OF_SCOPE",
                    "Ce vendeur n'appartient pas à vos bijouteries.",
                    status.HTTP_403_FORBIDDEN,
                )

    return vendor, None



def _update_client_if_provided(data, vente):
    client_data = data.get("client")

    if not client_data:
        return None

    nom = client_data.get("nom")
    prenom = client_data.get("prenom")
    telephone = client_data.get("telephone") or None

    if telephone:
        client, _ = Client.objects.get_or_create(
            telephone=telephone,
            defaults={"nom": nom, "prenom": prenom},
        )
        client.nom = nom
        client.prenom = prenom
        client.save(update_fields=["nom", "prenom"])
    else:
        client = Client.objects.create(
            nom=nom,
            prenom=prenom,
            telephone=None,
        )

    vente.client = client
    vente.save(update_fields=["client"])
    return None

def _resolve_product_for_sale_item(item):
    produit_id = item.get("produit_id")
    slug = item.get("slug")
    sku = item.get("sku")
    qr = item.get("qr") or item.get("qr_code")

    produit_qs = Produit.objects.select_related("marque", "purete")

    if produit_id:
        return produit_qs.filter(id=produit_id).first()

    if qr:
        qr = str(qr).strip()

        if not qr.startswith("P:"):
            return None

        raw_id = qr.replace("P:", "").strip()

        if not raw_id.isdigit():
            return None

        return produit_qs.filter(id=int(raw_id)).first()

    if sku:
        return produit_qs.filter(sku__iexact=str(sku).strip()).first()

    if slug:
        return produit_qs.filter(slug=slug).first()

    return None

# def _parse_decimal(value, default="0"):
#     try:
#         return Decimal(str(value if value not in [None, ""] else default))
#     except (InvalidOperation, TypeError):
#         raise ValueError("Decimal invalide")


def _recalculate_facture_from_vente(facture, vente, vendor):
    if facture:
        facture.montant_ht = vente.montant_total
        facture.bijouterie = vendor.bijouterie
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
- Ne touche pas au VendorStock.
- Ne crée pas InventoryMovement.
- Le stock sera consommé seulement au paiement complet.
- Modification autorisée uniquement si la facture est NON PAYÉE et sans paiement.
        """,
        request_body=UpdateVenteProduitSerializer,
        responses={200: VenteDetailSerializer},
        tags=["Ventes"],
    )
    @transaction.atomic
    def put(self, request, vente_id):
        user = request.user
        role = get_role_name(user)

        if role not in [ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR]:
            return error_response(
                "ACCESS_DENIED",
                "Accès refusé.",
                status.HTTP_403_FORBIDDEN
            )

        input_serializer = UpdateVenteProduitSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        vente = get_object_or_404(
            Vente.objects
            .select_for_update()
            .select_related("vendor", "bijouterie", "client"),
            id=vente_id,
        )

        if vente.is_cancelled:
            return error_response(
                "VENTE_CANCELLED",
                "Modification impossible : cette vente est annulée.",
                status.HTTP_400_BAD_REQUEST,
            )

        facture = _get_facture_locked(vente)

        # ✅ Contrôle AVANT toute modification
        facture_error = _validate_before_payment(facture)
        if facture_error:
            return facture_error

        if facture and facture.status != Facture.STAT_NON_PAYE:
            return error_response(
                "FACTURE_NOT_EDITABLE",
                "Modification impossible : la facture n'est plus non payée.",
                status.HTTP_400_BAD_REQUEST,
            )

        if facture and facture.total_paye > 0:
            return error_response(
                "FACTURE_HAS_PAYMENT",
                "Modification impossible : un paiement existe déjà.",
                status.HTTP_400_BAD_REQUEST,
            )

        vendor, vendor_error = _resolve_vendor_for_update(
            data,
            request,
            vente,
            role
        )
        if vendor_error:
            return vendor_error

        client_error = _update_client_if_provided(data, vente)
        if client_error:
            return client_error

        produits_data = data["produits"]

        # ✅ Remplacement des lignes sans toucher au stock
        VenteProduit.objects.select_for_update().filter(vente=vente).delete()

        for item in produits_data:
            quantite = item["quantite"]
            produit = _resolve_product_for_sale_item(item)

            if not produit:
                return error_response(
                    "PRODUCT_NOT_FOUND",
                    "Produit introuvable. Vérifiez produit_id, slug, sku ou qr.",
                    status.HTTP_404_NOT_FOUND,
                )

            prix_vente_grammes = item.get("prix_vente_grammes")

            if prix_vente_grammes in [None, "", 0, "0"]:
                try:
                    prix_vente_grammes = Decimal(str(produit.marque.prix))
                except Exception:
                    return error_response(
                        "PRICE_NOT_FOUND",
                        f"Aucun prix disponible pour {produit.nom}.",
                        status.HTTP_400_BAD_REQUEST,
                    )

            VenteProduit.objects.create(
                vente=vente,
                produit=produit,
                vendor=vendor,
                quantite=quantite,
                prix_vente_grammes=prix_vente_grammes,
                remise=item.get("remise", Decimal("0.00")),
                autres=item.get("autres", Decimal("0.00")),
            )

        vente.vendor = vendor
        vente.bijouterie = vendor.bijouterie
        vente.save(update_fields=["vendor", "bijouterie"])

        vente.mettre_a_jour_montant_total()
        vente.refresh_from_db()

        _recalculate_facture_from_vente(facture, vente, vendor)

        vente.refresh_from_db()

        return Response(
            VenteDetailSerializer(vente).data,
            status=status.HTTP_200_OK
        )

    @transaction.atomic
    def patch(self, request, vente_id):
        return self.put(request, vente_id)

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
- Ne touche pas au VendorStock.
- Ne crée pas InventoryMovement.
- Ne restaure pas le stock, car le stock n'a pas encore été consommé.
- Marque seulement la vente comme annulée.
- Verrouille la facture liée si elle existe.
- Refuse l'annulation si un paiement existe déjà.
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
    def post(self, request, vente_id):
        user = request.user
        role = get_role_name(user)

        if role not in [ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR]:
            return error_response(
                "ACCESS_DENIED",
                "Accès refusé.",
                status.HTTP_403_FORBIDDEN,
            )

        input_serializer = CancelProformaVenteSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        vente = get_object_or_404(
            Vente.objects
            .select_for_update()
            .select_related("vendor", "bijouterie", "client"),
            id=vente_id,
        )

        if vente.is_cancelled:
            return error_response(
                "VENTE_ALREADY_CANCELLED",
                "Cette vente est déjà annulée.",
                status.HTTP_400_BAD_REQUEST,
            )

        facture = _get_facture_locked(vente)

        facture_error = _validate_before_payment(facture)
        if facture_error:
            return facture_error

        if facture and facture.status != Facture.STAT_NON_PAYE:
            return error_response(
                "FACTURE_NOT_CANCELABLE",
                "Annulation impossible : la facture n'est plus non payée.",
                status.HTTP_400_BAD_REQUEST,
            )

        if facture and facture.total_paye > 0:
            return error_response(
                "FACTURE_HAS_PAYMENT",
                "Annulation impossible : un paiement existe déjà.",
                status.HTTP_400_BAD_REQUEST,
            )

        _, vendor_error = _resolve_vendor_for_update(
            data,
            request,
            vente,
            role,
        )
        if vendor_error:
            return vendor_error

        vente.is_cancelled = True
        vente.cancelled_at = timezone.now()
        vente.cancelled_by = user
        vente.save(
            update_fields=[
                "is_cancelled",
                "cancelled_at",
                "cancelled_by",
            ]
        )

        if facture:
            Facture.objects.filter(id=facture.id).update(
                is_locked=True,
                locked_at=timezone.now(),
            )

        vente.refresh_from_db()

        return Response(
            {
                "status": "success",
                "code": "VENTE_PROFORMA_CANCELLED",
                "message": "Vente non payée annulée avec succès.",
                "reason": data.get("reason"),
                "vente": VenteDetailSerializer(vente).data,
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
- facture payée
- stock déjà consommé
- délai maximum 72h
- restaure VendorStock
- crée InventoryMovement RETURN_IN
- FIFO réel basé sur SALE_OUT
        """,
        request_body=RetourVenteProduitSerializer,
        tags=["Ventes"],
    )
    @transaction.atomic
    def post(self, request, vente_id):

        user = request.user
        role = get_role_name(user)

        if role not in [ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR]:
            return error_response(
                "ACCESS_DENIED",
                "Accès refusé.",
                status.HTTP_403_FORBIDDEN,
            )

        input_serializer = RetourVenteProduitSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        vente = get_object_or_404(
            Vente.objects
            .select_for_update()
            .select_related(
                "vendor",
                "bijouterie",
                "client",
            ),
            id=vente_id,
        )

        if vente.is_cancelled:
            return error_response(
                "VENTE_CANCELLED",
                "Retour impossible : cette vente est annulée.",
                status.HTTP_400_BAD_REQUEST,
            )

        facture = _get_facture_locked(vente)

        if not facture:
            return error_response(
                "FACTURE_NOT_FOUND",
                "Retour impossible : aucune facture liée.",
                status.HTTP_404_NOT_FOUND,
            )

        if facture.status != Facture.STAT_PAYE:
            return error_response(
                "FACTURE_NOT_PAID",
                "Retour impossible : facture non payée.",
                status.HTTP_400_BAD_REQUEST,
            )

        if not facture.stock_consumed:
            return error_response(
                "STOCK_NOT_CONSUMED",
                "Retour impossible : stock non consommé.",
                status.HTTP_400_BAD_REQUEST,
            )

        reference_date = vente.delivered_at or facture.date_creation

        if timezone.now() > reference_date + timedelta(hours=72):
            return error_response(
                "RETURN_DELAY_EXPIRED",
                "Retour impossible : délai 72h dépassé.",
                status.HTTP_400_BAD_REQUEST,
            )

        _, vendor_error = _resolve_vendor_for_update(
            data,
            request,
            vente,
            role,
        )

        if vendor_error:
            return vendor_error

        reason = (
            data.get("reason")
            or "Retour client sous 72h"
        )

        produits_retour = data.get("produits") or []

        # =====================================================
        # AGREGER LES DEMANDES
        # =====================================================
        requested_by_line = {}

        for item in produits_retour:

            ligne_id = int(item["vente_ligne_id"])
            qty = int(item["quantite"])

            if qty <= 0:
                return error_response(
                    "INVALID_QTY",
                    "La quantité doit être supérieure à 0.",
                    status.HTTP_400_BAD_REQUEST,
                )

            requested_by_line[ligne_id] = (
                requested_by_line.get(ligne_id, 0) + qty
            )

        # =====================================================
        # FIFO DES SALE_OUT
        # =====================================================
        sale_outs = (
            InventoryMovement.objects
            .select_for_update()
            .filter(
                vente=vente,
                facture=facture,
                movement_type=InventoryMovement.MovementType.SALE_OUT,
            )
            .select_related(
                "produit",
                "produit_line",
                "lot",
                "vendor",
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
                vente_ligne_id__in=requested_by_line.keys()
            )

        total_returned_now = 0

        details = []

        # =====================================================
        # PARCOURS FIFO
        # =====================================================
        for move in sale_outs:

            ligne = move.vente_ligne

            if not ligne:
                continue

            already_returned = (
                InventoryMovement.objects
                .filter(
                    vente=vente,
                    facture=facture,
                    movement_type=InventoryMovement.MovementType.RETURN_IN,
                    vente_ligne=ligne,
                    produit_line=move.produit_line,
                )
                .aggregate(total=Sum("qty"))["total"]
                or 0
            )

            remaining_returnable = (
                int(move.qty)
                - int(already_returned)
            )

            if remaining_returnable <= 0:
                continue

            # =================================================
            # MODE PARTIEL
            # =================================================
            if requested_by_line:

                wanted_for_line = requested_by_line.get(
                    ligne.id,
                    0,
                )

                if wanted_for_line <= 0:
                    continue

                qty_to_return = min(
                    remaining_returnable,
                    wanted_for_line,
                )

                requested_by_line[ligne.id] -= qty_to_return

            else:
                qty_to_return = remaining_returnable

            # =================================================
            # RESTAURATION VENDOR STOCK
            # =================================================
            stock = (
                VendorStock.objects
                .select_for_update()
                .filter(
                    vendor=move.vendor,
                    produit_line=move.produit_line,
                )
                .first()
            )

            if not stock:
                return error_response(
                    "VENDOR_STOCK_NOT_FOUND",
                    f"Stock vendeur introuvable pour ligne {ligne.id}.",
                    status.HTTP_400_BAD_REQUEST,
                )

            if stock.quantite_vendue < qty_to_return:
                return error_response(
                    "INVALID_VENDOR_STOCK_STATE",
                    f"Stock vendeur incohérent pour {move.produit.nom}.",
                    status.HTTP_400_BAD_REQUEST,
                )

            stock.quantite_vendue -= qty_to_return

            stock.save(
                update_fields=[
                    "quantite_vendue",
                    "updated_at",
                ]
            )

            # =================================================
            # INVENTORY MOVEMENT RETURN_IN
            # =================================================
            log_move(
                produit=move.produit,
                qty=qty_to_return,
                movement_type=InventoryMovement.MovementType.RETURN_IN,
                src_bucket=InventoryMovement.Bucket.EXTERNAL,
                dst_bucket=InventoryMovement.Bucket.BIJOUTERIE,
                dst_bijouterie_id=move.vendor.bijouterie_id,
                unit_cost=move.unit_cost,
                produit_line=move.produit_line,
                lot=move.lot,
                vendor=move.vendor,
                vente=vente,
                facture=facture,
                vente_ligne=ligne,
                user=user,
                reason=reason,
            )

            total_returned_now += qty_to_return

            details.append({
                "vente_ligne_id": ligne.id,
                "produit_id": move.produit_id,
                "produit": move.produit.nom,
                "produit_line_id": move.produit_line_id,
                "lot_id": move.lot_id,
                "quantite_retournee": qty_to_return,
            })

        # =====================================================
        # QUANTITES NON RETOURNABLES
        # =====================================================
        if requested_by_line:

            not_returned = {
                k: v
                for k, v in requested_by_line.items()
                if v > 0
            }

            if not_returned:

                transaction.set_rollback(True)

                return error_response(
                    "RETURN_QTY_TOO_HIGH",
                    (
                        "Quantité demandée supérieure "
                        f"à la quantité retournable : {not_returned}"
                    ),
                    status.HTTP_400_BAD_REQUEST,
                )

        # =====================================================
        # RIEN RETOURNE
        # =====================================================
        if total_returned_now <= 0:
            return error_response(
                "NOTHING_TO_RETURN",
                "Aucune quantité retournable trouvée.",
                status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "status": "success",
                "code": "RETURN_IN_CREATED",
                "message": "Retour client enregistré avec succès.",

                "vente_id": vente.id,
                "numero_vente": vente.numero_vente,

                "facture": facture.numero_facture,

                "quantite_totale_retournee": total_returned_now,

                "details": details,
            },
            status=status.HTTP_200_OK,
        )





