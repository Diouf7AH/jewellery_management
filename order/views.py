# order/views.py
from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.roles import get_role_name
from sale.models import Facture, PaiementLigne

from .models import CommandeClient, Ouvrier
from .serializers import (AssignerOuvrierSerializer,
                          CommandeClientDetailSerializer,
                          CommandeDashboardRecentSerializer,
                          CommandeDashboardSerializer,
                          CreateCommandeClientSerializer,
                          OuvrierDashboardSerializer,
                          PayerSoldeCommandeSerializer,
                          TerminerCommandeSerializer)
from .services.commande_finance_service import (
    create_facture_finale_for_commande, register_facture_payment)
from .services.commande_pdf_service import generate_bon_commande_pdf
from .services.commande_workflow_service import (assigner_ouvrier_commande,
                                                 livrer_commande,
                                                 terminer_commande)


def can_access_commande(user, commande: CommandeClient) -> bool:
    role = get_role_name(user)

    if role == "admin":
        return True

    if role == "manager":
        return commande.bijouterie in user.staff_manager_profile.bijouteries.all()

    if role == "cashier":
        return commande.bijouterie_id == getattr(user.staff_cashier_profile, "bijouterie_id", None)

    if role == "vendor":
        return getattr(commande.vendor, "user_id", None) == user.id

    return False


class CommandeClientCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Créer une commande client",
        operation_description="""
Crée une commande client avec :
- lignes de commande
- paiement acompte accepté de 50% à 100%
- facture d'acompte automatique
- historique initial
""",
        request_body=CreateCommandeClientSerializer,
        responses={201: CommandeClientDetailSerializer},
    )
    @transaction.atomic
    def post(self, request):
        serializer = CreateCommandeClientSerializer(
            data=request.data,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        commande = serializer.save()

        return Response(
            {
                "message": "Commande client créée avec succès.",
                "commande": CommandeClientDetailSerializer(commande).data,
            },
            status=status.HTTP_201_CREATED,
        )


class CommandeClientListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CommandeClientDetailSerializer

    @swagger_auto_schema(
        operation_summary="Lister les commandes clients",
        manual_parameters=[
            openapi.Parameter("statut", openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter("bijouterie_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter("vendor_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter("ouvrier_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter("date_from", openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter("date_to", openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter("q", openapi.IN_QUERY, type=openapi.TYPE_STRING),
        ],
        responses={200: CommandeClientDetailSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        role = get_role_name(user)

        qs = (
            CommandeClient.objects
            .select_related("client", "bijouterie", "vendor__user", "ouvrier")
            .prefetch_related("lignes", "factures", "historiques")
        )

        if role == "vendor":
            qs = qs.filter(vendor__user=user)

        statut = self.request.query_params.get("statut")
        bijouterie_id = self.request.query_params.get("bijouterie_id")
        vendor_id = self.request.query_params.get("vendor_id")
        ouvrier_id = self.request.query_params.get("ouvrier_id")
        q = self.request.query_params.get("q")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        if statut:
            qs = qs.filter(statut=statut)
        if bijouterie_id:
            qs = qs.filter(bijouterie_id=bijouterie_id)
        if vendor_id:
            qs = qs.filter(vendor_id=vendor_id)
        if ouvrier_id:
            qs = qs.filter(ouvrier_id=ouvrier_id)
        if date_from:
            qs = qs.filter(date_commande__date__gte=date_from)
        if date_to:
            qs = qs.filter(date_commande__date__lte=date_to)
        if q:
            qs = qs.filter(
                Q(numero_commande__icontains=q) |
                Q(client__prenom__icontains=q) |
                Q(client__nom__icontains=q) |
                Q(client__telephone__icontains=q) |
                Q(lignes__nom_modele__icontains=q)
            ).distinct()

        return qs.order_by("-id")


class CommandeClientDetailView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CommandeClientDetailSerializer
    queryset = (
        CommandeClient.objects
        .select_related("client", "bijouterie", "vendor__user", "ouvrier")
        .prefetch_related("lignes", "factures", "historiques")
    )

    @swagger_auto_schema(
        operation_summary="Détail d'une commande client",
        responses={200: CommandeClientDetailSerializer},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        if not can_access_commande(request.user, obj):
            return Response({"detail": "Accès refusé."}, status=403)
        return super().retrieve(request, *args, **kwargs)


class CommandeAssignerOuvrierView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Assigner un ouvrier",
        operation_description="""
Assigne un ouvrier à la commande.
L'assignation passe automatiquement la commande en EN_PRODUCTION.
""",
        request_body=AssignerOuvrierSerializer,
        responses={200: CommandeClientDetailSerializer},
    )
    @transaction.atomic
    def patch(self, request, pk):
        commande = get_object_or_404(CommandeClient, pk=pk)

        if not can_access_commande(request.user, commande):
            return Response({"detail": "Accès refusé."}, status=403)

        serializer = AssignerOuvrierSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            commande = assigner_ouvrier_commande(
                commande=commande,
                ouvrier=serializer.validated_data["ouvrier"],
                user=request.user,
                commentaire=serializer.validated_data.get("commentaire", ""),
            )
        except DjangoValidationError as e:
            return Response(
                {
                    "detail": str(e),
                    "acompte_minimum_requis": commande.acompte_minimum_requis,
                    "total_acompte_paye": commande.total_acompte_paye,
                },
                status=400,
            )

        return Response(
            {
                "message": "Ouvrier affecté avec succès.",
                "commande": CommandeClientDetailSerializer(commande).data,
            }
        )


class CommandeTerminerView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Terminer une commande",
        request_body=TerminerCommandeSerializer,
        responses={200: CommandeClientDetailSerializer},
    )
    @transaction.atomic
    def patch(self, request, pk):
        commande = get_object_or_404(CommandeClient, pk=pk)

        if not can_access_commande(request.user, commande):
            return Response({"detail": "Accès refusé."}, status=403)

        serializer = TerminerCommandeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            commande = terminer_commande(
                commande=commande,
                user=request.user,
                date_depot_boutique=serializer.validated_data.get("date_depot_boutique"),
                date_fin_reelle=serializer.validated_data.get("date_fin_reelle"),
                commentaire=serializer.validated_data.get("commentaire", ""),
            )
        except DjangoValidationError as e:
            return Response({"detail": str(e)}, status=400)

        return Response(
            {
                "message": "Commande terminée avec succès.",
                "commande": CommandeClientDetailSerializer(commande).data,
            }
        )


class CommandePayerSoldeView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Payer le solde d'une commande",
        request_body=PayerSoldeCommandeSerializer,
        responses={200: "Paiement enregistré"},
    )
    @transaction.atomic
    def post(self, request, pk):
        commande = get_object_or_404(
            CommandeClient.objects.select_for_update().prefetch_related("factures"),
            pk=pk,
        )

        if not can_access_commande(request.user, commande):
            return Response({"detail": "Accès refusé."}, status=403)

        serializer = PayerSoldeCommandeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        facture_finale = (
            commande.factures
            .filter(type_facture=Facture.TYPE_FINALE)
            .order_by("-id")
            .first()
        )

        if not facture_finale:
            if commande.reste_global <= 0:
                return Response({"detail": "Aucun solde à payer."}, status=400)
            try:
                facture_finale = create_facture_finale_for_commande(commande=commande)
            except DjangoValidationError as e:
                return Response({"detail": str(e)}, status=400)

        register_facture_payment(
            facture=facture_finale,
            created_by=request.user,
            lignes=serializer.validated_data["lignes_paiement"],
        )

        facture_finale.refresh_from_db()
        commande.refresh_from_db()

        return Response(
            {
                "message": "Paiement du solde enregistré avec succès.",
                "commande": CommandeClientDetailSerializer(commande).data,
                "facture_finale_id": facture_finale.id,
                "facture_finale_status": facture_finale.status,
                "facture_finale_reste": facture_finale.reste_a_payer,
            }
        )


class CommandeLivrerView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Livrer une commande",
        responses={200: CommandeClientDetailSerializer},
    )
    @transaction.atomic
    def patch(self, request, pk):
        commande = get_object_or_404(
            CommandeClient.objects.select_for_update(),
            pk=pk
        )

        if not can_access_commande(request.user, commande):
            return Response({"detail": "Accès refusé."}, status=403)

        try:
            commande = livrer_commande(
                commande=commande,
                user=request.user,
            )
        except DjangoValidationError as e:
            return Response(
                {
                    "detail": str(e),
                    "reste_global": commande.reste_global,
                },
                status=400,
            )

        return Response(
            {
                "message": "Commande livrée avec succès.",
                "commande": CommandeClientDetailSerializer(commande).data,
            }
        )


class CommandeBonCommandePDFView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Télécharger le bon de commande PDF",
        responses={200: "PDF"},
    )
    def get(self, request, pk):
        commande = get_object_or_404(
            CommandeClient.objects
            .select_related("client", "bijouterie", "vendor__user", "ouvrier")
            .prefetch_related("lignes", "factures", "historiques"),
            pk=pk,
        )

        if not can_access_commande(request.user, commande):
            return Response({"detail": "Accès refusé."}, status=403)

        pdf_bytes = generate_bon_commande_pdf(commande=commande)

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'inline; filename="bon_commande_{commande.numero_commande}.pdf"'
        )
        return response


# class CommandeDashboardView(APIView):
#     permission_classes = [IsAuthenticated]
    
#     @swagger_auto_schema(
#     operation_summary="Dashboard commandes",
#     operation_description="""
# Dashboard résumé des commandes :
# - KPI globaux
# - répartition par statut
# - charge des ouvriers
# - dernières commandes
# """,
#     manual_parameters=[
#         openapi.Parameter("date_from", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Date début YYYY-MM-DD"),
#         openapi.Parameter("date_to", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Date fin YYYY-MM-DD"),
#         openapi.Parameter("bijouterie_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
#         openapi.Parameter("vendor_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
#         openapi.Parameter("ouvrier_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
#         openapi.Parameter("statut", openapi.IN_QUERY, type=openapi.TYPE_STRING),
#         openapi.Parameter("q", openapi.IN_QUERY, type=openapi.TYPE_STRING),
#     ],
#     responses={200: CommandeDashboardSerializer},
# )

#     def get_base_queryset(self, request):
#         user = request.user
#         role = get_role_name(user)

#         qs = (
#             CommandeClient.objects
#             .select_related("client", "bijouterie", "vendor__user", "ouvrier")
#             .prefetch_related("factures", "historiques", "lignes")
#             .all()
#         )

#         # Scope simple
#         if role == "vendor":
#             qs = qs.filter(vendor__user=user)

#         # Filtres
#         statut = request.query_params.get("statut")
#         bijouterie_id = request.query_params.get("bijouterie_id")
#         vendor_id = request.query_params.get("vendor_id")
#         ouvrier_id = request.query_params.get("ouvrier_id")
#         q = request.query_params.get("q")
#         date_from = request.query_params.get("date_from")
#         date_to = request.query_params.get("date_to")

#         if statut:
#             qs = qs.filter(statut=statut)

#         if bijouterie_id:
#             qs = qs.filter(bijouterie_id=bijouterie_id)

#         if vendor_id:
#             qs = qs.filter(vendor_id=vendor_id)

#         if ouvrier_id:
#             qs = qs.filter(ouvrier_id=ouvrier_id)

#         if date_from:
#             qs = qs.filter(date_commande__date__gte=date_from)

#         if date_to:
#             qs = qs.filter(date_commande__date__lte=date_to)

#         if q:
#             qs = qs.filter(
#                 Q(numero_commande__icontains=q)
#                 | Q(client__prenom__icontains=q)
#                 | Q(client__nom__icontains=q)
#                 | Q(client__telephone__icontains=q)
#                 | Q(lignes__nom_modele__icontains=q)
#             ).distinct()

#         return qs

#     def get(self, request):
#         qs = self.get_base_queryset(request)

#         total_commandes = qs.count()

#         total_montant = qs.aggregate(
#             total=Sum("montant_total")
#         )["total"] or Decimal("0.00")

#         total_paye = (
#             PaiementLigne.objects
#             .filter(paiement__facture__commande_client__in=qs)
#             .aggregate(total=Sum("montant_paye"))["total"]
#             or Decimal("0.00")
#         )

#         reste_global = total_montant - total_paye
#         if reste_global < 0:
#             reste_global = Decimal("0.00")

#         statuts = qs.aggregate(
#             brouillon=Count("id", filter=Q(statut=CommandeClient.STATUT_BROUILLON)),
#             en_attente=Count("id", filter=Q(statut=CommandeClient.STATUT_EN_ATTENTE)),
#             en_production=Count("id", filter=Q(statut=CommandeClient.STATUT_EN_PRODUCTION)),
#             terminees=Count("id", filter=Q(statut=CommandeClient.STATUT_TERMINEE)),
#             livrees=Count("id", filter=Q(statut=CommandeClient.STATUT_LIVREE)),
#             annulees=Count("id", filter=Q(statut=CommandeClient.STATUT_ANNULEE)),
#         )

#         # Ouvriers: seulement ceux qui ont au moins une commande dans le scope filtré
#         commande_ids = qs.values_list("id", flat=True)

#         ouvriers_qs = (
#             Ouvrier.objects
#             .filter(commandes_clients__in=qs)
#             .annotate(
#                 nb_commandes_total=Count(
#                     "commandes_clients",
#                     filter=Q(commandes_clients__id__in=commande_ids),
#                     distinct=True,
#                 ),
#                 nb_en_production=Count(
#                     "commandes_clients",
#                     filter=Q(
#                         commandes_clients__id__in=commande_ids,
#                         commandes_clients__statut=CommandeClient.STATUT_EN_PRODUCTION,
#                     ),
#                     distinct=True,
#                 ),
#                 nb_terminees=Count(
#                     "commandes_clients",
#                     filter=Q(
#                         commandes_clients__id__in=commande_ids,
#                         commandes_clients__statut=CommandeClient.STATUT_TERMINEE,
#                     ),
#                     distinct=True,
#                 ),
#                 nb_livrees=Count(
#                     "commandes_clients",
#                     filter=Q(
#                         commandes_clients__id__in=commande_ids,
#                         commandes_clients__statut=CommandeClient.STATUT_LIVREE,
#                     ),
#                     distinct=True,
#                 ),
#             )
#             .order_by("-nb_en_production", "-nb_commandes_total", "nom", "prenom")
#         )

#         recentes_qs = qs.order_by("-date_commande", "-id")[:10]

#         payload = {
#             "periode": {
#                 "date_from": request.query_params.get("date_from"),
#                 "date_to": request.query_params.get("date_to"),
#                 "bijouterie_id": request.query_params.get("bijouterie_id"),
#                 "vendor_id": request.query_params.get("vendor_id"),
#                 "ouvrier_id": request.query_params.get("ouvrier_id"),
#                 "statut": request.query_params.get("statut"),
#                 "q": request.query_params.get("q"),
#             },
#             "kpis": {
#                 "total_commandes": total_commandes,
#                 "montant_total_commandes": total_montant,
#                 "total_encaisse": total_paye,
#                 "reste_global": reste_global,
#             },
#             "statuts": {
#                 "brouillon": statuts["brouillon"],
#                 "en_attente": statuts["en_attente"],
#                 "en_production": statuts["en_production"],
#                 "terminees": statuts["terminees"],
#                 "livrees": statuts["livrees"],
#                 "annulees": statuts["annulees"],
#             },
#             "ouvriers": OuvrierDashboardSerializer(ouvriers_qs, many=True).data,
#             "recentes": CommandeDashboardRecentSerializer(recentes_qs, many=True).data,
#         }

#         serializer = CommandeDashboardSerializer(payload)
#         return Response(serializer.data)


class CommandeDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get_base_queryset(self, request):
        user = request.user
        role = get_role_name(user)

        qs = (
            CommandeClient.objects
            .select_related("client", "bijouterie", "vendor__user", "ouvrier")
            .prefetch_related("factures", "historiques", "lignes")
        )

        # Scope par rôle
        if role == "vendor":
            qs = qs.filter(vendor__user=user)

        elif role == "cashier":
            cashier_bijouterie = getattr(user.staff_cashier_profile, "bijouterie", None)
            if cashier_bijouterie:
                qs = qs.filter(bijouterie=cashier_bijouterie)
            else:
                qs = qs.none()

        elif role == "manager":
            manager_bijouteries = getattr(user.staff_manager_profile, "bijouteries", None)
            if manager_bijouteries is not None:
                qs = qs.filter(bijouterie__in=manager_bijouteries.all())
            else:
                qs = qs.none()

        # Filtres
        params = request.query_params

        if params.get("statut"):
            qs = qs.filter(statut=params["statut"])

        if params.get("bijouterie_id"):
            qs = qs.filter(bijouterie_id=params["bijouterie_id"])

        if params.get("vendor_id"):
            qs = qs.filter(vendor_id=params["vendor_id"])

        if params.get("ouvrier_id"):
            qs = qs.filter(ouvrier_id=params["ouvrier_id"])

        if params.get("date_from"):
            qs = qs.filter(date_commande__date__gte=params["date_from"])

        if params.get("date_to"):
            qs = qs.filter(date_commande__date__lte=params["date_to"])

        if params.get("q"):
            q = params["q"]
            qs = qs.filter(
                Q(numero_commande__icontains=q)
                | Q(client__prenom__icontains=q)
                | Q(client__nom__icontains=q)
                | Q(client__telephone__icontains=q)
                | Q(lignes__nom_modele__icontains=q)
            ).distinct()

        return qs

    @swagger_auto_schema(
        operation_summary="Dashboard commandes",
        operation_description="""
Dashboard résumé des commandes :
- KPI globaux
- répartition par statut
- charge des ouvriers
- dernières commandes
""",
        manual_parameters=[
            openapi.Parameter(
                "date_from",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Date début YYYY-MM-DD",
            ),
            openapi.Parameter(
                "date_to",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Date fin YYYY-MM-DD",
            ),
            openapi.Parameter(
                "bijouterie_id",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "vendor_id",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "ouvrier_id",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "statut",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "q",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
            ),
        ],
        responses={200: CommandeDashboardSerializer},
    )
    def get(self, request):
        qs = self.get_base_queryset(request)

        total_commandes = qs.count()

        total_montant = qs.aggregate(
            total=Sum("montant_total")
        )["total"] or Decimal("0.00")

        total_paye = (
            PaiementLigne.objects
            .filter(paiement__facture__commande_client__in=qs)
            .aggregate(total=Sum("montant_paye"))["total"]
            or Decimal("0.00")
        )

        reste_global = max(total_montant - total_paye, Decimal("0.00"))

        taux_paiement = (
            (total_paye / total_montant * 100)
            if total_montant > 0 else Decimal("0.00")
        )

        statuts = qs.aggregate(
            brouillon=Count(
                "id",
                filter=Q(statut=CommandeClient.STATUT_BROUILLON),
            ),
            en_attente=Count(
                "id",
                filter=Q(statut=CommandeClient.STATUT_EN_ATTENTE),
            ),
            en_production=Count(
                "id",
                filter=Q(statut=CommandeClient.STATUT_EN_PRODUCTION),
            ),
            terminees=Count(
                "id",
                filter=Q(statut=CommandeClient.STATUT_TERMINEE),
            ),
            livrees=Count(
                "id",
                filter=Q(statut=CommandeClient.STATUT_LIVREE),
            ),
            annulees=Count(
                "id",
                filter=Q(statut=CommandeClient.STATUT_ANNULEE),
            ),
        )

        ouvriers_qs = (
            Ouvrier.objects
            .filter(commandes_clients__in=qs)
            .annotate(
                nb_commandes_total=Count("commandes_clients", distinct=True),
                nb_en_production=Count(
                    "commandes_clients",
                    filter=Q(
                        commandes_clients__statut=CommandeClient.STATUT_EN_PRODUCTION
                    ),
                    distinct=True,
                ),
                nb_terminees=Count(
                    "commandes_clients",
                    filter=Q(
                        commandes_clients__statut=CommandeClient.STATUT_TERMINEE
                    ),
                    distinct=True,
                ),
                nb_livrees=Count(
                    "commandes_clients",
                    filter=Q(
                        commandes_clients__statut=CommandeClient.STATUT_LIVREE
                    ),
                    distinct=True,
                ),
            )
            .order_by("-nb_en_production", "-nb_commandes_total", "nom", "prenom")
        )

        recentes_qs = qs.order_by("-date_commande", "-id")[:10]

        payload = {
            "periode": {
                "date_from": request.query_params.get("date_from"),
                "date_to": request.query_params.get("date_to"),
                "bijouterie_id": request.query_params.get("bijouterie_id"),
                "vendor_id": request.query_params.get("vendor_id"),
                "ouvrier_id": request.query_params.get("ouvrier_id"),
                "statut": request.query_params.get("statut"),
                "q": request.query_params.get("q"),
            },
            "kpis": {
                "total_commandes": total_commandes,
                "montant_total_commandes": total_montant,
                "total_encaisse": total_paye,
                "reste_global": reste_global,
                "taux_paiement": taux_paiement,
            },
            "statuts": {
                "brouillon": statuts["brouillon"],
                "en_attente": statuts["en_attente"],
                "en_production": statuts["en_production"],
                "terminees": statuts["terminees"],
                "livrees": statuts["livrees"],
                "annulees": statuts["annulees"],
            },
            "ouvriers": OuvrierDashboardSerializer(ouvriers_qs, many=True).data,
            "recentes": CommandeDashboardRecentSerializer(recentes_qs, many=True).data,
        }

        serializer = CommandeDashboardSerializer(payload)
        return Response(serializer.data)


    
    

