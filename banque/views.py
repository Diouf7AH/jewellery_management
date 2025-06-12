from rest_framework.views import APIView
from django.db import transaction as db_transaction
from decimal import Decimal, InvalidOperation
from django.conf import settings
from rest_framework.response import Response
from rest_framework import status
from .models import CompteBancaire, Transaction
from django.template.loader import render_to_string
from django.http import HttpResponse

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from django.utils import timezone
from rest_framework.response import Response

from backend.renderers import UserRenderer
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
from .serializer import ClientBanqueSerializer, CompteBancaireSerializer, TransactionSerializer
from .models import ClientBanque, CompteBancaire, Transaction
from django.utils.text import slugify


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


class CreateClientAndCompteView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Créer un client et ouvrir un compte bancaire associé.",
        request_body=CompteBancaireSerializer,
        responses={201: openapi.Response("Client et compte créés avec succès")},
    )
    def post(self, request):
        user = request.user
        role = getattr(user.user_role, 'role', None)
        if role not in ['admin', 'manager', 'vendor']:
            return Response({"message": "Access Denied"}, status=403)

        serializer = CompteBancaireSerializer(data=request.data)
        if serializer.is_valid():
            client_data = serializer.validated_data['client']
            telephone = client_data.get('telephone')
            solde = serializer.validated_data.get('solde', 0)

            # 🔒 Utilise le montant minimum défini dans settings
            minimum_solde = getattr(settings, "COMPTE_SOLDE_MINIMUM", 5000)
            if solde < minimum_solde:
                return Response(
                    {"detail": f"Le solde initial doit être au moins de {minimum_solde} FCFA."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if ClientBanque.objects.filter(telephone=telephone).exists():
                return Response(
                    {"detail": "Un client avec ce numéro de téléphone existe déjà."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Création du client
            client = ClientBanque.objects.create(**client_data)

            # Génération du numéro de compte
            numero = self.generer_numero_compte(telephone, client_data.get("address", "ADDR"))

            # Création du compte bancaire
            compte = CompteBancaire.objects.create(
                client=client,
                numero_compte=numero,
                solde=Decimal(solde),
                created_by=request.user
            )

            return Response({
                "message": "Client et compte créés avec succès",
                "client": ClientBanqueSerializer(client).data,
                "compte": {
                    "numero_compte": compte.numero_compte,
                    "solde": compte.solde,
                    "date_creation": compte.date_creation,
                }
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def generer_numero_compte(self, telephone, address):
        date_str = timezone.now().strftime('%Y%m')
        slug_address = slugify(address)[:10].upper()  # max 10 caractères
        prefix = f"CB-{telephone}-{date_str}-{slug_address}"
        
        if len(prefix) > 50:
            prefix = prefix[:50]  # sécurité supplémentaire
        
        if not CompteBancaire.objects.filter(numero_compte=prefix).exists():
            return prefix

        # En cas de collision, ajoute un identifiant court
        for _ in range(10):
            suffix = uuid.uuid4().hex[:4].upper()
            numero = f"{prefix[:45]}-{suffix}"  # ≤ 50
            if not CompteBancaire.objects.filter(numero_compte=numero).exists():
                return numero

        raise Exception("Impossible de générer un numéro de compte unique.")


class DepotView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Effectuer un dépôt sur un compte bancaire existant.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['numero_compte', 'montant'],
            properties={
                'numero_compte': openapi.Schema(type=openapi.TYPE_STRING, description="Numéro du compte bancaire"),
                'montant': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal', description="Montant à déposer (positif)"),
            }
        ),
        responses={
            200: openapi.Response(description="Dépôt effectué avec succès"),
            400: openapi.Response(description="Requête invalide"),
            404: openapi.Response(description="Compte non trouvé"),
            500: openapi.Response(description="Erreur serveur"),
        }
    )
    def post(self, request):
        
        user = request.user
        role = getattr(user.user_role, 'role', None)
        if role not in ['admin', 'manager', 'cashier']:
            return Response({"message": "Access Denied"}, status=403)

        numero_compte = request.data.get('numero_compte')
        montant_str = request.data.get('montant')

        if not numero_compte or not montant_str:
            raise ValidationError("Les champs 'numero_compte' et 'montant' sont requis.")

        try:
            montant = Decimal(montant_str)
        except (InvalidOperation, ValueError):
            raise ValidationError("Le montant doit être un nombre décimal valide.")

        montant_minimum = getattr(settings, "DEPOT_MINIMUM", 5000)
        if montant < Decimal(montant_minimum):
            raise ValidationError(f"Le montant doit être d’au moins {montant_minimum} FCFA.")

        try:
            with db_transaction.atomic():
                compte = CompteBancaire.objects.select_for_update().get(numero_compte=numero_compte)
                compte.solde += montant
                compte.save()

                trans = Transaction.objects.create(
                    compte=compte,
                    type_transaction="Depot",
                    montant=montant,
                    user=request.user,
                    statut="Terminé"
                )

            return Response({
                "statut": "Succès",
                "message": "Dépôt effectué avec succès.",
                "compte": compte.numero_compte,
                "montant": str(montant),
                "nouveau_solde": str(compte.solde),
                "date_transaction": trans.date_transaction.strftime("%Y-%m-%d %H:%M:%S"),
            }, status=200)

        except CompteBancaire.DoesNotExist:
            return Response({
                "statut": "Échec",
                "error": "Compte non trouvé."
            }, status=404)

class RetraitView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Effectuer un retrait sur un compte bancaire.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["numero_compte", "montant"],
            properties={
                "numero_compte": openapi.Schema(type=openapi.TYPE_STRING, description="Numéro du compte bancaire"),
                "montant": openapi.Schema(type=openapi.TYPE_NUMBER, format='float', description="Montant à retirer (≥ minimum)"),
            }
        ),
        responses={
            200: openapi.Response(description="Reçu PDF du retrait"),
            400: openapi.Response(description="Requête invalide"),
            404: openapi.Response(description="Compte non trouvé"),
            500: openapi.Response(description="Erreur lors du retrait"),
        }
    )
    def post(self, request):
        
        user = request.user
        role = getattr(user.user_role, 'role', None)
        if role not in ['admin', 'manager', 'cashier']:
            return Response({"message": "Access Denied"}, status=403)
        
        numero_compte = request.data.get("numero_compte")
        montant_str = request.data.get("montant")

        if not numero_compte or not montant_str:
            raise ValidationError("Les champs 'numero_compte' et 'montant' sont requis.")

        try:
            montant = Decimal(montant_str)
            montant_minimum = getattr(settings, "RETRAIT_MINIMUM", 5000)
            if montant < montant_minimum:
                raise ValidationError(f"Le montant minimum de retrait est de {montant_minimum} FCFA.")
        except ValueError:
            raise ValidationError("Le montant doit être un nombre valide.")

        try:
            with db_transaction.atomic():
                compte = CompteBancaire.objects.select_for_update().get(numero_compte=numero_compte)

                if compte.solde < montant:
                    return Response({"error": "Solde insuffisant"}, status=status.HTTP_400_BAD_REQUEST)

                compte.solde -= montant
                compte.save()

                transaction = Transaction.objects.create(
                    compte=compte,
                    type_transaction="Retrait",
                    montant=montant,
                    user=request.user,
                    statut="Terminé"
                )

            serializer = TransactionSerializer(transaction)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except CompteBancaire.DoesNotExist:
            return Response({"error": "Compte non trouvé"}, status=status.HTTP_404_NOT_FOUND)


class GetSoldeAPIView(APIView):
    permission_classes = [IsAuthenticated]

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
        
        user = request.user
        role = getattr(user.user_role, 'role', None)
        if role not in ['admin', 'manager', 'cashier', 'vendor']:
            return Response({"message": "Access Denied"}, status=403)
        
        numero_compte = request.query_params.get('numero_compte')

        if not numero_compte:
            return Response({"detail": "Le paramètre 'numero_compte' est requis."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            compte = CompteBancaire.objects.get(numero_compte=numero_compte)
            return Response({
                "numero_compte": compte.numero_compte,
                "solde": compte.solde,
                "date_creation": compte.date_creation
            }, status=status.HTTP_200_OK)
        except CompteBancaire.DoesNotExist:
            return Response({"detail": "Compte non trouvé."}, status=status.HTTP_404_NOT_FOUND)


class ListerTousComptesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Lister tous les comptes bancaires. Optionnel : filtrer par téléphone du client.",
        manual_parameters=[
            openapi.Parameter(
                'telephone', openapi.IN_QUERY,
                description="Numéro de téléphone du client à filtrer",
                type=openapi.TYPE_STRING,
                required=False
            )
        ],
        responses={
            200: openapi.Response("Liste des comptes", CompteBancaireSerializer(many=True)),
        }
    )
    def get(self, request):
        
        user = request.user
        role = getattr(user.user_role, 'role', None)
        if role not in ['admin', 'manager', 'cashier', 'vendor']:
            return Response({"message": "Access Denied"}, status=403)
        
        telephone = request.query_params.get('telephone')

        if telephone:
            comptes = CompteBancaire.objects.filter(client__telephone=telephone)
        else:
            comptes = CompteBancaire.objects.all()

        serializer = CompteBancaireSerializer(comptes, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)