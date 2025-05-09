import random
import string
from decimal import Decimal
from django.db.models import Q
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
# import phonenumbers
# from phonenumbers import PhoneNumber
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.template.loader import get_template
from xhtml2pdf import pisa
from dateutil.relativedelta import relativedelta
from django.utils import timezone


from backend.renderers import UserRenderer
from stock.models import Stock
from store.models import Produit

from .models import Achat, AchatProduit, Fournisseur
from .serializers import (AchatProduitSerializer, AchatSerializer,
                        FournisseurSerializer)

from django.db.models import Sum, Count
from django.utils.dateparse import parse_date
import logging
logger = logging.getLogger(__name__)

# Create your views here.

allowed_roles = ['admin', 'manager', 'vendeur']

class FournisseurGetView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Récupère les informations d'un fournisseur par son ID.",
        responses={
            200: FournisseurSerializer(),
            403: openapi.Response(description="Accès refusé"),
            404: openapi.Response(description="Fournisseur introuvable"),
        }
    )
    def get(self, request, pk, format=None):
        user_role = getattr(request.user.user_role, 'role', None)
        if user_role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        try:
            fournisseur = Fournisseur.objects.get(pk=pk)
        except Fournisseur.DoesNotExist:
            return Response({"detail": "Fournisseur not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = FournisseurSerializer(fournisseur)
        return Response(serializer.data, status=200)

# PUT: mise à jour complète (tous les champs doivent être fournis)
# PATCH: mise à jour partielle (champs optionnels)
# Swagger : la doc est affichée proprement pour chaque méthode
# Contrôle des rôles (admin, manager)
class FournisseurUpdateView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Met à jour complètement un fournisseur (remplace tous les champs).",
        request_body=FournisseurSerializer,
        responses={
            200: FournisseurSerializer(),
            400: "Requête invalide",
            403: "Accès refusé",
            404: "Fournisseur introuvable",
        }
    )
    def put(self, request, pk, format=None):
        return self.update_fournisseur(request, pk, partial=False)

    @swagger_auto_schema(
        operation_description="Met à jour partiellement un fournisseur (seuls les champs fournis sont modifiés).",
        request_body=FournisseurSerializer,
        responses={
            200: FournisseurSerializer(),
            400: "Requête invalide",
            403: "Accès refusé",
            404: "Fournisseur introuvable",
        }
    )
    def patch(self, request, pk, format=None):
        return self.update_fournisseur(request, pk, partial=True)

    def update_fournisseur(self, request, pk, partial):
        user_role = getattr(request.user.user_role, 'role', None)
        if user_role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        try:
            fournisseur = Fournisseur.objects.get(pk=pk)
        except Fournisseur.DoesNotExist:
            return Response({"detail": "Fournisseur not found"}, status=404)

        serializer = FournisseurSerializer(fournisseur, data=request.data, partial=partial)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)


class FournisseurListView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Liste tous les fournisseurs, avec option de recherche par nom ou téléphone via le paramètre `search`.",
        manual_parameters=[
            openapi.Parameter(
                'search', openapi.IN_QUERY,
                description="Nom ou téléphone à rechercher",
                type=openapi.TYPE_STRING
            )
        ],
        responses={200: FournisseurSerializer(many=True)}
    )
    def get(self, request):
        user_role = getattr(request.user.user_role, 'role', None)
        if user_role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        search = request.query_params.get('search', '')
        fournisseurs = Fournisseur.objects.all()
        if search:
            fournisseurs = fournisseurs.filter(
                Q(nom__icontains=search) | Q(prenom__icontains=search) | Q(telephone__icontains=search)
            )

        serializer = FournisseurSerializer(fournisseurs, many=True)
        return Response(serializer.data, status=200)


class FournisseurDeleteView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Supprime un fournisseur à partir de son ID.",
        responses={
            204: "Fournisseur supprimé avec succès",
            403: "Accès refusé",
            404: "Fournisseur introuvable",
        }
    )
    def delete(self, request, pk, format=None):
        role = getattr(request.user.user_role, 'role', None)
        if role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        try:
            fournisseur = Fournisseur.objects.get(pk=pk)
        except Fournisseur.DoesNotExist:
            return Response({"detail": "Fournisseur not found"}, status=404)

        fournisseur.delete()
        return Response({"message": "Fournisseur supprimé avec succès."}, status=204)


class AchatDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Dashboard des achats filtré par période dynamique (en mois)",
        manual_parameters=[
            openapi.Parameter(
                'mois',
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                enum=[1, 3, 6, 12],
                default=3,
                description="Nombre de mois à remonter"
            )
        ],
        responses={200: openapi.Response(description="Statistiques + achats récents")}
    )
    def get(self, request):
        user_role = getattr(request.user.user_role, 'role', None)
        if user_role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        # Lire le paramètre "mois" dans l'URL, défaut = 3
        try:
            nb_mois = int(request.GET.get('mois', 3))
            nb_mois = max(1, min(nb_mois, 12))  # sécurise entre 1 et 12
        except ValueError:
            nb_mois = 3

        depuis = timezone.now() - relativedelta(months=nb_mois)

        achats = Achat.objects.filter(created_at__gte=depuis)

        stats = achats.aggregate(
            total_achats=Count('id'),
            montant_total_ht=Sum('montant_total_ht'),
            montant_total_ttc=Sum('montant_total_ttc')
        )

        achats_recents = achats.order_by('-created_at')[:10]
        achats_serializer = AchatSerializer(achats_recents, many=True)

        return Response({
            "periode": {
                "mois": nb_mois,
                "depuis": depuis.date().isoformat(),
                "jusqu_a": timezone.now().date().isoformat()
            },
            "statistiques": stats,
            "achats_recents": achats_serializer.data
        })

class AchatProduitCreateView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Créer un achat avec produits associés",
        operation_description="Crée un achat avec les produits, met à jour le stock et retourne les détails montant_total_tax() methode pour calculer le tax total .",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["fournisseur", "produits"],
            properties={
                "fournisseur": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    required=["nom", "prenom", "telephone"],
                    properties={
                        "nom": openapi.Schema(type=openapi.TYPE_STRING),
                        "prenom": openapi.Schema(type=openapi.TYPE_STRING),
                        "telephone": openapi.Schema(type=openapi.TYPE_STRING),
                        "address": openapi.Schema(type=openapi.TYPE_STRING),
                    }
                ),
                "produits": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        required=["produit", "quantite", "prix_achat_gramme"],
                        properties={
                            "produit": openapi.Schema(type=openapi.TYPE_OBJECT, properties={"id": openapi.Schema(type=openapi.TYPE_INTEGER)}),
                            "quantite": openapi.Schema(type=openapi.TYPE_INTEGER),
                            "prix_achat_gramme": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal"),
                            "tax": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal", default=0),
                        }
                    )
                )
            }
        ),
        responses={
            201: openapi.Response("Création réussie", AchatSerializer),
            400: "Requête invalide",
            403: "Accès refusé"
        }
    )
    @transaction.atomic
    def post(self, request):
        user = request.user
        if not user.user_role or user.user_role.role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        try:
            data = request.data
            fournisseur_data = data.get('fournisseur')
            fournisseur, _ = Fournisseur.objects.get_or_create(
                telephone=fournisseur_data['telephone'],
                defaults={
                    'nom': fournisseur_data['nom'],
                    'prenom': fournisseur_data['prenom'],
                    'address': fournisseur_data.get('address', '')
                }
            )

            achat = Achat.objects.create(fournisseur=fournisseur)
            stock_map = {}

            for item in data.get('produits', []):
                produit_id = item['produit']['id']
                quantite = int(item['quantite'])
                prix_achat_gramme = Decimal(item['prix_achat_gramme'])
                tax = Decimal(item.get('tax', 0))

                produit = Produit.objects.get(id=produit_id)

                # Créer et sauvegarder chaque AchatProduit (le modèle calcule lui-même le sous-total + mise à jour achat)
                AchatProduit.objects.create(
                    achat=achat,
                    produit=produit,
                    quantite=quantite,
                    prix_achat_gramme=prix_achat_gramme,
                    tax=tax,
                    fournisseur=fournisseur
                )

                # Mise à jour stock
                stock, _ = Stock.objects.get_or_create(produit=produit, defaults={"quantite": 0})
                stock.quantite += quantite
                stock.save()
                stock_map[produit.id] = stock.quantite

            # Mise à jour des totaux HT/TTC
            achat.update_total()

            return Response({
                "message": "Achat créé avec succès",
                "achat": AchatSerializer(achat).data,
                "stock": stock_map
            }, status=201)

        except Produit.DoesNotExist:
            return Response({"detail": "Produit introuvable."}, status=400)
        except Exception as e:
            return Response({"detail": str(e)}, status=500)


# class AchatProduitCreateView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Créer un achat avec produits associés",
#         operation_description="Crée un achat avec les produits, met à jour le stock et retourne les détails.",
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["fournisseur", "produits"],
#             properties={
#                 "fournisseur": openapi.Schema(
#                     type=openapi.TYPE_OBJECT,
#                     required=["nom", "prenom", "telephone"],
#                     properties={
#                         "nom": openapi.Schema(type=openapi.TYPE_STRING),
#                         "prenom": openapi.Schema(type=openapi.TYPE_STRING),
#                         "telephone": openapi.Schema(type=openapi.TYPE_STRING),
#                         "address": openapi.Schema(type=openapi.TYPE_STRING),
#                     }
#                 ),
#                 "produits": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["produit", "quantite", "prix_achat_gramme"],
#                         properties={
#                             "produit": openapi.Schema(
#                                 type=openapi.TYPE_OBJECT,
#                                 properties={"id": openapi.Schema(type=openapi.TYPE_INTEGER)}
#                             ),
#                             "quantite": openapi.Schema(type=openapi.TYPE_INTEGER),
#                             "prix_achat_gramme": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal"),
#                             "tax": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal", default=0),
#                         }
#                     )
#                 )
#             }
#         ),
#         responses={
#             201: openapi.Response("Création réussie", AchatSerializer),
#             400: "Requête invalide",
#             403: "Accès refusé"
#         }
#     )
#     @transaction.atomic
#     def post(self, request):
#         user = request.user
#         if not user.user_role or user.user_role.role not in ['admin', 'manager']:
#             return Response({"message": "Access Denied"}, status=403)

#         try:
#             data = request.data
#             fournisseur_data = data.get('fournisseur')
#             fournisseur, _ = Fournisseur.objects.get_or_create(
#                 telephone=fournisseur_data['telephone'],
#                 defaults={
#                     'nom': fournisseur_data['nom'],
#                     'prenom': fournisseur_data['prenom'],
#                     'address': fournisseur_data.get('address', '')
#                 }
#             )

#             achat = Achat.objects.create(fournisseur=fournisseur)
#             produits_data = data.get('produits', [])

#             achat_produits = []
#             montant_total_ht = Decimal(0)
#             montant_total_ttc = Decimal(0)
#             stock_map = {}

#             for item in produits_data:
#                 produit_id = item['produit']['id']
#                 quantite = int(item['quantite'])
#                 prix_achat_gramme = Decimal(item['prix_achat_gramme'])
#                 tax = Decimal(item.get('tax', 0))

#                 produit = Produit.objects.get(id=produit_id)
#                 poids = produit.poids or 1
#                 sous_total = prix_achat_gramme * quantite * poids

#                 achat_produits.append(AchatProduit(
#                     achat=achat,
#                     produit=produit,
#                     quantite=quantite,
#                     prix_achat_gramme=prix_achat_gramme,
#                     tax=tax,
#                     fournisseur=fournisseur,
#                     sous_total_prix_achat=sous_total
#                 ))

#                 stock, _ = Stock.objects.get_or_create(produit=produit, defaults={"quantite": 0})
#                 stock.quantite += quantite
#                 stock.save()

#                 montant_total_ht += sous_total
#                 montant_total_ttc += sous_total + tax
#                 stock_map[produit.id] = stock.quantite

#             AchatProduit.objects.bulk_create(achat_produits)
#             achat.montant_total_ht = montant_total_ht
#             achat.montant_total_ttc = montant_total_ttc
#             achat.save()

#             return Response({
#                 "message": "Achat créé avec succès",
#                 "achat": AchatSerializer(achat).data,
#                 "stock": stock_map
#             }, status=201)

#         except Produit.DoesNotExist:
#             return Response({"detail": "Produit introuvable."}, status=400)
#         except Fournisseur.DoesNotExist:
#             return Response({"detail": "Fournisseur introuvable."}, status=400)
#         except Exception as e:
#             return Response({"detail": str(e)}, status=500)


# class AchatProduitCreateView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Créer un achat avec les produits associés. Met à jour le stock et calcule le montant total.",
#         request_body=AchatSerializer,
#         responses={
#             201: openapi.Response("Achat créé avec succès", AchatSerializer),
#             400: openapi.Response("Erreur de requête", openapi.Schema(
#                 type=openapi.TYPE_OBJECT,
#                 properties={"detail": openapi.Schema(type=openapi.TYPE_STRING)}
#             ))
#         }
#     )
#     @transaction.atomic
#     def post(self, request):
#         """Create a new Achat record and associated AchatProduit records"""
#         user_role = getattr(request.user.user_role, 'role', None)
#         if user_role not in ['admin', 'manager']:
#             return Response({"message": "Access Denied"}, status=403)
#         try:
#             # Get Fournisseur and Produit information from the request data
#             data = request.data
#             fournisseur_data = data.get('fournisseur')
#             # produits_data = data.get('produit')  # Should be a list of dicts, e.g., [{'produit_id': 1, 'quantity': 3}]
#             # quantities = request.data.get('quantities')

#             # Récupérer les données du fournisseur
#             fournisseur, created = Fournisseur.objects.get_or_create(
#                 telephone=fournisseur_data['telephone'],
#                 # id=fournisseur_data['id'],
#                 # prenom=client_data['prenom'],
#                 # defaults={
#                 #     'nom': fournisseur_data['nom'],
#                 #     'prenom': fournisseur_data['prenom']
#                 #     }
#                 defaults=fournisseur_data
#             )

#             # Create Achat record
#             achat = Achat.objects.create(fournisseur=fournisseur)

#             # Liste pour les objets venteProduit
#             achat_produits = []
#             montant_total = 0
#             stock_map = {}
#             # Create AchatProduit records
#             for item in data.get('produits', []):
#                 produit = Produit.objects.get(id=item['produit']['id']) 
#                 # total_price = produit.price * quantity
#                 quantite = item['quantite']
#                 prix_achat_gramme = item['prix_achat_gramme']
#                 tax = item['tax']
#                 # tax = produit.prix_achat_avec_tax
                
#                 quantite = int(item.get('quantite', 0))
#                 prix_achat_gramme = Decimal(item.get('prix_achat_gramme', 0))
#                 tax = Decimal(item.get('tax', 0))
                
#                 if quantite <= 0:
#                     return Response({"detail": f"Quantité invalide pour le produit {produit.id}"}, status=status.HTTP_400_BAD_REQUEST)

#                 poids = produit.poids or 0
#                 prix_achat = prix_achat_gramme*poids
#                 sous_total_prix_achat = prix_achat*quantite

#                 # achat_produit = AchatProduit.objects.create(
#                 achat_produit = AchatProduit(
#                     achat=achat,
#                     produit=produit,
#                     fournisseur = fournisseur,
#                     quantite=quantite,
#                     prix_achat_gramme=prix_achat_gramme,
#                     tax=tax,
#                     sous_total_prix_achat=sous_total_prix_achat,
#                     # montant_total_tax_inclue=montant_total_tax_inclue,
#                     # sous_total_prix_achat=sous_total_prix_achat
#                 )
#                 achat_produits.append(achat_produit)
#                 # montant_total += prix_vente * quantite
#                 montant_total += sous_total_prix_achat

#                 # Update stock: If the produit exists in stock, increment it. Otherwise, create new stock entry
#                 stock, created = Stock.objects.get_or_create(produit=produit, defaults={'quantite': 0})
#                 stock.quantite = stock.quantite or 0  # protège contre None
#                 stock.quantite += quantite
#                 stock.save()
#                 stock_map[produit.id] = stock.quantite

#                 # # Update stock using model
#                 # stock, created = Stock.objects.get_or_create(produit=produit)
#                 # stock.update_stock(quantite)

#             # calcul de montant total avec tax
#             AchatProduit.objects.bulk_create(achat_produits)
#             # update montant_total in vente
#             # achat.montant_total=montant_total
#             # achat.save()
            
#             achat.montant_total = montant_total
#             achat.montant_total_tax_inclue = montant_total + sum(Decimal(item.get('tax', 0)) for item in data.get('produits', []))
#             achat.save()

#         #     # Retourner la réponse avec la vente et la facture
#         # achat_serializer = AchatSerializer(achat)
#         # achatproduit_serializer = AchatSerializer(achat_produits)
#         # # paiement_serializer = PaiementSerializers(paiement)
#         # return Response(achatproduit_serializer.data, status=status.HTTP_201_CREATED)
#             achatproduit_serializer = AchatSerializer(achat)
#             # return Response(achatproduit_serializer.data, status=status.HTTP_201_CREATED)
#             return Response({
#                 "message": "Achat et produits créés avec succès.",
#                 "achat": achatproduit_serializer.data,
#                 "stock_updated": [
#                     {
#                         "produit_id": p.produit.id,
#                         "produit_nom": p.produit.nom,
#                         "quantite_ajoutee": p.quantite,
#                         "stock_actuel": stock_map[p.produit.id]
#                     }
#                     for p in achat_produits
#                 ]
#             }, status=status.HTTP_201_CREATED)
#         except Fournisseur.DoesNotExist:
#             return Response({"detail": "Fournisseur not found."}, status=status.HTTP_400_BAD_REQUEST)
#         except Produit.DoesNotExist:
#             return Response({"detail": "Produit not found."}, status=status.HTTP_400_BAD_REQUEST)
#         except Exception as e:
#             logger.error(f"[AchatProduitCreateView] Erreur : {str(e)}")
#             return Response({"detail": "Une erreur est survenue. Veuillez réessayer."}, status=400)


class AchatListView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
       
        operation_description="Liste tous les achats avec leurs produits. Filtrable par fournisseur et date.",#
#        manual_parameters=[
#            openapi.Parameter('start_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Date de début (format YYYY-MM-DD)"),
#            openapi.Parameter('end_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Date de fin (format YYYY-MM-DD)"),
#            openapi.Parameter('fournisseur_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="ID du fournisseur")
#        ],

        responses={200: AchatSerializer(many=True)}
    )
    def get(self, request, *args, **kwargs):
        user_role = getattr(request.user.user_role, 'role', None)
        if user_role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        try:
            achats = Achat.objects.all().prefetch_related('produits__produit', 'fournisseur')

            serializer = AchatSerializer(achats, many=True)
            return Response(serializer.data, status=200)

        except Exception as e:
            return Response({'error': str(e)}, status=400)
        

class AchatProduitGetOneView(APIView):  # renommé pour cohérence
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Récupère un achat spécifique avec ses produits associés.",
        responses={
            200: openapi.Response('Achat trouvé', AchatSerializer),
            404: "Achat non trouvé",
            403: "Accès refusé"
        }
    )
    @transaction.atomic
    def get(self, request, pk):
        user_role = getattr(request.user.user_role, 'role', None)
        if user_role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        try:
            achat = Achat.objects.select_related('fournisseur').prefetch_related('produits__produit').get(pk=pk)
            serializer = AchatSerializer(achat)
            return Response(serializer.data, status=200)

        except Achat.DoesNotExist:
            return Response({"detail": "Achat not found."}, status=404)

        except Exception as e:
            return Response({"detail": f"Erreur interne : {str(e)}"}, status=500)


class AchatProduitUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Modifier un AchatProduit et les données associées de l'achat.",
        manual_parameters=[
            openapi.Parameter('achatproduit_id', openapi.IN_PATH, type=openapi.TYPE_INTEGER, required=True),
            openapi.Parameter('achat_id', openapi.IN_PATH, type=openapi.TYPE_INTEGER, required=True)
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['quantite', 'prix_achat_gramme', 'tax', 'produit_id', 'fournisseur_id'],
            properties={
                'quantite': openapi.Schema(type=openapi.TYPE_INTEGER),
                'prix_achat_gramme': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal'),
                'tax': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal'),
                'produit_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                'fournisseur_id': openapi.Schema(type=openapi.TYPE_INTEGER)
            }
        ),
        responses={200: AchatProduitSerializer}
    )
    @transaction.atomic
    def put(self, request, achat_id, achatproduit_id):
        role = getattr(request.user.user_role, 'role', None)
        if role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        try:
            achat = Achat.objects.get(id=achat_id)
            achat_produit = AchatProduit.objects.get(id=achatproduit_id, achat=achat)

            # Récupérer les nouvelles données
            quantite = int(request.data.get('quantite'))
            prix_achat_gramme = Decimal(request.data.get('prix_achat_gramme'))
            tax = Decimal(request.data.get('tax'))
            produit = Produit.objects.get(id=request.data.get('produit_id'))
            fournisseur = Fournisseur.objects.get(id=request.data.get('fournisseur_id'))

            # Calcul sous total
            sous_total = quantite * prix_achat_gramme * (produit.poids or 1)

            # Mise à jour AchatProduit
            achat_produit.quantite = quantite
            achat_produit.prix_achat_gramme = prix_achat_gramme
            achat_produit.tax = tax
            achat_produit.produit = produit
            achat_produit.fournisseur = fournisseur
            achat_produit.sous_total_prix_achat = sous_total
            achat_produit.save()

            # Mise à jour Achat
            achat.fournisseur = fournisseur
            achat.update_total()  # déjà calcule montant_total_ht et montant_total_ttc
            achat.save()

            return Response({
                "achat_produit_id": achat_produit.id,
                "produit_id": produit.id,
                "fournisseur_id": fournisseur.id,
                "quantite": quantite,
                "prix_achat_gramme": str(prix_achat_gramme),
                "tax": str(tax),
                "sous_total_prix_achat": str(sous_total),
                "achat": {
                    "id": achat.id,
                    "created_at": achat.created_at,
                    "numero_achat": achat.numero_achat,
                    "fournisseur_id": achat.fournisseur.id if achat.fournisseur else None,
                    "montant_total": str(achat.montant_total),
                    "montant_total_tax_inclue": str(achat.montant_total_tax_inclue)
                }
            }, status=200)

        except Achat.DoesNotExist:
            return Response({"detail": "Achat non trouvé."}, status=404)
        except AchatProduit.DoesNotExist:
            return Response({"detail": "AchatProduit non trouvé."}, status=404)
        except Produit.DoesNotExist:
            return Response({"detail": "Produit non trouvé."}, status=404)
        except Fournisseur.DoesNotExist:
            return Response({"detail": "Fournisseur non trouvé."}, status=404)
        except Exception as e:
            return Response({"detail": str(e)}, status=500)



# class AchatProduitUpdateAPIView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Modifier un produit spécifique d’un achat, y compris le fournisseur et les données produit.",
#         manual_parameters=[
#             openapi.Parameter('achat_id', openapi.IN_PATH, type=openapi.TYPE_INTEGER, required=True, description="ID de l'achat"),
#             openapi.Parameter('achatproduit_id', openapi.IN_PATH, type=openapi.TYPE_INTEGER, required=True, description="ID du produit d'achat à modifier")
#         ],
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=['quantite', 'prix_achat_gramme', 'tax'],
#             properties={
#                 'quantite': openapi.Schema(type=openapi.TYPE_INTEGER),
#                 'prix_achat_gramme': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal'),
#                 'tax': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal'),
#                 'produit': openapi.Schema(
#                     type=openapi.TYPE_OBJECT,
#                     properties={
#                         'id': openapi.Schema(type=openapi.TYPE_INTEGER),
#                         'nom': openapi.Schema(type=openapi.TYPE_STRING),
#                         'poids': openapi.Schema(type=openapi.TYPE_NUMBER),
#                         # Ajoute d'autres champs modifiables si nécessaire
#                     }
#                 ),
#                 'fournisseur': openapi.Schema(
#                     type=openapi.TYPE_OBJECT,
#                     properties={
#                         'nom': openapi.Schema(type=openapi.TYPE_STRING),
#                         'prenom': openapi.Schema(type=openapi.TYPE_STRING),
#                         'address': openapi.Schema(type=openapi.TYPE_STRING),
#                         'telephone': openapi.Schema(type=openapi.TYPE_STRING),
#                     }
#                 )
#             }
#         ),
#         responses={
#             200: openapi.Response("Produit mis à jour avec succès", AchatProduitSerializer),
#             400: "Erreur de validation",
#             403: "Accès refusé",
#             404: "Non trouvé"
#         }
#     )
#     @transaction.atomic
#     def put(self, request, achat_id, achatproduit_id):
#         role = getattr(request.user.user_role, 'role', None)
#         if role not in ['admin', 'manager']:
#             return Response({"message": "Access Denied"}, status=403)

#         try:
#             achat = Achat.objects.get(id=achat_id)
#             achat_produit = AchatProduit.objects.select_related('produit', 'fournisseur').get(id=achatproduit_id, achat=achat)

#             ancienne_quantite = achat_produit.quantite
#             produit = achat_produit.produit
#             fournisseur = achat_produit.fournisseur
#             stock, _ = Stock.objects.get_or_create(produit=produit)

#             # 1. Fournisseur (si fourni)
#             fournisseur_data = request.data.get('fournisseur')
#             if fournisseur_data and fournisseur:
#                 fournisseur.nom = fournisseur_data.get('nom', fournisseur.nom)
#                 fournisseur.prenom = fournisseur_data.get('prenom', fournisseur.prenom)
#                 fournisseur.address = fournisseur_data.get('address', fournisseur.address)
#                 fournisseur.telephone = fournisseur_data.get('telephone', fournisseur.telephone)
#                 fournisseur.save()

#             # 2. Produit (si fourni et existant)
#             produit_data = request.data.get('produit')
#             if produit_data:
#                 new_produit_id = produit_data.get('id')
#                 if new_produit_id and new_produit_id != produit.id:
#                     try:
#                         new_produit = Produit.objects.get(id=new_produit_id)
#                         produit = new_produit
#                         stock, _ = Stock.objects.get_or_create(produit=produit)  # nouveau stock
#                     except Produit.DoesNotExist:
#                         return Response({"detail": "Produit fourni introuvable."}, status=404)
#                 else:
#                     produit.nom = produit_data.get('nom', produit.nom)
#                     produit.poids = produit_data.get('poids', produit.poids)
#                     produit.save()

#             # 3. Mise à jour principale
#             quantite_nouvelle = int(request.data.get('quantite'))
#             prix_achat_gramme = Decimal(request.data.get('prix_achat_gramme'))
#             tax = Decimal(request.data.get('tax'))

#             if quantite_nouvelle <= 0:
#                 return Response({'detail': "Quantité invalide."}, status=400)

#             poids = produit.poids or 1
#             sous_total = prix_achat_gramme * quantite_nouvelle * poids

#             # Mise à jour de AchatProduit
#             achat_produit.produit = produit
#             achat_produit.quantite = quantite_nouvelle
#             achat_produit.prix_achat_gramme = prix_achat_gramme
#             achat_produit.tax = tax
#             achat_produit.sous_total_prix_achat = sous_total
#             achat_produit.save()

#             # Stock update
#             difference = quantite_nouvelle - ancienne_quantite
#             stock.quantite = (stock.quantite or 0) + difference
#             stock.save()

#             # Update total achat
#             achat.update_total()

#             return Response(AchatProduitSerializer(achat_produit).data, status=200)

#         except Achat.DoesNotExist:
#             return Response({"detail": "Achat non trouvé."}, status=404)
#         except AchatProduit.DoesNotExist:
#             return Response({"detail": "AchatProduit non trouvé."}, status=404)
#         except Exception as e:
#             return Response({"detail": str(e)}, status=500)


# class AchatProduitUpdateAPIView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Modifier un produit spécifique d’un achat.",
#         manual_parameters=[
#             openapi.Parameter('achat_id', openapi.IN_PATH, type=openapi.TYPE_INTEGER, required=True, description="ID de l'achat"),
#             openapi.Parameter('achatproduit_id', openapi.IN_PATH, type=openapi.TYPE_INTEGER, required=True, description="ID de l'achat produit à modifier")
#         ],
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=['quantite', 'prix_achat_gramme', 'tax'],
#             properties={
#                 'quantite': openapi.Schema(type=openapi.TYPE_INTEGER),
#                 'prix_achat_gramme': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal'),
#                 'tax': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal'),
#             }
#         ),
#         responses={
#             200: openapi.Response("Produit mis à jour avec succès", AchatProduitSerializer),
#             400: "Erreur de validation",
#             403: "Accès refusé",
#             404: "Non trouvé"
#         }
#     )
#     @transaction.atomic
#     def put(self, request, achat_id, achatproduit_id):
#         role = getattr(request.user.user_role, 'role', None)
#         if role not in ['admin', 'manager']:
#             return Response({"message": "Access Denied"}, status=403)

#         try:
#             achat = Achat.objects.get(id=achat_id)
#             achat_produit = AchatProduit.objects.select_related('produit').get(id=achatproduit_id, achat=achat)

#             # Stock avant mise à jour
#             ancienne_quantite = achat_produit.quantite
#             produit = achat_produit.produit
#             stock, _ = Stock.objects.get_or_create(produit=produit)

#             # Données entrantes
#             quantite_nouvelle = int(request.data.get('quantite'))
#             prix_achat_gramme = Decimal(request.data.get('prix_achat_gramme'))
#             tax = Decimal(request.data.get('tax'))

#             if quantite_nouvelle <= 0:
#                 return Response({'detail': "Quantité invalide."}, status=400)

#             poids = produit.poids or 1
#             sous_total = prix_achat_gramme * quantite_nouvelle * poids
#             total_ttc = sous_total + tax

#             # Mise à jour de l'objet AchatProduit
#             achat_produit.quantite = quantite_nouvelle
#             achat_produit.prix_achat_gramme = prix_achat_gramme
#             achat_produit.tax = tax
#             achat_produit.sous_total_prix_achat = sous_total
#             achat_produit.save()

#             # Mise à jour du stock (différence)
#             difference = quantite_nouvelle - ancienne_quantite
#             stock.quantite = (stock.quantite or 0) + difference
#             stock.save()

#             # Mise à jour de l'achat global
#             achat.update_total()

#             return Response(AchatProduitSerializer(achat_produit).data, status=200)

#         except Achat.DoesNotExist:
#             return Response({"detail": "Achat non trouvé."}, status=404)
#         except AchatProduit.DoesNotExist:
#             return Response({"detail": "AchatProduit non trouvé."}, status=404)
#         except Exception as e:
#             return Response({"detail": str(e)}, status=500)


# class AchatUpdateAchatProduitAPIView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]
    
#     @swagger_auto_schema(
#         operation_description="Met à jour un achat existant avec ses produits et le fournisseur.",
#         manual_parameters=[
#             openapi.Parameter('achat_id', openapi.IN_PATH, description="ID de l'achat à modifier", type=openapi.TYPE_INTEGER),
#         ],
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             properties={
#                 'fournisseur': openapi.Schema(
#                     type=openapi.TYPE_OBJECT,
#                     properties={
#                         'nom': openapi.Schema(type=openapi.TYPE_STRING),
#                         'prenom': openapi.Schema(type=openapi.TYPE_STRING),
#                         'address': openapi.Schema(type=openapi.TYPE_STRING),
#                         'telephone': openapi.Schema(type=openapi.TYPE_STRING),
#                     }
#                 ),
#                 'produits': openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         properties={
#                             'produit': openapi.Schema(type=openapi.TYPE_OBJECT, properties={
#                                 'id': openapi.Schema(type=openapi.TYPE_INTEGER)
#                             }),
#                             'quantite': openapi.Schema(type=openapi.TYPE_INTEGER),
#                             'prix_achat_gramme': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal'),
#                             'tax': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal'),
#                         }
#                     )
#                 )
#             }
#         ),
#         responses={
#             200: openapi.Response("Mise à jour réussie", AchatSerializer),
#             400: "Requête invalide",
#             403: "Accès refusé",
#             404: "Achat non trouvé"
#         }
#     )

#     @transaction.atomic
#     def put(self, request, achat_id):
#         user_role = getattr(request.user.user_role, 'role', None)
#         if user_role not in ['admin', 'manager']:
#             return Response({"message": "Access Denied"}, status=403)

#         try:
#             achat = Achat.objects.get(id=achat_id)
#             fournisseur_id = achat.fournisseur_id
#             fournisseur_data = request.data.get('fournisseur')

#             # Mise à jour du fournisseur
#             if fournisseur_data:
#                 fournisseur = Fournisseur.objects.get(id=fournisseur_id)
#                 fournisseur.nom = fournisseur_data.get('nom', fournisseur.nom)
#                 fournisseur.prenom = fournisseur_data.get('prenom', fournisseur.prenom)
#                 fournisseur.address = fournisseur_data.get('address', fournisseur.address)
#                 fournisseur.telephone = fournisseur_data.get('telephone', fournisseur.telephone)
#                 fournisseur.save()
#                 achat.fournisseur = fournisseur

#             montant_total = Decimal(0)

#             for produit_data in request.data.get('produits', []):
#                 produit_id = produit_data.get('produit', {}).get('id')
#                 quantite_nouvelle = int(produit_data.get('quantite', 0))
#                 prix_achat_gramme = Decimal(produit_data.get('prix_achat_gramme', 0))
#                 tax = Decimal(produit_data.get('tax', 0))

#                 try:
#                     produit = Produit.objects.get(id=produit_id)
#                 except Produit.DoesNotExist:
#                     return Response({"error": f"Produit ID {produit_id} introuvable"}, status=400)

#                 # Ancienne quantité
#                 achat_produit_obj = AchatProduit.objects.get(achat=achat, produit=produit)
#                 quantite_ancienne = achat_produit_obj.quantite

#                 # Mise à jour ou création
#                 poids = produit.poids or 0
#                 sous_total = prix_achat_gramme * quantite_nouvelle * poids

#                 achat_produit, _ = AchatProduit.objects.update_or_create(
#                     achat=achat,
#                     produit=produit,
#                     fournisseur=achat.fournisseur,
#                     defaults={
#                         'quantite': quantite_nouvelle,
#                         'prix_achat_gramme': prix_achat_gramme,
#                         'tax': tax,
#                         'sous_total_prix_achat': sous_total,
#                     }
#                 )

#                 # Mise à jour du stock (différence)
#                 stock, _ = Stock.objects.get_or_create(produit=produit)
#                 difference = quantite_nouvelle - quantite_ancienne
#                 stock.quantite = (stock.quantite or 0) + difference
#                 stock.save()

#                 montant_total += sous_total + tax

#             achat.montant_total = montant_total
#             achat.montant_total_tax_inclue = montant_total
#             achat.save()

#             updated_achat = Achat.objects.prefetch_related('produits').get(id=achat.id)
#             return Response(AchatSerializer(updated_achat).data, status=200)

#         except Achat.DoesNotExist:
#             return Response({"error": "Achat introuvable"}, status=404)


class AchatProduitPDFView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Télécharge le PDF du détail d’un produit acheté.",
        manual_parameters=[
            openapi.Parameter('pk', openapi.IN_PATH, description="ID de l'achat-produit", type=openapi.TYPE_INTEGER)
        ],
        responses={
            200: openapi.Response(description="PDF généré avec succès"),
            404: "Produit d'achat non trouvé",
            403: "Accès refusé"
        }
    )
    def get(self, request, pk):
        role = getattr(request.user.user_role, 'role', None)
        if role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        try:
            achat_produit = AchatProduit.objects.select_related('achat', 'produit', 'fournisseur').get(pk=pk)
        except AchatProduit.DoesNotExist:
            return Response({"detail": "AchatProduit non trouvé."}, status=404)

        context = {
            "p": achat_produit,
            "achat": achat_produit.achat,
            "fournisseur": achat_produit.fournisseur or achat_produit.achat.fournisseur
        }

        template = get_template("pdf/achat_produit_detail.html")
        html = template.render(context)

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename=AchatProduit_{achat_produit.id}.pdf'

        pisa_status = pisa.CreatePDF(html, dest=response)
        if pisa_status.err:
            return Response({"detail": "Erreur lors de la génération du PDF"}, status=500)

        return response


# class AchatPDFView(APIView):
#     permission_classes = [IsAuthenticated]
    
#     @swagger_auto_schema(
#         operation_description="Télécharge le PDF du détail d’un achat.",
#         manual_parameters=[
#             openapi.Parameter('pk', openapi.IN_PATH, description="ID de l'achat", type=openapi.TYPE_INTEGER)
#         ],
#         responses={
#             200: openapi.Response(description="PDF généré"),
#             404: "Achat non trouvé",
#             403: "Accès refusé"
#         }
#     )
#     def get(self, request, pk):
#         role = getattr(request.user.user_role, 'role', None)
#         if role not in ['admin', 'manager', 'vendeur']:
#             return Response({"message": "Access Denied"}, status=403)

#         try:
#             # achat = Achat.objects.select_related('fournisseur').prefetch_related('produits__produit').get(pk=pk)
#             achat = AchatProduit.objects.select_related('fournisseur').prefetch_related('produits__produit').get(pk=pk)
#         except Achat.DoesNotExist:
#             return Response({"detail": "Achat non trouvé."}, status=404)

#         template_path = 'pdf/achat_detail.html'
#         context = {'achat': achat}
#         template = get_template(template_path)
#         html = template.render(context)

#         response = HttpResponse(content_type='application/pdf')
#         response['Content-Disposition'] = f'attachment; filename=Achat_{achat.numero_achat}.pdf'

#         pisa_status = pisa.CreatePDF(html, dest=response)

#         if pisa_status.err:
#             return Response({"detail": "Erreur lors de la génération du PDF"}, status=500)
#         return response


# class AchatUpdateAPIView(APIView):
#     @transaction.atomic
#     def put(self, request, achat_id):
#         # Récupérer l'achat et ses informations
#         try:
#             achat = Achat.objects.get(id=achat_id)
#             fournisseur_data = request.data.get('fournisseur')
#             produits_data = request.data.get('produits')  # Liste de produits à mettre à jour
#             achatproduit_data = request.data.get('achatproduit')
#             # Mettre à jour l'achat
#             achat.montant_total = request.data.get('montant_total', achat.montant_total)

#             # #recupere le id du achatproduit pour setter le stock precendant
#             # achat_produit_obj = AchatProduit.objects.get(achat_id=achat.id)
#             # print(achat_produit_obj.quantite)
#             # quantite_achat_update = achat_produit_obj.quantite

#             achat.save()

#             # Mettre à jour le fournisseur
#             if fournisseur_data:
#                 fournisseur = Fournisseur.objects.get(id=fournisseur_data['id'])
#                 fournisseur.nom = fournisseur_data.get('nom', fournisseur.nom)
#                 fournisseur.prenom = fournisseur_data.get('prenom', fournisseur.prenom)
#                 fournisseur.address = fournisseur_data.get('address', fournisseur.address)
#                 fournisseur.telephone = fournisseur_data.get('telephone', fournisseur.telephone)
#                 fournisseur.save()
#                 achat.fournisseur = fournisseur  # Associer à l'achat
#                 achat.save()


#             # Mettre à jour les produits et le stock
#             for produit_data in produits_data:
#                 produit = Produit.objects.get(id=produit_data['id'])

#                 #recupere le id du achatproduit pour setter le stock precendant
#                 achat_produit_obj = AchatProduit.objects.get(achat_id=achat, produit_id=produit)
#                 print(achat_produit_obj.produit_id)
#                 print(achat_produit_obj.quantite)
#                 quantite_achat_update = achat_produit_obj.quantite

#                 quantite_achat = produit_data['quantite']
#                 #Ceux-ci  la quantité enregistré et il faut le odifier pour mettre a jour le stock
#                 # prix_achat = produit_data['prix_achat']
#                 prix_achat_gramme = produit_data['prix_achat_gramme']
#                 tax = produit_data['tax']

#                 prix_achat = Decimal(prix_achat_gramme)*Decimal(produit.poids)
#                 sous_total_prix_achat = Decimal(prix_achat)*Decimal(quantite_achat)

#                 prix_achat = Decimal(prix_achat_gramme)*Decimal(produit.poids)
#                 sous_total_prix_achat = Decimal(prix_achat)*Decimal(quantite_achat)

#                 # Mettre à jour la table AchatProduit
#                 # achatProduit = AchatProduit.objects.get(id=achatproduit_data['id'])
#                 # achatProduit.produit=produit
#                 # achatProduit.quantite = quantite_achat
#                 # achatProduit.prix_achat_gramme = prix_achat_gramme
#                 # achatProduit.tax=tax
#                 # achatProduit.sous_total_prix_achat=sous_total_prix_achat
#                 # achatProduit.save()
#                 achat_produit, created = AchatProduit.objects.update_or_create(
#                     achat=achat,
#                     produit=produit,
#                     defaults={
#                         'fournisseur': fournisseur,
#                         'quantite': quantite_achat,
#                         'prix_achat_gramme': prix_achat_gramme,
#                         'prix_achat': prix_achat,
#                         'tax':tax,
#                         'sous_total_prix_achat': sous_total_prix_achat
#                         }
#                 )
#                 # Mettre à jour le stock
#                 stock, created = Stock.objects.get_or_create(produit=produit)
#                 #Appliquon la quantité pour que la mis a jour soit normal sans la table stock
#                 quantite_achat_normal = quantite_achat - quantite_achat_update
#                 #si cette diference est egale a 0 il n'aura pas de changement de stock
#                 if quantite_achat_normal > 0:
#                     quantite_achat_normal = quantite_achat_normal
#                     stock.quantite += quantite_achat_normal  # Ajouter la quantité achetée
#                     stock.save()
#                 # elif quantite_achat_normal == 0:
#                 #     stock.quantite = quantite_achat_update
#                 #     stock.save()
#                 else:
#                     quantite_achat_normal = quantite_achat_normal*(-1)
#                     stock.quantite -= quantite_achat_normal  # Ajouter la quantité achetée
#                     stock.save()
#                 # stock.quantite += quantite_achat  # Ajouter la quantité achetée
#                 # stock.save()

#                 achatproduit_serializer = AchatSerializer(achat)
#             return Response(achatproduit_serializer.data, status=status.HTTP_200_OK)

#         except Exception as e:
#             # Si une erreur se produit, toute la transaction est annulée.
#             return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

# django apiview put produit, pachat, suplier, produitsuplier and stock @transaction-atomic json out update pachat suplier all produit in achate



# class AchatUpdateAchatProduitAPIView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]
    
#     @transaction.atomic
#     def put(self, request, achat_id):
#         if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager' and request.user.user_role.role != 'vendeur':
#             return Response({"message": "Access Denied"})
#         try:
#             # Retrieve the Achat object to update
#             achat = Achat.objects.get(id=achat_id)
#             fournisseur_data = request.data.get('fournisseur')
#             # fournisseur_id = Achat.objects.get(fournisseur_id=achat.fournisseur_id)
#             # print(fournisseur_id)
#             # print(achat)
#             fournisseur_id=achat.fournisseur_id

#             achat.save()

#             if fournisseur_data:
#                 fournisseur = Fournisseur.objects.get(id=fournisseur_id)
#                 fournisseur.nom = fournisseur_data.get('nom', fournisseur.nom)
#                 fournisseur.prenom = fournisseur_data.get('prenom', fournisseur.prenom)
#                 fournisseur.address = fournisseur_data.get('address', fournisseur.address)
#                 fournisseur.telephone = fournisseur_data.get('telephone', fournisseur.telephone)
#                 fournisseur.save()
#                 achat.fournisseur = fournisseur  # Associer à l'achat
#                 achat.save()
#             # except Achat.DoesNotExist:
#             #     return Response({"error": "Achat not found"}, status=status.HTTP_404_NOT_FOUND)

#             # Deserialize the incoming data
#             # serializer = AchatSerializer(achat, data=request.data)
#             # if serializer.is_valid():
#             #     # Update Achat fields
#             #     serializer.save()


#             # # Mettre à jour le fournisseur
#             # if fournisseur_data:
#             #     fournisseur = Fournisseur.objects.get(id=fournisseur_data['id'])
#             #     fournisseur.nom = fournisseur_data.get('nom', fournisseur.nom)
#             #     fournisseur.prenom = fournisseur_data.get('prenom', fournisseur.prenom)
#             #     fournisseur.address = fournisseur_data.get('address', fournisseur.address)
#             #     fournisseur.telephone = fournisseur_data.get('telephone', fournisseur.telephone)
#             #     fournisseur.save()
#             #     achat.fournisseur = fournisseur  # Associer à l'achat
#             #     achat.save()

#             # Loop through the products in the 'produits' field
#             montant_total = 0
#             for produit_data in request.data.get('produits', []):
#                 produit_id = produit_data.get('produit', {}).get('id')
#                 quantite = produit_data.get('quantite')
#                 prix_achat_gramme = produit_data.get('prix_achat_gramme')
#                 tax = produit_data.get('tax')
                
                
#                 # print(produit_data)
#                 if produit_id and quantite is not None:
#                     # Check if the produit exists
#                     try:
#                         produit = Produit.objects.get(id=produit_id)

#                     except Produit.DoesNotExist:
#                         return Response({"error": f"Produit with id {produit_id} not found"}, status=status.HTTP_400_BAD_REQUEST)


#                     #recupere le id du achatproduit pour setter le stock precendant
#                     achat_produit_obj = AchatProduit.objects.get(achat_id=achat, produit_id=produit)
#                     # print(achat_produit_obj.produit_id)
#                     # print(achat_produit_obj.quantite)
#                     quantite_achat_update = achat_produit_obj.quantite

#                     quantite_achat = produit_data['quantite']
#                     #Ceux-ci  la quantité enregistré et il faut le odifier pour mettre a jour le stock
#                     # prix_achat = produit_data['prix_achat']
#                     # prix_achat_gramme = produit_data['prix_achat_gramme']
#                     # tax = produit_data['tax']

#                     # prix_achat = Decimal(prix_achat_gramme)*Decimal(produit.poids)
#                     # sous_total_prix_achat = Decimal(prix_achat)*Decimal(quantite_achat)

#                     # prix_achat = Decimal(prix_achat_gramme)*Decimal(produit.poids)
#                     # sous_total_prix_achat = Decimal(prix_achat)*Decimal(quantite_achat)


#                     # # Update the stock for the produit
#                     # stock, created = Stock.objects.get_or_create(produit=produit)
#                     # stock.quantite += quantite  # Assuming a reduction in stock
#                     # stock.save()

#                     # Add or update the AchatProduit entry
#                     achat_produit, created = AchatProduit.objects.update_or_create(
#                         achat=achat,
#                         produit=produit,
#                         fournisseur=fournisseur,
#                         defaults={
#                             'quantite': quantite_achat,
#                             'prix_achat_gramme': prix_achat_gramme,
#                             # 'prix_achat': prix_achat,
#                             'tax':tax,
#                         }
#                     )
#                     poids = produit.poids
#                     achat_produit.sous_total_prix_achat = Decimal(prix_achat_gramme)*Decimal(quantite_achat)*Decimal(poids)
#                     montant_total += achat_produit.sous_total_prix_achat + achat_produit.tax
#                     achat_produit.save()
#                     achat.montant_total = montant_total
#                     achat.save()
#                     # montant_total = 0
#                     # Mettre à jour le stock
#                     stock, created = Stock.objects.get_or_create(produit=produit)
#                     #Appliquon la quantité pour que la mis a jour soit normal sans la table stock
#                     quantite_achat_normal = quantite_achat - quantite_achat_update
#                     #si cette diference est egale a 0 il n'aura pas de changement de stock
#                     if quantite_achat_normal > 0:
#                         quantite_achat_normal = quantite_achat_normal
#                         stock.quantite += quantite_achat_normal  # Ajouter la quantité achetée
#                         stock.save()
#                     # elif quantite_achat_normal == 0:
#                     #     stock.quantite = quantite_achat_update
#                     #     stock.save()
#                     else:
#                         quantite_achat_normal = quantite_achat_normal*(-1)
#                         stock.quantite -= quantite_achat_normal  # Ajouter la quantité achetée
#                         stock.save()
#                     # stock.quantite += quantite_achat  # Ajouter la quantité achetée
#                     # stock.save()

#             # Return the updated achat with the produits
#             updated_achat = Achat.objects.prefetch_related('produits').get(id=achat.id)
#             updated_achat_serializer = AchatSerializer(updated_achat)
#             return Response(updated_achat_serializer.data, status=status.HTTP_200_OK)

#         except Achat.DoesNotExist:
#             return Response({"error": "Achat not found"}, status=status.HTTP_404_NOT_FOUND)
#             # return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
