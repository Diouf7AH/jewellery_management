import uuid
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.db import transaction as db_transaction
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.renderers import UserRenderer

from .models import ClientDepot, CompteDepot, Transaction
from .serializers import (ClientDepotSerializer, CompteDepotSerializer,
                          TransactionCreateSerializer, TransactionSerializer)
from .services import effectuer_depot, effectuer_retrait

# class CreateClientAndCompteView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Créer un client et ouvrir un compte bancaire associé.",
#         request_body=CompteBancaireerializer,
#         responses={201: openapi.Response("Client et compte créés")},
#     )
#     def post(self, request):
#         serializer = CompteBancaireSerializer(data=request.data)
#         if serializer.is_valid():
#             client_data = serializer.validated_data['client']
#             solde = serializer.validated_data.get('solde', 0)

#             if solde < 0:
#                 return Response({"detail": "Le solde ne peut pas être négatif."}, status=400)

#             client = ClientBanque.objects.create(**client_data)
#             numero = self.generer_numero_compte()

#             compte = CompteBancaire.objects.create(
#                 client=client,
#                 numero_compte=numero,
#                 solde=Decimal(solde)
#             )

#             return Response({
#                 "message": "Client et compte créés avec succès",
#                 "client": ClientBanqueSerializer(client).data,
#                 "compte": {
#                     "numero_compte": compte.numero_compte,
#                     "solde": compte.solde,
#                     "date_creation": compte.date_creation,
#                 }
#             }, status=201)

#         return Response(serializer.errors, status=400)

#     def generer_numero_compte(self):
#         for _ in range(10):
#             numero = f"CB-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
#             if not CompteBancaire.objects.filter(numero_compte=numero).exists():
#                 return numero
#         raise Exception("Impossible de générer un numéro de compte unique.")


# class CreateClientAndCompteView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Créer un client et ouvrir un compte bancaire associé (solde min. 5000 FCFA).",
#         request_body=CompteBancaireCreateSerializer,
#         responses={201: openapi.Response("Client et compte créés avec succès")},
#     )
#     def post(self, request):
#         serializer = CompteBancaireCreateSerializer(data=request.data)
#         if serializer.is_valid():
#             client_data = serializer.validated_data['client']
#             solde = serializer.validated_data.get('solde', 0)

#             # Vérification stricte du solde minimal
#             if solde < 5000:
#                 return Response(
#                     {"detail": "Le solde initial doit être d'au moins 5000 FCFA."},
#                     status=status.HTTP_400_BAD_REQUEST
#                 )

#             # Création du client
#             client = ClientBanque.objects.create(**client_data)

#             # Génération d'un numéro de compte unique
#             numero = self.generer_numero_compte()

#             # Création du compte bancaire
#             compte = CompteBancaire.objects.create(
#                 client=client,
#                 numero_compte=numero,
#                 solde=Decimal(solde)
#             )

#             return Response({
#                 "message": "Client et compte créés avec succès.",
#                 "client": ClientBanqueSerializer(client).data,
#                 "compte": {
#                     "numero_compte": compte.numero_compte,
#                     "solde": compte.solde,
#                     "date_creation": getattr(compte, 'date_creation', timezone.now()),  # fallback si champ absent
#                 }
#             }, status=status.HTTP_201_CREATED)

#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#     def generer_numero_compte(self):
#         """Génère un numéro de compte unique."""
#         for _ in range(10):
#             numero = f"CB-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
#             if not CompteBancaire.objects.filter(numero_compte=numero).exists():
#                 return numero
#         raise Exception("Impossible de générer un numéro de compte unique.")


# class CreateClientAndCompteView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Créer un client et ouvrir un compte bancaire associé.",
#         request_body=CompteBancaireCreateSerializer,
#         responses={201: openapi.Response("Client et compte créés avec succès")},
#     )
#     def post(self, request):
#         user = request.user
#         role = getattr(user.user_role, 'role', None)
#         if role not in ['admin', 'manager', 'cashier']:
#             return Response({"message": "Access Denied"}, status=403)

#         serializer = CompteBancaireCreateSerializer(data=request.data)
#         if serializer.is_valid():
#             client_data = serializer.validated_data['client']
#             telephone = client_data.get('telephone')
#             address = client_data.get('address', 'ADDR') or 'ADDR'  # Valeur par défaut si vide
#             solde = serializer.validated_data.get('solde', 0)

#             if solde < 5000:
#                 return Response(
#                     {"detail": "Le solde initial doit être au moins de 5000 FCFA."},
#                     status=status.HTTP_400_BAD_REQUEST
#                 )

#             if ClientBanque.objects.filter(telephone=telephone).exists():
#                 return Response(
#                     {"detail": "Un client avec ce numéro de téléphone existe déjà."},
#                     status=status.HTTP_400_BAD_REQUEST
#                 )

#             # 👤 Création du client
#             client = ClientBanque.objects.create(**client_data)

#             # 🔢 Génération du numéro de compte unique
#             try:
#                 numero = self.generer_numero_compte(telephone, address)
#             except Exception as e:
#                 return Response(
#                     {"detail": "Erreur lors de la génération du numéro de compte."},
#                     status=status.HTTP_500_INTERNAL_SERVER_ERROR
#                 )

#             # 🏦 Création du compte bancaire
#             compte = CompteBancaire.objects.create(
#                 client=client,
#                 numero_compte=numero,
#                 solde=Decimal(solde),
#                 created_by=request.user
#             )

#             return Response({
#                 "message": "Client et compte créés avec succès",
#                 "client": ClientBanqueSerializer(client).data,
#                 "compte": {
#                     "numero_compte": compte.numero_compte,
#                     "solde": compte.solde,
#                     "date_creation": compte.date_creation,
#                 }
#             }, status=status.HTTP_201_CREATED)

#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#     def generer_numero_compte(self, telephone, address):
#         """ Génère un numéro de compte basé sur téléphone + mois/année + adresse """
#         date_str = timezone.now().strftime('%Y%m')
#         prefix = f"CB-{telephone}-{date_str}-{slugify(address)[:10].upper()}"
        
#         for _ in range(10):
#             numero = f"{prefix}"
#             if not CompteBancaire.objects.filter(numero_compte=numero).exists():
#                 return numero

#         # for _ in range(10):
#         #     numero = f"{prefix}-{uuid.uuid4().hex[:3].upper()}"
#         #     if not CompteBancaire.objects.filter(numero_compte=numero).exists():
#         #         return numero

#         raise Exception("Impossible de générer un numéro de compte unique.")



class ListCompteDepotView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Lister tous les comptes dépôt avec les informations du client.",
        responses={200: openapi.Response("Liste des comptes", CompteDepotSerializer(many=True))}
    )
    def get(self, request):
        try:
            user = request.user
            role = getattr(user.user_role, 'role', None)

            if role not in ['admin', 'manager', 'vendor']:
                return Response({"message": "Access Denied"}, status=403)

            comptes = CompteDepot.objects.select_related('client', 'created_by').all().order_by('-date_creation')
            serializer = CompteDepotSerializer(comptes, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# class CreateClientAndCompteView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Créer un client et ouvrir un compte dépôt associé.",
#         request_body=CompteDepotSerializer,
#         responses={201: openapi.Response("Client et compte créés avec succès")},
#     )
#     def post(self, request):
#         try:
#             user = request.user
#             role = getattr(user.user_role, 'role', None)
#             if role not in ['admin', 'manager', 'cashier']:
#                 return Response({"message": "Access Denied"}, status=403)

#             serializer = CompteDepotSerializer(data=request.data)
#             if serializer.is_valid():
#                 client_data = serializer.validated_data['client']
#                 telephone = client_data.get('telephone')
#                 solde = serializer.validated_data.get('solde', 0)

#                 minimum_solde = getattr(settings, "COMPTE_SOLDE_MINIMUM", 5000)
#                 if solde < minimum_solde:
#                     return Response(
#                         {"detail": f"Le solde initial doit être au moins de {minimum_solde} FCFA."},
#                         status=status.HTTP_400_BAD_REQUEST
#                     )

#                 client = ClientDepot.objects.filter(telephone=telephone).first()
#                 if client:
#                     if CompteDepot.objects.filter(client=client).exists():
#                         return Response(
#                             {"detail": "Ce client possède déjà un compte bancaire."},
#                             status=status.HTTP_400_BAD_REQUEST
#                         )
#                 else:
#                     client = ClientDepot.objects.create(**client_data)

#                 numero = self.generer_numero_compte(telephone)

#                 compte = CompteDepot.objects.create(
#                     client=client,
#                     numero_compte=numero,
#                     solde=Decimal(solde),
#                     created_by=user
#                 )

#                 return Response({
#                     "message": "Client et compte créés avec succès",
#                     "client": ClientDepotSerializer(client).data,
#                     "compte": {
#                         "numero_compte": compte.numero_compte,
#                         "solde": compte.solde,
#                         "date_creation": compte.date_creation,
#                     }
#                 }, status=status.HTTP_201_CREATED)

#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#         except Exception as e:
#             return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

#     def generer_numero_compte(self, telephone):
#         date_str = timezone.now().strftime('%y%m')
#         prefix = f"{telephone}-{date_str}"

#         if len(prefix) > 25:
#             prefix = prefix[:25]

#         if not CompteDepot.objects.filter(numero_compte=prefix).exists():
#             return prefix

#         for _ in range(10):
#             suffix = uuid.uuid4().hex[:4].upper()
#             numero = f"{prefix[:25]}-{suffix}"
#             if not CompteDepot.objects.filter(numero_compte=numero).exists():
#                 return numero

#         raise Exception("Impossible de générer un numéro de compte unique.")


class CreateClientAndCompteView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Créer un client et ouvrir un compte dépôt associé.",
        request_body=CompteDepotSerializer,
        responses={201: openapi.Response("Client et compte créés avec succès")},
    )
    @transaction.atomic
    def post(self, request):
        user = request.user
        role = getattr(getattr(user, 'user_role', None), 'role', None)
        if role not in ['admin', 'manager', 'cashier']:
            return Response({"message": "Access Denied"}, status=403)

        s = CompteDepotSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        client_data = s.validated_data['client']
        telephone = client_data.get('telephone')
        solde_initial = s.validated_data.get('solde', 0)

        minimum_solde = getattr(settings, "COMPTE_SOLDE_MINIMUM", 5000)
        if solde_initial < minimum_solde:
            return Response(
                {"detail": f"Le solde initial doit être au moins de {minimum_solde} FCFA."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # upsert client
        client = ClientDepot.objects.filter(telephone=telephone).first()
        if client and CompteDepot.objects.filter(client=client).exists():
            return Response({"detail": "Ce client possède déjà un compte."}, status=400)
        if not client:
            client = ClientDepot.objects.create(**client_data)

        numero = self.generer_numero_compte(telephone)
        compte = CompteDepot.objects.create(
            client=client,
            numero_compte=numero,
            created_by=user,
            solde=0  # ⚠️ on laisse à 0, puis on crédite via le service
        )

        # ✅ dépôt initial via le service (traçabilité Transaction)
        from .services import effectuer_depot
        effectuer_depot(compte.id, Decimal(solde_initial), user)

        return Response({
            "message": "Client et compte créés avec succès",
            "client": ClientDepotSerializer(client).data,
            "compte": {
                "numero_compte": compte.numero_compte,
                "solde": str(compte.solde),           # déjà mis à jour par le service
                "date_creation": compte.date_creation,
            }
        }, status=status.HTTP_201_CREATED)

    def generer_numero_compte(self, telephone):
        date_str = timezone.now().strftime('%y%m')
        prefix = f"{telephone}-{date_str}"
        if len(prefix) > 25:
            prefix = prefix[:25]
        if not CompteDepot.objects.filter(numero_compte=prefix).exists():
            return prefix
        # anti-collision
        for _ in range(10):
            suffix = uuid.uuid4().hex[:4].upper()
            numero = f"{prefix[:25]}-{suffix}"
            if not CompteDepot.objects.filter(numero_compte=numero).exists():
                return numero
        raise Exception("Impossible de générer un numéro de compte unique.")



# class DepotView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Effectuer un dépôt sur un compte depot existant.",
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=['numero_compte', 'montant'],
#             properties={
#                 'numero_compte': openapi.Schema(type=openapi.TYPE_STRING, description="Numéro du compte depot"),
#                 'montant': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal', description="Montant à déposer (positif)"),
#             }
#         ),
#         responses={
#             200: openapi.Response(description="Dépôt effectué avec succès"),
#             400: openapi.Response(description="Requête invalide"),
#             404: openapi.Response(description="Compte non trouvé"),
#             500: openapi.Response(description="Erreur serveur"),
#         }
#     )
#     def post(self, request):
#         try:
#             user = request.user
#             role = getattr(user.user_role, 'role', None)
#             if role not in ['admin', 'manager', 'cashier']:
#                 return Response({"message": "Access Denied"}, status=403)

#             numero_compte = request.data.get('numero_compte')
#             montant_str = request.data.get('montant')

#             if not numero_compte or not montant_str:
#                 raise ValidationError("Les champs 'numero_compte' et 'montant' sont requis.")

#             try:
#                 montant = Decimal(montant_str)
#             except (InvalidOperation, ValueError):
#                 raise ValidationError("Le montant doit être un nombre décimal valide.")

#             montant_minimum = getattr(settings, "DEPOT_MINIMUM", 5000)
#             if montant < Decimal(montant_minimum):
#                 raise ValidationError(f"Le montant doit être d’au moins {montant_minimum} FCFA.")

#             with db_transaction.atomic():
#                 compte = CompteDepot.objects.select_for_update().get(numero_compte=numero_compte)
#                 compte.solde += montant
#                 compte.save()

#                 trans = Transaction.objects.create(
#                     compte=compte,
#                     type_transaction="Depot",
#                     montant=montant,
#                     user=request.user,
#                     statut="Terminé"
#                 )

#             return Response({
#                 "statut": "Succès",
#                 "message": "Dépôt effectué avec succès.",
#                 "compte": compte.numero_compte,
#                 "montant": str(montant),
#                 "nouveau_solde": str(compte.solde),
#                 "date_transaction": trans.date_transaction.strftime("%Y-%m-%d %H:%M:%S"),
#             }, status=200)

#         except CompteDepot.DoesNotExist:
#             return Response({
#                 "statut": "Échec",
#                 "error": "Compte non trouvé."
#             }, status=404)

#         except Exception as e:
#             return Response({"error": str(e)}, status=500)

# Pour permettre un dépôt via le numéro de téléphone du client (au lieu du numero_compte), il suffit de :
# Rechercher le client via telephone.
# Récupérer son compte (CompteDepot) associé.
# Faire le dépôt.
# class DepotView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Effectuer un dépôt via le téléphone du client (ou le numéro de compte).",
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=['telephone', 'montant'],
#             properties={
#                 'telephone': openapi.Schema(type=openapi.TYPE_STRING, description="Téléphone du client (ou numéro de compte)"),
#                 'montant': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal', description="Montant à déposer (positif)"),
#             }
#         ),
#         responses={
#             200: openapi.Response(description="Dépôt effectué avec succès"),
#             400: openapi.Response(description="Requête invalide"),
#             404: openapi.Response(description="Client ou compte non trouvé"),
#             500: openapi.Response(description="Erreur serveur"),
#         }
#     )
#     def post(self, request):
#         try:
#             user = request.user
#             role = getattr(user.user_role, 'role', None)
#             if role not in ['admin', 'manager', 'cashier']:
#                 return Response({"message": "Access Denied"}, status=403)

#             telephone = request.data.get('telephone')
#             montant_str = request.data.get('montant')

#             if not telephone or not montant_str:
#                 raise ValidationError("Les champs 'telephone' et 'montant' sont requis.")

#             try:
#                 montant = Decimal(montant_str)
#             except (InvalidOperation, ValueError):
#                 raise ValidationError("Le montant doit être un nombre décimal valide.")

#             montant_minimum = getattr(settings, "DEPOT_MINIMUM", 5000)
#             if montant < Decimal(montant_minimum):
#                 raise ValidationError(f"Le montant doit être d’au moins {montant_minimum} FCFA.")

#             with db_transaction.atomic():
#                 client = ClientDepot.objects.filter(telephone=telephone).first()
#                 if not client:
#                     return Response({"error": "Client introuvable."}, status=404)

#                 compte = CompteDepot.objects.select_for_update().filter(client=client).first()
#                 if not compte:
#                     return Response({"error": "Compte associé introuvable."}, status=404)

#                 compte.solde += montant
#                 compte.save()

#                 trans = Transaction.objects.create(
#                     compte=compte,
#                     type_transaction="Depot",
#                     montant=montant,
#                     user=user,
#                     statut="Terminé"
#                 )

#             return Response({
#                 "statut": "Succès",
#                 "message": "Dépôt effectué avec succès.",
#                 "telephone": telephone,
#                 "numero_compte": compte.numero_compte,
#                 "montant": str(montant),
#                 "nouveau_solde": str(compte.solde),
#                 "date_transaction": trans.date_transaction.strftime("%Y-%m-%d %H:%M:%S"),
#             }, status=200)

#         except Exception as e:
#             return Response({"error": str(e)}, status=500)


# class RetraitView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Effectuer un retrait sur un compte bancaire.",
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["telephone", "montant"],
#             properties={
#                 "telephone": openapi.Schema(type=openapi.TYPE_STRING, description="Numéro de telephone depot"),
#                 "montant": openapi.Schema(type=openapi.TYPE_NUMBER, format='float', description="Montant à retirer (≥ minimum)"),
#             }
#         ),
#         responses={
#             200: openapi.Response(description="Reçu PDF du retrait"),
#             400: openapi.Response(description="Requête invalide"),
#             404: openapi.Response(description="Compte non trouvé"),
#             500: openapi.Response(description="Erreur lors du retrait"),
#         }
#     )
#     def post(self, request):
#         try:
#             user = request.user
#             role = getattr(user.user_role, 'role', None)
#             if role not in ['admin', 'manager', 'cashier']:
#                 return Response({"message": "Access Denied"}, status=403)

#             telephone = request.data.get('telephone')
#             montant_str = request.data.get("montant")

#             if not telephone or not montant_str:
#                 raise ValidationError("Les champs 'telephone' et 'montant' sont requis.")

#             try:
#                 montant = Decimal(montant_str)
#             except (ValueError, InvalidOperation):
#                 raise ValidationError("Le montant doit être un nombre valide.")

#             montant_minimum = getattr(settings, "RETRAIT_MINIMUM", 5000)
#             if montant < montant_minimum:
#                 raise ValidationError(f"Le montant minimum de retrait est de {montant_minimum} FCFA.")

#             with db_transaction.atomic():
#                 # compte = CompteDepot.objects.select_for_update().get(telephone=telephone)
#                 compte = CompteDepot.objects.select_for_update().get(client__telephone=telephone)
                
#                 if compte.solde < montant:
#                     return Response({"error": "Solde insuffisant"}, status=status.HTTP_400_BAD_REQUEST)

#                 compte.solde -= montant
#                 compte.save()

#                 transaction = Transaction.objects.create(
#                     compte=compte,
#                     type_transaction="Retrait",
#                     montant=montant,
#                     user=user,
#                     statut="Terminé"
#                 )

#             serializer = TransactionSerializer(transaction)
#             return Response(serializer.data, status=status.HTTP_200_OK)

#         except CompteDepot.DoesNotExist:
#             return Response({"error": "Compte non trouvé"}, status=status.HTTP_404_NOT_FOUND)

#         except Exception as e:
#             return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


ALLOWED_ROLES = {"admin", "manager", "cashier"}

def _user_role(user):
    return getattr(getattr(user, "user_role", None), "role", None)

class DepotView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Effectuer un dépôt sur un compte par son numéro.",
        request_body=TransactionCreateSerializer,
        responses={201: openapi.Response("Dépôt enregistré", TransactionSerializer)},
    )
    @transaction.atomic
    def post(self, request, numero_compte: str):
        role = _user_role(request.user)
        if role not in ALLOWED_ROLES:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        try:
            compte = CompteDepot.objects.select_for_update().get(numero_compte=numero_compte)
        except CompteDepot.DoesNotExist:
            return Response({"detail": "Compte introuvable."}, status=status.HTTP_404_NOT_FOUND)

        s = TransactionCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        try:
            tx = effectuer_depot(compte.id, Decimal(s.validated_data["montant"]), request.user)
        except ValidationError as e:
            return Response({"detail": e.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "message": "Dépôt enregistré",
            "transaction": TransactionSerializer(tx).data,
            "nouveau_solde": str(compte.solde),  # le service a mis à jour le solde
        }, status=status.HTTP_201_CREATED)


class RetraitView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Effectuer un retrait sur un compte par son numéro.",
        request_body=TransactionCreateSerializer,
        responses={201: openapi.Response("Retrait enregistré", TransactionSerializer)},
    )
    @transaction.atomic
    def post(self, request, numero_compte: str):
        role = _user_role(request.user)
        if role not in ALLOWED_ROLES:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        try:
            compte = CompteDepot.objects.select_for_update().get(numero_compte=numero_compte)
        except CompteDepot.DoesNotExist:
            return Response({"detail": "Compte introuvable."}, status=status.HTTP_404_NOT_FOUND)

        s = TransactionCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        try:
            tx = effectuer_retrait(compte.id, Decimal(s.validated_data["montant"]), request.user)
        except ValidationError as e:
            return Response({"detail": e.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "message": "Retrait enregistré",
            "transaction": TransactionSerializer(tx).data,
            "nouveau_solde": str(compte.solde),
        }, status=status.HTTP_201_CREATED)
        

class GetSoldeAPIView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [UserRenderer]
    
    @swagger_auto_schema(
        operation_description="Récupérer le solde d’un compte bancaire à partir du numéro de compte.",
        manual_parameters=[
            openapi.Parameter(
                'numero_compte', openapi.IN_QUERY,
                description="Numéro du compte bancaire",
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        responses={
            200: openapi.Response("Solde récupéré avec succès"),
            404: openapi.Response("Compte non trouvé"),
            400: openapi.Response("Paramètre manquant"),
        }
    )
    def get(self, request):
        try:
            user = request.user
            role = getattr(user.user_role, 'role', None)
            if role not in ['admin', 'manager', 'cashier', 'vendor']:
                return Response({"message": "Access Denied"}, status=403)

            numero_compte = request.query_params.get('numero_compte')

            if not numero_compte:
                return Response({"detail": "Le paramètre 'numero_compte' est requis."}, status=status.HTTP_400_BAD_REQUEST)

            try:
                compte = CompteDepot.objects.get(numero_compte=numero_compte)
                return Response({
                    "numero_compte": compte.numero_compte,
                    "solde": compte.solde,
                    "date_creation": compte.date_creation
                }, status=status.HTTP_200_OK)
            except CompteDepot.DoesNotExist:
                return Response({"detail": "Compte non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class ListerTousComptesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Lister tous les comptes depots. Optionnel : filtrer par téléphone du client (partiel ou complet).",
        manual_parameters=[
            openapi.Parameter(
                'telephone', openapi.IN_QUERY,
                description="Numéro de téléphone (partiel ou complet) du client",
                type=openapi.TYPE_STRING,
                required=False
            )
        ],
        responses={
            200: openapi.Response("Liste des comptes", CompteDepotSerializer(many=True)),
        }
    )
    def get(self, request):
        try:
            user = request.user
            role = getattr(user.user_role, 'role', None)
            if role not in ['admin', 'manager', 'cashier', 'vendor']:
                return Response({"message": "Access Denied"}, status=403)

            telephone = request.query_params.get('telephone')

            comptes = CompteDepot.objects.select_related('client', 'created_by')

            if telephone:
                comptes = comptes.filter(client__telephone__icontains=telephone)

            serializer = CompteDepotSerializer(comptes, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ListerToutesTransactionsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Lister toutes les transactions (dépôts et retraits). Optionnel : filtrer par téléphone ou numéro de compte.",
        manual_parameters=[
            openapi.Parameter(
                'telephone', openapi.IN_QUERY,
                description="Numéro de téléphone (partiel ou complet) du client",
                type=openapi.TYPE_STRING,
                required=False
            ),
            # openapi.Parameter(
            #     'numero_compte', openapi.IN_QUERY,
            #     description="Numéro exact du compte",
            #     type=openapi.TYPE_STRING,
            #     required=False
            # ),
        ],
        responses={
            200: openapi.Response("Liste des transactions", TransactionSerializer(many=True)),
        }
    )
    def get(self, request):
        try:
            user = request.user
            role = getattr(user.user_role, 'role', None)
            if role not in ['admin', 'manager', 'cashier', 'vendor']:
                return Response({"message": "Access Denied"}, status=403)

            telephone = request.query_params.get('telephone')
            # numero_compte = request.query_params.get('numero_compte')

            transactions = Transaction.objects.select_related('compte__client', 'user').order_by('-date_transaction')

            # if numero_compte:
            #     transactions = transactions.filter(compte__numero_compte=numero_compte)
            if telephone:
                transactions = transactions.filter(compte__client__telephone__icontains=telephone)

            serializer = TransactionSerializer(transactions, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

