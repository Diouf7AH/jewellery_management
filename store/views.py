# from knox.auth import TokenAuthentication
#Export to excel
import uuid
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.db.models.deletion import ProtectedError, RestrictedError
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django_filters.rest_framework import DjangoFilterBackend
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import (FileUploadParser, FormParser, JSONParser,
                                    MultiPartParser)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.bijouteries import get_user_bijouteries
from backend.permissions import (IsAdmin, IsAdminOrManager,
                                 IsAdminOrManagerOrVendor)
from backend.renderers import UserRenderer
from backend.roles import ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR, get_role_name
from purchase.models import ProduitLine
from store.models import (Bijouterie, Categorie, Gallery, Marque, MarquePurete,
                          MarquePuretePrixHistory, Modele, Produit, Purete)
from store.serializers import (BijouterieSerializer, CategorieSerializer,
                               MarquePuretePrixEvolutionPointSerializer,
                               MarquePuretePrixHistory,
                               MarquePuretePrixHistorySerializer,
                               MarquePureteSerializer, ModeleSerializer,
                               ProduitSerializer, PureteSerializer)

from .serializers import (MarquePuretePrixHistorySerializer,
                          ProduitRechercheSerializer)

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
    """
    Création d'une bijouterie.

    Accès :
    - Administrateur uniquement.

    Règles :
    - Nom unique.
    - NINEA unique lorsqu'il est renseigné.
    - TVA désactivée par défaut.
    - Taux de TVA conservé même si TVA désactivée.
    - Validation par BijouterieSerializer.
    """

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Créer une bijouterie",
        operation_description=(
            "Permet à un administrateur de créer "
            "une nouvelle bijouterie avec ses "
            "coordonnées, son NINEA, sa configuration "
            "TVA et ses logos."
        ),
        request_body=BijouterieSerializer,
        responses={
            201: openapi.Response(
                description="Bijouterie créée avec succès.",
                schema=BijouterieSerializer,
            ),
            400: "Données invalides.",
            403: "Accès refusé.",
        },
        tags=["Bijouteries"],
    )
    def post(self, request):

        # =====================================================
        # 1. Vérifier le rôle administrateur
        # =====================================================

        if get_role_name(request.user) != ROLE_ADMIN:
            return Response(
                {
                    "detail": (
                        "Seul un administrateur peut "
                        "créer une bijouterie."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # 2. Valider les données
        # =====================================================

        serializer = BijouterieSerializer(
            data=request.data,
            context={"request": request},
        )

        serializer.is_valid(raise_exception=True)

        # =====================================================
        # 3. Créer la bijouterie
        # =====================================================

        try:
            with transaction.atomic():
                bijouterie = serializer.save()

        except IntegrityError:
            return Response(
                {
                    "detail": (
                        "Impossible de créer la bijouterie. "
                        "Le nom ou le NINEA existe déjà."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # 4. Retourner la bijouterie créée
        # =====================================================

        response_serializer = BijouterieSerializer(
            bijouterie,
            context={"request": request},
        )

        return Response(
            {
                "message": "Bijouterie créée avec succès.",
                "bijouterie": response_serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


class BijouterieUpdateAPIView(APIView):
    """
    Mise à jour d'une bijouterie Rio-Gold.

    Administrateur :
        Peut modifier toutes les bijouteries.

    Manager :
        Peut modifier uniquement les bijouteries
        auxquelles il est autorisé à accéder.

    PUT :
        Mise à jour complète.

    PATCH :
        Mise à jour partielle.

    TVA :
        Le taux configuré reste enregistré
        lorsque appliquer_tva=False.
    """

    renderer_classes = [UserRenderer]

    permission_classes = [IsAuthenticated]

    parser_classes = [
        MultiPartParser,
        FormParser,
        JSONParser,
    ]

    # ========================================================
    # VÉRIFICATION DES PERMISSIONS
    # ========================================================

    def check_role(self, request):
        role = get_role_name(request.user)

        if role not in (ROLE_ADMIN, ROLE_MANAGER):
            return Response(
                {
                    "detail": (
                        "Vous n'avez pas la permission "
                        "de modifier une bijouterie."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return None

    # ========================================================
    # RÉCUPÉRATION SÉCURISÉE
    # ========================================================

    def get_bijouterie(self, request, pk):
        queryset = get_user_bijouteries(request.user)

        return get_object_or_404(
            queryset,
            pk=pk,
        )

    # ========================================================
    # MISE À JOUR
    # ========================================================

    def update_bijouterie(
        self,
        request,
        pk,
        partial=False,
    ):
        # 1. Vérifier le rôle.
        permission_error = self.check_role(request)

        if permission_error is not None:
            return permission_error

        # 2. Vérifier l'accès à la bijouterie.
        bijouterie = self.get_bijouterie(
            request,
            pk,
        )

        # 3. Valider les données.
        serializer = BijouterieSerializer(
            bijouterie,
            data=request.data,
            partial=partial,
            context={"request": request},
        )

        serializer.is_valid(raise_exception=True)

        # 4. Enregistrer.
        try:
            with transaction.atomic():
                serializer.save()

        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                errors = exc.message_dict
            else:
                errors = exc.messages

            raise ValidationError(errors)

        except IntegrityError:
            raise ValidationError({
                "detail": (
                    "Impossible de modifier la bijouterie. "
                    "Le nom ou le NINEA existe déjà."
                )
            })

        # 5. Retourner les données actualisées.
        response_serializer = BijouterieSerializer(
            serializer.instance,
            context={"request": request},
        )

        return Response(
            {
                "message": (
                    "Bijouterie mise à jour avec succès."
                ),
                "bijouterie": response_serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    # ========================================================
    # PUT
    # ========================================================

    @swagger_auto_schema(
        operation_summary="Modifier une bijouterie",
        operation_description=(
            "Mise à jour complète d'une bijouterie."
        ),
        request_body=BijouterieSerializer,
        responses={
            200: "Bijouterie mise à jour.",
            400: "Données invalides.",
            403: "Accès refusé.",
            404: "Bijouterie introuvable.",
        },
        tags=["Bijouteries"],
    )
    def put(self, request, pk):
        return self.update_bijouterie(
            request,
            pk,
            partial=False,
        )

    # ========================================================
    # PATCH
    # ========================================================

    @swagger_auto_schema(
        operation_summary="Modifier partiellement une bijouterie",
        operation_description=(
            "Modifie uniquement les champs transmis."
        ),
        request_body=BijouterieSerializer,
        responses={
            200: "Bijouterie mise à jour.",
            400: "Données invalides.",
            403: "Accès refusé.",
            404: "Bijouterie introuvable.",
        },
        tags=["Bijouteries"],
    )
    def patch(self, request, pk):
        return self.update_bijouterie(
            request,
            pk,
            partial=True,
        )
        


class BijouterieDeleteAPIView(APIView):
    """
    Suppression d'une bijouterie Rio-Gold.

    Règles :
    - Administrateur uniquement.
    - Suppression définitive si aucune relation
      protégée ne bloque l'opération.
    - Préservation des achats, ventes, factures
      et autres données protégées.
    """

    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Supprimer une bijouterie",
        operation_description=(
            "Permet à un administrateur de supprimer "
            "une bijouterie. La suppression est refusée "
            "si des données liées sont protégées."
        ),
        responses={
            204: "Bijouterie supprimée avec succès.",
            403: "Accès refusé.",
            404: "Bijouterie introuvable.",
            409: "Suppression impossible : données liées.",
        },
        tags=["Bijouteries"],
    )
    def delete(self, request, pk):

        # =====================================================
        # 1. Vérifier le rôle administrateur
        # =====================================================

        if get_role_name(request.user) != ROLE_ADMIN:
            return Response(
                {
                    "detail": (
                        "Seul un administrateur peut "
                        "supprimer une bijouterie."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # 2. Rechercher la bijouterie
        # =====================================================

        bijouterie = get_object_or_404(
            Bijouterie,
            pk=pk,
        )

        # =====================================================
        # 3. Suppression sécurisée
        # =====================================================

        try:
            with transaction.atomic():
                bijouterie.delete()

        except (ProtectedError, RestrictedError):
            return Response(
                {
                    "detail": (
                        "Impossible de supprimer cette "
                        "bijouterie car elle possède "
                        "des données liées protégées "
                        "(achats, ventes, stocks, "
                        "factures ou personnel)."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        # =====================================================
        # 4. Succès
        # =====================================================

        return Response(
            status=status.HTTP_204_NO_CONTENT,
        )


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
        tags=["Marque"],
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
        responses={201: "Créé/Mis à jour"},
        tags=["Marque"],   
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
        tags=["Marque"],
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
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            
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
        tags=["Marque"],
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
        },
        tags=["Marque"],
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
        },
        tags=["Marque"],
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
        },
        tags=["Modèle"]
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
        },
        tags=["Modèle"]
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
        },
        tags=["Modèle"]
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
        },
        tags=["Modèle"]
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

    @swagger_auto_schema(
        operation_description="🗑️ Supprimer un modèle",
        responses={
            204: "Modèle supprimé",
            403: "Accès refusé",
            404: "Modèle introuvable"
        },
        tags=["Modèle"]
    )
    def delete(self, request, pk):
        user = request.user
        if not user.user_role or user.user_role.role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        
        modele_instance = self.get_object(pk)
        if modele_instance is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        modele_instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)



class ProduitRecherchePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class ProduitRechercheQRView(APIView):

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_id="rechercherProduitParQR",
        operation_summary="Rechercher un produit par QR code",
        operation_description=(
            "Recherche automatiquement une ProduitLine "
            "à partir du QR code scanné.\n\n"
            "Format attendu : PL:<UUID>\n\n"
            "Retourne les informations du produit "
            "et de sa ligne d'achat."
        ),
        manual_parameters=[
            openapi.Parameter(
                name="qr_code",
                in_=openapi.IN_QUERY,
                description=(
                    "Contenu du QR code de la ProduitLine. "
                    "Exemple : PL:550e8400-e29b-41d4-a716-446655440000"
                ),
                type=openapi.TYPE_STRING,
                required=True,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Produit retrouvé avec succès.",
            ),
            400: openapi.Response(
                description="Format ou UUID du QR code invalide.",
            ),
            401: openapi.Response(
                description="Authentification requise.",
            ),
            404: openapi.Response(
                description="ProduitLine introuvable.",
            ),
        },
        tags=["Achats / Recherche produits"],
    )
    def get(self, request):

        qr_code = request.query_params.get(
            "qr_code", ""
        ).strip()

        if not qr_code.startswith("PL:"):
            return Response(
                {
                    "message": "Format de QR code invalide."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ligne_uuid = uuid.UUID(qr_code[3:])
        except (ValueError, AttributeError):
            return Response(
                {
                    "message": "UUID du QR code invalide."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        ligne = get_object_or_404(
            ProduitLine.objects.select_related(
                "produit",
                "lot",
                "lot__achat",
            ),
            uuid=ligne_uuid,
        )

        produit = ligne.produit

        return Response(
            {
                "message": "Produit retrouvé avec succès.",
                "produit": {
                    "id": produit.id,
                    "uuid": str(produit.uuid),
                    "sku": produit.sku,
                    "nom": produit.nom,
                    "poids": str(produit.poids),
                    "taille": (
                        str(produit.taille)
                        if produit.taille is not None
                        else None
                    ),
                },
                "ligne_achat": {
                    "id": ligne.id,
                    "uuid": str(ligne.uuid),
                    "etat": ligne.etat,
                    "quantite_achetee": ligne.quantite,
                    "poids_unitaire_achat": str(
                        ligne.poids_unitaire_achat
                    ),
                    "lot_id": ligne.lot_id,
                    "achat_id": ligne.lot.achat_id,
                },
            },
            status=status.HTTP_200_OK,
        )


class ProduitRechercheView(APIView):
    """
    Recherche de produits du catalogue.

    Utilisée notamment lors de la création d'un arrivage.

    Recherche :
    - SKU
    - nom
    - catégorie
    - modèle
    - marque
    - pureté

    Filtres :
    - categorie_id
    - modele_id
    - marque_id
    - purete_id
    - poids
    - taille

    Recherche insensible à la casse.
    """

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Rechercher un produit du catalogue",
        operation_description=(
            "Recherche paginée des produits existants. "
            "Permet de sélectionner un produit lors d'un arrivage. "
            "Aucune création ni modification de stock."
        ),
        manual_parameters=[
            openapi.Parameter(
                "q",
                openapi.IN_QUERY,
                description="SKU, nom, catégorie, modèle, marque ou pureté",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            *[
                openapi.Parameter(
                    champ,
                    openapi.IN_QUERY,
                    description=f"Filtrer par {champ}",
                    type=openapi.TYPE_INTEGER,
                    required=False,
                )
                for champ in [
                    "categorie_id",
                    "modele_id",
                    "marque_id",
                    "purete_id",
                ]
            ],
            openapi.Parameter(
                "poids",
                openapi.IN_QUERY,
                type=openapi.TYPE_NUMBER,
                required=False,
            ),
            openapi.Parameter(
                "taille",
                openapi.IN_QUERY,
                type=openapi.TYPE_NUMBER,
                required=False,
            ),
            openapi.Parameter(
                "page",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                "page_size",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
        ],
        responses={
            200: "Produits trouvés",
            400: "Paramètres invalides",
            401: "Authentification requise",
        },
        tags=["Produit"],
    )
    def get(self, request):
        queryset = (
            Produit.objects
            .select_related(
                "categorie",
                "modele",
                "marque",
                "purete",
            )
            .order_by("id")
        )

        q = request.query_params.get("q", "").strip()

        if q:
            queryset = queryset.filter(
                Q(sku__icontains=q)
                | Q(nom__icontains=q)
                | Q(categorie__nom__icontains=q)
                | Q(modele__modele__icontains=q)
                | Q(marque__marque__icontains=q)
                | Q(purete__purete__icontains=q)
            )

        for champ in [
            "categorie_id",
            "modele_id",
            "marque_id",
            "purete_id",
        ]:
            valeur = request.query_params.get(champ)

            if valeur is not None:
                try:
                    valeur = int(valeur)
                    if valeur < 1:
                        raise ValueError
                except (ValueError, TypeError):
                    return Response(
                        {
                            champ: [
                                "Un identifiant entier positif est requis."
                            ]
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                queryset = queryset.filter(
                    **{champ: valeur}
                )

        for champ in ["poids", "taille"]:
            valeur = request.query_params.get(champ)

            if valeur is not None:
                try:
                    decimal = Decimal(valeur)

                    if (
                        not decimal.is_finite()
                        or decimal < 0
                        or decimal.as_tuple().exponent < -2
                    ):
                        raise InvalidOperation

                except (InvalidOperation, ValueError, TypeError):
                    return Response(
                        {
                            champ: [
                                "Valeur décimale positive valide "
                                "avec deux décimales maximum requise."
                            ]
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                queryset = queryset.filter(
                    **{champ: decimal}
                )

        paginator = ProduitRecherchePagination()

        page = paginator.paginate_queryset(
            queryset,
            request,
            view=self,
        )

        serializer = ProduitRechercheSerializer(
            page,
            many=True,
            context={"request": request},
        )

        return paginator.get_paginated_response(
            serializer.data
        )


    
class ProduitListAPIView(APIView):
    """
    Liste des produits du catalogue.

    Accessible aux utilisateurs autorisés à consulter
    le catalogue produit.
    """

    renderer_classes = [UserRenderer]
    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]

    @swagger_auto_schema(
        operation_description=(
            "Liste tous les produits disponibles. "
            "Possibilité de rechercher par SKU."
        ),
        responses={
            200: ProduitSerializer(many=True),
            403: "Accès refusé",
        },
        manual_parameters=[
            openapi.Parameter(
                "search",
                openapi.IN_QUERY,
                description="Rechercher un produit par SKU",
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
        tags=["Produit"],
    )
    def get(self, request):
        search = request.query_params.get(
            "search",
            "",
        ).strip()

        queryset = (
            Produit.objects
            .select_related(
                "categorie",
                "purete",
                "marque",
                "modele",
            )
            .all()
        )

        if search:
            queryset = queryset.filter(
                sku__icontains=search,
            )

        serializer = ProduitSerializer(
            queryset,
            many=True,
            context={
                "request": request,
            },
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )


class ProduitCreateAPIView(APIView):
    """
    Création d'un produit dans le catalogue Rio-Gold.

    - Nouveau produit : HTTP 201
    - Produit existant : HTTP 200
    - Données invalides : HTTP 400

    Aucun doublon n'est créé lorsque les six
    caractéristiques correspondent.
    """

    permission_classes = [IsAdminOrManager]
    parser_classes = [MultiPartParser, FormParser]

    @swagger_auto_schema(
        operation_summary="Créer ou retrouver un produit",
        operation_description=(
            "Enregistre un produit dans le catalogue Rio-Gold. "
            "Si un produit possède déjà les mêmes six "
            "caractéristiques, il est automatiquement réutilisé. "
            "Un message d'information indique le résultat."
        ),
        tags=["Produit"],
        manual_parameters=[
            openapi.Parameter(
                "categorie_id",
                openapi.IN_FORM,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="Identifiant de la catégorie",
            ),
            openapi.Parameter(
                "modele_id",
                openapi.IN_FORM,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="Identifiant du modèle",
            ),
            openapi.Parameter(
                "marque_id",
                openapi.IN_FORM,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="Identifiant de la marque",
            ),
            openapi.Parameter(
                "purete_id",
                openapi.IN_FORM,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="Identifiant de la pureté",
            ),
            openapi.Parameter(
                "poids",
                openapi.IN_FORM,
                type=openapi.TYPE_NUMBER,
                required=True,
                description="Poids du bijou en grammes",
            ),
            openapi.Parameter(
                "taille",
                openapi.IN_FORM,
                type=openapi.TYPE_NUMBER,
                required=False,
                description="Taille du bijou",
            ),
            openapi.Parameter(
                "nom",
                openapi.IN_FORM,
                type=openapi.TYPE_STRING,
                required=False,
                description="Nom du produit",
            ),
            openapi.Parameter(
                "description",
                openapi.IN_FORM,
                type=openapi.TYPE_STRING,
                required=False,
                description="Description du produit",
            ),
            openapi.Parameter(
                "matiere",
                openapi.IN_FORM,
                type=openapi.TYPE_STRING,
                required=False,
                description="Matière du bijou",
            ),
            openapi.Parameter(
                "genre",
                openapi.IN_FORM,
                type=openapi.TYPE_STRING,
                required=False,
                description="Genre du bijou",
            ),
            openapi.Parameter(
                "image",
                openapi.IN_FORM,
                type=openapi.TYPE_FILE,
                required=False,
                description="Image principale",
            ),
        ],
        responses={
            200: openapi.Response(
                description="Produit existant réutilisé",
            ),
            201: openapi.Response(
                description="Nouveau produit enregistré",
            ),
            400: openapi.Response(
                description="Informations invalides",
            ),
            401: "Authentification requise",
        },
    )
    def post(self, request):

        serializer = ProduitSerializer(
            data=request.data,
            context={"request": request},
        )

        # Validation des informations.
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "created": False,
                    "type": "error",
                    "message": (
                        "Impossible d'enregistrer le produit. "
                        "Veuillez vérifier les informations saisies."
                    ),
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Création ou récupération.
        produit = serializer.save()

        created = serializer.produit_created

        produit_data = ProduitSerializer(
            produit,
            context={"request": request},
        ).data

        # Nouveau produit.
        if created:
            return Response(
                {
                    "success": True,
                    "created": True,
                    "type": "success",
                    "message": (
                        "Produit enregistré avec succès "
                        "dans le catalogue."
                    ),
                    "produit": produit_data,
                },
                status=status.HTTP_201_CREATED,
            )

        # Produit déjà existant.
        return Response(
            {
                "success": True,
                "created": False,
                "type": "info",
                "message": (
                    "Ce produit existe déjà dans le catalogue. "
                    "Aucun doublon n'a été créé. "
                    "Le produit existant a été réutilisé."
                ),
                "produit": produit_data,
            },
            status=status.HTTP_200_OK,
        )



class ProduitDetailSlugView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [UserRenderer]

    @swagger_auto_schema(
        operation_summary="Détail d’un produit via son slug",
        operation_description=(
            "Retourne les informations complètes d’un produit "
            "à partir de son slug.\n\n"
            "Accès : admin et manager uniquement."
        ),
        responses={
            200: openapi.Response(
                "Détail du produit",
                ProduitSerializer,
            ),
            403: "Accès refusé",
            404: "Produit non trouvé",
        },
        manual_parameters=[
            openapi.Parameter(
                "slug",
                openapi.IN_PATH,
                description="Slug du produit (ex: bague-or-abc123)",
                type=openapi.TYPE_STRING,
                required=True,
            )
        ],
        tags=["Produit"],
    )
    def get(self, request, slug):
        role = get_role_name(request.user)

        # Admin + Manager uniquement
        if role not in {ROLE_ADMIN, ROLE_MANAGER}:
            return Response(
                {
                    "detail": (
                        "Accès refusé. "
                        "Réservé aux administrateurs et managers."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            produit = (
                Produit.objects
                .select_related(
                    "categorie",
                    "marque",
                    "modele",
                    "purete",
                )
                .prefetch_related(
                    "produit_gallery",
                )
                .get(slug=slug)
            )

        except Produit.DoesNotExist:
            return Response(
                {"detail": "Produit non trouvé."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ProduitSerializer(
            produit,
            context={"request": request},
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
        

class ProduitGetOneAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return (
                Produit.objects
                .select_related(
                    "categorie",
                    "marque",
                    "modele",
                    "purete",
                )
                .prefetch_related(
                    "produit_gallery",
                )
                .get(pk=pk)
            )
        except Produit.DoesNotExist:
            return None

    @swagger_auto_schema(
        operation_summary="Récupérer un produit par ID",
        operation_description=(
            "Retourne le détail complet d’un produit par son ID.\n\n"
            "Accès : admin et manager uniquement."
        ),
        responses={
            200: openapi.Response(
                "Détail du produit",
                ProduitSerializer,
            ),
            403: "Accès refusé",
            404: "Produit non trouvé",
        },
        tags=["Produit"],
    )
    def get(self, request, pk):
        role = get_role_name(request.user)

        # Admin + Manager uniquement
        if role not in {ROLE_ADMIN, ROLE_MANAGER}:
            return Response(
                {
                    "detail": (
                        "Accès refusé. "
                        "Réservé aux administrateurs et managers."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        produit = self.get_object(pk)

        if produit is None:
            return Response(
                {"detail": "Produit non trouvé."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ProduitSerializer(
            produit,
            context={"request": request},
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

class ProduitUpdateAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_object(self, pk):
        try:
            return (
                Produit.objects
                .select_related(
                    "categorie",
                    "marque",
                    "modele",
                    "purete",
                )
                .prefetch_related(
                    "produit_gallery",
                )
                .get(pk=pk)
            )
        except Produit.DoesNotExist:
            raise Http404

    def check_role(self, user):
        """
        Admin et Manager uniquement.
        """
        role = get_role_name(user)

        if role not in {ROLE_ADMIN, ROLE_MANAGER}:
            raise PermissionDenied(
                "Accès refusé. Réservé aux administrateurs et managers."
            )

    # ========================================================
    # PUT
    # ========================================================

    @swagger_auto_schema(
        operation_summary="Modifier complètement un produit",
        operation_description=(
            "Mise à jour complète d'un produit.\n\n"
            "Accès : admin et manager uniquement."
        ),
        request_body=ProduitSerializer,
        responses={
            200: openapi.Response(
                "Produit mis à jour",
                ProduitSerializer,
            ),
            400: "Requête invalide",
            403: "Accès refusé",
            404: "Produit non trouvé",
        },
        tags=["Produit"],
    )
    def put(self, request, pk):
        self.check_role(request.user)

        produit = self.get_object(pk)

        serializer = ProduitSerializer(
            produit,
            data=request.data,
            context={"request": request},
        )

        serializer.is_valid(raise_exception=True)

        produit = serializer.save()

        # Réponse complète avec gallery
        produit = self.get_object(produit.pk)

        response_serializer = ProduitSerializer(
            produit,
            context={"request": request},
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_200_OK,
        )

    # ========================================================
    # PATCH
    # ========================================================

    @swagger_auto_schema(
        operation_summary="Modifier partiellement un produit",
        operation_description=(
            "Mise à jour partielle d'un produit.\n\n"
            "Accès : admin et manager uniquement."
        ),
        request_body=ProduitSerializer,
        responses={
            200: openapi.Response(
                "Produit mis à jour",
                ProduitSerializer,
            ),
            400: "Requête invalide",
            403: "Accès refusé",
            404: "Produit non trouvé",
        },
        tags=["Produit"],
    )
    def patch(self, request, pk):
        self.check_role(request.user)

        produit = self.get_object(pk)

        serializer = ProduitSerializer(
            produit,
            data=request.data,
            partial=True,
            context={"request": request},
        )

        serializer.is_valid(raise_exception=True)

        produit = serializer.save()

        # Réponse complète avec gallery
        produit = self.get_object(produit.pk)

        response_serializer = ProduitSerializer(
            produit,
            context={"request": request},
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_200_OK,
        )


class ProduitDeleteAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return Produit.objects.get(pk=pk)
        except Produit.DoesNotExist:
            return None

    @swagger_auto_schema(
        operation_summary="Supprimer un produit",
        operation_description=(
            "Supprime un produit par son ID.\n\n"
            "Accès : admin et manager uniquement."
        ),
        responses={
            204: "Produit supprimé avec succès",
            403: "Accès refusé",
            404: "Produit non trouvé",
        },
        tags=["Produit"],
    )
    def delete(self, request, pk):
        role = get_role_name(request.user)

        # Admin + Manager uniquement
        if role not in {ROLE_ADMIN, ROLE_MANAGER}:
            return Response(
                {
                    "detail": (
                        "Accès refusé. "
                        "Réservé aux administrateurs et managers."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        produit = self.get_object(pk)

        if produit is None:
            return Response(
                {"detail": "Produit non trouvé."},
                status=status.HTTP_404_NOT_FOUND,
            )

        produit.delete()

        return Response(
            status=status.HTTP_204_NO_CONTENT,
        )

# class QRCodeView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated, IsAdminOrManager]

#     @swagger_auto_schema(
#         operation_summary="Générer le QR code d'un produit",
#         operation_description=(
#             "Génère un QR code PNG pour un produit.\n\n"
#             "Accès : admin et manager uniquement."
#         ),
#         responses={
#             200: openapi.Response(
#                 description="QR code PNG du produit"
#             ),
#             403: "Accès refusé",
#             404: "Produit non trouvé",
#         },
#         tags=["Produit"],
#     )
#     def get(self, request, pk, format=None):
#         role = get_role_name(request.user)

#         if role not in {ROLE_ADMIN, ROLE_MANAGER}:
#             return Response(
#                 {
#                     "detail": (
#                         "Accès refusé. "
#                         "Réservé aux administrateurs et managers."
#                     )
#                 },
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         try:
#             produit = Produit.objects.get(pk=pk)

#         except Produit.DoesNotExist:
#             return Response(
#                 {"detail": "Produit non trouvé."},
#                 status=status.HTTP_404_NOT_FOUND,
#             )

#         # Contenu du QR code
#         qr_data = f"P:{produit.uuid}"

#         qr = qrcode.make(qr_data)

#         img_io = BytesIO()
#         qr.save(
#             img_io,
#             format="PNG",
#         )
#         img_io.seek(0)

#         return HttpResponse(
#             img_io.getvalue(),
#             content_type="image/png",
#         )


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
        
                                        