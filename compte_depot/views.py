# compte_depot/views.py

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.bijouteries import get_user_bijouteries
from backend.permissions import IsManagerOrCashier
from backend.renderers import UserRenderer
from backend.roles import (ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER, ROLE_VENDOR,
                           get_role_name)
from backend.utils.helpers import (resolve_bijouterie_for_user,
                                   user_can_access_bijouterie)
from compte_depot.models import CompteDepot, CompteDepotTransaction
from compte_depot.notifications import (send_compte_created_notification,
                                        send_compte_depot_notification)
from sale.models import Client

from .models import ClientDepot, CompteDepot, CompteDepotTransaction
from .pdf import generate_transaction_ticket_80mm_pdf
from .serializers import (ClientDepotSerializer, CompteDepotSerializer,
                          CompteDepotTelephoneTransactionSerializer,
                          CompteDepotTransactionSerializer,
                          CreateOrDepotCompteSerializer)
from .services.depot_retrait_services import effectuer_depot, effectuer_retrait

# ============================================================
# RATTACHER UN CLIENT COMMERCIAL À CLIENTDEPOT
# ============================================================

def creer_profil_depot_client_existant(
    client,
    bijouterie,
):
    """
    Crée uniquement la ligne enfant ClientDepot.

    Le client commercial existe déjà dans sale.Client.

    Ne modifie jamais :
    - son nom
    - son prénom
    - son téléphone
    - sa CNI
    - son utilisateur
    - son historique commercial

    À appeler dans transaction.atomic(), après avoir
    verrouillé le client parent.
    """

    profil = ClientDepot.objects.filter(
        pk=client.pk
    ).first()

    if profil:
        return profil

    parent_link = ClientDepot._meta.get_ancestor_link(
        Client
    )

    table = connection.ops.quote_name(
        ClientDepot._meta.db_table
    )

    parent_col = connection.ops.quote_name(
        parent_link.column
    )

    bijouterie_col = connection.ops.quote_name(
        ClientDepot._meta.get_field(
            "bijouterie"
        ).column
    )

    photo_field = ClientDepot._meta.get_field("photo")

    photo_col = connection.ops.quote_name(
        photo_field.column
    )

    photo_default = photo_field.get_default()

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {table}
                (
                    {parent_col},
                    {bijouterie_col},
                    {photo_col}
                )
            VALUES (%s, %s, %s)
            """,
            [
                client.pk,
                bijouterie.pk,
                photo_default,
            ],
        )

    return ClientDepot.objects.get(
        pk=client.pk
    )
    
    

# ============================================================
# rechercher un compte dépôt par téléphone
# ==========================================================

class ClientRechercheDepotAPIView(APIView):

    permission_classes = [
        IsAuthenticated,
        IsManagerOrCashier,
    ]

    @swagger_auto_schema(
        operation_summary="Rechercher un client pour un dépôt",
        operation_description=(
            "Réservé au manager et au caissier. "
            "Recherche un client par téléphone et indique "
            "s'il possède déjà un compte dépôt."
        ),
        manual_parameters=[
            openapi.Parameter(
                name="telephone",
                in_=openapi.IN_QUERY,
                description="Téléphone du client",
                type=openapi.TYPE_STRING,
                required=True,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Résultat de la recherche",
                examples={
                    "application/json": {
                        "client_existe": True,
                        "compte_existe": True,
                        "client": {
                            "id": 15,
                            "nom": "Diop",
                            "prenom": "Mamadou",
                            "telephone": "771234567",
                        },
                        "compte": {
                            "numero_compte": "CD-000123",
                            "solde": "150000.00",
                        },
                    }
                },
            ),
            400: "Téléphone obligatoire",
            401: "Authentification requise",
            403: "Accès interdit",
        },
        tags=["Compte dépôt"],
    )
    def get(self, request):

        telephone = (
            request.query_params.get("telephone") or ""
        ).strip()

        if not telephone:
            return Response(
                {
                    "detail": "Le téléphone est obligatoire."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        client = Client.objects.filter(
            telephone=telephone
        ).first()

        if client is None:
            return Response({
                "client_existe": False,
                "compte_existe": False,
                "client": None,
                "compte": None,
            })

        client_data = {
            "id": client.pk,
            "nom": client.nom,
            "prenom": client.prenom,
            "telephone": client.telephone,
        }

        profil = ClientDepot.objects.filter(
            pk=client.pk
        ).first()

        if profil is None:
            return Response({
                "client_existe": True,
                "compte_existe": False,
                "client": client_data,
                "compte": None,
            })

        compte = CompteDepot.objects.filter(
            client=profil
        ).first()

        return Response({
            "client_existe": True,
            "compte_existe": compte is not None,
            "client": client_data,
            "compte": (
                {
                    "numero_compte": compte.numero_compte,
                    "solde": str(compte.solde),
                }
                if compte else None
            ),
        })


# ============================================================
# CRÉER OU ALIMENTER UN COMPTE DÉPÔT
# ============================================================

class CreateOrDepotCompteView(APIView):

    permission_classes = [
        IsAuthenticated,
        IsManagerOrCashier,
    ]

    ALLOWED_ROLES = {
        ROLE_ADMIN,
        ROLE_MANAGER,
        ROLE_CASHIER,
    }

    @swagger_auto_schema(
        operation_id="createOrDepotCompte",
        operation_summary=(
            "Créer ou alimenter un compte dépôt"
        ),
        operation_description=(
            "Crée un compte dépôt ou alimente un compte "
            "existant.\n\n"
            "Un client commercial déjà enregistré est "
            "réutilisé sans doublon.\n\n"
            "Admin et manager : bijouterie_id obligatoire.\n"
            "Caissier : bijouterie automatique.\n"
            "Vendeur et acheteur : non autorisés."
        ),
        request_body=CreateOrDepotCompteSerializer,
        responses={
            200: openapi.Response(
                description="Dépôt sur compte existant."
            ),
            201: openapi.Response(
                description="Compte créé et crédité."
            ),
            400: "Données invalides.",
            403: "Accès refusé.",
        },
        tags=["compte dépôt"],
    )
    @transaction.atomic
    def post(self, request):

        # ====================================================
        # 1. RÔLE
        # ====================================================

        role = get_role_name(request.user)

        if role not in self.ALLOWED_ROLES:
            return Response(
                {"detail": "Accès refusé."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # ====================================================
        # 2. VALIDATION
        # ====================================================

        serializer = CreateOrDepotCompteSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        client_data = serializer.validated_data["client"]
        montant = serializer.validated_data["montant"]
        telephone = client_data["telephone"]

        bijouterie_id = serializer.validated_data.get(
            "bijouterie_id"
        )

        # ====================================================
        # 3. BIJOUTERIE AUTORISÉE
        # ====================================================

        bijouteries = get_user_bijouteries(
            request.user
        )

        if role == ROLE_CASHIER:

            user_bijouterie = bijouteries.first()

            if not user_bijouterie:
                return Response(
                    {
                        "detail": (
                            "Aucune bijouterie associée "
                            "au caissier."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        else:

            if not bijouterie_id:
                raise ValidationError({
                    "bijouterie_id": (
                        "Ce champ est obligatoire pour "
                        "l'admin et le manager."
                    )
                })

            user_bijouterie = (
                bijouteries
                .filter(pk=bijouterie_id)
                .first()
            )

            if not user_bijouterie:
                return Response(
                    {
                        "detail": (
                            "Bijouterie introuvable "
                            "ou accès refusé."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        # ====================================================
        # 4. RECHERCHER D'ABORD DANS CLIENT
        # ====================================================

        client_base = (
            Client.objects
            .select_for_update()
            .filter(telephone=telephone)
            .first()
        )

        nouveau_client = False
        nouveau_profil = False

        # ====================================================
        # 5. CLIENT COMMERCIAL EXISTANT
        # ====================================================

        if client_base:

            client_depot = (
                ClientDepot.objects
                .filter(pk=client_base.pk)
                .first()
            )

            if client_depot is None:

                client_depot = (
                    creer_profil_depot_client_existant(
                        client=client_base,
                        bijouterie=user_bijouterie,
                    )
                )

                nouveau_profil = True

        # ====================================================
        # 6. CLIENT TOTALEMENT NOUVEAU
        # ====================================================

        else:

            client_depot = ClientDepot.objects.create(
                **client_data,
                bijouterie=user_bijouterie,
            )

            nouveau_client = True
            nouveau_profil = True

        # ====================================================
        # 7. VÉRIFIER LA BIJOUTERIE DU PROFIL
        # ====================================================

        if client_depot.bijouterie_id is None:

            # Ne pas rattacher automatiquement un profil
            # existant sans connaître son historique.
            if not nouveau_profil:
                return Response(
                    {
                        "detail": (
                            "Le profil dépôt existe, "
                            "mais aucune bijouterie "
                            "ne lui est associée."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        elif (
            client_depot.bijouterie_id
            != user_bijouterie.pk
        ):

            return Response(
                {
                    "detail": (
                        "Ce profil dépôt appartient "
                        "à une autre bijouterie."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # ====================================================
        # 8. RECHERCHER LE COMPTE DÉPÔT
        # ====================================================

        compte = (
            CompteDepot.objects
            .select_for_update()
            .filter(client=client_depot)
            .first()
        )

        # ====================================================
        # 9. COMPTE EXISTANT : DÉPÔT
        # ====================================================

        if compte:

            tx = effectuer_depot(
                compte_id=compte.pk,
                montant=montant,
                user=request.user,
                reference="DEPOT_COMPTE_EXISTANT",
                commentaire=(
                    "Dépôt sur compte existant."
                ),
            )

            operation_type = "deposit_existing_account"

            message = (
                "Compte existant détecté, "
                "dépôt effectué avec succès."
            )

            http_status = status.HTTP_200_OK

            transaction.on_commit(
                lambda tx=tx: (
                    send_compte_depot_notification(tx)
                )
            )

        # ====================================================
        # 10. COMPTE INEXISTANT : OUVERTURE
        # ====================================================

        else:

            numero = self.generer_numero_compte(
                telephone
            )

            compte = CompteDepot.objects.create(
                client=client_depot,
                numero_compte=numero,
                created_by=request.user,
                solde=Decimal("0.00"),
            )

            tx = effectuer_depot(
                compte_id=compte.pk,
                montant=montant,
                user=request.user,
                reference="OUVERTURE_COMPTE",
                commentaire=(
                    "Ouverture et alimentation "
                    "du compte dépôt."
                ),
            )

            if nouveau_client:

                operation_type = (
                    "create_client_account_and_deposit"
                )

                message = (
                    "Nouveau client créé, "
                    "compte dépôt ouvert et crédité."
                )

            else:

                operation_type = (
                    "create_account_and_deposit"
                )

                message = (
                    "Client commercial existant "
                    "réutilisé, compte dépôt "
                    "ouvert et crédité."
                )

            http_status = status.HTTP_201_CREATED

            transaction.on_commit(
                lambda compte=compte, montant=montant: (
                    send_compte_created_notification(
                        compte,
                        montant,
                    )
                )
            )

        # ====================================================
        # 11. RÉPONSE
        # ====================================================

        return Response(
            {
                "message": message,

                "operation_type": operation_type,

                "client": ClientDepotSerializer(
                    client_depot
                ).data,

                "bijouterie": {
                    "id": user_bijouterie.pk,
                    "nom": user_bijouterie.nom,
                },

                "compte": {
                    "id": compte.pk,
                    "numero_compte": compte.numero_compte,
                    "solde": str(tx.solde_apres),
                    "created_at": compte.created_at,
                },

                "transaction": (
                    CompteDepotTransactionSerializer(
                        tx
                    ).data
                ),
            },
            status=http_status,
        )

    # ========================================================
    # 12. GÉNÉRATION NUMÉRO COMPTE
    # ========================================================

    def generer_numero_compte(self, telephone):

        date_str = timezone.localtime(
            timezone.now()
        ).strftime("%y%m")

        prefix = f"{telephone}-{date_str}"[:25]

        if not CompteDepot.objects.filter(
            numero_compte=prefix
        ).exists():
            return prefix

        for _ in range(10):

            suffix = uuid.uuid4().hex[:4].upper()

            numero = f"{prefix}-{suffix}"

            if not CompteDepot.objects.filter(
                numero_compte=numero
            ).exists():
                return numero

        raise ValidationError({
            "numero_compte": (
                "Impossible de générer "
                "un numéro de compte unique."
            )
        })


class DepotView(APIView):
    permission_classes = [
        IsAuthenticated,
        IsManagerOrCashier,
    ]

    @swagger_auto_schema(
        operation_id="depotCompteDepot",
        operation_summary="Effectuer un dépôt sur un compte dépôt",
        operation_description=(
            "Effectue un dépôt sur un compte dépôt via le téléphone du client.\n\n"
            "### Règles\n"
            "- Admin : toutes les bijouteries.\n"
            "- Manager : uniquement ses bijouteries.\n"
            "- Caissier : uniquement sa bijouterie.\n"
            "- Vendor : non autorisé.\n"
            "- Buyer : non autorisé."
        ),
        request_body=CompteDepotTelephoneTransactionSerializer,
        responses={
            201: openapi.Response(
                description="Dépôt effectué avec succès",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "message": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            example="Dépôt effectué avec succès.",
                        ),
                        "client": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "nom": openapi.Schema(
                                    type=openapi.TYPE_STRING
                                ),
                                "prenom": openapi.Schema(
                                    type=openapi.TYPE_STRING
                                ),
                                "telephone": openapi.Schema(
                                    type=openapi.TYPE_STRING
                                ),
                            },
                        ),
                        "bijouterie": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "id": openapi.Schema(
                                    type=openapi.TYPE_INTEGER
                                ),
                                "nom": openapi.Schema(
                                    type=openapi.TYPE_STRING
                                ),
                            },
                        ),
                        "transaction": openapi.Schema(
                            type=openapi.TYPE_OBJECT
                        ),
                        "compte": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "numero_compte": openapi.Schema(
                                    type=openapi.TYPE_STRING
                                ),
                                "nouveau_solde": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    example="60000.00",
                                ),
                            },
                        ),
                        "receipt_url": openapi.Schema(
                            type=openapi.TYPE_STRING
                        ),
                    },
                ),
            ),
            400: openapi.Response(
                description="Données invalides ou compte sans bijouterie"
            ),
            403: openapi.Response(
                description="Accès refusé ou bijouterie non autorisée"
            ),
            404: openapi.Response(
                description="Compte introuvable"
            ),
        },
        tags=["compte dépôt"],
    )
    @transaction.atomic
    def post(self, request):
        
        role = get_role_name(request.user)

        if role not in {
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_CASHIER,
        }:
            return Response(
                {
                    "message": (
                        "Seul l'admin, le manager ou le caissier "
                        "peut effectuer un dépôt."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CompteDepotTelephoneTransactionSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        telephone = serializer.validated_data["telephone"]

        try:
            compte = (
                CompteDepot.objects
                .select_for_update()
                .select_related(
                    "client",
                    "client__bijouterie",
                )
                .get(client__telephone=telephone)
            )
        except CompteDepot.DoesNotExist:
            return Response(
                {"detail": "Compte introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        client_bijouterie = getattr(
            compte.client,
            "bijouterie",
            None,
        )

        if not client_bijouterie:
            return Response(
                {
                    "message":
                    "Ce compte dépôt n'est lié à aucune bijouterie."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user_can_access_bijouterie(
            request.user,
            client_bijouterie,
        ):
            return Response(
                {
                    "message":
                    "Vous ne pouvez pas effectuer un dépôt "
                    "sur ce compte."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        tx = effectuer_depot(
            compte_id=compte.id,
            montant=serializer.validated_data["montant"],
            user=request.user,
        )

        transaction.on_commit(
            lambda tx=tx: send_compte_depot_notification(tx)
        )

        compte.refresh_from_db()

        return Response(
            {
                "message": "Dépôt effectué avec succès.",

                "client": {
                    "nom": compte.client.nom,
                    "prenom": compte.client.prenom,
                    "telephone": compte.client.telephone,
                },

                "bijouterie": {
                    "id": client_bijouterie.id,
                    "nom": client_bijouterie.nom,
                },

                "transaction":
                CompteDepotTransactionSerializer(tx).data,

                "compte": {
                    "numero_compte": compte.numero_compte,
                    "nouveau_solde": str(compte.solde),
                },

                "receipt_url":
                request.build_absolute_uri(
                    f"/api/compte-depot/transactions/"
                    f"{tx.id}/receipt/80mm/"
                ),
            },
            status=status.HTTP_201_CREATED,
        )


# =========================================================
# RETRAIT
# =========================================================
class RetraitView(APIView):
    permission_classes = [
        IsAuthenticated,
        IsManagerOrCashier,
    ]

    @swagger_auto_schema(
        operation_summary="Effectuer un retrait sur un compte dépôt",
        operation_description="""
        Effectue un retrait sur un compte dépôt via téléphone client.

        Règles :
        - Admin : toutes les bijouteries
        - Manager : uniquement ses bijouteries
        - Caissier : uniquement sa bijouterie
        - Vendor : non autorisé
        - Buyer : non autorisé
        """,
        request_body=CompteDepotTelephoneTransactionSerializer,
        responses={
            201: openapi.Response(
                description="Retrait effectué avec succès"
            ),
            400: openapi.Response(
                description="Données invalides"
            ),
            403: openapi.Response(
                description="Accès refusé"
            ),
            404: openapi.Response(
                description="Compte introuvable"
            ),
        },
        tags=["compte dépôt"],
    )
    @transaction.atomic
    def post(self, request):
        role = get_role_name(request.user)

        if role not in {
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_CASHIER,
        }:
            return Response(
                {
                    "message": (
                        "Seul l'admin, le manager ou le caissier "
                        "peut effectuer un retrait."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CompteDepotTelephoneTransactionSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        telephone = serializer.validated_data["telephone"]

        try:
            compte = (
                CompteDepot.objects
                .select_for_update()
                .select_related(
                    "client",
                    "client__bijouterie",
                )
                .get(client__telephone=telephone)
            )
        except CompteDepot.DoesNotExist:
            return Response(
                {"detail": "Compte introuvable."},
                status=status.HTTP_404_NOT_FOUND
            )

        client_bijouterie = getattr(
            compte.client,
            "bijouterie",
            None,
        )

        if not client_bijouterie:
            return Response(
                {
                    "message":
                    "Ce compte dépôt n'est lié à aucune bijouterie."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if not user_can_access_bijouterie(
            request.user,
            client_bijouterie
        ):
            return Response(
                {
                    "message":
                    "Vous ne pouvez pas effectuer un retrait "
                    "sur ce compte."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        tx = effectuer_retrait(
            compte_id=compte.id,
            montant=serializer.validated_data["montant"],
            user=request.user,
        )

        transaction.on_commit(
            lambda tx=tx: send_compte_depot_notification(tx)
        )

        compte.refresh_from_db()

        return Response(
            {
                "message": "Retrait effectué avec succès.",

                "client": {
                    "nom": compte.client.nom,
                    "prenom": compte.client.prenom,
                    "telephone": compte.client.telephone,
                },

                "bijouterie": {
                    "id": client_bijouterie.id,
                    "nom": client_bijouterie.nom,
                },

                "transaction":
                CompteDepotTransactionSerializer(tx).data,

                "compte": {
                    "numero_compte": compte.numero_compte,
                    "nouveau_solde": str(compte.solde),
                },

                "receipt_url":
                request.build_absolute_uri(
                    f"/api/compte-depot/transactions/"
                    f"{tx.id}/receipt/80mm/"
                ),
            },
            status=status.HTTP_201_CREATED
        )
        
# =========================================================
# SOLDE
# =========================================================
class GetSoldeAPIView(APIView):
    permission_classes = [
        IsAuthenticated,
        IsManagerOrCashier,
    ]
    renderer_classes = [UserRenderer]

    @swagger_auto_schema(
        operation_summary="Consulter le solde d’un compte dépôt",
        operation_description="""
        Récupérer le solde d’un compte dépôt via le téléphone du client.

        Règles :
        - Admin : tous les comptes
        - Manager : uniquement ses bijouteries
        - Caissier : uniquement sa bijouterie
        - Vendor : uniquement sa bijouterie
        """,
        manual_parameters=[
            openapi.Parameter(
                "telephone",
                openapi.IN_QUERY,
                description="Numéro de téléphone du client lié au compte dépôt",
                type=openapi.TYPE_STRING,
                required=True,
            )
        ],
        responses={
            200: openapi.Response(description="Solde récupéré avec succès"),
            400: openapi.Response(description="Paramètre invalide ou compte sans bijouterie"),
            403: openapi.Response(description="Accès refusé"),
            404: openapi.Response(description="Compte non trouvé"),
        },
        tags=["compte dépôt"],
    )
    def get(self, request):
        role = get_role_name(request.user)

        if role not in {
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_CASHIER,
            ROLE_VENDOR,
        }:
            return Response(
                {"message": "Accès refusé."},
                status=status.HTTP_403_FORBIDDEN,
            )

        telephone = request.query_params.get("telephone")

        if not telephone:
            return Response(
                {"detail": "Le paramètre 'telephone' est requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            compte = (
                CompteDepot.objects
                .select_related("client", "client__bijouterie")
                .get(client__telephone=telephone)
            )
        except CompteDepot.DoesNotExist:
            return Response(
                {"detail": "Compte non trouvé."},
                status=status.HTTP_404_NOT_FOUND,
            )

        client_bijouterie = getattr(
            compte.client,
            "bijouterie",
            None,
        )

        if not client_bijouterie:
            return Response(
                {"detail": "Ce compte n'est lié à aucune bijouterie."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user_can_access_bijouterie(
            request.user,
            client_bijouterie,
        ):
            return Response(
                {
                    "detail":
                    "Vous n'avez pas accès à la bijouterie de ce compte."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            {
                "client": {
                    "nom": compte.client.nom,
                    "prenom": compte.client.prenom,
                    "telephone": compte.client.telephone,
                },
                "bijouterie": {
                    "id": client_bijouterie.id,
                    "nom": client_bijouterie.nom,
                },
                "compte": {
                    "numero_compte": compte.numero_compte,
                    "solde": str(compte.solde),
                    "created_at": compte.created_at,
                },
            },
            status=status.HTTP_200_OK,
        )
        
# =========================================================
# LISTE COMPTES AVEC FILTRE
# =========================================================
class ListerTousComptesAPIView(APIView):
    permission_classes = [
        IsAuthenticated,
        IsManagerOrCashier,
    ]

    @swagger_auto_schema(
        operation_summary="Lister les comptes dépôt",
        operation_description="""
        Liste les comptes dépôt accessibles à l'utilisateur.

        Règles :
        - Admin : tous les comptes
        - Manager : uniquement ses bijouteries
        - Caissier : uniquement sa bijouterie
        - Vendor : uniquement sa bijouterie
        """,
        manual_parameters=[
            openapi.Parameter(
                "telephone",
                openapi.IN_QUERY,
                description="Numéro de téléphone partiel ou complet",
                type=openapi.TYPE_STRING,
                required=False,
            )
        ],
        responses={
            200: openapi.Response(
                "Liste des comptes",
                CompteDepotSerializer(many=True),
            ),
            403: openapi.Response(
                description="Accès refusé"
            ),
        },
        tags=["compte dépôt"],
    )
    def get(self, request):
        role = get_role_name(request.user)

        if role not in {
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_CASHIER,
            ROLE_VENDOR,
        }:
            return Response(
                {"message": "Accès refusé."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # ==========================================
        # BIJOUTERIES ACCESSIBLES
        # ==========================================

        bijouteries = get_user_bijouteries(request.user)

        if not bijouteries.exists():
            return Response(
                {
                    "detail":
                    "Aucune bijouterie accessible pour cet utilisateur."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # ==========================================
        # COMPTES ACCESSIBLES
        # ==========================================

        comptes = (
            CompteDepot.objects
            .select_related(
                "client",
                "client__bijouterie",
                "created_by",
            )
            .filter(
                client__bijouterie__in=bijouteries
            )
        )

        # ==========================================
        # FILTRE TELEPHONE
        # ==========================================

        telephone = request.query_params.get("telephone")

        if telephone:
            comptes = comptes.filter(
                client__telephone__icontains=telephone
            )

        comptes = comptes.order_by("-created_at")

        serializer = CompteDepotSerializer(
            comptes,
            many=True,
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
    
    
# =========================================================
# LISTE TRANSACTIONS
# =========================================================
class ListerToutesCompteDepotTransactionsAPIView(APIView):
    permission_classes = [IsAuthenticated, IsManagerOrCashier]

    @swagger_auto_schema(
        operation_summary="Lister les transactions compte dépôt",
        operation_description=(
            "Liste les transactions compte dépôt accessibles à l'utilisateur.\n\n"
            "### Règles\n"
            "- Admin : toutes les bijouteries.\n"
            "- Manager : uniquement ses bijouteries.\n"
            "- Caissier : uniquement sa bijouterie.\n"
        ),
        manual_parameters=[
            openapi.Parameter(
                "telephone",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "numero_compte",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "type_transaction",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "statut",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "start_date",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE,
                required=False,
            ),
            openapi.Parameter(
                "end_date",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE,
                required=False,
            ),
        ],
        responses={
            200: openapi.Response(
                "Liste des transactions",
                CompteDepotTransactionSerializer(many=True),
            ),
            403: openapi.Response(
                description="Accès refusé",
            ),
        },
        tags=["compte dépôt"],
    )
    def get(self, request):
        role = get_role_name(request.user)

        if role not in {
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_CASHIER,
        }:
            return Response(
                {"message": "Accès refusé."},
                status=status.HTTP_403_FORBIDDEN,
            )

        bijouteries = get_user_bijouteries(request.user)

        if not bijouteries.exists():
            return Response(
                {"detail": "Aucune bijouterie accessible."},
                status=status.HTTP_403_FORBIDDEN,
            )

        qs = (
            CompteDepotTransaction.objects
            .select_related(
                "compte",
                "compte__client",
                "compte__client__bijouterie",
                "user",
            )
            .filter(
                compte__client__bijouterie__in=bijouteries
            )
            .order_by("-date_transaction")
        )

        telephone = request.query_params.get("telephone")
        numero_compte = request.query_params.get("numero_compte")
        type_transaction = request.query_params.get("type_transaction")
        statut = request.query_params.get("statut")
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        if telephone:
            qs = qs.filter(
                compte__client__telephone__icontains=telephone
            )

        if numero_compte:
            qs = qs.filter(
                compte__numero_compte__icontains=numero_compte
            )

        if type_transaction:
            qs = qs.filter(
                type_transaction=type_transaction
            )

        if statut:
            qs = qs.filter(
                statut=statut
            )

        if start_date:
            qs = qs.filter(
                date_transaction__date__gte=start_date
            )

        if end_date:
            qs = qs.filter(
                date_transaction__date__lte=end_date
            )

        serializer = CompteDepotTransactionSerializer(
            qs,
            many=True,
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
        
# =========================================================
# EXPORT EXCEL TRANSACTIONS
# =========================================================

# historique mouvements
class ExportCompteDepotTransactionsExcelAPIView(APIView):
    permission_classes = [
        IsAuthenticated,
        IsManagerOrCashier,
    ]

    @swagger_auto_schema(
        operation_summary="Exporter les transactions compte dépôt en Excel",
        operation_description=(
            "Exporte les transactions compte dépôt accessibles à l'utilisateur.\n\n"
            "### Règles\n"
            "- Admin : toutes les bijouteries.\n"
            "- Manager : uniquement ses bijouteries.\n"
            "- Caissier : uniquement sa bijouterie.\n\n"
            "Filtres possibles : téléphone, numéro compte, type, statut, dates."
        ),
        manual_parameters=[
            openapi.Parameter(
                "telephone",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "numero_compte",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "type_transaction",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "statut",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "start_date",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE,
                required=False,
            ),
            openapi.Parameter(
                "end_date",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE,
                required=False,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Fichier Excel généré avec succès"
            ),
            403: openapi.Response(
                description="Accès refusé"
            ),
        },
        tags=["compte dépôt"],
    )
    def get(self, request):
        role = get_role_name(request.user)

        if role not in {
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_CASHIER,
        }:
            return Response(
                {"message": "Accès refusé."},
                status=status.HTTP_403_FORBIDDEN,
            )

        bijouteries = get_user_bijouteries(request.user)

        if not bijouteries.exists():
            return Response(
                {"detail": "Aucune bijouterie accessible."},
                status=status.HTTP_403_FORBIDDEN,
            )

        qs = (
            CompteDepotTransaction.objects
            .select_related(
                "compte",
                "compte__client",
                "compte__client__bijouterie",
                "user",
            )
            .filter(
                compte__client__bijouterie__in=bijouteries
            )
            .order_by("-date_transaction")
        )

        telephone = request.query_params.get("telephone")
        numero_compte = request.query_params.get("numero_compte")
        type_transaction = request.query_params.get("type_transaction")
        statut = request.query_params.get("statut")
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        if telephone:
            qs = qs.filter(
                compte__client__telephone__icontains=telephone
            )

        if numero_compte:
            qs = qs.filter(
                compte__numero_compte__icontains=numero_compte
            )

        if type_transaction:
            qs = qs.filter(
                type_transaction=type_transaction
            )

        if statut:
            qs = qs.filter(
                statut=statut
            )

        if start_date:
            qs = qs.filter(
                date_transaction__date__gte=start_date
            )

        if end_date:
            qs = qs.filter(
                date_transaction__date__lte=end_date
            )

        wb = Workbook()
        ws = wb.active
        ws.title = "Transactions Compte Depot"

        headers = [
            "Date",
            "Bijouterie",
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

        header_fill = PatternFill(
            fill_type="solid",
            fgColor="1F4E78",
        )
        header_font = Font(
            bold=True,
            color="FFFFFF",
        )

        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font

        for tx in qs:
            client = getattr(tx.compte, "client", None)
            bijouterie = getattr(client, "bijouterie", None) if client else None

            user_label = ""

            if tx.user:
                user_label = (
                    getattr(tx.user, "email", None)
                    or getattr(tx.user, "username", "")
                    or str(tx.user)
                )

            ws.append([
                timezone.localtime(
                    tx.date_transaction
                ).strftime("%Y-%m-%d %H:%M:%S")
                if tx.date_transaction else "",

                getattr(bijouterie, "nom", "") if bijouterie else "",

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
            length = max(
                len(str(cell.value or ""))
                for cell in column_cells
            )

            ws.column_dimensions[
                column_cells[0].column_letter
            ].width = min(length + 2, 40)

        response = HttpResponse(
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            )
        )

        filename = (
            "transactions_compte_depot_"
            f"{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )

        response["Content-Disposition"] = (
            f'attachment; filename="{filename}"'
        )

        wb.save(response)

        return response
    
    
# sauvegarde état des soldes actuels
class ExportCompteDepotSoldesExcelAPIView(APIView):
    permission_classes = [IsAuthenticated, IsManagerOrCashier]

    @swagger_auto_schema(
        operation_summary="Exporter les soldes des comptes dépôt en Excel",
        operation_description=(
            "Exporte l'état actuel des soldes des comptes dépôt.\n\n"
            "### Règles\n"
            "- Admin : toutes les bijouteries.\n"
            "- Manager : uniquement ses bijouteries.\n"
            "- Caissier : uniquement sa bijouterie.\n"
            "- Vendor : non autorisé.\n"
            "- Buyer : non autorisé."
        ),
        responses={
            200: openapi.Response(
                description="Fichier Excel généré avec succès"
            ),
            403: openapi.Response(
                description="Accès refusé"
            ),
        },
        tags=["compte dépôt"],
    )
    def get(self, request):
        role = get_role_name(request.user)

        if role not in {
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_CASHIER,
        }:
            return Response(
                {"message": "Accès refusé."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # ==========================================
        # BIJOUTERIES ACCESSIBLES
        # ==========================================

        bijouteries = get_user_bijouteries(request.user)

        if not bijouteries.exists():
            return Response(
                {
                    "detail":
                    "Aucune bijouterie accessible pour cet utilisateur."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # ==========================================
        # COMPTES ACCESSIBLES
        # ==========================================

        comptes = (
            CompteDepot.objects
            .select_related(
                "client",
                "client__bijouterie",
                "created_by",
            )
            .filter(
                client__bijouterie__in=bijouteries
            )
            .order_by(
                "client__bijouterie__nom",
                "client__nom",
            )
        )

        # ==========================================
        # EXCEL
        # ==========================================

        wb = Workbook()
        ws = wb.active
        ws.title = "Soldes Comptes Depot"

        headers = [
            "Date sauvegarde",
            "Bijouterie",
            "Nom client",
            "Prénom client",
            "Téléphone",
            "Numéro compte",
            "Solde actuel",
            "Date création compte",
            "Dernière transaction",
            "Créé par",
        ]

        ws.append(headers)

        header_fill = PatternFill(
            fill_type="solid",
            fgColor="1F4E78",
        )

        header_font = Font(
            bold=True,
            color="FFFFFF",
        )

        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font

        now = timezone.localtime(timezone.now())

        # ==========================================
        # DONNEES
        # ==========================================

        for compte in comptes:
            client = compte.client

            bijouterie = (
                getattr(client, "bijouterie", None)
                if client
                else None
            )

            # Dernière transaction du compte
            derniere_tx = (
                CompteDepotTransaction.objects
                .filter(compte=compte)
                .order_by("-date_transaction")
                .first()
            )

            created_by = ""

            if compte.created_by:
                created_by = (
                    getattr(compte.created_by, "email", None)
                    or getattr(compte.created_by, "username", "")
                    or str(compte.created_by)
                )

            ws.append([
                now.strftime("%Y-%m-%d %H:%M:%S"),

                getattr(bijouterie, "nom", "")
                if bijouterie
                else "",

                getattr(client, "nom", "")
                if client
                else "",

                getattr(client, "prenom", "")
                if client
                else "",

                getattr(client, "telephone", "")
                if client
                else "",

                compte.numero_compte,

                float(compte.solde),

                (
                    timezone.localtime(
                        compte.created_at
                    ).strftime("%Y-%m-%d %H:%M:%S")
                    if compte.created_at
                    else ""
                ),

                (
                    timezone.localtime(
                        derniere_tx.date_transaction
                    ).strftime("%Y-%m-%d %H:%M:%S")
                    if derniere_tx
                    else ""
                ),

                created_by,
            ])

        # ==========================================
        # LARGEUR COLONNES
        # ==========================================

        for column_cells in ws.columns:
            length = max(
                len(str(cell.value or ""))
                for cell in column_cells
            )

            ws.column_dimensions[
                column_cells[0].column_letter
            ].width = min(length + 2, 45)

        # ==========================================
        # RESPONSE
        # ==========================================

        response = HttpResponse(
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            )
        )

        filename = (
            "sauvegarde_soldes_compte_depot_"
            f"{now.strftime('%Y_%m_%d_%H%M%S')}.xlsx"
        )

        response["Content-Disposition"] = (
            f'attachment; filename="{filename}"'
        )

        wb.save(response)

        return response
    
    
# =========================================================
# DASHBOARD COMPTE DEPOT
# =========================================================
class CompteDepotDashboardAPIView(APIView):
    permission_classes = [
        IsAuthenticated,
        IsManagerOrCashier,
    ]

    @swagger_auto_schema(
        operation_summary="Dashboard comptes dépôt",
        operation_description=(
            "Dashboard des comptes dépôt accessibles à l'utilisateur.\n\n"
            "### Règles\n"
            "- Admin : toutes les bijouteries.\n"
            "- Manager : uniquement ses bijouteries.\n"
            "- Caissier : uniquement sa bijouterie.\n"
            "- Vendor : non autorisé.\n"
            "- Buyer : non autorisé.\n"
        ),
        manual_parameters=[
            openapi.Parameter(
                "start_date",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE,
                required=False,
            ),
            openapi.Parameter(
                "end_date",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE,
                required=False,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Dashboard comptes dépôt"
            ),
            403: openapi.Response(
                description="Accès refusé"
            ),
        },
        tags=["compte dépôt"],
    )
    def get(self, request):
        role = get_role_name(request.user)

        if role not in {
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_CASHIER,
        }:
            return Response(
                {"message": "Accès refusé."},
                status=status.HTTP_403_FORBIDDEN,
            )

        bijouteries = get_user_bijouteries(request.user)

        if not bijouteries.exists():
            return Response(
                {"detail": "Aucune bijouterie accessible."},
                status=status.HTTP_403_FORBIDDEN,
            )

        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        compte_qs = (
            CompteDepot.objects
            .select_related(
                "client",
                "client__bijouterie",
            )
            .filter(
                client__bijouterie__in=bijouteries
            )
        )

        tx_qs = (
            CompteDepotTransaction.objects
            .select_related(
                "compte",
                "compte__client",
                "compte__client__bijouterie",
                "user",
            )
            .filter(
                compte__client__bijouterie__in=bijouteries
            )
        )

        if start_date:
            tx_qs = tx_qs.filter(
                date_transaction__date__gte=start_date
            )

        if end_date:
            tx_qs = tx_qs.filter(
                date_transaction__date__lte=end_date
            )

        total_comptes = compte_qs.count()

        total_solde_global = compte_qs.aggregate(
            total=Coalesce(
                Sum("solde"),
                Decimal("0.00"),
            )
        )["total"]

        total_depots = tx_qs.filter(
            type_transaction=CompteDepotTransaction.TYPE_DEPOT,
            statut=CompteDepotTransaction.STAT_TERMINE,
        ).aggregate(
            total=Coalesce(
                Sum("montant"),
                Decimal("0.00"),
            )
        )["total"]

        total_retraits = tx_qs.filter(
            type_transaction=CompteDepotTransaction.TYPE_RETRAIT,
            statut=CompteDepotTransaction.STAT_TERMINE,
        ).aggregate(
            total=Coalesce(
                Sum("montant"),
                Decimal("0.00"),
            )
        )["total"]

        nombre_transactions = tx_qs.count()

        top_comptes = (
            compte_qs
            .order_by("-solde")[:10]
        )

        top_comptes_data = []

        for compte in top_comptes:
            client = getattr(compte, "client", None)
            bijouterie = (
                getattr(client, "bijouterie", None)
                if client
                else None
            )

            top_comptes_data.append({
                "numero_compte": compte.numero_compte,
                "solde": compte.solde,
                "client_nom": getattr(client, "nom", "") if client else "",
                "client_prenom": getattr(client, "prenom", "") if client else "",
                "telephone": getattr(client, "telephone", "") if client else "",
                "bijouterie": {
                    "id": bijouterie.id,
                    "nom": bijouterie.nom,
                } if bijouterie else None,
            })

        transactions_par_type = (
            tx_qs
            .values("type_transaction")
            .annotate(
                count=Count("id"),
                total=Coalesce(
                    Sum("montant"),
                    Decimal("0.00"),
                ),
            )
            .order_by("type_transaction")
        )

        latest_transactions = (
            tx_qs
            .order_by("-date_transaction")[:10]
        )

        return Response(
            {
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

                "transactions_par_type": list(
                    transactions_par_type
                ),

                "top_comptes": top_comptes_data,

                "dernieres_transactions":
                CompteDepotTransactionSerializer(
                    latest_transactions,
                    many=True,
                ).data,
            },
            status=status.HTTP_200_OK,
        )
        
# =========================================================
# RECU PDF 80MM
# =========================================================
class CompteDepotTransactionReceipt80mmPDFAPIView(APIView):
    permission_classes = [IsAuthenticated, IsManagerOrCashier]

    @swagger_auto_schema(
        operation_id="compteDepotTransactionReceipt",
        operation_summary="Récupérer les données d'un reçu compte dépôt",
        operation_description=(
            "Retourne les données nécessaires au frontend pour afficher "
            "et imprimer un reçu compte dépôt.\n\n"
            "### Règles\n"
            "- Admin : toutes les bijouteries.\n"
            "- Manager : uniquement ses bijouteries.\n"
            "- Caissier : uniquement sa bijouterie.\n"
            "- Vendor : non autorisé.\n"
            "- Buyer : non autorisé."
        ),
        responses={
            200: openapi.Response(
                description="Données du reçu récupérées avec succès"
            ),
            400: openapi.Response(
                description="Transaction sans bijouterie"
            ),
            403: openapi.Response(
                description="Accès refusé"
            ),
            404: openapi.Response(
                description="Transaction introuvable"
            ),
        },
        tags=["compte dépôt"],
    )
    def get(self, request, transaction_id):
        role = get_role_name(request.user)

        if role not in {
            ROLE_ADMIN,
            ROLE_MANAGER,
            ROLE_CASHIER,
        }:
            return Response(
                {"message": "Accès refusé."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            tx = (
                CompteDepotTransaction.objects
                .select_related(
                    "compte",
                    "compte__client",
                    "compte__client__bijouterie",
                    "user",
                )
                .get(pk=transaction_id)
            )

        except CompteDepotTransaction.DoesNotExist:
            return Response(
                {"detail": "Transaction introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        compte = tx.compte
        client = compte.client

        client_bijouterie = getattr(
            client,
            "bijouterie",
            None,
        )

        if not client_bijouterie:
            return Response(
                {
                    "detail":
                    "Cette transaction n'est liée à aucune bijouterie."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user_can_access_bijouterie(
            request.user,
            client_bijouterie,
        ):
            return Response(
                {
                    "detail":
                    "Vous n'avez pas accès à cette transaction."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            {
                "organisation": {
                    "nom": "BIJOUTERIE RIO GOLD",
                    "bijouterie": {
                        "id": client_bijouterie.id,
                        "nom": client_bijouterie.nom,
                    },
                },

                "client": {
                    "nom": client.nom,
                    "prenom": client.prenom,
                    "telephone": client.telephone,
                },

                "compte": {
                    "id": compte.id,
                    "numero_compte": compte.numero_compte,
                    "solde": str(compte.solde),
                },

                "transaction": {
                    "id": tx.id,
                    "type_transaction": tx.type_transaction,
                    "type_transaction_label":
                    tx.get_type_transaction_display(),

                    "montant": str(tx.montant),

                    "solde_avant": str(tx.solde_avant),
                    "solde_apres": str(tx.solde_apres),

                    "statut": tx.statut,
                    "statut_label":
                    tx.get_statut_display(),

                    "reference": tx.reference,
                    "commentaire": tx.commentaire,

                    "date_transaction":
                    tx.date_transaction,
                },

                "effectue_par": {
                    "id": tx.user_id,
                    "email": (
                        getattr(tx.user, "email", None)
                        if tx.user
                        else None
                    ),
                    "username": (
                        getattr(tx.user, "username", None)
                        if tx.user
                        else None
                    ),
                },
            },
            status=status.HTTP_200_OK,
        )
        
        