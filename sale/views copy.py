# # from weasyprint import HTML
# # import weasyprint
# from __future__ import annotations

# from collections import defaultdict
# from datetime import date, datetime
# from datetime import time as dtime
# from datetime import timedelta
# from decimal import Decimal

# from django.conf import settings
# from django.core.exceptions import ValidationError
# from django.core.exceptions import ValidationError as DjangoValidationError
# from django.core.files.base import ContentFile
# from django.core.paginator import EmptyPage, Paginator
# from django.db import transaction
# from django.db.models import Count, Exists, F, OuterRef, Q, Sum
# from django.http import FileResponse, HttpResponse
# from django.shortcuts import get_object_or_404
# from django.utils import timezone
# from drf_yasg import openapi
# from drf_yasg.utils import swagger_auto_schema
# from openpyxl import Workbook
# from openpyxl.styles import Font, numbers
# from rest_framework import permissions, status
# from rest_framework.exceptions import ValidationError
# from rest_framework.exceptions import ValidationError as DRFValidationError
# from rest_framework.permissions import IsAuthenticated
# from rest_framework.response import Response
# from rest_framework.views import APIView

# from backend.mixins import (GROUP_BY_CHOICES, ExportXlsxMixin,
#                             aware_range_month, parse_month_or_default,
#                             resolve_tz)
# from backend.permissions import CanCreateSale, IsCashierOnly
# from backend.query_scopes import scope_bijouterie_q
# from backend.renderers import UserRenderer
# from backend.roles import (ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER, ROLE_VENDOR,
#                            get_role_name)
# from compte_depot.models import (ClientDepot, CompteDepot,
#                                  CompteDepotTransaction)
# from sale.models import VenteProduit  # adapte le chemin si besoin
# from sale.models import Client, Facture, Paiement, PaiementLigne, Vente
# from sale.pdf.escpos_ticket_80mm import build_escpos_recu_paiement_80mm
# from sale.pdf.facture_A5_paysage import build_facture_a5_paysage_pdf
# from sale.pdf.ticket_paiement_80mm import build_ticket_paiement_80mm_pdf
# from sale.pdf.ticket_proforma_58mm import build_ticket_proforma_58mm_pdf
# from sale.serializers import (FactureListSerializer, FactureSerializer,
#                               PaiementFactureMultiModeResponseSerializer,
#                               PaiementMultiModeSerializer,
#                               VenteCreateInSerializer, VenteDetailSerializer,
#                               VenteListSerializer)
# from sale.services.comptable_export_service import export_comptable_factures
# from sale.services.confirm_service import confirm_sale_out_from_vendor
# from sale.services.facture_hash_service import generate_facture_hash
# from sale.services.facture_pdf_service import generate_facture_pdf
# from sale.services.facture_qr_service import generate_facture_qr
# from sale.services.receipt_service import generate_recu_paiement_pdf_bytes
# from sale.services.sale_service import (cancel_sale_restore_direct,
#                                         create_sale_one_vendor,
#                                         upsert_client_for_payment,
#                                         validate_facture_payable)
# from staff.models import Cashier
# from store.models import Bijouterie, MarquePurete, Produit
# from vendor.models import Vendor

# from .utils import ensure_role_and_bijouterie, user_bijouterie

# DEFAULT_PAGE_SIZE = getattr(settings, "DEFAULT_PAGE_SIZE", 50)
# MAX_PAGE_SIZE = getattr(settings, "MAX_PAGE_SIZE", 100)



# # class VenteProduitCreateView(APIView):
# #     permission_classes = [CanCreateSale]
# #     http_method_names = ["post"]

# #     @swagger_auto_schema(
# #         operation_summary="Créer une vente (1 vendeur) + facture PROFORMA (stock non consommé)",
# #         request_body=VenteCreateInSerializer,
# #         responses={
# #             201: openapi.Response("Créé"),
# #             400: "Erreur validation",
# #             403: "Accès refusé",
# #         },
# #         tags=["Ventes"],
# #     )
# #     @transaction.atomic
# #     def post(self, request):
# #         serializer = VenteCreateInSerializer(data=request.data, context={"request": request})
# #         serializer.is_valid(raise_exception=True)
# #         validated = serializer.validated_data

# #         role = (get_role_name(request.user) or "").lower().strip()

# #         payload = {
# #             "client": validated.get("client") or {},
# #             "produits": validated["produits"],
# #         }

# #         if role in {ROLE_ADMIN, ROLE_MANAGER}:
# #             vendor_email = (validated.get("vendor_email") or "").strip()

# #             if not vendor_email:
# #                 return Response(
# #                     {"detail": "vendor_email est requis pour admin/manager."},
# #                     status=status.HTTP_400_BAD_REQUEST,
# #                 )

# #             vendor = (
# #                 Vendor.objects
# #                 .select_related("bijouterie", "user")
# #                 .filter(user__email__iexact=vendor_email)
# #                 .first()
# #             )
# #             if not vendor:
# #                 return Response(
# #                     {"detail": "Vendeur introuvable pour ce vendor_email."},
# #                     status=status.HTTP_400_BAD_REQUEST,
# #                 )

# #             if role == ROLE_MANAGER:
# #                 manager_profile = getattr(request.user, "staff_manager_profile", None)

# #                 if not manager_profile or (hasattr(manager_profile, "verifie") and not manager_profile.verifie):
# #                     return Response(
# #                         {"detail": "Profil manager invalide."},
# #                         status=status.HTTP_403_FORBIDDEN,
# #                     )

# #                 if not manager_profile.bijouteries.filter(id=vendor.bijouterie_id).exists():
# #                     return Response(
# #                         {"detail": "⛔ Vous ne pouvez pas créer une vente pour un vendeur hors de vos bijouteries."},
# #                         status=status.HTTP_403_FORBIDDEN,
# #                     )

# #             payload["vendor_email"] = vendor_email

# #         try:
# #             vente, facture, audit_created = create_sale_one_vendor(
# #                 user=request.user,
# #                 role=role,
# #                 payload=payload,
# #             )
# #         except ValidationError as e:
# #             detail = getattr(e, "message_dict", None) or getattr(e, "messages", None) or str(e)
# #             return Response(
# #                 {"detail": detail},
# #                 status=status.HTTP_400_BAD_REQUEST,
# #             )

# #         lignes = [
# #             {
# #                 "ligne_id": ligne.id,
# #                 "produit_id": ligne.produit_id,
# #                 "produit_nom": getattr(ligne.produit, "nom", None),
# #                 "quantite": ligne.quantite,
# #                 "prix_vente_grammes": str(ligne.prix_vente_grammes),
# #                 "montant_ht": str(ligne.montant_ht),
# #                 "remise": str(ligne.remise or 0),
# #                 "autres": str(ligne.autres or 0),
# #                 "montant_total": str(ligne.montant_total or 0),
# #                 "montant_ht": str(facture.montant_ht),
# #                 "taux_tva": str(facture.taux_tva),
# #                 "montant_tva": str(facture.montant_tva),
# #                 "montant_total": str(facture.montant_total),
# #             }
# #             for ligne in vente.lignes.select_related("produit").all()
# #         ]

# #         client = getattr(vente, "client", None)

# #         return Response(
# #             {
# #                 "message": "Vente créée avec succès.",
# #                 "vente_id": vente.id,
# #                 "numero_vente": vente.numero_vente,
# #                 "facture_id": facture.id,
# #                 "numero_facture": facture.numero_facture,
# #                 "type_facture": facture.type_facture,
# #                 "status_facture": facture.status,

# #                 "montant_ht": str(facture.montant_ht),
# #                 "taux_tva": str(facture.taux_tva),
# #                 "montant_tva": str(facture.montant_tva),
# #                 "montant_total": str(facture.montant_total),

# #                 "audit_created": bool(audit_created),
# #                 "bijouterie_id": facture.bijouterie_id,
# #                 "bijouterie_nom": getattr(facture.bijouterie, "nom", None),

# #                 "client": {
# #                     "id": client.id if client else None,
# #                     "nom": getattr(client, "nom", None) if client else None,
# #                     "prenom": getattr(client, "prenom", None) if client else None,
# #                     "telephone": getattr(client, "telephone", None) if client else None,
# #                 },

# #                 "lignes": lignes,
# #             },
# #             status=status.HTTP_201_CREATED,
# #         )
        
        


# class VenteProduitCreateView(APIView):
#     permission_classes = [CanCreateSale]
#     http_method_names = ["post"]

#     @swagger_auto_schema(
#         operation_summary="Créer une vente (1 vendeur) + facture PROFORMA (stock non consommé)",
#         request_body=VenteCreateInSerializer,
#         responses={
#             201: openapi.Response("Créé"),
#             400: "Erreur validation",
#             403: "Accès refusé",
#         },
#         tags=["Ventes"],
#     )
#     @transaction.atomic
#     def post(self, request):
#         serializer = VenteCreateInSerializer(
#             data=request.data,
#             context={"request": request}
#         )
#         serializer.is_valid(raise_exception=True)
#         validated = serializer.validated_data

#         role = (get_role_name(request.user) or "").lower().strip()

#         payload = {
#             "client": validated.get("client") or {},
#             "produits": validated["produits"],
#         }

#         if role in {ROLE_ADMIN, ROLE_MANAGER}:
#             vendor_email = (validated.get("vendor_email") or "").strip()

#             if not vendor_email:
#                 return Response(
#                     {"detail": "vendor_email est requis pour admin/manager."},
#                     status=status.HTTP_400_BAD_REQUEST,
#                 )

#             vendor = (
#                 Vendor.objects
#                 .select_related("bijouterie", "user")
#                 .filter(user__email__iexact=vendor_email)
#                 .first()
#             )
#             if not vendor:
#                 return Response(
#                     {"detail": "Vendeur introuvable pour ce vendor_email."},
#                     status=status.HTTP_400_BAD_REQUEST,
#                 )

#             if role == ROLE_MANAGER:
#                 manager_profile = getattr(request.user, "staff_manager_profile", None)

#                 if not manager_profile or (
#                     hasattr(manager_profile, "verifie") and not manager_profile.verifie
#                 ):
#                     return Response(
#                         {"detail": "Profil manager invalide."},
#                         status=status.HTTP_403_FORBIDDEN,
#                     )

#                 if not manager_profile.bijouteries.filter(id=vendor.bijouterie_id).exists():
#                     return Response(
#                         {"detail": "⛔ Vous ne pouvez pas créer une vente pour un vendeur hors de vos bijouteries."},
#                         status=status.HTTP_403_FORBIDDEN,
#                     )

#             payload["vendor_email"] = vendor_email

#         try:
#             vente, facture, audit_created = create_sale_one_vendor(
#                 user=request.user,
#                 role=role,
#                 payload=payload,
#             )
#         except ValidationError as e:
#             detail = getattr(e, "message_dict", None) or getattr(e, "messages", None) or str(e)
#             return Response(
#                 {"detail": detail},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         lignes = [
#             {
#                 "ligne_id": ligne.id,
#                 "produit_id": ligne.produit_id,
#                 "produit_nom": getattr(ligne.produit, "nom", None),
#                 "quantite": ligne.quantite,
#                 "prix_vente_grammes": str(ligne.prix_vente_grammes),
#                 "montant_ht": str(ligne.montant_ht),
#                 "remise": str(ligne.remise or 0),
#                 "autres": str(ligne.autres or 0),
#                 "montant_total": str(ligne.montant_total or 0),
#             }
#             for ligne in vente.lignes.select_related("produit").all()
#         ]

#         client = getattr(vente, "client", None)

#         return Response(
#             {
#                 "message": "Vente créée avec succès.",
#                 "vente_id": vente.id,
#                 "numero_vente": vente.numero_vente,

#                 "facture": {
#                     "facture_id": facture.id,
#                     "numero_facture": facture.numero_facture,
#                     "type_facture": facture.type_facture,
#                     "status_facture": facture.status,
#                     "montant_ht": str(facture.montant_ht),
#                     "taux_tva": str(facture.taux_tva),
#                     "montant_tva": str(facture.montant_tva),
#                     "montant_total": str(facture.montant_total),
#                 },

#                 "audit_created": bool(audit_created),

#                 "bijouterie": {
#                     "id": facture.bijouterie_id,
#                     "nom": getattr(facture.bijouterie, "nom", None),
#                 },

#                 "client": {
#                     "id": client.id if client else None,
#                     "nom": getattr(client, "nom", None) if client else None,
#                     "prenom": getattr(client, "prenom", None) if client else None,
#                     "telephone": getattr(client, "telephone", None) if client else None,
#                 },

#                 "lignes": lignes,
#             },
#             status=status.HTTP_201_CREATED,
#         )



# class AnnulerVenteView(APIView):
#     permission_classes = [IsAuthenticated]
#     http_method_names = ["post"]

#     @swagger_auto_schema(
#         operation_summary="Annuler une vente (cashier/manager) + restauration stock direct",
#         operation_description=(
#             "Annule une vente entière :\n"
#             "- restaure VendorStock.quantite_vendue\n"
#             "- crée RETURN_IN (audit)\n"
#             "- idempotent\n\n"
#             "✅ Rôles autorisés : cashier, manager.\n"
#             "Sécurité : même bijouterie.\n"
#             "❌ Interdit si facture PAYÉE ou si un paiement existe (même partiel)."
#         ),
#         tags=["Ventes"],
#         responses={200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found"},
#     )
#     @transaction.atomic
#     def post(self, request, vente_id: int):
#         user = request.user
#         role = (get_role_name(user) or "").lower()

#         # 0) Permissions
#         if role not in {"cashier", "manager"}:
#             return Response(
#                 {"detail": "⛔ Accès refusé (cashier/manager requis)."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         # 1) Bijouterie du user (scope)
#         user_shop = user_bijouterie(user)
#         if not user_shop:
#             return Response(
#                 {"detail": "Profil non rattaché à une bijouterie vérifiée."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         # 2) Lock facture liée (c'est elle qui porte la bijouterie + paiements)
#         facture = (
#             Facture.objects
#             .select_for_update()
#             .select_related("bijouterie", "vente")
#             .filter(vente_id=vente_id)
#             .first()
#         )
#         if not facture:
#             return Response({"detail": "Aucune facture liée à cette vente."}, status=status.HTTP_404_NOT_FOUND)

#         # 3) Sécurité bijouterie
#         if facture.bijouterie_id != user_shop.id:
#             return Response(
#                 {"detail": "Cette vente n’appartient pas à votre bijouterie."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         # 4) Lock vente (et lignes) après validation scope
#         vente = (
#             Vente.objects
#             .select_for_update()
#             .prefetch_related("produits__produit", "produits__vendor")
#             .filter(pk=vente_id)
#             .first()
#         )
#         if not vente:
#             return Response({"detail": "Vente introuvable."}, status=status.HTTP_404_NOT_FOUND)

#         # 5) Interdits : facture payée / paiement existant
#         if facture.status == Facture.STAT_PAYE:
#             return Response(
#                 {"detail": "Impossible d’annuler : facture déjà payée."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         if facture.paiements.exists():
#             total_paye = facture.paiements.aggregate(t=Sum("montant_paye"))["t"] or Decimal("0.00")
#             return Response(
#                 {
#                     "detail": "Impossible d’annuler : un paiement existe déjà sur cette facture.",
#                     "total_paye": str(total_paye),
#                 },
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         # 6) Annulation + restauration (idempotent)
#         try:
#             result = cancel_sale_restore_direct(user=user, vente=vente, facture=facture)
#         except ValidationError as e:
#             detail = getattr(e, "message_dict", None) or getattr(e, "messages", None) or str(e)
#             return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)

#         # 7) Refresh + réponse
#         vente.refresh_from_db()
#         facture.refresh_from_db()

#         already = bool(result.get("already_cancelled"))
#         return Response(
#             {
#                 "message": "Vente déjà annulée (idempotent)." if already else "Vente annulée. Stock restauré.",
#                 "returned_movements": int(result.get("returned_movements") or 0),
#                 "vente": VenteDetailSerializer(vente).data,
#                 "facture": FactureSerializer(facture).data,
#             },
#             status=status.HTTP_200_OK,
#         )
        


# DEFAULT_PAGE_SIZE = 20
# MAX_PAGE_SIZE = 100

# class ListFacturePayeesView(APIView):
#     permission_classes = [IsAuthenticated]

#     def get(self, request):
#         user = request.user
#         role = get_role_name(user)  # admin/manager/vendor/cashier

#         if role not in {ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR, ROLE_CASHIER}:
#             return Response({"detail": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

#         qs = (
#             Facture.objects
#             .select_related("bijouterie", "vente", "vente__client")
#             .prefetch_related(
#                 "paiements",
#                 "vente__produits__vendor",
#                 "vente__produits__produit",
#                 "vente__produits__produit__categorie",
#                 "vente__produits__produit__marque",
#                 "vente__produits__produit__purete",
#                 "vente__produits__produit__modele",
#             )
#             .filter(status=Facture.STAT_PAYE)
#         )

#         # ✅ scope bijouterie (admin=all, manager=M2M, vendor/cashier=1)
#         qs = qs.filter(scope_bijouterie_q(user, field="bijouterie_id"))

#         # ✅ fenêtre auto
#         months = 36 if role == ROLE_ADMIN else 18
#         min_datetime = timezone.now() - timedelta(days=months * 30)
#         qs = qs.filter(date_creation__gte=min_datetime)

#         # ✅ filtres
#         numero = (request.query_params.get("numero_facture") or "").strip()
#         if numero:
#             qs = qs.filter(numero_facture__icontains=numero)

#         vendor_id = request.query_params.get("vendor_id")
#         if vendor_id:
#             try:
#                 vendor_id_int = int(vendor_id)
#             except ValueError:
#                 return Response({"vendor_id": "Doit être un entier."}, status=status.HTTP_400_BAD_REQUEST)

#             # vendor ne filtre que lui-même
#             if role == ROLE_VENDOR:
#                 my_vendor = getattr(user, "staff_vendor_profile", None)
#                 if not my_vendor or (hasattr(my_vendor, "verifie") and not my_vendor.verifie):
#                     return Response({"detail": "Profil vendeur introuvable ou non vérifié."}, status=403)
#                 if vendor_id_int != my_vendor.id:
#                     return Response({"detail": "Un vendeur ne peut filtrer que ses propres factures."}, status=403)

#             # manager ne filtre que vendors de ses bijouteries
#             if role == ROLE_MANAGER:
#                 mp = getattr(user, "staff_manager_profile", None)
#                 if not mp or (hasattr(mp, "verifie") and not mp.verifie):
#                     return Response({"detail": "Profil manager invalide."}, status=403)
#                 if not mp.bijouteries.filter(vendors__id=vendor_id_int).exists():
#                     return Response({"detail": "Vendeur hors de vos bijouteries."}, status=403)

#             venteproduit_exists = VenteProduit.objects.filter(
#                 vente_id=OuterRef("vente_id"),
#                 vendor_id=vendor_id_int,
#             )
#             qs = qs.annotate(_has_vendor=Exists(venteproduit_exists)).filter(_has_vendor=True)

#         client_q = (request.query_params.get("client_q") or "").strip()
#         if client_q:
#             qs = qs.filter(
#                 Q(vente__client__nom__icontains=client_q) |
#                 Q(vente__client__prenom__icontains=client_q) |
#                 Q(vente__client__telephone__icontains=client_q)
#             )

#         payment_mode = (request.query_params.get("payment_mode") or "").strip()
#         if payment_mode:
#             qs = qs.filter(paiements__mode_paiement__iexact=payment_mode).distinct()

#         qs = qs.order_by("-date_creation")

#         # ✅ pagination safe
#         def _int(name: str, default: int) -> int:
#             val = request.query_params.get(name)
#             if val in (None, ""):
#                 return default
#             try:
#                 return int(val)
#             except ValueError:
#                 return default

#         page = max(1, _int("page", 1))
#         page_size = max(1, min(_int("page_size", DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))

#         paginator = Paginator(qs, page_size)

#         if paginator.count == 0:
#             return Response(
#                 {"count": 0, "page": 1, "page_size": page_size, "num_pages": 0, "results": []},
#                 status=200,
#             )

#         try:
#             page_obj = paginator.page(page)
#         except EmptyPage:
#             page_obj = paginator.page(paginator.num_pages)

#         return Response(
#             {
#                 "count": paginator.count,
#                 "page": page_obj.number,
#                 "page_size": page_size,
#                 "num_pages": paginator.num_pages,
#                 "results": FactureListSerializer(page_obj.object_list, many=True).data,
#             },
#             status=200,
#         )



# DEFAULT_PAGE_SIZE = 20
# MAX_PAGE_SIZE = 100

# class ListFacturesAPayerView(APIView):
#     permission_classes = [IsAuthenticated]

#     def get(self, request):
#         user = request.user
#         role = get_role_name(user)

#         if role not in {ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR, ROLE_CASHIER}:
#             return Response({"detail": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

#         qs = (
#             Facture.objects
#             .select_related("bijouterie", "vente", "vente__client")
#             .prefetch_related(
#                 "paiements",
#                 "vente__produits__vendor",
#                 "vente__produits__produit",
#                 "vente__produits__produit__categorie",
#                 "vente__produits__produit__marque",
#                 "vente__produits__produit__purete",
#                 "vente__produits__produit__modele",
#             )
#             .filter(status=Facture.STAT_NON_PAYE)
#         )

#         # ✅ Scope bijouterie
#         qs = qs.filter(scope_bijouterie_q(user, field="bijouterie_id"))

#         # ✅ Fenêtre auto
#         months = 36 if role == ROLE_ADMIN else 18
#         min_datetime = timezone.now() - timedelta(days=months * 30)
#         qs = qs.filter(date_creation__gte=min_datetime)

#         # ✅ Filtres
#         numero = (request.query_params.get("numero_facture") or "").strip()
#         if numero:
#             qs = qs.filter(numero_facture__icontains=numero)

#         client_q = (request.query_params.get("client_q") or "").strip()
#         if client_q:
#             qs = qs.filter(
#                 Q(vente__client__nom__icontains=client_q) |
#                 Q(vente__client__prenom__icontains=client_q) |
#                 Q(vente__client__telephone__icontains=client_q)
#             )

#         # (optionnel) payment_mode -> DISTINCT nécessaire uniquement ici
#         payment_mode = (request.query_params.get("payment_mode") or "").strip()
#         if payment_mode:
#             qs = qs.filter(paiements__mode_paiement__iexact=payment_mode).distinct()

#         qs = qs.order_by("-date_creation")

#         # ✅ Pagination safe
#         def _int(name: str, default: int) -> int:
#             val = request.query_params.get(name)
#             if val in (None, ""):
#                 return default
#             try:
#                 return int(val)
#             except ValueError:
#                 return default

#         page = max(1, _int("page", 1))
#         page_size = max(1, min(_int("page_size", DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))

#         paginator = Paginator(qs, page_size)

#         if paginator.count == 0:
#             return Response(
#                 {"count": 0, "page": 1, "page_size": page_size, "num_pages": 0, "results": []},
#                 status=status.HTTP_200_OK,
#             )

#         try:
#             page_obj = paginator.page(page)
#         except EmptyPage:
#             page_obj = paginator.page(paginator.num_pages)

#         return Response(
#             {
#                 "count": paginator.count,
#                 "page": page_obj.number,
#                 "page_size": page_size,
#                 "num_pages": paginator.num_pages,
#                 "results": FactureListSerializer(page_obj.object_list, many=True).data,
#             },
#             status=status.HTTP_200_OK,
#         )



# # class PaiementFactureMultiModeView(APIView):
# #     permission_classes = [IsAuthenticated, IsCashierOnly]

# #     @swagger_auto_schema(
# #         operation_id="payerFactureMultiModeParNumeroFacture",
# #         operation_summary="Payer une facture par numéro avec un ou plusieurs modes de paiement",
# #         operation_description="""
# # Permet à un **caissier uniquement** d'enregistrer un paiement sur une facture
# # à partir du **numéro de facture**.

# # ### Règles métier
# # - seul un **caissier** peut effectuer un paiement
# # - le paiement se fait via **numero_facture**
# # - une facture peut recevoir **plusieurs paiements**
# # - un paiement peut contenir **un ou plusieurs modes**
# # - les modes disponibles sont :
# #   - `cash`
# #   - `wave`
# #   - `orange_money`
# #   - `depot`
# # - si le mode est `depot`, le système :
# #   - vérifie que le client possède un profil `ClientDepot`
# #   - vérifie l'existence d'un `CompteDepot`
# #   - vérifie que le solde est suffisant
# #   - débite le compte
# #   - crée une transaction de type `Retrait`
# # - une facture déjà totalement payée ne peut plus être encaissée
# # - le total des lignes ne doit jamais dépasser le reste à payer
# # - au moment du paiement, les informations du client sont mises à jour
# # - au premier paiement : `proforma -> facture`
# # - si la facture devient totalement payée : consommation FIFO du stock vendeur
# #         """,
# #         tags=["Paiements"],
# #         request_body=PaiementMultiModeSerializer,
# #         responses={
# #             201: openapi.Response(
# #                 description="Paiement enregistré avec succès.",
# #                 schema=PaiementFactureMultiModeResponseSerializer,
# #             ),
# #             400: "Erreur de validation ou règle métier non respectée.",
# #             401: "Utilisateur non authentifié.",
# #             403: "Accès refusé. Seul un caissier peut effectuer un paiement.",
# #         },
# #     )
# #     @transaction.atomic
# #     def post(self, request, *args, **kwargs):
# #         serializer = PaiementMultiModeSerializer(data=request.data)
# #         serializer.is_valid(raise_exception=True)

# #         cashier = Cashier.objects.filter(user=request.user).first()
# #         if not cashier:
# #             raise ValidationError({"detail": "Seul un caissier peut effectuer un paiement."})

# #         facture = serializer.validated_data["facture"]
# #         client_data = serializer.validated_data["client"]
# #         lignes_preparees = serializer.validated_data["lignes_preparees"]

# #         facture = (
# #             Facture.objects
# #             .select_for_update()
# #             .select_related("vente", "vente__client", "bijouterie")
# #             .prefetch_related("paiements")
# #             .get(pk=facture.pk)
# #         )

# #         validate_facture_payable(facture)

# #         if not facture.vente:
# #             raise ValidationError({"facture": "Aucune vente associée à cette facture."})

# #         client = upsert_client_for_payment(
# #             facture=facture,
# #             client_data=client_data,
# #         )

# #         total_payload = sum(
# #             (item["montant_paye"] for item in lignes_preparees),
# #             Decimal("0.00"),
# #         )

# #         if total_payload > facture.reste_a_payer:
# #             raise ValidationError({
# #                 "total": (
# #                     f"Le total des lignes ({total_payload}) dépasse le reste à payer "
# #                     f"({facture.reste_a_payer})."
# #                 )
# #             })

# #         paiement = Paiement.objects.create(
# #             facture=facture,
# #             created_by=request.user,
# #             cashier=cashier,
# #         )

# #         lignes_creees = []

# #         for item in lignes_preparees:
# #             mode = item["mode_obj"]
# #             montant_paye = item["montant_paye"]
# #             reference = item.get("reference")

# #             compte_depot = None
# #             transaction_depot = None

# #             if mode.est_mode_depot:
# #                 client_depot = ClientDepot.objects.filter(pk=client.pk).first()
# #                 if not client_depot:
# #                     raise ValidationError({
# #                         "depot": "Ce client ne possède pas de profil ClientDepot."
# #                     })

# #                 compte_depot = (
# #                     CompteDepot.objects
# #                     .select_for_update()
# #                     .filter(client=client_depot)
# #                     .first()
# #                 )
# #                 if not compte_depot:
# #                     raise ValidationError({
# #                         "depot": "Aucun compte dépôt trouvé pour ce client."
# #                     })

# #                 if compte_depot.solde < montant_paye:
# #                     raise ValidationError({
# #                         "depot": f"Solde insuffisant. Solde actuel : {compte_depot.solde} FCFA."
# #                     })

# #                 compte_depot.solde = compte_depot.solde - montant_paye
# #                 compte_depot.save(update_fields=["solde"])

# #                 transaction_depot = Transaction.objects.create(
# #                     compte=compte_depot,
# #                     type_transaction=Transaction.TYPE_RETRAIT,
# #                     montant=montant_paye,
# #                     user=request.user,
# #                     statut=Transaction.STAT_TERMINE,
# #                     facture=facture,
# #                     reference=reference or f"Paiement facture {facture.numero_facture}",
# #                     commentaire="Retrait depuis compte dépôt pour paiement facture",
# #                 )

# #             ligne = PaiementLigne(
# #                 paiement=paiement,
# #                 montant_paye=montant_paye,
# #                 mode_paiement=mode,
# #                 reference=reference,
# #                 compte_depot=compte_depot,
# #                 transaction_depot=transaction_depot,
# #             )

# #             try:
# #                 ligne.full_clean()
# #             except DjangoValidationError as e:
# #                 raise ValidationError(
# #                     e.message_dict if hasattr(e, "message_dict") else e.messages
# #                 )

# #             ligne.save()
# #             lignes_creees.append(ligne)

# #         # ✅ Au premier paiement : PROFORMA -> FACTURE
# #         if facture.type_facture == Facture.TYPE_PROFORMA:
# #             facture.type_facture = Facture.TYPE_FACTURE
# #             facture.save(update_fields=["type_facture"])

# #         # ✅ Recalcule uniquement le status
# #         Facture.recompute_facture_status(facture)
# #         facture.refresh_from_db()

# #         # ✅ Si totalement payée : consommation FIFO
# #         audit_result = {"created": 0, "already": 0, "lines_done": 0}

# #         if facture.status == Facture.STAT_PAYE and not facture.stock_consumed:
# #             audit_result = confirm_sale_out_from_vendor(
# #                 facture=facture,
# #                 by_user=request.user,
# #             )
# #             facture.refresh_from_db()

# #         response_data = {
# #             "message": "Paiement enregistré avec succès.",
# #             "paiement_id": paiement.id,
# #             "facture_id": facture.id,
# #             "numero_facture": facture.numero_facture,
# #             "type_facture": facture.type_facture,
# #             "montant_total_facture": facture.montant_total,
# #             "montant_operation": paiement.montant_total_paye,
# #             "total_paye": facture.total_paye,
# #             "reste_a_payer": facture.reste_a_payer,
# #             "status": facture.status,
# #             "stock_consumed": getattr(facture, "stock_consumed", False),
# #             "client": {
# #                 "id": client.id if client else None,
# #                 "nom": client.nom if client else None,
# #                 "prenom": client.prenom if client else None,
# #                 "telephone": client.telephone if client else None,
# #             },
# #             "lignes": [
# #                 {
# #                     "id": ligne.id,
# #                     "mode_paiement": ligne.mode_paiement.code,
# #                     "mode_paiement_nom": ligne.mode_paiement.nom,
# #                     "montant_paye": ligne.montant_paye,
# #                     "reference": ligne.reference,
# #                 }
# #                 for ligne in lignes_creees
# #             ],
# #             "stock_consumption": audit_result,
# #         }

# #         response_serializer = PaiementFactureMultiModeResponseSerializer(instance=response_data)
# #         return Response(response_serializer.data, status=201)


# class PaiementFactureMultiModeView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Paiement facture multi-mode",
#         operation_description="""
#     Paiement d'une facture avec plusieurs modes :

#     - cash
#     - wave
#     - orange money
#     - dépôt

#     Règles :
#     - PROFORMA → FACTURE au premier paiement
#     - si facture PAYÉE → consommation stock
#     - génération automatique PDF facture
#     - aucun stockage du reçu de paiement
#             """,
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["numero_facture", "client", "lignes"],
#             properties={
#                 "numero_facture": openapi.Schema(type=openapi.TYPE_STRING),
#                 "client": openapi.Schema(
#                     type=openapi.TYPE_OBJECT,
#                     required=["nom", "prenom"],
#                     properties={
#                         "nom": openapi.Schema(type=openapi.TYPE_STRING),
#                         "prenom": openapi.Schema(type=openapi.TYPE_STRING),
#                         "telephone": openapi.Schema(type=openapi.TYPE_STRING),
#                     },
#                 ),
#                 "lignes": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["mode", "montant"],
#                         properties={
#                             "mode": openapi.Schema(type=openapi.TYPE_STRING),
#                             "montant": openapi.Schema(type=openapi.TYPE_NUMBER),
#                             "reference": openapi.Schema(type=openapi.TYPE_STRING),
#                         },
#                     ),
#                 ),
#             },
#         ),
#         responses={201: "Paiement effectué"},
#         tags=["Paiements"],
#     )
#     @transaction.atomic
#     def post(self, request):

#         numero_facture = request.data.get("numero_facture")
#         client_data = request.data.get("client", {})
#         lignes_data = request.data.get("lignes", [])

#         if not numero_facture:
#             return Response({"detail": "numero_facture requis"}, status=400)

#         if not lignes_data:
#             return Response({"detail": "lignes requises"}, status=400)

#         # 🔒 Lock facture
#         facture = (
#             Facture.objects
#             .select_for_update()
#             .select_related("vente", "vente__client", "bijouterie")
#             .prefetch_related("paiements__lignes")
#             .get(numero_facture=numero_facture)
#         )

#         validate_facture_payable(facture)

#         # 👤 client
#         client = upsert_client_for_payment(
#             facture=facture,
#             client_data=client_data
#         )

#         # 💰 paiement principal
#         paiement = Paiement.objects.create(
#             facture=facture,
#             created_by=request.user,
#             cashier=Cashier.objects.filter(user=request.user).first()
#         )

#         total = Decimal("0.00")

#         lignes_creees = []

#         for item in lignes_data:
#             mode = item.get("mode")
#             montant = Decimal(str(item.get("montant") or "0"))

#             if montant <= 0:
#                 raise DjangoValidationError("Montant invalide")

#             ligne = PaiementLigne.objects.create(
#                 paiement=paiement,
#                 montant_paye=montant,
#                 reference=item.get("reference"),
#             )

#             total += montant
#             lignes_creees.append(ligne)

#         if total > facture.reste_a_payer:
#             raise DjangoValidationError("Montant dépasse le reste")

#         # 🔄 statut facture
#         Facture.recompute_facture_status(facture)
#         facture.refresh_from_db()

#         # 🔁 PROFORMA → FACTURE
#         if facture.type_facture == Facture.TYPE_PROFORMA:
#             facture.type_facture = Facture.TYPE_FACTURE
#             facture.save(update_fields=["type_facture"])

#         # 📦 consommation stock
#         audit = {"created": 0, "already": 0, "lines_done": 0}

#         if facture.status == Facture.STAT_PAYE and not facture.stock_consumed:
#             audit = confirm_sale_out_from_vendor(
#                 facture=facture,
#                 by_user=request.user
#             )

#         # 📄 génération PDF facture
#         facture_pdf_url = None
            
            
#         if facture.status == Facture.STAT_PAYE:

#             if not facture.facture_pdf:

#                 # 🔒 1. recalcul propre AVANT signature
#                 facture.refresh_from_db()

#                 # 🔐 2. générer hash (signature logique)
#                 if not facture.integrity_hash:
#                     generate_facture_hash(facture)

#                 # 📱 3. générer QR code
#                 if not facture.qr_code_image:
#                     generate_facture_qr(facture)

#                 # 📄 4. générer PDF FINAL
#                 facture_pdf_url = generate_facture_pdf(facture)

#                 # 🔒 5. LOCK après tout
#                 facture.is_locked = True
#                 facture.locked_at = timezone.now()
#                 facture.save(update_fields=["is_locked", "locked_at"])

#             else:
#                 try:
#                     facture_pdf_url = facture.facture_pdf.url
#                 except:
#                     facture_pdf_url = None

#         # 🎯 RESPONSE
#         return Response({
#             "message": "Paiement effectué avec succès",
#             "facture": facture.numero_facture,
#             "status": facture.status,
#             "total_paye": str(facture.total_paye),
#             "reste": str(facture.reste_a_payer),
#             "facture_pdf_url": facture_pdf_url,
#             "stock": audit,
#         }, status=status.HTTP_201_CREATED)
# # -------------------END PaiementFactureView-------------------


# # PDF
# def _can_access_facture(user, facture: Facture) -> bool:
#     role = (get_role_name(user) or "").lower().strip()

#     if role == ROLE_ADMIN:
#         return True

#     if role == ROLE_MANAGER:
#         manager_profile = getattr(user, "staff_manager_profile", None)
#         if not manager_profile or (hasattr(manager_profile, "verifie") and not manager_profile.verifie):
#             return False
#         return manager_profile.bijouteries.filter(id=facture.bijouterie_id).exists()

#     if role == ROLE_CASHIER:
#         cashier_profile = getattr(user, "staff_cashier_profile", None)
#         if not cashier_profile or (hasattr(cashier_profile, "verifie") and not cashier_profile.verifie):
#             return False
#         return getattr(cashier_profile, "bijouterie_id", None) == facture.bijouterie_id

#     if role == ROLE_VENDOR:
#         vente = getattr(facture, "vente", None)
#         if not vente:
#             return False
#         vendor_profile = getattr(user, "staff_vendor_profile", None)
#         if not vendor_profile or (hasattr(vendor_profile, "verifie") and not vendor_profile.verifie):
#             return False
#         return vente.vendor_id == getattr(vendor_profile, "id", None)

#     return False


# class TicketProforma58mmView(APIView):
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

#         if not facture.vente_id:
#             return Response(
#                 {"detail": "Aucune vente associée à cette facture."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         pdf_buffer = build_ticket_proforma_58mm_pdf(
#             vente=facture.vente,
#             facture=facture,
#         )

#         filename = f"ticket_proforma_{facture.numero_facture}.pdf"
#         return FileResponse(pdf_buffer, as_attachment=False, filename=filename)

# class TicketPaiement80mmESCPosView(APIView):
#     permission_classes = [IsAuthenticated]

#     def get(self, request, numero_facture: str):
#         facture = get_object_or_404(
#             Facture.objects.select_related("vente", "bijouterie", "vente__client"),
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
#             .order_by("-date_paiement", "-id")
#             .first()
#         )

#         if not paiement:
#             return Response(
#                 {"detail": "Aucun paiement trouvé"},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         bijouterie = facture.bijouterie
#         client = getattr(facture.vente, "client", None)

#         shop_name = getattr(bijouterie, "nom", "RIO-GOLD")
#         shop_phone = getattr(bijouterie, "telephone", None)

#         client_nom = None
#         if client:
#             client_nom = f"{client.prenom} {client.nom}".strip()

#         cashier_nom = None
#         if paiement.cashier:
#             cashier_nom = str(paiement.cashier)

#         escpos_bytes = build_escpos_recu_paiement_80mm(
#             shop_name=shop_name,
#             shop_phone=shop_phone,
#             numero_facture=facture.numero_facture,
#             date_paiement=paiement.date_paiement,
#             montant_paye=paiement.montant_total_paye,
#             reste_a_payer=facture.reste_a_payer,
#         )

#         return HttpResponse(
#             escpos_bytes,
#             content_type="application/octet-stream"
#         )


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
    


# from sale.services.export.export_facture_excel import export_factures_excel


# class ExportFacturesExcelView(APIView):
#     permission_classes = [IsAuthenticated]

#     def get(self, request):
#         factures = Facture.objects.all().select_related(
#             "vente",
#             "vente__client",
#             "vente__vendor__user",
#             "bijouterie",
#         )
#         return export_factures_excel(factures)
    


# class ExportComptableView(APIView):
#     permission_classes = [IsAuthenticated]

#     def get(self, request):
#         factures = Facture.objects.filter(status=Facture.STAT_PAYE).prefetch_related("paiements")
#         wb = export_comptable_factures(factures)

#         response = HttpResponse(
#             content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
#         )
#         response["Content-Disposition"] = 'attachment; filename="comptabilite.xlsx"'

#         wb.save(response)
#         return response
    
    


