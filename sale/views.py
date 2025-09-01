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
from rest_framework import status, permissions
from django.db.models import F
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
                            PaiementCreateSerializer, PaiementSerializer, 
                            VenteDetailSerializer)
from django.db import models
from store.models import Produit, MarquePurete
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
#vente direct lorsque le client achete directement a la boutique
# class VenteProduitCreateView(APIView):
#         renderer_classes = [UserRenderer]
#         permission_classes = [IsAuthenticated]

#         @swagger_auto_schema(
#             operation_summary="Vente direct créer une vente avec produits, client et facture",
#             operation_description="""Créer une vente avec des produits associés (par QR code), mise à jour du stock, génération automatique de la facture. Un admin peut spécifier un `vendor_email`.""",
#             manual_parameters=[
#                 openapi.Parameter(
#                     'vendor_email',
#                     openapi.IN_QUERY,
#                     description="Email du vendeur (optionnel, requis si admin/manager veut vendre à la place d’un vendeur)",
#                     type=openapi.TYPE_STRING
#                 )
#             ],
#             request_body=openapi.Schema(
#                 type=openapi.TYPE_OBJECT,
#                 required=["produits"],
#                 properties={
#                     "client": openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["nom", "prenom"],
#                         properties={
#                             "nom": openapi.Schema(type=openapi.TYPE_STRING, description="Nom du client"),
#                             "prenom": openapi.Schema(type=openapi.TYPE_STRING, description="Prénom du client"),
#                             "telephone": openapi.Schema(type=openapi.TYPE_STRING, example="770000000", description="Téléphone (optionnel)"),
#                         }
#                     ),
#                     "produits": openapi.Schema(
#                         type=openapi.TYPE_ARRAY,
#                         items=openapi.Schema(
#                             type=openapi.TYPE_OBJECT,
#                             required=["slug", "quantite"],
#                             properties={
#                                 "slug": openapi.Schema(type=openapi.TYPE_STRING),
#                                 "quantite": openapi.Schema(type=openapi.TYPE_INTEGER),
#                                 "prix_vente_grammes": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal"),
#                                 "remise": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal"),
#                                 "autres": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal"),
#                                 "tax": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal"),
#                             }
#                         )
#                     )
#                 }
#             ),
#             responses={201: "Création réussie", 400: "Requête invalide", 403: "Accès refusé", 500: "Erreur serveur"}
#         )
#         @transaction.atomic
#         def post(self, request):
#             try:
#                 user = request.user
#                 role = getattr(user.user_role, 'role', None)
#                 user_role_obj = getattr(user, 'user_role', None)
#                 role = getattr(user_role_obj, 'role', None)
#                 if role not in ['admin', 'manager', 'vendor']:
#                     return Response({"message": "Access Denied"}, status=403)

#                 data = request.data
#                 client_data = data.get('client')
#                 client_data = data.get('client', {})
#                 if not client_data.get("nom") or not client_data.get("prenom"):
#                     return Response({"error": "Les champs 'nom' et 'prenom' du client sont obligatoires."}, status=400)

#                 telephone = client_data.get("telephone", "").strip()
#                 if telephone:
#                     lookup = {"telephone": telephone}
#                 else:
#                     lookup = {"nom": client_data["nom"], "prenom": client_data["prenom"]}

#                 client, _ = Client.objects.get_or_create(
#                     defaults={"nom": client_data["nom"], "prenom": client_data["prenom"]},
#                     **lookup
#                 )
#                 # if telephone:
#                 #     client, _ = Client.objects.get_or_create(
#                 #         telephone=telephone,
#                 #         defaults={"nom": client_data["nom"], "prenom": client_data["prenom"]}
#                 #     )
#                 # else:
#                 #     client, _ = Client.objects.get_or_create(
#                 #         nom=client_data["nom"],
#                 #         prenom=client_data["prenom"]
#                 #     )

#                 vente = Vente.objects.create(client=client, created_by=user)
#                 vente_produits = []

#                 # 🔁 Vendor selection
#                 vendor_email = request.query_params.get('vendor_email')
#                 if role == 'vendor':
#                     try:
#                         vendor = Vendor.objects.get(user=user)
#                     except Vendor.DoesNotExist:
#                         return Response({"error": "Vous n'êtes pas associé à un compte vendeur."}, status=400)
#                 else:
#                     if not vendor_email:
#                         return Response({"error": "vendor_email est requis pour les admins et managers."}, status=400)
#                     try:
#                         vendor = Vendor.objects.select_related('user').get(user__email=vendor_email)
#                     except Vendor.DoesNotExist:
#                         return Response({"error": "Vendeur introuvable avec cet email."}, status=404)

#                 for item in data.get('produits', []):
#                     slug = item['slug']
#                     quantite = int(item.get('quantite', 0))
#                     if quantite <= 0:
#                         return Response({"error": f"Quantité invalide pour le produit {slug}."}, status=400)

#                     try:
#                         produit = Produit.objects.select_related('marque').get(slug=slug)
#                     except Produit.DoesNotExist:
#                         return Response({"error": f"Produit avec QR code {slug} introuvable."}, status=404)

#                     try:
#                         brut = item.get('prix_vente_grammes')

#                         if brut and Decimal(str(brut)) > 0:
#                             prix_vente_grammes = Decimal(str(brut))
#                         else:
#                             # Récupération du prix dans MarquePurete
#                             try:
#                                 lien_mp = MarquePurete.objects.get(
#                                     marque=produit.marque,
#                                     purete=produit.purete
#                                 )
#                                 prix_vente_grammes = Decimal(str(lien_mp.prix))
#                             except MarquePurete.DoesNotExist:
#                                 return Response(
#                                     {"error": f"Prix introuvable pour la marque '{produit.marque}' et la pureté '{produit.purete}'."},
#                                     status=400
#                                 )

#                     except (InvalidOperation, AttributeError, TypeError, ValueError):
#                         return Response({"error": f"Prix de vente invalide pour le produit {slug}."}, status=400)

#                     remise = Decimal(str(item.get('remise') or 0))
#                     autres = Decimal(str(item.get('autres') or 0))
#                     tax = Decimal(str(item.get('tax') or 0))

#                     try:
#                         vendor_stock = VendorProduit.objects.get(produit=produit, vendor=vendor)
#                     except VendorProduit.DoesNotExist:
#                         return Response({"error": f"Produit {produit.nom} non disponible dans le stock du vendeur."}, status=400)

#                     if vendor_stock.quantite < quantite:
#                         return Response({
#                             "error": f"Stock insuffisant pour {produit.nom}. Stock disponible : {vendor_stock.quantite}"
#                         }, status=400)

#                     vente_produit = VenteProduit(
#                         vente=vente,
#                         produit=produit,
#                         quantite=quantite,
#                         prix_vente_grammes=prix_vente_grammes,
#                         remise=remise,
#                         autres=autres,
#                         tax=tax,
#                         vendor=vendor
#                     )
#                     vente_produit.save()  # ✅ calcul automatique du HT/TTC ici
#                     vente_produits.append(vente_produit)
#                     vendor_stock.quantite -= quantite
#                     vendor_stock.save()


#                 # ✅ Génération du numéro de facture
#                 numero = Facture.generer_numero_unique()
#                 facture = Facture.objects.create(
#                     vente=vente,
#                     montant_total=vente.montant_total,
#                     numero_facture=numero,
#                     type_facture='vente_directe'
#                 )

#                 vente_detail = VenteDetailSerializer(vente)
#                 return Response(vente_detail.data, status=status.HTTP_201_CREATED)

#             except Exception as e:
#                 transaction.set_rollback(True)
#                 return Response({"detail": str(e)}, status=500)


# class VenteProduitCreateView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Vente directe avec produits, client et facture",
#         operation_description="Créer une vente avec des produits (par slug/QR), MAJ stock sécurisée, facture générée. Admin/manager: passer ?vendor_email=…",
#         manual_parameters=[
#             openapi.Parameter(
#                 'vendor_email', openapi.IN_QUERY, description="Email du vendeur (requis si admin/manager)",
#                 type=openapi.TYPE_STRING
#             )
#         ],
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["produits"],
#             properties={
#                 "client": openapi.Schema(
#                     type=openapi.TYPE_OBJECT,
#                     required=["nom", "prenom"],
#                     properties={
#                         "nom": openapi.Schema(type=openapi.TYPE_STRING),
#                         "prenom": openapi.Schema(type=openapi.TYPE_STRING),
#                         "telephone": openapi.Schema(type=openapi.TYPE_STRING, example="770000000"),
#                     }
#                 ),
#                 "produits": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["slug", "quantite"],
#                         properties={
#                             "slug": openapi.Schema(type=openapi.TYPE_STRING),
#                             "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, minimum=1),
#                             "prix_vente_grammes": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal"),
#                             "remise": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal"),
#                             "autres": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal"),
#                             "tax": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal"),
#                         }
#                     )
#                 )
#             }
#         ),
#         responses={201: "Création réussie", 400: "Requête invalide", 403: "Accès refusé", 404: "Introuvable", 409: "Conflit stock"}
#     )
#     @transaction.atomic
#     def post(self, request):
#         user = request.user
#         role = getattr(getattr(user, 'user_role', None), 'role', None)
#         if role not in ('admin', 'manager', 'vendor'):
#             return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

#         data = request.data or {}
#         produits_payload = data.get('produits') or []
#         if not produits_payload:
#             return Response({"error": "La liste 'produits' est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)

#         # Client
#         client_data = data.get('client') or {}
#         if not client_data.get("nom") or not client_data.get("prenom"):
#             return Response({"error": "Les champs client 'nom' et 'prenom' sont obligatoires."}, status=status.HTTP_400_BAD_REQUEST)

#         telephone = (client_data.get("telephone") or "").strip()
#         lookup = {"telephone": telephone} if telephone else {"nom": client_data["nom"], "prenom": client_data["prenom"]}
#         client, _ = Client.objects.get_or_create(defaults={"nom": client_data["nom"], "prenom": client_data["prenom"]}, **lookup)

#         # Vendor
#         vendor_email = request.query_params.get('vendor_email')
#         if role == 'vendor':
#             try:
#                 vendor = Vendor.objects.select_for_update().get(user=user)
#             except Vendor.DoesNotExist:
#                 return Response({"error": "Vous n'êtes pas associé à un compte vendeur."}, status=status.HTTP_400_BAD_REQUEST)
#         else:
#             if not vendor_email:
#                 return Response({"error": "vendor_email est requis pour les admins et managers."}, status=status.HTTP_400_BAD_REQUEST)
#             try:
#                 vendor = Vendor.objects.select_related('user').select_for_update().get(user__email=vendor_email)
#             except Vendor.DoesNotExist:
#                 return Response({"error": "Vendeur introuvable avec cet email."}, status=status.HTTP_404_NOT_FOUND)

#         # Vente
#         vente = Vente.objects.create(client=client, created_by=user)

#         # Préparer lignes + contrôle stock atomique
#         # On peut sommer les quantités si même slug fourni plusieurs fois
#         wanted = {}
#         raw_rows = []
#         for item in produits_payload:
#             slug = item.get('slug')
#             q = int(item.get('quantite', 0) or 0)
#             if not slug or q <= 0:
#                 return Response({"error": "Chaque produit doit avoir un 'slug' et une 'quantite' >= 1."}, status=status.HTTP_400_BAD_REQUEST)
#             wanted[slug] = wanted.get(slug, 0) + q
#             raw_rows.append(item)

#         # Verrouiller les stocks des produits concernés (anti course)
#         slugs = list(wanted.keys())
#         produits = {p.slug: p for p in Produit.objects.select_related('marque').filter(slug__in=slugs)}
#         if len(produits) != len(slugs):
#             manquants = [s for s in slugs if s not in produits]
#             return Response({"error": f"Produits introuvables: {', '.join(manquants)}"}, status=status.HTTP_404_NOT_FOUND)

#         # Charger le stock VendorProduit et verrouiller
#         stocks = {vp.produit.slug: vp for vp in VendorProduit.objects.select_for_update().filter(vendor=vendor, produit__slug__in=slugs)}
#         missing_in_stock = [s for s in slugs if s not in stocks]
#         if missing_in_stock:
#             return Response({"error": f"Non disponibles chez le vendeur: {', '.join(missing_in_stock)}"}, status=status.HTTP_400_BAD_REQUEST)

#         # Vérifier stock suffisant pour chaque slug demandé (quantité totale)
#         insufficient = [s for s in slugs if stocks[s].quantite < wanted[s]]
#         if insufficient:
#             details = {s: {"demande": wanted[s], "dispo": stocks[s].quantite} for s in insufficient}
#             return Response({"error": "Stock insuffisant pour certains produits.", "details": details}, status=status.HTTP_409_CONFLICT)

#         # Créer les lignes de vente et décrémenter le stock
#         lignes = []
#         for item in raw_rows:
#             slug = item['slug']
#             quantite = int(item['quantite'])
#             produit = produits[slug]

#             # Prix gramme
#             try:
#                 brut = item.get('prix_vente_grammes')
#                 prix_vente_grammes = Decimal(str(brut)) if brut is not None else None
#                 if not prix_vente_grammes or prix_vente_grammes <= 0:
#                     # fallback marque.prix
#                     prix_vente_grammes = Decimal(str(getattr(produit.marque, 'prix', None)))
#                     if not prix_vente_grammes or prix_vente_grammes <= 0:
#                         return Response({"error": f"Prix de vente invalide ou manquant pour {slug}."}, status=status.HTTP_400_BAD_REQUEST)
#             except (InvalidOperation, TypeError):
#                 return Response({"error": f"Prix de vente invalide pour {slug}."}, status=status.HTTP_400_BAD_REQUEST)

#             remise = Decimal(str(item.get('remise') or 0))
#             autres = Decimal(str(item.get('autres') or 0))
#             tax = Decimal(str(item.get('tax') or 0))

#             vp = VenteProduit.objects.create(
#                 vente=vente,
#                 produit=produit,
#                 quantite=quantite,
#                 prix_vente_grammes=prix_vente_grammes,
#                 remise=remise,
#                 autres=autres,
#                 tax=tax,
#                 vendor=vendor
#             )
#             lignes.append(vp)

#             # décrémenter sécuritairement (déjà vérifié; on met à jour)
#             VendorProduit.objects.filter(pk=stocks[slug].pk).update(quantite=F('quantite') - quantite)

#         # Générer facture
#         numero = Facture.generer_numero_unique()
#         facture = Facture.objects.create(
#             vente=vente,
#             montant_total=vente.montant_total,   # suppose calculé côté modèle/signal
#             numero_facture=numero,
#             type_facture='vente_directe'
#         )

#         # Réponse
#         payload = VenteDetailSerializer(vente).data
#         payload["facture_numero"] = facture.numero_facture
#         return Response(payload, status=status.HTTP_201_CREATED)


# class VenteProduitCreateView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Vente directe (admin/manager sans rôle vendor possible)",
#         operation_description=(
#             "Créer une vente (slug/QR), MAJ stock atomique, facture générée.\n"
#             "- Vendor: utilise son Vendor lié.\n"
#             "- Admin/Manager: peut passer ?vendor_email=... (global) ou 'vendor_email' par item.\n"
#             "- Sans email: sélection automatique du vendeur qui a le stock (refus si plusieurs)."
#         ),
#         manual_parameters=[
#             openapi.Parameter(
#                 'vendor_email', openapi.IN_QUERY,
#                 description="Email du vendeur (optionnel pour admin/manager, global pour toutes les lignes)",
#                 type=openapi.TYPE_STRING
#             )
#         ],
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["produits"],
#             properties={
#                 "client": openapi.Schema(
#                     type=openapi.TYPE_OBJECT,
#                     required=["nom", "prenom"],
#                     properties={
#                         "nom": openapi.Schema(type=openapi.TYPE_STRING),
#                         "prenom": openapi.Schema(type=openapi.TYPE_STRING),
#                         "telephone": openapi.Schema(type=openapi.TYPE_STRING, example="770000000"),
#                     }
#                 ),
#                 "produits": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["slug", "quantite"],
#                         properties={
#                             "slug": openapi.Schema(type=openapi.TYPE_STRING),
#                             "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, minimum=1),
#                             "prix_vente_grammes": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal"),
#                             "remise": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal"),
#                             "autres": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal"),
#                             "tax": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal"),
#                             # 👇 optionnel: vendeur par item
#                             "vendor_email": openapi.Schema(type=openapi.TYPE_STRING, description="Vendeur pour cet item"),
#                         }
#                     )
#                 )
#             }
#         ),
#         responses={201: "Créé", 400: "Requête invalide", 403: "Accès refusé", 404: "Introuvable", 409: "Stock insuffisant"}
#     )
#     @transaction.atomic
#     def post(self, request):
#         user = request.user
#         role = getattr(getattr(user, 'user_role', None), 'role', None)
#         if role not in ('admin', 'manager', 'vendor'):
#             return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

#         data = request.data or {}
#         produits_payload = data.get('produits') or []
#         if not produits_payload:
#             return Response({"error": "La liste 'produits' est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)

#         # Client
#         client_data = data.get('client') or {}
#         if not client_data.get("nom") or not client_data.get("prenom"):
#             return Response({"error": "Les champs client 'nom' et 'prenom' sont obligatoires."}, status=status.HTTP_400_BAD_REQUEST)
#         telephone = (client_data.get("telephone") or "").strip()
#         lookup = {"telephone": telephone} if telephone else {"nom": client_data["nom"], "prenom": client_data["prenom"]}
#         client, _ = Client.objects.get_or_create(defaults={"nom": client_data["nom"], "prenom": client_data["prenom"]}, **lookup)

#         # Précharger les produits
#         slugs, rows = [], []
#         for it in produits_payload:
#             slug = it.get('slug')
#             q = int(it.get('quantite', 0) or 0)
#             if not slug or q <= 0:
#                 return Response({"error": "Chaque produit doit avoir 'slug' et 'quantite' >= 1."}, status=status.HTTP_400_BAD_REQUEST)
#             slugs.append(slug)
#             rows.append(it)

#         produits = {p.slug: p for p in Produit.objects.select_related('marque', 'purete').filter(slug__in=slugs)}
#         if len(produits) != len(slugs):
#             manquants = [s for s in slugs if s not in produits]
#             return Response({"error": f"Produits introuvables: {', '.join(manquants)}"}, status=status.HTTP_404_NOT_FOUND)

#         vendor_email_global = request.query_params.get('vendor_email')

#         # Helper: choisir le vendor pour UNE ligne
#         def resolve_vendor_for_item(item_slug, item_vendor_email=None):
#             # 1) vendeur connecté
#             if role == 'vendor':
#                 return Vendor.objects.select_for_update().get(user=user)
#             # 2) admin/manager → email explicite (item > global)
#             email = item_vendor_email or vendor_email_global
#             if email:
#                 vendor = Vendor.objects.select_related('user').select_for_update().filter(user__email=email).first()
#                 if vendor:
#                     return vendor
#                 # fallback automatique si email invalide → auto-sélection
#             # 3) auto: un seul vendeur a du stock
#             qs = (VendorProduit.objects
#                   .select_related('vendor', 'vendor__user', 'produit')
#                   .select_for_update()
#                   .filter(produit__slug=item_slug, quantite__gt=0))
#             count = qs.count()
#             if count == 0:
#                 raise VendorProduit.DoesNotExist("Aucun vendeur n'a ce produit en stock.")
#             if count > 1:
#                 raise ValueError("Plusieurs vendeurs possibles (ambigu).")
#             return qs.first().vendor

#         # Créer la vente
#         vente = Vente.objects.create(client=client, created_by=user)

#         # Traiter chaque ligne
#         for item in rows:
#             slug = item['slug']
#             quantite = int(item['quantite'])
#             produit = produits[slug]

#             # Vendeur pour l'item
#             try:
#                 vendor = resolve_vendor_for_item(slug, item.get('vendor_email'))
#             except Vendor.DoesNotExist:
#                 return Response({"error": "Vendeur introuvable."}, status=status.HTTP_404_NOT_FOUND)
#             except VendorProduit.DoesNotExist as e:
#                 return Response({"error": f"{produit.nom}: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
#             except ValueError as e:
#                 return Response({"error": f"{produit.nom}: {str(e)}. Précisez 'vendor_email' (global ou par item)."}, status=status.HTTP_400_BAD_REQUEST)

#             # Stock du vendor
#             try:
#                 vp = VendorProduit.objects.select_for_update().get(vendor=vendor, produit=produit)
#             except VendorProduit.DoesNotExist:
#                 return Response({"error": f"{produit.nom}: non disponible chez le vendeur sélectionné."}, status=status.HTTP_400_BAD_REQUEST)
#             if vp.quantite < quantite:
#                 return Response({"error": f"Stock insuffisant pour {produit.nom}. Dispo: {vp.quantite}"}, status=status.HTTP_409_CONFLICT)

#             # Prix (payload > MarquePurete)
#             try:
#                 brut = item.get('prix_vente_grammes')
#                 prix_vente_grammes = Decimal(str(brut)) if brut is not None else None
#                 if not prix_vente_grammes or prix_vente_grammes <= 0:
#                     lien = MarquePurete.objects.get(marque=produit.marque, purete=produit.purete)
#                     prix_vente_grammes = Decimal(str(lien.prix))
#                     if prix_vente_grammes <= 0:
#                         raise InvalidOperation()
#             except (MarquePurete.DoesNotExist, InvalidOperation, TypeError, ValueError):
#                 return Response({"error": f"Prix de vente invalide pour {produit.nom} (marque/pureté non tarifiées)."}, status=status.HTTP_400_BAD_REQUEST)

#             remise = Decimal(str(item.get('remise') or 0))
#             autres = Decimal(str(item.get('autres') or 0))
#             tax = Decimal(str(item.get('tax') or 0))

#             # Créer la ligne + décrément stock
#             VenteProduit.objects.create(
#                 vente=vente,
#                 produit=produit,
#                 quantite=quantite,
#                 prix_vente_grammes=prix_vente_grammes,
#                 remise=remise,
#                 autres=autres,
#                 tax=tax,
#                 vendor=vendor
#             )
#             VendorProduit.objects.filter(pk=vp.pk).update(quantite=F('quantite') - quantite)

#         # Facture
#         numero = Facture.generer_numero_unique()
#         facture = Facture.objects.create(
#             vente=vente,
#             montant_total=vente.montant_total,  # calculé côté modèle/signal
#             numero_facture=numero,
#             type_facture='vente_directe'
#         )

#         payload = dict(VenteDetailSerializer(vente).data)
#         payload["facture_numero"] = facture.numero_facture
#         return Response(payload, status=status.HTTP_201_CREATED)


# class VenteProduitCreateView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [permissions.IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Vente directe (admin/manager/vendor)",
#         operation_description=(
#             "Crée une vente (une ligne par item), décrémente le stock **vendeur**, et génère une facture.\n"
#             "- Vendor connecté : son Vendor est utilisé.\n"
#             "- Admin/Manager : peut donner ?vendor_email=... (global) ou 'vendor_email' par item.\n"
#             "- Sans email : sélection automatique du seul vendeur ayant du stock (refus si plusieurs)."
#         ),
#         manual_parameters=[
#             openapi.Parameter('vendor_email', openapi.IN_QUERY, description="Email vendeur (global)", type=openapi.TYPE_STRING),
#         ],
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["produits"],
#             properties={
#                 "client": openapi.Schema(
#                     type=openapi.TYPE_OBJECT, required=["nom", "prenom"],
#                     properties={
#                         "nom": openapi.Schema(type=openapi.TYPE_STRING),
#                         "prenom": openapi.Schema(type=openapi.TYPE_STRING),
#                         "telephone": openapi.Schema(type=openapi.TYPE_STRING),
#                     }
#                 ),
#                 "produits": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT, required=["slug", "quantite"],
#                         properties={
#                             "slug": openapi.Schema(type=openapi.TYPE_STRING),
#                             "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, minimum=1),
#                             "prix_vente_grammes": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal"),
#                             "remise": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal", description="montant FCFA"),
#                             "autres": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal", description="montant FCFA"),
#                             "tax": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal", description="montant FCFA"),
#                             "vendor_email": openapi.Schema(type=openapi.TYPE_STRING, description="Vendeur pour cet item"),
#                         }
#                     )
#                 )
#             }
#         ),
#         responses={201: "Créé", 400: "Requête invalide", 403: "Accès refusé", 404: "Introuvable", 409: "Stock insuffisant"}
#     )
#     @transaction.atomic
#     def post(self, request):
#         user = request.user
#         role = getattr(getattr(user, 'user_role', None), 'role', None)
#         if role not in ('admin', 'manager', 'vendor'):
#             return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

#         data = request.data or {}
#         items = data.get('produits') or []
#         if not isinstance(items, list) or not items:
#             return Response({"error": "La liste 'produits' est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)

#         # Client
#         c = data.get('client') or {}
#         if not c.get("nom") or not c.get("prenom"):
#             return Response({"error": "Les champs client 'nom' et 'prenom' sont obligatoires."}, status=status.HTTP_400_BAD_REQUEST)
#         telephone = (c.get("telephone") or "").strip()
#         lookup = {"telephone": telephone} if telephone else {"nom": c["nom"], "prenom": c["prenom"]}
#         client, _ = Client.objects.get_or_create(defaults={"nom": c["nom"], "prenom": c["prenom"]}, **lookup)

#         # Précharger produits
#         slugs = [it.get('slug') for it in items if it.get('slug')]
#         produits = {p.slug: p for p in Produit.objects.select_related('marque', 'purete').filter(slug__in=slugs)}
#         if len(produits) != len(set(slugs)):
#             missing = [s for s in set(slugs) if s not in produits]
#             return Response({"error": f"Produits introuvables: {', '.join(missing)}"}, status=status.HTTP_404_NOT_FOUND)

#         # Précharger tarifs MarquePurete (fallback prix)
#         pairs = {(p.marque_id, p.purete_id) for p in produits.values()}
#         tarifs = {
#             (mp.marque_id, mp.purete_id): Decimal(str(mp.prix))
#             for mp in MarquePurete.objects.filter(
#                 marque_id__in=[m for (m, _) in pairs],
#                 purete_id__in=[r for (_, r) in pairs]
#             )
#         }

#         vendor_email_global = (request.query_params.get('vendor_email') or "").strip()

#         def resolve_vendor(item_slug, item_vendor_email=None):
#             if role == 'vendor':
#                 v = get_object_or_404(Vendor.objects.select_related('user').select_for_update(), user=user)
#                 if not v.verifie:
#                     raise PermissionError("Votre compte vendeur est désactivé.")
#                 return v
#             email = (item_vendor_email or vendor_email_global or "").strip()
#             if email:
#                 v = Vendor.objects.select_related('user').select_for_update().filter(user__email__iexact=email).first()
#                 if not v:
#                     raise Vendor.DoesNotExist(f"Vendeur '{email}' introuvable.")
#                 if not v.verifie:
#                     raise PermissionError(f"Le vendeur '{email}' est désactivé.")
#                 return v
#             qs = (VendorProduit.objects
#                   .select_related('vendor', 'vendor__user', 'produit')
#                   .select_for_update()
#                   .filter(produit__slug=item_slug, quantite__gt=0))
#             n = qs.count()
#             if n == 0:
#                 raise VendorProduit.DoesNotExist("Aucun vendeur n'a ce produit en stock.")
#             if n > 1:
#                 raise ValueError("Plusieurs vendeurs possibles (ambigu).")
#             v = qs.first().vendor
#             if not v.verifie:
#                 raise PermissionError("Le vendeur sélectionné automatiquement est désactivé.")
#             return v

#         # Créer la vente
#         vente = Vente.objects.create(client=client, created_by=user)

#         # Une ligne par item (cohérence exacte avec le calcul du modèle)
#         for it in items:
#             slug = it.get('slug')
#             try:
#                 qte = int(it.get('quantite', 0) or 0)
#             except Exception:
#                 return Response({"error": "La quantité doit être un entier >= 1."}, status=status.HTTP_400_BAD_REQUEST)
#             if not slug or qte <= 0:
#                 return Response({"error": "Chaque item doit avoir 'slug' et 'quantite' >= 1."}, status=status.HTTP_400_BAD_REQUEST)

#             produit = produits[slug]

#             # Vendeur
#             try:
#                 vendor = resolve_vendor(slug, it.get('vendor_email'))
#             except Vendor.DoesNotExist as e:
#                 return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
#             except VendorProduit.DoesNotExist as e:
#                 return Response({"error": f"{produit.nom}: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
#             except PermissionError as e:
#                 return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
#             except ValueError as e:
#                 return Response({"error": f"{produit.nom}: {str(e)}. Précisez 'vendor_email'."}, status=status.HTTP_400_BAD_REQUEST)

#             # Stock vendeur (lock + décrément atomique)
#             try:
#                 vp_stock = VendorProduit.objects.select_for_update().get(vendor=vendor, produit=produit)
#             except VendorProduit.DoesNotExist:
#                 return Response({"error": f"{produit.nom}: non disponible chez le vendeur sélectionné."}, status=status.HTTP_400_BAD_REQUEST)
#             if vp_stock.quantite < qte:
#                 return Response({"error": f"Stock insuffisant pour {produit.nom}. Dispo: {vp_stock.quantite}"}, status=status.HTTP_409_CONFLICT)

#             # Prix unitaire : payload > MarquePurete
#             brut = it.get('prix_vente_grammes')
#             try:
#                 pvg = Decimal(str(brut)) if brut not in (None, "", 0, "0") else None
#             except (InvalidOperation, TypeError, ValueError):
#                 pvg = None
#             if not pvg or pvg <= 0:
#                 key = (produit.marque_id, produit.purete_id)
#                 pvg = tarifs.get(key)
#                 if not pvg or pvg <= 0:
#                     return Response({"error": f"Tarif indisponible pour {produit.nom} (marque/pureté non tarifiées)."}, status=status.HTTP_400_BAD_REQUEST)

#             remise = Decimal(str(it.get('remise') or 0))
#             autres = Decimal(str(it.get('autres') or 0))
#             tax    = Decimal(str(it.get('tax') or 0))

#             # Créer la ligne → calcul HT/TTC dans le modèle
#             VenteProduit.objects.create(
#                 vente=vente, produit=produit, vendor=vendor,
#                 quantite=qte, prix_vente_grammes=pvg,
#                 remise=remise, autres=autres, tax=tax,
#             )

#             # Décrément atomique du stock
#             updated = VendorProduit.objects.filter(pk=vp_stock.pk, quantite__gte=qte).update(
#                 quantite=F('quantite') - qte
#             )
#             if not updated:
#                 return Response({"error": f"Conflit de stock détecté pour {produit.nom}. Réessayez."}, status=status.HTTP_409_CONFLICT)

#         # Facture (si ton modèle existe)
#         try:
#             numero = Facture.generer_numero_unique()
#             facture = Facture.objects.create(
#                 vente=vente,
#                 montant_total=vente.montant_total,   # TTC
#                 numero_facture=numero,
#                 type_facture='vente_directe'
#             )
#             facture_numero = facture.numero_facture
#         except Exception:
#             facture_numero = None  # laisse passer si tu préfères créer la facture ailleurs

#         # Réponse
#         lignes = [
#             {
#                 "produit_slug": lp.produit.slug if lp.produit else None,
#                 "quantite": lp.quantite,
#                 "prix_vente_grammes": str(lp.prix_vente_grammes),
#                 "sous_total_ht": str(lp.sous_total_prix_vente_ht),
#                 "tax": str(lp.tax or Decimal('0')),
#                 "prix_ttc": str(lp.prix_ttc),
#                 "vendor_id": lp.vendor_id,
#             }
#             for lp in VenteProduit.objects.filter(vente=vente).select_related("produit")
#         ]

#         return Response({
#             "message": "✅ Vente créée",
#             "vente_id": vente.id,
#             "numero_vente": vente.numero_vente,
#             "facture_numero": facture_numero,
#             "client": {
#                 "id": client.id,
#                 "nom": client.nom,
#                 "prenom": client.prenom,
#                 "telephone": client.telephone,
#             },
#             "lignes": lignes,
#             "montant_total": str(vente.montant_total)
#         }, status=status.HTTP_201_CREATED)


class VenteProduitCreateView(APIView):
    """Vente directe: 1 item = 1 ligne, stock décrémenté chez le vendeur, facture générée."""
    renderer_classes = [UserRenderer]  # supprime si pas utilisé
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Vente directe (admin/manager/vendor)",
        operation_description=(
            "Crée une vente par items, décrémente le stock vendeur, et génère une facture.\n"
            "- Vendor connecté : son Vendor est utilisé.\n"
            "- Admin/Manager : peut passer ?vendor_email=... (global) ou 'vendor_email' par item.\n"
            "- Sans email : sélection automatique du seul vendeur ayant du stock (refus si plusieurs)."
        ),
        manual_parameters=[
            openapi.Parameter('vendor_email', openapi.IN_QUERY, description="Email vendeur (global)", type=openapi.TYPE_STRING),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["produits"],
            properties={
                "client": openapi.Schema(
                    type=openapi.TYPE_OBJECT, required=["nom", "prenom"],
                    properties={
                        "nom": openapi.Schema(type=openapi.TYPE_STRING),
                        "prenom": openapi.Schema(type=openapi.TYPE_STRING),
                        "telephone": openapi.Schema(type=openapi.TYPE_STRING),
                    }
                ),
                "produits": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT, required=["slug", "quantite"],
                        properties={
                            "slug": openapi.Schema(type=openapi.TYPE_STRING),
                            "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, minimum=1),
                            "prix_vente_grammes": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal"),
                            "remise": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal", description="montant FCFA"),
                            "autres": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal", description="montant FCFA"),
                            "tax": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal", description="montant FCFA"),
                            "vendor_email": openapi.Schema(type=openapi.TYPE_STRING, description="Vendeur pour cet item"),
                        }
                    )
                )
            }
        ),
        responses={201: "Créé", 400: "Requête invalide", 403: "Accès refusé", 404: "Introuvable", 409: "Stock insuffisant"}
    )
    @transaction.atomic
    def post(self, request):
        # ---- Rôles ----
        user = request.user
        role = getattr(getattr(user, 'user_role', None), 'role', None)
        if role not in ('admin', 'manager', 'vendor'):
            return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

        # ---- Payload ----
        data = request.data or {}
        items = data.get('produits') or []
        if not isinstance(items, list) or not items:
            return Response({"error": "La liste 'produits' est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)

        # ---- Client ----
        c = data.get('client') or {}
        if not c.get("nom") or not c.get("prenom"):
            return Response({"error": "Les champs client 'nom' et 'prenom' sont obligatoires."}, status=status.HTTP_400_BAD_REQUEST)
        telephone = (c.get("telephone") or "").strip()
        lookup = {"telephone": telephone} if telephone else {"nom": c["nom"], "prenom": c["prenom"]}
        client, _ = Client.objects.get_or_create(defaults={"nom": c["nom"], "prenom": c["prenom"]}, **lookup)

        # ---- Préchargements produits & tarifs ----
        slugs = [it.get('slug') for it in items if it.get('slug')]
        produits = {p.slug: p for p in Produit.objects.select_related('marque', 'purete').filter(slug__in=slugs)}
        if len(produits) != len(set(slugs)):
            missing = [s for s in set(slugs) if s not in produits]
            return Response({"error": f"Produits introuvables: {', '.join(missing)}"}, status=status.HTTP_404_NOT_FOUND)

        pairs = {(p.marque_id, p.purete_id) for p in produits.values()}
        tarifs = {
            (mp.marque_id, mp.purete_id): Decimal(str(mp.prix))
            for mp in MarquePurete.objects.filter(
                marque_id__in=[m for (m, _) in pairs],
                purete_id__in=[r for (_, r) in pairs]
            )
        }

        # ---- Validation précoce prix (payload OU MarquePurete) ----
        manquants, sans_attributs = [], []
        for it in items:
            slug = it.get('slug')
            if not slug:
                continue
            p = produits[slug]

            # prix fourni ?
            brut = it.get('prix_vente_grammes')
            try:
                pvg = Decimal(str(brut)) if brut not in (None, "", 0, "0") else None
            except Exception:
                pvg = None
            if pvg and pvg > 0:
                continue

            # sinon il faut (marque,purete) + tarif
            if not p.marque_id or not p.purete_id:
                sans_attributs.append(f"{p.nom} (slug={p.slug})")
                continue
            if (p.marque_id, p.purete_id) not in tarifs:
                nom_marque = getattr(p.marque, "nom", p.marque_id)
                nom_purete = getattr(p.purete, "nom", p.purete_id)
                manquants.append(f"{p.nom} (marque={nom_marque}, purete={nom_purete})")

        if sans_attributs:
            return Response({
                "error": "Certains produits n'ont pas (marque, purete) renseignés.",
                "details": sans_attributs
            }, status=status.HTTP_400_BAD_REQUEST)

        if manquants:
            return Response({
                "error": "Tarif MarquePurete manquant pour certains produits.",
                "details": manquants,
                "solutions": [
                    "Ajoutez le tarif dans MarquePurete pour chaque (marque, purete) listé.",
                    "OU fournissez 'prix_vente_grammes' (> 0) dans le payload pour ces lignes."
                ]
            }, status=status.HTTP_400_BAD_REQUEST)

        vendor_email_global = (request.query_params.get('vendor_email') or "").strip()

        # ---- Helper: résoudre le vendeur pour un item ----
        def resolve_vendor(item_slug, item_vendor_email=None):
            if role == 'vendor':
                v = get_object_or_404(Vendor.objects.select_related('user').select_for_update(), user=user)
                if not v.verifie:
                    raise PermissionError("Votre compte vendeur est désactivé.")
                return v
            email = (item_vendor_email or vendor_email_global or "").strip()
            if email:
                v = Vendor.objects.select_related('user').select_for_update().filter(user__email__iexact=email).first()
                if not v:
                    raise Vendor.DoesNotExist(f"Vendeur '{email}' introuvable.")
                if not v.verifie:
                    raise PermissionError(f"Le vendeur '{email}' est désactivé.")
                return v
            # auto: un seul vendeur avec stock
            qs = (VendorProduit.objects
                  .select_related('vendor', 'vendor__user', 'produit')
                  .select_for_update()
                  .filter(produit__slug=item_slug, quantite__gt=0))
            n = qs.count()
            if n == 0:
                raise VendorProduit.DoesNotExist("Aucun vendeur n'a ce produit en stock.")
            if n > 1:
                raise ValueError("Plusieurs vendeurs possibles (ambigu).")
            v = qs.first().vendor
            if not v.verifie:
                raise PermissionError("Le vendeur sélectionné automatiquement est désactivé.")
            return v

        # ---- Créer la vente ----
        vente = Vente.objects.create(client=client, created_by=user)

        # ---- Une ligne par item (calcul HT/TTC fait par le modèle) ----
        for it in items:
            slug = it.get('slug')
            try:
                qte = int(it.get('quantite', 0) or 0)
            except Exception:
                return Response({"error": "La quantité doit être un entier >= 1."}, status=status.HTTP_400_BAD_REQUEST)
            if not slug or qte <= 0:
                return Response({"error": "Chaque item doit avoir 'slug' et 'quantite' >= 1."}, status=status.HTTP_400_BAD_REQUEST)

            produit = produits[slug]

            # Vendeur
            try:
                vendor = resolve_vendor(slug, it.get('vendor_email'))
            except Vendor.DoesNotExist as e:
                return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
            except VendorProduit.DoesNotExist as e:
                return Response({"error": f"{produit.nom}: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
            except PermissionError as e:
                return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
            except ValueError as e:
                return Response({"error": f"{produit.nom}: {str(e)}. Précisez 'vendor_email'."}, status=status.HTTP_400_BAD_REQUEST)

            # Stock vendeur
            try:
                vp_stock = VendorProduit.objects.select_for_update().get(vendor=vendor, produit=produit)
            except VendorProduit.DoesNotExist:
                return Response({"error": f"{produit.nom}: non disponible chez le vendeur sélectionné."}, status=status.HTTP_400_BAD_REQUEST)
            if vp_stock.quantite < qte:
                return Response({"error": f"Stock insuffisant pour {produit.nom}. Dispo: {vp_stock.quantite}"}, status=status.HTTP_409_CONFLICT)

            # Prix unitaire: payload > MarquePurete
            brut = it.get('prix_vente_grammes')
            try:
                pvg = Decimal(str(brut)) if brut not in (None, "", 0, "0") else None
            except (InvalidOperation, TypeError, ValueError):
                pvg = None
            if not pvg or pvg <= 0:
                pvg = tarifs[(produit.marque_id, produit.purete_id)]  # existe après validation

            remise = Decimal(str(it.get('remise') or 0))
            autres = Decimal(str(it.get('autres') or 0))
            tax    = Decimal(str(it.get('tax') or 0))

            # Créer la ligne → le modèle calcule sous_total_prix_vente_ht & prix_ttc
            VenteProduit.objects.create(
                vente=vente, produit=produit, vendor=vendor,
                quantite=qte, prix_vente_grammes=pvg,
                remise=remise, autres=autres, tax=tax,
            )

            # Décrément atomique du stock
            updated = VendorProduit.objects.filter(pk=vp_stock.pk, quantite__gte=qte).update(
                quantite=F('quantite') - qte
            )
            if not updated:
                return Response({"error": f"Conflit de stock détecté pour {produit.nom}. Réessayez."}, status=status.HTTP_409_CONFLICT)

        # ---- Facture (si dispo) ----
        try:
            numero = Facture.generer_numero_unique()
            facture = Facture.objects.create(
                vente=vente,
                montant_total=vente.montant_total,   # TTC de la vente
                numero_facture=numero,
                type_facture='vente_directe'
            )
            facture_numero = facture.numero_facture
        except Exception:
            facture_numero = None  # crée la facture ailleurs si besoin

        # ---- Réponse ----
        lignes = [
            {
                "produit_slug": lp.produit.slug if lp.produit else None,
                "quantite": lp.quantite,
                "prix_vente_grammes": str(lp.prix_vente_grammes),
                "sous_total_ht": str(lp.sous_total_prix_vente_ht),
                "tax": str(lp.tax or Decimal('0')),
                "prix_ttc": str(lp.prix_ttc),
                "vendor_id": lp.vendor_id,
            }
            for lp in VenteProduit.objects.filter(vente=vente).select_related("produit")
        ]

        return Response({
            "message": "✅ Vente créée",
            "vente_id": vente.id,
            "numero_vente": vente.numero_vente,
            "facture_numero": facture_numero,
            "client": {
                "id": client.id,
                "nom": client.nom,
                "prenom": client.prenom,
                "telephone": client.telephone,
            },
            "lignes": lignes,
            "montant_total": str(vente.montant_total)
        }, status=status.HTTP_201_CREATED)
        

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


# Vue avec verrouillage et validations anti-surpaiement
# class PaiementFactureView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]
    
#     ROLES_AUTORISES_COMME_CAISSIER = ['admin', 'manager', 'cashier']

#     @swagger_auto_schema(
#         operation_description="Effectuer un paiement pour une facture donnée par son numéro.",
#         request_body=PaiementSerializer,
#         responses={
#             201: openapi.Response("Paiement enregistré avec succès", PaiementSerializer),
#             400: openapi.Response("Requête invalide"),
#             403: openapi.Response("Accès interdit"),
#             404: openapi.Response("Facture introuvable")
#         }
#     )
#     def post(self, request, facture_numero):
#         role = getattr(request.user.user_role, 'role', None)
#         if role not in self.ROLES_AUTORISES_COMME_CAISSIER:
#             return Response({"message": "Access Denied"}, status=403)

#         try:
#             # facture = Facture.objects.get(numero_facture=facture_numero)
#             facture_numero = facture_numero.strip()
#             facture = Facture.objects.get(numero_facture__iexact=facture_numero)
#         except Facture.DoesNotExist:
#             return Response({"detail": "Facture introuvable."}, status=404)

#         if facture.status == 'Payé':
# #         if facture.status == 'Payé'
#             return Response({'error': 'La facture est déjà réglée'}, status=400)

#         # ✅ UTILISATION DE validated_data
#         serializer = PaiementSerializer(data=request.data)
#         serializer.is_valid(raise_exception=True)  # ➜ ça appelle automatiquement validate_montant_paye du serializer

#         montant_paye = serializer.validated_data['montant_paye']
#         mode_paiement = serializer.validated_data.get('mode_paiement', 'cash')
        
#         if facture.total_paye + montant_paye > facture.montant_total:
#             return Response({
#                 'error': f"Le solde restant est de {facture.reste_a_payer}. Veuillez saisir un montant inférieur ou égal."
#             }, status=400)

#         paiement = Paiement.objects.create(
#             facture=facture,
#             montant_paye=montant_paye,
#             mode_paiement=mode_paiement,
#             created_by=request.user
#         )

#         # ✅ Mise à jour du statut de la facture
#         if facture.total_paye >= facture.montant_total and facture.status != "Payé":
#             facture.status = "Payé"
#             facture.save()

#         return Response({
#             'message': 'Paiement enregistré avec succès',
#             'paiement': PaiementSerializer(paiement).data,
#             'total_paye': str(facture.total_paye),
#             'reste_a_payer': str(facture.reste_a_payer),
#             'statut_facture': facture.status
#         }, status=201)


class PaiementFactureView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    ROLES_AUTORISES_COMME_CAISSIER = ['admin', 'manager', 'cashier']

    @swagger_auto_schema(
        operation_description="Effectuer un paiement pour une facture donnée par son numéro.",
        request_body=PaiementCreateSerializer,
        responses={
            201: openapi.Response("Paiement enregistré avec succès", PaiementSerializer),
            400: openapi.Response("Requête invalide"),
            403: openapi.Response("Accès interdit"),
            404: openapi.Response("Facture introuvable")
        }
    )
    @transaction.atomic
    def post(self, request, facture_numero):
        # 1) Permissions
        role = getattr(getattr(request.user, "user_role", None), "role", None)
        if role not in self.ROLES_AUTORISES_COMME_CAISSIER:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        # 2) Facture (verrou)
        numero = (facture_numero or "").strip()
        try:
            # lock la facture pour éviter les surpaiements concurrents
            facture = Facture.objects.select_for_update().get(numero_facture__iexact=numero)
        except Facture.DoesNotExist:
            return Response({"detail": "Facture introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if getattr(facture, "status", None) == "Payé":
            return Response({"error": "La facture est déjà réglée."}, status=status.HTTP_400_BAD_REQUEST)

        # 3) Validation input
        s = PaiementCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        montant = s.validated_data["montant_paye"]
        mode = s.validated_data.get("mode_paiement", "cash")

        # 4) Somme déjà payée (en base, sous verrou)
        deja = facture.paiements.aggregate(t=Sum("montant_paye"))["t"] or Decimal("0.00")
        total = getattr(facture, "montant_total", None)
        if total is None:
            return Response({"error": "La facture n'a pas de montant_total défini."}, status=status.HTTP_400_BAD_REQUEST)

        if deja + montant > total:
            reste = total - deja
            return Response(
                {"error": f"Le solde restant est de {reste}. Veuillez saisir un montant ≤ au reste à payer."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 5) Créer le paiement (le modèle liera cashier via created_by si absent)
        paiement = Paiement.objects.create(
            facture=facture,
            montant_paye=montant,
            mode_paiement=mode,
            created_by=request.user
        )

        # 6) Mettre à jour le statut (si tu utilises un champ dénormalisé)
        # Recalcule le total payé juste après insert
        total_paye = facture.paiements.aggregate(t=Sum("montant_paye"))["t"] or Decimal("0.00")
        if total_paye >= total and getattr(facture, "status", None) is not None:
            facture.status = "Payé"
            facture.save(update_fields=["status"])

        # 7) Réponse
        return Response(
            {
                "message": "Paiement enregistré avec succès",
                "paiement": PaiementSerializer(paiement).data,
                "total_paye": str(total_paye),
                "reste_a_payer": str(total - total_paye),
                "statut_facture": getattr(facture, "status", None),
            },
            status=status.HTTP_201_CREATED
        )



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

