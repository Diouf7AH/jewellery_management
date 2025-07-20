import random
import string

# from weasyprint import HTML
# import weasyprint
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
# import phonenumbers
# from phonenumbers import PhoneNumber
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from decimal import Decimal

from backend.renderers import UserRenderer
from sale.models import Client, Facture, Paiement, Vente, VenteProduit
from sale.serializers import (ClientSerializer, VenteSerializer, FactureSerializer,
                            PaiementSerializer, VenteProduitSerializer,
                            VenteDetailSerializer)
from django.db import models
from store.models import Produit
from vendor.models import Vendor, VendorProduit
from decimal import Decimal, InvalidOperation

from django.db.models import Sum
from django.utils.timezone import now
from django.shortcuts import get_object_or_404

from sale.models import VenteProduit
from vendor.models import Vendor


# class VenteProduitCreateView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Créer une vente (directe ou via commande)",
#         operation_description="Gère une vente directe ou issue d’une commande client.",
#         manual_parameters=[
#             openapi.Parameter(
#                 'vendor_email',
#                 openapi.IN_QUERY,
#                 description="Email du vendeur (obligatoire pour admin/manager)",
#                 type=openapi.TYPE_STRING
#             )
#         ],
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["produits", "client"],
#             properties={
#                 "client": openapi.Schema(
#                     type=openapi.TYPE_OBJECT,
#                     properties={
#                         "nom": openapi.Schema(type=openapi.TYPE_STRING),
#                         "prenom": openapi.Schema(type=openapi.TYPE_STRING),
#                         "telephone": openapi.Schema(type=openapi.TYPE_STRING),
#                     }
#                 ),
#                                 "numero_commande": openapi.Schema(
#                     type=openapi.TYPE_STRING,
#                     description="Numéro de la commande client source (optionnel)"
#                 ),
#                 "produits": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["slug", "quantite"],
#                         properties={
#                             "slug": openapi.Schema(type=openapi.TYPE_STRING),
#                             "quantite": openapi.Schema(type=openapi.TYPE_INTEGER),
#                             "prix_vente_grammes": openapi.Schema(type=openapi.TYPE_NUMBER),
#                             "remise": openapi.Schema(type=openapi.TYPE_NUMBER),
#                             "autres": openapi.Schema(type=openapi.TYPE_NUMBER),
#                             "tax": openapi.Schema(type=openapi.TYPE_NUMBER),
#                         }
#                     )
#                 )
#             }
#         ),
#         responses={201: "Création réussie", 400: "Erreur", 403: "Accès refusé"}
#     )
#     @transaction.atomic
#     def post(self, request):
#         try:
#             user = request.user
#             role = getattr(user.user_role, 'role', None)
#             if role not in ['admin', 'manager', 'vendor']:
#                 return Response({"message": "⛔ Accès refusé"}, status=403)

#             data = request.data
#             client_data = data.get('client')
#             if not client_data:
#                 return Response({"error": "Les informations du client sont requises."}, status=400)

#             client, _ = Client.objects.get_or_create(
#                 nom=client_data['nom'],
#                 prenom=client_data['prenom'],
#                 defaults={"telephone": client_data.get("telephone", "")}
#             )

#             commande_source = None
#             numero_commande = data.get("numero_commande")
#             if commande_source:
#                 from order.models import CommandeClient
#                 try:
#                     commande_source = CommandeClient.objects.get(numero_commande=numero_commande)
#                 except CommandeClient.DoesNotExist:
#                     return Response({"error": "Commande client source introuvable."}, status=404)

#             # 🔁 Vendor (vendeur concerné)
#             vendor_email = request.query_params.get("vendor_email")
#             if role == "vendor":
#                 try:
#                     vendor = Vendor.objects.get(user=user)
#                 except Vendor.DoesNotExist:
#                     return Response({"error": "Aucun compte vendeur lié."}, status=404)
#             else:
#                 if not vendor_email:
#                     return Response({"error": "vendor_email requis pour admin/manager."}, status=400)
#                 try:
#                     vendor = Vendor.objects.get(user__email=vendor_email)
#                 except Vendor.DoesNotExist:
#                     return Response({"error": "Vendeur introuvable."}, status=404)

#             vente = Vente.objects.create(
#                 client=client,
#                 created_by=user,
#                 commande_source=commande_source
#             )

#             produits_data = data.get("produits", [])
#             if not produits_data:
#                 return Response({"error": "Aucun produit fourni."}, status=400)

#             for item in produits_data:
#                 slug = item.get("slug")
#                 quantite = int(item.get("quantite", 0))
#                 if not slug or quantite <= 0:
#                     return Response({"error": f"Produit ou quantité invalide : {slug}"}, status=400)

#                 try:
#                     produit = Produit.objects.get(slug=slug)
#                 except Produit.DoesNotExist:
#                     return Response({"error": f"Produit introuvable: {slug}"}, status=404)

#                 prix_vente_grammes = Decimal(str(item.get("prix_vente_grammes", produit.marque.prix)))
#                 remise = Decimal(str(item.get("remise", 0)))
#                 autres = Decimal(str(item.get("autres", 0)))
#                 tax = Decimal(str(item.get("tax", 0)))

#                 try:
#                     stock_vendeur = VendorProduit.objects.get(vendor=vendor, produit=produit)
#                 except VendorProduit.DoesNotExist:
#                     return Response({"error": f"{produit.nom} non disponible pour ce vendeur."}, status=400)

#                 if stock_vendeur.quantite < quantite:
#                     return Response({"error": f"Stock insuffisant pour {produit.nom}."}, status=400)

#                 VenteProduit.objects.create(
#                     vente=vente,
#                     produit=produit,
#                     quantite=quantite,
#                     prix_vente_grammes=prix_vente_grammes,
#                     remise=remise,
#                     autres=autres,
#                     tax=tax,
#                     vendor=vendor
#                 )

#                 stock_vendeur.quantite -= quantite
#                 stock_vendeur.save()

#             facture = Facture.objects.create(
#                 vente=vente,
#                 numero_facture=Facture.generer_numero_unique(),
#                 montant_total=vente.montant_total
#             )

#             return Response(VenteDetailSerializer(vente).data, status=201)

#         except Exception as e:
#             transaction.set_rollback(True)
#             return Response({"detail": str(e)}, status=500)



# class VenteDirecteView(APIView):
class VenteProduitCreateView(APIView):
        renderer_classes = [UserRenderer]
        permission_classes = [IsAuthenticated]

        @swagger_auto_schema(
            operation_summary="Créer une vente avec produits, client et facture",
            operation_description="Créer une vente avec des produits associés (par QR code), mise à jour du stock, génération automatique de la facture. Un admin peut spécifier un `vendor_email`.",
            manual_parameters=[
                openapi.Parameter(
                    'vendor_email',
                    openapi.IN_QUERY,
                    description="Email du vendeur (optionnel, requis si admin/manager veut vendre à la place d’un vendeur)",
                    type=openapi.TYPE_STRING
                )
            ],
            request_body=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                required=["produits"],
                properties={
                    "client": openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        required=["nom", "prenom"],
                        properties={
                            "nom": openapi.Schema(type=openapi.TYPE_STRING, description="Nom du client"),
                            "prenom": openapi.Schema(type=openapi.TYPE_STRING, description="Prénom du client"),
                            "telephone": openapi.Schema(type=openapi.TYPE_STRING, example="770000000", description="Téléphone (optionnel)"),
                        }
                    ),
                    "produits": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            required=["slug", "quantite"],
                            properties={
                                "slug": openapi.Schema(type=openapi.TYPE_STRING),
                                "quantite": openapi.Schema(type=openapi.TYPE_INTEGER),
                                "prix_vente_grammes": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal"),
                                "remise": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal"),
                                "autres": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal"),
                                "tax": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal"),
                            }
                        )
                    )
                }
            ),
            responses={201: "Création réussie", 400: "Requête invalide", 403: "Accès refusé", 500: "Erreur serveur"}
        )
        @transaction.atomic
        def post(self, request):
            try:
                user = request.user
                role = getattr(user.user_role, 'role', None)
                if role not in ['admin', 'manager', 'vendor']:
                    return Response({"message": "Access Denied"}, status=403)

                data = request.data
                client_data = data.get('client')
                client_data = data.get('client', {})
                if not client_data.get("nom") or not client_data.get("prenom"):
                    return Response({"error": "Les champs 'nom' et 'prenom' du client sont obligatoires."}, status=400)

                telephone = client_data.get("telephone", "").strip()

                if telephone:
                    client, _ = Client.objects.get_or_create(
                        telephone=telephone,
                        defaults={"nom": client_data["nom"], "prenom": client_data["prenom"]}
                    )
                else:
                    client, _ = Client.objects.get_or_create(
                        nom=client_data["nom"],
                        prenom=client_data["prenom"]
                    )

                vente = Vente.objects.create(client=client, created_by=user)
                vente_produits = []

                # 🔁 Vendor selection
                vendor_email = request.query_params.get('vendor_email')
                if role == 'vendor':
                    try:
                        vendor = Vendor.objects.get(user=user)
                    except Vendor.DoesNotExist:
                        return Response({"error": "Vous n'êtes pas associé à un compte vendeur."}, status=400)
                else:
                    if not vendor_email:
                        return Response({"error": "vendor_email est requis pour les admins et managers."}, status=400)
                    try:
                        vendor = Vendor.objects.select_related('user').get(user__email=vendor_email)
                    except Vendor.DoesNotExist:
                        return Response({"error": "Vendeur introuvable avec cet email."}, status=404)

                for item in data.get('produits', []):
                    slug = item['slug']
                    quantite = int(item.get('quantite', 0))
                    if quantite <= 0:
                        return Response({"error": f"Quantité invalide pour le produit {slug}."}, status=400)

                    try:
                        produit = Produit.objects.select_related('marque').get(slug=slug)
                    except Produit.DoesNotExist:
                        return Response({"error": f"Produit avec QR code {slug} introuvable."}, status=404)

                    try:
                        brut = item.get('prix_vente_grammes')
                        prix_vente_grammes = Decimal(str(brut)) if brut and Decimal(str(brut)) > 0 else Decimal(str(produit.marque.prix))
                    except (InvalidOperation, AttributeError, TypeError):
                        return Response({"error": f"Prix de vente invalide pour le produit {slug}."}, status=400)

                    remise = Decimal(str(item.get('remise') or 0))
                    autres = Decimal(str(item.get('autres') or 0))
                    tax = Decimal(str(item.get('tax') or 0))

                    try:
                        vendor_stock = VendorProduit.objects.get(produit=produit, vendor=vendor)
                    except VendorProduit.DoesNotExist:
                        return Response({"error": f"Produit {produit.nom} non disponible dans le stock du vendeur."}, status=400)

                    if vendor_stock.quantite < quantite:
                        return Response({
                            "error": f"Stock insuffisant pour {produit.nom}. Stock disponible : {vendor_stock.quantite}"
                        }, status=400)

                    vente_produit = VenteProduit(
                        vente=vente,
                        produit=produit,
                        quantite=quantite,
                        prix_vente_grammes=prix_vente_grammes,
                        remise=remise,
                        autres=autres,
                        tax=tax,
                        vendor=vendor
                    )
                    vente_produit.save()  # ✅ calcul automatique du HT/TTC ici
                    vente_produits.append(vente_produit)
                    vendor_stock.quantite -= quantite
                    vendor_stock.save()


                # ✅ Génération du numéro de facture
                numero = Facture.generer_numero_unique()
                facture = Facture.objects.create(
                    vente=vente,
                    montant_total=vente.montant_total,
                    numero_facture=numero,
                    type_facture='vente_directe'
                )

                vente_detail = VenteDetailSerializer(vente)
                return Response(vente_detail.data, status=status.HTTP_201_CREATED)

            except Exception as e:
                transaction.set_rollback(True)
                return Response({"detail": str(e)}, status=500)



class ListFactureView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        responses={200: openapi.Response('response description', FactureSerializer)},
    )
    def get(self, request):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager' and request.user.user_role.role != 'vendor' and request.user.user_role.role != 'cashier':
            return Response({"message": "Access Denied"})
        factures = Facture.objects.all()
        serializer = FactureSerializer(factures, many=True)
        return Response(serializer.data)


class RechercherFactureView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        responses={200: openapi.Response('response description', FactureSerializer)},
    )
    def get(self, request, numero_facture):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager' and request.user.user_role.role != 'vendor' and request.user.user_role.role != 'cashier':
            return Response({"message": "Access Denied"})
        try:
            # Recherche du produit par son code
            facture = Facture.objects.get(numero_facture=numero_facture)
        except Facture.DoesNotExist:
            raise NotFound("Facture non trouvé avec ce numero de facture.")

        # Sérialisation des données du produit
        serializer = FactureSerializer(facture)
        return Response(serializer.data)



class PaiementFactureView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    
    ROLES_AUTORISES_COMME_CAISSIER = ['admin', 'manager', 'cashier']

    @swagger_auto_schema(
        operation_description="Effectuer un paiement pour une facture donnée par son numéro.",
        request_body=PaiementSerializer,
        responses={
            201: openapi.Response("Paiement enregistré avec succès", PaiementSerializer),
            400: openapi.Response("Requête invalide"),
            403: openapi.Response("Accès interdit"),
            404: openapi.Response("Facture introuvable")
        }
    )
    def post(self, request, facture_numero):
        role = getattr(request.user.user_role, 'role', None)
        if role not in self.ROLES_AUTORISES_COMME_CAISSIER:
            return Response({"message": "Access Denied"}, status=403)

        try:
            # facture = Facture.objects.get(numero_facture=facture_numero)
            facture_numero = facture_numero.strip()
            facture = Facture.objects.get(numero_facture__iexact=facture_numero)
        except Facture.DoesNotExist:
            return Response({"detail": "Facture introuvable."}, status=404)

        if facture.status == 'Payé':
            return Response({'error': 'La facture est déjà réglée'}, status=400)

        # ✅ UTILISATION DE validated_data
        serializer = PaiementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # ➜ ça appelle automatiquement validate_montant_paye du serializer

        montant_paye = serializer.validated_data['montant_paye']
        mode_paiement = serializer.validated_data.get('mode_paiement', 'cash')
        
        if facture.total_paye + montant_paye > facture.montant_total:
            return Response({
                'error': f"Le solde restant est de {facture.reste_a_payer}. Veuillez saisir un montant inférieur ou égal."
            }, status=400)

        paiement = Paiement.objects.create(
            facture=facture,
            montant_paye=montant_paye,
            mode_paiement=mode_paiement,
            created_by=request.user
        )

        # ✅ Mise à jour du statut de la facture
        if facture.total_paye >= facture.montant_total and facture.status != "Payé":
            facture.status = "Payé"
            facture.save()

        return Response({
            'message': 'Paiement enregistré avec succès',
            'paiement': PaiementSerializer(paiement).data,
            'total_paye': str(facture.total_paye),
            'reste_a_payer': str(facture.reste_a_payer),
            'statut_facture': facture.status
        }, status=201)




class VentListAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Liste des ventes. Le vendeur voit ses ventes, les autres voient toutes les ventes.",
        responses={200: openapi.Response('Liste des ventes', VenteSerializer(many=True))}
    )
    def get(self, request):
        role = getattr(request.user.user_role, 'role', None)

        if role not in ['admin', 'manager', 'vendor', 'cashier']:
            return Response({"message": "Access Denied"}, status=403)

        if role == 'vendor':
            try:
                vendor = Vendor.objects.get(user=request.user)
                ventes = Vente.objects.filter(produits__vendor=vendor).distinct()
            except Vendor.DoesNotExist:
                return Response({"error": "Aucun vendeur associé à cet utilisateur."}, status=400)
        else:
            ventes = Vente.objects.all()

        serializer = VenteSerializer(ventes, many=True)
        return Response(serializer.data)




class RapportVentesMensuelAPIView(APIView):
    permission_classes = [IsAuthenticated]
    allowed_roles = ['admin', 'manager']

    @swagger_auto_schema(
        operation_description="Rapport des ventes mensuelles, avec option de filtrage par téléphone du vendeur.",
        manual_parameters=[
            openapi.Parameter(
                'mois', openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Mois à filtrer au format YYYY-MM (ex: 2025-06)",
                required=False
            ),
            openapi.Parameter(
                'vendor_telephone', openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Téléphone exact du vendeur à filtrer",
                required=False
            ),
        ],
        responses={200: openapi.Response(description="Rapport JSON des ventes mensuelles")}
    )
    def get(self, request):
        user_role = getattr(request.user.user_role, 'role', None)
        if user_role not in self.allowed_roles:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        mois = request.GET.get('mois', now().strftime('%Y-%m'))
        vendor_telephone = request.GET.get('vendor_telephone')

        try:
            annee, mois_num = map(int, mois.split('-'))
        except ValueError:
            return Response({"detail": "Format de mois invalide. Format attendu : YYYY-MM"}, status=400)

        ventes = VenteProduit.objects.filter(
            vente__created_at__year=annee,
            vente__created_at__month=mois_num
        )

        vendeur_nom = "Tous les vendeurs"
        if vendor_telephone:
            vendor = get_object_or_404(Vendor, user__telephone=vendor_telephone)
            ventes = ventes.filter(produit__in=vendor.vendor_produits.values('produit'))
            vendeur_nom = f"{vendor.user.first_name} {vendor.user.last_name}".strip()

        montant_total = ventes.aggregate(total=Sum('sous_total_prix_vent'))['total'] or 0

        ventes_list = [
            {
                "date": v.vente.created_at.strftime("%Y-%m-%d"),
                "produit": v.produit.nom,
                "quantite": v.quantite,
                "montant": float(v.sous_total_prix_vent),
            }
            for v in ventes
        ]

        return Response({
            "mois": mois,
            "vendeur": vendeur_nom,
            "total_ventes": ventes.count(),
            "montant_total": float(montant_total),
            "ventes": ventes_list
        }, status=200)

