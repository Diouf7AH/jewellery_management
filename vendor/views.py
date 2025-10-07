from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import F, Q, Sum
from collections import defaultdict
from backend.renderers import UserRenderer
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum
from io import BytesIO
from datetime import datetime
from django.utils import timezone
import datetime
from store.models import Produit, Bijouterie
from userauths.models import Role
from stock.models import Stock
from userauths.serializers import UserRegistrationSerializer, UserSerializer
from sale.models import VenteProduit
from sale.serializers import VenteProduitSerializer
from store.serializers import ProduitSerializer
from .models import Vendor, VendorProduit
from .serializer import (VendorProduitSerializer, VendorSerializer,
                        VendorStatusInputSerializer, UserSerializer,
                        VendorReadSerializer, VendorUpdateSerializer,
                        )

from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from django.contrib.auth import get_user_model
from inventory.models import InventoryMovement, MovementType, Bucket
# ⬇️ aligne le chemin du modèle de lot d’achat
from purchase.models import AchatProduitLot
from inventory.models import InventoryMovement, MovementType

# Create your views here.
User = get_user_model()
allowed_all_roles = ['admin', 'manager', 'vendeur']
allowed_roles_admin_manager = ['admin', 'manager',]


# Un dashboard riche avec produits, ventes et stats
# Un endpoint PATCH pour que le vendeur mette à jour son profil et son compte
# Un accès admin pour voir n’importe quel vendeur via user_id
# Un admin peut voir n'importe quel vendeur (avec user_id).
# Un manager peut aussi voir n'importe quel vendeur.
# Un vendeur peut uniquement voir son propre dashboard.
# class VendorDashboardView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_id="Dashboard Vendeur reserver pour vendeur seulement",
#         operation_description="Voir les statistiques d’un vendeur (admin, manager ou vendeur connecté).",
#         responses={200: "Statistiques du vendeur"}
#     )
#     def get(self, request):
#         user = request.user
#         role = getattr(user.user_role, 'role', None)
#         is_admin_or_manager_or_vendor = role in ['admin', 'manager', 'vendor']

#         # 🔎 Récupération et validation du user_id
#         user_id = request.GET.get('user_id')
#         if user_id:
#             if not user_id.isdigit():
#                 return Response({"detail": "user_id invalide."}, status=400)
#             if not is_admin_or_manager_or_vendor:
#                 return Response({"detail": "Accès refusé."}, status=403)
#             target_user = get_object_or_404(User, id=int(user_id))
#         else:
#             target_user = user

#         # 🔐 Vérifie que le compte est bien un vendeur
#         if not target_user.user_role or target_user.user_role.role != 'vendor':
#             return Response({"detail": "Ce compte n'est pas un vendeur."}, status=400)

#         try:
#             vendor = Vendor.objects.get(user=target_user)
#         except Vendor.DoesNotExist:
#             return Response({"detail": "Vendeur introuvable."}, status=404)

#         produits = VendorProduit.objects.filter(vendor=vendor)
#         ventes = VenteProduit.objects.filter(produit__in=produits.values('produit'))

#         # 📊 Statistiques globales
#         total_produits = produits.count()
#         total_ventes = ventes.count()
#         total_qte_vendue = ventes.aggregate(total=Sum('quantite'))['total'] or 0
#         total_montant = ventes.aggregate(total=Sum('sous_total_prix_vent'))['total'] or 0
#         stock_total = produits.aggregate(stock=Sum('quantite'))['stock'] or 0
#         total_remise = ventes.aggregate(remise=Sum('remise'))['remise'] or 0

#         # 📆 Regroupement par période
#         group_by = request.GET.get('group_by', 'month')
#         if group_by == 'day':
#             trunc = TruncDay('vente__created_at')
#         elif group_by == 'week':
#             trunc = TruncWeek('vente__created_at')
#         else:
#             trunc = TruncMonth('vente__created_at')

#         stats_grouped = (
#             ventes.annotate(period=trunc)
#             .values('period')
#             .annotate(
#                 total_qte=Sum('quantite'),
#                 total_montant=Sum('sous_total_prix_vent')
#             ).order_by('period')
#         )

#         top_produits = (
#             ventes.values('produit__id', 'produit__nom')
#             .annotate(total_qte=Sum('quantite'))
#             .order_by('-total_qte')[:5]
#         )
        
#         # Générer un tableau de produit
#         produits_tableau = (
#             ventes.values('produit__id', 'produit__slug',  'produit__nom')
#             .annotate(
#                 quantite_vendue=Sum('quantite'),
#                 montant_total=Sum('sous_total_prix_vent'),
#                 remise_totale=Sum('remise')
#             )
#             .order_by('-quantite_vendue')
#         )

#         return Response({
#             "vendeur": VendorSerializer(vendor).data,
#             "user": UserSerializer(target_user).data,
#             "stats": {
#                 "produits": total_produits,
#                 "ventes": total_ventes,
#                 "quantite_totale_vendue": total_qte_vendue,
#                 "stock_restant": stock_total,
#                 "montant_total_ventes": total_montant,
#                 "remise_totale": total_remise,
#             },
#             "stats_groupées": stats_grouped,
#             "top_produits": top_produits,
#             "produits": VendorProduitSerializer(produits, many=True).data,
#             "ventes": VenteProduitSerializer(ventes, many=True).data,
#             "produits_tableau": produits_tableau,
#         })

class VendorDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_id="Dashboard Vendeur (vendeur / admin / manager)",
        operation_description=(
            "Voir les statistiques d’un vendeur. "
            "Un vendeur voit son propre dashboard. "
            "Admin/manager peuvent cibler via ?user_id=... ou ?vendor_email=... "
            "Filtres: ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&group_by=day|week|month "
            "Export Excel: ?export=excel"
        ),
        manual_parameters=[
            openapi.Parameter("user_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="Cibler un user vendeur (admin/manager)"),
            openapi.Parameter("vendor_email", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Cibler un vendeur par email (admin/manager)"),
            openapi.Parameter("date_from", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Filtre début (YYYY-MM-DD)"),
            openapi.Parameter("date_to", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Filtre fin (YYYY-MM-DD)"),
            openapi.Parameter("group_by", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="day|week|month (par défaut: month)"),
            openapi.Parameter("export", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="excel pour exporter en .xlsx"),
        ],
        responses={200: "Statistiques du vendeur ou fichier Excel"}
    )
    def get(self, request):
        user = request.user
        role = getattr(getattr(user, 'user_role', None), 'role', None)
        is_admin_or_manager = role in {'admin', 'manager'}

        # -------- Sélection de la cible : vendor_email > user_id > self --------
        vendor_email = (request.query_params.get("vendor_email") or "").strip()
        user_id = request.query_params.get("user_id")

        target_user = None

        if vendor_email:
            # Vendeur ne peut cibler que lui-même
            if role == 'vendor' and vendor_email.lower() != user.email.lower():
                return Response({"detail": "Accès refusé: vous ne pouvez cibler que votre propre email."}, status=403)

            if not (is_admin_or_manager or user.is_superuser or role == 'vendor'):
                return Response({"detail": "Accès refusé."}, status=403)

            target_user = User.objects.filter(email__iexact=vendor_email).first()
            if not target_user:
                return Response({"detail": "Utilisateur introuvable pour cet email."}, status=404)

        elif user_id:
            if not user_id.isdigit():
                return Response({"detail": "user_id invalide."}, status=400)
            if not (is_admin_or_manager or user.is_superuser):
                return Response({"detail": "Accès refusé."}, status=403)
            target_user = get_object_or_404(User, id=int(user_id))

        else:
            target_user = user

        # Si les deux sont fournis, s'assurer qu'ils pointent vers le même user
        if vendor_email and user_id:
            if str(target_user.id) != str(user_id):
                return Response({"detail": "vendor_email et user_id ne pointent pas vers le même utilisateur."}, status=400)

        if getattr(getattr(target_user, 'user_role', None), 'role', None) != 'vendor':
            return Response({"detail": "Ce compte n'est pas un vendeur."}, status=400)

        vendor = Vendor.objects.select_related('user').filter(user=target_user).first()
        if not vendor:
            return Response({"detail": "Vendeur introuvable."}, status=404)

        # --- QS de base
        produits_qs = VendorProduit.objects.select_related('produit').filter(vendor=vendor)
        ventes_qs = (
            VenteProduit.objects
            .select_related('produit', 'vente', 'vendor', 'vendor__user')
            .filter(vendor=vendor)
        )

        # --- Filtres temporels
        date_from = request.query_params.get('date_from')
        date_to   = request.query_params.get('date_to')
        if date_from:
            ventes_qs = ventes_qs.filter(vente__created_at__date__gte=date_from)
        if date_to:
            ventes_qs = ventes_qs.filter(vente__created_at__date__lte=date_to)

        # --- Stats globales
        total_produits    = produits_qs.count()
        total_ventes      = ventes_qs.count()
        total_qte_vendue  = ventes_qs.aggregate(s=Sum('quantite'))['s'] or 0
        total_montant_ht  = ventes_qs.aggregate(s=Sum('sous_total_prix_vente_ht'))['s'] or 0
        total_montant_ttc = ventes_qs.aggregate(s=Sum('prix_ttc'))['s'] or 0
        stock_total       = produits_qs.aggregate(s=Sum('quantite'))['s'] or 0
        total_remise      = ventes_qs.aggregate(s=Sum('remise'))['s'] or 0

        # --- Regroupement (day/week/month)
        group_by = (request.query_params.get('group_by') or 'month').lower()
        if group_by == 'day':
            trunc = TruncDay('vente__created_at')
        elif group_by == 'week':
            trunc = TruncWeek('vente__created_at')
        else:
            trunc = TruncMonth('vente__created_at')

        stats_grouped = list(
            ventes_qs.annotate(period=trunc)
            .values('period')
            .annotate(
                total_qte=Sum('quantite'),
                total_montant_ht=Sum('sous_total_prix_vente_ht'),
                total_montant_ttc=Sum('prix_ttc'),
            )
            .order_by('period')
        )

        # --- Top produits
        top_produits = list(
            ventes_qs.values('produit__id', 'produit__nom', 'produit__slug')
            .annotate(total_qte=Sum('quantite'))
            .order_by('-total_qte')[:5]
        )

        # --- Tableau produits synthèse
        produits_tableau = list(
            ventes_qs.values('produit__id', 'produit__slug', 'produit__nom')
            .annotate(
                quantite_vendue=Sum('quantite'),
                montant_total_ht=Sum('sous_total_prix_vente_ht'),
                remise_totale=Sum('remise'),
            )
            .order_by('-quantite_vendue')
        )

        # --- Export Excel ?
        if (request.query_params.get("export") or "").lower() == "excel":
            return self._export_excel(
                vendor=vendor,
                stats={
                    "total_produits": total_produits,
                    "total_ventes": total_ventes,
                    "total_qte_vendue": total_qte_vendue,
                    "stock_total": stock_total,
                    "total_montant_ht": total_montant_ht,
                    "total_montant_ttc": total_montant_ttc,
                    "total_remise": total_remise,
                },
                ventes=list(ventes_qs),
                produits_tableau=produits_tableau,
                stats_grouped=stats_grouped,
                group_by=group_by,
            )

        # --- JSON par défaut
        try:
            from sale.serializers import VenteProduitSerializer as VPSerializer
            ventes_payload = VPSerializer(ventes_qs, many=True).data
        except Exception:
            ventes_payload = list(ventes_qs.values('id', 'vente_id', 'produit_id', 'quantite'))

        return Response({
            "vendeur": VendorSerializer(vendor).data,
            "user": {"id": target_user.id, "email": target_user.email, "slug": getattr(target_user, "slug", None)},
            "stats": {
                "produits": total_produits,
                "ventes": total_ventes,
                "quantite_totale_vendue": total_qte_vendue,
                "stock_restant": stock_total,
                "montant_total_ht": total_montant_ht,
                "montant_total_ttc": total_montant_ttc,
                "remise_totale": total_remise,
            },
            "stats_groupees": stats_grouped,
            "top_produits": top_produits,
            "produits": VendorProduitSerializer(produits_qs, many=True).data,
            "ventes": ventes_payload,
            "produits_tableau": produits_tableau,
        })

    # ---------- Export Excel helper (inchangé) ----------
    # def _export_excel(self, vendor, stats, ventes, produits_tableau, stats_grouped, group_by):
    #     try:
    #         from openpyxl import Workbook
    #         from openpyxl.utils import get_column_letter
    #     except ImportError:
    #         return Response({"detail": "openpyxl manquant. Installez-le : pip install openpyxl"}, status=500)

    #     wb = Workbook()
    #     ws = wb.active; ws.title = "Résumé"
    #     ws.append(["Dashboard vendeur"])
    #     ws.append(["Vendeur", getattr(getattr(vendor, "user", None), "email", "")])
    #     ws.append(["Slug", getattr(getattr(vendor, "user", None), "slug", "")])
    #     ws.append([])
    #     ws.append(["Indicateur", "Valeur"])
    #     ws.append(["Produits en stock", stats["total_produits"]])
    #     ws.append(["Ventes (lignes)", stats["total_ventes"]])
    #     ws.append(["Quantité totale vendue", stats["total_qte_vendue"]])
    #     ws.append(["Stock restant", stats["stock_total"]])
    #     ws.append(["Montant total HT", float(stats["total_montant_ht"] or 0)])
    #     ws.append(["Montant total TTC", float(stats["total_montant_ttc"] or 0)])
    #     ws.append(["Remise totale", float(stats["total_remise"] or 0)])

    #     ws2 = wb.create_sheet(title="Ventes")
    #     ws2.append(["Date vente", "N° vente", "Produit", "Slug", "Quantité", "Prix/gr.", "Sous-total HT", "Tax", "TTC", "Remise", "Autres", "Vendeur (email)"])
    #     for vp in ventes:
    #         vente = getattr(vp, "vente", None)
    #         produit = getattr(vp, "produit", None)
    #         vendeur = getattr(vp, "vendor", None)
    #         ws2.append([
    #             getattr(vente, "created_at", None).strftime("%Y-%m-%d %H:%M") if getattr(vente, "created_at", None) else "",
    #             getattr(vente, "numero_vente", ""),
    #             getattr(produit, "nom", "") if produit else "",
    #             getattr(produit, "slug", "") if produit else "",
    #             int(getattr(vp, "quantite", 0) or 0),
    #             float(getattr(vp, "prix_vente_grammes", 0) or 0),
    #             float(getattr(vp, "sous_total_prix_vente_ht", 0) or 0),
    #             float(getattr(vp, "tax", 0) or 0),
    #             float(getattr(vp, "prix_ttc", 0) or 0),
    #             float(getattr(vp, "remise", 0) or 0),
    #             float(getattr(vp, "autres", 0) or 0),
    #             getattr(getattr(vendeur, "user", None), "email", "") if vendeur else "",
    #         ])

    #     ws3 = wb.create_sheet(title="Produits (agrégés)")
    #     ws3.append(["Produit ID", "Slug", "Nom", "Quantité vendue", "Montant total HT", "Remise totale"])
    #     for row in produits_tableau:
    #         ws3.append([
    #             row.get("produit__id"),
    #             row.get("produit__slug"),
    #             row.get("produit__nom"),
    #             int(row.get("quantite_vendue") or 0),
    #             float(row.get("montant_total_ht") or 0),
    #             float(row.get("remise_totale") or 0),
    #         ])

    #     title_map = {"day": "Journalier", "week": "Hebdomadaire", "month": "Mensuel"}
    #     ws4 = wb.create_sheet(title=f"Série {title_map.get(group_by, group_by)}")
    #     ws4.append(["Période", "Total quantité", "Total HT", "Total TTC"])
    #     for r in stats_grouped:
    #         per = r.get("period")
    #         label = per.strftime("%Y-%m-%d") if hasattr(per, "strftime") else str(per)
    #         ws4.append([
    #             label,
    #             int(r.get("total_qte") or 0),
    #             float(r.get("total_montant_ht") or 0),
    #             float(r.get("total_montant_ttc") or 0),
    #         ])

    #     for sheet in wb.worksheets:
    #         for col_idx, _ in enumerate(next(sheet.iter_rows(min_row=1, max_row=1)), start=1):
    #             sheet.column_dimensions[get_column_letter(col_idx)].width = 18

    #     stream = BytesIO(); wb.save(stream); stream.seek(0)
    #     filename = f"dashboard_vendeur_{getattr(getattr(vendor, 'user', None), 'slug', 'vendeur')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    #     resp = HttpResponse(stream.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    #     resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    #     return resp

# Un endpoint PATCH pour que le vendeur mette à jour son profil et son compte
# class VendorProfileView(APIView):
#     permission_classes = [IsAuthenticated]

#     # @swagger_auto_schema(
#     #     operation_id="Vendeur - Voir mon profil",
#     #     operation_description="Voir son profil vendeur avec statistiques groupées par période.",
#     #     manual_parameters=[
#     #         openapi.Parameter('group_by', openapi.IN_QUERY, description="Période de regroupement (day, week, month)", type=openapi.TYPE_STRING, enum=['day', 'week', 'month'], default='month'),
#     #         openapi.Parameter('start_date', openapi.IN_QUERY, description="Date de début (YYYY-MM-DD)", type=openapi.TYPE_STRING),
#     #         openapi.Parameter('end_date', openapi.IN_QUERY, description="Date de fin (YYYY-MM-DD)", type=openapi.TYPE_STRING),
#     #     ],
#     #     responses={200: openapi.Response("Détails du profil vendeur", VendorSerializer)}
#     # )
#     # def get(self, request, user_id=None):
#     #     user = request.user

#     #     # if user_id and (not user.user_role or user.user_role.role != 'admin'):
#     #     #     return Response({"detail": "Accès refusé."}, status=403)
#     #     if not request.user.user_role or request.user.user_role.role not in allowed_roles_admin_manager:
#     #         return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

#     #     target_user = user if not user_id else get_object_or_404(User, id=user_id)

#     #     if not target_user.user_role or target_user.user_role.role != 'vendor':
#     #         return Response({"detail": "Ce compte n'est pas un vendeur."}, status=400)

#     #     try:
#     #         vendor = Vendor.objects.get(user=target_user)
#     #     except Vendor.DoesNotExist:
#     #         return Response({"detail": "Vendeur introuvable."}, status=404)

#     #     produits = VendorProduit.objects.filter(vendor=vendor)
#     #     ventes = VenteProduit.objects.filter(produit__in=produits.values('produit'))

#     #     # 🔎 Application de la période personnalisée si fournie
#     #     start_date = request.GET.get('start_date')
#     #     end_date = request.GET.get('end_date')
#     #     if start_date:
#     #         ventes = ventes.filter(vente__created_at__date__gte=parse_date(start_date))
#     #     if end_date:
#     #         ventes = ventes.filter(vente__created_at__date__lte=parse_date(end_date))

#     #     # 📊 Stats globales
#     #     total_produits = produits.count()
#     #     total_ventes = ventes.count()
#     #     total_qte_vendue = ventes.aggregate(total=Sum('quantite'))['total'] or 0
#     #     total_montant_ventes = ventes.aggregate(montant=Sum('sous_total_prix_vent'))['montant'] or 0
#     #     stock_total = produits.aggregate(stock=Sum('quantite'))['stock'] or 0

#     #     # 📆 Regroupement par période
#     #     group_by = request.GET.get('group_by', 'month')
#     #     if group_by == 'day':
#     #         trunc = TruncDay('vente__created_at')
#     #     elif group_by == 'week':
#     #         trunc = TruncWeek('vente__created_at')
#     #     else:
#     #         trunc = TruncMonth('vente__created_at')

#     #     stats_grouped = (
#     #         ventes
#     #         .annotate(period=trunc)
#     #         .values('period')
#     #         .annotate(
#     #             total_qte=Sum('quantite'),
#     #             total_montant=Sum('sous_total_prix_vent')
#     #         )
#     #         .order_by('period')
#     #     )

#     #     top_produits = (
#     #         ventes
#     #         .values('produit__id', 'produit__nom')
#     #         .annotate(total_qte=Sum('quantite'))
#     #         .order_by('-total_qte')[:5]
#     #     )

#     #     return Response({
#     #         "vendeur": VendorSerializer(vendor).data,
#     #         "user": UserSerializer(target_user).data,
#     #         "stats": {
#     #             "produits": total_produits,
#     #             "ventes": total_ventes,
#     #             "quantite_totale_vendue": total_qte_vendue,
#     #             "stock_restant": stock_total,
#     #             "montant_total_ventes": total_montant_ventes
#     #         },
#     #         "stats_groupées": stats_grouped,
#     #         "top_produits": top_produits,
#     #         "mode_groupement": group_by,
#     #         "produits": VendorProduitSerializer(produits, many=True).data,
#     #         "ventes": VenteProduitSerializer(ventes, many=True).data
#     #     })

#     @swagger_auto_schema(
#         operation_id="Vendeur - Modifier mon profil",
#         operation_description="Modifier son profil vendeur et utilisateur.",
#         request_body=VendorSerializer,
#         responses={200: VendorSerializer}
#     )
#     def patch(self, request):
#         user = request.user
#         if not user.user_role or user.user_role.role != 'vendor':
#             return Response({"detail": "⛔ Accès refusé."}, status=403)

#         try:
#             vendor = Vendor.objects.get(user=user)
#         except Vendor.DoesNotExist:
#             return Response({"detail": "Vendeur introuvable."}, status=404)

#         vendor_serializer = VendorSerializer(vendor, data=request.data, partial=True)

#         user_data = {
#             field: request.data.get(field)
#             for field in ['first_name', 'last_name', 'username', 'email', 'phone']
#             if field in request.data
#         }
#         user_serializer = UserSerializer(user, data=user_data, partial=True)

#         if vendor_serializer.is_valid() and user_serializer.is_valid():
#             vendor_serializer.save()
#             user_serializer.save()
#             return Response({
#                 "message": "✅ Profil mis à jour.",
#                 "user": user_serializer.data,
#                 "vendeur": vendor_serializer.data
#             })

#         return Response({
#             "errors": {
#                 "user": user_serializer.errors,
#                 "vendor": vendor_serializer.errors
#             }
#         }, status=400)

#     @swagger_auto_schema(
#         operation_id="Admin - Désactiver un vendeur",
#         operation_description="Désactiver un vendeur (admin uniquement).",
#         responses={204: "Vendeur désactivé avec succès."}
#     )
#     def delete(self, request, user_id=None):
#         allowed_roles_admin_manager = ['admin', 'manager']  # 🔧 ligne à ajouter
#         # if not request.user.user_role or request.user.user_role.role != 'admin':
#         #     return Response({"detail": "Accès refusé."}, status=403)
#         if not request.user.user_role or request.user.user_role.role not in self.allowed_roles_admin_manager:
#             return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

#         if not user_id:
#             return Response({"detail": "ID utilisateur requis."}, status=400)

#         try:
#             target_user = User.objects.get(id=user_id)
#             if target_user.user_role.role != 'vendor':
#                 return Response({"detail": "Ce n'est pas un vendeur."}, status=400)
#             vendor = Vendor.objects.get(user=target_user)
#             vendor.verifie = False
#             vendor.raison_desactivation = request.data.get('raison', 'Désactivation par l’administrateur')
#             vendor.save()
#             return Response({"message": "✅ Vendeur désactivé."}, status=204)
#         except User.DoesNotExist:
#             return Response({"detail": "Utilisateur introuvable."}, status=404)
#         except Vendor.DoesNotExist:
#             return Response({"detail": "Vendeur introuvable."}, status=404)
        

# Un vendeur authentifié peut appeler GET /api/vendor/produits/
# Il recevra la liste des produits associés à son stock
class VendorProduitListView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Lister les produits associés au vendeur connecté",
        responses={200: ProduitSerializer(many=True)},
    )
    def get(self, request):
        user = request.user
        role = getattr(user.user_role, 'role', None)

        if role != 'vendor':
            return Response({"error": "Seul un vendeur peut accéder à ses produits."}, status=403)

        try:
            vendor = Vendor.objects.get(user=user)
        except Vendor.DoesNotExist:
            return Response({"error": "Aucun vendeur associé à cet utilisateur."}, status=400)

        vendor_produits = VendorProduit.objects.filter(vendor=vendor).select_related('produit')
        produits = [vp.produit for vp in vendor_produits]
        serializer = ProduitSerializer(produits, many=True)

        return Response(serializer.data)
    

# class DashboardVendeurStatsAPIView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Dashboard du vendeur connecté.",
#         responses={200: "Données du vendeur et statistiques"}
#     )
#     def get(self, request):
#         user = request.user

#         # Vérifie que c’est bien un vendeur
#         if not user.user_role or user.user_role.role != 'vendor':
#             return Response({"detail": "Accès réservé aux vendeurs."}, status=403)

#         try:
#             vendor = Vendor.objects.get(user=user)
#         except Vendor.DoesNotExist:
#             return Response({"detail": "Profil vendeur introuvable."}, status=404)
        

#         # Produits assignés
#         produits = VendorProduit.objects.filter(vendor=vendor)
#         ventes = VenteProduit.objects.filter(produit__in=produits.values('produit'))

#         # Stats
#         total_produits = produits.count()
#         total_ventes = ventes.count()
#         total_qte_vendue = ventes.aggregate(total=models.Sum('quantite'))['total'] or 0
#         total_ventes_montant = ventes.aggregate(montant=models.Sum('sous_total_prix_vent'))['montant'] or 0
#         stock_total = produits.aggregate(stock=models.Sum('quantite'))['stock'] or 0

#         return Response({
#             "vendeur": VendorSerializer(vendor).data,
#             "produits": total_produits,
#             "ventes": total_ventes,
#             "quantite_totale_vendue": total_qte_vendue,
#             "stock_restant": stock_total,
#             "montant_total_ventes": total_ventes_montant
#         }, status=200)

# endpoint dédié (admin et manager only) pour activer / désactiver un vendeur
# admin puisse activer/désactiver un vendeur depuis un bouton (frontend),
# class ToggleVendorStatusView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]
    
#     @swagger_auto_schema(
#         operation_description="Admin - Mise à jour des statuts du vendeur (verifie).",
#         request_body=VendorSerializer,
#         responses={200: "Statut mis à jour"}
#     )

#     def patch(self, request, user_id):
#         allowed_roles_admin_manager = ['admin', 'manager'] 
#         if not request.user.user_role or request.user.user_role.role not in self.allowed_roles_admin_manager:
#             return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

#         try:
#             target_user = User.objects.get(id=user_id)
#             vendor = Vendor.objects.get(user=target_user)
#             vendor.verifie = not vendor.verifie  # 👈 toggle on/off
#             vendor.save()
#             return Response({
#                 "message": f"✅ Vendeur {'activé' if vendor.verifie else 'désactivé'}.",
#                 "verifie": vendor.verifie
#             })
#         except User.DoesNotExist:
#             return Response({"detail": "Utilisateur introuvable."}, status=404)
#         except Vendor.DoesNotExist:
#             return Response({"detail": "Vendeur introuvable."}, status=404)



# ---------- LISTE / LECTURE ----------
class VendorListView(generics.ListAPIView):
    """
    GET /api/vendors/?q=&bijouterie_id=&verifie=true|false
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = VendorReadSerializer

    def get_queryset(self):
        qs = Vendor.objects.select_related("user", "bijouterie").all()

        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(
                Q(user__email__icontains=q) |
                Q(user__username__icontains=q) |
                Q(user__first_name__icontains=q) |
                Q(user__last_name__icontains=q) |
                Q(user__telephone__icontains=q)
            )

        bijouterie_id = self.request.query_params.get("bijouterie_id")
        if bijouterie_id:
            qs = qs.filter(bijouterie_id=bijouterie_id)

        verifie = self.request.query_params.get("verifie")
        if verifie is not None:
            if verifie.lower() in ("true", "1", "yes", "oui"):
                qs = qs.filter(verifie=True)
            elif verifie.lower() in ("false", "0", "no", "non"):
                qs = qs.filter(verifie=False)

        return qs.order_by("-id")

    # Swagger
    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter("q", openapi.IN_QUERY, description="Recherche (email, username, nom, prénom, téléphone)", type=openapi.TYPE_STRING),
            openapi.Parameter("bijouterie_id", openapi.IN_QUERY, description="Filtrer par bijouterie id", type=openapi.TYPE_INTEGER),
            openapi.Parameter("verifie", openapi.IN_QUERY, description="true/false", type=openapi.TYPE_STRING),
        ],
        responses={200: VendorReadSerializer(many=True)}
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


# ---------- DÉTAIL / LECTURE + MÀJ ----------
class VendorDetailView(APIView):
    """
    GET  /api/vendors/<int:id>/
    GET  /api/vendors/by-slug/<slug:slug>/
    PATCH/PUT idem (avec VendorUpdateSerializer)
    """
    permission_classes = [permissions.IsAuthenticated]

    def _get_obj(self, **kwargs):
        vendor_id = kwargs.get("id") or kwargs.get("pk")
        slug = kwargs.get("slug") or self.request.query_params.get("slug")

        if vendor_id:
            return get_object_or_404(
                Vendor.objects.select_related("user", "bijouterie"),
                pk=vendor_id
            )
        if slug:
            return get_object_or_404(
                Vendor.objects.select_related("user", "bijouterie"),
                user__slug=slug
            )
        # Fallback explicite
        return get_object_or_404(
            Vendor.objects.select_related("user", "bijouterie"),
            pk=self.request.query_params.get("id")
        )

    def _can_update(self, request, vendor: Vendor) -> bool:
        role = getattr(getattr(request.user, "user_role", None), "role", None)
        is_admin_or_manager = role in {"admin", "manager"}
        is_owner = vendor.user_id == request.user.id
        return bool(is_admin_or_manager or is_owner)

    # --- GET ---
    @swagger_auto_schema(
        responses={200: VendorReadSerializer},
        manual_parameters=[
            openapi.Parameter("slug", openapi.IN_QUERY, description="(optionnel si non fourni dans l'URL) user.slug", type=openapi.TYPE_STRING),
            openapi.Parameter("id", openapi.IN_QUERY, description="(optionnel si non fourni dans l'URL) vendor id", type=openapi.TYPE_INTEGER),
        ],
    )
    def get(self, request, *args, **kwargs):
        vendor = self._get_obj(**kwargs)
        return Response(VendorReadSerializer(vendor).data)

    # --- PATCH ---
    @swagger_auto_schema(
        request_body=VendorUpdateSerializer,
        responses={200: VendorReadSerializer, 403: "Access Denied"},
    )
    def patch(self, request, *args, **kwargs):
        vendor = self._get_obj(**kwargs)
        if not self._can_update(request, vendor):
            return Response({"detail": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        s = VendorUpdateSerializer(vendor, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(VendorReadSerializer(vendor).data, status=200)

    # --- PUT (comportement identique, mais non-partial) ---
    @swagger_auto_schema(
        request_body=VendorUpdateSerializer,
        responses={200: VendorReadSerializer, 403: "Access Denied"},
    )
    def put(self, request, *args, **kwargs):
        vendor = self._get_obj(**kwargs)
        if not self._can_update(request, vendor):
            return Response({"detail": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        s = VendorUpdateSerializer(vendor, data=request.data, partial=False)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(VendorReadSerializer(vendor).data, status=200)


class UpdateVendorStatusAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    ALLOWED_ROLES = {"admin", "manager"}

    @swagger_auto_schema(
        operation_summary="Mise à jour du statut vendeur (verifie)",
        operation_description="Active/Désactive un vendeur via le champ booléen 'verifie'. "
                              "Autorisé: admin, manager.",
        request_body=VendorStatusInputSerializer,
        responses={200: "Statut mis à jour", 403: "Accès refusé", 404: "Vendeur introuvable"}
    )
    def patch(self, request, user_id: int):
        # 1) Rôle
        role = getattr(getattr(request.user, "user_role", None), "role", None)
        if role not in self.ALLOWED_ROLES:
            return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

        # 2) Vendeur
        vendor = Vendor.objects.select_related("user").filter(user_id=user_id).first()
        if not vendor:
            return Response({"detail": "Vendeur introuvable."}, status=status.HTTP_404_NOT_FOUND)

        # 3) (Optionnel) Si manager, vérifier même bijouterie
        # my_shop_id = getattr(getattr(request.user, "staff_manager_profile", None), "bijouterie_id", None)
        # if role == "manager" and my_shop_id and vendor.bijouterie_id != my_shop_id:
        #     return Response({"detail": "Vendeur d'une autre bijouterie."}, status=status.HTTP_403_FORBIDDEN)

        # 4) Validation du champ 'verifie'
        s = VendorStatusInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        old = bool(vendor.verifie)
        vendor.verifie = s.validated_data["verifie"]
        vendor.save(update_fields=["verifie"])

        return Response({
            "message": f"✅ Vendeur {'activé' if vendor.verifie else 'désactivé'}.",
            "vendor_id": vendor.id,
            "user_id": vendor.user_id,
            "verifie_avant": old,
            "verifie_apres": vendor.verifie,
            "email": getattr(vendor.user, "email", None),
        }, status=status.HTTP_200_OK)
    

# class VendorProduitAssociationAPIView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]
#     allowed_roles_admin_manager = ['admin', 'manager']

#     @swagger_auto_schema(
#         operation_description="Associer des produits à un vendeur et ajuster les stocks.",
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["email", "produits"],
#             properties={
#                 "email": openapi.Schema(type=openapi.TYPE_STRING),
#                 "produits": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["produit_id", "quantite"],
#                         properties={
#                             "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                             "quantite": openapi.Schema(type=openapi.TYPE_INTEGER),
#                         }
#                     )
#                 )
#             }
#         ),
#         responses={201: "Produits associés", 400: "Requête invalide", 403: "Accès refusé", 404: "Ressource introuvable"}
#     )
#     @transaction.atomic
#     def post(self, request):
#         if not request.user.user_role or request.user.user_role.role not in self.allowed_roles_admin_manager:
#             return Response({"message": "⛔ Accès refusé"}, status=403)

#         email = request.data.get("email")
#         produits_data = request.data.get("produits", [])

#         if not email:
#             return Response({"error": "L'email du vendeur est requis."}, status=400)

#         try:
#             vendor = Vendor.objects.select_related("user").get(user__email=email)
#         except Vendor.DoesNotExist:
#             return Response({"error": "Vendeur introuvable."}, status=404)

#         if not vendor.active:
#             return Response({"error": "Ce vendeur est désactivé."}, status=403)

#         if not produits_data:
#             return Response({"error": "La liste des produits est vide."}, status=400)

#         produits_associes = []

#         for produit_info in produits_data:
#             produit_id = produit_info.get("produit_id")
#             quantite = produit_info.get("quantite")

#             if not produit_id or quantite is None:
#                 return Response({"error": "Chaque produit doit avoir un `produit_id` et une `quantite`."}, status=400)

#             try:
#                 quantite = int(quantite)
#                 if quantite <= 0:
#                     return Response({"error": "Quantité doit être strictement positive."}, status=400)
#             except Exception:
#                 return Response({"error": "Quantité invalide."}, status=400)

#             try:
#                 produit = Produit.objects.get(id=produit_id)
#             except Produit.DoesNotExist:
#                 return Response({"error": f"Produit ID {produit_id} introuvable."}, status=404)

#             stock = Stock.objects.filter(produit=produit).first()
#             if not stock or stock.quantite < quantite:
#                 return Response({
#                     "error": f"Stock insuffisant pour le produit {produit.nom}. Stock actuel : {stock.quantite if stock else 0}"
#                 }, status=400)

#             vendor_produit, created = VendorProduit.objects.get_or_create(
#                 vendor=vendor,
#                 produit=produit,
#                 defaults={"quantite": quantite}
#             )

#             if not created:
#                 vendor_produit.quantite += quantite
#                 vendor_produit.save()

#             stock.quantite -= quantite
#             stock.save()

#             produits_associes.append({
#                 "produit_id": produit.id,
#                 "nom": produit.nom,
#                 "quantite_attribuee": quantite,
#                 "stock_vendeur": vendor_produit.quantite,
#                 "stock_restant_global": stock.quantite,
#                 "status": "créé" if created else "mis à jour"
#             })

#         return Response({
#             "message": "✅ Produits associés avec succès.",
#             "vendeur": {
#                 "id": vendor.id,
#                 "nom_complet": vendor.user.get_full_name(),
#                 "email": vendor.user.email
#             },
#             "produits": produits_associes
#         }, status=201)


# class VendorProduitAssociationAPIView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]
#     allowed_roles_admin_manager = {"admin", "manager"}

#     @swagger_auto_schema(
#         operation_description="Associer des produits à un vendeur et ajuster les stocks.",
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["email", "produits"],
#             properties={
#                 "email": openapi.Schema(type=openapi.TYPE_STRING),
#                 "produits": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["produit_id", "quantite"],
#                         properties={
#                             "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                             "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, description="> 0"),
#                         }
#                     )
#                 )
#             }
#         ),
#         responses={201: "Produits associés", 400: "Requête invalide", 403: "Accès refusé", 404: "Ressource introuvable"}
#     )
#     @transaction.atomic
#     def post(self, request):
#         # 1) Permissions
#         role = getattr(getattr(request.user, "user_role", None), "role", None)
#         if role not in self.allowed_roles_admin_manager:
#             return Response({"message": "⛔ Accès refusé"}, status=403)

#         # 2) Entrées
#         email = request.data.get("email")
#         produits_data = request.data.get("produits", [])

#         if not email:
#             return Response({"error": "L'email du vendeur est requis."}, status=400)
#         if not isinstance(produits_data, list) or not produits_data:
#             return Response({"error": "La liste des produits est vide ou invalide."}, status=400)

#         # 3) Vendeur
#         try:
#             vendor = Vendor.objects.select_related("user").get(user__email=email)
#         except Vendor.DoesNotExist:
#             return Response({"error": "Vendeur introuvable."}, status=404)

#         # ⚠️ Correction ici : 'verifie' (pas 'active')
#         if not vendor.verifie:
#             return Response({"error": "Ce vendeur est désactivé."}, status=403)

#         # 4) Normaliser/agréger les lignes (doublons produit_id -> somme des quantités)
#         demandes = defaultdict(int)
#         for item in produits_data:
#             try:
#                 pid = int(item.get("produit_id"))
#                 qty = int(item.get("quantite"))
#             except Exception:
#                 return Response({"error": "Chaque item doit contenir un produit_id et une quantite (entiers)."}, status=400)
#             if pid <= 0 or qty <= 0:
#                 return Response({"error": "produit_id et quantite doivent être > 0."}, status=400)
#             demandes[pid] += qty

#         # 5) Vérifier l’existence des produits demandés
#         produits = Produit.objects.filter(id__in=demandes.keys())
#         if produits.count() != len(demandes):
#             ids_trouves = set(produits.values_list("id", flat=True))
#             manquants = [pid for pid in demandes.keys() if pid not in ids_trouves]
#             return Response({"error": f"Produit(s) introuvable(s): {manquants}"}, status=404)

#         produits_by_id = {p.id: p for p in produits}

#         # 6) Préparer la réponse
#         produits_associes = []

#         # 7) Traiter chaque produit avec verrouillage ligne par ligne
#         for pid, qty in demandes.items():
#             produit = produits_by_id[pid]

#             # 7.a Stock global verrouillé (évite les races)
#             stock = (
#                 Stock.objects.select_for_update()
#                 .filter(produit_id=pid)
#                 .first()
#             )
#             if not stock:
#                 return Response({"error": f"Aucun stock pour le produit {produit.nom}."}, status=400)

#             if stock.quantite < qty:
#                 return Response(
#                     {"error": f"Stock insuffisant pour {produit.nom}. Stock actuel : {stock.quantite}, demandé : {qty}"},
#                     status=400,
#                 )

#             # 7.b Décrémente atomiquement si assez de stock
#             updated = (
#                 Stock.objects
#                 .filter(pk=stock.pk, quantite__gte=qty)
#                 .update(quantite=F("quantite") - qty)
#             )
#             if not updated:
#                 # Quelqu'un a peut-être pris le stock entre-temps
#                 return Response(
#                     {"error": f"Conflit de stock détecté pour {produit.nom}. Réessayez."},
#                     status=409,
#                 )
#             stock.refresh_from_db()

#             # 7.c Associer au vendeur (verrouiller/mettre à jour la ligne VendorProduit)
#             vp = (
#                 VendorProduit.objects.select_for_update()
#                 .filter(vendor=vendor, produit_id=pid)
#                 .first()
#             )
#             if vp:
#                 vp.quantite = F("quantite") + qty
#                 vp.save(update_fields=["quantite"])
#                 vp.refresh_from_db()
#                 status_item = "mis à jour"
#             else:
#                 vp = VendorProduit.objects.create(vendor=vendor, produit_id=pid, quantite=qty)
#                 status_item = "créé"

#             produits_associes.append({
#                 "produit_id": produit.id,
#                 "nom": produit.nom,
#                 "quantite_attribuee": qty,
#                 "stock_vendeur": vp.quantite,
#                 "stock_restant_global": stock.quantite,
#                 "status": status_item,
#             })

#         # 8) OK
#         return Response({
#             "message": "✅ Produits associés avec succès.",
#             "vendeur": {
#                 "id": vendor.id,
#                 "nom_complet": vendor.user.get_full_name() if vendor.user else "",
#                 "email": vendor.user.email if vendor.user else "",
#             },
#             "produits": produits_associes
#         }, status=201)


# class VendorProduitAssociationAPIView(APIView):
#     permission_classes = [permissions.IsAuthenticated]
#     allowed_roles_admin_manager = {"admin", "manager"}

#     @swagger_auto_schema(
#         operation_description=(
#             "tu peux faire évoluer VendorProduitAssociationAPIView pour gérer deux sources d’affectation :"
#             "Depuis un lot d’achat (affectation par lots) → on prélève sur le lot, on crédite le vendeur, "
#             "et on trace un InventoryMovement de type ALLOCATE (RESERVED → BIJOUTERIE)."
#             "Depuis le stock boutique “libre” (affectation directe) → on décrémente Stock, "
#             "on crédite le vendeur, sans mouvement d’inventaire (sinon tu compterais deux fois).\n\n"
#             "Associer des produits à un vendeur.\n\n"
#             "Deux modes par item :\n"
#             "- **Depuis un lot**: fournir `lot_id` + `quantite` (trace un mouvement ALLOCATE Reserved→Bijouterie).\n"
#             "- **Depuis le stock**: fournir `produit_id` + `quantite` (décrémente Stock, crédite le vendeur).\n"
#             "Ne pas mélanger `lot_id` et `produit_id` dans le même item."
#         ),
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["email", "items"],
#             properties={
#                 "email": openapi.Schema(type=openapi.TYPE_STRING, description="Email du vendeur cible"),
#                 "items": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["quantite"],
#                         properties={
#                             "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, description="> 0"),
#                             "lot_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="Affection par lot (option 1)"),
#                             "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="Affection depuis stock (option 2)"),
#                         }
#                     )
#                 )
#             }
#         ),
#         responses={
#             201: "Produits associés",
#             400: "Requête invalide",
#             403: "Accès refusé",
#             404: "Ressource introuvable"
#         }
#     )
#     @transaction.atomic
#     def post(self, request):
#         # --- 1) Permissions
#         role = getattr(getattr(request.user, "user_role", None), "role", None)
#         if role not in self.allowed_roles_admin_manager:
#             return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

#         # --- 2) Entrées
#         email = (request.data.get("email") or "").strip()
#         items = request.data.get("items") or []
#         if not email:
#             return Response({"error": "L'email du vendeur est requis."}, status=400)
#         if not isinstance(items, list) or not items:
#             return Response({"error": "La liste 'items' est vide ou invalide."}, status=400)

#         # --- 3) Vendeur + bijouterie
#         try:
#             vendor = Vendor.objects.select_related("user", "bijouterie").get(user__email__iexact=email)
#         except Vendor.DoesNotExist:
#             return Response({"error": "Vendeur introuvable."}, status=404)
#         if not vendor.verifie:
#             return Response({"error": "Ce vendeur est désactivé."}, status=403)
#         if not vendor.bijouterie_id:
#             return Response({"error": "Ce vendeur n’est rattaché à aucune bijouterie."}, status=400)
#         bijouterie: Bijouterie = vendor.bijouterie

#         # --- 4) Normalisation / agrégation
#         # On sépare les lignes lot vs stock et on agrège par clé (pour verrouiller une seule fois)
#         demandes_stock = defaultdict(int)   # {produit_id: total_qty}
#         demandes_lot   = defaultdict(int)   # {lot_id: total_qty}
#         lignes_norm    = []                 # pour la réponse

#         for raw in items:
#             try:
#                 qty = int(raw.get("quantite"))
#             except Exception:
#                 return Response({"error": "Chaque item doit contenir 'quantite' entière > 0."}, status=400)
#             if qty <= 0:
#                 return Response({"error": "quantite doit être > 0."}, status=400)

#             lot_id = raw.get("lot_id")
#             pid    = raw.get("produit_id")

#             if bool(lot_id) == bool(pid):
#                 return Response({"error": "Un item doit avoir soit 'lot_id' soit 'produit_id', pas les deux."}, status=400)

#             if lot_id:
#                 try:
#                     lot_id = int(lot_id)
#                 except Exception:
#                     return Response({"error": "lot_id doit être entier."}, status=400)
#                 demandes_lot[lot_id] += qty
#                 lignes_norm.append({"source": "lot", "lot_id": lot_id, "quantite": qty})
#             else:
#                 try:
#                     pid = int(pid)
#                 except Exception:
#                     return Response({"error": "produit_id doit être entier."}, status=400)
#                 demandes_stock[pid] += qty
#                 lignes_norm.append({"source": "stock", "produit_id": pid, "quantite": qty})

#         # --- 5) Préchargements
#         produits = {}
#         if demandes_stock:
#             qs_p = Produit.objects.in_bulk(demandes_stock.keys())
#             if len(qs_p) != len(demandes_stock):
#                 manq = sorted(set(demandes_stock.keys()) - set(qs_p.keys()))
#                 return Response({"error": f"Produit(s) introuvable(s): {manq}"}, status=404)
#             produits = qs_p

#         lots = {}
#         if demandes_lot:
#             # ⚠️ TODO : aligne les noms de champs de lot :
#             # - produit (FK → store.Produit)
#             # - quantite_restante ou available_qty
#             # - achat_produit (FK → AchatProduit) si tu veux tracer la ligne d’achat
#             lots_qs = (
#                 AchatProduitLot.objects
#                 .select_for_update()
#                 .select_related("produit")              # TODO: s'assure que le FK s'appelle bien 'produit'
#                 .filter(id__in=demandes_lot.keys())
#             )
#             lots = {l.id: l for l in lots_qs}
#             if len(lots) != len(demandes_lot):
#                 manq = sorted(set(demandes_lot.keys()) - set(lots.keys()))
#                 return Response({"error": f"Lot(s) introuvable(s): {manq}"}, status=404)

#         # --- 6) Traitement (lot → vendeur)
#         result_items = []
#         now = timezone.now()

#         for lot_id, qty in demandes_lot.items():
#             lot = lots[lot_id]
#             produit = getattr(lot, "produit", None)
#             if not produit:
#                 return Response({"error": f"Le lot #{lot_id} n’a pas de produit."}, status=400)

#             # ⚠️ TODO : remplace 'quantite_restante' par ton champ réel (ex: available_qty, reste, etc.)
#             dispo = getattr(lot, "quantite_restante", None)
#             if dispo is None:
#                 return Response({"error": "Le modèle de lot doit exposer la quantité disponible (ex: 'quantite_restante')."}, status=500)
#             if dispo < qty:
#                 return Response({"error": f"Lot #{lot_id} : quantité disponible insuffisante ({dispo} < {qty})."}, status=400)

#             # Décrément du lot
#             setattr(lot, "quantite_restante", dispo - qty)  # TODO: adapte le champ
#             lot.save(update_fields=["quantite_restante"])    # TODO: idem

#             # Crédit du vendeur (VendorProduit)
#             vp, created = VendorProduit.objects.select_for_update().get_or_create(
#                 vendor=vendor, produit=produit, defaults={"quantite": 0}
#             )
#             VendorProduit.objects.filter(pk=vp.pk).update(quantite=F("quantite") + qty)
#             vp.refresh_from_db(fields=["quantite"])

#             # Mouvement inventaire ALLOCATE (Reserved → Bijouterie)
#             InventoryMovement.objects.create(
#                 produit=produit,
#                 movement_type=MovementType.ALLOCATE,
#                 qty=qty,
#                 unit_cost=getattr(lot, "unit_cost", None),  # si dispo sur ton lot
#                 lot=lot,
#                 reason=f"Affectation lot #{lot_id} → vendeur {vendor.id}",
#                 src_bucket=Bucket.RESERVED,
#                 src_bijouterie=None,
#                 dst_bucket=Bucket.BIJOUTERIE,
#                 dst_bijouterie=bijouterie,
#                 # Liens achat si dispo
#                 achat=getattr(getattr(lot, "achat_produit", None), "achat", None),   # TODO: adapte
#                 achat_ligne=getattr(lot, "achat_produit", None),                     # TODO: adapte
#                 occurred_at=now,
#                 created_by=request.user,
#             )

#             result_items.append({
#                 "source": "lot",
#                 "lot_id": lot_id,
#                 "produit_id": produit.id,
#                 "produit_nom": getattr(produit, "nom", produit.id),
#                 "quantite": qty,
#                 "stock_vendeur": vp.quantite,
#                 "message": "Affecté depuis lot + mouvement ALLOCATE créé"
#             })

#         # --- 7) Traitement (stock → vendeur)
#         if demandes_stock:
#             # lock les lignes de stock correspondantes
#             stocks = {s.produit_id: s for s in
#                       Stock.objects.select_for_update().filter(produit_id__in=demandes_stock.keys())}
#             if len(stocks) != len(demandes_stock):
#                 manq = sorted(set(demandes_stock.keys()) - set(stocks.keys()))
#                 return Response({"error": f"Stock indisponible pour produit(s): {manq}"}, status=400)

#             for pid, qty in demandes_stock.items():
#                 produit = produits[pid]
#                 stock = stocks[pid]

#                 if stock.quantite < qty:
#                     return Response(
#                         {"error": f"Stock insuffisant pour {getattr(produit, 'nom', pid)}. "
#                                   f"Stock actuel: {stock.quantite}, demandé: {qty}"},
#                         status=400
#                     )

#                 # Décrément atomique du stock
#                 updated = Stock.objects.filter(pk=stock.pk, quantite__gte=qty)\
#                                        .update(quantite=F("quantite") - qty)
#                 if not updated:
#                     return Response({"error": f"Conflit de stock pour {getattr(produit, 'nom', pid)}. Réessayez."}, status=409)
#                 stock.refresh_from_db(fields=["quantite"])

#                 # Crédit du vendeur
#                 vp, created = VendorProduit.objects.select_for_update().get_or_create(
#                     vendor=vendor, produit=produit, defaults={"quantite": 0}
#                 )
#                 VendorProduit.objects.filter(pk=vp.pk).update(quantite=F("quantite") + qty)
#                 vp.refresh_from_db(fields=["quantite"])

#                 # Pas de mouvement d’inventaire ici (interne boutique → vendeur)
#                 result_items.append({
#                     "source": "stock",
#                     "produit_id": produit.id,
#                     "produit_nom": getattr(produit, "nom", produit.id),
#                     "quantite": qty,
#                     "stock_vendeur": vp.quantite,
#                     "stock_boutique_restant": stock.quantite,
#                     "message": "Affecté depuis stock (sans mouvement inventaire)"
#                 })

#         # --- 8) Réponse
#         return Response({
#             "message": "✅ Affectations effectuées.",
#             "vendeur": {
#                 "id": vendor.id,
#                 "email": vendor.user.email if vendor.user else None,
#                 "bijouterie_id": bijouterie.id,
#                 "bijouterie": getattr(bijouterie, "nom", None),
#             },
#             "items": result_items
#         }, status=201)



class VendorProduitAssociationAPIView(APIView):
    permission_classes = [IsAuthenticated]
    allowed_roles_admin_manager = {"admin", "manager"}

    @swagger_auto_schema(
        operation_description=(
            "Associer des produits à un vendeur et ajuster les stocks.\n\n"
            "- Si `lot_id` est fourni pour un item, on décrémente **aussi** le lot correspondant (FIFO manuel) "
            "et on journalise le mouvement VENDOR_ASSIGN en liant le lot.\n"
            "- Sans `lot_id`, on décrémente uniquement le stock global et on journalise le VENDOR_ASSIGN sans lot."
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["email", "produits"],
            properties={
                "email": openapi.Schema(type=openapi.TYPE_STRING),
                "produits": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        required=["produit_id", "quantite"],
                        properties={
                            "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                            "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, description="> 0"),
                            "lot_id": openapi.Schema(
                                type=openapi.TYPE_INTEGER,
                                description="ID du lot d’achat à débiter (optionnel)"
                            ),
                        }
                    )
                )
            }
        ),
        responses={
            201: "Produits associés",
            400: "Requête invalide",
            403: "Accès refusé",
            404: "Ressource introuvable",
        }
    )
    @transaction.atomic
    def post(self, request):
        # 1) Permissions
        role = getattr(getattr(request.user, "user_role", None), "role", None)
        if role not in self.allowed_roles_admin_manager:
            return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

        # 2) Entrées
        email = request.data.get("email")
        produits_data = request.data.get("produits", [])

        if not email:
            return Response({"error": "L'email du vendeur est requis."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(produits_data, list) or not produits_data:
            return Response({"error": "La liste des produits est vide ou invalide."}, status=status.HTTP_400_BAD_REQUEST)

        # 3) Vendeur
        try:
            vendor = Vendor.objects.select_related("user").get(user__email=email)
        except Vendor.DoesNotExist:
            return Response({"error": "Vendeur introuvable."}, status=status.HTTP_404_NOT_FOUND)
        if not vendor.verifie:
            return Response({"error": "Ce vendeur est désactivé."}, status=status.HTTP_403_FORBIDDEN)

        # ⚠️ On NE regroupe plus par produit_id pour conserver l'information de lot par item.
        #    On valide et normalise d'abord tous les items.
        cleaned_items = []
        produit_ids = set()
        lot_ids = set()

        for idx, raw in enumerate(produits_data, start=1):
            try:
                pid = int(raw.get("produit_id"))
                qty = int(raw.get("quantite"))
            except Exception:
                return Response(
                    {"error": f"Item {idx}: 'produit_id' et 'quantite' doivent être des entiers."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if pid <= 0 or qty <= 0:
                return Response(
                    {"error": f"Item {idx}: 'produit_id' et 'quantite' doivent être > 0."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            lot_id = raw.get("lot_id")
            if lot_id is not None:
                try:
                    lot_id = int(lot_id)
                    if lot_id <= 0:
                        return Response({"error": f"Item {idx}: 'lot_id' doit être > 0."},
                                        status=status.HTTP_400_BAD_REQUEST)
                    lot_ids.add(lot_id)
                except Exception:
                    return Response({"error": f"Item {idx}: 'lot_id' doit être un entier."},
                                    status=status.HTTP_400_BAD_REQUEST)

            produit_ids.add(pid)
            cleaned_items.append({"produit_id": pid, "quantite": qty, "lot_id": lot_id})

        # 4) Existence des produits
        produits = Produit.objects.filter(id__in=produit_ids)
        if produits.count() != len(produit_ids):
            ids_trouves = set(produits.values_list("id", flat=True))
            manquants = [pid for pid in produit_ids if pid not in ids_trouves]
            return Response({"error": f"Produit(s) introuvable(s): {manquants}"}, status=status.HTTP_404_NOT_FOUND)
        produits_by_id = {p.id: p for p in produits}

        # 5) Charger / vérifier les lots si présents
        lots_by_id = {}
        if lot_ids:
            lots = (AchatProduitLot.objects
                    .select_related("achat_ligne__produit")
                    .filter(id__in=lot_ids))
            if lots.count() != len(lot_ids):
                ids_trouves = set(lots.values_list("id", flat=True))
                manquants = [lid for lid in lot_ids if lid not in ids_trouves]
                return Response({"error": f"Lot(s) introuvable(s): {manquants}"}, status=status.HTTP_404_NOT_FOUND)
            lots_by_id = {l.id: l for l in lots}

        # 6) Traitement item par item (verrouillage par ligne)
        produits_associes = []
        for idx, item in enumerate(cleaned_items, start=1):
            pid = item["produit_id"]
            qty = item["quantite"]
            lot_id = item["lot_id"]
            produit = produits_by_id[pid]
            unit_cost = None

            # 6.a Verrouiller & décrémenter le stock global (agrégé)
            stock = Stock.objects.select_for_update().filter(produit_id=pid).first()
            if not stock:
                return Response({"error": f"Aucun stock pour le produit {produit.nom}."},
                                status=status.HTTP_400_BAD_REQUEST)
            if stock.quantite < qty:
                return Response(
                    {"error": f"Stock insuffisant pour {produit.nom}. Stock actuel : {stock.quantite}, demandé : {qty}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            updated = (Stock.objects
                       .filter(pk=stock.pk, quantite__gte=qty)
                       .update(quantite=F("quantite") - qty))
            if not updated:
                return Response({"error": f"Conflit de stock détecté pour {produit.nom}. Réessayez."},
                                status=status.HTTP_409_CONFLICT)
            stock.refresh_from_db()

            # 6.b Si lot indiqué : vérifier appariement & décrémenter le lot
            lot_code = None
            if lot_id:
                lot = (AchatProduitLot.objects
                       .select_for_update()
                       .select_related("achat_ligne__produit")
                       .get(pk=lot_id))
                # Cohérence produit <-> lot
                lot_prod_id = getattr(getattr(lot, "achat_ligne", None), "produit_id", None)
                if lot_prod_id != pid:
                    return Response(
                        {"error": f"Item {idx}: le lot #{lot_id} ne correspond pas au produit #{pid}."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                # Décrément sécurisé du lot
                updated_lot = (AchatProduitLot.objects
                               .filter(pk=lot.pk, quantite_restante__gte=qty)
                               .update(quantite_restante=F("quantite_restante") - qty))
                if not updated_lot:
                    return Response(
                        {"error": f"Lot #{lot_id}: quantité restante insuffisante (reste {lot.quantite_restante})."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                lot.refresh_from_db(fields=["quantite_restante"])
                unit_cost = lot.prix_achat_gramme
                lot_code = lot.lot_code

            # 6.c Associer au vendeur (VendorProduit)
            vp = (VendorProduit.objects
                  .select_for_update()
                  .filter(vendor=vendor, produit_id=pid)
                  .first())
            if vp:
                VendorProduit.objects.filter(pk=vp.pk).update(quantite=F("quantite") + qty)
                vp.refresh_from_db(fields=["quantite"])
                status_item = "mis à jour"
            else:
                vp = VendorProduit.objects.create(vendor=vendor, produit_id=pid, quantite=qty)
                status_item = "créé"

            # 6.d Mouvement d’affectation (journal) — VENDOR_ASSIGN
            InventoryMovement.objects.create(
                produit=produit,
                movement_type=MovementType.VENDOR_ASSIGN,
                qty=qty,
                unit_cost=unit_cost,     # renseigne le coût du lot si dispo
                lot_id=lot_id,           # 👈 lien direct au lot
                reason=f"Affectation au vendeur #{vendor.id}"
                       + (f" depuis lot {lot_code}" if lot_id else " depuis stock"),
                # pas d’obligation de buckets pour VENDOR_ASSIGN
                achat=None, achat_ligne=None,
                facture=None, vente=None, vente_ligne=None,
                created_by=request.user,
            )

            produits_associes.append({
                "produit_id": produit.id,
                "nom": produit.nom,
                "quantite_attribuee": qty,
                "lot_id": lot_id,
                "stock_vendeur": vp.quantite,
                "stock_restant_global": stock.quantite,
                "status": status_item,
            })

        # 7) OK
        return Response({
            "message": "✅ Produits associés avec succès.",
            "vendeur": {
                "id": vendor.id,
                "nom_complet": vendor.user.get_full_name() if vendor.user else "",
                "email": vendor.user.email if vendor.user else "",
            },
            "produits": produits_associes
        }, status=status.HTTP_201_CREATED)



# def _parse_iso_dt(s: str):
#     if not s:
#         return None
#     try:
#         dt = datetime.fromisoformat(s)
#     except ValueError:
#         # support YYYY-MM-DD
#         try:
#             dt = datetime.strptime(s, "%Y-%m-%d")
#         except ValueError:
#             return None
#     if timezone.is_naive(dt):
#         dt = timezone.make_aware(dt, timezone.get_current_timezone())
#     return dt
