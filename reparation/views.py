# reparation/views.py

from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.bijouteries import get_user_bijouteries
from backend.roles import ROLE_VENDOR, get_role_name
from reparation.models import Reparation
from reparation.serializers import (PaiementReparationCreateSerializer,
                                    ReparationListSerializer)
from reparation.services.paiement_reparation_service import payer_reparation
from reparation.services.reparation_service import (
    ROLES_PAIEMENT, ROLES_SUIVI, verifier_permission_reparation)
from reparation.services.ticket_de_restitution import \
    generer_recu_paiement_reparation_pdf
from reparation.services.ticket_reparation_A5 import generer_ticket_depot_pdf

from .serializers import ReparationCreateSerializer, ReparationDetailSerializer


class ReparationListAPIView(generics.ListAPIView):
    """
    Liste paginée des réparations Rio-Gold.

    Filtres :
    - periode : 1_mois, 3_mois, 1_an, tout
    - statut : en_attente, en_cours, pret,
               restitue, annule, tout
    - paiement_effectue : true, false
    - bijouterie_id
    - search : numéro de réparation

    Permissions :
    - Admin : toutes les réparations.
    - Manager : réparations de ses bijouteries.
    - Vendor : uniquement ses réparations.

    Pagination :
    - Configuration globale DRF (20 résultats).
    """

    serializer_class = ReparationListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        user = self.request.user
        params = self.request.query_params

        # ----------------------------------------------------
        # 1. Vérification du rôle
        # ----------------------------------------------------

        role = get_role_name(user)

        if role not in ROLES_SUIVI:
            raise PermissionDenied(
                "Vous n'êtes pas autorisé à consulter "
                "les réparations."
            )

        # ----------------------------------------------------
        # 2. Queryset optimisé
        # ----------------------------------------------------

        queryset = (
            Reparation.objects
            .select_related(
                "bijouterie",
                "client",
                "vendeur",
                "paiement",
            )
        )

        # ----------------------------------------------------
        # 3. Périmètre des bijouteries autorisées
        # ----------------------------------------------------

        bijouteries_autorisees = get_user_bijouteries(user)

        queryset = queryset.filter(
            bijouterie_id__in=bijouteries_autorisees.values(
                "pk"
            )
        )

        # ----------------------------------------------------
        # 4. Périmètre vendeur
        # ----------------------------------------------------

        if role == ROLE_VENDOR:

            vendor = getattr(
                user,
                "staff_vendor_profile",
                None,
            )

            if vendor is None or not vendor.verifie:
                raise PermissionDenied(
                    "Profil vendeur introuvable ou désactivé."
                )

            queryset = queryset.filter(
                vendeur_id=vendor.pk
            )

        # ----------------------------------------------------
        # 5. Filtre bijouterie
        # ----------------------------------------------------

        bijouterie_id = params.get(
            "bijouterie_id",
            "",
        ).strip()

        if bijouterie_id:

            try:
                bijouterie_id = int(bijouterie_id)

            except (TypeError, ValueError):
                raise ValidationError({
                    "bijouterie_id": (
                        "L'identifiant doit être un entier."
                    )
                })

            if bijouterie_id <= 0:
                raise ValidationError({
                    "bijouterie_id": (
                        "Identifiant de bijouterie invalide."
                    )
                })

            queryset = queryset.filter(
                bijouterie_id=bijouterie_id
            )

        # ----------------------------------------------------
        # 6. Filtre période
        # ----------------------------------------------------

        periode = params.get(
            "periode",
            "1_mois",
        ).strip().lower()

        periodes = {
            "1_mois": relativedelta(months=1),
            "3_mois": relativedelta(months=3),
            "1_an": relativedelta(years=1),
        }

        if periode != "tout":

            if periode not in periodes:
                raise ValidationError({
                    "periode": (
                        "Valeurs autorisées : "
                        "1_mois, 3_mois, 1_an, tout."
                    )
                })

            maintenant = timezone.now()
            date_debut = maintenant - periodes[periode]

            queryset = queryset.filter(
                date_depot__gte=date_debut,
                date_depot__lte=maintenant,
            )

        # ----------------------------------------------------
        # 7. Filtre statut
        # ----------------------------------------------------

        statut = params.get(
            "statut",
            "tout",
        ).strip().lower()

        statuts_valides = {
            valeur
            for valeur, _ in Reparation.Statut.choices
        }

        if statut != "tout":

            if statut not in statuts_valides:
                raise ValidationError({
                    "statut": (
                        "Statut invalide. Valeurs autorisées : "
                        + ", ".join(sorted(statuts_valides))
                    )
                })

            queryset = queryset.filter(
                statut=statut
            )

        # ----------------------------------------------------
        # 8. Filtre paiement
        # ----------------------------------------------------

        paiement_effectue = params.get(
            "paiement_effectue",
            "",
        ).strip().lower()

        if paiement_effectue:

            if paiement_effectue not in {"true", "false"}:
                raise ValidationError({
                    "paiement_effectue": (
                        "Valeurs autorisées : true, false."
                    )
                })

            queryset = queryset.filter(
                paiement__isnull=(
                    paiement_effectue == "false"
                )
            )

        # ----------------------------------------------------
        # 9. Recherche par numéro de réparation
        # ----------------------------------------------------

        search = params.get(
            "search",
            "",
        ).strip()

        if search:
            queryset = queryset.filter(
                numero_reparation__icontains=search
            )

        # ----------------------------------------------------
        # 10. Tri : réparations récentes en premier
        # ----------------------------------------------------

        return queryset.order_by(
            "-date_depot",
            "-pk",
        )



class ReparationCreateAPIView(GenericAPIView):
    """
    Enregistre une réparation contenant un ou plusieurs bijoux.

    Fonctionnement :
    - Vérification des données par le serializer.
    - Vérification des permissions par le service métier.
    - Création atomique du dossier et de ses bijoux.
    - Aucun paiement à la création.
    - Aucune Vente, VenteAutre ou Facture.
    - Retour de l'URL du ticket de dépôt PDF A5.

    Le ticket PDF est généré à la demande.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ReparationCreateSerializer

    def post(self, request, *args, **kwargs):

        # ----------------------------------------------------
        # 1. Valider les données
        # ----------------------------------------------------

        serializer = self.get_serializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        # ----------------------------------------------------
        # 2. Créer la réparation
        # ----------------------------------------------------

        try:
            reparation = serializer.save()

        except DjangoValidationError as exc:

            if hasattr(exc, "message_dict"):
                raise ValidationError(
                    exc.message_dict
                ) from exc

            raise ValidationError(
                exc.messages
            ) from exc

        # ----------------------------------------------------
        # 3. Construire l'URL du ticket PDF A5
        # ----------------------------------------------------

        ticket_url = request.build_absolute_uri(
            reverse(
                "reparation_ticket_depot",
                kwargs={
                    "pk": reparation.pk,
                },
            )
        )

        # ----------------------------------------------------
        # 4. Sérialiser le dossier complet
        # ----------------------------------------------------

        resultat = ReparationDetailSerializer(
            reparation,
            context=self.get_serializer_context(),
        )

        # ----------------------------------------------------
        # 5. Réponse Angular
        # ----------------------------------------------------

        return Response(
            {
                "success": True,
                "message": (
                    "Réparation enregistrée avec succès. "
                    "Le ticket de dépôt PDF A5 est disponible."
                ),
                "reparation": resultat.data,
                "ticket": {
                    "format": "A5",
                    "type": "application/pdf",
                    "url": ticket_url,
                    "numero_reparation": (
                        reparation.numero_reparation
                    ),
                },
            },
            status=status.HTTP_201_CREATED,
        )
        


class TicketDepotReparationAPIView(APIView):
    """
    Génère le ticket de dépôt PDF A5.

    Accessible aux utilisateurs autorisés
    de la bijouterie concernée.

    Le PDF est généré à la demande.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):

        reparation = get_object_or_404(
            Reparation.objects.select_related(
                "bijouterie",
                "client",
                "vendeur",
            ).prefetch_related(
                "bijoux",
            ),
            pk=pk,
        )

        try:
            verifier_permission_reparation(
                user=request.user,
                bijouterie=reparation.bijouterie,
                roles_autorises=ROLES_SUIVI,
            )

            pdf = generer_ticket_depot_pdf(
                reparation
            )

        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise ValidationError(
                    exc.message_dict
                ) from exc

            raise ValidationError(
                exc.messages
            ) from exc

        response = HttpResponse(
            pdf,
            content_type="application/pdf",
        )

        response["Content-Disposition"] = (
            'inline; filename="ticket-depot-'
            f'{reparation.numero_reparation}.pdf"'
        )

        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"

        return response


class PaiementReparationAPIView(APIView):
    """
    Encaisse le paiement intégral d'une réparation.

    Règles métier :
    - Réparation au statut PRET.
    - Un seul mode de paiement.
    - Paiement intégral obligatoire.
    - Aucun paiement en double.
    - Contrôle des permissions et de la bijouterie.
    - Idempotence de l'encaissement.
    - Aucun objet Vente, VenteAutre ou Facture créé.

    La restitution du bijou reste une opération séparée.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):

        # 1. Valider les données reçues
        serializer = PaiementReparationCreateSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        # 2. Vérifier l'existence de la réparation
        reparation = get_object_or_404(
            Reparation.objects.only(
                "id",
                "bijouterie_id",
            ),
            pk=pk,
        )

        # 3. Encaisser via le service métier
        try:
            resultat = payer_reparation(
                reparation_id=reparation.pk,
                bijouterie_id=reparation.bijouterie_id,
                user=request.user,
                lignes_data=serializer.validated_data["lignes"],
                idempotency_key=serializer.validated_data[
                    "idempotency_key"
                ],
            )

        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise ValidationError(exc.message_dict)

            raise ValidationError(exc.messages)

        # 4. Retourner le résultat de l'encaissement
        return Response(
            resultat,
            status=status.HTTP_200_OK,
        )


class RecuPaiementReparationAPIView(APIView):
    """
    Génère le reçu thermique PDF 80 mm
    après paiement intégral.

    Le reçu peut être imprimé lorsque
    la réparation est encore PRET.

    Aucun nouveau paiement n'est créé.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):

        reparation = get_object_or_404(
            Reparation.objects.select_related(
                "bijouterie",
                "client",
                "vendeur",
                "restitue_par",
                "paiement__mode_paiement",
                "paiement__compte_depot",
            ).prefetch_related(
                "bijoux",
            ),
            pk=pk,
        )

        try:
            verifier_permission_reparation(
                user=request.user,
                bijouterie=reparation.bijouterie,
                roles_autorises=ROLES_PAIEMENT,
            )

            pdf = generer_recu_paiement_reparation_pdf(
                reparation
            )

        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise ValidationError(
                    exc.message_dict
                ) from exc

            raise ValidationError(
                exc.messages
            ) from exc

        response = HttpResponse(
            pdf,
            content_type="application/pdf",
        )

        response["Content-Disposition"] = (
            'inline; filename="recu-reparation-'
            f'{reparation.numero_reparation}.pdf"'
        )

        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"

        return response


