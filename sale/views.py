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

from backend.renderers import UserRenderer
from sale.models import Client, Facture, Paiement, Vente, VenteProduit
from sale.serializers import (ClientSerializers, FactureSerializers,
                            PaiementSerializers, VenteProduitSerializer,
                            VenteSerializers)
from store.models import Produit
from vendor.models import Vendor

# #PDF
# pip install weasyprint
# from django.template.loader import render_to_string
# from weasyprint import HTML
# import os
# from django.core.files.base import ContentFile



# Create your views here.
class VenteProduitCreateView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Créer une vente avec produits, client, et facture",
        operation_description="Créer une vente avec produits associés (par QR code), mise à jour du stock vendeur, génération automatique de la facture.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["produits"],
            # required=["client", "produits"],
            properties={
                "client": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    # required=["nom", "prenom"],
                    properties={
                        "nom": openapi.Schema(type=openapi.TYPE_STRING, description="Nom du client"),
                        "prenom": openapi.Schema(type=openapi.TYPE_STRING, description="Prénom du client"),
                        "telephone": openapi.Schema(type=openapi.TYPE_STRING, description="Téléphone du client", example="770000000"),
                    }
                ),
                "produits": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        required=["sku", "quantite"],
                        properties={
                            "sku": openapi.Schema(type=openapi.TYPE_STRING, description="QR Code du produit via SKU"),
                            "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, description="Quantité vendue"),
                            "prix_vente_grammes": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal", description="Prix de vente par gramme (facultatif)"),
                            "remise": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal", description="Remise en % (facultatif)"),
                            "autre": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal", description="Autre montant (facultatif)"),
                        }
                    )
                )
            }
        ),
        responses={
            201: openapi.Response(description="Vente et facture créées avec succès"),
            400: openapi.Response(description="Requête invalide"),
            403: openapi.Response(description="Accès refusé"),
            500: openapi.Response(description="Erreur serveur"),
        }
    )
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        try:
            user = request.user
            role = getattr(user.user_role, 'role', None)
            if role not in ['admin', 'manager', 'vendeur']:
                return Response({"message": "Access Denied"}, status=403)

            data = request.data
            client_data = data.get('client')
            client, _ = Client.objects.get_or_create(
                nom=client_data['nom'],
                prenom=client_data['prenom'],
                defaults=client_data
            )
            vente = Vente.objects.create(client=client)

            vente_produits = []
            montant_total = 0

            try:
                vendor = Vendor.objects.get(user=user)
            except Vendor.DoesNotExist:
                return Response({"error": "Vous n'êtes pas associé à un compte vendeur."}, status=400)

            for item in data.get('produits', []):
                sku = item['sku']
                quantite = int(item.get('quantite', 0))
                prix_vente_grammes = item.get('prix_vente_grammes')
                remise = float(item.get('remise', 0.0))
                autres = Decimal(item.get('autre', 0.0))

                try:
                    if quantite <= 0:
                        return Response({"error": f"Quantité invalide pour le QR code {sku}."}, status=400)
                except (ValueError, TypeError):
                    return Response({"error": f"Quantité manquante ou invalide pour le QR code {sku}."}, status=400)

                try:
                    produit = Produit.objects.select_related('marque').get(sku=sku)
                except Produit.DoesNotExist:
                    return Response({"error": f"Produit avec QR code {sku} introuvable."}, status=404)

                if prix_vente_grammes is None:
                    prix_vente_grammes = Decimal(produit.marque.prix)

                try:
                    vendor_stock = VendorProduit.objects.get(produit=produit, vendor=vendor)
                except VendorProduit.DoesNotExist:
                    return Response({"error": f"Produit {produit.nom} non disponible dans votre stock."}, status=400)

                if vendor_stock.quantite < quantite:
                    return Response({
                        "error": f"Stock insuffisant pour {produit.nom}. Stock disponible : {vendor_stock.quantite}"
                    }, status=400)

                poids = produit.poids or 1
                prix_vente_unitaire = prix_vente_grammes * poids
                prix_remise = prix_vente_unitaire - remise
                # prix_remise = prix_vente_unitaire * (1 - remise / 100)
                sous_total = (prix_remise * quantite) + autres

                vente_produit = VenteProduit(
                    vente=vente,
                    produit=produit,
                    quantite=quantite,
                    prix_vente_grammes=prix_vente_grammes,
                    sous_total_prix_vent=sous_total,
                    remise=remise,
                    autres=autres
                )
                vente_produits.append(vente_produit)
                montant_total += sous_total

                vendor_stock.quantite -= quantite
                vendor_stock.save()

            VenteProduit.objects.bulk_create(vente_produits)
            vente.montant_total = montant_total
            vente.save()

            for _ in range(10):
                numero = Facture.generer_numero_facture()
                if not Facture.objects.filter(numero_facture=numero).exists():
                    break
            else:
                raise Exception("Impossible de générer un numéro de facture unique.")

            facture = Facture.objects.create(
                vente=vente,
                montant_total=montant_total,
                numero_facture=numero
            )
            facture.save()

            facture_serializer = FactureSerializers(facture)
            return Response(facture_serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# class VenteProduitCreateView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Créer une vente avec produits, client, et facture",
#         operation_description="Créer une vente avec produits associés, mise à jour du stock vendeur, génération automatique de la facture.",
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["client", "produits"],
#             properties={
#                 "client": openapi.Schema(
#                     type=openapi.TYPE_OBJECT,
#                     required=["nom", "prenom"],
#                     properties={
#                         "nom": openapi.Schema(type=openapi.TYPE_STRING, description="Nom du client"),
#                         "prenom": openapi.Schema(type=openapi.TYPE_STRING, description="Prénom du client"),
#                         "telephone": openapi.Schema(type=openapi.TYPE_STRING, description="Téléphone du client", example="770000000"),
#                     }
#                 ),
#                 "produits": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["qrcode", "quantite"],
#                         properties={
#                             "qrcode": openapi.Schema(type=openapi.TYPE_STRING, description="QR Code du produit"),
#                             "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, description="Quantité vendue"),
#                             "prix_vente_grammes": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal", description="Prix de vente par gramme (facultatif)"),
#                             "remise": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal", description="Remise en % (facultatif)"),
#                             "autres": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal", description="Autres informations tarifaires (facultatif)"),
#                         }
#                     )
#                 )
#             }
#         ),
#         responses={
#             201: openapi.Response(description="Vente et facture créées avec succès"),
#             400: openapi.Response(description="Requête invalide"),
#             403: openapi.Response(description="Accès refusé"),
#             500: openapi.Response(description="Erreur serveur"),
#         }
#     )
#     @transaction.atomic
#     def post(self, request, *args, **kwargs):
#         try:
#             user = request.user
#             role = getattr(user.user_role, 'role', None)

#             if role not in ['admin', 'manager', 'vendeur']:
#                 return Response({"message": "Access Denied"}, status=403)

#             data = request.data
#             client_data = data.get('client')
#             client, created = Client.objects.get_or_create(
#                 nom=client_data['nom'],
#                 prenom=client_data['prenom'],
#                 defaults=client_data
#             )

#             vente = Vente.objects.create(client=client)
#             vente_produits = []
#             montant_total = 0

#             try:
#                 vendor = Vendor.objects.get(user=user)
#             except Vendor.DoesNotExist:
#                 return Response({"error": "Vous n'êtes pas associé à un compte vendeur."}, status=400)

#             for item in data.get('produits', []):
#                 qrcode = item.get('qrcode')
#                 quantite = int(item.get('quantite', 0))
#                 prix_vente_grammes = item.get('prix_vente_grammes')
#                 remise = Decimal(item.get('remise', 0))
#                 autres = Decimal(item.get('autres', 0))

#                 try:
#                     produit = Produit.objects.select_related('marque').get(qrcode=qrcode)
#                 except Produit.DoesNotExist:
#                     return Response({"error": f"Produit avec QR Code {qrcode} introuvable."}, status=404)

#                 if quantite <= 0:
#                     return Response({"error": f"Quantité invalide pour le produit {produit.nom}."}, status=400)

#                 try:
#                     vendor_stock = VendorProduit.objects.get(produit=produit, vendor=vendor)
#                 except VendorProduit.DoesNotExist:
#                     return Response({"error": f"Produit {produit.nom} non disponible dans votre stock."}, status=400)

#                 if vendor_stock.quantite < quantite:
#                     return Response({"error": f"Stock insuffisant pour {produit.nom}. Stock disponible : {vendor_stock.quantite}"}, status=400)

#                 if prix_vente_grammes is None:
#                     prix_vente_grammes = Decimal(produit.marque.prix)
#                 else:
#                     prix_vente_grammes = Decimal(prix_vente_grammes)

#                 prix_vente_unitaire = prix_vente_grammes * produit.poids
#                 prix_remise = prix_vente_unitaire - remise
#                 # prix_remise = prix_vente_unitaire * (1 - remise / 100)
#                 sous_total = (prix_remise * quantite) + autres

#                 vente_produit = VenteProduit(
#                     vente=vente,
#                     produit=produit,
#                     quantite=quantite,
#                     prix_vente_grammes=prix_vente_grammes,
#                     remise=remise,
#                     autres=autres,
#                     sous_total_prix_vent=sous_total
#                 )
#                 vente_produits.append(vente_produit)
#                 montant_total += sous_total

#                 vendor_stock.quantite -= quantite
#                 vendor_stock.save()

#             VenteProduit.objects.bulk_create(vente_produits)
#             vente.montant_total = montant_total
#             vente.save()

#             for _ in range(10):
#                 numero = Facture.generer_numero_facture()
#                 if not Facture.objects.filter(numero_facture=numero).exists():
#                     break
#             else:
#                 raise Exception("Impossible de générer un numéro de facture unique.")

#             facture = Facture.objects.create(
#                 vente=vente,
#                 montant_total=montant_total,
#                 numero_facture=numero
#             )
#             facture.save()

#             facture_serializer = FactureSerializers(facture)
#             return Response(facture_serializer.data, status=status.HTTP_201_CREATED)

#         except Exception as e:
#             import traceback
#             print(traceback.format_exc())
#             return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
# class VenteProduitCreateView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]
    
#     @swagger_auto_schema(
#         operation_summary="Créer une vente avec produits, client, et facture",
#         operation_description="Créer une vente avec produits associés, mise à jour du stock vendeur, génération automatique de la facture.",
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["client", "produits"],
#             properties={
#                 "client": openapi.Schema(
#                     type=openapi.TYPE_OBJECT,
#                     required=["nom", "prenom"],
#                     properties={
#                         "nom": openapi.Schema(type=openapi.TYPE_STRING, description="Nom du client"),
#                         "prenom": openapi.Schema(type=openapi.TYPE_STRING, description="Prénom du client"),
#                         "telephone": openapi.Schema(type=openapi.TYPE_STRING, description="Téléphone du client", example="770000000"),
#                     }
#                 ),
#                 "produits": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["produit_id", "quantite"],
#                         properties={
#                             "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="ID du produit"),
#                             "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, description="Quantité vendue"),
#                             "prix_vente_grammes": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal", description="Prix de vente par gramme (facultatif)"),
#                         }
#                     )
#                 )
#             }
#         ),
#         responses={
#             201: openapi.Response(description="Vente et facture créées avec succès"),
#             400: openapi.Response(description="Requête invalide"),
#             403: openapi.Response(description="Accès refusé"),
#             500: openapi.Response(description="Erreur serveur"),
#         }
#     )
    
#     @transaction.atomic
#     def post(self, request, *args, **kwargs):
#         try:
#             user = request.user
#             role = getattr(user.user_role, 'role', None)
            
#             if role not in ['admin', 'manager', 'vendeur']:
#                 return Response({"message": "Access Denied"}, status=403)
            
#             data = request.data
            
#             # Récupérer les données du client
#             client_data = data.get('client')
#             client, created = Client.objects.get_or_create(
#                 # telephone=client_data['telephone'],
#                 nom=client_data['nom'],
#                 prenom=client_data['prenom'],
#                 defaults=client_data
#             )

#             # Créer la vente
#             vente = Vente.objects.create(client=client)

#             # Liste pour les objets venteProduit
#             vente_produits = []
#             montant_total = 0
            
#             # Récupération du vendeur
#             try:
#                 vendor = Vendor.objects.get(user=user)
#             except Vendor.DoesNotExist:
#                 return Response({"error": "Vous n'êtes pas associé à un compte vendeur."}, status=400)

#             # Ajouter les produits à la vente
#             for item in data.get('produits', []):
#                 # produit = Produit.objects.get(id=item['produit']['id'])
#                 # optimiser
#                 # produit = Produit.objects.select_related('marque').get(id=item['produit']['id'])
#                 produit_id = item['produit_id']
#                 quantite = int(item.get('quantite', 0))
#                 prix_vente_grammes = item.get('prix_vente_grammes')
#                 remise = Decimal(item.get('remise', 0.0))
#                 autres = Decimal(item.get('autres', 0.0))
                
#                 #verifier le stock
#                 # if produit.quantite_en_stock < quantite:
#                 #     return Response({"error": f"Pas assez de stock pour {produit.nom} le stock est {produit.quantite_en_stock}"}, status=status.HTTP_400_BAD_REQUEST)
#                 try:
#                     # quantite = int(quantite)
#                     if quantite <= 0:
#                         return Response({"error": f"Quantité invalide pour le produit {produit.sku}."}, status=status.HTTP_400_BAD_REQUEST)
#                     # if not 0 <= remise <= 100:
#                     #     return Response({"error": f"Remise invalide pour le produit {produit_id}."}, status=400)
#                 except (ValueError, TypeError):
#                     return Response({"error": f"Quantité manquante ou invalide pour le produit {produit.sku}."}, status=status.HTTP_400_BAD_REQUEST)
                
                
#                 # try:
#                 #     produit = Produit.objects.select_related('marque').get(id=item['produit']['id'])
#                 # except Produit.DoesNotExist:
#                 #     return Response({"error": f"Produit avec ID {item['produit']['id']} introuvable."}, status=status.HTTP_404_NOT_FOUND)
                
#                 try:
#                     produit = Produit.objects.select_related('marque').get(id=produit_id)
#                 except Produit.DoesNotExist:
#                     return Response({"error": f"Produit {produit_id} introuvable."}, status=404)
                
#                 # quantite = item['quantite']
#                 # prix_vente_grammes = item['prix_vente_grammes']
#                 # #controle prix de vente et prix de vente reel du produit
#                 # #si le prix de vente du gramme dans la table vente est nulle on recure le prix de vente qui est dans dans la table produit
#                 # prix_vente_grammes = item.get('prix_vente_grammes') or produit.marque.prix
                
#                 # # Prix par défaut
#                 # if prix_vente_grammes is None:
#                 #     prix_vente_grammes = Decimal(produit.marque.prix)
            
#                 # Vérifier le stock du vendeur
#                 try:
#                     vendor_stock = VendorProduit.objects.get(produit=produit, vendor=vendor)
#                 except VendorProduit.DoesNotExist:
#                     return Response({"error": f"Produit {produit.nom} non disponible dans votre stock."}, status=400)

#                 if vendor_stock.quantite < quantite:
#                     return Response({
#                         "error": f"Stock insuffisant pour {produit.nom}. Stock disponible : {vendor_stock.quantite}"
#                     }, status=400)
                
#                 # Calculs
#                 poids = produit.poids or 1
#                 prix_vente = prix_vente_grammes * poids
#                 sous_total = (prix_vente * quantite) + autres 
#                 # sous_total_remise = sous_total * (1 - (remise / 100))
#                 sous_total_remise = sous_total - remise
                
#                 # prix_vente_grammes = produit.marque.prix
#                 # prix_vente = produit.prix_vente
#                 # sous_total_prix_vent = produit.prix_vente*quantite
#                 # prix_at_vente = produit.prix_vente

#                 # # Créer l'objet venteProduit
#                 # #controle prix de vente et prix de vente reel du produit
#                 # #si le prix de vente du gramme dans la table vente est nulle on recure le prix de vente qui est dans dans la table produit
#                 # if prix_vente_grammes is None:
#                 #     prix_vente_grammes = produit.marque.prix
#                 # else:
#                 #     prix_vente_grammes = prix_vente_grammes
                    
                
#                 vente_produit = VenteProduit(
#                     vente=vente,
#                     produit=produit,
#                     quantite=quantite,
#                     prix_vente_grammes=prix_vente_grammes,
#                     remise=remise,
#                     autres=autres,
#                                 )
#                 vente_produits.append(vente_produit)
#                 # montant_total += prix_vente * quantite
#                 montant_total += sous_total
                
#                 # Mise à jour du stock vendeur
#                 vendor_stock.quantite -= quantite
#                 vendor_stock.save()
                

#             # Sauvegarder les produits de la vente
#             VenteProduit.objects.bulk_create(vente_produits)
            
#             # Sauvegarde du montant total
#             # vente.montant_total = montant_total
#             vente.save()
            
#             # Créer la facture
#             # vérification dans ta vue si tu veux éviter les collisions 
#             # (même si la chance est très faible)
#             for _ in range(10):
#                 numero = Facture.generer_numero_facture()
#                 if not Facture.objects.filter(numero_facture=numero).exists():
#                     break
#             else:
#                 raise Exception("Impossible de générer un numéro de facture unique.")

#             facture = Facture.objects.create(
#                 vente=vente,
#                 montant_total=montant_total,
#                 numero_facture=numero
#             )
#             # update nemero facture
#             # facture.numero_facture = f"FAC-{facture.date_creation.strftime('%Y-%m')}-{''.join(random.choices(string.digits, k=7))}"
#             facture.status
#             facture.save()
#             # Créer le paiement
#             # paiement = Paiement.objects.create(facture=facture, montant_paye=0)

#             # Retourner la réponse avec la vente et la facture
#             facture_serializer = FactureSerializers(facture)
#             # paiement_serializer = PaiementSerializers(paiement)
#             return Response(facture_serializer.data, status=status.HTTP_201_CREATED)

#         except Exception as e:
#             import traceback
#             print(traceback.format_exc())
#             return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        

class ListFactureView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        responses={200: openapi.Response('response description', FactureSerializers)},
    )
    def get(self, request):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager' and request.user.user_role.role != 'vendeur' and request.user.user_role.role != 'caissier':
            return Response({"message": "Access Denied"})
        factures = Facture.objects.all()
        serializer = FactureSerializers(factures, many=True)
        return Response(serializer.data)


class RechercherFactureView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        responses={200: openapi.Response('response description', FactureSerializers)},
    )
    def get(self, request, numero_facture):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager' and request.user.user_role.role != 'vendeur' and request.user.user_role.role != 'caissier':
            return Response({"message": "Access Denied"})
        try:
            # Recherche du produit par son code
            facture = Facture.objects.get(numero_facture=numero_facture)
        except Facture.DoesNotExist:
            raise NotFound("Facture non trouvé avec ce numero de facture.")
        
        # Sérialisation des données du produit
        serializer = FactureSerializers(facture)
        return Response(serializer.data)

class PaiementFactureView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="User login with email and password",
        request_body=PaiementSerializers,
        responses={
            200: openapi.Response("Login successful", openapi.Schema(type=openapi.TYPE_OBJECT, properties={"token": openapi.Schema(type=openapi.TYPE_STRING)})),
            400: openapi.Response("Bad request", openapi.Schema(type=openapi.TYPE_OBJECT, properties={"detail": openapi.Schema(type=openapi.TYPE_STRING)}))
        }
    )
    
    def post(self, request, facture_numero):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager' and request.user.user_role.role != 'caissier':
            return Response({"message": "Access Denied"})
        try:
            # Get the facture by the facture_num
            facture = Facture.objects.get(numero_facture=facture_numero)
        except Facture.DoesNotExist:
            return Response({"detail": "Facture not found."}, status=status.HTTP_404_NOT_FOUND)

        if facture.status == 'Payé':
            return Response({'error': 'La facture est déjà payée'}, status=status.HTTP_400_BAD_REQUEST)

        paiement_data = request.data.get('paiement')
        montant_paye = paiement_data['montant_paye']
        if not montant_paye:
            return Response({'error': 'montant paye is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # pour plusieur field
        # amount_paid = request.data.get('amount_paid')
        # payment_method = request.data.get('payment_method')
        # transaction_id = request.data.get('transaction_id')
        # if not all([amount_paid, payment_method, transaction_id]):
        #     return Response({'error': 'All payment fields are required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Record the payment
        paiement = Paiement.objects.create(
            facture=facture,
            montant_paye=montant_paye,
        )
        
        # Check if invoice is fully paid
        # total_paye = facture.paiement_facture.aggregate(models.Sum('montant_paye'))['montant_paye__sum'] or 0
        # Check if the paiement covers the total amount
        if paiement.montant_paye >= facture.montant_total:
            facture.status = "Payé"
        else:
            facture.status = "Nom Payé"

        # Save the updated payment status
        facture.save()
            

        return Response({'message': 'Paiement réussi', 'paiement': PaiementSerializers(paiement).data}, status=status.HTTP_201_CREATED)


# Vue API pour modifier un produit dans une vente
# path('vente/<int:vente_id>/produit/<int:venteproduit_id>/edit', VenteProduitEditView.as_view(), name='vente-produit-edit'),
# class VenteProduitEditView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Modifier un produit spécifique dans une vente",
#         manual_parameters=[
#             openapi.Parameter('vente_id', openapi.IN_PATH, type=openapi.TYPE_INTEGER, required=True, description="ID de la vente"),
#             openapi.Parameter('venteproduit_id', openapi.IN_PATH, type=openapi.TYPE_INTEGER, required=True, description="ID du produit dans la vente"),
#         ],
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["quantite", "prix_vente_grammes"],
#             properties={
#                 "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, description="Nouvelle quantité"),
#                 "prix_vente_grammes": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal", description="Nouveau prix par gramme"),
#             }
#         ),
#         responses={
#             200: openapi.Response(description="Produit modifié avec succès"),
#             400: openapi.Response(description="Requête invalide"),
#             404: openapi.Response(description="Produit ou vente non trouvé"),
#             403: openapi.Response(description="Accès refusé"),
#         }
#     )
#     @transaction.atomic
#     def put(self, request, vente_id, venteproduit_id):
#         role = getattr(request.user.user_role, 'role', None)
#         if role not in ['admin', 'manager', 'vendeur']:
#             return Response({"message": "Access Denied"}, status=403)

#         try:
#             from sale.models import VenteProduit, Vente
#             from stock.models import VendorProduit

#             vente = Vente.objects.get(id=vente_id)
#             vp = VenteProduit.objects.select_related('produit').get(id=venteproduit_id, vente=vente)

#             ancienne_quantite = vp.quantite
#             produit = vp.produit

#             quantite = int(request.data.get("quantite"))
#             prix_vente_grammes = Decimal(request.data.get("prix_vente_grammes"))

#             if quantite <= 0 or prix_vente_grammes <= 0:
#                 return Response({"detail": "Quantité ou prix invalide."}, status=400)

#             # Recalculer les prix
#             sous_total = quantite * prix_vente_grammes * produit.poids

#             # Mettre à jour l'objet
#             vp.quantite = quantite
#             vp.prix_vente_grammes = prix_vente_grammes
#             vp.sous_total_prix_vent = sous_total
#             vp.save()

#             # Mise à jour du stock vendeur
#             try:
#                 vp_stock = VendorProduit.objects.get(produit=produit, vendor__user=request.user)
#                 difference = quantite - ancienne_quantite
#                 vp_stock.quantite -= difference
#                 vp_stock.save()
#             except:
#                 pass  # ignorer si pas trouvé (cas rare)

#             # Recalculer le total de la vente
#             total = sum(p.sous_total_prix_vent for p in vente.produits.all())
#             vente.montant_total = total
#             vente.save()

#             return Response({
#                 "message": "Produit mis à jour avec succès.",
#                 "vente_id": vente.id,
#                 "produit_id": vp.produit.id,
#                 "quantite": vp.quantite,
#                 "prix_vente_grammes": float(vp.prix_vente_grammes),
#                 "sous_total": float(vp.sous_total_prix_vent)
#             }, status=200)

#         except Vente.DoesNotExist:
#             return Response({"detail": "Vente introuvable."}, status=404)
#         except VenteProduit.DoesNotExist:
#             return Response({"detail": "Produit dans la vente introuvable."}, status=404)
#         except Exception as e:
#             return Response({"detail": str(e)}, status=500)



# class PaiementUpdateView(APIView):
    
#     # def get(self, request, id, format=None):
#     #     try:
#     #         facture = Facture.objects.get(id=id)  # Find the book by primary key (id)
#     #     except Facture.DoesNotExist:
#     #         raise NotFound("Facture not found")

#     #     # Serialize the book data
#     #     serializer = FactureSerializers(facture)
#     #     return Response(serializer.data)
    
#     def get(self, request, id):
#         try:
#             facture = Facture.objects.get(id=id)
#             serializer = FactureSerializers(facture)
#             return Response(serializer.data)
#         except Facture.DoesNotExist:
#             return Response({'detail': 'Facture non trouvé'}, status=status.HTTP_404_NOT_FOUND)
    
    
#     def post(self, request, facture_numero):
        
#         try:
#             # Get the facture by the facture_id
#             facture = Facture.objects.get(numero_facture=facture_numero)
#             print(facture)
#         except Facture.DoesNotExist:
#             return Response({"detail": "Facture not found."}, status=status.HTTP_404_NOT_FOUND)

#         # Get the associated paiement for the facture
#         paiement = Paiement.objects.filter(facture=facture).first()

#         if not paiement:
#             return Response({"detail": "No payment record found for this facture."}, status=status.HTTP_400_BAD_REQUEST)
        
#         # Check if the paiement covers the total amount
#         if paiement.montant_paye >= facture.montant_total:
#             facture.payment_status = "payé"
#             paiement.montant_paye = facture.montant_total
#         else:
#             facture.payment_status = "en attente"

#         # Save the updated payment status
#         facture.save()
#         paiement.save()

#         return Response({"payment_status": facture.payment_status}, status=status.HTTP_200_OK)
    
#     # def put(self, request, pk):
#     #     try:
#     #         paiement = Paiement.objects.get(pk=pk)
#     #     except Paiement.DoesNotExist:
#     #         raise NotFound(detail="Paiement non trouvé")
        
#     #     serializer = PaiementSerializers(paiement, data=request.data, partial=True)
#     #     if serializer.is_valid():
#     #         paiement = serializer.save()
#     #         # Update etat facture 
#     #         facture = paiement.facture
#     #         facture.payment_status = "Payée"
#     #         # update montant paiement in table paiement
#     #         paiement.montant_paye = paiement.facture.montant_total
#     #         facture.save()
#     #         paiement.save()
#     #         return Response(serializer.data)
#     #     return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    


class VentProduitsListAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        responses={200: openapi.Response('response description', VenteProduitSerializer)},
    )
    def get(self, request):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager' and request.user.user_role.role != 'vendeur' and request.user.user_role.role != 'caissier':
            return Response({"message": "Access Denied"})
        venteproduits = VenteProduit.objects.all()
        serializer = VenteProduitSerializer(venteproduits, many=True)
        return Response(serializer.data)


# # Fonction pour générer le PDF
# def generer_facture_pdf(facture):
#     html_string = render_to_string('facture_template.html', {'facture': facture})
#     pdf_file = HTML(string=html_string).write_pdf()

#     # Nom du fichier
#     filename = f"facture_{facture.id}.pdf"
#     facture.fichier_pdf.save(filename, ContentFile(pdf_file), save=True)

#     facture = Facture.objects.create(vente=vente, montant_total=montant_total)

#     # Générer et attacher le PDF
#     generer_facture_pdf(facture)

#     # Retour
#     fichier_url = request.build_absolute_uri(facture.fichier_pdf.url)
#     return Response({
#         "facture": FactureSerializers(facture).data,
#         "fichier_pdf": fichier_url
#     }, status=201)



# class VenteProduitDetailAPIView(APIView):
#     # renderer_classes = [UserRenderer]
#     # permission_classes = [IsAuthenticated]
#     def get_object(self, slug):
#         try:
#             return VenteProduit.objects.get(slug=slug)
#         except VenteProduit.DoesNotExist:
#             return None

#     def get(self, request, slug):
#         venteProduit = self.get_object(slug)
#         if venteProduit is None:
#             return Response(status=status.HTTP_404_NOT_FOUND)
#         serializer = VenteProduitSerializer(venteProduit)
#         return Response(serializer.data)

#     def put(self, request, slug):
#         # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
#         #     return Response({"message": "Access Denied"})
#         venteProduit = self.get_object(slug)
#         if venteProduit is None:
#             return Response(status=status.HTTP_404_NOT_FOUND)
#         serializer = VenteProduitSerializer(venteProduit, data=request.data)
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# class FactureListAPIView(APIView):
#     # renderer_classes = [UserRenderer]
#     # permission_classes = [IsAuthenticated]
#     def get(self, request):
#         factures = Facture.objects.all()
#         serializer = FactureSerializer(factures, many=True)
#         return Response(serializer.data)


# class FactureDetailAPIView(APIView):
#     # renderer_classes = [UserRenderer]
#     # permission_classes = [IsAuthenticated]
#     def get_object(self, numero_facture):
#         try:
#             return Facture.objects.get(str=numero_facture)
#         except Facture.DoesNotExist:
#             return None

#     def get(self, request, numero_facture):
#         facture = self.get_object(numero_facture)
#         if facture is None:
#             return Response(status=status.HTTP_404_NOT_FOUND)
#         serializer = FactureSerializer(facture)
#         return Response(serializer.data)

#     def put(self, request, numero_facture):
#         # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
#         #     return Response({"message": "Access Denied"})
#         facture = self.get_object(numero_facture)
#         if facture is None:
#             return Response(status=status.HTTP_404_NOT_FOUND)
#         serializer = FactureSerializer(facture, data=request.data)
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# class GenerateFacturePDF(APIView):
    # def get(self, request, facture_numero):
    #     # Fetch the invoice object from the database
    #     # facture = Facture.objects.get(id=facture_id)
    #     facture = Facture.objects.get(numero_facture=facture_numero)
        
    #     # Prepare context for the template
    #     context = {
    #         'facture': facture
    #     }
        
    #     # Render the HTML template with the context data
    #     html_string = render(request, 'facture.html', context)
        
    #     # Generate PDF from the HTML
    #     pdf = HTML(string=html_string.content).write_pdf()

    #     # Create the HTTP response with the PDF file
    #     response = HttpResponse(pdf, content_type='application/pdf')
    #     # response['Content-Disposition'] = f'attachment; filename="facture_{facture.id}.pdf"'
    #     response['Content-Disposition'] = f'attachment; filename="facture_{facture.numero_facture}.pdf"'
        
    #     return response
