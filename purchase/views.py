from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from openpyxl import Workbook
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.mixins import ExportXlsxMixin
from backend.permissions import IsAdminOrManager
from backend.renderers import UserRenderer
from inventory.models import Bucket, InventoryMovement, MovementType
from stock.models import Stock
from store.models import Produit

from .models import Achat, Fournisseur, Lot, ProduitLine
from .serializers import (AchatDetailSerializer, AchatSerializer,
                          ArrivageAdjustmentsInSerializer,
                          ArrivageCreateInSerializer,
                          ArrivageCreateResponseSerializer,
                          ArrivageMetaUpdateInSerializer,
                          FournisseurSerializer, LotDisplaySerializer,
                          LotListSerializer, ProduitLineMiniSerializer)
from .utils import recalc_totaux_achat


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


class AchatProduitGetOneView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAdminOrManager]

    @swagger_auto_schema(
        operation_description="Récupère un achat spécifique avec ses lots et produits associés.",
        responses={
            200: openapi.Response("Achat trouvé", AchatDetailSerializer),
            404: "Achat non trouvé",
            403: "Accès refusé"
        },
        tags=["Achats / Arrivages"],
    )
    @transaction.atomic
    def get(self, request, pk):
        user_role = getattr(request.user.user_role, 'role', None)
        if user_role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        try:
            achat = (
                Achat.objects
                .select_related('fournisseur')
                .prefetch_related(
                    "lots",                  # tous les lots
                    "lots__lignes",          # lignes de chaque lot
                    "lots__lignes__produit", # produit de chaque ligne
                )
                .get(pk=pk)
            )
        except Achat.DoesNotExist:
            return Response({"detail": "Achat not found."}, status=404)
        except Exception as e:
            return Response({"detail": f"Erreur interne : {str(e)}"}, status=500)

        serializer = AchatDetailSerializer(achat)
        return Response(serializer.data, status=200)


class LotDetailView(RetrieveAPIView):
    """
    Détail d’un lot dans un format “affichage” :
    - fournisseur
    - frais
    - numéro de lot
    - lignes produits (produit_id, quantite, prix_achat_gramme)
    """
    queryset = (
        Lot.objects
        .select_related("achat", "achat__fournisseur")
        .prefetch_related("lignes__produit")
    )
    serializer_class = LotDisplaySerializer
    permission_classes = [IsAuthenticated, IsAdminOrManager]
    lookup_field = "pk"  # facultatif, c’est le défaut

    @swagger_auto_schema(
        operation_id="Details_lot",
        operation_summary="Détail d’un lot (format affichage personnalisé)",
        tags=["Achats / Arrivages"],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)




def generate_numero_lot() -> str:
    """Génère LOT-YYYYMMDD-XXXX ; XXXX repart à 0001 chaque jour."""
    today = timezone.localdate().strftime("%Y%m%d")
    prefix = f"LOT-{today}-"
    last = (
        Lot.objects
        .filter(numero_lot__startswith=prefix)
        .order_by("-numero_lot")
        .values_list("numero_lot", flat=True)
        .first()
    )
    if last:
        try:
            seq = int(last.rsplit("-", 1)[-1]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"


# class ArrivageCreateView(APIView):
#     """
#     Version 1 ACHAT → N LOTS (réceptions partielles possibles)

#     - Crée 1 Achat (fournisseur + frais)
#     - Crée N Lots rattachés à cet achat, chacun avec numero_lot auto (LOT-YYYYMMDD-XXXX)
#     - Crée les ProduitLine (quantité achetée, prix_achat_gramme) pour chaque lot
#     - Pousse 100% de la quantité en stock "Réserve" (Stock bijouterie=None) par ProduitLine
#     - Crée un mouvement d’inventaire PURCHASE_IN (EXTERNAL -> RESERVED) par ligne
#     - Calcule montant_total_ht et montant_total_ttc via achat.update_total()
    
#     - payload JSON complet pour un achat avec 3 produits différents
#     {
#     "fournisseur": {
#         "nom": "DIALLO",
#         "prenom": "Mamadou",
#         "telephone": "771234567"
#     },
#     "description": "Commande bijoux or 18k – livraison complète",
#     "frais_transport": 15000.00,
#     "frais_douane": 5000.00,
#     "lots": [
#         {
#         "received_at": "2026-01-30T10:30:00Z",
#         "description": "Livraison principale",
#         "lignes": [
#             {
#             "produit_id": 12,
#             "quantite": 5,
#             "prix_achat_gramme": 42000.00
#             },
#             {
#             "produit_id": 18,
#             "quantite": 3,
#             "prix_achat_gramme": 41500.00
#             },
#             {
#             "produit_id": 25,
#             "quantite": 2,
#             "prix_achat_gramme": 43000.00
#             }
#         ]
#         }
#     ]
#     }
    
    
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManager]
#     http_method_names = ["post"]

#     @swagger_auto_schema(
#         operation_id="createArrivage",
#         operation_summary="Créer un arrivage (1 achat → N lots) et initialiser l’inventaire",
#         operation_description=(
#             "Crée un **Achat** puis crée **N Lots** rattachés à cet achat (réceptions partielles).\n\n"
#             "Pour chaque lot :\n"
#             "- Génère un `numero_lot` auto (LOT-YYYYMMDD-XXXX)\n"
#             "- Crée les `ProduitLine` (quantité, prix_achat_gramme)\n"
#             "- Ajoute 100% du stock en **Réserve** (Stock.bijouterie = null)\n"
#             "- Crée un mouvement d’inventaire **PURCHASE_IN** (EXTERNAL → RESERVED) par ligne\n\n"
#             "Enfin, recalcule les totaux de l’achat via `achat.update_total()`.\n"
#         ),
#         request_body=ArrivageCreateInSerializer,
#         responses={
#             201: openapi.Response(
#                 description="Arrivage créé (achat + lots + lignes)",
#                 schema=ArrivageCreateResponseSerializer,
#             ),
#             400: openapi.Response(description="Bad Request (validation payload / produits / lots)"),
#             401: openapi.Response(description="Unauthorized"),
#             403: openapi.Response(description="Forbidden"),
#         },
#         tags=["Achats / Arrivages"],
#     )
#     @transaction.atomic
#     def post(self, request):
#         # ---------- Validation du payload ----------
#         s = ArrivageCreateInSerializer(data=request.data)
#         s.is_valid(raise_exception=True)
#         v = s.validated_data

#         lots_in = v["lots"]
#         if not lots_in:
#             return Response({"lots": "Au moins un lot est requis."}, status=400)

#         # ---------- Collecte de tous les produit_id (tous lots/lignes) ----------
#         pids = set()
#         for lot_in in lots_in:
#             lignes = lot_in.get("lignes") or []
#             for row in lignes:
#                 pids.add(row["produit_id"])

#         if not pids:
#             return Response({"lots": "Au moins une ligne produit est requise."}, status=400)

#         # ---------- Validation produits existants ----------
#         exists = set(Produit.objects.filter(id__in=pids).values_list("id", flat=True))
#         missing = pids - exists
#         if missing:
#             return Response(
#                 {"lots": f"Produit(s) introuvable(s): {sorted(missing)}."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         # On exige un poids pour chaque produit
#         missing_weight = list(
#             Produit.objects.filter(id__in=pids, poids__isnull=True).values_list("id", flat=True)
#         )
#         if missing_weight:
#             return Response(
#                 {"lots": f"Produit(s) sans poids: {sorted(missing_weight)}."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         # Cache produits
#         produits_by_id = {
#             p.id: p for p in Produit.objects.filter(id__in=pids).only("id", "poids", "nom")
#         }

#         # ---------- Fournisseur ----------
#         f = v["fournisseur"]
#         tel = (f.get("telephone") or "").strip() or None

#         if tel:
#             # ✅ évite collision NULL / améliore mise à jour des infos
#             fournisseur, _ = Fournisseur.objects.update_or_create(
#                 telephone=tel,
#                 defaults={"nom": f["nom"], "prenom": f.get("prenom", "")},
#             )
#         else:
#             # Pas de téléphone → on crée un nouveau fournisseur
#             fournisseur = Fournisseur.objects.create(
#                 nom=f["nom"], prenom=f.get("prenom", ""), telephone=None
#             )

#         # ---------- Achat ----------
#         now = timezone.now()
#         frais_transport = v.get("frais_transport") or Decimal("0.00")
#         frais_douane = v.get("frais_douane") or Decimal("0.00")

#         achat = Achat.objects.create(
#             fournisseur=fournisseur,
#             reference_commande=v.get("reference_commande"),
#             description=v.get("description", ""),
#             frais_transport=frais_transport,
#             frais_douane=frais_douane,
#             status=Achat.STATUS_CONFIRMED,
#         )

#         # ---------- Création lots + lignes + stock + mouvements ----------
#         lots_created = []

#         for lot_in in lots_in:
#             lot_desc = lot_in.get("description") or v.get("description", "") or ""
#             received_at = lot_in.get("received_at") or now
#             lignes_in = lot_in.get("lignes") or []

#             if not lignes_in:
#                 return Response(
#                     {"lots": "Chaque lot doit contenir au moins une ligne."},
#                     status=status.HTTP_400_BAD_REQUEST,
#                 )

#             # Générer numero_lot (retry collision)
#             lot = None
#             for _ in range(5):
#                 numero_lot = generate_numero_lot()
#                 try:
#                     lot = Lot.objects.create(
#                         achat=achat,
#                         numero_lot=numero_lot,
#                         description=lot_desc,
#                         received_at=received_at,
#                     )
#                     break
#                 except IntegrityError:
#                     continue
#             if lot is None:
#                 return Response(
#                     {"detail": "Impossible de générer un numéro de lot unique."},
#                     status=status.HTTP_400_BAD_REQUEST,
#                 )

#             # lignes du lot
#             for row in lignes_in:
#                 produit = produits_by_id[row["produit_id"]]

#                 # Quantité
#                 try:
#                     qte = int(row["quantite"])
#                 except (TypeError, ValueError):
#                     return Response({"lots": "Quantité invalide."}, status=400)

#                 if qte < 1:
#                     return Response({"lots": "Quantité doit être >= 1."}, status=400)

#                 prix_achat_gramme = row.get("prix_achat_gramme")

#                 # ProduitLine
#                 pl = ProduitLine.objects.create(
#                     lot=lot,
#                     produit=produit,
#                     prix_achat_gramme=prix_achat_gramme,
#                     quantite=qte,
#                 )

#                 # # Stock en Réserve (bijouterie=None)
#                 # stock_reserve, created = Stock.objects.get_or_create(
#                 #     produit_line=pl,
#                 #     bijouterie=None,
#                 #     defaults={"quantite_disponible": 0, "en_stock": qte},
#                 # )
                
                
#                 if not created:
#                     # verrou row + update atomique
#                     Stock.objects.select_for_update().filter(id=stock_reserve.id)
#                     Stock.objects.filter(id=stock_reserve.id).update(
#                         quantite_disponible=0,
#                         en_stock=F("en_stock") + qte,
#                         updated_at=timezone.now(),
#                     )

#                 # unit_cost (coût unitaire pièce)
#                 unit_cost = None
#                 if prix_achat_gramme is not None and produit.poids is not None:
#                     try:
#                         unit_cost = (
#                             Decimal(str(prix_achat_gramme)) * Decimal(str(produit.poids))
#                         ).quantize(Decimal("0.01"))
#                     except (InvalidOperation, TypeError, ValueError):
#                         unit_cost = None

#                 # mouvement inventaire
#                 InventoryMovement.objects.create(
#                     produit=produit,
#                     movement_type=MovementType.PURCHASE_IN,
#                     qty=qte,
#                     unit_cost=unit_cost,
#                     lot=lot,
#                     reason="Arrivage initial",
#                     src_bucket=Bucket.EXTERNAL,
#                     dst_bucket=Bucket.RESERVED,
#                     achat=achat,
#                     occurred_at=timezone.now(),
#                     created_by=request.user,
#                 )

#             lots_created.append(lot)
#         # ---------- CALCUL FINAL HT / TTC ----------
#         # ---------- Totaux achat ----------
#         # achat.montant_total_ht = base_ht + frais_transport + frais_douane
#         # achat.montant_total_ttc = achat.montant_total_ht  # pas de TVA pour l'instant
#         # achat.save(update_fields=["montant_total_ht", "montant_total_ttc"])
#         achat.update_total(save=True)
        
        
#         # ---------- Réponse ----------
#         # ✅ Si ton serializer de réponse est centré Achat: renvoie achat.
#         # Si tu veux renvoyer aussi la liste des lots créés, on peut faire un serializer dédié.
#         lots_qs = (
#             Lot.objects
#             .filter(id__in=[l.id for l in lots_created])
#             .select_related("achat", "achat__fournisseur")
#             .prefetch_related("lignes__produit")
#             .order_by("received_at", "id")
#         )

#         payload = {"achat": achat, "lots": list(lots_qs)}
#         out = ArrivageCreateResponseSerializer(payload).data
#         return Response(out, status=status.HTTP_201_CREATED)


class ArrivageCreateView(APIView):
    """
    Version 1 ACHAT → N LOTS (réceptions partielles possibles)

    - Crée 1 Achat (fournisseur + frais)
    - Crée N Lots rattachés à cet achat
    - Crée les ProduitLine (quantite, prix_achat_gramme) pour chaque lot
    - Stocke 100% en Réserve (Stock.bijouterie=None) par ProduitLine
      ✅ règle DB: quantite_totale >= en_stock
    - Crée un mouvement PURCHASE_IN (EXTERNAL -> RESERVED) par ligne
    - Recalcule les totaux via achat.update_total()
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]
    http_method_names = ["post"]

    @swagger_auto_schema(
        operation_id="createArrivage",
        operation_summary="Créer un arrivage (1 achat → N lots) et initialiser l’inventaire",
        request_body=ArrivageCreateInSerializer,
        responses={
            201: openapi.Response("Arrivage créé", schema=ArrivageCreateResponseSerializer),
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
        },
        tags=["Achats / Arrivages"],
    )
    @transaction.atomic
    def post(self, request):
        s = ArrivageCreateInSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        lots_in = v.get("lots") or []
        if not lots_in:
            return Response({"lots": "Au moins un lot est requis."}, status=400)

        # -------- Collecte produit_id --------
        pids = set()
        for lot_in in lots_in:
            for row in (lot_in.get("lignes") or []):
                pids.add(row["produit_id"])

        if not pids:
            return Response({"lots": "Au moins une ligne produit est requise."}, status=400)

        # -------- Validation produits --------
        exists = set(Produit.objects.filter(id__in=pids).values_list("id", flat=True))
        missing = pids - exists
        if missing:
            return Response({"lots": f"Produit(s) introuvable(s): {sorted(missing)}."}, status=400)

        # poids obligatoire (si tu en as besoin ailleurs)
        missing_weight = list(
            Produit.objects.filter(id__in=pids, poids__isnull=True).values_list("id", flat=True)
        )
        if missing_weight:
            return Response({"lots": f"Produit(s) sans poids: {sorted(missing_weight)}."}, status=400)

        produits_by_id = {
            p.id: p for p in Produit.objects.filter(id__in=pids).only("id", "poids", "nom")
        }

        # -------- Fournisseur --------
        f = v["fournisseur"]
        tel = (f.get("telephone") or "").strip() or None

        if tel:
            fournisseur, _ = Fournisseur.objects.update_or_create(
                telephone=tel,
                defaults={"nom": f["nom"], "prenom": f.get("prenom", "")},
            )
        else:
            fournisseur = Fournisseur.objects.create(
                nom=f["nom"], prenom=f.get("prenom", ""), telephone=None
            )

        # -------- Achat --------
        now = timezone.now()
        achat = Achat.objects.create(
            fournisseur=fournisseur,
            reference_commande=v.get("reference_commande"),
            description=v.get("description", ""),
            frais_transport=v.get("frais_transport") or Decimal("0.00"),
            frais_douane=v.get("frais_douane") or Decimal("0.00"),
            status=Achat.STATUS_CONFIRMED,
        )

        lots_created = []

        # -------- Lots + lignes + stock + mouvements --------
        for lot_in in lots_in:
            lot_desc = lot_in.get("description") or v.get("description", "") or ""
            received_at = lot_in.get("received_at") or now
            lignes_in = lot_in.get("lignes") or []

            if not lignes_in:
                return Response({"lots": "Chaque lot doit contenir au moins une ligne."}, status=400)

            lot = None
            for _ in range(5):
                try:
                    lot = Lot.objects.create(
                        achat=achat,
                        numero_lot=generate_numero_lot(),
                        description=lot_desc,
                        received_at=received_at,
                    )
                    break
                except IntegrityError:
                    continue
            if lot is None:
                return Response({"detail": "Impossible de générer un numéro de lot unique."}, status=400)

            for row in lignes_in:
                produit = produits_by_id[row["produit_id"]]

                try:
                    qte = int(row["quantite"])
                except (TypeError, ValueError):
                    return Response({"lots": "Quantité invalide."}, status=400)
                if qte < 1:
                    return Response({"lots": "Quantité doit être >= 1."}, status=400)

                prix_achat_gramme = row.get("prix_achat_gramme")

                pl = ProduitLine.objects.create(
                    lot=lot,
                    produit=produit,
                    prix_achat_gramme=prix_achat_gramme,
                    quantite=qte,
                )

                # ✅ STOCK RÉSERVE: quantite_totale >= en_stock (on incrémente les deux)
                stock_reserve, created = Stock.objects.get_or_create(
                    produit_line=pl,
                    bijouterie=None,
                    defaults={"quantite_totale": qte, "en_stock": qte},
                )
                if not created:
                    # lock réel (optionnel, mais propre)
                    Stock.objects.select_for_update().get(pk=stock_reserve.pk)

                    Stock.objects.filter(pk=stock_reserve.pk).update(
                        quantite_totale=F("quantite_totale") + qte,
                        en_stock=F("en_stock") + qte,
                        updated_at=timezone.now(),
                    )

                # ✅ unit_cost = PRIX PAR GRAMME (comme tu l’as dit)
                unit_cost = None
                if prix_achat_gramme is not None:
                    try:
                        unit_cost = Decimal(str(prix_achat_gramme)).quantize(Decimal("0.01"))
                    except (InvalidOperation, TypeError, ValueError):
                        unit_cost = None

                InventoryMovement.objects.create(
                    produit=produit,
                    movement_type=MovementType.PURCHASE_IN,
                    qty=qte,
                    unit_cost=unit_cost,      # ✅ prix/gramme
                    lot=lot,
                    reason="Arrivage initial",
                    src_bucket=Bucket.EXTERNAL,
                    dst_bucket=Bucket.RESERVED,
                    achat=achat,
                    achat_ligne=pl,            # ✅ bonus: trace la ligne d'achat
                    occurred_at=timezone.now(),
                    created_by=request.user,
                )

            lots_created.append(lot)

        # -------- Totaux --------
        achat.update_total(save=True)

        # -------- Réponse --------
        # lots_qs = (
        #     Lot.objects
        #     .filter(id__in=[l.id for l in lots_created])
        #     .select_related("achat", "achat__fournisseur")
        #     .prefetch_related("lignes__produit")
        #     .order_by("received_at", "id")
        # )
        # out = ArrivageCreateResponseSerializer({"achat": achat, "lots": list(lots_qs)}).data
        out = ArrivageCreateResponseSerializer({"achat": achat,}).data
        return Response(out, status=201)



# class LotListView(ListAPIView):
#     """
#     Liste des lots :
#     - par défaut : année courante (sur received_at)
#     - si date_from & date_to sont fournis : intervalle [date_from, date_to] (inclus)
#     Filtres optionnels :
#     - reference_commande (icontains)
#     - numero_lot (icontains)
#     - numero_achat (exact)
#     - fournisseur_id
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManager]
#     serializer_class = LotListSerializer

#     @swagger_auto_schema(
#         operation_id="listLots",
#         operation_summary="Lister les lots avec filtres",
#         operation_description=(
#             "• Si `date_from` **et** `date_to` sont fournis → filtre inclusif sur `received_at`.\n"
#             "• Sinon → lots de l’**année courante** (received_at).\n\n"
#             "Filtres supplémentaires :\n"
#             "- `reference_commande` (recherche partielle, icontains)\n"
#             "- `numero_lot` (recherche partielle, icontains)\n"
#             "- `numero_achat` (exact)\n"
#             "- `fournisseur_id` (id du fournisseur de l'achat)\n\n"
#             "Formats de date : `YYYY-MM-DD`."
#         ),
#         manual_parameters=[
#             openapi.Parameter(
#                 "reference_commande",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Recherche partielle sur la référence commande (icontains).",
#             ),
#             openapi.Parameter(
#                 "date_from",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Borne min incluse sur received_at (YYYY-MM-DD). Avec date_to.",
#             ),
#             openapi.Parameter(
#                 "date_to",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Borne max incluse sur received_at (YYYY-MM-DD). Avec date_from.",
#             ),
#             openapi.Parameter(
#                 "numero_lot",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Recherche partielle sur le numéro de lot (icontains).",
#             ),
#             openapi.Parameter(
#                 "numero_achat",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Filtre exact sur le numéro d'achat.",
#             ),
#             openapi.Parameter(
#                 "fournisseur_id",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_INTEGER,
#                 description="Filtre sur l'id du fournisseur.",
#             ),
#             openapi.Parameter(
#                 "ordering",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Tri: -received_at (défaut), received_at, numero_lot, -numero_lot",
#             ),
#         ],
#         responses={200: LotListSerializer(many=True)},
#         tags=["Achats / Arrivages"],
#     )
#     def get(self, request, *args, **kwargs):
#         def _check_date(label, val):
#             if not val:
#                 return
#             try:
#                 datetime.strptime(val, "%Y-%m-%d").date()
#             except Exception:
#                 raise ValidationError({label: "Format invalide. Utiliser YYYY-MM-DD."})

#         qp = request.query_params
#         _check_date("date_from", qp.get("date_from"))
#         _check_date("date_to", qp.get("date_to"))

#         # si un seul des deux est fourni → on force la règle
#         if (qp.get("date_from") and not qp.get("date_to")) or (qp.get("date_to") and not qp.get("date_from")):
#             raise ValidationError({"detail": "Fournir date_from ET date_to ensemble."})

#         return super().get(request, *args, **kwargs)

#     def get_queryset(self):
#         params = self.request.query_params
#         getf = params.get

#         # --------- Tri ---------
#         ordering = getf("ordering") or "-received_at"
#         allowed = {"received_at", "-received_at", "numero_lot", "-numero_lot"}
#         if ordering not in allowed:
#             ordering = "-received_at"

#         # --------- Base queryset + agrégats ---------
#         qs = (
#             Lot.objects
#             .select_related("achat", "achat__fournisseur")
#             .prefetch_related(
#                 "lignes",
#                 "lignes__produit",
#                 "lignes__produit__categorie",
#                 "lignes__produit__marque",
#             )
#             .annotate(
#                 nb_lignes=Coalesce(Count("lignes", distinct=True), 0),
#                 quantite_total=Coalesce(Sum("lignes__quantite"), 0),
#             )
#         )

#         # --------- Filtre par dates (sur received_at) ---------
#         date_from_s = getf("date_from")
#         date_to_s = getf("date_to")

#         if date_from_s and date_to_s:
#             df = datetime.strptime(date_from_s, "%Y-%m-%d").date()
#             dt = datetime.strptime(date_to_s, "%Y-%m-%d").date()
#             if df > dt:
#                 raise ValidationError({"detail": "date_from doit être ≤ date_to."})
#             qs = qs.filter(received_at__date__gte=df, received_at__date__lte=dt)
#         else:
#             # année courante sur received_at
#             y = timezone.localdate().year
#             qs = qs.filter(received_at__year=y)

#         # --------- Autres filtres ---------
#         reference_commande = getf("reference_commande")
#         if reference_commande:
#             qs = qs.filter(achat__reference_commande__icontains=reference_commande)

#         numero_lot = getf("numero_lot")
#         if numero_lot:
#             qs = qs.filter(numero_lot__icontains=numero_lot)

#         numero_achat = getf("numero_achat")
#         if numero_achat:
#             qs = qs.filter(achat__numero_achat=numero_achat)

#         fournisseur_id = getf("fournisseur_id")
#         if fournisseur_id:
#             try:
#                 fid = int(fournisseur_id)
#                 if fid > 0:
#                     qs = qs.filter(achat__fournisseur_id=fid)
#             except ValueError:
#                 # on ignore un id non entier plutôt que lever une 500
#                 pass

#         return qs.order_by(ordering)


class LotListView(ListAPIView):
    """
    Liste des lots :
    - si date_from & date_to : intervalle inclusif sur received_at__date
    - sinon : filtre par year (si fourni) sinon année courante

    Filtres optionnels :
    - year (int)
    - reference_commande (icontains)
    - numero_lot (icontains)
    - numero_achat (exact)
    - fournisseur_id
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]
    serializer_class = LotListSerializer

    @swagger_auto_schema(
        operation_id="listLots",
        operation_summary="Lister les lots avec filtres",
        operation_description=(
            "Priorité au filtre par dates :\n"
            "• Si `date_from` **et** `date_to` sont fournis → filtre inclusif sur `received_at`.\n"
            "• Sinon → filtre par `year` (si fourni), sinon année courante.\n\n"
            "Formats : date `YYYY-MM-DD`, year `YYYY`."
            "Exemples d’appels :"
                " • Lots de 2026 : GET /api/lots/?year=2026"
                " • Lots entre deux dates : GET /api/lots/?date_from=2026-01-01&date_to=2026-01-31"
                " • Recherche commande : GET /api/lots/?reference_commande=CMD-2026"
        ),
        manual_parameters=[
            openapi.Parameter("year", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="Année sur received_at (ex: 2026). Ignoré si date_from/date_to."),
            openapi.Parameter("reference_commande", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Recherche partielle (icontains) sur la référence commande."),
            openapi.Parameter("date_from", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Borne min incluse (YYYY-MM-DD). Avec date_to."),
            openapi.Parameter("date_to", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Borne max incluse (YYYY-MM-DD). Avec date_from."),
            openapi.Parameter("numero_lot", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Recherche partielle (icontains) sur le numéro de lot."),
            openapi.Parameter("numero_achat", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Filtre exact sur le numéro d'achat."),
            openapi.Parameter("fournisseur_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="Filtre sur l'id du fournisseur."),
            openapi.Parameter("ordering", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Tri: -received_at (défaut), received_at, numero_lot, -numero_lot"),
        ],
        responses={200: LotListSerializer(many=True)},
        tags=["Achats / Arrivages"],
    )
    def get(self, request, *args, **kwargs):
        def _check_date(label, val):
            if not val:
                return
            try:
                datetime.strptime(val, "%Y-%m-%d").date()
            except Exception:
                raise ValidationError({label: "Format invalide. Utiliser YYYY-MM-DD."})

        qp = request.query_params
        date_from = qp.get("date_from")
        date_to = qp.get("date_to")
        year = qp.get("year")

        _check_date("date_from", date_from)
        _check_date("date_to", date_to)

        # ✅ si un seul des deux est fourni
        if (date_from and not date_to) or (date_to and not date_from):
            raise ValidationError({"detail": "Fournir date_from ET date_to ensemble."})

        # ✅ year doit être int si fourni (on valide juste pour swagger/UX)
        if year:
            try:
                int(year)
            except ValueError:
                raise ValidationError({"year": "Année invalide. Exemple: 2026"})

        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        getf = self.request.query_params.get

        # --------- Tri ---------
        ordering = (getf("ordering") or "-received_at").strip()
        allowed = {"received_at", "-received_at", "numero_lot", "-numero_lot"}
        if ordering not in allowed:
            ordering = "-received_at"

        # --------- Base queryset + agrégats ---------
        qs = (
            Lot.objects
            .select_related("achat", "achat__fournisseur")
            .prefetch_related(
                "lignes",
                "lignes__produit",
                "lignes__produit__categorie",
                "lignes__produit__marque",
            )
            .annotate(
                nb_lignes=Coalesce(Count("lignes", distinct=True), 0),
                quantite_total=Coalesce(Sum("lignes__quantite"), 0),
            )
        )

        # --------- Filtre dates OU year ---------
        date_from_s = getf("date_from")
        date_to_s = getf("date_to")

        if date_from_s and date_to_s:
            df = datetime.strptime(date_from_s, "%Y-%m-%d").date()
            dt = datetime.strptime(date_to_s, "%Y-%m-%d").date()
            if df > dt:
                raise ValidationError({"detail": "date_from doit être ≤ date_to."})
            qs = qs.filter(received_at__date__gte=df, received_at__date__lte=dt)
        else:
            year_s = getf("year")
            if year_s:
                year = int(year_s)
            else:
                year = timezone.localdate().year
            qs = qs.filter(received_at__year=year)

        # --------- Autres filtres ---------
        reference_commande = (getf("reference_commande") or "").strip()
        if reference_commande:
            qs = qs.filter(achat__reference_commande__icontains=reference_commande)

        numero_lot = (getf("numero_lot") or "").strip()
        if numero_lot:
            qs = qs.filter(numero_lot__icontains=numero_lot)

        numero_achat = (getf("numero_achat") or "").strip()
        if numero_achat:
            qs = qs.filter(achat__numero_achat=numero_achat)

        fournisseur_id = getf("fournisseur_id")
        if fournisseur_id:
            try:
                fid = int(fournisseur_id)
                if fid > 0:
                    qs = qs.filter(achat__fournisseur_id=fid)
            except ValueError:
                pass

        return qs.order_by(ordering)



# class AchatListView(ListAPIView):
#     """
#     Liste des achats :
#     - par défaut : année courante (created_at)
#     - si date_from & date_to sont fournis : intervalle [date_from, date_to] (inclus)

#     Filtres optionnels :
#     - reference_commande (icontains)
#     - numero_achat (exact)
#     - fournisseur_id
#     - status
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManager]
#     serializer_class = AchatSerializer
#     # pagination_class = None

#     @swagger_auto_schema(
#         operation_id="listAchats",
#         operation_summary="Lister les achats (année courante par défaut, sinon entre deux dates)",
#         operation_description=(
#             "• Si `date_from` **et** `date_to` sont fournis → filtre inclusif sur `created_at__date`.\n"
#             "• Sinon → achats de l’**année courante**.\n\n"
#             "Filtres :\n"
#             "- `reference_commande` (recherche partielle, icontains)\n"
#             "- `numero_achat` (exact)\n"
#             "- `fournisseur_id`\n"
#             "- `status` (confirmed / cancelled)\n\n"
#             "Formats attendus : `YYYY-MM-DD`."
#         ),
#         manual_parameters=[
#             openapi.Parameter(
#                 "reference_commande",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Recherche partielle sur la référence commande (icontains).",
#             ),
#             openapi.Parameter(
#                 "numero_achat",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Filtre exact sur le numéro d'achat.",
#             ),
#             openapi.Parameter(
#                 "fournisseur_id",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_INTEGER,
#                 description="Filtre sur l'id du fournisseur.",
#             ),
#             openapi.Parameter(
#                 "status",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Filtre sur le status (confirmed / cancelled).",
#             ),
#             openapi.Parameter(
#                 "date_from",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Borne min incluse (YYYY-MM-DD). Utiliser avec `date_to`.",
#             ),
#             openapi.Parameter(
#                 "date_to",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Borne max incluse (YYYY-MM-DD). Utiliser avec `date_from`.",
#             ),
#             openapi.Parameter(
#                 "ordering",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Tri: -created_at (défaut), created_at, numero_achat, -numero_achat",
#             ),
#         ],
#         responses={200: AchatSerializer(many=True)},
#         tags=["Achats / Arrivages"],
#     )
#     def get(self, request, *args, **kwargs):
#         def _check_date(label, val):
#             if not val:
#                 return
#             try:
#                 datetime.strptime(val, "%Y-%m-%d").date()
#             except Exception:
#                 raise ValidationError({label: "Format invalide. Utiliser YYYY-MM-DD."})

#         qp = request.query_params
#         _check_date("date_from", qp.get("date_from"))
#         _check_date("date_to", qp.get("date_to"))

#         # ✅ impose date_from + date_to ensemble (évite ambiguïtés)
#         if (qp.get("date_from") and not qp.get("date_to")) or (qp.get("date_to") and not qp.get("date_from")):
#             raise ValidationError({"detail": "Fournir date_from ET date_to ensemble."})

#         return super().get(request, *args, **kwargs)

#     def get_queryset(self):
#         params = self.request.query_params
#         getf = params.get

#         # -------- Tri --------
#         ordering = getf("ordering") or "-created_at"
#         allowed = {"created_at", "-created_at", "numero_achat", "-numero_achat"}
#         if ordering not in allowed:
#             ordering = "-created_at"

#         # -------- Base queryset --------
#         qs = (
#             Achat.objects
#             .select_related("fournisseur")
#             .prefetch_related(
#                 "lots",
#                 "lots__lignes",
#                 "lots__lignes__produit",
#             )
#         )

#         # -------- Filtre dates --------
#         date_from_s = getf("date_from")
#         date_to_s = getf("date_to")

#         if date_from_s and date_to_s:
#             df = datetime.strptime(date_from_s, "%Y-%m-%d").date()
#             dt = datetime.strptime(date_to_s, "%Y-%m-%d").date()
#             if df > dt:
#                 raise ValidationError({"detail": "date_from doit être ≤ date_to."})
#             qs = qs.filter(created_at__date__gte=df, created_at__date__lte=dt)
#         else:
#             year = timezone.localdate().year
#             qs = qs.filter(created_at__year=year)

#         # -------- Filtres optionnels --------
#         reference_commande = getf("reference_commande")
#         if reference_commande:
#             qs = qs.filter(reference_commande__icontains=reference_commande)

#         numero_achat = getf("numero_achat")
#         if numero_achat:
#             qs = qs.filter(numero_achat=numero_achat)

#         fournisseur_id = getf("fournisseur_id")
#         if fournisseur_id:
#             try:
#                 fid = int(fournisseur_id)
#                 if fid > 0:
#                     qs = qs.filter(fournisseur_id=fid)
#             except ValueError:
#                 pass

#         status_ = getf("status")
#         if status_:
#             status_ = status_.strip().lower()
#             # ✅ sécurité : on accepte seulement les valeurs prévues
#             if status_ in {"confirmed", "cancelled"}:
#                 qs = qs.filter(status=status_)

#         return qs.order_by(ordering)


class AchatListView(ListAPIView):
    """
    Liste des achats :
    - si date_from & date_to : intervalle inclusif sur created_at__date
    - sinon : filtre par year (si fourni) sinon année courante

    Filtres optionnels :
    - year (int)
    - reference_commande (icontains)
    - numero_achat (exact)
    - fournisseur_id
    - status
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]
    serializer_class = AchatSerializer

    @swagger_auto_schema(
        operation_id="listAchats",
        operation_summary="Lister les achats (par année ou entre deux dates)",
        operation_description=(
            "Priorité au filtre par dates :\n"
            "• Si `date_from` **et** `date_to` sont fournis → filtre inclusif sur `created_at__date`.\n"
            "• Sinon → filtre par `year` (si fourni), sinon année courante.\n\n"
            "Filtres : reference_commande (icontains), numero_achat (exact), fournisseur_id, status.\n"
            "Formats : date `YYYY-MM-DD`, year `YYYY`."
        ),
        manual_parameters=[
            openapi.Parameter(
                "year", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                description="Année sur created_at (ex: 2026). Ignoré si date_from/date_to."
            ),
            openapi.Parameter(
                "reference_commande", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                description="Recherche partielle sur la référence commande (icontains)."
            ),
            openapi.Parameter(
                "numero_achat", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                description="Filtre exact sur le numéro d'achat."
            ),
            openapi.Parameter(
                "fournisseur_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                description="Filtre sur l'id du fournisseur."
            ),
            openapi.Parameter(
                "status", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                description="Filtre sur le status (ex: confirmed / cancelled)."
            ),
            openapi.Parameter(
                "date_from", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                description="Borne min incluse (YYYY-MM-DD). Utiliser avec date_to."
            ),
            openapi.Parameter(
                "date_to", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                description="Borne max incluse (YYYY-MM-DD). Utiliser avec date_from."
            ),
            openapi.Parameter(
                "ordering", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                description="Tri: -created_at (défaut), created_at, numero_achat, -numero_achat"
            ),
        ],
        responses={200: AchatSerializer(many=True)},
        tags=["Achats / Arrivages"],
    )
    def get(self, request, *args, **kwargs):
        def _check_date(label, val):
            if not val:
                return
            try:
                datetime.strptime(val, "%Y-%m-%d").date()
            except Exception:
                raise ValidationError({label: "Format invalide. Utiliser YYYY-MM-DD."})

        qp = request.query_params
        date_from = qp.get("date_from")
        date_to = qp.get("date_to")
        year = qp.get("year")

        _check_date("date_from", date_from)
        _check_date("date_to", date_to)

        # ✅ impose date_from + date_to ensemble
        if (date_from and not date_to) or (date_to and not date_from):
            raise ValidationError({"detail": "Fournir date_from ET date_to ensemble."})

        # ✅ year doit être int si fourni
        if year:
            try:
                int(year)
            except ValueError:
                raise ValidationError({"year": "Année invalide. Exemple: 2026"})

        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        getf = self.request.query_params.get

        # -------- Tri --------
        ordering = (getf("ordering") or "-created_at").strip()
        allowed = {"created_at", "-created_at", "numero_achat", "-numero_achat"}
        if ordering not in allowed:
            ordering = "-created_at"

        # -------- Base queryset --------
        qs = (
            Achat.objects
            .select_related("fournisseur")
            .prefetch_related(
                "lots",
                "lots__lignes",
                "lots__lignes__produit",
            )
        )

        # -------- Filtre dates OU year --------
        date_from_s = getf("date_from")
        date_to_s = getf("date_to")

        if date_from_s and date_to_s:
            df = datetime.strptime(date_from_s, "%Y-%m-%d").date()
            dt = datetime.strptime(date_to_s, "%Y-%m-%d").date()
            if df > dt:
                raise ValidationError({"detail": "date_from doit être ≤ date_to."})
            qs = qs.filter(created_at__date__gte=df, created_at__date__lte=dt)
        else:
            year_s = getf("year")
            year = int(year_s) if year_s else timezone.localdate().year
            qs = qs.filter(created_at__year=year)

        # -------- Filtres optionnels --------
        reference_commande = (getf("reference_commande") or "").strip()
        if reference_commande:
            qs = qs.filter(reference_commande__icontains=reference_commande)

        numero_achat = (getf("numero_achat") or "").strip()
        if numero_achat:
            qs = qs.filter(numero_achat=numero_achat)  # exact

        fournisseur_id = getf("fournisseur_id")
        if fournisseur_id:
            try:
                fid = int(fournisseur_id)
                if fid > 0:
                    qs = qs.filter(fournisseur_id=fid)
            except ValueError:
                pass

        status_ = (getf("status") or "").strip().lower()
        if status_:
            # ✅ adapte aux constantes si tu les as
            allowed_status = {"confirmed", "cancelled"}
            if status_ in allowed_status:
                qs = qs.filter(status=status_)

        return qs.order_by(ordering)



# class ArrivageMetaUpdateView(APIView):
#     """
#     PATCH /api/achat/arrivage/{lot_id}/meta/

#     Met à jour UNIQUEMENT les informations documentaires :
#     - côté Achat : description, frais_transport, frais_douane, fournisseur
#     - côté Lot   : description, received_at

#     ❌ Aucun impact sur le stock ou les mouvements d'inventaire.
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManager]
#     http_method_names = ["patch"]

#     @swagger_auto_schema(
#         operation_id="arrivageMetaUpdate",
#         operation_summary="Mettre à jour les métadonnées d’un arrivage (Achat + Lot)",
#         operation_description=(
#             "Permet de corriger / compléter les infos documentaires d’un arrivage :\n"
#             "- `achat`: description, frais_transport, frais_douane, fournisseur (ref ou upsert par téléphone)\n"
#             "- `lot`: description, received_at\n\n"
#             "Ne touche ni au stock ni aux mouvements d’inventaire."
#         ),
#         request_body=ArrivageMetaUpdateInSerializer,
#         responses={
#             200: AchatCreateResponseSerializer,
#             400: "Bad Request",
#             401: "Unauthorized",
#             403: "Forbidden",
#             404: "Not Found",
#         },
#         tags=["Achats / Arrivages"],
#         manual_parameters=[
#             openapi.Parameter(
#                 "lot_id",
#                 in_=openapi.IN_PATH,
#                 type=openapi.TYPE_INTEGER,
#                 description="ID du lot concerné",
#                 required=True,
#             ),
#         ],
#     )
#     @transaction.atomic
#     def patch(self, request, lot_id: int):
#         # ----- Récup lot + achat -----
#         lot = get_object_or_404(
#             Lot.objects.select_related("achat", "achat__fournisseur"),
#             pk=lot_id,
#         )
#         achat = lot.achat

#         # ----- Validation payload -----
#         s = ArrivageMetaUpdateInSerializer(data=request.data)
#         s.is_valid(raise_exception=True)
#         data = s.validated_data

#         # ====================
#         #  MAJ côté Achat
#         # ====================
#         achat_data = data.get("achat")
#         if achat_data:
#             # description
#             if "description" in achat_data:
#                 achat.description = achat_data.get("description") or ""

#             # frais
#             if "frais_transport" in achat_data:
#                 achat.frais_transport = achat_data["frais_transport"]
#             if "frais_douane" in achat_data:
#                 achat.frais_douane = achat_data["frais_douane"]

#             # fournisseur (ref / upsert)
#             fournisseur_data = achat_data.get("fournisseur")
#             if fournisseur_data:
#                 fournisseur_obj = None

#                 # 1) on privilégie l'id s'il est fourni
#                 fid = fournisseur_data.get("id")
#                 if fid:
#                     fournisseur_obj = get_object_or_404(Fournisseur, pk=fid)
#                 else:
#                     # 2) sinon upsert par téléphone
#                     tel = (fournisseur_data.get("telephone") or "").strip() or None
#                     if tel:
#                         fournisseur_obj, _ = Fournisseur.objects.get_or_create(
#                             telephone=tel,
#                             defaults={
#                                 "nom": fournisseur_data.get("nom") or "",
#                                 "prenom": fournisseur_data.get("prenom") or "",
#                                 "address": "",
#                             },
#                         )

#                 if fournisseur_obj:
#                     achat.fournisseur = fournisseur_obj

#             # on recalculera les totaux plus bas
#             achat.save()

#         # ====================
#         #  MAJ côté Lot
#         # ====================
#         lot_data = data.get("lot")
#         if lot_data:
#             update_fields = []
#             if "description" in lot_data:
#                 lot.description = lot_data.get("description") or ""
#                 update_fields.append("description")
#             if "received_at" in lot_data:
#                 lot.received_at = lot_data["received_at"]
#                 update_fields.append("received_at")

#             if update_fields:
#                 lot.save(update_fields=update_fields)

#         # Recalcul des totaux achat (car frais peuvent avoir changé)
#         if achat_data:
#             achat.update_total(save=True)

#         # ----- Réponse : même format que ArrivageCreateView -----
#         out = AchatCreateResponseSerializer(lot).data
#         return Response(out, status=status.HTTP_200_OK)
    

# class ArrivageMetaUpdateView(APIView):
#     """
#     PATCH /api/achat/arrivage/{lot_id}/meta/

#     Met à jour UNIQUEMENT les informations documentaires :
#     - côté Achat : description, frais_transport, frais_douane, fournisseur
#     - côté Lot   : description, received_at

#     ❌ Aucun impact sur le stock ou les mouvements d'inventaire.
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManager]
#     http_method_names = ["patch"]

#     @swagger_auto_schema(
#         operation_id="arrivageMetaUpdate",
#         operation_summary="Mettre à jour les métadonnées d’un arrivage (Achat + Lot)",
#         operation_description=(
#             "Permet de corriger / compléter les infos documentaires d’un arrivage :\n"
#             "- `achat`: description, frais_transport, frais_douane, fournisseur (ref ou upsert par téléphone)\n"
#             "- `lot`: description, received_at\n\n"
#             "Ne touche ni au stock ni aux mouvements d’inventaire."
#         ),
#         request_body=ArrivageMetaUpdateInSerializer,
#         responses={
#             200: ArrivageCreateResponseSerializer,
#             400: "Bad Request",
#             401: "Unauthorized",
#             403: "Forbidden",
#             404: "Not Found",
#         },
#         tags=["Achats / Arrivages"],
#         manual_parameters=[
#             openapi.Parameter(
#                 "lot_id",
#                 in_=openapi.IN_PATH,
#                 type=openapi.TYPE_INTEGER,
#                 description="ID du lot concerné",
#                 required=True,
#             ),
#         ],
#     )
#     @transaction.atomic
#     def patch(self, request, lot_id: int):
#         # ----- Récup lot + achat -----
#         lot = get_object_or_404(
#             Lot.objects.select_related("achat", "achat__fournisseur").prefetch_related("lignes__produit"),
#             pk=lot_id,
#         )
#         achat = lot.achat

#         # ----- Validation payload -----
#         s = ArrivageMetaUpdateInSerializer(data=request.data)
#         s.is_valid(raise_exception=True)
#         data = s.validated_data

#         achat_data = data.get("achat")
#         lot_data = data.get("lot")

#         # ====================
#         #  MAJ côté Achat
#         # ====================
#         if achat_data:
#             if "description" in achat_data:
#                 achat.description = achat_data.get("description") or ""

#             if "frais_transport" in achat_data:
#                 achat.frais_transport = achat_data["frais_transport"]

#             if "frais_douane" in achat_data:
#                 achat.frais_douane = achat_data["frais_douane"]

#             # fournisseur (ref / upsert)
#             fournisseur_data = achat_data.get("fournisseur")
#             if fournisseur_data:
#                 fournisseur_obj = None

#                 fid = fournisseur_data.get("id")
#                 if fid:
#                     fournisseur_obj = get_object_or_404(Fournisseur, pk=fid)
#                 else:
#                     tel = (fournisseur_data.get("telephone") or "").strip() or None
#                     if tel:
#                         fournisseur_obj, _ = Fournisseur.objects.update_or_create(
#                             telephone=tel,
#                             defaults={
#                                 "nom": fournisseur_data.get("nom") or "",
#                                 "prenom": fournisseur_data.get("prenom") or "",
#                                 "address": fournisseur_data.get("address") or "",
#                             },
#                         )

#                 if fournisseur_obj:
#                     achat.fournisseur = fournisseur_obj

#             achat.save()

#         # ====================
#         #  MAJ côté Lot
#         # ====================
#         if lot_data:
#             update_fields = []
#             if "description" in lot_data:
#                 lot.description = lot_data.get("description") or ""
#                 update_fields.append("description")

#             if "received_at" in lot_data:
#                 lot.received_at = lot_data["received_at"]
#                 update_fields.append("received_at")

#             if update_fields:
#                 lot.save(update_fields=update_fields)

#         # Recalcul des totaux achat (car frais peuvent avoir changé)
#         if achat_data:
#             achat.update_total(save=True)

#         # ✅ Réponse cohérente avec ton wrapper : achat + [lot]
#         payload = {"achat": achat, "lots": [lot]}
#         out = ArrivageCreateResponseSerializer(payload).data
#         return Response(out, status=status.HTTP_200_OK)
    


class ArrivageMetaUpdateView(APIView):
    """
    PATCH /api/achat/arrivage/{lot_id}/meta/

    Met à jour UNIQUEMENT les infos documentaires :
    - Achat : description, frais_transport, frais_douane, fournisseur
    - Lot   : description, received_at

    ❌ Aucun impact stock / inventaire.
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]
    http_method_names = ["patch"]

    @swagger_auto_schema(
        operation_id="arrivageMetaUpdate",
        operation_summary="Mettre à jour les métadonnées d’un arrivage (Achat + Lot)",
        operation_description=(
            "Permet de corriger / compléter les infos documentaires d’un arrivage :\n"
            "- `achat`: description, frais_transport, frais_douane, fournisseur (ref ou upsert par téléphone)\n"
            "- `lot`: description, received_at\n\n"
            "Ne touche ni au stock ni aux mouvements d’inventaire."
        ),
        request_body=ArrivageMetaUpdateInSerializer,
        responses={
            200: ArrivageCreateResponseSerializer,
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
        },
        tags=["Achats / Arrivages"],
        manual_parameters=[
            openapi.Parameter(
                "lot_id",
                in_=openapi.IN_PATH,
                type=openapi.TYPE_INTEGER,
                description="ID du lot concerné",
                required=True,
            ),
        ],
    )
    @transaction.atomic
    def patch(self, request, lot_id: int):
        # ----- Récup lot + achat -----
        lot = get_object_or_404(
            Lot.objects
            .select_related("achat", "achat__fournisseur")
            .prefetch_related("lignes__produit"),
            pk=lot_id,
        )
        achat: Achat = lot.achat

        # ----- Validation payload -----
        s = ArrivageMetaUpdateInSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        achat_data = data.get("achat") or None
        lot_data = data.get("lot") or None

        # ====================
        #  MAJ côté Achat
        # ====================
        if achat_data:
            update_achat_fields = []

            if "description" in achat_data:
                achat.description = achat_data.get("description") or ""
                update_achat_fields.append("description")

            if "frais_transport" in achat_data:
                achat.frais_transport = achat_data["frais_transport"]
                update_achat_fields.append("frais_transport")

            if "frais_douane" in achat_data:
                achat.frais_douane = achat_data["frais_douane"]
                update_achat_fields.append("frais_douane")

            # fournisseur (ref / upsert / create)
            fournisseur_data = achat_data.get("fournisseur") or None
            if fournisseur_data:
                fournisseur_obj = None

                fid = fournisseur_data.get("id")
                if fid:
                    fournisseur_obj = get_object_or_404(Fournisseur, pk=fid)
                else:
                    tel = (fournisseur_data.get("telephone") or "").strip() or None
                    if tel:
                        fournisseur_obj, _ = Fournisseur.objects.update_or_create(
                            telephone=tel,
                            defaults={
                                "nom": fournisseur_data.get("nom") or "",
                                "prenom": fournisseur_data.get("prenom") or "",
                                "address": fournisseur_data.get("address") or "",
                            },
                        )
                    else:
                        # pas d'id, pas de tel => nouveau fournisseur
                        fournisseur_obj = Fournisseur.objects.create(
                            nom=fournisseur_data.get("nom") or "",
                            prenom=fournisseur_data.get("prenom") or "",
                            telephone=None,
                            address=fournisseur_data.get("address") or "",
                        )

                if fournisseur_obj and achat.fournisseur_id != fournisseur_obj.id:
                    achat.fournisseur = fournisseur_obj
                    update_achat_fields.append("fournisseur")

            if update_achat_fields:
                achat.full_clean()
                achat.save(update_fields=list(set(update_achat_fields)))

        # ====================
        #  MAJ côté Lot
        # ====================
        if lot_data:
            update_lot_fields = []

            if "description" in lot_data:
                lot.description = lot_data.get("description") or ""
                update_lot_fields.append("description")

            if "received_at" in lot_data:
                lot.received_at = lot_data["received_at"]
                update_lot_fields.append("received_at")

            if update_lot_fields:
                lot.full_clean()
                lot.save(update_fields=list(set(update_lot_fields)))

        # 🔁 Recalcul des totaux achat (uniquement si achat touché)
        if achat_data:
            achat.update_total(save=True)

        # ✅ Réponse cohérente avec ton wrapper : achat + [lot]
        payload = {"achat": achat, "lots": [lot]}
        out = ArrivageCreateResponseSerializer(payload).data
        return Response(out, status=status.HTTP_200_OK)
    

# ---------------------------Adjustement-----------------------------
# class ArrivageAdjustmentsView(APIView):
#     """
#     POST /api/achat/arrivage/<lot_id>/adjustments/

#     Ajustements d’un arrivage (lot) :
#     - PURCHASE_IN  : ajout d’une ProduitLine + crédit réserve + mouvement PURCHASE_IN
#     - CANCEL_PURCHASE : retrait partiel d’une ProduitLine + débit réserve + mouvement CANCEL_PURCHASE
#       + supprime automatiquement la ProduitLine (et son stock réserve) si quantite == 0

#     Règles fortes :
#     - Si l'achat a déjà des allocations bijouterie (n'importe quel lot), on bloque tout ajustement.
#     - CANCEL_PURCHASE interdit si la ProduitLine a une allocation bijouterie (stock bijouterie != None, quantite_disponible > 0)
#     - CANCEL_PURCHASE n'autorise jamais un retrait > stock réserve disponible.
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManager]
#     http_method_names = ["post"]

#     @swagger_auto_schema(
#         operation_id="arrivageAdjustments",
#         operation_summary="Ajuster un arrivage (ajouts / retraits sur un lot)",
#         operation_description=(
#             "Permet d'ajouter des lignes (PURCHASE_IN) ou de réduire des lignes existantes "
#             "(CANCEL_PURCHASE) pour un lot donné.\n\n"
#             "**Types d'actions :**\n"
#             "- `PURCHASE_IN` : `produit_id`, `quantite`, `prix_achat_gramme`\n"
#             "- `CANCEL_PURCHASE` : `produit_line_id`, `quantite`\n\n"
#             "**Règles :**\n"
#             "- Les ajouts vont en bucket RÉSERVE (bijouterie=None).\n"
#             "- Les retraits ne peuvent porter que sur la quantité disponible en RÉSERVE.\n"
#             "- Si des allocations bijouterie existent pour la ligne, le retrait est refusé.\n"
#             "- Si l'achat a déjà des allocations bijouterie (peu importe le lot), aucun ajustement n'est autorisé.\n"
#             "- Nettoyage : si une ligne arrive à 0, on supprime la ProduitLine + son stock réserve."
#         ),
#         manual_parameters=[
#             openapi.Parameter(
#                 "lot_id",
#                 in_=openapi.IN_PATH,
#                 type=openapi.TYPE_INTEGER,
#                 description="ID du lot concerné",
#                 required=True,
#             ),
#         ],
#         request_body=ArrivageAdjustmentsInSerializer,
#         responses={
#             200: openapi.Response(
#                 description="Ajustements appliqués + réponse complète achat+lots",
#                 schema=ArrivageCreateResponseSerializer,
#             ),
#             400: "Bad Request",
#             401: "Unauthorized",
#             403: "Forbidden",
#             404: "Not Found",
#             409: "Conflict",
#         },
#         tags=["Achats / Arrivages"],
#     )
#     @transaction.atomic
#     def post(self, request, lot_id: int):
#         # --------- Lock lot + achat ----------
#         lot = get_object_or_404(
#             Lot.objects.select_related("achat"),
#             pk=lot_id
#         )
#         achat = lot.achat

#         # 🔒 Si l'achat a déjà des allocations bijouterie, on bloque TOUT ajustement
#         if achat.has_bijouterie_allocations:
#             return Response(
#                 {
#                     "detail": (
#                         "Ajustement impossible : au moins une partie de cet achat "
#                         "est déjà allouée à une bijouterie."
#                     )
#                 },
#                 status=status.HTTP_409_CONFLICT,
#             )

#         s = ArrivageAdjustmentsInSerializer(data=request.data)
#         s.is_valid(raise_exception=True)
#         actions = s.validated_data["actions"]

#         now = timezone.now()

#         for idx, act in enumerate(actions):
#             t = act["type"]
#             q = int(act["quantite"] or 0)
#             if q < 1:
#                 return Response(
#                     {f"actions[{idx}]": "quantite doit être >= 1."},
#                     status=status.HTTP_400_BAD_REQUEST,
#                 )

#             reason = (act.get("reason") or "").strip()

#             # =======================
#             # PURCHASE_IN (ajout ligne)
#             # =======================
#             if t == "PURCHASE_IN":
#                 pid = act.get("produit_id")
#                 if not pid:
#                     return Response(
#                         {f"actions[{idx}]": "produit_id est obligatoire (PURCHASE_IN)."},
#                         status=status.HTTP_400_BAD_REQUEST,
#                     )

#                 produit = get_object_or_404(
#                     Produit.objects.only("id", "poids", "nom"),
#                     pk=int(pid),
#                 )

#                 prix_achat_gramme = act.get("prix_achat_gramme")
#                 if prix_achat_gramme is None:
#                     return Response(
#                         {f"actions[{idx}]": "prix_achat_gramme est obligatoire (PURCHASE_IN)."},
#                         status=status.HTTP_400_BAD_REQUEST,
#                     )

#                 # Create ProduitLine
#                 pl = ProduitLine.objects.create(
#                     lot=lot,
#                     produit=produit,
#                     prix_achat_gramme=prix_achat_gramme,
#                     quantite=q,
#                 )

#                 # Stock réserve : allouée=0, dispo=q
#                 Stock.objects.create(
#                     produit_line=pl,
#                     bijouterie=None,
#                     quantite_disponible=0,
#                     en_stock=q,
#                 )

#                 # unit_cost = prix_gramme * poids
#                 unit_cost = None
#                 if produit.poids is not None:
#                     try:
#                         unit_cost = (
#                             Decimal(str(prix_achat_gramme)) * Decimal(str(produit.poids))
#                         ).quantize(Decimal("0.01"))
#                     except (InvalidOperation, TypeError, ValueError):
#                         unit_cost = None

#                 InventoryMovement.objects.create(
#                     produit=produit,
#                     movement_type=MovementType.PURCHASE_IN,
#                     qty=q,
#                     unit_cost=unit_cost,
#                     lot=lot,
#                     reason=reason or "Ajout ligne (arrivage)",
#                     src_bucket=Bucket.EXTERNAL,
#                     dst_bucket=Bucket.RESERVED,
#                     achat=achat,
#                     occurred_at=now,
#                     created_by=request.user,
#                 )

#             # ============================
#             # CANCEL_PURCHASE (retrait)
#             # ============================
#             elif t == "CANCEL_PURCHASE":
#                 pl_id = act.get("produit_line_id")
#                 if not pl_id:
#                     return Response(
#                         {f"actions[{idx}]": "produit_line_id est obligatoire (CANCEL_PURCHASE)."},
#                         status=status.HTTP_400_BAD_REQUEST,
#                     )

#                 pl = get_object_or_404(
#                     ProduitLine.objects.select_related("produit", "lot"),
#                     pk=int(pl_id),
#                 )

#                 # La ligne doit appartenir au lot
#                 if pl.lot_id != lot.id:
#                     return Response(
#                         {f"actions[{idx}]": f"ProduitLine {pl.id} n'appartient pas au lot {lot.id}."},
#                         status=status.HTTP_400_BAD_REQUEST,
#                     )

#                 # Interdit si allocations bijouterie existent pour cette ligne
#                 has_alloc = Stock.objects.filter(
#                     produit_line=pl,
#                     bijouterie__isnull=False,
#                     quantite_disponible__gt=0,
#                 ).exists()
#                 if has_alloc:
#                     return Response(
#                         {f"actions[{idx}]": f"Ligne {pl.id}: allocations bijouterie existantes, retrait interdit."},
#                         status=status.HTTP_400_BAD_REQUEST,
#                     )

#                 # 🔒 Lock stock réserve
#                 try:
#                     reserve = (
#                         Stock.objects
#                         .select_for_update()
#                         .get(produit_line=pl, bijouterie__isnull=True)
#                     )
#                 except Stock.DoesNotExist:
#                     return Response(
#                         {f"actions[{idx}]": f"Ligne {pl.id}: stock réserve introuvable."},
#                         status=status.HTTP_400_BAD_REQUEST,
#                     )

#                 disponible = int(reserve.en_stock or 0)
#                 if q > disponible:
#                     return Response(
#                         {f"actions[{idx}]": f"Réduction {q} > disponible en réserve ({disponible}) pour la ligne {pl.id}."},
#                         status=status.HTTP_400_BAD_REQUEST,
#                     )

#                 # On réduit la ligne
#                 old_pl_qty = int(pl.quantite or 0)
#                 new_pl_qty = old_pl_qty - q
#                 if new_pl_qty < 0:
#                     # garde-fou (normalement impossible si stock cohérent)
#                     return Response(
#                         {f"actions[{idx}]": f"Réduction {q} > quantite de la ligne ({old_pl_qty}) pour ProduitLine {pl.id}."},
#                         status=status.HTTP_400_BAD_REQUEST,
#                     )

#                 # MAJ stock réserve
#                 reserve.quantite_disponible = 0
#                 reserve.en_stock = disponible - q
#                 reserve.save(update_fields=["quantite_disponible", "en_stock"])

#                 # Mouvement d’inventaire (historique)
#                 InventoryMovement.objects.create(
#                     produit=pl.produit,
#                     movement_type=MovementType.CANCEL_PURCHASE,
#                     qty=q,
#                     unit_cost=None,
#                     lot=lot,
#                     reason=reason or "Retrait partiel (arrivage)",
#                     src_bucket=Bucket.RESERVED,
#                     dst_bucket=Bucket.EXTERNAL,
#                     achat=achat,
#                     occurred_at=now,
#                     created_by=request.user,
#                 )

#                 # Si la ligne tombe à 0 -> delete propre (stock puis ligne)
#                 if new_pl_qty == 0:
#                     # supprime stock réserve si 0
#                     if int(reserve.en_stock or 0) == 0:
#                         reserve.delete()
#                     pl.delete()
#                 else:
#                     pl.quantite = new_pl_qty
#                     pl.save(update_fields=["quantite"])

#             else:
#                 return Response(
#                     {f"actions[{idx}]": f"Type inconnu: {t}"},
#                     status=status.HTTP_400_BAD_REQUEST,
#                 )

#         # 🔁 Recalcule totaux via le modèle (plus fiable que recalcul manuel)
#         achat.update_total(save=True)

#         # ✅ Réponse complète achat + lots (tous les lots de l'achat)
#         lots_qs = (
#             Lot.objects
#             .filter(achat=achat)
#             .select_related("achat", "achat__fournisseur")
#             .prefetch_related("lignes__produit")
#             .order_by("received_at", "id")
#         )

#         payload = {"achat": achat, "lots": list(lots_qs)}
#         out = ArrivageCreateResponseSerializer(payload).data
#         return Response(out, status=status.HTTP_200_OK)


def _to_decimal(v):
    if v in (None, "", "null"):
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return None


class ArrivageAdjustmentsView(APIView):
    """
    POST /api/achat/arrivage/<lot_id>/adjustments/

    Ajustements d’un arrivage (lot) :
    - PURCHASE_IN     : ajout d’une ProduitLine + crédit réserve + mouvement PURCHASE_IN
    - CANCEL_PURCHASE : retrait partiel d’une ProduitLine + débit réserve + mouvement CANCEL_PURCHASE
                        + supprime automatiquement la ProduitLine (+ stock réserve) si quantite == 0

    Règles fortes :
    - Si l'achat a déjà des allocations bijouterie (n'importe quel lot), on bloque tout ajustement.
    - CANCEL_PURCHASE interdit si la ProduitLine a une allocation bijouterie (stock bijouterie != None et en_stock > 0).
    - CANCEL_PURCHASE n'autorise jamais un retrait > stock réserve disponible.
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]
    http_method_names = ["post"]

    @swagger_auto_schema(
        operation_id="arrivageAdjustments",
        operation_summary="Ajuster un arrivage (ajouts / retraits sur un lot)",
        operation_description=(
            "Permet d'ajouter des lignes (PURCHASE_IN) ou de réduire des lignes existantes "
            "(CANCEL_PURCHASE) pour un lot donné.\n\n"
            "**Types d'actions :**\n"
            "- `PURCHASE_IN` : `produit_id`, `quantite`, `prix_achat_gramme`\n"
            "- `CANCEL_PURCHASE` : `produit_line_id`, `quantite`\n\n"
            "**Règles :**\n"
            "- Les ajouts vont en bucket RÉSERVE (bijouterie=None).\n"
            "- Les retraits ne peuvent porter que sur la quantité disponible en RÉSERVE.\n"
            "- Si des allocations bijouterie existent pour la ligne, le retrait est refusé.\n"
            "- Si l'achat a déjà des allocations bijouterie (peu importe le lot), aucun ajustement n'est autorisé.\n"
            "- Nettoyage : si une ligne arrive à 0, on supprime la ProduitLine + son stock réserve."
        ),
        manual_parameters=[
            openapi.Parameter(
                "lot_id",
                in_=openapi.IN_PATH,
                type=openapi.TYPE_INTEGER,
                description="ID du lot concerné",
                required=True,
            ),
        ],
        request_body=ArrivageAdjustmentsInSerializer,
        responses={
            200: openapi.Response(
                description="Ajustements appliqués + réponse complète achat+lots",
                schema=ArrivageCreateResponseSerializer,
            ),
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            409: "Conflict",
        },
        tags=["Achats / Arrivages"],
    )
    @transaction.atomic
    def post(self, request, lot_id: int):
        # --------- Lot + achat ----------
        lot = get_object_or_404(Lot.objects.select_related("achat"), pk=lot_id)
        achat = lot.achat

        # 🔒 blocage si allocations bijouterie déjà faites sur l'achat
        if getattr(achat, "has_bijouterie_allocations", False):
            return Response(
                {
                    "detail": (
                        "Ajustement impossible : au moins une partie de cet achat "
                        "est déjà allouée à une bijouterie."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        s = ArrivageAdjustmentsInSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        actions = s.validated_data["actions"]
        now = timezone.now()

        for idx, act in enumerate(actions):
            t = (act.get("type") or "").strip().upper()
            q = int(act.get("quantite") or 0)

            if q < 1:
                return Response(
                    {f"actions[{idx}]": "quantite doit être >= 1."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            reason = (act.get("reason") or "").strip()

            # =======================
            # PURCHASE_IN (ajout)
            # =======================
            if t == "PURCHASE_IN":
                pid = act.get("produit_id")
                if not pid:
                    return Response(
                        {f"actions[{idx}]": "produit_id est obligatoire (PURCHASE_IN)."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                prix_achat_gramme = _to_decimal(act.get("prix_achat_gramme"))
                if prix_achat_gramme is None:
                    return Response(
                        {f"actions[{idx}]": "prix_achat_gramme est obligatoire et doit être un nombre."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                produit = get_object_or_404(
                    Produit.objects.only("id", "poids", "nom"),
                    pk=int(pid),
                )

                pl = ProduitLine.objects.create(
                    lot=lot,
                    produit=produit,
                    prix_achat_gramme=prix_achat_gramme,
                    quantite=q,
                )

                # ✅ Stock réserve: disponible = en_stock
                Stock.objects.create(
                    produit_line=pl,
                    bijouterie=None,
                    en_stock=q,
                    quantite_totale=q,
                )

                # unit_cost = prix_gramme * poids
                unit_cost = None
                if produit.poids is not None:
                    try:
                        unit_cost = (prix_achat_gramme * Decimal(str(produit.poids))).quantize(Decimal("0.01"))
                    except (InvalidOperation, TypeError, ValueError):
                        unit_cost = None

                InventoryMovement.objects.create(
                    produit=produit,
                    movement_type=MovementType.PURCHASE_IN,
                    qty=q,
                    unit_cost=unit_cost,
                    lot=lot,
                    achat=achat,
                    reason=reason or "Ajout ligne (arrivage)",
                    src_bucket=Bucket.EXTERNAL,
                    dst_bucket=Bucket.RESERVED,
                    occurred_at=now,
                    created_by=request.user,
                )

            # ==========================
            # CANCEL_PURCHASE (retrait)
            # ==========================
            elif t == "CANCEL_PURCHASE":
                pl_id = act.get("produit_line_id")
                if not pl_id:
                    return Response(
                        {f"actions[{idx}]": "produit_line_id est obligatoire (CANCEL_PURCHASE)."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                pl = get_object_or_404(
                    ProduitLine.objects.select_related("produit", "lot"),
                    pk=int(pl_id),
                )

                if pl.lot_id != lot.id:
                    return Response(
                        {f"actions[{idx}]": f"ProduitLine {pl.id} n'appartient pas au lot {lot.id}."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # ❌ interdit si la ligne a déjà un stock en bijouterie (allocation)
                has_alloc = Stock.objects.filter(
                    produit_line=pl,
                    bijouterie__isnull=False,
                    en_stock__gt=0,
                ).exists()
                if has_alloc:
                    return Response(
                        {f"actions[{idx}]": f"Ligne {pl.id}: allocations bijouterie existantes, retrait interdit."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # 🔒 lock stock réserve
                try:
                    reserve = (
                        Stock.objects
                        .select_for_update()
                        .get(produit_line=pl, bijouterie__isnull=True)
                    )
                except Stock.DoesNotExist:
                    return Response(
                        {f"actions[{idx}]": f"Ligne {pl.id}: stock réserve introuvable."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                dispo = int(reserve.quantite_totale or 0)
                if q > dispo:
                    return Response(
                        {f"actions[{idx}]": f"Réduction {q} > disponible en réserve ({dispo}) pour la ligne {pl.id}."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                old_pl_qty = int(pl.quantite or 0)
                if q > old_pl_qty:
                    return Response(
                        {f"actions[{idx}]": f"Réduction {q} > quantite de la ligne ({old_pl_qty}) pour ProduitLine {pl.id}."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # MAJ ProduitLine
                new_pl_qty = old_pl_qty - q
                pl.quantite = new_pl_qty
                pl.save(update_fields=["quantite"])

                # MAJ Stock réserve (retire sur les deux)
                reserve.en_stock = max(0, int(reserve.en_stock or 0) - q)
                reserve.quantite_totale = max(0, int(reserve.quantite_totale or 0) - q)
                reserve.save(update_fields=["en_stock", "quantite_totale"])

                InventoryMovement.objects.create(
                    produit=pl.produit,
                    movement_type=MovementType.CANCEL_PURCHASE,
                    qty=q,
                    unit_cost=None,
                    lot=lot,
                    achat=achat,
                    reason=reason or "Retrait partiel (arrivage)",
                    src_bucket=Bucket.RESERVED,
                    dst_bucket=Bucket.EXTERNAL,
                    occurred_at=now,
                    created_by=request.user,
                )

                # ✅ nettoyage si tout à zéro
                if new_pl_qty == 0:
                    reserve.delete()
                    pl.delete()

            else:
                return Response(
                    {f"actions[{idx}]": f"Type inconnu: {t}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # 🔁 Totaux
        achat.update_total(save=True)

        # ✅ Réponse complète achat + lots de l'achat
        lots_qs = (
            Lot.objects
            .filter(achat=achat)
            .select_related("achat", "achat__fournisseur")
            .prefetch_related("lignes__produit")
            .order_by("received_at", "id")
        )
        payload = {"achat": achat, "lots": list(lots_qs)}
        out = ArrivageCreateResponseSerializer(payload).data
        return Response(out, status=status.HTTP_200_OK)


# -------------------------InventoryPhotoView---------------------
class InventoryPhotoView(ExportXlsxMixin, ListAPIView):
    """
    Inventaire "photo" : ProduitLine (lot+produit) + agrégats Stock.
    + filtre reference_commande (icontains)
    + export Excel (?export=xlsx)
    
    Exemple d’appels utiles

        Inventaire global année courante :
        GET /api/inventaire/photo/

        Filtrer par référence commande :
        GET /api/inventaire/photo/?reference_commande=CMD-2026

        Inventaire uniquement réserve :
        GET /api/inventaire/photo/?reserve_only=1

        Inventaire d’une bijouterie :
        GET /api/inventaire/photo/?bijouterie_id=2

        Export Excel :
        GET /api/inventaire/photo/?export=xlsx&reference_commande=CMD-2026
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]
    serializer_class = ProduitLineMiniSerializer
    pagination_class = None

    @swagger_auto_schema(
        operation_id="listProduitLinesInventory",
        operation_summary="Inventaire par lot + produit (ProduitLine) avec agrégats Stock + export Excel",
        operation_description=(
            "Retourne les ProduitLine (lot+produit) avec agrégats Stock.\n\n"
            "• Par défaut : année courante (`lot.received_at`).\n"
            "• `reference_commande` : recherche partielle sur Achat.reference_commande.\n"
            "• `bijouterie_id` : agrège uniquement le stock de cette bijouterie.\n"
            "• `reserve_only=1` : agrège uniquement le stock de réserve (bijouterie=NULL).\n"
            "⚠️ `reserve_only=1` et `bijouterie_id` ne peuvent pas être utilisés ensemble.\n\n"
            "Export Excel : `?export=xlsx`"
        ),
        manual_parameters=[
            openapi.Parameter("year", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="Année (ex: 2026). Défaut : année courante."),
            openapi.Parameter("reference_commande", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Recherche partielle sur la référence commande (icontains)."),
            openapi.Parameter("lot_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="Filtre exact sur le lot_id."),
            openapi.Parameter("produit_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="Filtre exact sur le produit_id."),
            openapi.Parameter("numero_lot", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Recherche partielle sur numero_lot (icontains)."),
            openapi.Parameter("numero_achat", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Filtre exact sur numero_achat."),
            openapi.Parameter("fournisseur_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="Filtre exact sur fournisseur_id."),
            openapi.Parameter("bijouterie_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="Si fourni, agrège uniquement le stock de cette bijouterie."),
            openapi.Parameter("reserve_only", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="1 = seulement réserve (bijouterie=NULL)."),
            openapi.Parameter("ordering", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Tri: -received_at (défaut), received_at, id, -id"),
            openapi.Parameter("export", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="xlsx pour exporter (ex: export=xlsx)."),
        ],
        responses={200: ProduitLineMiniSerializer(many=True)},
        tags=["Achats / Arrivages"],
    )
    def get(self, request, *args, **kwargs):
        # sécurise year
        y = request.query_params.get("year")
        if y:
            try:
                int(y)
            except ValueError:
                raise ValidationError({"year": "Doit être un entier (ex: 2026)."})
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        qp = self.request.query_params
        getf = qp.get

        # ---- year ----
        year = getf("year")
        try:
            year = int(year) if year else timezone.localdate().year
        except ValueError:
            year = timezone.localdate().year

        # ---- ordering ----
        ordering = (getf("ordering") or "-received_at").strip()
        allowed_order = {"-received_at", "received_at", "id", "-id"}
        if ordering not in allowed_order:
            ordering = "-received_at"

        # ---- filtres stock ----
        bijouterie_id = getf("bijouterie_id")
        reserve_only = getf("reserve_only")

        if reserve_only == "1" and bijouterie_id:
            raise ValidationError({"detail": "Utilise soit reserve_only=1 soit bijouterie_id, pas les deux."})

        bijouterie_id_int = None
        if bijouterie_id:
            try:
                bijouterie_id_int = int(bijouterie_id)
            except ValueError:
                raise ValidationError({"bijouterie_id": "Doit être un entier."})

        # ---- base ----
        qs = (
            ProduitLine.objects
            .select_related(
                "lot",
                "lot__achat",
                "lot__achat__fournisseur",
                "produit",
                "produit__categorie",
                "produit__marque",
                "produit__purete",
            )
            .filter(lot__received_at__year=year)
        )

        # ---- filtres simples ----
        reference_commande = (getf("reference_commande") or "").strip()
        if reference_commande:
            qs = qs.filter(lot__achat__reference_commande__icontains=reference_commande)

        lot_id = getf("lot_id")
        if lot_id:
            try:
                qs = qs.filter(lot_id=int(lot_id))
            except ValueError:
                raise ValidationError({"lot_id": "Doit être un entier."})

        produit_id = getf("produit_id")
        if produit_id:
            try:
                qs = qs.filter(produit_id=int(produit_id))
            except ValueError:
                raise ValidationError({"produit_id": "Doit être un entier."})

        numero_lot = (getf("numero_lot") or "").strip()
        if numero_lot:
            qs = qs.filter(lot__numero_lot__icontains=numero_lot)

        numero_achat = (getf("numero_achat") or "").strip()
        if numero_achat:
            qs = qs.filter(lot__achat__numero_achat=numero_achat)

        fournisseur_id = getf("fournisseur_id")
        if fournisseur_id:
            try:
                qs = qs.filter(lot__achat__fournisseur_id=int(fournisseur_id))
            except ValueError:
                raise ValidationError({"fournisseur_id": "Doit être un entier."})

        # ---- agrégats stock propres (SUM conditionnels) ----
        if reserve_only == "1":
            qs = qs.annotate(
                quantite_totale_total=Coalesce(
                    Sum("stocks__quantite_totale", filter=Q(stocks__bijouterie__isnull=True)),
                    0
                ),
                en_stock_total=Coalesce(
                    Sum("stocks__en_stock", filter=Q(stocks__bijouterie__isnull=True)),
                    0
                ),
            )
        elif bijouterie_id_int is not None:
            qs = qs.annotate(
                quantite_totale_total=Coalesce(
                    Sum("stocks__quantite_totale", filter=Q(stocks__bijouterie_id=bijouterie_id_int)),
                    0
                ),
                en_stock_total=Coalesce(
                    Sum("stocks__en_stock", filter=Q(stocks__bijouterie_id=bijouterie_id_int)),
                    0
                ),
            )
        else:
            qs = qs.annotate(
                quantite_totale_total=Coalesce(Sum("stocks__quantite_totale"), 0),
                en_stock_total=Coalesce(Sum("stocks__en_stock"), 0),
            )

        # ---- ordering final ----
        if ordering in {"received_at", "-received_at"}:
            return qs.order_by(
                "lot__received_at" if ordering == "received_at" else "-lot__received_at",
                "lot__numero_lot",
                "id",
            )
        return qs.order_by(ordering)

    def list(self, request, *args, **kwargs):
        """
        Si ?export=xlsx => Excel
        Sinon => JSON normal DRF
        """
        export = (request.query_params.get("export") or "").strip().lower()
        if export != "xlsx":
            return super().list(request, *args, **kwargs)

        qs = self.filter_queryset(self.get_queryset())

        wb = Workbook()
        ws = wb.active
        ws.title = "Inventaire"

        headers = [
            "produit_line_id",
            "lot_id", "numero_lot", "received_at",
            "numero_achat", "reference_commande",
            "fournisseur",
            "produit_id", "produit_nom",
            "categorie", "marque", "purete",
            "prix_achat_gramme",
            "quantite_ligne",
            "en_stock_total",
            "quantite_totale_total",
        ]
        ws.append(headers)

        for pl in qs:
            lot = pl.lot
            achat = lot.achat if lot else None
            fournisseur = achat.fournisseur if achat else None
            produit = pl.produit

            ws.append([
                pl.id,
                lot.id if lot else None,
                getattr(lot, "numero_lot", None),
                lot.received_at.isoformat() if getattr(lot, "received_at", None) else None,
                getattr(achat, "numero_achat", None),
                getattr(achat, "reference_commande", None),
                f"{getattr(fournisseur,'nom','')} {getattr(fournisseur,'prenom','')}".strip() if fournisseur else None,
                produit.id if produit else None,
                getattr(produit, "nom", None),
                getattr(getattr(produit, "categorie", None), "nom", None),
                getattr(getattr(produit, "marque", None), "nom", None),
                getattr(getattr(produit, "purete", None), "nom", None),
                str(pl.prix_achat_gramme) if pl.prix_achat_gramme is not None else None,
                int(pl.quantite or 0),
                int(getattr(pl, "en_stock_total", 0) or 0),
                int(getattr(pl, "quantite_totale_total", 0) or 0),
            ])

        self._autosize(ws)
        return self._xlsx_response(wb, "inventaire_photo.xlsx")
# -------------------------End InventoryPhotoView---------------------



