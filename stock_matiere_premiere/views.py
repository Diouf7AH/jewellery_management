from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce, ExtractMonth
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.roles import (ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER, ROLE_VENDOR,
                           get_role_name)
from backend.utils.helpers import resolve_bijouterie_for_user
from sale.models import Client
from stock_matiere_premiere.serializers import (
    CancelRachatClientSerializer, RachatClientCreateSerializer,
    RachatClientDetailSerializer, RaffinageCreateSerializer,
    ReverseAchatMatierePremiereSerializer, ReverseRachatClientSerializer,
    VenteMatierePremiereCreateSerializer, generate_ticket_number)
from store.models import Purete

from .models import (AchatMatierePremiere, AchatMatierePremiereItem,
                     MatierePremiereMovement, MatierePremiereStock,
                     RachatClient, RachatClientItem, Raffinage, StockRaffine,
                     VenteMatierePremiere)
from .pdf.attestation_rachat_client_pdf import \
    build_attestation_rachat_client_pdf
from .pdf.ticket_rachat_client_58mm import build_rachat_client_ticket_58mm
from .serializers import (AchatMatierePremiereCreateSerializer,
                          AchatMatierePremiereDetailSerializer,
                          AchatMatierePremiereItemOutputSerializer,
                          RachatClientItemOutputSerializer)


class RachatClientCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Créer un bon de rachat client",
        operation_description="""
        Création d’un BON DE RACHAT CLIENT.

        ⚠️ IMPORTANT :
        - Ne touche PAS au stock
        - Ne crée PAS de mouvement
        - Génère uniquement un ticket

        💰 Le stock sera mis à jour uniquement lors du paiement caisse.

        👥 Rôles autorisés :
        - Admin
        - Manager
        - Vendeur
        """,
        request_body=RachatClientCreateSerializer,
        responses={
            201: RachatClientDetailSerializer,
            400: "Erreur de validation",
            403: "Accès refusé",
        },
        tags=["Rachat Client"],
    )
    @transaction.atomic
    def post(self, request):
        user = request.user
        role = get_role_name(user)

        # 🔒 Permissions
        if role not in [ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR]:
            return Response(
                {"detail": "Accès refusé."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 📍 Résolution bijouterie
        try:
            bijouterie = resolve_bijouterie_for_user(request.user)
        except Exception:
            return Response(
                "BIJOUTERIE_NOT_FOUND",
                "Aucune bijouterie associée à cet utilisateur.",
                status.HTTP_400_BAD_REQUEST,
            )

        # 📥 Validation input
        serializer = RachatClientCreateSerializer(
            data=request.data,
            context={"bijouterie": bijouterie}
        )
        serializer.is_valid(raise_exception=True)

        # 💾 Création du rachat (SANS STOCK)
        rachat = serializer.save()

        # 🔄 Recharge avec relations pour éviter les requêtes inutiles
        rachat = (
            RachatClient.objects
            .select_related("client", "bijouterie")
            .prefetch_related("items__purete")
            .get(id=rachat.id)
        )

        data = RachatClientDetailSerializer(rachat).data
        data["ticket_url"] = request.build_absolute_uri(
            f"/api/stock-matiere-premiere/rachats/{rachat.id}/ticket-58mm/"
        )

        return Response(data, status=status.HTTP_201_CREATED)
    





class RachatClientTicket58mmPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, rachat_id):
        rachat = get_object_or_404(
            RachatClient.objects.select_related("client", "bijouterie")
            .prefetch_related("items__purete"),
            id=rachat_id,
        )

        buffer = BytesIO()
        build_rachat_client_ticket_58mm(buffer, rachat)
        buffer.seek(0)

        filename = f"ticket_rachat_{rachat.numero_ticket}.pdf"

        return FileResponse(
            buffer,
            as_attachment=False,
            filename=filename,
            content_type="application/pdf",
        )
        



class PayRachatClientTicketView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Payer un ticket de rachat client",
        operation_description="""
        Le caissier valide le paiement d'un ticket de rachat client.

        Effets :
        - Le ticket passe à PAYÉ
        - Le stock matière première augmente
        - Un mouvement est créé pour chaque ligne
        - Une fiche d’attestation peut ensuite être imprimée
        """,
        manual_parameters=[
            openapi.Parameter(
                "numero_ticket",
                openapi.IN_PATH,
                description="Numéro du ticket de rachat client",
                type=openapi.TYPE_STRING,
                required=True,
            )
        ],
        responses={200: RachatClientDetailSerializer},
        tags=["Rachat Client"],
    )
    @transaction.atomic
    def post(self, request, numero_ticket):
        user = request.user
        role = get_role_name(user)

        if role not in [ROLE_CASHIER, ROLE_ADMIN, ROLE_MANAGER]:
            return Response(
                {"detail": "Seul le caissier, le manager ou l'admin peut payer ce ticket."},
                status=status.HTTP_403_FORBIDDEN,
            )

        rachat = get_object_or_404(
            RachatClient.objects.select_for_update()
            .select_related("client", "bijouterie")
            .prefetch_related("items__purete"),
            numero_ticket=numero_ticket,
        )

        if rachat.payment_status == RachatClient.PAYMENT_PAID:
            return Response(
                {"detail": "Ce ticket est déjà payé."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if rachat.payment_status == RachatClient.PAYMENT_CANCELLED:
            return Response(
                {"detail": "Ce ticket est annulé, paiement impossible."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if rachat.status == RachatClient.STATUS_CANCELLED:
            return Response(
                {"detail": "Ce rachat est annulé."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        for item in rachat.items.select_for_update().all():
            stock, _ = MatierePremiereStock.objects.select_for_update().get_or_create(
                bijouterie=rachat.bijouterie,
                matiere=item.matiere,
                purete=item.purete,
                defaults={"poids_total": 0},
            )

            stock.poids_total = F("poids_total") + item.poids
            stock.save(update_fields=["poids_total", "updated_at"])
            stock.refresh_from_db()

            movement = MatierePremiereMovement.objects.create(
                stock=stock,
                bijouterie=rachat.bijouterie,
                matiere=item.matiere,
                purete=item.purete,
                poids=item.poids,
                source=MatierePremiereMovement.SOURCE_RACHAT_CLIENT,
                rachat=rachat,
            )

            item.movement = movement
            item.save(update_fields=["movement"])

        rachat.payment_status = RachatClient.PAYMENT_PAID
        rachat.paid_at = timezone.now()
        rachat.paid_by = user
        rachat.save(update_fields=["payment_status", "paid_at", "paid_by"])

        data = RachatClientDetailSerializer(rachat).data
        data["attestation_url"] = request.build_absolute_uri(
            f"/api/stock-matiere-premiere/rachats/{rachat.id}/attestation/"
        )

        return Response(data, status=status.HTTP_200_OK)
    


class RachatClientAttestationPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, rachat_id):
        rachat = get_object_or_404(
            RachatClient.objects.select_related("client", "bijouterie", "paid_by")
            .prefetch_related("items__purete"),
            id=rachat_id,
        )

        if rachat.payment_status != RachatClient.PAYMENT_PAID:
            return Response(
                {"detail": "La fiche d’attestation est disponible seulement après paiement."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        buffer = BytesIO()
        build_attestation_rachat_client_pdf(buffer, rachat)
        buffer.seek(0)

        filename = f"attestation_rachat_{rachat.numero_ticket}.pdf"

        return FileResponse(
            buffer,
            as_attachment=False,
            filename=filename,
            content_type="application/pdf",
        )


class CancelRachatClientView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Annuler un bon de rachat client",
        operation_description="""
        Annule un bon de rachat client.

        Règles métier :
        - Seul ADMIN ou MANAGER peut annuler.
        - Annulation autorisée uniquement AVANT paiement.
        - Impossible d'annuler un ticket déjà payé.
        - Impossible d'annuler un ticket déjà annulé.
        - Aucun stock n'est modifié ici (stock créé uniquement après paiement).
        """,
        request_body=CancelRachatClientSerializer,
        responses={
            200: RachatClientDetailSerializer,
            400: "Annulation impossible",
            403: "Accès refusé",
            404: "Rachat introuvable",
        },
        tags=["Rachat Client"],
    )
    @transaction.atomic
    def post(self, request, rachat_id):
        role = get_role_name(request.user)

        # 🔒 Permissions
        if role not in [ROLE_ADMIN, ROLE_MANAGER]:
            return Response(
                {"detail": "Accès refusé. Seul un admin ou un manager peut annuler ce rachat."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CancelRachatClientSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        rachat = get_object_or_404(
            RachatClient.objects.select_for_update()
            .select_related("client", "bijouterie")
            .prefetch_related("items__purete"),
            id=rachat_id,
        )

        # 🔁 Déjà annulé
        if rachat.status == RachatClient.STATUS_CANCELLED:
            return Response(
                {"detail": "Ce rachat est déjà annulé."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 💰 Déjà payé → interdit
        if rachat.payment_status == RachatClient.PAYMENT_PAID:
            return Response(
                {"detail": "Impossible d'annuler un rachat déjà payé."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ❌ Déjà annulé côté paiement
        if rachat.payment_status == RachatClient.PAYMENT_CANCELLED:
            return Response(
                {"detail": "Ce ticket est déjà annulé."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 📝 Motif
        reason = serializer.validated_data.get("reason") or ""

        # ✅ Annulation
        rachat.status = RachatClient.STATUS_CANCELLED
        rachat.payment_status = RachatClient.PAYMENT_CANCELLED
        rachat.cancelled_at = timezone.now()
        rachat.cancelled_by = request.user
        rachat.cancel_reason = reason

        rachat.save(update_fields=[
            "status",
            "payment_status",
            "cancelled_at",
            "cancelled_by",
            "cancel_reason",
        ])

        return Response(
            RachatClientDetailSerializer(rachat).data,
            status=status.HTTP_200_OK,
        )

#annule rachat
class ReverseRachatClientView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Corriger / inverser un rachat client déjà payé",
        operation_description="""
        Corrige un rachat client déjà payé.

        Règles métier :
        - Seul ADMIN ou MANAGER peut faire une correction après paiement.
        - Le rachat doit être PAYÉ.
        - Le rachat ne doit pas être déjà annulé.
        - Correction autorisée uniquement dans les 48h après paiement.
        - Le stock matière première est diminué.
        - Un mouvement inverse est créé pour chaque ligne.
        - Cette action garde l'historique au lieu de supprimer l'opération.
        """,
        request_body=ReverseRachatClientSerializer,
        responses={
            200: RachatClientDetailSerializer,
            400: "Correction impossible",
            403: "Accès refusé",
            404: "Rachat introuvable",
        },
        tags=["Rachat Client"],
    )
    @transaction.atomic
    def post(self, request, rachat_id):
        role = get_role_name(request.user)

        if role not in [ROLE_ADMIN, ROLE_MANAGER]:
            return Response(
                {"detail": "Accès refusé. Seul un admin ou un manager peut corriger un rachat payé."},
                status=status.HTTP_403_FORBIDDEN,
            )

        input_serializer = ReverseRachatClientSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        rachat = get_object_or_404(
            RachatClient.objects.select_for_update()
            .select_related("client", "bijouterie")
            .prefetch_related("items__purete", "movements"),
            id=rachat_id,
        )

        if rachat.status == RachatClient.STATUS_CANCELLED:
            return Response(
                {"detail": "Ce rachat est déjà annulé/corrigé."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if rachat.payment_status != RachatClient.PAYMENT_PAID:
            return Response(
                {"detail": "Seul un rachat déjà payé peut être corrigé par opération inverse."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not rachat.paid_at:
            return Response(
                {"detail": "Date de paiement introuvable, correction impossible."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if timezone.now() - rachat.paid_at > timedelta(hours=48):
            return Response(
                {"detail": "Correction impossible après 48h suivant le paiement."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        already_reversed = MatierePremiereMovement.objects.filter(
            rachat=rachat,
            source=MatierePremiereMovement.SOURCE_RACHAT_CLIENT_CANCEL,
        ).exists()

        if already_reversed:
            return Response(
                {"detail": "Ce rachat possède déjà des mouvements inverses."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reason = input_serializer.validated_data["reason"]

        for item in rachat.items.select_for_update().all():
            stock = MatierePremiereStock.objects.select_for_update().filter(
                bijouterie=rachat.bijouterie,
                matiere=item.matiere,
                purete=item.purete,
            ).first()

            if not stock:
                return Response(
                    {
                        "detail": (
                            f"Stock introuvable pour {item.matiere} / "
                            f"{item.purete}. Correction impossible."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            stock.refresh_from_db()

            if stock.poids_total < item.poids:
                return Response(
                    {
                        "detail": (
                            f"Stock insuffisant pour annuler la ligne "
                            f"{item.description}. Disponible: {stock.poids_total} g, "
                            f"à retirer: {item.poids} g."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            stock.poids_total = F("poids_total") - item.poids
            stock.save(update_fields=["poids_total", "updated_at"])
            stock.refresh_from_db()

            MatierePremiereMovement.objects.create(
                stock=stock,
                bijouterie=rachat.bijouterie,
                matiere=item.matiere,
                purete=item.purete,
                poids=item.poids,
                source=MatierePremiereMovement.SOURCE_RACHAT_CLIENT_CANCEL,
                rachat=rachat,
            )

        rachat.status = RachatClient.STATUS_CANCELLED
        rachat.payment_status = RachatClient.PAYMENT_CANCELLED
        rachat.cancelled_at = timezone.now()
        rachat.cancelled_by = request.user
        rachat.cancel_reason = reason
        rachat.save(update_fields=[
            "status",
            "payment_status",
            "cancelled_at",
            "cancelled_by",
            "cancel_reason",
        ])

        return Response(
            RachatClientDetailSerializer(rachat).data,
            status=status.HTTP_200_OK,
        )
    

# ///////////////////f///////////////////////
    # fournisseur
# ///////////////////f///////////////////////
class AchatMatierePremiereCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Créer un achat matière première",
        operation_description="""
        Création d’un achat matière première fournisseur.

        ⚠️ IMPORTANT :
        - Paiement effectué immédiatement par le manager/admin
        - Stock matière première mis à jour immédiatement
        - Movement créé automatiquement
        - Aucun passage en caisse
        - Aucun ticket imprimé
        """,
        request_body=AchatMatierePremiereCreateSerializer,
        responses={201: AchatMatierePremiereDetailSerializer},
        tags=["Achat Matière Première"],
    )
    @transaction.atomic
    def post(self, request):
        user = request.user
        role = get_role_name(user)

        # 🔒 Permissions
        if role not in [ROLE_ADMIN, ROLE_MANAGER]:
            return Response(
                {"detail": "Seul un admin ou manager peut créer un achat."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 📍 Bijouterie
        bijouterie = resolve_bijouterie_for_user(user)

        serializer = AchatMatierePremiereCreateSerializer(
            data=request.data,
            context={"bijouterie": bijouterie},
        )
        serializer.is_valid(raise_exception=True)

        # 💾 Création achat
        achat = serializer.save()

        # 💰 Paiement direct
        achat.payment_status = AchatMatierePremiere.PAYMENT_PAID
        achat.paid_at = timezone.now()
        achat.paid_by = user
        achat.save(update_fields=["payment_status", "paid_at", "paid_by"])

        # 📦 STOCK + MOVEMENT
        for item in achat.items.select_for_update():
            stock, _ = MatierePremiereStock.objects.select_for_update().get_or_create(
                bijouterie=achat.bijouterie,
                matiere=item.matiere,
                purete=item.purete,
                defaults={"poids_total": 0},
            )

            # ➕ Ajouter au stock
            stock.poids_total = F("poids_total") + item.poids
            stock.save(update_fields=["poids_total", "updated_at"])
            stock.refresh_from_db()

            # 🧾 Movement
            movement = MatierePremiereMovement.objects.create(
                stock=stock,
                bijouterie=achat.bijouterie,
                matiere=item.matiere,
                purete=item.purete,
                poids=item.poids,
                source=MatierePremiereMovement.SOURCE_ACHAT_FOURNISSEUR,
                achat=achat,
            )

            item.movement = movement
            item.save(update_fields=["movement"])

        return Response(
            AchatMatierePremiereDetailSerializer(achat).data,
            status=status.HTTP_201_CREATED,
        )
        



class AchatRachatMatierePremiereListView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Lister les achats et rachats matière première",
        operation_description="""
        Liste tous les achats fournisseur et rachats client de matière première.

        Règles :
        - ADMIN voit tout
        - MANAGER voit ses bijouteries
        - Vendeur non autorisé
        """,
        manual_parameters=[
            openapi.Parameter("year",openapi.IN_QUERY,type=openapi.TYPE_INTEGER,description="Année à afficher. Par défaut : année en cours",),
            openapi.Parameter("type", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="achat ou rachat"),
            openapi.Parameter("bijouterie_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter("status", openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter("payment_status", openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter("start_date", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="YYYY-MM-DD"),
            openapi.Parameter("end_date", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="YYYY-MM-DD"),
        ],
        responses={200: "Liste achats/rachats matière première"},
        tags=["Matière Première"],
    )
    def get(self, request):
        user = request.user
        role = get_role_name(user)

        if role not in [ROLE_ADMIN, ROLE_MANAGER]:
            return Response(
                {"detail": "Accès refusé."},
                status=status.HTTP_403_FORBIDDEN,
            )

        achats = AchatMatierePremiere.objects.select_related(
            "fournisseur", "bijouterie", "paid_by", "cancelled_by"
        ).prefetch_related("items__purete")

        rachats = RachatClient.objects.select_related(
            "client", "bijouterie", "paid_by", "cancelled_by"
        ).prefetch_related("items__purete")

        if role == ROLE_MANAGER:
            manager_profile = getattr(user, "manager_profile", None)
            if not manager_profile:
                return Response(
                    {"detail": "Aucune bijouterie associée à ce manager."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            bijouteries = manager_profile.bijouteries.all()
            achats = achats.filter(bijouterie__in=bijouteries)
            rachats = rachats.filter(bijouterie__in=bijouteries)

        type_filter = request.query_params.get("type")
        bijouterie_id = request.query_params.get("bijouterie_id")
        status_filter = request.query_params.get("status")
        payment_status = request.query_params.get("payment_status")
        year = request.query_params.get("year")
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        
        # ✅ Par défaut : année en cours
        if not start_date and not end_date:
            current_year = int(year) if year else timezone.now().year
            achats = achats.filter(created_at__year=current_year)
            rachats = rachats.filter(created_at__year=current_year)

        if bijouterie_id:
            achats = achats.filter(bijouterie_id=bijouterie_id)
            rachats = rachats.filter(bijouterie_id=bijouterie_id)

        if status_filter:
            achats = achats.filter(status=status_filter)
            rachats = rachats.filter(status=status_filter)

        if payment_status:
            achats = achats.filter(payment_status=payment_status)
            rachats = rachats.filter(payment_status=payment_status)

        if start_date:
            achats = achats.filter(created_at__date__gte=start_date)
            rachats = rachats.filter(created_at__date__gte=start_date)

        if end_date:
            achats = achats.filter(created_at__date__lte=end_date)
            rachats = rachats.filter(created_at__date__lte=end_date)

        result = []

        if type_filter in [None, "", "achat"]:
            for achat in achats:
                result.append({
                    "type": "achat",
                    "id": achat.id,
                    "numero_ticket": achat.numero_ticket,
                    "personne": str(achat.fournisseur),
                    "bijouterie": str(achat.bijouterie),
                    "montant_total": achat.montant_total,
                    "mode_paiement": achat.mode_paiement,
                    "payment_status": achat.payment_status,
                    "status": achat.status,
                    "created_at": achat.created_at,
                })

        if type_filter in [None, "", "rachat"]:
            for rachat in rachats:
                result.append({
                    "type": "rachat",
                    "id": rachat.id,
                    "numero_ticket": rachat.numero_ticket,
                    "personne": str(rachat.client),
                    "bijouterie": str(rachat.bijouterie),
                    "montant_total": rachat.montant_total,
                    "mode_paiement": rachat.mode_paiement,
                    "payment_status": rachat.payment_status,
                    "status": rachat.status,
                    "created_at": rachat.created_at,
                    })

        result = sorted(result, key=lambda x: x["created_at"], reverse=True)

        return Response(result, status=status.HTTP_200_OK)



class AchatRachatMatierePremiereDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Détail achat ou rachat matière première",
        operation_description="""
        Retourne le détail d'un achat fournisseur ou d'un rachat client.

        Paramètre type :
        - achat
        - rachat

        Règles :
        - ADMIN voit tout
        - MANAGER voit seulement ses bijouteries
        """,
        manual_parameters=[
            openapi.Parameter(
                "type",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=True,
                description="Type de document : achat ou rachat",
            ),
        ],
        responses={200: "Détail achat/rachat matière première"},
        tags=["Matière Première"],
    )
    def get(self, request, pk):
        user = request.user
        role = get_role_name(user)

        if role not in [ROLE_ADMIN, ROLE_MANAGER]:
            return Response(
                {"detail": "Accès refusé."},
                status=status.HTTP_403_FORBIDDEN,
            )

        type_doc = request.query_params.get("type")

        if type_doc not in ["achat", "rachat"]:
            return Response(
                {"detail": "Le paramètre type est obligatoire : achat ou rachat."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if type_doc == "achat":
            obj = get_object_or_404(
                AchatMatierePremiere.objects.select_related(
                    "fournisseur", "bijouterie", "paid_by", "cancelled_by"
                ).prefetch_related("items__purete"),
                id=pk,
            )

            if role == ROLE_MANAGER:
                manager_profile = getattr(user, "manager_profile", None)

                if not manager_profile or not manager_profile.bijouteries.filter(id=obj.bijouterie_id).exists():
                    return Response(
                        {"detail": "Accès refusé pour cette bijouterie."},
                        status=status.HTTP_403_FORBIDDEN,
                    )

            return Response(
                AchatMatierePremiereDetailSerializer(obj).data,
                status=status.HTTP_200_OK,
            )

        obj = get_object_or_404(
            RachatClient.objects.select_related(
                "client", "bijouterie", "paid_by", "cancelled_by"
            ).prefetch_related("items__purete"),
            id=pk,
        )

        if role == ROLE_MANAGER:
            manager_profile = getattr(user, "manager_profile", None)

            if not manager_profile or not manager_profile.bijouteries.filter(id=obj.bijouterie_id).exists():
                return Response(
                    {"detail": "Accès refusé pour cette bijouterie."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        return Response(
            RachatClientDetailSerializer(obj).data,
            status=status.HTTP_200_OK,
        )


class DashboardAchatRachatMatierePremiereView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Dashboard achats et rachats matière première",
        operation_description="""
        Dashboard global des achats fournisseur et rachats client de matière première.

        Donne :
        - Nombre total d'achats
        - Nombre total de rachats
        - Montant total achats
        - Montant total rachats
        - Poids total achats
        - Poids total rachats
        - Stock matière actuel
        - Répartition par matière et pureté

        Règles :
        - ADMIN voit tout
        - MANAGER voit seulement ses bijouteries
        """,
        manual_parameters=[
            openapi.Parameter(
                "bijouterie_id",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="Filtrer par bijouterie",
            ),
            openapi.Parameter(
                "start_date",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
                description="Date début YYYY-MM-DD",
            ),
            openapi.Parameter(
                "end_date",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
                description="Date fin YYYY-MM-DD",
            ),
        ],
        responses={200: "Dashboard achats/rachats matière première"},
        tags=["Dashboard Matière Première"],
    )
    def get(self, request):
        user = request.user
        role = get_role_name(user)

        if role not in [ROLE_ADMIN, ROLE_MANAGER]:
            return Response(
                {"detail": "Accès refusé."},
                status=status.HTTP_403_FORBIDDEN,
            )

        achats = AchatMatierePremiere.objects.filter(
            status=AchatMatierePremiere.STATUS_CONFIRMED,
            payment_status=AchatMatierePremiere.PAYMENT_PAID,
        )

        rachats = RachatClient.objects.filter(
            status=RachatClient.STATUS_CONFIRMED,
            payment_status=RachatClient.PAYMENT_PAID,
        )

        achat_items = AchatMatierePremiereItem.objects.filter(
            achat__status=AchatMatierePremiere.STATUS_CONFIRMED,
            achat__payment_status=AchatMatierePremiere.PAYMENT_PAID,
        )

        rachat_items = RachatClientItem.objects.filter(
            rachat__status=RachatClient.STATUS_CONFIRMED,
            rachat__payment_status=RachatClient.PAYMENT_PAID,
        )

        stocks = MatierePremiereStock.objects.all()

        # Scope manager
        if role == ROLE_MANAGER:
            manager_profile = getattr(user, "manager_profile", None)

            if not manager_profile:
                return Response(
                    {"detail": "Aucune bijouterie associée à ce manager."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            bijouteries = manager_profile.bijouteries.all()

            achats = achats.filter(bijouterie__in=bijouteries)
            rachats = rachats.filter(bijouterie__in=bijouteries)
            achat_items = achat_items.filter(achat__bijouterie__in=bijouteries)
            rachat_items = rachat_items.filter(rachat__bijouterie__in=bijouteries)
            stocks = stocks.filter(bijouterie__in=bijouteries)

        bijouterie_id = request.query_params.get("bijouterie_id")
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        if bijouterie_id:
            achats = achats.filter(bijouterie_id=bijouterie_id)
            rachats = rachats.filter(bijouterie_id=bijouterie_id)
            achat_items = achat_items.filter(achat__bijouterie_id=bijouterie_id)
            rachat_items = rachat_items.filter(rachat__bijouterie_id=bijouterie_id)
            stocks = stocks.filter(bijouterie_id=bijouterie_id)

        if start_date:
            achats = achats.filter(created_at__date__gte=start_date)
            rachats = rachats.filter(created_at__date__gte=start_date)
            achat_items = achat_items.filter(achat__created_at__date__gte=start_date)
            rachat_items = rachat_items.filter(rachat__created_at__date__gte=start_date)

        if end_date:
            achats = achats.filter(created_at__date__lte=end_date)
            rachats = rachats.filter(created_at__date__lte=end_date)
            achat_items = achat_items.filter(achat__created_at__date__lte=end_date)
            rachat_items = rachat_items.filter(rachat__created_at__date__lte=end_date)

        current_year = timezone.now().year

        achats_year = AchatMatierePremiere.objects.filter(
            status=AchatMatierePremiere.STATUS_CONFIRMED,
            payment_status=AchatMatierePremiere.PAYMENT_PAID,
            created_at__year=current_year
        )

        rachats_year = RachatClient.objects.filter(
            status=RachatClient.STATUS_CONFIRMED,
            payment_status=RachatClient.PAYMENT_PAID,
            created_at__year=current_year
        )

        achat_items_year = AchatMatierePremiereItem.objects.filter(
            achat__status=AchatMatierePremiere.STATUS_CONFIRMED,
            achat__payment_status=AchatMatierePremiere.PAYMENT_PAID,
            achat__created_at__year=current_year
        )

        rachat_items_year = RachatClientItem.objects.filter(
            rachat__status=RachatClient.STATUS_CONFIRMED,
            rachat__payment_status=RachatClient.PAYMENT_PAID,
            rachat__created_at__year=current_year
        )
        
        achats_year_stats = achats_year.aggregate(
            total_achats=Count("id"),
            montant_total=Coalesce(Sum("montant_total"), Decimal("0.00")),
        )

        rachats_year_stats = rachats_year.aggregate(
            total_rachats=Count("id"),
            montant_total=Coalesce(Sum("montant_total"), Decimal("0.00")),
        )

        poids_achats_year = achat_items_year.aggregate(
            poids_total=Coalesce(Sum("poids"), Decimal("0.000"))
        )["poids_total"]

        poids_rachats_year = rachat_items_year.aggregate(
            poids_total=Coalesce(Sum("poids"), Decimal("0.000"))
        )["poids_total"]

        stock_total = stocks.aggregate(
            poids_total=Coalesce(Sum("poids_total"), Decimal("0.000"))
        )["poids_total"]

        repartition_achats = achat_items.values(
            "matiere",
            "purete__purete",
        ).annotate(
            poids_total=Coalesce(Sum("poids"), Decimal("0.000")),
            nombre_lignes=Count("id"),
        ).order_by("matiere", "purete__purete")

        repartition_rachats = rachat_items.values(
            "matiere",
            "purete__purete",
        ).annotate(
            poids_total=Coalesce(Sum("poids"), Decimal("0.000")),
            nombre_lignes=Count("id"),
        ).order_by("matiere", "purete__purete")

        stock_actuel = stocks.values(
            "matiere",
            "purete__purete",
            "bijouterie__nom",
        ).annotate(
            poids_total=Coalesce(Sum("poids_total"), Decimal("0.000")),
        ).order_by("bijouterie__nom", "matiere", "purete__purete")
        
        achats_stats = achats.aggregate(
            total_achats=Count("id"),
            montant_total_achats=Coalesce(Sum("montant_total"), Decimal("0.00")),
        )

        rachats_stats = rachats.aggregate(
            total_rachats=Count("id"),
            montant_total_rachats=Coalesce(Sum("montant_total"), Decimal("0.00")),
        )

        poids_achats = achat_items.aggregate(
            poids_total=Coalesce(Sum("poids"), Decimal("0.000"))
        )["poids_total"]

        poids_rachats = rachat_items.aggregate(
            poids_total=Coalesce(Sum("poids"), Decimal("0.000"))
        )["poids_total"]

        return Response({
            "resume": {
                "total_achats": achats_stats["total_achats"],
                "total_rachats": rachats_stats["total_rachats"],
                "montant_total_achats": achats_stats["montant_total_achats"],
                "montant_total_rachats": rachats_stats["montant_total_rachats"],
                "poids_total_achats": poids_achats,
                "poids_total_rachats": poids_rachats,
                "stock_total_actuel": stock_total,
            },

            "annee_en_cours": {
                "annee": current_year,
                "total_achats": achats_year_stats["total_achats"],
                "total_rachats": rachats_year_stats["total_rachats"],
                "montant_total_achats": achats_year_stats["montant_total"],
                "montant_total_rachats": rachats_year_stats["montant_total"],
                "poids_total_achats": poids_achats_year,
                "poids_total_rachats": poids_rachats_year,
            },

            "repartition_achats": list(repartition_achats),
            "repartition_rachats": list(repartition_rachats),
            "stock_actuel": list(stock_actuel),

        }, status=status.HTTP_200_OK)
                



class ReverseAchatMatierePremiereView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Corriger / inverser un achat matière première",
        operation_description="""
        Corrige un achat matière première déjà enregistré.

        Règles métier :
        - Seul ADMIN ou MANAGER peut corriger.
        - L'achat doit être payé.
        - Impossible de corriger un achat déjà annulé.
        - Le stock matière première est diminué.
        - Un mouvement inverse est créé pour chaque ligne.
        - L'historique est conservé.
        """,
        request_body=ReverseAchatMatierePremiereSerializer,
        responses={
            200: AchatMatierePremiereDetailSerializer,
            400: "Correction impossible",
            403: "Accès refusé",
            404: "Achat introuvable",
        },
        tags=["Achat Matière Première"],
    )
    @transaction.atomic
    def post(self, request, achat_id):
        user = request.user
        role = get_role_name(user)

        if role not in [ROLE_ADMIN, ROLE_MANAGER]:
            return Response(
                {"detail": "Accès refusé. Seul un admin ou un manager peut corriger cet achat."},
                status=status.HTTP_403_FORBIDDEN,
            )

        input_serializer = ReverseAchatMatierePremiereSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        achat = get_object_or_404(
            AchatMatierePremiere.objects.select_for_update()
            .select_related("fournisseur", "bijouterie", "paid_by")
            .prefetch_related("items__purete"),
            id=achat_id,
        )

        if achat.status == AchatMatierePremiere.STATUS_CANCELLED:
            return Response(
                {"detail": "Cet achat est déjà annulé/corrigé."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if achat.payment_status != AchatMatierePremiere.PAYMENT_PAID:
            return Response(
                {"detail": "Seul un achat déjà payé peut être corrigé."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        already_reversed = MatierePremiereMovement.objects.filter(
            achat=achat,
            source=MatierePremiereMovement.SOURCE_ACHAT_FOURNISSEUR_CANCEL,
        ).exists()

        if already_reversed:
            return Response(
                {"detail": "Cet achat possède déjà des mouvements inverses."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reason = input_serializer.validated_data["reason"]

        for item in achat.items.select_for_update().all():
            stock = MatierePremiereStock.objects.select_for_update().filter(
                bijouterie=achat.bijouterie,
                matiere=item.matiere,
                purete=item.purete,
            ).first()

            if not stock:
                return Response(
                    {"detail": f"Stock introuvable pour {item.matiere} / {item.purete}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            stock.refresh_from_db()

            if stock.poids_total < item.poids:
                return Response(
                    {
                        "detail": (
                            f"Stock insuffisant pour corriger la ligne '{item.description}'. "
                            f"Disponible : {stock.poids_total} g, à retirer : {item.poids} g."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            stock.poids_total = F("poids_total") - item.poids
            stock.save(update_fields=["poids_total", "updated_at"])
            stock.refresh_from_db()

            MatierePremiereMovement.objects.create(
                stock=stock,
                bijouterie=achat.bijouterie,
                matiere=item.matiere,
                purete=item.purete,
                poids=item.poids,
                source=MatierePremiereMovement.SOURCE_ACHAT_FOURNISSEUR_CANCEL,
                achat=achat,
            )

        achat.status = AchatMatierePremiere.STATUS_CANCELLED
        achat.payment_status = AchatMatierePremiere.PAYMENT_CANCELLED
        achat.cancelled_at = timezone.now()
        achat.cancelled_by = user
        achat.cancel_reason = reason
        achat.save(update_fields=[
            "status",
            "payment_status",
            "cancelled_at",
            "cancelled_by",
            "cancel_reason",
        ])

        return Response(
            AchatMatierePremiereDetailSerializer(achat).data,
            status=status.HTTP_200_OK,
        )

################################################################
########################## Rafinage ############################
################################################################
class RaffinageCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Créer une opération de raffinage",
        operation_description="""
        Crée une opération de raffinage.

        Effets :
        - Retire le poids du stock matière première
        - Ajoute le poids obtenu dans le stock raffiné
        - Enregistre les mouvements de traçabilité

        Rôles autorisés :
        - ADMIN
        - MANAGER
        """,
        request_body=RaffinageCreateSerializer,
        responses={
            201: "Raffinage créé avec succès",
            400: "Erreur de validation",
            403: "Accès refusé",
        },
        tags=["Raffinage"],
    )
    @transaction.atomic
    def post(self, request):
        user = request.user
        role = get_role_name(user)

        if role not in [ROLE_ADMIN, ROLE_MANAGER]:
            return Response(
                {"detail": "Accès refusé. Seul un admin ou manager peut faire un raffinage."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            bijouterie = resolve_bijouterie_for_user(user)
        except Exception:
            return Response(
                {"detail": "Aucune bijouterie associée à cet utilisateur."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = RaffinageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        purete_avant = get_object_or_404(Purete, id=data["purete_avant_id"])
        purete_apres = get_object_or_404(Purete, id=data["purete_apres_id"])

        stock_mp = MatierePremiereStock.objects.select_for_update().filter(bijouterie=bijouterie,
            matiere=data["matiere"],purete=purete_avant,).first()

        if not stock_mp:
            return Response(
                {"detail": "Stock matière première introuvable pour cette matière/pureté."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if stock_mp.poids_total < data["poids_entree"]:
            return Response(
                {
                    "detail": (
                        f"Stock insuffisant. Disponible : {stock_mp.poids_total} g, "
                        f"demandé : {data['poids_entree']} g."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        perte = data["poids_entree"] - data["poids_sortie"]

        raffinage = Raffinage.objects.create(
            numero_operation=generate_ticket_number("RAF", Raffinage),
            bijouterie=bijouterie,
            matiere=data["matiere"],
            purete_avant=purete_avant,
            purete_apres=purete_apres,
            poids_entree=data["poids_entree"],
            poids_sortie=data["poids_sortie"],
            perte=perte,
            description=data.get("description"),
            created_by=user,
        )

        # Sortie stock matière première
        stock_mp.poids_total = F("poids_total") - data["poids_entree"]
        stock_mp.save(update_fields=["poids_total", "updated_at"])
        stock_mp.refresh_from_db()

        MatierePremiereMovement.objects.create(
            stock=stock_mp,
            bijouterie=bijouterie,
            matiere=data["matiere"],
            purete=purete_avant,
            poids=data["poids_entree"],
            source=MatierePremiereMovement.SOURCE_RAFFINAGE_OUT,
        )

        # Entrée stock raffiné
        stock_raffine, _ = StockRaffine.objects.select_for_update().get_or_create(
            bijouterie=bijouterie,
            matiere=data["matiere"],
            purete=purete_apres,
            defaults={"poids_total": Decimal("0.000")},
        )

        stock_raffine.poids_total = F("poids_total") + data["poids_sortie"]
        stock_raffine.save(update_fields=["poids_total", "updated_at"])
        stock_raffine.refresh_from_db()

        return Response(
            {
                "detail": "Raffinage créé avec succès.",
                "id": raffinage.id,
                "numero_operation": raffinage.numero_operation,
                "matiere": raffinage.matiere,
                "purete_avant": str(purete_avant),
                "purete_apres": str(purete_apres),
                "poids_entree": raffinage.poids_entree,
                "poids_sortie": raffinage.poids_sortie,
                "perte": raffinage.perte,
                "stock_matiere_restant": stock_mp.poids_total,
                "stock_raffine_total": stock_raffine.poids_total,
            },
            status=status.HTTP_201_CREATED,
        )
        
        
###################################################################
#################  Vente matiere premiere   #######################
###################################################################
        
class VenteMatierePremiereCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Créer une vente de matière première",
        operation_description="""
        Crée une vente de matière première au poids.

        Deux sources possibles :
        - avant_raffinage : sortie depuis MatierePremiereStock
        - apres_raffinage : sortie depuis StockRaffine

        Effets :
        - vérifie le stock disponible
        - diminue le stock concerné
        - crée VenteMatierePremiere
        - crée MatierePremiereMovement
        """,
        request_body=VenteMatierePremiereCreateSerializer,
        responses={
            201: "Vente matière créée",
            400: "Erreur de validation / stock insuffisant",
            403: "Accès refusé",
        },
        tags=["Vente Matière Première"],
    )
    @transaction.atomic
    def post(self, request):
        user = request.user
        role = get_role_name(user)

        if role not in [ROLE_ADMIN, ROLE_MANAGER]:
            return Response(
                {"detail": "Accès refusé. Seul admin ou manager peut vendre la matière."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            bijouterie = resolve_bijouterie_for_user(user)
        except Exception:
            return Response(
                {"detail": "Aucune bijouterie associée à cet utilisateur."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = VenteMatierePremiereCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        purete = get_object_or_404(Purete, id=data["purete_id"])

        client = None
        if data.get("client_id"):
            client = get_object_or_404(Client, id=data["client_id"])

        # 1. Vente avant raffinage
        if data["source_stock"] == VenteMatierePremiere.SOURCE_AVANT_RAFFINAGE:
            stock = MatierePremiereStock.objects.select_for_update().filter(
                bijouterie=bijouterie,
                matiere=data["matiere"],
                purete=purete,
            ).first()

            if not stock:
                return Response(
                    {"detail": "Stock matière première introuvable."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if stock.poids_total < data["poids"]:
                return Response(
                    {
                        "detail": (
                            f"Stock insuffisant. Disponible : {stock.poids_total} g, "
                            f"demandé : {data['poids']} g."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            stock.poids_total = F("poids_total") - data["poids"]
            stock.save(update_fields=["poids_total", "updated_at"])
            stock.refresh_from_db()

            movement_source = MatierePremiereMovement.SOURCE_VENTE_POIDS

        # 2. Vente après raffinage
        else:
            stock_raffine = StockRaffine.objects.select_for_update().filter(
                bijouterie=bijouterie,
                matiere=data["matiere"],
                purete=purete,
            ).first()

            if not stock_raffine:
                return Response(
                    {"detail": "Stock raffiné introuvable."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if stock_raffine.poids_total < data["poids"]:
                return Response(
                    {
                        "detail": (
                            f"Stock raffiné insuffisant. Disponible : {stock_raffine.poids_total} g, "
                            f"demandé : {data['poids']} g."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            stock_raffine.poids_total = F("poids_total") - data["poids"]
            stock_raffine.save(update_fields=["poids_total", "updated_at"])
            stock_raffine.refresh_from_db()

            # Ici movement.stock attend MatierePremiereStock.
            # Donc on crée seulement la vente, pas de movement lié au stock raffiné.
            stock = None
            movement_source = MatierePremiereMovement.SOURCE_VENTE_RAFFINE

        vente = VenteMatierePremiere.objects.create(
            numero_vente=generate_ticket_number("VMP", VenteMatierePremiere),
            source_stock=data["source_stock"],
            bijouterie=bijouterie,
            client=client,
            matiere=data["matiere"],
            purete=purete,
            poids=data["poids"],
            prix_gramme=data["prix_gramme"],
            montant_total=data["montant_total"],
            created_by=user,
        )

        if stock:
            MatierePremiereMovement.objects.create(
                stock=stock,
                bijouterie=bijouterie,
                matiere=data["matiere"],
                purete=purete,
                poids=data["poids"],
                source=movement_source,
                montant_total=data["montant_total"],
            )

        return Response(
            {
                "detail": "Vente matière première créée avec succès.",
                "id": vente.id,
                "numero_vente": vente.numero_vente,
                "source_stock": vente.source_stock,
                "matiere": vente.matiere,
                "purete": str(vente.purete),
                "poids": vente.poids,
                "prix_gramme": vente.prix_gramme,
                "montant_total": vente.montant_total,
            },
            status=status.HTTP_201_CREATED,
        )


class DashboardMatierePremiereView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Dashboard global matière première",
        operation_description="""
        Dashboard global de l'application matière première.

        Donne :
        - Stock brut total
        - Stock raffiné total
        - Achats année en cours
        - Rachats année en cours
        - Ventes matière année en cours
        - Raffinages année en cours
        - Mouvements par source
        - Evolution mensuelle
        - Alertes stock faible

        Règles :
        - ADMIN voit tout
        - MANAGER voit ses bijouteries
        """,
        manual_parameters=[
            openapi.Parameter(
                "bijouterie_id",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="Filtrer par bijouterie",
            ),
            openapi.Parameter(
                "seuil_stock",
                openapi.IN_QUERY,
                type=openapi.TYPE_NUMBER,
                required=False,
                description="Seuil d'alerte stock faible en grammes. Par défaut 5g.",
            ),
        ],
        responses={200: "Dashboard matière première"},
        tags=["Dashboard Matière Première"],
    )
    def get(self, request):
        user = request.user
        role = get_role_name(user)

        if role not in [ROLE_ADMIN, ROLE_MANAGER]:
            return Response(
                {"detail": "Accès refusé."},
                status=status.HTTP_403_FORBIDDEN,
            )

        current_year = timezone.now().year
        seuil_stock = Decimal(str(request.query_params.get("seuil_stock", "5.000")))

        stock_brut = MatierePremiereStock.objects.select_related(
            "bijouterie", "purete"
        )

        stock_raffine = StockRaffine.objects.select_related(
            "bijouterie", "purete"
        )

        mouvements = MatierePremiereMovement.objects.select_related(
            "bijouterie", "purete"
        ).filter(created_at__year=current_year)

        achats = AchatMatierePremiere.objects.filter(
            status=AchatMatierePremiere.STATUS_CONFIRMED,
            payment_status=AchatMatierePremiere.PAYMENT_PAID,
            created_at__year=current_year,
        )

        rachats = RachatClient.objects.filter(
            status=RachatClient.STATUS_CONFIRMED,
            payment_status=RachatClient.PAYMENT_PAID,
            created_at__year=current_year,
        )

        raffinages = Raffinage.objects.filter(created_at__year=current_year)

        ventes = VenteMatierePremiere.objects.filter(created_at__year=current_year)

        if role == ROLE_MANAGER:
            manager_profile = getattr(user, "manager_profile", None)

            if not manager_profile:
                return Response(
                    {"detail": "Aucune bijouterie associée à ce manager."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            bijouteries = manager_profile.bijouteries.all()

            stock_brut = stock_brut.filter(bijouterie__in=bijouteries)
            stock_raffine = stock_raffine.filter(bijouterie__in=bijouteries)
            mouvements = mouvements.filter(bijouterie__in=bijouteries)
            achats = achats.filter(bijouterie__in=bijouteries)
            rachats = rachats.filter(bijouterie__in=bijouteries)
            raffinages = raffinages.filter(bijouterie__in=bijouteries)
            ventes = ventes.filter(bijouterie__in=bijouteries)

        bijouterie_id = request.query_params.get("bijouterie_id")

        if bijouterie_id:
            stock_brut = stock_brut.filter(bijouterie_id=bijouterie_id)
            stock_raffine = stock_raffine.filter(bijouterie_id=bijouterie_id)
            mouvements = mouvements.filter(bijouterie_id=bijouterie_id)
            achats = achats.filter(bijouterie_id=bijouterie_id)
            rachats = rachats.filter(bijouterie_id=bijouterie_id)
            raffinages = raffinages.filter(bijouterie_id=bijouterie_id)
            ventes = ventes.filter(bijouterie_id=bijouterie_id)

        stock_brut_total = stock_brut.aggregate(
            total=Coalesce(Sum("poids_total"), Decimal("0.000"))
        )["total"]

        stock_raffine_total = stock_raffine.aggregate(
            total=Coalesce(Sum("poids_total"), Decimal("0.000"))
        )["total"]

        achats_stats = achats.aggregate(
            total=Count("id"),
            montant=Coalesce(Sum("montant_total"), Decimal("0.00")),
        )

        rachats_stats = rachats.aggregate(
            total=Count("id"),
            montant=Coalesce(Sum("montant_total"), Decimal("0.00")),
        )

        ventes_stats = ventes.aggregate(
            total=Count("id"),
            montant=Coalesce(Sum("montant_total"), Decimal("0.00")),
            poids=Coalesce(Sum("poids"), Decimal("0.000")),
        )

        raffinage_stats = raffinages.aggregate(
            total=Count("id"),
            poids_entree=Coalesce(Sum("poids_entree"), Decimal("0.000")),
            poids_sortie=Coalesce(Sum("poids_sortie"), Decimal("0.000")),
            perte=Coalesce(Sum("perte"), Decimal("0.000")),
        )

        stock_brut_detail = stock_brut.values(
            "bijouterie__nom",
            "matiere",
            "purete__purete",
        ).annotate(
            poids_total=Coalesce(Sum("poids_total"), Decimal("0.000"))
        ).order_by("bijouterie__nom", "matiere", "purete__purete")

        stock_raffine_detail = stock_raffine.values(
            "bijouterie__nom",
            "matiere",
            "purete__purete",
        ).annotate(
            poids_total=Coalesce(Sum("poids_total"), Decimal("0.000"))
        ).order_by("bijouterie__nom", "matiere", "purete__purete")

        mouvements_par_source = mouvements.values(
            "source"
        ).annotate(
            total=Count("id"),
            poids_total=Coalesce(Sum("poids"), Decimal("0.000")),
        ).order_by("source")

        mouvements_par_mois = mouvements.annotate(
            mois=ExtractMonth("created_at")
        ).values(
            "mois"
        ).annotate(
            total=Count("id"),
            poids_total=Coalesce(Sum("poids"), Decimal("0.000")),
        ).order_by("mois")

        ventes_par_source = ventes.values(
            "source_stock"
        ).annotate(
            total=Count("id"),
            poids_total=Coalesce(Sum("poids"), Decimal("0.000")),
            montant_total=Coalesce(Sum("montant_total"), Decimal("0.00")),
        ).order_by("source_stock")

        alertes = []

        for stock in stock_brut.filter(poids_total__lte=seuil_stock):
            alertes.append({
                "type": "stock_brut_faible",
                "bijouterie": str(stock.bijouterie),
                "matiere": stock.matiere,
                "purete": str(stock.purete),
                "poids_total": stock.poids_total,
            })

        for stock in stock_raffine.filter(poids_total__lte=seuil_stock):
            alertes.append({
                "type": "stock_raffine_faible",
                "bijouterie": str(stock.bijouterie),
                "matiere": stock.matiere,
                "purete": str(stock.purete),
                "poids_total": stock.poids_total,
            })

        return Response({
            "annee": current_year,
            "resume": {
                "stock_brut_total": stock_brut_total,
                "stock_raffine_total": stock_raffine_total,
                "total_achats_annee": achats_stats["total"],
                "montant_achats_annee": achats_stats["montant"],
                "total_rachats_annee": rachats_stats["total"],
                "montant_rachats_annee": rachats_stats["montant"],
                "total_ventes_annee": ventes_stats["total"],
                "poids_vendu_annee": ventes_stats["poids"],
                "montant_ventes_annee": ventes_stats["montant"],
                "total_raffinages_annee": raffinage_stats["total"],
            },
            "stock": {
                "brut": list(stock_brut_detail),
                "raffine": list(stock_raffine_detail),
            },
            "mouvements": {
                "par_source": list(mouvements_par_source),
                "evolution_mensuelle": list(mouvements_par_mois),
            },
            "raffinage": {
                "poids_entree": raffinage_stats["poids_entree"],
                "poids_sortie": raffinage_stats["poids_sortie"],
                "perte": raffinage_stats["perte"],
            },
            "ventes": {
                "par_source": list(ventes_par_source),
            },
            "alertes": alertes,
        }, status=status.HTTP_200_OK)
        
    
    
class DashboardMatierePremiereView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        role = get_role_name(user)

        if role not in [ROLE_ADMIN, ROLE_MANAGER]:
            return Response({"detail": "Accès refusé"}, status=403)

        current_year = timezone.now().year
        year_param = request.query_params.get("year")
        bijouterie_id = request.query_params.get("bijouterie_id")

        # =========================
        # Validation year
        # =========================
        if year_param:
            try:
                year = int(year_param)
            except ValueError:
                return Response({"detail": "year invalide"}, status=400)
        else:
            year = current_year

        # =========================
        # Querysets
        # =========================
        stock_brut_qs = MatierePremiereStock.objects.all()
        stock_raffine_qs = StockRaffine.objects.all()
        mouvement_qs = MatierePremiereMovement.objects.all()
        achat_qs = AchatMatierePremiere.objects.all()
        rachat_qs = RachatClient.objects.all()
        raffinage_qs = Raffinage.objects.all()
        vente_qs = VenteMatierePremiere.objects.all()

        # =========================
        # Scope manager
        # =========================
        if role == ROLE_MANAGER:
            manager_profile = getattr(user, "manager_profile", None)

            if not manager_profile:
                return Response({"detail": "Aucune bijouterie"}, status=400)

            bijouteries = manager_profile.bijouteries.all()

            stock_brut_qs = stock_brut_qs.filter(bijouterie__in=bijouteries)
            stock_raffine_qs = stock_raffine_qs.filter(bijouterie__in=bijouteries)
            mouvement_qs = mouvement_qs.filter(bijouterie__in=bijouteries)
            achat_qs = achat_qs.filter(bijouterie__in=bijouteries)
            rachat_qs = rachat_qs.filter(bijouterie__in=bijouteries)
            raffinage_qs = raffinage_qs.filter(bijouterie__in=bijouteries)
            vente_qs = vente_qs.filter(bijouterie__in=bijouteries)

        # =========================
        # Filtre bijouterie
        # =========================
        if bijouterie_id:
            try:
                bijouterie_id = int(bijouterie_id)
            except ValueError:
                return Response({"detail": "bijouterie_id invalide"}, status=400)

            stock_brut_qs = stock_brut_qs.filter(bijouterie_id=bijouterie_id)
            stock_raffine_qs = stock_raffine_qs.filter(bijouterie_id=bijouterie_id)
            mouvement_qs = mouvement_qs.filter(bijouterie_id=bijouterie_id)
            achat_qs = achat_qs.filter(bijouterie_id=bijouterie_id)
            rachat_qs = rachat_qs.filter(bijouterie_id=bijouterie_id)
            raffinage_qs = raffinage_qs.filter(bijouterie_id=bijouterie_id)
            vente_qs = vente_qs.filter(bijouterie_id=bijouterie_id)

        # =========================
        # Filtre année
        # =========================
        mouvement_qs = mouvement_qs.filter(created_at__year=year)
        achat_qs = achat_qs.filter(created_at__year=year)
        rachat_qs = rachat_qs.filter(created_at__year=year)
        raffinage_qs = raffinage_qs.filter(created_at__year=year)
        vente_qs = vente_qs.filter(created_at__year=year)

        # =========================
        # Résumé
        # =========================
        stock_brut_total = stock_brut_qs.aggregate(
            total=Coalesce(Sum("poids_total"), Decimal("0.000"))
        )["total"]

        stock_raffine_total = stock_raffine_qs.aggregate(
            total=Coalesce(Sum("poids_total"), Decimal("0.000"))
        )["total"]

        resume = {
            "stock_brut_total": stock_brut_total,
            "stock_raffine_total": stock_raffine_total,
            "total_achats": achat_qs.count(),
            "total_rachats": rachat_qs.count(),
            "total_ventes": vente_qs.count(),
            "total_raffinages": raffinage_qs.count(),
        }

        # =========================
        # Mouvements par source
        # =========================
        mouvements_par_source = mouvement_qs.values("source").annotate(
            total=Count("id"),
            poids_total=Coalesce(Sum("poids"), Decimal("0.000")),
        )

        # =========================
        # Evolution mensuelle
        # =========================
        evolution = mouvement_qs.annotate(
            mois=ExtractMonth("created_at")
        ).values("mois").annotate(
            poids=Coalesce(Sum("poids"), Decimal("0.000"))
        ).order_by("mois")

        # =========================
        # Raffinage
        # =========================
        raffinage_stats = raffinage_qs.aggregate(
            entree=Coalesce(Sum("poids_entree"), Decimal("0.000")),
            sortie=Coalesce(Sum("poids_sortie"), Decimal("0.000")),
            perte=Coalesce(Sum("perte"), Decimal("0.000")),
        )

        # =========================
        # Vente
        # =========================
        ventes_stats = vente_qs.values("source_stock").annotate(
            poids=Coalesce(Sum("poids"), Decimal("0.000")),
            montant=Coalesce(Sum("montant_total"), Decimal("0.00")),
        )

        # =========================
        # Alertes
        # =========================
        seuil = Decimal("5.000")

        alertes = []

        for s in stock_brut_qs.filter(poids_total__lte=seuil):
            alertes.append({
                "type": "stock_brut_faible",
                "bijouterie": str(s.bijouterie),
                "matiere": s.matiere,
                "purete": str(s.purete),
                "poids": s.poids_total,
            })

        for s in stock_raffine_qs.filter(poids_total__lte=seuil):
            alertes.append({
                "type": "stock_raffine_faible",
                "bijouterie": str(s.bijouterie),
                "matiere": s.matiere,
                "purete": str(s.purete),
                "poids": s.poids_total,
            })

        # =========================
        # RESPONSE
        # =========================
        return Response({
            "annee": year,
            "resume": resume,
            "mouvements": list(mouvements_par_source),
            "evolution_mensuelle": list(evolution),
            "raffinage": raffinage_stats,
            "ventes": list(ventes_stats),
            "alertes": alertes,
        })
    



class ExportDashboardMatierePremiereExcelView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        role = get_role_name(user)

        current_year = timezone.now().year
        mode = request.query_params.get("mode", "single")
        bijouterie_id = request.query_params.get("bijouterie_id")

        # =========================
        # Gestion années
        # =========================
        if mode == "multi":
            years = [current_year, current_year - 1, current_year - 2]
        else:
            years = [current_year]

        # =========================
        # Gestion scope bijouterie
        # =========================
        stock_brut_qs = MatierePremiereStock.objects.all()
        stock_raffine_qs = StockRaffine.objects.all()
        mouvement_qs = MatierePremiereMovement.objects.all()
        achat_qs = AchatMatierePremiere.objects.all()
        rachat_qs = RachatClient.objects.all()
        raffinage_qs = Raffinage.objects.all()
        vente_qs = VenteMatierePremiere.objects.all()

        if role == ROLE_MANAGER:
            manager_profile = getattr(user, "manager_profile", None)
            if not manager_profile:
                return Response({"detail": "Aucune bijouterie."}, status=400)

            bijouteries = manager_profile.bijouteries.all()

            stock_brut_qs = stock_brut_qs.filter(bijouterie__in=bijouteries)
            stock_raffine_qs = stock_raffine_qs.filter(bijouterie__in=bijouteries)
            mouvement_qs = mouvement_qs.filter(bijouterie__in=bijouteries)
            achat_qs = achat_qs.filter(bijouterie__in=bijouteries)
            rachat_qs = rachat_qs.filter(bijouterie__in=bijouteries)
            raffinage_qs = raffinage_qs.filter(bijouterie__in=bijouteries)
            vente_qs = vente_qs.filter(bijouterie__in=bijouteries)

        # filtre spécifique
        if bijouterie_id:
            stock_brut_qs = stock_brut_qs.filter(bijouterie_id=bijouterie_id)
            stock_raffine_qs = stock_raffine_qs.filter(bijouterie_id=bijouterie_id)
            mouvement_qs = mouvement_qs.filter(bijouterie_id=bijouterie_id)
            achat_qs = achat_qs.filter(bijouterie_id=bijouterie_id)
            rachat_qs = rachat_qs.filter(bijouterie_id=bijouterie_id)
            raffinage_qs = raffinage_qs.filter(bijouterie_id=bijouterie_id)
            vente_qs = vente_qs.filter(bijouterie_id=bijouterie_id)

        wb = Workbook()
        wb.remove(wb.active)

        bold = Font(bold=True)

        # =========================
        # LOOP ANNEES
        # =========================
        for year in years:
            ws = wb.create_sheet(title=str(year))
            row = 1

            def write_title(title):
                nonlocal row
                ws.cell(row=row, column=1, value=title).font = bold
                row += 1

            def write_row(values):
                nonlocal row
                for col, val in enumerate(values, 1):
                    ws.cell(row=row, column=col, value=val)
                row += 1

            # =========================
            # 1. Résumé
            # =========================
            write_title(f"1. Résumé {year}")

            stock_brut_total = stock_brut_qs.aggregate(
                total=Coalesce(Sum("poids_total"), Decimal("0.000"))
            )["total"]

            stock_raffine_total = stock_raffine_qs.aggregate(
                total=Coalesce(Sum("poids_total"), Decimal("0.000"))
            )["total"]

            achats = achat_qs.filter(created_at__year=year)
            rachats = rachat_qs.filter(created_at__year=year)
            ventes = vente_qs.filter(created_at__year=year)
            raffinages = raffinage_qs.filter(created_at__year=year)

            write_row(["Stock brut total", stock_brut_total])
            write_row(["Stock raffiné total", stock_raffine_total])
            write_row(["Total achats", achats.count()])
            write_row(["Total rachats", rachats.count()])
            write_row(["Total ventes", ventes.count()])
            write_row(["Total raffinages", raffinages.count()])

            row += 2

            # =========================
            # 2. Stock brut
            # =========================
            write_title("2. Stock brut")

            write_row(["Bijouterie", "Matière", "Pureté", "Poids"])

            for s in stock_brut_qs:
                write_row([
                    str(s.bijouterie),
                    s.matiere,
                    str(s.purete),
                    s.poids_total
                ])

            row += 2

            # =========================
            # Stock raffiné
            # =========================
            write_title("Stock raffiné")

            write_row(["Bijouterie", "Matière", "Pureté", "Poids"])

            for s in stock_raffine_qs:
                write_row([
                    str(s.bijouterie),
                    s.matiere,
                    str(s.purete),
                    s.poids_total
                ])

            row += 2

            # =========================
            # 3. Mouvements
            # =========================
            write_title("3. Mouvements")

            mouvements = mouvement_qs.filter(created_at__year=year)

            write_row(["Source", "Poids"])

            par_source = mouvements.values("source").annotate(
                poids=Coalesce(Sum("poids"), Decimal("0.000"))
            )

            for m in par_source:
                write_row([m["source"], m["poids"]])

            row += 2

            # =========================
            # 4. Raffinage
            # =========================
            write_title("4. Raffinage")

            stats = raffinages.aggregate(
                entree=Coalesce(Sum("poids_entree"), Decimal("0.000")),
                sortie=Coalesce(Sum("poids_sortie"), Decimal("0.000")),
                perte=Coalesce(Sum("perte"), Decimal("0.000")),
            )

            write_row(["Entrée", stats["entree"]])
            write_row(["Sortie", stats["sortie"]])
            write_row(["Perte", stats["perte"]])

            row += 2

            # =========================
            # 5. Vente
            # =========================
            write_title("5. Vente matière")

            ventes_stats = ventes.values("source_stock").annotate(
                poids=Coalesce(Sum("poids"), Decimal("0.000")),
                montant=Coalesce(Sum("montant_total"), Decimal("0.00")),
            )

            write_row(["Type", "Poids", "Montant"])

            for v in ventes_stats:
                write_row([v["source_stock"], v["poids"], v["montant"]])

            row += 2

            # =========================
            # 6. Alertes
            # =========================
            write_title("6. Alertes")

            seuil = Decimal("5.000")

            write_row(["Type", "Bijouterie", "Matière", "Pureté", "Poids"])

            for s in stock_brut_qs.filter(poids_total__lte=seuil):
                write_row(["Brut faible", str(s.bijouterie), s.matiere, str(s.purete), s.poids_total])

            for s in stock_raffine_qs.filter(poids_total__lte=seuil):
                write_row(["Raffiné faible", str(s.bijouterie), s.matiere, str(s.purete), s.poids_total])

        # =========================
        # EXPORT
        # =========================
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        filename = "dashboard_matiere.xlsx"
        if mode == "multi":
            filename = "dashboard_matiere_3_ans.xlsx"

        if bijouterie_id:
            filename = f"dashboard_matiere_bijouterie_{bijouterie_id}.xlsx"

        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        wb.save(response)
        return response


