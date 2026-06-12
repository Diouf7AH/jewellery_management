from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import generics, permissions, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.permissions import (ROLE_MANAGER, ROLE_VENDOR, IsAdminOrManager,
                                 IsAdminOrManagerOrVendor, get_role_name)
from e_commerce.models import (CommandeEcommerce, EcommerceBanner,
                               LivraisonEcommerce, PaiementEcommerce)
from e_commerce.selectors.products import get_ecommerce_products
from e_commerce.serializers import (CommandeEcommerceCreateSerializer,
                                    CommandeEcommerceDetailSerializer,
                                    EcommerceDashboardQuerySerializer)
from e_commerce.services.payment import initiate_payment
from e_commerce.services.webhook import confirm_ecommerce_payment
from sale.models import VenteProduit
from stock.models import Stock

from .models import CommandeEcommerce
from .serializers import (CommandeEcommerceCreateSerializer,
                          CommandeEcommerceDetailSerializer,
                          EcommerceDashboardQuerySerializer,
                          EcommerceProductDetailSerializer,
                          EcommerceProductListSerializer,
                          LivraisonEcommerceSerializer)


class CommandeEcommerceCreateView(APIView):
    permission_classes = [permissions.AllowAny]

    @swagger_auto_schema(
        operation_summary="Créer une commande e-commerce",
        operation_description=(
            "Crée une commande e-commerce en attente de paiement.\n\n"
            "La commande utilise le stock de la bijouterie sélectionnée.\n"
            "Aucune vente, facture ou sortie de stock n'est créée à cette étape.\n"
            "La vente, la facture et le mouvement SALE_OUT seront créés après confirmation du paiement via webhook."
        ),
        request_body=CommandeEcommerceCreateSerializer,
        responses={
            201: openapi.Response(
                description="Commande e-commerce créée avec succès",
                schema=CommandeEcommerceDetailSerializer,
            ),
            400: "Erreur de validation : stock insuffisant, produit introuvable, bijouterie introuvable.",
        },
        tags=["E-commerce"],
    )
    def post(self, request):
        serializer = CommandeEcommerceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        commande = serializer.save()

        return Response(
            CommandeEcommerceDetailSerializer(commande).data,
            status=status.HTTP_201_CREATED,
        )


class EcommerceProductListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = EcommerceProductListSerializer

    @swagger_auto_schema(
        operation_summary="Lister les produits e-commerce",
        operation_description=(
            "Retourne les produits disponibles à la vente sur le site e-commerce.\n\n"
            "- Utilise uniquement le stock de bijouterie.\n"
            "- Ignore le stock réserve.\n"
            "- Ignore les produits en rupture de stock.\n"
        ),
        manual_parameters=[
            openapi.Parameter(
                "bijouterie_id",
                openapi.IN_QUERY,
                description="Filtrer les produits par bijouterie",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
        ],
        responses={
            200: EcommerceProductListSerializer(many=True),
        },
        tags=["E-commerce"],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return get_ecommerce_products(
            bijouterie_id=self.request.query_params.get("bijouterie_id")
        )


class EcommerceProductDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = EcommerceProductDetailSerializer

    lookup_field = "produit_line__produit__uuid"
    lookup_url_kwarg = "uuid"

    @swagger_auto_schema(
        operation_summary="Détail d'un produit e-commerce",
        operation_description=(
            "Retourne le détail complet d'un produit disponible "
            "sur le catalogue e-commerce."
        ),
        manual_parameters=[
            openapi.Parameter(
                "uuid",
                openapi.IN_PATH,
                description="UUID du produit",
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "bijouterie_id",
                openapi.IN_QUERY,
                description="Filtrer sur une bijouterie spécifique",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                "q",
                openapi.IN_QUERY,
                description="Recherche par nom, SKU, marque ou modèle",
                type=openapi.TYPE_STRING,
                required=False,
            ),

            openapi.Parameter(
                "categorie",
                openapi.IN_QUERY,
                description="Filtrer par catégorie",
                type=openapi.TYPE_STRING,
                required=False,
            ),

            openapi.Parameter(
                "marque",
                openapi.IN_QUERY,
                description="Filtrer par marque",
                type=openapi.TYPE_STRING,
                required=False,
            ),

            openapi.Parameter(
                "purete",
                openapi.IN_QUERY,
                description="Filtrer par pureté",
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
        responses={
            200: EcommerceProductDetailSerializer,
            404: "Produit introuvable",
        },
        tags=["E-commerce"],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return get_ecommerce_products(
            bijouterie_id=self.request.query_params.get(
                "bijouterie_id"
            )
        )


class PaymentWebhookView(APIView):
    permission_classes = [permissions.AllowAny]

    @swagger_auto_schema(
        operation_summary="Webhook de confirmation paiement e-commerce",
        operation_description=(
            "Reçoit la confirmation de paiement depuis Wave, Orange Money ou carte bancaire.\n\n"
            "Si le paiement est confirmé :\n"
            "- PaiementEcommerce passe à success\n"
            "- CommandeEcommerce passe à paid\n"
            "- Vente ERP créée\n"
            "- Facture créée\n"
            "- Stock bijouterie consommé\n"
            "- InventoryMovement SALE_OUT créé\n\n"
            "⚠️ En production, ajouter la vérification de signature du fournisseur."
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["provider_reference"],
            properties={
                "provider_reference": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Référence fournisseur du paiement",
                    example="ECOM-123456",
                ),
                "transaction_id": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="ID transaction fournisseur",
                    example="TX-987654",
                ),
                "reference_paiement": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Référence paiement interne ou externe",
                    example="PAY-20260606-001",
                ),
                "status": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Statut retourné par le fournisseur",
                    example="success",
                ),
            },
        ),
        responses={
            200: openapi.Response(
                description="Paiement confirmé avec succès",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "detail": openapi.Schema(type=openapi.TYPE_STRING),
                        "commande_uuid": openapi.Schema(type=openapi.TYPE_STRING),
                        "commande_status": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
            400: "provider_reference obligatoire",
            404: "Paiement e-commerce introuvable",
        },
        tags=["E-commerce Paiements"],
    )
    def post(self, request):
        payload = request.data

        provider_reference = (
            payload.get("provider_reference")
            or payload.get("transaction_id")
            or payload.get("reference_paiement")
        )

        if not provider_reference:
            return Response(
                {"detail": "provider_reference est obligatoire."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        paiement = (
            PaiementEcommerce.objects.filter(provider_reference=provider_reference).first()
            or PaiementEcommerce.objects.filter(transaction_id=provider_reference).first()
            or PaiementEcommerce.objects.filter(reference_paiement=provider_reference).first()
        )

        if not paiement:
            return Response(
                {"detail": "Paiement e-commerce introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        commande = confirm_ecommerce_payment(
            paiement=paiement,
            payload=payload,
        )

        return Response(
            {
                "detail": "Paiement confirmé avec succès.",
                "commande_uuid": commande.uuid,
                "commande_status": commande.status,
            },
            status=status.HTTP_200_OK,
        )
        


class PaymentInitiateView(APIView):
    permission_classes = [permissions.AllowAny]

    @swagger_auto_schema(
        operation_summary="Initialiser un paiement e-commerce",
        operation_description=(
            "Génère ou récupère le lien de paiement d'une commande e-commerce.\n\n"
            "La commande doit être en attente de paiement.\n"
            "Cette API ne crée pas encore la vente ERP, la facture ou la sortie de stock.\n"
            "Ces actions seront faites uniquement après confirmation du paiement via webhook."
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["commande_uuid"],
            properties={
                "commande_uuid": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format=openapi.FORMAT_UUID,
                    description="UUID de la commande e-commerce",
                    example="7d68f4d3-9b88-4f8d-b6ab-6f15a0a59b74",
                ),
            },
        ),
        responses={
            200: openapi.Response(
                description="Lien de paiement généré",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "payment_uuid": openapi.Schema(type=openapi.TYPE_STRING),
                        "commande_uuid": openapi.Schema(type=openapi.TYPE_STRING),
                        "mode": openapi.Schema(type=openapi.TYPE_STRING),
                        "status": openapi.Schema(type=openapi.TYPE_STRING),
                        "montant": openapi.Schema(type=openapi.TYPE_STRING),
                        "checkout_url": openapi.Schema(type=openapi.TYPE_STRING),
                        "provider_reference": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
            400: "commande_uuid obligatoire ou commande déjà payée",
            404: "Commande ou paiement introuvable",
        },
        tags=["E-commerce Paiements"],
    )
    def post(self, request):
        commande_uuid = request.data.get("commande_uuid")

        if not commande_uuid:
            return Response(
                {"detail": "commande_uuid est obligatoire."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        commande = CommandeEcommerce.objects.filter(
            uuid=commande_uuid
        ).first()

        if not commande:
            return Response(
                {"detail": "Commande introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if commande.status == CommandeEcommerce.STATUS_PAID:
            return Response(
                {"detail": "Cette commande est déjà payée."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        paiement = commande.paiements.filter(
            status=PaiementEcommerce.STATUS_PENDING
        ).order_by("-id").first()

        if not paiement:
            return Response(
                {"detail": "Aucun paiement en attente pour cette commande."},
                status=status.HTTP_404_NOT_FOUND,
            )

        paiement = initiate_payment(paiement=paiement)

        return Response(
            {
                "payment_uuid": paiement.uuid,
                "commande_uuid": commande.uuid,
                "mode": paiement.mode,
                "status": paiement.status,
                "montant": paiement.montant,
                "checkout_url": paiement.checkout_url,
                "provider_reference": paiement.provider_reference,
            },
            status=status.HTTP_200_OK,
        )
        



class EcommerceInvoiceView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary="Récupérer la facture PDF d'une commande e-commerce",
        operation_description=(
            "Retourne les informations de facture liées à une commande e-commerce.\n\n"
            "La facture est disponible uniquement après confirmation du paiement."
        ),
        manual_parameters=[
            openapi.Parameter(
                "uuid",
                openapi.IN_PATH,
                description="UUID de la commande e-commerce",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_UUID,
                required=True,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Facture disponible",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "numero_facture": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            example="FAC-20260606-0001",
                        ),
                        "facture_pdf": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            nullable=True,
                            example="/media/factures/FAC-20260606-0001.pdf",
                        ),
                    },
                ),
            ),
            404: "Commande introuvable ou facture indisponible",
        },
        tags=["E-commerce Factures"],
    )
    def get(self, request, uuid):
        commande = get_object_or_404(
            CommandeEcommerce,
            uuid=uuid,
        )

        if not commande.facture:
            return Response(
                {"detail": "Facture indisponible."},
                status=404,
            )

        return Response({
            "numero_facture": commande.facture.numero_facture,
            "facture_pdf": (
                commande.facture.facture_pdf.url
                if commande.facture.facture_pdf
                else None
            ),
        })


class EcommerceDashboardView(APIView):
    permission_classes = [IsAdminOrManager]

    @swagger_auto_schema(
        operation_summary="Dashboard e-commerce",
        operation_description=(
            "Retourne les statistiques e-commerce : commandes, paiements, "
            "ventes et top produits.\n\n"
            "Filtres disponibles : bijouterie, date début, date fin."
        ),
        manual_parameters=[
            openapi.Parameter(
                "bijouterie_id",
                openapi.IN_QUERY,
                description="Filtrer par bijouterie",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                "start_date",
                openapi.IN_QUERY,
                description="Date de début au format YYYY-MM-DD",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE,
                required=False,
            ),
            openapi.Parameter(
                "end_date",
                openapi.IN_QUERY,
                description="Date de fin au format YYYY-MM-DD",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE,
                required=False,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Statistiques e-commerce",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "commandes": openapi.Schema(type=openapi.TYPE_OBJECT),
                        "paiements": openapi.Schema(type=openapi.TYPE_OBJECT),
                        "ventes": openapi.Schema(type=openapi.TYPE_OBJECT),
                        "top_produits": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(type=openapi.TYPE_OBJECT),
                        ),
                    },
                ),
            )
        },
        tags=["E-commerce Dashboard"],
    )
    def get(self, request):
        serializer = EcommerceDashboardQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        commandes = CommandeEcommerce.objects.all()

        if data.get("bijouterie_id"):
            commandes = commandes.filter(bijouterie_id=data["bijouterie_id"])

        if data.get("start_date"):
            commandes = commandes.filter(created_at__date__gte=data["start_date"])

        if data.get("end_date"):
            commandes = commandes.filter(created_at__date__lte=data["end_date"])

        paiements = PaiementEcommerce.objects.filter(commande__in=commandes)
        ventes = commandes.filter(vente__isnull=False)

        top_produits = (
            VenteProduit.objects
            .filter(
                vente__source_vente="ecommerce",
                vente__commande_ecommerce__in=commandes,
            )
            .values(
                "produit_id",
                "produit__nom",
                "produit__sku",
            )
            .annotate(
                quantite_vendue=Sum("quantite"),
                chiffre_affaires=Sum("montant_total"),
            )
            .order_by("-quantite_vendue")[:10]
        )

        return Response({
            "commandes": {
                "total": commandes.count(),
                "pending": commandes.filter(status="pending").count(),
                "paid": commandes.filter(status="paid").count(),
                "failed": commandes.filter(status="failed").count(),
                "cancelled": commandes.filter(status="cancelled").count(),
                "montant_total": commandes.aggregate(total=Sum("montant_total"))["total"] or 0,
            },
            "paiements": {
                "total": paiements.count(),
                "pending": paiements.filter(status="pending").count(),
                "success": paiements.filter(status="success").count(),
                "failed": paiements.filter(status="failed").count(),
                "montant_encaisse": paiements.filter(status="success").aggregate(total=Sum("montant"))["total"] or 0,
            },
            "ventes": {
                "total": ventes.count(),
                "chiffre_affaires": ventes.aggregate(total=Sum("vente__montant_total"))["total"] or 0,
            },
            "top_produits": list(top_produits),
        })


class EcommerceOrderListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CommandeEcommerceDetailSerializer

    @swagger_auto_schema(
        operation_summary="Lister les commandes e-commerce",
        operation_description=(
            "Retourne la liste des commandes e-commerce avec filtres.\n\n"
            "Filtres disponibles : bijouterie, statut et téléphone client."
        ),
        manual_parameters=[
            openapi.Parameter(
                "bijouterie_id",
                openapi.IN_QUERY,
                description="Filtrer par ID de bijouterie",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                description="Filtrer par statut : pending, paid, failed, cancelled",
                type=openapi.TYPE_STRING,
                required=False,
                enum=["pending", "paid", "failed", "cancelled"],
            ),
            openapi.Parameter(
                "telephone",
                openapi.IN_QUERY,
                description="Rechercher par téléphone client",
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Liste des commandes e-commerce",
                schema=CommandeEcommerceDetailSerializer(many=True),
            ),
        },
        tags=["E-commerce Commandes"],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = CommandeEcommerce.objects.select_related(
            "client",
            "bijouterie",
            "vente",
            "facture",
        ).prefetch_related(
            "lignes",
            "paiements",
        ).order_by("-created_at")

        bijouterie_id = self.request.query_params.get("bijouterie_id")
        status_value = self.request.query_params.get("status")
        telephone = self.request.query_params.get("telephone")

        if bijouterie_id:
            queryset = queryset.filter(bijouterie_id=bijouterie_id)

        if status_value:
            queryset = queryset.filter(status=status_value)

        if telephone:
            queryset = queryset.filter(telephone_client__icontains=telephone)

        return queryset



class EcommerceLivraisonDetailView(APIView):
    permission_classes = [permissions.AllowAny]

    @swagger_auto_schema(
        operation_summary="Détail livraison e-commerce",
        operation_description=(
            "Retourne les informations de livraison liées à une commande e-commerce."
        ),
        manual_parameters=[
            openapi.Parameter(
                "uuid",
                openapi.IN_PATH,
                description="UUID de la commande e-commerce",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_UUID,
                required=True,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Détail de la livraison",
                schema=LivraisonEcommerceSerializer,
            ),
            404: "Livraison introuvable",
        },
        tags=["E-commerce Livraison"],
    )
    def get(self, request, uuid):
        livraison = get_object_or_404(
            LivraisonEcommerce.objects.select_related("commande"),
            commande__uuid=uuid,
        )

        return Response(
            LivraisonEcommerceSerializer(livraison).data
        )
        


class LivraisonEcommerceUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Mettre à jour la livraison e-commerce",
        operation_description=(
            "Met à jour le statut de livraison d'une commande e-commerce.\n\n"
            "Statuts possibles :\n"
            "- en_preparation\n"
            "- expedie\n"
            "- livre\n"
            "- annule"
        ),
        manual_parameters=[
            openapi.Parameter(
                "uuid",
                openapi.IN_PATH,
                description="UUID de la commande e-commerce",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_UUID,
                required=True,
            ),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "status": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=["en_preparation", "expedie", "livre", "annule"],
                    example="expedie",
                ),
                "transporteur": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    example="Yango Livraison",
                ),
                "numero_suivi": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    example="TRK-20260606-001",
                ),
                "note": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    example="Colis remis au transporteur.",
                ),
            },
        ),
        responses={
            200: openapi.Response(
                description="Livraison mise à jour",
                schema=LivraisonEcommerceSerializer,
            ),
            404: "Livraison introuvable",
        },
        tags=["E-commerce Livraison"],
    )
    def patch(self, request, uuid):
        livraison = get_object_or_404(
            LivraisonEcommerce,
            commande__uuid=uuid,
        )

        status_value = request.data.get("status")

        if status_value:
            livraison.status = status_value
            now = timezone.now()

            if status_value == LivraisonEcommerce.STATUS_PREPARATION:
                livraison.prepared_at = now
            elif status_value == LivraisonEcommerce.STATUS_EXPEDIE:
                livraison.shipped_at = now
            elif status_value == LivraisonEcommerce.STATUS_LIVRE:
                livraison.delivered_at = now
            elif status_value == LivraisonEcommerce.STATUS_ANNULE:
                livraison.cancelled_at = now

        livraison.transporteur = request.data.get("transporteur", livraison.transporteur)
        livraison.numero_suivi = request.data.get("numero_suivi", livraison.numero_suivi)
        livraison.note = request.data.get("note", livraison.note)

        livraison.save()

        return Response(LivraisonEcommerceSerializer(livraison).data)



from e_commerce.serializers import EcommerceBannerSerializer


class EcommerceBannerListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = EcommerceBannerSerializer

    @swagger_auto_schema(
        operation_summary="Lister les bannières e-commerce",
        operation_description=(
            "Retourne toutes les bannières actives du site e-commerce.\n\n"
            "Une bannière peut être :\n"
            "- une image\n"
            "- une vidéo\n\n"
            "Les résultats sont triés selon ordre_affichage."
        ),
        responses={
            200: openapi.Response(
                description="Liste des bannières actives",
                schema=EcommerceBannerSerializer(many=True),
            ),
        },
        tags=["E-commerce Bannières"],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return EcommerceBanner.objects.filter(
            active=True
        ).order_by(
            "ordre_affichage",
            "-created_at",
        )
        


class EcommerceBannerDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = EcommerceBannerSerializer

    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"

    queryset = EcommerceBanner.objects.filter(
        active=True
    )

    @swagger_auto_schema(
        operation_summary="Détail d'une bannière e-commerce",
        operation_description=(
            "Retourne le détail d'une bannière active du site e-commerce.\n\n"
            "La bannière peut contenir :\n"
            "- une image\n"
            "- une vidéo\n"
            "- un bouton d'action\n"
            "- un lien de redirection"
        ),
        manual_parameters=[
            openapi.Parameter(
                "uuid",
                openapi.IN_PATH,
                description="UUID de la bannière",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_UUID,
                required=True,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Détail de la bannière",
                schema=EcommerceBannerSerializer,
            ),
            404: "Bannière introuvable",
        },
        tags=["E-commerce Bannières"],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
    
    

