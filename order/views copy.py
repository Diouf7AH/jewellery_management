from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.parsers import MultiPartParser, FormParser
from sale.models import Client
from order.serializers import InfoClientPassCommandeSerializer, CommandeClientSerializer, CommandeProduitClientSerializer, PaiementAcompteBonCommandeViewSerializer
from order.models import CommandeClient, CommandeProduitClient, BonCommande
from userauths.models import User  # si nécessaire pour created_by
import json
from decimal import Decimal
from decimal import Decimal, InvalidOperation
from rest_framework.exceptions import ValidationError

# class CreateCommandeClientView(APIView):
#     permission_classes = [IsAuthenticated]
#     parser_classes = [MultiPartParser, FormParser]  # <== indispensable pour fichier image

#     @swagger_auto_schema(
#         operation_summary="Créer une commande client",
#         operation_description="Créer une commande client avec ajout de produits (officiels ou personnalisés). Le client est créé automatiquement s’il n’existe pas.",
#         manual_parameters=[
#             openapi.Parameter(
#                 name="client",
#                 in_=openapi.IN_FORM,
#                 type=openapi.TYPE_STRING,
#                 description="Objet JSON : {nom, prenom, telephone}"
#             ),
#             openapi.Parameter(
#                 name="produits",
#                 in_=openapi.IN_FORM,
#                 type=openapi.TYPE_STRING,
#                 description="Liste JSON de produits avec champs : produit, categorie, marque, modele, genre, taille, matiere, poids, purete, prix_gramme, quantite, prix, personnalise"
#             ),
#             openapi.Parameter(
#                 name="commentaire",
#                 in_=openapi.IN_FORM,
#                 type=openapi.TYPE_STRING,
#                 required=False,
#                 description="Commentaire optionnel"
#             ),
#             openapi.Parameter(
#                 name="image",
#                 in_=openapi.IN_FORM,
#                 type=openapi.TYPE_FILE,
#                 required=False,
#                 description="Image facultative"
#             ),
#         ],
#         responses={
#             201: openapi.Response(description="✅ Commande créée avec succès."),
#             400: openapi.Response(description="Requête invalide."),
#             500: openapi.Response(description="Erreur serveur."),
#         }
#     )
#     def post(self, request):
#         try:
#             data = request.data
#             client_data = data.get('client')
#             produits_data = data.get('produits', [])

#             if not client_data:
#                 return Response({"error": "Les informations du client sont requises."}, status=400)

#             if not produits_data:
#                 return Response({"error": "Au moins un produit est requis."}, status=400)

#             with transaction.atomic():
#                 telephone = client_data.get('telephone').strip()
#                 client = Client.objects.filter(telephone=telephone).first()

#                 if not client:
#                     client_serializer = InfoClientPassCommandeSerializer(data=client_data)
#                     client_serializer.is_valid(raise_exception=True)
#                     client = client_serializer.save()

#                 image = request.FILES.get('image')  # ✅ récupère l'image

#                 commande = CommandeClient.objects.create(
#                     client=client,
#                     created_by=request.user,
#                     commentaire=data.get('commentaire'),
#                     image=image
#                 )

#                 for produit_data in produits_data:
#                     produit_data['commande_client'] = commande.id
#                     produit_serializer = CommandeProduitClientSerializer(data=produit_data)
#                     produit_serializer.is_valid(raise_exception=True)
#                     produit_serializer.save()

#             return Response({
#                 "message": "✅ Commande créée avec succès.",
#                 "commande": CommandeClientSerializer(commande, context={"request": request}).data
#             }, status=201)

#         except Exception as e:
#             return Response({"error": str(e)}, status=500)


# class CreateCommandeClientView(APIView):
#     permission_classes = [IsAuthenticated]
#     parser_classes = [MultiPartParser, FormParser]

#     @swagger_auto_schema(
#         operation_summary="Créer une commande client",
#         operation_description="Créer une commande client avec des produits (officiels ou personnalisés). Le client est créé automatiquement s’il n’existe pas.",
#         manual_parameters=[
#             openapi.Parameter(
#                 name="commentaire",
#                 in_=openapi.IN_FORM,
#                 type=openapi.TYPE_STRING,
#                 required=False,
#                 description="Commentaire de la commande"
#             ),
#             openapi.Parameter(
#                 name="image",
#                 in_=openapi.IN_FORM,
#                 type=openapi.TYPE_FILE,
#                 required=False,
#                 description="Image facultative liée à la commande"
#             ),
#         ],
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["client", "produits"],
#             properties={
#                 "client": openapi.Schema(
#                     type=openapi.TYPE_OBJECT,
#                     properties={
#                         "nom": openapi.Schema(type=openapi.TYPE_STRING),
#                         "prenom": openapi.Schema(type=openapi.TYPE_STRING),
#                         "telephone": openapi.Schema(type=openapi.TYPE_STRING),
#                     },
#                     required=["telephone"]
#                 ),
#                 "produits": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["quantite", "prix_prevue"],
#                         properties={
#                             "produit": openapi.Schema(type=openapi.TYPE_INTEGER, description="ID produit (optionnel)"),
#                             "categorie": openapi.Schema(type=openapi.TYPE_INTEGER),
#                             "marque": openapi.Schema(type=openapi.TYPE_INTEGER),
#                             "modele": openapi.Schema(type=openapi.TYPE_INTEGER),
#                             "genre": openapi.Schema(type=openapi.TYPE_STRING),
#                             "taille": openapi.Schema(type=openapi.TYPE_STRING),
#                             "matiere": openapi.Schema(type=openapi.TYPE_STRING),
#                             "poids": openapi.Schema(type=openapi.TYPE_NUMBER),
#                             "purete": openapi.Schema(type=openapi.TYPE_INTEGER),
#                             "prix_gramme": openapi.Schema(type=openapi.TYPE_NUMBER),
#                             "quantite": openapi.Schema(type=openapi.TYPE_INTEGER),
#                             "prix_prevue": openapi.Schema(type=openapi.TYPE_NUMBER),
#                             "personnalise": openapi.Schema(type=openapi.TYPE_BOOLEAN)
#                         }
#                     )
#                 )
#             }
#         ),
#         responses={
#             201: openapi.Response(description="✅ Commande créée avec succès."),
#             400: openapi.Response(description="Requête invalide."),
#             500: openapi.Response(description="Erreur serveur."),
#         }
#     )
#     @transaction.atomic
#     def post(self, request):
#         try:
#             data = request.data
#             client_data = data.get("client")
#             produits_data = data.get("produits", [])

#             if not client_data:
#                 return Response({"error": "Les informations du client sont requises."}, status=400)

#             if not produits_data:
#                 return Response({"error": "Au moins un produit est requis."}, status=400)

#             telephone = client_data.get("telephone").strip()
#             client, _ = Client.objects.get_or_create(
#                 telephone=telephone,
#                 defaults={
#                     "nom": client_data.get("nom", ""),
#                     "prenom": client_data.get("prenom", "")
#                 }
#             )

#             image = request.FILES.get("image")
#             commentaire = data.get("commentaire")

#             commande = CommandeClient.objects.create(
#                 client=client,
#                 created_by=request.user,
#                 commentaire=commentaire,
#                 image=image
#             )

#             for produit_data in produits_data:
#                 produit_data["commande_client"] = commande.id
#                 produit_serializer = CommandeProduitClientSerializer(data=produit_data)
#                 produit_serializer.is_valid(raise_exception=True)
#                 produit_serializer.save()

#             return Response({
#                 "message": "✅ Commande créée avec succès.",
#                 "commande": CommandeClientSerializer(commande, context={"request": request}).data
#             }, status=201)

#         except Exception as e:
#             transaction.set_rollback(True)
#             return Response({"error": str(e)}, status=500)


# class CreateCommandeClientView(APIView):
#     permission_classes = [IsAuthenticated]
#     parser_classes = [MultiPartParser, FormParser]  # Pour accepter l’image

#     @swagger_auto_schema(
#         operation_summary="Créer une commande client",
#         operation_description="Créer une commande avec des produits personnalisés ou officiels. "
#                             "Le client est créé automatiquement si le téléphone est nouveau.",
#         manual_parameters=[
#             openapi.Parameter(
#                 name="client",
#                 in_=openapi.IN_FORM,
#                 type=openapi.TYPE_STRING,
#                 description="Objet JSON : {nom, prenom, telephone}"
#             ),
#             openapi.Parameter(
#                 name="produits",
#                 in_=openapi.IN_FORM,
#                 type=openapi.TYPE_STRING,
#                 description=(
#                     "Liste JSON des produits. Exemple prix_prevue, sous_total et le montant_total sont des champs calculé, :\n"
#                     '[{"categorie": 1, "marque": 2, "poids": 3.5, "quantite": 1, '
#                     ' "prix_gramme": 5500, "personnalise": true}]'
#                 )
#             ),
#             openapi.Parameter(
#                 name="commentaire",
#                 in_=openapi.IN_FORM,
#                 type=openapi.TYPE_STRING,
#                 required=False,
#                 description="Commentaire de la commande (facultatif)"
#             ),
#             openapi.Parameter(
#                 name="image",
#                 in_=openapi.IN_FORM,
#                 type=openapi.TYPE_FILE,
#                 required=False,
#                 description="Image facultative liée à la commande"
#             ),
#         ],
#         responses={
#             201: openapi.Response(description="✅ Commande créée avec succès."),
#             400: openapi.Response(description="❌ Requête invalide."),
#             500: openapi.Response(description="💥 Erreur serveur."),
#         }
#     )
#     @transaction.atomic
#     def post(self, request):
#         try:
#             data = request.data

#             client_raw = data.get("client")
#             produits_raw = data.get("produits")

#             if not client_raw:
#                 return Response({"error": "Le champ client est requis."}, status=400)
#             if not produits_raw:
#                 return Response({"error": "Le champ produits est requis."}, status=400)

#             try:
#                 client_data = json.loads(client_raw)
#                 produits_data = json.loads(produits_raw)
#             except json.JSONDecodeError:
#                 return Response({"error": "Format JSON invalide pour client ou produits."}, status=400)

#             telephone = client_data.get("telephone", "").strip()
#             if not telephone:
#                 return Response({"error": "Le numéro de téléphone du client est requis."}, status=400)

#             client, _ = Client.objects.get_or_create(
#                 telephone=telephone,
#                 defaults={
#                     "nom": client_data.get("nom", ""),
#                     "prenom": client_data.get("prenom", "")
#                 }
#             )

#             image = request.FILES.get("image")
#             commentaire = data.get("commentaire")

#             commande = CommandeClient.objects.create(
#                 client=client,
#                 created_by=request.user,
#                 commentaire=commentaire,
#                 image=image
#             )

#             # for produit_data in produits_data:
#             #     produit_data["commande_client"] = commande.id
#             #     serializer = CommandeProduitClientSerializer(data=produit_data)
#             #     serializer.is_valid(raise_exception=True)
#             #     serializer.save()
            
#             for produit_data in produits_data:
#                 produit_data["commande_client"] = commande.id

#                 try:
#                     poids = Decimal(str(produit_data.get("poids")))
#                     prix_gramme = Decimal(str(produit_data.get("prix_gramme")))
#                     if poids is None or prix_gramme is None:
#                         raise ValueError("poids ou prix_gramme manquant.")
#                     prix_prevue = poids * prix_gramme
#                 except (InvalidOperation, ValueError, TypeError):
#                     raise ValidationError("Impossible de calculer prix_prevue : poids ou prix_gramme invalide.")

#                 produit_data["prix_prevue"] = prix_prevue

#                 serializer = CommandeProduitClientSerializer(data=produit_data)
#                 serializer.is_valid(raise_exception=True)
#                 serializer.save()
            
#             # 💰 Calcul du montant total prévu
#             montant_total = sum([
#                 Decimal(p.get("prix_prevue", 0)) * int(p.get("quantite", 1))
#                 for p in produits_data
#             ])

#             # 📦 Création du bon de commande avec numéro égal à la commande
#             bon_command = BonCommande.objects.create(
#                 commande=commande,
#                 numero_bon=commande.numero_commande,
#                 montant_total=montant_total,
#                 acompte=Decimal("0")  # tu pourras permettre de fournir un acompte plus tard si nécessaire
#             )

#             return Response({
#                 "message": "✅ Commande créée avec succès.",
#                 "commande": CommandeClientSerializer(commande, context={"request": request}).data
#             }, status=201)

#         except Exception as e:
#             transaction.set_rollback(True)
#             return Response({"error": str(e)}, status=500)


class CreateCommandeClientView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @swagger_auto_schema(
        operation_summary="Créer une commande client",
        operation_description="""Créer une commande avec des produits personnalisés ou officiels.
                            Le client est créé automatiquement si le téléphone est nouveau.
                            Commande avec acompte
                                1.Création d’une CommandeClient → statut en_attente_acompte
                                2.Paiement partiel → création d’une Facture(type='acompte')
                                3.Livraison → paiement final → création Facture(type='finale')
                                4.La facture finale peut déduire automatiquement l’acompte

                                """,
        manual_parameters=[
            openapi.Parameter(
                name="client",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_STRING,
                description="Objet JSON : {nom, prenom, telephone}"
            ),
            openapi.Parameter(
                name="produits",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_STRING,
                description=(
                    "Liste JSON des produits. Les champs 'prix_prevue', 'sous_total' et 'montant_total' sont calculés automatiquement. "
                    'Exemple : [{"categorie": "Bague", "marque": "local", "modele": "Alliance Homme Or Jaune", "purete":18, "poids": 3.5, "quantite": 1, "prix_gramme": 5500, "personnalise": true, "matiere": "or", "genre: "F"}]'
                )
            ),
            openapi.Parameter(
                name="commentaire",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_STRING,
                required=False,
                description="Commentaire de la commande (facultatif)"
            ),
            openapi.Parameter(
                name="image",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_FILE,
                required=False,
                description="Image facultative liée à la commande"
            ),
        ],
        responses={
            201: openapi.Response(description="✅ Commande créée avec succès."),
            400: openapi.Response(description="❌ Requête invalide."),
            500: openapi.Response(description="💥 Erreur serveur."),
        }
    )
    @transaction.atomic
    def post(self, request):
        try:
            data = request.data

            client_raw = data.get("client")
            produits_raw = data.get("produits")

            if not client_raw:
                return Response({"error": "Le champ client est requis."}, status=400)
            if not produits_raw:
                return Response({"error": "Le champ produits est requis."}, status=400)

            try:
                client_data = json.loads(client_raw)
                produits_data = json.loads(produits_raw)
            except json.JSONDecodeError:
                return Response({"error": "Format JSON invalide pour client ou produits."}, status=400)

            telephone = client_data.get("telephone", "").strip()
            if not telephone:
                return Response({"error": "Le numéro de téléphone du client est requis."}, status=400)

            client, _ = Client.objects.get_or_create(
                telephone=telephone,
                defaults={
                    "nom": client_data.get("nom", ""),
                    "prenom": client_data.get("prenom", "")
                }
            )

            image = request.FILES.get("image")
            commentaire = data.get("commentaire")

            commande = CommandeClient.objects.create(
                client=client,
                created_by=request.user,
                commentaire=commentaire,
                image=image
            )

            montant_total = Decimal("0")

            for produit_data in produits_data:
                produit_data["commande_client"] = commande.id

                try:
                    poids = Decimal(str(produit_data.get("poids")))
                    prix_gramme = Decimal(str(produit_data.get("prix_gramme")))
                    prix_prevue = poids * prix_gramme
                except (InvalidOperation, TypeError, ValueError):
                    raise ValidationError("Impossible de calculer 'prix_prevue' : poids ou prix_gramme invalide.")

                produit_data["prix_prevue"] = prix_prevue

                serializer = CommandeProduitClientSerializer(data=produit_data)
                serializer.is_valid(raise_exception=True)
                produit_instance = serializer.save()

                montant_total += produit_instance.sous_total

            BonCommande.objects.create(
                commande=commande,
                numero_bon=commande.numero_commande,
                montant_total=montant_total,
                acompte=Decimal("0")
            )

            return Response({
                "message": "✅ Commande créée avec succès.",
                "commande": CommandeClientSerializer(commande, context={"request": request}).data
            }, status=201)

        except ValidationError as e:
            transaction.set_rollback(True)
            return Response({"error": e.detail if hasattr(e, "detail") else str(e)}, status=400)

        except Exception as e:
            transaction.set_rollback(True)
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


class PaiementAcompteBonCommandeView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Mettre à jour l'acompte d’un bon de commande",
        operation_description="Met à jour le montant de l’acompte versé, recalcule le reste à payer, et ajuste le statut de la commande (en_attente_acompte, en_attente, payee).",
        manual_parameters=[
            openapi.Parameter(
                'numero_bon', openapi.IN_PATH,
                type=openapi.TYPE_STRING,
                required=True,
                description="Numéro du bon de commande (même que la commande)"
            )
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["acompte"],
            properties={
                "acompte": openapi.Schema(
                    type=openapi.TYPE_NUMBER,
                    format='decimal',
                    description="Nouveau montant de l’acompte versé"
                )
            }
        ),
        responses={
            200: openapi.Response("✅ Acompte mis à jour avec succès."),
            400: "Données invalides",
            404: "Bon de commande introuvable",
        }
    )
    def patch(self, request, numero_bon):
        acompte_str = request.data.get("acompte")
        if acompte_str is None:
            return Response({"error": "Le champ 'acompte' est requis."}, status=400)

        try:
            acompte = Decimal(str(acompte_str))
            if acompte < 0:
                return Response({"error": "L’acompte ne peut pas être négatif."}, status=400)
        except:
            return Response({"error": "Montant d’acompte invalide."}, status=400)

        try:
            bon = BonCommande.objects.select_related("commande").get(numero_bon=numero_bon)
        except BonCommande.DoesNotExist:
            return Response({"error": "Bon de commande introuvable."}, status=404)

        if acompte > bon.montant_total:
            return Response({
                "error": f"L’acompte ({acompte}) ne peut pas dépasser le montant total ({bon.montant_total})."
            }, status=400)

        # ✅ Mise à jour des montants
        bon.acompte = acompte
        bon.reste_a_payer = bon.montant_total - acompte
        bon.save()

        # ✅ Mise à jour du statut selon les règles
        commande = bon.commande
        seuil_moitie = bon.montant_total / Decimal("2")

        if acompte == bon.montant_total:
            commande.statut = CommandeClient.STATUT_PAYEE
        elif acompte >= seuil_moitie:
            commande.statut = CommandeClient.STATUT_EN_ATTENTE
        else:
            commande.statut = CommandeClient.STATUT_EN_ATTENTE_ACOMPTE
        commande.save()

        return Response({
            "message": "✅ Acompte mis à jour avec succès.",
            "numero_bon": bon.numero_bon,
            "montant_total": str(bon.montant_total),
            "acompte": str(bon.acompte),
            "reste_a_payer": str(bon.reste_a_payer),
            "statut_commande": commande.statut,
        }, status=200)


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
