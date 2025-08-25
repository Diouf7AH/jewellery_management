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
from django.db.models import F, Q
from collections import defaultdict
from backend.renderers import UserRenderer
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum

from django.utils import timezone
import datetime
from store.models import Produit, Bijouterie
from userauths.models import Role
from stock.models import Stock
from userauths.serializers import UserRegistrationSerializer, UserSerializer
from sale.models import VenteProduit
from sale.serializers import VenteProduitSerializer
from store.serializers import ProduitSerializer
from django.db import IntegrityError

from .models import Vendor, VendorProduit, Cashier
from .serializer import (VendorProduitSerializer, VendorSerializer,
                        VendorUpdateStatusSerializer,CashierSerializer, UserSerializer,
                        CreateStaffMemberSerializer, VendorReadSerializer, VendorUpdateSerializer,
                        CashierReadSerializer, CashierUpdateSerializer)

from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from django.contrib.auth import get_user_model
from userauths.models import Role

# Create your views here.
# User = get_user_model()
# allowed_all_roles = ['admin', 'manager', 'vendeur']
# allowed_roles_admin_manager = ['admin', 'manager',]


# Un dashboard riche avec produits, ventes et stats
# Un endpoint PATCH pour que le vendeur mette à jour son profil et son compte
# Un accès admin pour voir n’importe quel vendeur via user_id
# Un admin peut voir n'importe quel vendeur (avec user_id).
# Un manager peut aussi voir n'importe quel vendeur.
# Un vendeur peut uniquement voir son propre dashboard.
class VendorDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_id="Dashboard Vendeur reserver pour vendeur seulement",
        operation_description="Voir les statistiques d’un vendeur (admin, manager ou vendeur connecté).",
        responses={200: "Statistiques du vendeur"}
    )
    def get(self, request):
        user = request.user
        role = getattr(user.user_role, 'role', None)
        is_admin_or_manager = role in ['admin', 'manager']

        # 🔎 Récupération et validation du user_id
        user_id = request.GET.get('user_id')
        if user_id:
            if not user_id.isdigit():
                return Response({"detail": "user_id invalide."}, status=400)
            if not is_admin_or_manager:
                return Response({"detail": "Accès refusé."}, status=403)
            target_user = get_object_or_404(User, id=int(user_id))
        else:
            target_user = user

        # 🔐 Vérifie que le compte est bien un vendeur
        if not target_user.user_role or target_user.user_role.role != 'vendor':
            return Response({"detail": "Ce compte n'est pas un vendeur."}, status=400)

        try:
            vendor = Vendor.objects.get(user=target_user)
        except Vendor.DoesNotExist:
            return Response({"detail": "Vendeur introuvable."}, status=404)

        produits = VendorProduit.objects.filter(vendor=vendor)
        ventes = VenteProduit.objects.filter(produit__in=produits.values('produit'))

        # 📊 Statistiques globales
        total_produits = produits.count()
        total_ventes = ventes.count()
        total_qte_vendue = ventes.aggregate(total=Sum('quantite'))['total'] or 0
        total_montant = ventes.aggregate(total=Sum('sous_total_prix_vent'))['total'] or 0
        stock_total = produits.aggregate(stock=Sum('quantite'))['stock'] or 0
        total_remise = ventes.aggregate(remise=Sum('remise'))['remise'] or 0

        # 📆 Regroupement par période
        group_by = request.GET.get('group_by', 'month')
        if group_by == 'day':
            trunc = TruncDay('vente__created_at')
        elif group_by == 'week':
            trunc = TruncWeek('vente__created_at')
        else:
            trunc = TruncMonth('vente__created_at')

        stats_grouped = (
            ventes.annotate(period=trunc)
            .values('period')
            .annotate(
                total_qte=Sum('quantite'),
                total_montant=Sum('sous_total_prix_vent')
            ).order_by('period')
        )

        top_produits = (
            ventes.values('produit__id', 'produit__nom')
            .annotate(total_qte=Sum('quantite'))
            .order_by('-total_qte')[:5]
        )
        
        # Générer un tableau de produit
        produits_tableau = (
            ventes.values('produit__id', 'produit__slug',  'produit__nom')
            .annotate(
                quantite_vendue=Sum('quantite'),
                montant_total=Sum('sous_total_prix_vent'),
                remise_totale=Sum('remise')
            )
            .order_by('-quantite_vendue')
        )

        return Response({
            "vendeur": VendorSerializer(vendor).data,
            "user": UserSerializer(target_user).data,
            "stats": {
                "produits": total_produits,
                "ventes": total_ventes,
                "quantite_totale_vendue": total_qte_vendue,
                "stock_restant": stock_total,
                "montant_total_ventes": total_montant,
                "remise_totale": total_remise,
            },
            "stats_groupées": stats_grouped,
            "top_produits": top_produits,
            "produits": VendorProduitSerializer(produits, many=True).data,
            "ventes": VenteProduitSerializer(ventes, many=True).data,
            "produits_tableau": produits_tableau,
        })

# Un endpoint PATCH pour que le vendeur mette à jour son profil et son compte
class VendorProfileView(APIView):
    permission_classes = [IsAuthenticated]

    # @swagger_auto_schema(
    #     operation_id="Vendeur - Voir mon profil",
    #     operation_description="Voir son profil vendeur avec statistiques groupées par période.",
    #     manual_parameters=[
    #         openapi.Parameter('group_by', openapi.IN_QUERY, description="Période de regroupement (day, week, month)", type=openapi.TYPE_STRING, enum=['day', 'week', 'month'], default='month'),
    #         openapi.Parameter('start_date', openapi.IN_QUERY, description="Date de début (YYYY-MM-DD)", type=openapi.TYPE_STRING),
    #         openapi.Parameter('end_date', openapi.IN_QUERY, description="Date de fin (YYYY-MM-DD)", type=openapi.TYPE_STRING),
    #     ],
    #     responses={200: openapi.Response("Détails du profil vendeur", VendorSerializer)}
    # )
    # def get(self, request, user_id=None):
    #     user = request.user

    #     # if user_id and (not user.user_role or user.user_role.role != 'admin'):
    #     #     return Response({"detail": "Accès refusé."}, status=403)
    #     if not request.user.user_role or request.user.user_role.role not in allowed_roles_admin_manager:
    #         return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

    #     target_user = user if not user_id else get_object_or_404(User, id=user_id)

    #     if not target_user.user_role or target_user.user_role.role != 'vendor':
    #         return Response({"detail": "Ce compte n'est pas un vendeur."}, status=400)

    #     try:
    #         vendor = Vendor.objects.get(user=target_user)
    #     except Vendor.DoesNotExist:
    #         return Response({"detail": "Vendeur introuvable."}, status=404)

    #     produits = VendorProduit.objects.filter(vendor=vendor)
    #     ventes = VenteProduit.objects.filter(produit__in=produits.values('produit'))

    #     # 🔎 Application de la période personnalisée si fournie
    #     start_date = request.GET.get('start_date')
    #     end_date = request.GET.get('end_date')
    #     if start_date:
    #         ventes = ventes.filter(vente__created_at__date__gte=parse_date(start_date))
    #     if end_date:
    #         ventes = ventes.filter(vente__created_at__date__lte=parse_date(end_date))

    #     # 📊 Stats globales
    #     total_produits = produits.count()
    #     total_ventes = ventes.count()
    #     total_qte_vendue = ventes.aggregate(total=Sum('quantite'))['total'] or 0
    #     total_montant_ventes = ventes.aggregate(montant=Sum('sous_total_prix_vent'))['montant'] or 0
    #     stock_total = produits.aggregate(stock=Sum('quantite'))['stock'] or 0

    #     # 📆 Regroupement par période
    #     group_by = request.GET.get('group_by', 'month')
    #     if group_by == 'day':
    #         trunc = TruncDay('vente__created_at')
    #     elif group_by == 'week':
    #         trunc = TruncWeek('vente__created_at')
    #     else:
    #         trunc = TruncMonth('vente__created_at')

    #     stats_grouped = (
    #         ventes
    #         .annotate(period=trunc)
    #         .values('period')
    #         .annotate(
    #             total_qte=Sum('quantite'),
    #             total_montant=Sum('sous_total_prix_vent')
    #         )
    #         .order_by('period')
    #     )

    #     top_produits = (
    #         ventes
    #         .values('produit__id', 'produit__nom')
    #         .annotate(total_qte=Sum('quantite'))
    #         .order_by('-total_qte')[:5]
    #     )

    #     return Response({
    #         "vendeur": VendorSerializer(vendor).data,
    #         "user": UserSerializer(target_user).data,
    #         "stats": {
    #             "produits": total_produits,
    #             "ventes": total_ventes,
    #             "quantite_totale_vendue": total_qte_vendue,
    #             "stock_restant": stock_total,
    #             "montant_total_ventes": total_montant_ventes
    #         },
    #         "stats_groupées": stats_grouped,
    #         "top_produits": top_produits,
    #         "mode_groupement": group_by,
    #         "produits": VendorProduitSerializer(produits, many=True).data,
    #         "ventes": VenteProduitSerializer(ventes, many=True).data
    #     })

    @swagger_auto_schema(
        operation_id="Vendeur - Modifier mon profil",
        operation_description="Modifier son profil vendeur et utilisateur.",
        request_body=VendorSerializer,
        responses={200: VendorSerializer}
    )
    def patch(self, request):
        user = request.user
        if not user.user_role or user.user_role.role != 'vendor':
            return Response({"detail": "⛔ Accès refusé."}, status=403)

        try:
            vendor = Vendor.objects.get(user=user)
        except Vendor.DoesNotExist:
            return Response({"detail": "Vendeur introuvable."}, status=404)

        vendor_serializer = VendorSerializer(vendor, data=request.data, partial=True)

        user_data = {
            field: request.data.get(field)
            for field in ['first_name', 'last_name', 'username', 'email', 'phone']
            if field in request.data
        }
        user_serializer = UserSerializer(user, data=user_data, partial=True)

        if vendor_serializer.is_valid() and user_serializer.is_valid():
            vendor_serializer.save()
            user_serializer.save()
            return Response({
                "message": "✅ Profil mis à jour.",
                "user": user_serializer.data,
                "vendeur": vendor_serializer.data
            })

        return Response({
            "errors": {
                "user": user_serializer.errors,
                "vendor": vendor_serializer.errors
            }
        }, status=400)

    @swagger_auto_schema(
        operation_id="Admin - Désactiver un vendeur",
        operation_description="Désactiver un vendeur (admin uniquement).",
        responses={204: "Vendeur désactivé avec succès."}
    )
    def delete(self, request, user_id=None):
        allowed_roles_admin_manager = ['admin', 'manager']  # 🔧 ligne à ajouter
        # if not request.user.user_role or request.user.user_role.role != 'admin':
        #     return Response({"detail": "Accès refusé."}, status=403)
        if not request.user.user_role or request.user.user_role.role not in self.allowed_roles_admin_manager:
            return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

        if not user_id:
            return Response({"detail": "ID utilisateur requis."}, status=400)

        try:
            target_user = User.objects.get(id=user_id)
            if target_user.user_role.role != 'vendor':
                return Response({"detail": "Ce n'est pas un vendeur."}, status=400)
            vendor = Vendor.objects.get(user=target_user)
            vendor.verifie = False
            vendor.raison_desactivation = request.data.get('raison', 'Désactivation par l’administrateur')
            vendor.save()
            return Response({"message": "✅ Vendeur désactivé."}, status=204)
        except User.DoesNotExist:
            return Response({"detail": "Utilisateur introuvable."}, status=404)
        except Vendor.DoesNotExist:
            return Response({"detail": "Vendeur introuvable."}, status=404)
        

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
class ToggleVendorStatusView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Admin - Mise à jour des statuts du vendeur (verifie).",
        request_body=VendorSerializer,
        responses={200: "Statut mis à jour"}
    )

    def patch(self, request, user_id):
        allowed_roles_admin_manager = ['admin', 'manager'] 
        if not request.user.user_role or request.user.user_role.role not in self.allowed_roles_admin_manager:
            return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

        try:
            target_user = User.objects.get(id=user_id)
            vendor = Vendor.objects.get(user=target_user)
            vendor.verifie = not vendor.verifie  # 👈 toggle on/off
            vendor.save()
            return Response({
                "message": f"✅ Vendeur {'activé' if vendor.verifie else 'désactivé'}.",
                "verifie": vendor.verifie
            })
        except User.DoesNotExist:
            return Response({"detail": "Utilisateur introuvable."}, status=404)
        except Vendor.DoesNotExist:
            return Response({"detail": "Vendeur introuvable."}, status=404)


# class ListVendorAPIView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         responses={200: openapi.Response('Liste des vendeurs', VendorSerializer(many=True))},
#     )
#     def get(self, request):
#         allowed_roles = ['admin', 'manager']
#         role = getattr(request.user.user_role, 'role', None)

#         if role not in allowed_roles:
#             return Response({"message": "Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

#         vendors = Vendor.objects.all()
#         serializer = VendorSerializer(vendors, many=True)
#         return Response(serializer.data, status=status.HTTP_200_OK)

# class CreateVendorView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]
    
#     @swagger_auto_schema(
#         operation_description="Créer un nouveau vendeur le vendeur est recherche a traver son email qui se trouvedans le table user",
#         request_body=VendorSerializer,
#         responses={
#             201: VendorSerializer,
#             400: "Données invalides"
#         }
#     )
#     def post(self, request, *args, **kwargs):
#         if not request.user.user_role or request.user.user_role.role not in allowed_roles:
#             return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
#         # Get user data from request
#         username = request.data.get('username')
#         password = request.data.get('password')
#         email = request.data.get('email')
#         first_name = request.data.get('first_name')
#         last_name = request.data.get('last_name')
#         phone = request.data.get('phone')
#         # user_role = request.data.get('user_role')
#         bijoterie = request.data.get('bijoterie')
#         description = request.data.get('description')

#         try:
#             # Check if the user exists
#             user = User.objects.filter(email=email).first()

#             # affecte user on user_role
#             role = Role.objects.get(role='vendor')
#             user_role = role
            
#             #if user and vandor are not exists
#             if not user:
#                 # User doesn't exist, create a new user
#                 user = User.objects.create_user(email=email,
#                                                 username=username, 
#                                                 password=password, 
#                                                 first_name=first_name,
#                                                 user_role=user_role,
#                                                 last_name=last_name,
#                                                 phone=phone
#                                                 )
                
#                 # Create a new vendor associated with the new user
#                 vendor = Vendor.objects.create(user=user, bijoterie=bijoterie, description=description)
                
#                 # Serialize user and vendor data
#                 user_data = UserRegistrationSerializer(user)
#                 vendor_data = VendorSerializer(vendor)

#                 # Return the created user and vendor data as response
#                 return Response({
#                     'user': user_data.data,
#                     'vendor': vendor_data.data
#                 }, status=status.HTTP_201_CREATED)
            
#             elif user:
#                 # If user already exists, you create a vendor return the user and vendor data
#                 # Create a new vendor associated with the new user
#                 #update role
#                 role = Role.objects.get(role='vendor')
#                 user.user_role = role
#                 user.save()
#                 vendor = Vendor.objects.create(user=user, bijoterie=bijoterie, description=description)
#                 # vendor = user.user_vendor  # Assuming one-to-one relationship recupere le id du user
#                 user_data = UserRegistrationSerializer(user)
#                 vendor_data = VendorSerializer(vendor)

#                 return Response({
#                     'user': user_data.data,
#                     'vendor': vendor_data.data
#                 }, status=status.HTTP_200_OK)
#         except Exception as e:
#                 # return Response({"error": str(e)})
#                 return Response({'error': 'Vendor already exists.'}, status=status.HTTP_400_BAD_REQUEST)


# class CreateVendorView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]
#     allowed_roles_admin_manager = ['admin', 'manager']

#     @swagger_auto_schema(
#         operation_description="Créer un vendeur via un utilisateur existant (email et nom de la bijouterie).",
#         request_body=CreateVendorSerializer,
#         responses={
#             201: openapi.Response(description="Vendeur créé", schema=VendorSerializer),
#             400: openapi.Response(description="Erreur ou données invalides"),
#             403: openapi.Response(description="⛔ Accès refusé")
#         }
#     )
#     def post(self, request, *args, **kwargs):
#         # 🔐 Vérification du rôle utilisateur
#         # user_role = getattr(request.user.user_role, 'role', None)

#         # if user_role not in allowed_roles:
#         #     return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

#         if not request.user.user_role or request.user.user_role.role not in self.allowed_roles_admin_manager:
#             return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

#         # ✅ Validation via serializer
#         serializer = CreateVendorSerializer(data=request.data)
#         if not serializer.is_valid():
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#         validated_data = serializer.validated_data
#         email = validated_data['email']
#         bijouterie = validated_data['bijouterie']
#         description = validated_data.get('description', '')

#         # 🔍 Rôle vendeur
#         role_vendor = Role.objects.filter(role='vendor').first()
#         if not role_vendor:
#             return Response({"error": "Le rôle 'vendor' n'existe pas."}, status=status.HTTP_400_BAD_REQUEST)

#         # 🔍 Recherche de l'utilisateur
#         user = User.objects.filter(email__iexact=email).first()
#         if not user:
#             return Response({"error": "Aucun utilisateur trouvé."}, status=status.HTTP_404_NOT_FOUND)

#         try:
#             # 🔐 Assigner rôle vendeur si besoin
#             if user.user_role != role_vendor:
#                 user.user_role = role_vendor
#                 user.save(update_fields=["user_role"])

#             # 🔁 Vérifie s’il est déjà vendeur
#             if Vendor.objects.filter(user=user).exists():
#                 return Response({"error": "Ce user est déjà enregistré comme vendeur."}, status=status.HTTP_400_BAD_REQUEST)

#             # ✅ Création du vendeur
#             vendor = Vendor.objects.create(user=user, bijouterie=bijouterie, description=description)

#             return Response({
#                 'vendor': VendorSerializer(vendor).data,
#                 'user': UserSerializer(user).data,
#                 'message': "✅ Vendeur créé avec succès"
#             }, status=status.HTTP_201_CREATED)

#         except Exception as e:
#             return Response({'error': f'Une erreur est survenue : {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)


# class CreateVendorView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]
#     allowed_roles_admin_manager = ['admin', 'manager']

#     @swagger_auto_schema(
#         operation_summary="Créer un vendeur à partir d’un utilisateur existant",
#         operation_description=(
#             "Associe un utilisateur existant à un profil Vendor (et une bijouterie). "
#             "N’altère pas le rôle existant (admin/manager) du user."
#         ),
#         request_body=CreateVendorSerializer,
#         responses={
#             201: openapi.Response(description="Vendeur créé", schema=VendorSerializer),
#             400: openapi.Response(description="Erreur ou données invalides"),
#             403: openapi.Response(description="⛔ Accès refusé")
#         }
#     )
#     @transaction.atomic
#     def post(self, request, *args, **kwargs):
#         # Vérification du rôle appelant
#         caller_role = getattr(getattr(request.user, "user_role", None), "role", None)
#         if caller_role not in self.allowed_roles_admin_manager:
#             return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

#         # Validation
#         serializer = CreateVendorSerializer(data=request.data)
#         if not serializer.is_valid():
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#         email = serializer.validated_data["email"]
#         bijouterie = serializer.validated_data["bijouterie"]  # suppose que le serializer retourne une instance
#         # description = serializer.validated_data.get("description", "")  # ⚠️ uniquement si le modèle Vendor a ce champ

#         # Récupération de l'utilisateur
#         user = User.objects.select_for_update().filter(email__iexact=email).first()
#         if not user:
#             return Response({"error": "Aucun utilisateur trouvé avec cet email."}, status=status.HTTP_404_NOT_FOUND)

#         # Empêcher les doublons Vendor
#         if Vendor.objects.filter(user=user).exists():
#             return Response({"error": "Ce user est déjà enregistré comme vendeur."}, status=status.HTTP_400_BAD_REQUEST)

#         # Option : si le user n’a aucun rôle, on peut lui assigner 'vendor' (sinon on ne touche pas)
#         if not getattr(user, "user_role", None):
#             role_vendor = Role.objects.filter(role="vendor").first()
#             if not role_vendor:
#                 # On peut créer le rôle si tu veux, ou bien refuser proprement
#                 # role_vendor = Role.objects.create(role="vendor")
#                 return Response({"error": "Le rôle 'vendor' n'existe pas. Créez-le d’abord."}, status=status.HTTP_400_BAD_REQUEST)
#             user.user_role = role_vendor
#             user.save(update_fields=["user_role"])

#         # Création du Vendor (⚠️ pas de description si le champ n’existe pas dans le modèle)
#         vendor = Vendor.objects.create(
#             user=user,
#             bijouterie=bijouterie,
#             # description=description,  # décommente seulement si le champ existe dans Vendor
#         )

#         return Response(
#             {
#                 "vendor": VendorSerializer(vendor).data,
#                 "user": UserSerializer(user).data,
#                 "message": "✅ Vendeur créé avec succès"
#             },
#             status=status.HTTP_201_CREATED
#         )



# class CreateStaffMemberView(APIView):
#     """
#     POST /staff/create/?upsert=true|false
#     - Crée un Vendor OU un Cashier pour un utilisateur existant.
#     - Accès: admin/manager uniquement
#     - upsert=true: si le staff existe déjà, renvoie 200 avec l'objet existant (idempotent)
#     """
#     permission_classes = [IsAuthenticated]
#     allowed_roles_admin_manager = (ROLE_ADMIN, ROLE_MANAGER)
#     MAP = {ROLE_VENDOR: (Vendor, VendorSerializer), ROLE_CASHIER: (Cashier, CashierSerializer)}

#     upsert_param = openapi.Parameter(
#         name="upsert", in_=openapi.IN_QUERY, type=openapi.TYPE_BOOLEAN, required=False,
#         description="Si true, renvoie le staff existant (200) au lieu d'un 409."
#     )

#     @swagger_auto_schema(
#         operation_summary="Créer un vendor ou un cashier (idempotent avec ?upsert=true)",
#         request_body=CreateStaffMemberSerializer,
#         manual_parameters=[upsert_param],
#         responses={
#             201: "Créé",
#             200: "Existant (upsert)",
#             400: "Requête invalide",
#             403: "⛔ Accès refusé",
#             404: "Introuvable",
#             409: "Conflit"
#         }
#     )
#     @transaction.atomic
#     def post(self, request):
#         # 1) Permissions appelant
#         caller_role = getattr(getattr(request.user, "user_role", None), "role", None)
#         if caller_role not in self.allowed_roles_admin_manager:
#             return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

#         # 2) Paramètre upsert (idempotence)
#         TRUTHY = {"1", "true", "yes"}
#         upsert = str(request.query_params.get("upsert", "false")).lower() in TRUTHY

#         # 3) Validation payload
#         inp = CreateStaffMemberSerializer(data=request.data)
#         inp.is_valid(raise_exception=True)
#         data = inp.validated_data

#         wanted_role = data["role"].lower()
#         if wanted_role not in self.MAP:
#             return Response({"error": "role doit être 'vendor' ou 'cashier'."}, status=400)
#         Model, OutSer = self.MAP[wanted_role]

#         email = (data.get("email") or "").strip()
#         username = (data.get("username") or "").strip()
#         phone = (data.get("phone") or "").strip()

#         # 4) Bijouterie (ID prioritaire, sinon nom)
#         bijouterie = None
#         if data.get("bijouterie"):
#             bijouterie = Bijouterie.objects.select_for_update().filter(pk=data["bijouterie"]).first()
#             if not bijouterie:
#                 return Response({"error": "Bijouterie introuvable (ID)."}, status=404)
#         else:
#             bijouterie = Bijouterie.objects.select_for_update().filter(nom__iexact=data["bijouterie_nom"]).first()
#             if not bijouterie:
#                 return Response({"error": f"Bijouterie '{data['bijouterie_nom']}' introuvable."}, status=404)

#         # 5) User sous verrou
#         user = User.objects.select_for_update().filter(
#             (Q(email__iexact=email) if email else Q()) |
#             (Q(username__iexact=username) if username else Q()) |
#             (Q(phone__iexact=phone) if phone else Q())
#         ).first()
#         if not user:
#             return Response({"error": "Utilisateur introuvable avec les identifiants fournis."}, status=404)

#         # 6) Rôles en base
#         role_vendor = Role.objects.filter(role=ROLE_VENDOR).first()
#         role_cashier = Role.objects.filter(role=ROLE_CASHIER).first()
#         if not role_vendor or not role_cashier:
#             return Response({"error": "Rôles 'vendor' et/ou 'cashier' manquants en base."}, status=400)

#         existing_role = getattr(getattr(user, "user_role", None), "role", None)

#         # 6a) Ne pas toucher aux admins/managers
#         if existing_role in self.allowed_roles_admin_manager:
#             return Response({"error": f"User déjà '{existing_role}', opération interdite."}, status=409)

#         # 6b) Si user a un rôle différent du demandé
#         if existing_role and existing_role != wanted_role:
#             return Response({"error": f"User a déjà le rôle '{existing_role}'."}, status=409)

#         # 7) Idempotence: staff de même type ?
#         existing_same = Model.objects.select_for_update().filter(user_id=user.id).first()
#         if existing_same:
#             if upsert:
#                 return Response(
#                     {
#                         "staff_type": wanted_role,
#                         "staff": OutSer(existing_same).data,
#                         "user": UserSerializer(user).data,
#                         "message": "ℹ️ Déjà existant (upsert)"
#                     },
#                     status=200
#                 )
#             return Response({"error": f"User déjà {wanted_role}."}, status=409)

#         # 7b) Staff de l'autre type existe ?
#         other_model = Cashier if wanted_role == ROLE_VENDOR else Vendor
#         if other_model.objects.select_for_update().filter(user_id=user.id).exists():
#             return Response({"error": f"User déjà {'cashier' if wanted_role == ROLE_VENDOR else 'vendor'}."}, status=409)

#         # 8) Assigner le rôle si aucun
#         if not existing_role:
#             user.user_role = role_vendor if wanted_role == ROLE_VENDOR else role_cashier
#             user.save(update_fields=["user_role"])

#         # 9) Créer le staff
#         try:
#             staff = Model.objects.create(user=user, bijouterie=bijouterie)
#         except IntegrityError:
#             # création concurrente → renvoyer l’existant si upsert
#             staff = Model.objects.filter(user_id=user.id).first()
#             if staff and upsert:
#                 return Response(
#                     {
#                         "staff_type": wanted_role,
#                         "staff": OutSer(staff).data,
#                         "user": UserSerializer(user).data,
#                         "message": "ℹ️ Déjà existant (création concurrente, upsert)"
#                     },
#                     status=200
#                 )
#             return Response({"error": "Conflit de création (concurrence)."}, status=409)

#         return Response(
#             {
#                 "staff_type": wanted_role,
#                 "staff": OutSer(staff).data,
#                 "user": UserSerializer(user).data,
#                 "message": "✅ Créé avec succès"
#             },
#             status=201
#         )

ROLE_ADMIN, ROLE_MANAGER = "admin", "manager"
ROLE_VENDOR, ROLE_CASHIER = "vendor", "cashier"
# class CreateStaffMemberView(APIView):
#     permission_classes = [IsAuthenticated]
#     allowed_roles_admin_manager = ("admin", "manager")
#     MAP = {
#         "vendor": (Vendor, VendorSerializer),
#         "cashier": (Cashier, CashierSerializer),
#     }

#     @swagger_auto_schema(
#         operation_summary="Créer un staff (vendor ou cashier) à partir d’un utilisateur existant",
#         request_body=CreateStaffMemberSerializer,
#         responses={201: "Créé", 400: "Erreur", 403: "Accès refusé", 404: "Introuvable", 409: "Conflit"}
#     )
#     @transaction.atomic
#     def post(self, request):
#         # Vérification rôle appelant
#         caller_role = getattr(getattr(request.user, "user_role", None), "role", None)
#         if caller_role not in self.allowed_roles_admin_manager:
#             return Response({"error": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

#         # Validation payload
#         serializer = CreateStaffMemberSerializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         data = serializer.validated_data

#         email, bijouterie, wanted_role = data["email"], data["bijouterie"], data["role"]
#         Model, OutSer = self.MAP[wanted_role]

#         # Vérifier l’utilisateur par email
#         user = User.objects.select_for_update().filter(email__iexact=email).first()
#         if not user:
#             return Response({"error": f"Aucun utilisateur trouvé avec l’email {email}."}, status=404)

#         # Vérifier rôles
#         role_vendor = Role.objects.filter(role="vendor").first()
#         role_cashier = Role.objects.filter(role="cashier").first()
#         if not role_vendor or not role_cashier:
#             return Response({"error": "Les rôles vendor/cashier n’existent pas en base."}, status=400)

#         existing_role = getattr(getattr(user, "user_role", None), "role", None)
#         if existing_role in self.allowed_roles_admin_manager:
#             return Response({"error": f"User déjà {existing_role}, impossible de le transformer."}, status=409)
#         if existing_role and existing_role != wanted_role:
#             return Response({"error": f"User déjà {existing_role}."}, status=409)

#         # Vérifier staff déjà existant
#         if Model.objects.filter(user=user).exists():
#             return Response({"error": f"Ce user est déjà {wanted_role}."}, status=409)

#         # Si aucun rôle, assigner
#         if not existing_role:
#             user.user_role = role_vendor if wanted_role == "vendor" else role_cashier
#             user.save(update_fields=["user_role"])

#         # Création
#         try:
#             staff = Model.objects.create(
#                 user=user,
#                 bijouterie=bijouterie,
#                 description=data.get("description", "")
#             )
#         except IntegrityError:
#             return Response({"error": "Conflit de création (intégrité)."}, status=409)

#         return Response(
#             {
#                 "staff_type": wanted_role,
#                 "staff": OutSer(staff).data,
#                 "user": UserSerializer(user).data,
#                 "message": "✅ Staff créé avec succès"
#             },
#             status=201
#         )


class CreateStaffMemberView(APIView):
    permission_classes = [IsAuthenticated]
    allowed_roles_admin_manager = (ROLE_ADMIN, ROLE_MANAGER)
    MAP = {
        ROLE_VENDOR: (Vendor, VendorSerializer),
        ROLE_CASHIER: (Cashier, CashierSerializer),
    }

    @swagger_auto_schema(
        operation_summary="Créer un staff (vendor ou cashier) à partir d’un utilisateur existant",
        request_body=CreateStaffMemberSerializer,
        responses={201: "Créé", 400: "Erreur", 403: "Accès refusé", 404: "Introuvable", 409: "Conflit"}
    )
    @transaction.atomic
    def post(self, request):
        # 0) Permissions
        caller_role = getattr(getattr(request.user, "user_role", None), "role", None)
        if caller_role not in self.allowed_roles_admin_manager:
            return Response({"error": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

        # 1) Validation
        serializer = CreateStaffMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        email = data["email"].strip()
        bijouterie = data["bijouterie"]                # instance validée par le serializer
        wanted_role = data["role"].lower()

        if wanted_role not in self.MAP:
            return Response({"error": "role doit être 'vendor' ou 'cashier'."}, status=400)
        Model, OutSer = self.MAP[wanted_role]

        # 2) User sous verrou
        user = User.objects.select_for_update().filter(email__iexact=email).first()
        if not user:
            return Response({"error": f"Aucun utilisateur trouvé avec l’email {email}."}, status=404)

        # 3) Rôles présents en base
        role_vendor = Role.objects.filter(role=ROLE_VENDOR).first()
        role_cashier = Role.objects.filter(role=ROLE_CASHIER).first()
        if not role_vendor or not role_cashier:
            return Response({"error": "Les rôles vendor/cashier n’existent pas en base."}, status=400)

        existing_role = getattr(getattr(user, "user_role", None), "role", None)

        # 4) Protections rôle
        if existing_role in self.allowed_roles_admin_manager:
            return Response({"error": f"User déjà {existing_role}, impossible de le transformer."}, status=409)
        if existing_role and existing_role != wanted_role:
            return Response({"error": f"User déjà {existing_role}."}, status=409)

        # 5) Déjà staff ?
        # même type
        if Model.objects.select_for_update().filter(user_id=user.id).exists():
            return Response({"error": f"Ce user est déjà {wanted_role}."}, status=409)
        # autre type
        other_model = Cashier if wanted_role == ROLE_VENDOR else Vendor
        if other_model.objects.select_for_update().filter(user_id=user.id).exists():
            other_name = ROLE_CASHIER if wanted_role == ROLE_VENDOR else ROLE_VENDOR
            return Response({"error": f"Ce user est déjà {other_name}."}, status=409)

        # 6) Assigner le rôle si aucun
        if not existing_role:
            user.user_role = role_vendor if wanted_role == ROLE_VENDOR else role_cashier
            user.save(update_fields=["user_role"])

        # 7) Création (race-safe)
        try:
            staff = Model.objects.create(
                user=user,
                bijouterie=bijouterie,
                # description=data.get("description", "")
            )
        except IntegrityError:
            # création concurrente → conflit explicite
            return Response({"error": "Conflit de création (intégrité)."}, status=409)

        return Response(
            {
                "staff_type": wanted_role,
                "staff": OutSer(staff).data,
                "user": UserSerializer(user).data,
                "message": "✅ Staff créé avec succès"
            },
            status=201
        )


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



class RetrieveVendorView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Récupérer un vendeur en filtrant par email, username ou téléphone de l'utilisateur.",
        manual_parameters=[
            openapi.Parameter('search', openapi.IN_QUERY, description="Email, username ou téléphone", type=openapi.TYPE_STRING),
        ],
        responses={
            200: openapi.Response(description="Vendeur trouvé", schema=VendorSerializer),
            404: "Aucun vendeur correspondant",
        }
    )
    def get(self, request, *args, **kwargs):
        # allowed_roles = ['admin', 'manager']
        # user_role = getattr(request.user.user_role, 'role', None)

        # if user_role not in allowed_roles:
        #     return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        if not request.user.user_role or request.user.user_role.role not in self.allowed_roles_admin_manager:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        
        search = request.GET.get('search')
        if not search:
            return Response({"error": "Veuillez fournir un paramètre de recherche (email, username ou phone)."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.filter(
                Q(email__iexact=search) |
                Q(username__iexact=search) |
                Q(phone__iexact=search)
            ).first()

            if not user:
                return Response({"error": "Aucun utilisateur correspondant."}, status=status.HTTP_404_NOT_FOUND)

            vendor = Vendor.objects.filter(user=user).first()
            if not vendor:
                return Response({"error": "Aucun vendeur associé à cet utilisateur."}, status=status.HTTP_404_NOT_FOUND)

            return Response({
                "vendor": VendorSerializer(vendor).data,
                "user": UserSerializer(user).data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": f"Une erreur est survenue : {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)



class UpdateVendorStatusAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Admin - Mise à jour des statuts du vendeur (active et/ou désactivé).",
        request_body=VendorSerializer,
        responses={200: "Statut mis à jour"}
    )
    def patch(self, request, user_id, *args, **kwargs):
        # allowed_roles = ['admin', 'manager']
        # user_role = getattr(request.user.user_role, 'role', None)

        # if user_role not in allowed_roles:
        #     return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        if not request.user.user_role or request.user.user_role.role not in self.allowed_roles_admin_manager:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        
        # Get the Vendor instance associated with the given user_id
        vendor = get_object_or_404(Vendor, user__id=user_id)

        # Ensure the request payload contains the 'active' field
        if 'active' not in request.data:
            return Response({'detail': 'Active status is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Update the active status
        vendor.active = request.data['active']
        vendor.save()

        # Return the updated vendor details
        serializer = VendorUpdateStatusSerializer(vendor)
        return Response(serializer.data, status=status.HTTP_200_OK)


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


class VendorProduitAssociationAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    allowed_roles_admin_manager = {"admin", "manager"}

    @swagger_auto_schema(
        operation_description="Associer des produits à un vendeur et ajuster les stocks.",
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
                        }
                    )
                )
            }
        ),
        responses={201: "Produits associés", 400: "Requête invalide", 403: "Accès refusé", 404: "Ressource introuvable"}
    )
    @transaction.atomic
    def post(self, request):
        # 1) Permissions
        role = getattr(getattr(request.user, "user_role", None), "role", None)
        if role not in self.allowed_roles_admin_manager:
            return Response({"message": "⛔ Accès refusé"}, status=403)

        # 2) Entrées
        email = request.data.get("email")
        produits_data = request.data.get("produits", [])

        if not email:
            return Response({"error": "L'email du vendeur est requis."}, status=400)
        if not isinstance(produits_data, list) or not produits_data:
            return Response({"error": "La liste des produits est vide ou invalide."}, status=400)

        # 3) Vendeur
        try:
            vendor = Vendor.objects.select_related("user").get(user__email=email)
        except Vendor.DoesNotExist:
            return Response({"error": "Vendeur introuvable."}, status=404)

        # ⚠️ Correction ici : 'verifie' (pas 'active')
        if not vendor.verifie:
            return Response({"error": "Ce vendeur est désactivé."}, status=403)

        # 4) Normaliser/agréger les lignes (doublons produit_id -> somme des quantités)
        demandes = defaultdict(int)
        for item in produits_data:
            try:
                pid = int(item.get("produit_id"))
                qty = int(item.get("quantite"))
            except Exception:
                return Response({"error": "Chaque item doit contenir un produit_id et une quantite (entiers)."}, status=400)
            if pid <= 0 or qty <= 0:
                return Response({"error": "produit_id et quantite doivent être > 0."}, status=400)
            demandes[pid] += qty

        # 5) Vérifier l’existence des produits demandés
        produits = Produit.objects.filter(id__in=demandes.keys())
        if produits.count() != len(demandes):
            ids_trouves = set(produits.values_list("id", flat=True))
            manquants = [pid for pid in demandes.keys() if pid not in ids_trouves]
            return Response({"error": f"Produit(s) introuvable(s): {manquants}"}, status=404)

        produits_by_id = {p.id: p for p in produits}

        # 6) Préparer la réponse
        produits_associes = []

        # 7) Traiter chaque produit avec verrouillage ligne par ligne
        for pid, qty in demandes.items():
            produit = produits_by_id[pid]

            # 7.a Stock global verrouillé (évite les races)
            stock = (
                Stock.objects.select_for_update()
                .filter(produit_id=pid)
                .first()
            )
            if not stock:
                return Response({"error": f"Aucun stock pour le produit {produit.nom}."}, status=400)

            if stock.quantite < qty:
                return Response(
                    {"error": f"Stock insuffisant pour {produit.nom}. Stock actuel : {stock.quantite}, demandé : {qty}"},
                    status=400,
                )

            # 7.b Décrémente atomiquement si assez de stock
            updated = (
                Stock.objects
                .filter(pk=stock.pk, quantite__gte=qty)
                .update(quantite=F("quantite") - qty)
            )
            if not updated:
                # Quelqu'un a peut-être pris le stock entre-temps
                return Response(
                    {"error": f"Conflit de stock détecté pour {produit.nom}. Réessayez."},
                    status=409,
                )
            stock.refresh_from_db()

            # 7.c Associer au vendeur (verrouiller/mettre à jour la ligne VendorProduit)
            vp = (
                VendorProduit.objects.select_for_update()
                .filter(vendor=vendor, produit_id=pid)
                .first()
            )
            if vp:
                vp.quantite = F("quantite") + qty
                vp.save(update_fields=["quantite"])
                vp.refresh_from_db()
                status_item = "mis à jour"
            else:
                vp = VendorProduit.objects.create(vendor=vendor, produit_id=pid, quantite=qty)
                status_item = "créé"

            produits_associes.append({
                "produit_id": produit.id,
                "nom": produit.nom,
                "quantite_attribuee": qty,
                "stock_vendeur": vp.quantite,
                "stock_restant_global": stock.quantite,
                "status": status_item,
            })

        # 8) OK
        return Response({
            "message": "✅ Produits associés avec succès.",
            "vendeur": {
                "id": vendor.id,
                "nom_complet": vendor.user.get_full_name() if vendor.user else "",
                "email": vendor.user.email if vendor.user else "",
            },
            "produits": produits_associes
        }, status=201)

def _parse_iso_dt(s: str):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # support YYYY-MM-DD
        try:
            dt = datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


# -------- LISTE / LECTURE --------
class CashierListView(generics.ListAPIView):
    """
    GET /api/cashiers/?q=&bijouterie_id=&verifie=true|false&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CashierReadSerializer

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter("q", openapi.IN_QUERY, description="Recherche (email, username, nom, prénom, téléphone)", type=openapi.TYPE_STRING),
            openapi.Parameter("bijouterie_id", openapi.IN_QUERY, description="Filtrer par bijouterie id", type=openapi.TYPE_INTEGER),
            openapi.Parameter("verifie", openapi.IN_QUERY, description="true/false", type=openapi.TYPE_STRING),
            openapi.Parameter("start_date", openapi.IN_QUERY, description="Filtrer total_encaisse à partir de (YYYY-MM-DD)", type=openapi.TYPE_STRING),
            openapi.Parameter("end_date", openapi.IN_QUERY, description="Filtrer total_encaisse jusqu’à (YYYY-MM-DD)", type=openapi.TYPE_STRING),
        ],
        responses={200: CashierReadSerializer(many=True)}
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        qs = Cashier.objects.select_related("user", "bijouterie").all()

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
            v = verifie.lower()
            if v in ("true", "1", "yes", "oui"):
                qs = qs.filter(verifie=True)
            elif v in ("false", "0", "no", "non"):
                qs = qs.filter(verifie=False)

        # Annotation du total encaissé (optionnelle)
        start = _parse_iso_dt(self.request.query_params.get("start_date"))
        end = _parse_iso_dt(self.request.query_params.get("end_date"))
        filt = Q()
        if start:
            filt &= Q(encaissements__created_at__gte=start)
        if end:
            filt &= Q(encaissements__created_at__lte=end)
        qs = qs.annotate(total_encaisse=Sum("encaissements__montant", filter=filt))

        return qs.order_by("-id")


# -------- DÉTAIL / LECTURE + MÀJ --------
class CashierDetailView(APIView):
    """
    GET  /api/cashiers/<int:id>/
    GET  /api/cashiers/by-slug/<slug:slug>/
    PATCH/PUT idem (CashierUpdateSerializer)
    """
    permission_classes = [permissions.IsAuthenticated]

    def _get_obj(self, **kwargs):
        cashier_id = kwargs.get("id") or kwargs.get("pk")
        slug = kwargs.get("slug") or self.request.query_params.get("slug")
        base_qs = Cashier.objects.select_related("user", "bijouterie")

        # facultatif : annotate total via query params
        start = _parse_iso_dt(self.request.query_params.get("start_date"))
        end = _parse_iso_dt(self.request.query_params.get("end_date"))
        filt = Q()
        if start:
            filt &= Q(encaissements__created_at__gte=start)
        if end:
            filt &= Q(encaissements__created_at__lte=end)
        base_qs = base_qs.annotate(total_encaisse=Sum("encaissements__montant", filter=filt))

        if cashier_id:
            return generics.get_object_or_404(base_qs, pk=cashier_id)
        if slug:
            return generics.get_object_or_404(base_qs, user__slug=slug)
        return generics.get_object_or_404(base_qs, pk=self.request.query_params.get("id"))

    def _can_update(self, request, cashier: Cashier) -> bool:
        role = getattr(getattr(request.user, "user_role", None), "role", None)
        is_admin_or_manager = role in {"admin", "manager"}
        is_owner = cashier.user_id == request.user.id
        return bool(is_admin_or_manager or is_owner)

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter("slug", openapi.IN_QUERY, description="(optionnel) user.slug si pas d'id dans l'URL", type=openapi.TYPE_STRING),
            openapi.Parameter("start_date", openapi.IN_QUERY, description="Filtrer total_encaisse à partir de (YYYY-MM-DD)", type=openapi.TYPE_STRING),
            openapi.Parameter("end_date", openapi.IN_QUERY, description="Filtrer total_encaisse jusqu’à (YYYY-MM-DD)", type=openapi.TYPE_STRING),
        ],
        responses={200: CashierReadSerializer}
    )
    def get(self, request, *args, **kwargs):
        cashier = self._get_obj(**kwargs)
        return Response(CashierReadSerializer(cashier).data)

    @swagger_auto_schema(request_body=CashierUpdateSerializer, responses={200: CashierReadSerializer, 403: "Access Denied"})
    def patch(self, request, *args, **kwargs):
        cashier = self._get_obj(**kwargs)
        if not self._can_update(request, cashier):
            return Response({"detail": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        s = CashierUpdateSerializer(cashier, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(CashierReadSerializer(cashier).data)

    @swagger_auto_schema(request_body=CashierUpdateSerializer, responses={200: CashierReadSerializer, 403: "Access Denied"})
    def put(self, request, *args, **kwargs):
        cashier = self._get_obj(**kwargs)
        if not self._can_update(request, cashier):
            return Response({"detail": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        s = CashierUpdateSerializer(cashier, data=request.data, partial=False)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(CashierReadSerializer(cashier).data)



# class VendorProduitAssociationAPIView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]
#     allowed_roles_admin_manager = ['admin', 'manager']  # 🔧 ligne à ajouter

#     @swagger_auto_schema(
#         operation_description="""Associer des produits à un vendeur vérifié.
        
#         - 🎯 Associe un vendeur via son `user_id`.
#         - 🧾 Utilise `produit_id` pour POST (write-only).
#         - 📦 `produit` est retourné dans les réponses avec les détails complets.
#         - ✅ Seuls les rôles `admin` et `manager` sont autorisés.
#         - ⚠️ Vérifie automatiquement le stock disponible.
#         """,
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["user_id", "produits"],
#             properties={
#                 "email": openapi.Schema(type=openapi.TYPE_STRING, description="Email du vendeur"),
#                 "produits": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["produit_id", "quantite"],
#                         properties={
#                             "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                             "quantite": openapi.Schema(type=openapi.TYPE_INTEGER)
#                         }
#                     )
#                 )
#             }
#         ),
#         responses={201: "✅ Produits associés", 400: "❌ Requête invalide", 403: "⛔ Accès refusé", 404: "❌ Vendeur/Produit introuvable"}
#     )
#     @transaction.atomic
#     def post(self, request):
        
#         if not request.user.user_role or request.user.user_role.role not in self.allowed_roles_admin_manager:
#             return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

#         email = request.data.get('email')
#         produits_data = request.data.get('produits', [])

#         if not email:
#             return Response({"error": "email requis"}, status=400)

#         try:
#             vendor = Vendor.objects.get(user__email=email)
#         except Vendor.DoesNotExist:
#             return Response({"error": "Vendeur introuvable."}, status=404)

#         if not vendor.user or vendor.user.user_role.role != 'vendor':
#             return Response({"error": "Utilisateur non autorisé ou rôle incorrect."}, status=403)

#         if not vendor.active:
#             return Response({"error": "Ce vendeur est désactivé."}, status=403)

#         if not produits_data:
#             return Response({"error": "La liste des produits est vide."}, status=400)

#         produits_associes = []

#         for produit_info in produits_data:
#             produit_id = produit_info.get('produit_id')
#             quantite = produit_info.get('quantite')

#             if not produit_id or quantite is None:
#                 return Response({"error": "produit_id et quantite sont requis."}, status=400)

#             try:
#                 produit = Produit.objects.get(id=produit_id)
#             except Produit.DoesNotExist:
#                 return Response({"error": f"Produit ID {produit_id} introuvable."}, status=404)

#             try:
#                 quantite = int(quantite)
#                 if quantite <= 0:
#                     return Response({"error": "Quantité doit être > 0."}, status=400)
#             except Exception:
#                 return Response({"error": "Quantité invalide."}, status=400)

#             stock = Stock.objects.filter(produit=produit).first()
#             if not stock or stock.quantite < quantite:
#                 return Response(
#                     {"error": f"Stock insuffisant pour {produit.sku} qui a pour ID {produit.id}. Stock actuel : {stock.quantite if stock else 0}"},
#                     status=400
#                 )

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
#                 "quantite": quantite,
#                 "status": "créé" if created else "mis à jour"
#             })

#         return Response({
#             "message": "✅ Produits associés avec succès.",
#             "vendeur": {
#                 "id": vendor.id,
#                 "nom": vendor.user.get_full_name(),
#                 "email": vendor.user.email
#             },
#             "produits": produits_associes
#         }, status=201)



# class VendorProduitAssociationAPIView(APIView):
#     @swagger_auto_schema(
#         operation_description="Register a new user",
#         request_body=VendorSerializer,
#         responses={
#             status.HTTP_201_CREATED: openapi.Response('Association des produits à un vendeur', VendorSerializer),
#             status.HTTP_400_BAD_REQUEST: openapi.Response('Bad Request')
#         }
#     )
#     @transaction.atomic  # Garantir que la transaction soit atomique
#     def post(self, request):
#         user_id = request.data.get('user_id')
#         # verifiie = request.data.get('verifier')
#         # Récupérer le vendor
        
#         try:
#             vendor = Vendor.objects.get(user_id=user_id)
#             # print(role)
#             # print(vendor)
#             # print(vendor.verifie)
#             # print(vendor.user.user_role)
#             # if vendor.user.user_role is None or vendor.user.user_role.role is None:
#             if vendor.user.user_role is None:
#                 return Response({"detail": "Role is not assigned to the user."}, status=status.HTTP_400_BAD_REQUEST)
#             # Check if vendor is not verified or user role is not 'vendor'
#             # if vendor.verifie != True and vendor.user.user_role.role != 'vendor':
#             if not vendor.verifie or vendor.user.user_role.role != 'vendor':
#                 return Response({"detail": "Access denied. The vendor is either not verified or does not have the correct role."}, status=status.HTTP_403_FORBIDDEN)
            
            
#             # Récupérer les données envoyées
#             # Récupérer les produits et les quantités dans la requête
#             produits_data = request.data.get('produits', [])
            
#             # Boucle sur chaque produit et associer avec le vendeur
#             for produit_data in produits_data:
#                 produit_id = produit_data.get('produit_id')
#                 quantite = produit_data.get('quantite')
                
#                 # Vérifier si le tableau de produits est fourni
#                 if not produit_id or quantite is None:
#                     return Response({"error": "produit_id et quantite sont requis."}, status=status.HTTP_400_BAD_REQUEST)

#                 # Vérifier si le produit existe
#                 try:
#                     produit = Produit.objects.get(id=produit_id)
#                 except Produit.DoesNotExist:
#                     return Response({"error": f"Produit avec l'ID {produit_id} non trouvé."}, status=status.HTTP_404_NOT_FOUND)

#                 # Vérification de la quantité
#                 try:
#                     quantite = int(quantite)
#                     if quantite <= 0:
#                         return Response({"error": "La quantité doit être un entier positif."}, status=status.HTTP_400_BAD_REQUEST)
#                 except (ValueError, TypeError):
#                     return Response({"error": "Quantité invalide."}, status=status.HTTP_400_BAD_REQUEST)

#                 try:
#                     produit = Produit.objects.get(id=produit_id)
#                 except Produit.DoesNotExist:
#                     return Response({"error": f"Produit avec l'ID {produit_id} non trouvé."}, status=status.HTTP_404_NOT_FOUND)

#                 stock = Stock.objects.filter(produit=produit).first()
#                 if not stock or stock.quantite is None or stock.quantite < quantite:
#                     return Response(
#                         {'erreur': f'Stock insuffisant pour le produit {produit.sku}. Stock actuel: {stock.quantite_totale if stock else 0}'},
#                         status=status.HTTP_400_BAD_REQUEST
#                     )

#                 # Création ou mise à jour
#                 vendor_produit, created = VendorProduit.objects.update_or_create(
#                     produit=produit,
#                     vendor=vendor,
#                     quantite = quantite
#                 )
#                 print(f"VendorProduit {'created' if created else 'updated'}: {vendor_produit}")

#                 stock.quantite -= quantite
#                 stock.save()

#             # return Response({
#             #     "message": f"Produits associés avec succès au vendeur {vendor.user.first_name} {vendor.user.last_name}."
#             # }, status=status.HTTP_201_CREATED)
            
#             return Response(produit_serializer.data, status=status.HTTP_201_CREATED)

#         except Vendor.DoesNotExist:
#             return Response({"error": "Vendor not found."}, status=status.HTTP_404_NOT_FOUND)

