


# Create your views here.
# methode 1
# class ProduitStockAPIView(APIView):
#     def post(self, request, *args, **kwargs):
#         # Assume the incoming data has 'produit', 'fournisseur', 'quantity', and 'price'
#         produit_data = request.data.get("produit")
#         fournisseur_data = request.data.get("fournisseur")
#         poids = request.data.get("poids")
#         prix_achat_gramm = request.data.get("prix_achat_gramm")
#         # prix_achat_unite = request.data.get("prix_achat_unite")
#         # slug = request.data.get("slug")
#         quantite = request.data.get("quantite")
#         # total_prix_achat = request.data.get("total_prix_achat")
#         date_ajout = request.data.get("date_ajout")

#         try:
#             with transaction.atomic():
#                 # Create or update Produit
#                 produit, created_produit = Produit.objects.get_or_create(
#                     nom=produit_data['nom'],
#                     image=produit_data['image'],
#                     categorie=produit_data['categorie'],
#                     purete=produit_data['purete'],
#                     marque=produit_data['marque'],
#                     matiere=produit_data['matiere'],
#                     modele=produit_data['modele'],
#                     status=produit_data['status'],
#                     # qr_code=produit_data['qr_code'],
#                     poids=produit_data['poids'],
#                     taille=produit_data['taille'],
#                     genre=produit_data['genre'],
#                     prix_vente=produit_data['prix_vente'],
#                     # prix_vente_reel=produit_data['prix_vente_reel'],
#                     prix_avec_tax=produit_data['prix_avec_tax'],
#                     # sku=produit_data['sku'],
#                     # pid=produit_data['pid'],
#                     # slug=produit_data['slug'],
#                     # date=produit_data['date'],
#                     defaults={'description': produit_data['description']}
#                 )

#                 # Create or update Fournisseur
#                 fournisseur, created_fournisseur = Fournisseur.objects.get_or_create(
#                     nom=fournisseur_data['nom'],
#                     prenom=fournisseur_data['prenom'],
#                     address=fournisseur_data['address'],
#                 )

#                 # Add to Stock
#                 Stock.objects.create(
#                     produit=produit,
#                     fournisseur=fournisseur,
#                     poids=poids,
#                     prix_achat_gramm=prix_achat_gramm,
#                     # prix_achat_unite=prix_achat_unite,
#                     # total_prix_achat=total_prix_achat,
#                     # slug=slug,
#                     quantite=quantite,
#                     date_ajout=date_ajout,
#                 )

#                 # If everything is fine, return success response
#                 return Response({
#                     "message": "Produit, Stock, and Fournisseur created successfully"
#                 }, status=status.HTTP_201_CREATED)

#         except Exception as e:
#             # In case of an error, the transaction is rolled back
#             return Response({
#                 "error": str(e)
#             }, status=status.HTTP_400_BAD_REQUEST)



#mthode 2
# class StockAPIView(APIView):
#     def post(self, request, *args, **kwargs):
#         """
#         Crée une nouvelle entrée de stock pour un produit et un fournisseur donné.
#         Cette opération est atomique.
#         """
#         with transaction.atomic():
#             try:
#                 # Désérialiser les données
#                 produit_data = request.data.get('produit')
#                 fournisseur_data = request.data.get('fournisseur')
#                 quantite = request.data.get('quantite')
#                 date_approvisionnement = request.data.get('date_approvisionnement')

#                 # Créer ou récupérer le produit
#                 produit, created = Produit.objects.get_or_create(**produit_data)

#                 # Créer ou récupérer le fournisseur
#                 fournisseur, created = Fournisseur.objects.get_or_create(**fournisseur_data)

#                 # Créer un nouvel enregistrement de stock
#                 stock = Stock.objects.create(
#                     produit=produit,
#                     fournisseur=fournisseur,
#                     quantite=quantite,
#                     date_approvisionnement=date_approvisionnement
#                 )

#                 # Sérialiser la réponse
#                 stock_serializer = StockSerializer(stock)

#                 # Retourner la réponse
#                 return Response(stock_serializer.data, status=status.HTTP_201_CREATED)

#             except Exception as e:
#                 # En cas d'erreur, la transaction sera annulée
#                 return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

#     def get(self, request, *args, **kwargs):
#         """
#         Récupère tous les stocks.
#         """
#         stocks = Stock.objects.all()
#         stock_serializer = StockSerializer(stocks, many=True)
#         return Response(stock_serializer.data)





#     # @transaction.atomic
#     # def put(self, request, *args, **kwargs):
#     #         """
#     #     Update produit and Stock records atomically.
#     #         """
#     #         try:
#     #             produit_id = request.data.get('produit_id')
#     #             produit = Produit.objects.get(id=produit_id)
#     #             produit.non = request.data.get('produit_non', produit.nom)
#     #             produit.description = request.data.get('description', produit.description)
#     #             produit.image = request.data.get('image', produit.image)
#     #             produit.categorie = request.data.get('categorie', produit.categorie)
#     #             produit.purete = request.data.get('purete', produit.purete)
#     #             produit.marque = request.data.get('marque', produit.marque)
#     #             produit.matiere = request.data.get('matiere', produit.matiere)
#     #             produit.modele = request.data.get('modele', produit.modele)
#     #             produit.status = request.data.get('status', produit.status)
#     #             produit.poids = request.data.get('poids', produit.poids)
#     #             produit.taille = request.data.get('taille', produit.taille)
#     #             produit.genre = request.data.get('genre', produit.genre)
#     #             produit.prix_vente = request.data.get('prix_vente', produit.prix_vente)
#     #             produit.prix_vente_reel = request.data.get('prix_vente_reel', produit.prix_vente_reel)
#     #             produit.prix_avec_tax = request.data.get('prix_avec_tax', produit.prix_avec_tax)
#     #             produit.sku = request.data.get('sku', produit.sku)
#     #             produit.pid = request.data.get('pid', produit.pid)
#     #             produit.slug = request.data.get('pid', produit.slug)
#     #             produit.date = request.data.get('pid', produit.date)
#     #             produit.save()
                
#     #             fournisseur_id = request.data.get('fournisseur_id')
#     #             fournisseur = Fournisseur.objects.get(id=fournisseur_id)
#     #             fournisseur.non = request.data.get('fournisseur_non', fournisseur.nom)
#     #             fournisseur.prenon = request.data.get('fournisseur_prenon', fournisseur.prenom)
#     #             fournisseur.address = request.data.get('fournisseur_address', fournisseur.address)
#     #             fournisseur.telephone = request.data.get('fournisseur_non', fournisseur.telephone)
#     #             fournisseur.save()

#     #             stock_data = request.data.get('stock')
#     #             stock = Stock.objects.get(id=stock_data.get('id'))
#     #             stock.poids = stock_data.get('poids', stock.poids)
#     #             stock.prix_achat_gramm = stock_data.get('prix_achat_gramm', stock.prix_achat_gramm)
#     #             stock.quantity = stock_data.get('quantity', stock.quantity)
#     #             stock.total_prix_achat = stock_data.get('total_prix_achat', stock.total_prix_achat)
#     #             stock.save()

#     #             # return Response({
#     #             #     'produit': ProduitSerializer(produit).data,
#     #             #     'fournisseur': FournisseurSerializer(fournisseur).data,
#     #             #     'stock': StockSerializer(stock).data,
#     #             # }, status=status.HTTP_200_OK)
                
#     #             # If everything is fine, return success response
#     #             return Response({
#     #                 "message": "Produit, Stock, and Fournisseur updating successfully"
#     #             }, status=status.HTTP_201_CREATED)

#     #         # except produit.DoesNotExist:
#     #         #     return Response({'error': 'produit not found'}, status=status.HTTP_404_NOT_FOUND)
#     #         # except fournisseur.DoesNotExist:
#     #         #     return Response({'error': 'fournisseur not found'}, status=status.HTTP_404_NOT_FOUND)
#     #         # except Stock.DoesNotExist:
#     #         #     return Response({'error': 'Stock record not found'}, status=status.HTTP_404_NOT_FOUND)
#     #         except Exception as e:
#     #             transaction.set_rollback(True)
#     #             return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


#     # def put(self, request, produit_id, fournisseur_id):
#     #     try:
#     #         # Récupérer le produit et le fournisseur à partir des paramètres
#     #         produit = Produit.objects.get(id=produit_id)
#     #         fournisseur = Fournisseur.objects.get(id=fournisseur_id)
            
#     #         # Récupérer ou créer le stock
#     #         stock, created = Stock.objects.get_or_create(produit=produit, fournisseur=fournisseur)

#     #         # Mettre à jour la quantité en fonction des données envoyées
#     #         new_quantite = request.data.get('quantite')
#     #         if new_quantite is None:
#     #             return Response({"error": "Quantité non fournie"}, status=status.HTTP_400_BAD_REQUEST)
            
#     #         # Utiliser une transaction atomique pour garantir la consistance des données
#     #         with transaction.atomic():
#     #             # Mise à jour de la quantité dans le stock
#     #             stock.quantite = new_quantite
#     #             stock.save()

#     #             # Vous pourriez ajouter ici des vérifications supplémentaires si nécessaire, comme la mise à jour du prix
#     #             # pour le produit, etc. Par exemple, si vous voulez ajuster le prix du produit basé sur les quantités.

#     #         return Response({"message": "Stock mis à jour avec succès"}, status=status.HTTP_200_OK)

#     #     except Produit.DoesNotExist:
#     #         return Response({"error": "Produit non trouvé"}, status=status.HTTP_404_NOT_FOUND)
#     #     except Fournisseur.DoesNotExist:
#     #         return Response({"error": "Fournisseur non trouvé"}, status=status.HTTP_404_NOT_FOUND)
#     #     except Exception as e:
#     #         return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



        
# rechercher et mettre à jour la facture (views.py):
# def get(self, request, numero_facture):
#         """
#         Recherche un paiement par numéro de facture et le met à jour
#         """
#         try:
#             # Rechercher le paiement par numéro de facture
#             paiement = Paiement.objects.get(facture__numero_facture=numero_facture).first()
            
#             # Sérialiser les données de paiement
#             serializer = PaiementSerializers(paiement)
#             return Response(serializer.data, status=status.HTTP_200_OK)
        
#         except Paiement.DoesNotExist:
#             return Response({"detail": "Paiement non trouvé."}, status=status.HTTP_404_NOT_FOUND)

#     def put(self, request, numero_facture):
#         """
#         Met à jour les informations d'un paiement existant
#         """
#         try:
#             # Rechercher le paiement par numéro de facture
#             paiement = Paiement.objects.get(facture__numero_facture=numero_facture)
            
#             # Sérialiser les nouvelles données et les valider
#             serializer = PaiementSerializer(paiement, data=request.data, partial=True)
#             if serializer.is_valid():
#                 # Sauvegarder les données mises à jour
#                 serializer.save()
#                 return Response(serializer.data, status=status.HTTP_200_OK)
#             else:
#                 return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#         except Paiement.DoesNotExist:
#             return Response({"detail": "Paiement non trouvé."}, status=status.HTTP_404_NOT_FOUND)
        