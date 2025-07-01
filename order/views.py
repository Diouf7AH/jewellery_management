from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.db import transaction
from django.shortcuts import get_object_or_404

from sale.models import Client
from order.serializers import InfoClientPassCommandeSerializer, CommandeClientSerializer, CommandeProduitClientSerializer
from order.models import CommandeClient, CommandeProduitClient
from userauths.models import User  # si nécessaire pour created_by

# class CreateCommandeClientView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Créer une commande client avec ses produits.",
#         request_body=CommandeClientSerializer,
#         responses={201: openapi.Response(description="Commande créée", schema=CommandeClientSerializer())}
#     )
#     def post(self, request):
#         data = request.data.copy()
#         produits_data = data.pop('produits', [])

#         serializer = CommandeClientSerializer(data=data, context={"request": request})
#         if serializer.is_valid():
#             try:
#                 with transaction.atomic():
#                     commande = serializer.save(created_by=request.user)

#                     for produit_data in produits_data:
#                         produit_data['commande'] = commande.id
#                         produit_serializer = CommandeProduitClientSerializer(data=produit_data)
#                         produit_serializer.is_valid(raise_exception=True)
#                         produit_serializer.save()

#                 return Response({
#                     "message": "Commande créée avec succès.",
#                     "commande": CommandeClientSerializer(commande, context={"request": request}).data
#                 }, status=status.HTTP_201_CREATED)

#             except Exception as e:
#                 return Response({"error": f"Une erreur est survenue : {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CreateCommandeClientView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Créer une commande client avec produits officiels et personnalisés",
        # operation_description="Cette API permet de créer une commande en ajoutant un nouveau client si nécessaire. Elle gère à la fois les produits existants (via ID) et les produits personnalisés (avec nom, poids, etc.).",
        operation_description="""
            Cette API permet de créer une commande en ajoutant un nouveau client si nécessaire. Elle gère à la fois les produits existants (via ID) et les produits personnalisés (avec nom, poids, etc.).
            - Exemple de payload JSON côté API :
            
                Pour un produit existant :
                    {
                        "produit": 7,
                        "quantite": 2,
                        "prix_prevue": 125000
                    }
                
                Pour un produit personnalisé :
                    {
                        "produit_libre": "Bracelet sur mesure",
                        "poids_prevu": 12.5,
                        "marque_personnalisee": "Rio Gold",
                        "categorie_personnalisee": "Bracelet",
                        "type_personnalise": "Femmes",
                        "quantite": 1,
                        "prix_prevue": 85000
                    }
        """,
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['client', 'produits'],
            properties={
                'client': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'nom': openapi.Schema(type=openapi.TYPE_STRING, example="Seynabou"),
                        'prenom': openapi.Schema(type=openapi.TYPE_STRING, example="Diouf"),
                        'telephone': openapi.Schema(type=openapi.TYPE_STRING, example="771234567"),
                    },
                    required=['telephone']
                ),
                'produits': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        required=['quantite', 'prix_prevue'],
                        properties={
                            'produit': openapi.Schema(type=openapi.TYPE_INTEGER, description="ID du produit existant (optionnel)", example=3),
                            'produit_libre': openapi.Schema(type=openapi.TYPE_STRING, description="Nom du produit personnalisé", example="Collier personnalisé"),
                            'poids_prevu': openapi.Schema(type=openapi.TYPE_NUMBER, format='float', description="Poids estimé en grammes", example=15.5),
                            'marque_personnalisee': openapi.Schema(type=openapi.TYPE_STRING, example="Rio-Gold"),
                            'categorie_personnalisee': openapi.Schema(type=openapi.TYPE_STRING, example="Collier"),
                            'type_personnalise': openapi.Schema(type=openapi.TYPE_STRING, example="Femme"),
                            'quantite': openapi.Schema(type=openapi.TYPE_INTEGER, example=1),
                            'prix_prevue': openapi.Schema(type=openapi.TYPE_NUMBER, format='float', example=150000),
                        }
                    )
                ),
                'commentaire': openapi.Schema(type=openapi.TYPE_STRING, example="Commande spéciale pour cadeau"),
                'image': openapi.Schema(type=openapi.TYPE_STRING, format='binary'),
            }
        ),
        responses={
            201: openapi.Response(description="Commande créée avec succès."),
            400: "Requête invalide",
            500: "Erreur serveur"
        }
    )
    def post(self, request):
        try:
            data = request.data
            client_data = data.get('client')
            produits_data = data.get('produits', [])

            if not client_data:
                return Response({"error": "Les informations du client sont requises."}, status=400)

            with transaction.atomic():
                # Vérifie si le client existe déjà par téléphone
                telephone = client_data.get('telephone').strip()
                client = Client.objects.filter(telephone=telephone).first()

                if not client:
                    client_serializer = InfoClientPassCommandeSerializer(data=client_data)
                    client_serializer.is_valid(raise_exception=True)
                    client = client_serializer.save()

                # Création de la commande
                commande = CommandeClient.objects.create(
                    client=client,
                    created_by=request.user,
                    commentaire=data.get('commentaire'),
                    image=data.get('image')  # si tu as un champ image
                )

                # Enregistrement des produits
                for index, produit_data in enumerate(produits_data, start=1):
                    produit_data['commande_client'] = commande.id
                    produit_serializer = CommandeProduitClientSerializer(data=produit_data)
                    produit_serializer.is_valid(raise_exception=True)
                    produit_serializer.save()

            return Response({
                "message": "✅ Commande créée avec succès.",
                "commande": CommandeClientSerializer(commande, context={"request": request}).data
            }, status=201)

        except Exception as e:
            return Response({"error": str(e)}, status=500)
        

class ListCommandeClientView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Lister toutes les commandes triées par date d'arrivée (récentes en premier), avec client, produits et créateur.",
        responses={200: openapi.Response(description="Liste des commandes", schema=CommandeClientSerializer(many=True))}
    )
    def get(self, request):
        commandes = CommandeClient.objects.select_related('client', 'created_by')\
            .prefetch_related('produits')\
            .order_by('-date_commande')

        serializer = CommandeClientSerializer(commandes, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class UpdateCommandeByNumeroView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Modifier une commande client à partir de son numéro.",
        request_body=CommandeClientSerializer,
        responses={200: openapi.Response("Commande mise à jour", CommandeClientSerializer())}
    )
    def put(self, request, numero_commande):
        commande = get_object_or_404(CommandeClient, numero_commande=numero_commande)
        data = request.data.copy()
        produits_data = data.pop('produits', [])

        serializer = CommandeClientSerializer(commande, data=data, partial=True, context={'request': request})
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    commande = serializer.save()

                    # Supprimer les anciens produits
                    CommandeProduitClient.objects.filter(commande_client=commande).delete()

                    # Ajouter les nouveaux produits
                    for produit_data in produits_data:
                        CommandeProduitClient.objects.create(commande_client=commande, **produit_data)

                return Response({
                    "message": "Commande mise à jour avec succès.",
                    "commande": CommandeClientSerializer(commande, context={'request': request}).data
                }, status=status.HTTP_200_OK)

            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class ChangeCommandeStatusView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Changer le statut d'une commande via son numéro.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["statut"],
            properties={
                "statut": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=["en_attente", "en_preparation", "livree", "annulee"],
                    description="Nouveau statut"
                )
            }
        ),
        responses={200: openapi.Response(description="Statut mis à jour")}
    )
    def patch(self, request, numero_commande):
        commande = get_object_or_404(CommandeClient, numero_commande=numero_commande)
        nouveau_statut = request.data.get("statut")

        if nouveau_statut not in ["en_attente", "en_preparation", "livree", "annulee"]:
            return Response({"error": "Statut invalide."}, status=status.HTTP_400_BAD_REQUEST)

        commande.statut = nouveau_statut
        commande.save()

        return Response({
            "message": f"Statut de la commande {commande.numero_commande} mis à jour.",
            "statut": commande.statut
        }, status=status.HTTP_200_OK)
