# compte_depot/views.py

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.renderers import UserRenderer
from backend.utils.helpers import (resolve_bijouterie_for_user,
                                   user_can_access_bijouterie)
from compte_depot.notifications import (send_compte_created_notification,
                                        send_compte_depot_notification)

from .models import ClientDepot, CompteDepot, CompteDepotTransaction
from .pdf import generate_transaction_ticket_80mm_pdf
from .serializers import (ClientDepotSerializer, CompteDepotSerializer,
                          CompteDepotTelephoneTransactionSerializer,
                          CompteDepotTransactionSerializer,
                          CreateOrDepotCompteSerializer)
from .services import effectuer_depot, effectuer_retrait

ALLOWED_ROLES = {"admin", "manager", "cashier"}


def _user_role(user):
    return getattr(getattr(user, "user_role", None), "role", None)


def get_user_bijouterie(user):
    """
    Retourne la bijouterie liée à l'utilisateur si elle existe.
    Adapte cette logique selon ta structure réelle.
    """
    vendor_profile = getattr(user, "staff_vendor_profile", None)
    if vendor_profile and getattr(vendor_profile, "bijouterie", None):
        return vendor_profile.bijouterie

    cashier_profile = getattr(user, "staff_cashier_profile", None)
    if cashier_profile and getattr(cashier_profile, "bijouterie", None):
        return cashier_profile.bijouterie

    manager_profile = getattr(user, "staff_manager_profile", None)
    if manager_profile:
        bijouterie = manager_profile.bijouteries.first()
        if bijouterie:
            return bijouterie

    return None


# =========================================================
# LISTE COMPTES
# =========================================================
# class ListCompteDepotView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Lister tous les comptes dépôt avec les informations du client.",
#         responses={200: openapi.Response("Liste des comptes", CompteDepotSerializer(many=True))},
#         tags=["compte dépôt"],  
#     )
#     def get(self, request):
#         role = _user_role(request.user)
#         if role not in ["admin", "manager", "vendor"]:
#             return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

#         comptes = CompteDepot.objects.select_related("client", "created_by").order_by("-created_at")
#         return Response(CompteDepotSerializer(comptes, many=True).data, status=status.HTTP_200_OK)


# =========================================================
# CREATE OR DEPOSIT
# =========================================================
class CreateOrDepotCompteView(APIView):
    permission_classes = [IsAuthenticated]
    ALLOWED_ROLES = {"manager", "cashier"}

    @swagger_auto_schema(
        operation_description=(
            "Créer un client et un compte dépôt si nécessaire. "
            "Si le client possède déjà un compte via son téléphone, "
            "effectuer directement un dépôt sur le compte existant."
        ),
        tags=["compte dépôt"],  
        request_body=CreateOrDepotCompteSerializer,
    )
    @transaction.atomic
    def post(self, request):
        role = _user_role(request.user)
        if role not in ALLOWED_ROLES:
            return Response(
                {"message": "Access Denied"},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = CreateOrDepotCompteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        client_data = serializer.validated_data["client"]
        telephone = client_data.get("telephone")
        montant = serializer.validated_data["montant"]

        minimum_depot = Decimal(str(getattr(settings, "COMPTE_DEPOT_DEPOT_MINIMUM", 5000)))
        if montant < minimum_depot:
            return Response(
                {"detail": f"Le montant minimum du dépôt est {minimum_depot} FCFA."},
                status=status.HTTP_400_BAD_REQUEST
            )

        client = ClientDepot.objects.filter(telephone=telephone).first()

        user_bijouterie = resolve_bijouterie_for_user(request.user)

        if not user_bijouterie:
            return Response(
                {"detail": "Aucune bijouterie associée à cet utilisateur."},
                status=status.HTTP_403_FORBIDDEN
            )

        if client and not user_can_access_bijouterie(
            request.user,
            client.bijouterie
        ):
            return Response(
                {"detail": "Ce compte appartient à une autre bijouterie."},
                status=status.HTTP_403_FORBIDDEN
            )

        # CAS 1 : client existe déjà
        if client:
            compte = CompteDepot.objects.filter(client=client).first()

            # CAS 1A : compte existant => dépôt direct
            if compte:
                tx = effectuer_depot(
                    compte_id=compte.id,
                    montant=montant,
                    user=request.user,
                    reference="DEPOT_COMPTE_EXISTANT",
                    commentaire="Dépôt effectué sur compte existant via téléphone client."
                )
                compte.refresh_from_db()

                return Response({
                    "message": "Compte existant détecté, dépôt effectué avec succès.",
                    "operation_type": "deposit_existing_account",
                    "client": ClientDepotSerializer(client).data,
                    "compte": {
                        "id": compte.id,
                        "numero_compte": compte.numero_compte,
                        "solde": str(compte.solde),
                        "created_at": compte.created_at,
                    },
                    "transaction": CompteDepotTransactionSerializer(tx).data,
                    "receipt_url": request.build_absolute_uri(
                        f"/api/compte-depot/transactions/{tx.id}/receipt/80mm/"
                    ),
                }, status=status.HTTP_200_OK)

            # CAS 1B : client existe sans compte => création compte + dépôt
            numero = self.generer_numero_compte(telephone)
            compte = CompteDepot.objects.create(
                client=client,
                numero_compte=numero,
                created_by=request.user,
                solde=0,
            )

            tx = effectuer_depot(
                compte_id=compte.id,
                montant=montant,
                user=request.user,
                reference="OUVERTURE_COMPTE_CLIENT_EXISTANT",
                commentaire="Nouveau compte créé puis crédité pour un client existant."
            )
            # Client existant sans compte
            send_compte_created_notification(
                compte,
                montant
            )
            
            compte.refresh_from_db()

            return Response({
                "message": "Nouveau compte créé puis crédité avec succès.",
                "operation_type": "create_account_and_deposit",
                "client": ClientDepotSerializer(client).data,
                "compte": {
                    "id": compte.id,
                    "numero_compte": compte.numero_compte,
                    "solde": str(compte.solde),
                    "created_at": compte.created_at,
                },
                "transaction": CompteDepotTransactionSerializer(tx).data,
                "receipt_url": request.build_absolute_uri(
                    f"/api/compte-depot/transactions/{tx.id}/receipt/80mm/"
                ),
            }, status=status.HTTP_201_CREATED)

        # CAS 2 : client inexistant => création client + compte + dépôt
        client = ClientDepot.objects.create(
            **client_data,
            bijouterie=user_bijouterie
        )

        numero = self.generer_numero_compte(telephone)
        compte = CompteDepot.objects.create(
            client=client,
            numero_compte=numero,
            created_by=request.user,
            solde=0,
        )

        tx = effectuer_depot(
            compte_id=compte.id,
            montant=montant,
            user=request.user,
            reference="OUVERTURE_NOUVEAU_COMPTE",
            commentaire="Nouveau client créé, compte ouvert et crédité."
        )
        # Nouveau client + nouveau compte
        send_compte_created_notification(compte, montant)
        compte.refresh_from_db()

        return Response({
            "message": "Nouveau client créé, compte ouvert et crédité avec succès.",
            "operation_type": "create_client_account_and_deposit",
            "client": ClientDepotSerializer(client).data,
            "compte": {
                "id": compte.id,
                "numero_compte": compte.numero_compte,
                "solde": str(compte.solde),
                "created_at": compte.created_at,
            },
            "transaction": CompteDepotTransactionSerializer(tx).data,
            "receipt_url": request.build_absolute_uri(
                f"/api/compte-depot/transactions/{tx.id}/receipt/80mm/"
            ),
        }, status=status.HTTP_201_CREATED)

    def generer_numero_compte(self, telephone):
        date_str = timezone.now().strftime("%y%m")
        prefix = f"{telephone}-{date_str}"[:25]

        if not CompteDepot.objects.filter(numero_compte=prefix).exists():
            return prefix

        for _ in range(10):
            suffix = uuid.uuid4().hex[:4].upper()
            numero = f"{prefix}-{suffix}"
            if not CompteDepot.objects.filter(numero_compte=numero).exists():
                return numero

        raise Exception("Impossible de générer un numéro de compte unique.")


# =========================================================
# DEPOT
# =========================================================
# class DepotView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Effectuer un dépôt sur un compte dépôt",
#         operation_description="Effectue un dépôt sur un compte existant à partir de son numéro de compte.",
#         request_body=CompteDepotTransactionCreateSerializer,
#         responses={
#             201: openapi.Response(
#                 description="Dépôt effectué avec succès"
#             ),
#             400: openapi.Response(
#                 description="Données invalides"
#             ),
#             403: openapi.Response(
#                 description="Accès refusé"
#             ),
#             404: openapi.Response(
#                 description="Compte introuvable"
#             ),
#         },
#         tags=["compte dépôt"],  
#     )
#     @transaction.atomic
#     def post(self, request, numero_compte):
#         role = _user_role(request.user)
#         if role not in ALLOWED_ROLES:
#             return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

#         try:
#             compte = CompteDepot.objects.select_for_update().get(numero_compte=numero_compte)
#         except CompteDepot.DoesNotExist:
#             return Response({"detail": "Compte introuvable."}, status=status.HTTP_404_NOT_FOUND)

#         serializer = CompteDepotTransactionCreateSerializer(data=request.data)
#         serializer.is_valid(raise_exception=True)

#         tx = effectuer_depot(
#             compte_id=compte.id,
#             montant=serializer.validated_data["montant"],
#             user=request.user,
#             reference=serializer.validated_data.get("reference"),
#             commentaire=serializer.validated_data.get("commentaire"),
#         )
#         compte.refresh_from_db()

#         return Response({
#             "message": "Dépôt effectué avec succès.",
#             "transaction": CompteDepotTransactionSerializer(tx).data,
#             "nouveau_solde": str(compte.solde),
#             "receipt_url": request.build_absolute_uri(
#                 f"/api/compte-depot/transactions/{tx.id}/receipt/80mm/"
#             ),
#         }, status=status.HTTP_201_CREATED)
class DepotView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Effectuer un dépôt sur un compte dépôt",
        operation_description="""
        Effectue un dépôt sur un compte dépôt via téléphone client.

        Règles :
        - Manager : uniquement ses bijouteries
        - Caissier : uniquement sa bijouterie
        - Admin : non autorisé
        - Vendeur : non autorisé
        """,
        request_body=CompteDepotTelephoneTransactionSerializer,
        responses={
            201: openapi.Response(description="Dépôt effectué avec succès"),
            400: openapi.Response(description="Données invalides"),
            403: openapi.Response(description="Accès refusé"),
            404: openapi.Response(description="Compte introuvable"),
        },
        tags=["compte dépôt"],
    )
    @transaction.atomic
    def post(self, request):
        role = _user_role(request.user)

        if role not in ["manager", "cashier"]:
            return Response(
                {"message": "Seul le manager ou le caissier peut effectuer un dépôt."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = CompteDepotTelephoneTransactionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        telephone = serializer.validated_data["telephone"]

        try:
            compte = (
                CompteDepot.objects
                .select_for_update()
                .select_related("client")
                .get(client__telephone=telephone)
            )
        except CompteDepot.DoesNotExist:
            return Response(
                {"detail": "Compte introuvable."},
                status=status.HTTP_404_NOT_FOUND
            )

        client_bijouterie = getattr(compte.client, "bijouterie", None)

        if not client_bijouterie:
            return Response(
                {"message": "Ce compte dépôt n'est lié à aucune bijouterie."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not user_can_access_bijouterie(request.user, client_bijouterie):
            return Response(
                {"message": "Vous ne pouvez effectuer un dépôt que dans votre bijouterie."},
                status=status.HTTP_403_FORBIDDEN
            )

        tx = effectuer_depot(
            compte_id=compte.id,
            montant=serializer.validated_data["montant"],
            user=request.user,
            reference=serializer.validated_data.get("reference"),
            commentaire=serializer.validated_data.get("commentaire"),
        )
        
        send_compte_depot_notification(tx)

        compte.refresh_from_db()

        return Response({
            "message": "Dépôt effectué avec succès.",
            "client": {
                "nom": compte.client.nom,
                "prenom": compte.client.prenom,
                "telephone": compte.client.telephone,
            },
            "transaction": CompteDepotTransactionSerializer(tx).data,
            "compte": {
                "numero_compte": compte.numero_compte,
                "nouveau_solde": str(compte.solde),
            },
            "receipt_url": request.build_absolute_uri(
                f"/api/compte-depot/transactions/{tx.id}/receipt/80mm/"
            ),
        }, status=status.HTTP_201_CREATED)
# =========================================================
# RETRAIT
# =========================================================
class RetraitView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Effectuer un retrait sur un compte dépôt",
        operation_description="""
        Effectue un retrait sur un compte dépôt via téléphone client.

        Règles :
        - Manager : uniquement ses bijouteries
        - Caissier : uniquement sa bijouterie
        - Admin : non autorisé
        - Vendeur : non autorisé
        """,
        request_body=CompteDepotTelephoneTransactionSerializer,
        responses={
            201: openapi.Response(description="Retrait effectué avec succès"),
            400: openapi.Response(description="Données invalides"),
            403: openapi.Response(description="Accès refusé"),
            404: openapi.Response(description="Compte introuvable"),
        },
        tags=["compte dépôt"],
    )
    @transaction.atomic
    def post(self, request):
        role = _user_role(request.user)

        if role not in ["manager", "cashier"]:
            return Response(
                {"message": "Seul le manager ou le caissier peut effectuer un retrait."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = CompteDepotTelephoneTransactionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        telephone = serializer.validated_data["telephone"]

        try:
            compte = (
                CompteDepot.objects
                .select_for_update()
                .select_related("client")
                .get(client__telephone=telephone)
            )
        except CompteDepot.DoesNotExist:
            return Response(
                {"detail": "Compte introuvable."},
                status=status.HTTP_404_NOT_FOUND
            )

        client_bijouterie = getattr(compte.client, "bijouterie", None)

        if not client_bijouterie:
            return Response(
                {"message": "Ce compte dépôt n'est lié à aucune bijouterie."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not user_can_access_bijouterie(request.user, client_bijouterie):
            return Response(
                {"message": "Vous ne pouvez effectuer un retrait que dans votre bijouterie."},
                status=status.HTTP_403_FORBIDDEN
            )

        tx = effectuer_retrait(
            compte_id=compte.id,
            montant=serializer.validated_data["montant"],
            user=request.user,
            reference=serializer.validated_data.get("reference"),
            commentaire=serializer.validated_data.get("commentaire"),
        )
        
        send_compte_depot_notification(tx)

        compte.refresh_from_db()

        return Response({
            "message": "Retrait effectué avec succès.",
            "client": {
                "nom": compte.client.nom,
                "prenom": compte.client.prenom,
                "telephone": compte.client.telephone,
            },
            "transaction": CompteDepotTransactionSerializer(tx).data,
            "compte": {
                "numero_compte": compte.numero_compte,
                "nouveau_solde": str(compte.solde),
            },
            "receipt_url": request.build_absolute_uri(
                f"/api/compte-depot/transactions/{tx.id}/receipt/80mm/"
            ),
        }, status=status.HTTP_201_CREATED)
        
# =========================================================
# SOLDE
# =========================================================
class GetSoldeAPIView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [UserRenderer]

    @swagger_auto_schema(
        operation_description="""
        Récupérer le solde d’un compte dépôt.

        Règles :
        - Vendor : uniquement sa bijouterie
        - Manager : uniquement ses bijouteries
        - Caissier : uniquement sa bijouterie
        - Admin : non autorisé
        """,
        manual_parameters=[
            openapi.Parameter(
                "telephone",
                openapi.IN_QUERY,
                description="Numéro de téléphone du client lié au compte dépôt",
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        tags=["compte dépôt"],
    )
    def get(self, request):
        role = _user_role(request.user)

        if role not in ["vendor", "manager", "cashier"]:
            return Response(
                {"message": "Accès refusé."},
                status=status.HTTP_403_FORBIDDEN
            )

        telephone = request.query_params.get("telephone")

        if not telephone:
            return Response(
                {"detail": "Le paramètre 'telephone' est requis."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            compte = (
                CompteDepot.objects
                .select_related("client")
                .get(client__telephone=telephone)
            )
        except CompteDepot.DoesNotExist:
            return Response(
                {"detail": "Compte non trouvé."},
                status=status.HTTP_404_NOT_FOUND
            )

        client_bijouterie = getattr(compte.client, "bijouterie", None)

        if not client_bijouterie:
            return Response(
                {"detail": "Ce compte n'est lié à aucune bijouterie."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not user_can_access_bijouterie(request.user, client_bijouterie):
            return Response(
                {"detail": "Vous ne pouvez consulter que les comptes de votre bijouterie."},
                status=status.HTTP_403_FORBIDDEN
            )

        return Response({
            "client": {
                "nom": compte.client.nom,
                "prenom": compte.client.prenom,
                "telephone": compte.client.telephone,
            },
            "compte": {
                "numero_compte": compte.numero_compte,
                "solde": str(compte.solde),
                "created_at": compte.created_at,
            }
        }, status=status.HTTP_200_OK)

# =========================================================
# LISTE COMPTES AVEC FILTRE
# =========================================================
class ListerTousComptesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="""
        Lister les comptes dépôt.

        Règles :
        - Vendor : uniquement sa bijouterie
        - Manager : uniquement ses bijouteries
        - Caissier : uniquement sa bijouterie
        - Admin : non autorisé
        """,
        manual_parameters=[
            openapi.Parameter(
                "telephone",
                openapi.IN_QUERY,
                description="Numéro de téléphone partiel ou complet",
                type=openapi.TYPE_STRING,
                required=False
            )
        ],
        tags=["compte dépôt"],
        responses={
            200: openapi.Response(
                "Liste des comptes",
                CompteDepotSerializer(many=True)
            )
        }
    )
    def get(self, request):
        role = _user_role(request.user)

        if role not in ["vendor", "manager", "cashier"]:
            return Response(
                {"message": "Access Denied"},
                status=status.HTTP_403_FORBIDDEN
            )

        telephone = request.query_params.get("telephone")

        comptes = (
            CompteDepot.objects
            .select_related("client", "created_by")
        )

        # =========================
        # FILTRE BIJOUTERIE
        # =========================

        if role == "vendor":
            vendor_profile = getattr(request.user, "staff_vendor_profile", None)

            if not vendor_profile or not vendor_profile.bijouterie:
                return Response(
                    {"detail": "Bijouterie vendeur introuvable."},
                    status=status.HTTP_403_FORBIDDEN
                )

            comptes = comptes.filter(
                client__bijouterie=vendor_profile.bijouterie
            )

        elif role == "cashier":
            cashier_profile = getattr(request.user, "staff_cashier_profile", None)

            if not cashier_profile or not cashier_profile.bijouterie:
                return Response(
                    {"detail": "Bijouterie caissier introuvable."},
                    status=status.HTTP_403_FORBIDDEN
                )

            comptes = comptes.filter(
                client__bijouterie=cashier_profile.bijouterie
            )

        elif role == "manager":
            manager_profile = getattr(request.user, "staff_manager_profile", None)

            if not manager_profile:
                return Response(
                    {"detail": "Profil manager introuvable."},
                    status=status.HTTP_403_FORBIDDEN
                )

            comptes = comptes.filter(
                client__bijouterie__in=manager_profile.bijouteries.all()
            )

        # =========================
        # FILTRE TELEPHONE
        # =========================

        if telephone:
            comptes = comptes.filter(
                client__telephone__icontains=telephone
            )

        serializer = CompteDepotSerializer(
            comptes.order_by("-created_at"),
            many=True
        )

        return Response(serializer.data, status=status.HTTP_200_OK)

# =========================================================
# LISTE TRANSACTIONS
# =========================================================
class ListerToutesCompteDepotTransactionsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Lister toutes les transactions. Filtres possibles : téléphone, numéro compte, type, statut, dates.",
        manual_parameters=[
            openapi.Parameter("telephone", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=False),
            openapi.Parameter("numero_compte", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=False),
            openapi.Parameter("type_transaction", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=False),
            openapi.Parameter("statut", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=False),
            openapi.Parameter("start_date", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE, required=False),
            openapi.Parameter("end_date", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE, required=False),
        ],
        tags=["compte dépôt"],
        responses={200: openapi.Response("Liste des transactions", CompteDepotTransactionSerializer(many=True))}
    )
    def get(self, request):
        role = _user_role(request.user)
        if role not in ["admin", "manager", "cashier"]:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        telephone = request.query_params.get("telephone")
        numero_compte = request.query_params.get("numero_compte")
        type_transaction = request.query_params.get("type_transaction")
        statut = request.query_params.get("statut")
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        qs = CompteDepotTransaction.objects.select_related("compte__client", "user").order_by("-date_transaction")

        # ✅ Scope par bijouterie
        if role == "manager":
            manager = getattr(request.user, "staff_manager_profile", None)

            if not manager:
                return Response(
                    {"detail": "Profil manager introuvable."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            qs = qs.filter(
                compte__client__bijouterie__in=manager.bijouteries.all()
            )

        elif role == "cashier":
            cashier = getattr(request.user, "staff_cashier_profile", None)

            if not cashier or not cashier.bijouterie:
                return Response(
                    {"detail": "Profil caissier invalide."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            qs = qs.filter(
                compte__client__bijouterie=cashier.bijouterie
            )

        if telephone:
            qs = qs.filter(compte__client__telephone__icontains=telephone)
        if numero_compte:
            qs = qs.filter(compte__numero_compte__icontains=numero_compte)
        if type_transaction:
            qs = qs.filter(type_transaction=type_transaction)
        if statut:
            qs = qs.filter(statut=statut)
        if start_date:
            qs = qs.filter(date_transaction__date__gte=start_date)
        if end_date:
            qs = qs.filter(date_transaction__date__lte=end_date)

        serializer = CompteDepotTransactionSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


# =========================================================
# EXPORT EXCEL TRANSACTIONS
# =========================================================

# historique mouvements
class ExportCompteDepotTransactionsExcelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Exporter les transactions compte dépôt en Excel. Filtres possibles : téléphone, numéro compte, type, statut, dates.",
        manual_parameters=[
            openapi.Parameter("telephone", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=False),
            openapi.Parameter("numero_compte", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=False),
            openapi.Parameter("type_transaction", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=False),
            openapi.Parameter("statut", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=False),
            openapi.Parameter("start_date", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE, required=False),
            openapi.Parameter("end_date", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE, required=False),
        ],
        tags=["compte dépôt"],  
    )
    def get(self, request):
        role = _user_role(request.user)
        if role not in ["admin", "manager", "cashier"]:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        telephone = request.query_params.get("telephone")
        numero_compte = request.query_params.get("numero_compte")
        type_transaction = request.query_params.get("type_transaction")
        statut = request.query_params.get("statut")
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        qs = CompteDepotTransaction.objects.select_related("compte__client", "user").order_by("-date_transaction")

        if telephone:
            qs = qs.filter(compte__client__telephone__icontains=telephone)
        if numero_compte:
            qs = qs.filter(compte__numero_compte__icontains=numero_compte)
        if type_transaction:
            qs = qs.filter(type_transaction=type_transaction)
        if statut:
            qs = qs.filter(statut=statut)
        if start_date:
            qs = qs.filter(date_transaction__date__gte=start_date)
        if end_date:
            qs = qs.filter(date_transaction__date__lte=end_date)

        wb = Workbook()
        ws = wb.active
        ws.title = "Transactions Compte Depot"

        headers = [
            "Date",
            "Type",
            "Statut",
            "Numero compte",
            "Nom",
            "Prenom",
            "Telephone",
            "Montant",
            "Solde avant",
            "Solde apres",
            "Reference",
            "Commentaire",
            "Utilisateur",
        ]
        ws.append(headers)

        header_fill = PatternFill(fill_type="solid", fgColor="1F4E78")
        header_font = Font(bold=True, color="FFFFFF")

        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font

        for tx in qs:
            client = getattr(tx.compte, "client", None)
            user_label = ""
            if tx.user:
                user_label = getattr(tx.user, "email", None) or getattr(tx.user, "username", "") or str(tx.user)

            ws.append([
                timezone.localtime(tx.date_transaction).strftime("%Y-%m-%d %H:%M:%S") if tx.date_transaction else "",
                tx.get_type_transaction_display(),
                tx.get_statut_display(),
                tx.compte.numero_compte,
                getattr(client, "nom", "") if client else "",
                getattr(client, "prenom", "") if client else "",
                getattr(client, "telephone", "") if client else "",
                float(tx.montant),
                float(tx.solde_avant),
                float(tx.solde_apres),
                tx.reference or "",
                tx.commentaire or "",
                user_label,
            ])

        for column_cells in ws.columns:
            length = max(len(str(cell.value or "")) for cell in column_cells)
            ws.column_dimensions[column_cells[0].column_letter].width = min(length + 2, 40)

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        filename = f"transactions_compte_depot_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        wb.save(response)
        return response


# sauvegarde état des soldes actuels
class ExportCompteDepotSoldesExcelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Exporter la sauvegarde des soldes actuels des comptes dépôt.",
        tags=["compte dépôt"],
    )
    def get(self, request):
        role = _user_role(request.user)

        if role not in ["manager", "cashier"]:
            return Response(
                {"message": "Access Denied"},
                status=status.HTTP_403_FORBIDDEN
            )

        comptes = CompteDepot.objects.select_related(
            "client",
            "client__bijouterie",
            "created_by",
        ).order_by("client__bijouterie__nom", "client__nom")

        if role == "cashier":
            cashier_profile = getattr(request.user, "staff_cashier_profile", None)
            if not cashier_profile or not cashier_profile.bijouterie:
                return Response({"detail": "Bijouterie caissier introuvable."}, status=403)

            comptes = comptes.filter(client__bijouterie=cashier_profile.bijouterie)

        if role == "manager":
            manager_profile = getattr(request.user, "staff_manager_profile", None)
            if not manager_profile:
                return Response({"detail": "Profil manager introuvable."}, status=403)

            comptes = comptes.filter(client__bijouterie__in=manager_profile.bijouteries.all())

        wb = Workbook()
        ws = wb.active
        ws.title = "Soldes Comptes Depot"

        headers = [
            "Date sauvegarde",
            "Bijouterie",
            "Nom",
            "Prénom",
            "Téléphone",
            "Numéro compte",
            "Solde actuel",
            "Date création compte",
            "Créé par",
        ]
        ws.append(headers)

        header_fill = PatternFill(fill_type="solid", fgColor="1F4E78")
        header_font = Font(bold=True, color="FFFFFF")

        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font

        now = timezone.localtime(timezone.now())

        for compte in comptes:
            client = compte.client
            bijouterie = getattr(client, "bijouterie", None)

            created_by = ""
            if compte.created_by:
                created_by = (
                    getattr(compte.created_by, "email", None)
                    or getattr(compte.created_by, "username", "")
                    or str(compte.created_by)
                )

            ws.append([
                now.strftime("%Y-%m-%d %H:%M:%S"),
                getattr(bijouterie, "nom", "") if bijouterie else "",
                getattr(client, "nom", "") if client else "",
                getattr(client, "prenom", "") if client else "",
                getattr(client, "telephone", "") if client else "",
                compte.numero_compte,
                float(compte.solde),
                timezone.localtime(compte.created_at).strftime("%Y-%m-%d %H:%M:%S") if compte.created_at else "",
                created_by,
            ])

        for column_cells in ws.columns:
            length = max(len(str(cell.value or "")) for cell in column_cells)
            ws.column_dimensions[column_cells[0].column_letter].width = min(length + 2, 45)

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        filename = f"sauvegarde_soldes_compte_depot_{now.strftime('%Y_%m_%d_%H%M%S')}.xlsx"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        wb.save(response)
        return response
# =========================================================
# DASHBOARD COMPTE DEPOT
# =========================================================
class CompteDepotDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Dashboard global des comptes dépôt.",
        manual_parameters=[
            openapi.Parameter("start_date", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE, required=False),
            openapi.Parameter("end_date", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE, required=False),
        ],
        tags=["compte dépôt"],  
    )
    def get(self, request):
        role = _user_role(request.user)
        if role not in ["admin", "manager", "cashier", "vendor"]:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        tx_qs = CompteDepotTransaction.objects.select_related("compte__client", "user")
        compte_qs = CompteDepot.objects.select_related("client")

        if start_date:
            tx_qs = tx_qs.filter(date_transaction__date__gte=start_date)
        if end_date:
            tx_qs = tx_qs.filter(date_transaction__date__lte=end_date)

        total_comptes = compte_qs.count()
        total_solde_global = compte_qs.aggregate(
            total=Coalesce(Sum("solde"), Decimal("0.00"))
        )["total"]

        total_depots = tx_qs.filter(
            type_transaction=CompteDepotTransaction.TYPE_DEPOT,
            statut=CompteDepotTransaction.STAT_TERMINE
        ).aggregate(total=Coalesce(Sum("montant"), Decimal("0.00")))["total"]

        total_retraits = tx_qs.filter(
            type_transaction=CompteDepotTransaction.TYPE_RETRAIT,
            statut=CompteDepotTransaction.STAT_TERMINE
        ).aggregate(total=Coalesce(Sum("montant"), Decimal("0.00")))["total"]

        nombre_transactions = tx_qs.count()

        top_comptes = compte_qs.order_by("-solde")[:10]
        top_comptes_data = []
        for compte in top_comptes:
            client = getattr(compte, "client", None)
            top_comptes_data.append({
                "numero_compte": compte.numero_compte,
                "solde": compte.solde,
                "client_nom": getattr(client, "nom", "") if client else "",
                "client_prenom": getattr(client, "prenom", "") if client else "",
                "telephone": getattr(client, "telephone", "") if client else "",
            })

        transactions_par_type = tx_qs.values("type_transaction").annotate(
            count=Count("id"),
            total=Coalesce(Sum("montant"), Decimal("0.00"))
        ).order_by("type_transaction")

        latest_transactions = tx_qs.order_by("-date_transaction")[:10]

        return Response({
            "periode": {
                "start_date": start_date,
                "end_date": end_date,
            },
            "kpis": {
                "total_comptes": total_comptes,
                "total_solde_global": total_solde_global,
                "total_depots": total_depots,
                "total_retraits": total_retraits,
                "nombre_transactions": nombre_transactions,
            },
            "transactions_par_type": list(transactions_par_type),
            "top_comptes": top_comptes_data,
            "dernieres_transactions": CompteDepotTransactionSerializer(latest_transactions, many=True).data,
        }, status=status.HTTP_200_OK)



# =========================================================
# RECU PDF 80MM
# =========================================================
class CompteDepotTransactionReceipt80mmPDFAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Reçu ticket 80mm d'une transaction compte dépôt",
        operation_description="Génère un reçu PDF thermique 80mm pour une transaction compte dépôt.",
        tags=["compte dépôt"],  
    )
    def get(self, request, transaction_id):
        role = _user_role(request.user)
        if role not in ["admin", "manager", "cashier", "vendor"]:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        try:
            tx = CompteDepotTransaction.objects.select_related(
                "compte__client",
                "user",
            ).get(pk=transaction_id)
        except CompteDepotTransaction.DoesNotExist:
            return Response(
                {"detail": "Transaction introuvable."},
                status=status.HTTP_404_NOT_FOUND
            )

        return generate_transaction_ticket_80mm_pdf(
            tx,
            organisation_name="BANQUE TAKAYE"
        )
        


