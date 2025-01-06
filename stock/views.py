import json

from django.db import transaction
from django.shortcuts import get_object_or_404, render
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.renderers import UserRenderer
from stock.models import Fournisseur, Stock
from stock.serializers import FournisseurSerializer, StockSerializer
from store.models import Categorie, Marque, Modele, Produit, Purete
from store.serializers import MarqueSerializer, ProduitSerializer


# django post using apiview relation 4 tables categorie produit fournisseur stock relation                table produit relation category = models.ForeignKey(Categorie, related_nom='produits', on_delete=models.CASCADE)
#   table stock relation produit = models.ForeignKey(Produit, related_nom='stocks', on_delete=models.CASCADE)                     fournosseur = models.ForeignKey(fornisseur, related_nom='stocks_four', on_delete=models.CASCADE)
# Create your views here.
# methode 1
class ProduitStockAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        """
        Create produit, stock, and fournisseur in one transaction.
        """

        # Start a transaction block
        try:
            # Validate and create Produit
            produit_data = request.data.get('produit')
            produit_serializer = ProduitSerializer(data=produit_data)
            if produit_serializer.is_valid():
                produit = produit_serializer.save()
            else:
                return Response(produit_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            # On suppose que l'attribut par lequel on cherche est 'id'
            fournisseur_data = request.data.get('fournisseur')
            fournisseur_telephone = fournisseur_data.get('telephone')
            fournisseur, created = Fournisseur.objects.update_or_create(
                telephone=fournisseur_telephone,  # ou n'importe quel autre champ unique
                defaults=fournisseur_data # Met à jour avec les nouvelles données
            )
            # Serializer l'instance pour la réponse
            fournisseur_serializer=FournisseurSerializer(fournisseur_data)
            
            # if created:
            #     return Response(fournisseur_serializer.data, status=status.HTTP_201_CREATED)
            # else:
            #     return Response(fournisseur_serializer.data, status=status.HTTP_200_OK)
            
    
            # Validate and create Stock
            stock_data = request.data.get('stock')
            stock_data['produit'] = produit.id
            stock_data['fournisseur'] = fournisseur.id
            stock_serializer = StockSerializer(data=stock_data)
            if stock_serializer.is_valid():
                stock=stock_serializer.save()
                # Update total_poids_achat
                # stock.total_poids_achat = produit.poids * stock.quantite
                # Update the produit's stock quantity
                produit = stock.produit
                print(stock)
                print(produit)
                produit.quantite_en_stock += stock.quantite
                produit.save()
                
            else:
                return Response(stock_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            # Commit transaction if everything is successful
            return Response({
                'produit': produit_serializer.data,
                'fournisseur': fournisseur_serializer.data,
                'stock': stock_serializer.data
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            # If any exception occurs, the transaction will be rolled back
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    
    
    #get all
    def get(self, request, *args, **kwargs):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager' and request.user.user_role.role != 'vendeur':
            return Response({"message": "Access Denied"})
        try:
            # Début de la transaction
            with transaction.atomic():
                # Récupérer tous les produits
                produits = Produit.objects.all()
                fournisseurs = Fournisseur.objects.all()

                # Récupérer le stock pour chaque produit et fournisseur
                stocks = Stock.objects.select_related('produit', 'fournisseur').all()

                # Sérialisation des stocks
                stock_serializer = StockSerializer(stocks, many=True)

                # Sérialisation des produits (optionnel, si vous voulez des détails sur les produits aussi)
                produit_serializer = ProduitSerializer(produits, many=True)
                fournisseur_serializer = FournisseurSerializer(fournisseurs, many=True)

                # Retourner les données sous forme de réponse
                return Response({
                    'produits': produit_serializer.data,
                    'fournisseurs': fournisseur_serializer.data,
                    'stocks': stock_serializer.data
                }, status=status.HTTP_200_OK)

        except Exception as e:
            # Si une erreur survient, annuler la transaction et renvoyer une erreur
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    


class ProduitStockDetailAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    def get(self, request, produit_id, fournisseur_id):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        try:
            with transaction.atomic():
                # Récupérer le produit
                produit = Produit.objects.get(id=produit_id)
                fournisseur = Fournisseur.objects.get(id=fournisseur_id)

                # Récupérer le stock du produit pour tous les fournisseurs
                stock = Stock.objects.filter(produit=produit,fournisseur=fournisseur)
                
                # Sérialiser les données
                produit_serializer = ProduitSerializer(produit)
                fournisseur_serializer =FournisseurSerializer(fournisseur)
                stock_serializer = StockSerializer(stock, many=True)

                # Retourner la réponse avec le produit et son stock
                return Response({
                    'produit': produit_serializer.data,
                    'fournisseur': fournisseur_serializer.data,
                    'stock': stock_serializer.data
                })

        except Produit.DoesNotExist:
            return Response({'detail': 'Produit non trouvé'}, status=404)
        except Fournisseur.DoesNotExist:
            return Response({'error': 'fournisseur not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)
    
        
    @transaction.atomic  # Nous utilisons transaction.atomic() pour garantir l'atomicité
    def put(self, request, produit_id, fournisseur_id):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        try:

            # Récupérer le produit, le fournisseur et le stock associés
            produit = Produit.objects.get(id=produit_id)
            fournisseur = Fournisseur.objects.get(id=fournisseur_id)
            stock = Stock.objects.get(produit=produit, fournisseur=fournisseur)

            # Mettre à jour le produit avec les données envoyées
            produit_serializer = ProduitSerializer(produit, data=request.data.get('produit'), partial=True)
            if produit_serializer.is_valid():
                # produit.prix_vente = produit.calcule_prix_vente()
                produit_serializer.save()
            else:
                return Response(produit_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            # Mettre à jour le stock avec les nouvelles informations (quantité, prix, etc.)
            stock_serializer = StockSerializer(stock, data=request.data.get('stock'), partial=True)
            if stock_serializer.is_valid():
                stock_serializer.save()
            else:
                return Response(stock_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            # Mettre à jour le fournisseur (si nécessaire)
            fournisseur_data = request.data.get('fournisseur', {})
            if fournisseur_data:
                fournisseur_serializer = FournisseurSerializer(fournisseur, data=fournisseur_data, partial=True)
                if fournisseur_serializer.is_valid():
                    fournisseur_serializer.save()

            # Si tout se passe bien, renvoyer une réponse réussie
            return Response({
                'produit': produit_serializer.data,
                'stock': stock_serializer.data,
                'fournisseur': fournisseur_serializer.data if 'fournisseur' in request.data else None
            }, status=status.HTTP_200_OK)

        except Produit.DoesNotExist:
            return Response({'error': 'Produit non trouvé'}, status=status.HTTP_404_NOT_FOUND)
        except Fournisseur.DoesNotExist:
            return Response({'error': 'Fournisseur non trouvé'}, status=status.HTTP_404_NOT_FOUND)
        except Stock.DoesNotExist:
            return Response({'error': 'Stock non trouvé pour ce produit et ce fournisseur'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
#Cette methode est utilise pour mettre a jour le stock du produit
#En realite en fait un nouveau enregistrement de stock pour l'inventaire et on modifie la quanti_en_stock dans produit    
class UpdateStockAPIView(APIView):   
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    #metrre a jour le stock
    # def patch(self, request, pk, format=None):
    #     try:
    #         stock = Stock.objects.get(pk=pk)
    #     except Stock.DoesNotExist:
    #         return Response({'error': 'Stock not found'}, status=status.HTTP_404_NOT_FOUND)

    #     # Deserialize the incoming data
    #     serializer = StockSerializer(stock, data=request.data, partial=True)  # partial=True allows partial updates

    #     if serializer.is_valid():
    #         # Save the updated stock
    #         serializer.save()
    #         return Response(serializer.data, status=status.HTTP_200_OK)

    #     return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def get(self, request, pk, format=None):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        try:
            stock = Stock.objects.get(pk=pk)
        except Stock.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = StockSerializer(stock)
        return Response(serializer.data)
    
    # POST method to create a new stock instance
    def post(self, request, format=None):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        serializer = StockSerializer(data=request.data)
        if serializer.is_valid():
            stock = serializer.save()
            #Update quantite en stock in produit
            produit = stock.produit
            produit.quantite_en_stock += stock.quantite
            produit.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



