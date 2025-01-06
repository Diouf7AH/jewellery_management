import random
import string

# from weasyprint import HTML
# import weasyprint
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
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
                              PaiementSerializers, VenteProduitSerializers,
                              VenteSerializers)
from store.models import Produit


# Create your views here.
class VenteProduitCreateView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager' and request.user.user_role.role != 'vendeur':
            return Response({"message": "Access Denied"})
        data = request.data

        # Récupérer les données du client
        client_data = data.get('client')
        client, created = Client.objects.get_or_create(
            # telephone=client_data['telephone'],
            nom=client_data['nom'],
            prenom=client_data['prenom'],
            defaults=client_data
        )

        # Créer la vente
        vente = Vente.objects.create(client=client)

        # Liste pour les objets venteProduit
        vente_produits = []
        montant_total = 0

        # Ajouter les produits à la vente
        for item in data.get('produits', []):
            produit = Produit.objects.get(id=item['produit']['id'])
            quantite = item['quantite']
            prix_vente_grammes = item['prix_vente_grammes']
            #verifier le stock
            if produit.quantite_en_stock < quantite:
                return Response({"error": f"Pas assez de stock pour {produit.nom} le stock est {produit.quantite_en_stock}"}, status=status.HTTP_400_BAD_REQUEST)
            # prix_vente_grammes = produit.marque.prix
            # prix_vente = produit.prix_vente
            # sous_total_prix_vent = produit.prix_vente*quantite
            # prix_at_vente = produit.prix_vente

            # Créer l'objet venteProduit
            #controle prix de vente et prix de vente reel du produit
            #si le prix de vente du gramme dans la table vente est nulle on recure le prix de vente qui est dans dans la table produit
            if prix_vente_grammes is None:
                prix_vente_grammes = produit.marque.prix
            else:
                prix_vente_grammes = prix_vente_grammes
                
            prix_vente = prix_vente_grammes*produit.poids
            sous_total_prix_vent = prix_vente*quantite
            vente_produit = VenteProduit(
                vente=vente,
                produit=produit,
                quantite=quantite,
                prix_vente_grammes=prix_vente_grammes,
                sous_total_prix_vent=sous_total_prix_vent,
                # prix_at_vente=prix_at_vente
            )
            vente_produits.append(vente_produit)
            # montant_total += prix_vente * quantite
            montant_total += sous_total_prix_vent

            # Mettre à jour le stock de produit et le prix de vente du gramme
            produit.quantite_en_stock -= quantite
            produit.prix_vente_grammes=prix_vente_grammes
            produit.save()

        # Sauvegarder les produits de la vente
        VenteProduit.objects.bulk_create(vente_produits)
        # update montant_total in vente
        vente.montant_total=montant_total
        vente.save()
        # Créer la facture
        facture = Facture.objects.create(vente=vente, montant_total=montant_total)
        # update nemero facture
        # facture.numero_facture = f"FAC-{facture.date_creation.strftime('%Y-%m')}-{''.join(random.choices(string.digits, k=7))}",
        # facture.save()
        # Créer le paiement
        # paiement = Paiement.objects.create(facture=facture, montant_paye=0)

        # Retourner la réponse avec la vente et la facture
        facture_serializer = FactureSerializers(facture)
        # paiement_serializer = PaiementSerializers(paiement)
        return Response(facture_serializer.data, status=status.HTTP_201_CREATED)


class ListFactureView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    def get(self, request):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager' and request.user.user_role.role != 'vendeur' and request.user.user_role.role != 'caissier':
            return Response({"message": "Access Denied"})
        factures = Facture.objects.all()
        serializer = FactureSerializers(factures, many=True)
        return Response(serializer.data)


class RechercherFactureView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
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
            facture.status = "En attente"

        # Save the updated payment status
        facture.save()
            

        return Response({'message': 'Paiement réussi', 'paiement': PaiementSerializers(paiement).data}, status=status.HTTP_201_CREATED)
    
    
    
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
    def get(self, request):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager' and request.user.user_role.role != 'vendeur' and request.user.user_role.role != 'caissier':
            return Response({"message": "Access Denied"})
        venteproduits = VenteProduit.objects.all()
        serializer = VenteProduitSerializers(venteproduits, many=True)
        return Response(serializer.data)
    

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
    
    # def get(self, request, facture_id):
    # def get(self, request, facture_numero):
    #     # Récupérer la facture à partir de l'ID
    #     try:
    #         # facture = Facture.objects.get(id=facture_id)
    #         facture = Facture.objects.get(numero_facture=facture_numero)
    #     except Facture.DoesNotExist:
    #         return Response({'error': 'Facture non trouvée'}, status=404)

    #     # Rendre le modèle HTML pour la facture
    #     html_string = render_to_string('facture_template.html', {'facture': facture})

    #     # Convertir l'HTML en PDF
    #     pdf_file = weasyprint.HTML(string=html_string).write_pdf()

    #     # Retourner la réponse PDF
    #     response = HttpResponse(pdf_file, content_type='application/pdf')
    #     response['Content-Disposition'] = f'attachment; filename="facture_{facture.numero_facture}.pdf"'

    #     return response