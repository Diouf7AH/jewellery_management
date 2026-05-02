# from datetime import timedelta
# from decimal import Decimal

# from django.db import transaction
# from django.db.models import Count, Sum
# from django.http import HttpResponse
# from django.shortcuts import get_object_or_404
# from django.utils import timezone
# from django.utils.dateparse import parse_date
# from drf_yasg import openapi
# from drf_yasg.utils import swagger_auto_schema
# from openpyxl import Workbook
# from rest_framework import status
# from rest_framework.permissions import IsAuthenticated
# from rest_framework.response import Response
# from rest_framework.views import APIView

# from backend.roles import ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR, get_role_name
# from store.models import Bijouterie

# from .models import (AchatMatierePremiere, MatierePremiereMovement,
#                      MatierePremiereStock, RachatClient)
# from .pdf.fiche_rachat_client_a4 import build_fiche_rachat_client_a4_pdf
# from .serializers import (AchatMatierePremiereCreateSerializer,
#                           RachatClientCreateSerializer,
#                           RachatClientDetailSerializer)


# def get_user_bijouterie(user, request=None):
#     role = get_role_name(user)

#     if role == ROLE_VENDOR:
#         profile = getattr(user, "staff_vendor_profile", None)
#         return profile.bijouterie if profile else None

#     if role == ROLE_MANAGER:
#         profile = getattr(user, "staff_manager_profile", None)
#         return profile.bijouteries.first() if profile else None

#     if role == ROLE_ADMIN:
#         bijouterie_id = request.data.get("bijouterie_id") if request else None

#         if not bijouterie_id:
#             return None

#         return Bijouterie.objects.filter(id=bijouterie_id).first()

#     return None


# class RachatClientCreateView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Créer un rachat client",
#         operation_description="""
# Créer un rachat client avec plusieurs lignes.

# Règles :
# - Accessible aux rôles ADMIN, MANAGER et VENDOR.
# - Pour VENDOR : la bijouterie vient automatiquement du vendeur connecté.
# - Pour MANAGER : la bijouterie vient automatiquement de ses bijouteries.
# - Pour ADMIN : bijouterie_id est obligatoire dans le payload.
# - Le téléphone du client est obligatoire.
# - Si le client existe, il est récupéré par téléphone.
# - Si le client n'existe pas, il est créé automatiquement.
# - Chaque ligne met à jour MatierePremiereStock.
# - Chaque ligne crée un MatierePremiereMovement.
# - Le montant_total est le montant négocié global du rachat.
#         """,
#         request_body=RachatClientCreateSerializer,
#         responses={
#             201: RachatClientDetailSerializer,
#             400: "Erreur de validation",
#             403: "Accès refusé",
#         },
#         tags=["Rachat Client"],
#     )
#     @transaction.atomic
#     def post(self, request):
#         role = get_role_name(request.user)

#         if role not in [ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR]:
#             return Response(
#                 {
#                     "detail": "Seuls les administrateurs, managers et vendeurs peuvent effectuer un rachat client."
#                 },
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         bijouterie = get_user_bijouterie(request.user, request)

#         if not bijouterie:
#             return Response(
#                 {
#                     "detail": "Aucune bijouterie trouvée. Pour un admin, le champ bijouterie_id est obligatoire."
#                 },
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         serializer = RachatClientCreateSerializer(
#             data=request.data,
#             context={
#                 "request": request,
#                 "bijouterie": bijouterie,
#             },
#         )
#         serializer.is_valid(raise_exception=True)
#         rachat = serializer.save()

#         return Response(
#             RachatClientDetailSerializer(rachat).data,
#             status=status.HTTP_201_CREATED,
#         )  


# class RachatClientFichePDFView(APIView):
#     permission_classes = [IsAuthenticated]

#     def get(self, request, rachat_id):
#         rachat = get_object_or_404(
#             RachatClient.objects.select_related("client", "bijouterie").prefetch_related("items"),
#             id=rachat_id,
#         )

#         pdf = build_fiche_rachat_client_a4_pdf(rachat)

#         response = HttpResponse(pdf, content_type="application/pdf")
#         response["Content-Disposition"] = f'inline; filename="fiche-rachat-{rachat.id}.pdf"'
#         return response


# # fournissuer
# class AchatMatierePremiereCreateView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Créer un achat matière première",
#         operation_description="""
# Créer un achat matière première fournisseur.

# Règles :
# - Accessible ADMIN et MANAGER
# - Met à jour le stock matière première
# - Crée les mouvements
#         """,
#         request_body=AchatMatierePremiereCreateSerializer,
#         tags=["Achat Matière Première"],
#     )
#     @transaction.atomic
#     def post(self, request):
#         role = get_role_name(request.user)

#         if role not in [ROLE_ADMIN, ROLE_MANAGER]:
#             return Response(
#                 {"detail": "Seuls les admins et managers peuvent effectuer cet achat."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         bijouterie = get_user_bijouterie(request.user, request)

#         if not bijouterie:
#             return Response(
#                 {
#                     "detail": "Aucune bijouterie trouvée. Pour un admin, le champ bijouterie_id est obligatoire."
#                 },
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         serializer = AchatMatierePremiereCreateSerializer(
#             data=request.data,
#             context={
#                 "bijouterie": bijouterie
#             }
#         )

#         serializer.is_valid(raise_exception=True)
#         achat = serializer.save()

#         return Response(
#             {"message": "Achat matière première enregistré avec succès"},
#             status=status.HTTP_201_CREATED,
#         )
    


# def three_years_start_date():
#     current_year = timezone.now().year
#     return timezone.datetime(
#         current_year - 2, 1, 1,
#         tzinfo=timezone.get_current_timezone()
#     )


# class ExportMatierePremiereMovementsExcelView(APIView):
#     permission_classes = [IsAuthenticated]

#     def get(self, request):
#         role = get_role_name(request.user)

#         if role not in [ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR]:
#             return Response(
#                 {"detail": "Accès refusé."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         start_date = three_years_start_date()

#         queryset = (
#             MatierePremiereMovement.objects
#             .filter(created_at__gte=start_date)
#             .select_related(
#                 "bijouterie",
#                 "purete",
#                 "rachat",
#                 "rachat__client",
#                 "achat",
#                 "achat__fournisseur",
#             )
#             .order_by("-created_at")
#         )

#         wb = Workbook()
#         ws = wb.active
#         ws.title = "Mouvements Matière"

#         # 🔥 En-têtes
#         ws.append([
#             "Date",
#             "Bijouterie",
#             "Source",
#             "Type",
#             "Client",
#             "Téléphone client",
#             "Fournisseur",
#             "Téléphone fournisseur",
#             "Matière",
#             "Pureté",
#             "Poids (g)",
#         ])

#         for mv in queryset:
#             rachat = mv.rachat
#             achat = mv.achat

#             client = rachat.client if rachat else None
#             fournisseur = achat.fournisseur if achat else None

#             ws.append([
#                 mv.created_at.strftime("%d/%m/%Y %H:%M"),
#                 str(mv.bijouterie),
#                 mv.source,
#                 "Rachat client" if rachat else "Achat fournisseur",
#                 str(client) if client else "",
#                 getattr(client, "telephone", "") if client else "",
#                 str(fournisseur) if fournisseur else "",
#                 getattr(fournisseur, "telephone", "") if fournisseur else "",
#                 mv.matiere,
#                 str(mv.purete),
#                 float(mv.poids),
#             ])

#         response = HttpResponse(
#             content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
#         )
#         response["Content-Disposition"] = 'attachment; filename="mouvements_matiere_3_ans.xlsx"'

#         wb.save(response)
#         return response




# def decimal_value(value):
#     return value or Decimal("0.000")


# def get_user_bijouteries(user, request):
#     role = get_role_name(user)

#     if role == ROLE_VENDOR:
#         profile = getattr(user, "staff_vendor_profile", None)
#         return [profile.bijouterie] if profile and profile.bijouterie else []

#     if role == ROLE_MANAGER:
#         profile = getattr(user, "staff_manager_profile", None)
#         return list(profile.bijouteries.all()) if profile else []

#     if role == ROLE_ADMIN:
#         bijouterie_id = request.query_params.get("bijouterie_id")
#         if bijouterie_id:
#             bijouterie = Bijouterie.objects.filter(id=bijouterie_id).first()
#             return [bijouterie] if bijouterie else []
#         return list(Bijouterie.objects.all())

#     return []


# class DashboardMatierePremiereView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Dashboard stock matière première",
#         operation_description="""
# Dashboard du stock matière première.

# Par défaut :
# - filtre sur l'année en cours
# - total stock actuel
# - total entrées période
# - total par matière/pureté
# - valeur totale des rachats et achats fournisseur

# Filtres :
# - start_date=YYYY-MM-DD
# - end_date=YYYY-MM-DD
# - bijouterie_id=1 uniquement utile pour admin
#         """,
#         manual_parameters=[
#             openapi.Parameter("start_date", openapi.IN_QUERY, type=openapi.TYPE_STRING),
#             openapi.Parameter("end_date", openapi.IN_QUERY, type=openapi.TYPE_STRING),
#             openapi.Parameter("bijouterie_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
#         ],
#         tags=["Dashboard Matière Première"],
#     )
#     def get(self, request):
#         role = get_role_name(request.user)

#         if role not in [ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR]:
#             return Response(
#                 {"detail": "Accès refusé."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         today = timezone.localdate()
#         start_date = parse_date(request.query_params.get("start_date", "")) or today.replace(month=1, day=1)
#         end_date = parse_date(request.query_params.get("end_date", "")) or today

#         start_dt = timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time()))
#         end_dt = timezone.make_aware(timezone.datetime.combine(end_date, timezone.datetime.max.time()))

#         bijouteries = get_user_bijouteries(request.user, request)

#         if not bijouteries:
#             return Response(
#                 {"detail": "Aucune bijouterie trouvée."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         bijouterie_ids = [b.id for b in bijouteries]

#         stocks = MatierePremiereStock.objects.filter(
#             bijouterie_id__in=bijouterie_ids
#         ).select_related("bijouterie", "purete")

#         movements = MatierePremiereMovement.objects.filter(
#             bijouterie_id__in=bijouterie_ids,
#             created_at__range=(start_dt, end_dt),
#         ).select_related("bijouterie", "purete")

#         rachats = RachatClient.objects.filter(
#             bijouterie_id__in=bijouterie_ids,
#             created_at__range=(start_dt, end_dt),
#         )

#         achats = AchatMatierePremiere.objects.filter(
#             bijouterie_id__in=bijouterie_ids,
#             created_at__range=(start_dt, end_dt),
#         )

#         total_stock_actuel = stocks.aggregate(
#             total=Sum("poids_total")
#         )["total"] or Decimal("0.000")

#         total_entrees_periode = movements.aggregate(
#             total=Sum("poids")
#         )["total"] or Decimal("0.000")

#         total_rachats = rachats.aggregate(
#             total=Sum("montant_total"),
#             count=Count("id"),
#         )

#         total_achats = achats.aggregate(
#             total=Sum("montant_total"),
#             count=Count("id"),
#         )

#         stock_par_purete = (
#             stocks.values(
#                 "matiere",
#                 "purete_id",
#                 "purete__purete",
#             )
#             .annotate(total_poids=Sum("poids_total"))
#             .order_by("matiere", "purete__purete")
#         )

#         entrees_par_purete = (
#             movements.values(
#                 "matiere",
#                 "purete_id",
#                 "purete__purete",
#                 "source",
#             )
#             .annotate(total_poids=Sum("poids"), nombre=Count("id"))
#             .order_by("matiere", "purete__purete", "source")
#         )

#         return Response({
#             "periode": {
#                 "start_date": str(start_date),
#                 "end_date": str(end_date),
#             },
#             "bijouteries": [
#                 {"id": b.id, "nom": str(b)} for b in bijouteries
#             ],
#             "resume": {
#                 "total_stock_actuel_poids": total_stock_actuel,
#                 "total_entrees_periode_poids": total_entrees_periode,
#                 "nombre_rachats": total_rachats["count"] or 0,
#                 "valeur_rachats": total_rachats["total"] or Decimal("0.00"),
#                 "nombre_achats_fournisseur": total_achats["count"] or 0,
#                 "valeur_achats_fournisseur": total_achats["total"] or Decimal("0.00"),
#                 "valeur_totale_entrees": (
#                     (total_rachats["total"] or Decimal("0.00")) +
#                     (total_achats["total"] or Decimal("0.00"))
#                 ),
#             },
#             "stock_actuel_par_purete": list(stock_par_purete),
#             "entrees_periode_par_purete": list(entrees_par_purete),
#         })



# class CancelRachatClientView(APIView):
#     permission_classes = [IsAuthenticated]

#     @transaction.atomic
#     def post(self, request, rachat_id):
#         role = get_role_name(request.user)

#         if role not in [ROLE_ADMIN, ROLE_MANAGER]:
#             return Response({"detail": "Accès refusé."}, status=403)

#         rachat = get_object_or_404(
#             RachatClient.objects.prefetch_related("items__purete"),
#             id=rachat_id
#         )

#         # 🔒 Déjà annulé
#         if rachat.status == RachatClient.STATUS_CANCELLED:
#             return Response({"detail": "Rachat déjà annulé."}, status=400)

#         # ⏱️ Vérification 48h
#         if timezone.now() - rachat.created_at > timedelta(hours=48):
#             return Response(
#                 {"detail": "Annulation impossible après 48h."},
#                 status=400
#             )

#         reason = request.data.get("reason", "")

#         for item in rachat.items.all():
#             stock = MatierePremiereStock.objects.select_for_update().get(
#                 bijouterie=rachat.bijouterie,
#                 matiere=item.matiere,
#                 purete=item.purete,
#             )

#             # 🔻 Retirer du stock
#             stock.poids_total -= item.poids

#             if stock.poids_total < 0:
#                 return Response(
#                     {"detail": "Stock insuffisant pour annuler."},
#                     status=400
#                 )

#             stock.save()

#             # 🔁 Movement inverse
#             MatierePremiereMovement.objects.create(
#                 stock=stock,
#                 bijouterie=rachat.bijouterie,
#                 matiere=item.matiere,
#                 purete=item.purete,
#                 poids=item.poids,
#                 source=MatierePremiereMovement.SOURCE_RACHAT_CLIENT_CANCEL,
#                 rachat=rachat,
#             )

#         # ✅ Mise à jour statut
#         rachat.status = RachatClient.STATUS_CANCELLED
#         rachat.cancelled_at = timezone.now()
#         rachat.cancelled_by = request.user
#         rachat.cancel_reason = reason
#         rachat.save()

#         return Response({"message": "Rachat annulé avec succès"})


# class CancelAchatMatierePremiereView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Annuler un achat matière première",
#         operation_description="""
#         Annule un achat matière première fournisseur.

#         Règles :
#         - Seul admin ou manager peut annuler.
#         - Impossible si déjà annulé.
#         - Annulation autorisée seulement dans les 48h.
#         - Le stock matière première est diminué.
#         - Un mouvement inverse est créé pour chaque ligne.
#         """,
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             properties={
#                 "reason": openapi.Schema(
#                     type=openapi.TYPE_STRING,
#                     description="Motif de l'annulation",
#                     example="Erreur de saisie sur le poids",
#                 )
#             },
#         ),
#         responses={
#             200: openapi.Response("Achat matière première annulé avec succès"),
#             400: "Erreur métier",
#             403: "Accès refusé",
#             404: "Achat introuvable",
#         },
#         tags=["Matière première - Achat fournisseur"],
#     )
#     @transaction.atomic
#     def post(self, request, achat_id):
#         role = get_role_name(request.user)

#         if role not in [ROLE_ADMIN, ROLE_MANAGER]:
#             return Response(
#                 {"detail": "Accès refusé."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         achat = get_object_or_404(
#             AchatMatierePremiere.objects
#             .select_for_update()
#             .prefetch_related("items__purete"),
#             id=achat_id,
#         )

#         if achat.status == AchatMatierePremiere.STATUS_CANCELLED:
#             return Response(
#                 {"detail": "Cet achat matière première est déjà annulé."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         if timezone.now() - achat.created_at > timedelta(hours=48):
#             return Response(
#                 {"detail": "Annulation impossible après 48h."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         reason = request.data.get("reason", "").strip()

#         created_movements = []

#         for item in achat.items.all():
#             stock = get_object_or_404(
#                 MatierePremiereStock.objects.select_for_update(),
#                 bijouterie=achat.bijouterie,
#                 matiere=item.matiere,
#                 purete=item.purete,
#             )

#             if stock.poids_total < item.poids:
#                 return Response(
#                     {
#                         "detail": (
#                             f"Stock insuffisant pour annuler cette ligne : "
#                             f"{item.matiere} / {item.purete}. "
#                             f"Stock actuel : {stock.poids_total} g, "
#                             f"à retirer : {item.poids} g."
#                         )
#                     },
#                     status=status.HTTP_400_BAD_REQUEST,
#                 )

#             stock.poids_total -= item.poids
#             stock.save(update_fields=["poids_total", "updated_at"])

#             movement = MatierePremiereMovement.objects.create(
#                 stock=stock,
#                 bijouterie=achat.bijouterie,
#                 matiere=item.matiere,
#                 purete=item.purete,
#                 poids=item.poids,
#                 source=MatierePremiereMovement.SOURCE_ACHAT_FOURNISSEUR_CANCEL,
#                 achat=achat,
#             )

#             created_movements.append(movement.id)

#         achat.status = AchatMatierePremiere.STATUS_CANCELLED
#         achat.cancelled_at = timezone.now()
#         achat.cancelled_by = request.user
#         achat.cancel_reason = reason
#         achat.save(
#             update_fields=[
#                 "status",
#                 "cancelled_at",
#                 "cancelled_by",
#                 "cancel_reason",
#             ]
#         )

#         return Response(
#             {
#                 "detail": "Achat matière première annulé avec succès.",
#                 "achat_id": achat.id,
#                 "status": achat.status,
#                 "cancelled_at": achat.cancelled_at,
#                 "cancelled_by": request.user.id,
#                 "cancel_reason": achat.cancel_reason,
#                 "movements_created": created_movements,
#             },
#             status=status.HTTP_200_OK,
#         )
    
    

from datetime import timedelta
from io import BytesIO

from django.db import transaction
from django.db.models import F
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
from stock_matiere_premiere.serializers import (CancelRachatClientSerializer,
                                                RachatClientCreateSerializer,
                                                RachatClientDetailSerializer,
                                                ReverseRachatClientSerializer)

from .models import MatierePremiereMovement, MatierePremiereStock, RachatClient
from .pdf.attestation_rachat_client_pdf import \
    build_attestation_rachat_client_pdf
from .pdf.ticket_rachat_client_58mm import build_rachat_client_ticket_58mm


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
    

    

