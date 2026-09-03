# e_commerce/views.py

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.permissions import IsAdminOrManager
from e_commerce.models import (CommandeEcommerce, EcommerceBanner,
                               EcommerceBannerNouveauArrivage,
                               PaiementEcommerce)
from e_commerce.selectors.produits import get_ecommerce_produits
from e_commerce.serializers import (CommandeEcommerceCreateSerializer,
                                    CommandeEcommerceDetailSerializer,
                                    EcommerceBannerNouveauArrivageSerializer,
                                    EcommerceBannerSerializer,
                                    EcommerceProduitDetailSerializer,
                                    EcommerceProduitListSerializer,
                                    PaiementEcommerceSerializer)
from e_commerce.services.confirmation_paiement import confirm_ecommerce_payment
from e_commerce.services.payment import initiate_payment
from e_commerce.services.signatures_paiement import (
    verifier_signature_carte, verifier_signature_orange_money,
    verifier_signature_wave)
from sale.models import Client


class EcommerceHomeView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_id="ecommerceHome",
        operation_summary="Page d'accueil e-commerce",
        operation_description=(
            "Retourne toutes les données nécessaires "
            "à la page d'accueil e-commerce."
        ),
        tags=["E-commerce - Accueil"],
    )
    def get(self, request):

        banners = (
            EcommerceBanner.objects
            .filter(active=True)
            .order_by(
                "ordre_affichage",
                "-created_at",
            )
        )

        produits_recents = get_ecommerce_produits(
            bijouterie_id=request.query_params.get(
                "bijouterie_id"
            )
        )[:12]

        return Response({
            "banners": EcommerceBannerSerializer(
                banners,
                many=True,
                context={"request": request},
            ).data,

            "produits_recents": EcommerceProduitListSerializer(
                produits_recents,
                many=True,
                context={"request": request},
            ).data,
        })


# ============================================================
# BANNIÈRE PRINCIPALE E-COMMERCE
# ============================================================
class EcommerceBannerManageView(
    generics.RetrieveUpdateAPIView
):
    permission_classes = [IsAdminOrManager]
    serializer_class = EcommerceBannerSerializer
    queryset = EcommerceBanner.objects.all()

    @swagger_auto_schema(
        operation_id="detailBannerEcommerce",
        operation_summary="Consulter une bannière e-commerce",
        operation_description=(
            "Retourne une bannière e-commerce afin de permettre "
            "sa gestion depuis l'administration."
        ),
        responses={
            200: EcommerceBannerSerializer(),
            404: "Bannière introuvable.",
        },
        tags=["E-commerce - Banner"],
    )
    def get(self, request, *args, **kwargs):
        return super().get(
            request,
            *args,
            **kwargs,
        )

    @swagger_auto_schema(
        operation_id="modifierBannerEcommerce",
        operation_summary="Modifier une bannière e-commerce",
        operation_description=(
            "Permet de modifier la bannière de la page d'accueil.\n\n"
            "Il est possible de modifier :\n"
            "- l'image ;\n"
            "- le titre ;\n"
            "- le sous-titre ;\n"
            "- la description ;\n"
            "- le texte du bouton ;\n"
            "- le lien du bouton ;\n"
            "- l'ordre d'affichage ;\n"
            "- son état actif/inactif."
        ),
        request_body=EcommerceBannerSerializer,
        responses={
            200: EcommerceBannerSerializer(),
            400: "Données invalides.",
            404: "Bannière introuvable.",
        },
        tags=["E-commerce - Banner"],
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(
            request,
            *args,
            **kwargs,
        )

        
class CommandeEcommerceCreateView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    @swagger_auto_schema(
        operation_id="createEcommerceOrder",
        operation_summary="Créer une commande e-commerce",
        operation_description=(
            "Crée une commande e-commerce en attente de paiement.\n\n"
            "Le client doit être authentifié.\n\n"
            "Le backend :\n"
            "- identifie le client connecté ;\n"
            "- vérifie la bijouterie ;\n"
            "- vérifie les produits ;\n"
            "- effectue une première vérification de Stock.en_stock ;\n"
            "- ne réserve aucun stock ;\n"
            "- ne diminue aucun stock ;\n"
            "- calcule le montant HT ;\n"
            "- calcule la TVA ;\n"
            "- calcule les frais de transaction ;\n"
            "- calcule le montant final à payer ;\n"
            "- crée CommandeEcommerce = pending ;\n"
            "- crée PaiementEcommerce = pending.\n\n"
            "Aucune Vente, Facture ou sortie de stock n'est créée ici."
        ),
        request_body=CommandeEcommerceCreateSerializer,
        responses={
            201: openapi.Response(
                description="Commande créée",
                schema=CommandeEcommerceDetailSerializer,
            ),
            400: "Erreur de validation.",
            401: "Authentification requise.",
        },
        tags=["E-commerce"],
    )
    def post(self, request):
        serializer = CommandeEcommerceCreateSerializer(
            data=request.data,
            context={"request": request},
        )

        serializer.is_valid(raise_exception=True)

        commande = serializer.save()

        paiement = (
            commande.paiements
            .filter(
                status=PaiementEcommerce.STATUS_PENDING
            )
            .order_by("-created_at")
            .first()
        )

        if paiement is None:
            return Response(
                {
                    "detail": (
                        "Aucun paiement en attente "
                        "n'a été créé pour cette commande."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "commande": CommandeEcommerceDetailSerializer(
                    commande,
                    context={"request": request},
                ).data,

                "paiement": PaiementEcommerceSerializer(
                    paiement,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )


# ============================================================
# INITIALISER LE PAIEMENT
# ============================================================
class EcommercePaymentInitiateView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    @swagger_auto_schema(
        operation_id="initiateEcommercePayment",
        operation_summary="Initialiser un paiement e-commerce",
        operation_description=(
            "Initialise le paiement Wave, Orange Money "
            "ou carte bancaire d'une commande e-commerce.\n\n"
            "Règles :\n"
            "- le client doit être authentifié ;\n"
            "- la commande doit appartenir au client connecté ;\n"
            "- la commande doit être en attente de paiement ;\n"
            "- les informations client doivent être complètes ;\n"
            "- aucun stock n'est consommé à cette étape."
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["commande_uuid"],
            properties={
                "commande_uuid": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format=openapi.FORMAT_UUID,
                ),
            },
        ),
        responses={
            200: openapi.Response(
                description="Paiement initialisé",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "payment_uuid": openapi.Schema(
                            type=openapi.TYPE_STRING,
                        ),
                        "commande_uuid": openapi.Schema(
                            type=openapi.TYPE_STRING,
                        ),
                        "mode": openapi.Schema(
                            type=openapi.TYPE_STRING,
                        ),
                        "status": openapi.Schema(
                            type=openapi.TYPE_STRING,
                        ),
                        "montant": openapi.Schema(
                            type=openapi.TYPE_STRING,
                        ),
                        "checkout_url": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            nullable=True,
                        ),
                        "provider_reference": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            nullable=True,
                        ),
                    },
                ),
            ),
            400: "Commande invalide ou informations manquantes.",
            401: "Authentification requise.",
            403: "Aucun profil client associé au compte.",
            404: "Commande ou paiement introuvable.",
        },
        tags=["E-commerce"],
    )
    def post(self, request):
        # ========================================================
        # 1. UUID COMMANDE
        # ========================================================

        commande_uuid = request.data.get(
            "commande_uuid"
        )

        if not commande_uuid:
            return Response(
                {
                    "detail": (
                        "commande_uuid est obligatoire."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ========================================================
        # 2. CLIENT CONNECTÉ
        # ========================================================

        try:
            client = request.user.client

        except Client.DoesNotExist:
            return Response(
                {
                    "detail": (
                        "Aucun profil client n'est associé "
                        "à ce compte."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # ========================================================
        # 3. COMMANDE DU CLIENT CONNECTÉ
        # ========================================================

        commande = get_object_or_404(
            CommandeEcommerce.objects
            .select_related(
                "client",
                "bijouterie",
            ),
            uuid=commande_uuid,
            client=client,
        )

        # ========================================================
        # 4. STATUT COMMANDE
        # ========================================================

        if (
            commande.status
            == CommandeEcommerce.STATUS_PAID
        ):
            return Response(
                {
                    "detail": (
                        "Cette commande est déjà payée."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if (
            commande.status
            != CommandeEcommerce.STATUS_PENDING
        ):
            return Response(
                {
                    "detail": (
                        "Cette commande n'est pas disponible "
                        "pour le paiement."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ========================================================
        # 5. INFORMATIONS CLIENT OBLIGATOIRES
        # ========================================================

        champs_manquants = []

        if not commande.nom_client:
            champs_manquants.append(
                "nom_client"
            )

        if not commande.telephone_client:
            champs_manquants.append(
                "telephone_client"
            )

        if not commande.email_client:
            champs_manquants.append(
                "email_client"
            )

        if not commande.adresse_livraison:
            champs_manquants.append(
                "adresse_livraison"
            )

        if champs_manquants:
            return Response(
                {
                    "detail": (
                        "Les informations client "
                        "sont incomplètes."
                    ),
                    "champs_manquants":
                        champs_manquants,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ========================================================
        # 6. PAIEMENT PENDING
        # ========================================================

        paiement = (
            commande.paiements
            .filter(
                status=PaiementEcommerce.STATUS_PENDING
            )
            .order_by(
                "-created_at"
            )
            .first()
        )

        if paiement is None:
            return Response(
                {
                    "detail": (
                        "Aucun paiement en attente "
                        "pour cette commande."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # ========================================================
        # 7. INITIALISER LE PROVIDER
        #
        # IMPORTANT :
        # - aucun Stock.en_stock n'est diminué ici ;
        # - aucune Vente n'est créée ici ;
        # - aucune Facture n'est créée ici.
        # ========================================================

        paiement = initiate_payment(
            paiement=paiement
        )

        # ========================================================
        # 8. RÉPONSE
        # ========================================================

        return Response(
            {
                "payment_uuid":
                    str(paiement.uuid),

                "commande_uuid":
                    str(commande.uuid),

                "mode":
                    paiement.mode,

                "status":
                    paiement.status,

                "montant":
                    str(paiement.montant),

                "checkout_url":
                    paiement.checkout_url,

                "provider_reference":
                    paiement.provider_reference,
            },
            status=status.HTTP_200_OK,
        )
        
    
# ============================================================
# confirmation_paiement PAIEMENT
# ============================================================
class ConfirmationPaiementEcommerceView(APIView):
    permission_classes = [AllowAny]
    http_method_names = ["post", "options"]

    @swagger_auto_schema(
        operation_id="confirmationPaiementEcommerce",
        operation_summary="Confirmation du paiement e-commerce",
        operation_description=(
            "Reçoit la confirmation d'un paiement e-commerce.\n\n"
            "Le backend :\n"
            "- identifie le paiement concerné ;\n"
            "- vérifie l'authenticité du provider ;\n"
            "- vérifie le statut du paiement ;\n"
            "- vérifie le montant confirmé ;\n"
            "- traite la confirmation de manière atomique ;\n"
            "- effectue une seconde vérification du stock ;\n"
            "- crée la Vente ERP ;\n"
            "- crée la Facture ;\n"
            "- crée le Paiement ERP ;\n"
            "- diminue Stock.en_stock ;\n"
            "- crée InventoryMovement SALE_OUT ;\n"
            "- marque PaiementEcommerce = success ;\n"
            "- marque CommandeEcommerce = paid."
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=[
                "status",
                "montant",
            ],
            properties={
                "provider_reference": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    nullable=True,
                ),
                "transaction_id": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    nullable=True,
                ),
                "reference_paiement": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    nullable=True,
                ),
                "status": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    example="success",
                ),
                "montant": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    example="250000.00",
                ),
            },
        ),
        responses={
            200: "Paiement confirmé avec succès.",
            400: "Paiement non confirmé ou données invalides.",
            401: "Signature du provider invalide.",
            404: "Paiement introuvable.",
            501: "Provider non encore configuré.",
        },
        tags=["E-commerce"],
    )
    def post(self, request):
        # ========================================================
        # 1. CONSERVER LE CORPS BRUT
        #
        # Utile pour la vérification cryptographique
        # de certains providers.
        # ========================================================

        raw_body = request.body

        payload = request.data

        # ========================================================
        # 2. RÉFÉRENCE DU PAIEMENT
        # ========================================================

        provider_reference = (
            payload.get("provider_reference")
            or payload.get("transaction_id")
            or payload.get("reference_paiement")
        )

        if not provider_reference:
            return Response(
                {
                    "detail": (
                        "Une référence de paiement est obligatoire."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ========================================================
        # 3. RETROUVER LE PAIEMENT E-COMMERCE
        # ========================================================

        paiement = (
            PaiementEcommerce.objects
            .filter(
                provider_reference=provider_reference
            )
            .first()
        )

        if paiement is None:
            paiement = (
                PaiementEcommerce.objects
                .filter(
                    transaction_id=provider_reference
                )
                .first()
            )

        if paiement is None:
            paiement = (
                PaiementEcommerce.objects
                .filter(
                    reference_paiement=provider_reference
                )
                .first()
            )

        if paiement is None:
            return Response(
                {
                    "detail": (
                        "Paiement e-commerce introuvable."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # ========================================================
        # 4. VÉRIFIER L'AUTHENTICITÉ DU PROVIDER
        #
        # Aucun traitement ERP ne doit commencer
        # avant cette vérification.
        # ========================================================

        try:
            if (
                paiement.mode
                == PaiementEcommerce.MODE_WAVE
            ):
                verifier_signature_wave(
                    request
                )

            elif (
                paiement.mode
                == PaiementEcommerce.MODE_ORANGE
            ):
                verifier_signature_orange_money(
                    request
                )

            elif (
                paiement.mode
                == PaiementEcommerce.MODE_CARTE
            ):
                verifier_signature_carte(
                    request
                )

            else:
                raise ValidationError(
                    "Mode de paiement non pris en charge."
                )

        except NotImplementedError as exc:
            return Response(
                {
                    "detail": str(exc)
                },
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        except ValidationError as exc:
            return Response(
                {
                    "detail": (
                        exc.messages
                        if hasattr(exc, "messages")
                        else str(exc)
                    )
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # ========================================================
        # 5. CONFIRMER LE PAIEMENT
        #
        # confirm_ecommerce_payment() doit gérer :
        #
        # - statut provider ;
        # - montant provider ;
        # - transaction.atomic() ;
        # - select_for_update() paiement ;
        # - select_for_update() commande ;
        # - idempotence ;
        # - création Vente ;
        # - création Facture ;
        # - création Paiement ERP ;
        # - seconde vérification Stock ;
        # - consommation Stock ;
        # - SALE_OUT ;
        # - PaiementEcommerce success ;
        # - CommandeEcommerce paid.
        # ========================================================

        try:
            commande = confirm_ecommerce_payment(
                paiement=paiement,
                payload=payload,
            )

        except ValidationError as exc:
            return Response(
                {
                    "detail": (
                        exc.messages
                        if hasattr(exc, "messages")
                        else str(exc)
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ========================================================
        # 6. RÉPONSE
        # ========================================================

        return Response(
            {
                "detail": (
                    "Paiement confirmé avec succès."
                ),
                "commande_uuid": str(
                    commande.uuid
                ),
                "commande_status":
                    commande.status,
                "paiement_uuid": str(
                    paiement.uuid
                ),
                "paiement_status":
                    PaiementEcommerce.STATUS_SUCCESS,
            },
            status=status.HTTP_200_OK,
        )
        
        
# ============================================================
# DÉTAIL COMMANDE
class CommandeEcommerceDetailView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "options"]

    @swagger_auto_schema(
        operation_id="detailCommandeEcommerce",
        operation_summary="Détail d'une commande e-commerce",
        operation_description=(
            "Retourne le détail d'une commande e-commerce "
            "appartenant au client connecté."
        ),
        responses={
            200: CommandeEcommerceDetailSerializer,
            401: "Authentification requise.",
            403: "Aucun profil client associé au compte.",
            404: "Commande introuvable.",
        },
        tags=["E-commerce"],
        
    )
    def get(self, request, uuid):
        try:
            client = request.user.client

        except Client.DoesNotExist:
            return Response(
                {
                    "detail": (
                        "Aucun profil client n'est associé "
                        "à ce compte."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        commande = get_object_or_404(
            CommandeEcommerce.objects
            .select_related(
                "bijouterie",
                "client",
                "vente",
                "facture",
            )
            .prefetch_related(
                "lignes",
                "paiements",
            ),
            uuid=uuid,
            client=client,
        )

        return Response(
            CommandeEcommerceDetailSerializer(
                commande,
                context={"request": request},
            ).data,
            status=status.HTTP_200_OK,
        )
        
# ============================================================
# FACTURE E-COMMERCE
# ============================================================
class EcommerceInvoiceView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "options"]

    @swagger_auto_schema(
        operation_id="factureCommandeEcommerce",
        operation_summary=(
            "Récupérer la facture d'une commande e-commerce"
        ),
        operation_description=(
            "Retourne la facture associée à une commande "
            "appartenant au client connecté."
        ),
        responses={
            200: "Facture disponible.",
            401: "Authentification requise.",
            403: "Aucun profil client associé au compte.",
            404: "Commande ou facture introuvable.",
        },
        tags=["E-commerce"],
    )
    def get(self, request, uuid):
        try:
            client = request.user.client
        except Client.DoesNotExist:
            return Response(
                {
                    "detail": (
                        "Aucun profil client n'est associé "
                        "à ce compte."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        commande = get_object_or_404(
            CommandeEcommerce.objects
            .select_related(
                "facture",
                "client",
            ),
            uuid=uuid,
            client=client,
        )

        facture = commande.facture

        if facture is None:
            return Response(
                {
                    "detail": (
                        "La facture n'est pas encore disponible."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "numero_facture":
                    facture.numero_facture,

                "montant_ht":
                    str(facture.montant_ht),

                "montant_tva": (
                    str(facture.montant_tva)
                    if facture.montant_tva is not None
                    else "0.00"
                ),

                "frais_transaction":
                    str(facture.frais_transaction),

                "montant_total":
                    str(facture.montant_total),

                "facture_pdf": (
                    facture.facture_pdf.url
                    if facture.facture_pdf
                    else None
                ),
            },
            status=status.HTTP_200_OK,
        )
        
class EcommerceProduitListView(
    generics.ListAPIView
):
    permission_classes = [AllowAny]
    serializer_class = EcommerceProduitListSerializer

    @swagger_auto_schema(
        operation_id="listeProduitsEcommerce",
        operation_summary="Lister les produits e-commerce",
        operation_description=(
            "Retourne les produits publiés disponibles à la vente "
            "sur l'e-commerce.\n\n"
            "Règles :\n"
            "- produit publié ;\n"
            "- Stock.en_stock > 0 ;\n"
            "- stock rattaché à une bijouterie ;\n"
            "- prix calculé selon MarquePurete ;\n"
            "- possibilité de filtrer par bijouterie_id."
        ),
        manual_parameters=[
            openapi.Parameter(
                "bijouterie_id",
                openapi.IN_QUERY,
                description="Identifiant de la bijouterie",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
        ],
        responses={
            200: EcommerceProduitListSerializer(
                many=True
            ),
        },
        tags=["E-commerce - Catalogue"],
    )
    def get_queryset(self):
        return get_ecommerce_produits(
            bijouterie_id=(
                self.request.query_params.get(
                    "bijouterie_id"
                )
            )
        )
        

class EcommerceNouveauxArrivagesMediaView(
    generics.ListAPIView
):
    permission_classes = [AllowAny]

    serializer_class = (
        EcommerceBannerNouveauArrivageSerializer
    )

    @swagger_auto_schema(
        operation_id="nouveauxArrivagesMediaEcommerce",
        operation_summary=(
            "Afficher les médias des nouveaux arrivages"
        ),
        operation_description=(
            "Retourne les médias actifs de la section "
            "'Nouveaux arrivages'.\n\n"
            "Chaque élément peut être une image ou une vidéo.\n\n"
            "Les éléments sont retournés selon leur ordre "
            "d'affichage."
        ),
        responses={
            200: EcommerceBannerNouveauArrivageSerializer(
                many=True
            ),
        },
        tags=["E-commerce - Accueil"],
    )
    def get_queryset(self):
        return (
            EcommerceBannerNouveauArrivage.objects
            .filter(
                active=True,
            )
            .order_by(
                "ordre_affichage",
                "-created_at",
            )
        )
        
        
class EcommerceProduitsRecentsView(
    generics.ListAPIView
):
    permission_classes = [AllowAny]
    serializer_class = EcommerceProduitListSerializer

    @swagger_auto_schema(
        operation_id="produitsRecentsEcommerce",
        operation_summary="Lister les produits récents",
        operation_description=(
            "Retourne les 12 produits publiés et disponibles "
            "les plus récents.\n\n"
            "Possibilité de filtrer les produits par bijouterie."
        ),
        manual_parameters=[
            openapi.Parameter(
                "bijouterie_id",
                openapi.IN_QUERY,
                description="Identifiant de la bijouterie",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
        ],
        responses={
            200: EcommerceProduitListSerializer(
                many=True
            ),
        },
        tags=["E-commerce - Catalogue"],
    )
    def get_queryset(self):
        return get_ecommerce_produits(
            bijouterie_id=(
                self.request.query_params.get(
                    "bijouterie_id"
                )
            )
        )[:12]



# ============================================================
# DÉTAIL PRODUIT E-COMMERCE
# ============================================================
class EcommerceProduitDetailView(
    generics.RetrieveAPIView
):
    permission_classes = [AllowAny]
    serializer_class = EcommerceProduitDetailSerializer

    def get_queryset(self):
        bijouterie_id = self.request.query_params.get(
            "bijouterie_id"
        )

        if not bijouterie_id:
            return get_ecommerce_produits(
                bijouterie_id=None
            ).none()

        return get_ecommerce_produits(
            bijouterie_id=bijouterie_id
        )

    def get_object(self):
        bijouterie_id = self.request.query_params.get(
            "bijouterie_id"
        )

        if not bijouterie_id:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({
                "bijouterie_id": (
                    "bijouterie_id est obligatoire."
                )
            })

        queryset = self.get_queryset()

        obj = get_object_or_404(
            queryset,
            produit_line__produit__slug=self.kwargs["slug"],
        )

        self.check_object_permissions(
            self.request,
            obj,
        )

        return obj

    @swagger_auto_schema(
        operation_id="detailProduitEcommerce",
        operation_summary="Consulter un produit e-commerce",
        operation_description=(
            "Retourne le détail public d'un produit e-commerce.\n\n"
            "Le produit doit :\n"
            "- être publié ;\n"
            "- avoir un stock disponible ;\n"
            "- être rattaché à la bijouterie demandée ;\n"
            "- avoir un prix de vente configuré."
        ),
        manual_parameters=[
            openapi.Parameter(
                "bijouterie_id",
                openapi.IN_QUERY,
                description="Identifiant de la bijouterie",
                type=openapi.TYPE_INTEGER,
                required=True,
            ),
        ],
        responses={
            200: EcommerceProduitDetailSerializer(),
            400: "bijouterie_id est obligatoire.",
            404: "Produit introuvable ou indisponible.",
        },
        tags=["E-commerce - Catalogue"],
    )
    def get(self, request, *args, **kwargs):
        return super().get(
            request,
            *args,
            **kwargs,
        )
        

