# from knox.auth import TokenAuthentication
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from io import BytesIO

#Export to excel
import qrcode
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django_filters.rest_framework import DjangoFilterBackend
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from PIL import Image
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.parsers import (FileUploadParser, FormParser, JSONParser,
                                    MultiPartParser)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.permissions import IsAdminOrManager, IsAdminOrManagerOrVendor
from backend.renderers import UserRenderer
from backend.roles import ROLE_MANAGER, ROLE_VENDOR, get_role_name
from store.models import (Bijouterie, Categorie, Gallery, Marque, MarquePurete,
                          MarquePuretePrixHistory, Modele, Produit, Purete)
from store.serializers import (BijouterieSerializer, CategorieSerializer,
                               MarqueListSerializer,
                               MarquePuretePrixEvolutionPointSerializer,
                               MarquePuretePrixHistory,
                               MarquePuretePrixHistorySerializer,
                               MarquePureteSerializer, MarqueSerializer,
                               ModeleSerializer, ProduitSerializer,
                               ProduitWithGallerySerializer, PureteSerializer)
from store.services.price_history_service import update_marque_purete_price

from .serializers import MarquePuretePrixHistorySerializer

allowed_roles_admin_manager_vendeur = ['admin', 'manager', 'vendeur']
allowed_roles_admin_manager = ['admin', 'manager']

# Create your views here.
class BijouterieListAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Lister les bijouteries",
        operation_description="Retourne la liste de toutes les bijouteries enregistrées. Accès réservé aux rôles : admin, manager.",
        responses={
            200: openapi.Response(
                description="Liste des bijouteries",
                schema=BijouterieSerializer(many=True)
            ),
            403: "Accès refusé"
        }
    )
    def get(self, request):

        user_role = getattr(request.user.user_role, 'role', None)
        if user_role not in allowed_roles_admin_manager:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        bijouteries = Bijouterie.objects.all()
        serializer = BijouterieSerializer(bijouteries, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class BijouterieCreateAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @swagger_auto_schema(
        operation_summary="Créer une bijouterie",
        operation_description="Permet à un administrateur ou manager d’enregistrer une nouvelle bijouterie, y compris les logos et les contacts.",
        request_body=BijouterieSerializer,
        responses={
            201: openapi.Response("Bijouterie créée avec succès", BijouterieSerializer),
            400: openapi.Response("Requête invalide")
        }
    )
    def post(self, request):
        user_role = getattr(request.user.user_role, 'role', None)

        if user_role not in allowed_roles_admin_manager:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        serializer = BijouterieSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class BijouterieUpdateAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @swagger_auto_schema(
        operation_summary="Mettre à jour une bijouterie",
        operation_description="Permet de modifier les informations d'une bijouterie existante.",
        manual_parameters=[
            openapi.Parameter(
                'pk', openapi.IN_PATH, description="ID de la bijouterie à mettre à jour",
                type=openapi.TYPE_INTEGER, required=True
            )
        ],
        request_body=BijouterieSerializer,
        responses={
            200: openapi.Response("Bijouterie mise à jour", BijouterieSerializer),
            400: "Requête invalide",
            403: "Accès refusé",
            404: "Bijouterie introuvable"
        }
    )
    def put(self, request, pk):
        if not request.user.user_role or request.user.user_role.role not in allowed_roles_admin_manager:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        try:
            bijouterie = Bijouterie.objects.get(pk=pk)
        except Bijouterie.DoesNotExist:
            return Response({"detail": "Bijouterie introuvable."}, status=404)

        serializer = BijouterieSerializer(bijouterie, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    def patch(self, request, pk):
        if not request.user.user_role or request.user.user_role.role not in allowed_roles_admin_manager:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        try:
            bijouterie = Bijouterie.objects.get(pk=pk)
        except Bijouterie.DoesNotExist:
            return Response({"detail": "Bijouterie introuvable."}, status=404)

        serializer = BijouterieSerializer(bijouterie, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)


class BijouterieDeleteAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Supprimer une bijouterie",
        operation_description="Supprime définitivement une bijouterie à partir de son ID.",
        manual_parameters=[
            openapi.Parameter(
                'pk', openapi.IN_PATH, description="ID de la bijouterie à supprimer",
                type=openapi.TYPE_INTEGER, required=True
            )
        ],
        responses={
            204: openapi.Response("Bijouterie supprimée avec succès"),
            403: "Accès refusé",
            404: "Bijouterie introuvable"
        }
    )
    def delete(self, request, pk):
        if not request.user.user_role or request.user.user_role.role not in allowed_roles_admin_manager:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        try:
            bijouterie = Bijouterie.objects.get(pk=pk)
            bijouterie.delete()
            return Response({"message": "Bijouterie supprimée avec succès."}, status=status.HTTP_204_NO_CONTENT)
        except Bijouterie.DoesNotExist:
            return Response({"detail": "Bijouterie introuvable."}, status=status.HTTP_404_NOT_FOUND)


class CategorieListAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @swagger_auto_schema(
        operation_description="Lister les catégories avec filtrage par nom (paramètre `search`).",
        manual_parameters=[
            openapi.Parameter(
                'search', openapi.IN_QUERY,
                description="Filtrer par nom de catégorie",
                type=openapi.TYPE_STRING
            )
        ],
        responses={200: openapi.Response('Liste des catégories', CategorieSerializer(many=True))}
    )
    def get(self, request):
        role = getattr(request.user.user_role, 'role', None)
        if role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        search_query = request.query_params.get('search')
        categories = Categorie.objects.all()

        if search_query:
            categories = categories.filter(nom__icontains=search_query)

        serializer = CategorieSerializer(categories, many=True)
        return Response(serializer.data)


class CategorieCreateAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    parser_classes = (FormParser, MultiPartParser, FileUploadParser)

    @swagger_auto_schema(
        operation_description="Créer une nouvelle catégorie avec un nom et une image.",
        request_body=CategorieSerializer,
        responses={
            status.HTTP_201_CREATED: openapi.Response('Catégorie créée avec succès', CategorieSerializer),
            status.HTTP_400_BAD_REQUEST: openapi.Response('Requête invalide')
        }
    )
    def post(self, request):
        role = getattr(request.user.user_role, 'role', None)
        if role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        serializer = CategorieSerializer(data=request.data)
        if serializer.is_valid():
            try:
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class CategorieUpdateAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    parser_classes = (FormParser, MultiPartParser, FileUploadParser)

    def get_object(self, pk):
        try:
            return Categorie.objects.get(pk=pk)
        except Categorie.DoesNotExist:
            return None

    def has_access(self, user):
        return user.user_role and user.user_role.role in ['admin', 'manager']

    @swagger_auto_schema(
        operation_summary="Modifier une catégorie (PUT)",
        operation_description="Remplace complètement une catégorie existante.",
        request_body=CategorieSerializer,
        responses={
            200: openapi.Response("Catégorie mise à jour avec succès", CategorieSerializer),
            400: "Erreur de validation",
            403: "Accès refusé",
            404: "Catégorie non trouvée"
        }
    )
    def put(self, request, pk):
        if not self.has_access(request.user):
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        categorie = self.get_object(pk)
        if not categorie:
            return Response({"message": "Catégorie non trouvée"}, status=status.HTTP_404_NOT_FOUND)

        serializer = CategorieSerializer(categorie, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_summary="Modifier partiellement une catégorie (PATCH)",
        operation_description="Met à jour partiellement les champs d'une catégorie existante.",
        request_body=CategorieSerializer,
        responses={
            200: openapi.Response("Catégorie mise à jour avec succès", CategorieSerializer),
            400: "Erreur de validation",
            403: "Accès refusé",
            404: "Catégorie non trouvée"
        }
    )
    def patch(self, request, pk):
        if not self.has_access(request.user):
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        categorie = self.get_object(pk)
        if not categorie:
            return Response({"message": "Catégorie non trouvée"}, status=status.HTTP_404_NOT_FOUND)

        serializer = CategorieSerializer(categorie, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class CategorieDeleteAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Supprimer une catégorie",
        operation_description="Supprime une catégorie existante par son ID.",
        manual_parameters=[
            openapi.Parameter(
                'pk',
                openapi.IN_PATH,
                description="ID de la catégorie à supprimer",
                type=openapi.TYPE_INTEGER,
                required=True
            )
        ],
        responses={
            204: openapi.Response(description="Catégorie supprimée avec succès"),
            403: "Accès refusé",
            404: "Catégorie non trouvée"
        }
    )
    def delete(self, request, pk):
        user = request.user
        if not user.user_role or user.user_role.role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        try:
            categorie = Categorie.objects.get(pk=pk)
        except Categorie.DoesNotExist:
            return Response({"message": "Catégorie non trouvée"}, status=status.HTTP_404_NOT_FOUND)

        categorie.delete()
        return Response({"message": "Catégorie supprimée avec succès."}, status=status.HTTP_204_NO_CONTENT)


class PureteListAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Lister les puretés",
        operation_description="Retourne la liste de toutes les puretés, avec option de filtrage par valeur partielle (`?search=`).",
        manual_parameters=[
            openapi.Parameter(
                'search', openapi.IN_QUERY,
                description="Recherche partielle par valeur de pureté (ex: 18 ou 24K)",
                type=openapi.TYPE_STRING
            )
        ],
        responses={200: openapi.Response('Liste des puretés', PureteSerializer(many=True))}
    )
    def get(self, request):
        user = request.user
        if not user.user_role or user.user_role.role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        search = request.query_params.get('search', None)
        queryset = Purete.objects.all()
        if search:
            queryset = queryset.filter(Q(purete__icontains=search))

        serializer = PureteSerializer(queryset, many=True)
        return Response(serializer.data)



class PureteCreateAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Créer une nouvelle pureté",
        operation_description="Permet à un administrateur ou un manager d'ajouter une nouvelle pureté (ex : 18K, 24K).",
        request_body=PureteSerializer,
        responses={
            status.HTTP_201_CREATED: openapi.Response('Pureté créée avec succès', PureteSerializer),
            status.HTTP_400_BAD_REQUEST: openapi.Response('Erreur de validation')
        }
    )
    def post(self, request):
        user = request.user
        if not user.user_role or user.user_role.role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        serializer = PureteSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    


class PureteUpdateAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Modifier une pureté",
        operation_description="Permet à un admin ou un manager de mettre à jour une pureté existante (PUT).",
        request_body=PureteSerializer,
        responses={
            200: openapi.Response("Mise à jour réussie", PureteSerializer),
            400: "Erreur de validation",
            403: "Accès refusé",
            404: "Pureté non trouvée"
        }
    )
    def put(self, request, pk):
        user = request.user
        if not user.user_role or user.user_role.role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        purete = self.get_object(pk)
        if not purete:
            return Response({"message": "Pureté introuvable"}, status=404)

        serializer = PureteSerializer(purete, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    @swagger_auto_schema(
        operation_summary="Modifier partiellement une pureté",
        operation_description="Permet de modifier partiellement une pureté existante (PATCH).",
        request_body=PureteSerializer,
        responses={
            200: openapi.Response("Mise à jour partielle réussie", PureteSerializer),
            400: "Erreur de validation",
            403: "Accès refusé",
            404: "Pureté non trouvée"
        }
    )
    def patch(self, request, pk):
        user = request.user
        if not user.user_role or user.user_role.role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        purete = self.get_object(pk)
        if not purete:
            return Response({"message": "Pureté introuvable"}, status=404)

        serializer = PureteSerializer(purete, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def get_object(self, pk):
        try:
            return Purete.objects.get(pk=pk)
        except Purete.DoesNotExist:
            return None


class PureteDeleteAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Supprimer une pureté",
        operation_description="Supprime une pureté par son ID. Accès réservé aux rôles admin ou manager.",
        manual_parameters=[
            openapi.Parameter(
                name='pk',
                in_=openapi.IN_PATH,
                description="ID de la pureté à supprimer",
                type=openapi.TYPE_INTEGER
            )
        ],
        responses={
            204: "Supprimée avec succès",
            403: "Accès refusé",
            404: "Pureté introuvable"
        }
    )
    def delete(self, request, pk):
        user = request.user
        if not user.user_role or user.user_role.role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        purete = self.get_object(pk)
        if not purete:
            return Response({"detail": "Pureté introuvable"}, status=404)

        purete.delete()
        return Response({"message": "Pureté supprimée avec succès"}, status=204)

    def get_object(self, pk):
        try:
            return Purete.objects.get(pk=pk)
        except Purete.DoesNotExist:
            return None


# class MarqueListAPIView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Lister les marques avec leurs puretés et prix",
#         operation_description="""
#         Retourne les marques avec leurs puretés associées.

#         Format :
#         {
#             "marque": "Dubai",
#             "puretes": [
#                 {"purete_id": 1, "prix": "45000"}
#             ]
#         }
#         """,
#         responses={200: MarqueListSerializer(many=True)},
#         tags=["Marques"],
#     )
#     def get(self, request):
#         queryset = MarquePurete.objects.select_related(
#             "marque",
#             "purete"
#         ).order_by("marque__marque", "purete__id")

#         grouped = defaultdict(list)

#         for item in queryset:
#             grouped[item.marque.marque].append({
#                 "purete_id": item.purete.id,
#                 "prix": str(item.prix)
#             })

#         result = [
#             {
#                 "marque": marque,
#                 "puretes": puretes
#             }
#             for marque, puretes in grouped.items()
#         ]

#         return Response(result, status=200)

# class ListMarquePureteView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Lister toutes les liaisons Marque–Pureté avec prix",
#         responses={200: MarquePureteListSerializer(many=True)}
#     )
#     def get(self, request):
#         queryset = MarquePurete.objects.select_related('marque', 'purete').all()
#         serializer = MarquePureteListSerializer(queryset, many=True)
#         return Response(serializer.data, status=200)


# class MarqueCreateAPIView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]

#     # ✅ Rôles autorisés à créer une marque
#     allowed_roles_admin_manager = ['admin', 'manager']

#     @swagger_auto_schema(
#         operation_summary="Créer une nouvelle marque",
#         operation_description="Permet à un admin ou manager d'ajouter une marque avec son prix et sa pureté.",
#         request_body=MarqueSerializer,
#         responses={
#             201: openapi.Response(description="Marque créée avec succès", schema=MarqueSerializer),
#             400: openapi.Response(description="Erreur de validation"),
#             403: openapi.Response(description="Accès refusé")
#         }
#     )
#     def post(self, request):
#         user = request.user
#         if not user.user_role or user.user_role.role not in self.allowed_roles_admin_manager:
#             return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

#         serializer = MarqueSerializer(data=request.data)
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data, status=status.HTTP_201_CREATED)

#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# class CreateMarquePureteView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="""Créer / mettre à jour le Modèle et la liaison Marque–Pureté (avec prix)
#                             (crée ou met à jour le prix si la liaison existe)
#                             But : rendre l’API pratique et idempotente.
#                             Avantages
#                             Moins d’allers-retours client.
#                             Très utile si les prix changent souvent.
#                             Inconvénients
#                             Moins strict : un POST peut modifier des données existantes.
#                             À privilégier si : tu veux optimiser les flux et mettre à jour fréquemment les prix sans friction.""",
#         request_body=MarquePureteSerializer,
#         responses={201: "Créé/Mis à jour"}
#     )
#     @transaction.atomic
#     def post(self, request):
#         s = MarquePureteSerializer(data=request.data)
#         if not s.is_valid():
#             return Response(s.errors, status=400)

#         # modele_nom = s.validated_data["modele"].strip().title()
#         marque_nom = s.validated_data["marque"].strip().title()
#         puretes_data = s.validated_data["puretes"]

#         # 0) Déduplication & validation prix >= 0
#         latest = {}
#         try:
#             for e in puretes_data:
#                 pid = int(e["purete_id"])
#                 prix = Decimal(e["prix"])
#                 if prix < 0:
#                     return Response({"puretes": [{"purete_id": pid, "prix": "Doit être ≥ 0"}]}, status=400)
#                 latest[pid] = prix  # garde le dernier prix par purete_id
#         except (ValueError, InvalidOperation):
#             return Response({"error": "purete_id/prix invalide."}, status=400)

#         purete_ids = list(latest.keys())

#         # 1) Vérifier que toutes les puretés existent en une fois
#         found = list(Purete.objects.filter(id__in=purete_ids).values_list("id", flat=True))
#         missing = sorted(set(purete_ids) - set(found))
#         if missing:
#             return Response({"error": f"Pureté(s) introuvable(s): {missing}"}, status=404)

#         # 2) Upsert Modele & Marque
#         # modele, _ = Modele.objects.get_or_create(modele=modele_nom)
#         marque, _ = Marque.objects.get_or_create(marque=marque_nom)

#         # 3) Précharger les liaisons existantes pour cette marque
#         existing = {
#             (mp.purete_id): mp
#             for mp in MarquePurete.objects.filter(marque=marque, purete_id__in=purete_ids)
#         }

#         created, updated = [], []
#         for pid, prix in latest.items():
#             mp = existing.get(pid)
#             if mp:
#                 if mp.prix != prix:
#                     mp.prix = prix
#                     mp.save(update_fields=["prix"])
#                 updated.append({"id": pid, "purete": mp.purete.purete, "prix": str(mp.prix)})
#             else:
#                 new = MarquePurete.objects.create(marque=marque, purete_id=pid, prix=prix)
#                 created.append({"id": pid, "purete": new.purete.purete, "prix": str(new.prix)})

#         status_code = 201 if created else 200
#         return Response({
#             "message": "✅ Enregistré.",
#             # "modele": {"id": modele.id, "nom": modele.modele},
#             "marque": {"id": marque.id, "nom": marque.marque},
#             "created": created,
#             "updated": updated
#         }, status=status_code)

class ListMarquePureteView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Lister les marques avec puretés et prix",
        operation_description="""
        Retourne les marques avec leurs puretés et prix associés.

        Exemple :
        [
            {
                "marque_id": 1,
                "marque": "Local",
                "puretes": [
                    {
                        "purete_id": 2,
                        "purete": "18",
                        "prix": "5000.00"
                    }
                ]
            }
        ]
        """,
        responses={200: openapi.Response(description="Liste des marques")},
        tags=["Marques"],
    )
    def get(self, request):
        queryset = MarquePurete.objects.select_related(
            "marque",
            "purete"
        ).order_by("marque__marque", "purete__purete")

        grouped = {}

        for item in queryset:
            marque_id = item.marque.id

            if marque_id not in grouped:
                grouped[marque_id] = {
                    "marque_id": item.marque.id,  # 👈 ajouté
                    "marque": item.marque.marque,
                    "puretes": []
                }

            grouped[marque_id]["puretes"].append({
                "purete_id": item.purete.id,
                "purete": item.purete.purete,
                "prix": str(item.prix),
            })

        return Response(list(grouped.values()), status=200)
    

class CreateMarquePureteView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Créer/mettre à jour Marque–Pureté (et journaliser l'ancien prix)",
        request_body=MarquePureteSerializer,
        responses={201: "Créé/Mis à jour"}
    )
    @transaction.atomic
    def post(self, request):
        s = MarquePureteSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        modele_nom = s.validated_data.get("modele")
        marque_nom = s.validated_data["marque"]
        items = s.validated_data["puretes"]

        if modele_nom:
            Modele.objects.get_or_create(modele=modele_nom.strip().title())

        marque, _ = Marque.objects.get_or_create(marque=marque_nom)

        latest = {
            int(e["purete_id"]): Decimal(e["prix"])
            for e in items
        }

        ids = list(latest.keys())

        found = set(
            Purete.objects.filter(id__in=ids)
            .values_list("id", flat=True)
        )

        missing = sorted(set(ids) - found)

        if missing:
            return Response(
                {"error": f"Pureté(s) introuvable(s): {missing}"},
                status=404
            )

        existing = {
            mp.purete_id: mp
            for mp in MarquePurete.objects
            .select_related("purete")
            .filter(marque=marque, purete_id__in=ids)
        }

        created = []
        updated = []
        unchanged = []
        history = []

        user = request.user if request.user.is_authenticated else None

        for pid, new_price in latest.items():
            mp = existing.get(pid)

            if mp:
                if mp.prix != new_price:
                    old_price = mp.prix

                    MarquePuretePrixHistory.objects.create(
                        marque_purete=mp,
                        marque=marque,
                        purete=mp.purete,
                        ancien_prix=old_price,
                        nouveau_prix=new_price,
                        modifier_par=user,
                        source=MarquePuretePrixHistory.SOURCE_API,
                    )

                    mp.prix = new_price
                    mp.save(update_fields=["prix", "date_modification"])

                    updated.append({
                        "id": pid,
                        "purete": mp.purete.purete,
                        "ancien_prix": str(old_price),
                        "prix": str(new_price),
                    })

                    history.append({
                        "id": pid,
                        "purete": mp.purete.purete,
                        "ancien_prix": str(old_price),
                        "nouveau_prix": str(new_price),
                    })
                else:
                    unchanged.append({
                        "id": pid,
                        "purete": mp.purete.purete,
                        "prix": str(mp.prix),
                    })
            else:
                new = MarquePurete.objects.create(
                    marque=marque,
                    purete_id=pid,
                    prix=new_price
                )

                created.append({
                    "id": pid,
                    "purete": new.purete.purete,
                    "prix": str(new.prix),
                })

        return Response({
            "message": "✅ Enregistré avec succès.",
            "marque": {
                "id": marque.id,
                "nom": marque.marque,
            },
            "created": created,
            "updated": updated,
            "unchanged": unchanged,
            "history_records": history,
        }, status=201 if created else 200)
        

class MarqueUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    allowed_roles_admin_manager = ["admin", "manager"]

    def has_permission_role(self, user):
        return user.user_role and user.user_role.role in self.allowed_roles_admin_manager

    @swagger_auto_schema(
        operation_summary="Modifier une marque + ses puretés + prix",
        operation_description="""
        Modifie une marque existante et ses prix par pureté.

        - Met à jour le nom de la marque.
        - Crée les nouvelles liaisons Marque–Pureté si elles n'existent pas.
        - Met à jour le prix si la liaison existe.
        - Journalise l'ancien prix dans MarquePuretePrixHistory.
        """,
        request_body=MarquePureteSerializer,
        responses={
            200: "Marque mise à jour",
            201: "Nouvelle liaison créée",
            400: "Erreur de validation",
            403: "Accès refusé",
            404: "Marque non trouvée / Pureté introuvable",
        },
        tags=["Marques"],
    )
    @transaction.atomic
    def put(self, request, pk):
        user = request.user

        if not self.has_permission_role(user):
            return Response(
                {"message": "Access Denied"},
                status=status.HTTP_403_FORBIDDEN
            )

        s = MarquePureteSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        marque_nom = s.validated_data["marque"]
        items = s.validated_data["puretes"]

        try:
            marque = Marque.objects.select_for_update().get(pk=pk)
        except Marque.DoesNotExist:
            return Response(
                {"detail": "Marque non trouvée."},
                status=status.HTTP_404_NOT_FOUND
            )

        old_marque_name = marque.marque
        marque.marque = marque_nom
        marque.save(update_fields=["marque"])

        latest = {
            int(e["purete_id"]): Decimal(e["prix"])
            for e in items
        }

        ids = list(latest.keys())

        found = set(
            Purete.objects.filter(id__in=ids)
            .values_list("id", flat=True)
        )

        missing = sorted(set(ids) - found)

        if missing:
            return Response(
                {"error": f"Pureté(s) introuvable(s): {missing}"},
                status=status.HTTP_404_NOT_FOUND
            )

        existing = {
            mp.purete_id: mp
            for mp in MarquePurete.objects.select_for_update()
            .select_related("purete")
            .filter(marque=marque, purete_id__in=ids)
        }

        created = []
        updated = []
        unchanged = []
        history = []

        for pid, new_price in latest.items():
            mp = existing.get(pid)

            if mp:
                old_price = mp.prix

                if old_price != new_price:
                    MarquePuretePrixHistory.objects.create(
                    marque_purete=mp,
                    marque=marque,
                    purete=mp.purete,
                    ancien_prix=old_price,
                    nouveau_prix=new_price,
                    modifier_par=user,
                    source=MarquePuretePrixHistory.SOURCE_API,
                )
                    mp.prix = new_price
                    mp.save(update_fields=["prix", "date_modification"])

                    updated.append({
                        "id": pid,
                        "purete": mp.purete.purete,
                        "ancien_prix": str(old_price),
                        "prix": str(new_price),
                    })

                    history.append({
                        "id": pid,
                        "purete": mp.purete.purete,
                        "ancien_prix": str(old_price),
                        "nouveau_prix": str(new_price),
                    })

                else:
                    unchanged.append({
                        "id": pid,
                        "purete": mp.purete.purete,
                        "prix": str(mp.prix),
                    })

            else:
                new = MarquePurete.objects.create(
                    marque=marque,
                    purete_id=pid,
                    prix=new_price
                )

                created.append({
                    "id": pid,
                    "purete": new.purete.purete,
                    "prix": str(new.prix),
                })

        return Response(
            {
                "message": "✅ Marque mise à jour avec succès.",
                "marque": {
                    "id": marque.id,
                    "ancien_nom": old_marque_name,
                    "nom": marque.marque,
                },
                "created": created,
                "updated": updated,
                "unchanged": unchanged,
                "history_records": history,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )

    @swagger_auto_schema(
        operation_summary="Modifier partiellement une marque + ses puretés + prix",
        request_body=MarquePureteSerializer,
        responses={
            200: "Marque partiellement mise à jour",
            201: "Nouvelle liaison créée",
            400: "Erreur de validation",
            403: "Accès refusé",
            404: "Marque non trouvée / Pureté introuvable",
        },
        tags=["Marques"],
    )
    @transaction.atomic
    def patch(self, request, pk):
        return self.put(request, pk)


class MarquePureteHistoryListView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Lister l'historique des prix Marque ↔ Pureté",
        manual_parameters=[
            openapi.Parameter("marque_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                            description="Filtrer par ID de marque", required=False),
            openapi.Parameter("purete_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                            description="Filtrer par ID de pureté", required=False),
            openapi.Parameter("limit", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                            description="Nombre max de lignes (pagination simple)", required=False),
            openapi.Parameter("offset", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                            description="Décalage (pagination simple)", required=False),
        ],
        responses={
            200: openapi.Response(
                description="Liste de l'historique",
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "marque": openapi.Schema(type=openapi.TYPE_STRING),
                            "purete": openapi.Schema(type=openapi.TYPE_STRING),
                            "ancien_prix": openapi.Schema(type=openapi.TYPE_STRING),
                            "nouveau_prix": openapi.Schema(type=openapi.TYPE_STRING),
                            "date_modification": openapi.Schema(type=openapi.TYPE_STRING, format="date-time"),
                            "modifier_par": openapi.Schema(type=openapi.TYPE_STRING, nullable=True),
                        }
                    )
                )
            )
        }
    )
    def get(self, request):
        # Evite le crash pendant la génération du schéma YASG
        if getattr(self, "swagger_fake_view", False):
            return Response([])

        marque_id = request.query_params.get("marque_id")
        purete_id = request.query_params.get("purete_id")
        limit = request.query_params.get("limit")
        offset = request.query_params.get("offset")

        qs = (
            MarquePuretePrixHistory.objects
            .select_related(
                "marque_purete",
                "marque",
                "purete",
                "modifier_par",
            )
            .order_by("-date_modification", "-id")
        )

        if marque_id:
            qs = qs.filter(marque_id=marque_id)
        if purete_id:
            qs = qs.filter(purete_id=purete_id)

        # Pagination simple (optionnelle)
        try:
            if offset is not None:
                offset = max(int(offset), 0)
            else:
                offset = 0
            if limit is not None:
                limit = max(int(limit), 1)
                qs = qs[offset:offset + limit]
            elif offset:
                qs = qs[offset:]
        except ValueError:
            return Response({"error": "limit/offset doivent être des entiers positifs."}, status=400)

        data = [{
            "marque": h.marque.marque if h.marque else None,
            "purete": h.purete.purete if h.purete else None,
            "ancien_prix": str(h.ancien_prix),
            "nouveau_prix": str(h.nouveau_prix),
            "date_modification": h.date_modification.isoformat(),
            "modifier_par": getattr(h.modifier_par, "username", None),
        } for h in qs]

        return Response(data, status=200)

# class MarqueUpdateAPIView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]

#     # ✅ Rôles autorisés à modifier une marque
#     allowed_roles_admin_manager = ['admin', 'manager']

#     def get_object(self, pk):
#         try:
#             return Marque.objects.get(pk=pk)
#         except Marque.DoesNotExist:
#             return None

#     @swagger_auto_schema(
#         operation_summary="Mettre à jour une marque (PUT)",
#         operation_description="Permet de remplacer complètement une marque avec les nouvelles données.",
#         request_body=MarqueSerializer,
#         responses={
#             200: openapi.Response(description="Marque mise à jour avec succès", schema=MarqueSerializer),
#             400: "Erreur de validation",
#             403: "Accès refusé",
#             404: "Marque non trouvée"
#         }
#     )
#     def put(self, request, pk):
#         user = request.user
#         if not user.user_role or user.user_role.role not in self.allowed_roles_admin_manager:
#             return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

#         marque = self.get_object(pk)
#         if not marque:
#             return Response({"detail": "Marque non trouvée"}, status=status.HTTP_404_NOT_FOUND)

#         serializer = MarqueSerializer(marque, data=request.data)
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#     @swagger_auto_schema(
#         operation_summary="Modifier une marque partiellement (PATCH)",
#         operation_description="Permet de mettre à jour certains champs d'une marque.",
#         request_body=MarqueSerializer,
#         responses={
#             200: openapi.Response(description="Marque partiellement mise à jour", schema=MarqueSerializer),
#             400: "Erreur de validation",
#             403: "Accès refusé",
#             404: "Marque non trouvée"
#         }
#     )
#     def patch(self, request, pk):
#         user = request.user
#         if not user.user_role or user.user_role.role not in self.allowed_roles_admin_manager:
#             return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

#         marque = self.get_object(pk)
#         if not marque:
#             return Response({"detail": "Marque non trouvée"}, status=status.HTTP_404_NOT_FOUND)

#         serializer = MarqueSerializer(marque, data=request.data, partial=True)
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    

class MarqueDeleteAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    # ✅ Rôles autorisés à supprimer une marque
    allowed_roles_admin_manager = ['admin', 'manager']

    def get_object(self, pk):
        try:
            return Marque.objects.get(pk=pk)
        except Marque.DoesNotExist:
            return None

    @swagger_auto_schema(
        operation_summary="🗑 Supprimer une marque",
        operation_description="Permet à un administrateur ou manager de supprimer une marque spécifique par son ID.",
        manual_parameters=[
            openapi.Parameter(
                'pk', openapi.IN_PATH,
                description="ID de la marque à supprimer",
                type=openapi.TYPE_INTEGER
            )
        ],
        responses={
            204: "Marque supprimée avec succès",
            403: "⛔ Accès refusé",
            404: "❌ Marque non trouvée"
        }
    )
    def delete(self, request, pk):
        user = request.user
        if not user.user_role or user.user_role.role not in self.allowed_roles_admin_manager:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        marque = self.get_object(pk)
        if not marque:
            return Response({"detail": "Marque non trouvée"}, status=status.HTTP_404_NOT_FOUND)

        marque.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    

class ModeleListAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    # ✅ Rôles autorisés
    allowed_roles_admin_manager = ['admin', 'manager']

    @swagger_auto_schema(
        operation_description="Lister tous les modèles, avec possibilité de filtrer par nom ou catégorie.",
        manual_parameters=[
            openapi.Parameter(
                'nom', openapi.IN_QUERY,
                description="Nom du modèle (recherche partielle)",
                type=openapi.TYPE_STRING
            ),
            openapi.Parameter(
                'categorie_id', openapi.IN_QUERY,
                description="ID de la catégorie",
                type=openapi.TYPE_INTEGER
            )
        ],
        responses={
            200: openapi.Response("Liste des modèles", ModeleSerializer(many=True)),
            403: "⛔ Accès refusé"
        }
    )
    def get(self, request):
        user = request.user
        if not user.user_role or user.user_role.role not in self.allowed_roles_admin_manager:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        queryset = Modele.objects.all()
        nom = request.GET.get('nom')
        categorie_id = request.GET.get('categorie_id')

        if nom:
            queryset = queryset.filter(modele__icontains=nom)
        if categorie_id:
            queryset = queryset.filter(categorie_id=categorie_id)

        serializer = ModeleSerializer(queryset, many=True)
        return Response(serializer.data)
    


class ModeleCreateAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    # ✅ Rôles autorisés pour créer un modèle
    allowed_roles_admin_manager = ['admin', 'manager']

    @swagger_auto_schema(
        operation_description="Créer un nouveau modèle en utilisant le nom de la catégorie.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["modele", "categorie"],
            properties={
                "modele": openapi.Schema(type=openapi.TYPE_STRING, description="Nom du modèle"),
                "categorie": openapi.Schema(type=openapi.TYPE_STRING, description="Nom de la catégorie (ex: 'Bague')"),
            },
            example={
                "modele": "Alliance homme or jaune",
                "categorie": "Bague"
            }
        ),
        responses={
            201: openapi.Response("Modèle créé avec succès", ModeleSerializer),
            400: "Erreur de validation",
            403: "⛔ Accès refusé"
        }
    )
    def post(self, request):
        user = request.user
        if not user.user_role or user.user_role.role not in self.allowed_roles_admin_manager:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        serializer = ModeleSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ModeleUpdateAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    # ✅ Liste des rôles autorisés
    allowed_roles_admin_manager = ['admin', 'manager']

    def get_object(self, pk):
        try:
            return Modele.objects.get(pk=pk)
        except Modele.DoesNotExist:
            return None

    @swagger_auto_schema(
        operation_description="🛠 Modifier complètement un modèle (PUT)",
        request_body=ModeleSerializer,
        responses={
            200: openapi.Response("Modèle mis à jour avec succès", ModeleSerializer),
            400: "Requête invalide",
            403: "Accès refusé",
            404: "Modèle introuvable"
        }
    )
    def put(self, request, pk):
        user = request.user
        if not user.user_role or user.user_role.role not in self.allowed_roles_admin_manager:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        modele_instance = self.get_object(pk)
        if modele_instance is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = ModeleSerializer(modele_instance, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_description="✏️ Modifier partiellement un modèle (PATCH)",
        request_body=ModeleSerializer,
        responses={
            200: openapi.Response("Modèle mis à jour partiellement", ModeleSerializer),
            400: "Requête invalide",
            403: "Accès refusé",
            404: "Modèle introuvable"
        }
    )
    def patch(self, request, pk):
        user = request.user
        if not user.user_role or user.user_role.role not in self.allowed_roles_admin_manager:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        modele = self.get_object(pk)
        if modele is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = ModeleSerializer(modele, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class ModeleDeleteAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    def get_object(self, pk):
        try:
            return Modele.objects.get(pk=pk)
        except Modele.DoesNotExist:
            return None

    def delete(self, request, pk):
        user = request.user
        if not user.user_role or user.user_role.role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        
        modele_instance = self.get_object(pk)
        if modele_instance is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        modele_instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProduitListAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Liste tous les rôles disponibles",
        responses={200: ProduitSerializer(many=True)},
        manual_parameters=[
            openapi.Parameter(
                'search',
                openapi.IN_QUERY,
                description="Filtrer les rôles par sku",
                type=openapi.TYPE_STRING
            )
        ]
    )
    def get(self, request):
        user = request.user
        if not user.user_role or user.user_role.role not in ['admin', 'manager', 'vendor']:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        
        search = request.GET.get('search')
        queryset = Produit.objects.all()
        if search:
            queryset = queryset.filter(sku__icontains=search)
        serializer = ProduitSerializer(queryset, many=True)
        return Response(serializer.data)



class ProduitCreateAPIView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]
    renderer_classes = [UserRenderer]

    @swagger_auto_schema(
        operation_summary="Créer un produit avec images et QR code",
        manual_parameters=[
            openapi.Parameter('image', openapi.IN_FORM, type=openapi.TYPE_FILE),
            openapi.Parameter('nom', openapi.IN_FORM, type=openapi.TYPE_STRING),
            openapi.Parameter('description', openapi.IN_FORM, type=openapi.TYPE_STRING),
            openapi.Parameter('genre', openapi.IN_FORM, type=openapi.TYPE_STRING, enum=['F', 'H', 'E'], default='F'),
            openapi.Parameter('categorie', openapi.IN_FORM, type=openapi.TYPE_STRING, description="Nom de la catégorie"),
            openapi.Parameter('marque', openapi.IN_FORM, type=openapi.TYPE_STRING, description="Nom de la marque"),
            openapi.Parameter('modele', openapi.IN_FORM, type=openapi.TYPE_STRING, description="Nom du modèle"),
            openapi.Parameter('purete', openapi.IN_FORM, type=openapi.TYPE_STRING, description="Valeur de la pureté (ex: '18')"),
            openapi.Parameter('matiere', openapi.IN_FORM, type=openapi.TYPE_STRING, enum=['or', 'argent', 'mixte'], default='or'),
            openapi.Parameter('poids', openapi.IN_FORM, type=openapi.TYPE_NUMBER),
            openapi.Parameter('taille', openapi.IN_FORM, type=openapi.TYPE_NUMBER),
            openapi.Parameter('status', openapi.IN_FORM, type=openapi.TYPE_STRING, enum=['publié', 'désactivé', 'rejetée'], default='publié'),
            openapi.Parameter('etat', openapi.IN_FORM, type=openapi.TYPE_STRING, enum=['N', 'R'], default='N'),
            openapi.Parameter('gallery', openapi.IN_FORM, type=openapi.TYPE_FILE, description="Fichiers galerie", required=False, multiple=True),
        ],
        responses={
            201: openapi.Response("Produit créé", ProduitSerializer),
            400: "Erreur de validation"
        }
    )
    @transaction.atomic
    def post(self, request):
        user = request.user
        if not user.user_role or user.user_role.role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        data = request.data.copy()

        # Serializer utilisera les noms pour FK : categorie, marque, modele, purete
        serializer = ProduitSerializer(data=data, context={"request": request})
        if serializer.is_valid():
            produit = serializer.save()

            # Sauvegarder les images de galerie si elles sont présentes
            for image in request.FILES.getlist("gallery"):
                Gallery.objects.create(produit=produit, image=image)

            # Recharge et renvoie la donnée enrichie
            produit.refresh_from_db()
            return Response(ProduitSerializer(produit, context={"request": request}).data, status=201)
        return Response(serializer.errors, status=400)


class ProduitDetailSlugView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="🧾 Détail d’un produit via son slug",
        operation_description="Retourne les informations complètes d’un produit en le récupérant par son `slug`.",
        responses={
            200: openapi.Response("Détail du produit", ProduitSerializer),
            404: "Produit non trouvé"
        },
        manual_parameters=[
            openapi.Parameter(
                'slug',
                openapi.IN_PATH,
                description="Slug du produit (ex: bague-or-abc123)",
                type=openapi.TYPE_STRING,
                required=True
            )
        ]
    )
    def get(self, request, slug):
        try:
            produit = Produit.objects.get(slug=slug)
            serializer = ProduitSerializer(produit, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Produit.DoesNotExist:
            return Response({"error": "Produit non trouvé."}, status=status.HTTP_404_NOT_FOUND)



class ProduitGetOneAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    
    def get_object(self, pk):
        try:
            return Produit.objects.get(pk=pk)
        except Produit.DoesNotExist:
            return None

    @swagger_auto_schema(
        operation_description="Récupère un produit par ID",
        responses={200: ProduitSerializer, 404: "Produit non trouvé"}
    )
    def get(self, request, pk):
        user = request.user
        if not user.user_role or user.user_role.role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        
        produit = self.get_object(pk)
        if produit is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = ProduitSerializer(produit)
        return Response(serializer.data)


class ProduitUpdateAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    
    def get_object(self, pk):
        try:
            return Produit.objects.get(pk=pk)
        except Produit.DoesNotExist:
            raise Http404
        
    @swagger_auto_schema(
        operation_description="Mise à jour complète d'un produit",
        request_body=ProduitSerializer,
        responses={
            200: ProduitSerializer,
            400: "Requête invalide",
            404: "Produit non trouvé"
        }
    )
    def put(self, request, pk):
        user = request.user
        if not user.user_role or user.user_role.role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        
        # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
        #     return Response({"message": "Access Denied"})
        produit = self.get_object(pk)
        if produit is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = ProduitSerializer(produit, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @swagger_auto_schema(
        operation_description="Mise à jour partielle d'un produit",
        request_body=ProduitSerializer,
        responses={
            200: ProduitSerializer,
            400: "Requête invalide",
            404: "Rôle non trouvé"
        }
    )
    def patch(self, request, pk):
        user = request.user
        if not user.user_role or user.user_role.role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        produit = self.get_object(pk)
        serializer = ProduitSerializer(produit, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProduitDeleteAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    
    def get_object(self, pk):
        try:
            return Produit.objects.get(pk=pk)
        except Produit.DoesNotExist:
            return None
    @swagger_auto_schema(
        operation_description="Supprime un produit par ID",
        responses={
            204: 'Supprimé avec succès',
            404: 'Produit non trouvé'
        }
    )
    def delete(self, request, pk):
        user = request.user
        if not user.user_role or user.user_role.role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        
        produit = self.get_object(pk)
        if produit is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        produit.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)



class QRCodeView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        responses={200: openapi.Response('response description', ProduitSerializer)},
        )
    def get(self, request, pk, format=None):
        user = request.user
        if not user.user_role or user.user_role.role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            # Retrieve the produit by its ID
            produit = Produit.objects.get(pk=pk)
            # Generate QR code data, e.g., produit URL or information
            # qr_data = f"Produit Nom: {produit.categorie.nom} {produit.modele} {produit.marque} {produit.purete}\nPrix gramme: {produit.marque.prix}\nDescription: {produit.description}"
            qr_data = f"Produit qr-code: {produit.slug}"
            # Create a QR code
            qr = qrcode.make(qr_data)
            # Save the QR code in a BytesIO object
            img_io = BytesIO()
            qr.save(img_io)
            img_io.seek(0)
            # Return the image as an HTTP response
            return HttpResponse(img_io, content_type="image/png")
        
        except Produit.DoesNotExist:
            return Response({"error": "Produit not found"}, status=status.HTTP_404_NOT_FOUND)
        


class ExportOneQRCodeExcelAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        responses={200: openapi.Response('response description', ProduitSerializer)},
        )
    def get(self, request, slug):
        try:
            produit = Produit.objects.get(slug=slug)
        except Produit.DoesNotExist:
            raise Http404("Produit non trouvé")

        # Créer le QR code
        data = f"Produit SKU: {produit.slug}"
        qr = qrcode.make(data)

        buffer = BytesIO()
        qr.save(buffer, format="PNG")
        buffer.seek(0)

        # Préparer le fichier Excel
        wb = Workbook()
        ws = wb.active
        ws.title = "QR Code Produit"
        ws.append(["Nom du produit", "QR Code"])
        ws.cell(row=2, column=1, value=produit.slug)

        # Ajouter l’image
        img = XLImage(buffer)
        img.width = 100
        img.height = 100
        ws.add_image(img, "B2")

        # Export
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        filename = f"qr_code_produit_{produit.slug}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        excel_buffer = BytesIO()
        wb.save(excel_buffer)
        response.write(excel_buffer.getvalue())

        return response


class ProduitRecentListAPIView(APIView):
    # permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Lister les produits actifs les plus récents",
        responses={200: ProduitWithGallerySerializer(many=True)}
    )
    def get(self, request):
        produits = Produit.objects.filter(status='publié').order_by('-date_ajout')[:20]
        serializer = ProduitWithGallerySerializer(produits, many=True, context={'request': request})
        return Response(serializer.data)



class MarquePuretePriceCompareDatesView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrManagerOrVendor]

    def get_price_at(self, *, marque, purete, bijouterie_id, dt):
        qs = MarquePuretePrixHistory.objects.filter(
            marque__marque__iexact=marque.strip(),
            purete__purete__iexact=str(purete).strip(),
            date_modification__lte=dt,
        )

        if bijouterie_id:
            qs = qs.filter(bijouterie_id=bijouterie_id)

        obj = qs.order_by("-date_modification", "-id").first()
        return obj.nouveau_prix if obj else None

    @swagger_auto_schema(
        operation_id="compareMarquePuretePriceByDates",
        operation_summary="Comparer le prix entre deux dates",
        operation_description="""
Compare le prix d'une combinaison marque / pureté entre deux dates.

Utilisation typique :
- savoir combien valait le prix à une date donnée
- comparer l'évolution entre deux moments
        """,
        manual_parameters=[
            openapi.Parameter("marque", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=True, description="Nom de la marque, ex: local"),
            openapi.Parameter("purete", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=True, description="Pureté, ex: 18"),
            openapi.Parameter("bijouterie_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, required=False, description="ID de la bijouterie"),
            openapi.Parameter("date_1", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=True, description="Date ISO datetime, ex: 2026-03-20T10:00:00Z"),
            openapi.Parameter("date_2", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=True, description="Date ISO datetime, ex: 2026-03-22T10:00:00Z"),
        ],
        responses={
            200: openapi.Response(
                description="Comparaison effectuée avec succès.",
                examples={
                    "application/json": {
                        "marque": "local",
                        "purete": "18",
                        "bijouterie_id": 1,
                        "date_1": "2026-03-20T10:00:00Z",
                        "prix_date_1": "4800.00",
                        "date_2": "2026-03-22T10:00:00Z",
                        "prix_date_2": "5200.00",
                        "difference": "400.00"
                    }
                }
            ),
            400: openapi.Response(
                description="Paramètres invalides."
            ),
        },
        tags=["Prix / Historique"],
    )
    def get(self, request, *args, **kwargs):
        marque = request.query_params.get("marque")
        purete = request.query_params.get("purete")
        bijouterie_id = request.query_params.get("bijouterie_id")
        date_1 = request.query_params.get("date_1")
        date_2 = request.query_params.get("date_2")

        if not marque or not purete or not date_1 or not date_2:
            return Response(
                {"detail": "Les paramètres marque, purete, date_1 et date_2 sont obligatoires."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        dt1 = parse_datetime(date_1)
        dt2 = parse_datetime(date_2)

        if not dt1 or not dt2:
            return Response(
                {"detail": "date_1 et date_2 doivent être au format ISO datetime."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        prix_1 = self.get_price_at(
            marque=marque,
            purete=purete,
            bijouterie_id=bijouterie_id,
            dt=dt1,
        )
        prix_2 = self.get_price_at(
            marque=marque,
            purete=purete,
            bijouterie_id=bijouterie_id,
            dt=dt2,
        )

        difference = None
        if prix_1 is not None and prix_2 is not None:
            difference = Decimal(str(prix_2)) - Decimal(str(prix_1))

        return Response(
            {
                "marque": marque,
                "purete": purete,
                "bijouterie_id": bijouterie_id,
                "date_1": date_1,
                "prix_date_1": str(prix_1) if prix_1 is not None else None,
                "date_2": date_2,
                "prix_date_2": str(prix_2) if prix_2 is not None else None,
                "difference": str(difference) if difference is not None else None,
            },
            status=status.HTTP_200_OK,
        )
    
    



class MarquePuretePriceEvolutionView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrManagerOrVendor]

    @swagger_auto_schema(
        operation_id="getMarquePuretePriceEvolution",
        operation_summary="Graphique évolution prix",
        operation_description="""
Retourne l'évolution chronologique du prix pour une combinaison marque / pureté.

Rôles autorisés :
- admin : accès global
- manager : accès limité à ses bijouteries
- vendor : accès limité à sa bijouterie

Utilisation typique :
- tracer une courbe dans le front
- voir l'évolution du prix dans le temps

Paramètres :
- marque (obligatoire)
- purete (obligatoire)
- bijouterie_id (optionnel)
        """,
        manual_parameters=[
            openapi.Parameter(
                "marque",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=True,
                description="Nom de la marque, ex: local",
            ),
            openapi.Parameter(
                "purete",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=True,
                description="Pureté, ex: 18",
            ),
            openapi.Parameter(
                "bijouterie_id",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="ID de la bijouterie",
            ),
        ],
        responses={
            200: openapi.Response(
                description="Évolution des prix.",
                examples={
                    "application/json": {
                        "count": 3,
                        "results": [
                            {"date": "2026-03-20T10:00:00Z", "prix": "4800.00"},
                            {"date": "2026-03-21T10:00:00Z", "prix": "5000.00"},
                            {"date": "2026-03-22T10:00:00Z", "prix": "5200.00"},
                        ],
                    }
                },
            ),
            400: openapi.Response(
                description="Paramètres invalides",
                examples={
                    "application/json": {
                        "detail": "Les paramètres 'marque' et 'purete' sont obligatoires."
                    }
                },
            ),
        },
        tags=["Prix / Historique"],
    )
    def get(self, request, *args, **kwargs):
        marque = (request.query_params.get("marque") or "").strip()
        purete = (request.query_params.get("purete") or "").strip()
        bijouterie_id = request.query_params.get("bijouterie_id")

        if not marque or not purete:
            return Response(
                {"detail": "Les paramètres 'marque' et 'purete' sont obligatoires."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        qs = (
            MarquePuretePrixHistory.objects
            .select_related("marque", "purete", "bijouterie")
            .filter(
                marque__marque__iexact=marque,
                purete__purete__iexact=purete,
            )
        )

        role = get_role_name(request.user)

        if role == ROLE_MANAGER:
            manager = getattr(request.user, "staff_manager_profile", None)
            if manager:
                qs = qs.filter(bijouterie__in=manager.bijouteries.all())
            else:
                qs = qs.none()

        elif role == ROLE_VENDOR:
            vendor = getattr(request.user, "staff_vendor_profile", None)
            if vendor and vendor.bijouterie_id:
                qs = qs.filter(bijouterie_id=vendor.bijouterie_id)
            else:
                qs = qs.none()

        if bijouterie_id:
            try:
                bijouterie_id = int(bijouterie_id)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "Le paramètre 'bijouterie_id' doit être un entier."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(bijouterie_id=bijouterie_id)

        qs = qs.order_by("date_modification", "id")

        points = [
            {
                "date": obj.date_modification.isoformat() if obj.date_modification else None,
                "prix": str(obj.nouveau_prix),
            }
            for obj in qs
        ]

        return Response({
            "count": len(points),
            "results": points,
        })


class MarquePuretePrixHistoryListView(ListAPIView):
    """
    Audit des changements de prix marque/pureté.
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]
    serializer_class = MarquePuretePrixHistorySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["bijouterie", "marque", "purete", "source", "changed_by"]

    @swagger_auto_schema(
        operation_id="listMarquePuretePrixHistory",
        operation_summary="Lister l'audit historique des changements de prix",
        operation_description="""
Retourne l’historique complet des changements de prix par marque / pureté.

Permet de savoir :
- qui a changé le prix
- quand
- de combien à combien
- depuis quelle source (api, admin, import_excel, rollback)
- pour quelle bijouterie, marque et pureté

### Filtres disponibles
- `bijouterie`
- `marque`
- `purete`
- `source`
- `changed_by`
- `date_from`
- `date_to`

### Exemples
- `/api/prix/history/`
- `/api/prix/history/?marque=1&purete=2`
- `/api/prix/history/?source=api`
- `/api/prix/history/?date_from=2026-03-01&date_to=2026-03-31`
        """,
        manual_parameters=[
            openapi.Parameter(
                "bijouterie",
                openapi.IN_QUERY,
                description="ID de la bijouterie",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                "marque",
                openapi.IN_QUERY,
                description="ID de la marque",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                "purete",
                openapi.IN_QUERY,
                description="ID de la pureté",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                "source",
                openapi.IN_QUERY,
                description="Source du changement : api, admin, import_excel, rollback",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "changed_by",
                openapi.IN_QUERY,
                description="ID de l'utilisateur ayant fait la modification",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                "date_from",
                openapi.IN_QUERY,
                description="Date début au format YYYY-MM-DD",
                type=openapi.TYPE_STRING,
                format="date",
                required=False,
            ),
            openapi.Parameter(
                "date_to",
                openapi.IN_QUERY,
                description="Date fin au format YYYY-MM-DD",
                type=openapi.TYPE_STRING,
                format="date",
                required=False,
            ),
        ],
        responses={200: MarquePuretePrixHistorySerializer(many=True)},
        tags=["Prix / Historique"],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        qs = (
            MarquePuretePrixHistory.objects
            .select_related("marque_purete", "marque", "purete", "bijouterie", "changed_by")
            .all()
        )

        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        if date_from:
            qs = qs.filter(date_modification__date__gte=date_from)

        if date_to:
            qs = qs.filter(date_modification__date__lte=date_to)

        # sécurité manager -> seulement ses bijouteries
        user = self.request.user
        manager = getattr(user, "staff_manager_profile", None)
        if manager and not getattr(user, "is_superuser", False):
            if manager.bijouteries.exists():
                qs = qs.filter(bijouterie__in=manager.bijouteries.all())

        return qs


class MarquePuretePrixEvolutionView(APIView):
    """
    Retourne les points chronologiques d'évolution du prix.
    """
    permission_classes = [IsAuthenticated, IsAdminOrManagerOrVendor]

    @swagger_auto_schema(
        operation_id="getMarquePuretePrixEvolution",
        operation_summary="Graphique évolution des prix",
        operation_description="""
Retourne l’évolution chronologique du prix pour une combinaison marque / pureté.

Cette vue est utile pour :
- tracer un graphique dans React / Angular
- analyser l’évolution du prix dans le temps
- filtrer par bijouterie, marque, pureté et période

### Filtres disponibles
- `marque`
- `purete`
- `bijouterie`
- `date_from`
- `date_to`

### Exemples
- `/api/prix/evolution/?marque=local&purete=18`
- `/api/prix/evolution/?marque=local&purete=18&date_from=2026-03-01&date_to=2026-03-31`
- `/api/prix/evolution/?bijouterie=1`
        """,
        manual_parameters=[
            openapi.Parameter(
                "marque",
                openapi.IN_QUERY,
                description="Nom de la marque, ex: local",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "purete",
                openapi.IN_QUERY,
                description="Valeur de la pureté, ex: 18",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "bijouterie",
                openapi.IN_QUERY,
                description="ID de la bijouterie",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                "date_from",
                openapi.IN_QUERY,
                description="Date début au format YYYY-MM-DD",
                type=openapi.TYPE_STRING,
                format="date",
                required=False,
            ),
            openapi.Parameter(
                "date_to",
                openapi.IN_QUERY,
                description="Date fin au format YYYY-MM-DD",
                type=openapi.TYPE_STRING,
                format="date",
                required=False,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Liste chronologique des points d'évolution.",
                examples={
                    "application/json": {
                        "count": 3,
                        "marque": "local",
                        "purete": "18",
                        "results": [
                            {
                                "date": "2026-03-20T09:00:00Z",
                                "prix": "4800.00",
                                "marque": "local",
                                "purete": "18",
                                "source": "api"
                            },
                            {
                                "date": "2026-03-21T09:00:00Z",
                                "prix": "5000.00",
                                "marque": "local",
                                "purete": "18",
                                "source": "import_excel"
                            },
                            {
                                "date": "2026-03-22T09:00:00Z",
                                "prix": "5200.00",
                                "marque": "local",
                                "purete": "18",
                                "source": "api"
                            }
                        ]
                    }
                },
            )
        },
        tags=["Prix / Historique"],
    )
    def get(self, request, *args, **kwargs):
        marque = request.query_params.get("marque")
        purete = request.query_params.get("purete")
        bijouterie = request.query_params.get("bijouterie")
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")

        qs = (
            MarquePuretePrixHistory.objects
            .select_related("marque", "purete", "bijouterie", "changed_by")
            .all()
        )

        if marque:
            qs = qs.filter(marque__marque__iexact=marque.strip())

        if purete:
            qs = qs.filter(purete__purete__iexact=str(purete).strip())

        if bijouterie:
            qs = qs.filter(bijouterie_id=bijouterie)

        if date_from:
            qs = qs.filter(date_modification__date__gte=date_from)

        if date_to:
            qs = qs.filter(date_modification__date__lte=date_to)

        # sécurité manager -> seulement ses bijouteries
        user = request.user
        manager = getattr(user, "staff_manager_profile", None)
        if manager and not getattr(user, "is_superuser", False):
            if manager.bijouteries.exists():
                qs = qs.filter(bijouterie__in=manager.bijouteries.all())

        qs = qs.order_by("date_modification", "id")

        results = [
            {
                "date": obj.date_modification,
                "prix": obj.nouveau_prix,
                "marque": getattr(obj.marque, "marque", None),
                "purete": getattr(obj.purete, "purete", None),
                "source": obj.source,
            }
            for obj in qs
        ]

        serializer = MarquePuretePrixEvolutionPointSerializer(results, many=True)

        return Response(
            {
                "count": len(serializer.data),
                "marque": marque,
                "purete": purete,
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )
        
        

class MarquePuretePriceRollbackView(APIView):
    """
    Restaure un ancien prix à partir d'une ligne d'historique.
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]

    @swagger_auto_schema(
        operation_id="rollbackMarquePuretePrice",
        operation_summary="Rollback d'un ancien prix",
        operation_description="""
Permet de restaurer un ancien prix à partir d'une ligne d'historique.

Fonctionnement :
- on lit une ligne d'historique
- on prend `ancien_prix`
- on le remet comme prix courant dans `MarquePurete`
- on crée une nouvelle ligne d'historique avec `source="rollback"`

### Cas d’usage
- erreur de saisie d’un prix
- besoin de revenir à une valeur précédente
- correction rapide par admin ou manager
        """,
        responses={
            200: openapi.Response(
                description="Rollback effectué avec succès.",
                examples={
                    "application/json": {
                        "message": "Rollback effectué avec succès.",
                        "marque": "local",
                        "purete": "18",
                        "ancien_prix_courant": "5200.00",
                        "prix_restaure": "5000.00",
                        "rollback_history_id": 14
                    }
                },
            ),
            400: openapi.Response(
                description="Le prix courant est déjà égal au prix à restaurer.",
                examples={
                    "application/json": {
                        "detail": "Le prix courant est déjà égal au prix à restaurer."
                    }
                },
            ),
            403: openapi.Response(
                description="Accès refusé."
            ),
            404: openapi.Response(
                description="Historique introuvable.",
                examples={
                    "application/json": {
                        "detail": "Historique introuvable."
                    }
                },
            ),
        },
        tags=["Prix / Historique"],
    )
    @transaction.atomic
    def post(self, request, history_id, *args, **kwargs):
        try:
            history = (
                MarquePuretePrixHistory.objects
                .select_related("marque_purete", "marque", "purete", "bijouterie")
                .select_for_update()
                .get(pk=history_id)
            )
        except MarquePuretePrixHistory.DoesNotExist:
            return Response(
                {"detail": "Historique introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        obj = history.marque_purete

        # sécurité manager -> seulement ses bijouteries
        user = request.user
        manager = getattr(user, "staff_manager_profile", None)
        if manager and not getattr(user, "is_superuser", False):
            if history.bijouterie_id and not manager.bijouteries.filter(pk=history.bijouterie_id).exists():
                return Response(
                    {"detail": "Vous ne pouvez pas effectuer un rollback sur cette bijouterie."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        old_current_price = Decimal(str(obj.prix or "0.00"))
        rollback_price = Decimal(str(history.ancien_prix or "0.00"))

        if old_current_price == rollback_price:
            return Response(
                {"detail": "Le prix courant est déjà égal au prix à restaurer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # mise à jour du prix courant
        obj.prix = rollback_price
        obj.save(update_fields=["prix"])

        # nouvelle ligne d'historique
        rollback_history = MarquePuretePrixHistory.objects.create(
            marque_purete=obj,
            marque=obj.marque,
            purete=obj.purete,
            bijouterie=history.bijouterie,
            ancien_prix=old_current_price,
            nouveau_prix=rollback_price,
            changed_by=request.user,
            source=MarquePuretePrixHistory.SOURCE_ROLLBACK,
            note=f"Rollback depuis historique #{history.id}",
        )

        return Response(
            {
                "message": "Rollback effectué avec succès.",
                "marque": getattr(obj.marque, "marque", None),
                "purete": getattr(obj.purete, "purete", None),
                "ancien_prix_courant": str(old_current_price),
                "prix_restaure": str(rollback_price),
                "rollback_history_id": rollback_history.id,
            },
            status=status.HTTP_200_OK,
        )
        
        


class MarquePuretePriceCompareDatesView(APIView):
    """
    Compare le prix d'une combinaison marque / pureté entre deux dates.
    """
    permission_classes = [IsAuthenticated, IsAdminOrManagerOrVendor]

    def get_price_at(self, *, marque, purete, bijouterie_id, dt):
        qs = MarquePuretePrixHistory.objects.filter(
            marque__marque__iexact=marque.strip(),
            purete__purete__iexact=str(purete).strip(),
            date_modification__lte=dt,
        )

        if bijouterie_id:
            qs = qs.filter(bijouterie_id=bijouterie_id)

        obj = qs.order_by("-date_modification", "-id").first()
        return obj.nouveau_prix if obj else None

    @swagger_auto_schema(
        operation_id="compareMarquePuretePriceByDates",
        operation_summary="Comparer le prix entre deux dates",
        operation_description="""
Compare le prix d'une combinaison marque / pureté entre deux dates.

Principe :
- on cherche la dernière valeur connue avant `date_1`
- on cherche la dernière valeur connue avant `date_2`
- on calcule la différence

### Paramètres requis
- `marque`
- `purete`
- `date_1`
- `date_2`

### Paramètre optionnel
- `bijouterie_id`

### Exemple
`/api/prix/compare-dates/?marque=local&purete=18&date_1=2026-03-20T10:00:00Z&date_2=2026-03-22T10:00:00Z`
        """,
        manual_parameters=[
            openapi.Parameter(
                "marque",
                openapi.IN_QUERY,
                description="Nom de la marque, ex: local",
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "purete",
                openapi.IN_QUERY,
                description="Valeur de la pureté, ex: 18",
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "bijouterie_id",
                openapi.IN_QUERY,
                description="ID de la bijouterie",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                "date_1",
                openapi.IN_QUERY,
                description="Première date au format ISO datetime, ex: 2026-03-20T10:00:00Z",
                type=openapi.TYPE_STRING,
                format="date-time",
                required=True,
            ),
            openapi.Parameter(
                "date_2",
                openapi.IN_QUERY,
                description="Deuxième date au format ISO datetime, ex: 2026-03-22T10:00:00Z",
                type=openapi.TYPE_STRING,
                format="date-time",
                required=True,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Comparaison effectuée avec succès.",
                examples={
                    "application/json": {
                        "marque": "local",
                        "purete": "18",
                        "bijouterie_id": 1,
                        "date_1": "2026-03-20T10:00:00Z",
                        "prix_date_1": "4800.00",
                        "date_2": "2026-03-22T10:00:00Z",
                        "prix_date_2": "5200.00",
                        "difference": "400.00"
                    }
                },
            ),
            400: openapi.Response(
                description="Paramètres invalides.",
                examples={
                    "application/json": {
                        "detail": "Les paramètres marque, purete, date_1 et date_2 sont obligatoires."
                    }
                },
            ),
            403: openapi.Response(description="Accès refusé."),
        },
        tags=["Prix / Historique"],
    )
    def get(self, request, *args, **kwargs):
        marque = request.query_params.get("marque")
        purete = request.query_params.get("purete")
        bijouterie_id = request.query_params.get("bijouterie_id")
        date_1 = request.query_params.get("date_1")
        date_2 = request.query_params.get("date_2")

        if not marque or not purete or not date_1 or not date_2:
            return Response(
                {"detail": "Les paramètres marque, purete, date_1 et date_2 sont obligatoires."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        dt1 = parse_datetime(date_1)
        dt2 = parse_datetime(date_2)

        if not dt1 or not dt2:
            return Response(
                {"detail": "date_1 et date_2 doivent être au format ISO datetime."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # sécurité manager -> seulement ses bijouteries
        user = request.user
        manager = getattr(user, "staff_manager_profile", None)
        if manager and not getattr(user, "is_superuser", False):
            if bijouterie_id and not manager.bijouteries.filter(pk=bijouterie_id).exists():
                return Response(
                    {"detail": "Vous ne pouvez pas consulter cette bijouterie."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        prix_1 = self.get_price_at(
            marque=marque,
            purete=purete,
            bijouterie_id=bijouterie_id,
            dt=dt1,
        )
        prix_2 = self.get_price_at(
            marque=marque,
            purete=purete,
            bijouterie_id=bijouterie_id,
            dt=dt2,
        )

        difference = None
        if prix_1 is not None and prix_2 is not None:
            difference = Decimal(str(prix_2)) - Decimal(str(prix_1))

        return Response(
            {
                "marque": marque,
                "purete": purete,
                "bijouterie_id": bijouterie_id,
                "date_1": date_1,
                "prix_date_1": str(prix_1) if prix_1 is not None else None,
                "date_2": date_2,
                "prix_date_2": str(prix_2) if prix_2 is not None else None,
                "difference": str(difference) if difference is not None else None,
            },
            status=status.HTTP_200_OK,
        )
        
                                        
                                