from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from textwrap import dedent

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import (Case, Count, DecimalField, ExpressionWrapper, F,
                              IntegerField, Prefetch, Q, Sum, Value, When)
from django.db.models.functions import Cast, Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.permissions import IsAdminOrManager
from backend.renderers import UserRenderer
from inventory.models import Bucket, InventoryMovement, MovementType
from purchase.models import Achat, Fournisseur, Lot, ProduitLine
from purchase.services import _get_or_upsert_fournisseur, _recalc_totaux_achat
from stock.models import Stock
from store.models import Produit

from .serializers import (AchatCreateResponseSerializer, AchatSerializer,
                          ArrivageCreateInSerializer)

# ZERO = Decimal("0.00") 
# TWOPLACES = Decimal('0.01')

# class FournisseurGetView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Récupère les informations d'un fournisseur par son ID.",
#         responses={
#             200: FournisseurSerializer(),
#             403: openapi.Response(description="Accès refusé"),
#             404: openapi.Response(description="Fournisseur introuvable"),
#         }
#     )
#     def get(self, request, pk, format=None):
#         user_role = getattr(request.user.user_role, 'role', None)
#         if user_role not in ['admin', 'manager']:
#             return Response({"message": "Access Denied"}, status=403)

#         try:
#             fournisseur = Fournisseur.objects.get(pk=pk)
#         except Fournisseur.DoesNotExist:
#             return Response({"detail": "Fournisseur not found"}, status=status.HTTP_404_NOT_FOUND)

#         serializer = FournisseurSerializer(fournisseur)
#         return Response(serializer.data, status=200)

# class FournisseurGetView(APIView):
#     """
#     Récupérer un fournisseur par son ID.
#     Accessible uniquement aux rôles admin / manager.
#     """
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated, IsAdminOrManager]

#     @swagger_auto_schema(
#         operation_id="getFournisseur",
#         operation_summary="Détail d'un fournisseur",
#         operation_description="Récupère les informations d'un fournisseur par son ID.",
#         responses={
#             200: FournisseurSerializer(),
#             403: openapi.Response(description="Accès refusé"),
#             404: openapi.Response(description="Fournisseur introuvable"),
#         },
#         tags=["Fournisseurs"],
#     )
#     def get(self, request, pk, format=None):
#         try:
#             fournisseur = Fournisseur.objects.get(pk=pk)
#         except Fournisseur.DoesNotExist:
#             return Response(
#                 {"detail": "Fournisseur introuvable."},
#                 status=status.HTTP_404_NOT_FOUND,
#             )

#         serializer = FournisseurSerializer(fournisseur)
#         return Response(serializer.data, status=status.HTTP_200_OK)

# PUT: mise à jour complète (tous les champs doivent être fournis)
# PATCH: mise à jour partielle (champs optionnels)
# Swagger : la doc est affichée proprement pour chaque méthode
# Contrôle des rôles (admin, manager)
# class FournisseurUpdateView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Met à jour complètement un fournisseur (remplace tous les champs).",
#         request_body=FournisseurSerializer,
#         responses={
#             200: FournisseurSerializer(),
#             400: "Requête invalide",
#             403: "Accès refusé",
#             404: "Fournisseur introuvable",
#         }
#     )
#     def put(self, request, pk, format=None):
#         return self.update_fournisseur(request, pk, partial=False)

#     @swagger_auto_schema(
#         operation_description="Met à jour partiellement un fournisseur (seuls les champs fournis sont modifiés).",
#         request_body=FournisseurSerializer,
#         responses={
#             200: FournisseurSerializer(),
#             400: "Requête invalide",
#             403: "Accès refusé",
#             404: "Fournisseur introuvable",
#         }
#     )
#     def patch(self, request, pk, format=None):
#         return self.update_fournisseur(request, pk, partial=True)

#     def update_fournisseur(self, request, pk, partial):
#         user_role = getattr(request.user.user_role, 'role', None)
#         if user_role not in ['admin', 'manager']:
#             return Response({"message": "Access Denied"}, status=403)

#         try:
#             fournisseur = Fournisseur.objects.get(pk=pk)
#         except Fournisseur.DoesNotExist:
#             return Response({"detail": "Fournisseur not found"}, status=404)

#         serializer = FournisseurSerializer(fournisseur, data=request.data, partial=partial)
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data, status=200)
#         return Response(serializer.errors, status=400)



# class FournisseurListView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Liste tous les fournisseurs, avec option de recherche par nom ou téléphone via le paramètre `search`.",
#         manual_parameters=[
#             openapi.Parameter(
#                 'search', openapi.IN_QUERY,
#                 description="Nom ou téléphone à rechercher",
#                 type=openapi.TYPE_STRING
#             )
#         ],
#         responses={200: FournisseurSerializer(many=True)}
#     )
#     def get(self, request):
#         user_role = getattr(request.user.user_role, 'role', None)
#         if user_role not in ['admin', 'manager']:
#             return Response({"message": "Access Denied"}, status=403)

#         search = request.query_params.get('search', '')
#         fournisseurs = Fournisseur.objects.all()
#         if search:
#             fournisseurs = fournisseurs.filter(
#                 Q(nom__icontains=search) | Q(prenom__icontains=search) | Q(telephone__icontains=search)
#             )

#         serializer = FournisseurSerializer(fournisseurs, many=True)
#         return Response(serializer.data, status=200)



# class FournisseurDeleteView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Supprime un fournisseur à partir de son ID.",
#         responses={
#             204: "Fournisseur supprimé avec succès",
#             403: "Accès refusé",
#             404: "Fournisseur introuvable",
#         }
#     )
#     def delete(self, request, pk, format=None):
#         role = getattr(request.user.user_role, 'role', None)
#         if role not in ['admin', 'manager']:
#             return Response({"message": "Access Denied"}, status=403)

#         try:
#             fournisseur = Fournisseur.objects.get(pk=pk)
#         except Fournisseur.DoesNotExist:
#             return Response({"detail": "Fournisseur not found"}, status=404)

#         fournisseur.delete()
#         return Response({"message": "Fournisseur supprimé avec succès."}, status=204)



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


class ArrivageCreateView(APIView):
    """
    Création d’un arrivage simple :

    - Crée un Achat (fournisseur + frais)
    - Crée 1 Lot rattaché à cet achat, avec numero_lot auto (LOT-YYYYMMDD-XXXX)
    - Crée les ProduitLine (quantité achetée, prix_achat_gramme)
    - Pousse 100% de la quantité en stock "Réserve"
    - Log automatiquement un mouvement d’inventaire PURCHASE_IN (EXTERNAL -> RESERVED)
    - Recalcule les totaux de l’achat via Achat.update_total()
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]
    http_method_names = ["post"]

    @swagger_auto_schema(
        operation_id="createArrivage",
        operation_summary="Créer un arrivage (lot auto-numéroté) et initialiser l'inventaire",
        operation_description=(
            "Crée un Achat, un Lot avec un numéro auto (LOT-YYYYMMDD-XXXX), les lignes produits (quantités), "
            "pousse 100% du stock en Réserve, log un mouvement PURCHASE_IN (EXTERNAL → RESERVED) "
            "et valorise l'achat au gramme si fourni."
        ),
        request_body=ArrivageCreateInSerializer,
        responses={
            201: AchatCreateResponseSerializer,
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

        lots_in = v["lots"]

        # --------- Validation produits ---------
        pids = {row["produit_id"] for row in lots_in}
        exists = set(Produit.objects.filter(id__in=pids).values_list("id", flat=True))
        missing = pids - exists
        if missing:
            return Response(
                {"lots": f"Produit(s) introuvable(s): {sorted(list(missing))}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        missing_weight = list(
            Produit.objects
            .filter(id__in=pids, poids__isnull=True)
            .values_list("id", flat=True)
        )
        if missing_weight:
            return Response(
                {"lots": f"Produit(s) sans poids: {missing_weight}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --------- Fournisseur ---------
        f = v["fournisseur"]
        fournisseur, _ = Fournisseur.objects.get_or_create(
            telephone=(f.get("telephone") or "").strip() or None,
            defaults={
                "nom": f["nom"],
                "prenom": f.get("prenom", ""),
            },
        )

        # --------- Achat ---------
        achat = Achat.objects.create(
            fournisseur=fournisseur,
            description=v.get("description", ""),
            frais_transport=v.get("frais_transport", Decimal("0")),
            frais_douane=v.get("frais_douane", Decimal("0")),
            # status par défaut défini dans le modèle (ex: STATUS_CONFIRMED)
        )

        # --------- Lot (header) ---------
        for _ in range(5):
            numero_lot = generate_numero_lot()
            try:
                lot = Lot.objects.create(
                    achat=achat,
                    numero_lot=numero_lot,
                    description=v.get("description", ""),
                    received_at=timezone.now(),
                )
                break
            except IntegrityError:
                continue
        else:
            return Response(
                {"detail": "Impossible de générer un numéro de lot unique."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --------- Lignes produit + Stock Réserve + Mouvements ---------
        produits_by_id = {
            p.id: p
            for p in Produit.objects.filter(id__in=pids).only("id", "poids", "nom")
        }

        for row in lots_in:
            produit = produits_by_id[row["produit_id"]]
            qte = int(row["quantite"])
            prix_achat_gramme = row.get("prix_achat_gramme")

            # Ligne d’achat (ProduitLine)
            pl = ProduitLine.objects.create(
                lot=lot,
                produit=produit,
                prix_gramme_achat=prix_achat_gramme,
                # si ton modèle a quantite_total / quantite_restante au lieu de quantite, adapte ici :
                # quantite_total=qte,
                # quantite_restante=qte,
                quantite=qte,
            )

            # Stock initial en Réserve (bijouterie=None = bucket RESERVED)
            Stock.objects.create(
                produit_line=pl,
                bijouterie=None,
                quantite_allouee=qte,
                quantite_disponible=qte,
            )

            # ---- Mouvement d’inventaire : EXTERNAL -> RESERVED ----
            # Option : valoriser à la pièce si prix_achat_gramme présent
            unit_cost = None
            if prix_achat_gramme is not None and produit.poids is not None:
                try:
                    unit_cost = (
                        Decimal(str(prix_achat_gramme)) * Decimal(str(produit.poids))
                    ).quantize(Decimal("0.01"))
                except (InvalidOperation, TypeError):
                    unit_cost = None

            InventoryMovement.objects.create(
                produit=produit,
                movement_type=MovementType.PURCHASE_IN,
                qty=qte,
                unit_cost=unit_cost,
                lot=lot,
                reason="Arrivage initial",
                src_bucket=Bucket.EXTERNAL,
                dst_bucket=Bucket.RESERVED,
                achat=achat,
                occurred_at=timezone.now(),
                created_by=request.user,
            )

        # --------- Totaux Achat via logique centrale ---------
        achat.update_total(save=True)

        # Réponse : détail du lot + achat
        out = AchatCreateResponseSerializer(lot).data
        return Response(out, status=status.HTTP_201_CREATED)

# -----------------------------Liste des achats---------------------------------
# class AchatListView(ListAPIView):
#     """
#     Liste des achats :
#     - par défaut : année courante
#     - si date_from & date_to sont fournis : intervalle [date_from, date_to] (inclus)
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManager]
#     serializer_class = AchatSerializer
#     # pagination_class = None  # pas de pagination

#     @swagger_auto_schema(
#         operation_summary="Lister les achats (année courante par défaut, sinon entre deux dates)",
#         operation_description=(
#             "• Si `date_from` **et** `date_to` sont fournis → filtre inclusif.\n"
#             "• Sinon → achats de l’**année courante**.\n"
#             "Formats : `YYYY-MM-DD`."
#         ),
#         manual_parameters=[
#             openapi.Parameter("date_from", openapi.IN_QUERY, type=openapi.TYPE_STRING,
#                               description="Borne min incluse (YYYY-MM-DD). Avec date_to."),
#             openapi.Parameter("date_to", openapi.IN_QUERY, type=openapi.TYPE_STRING,
#                               description="Borne max incluse (YYYY-MM-DD). Avec date_from."),
#             openapi.Parameter("ordering", openapi.IN_QUERY, type=openapi.TYPE_STRING,
#                               description="Tri: -created_at (défaut), created_at, numero_achat, -numero_achat"),
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
#         _check_date("date_from", request.query_params.get("date_from"))
#         _check_date("date_to", request.query_params.get("date_to"))
#         return super().get(request, *args, **kwargs)

#     def get_queryset(self):
#         params = self.request.query_params
#         getf = params.get

#         ordering = getf("ordering") or "-created_at"
#         allowed = {"created_at", "-created_at", "numero_achat", "-numero_achat"}
#         if ordering not in allowed:
#             ordering = "-created_at"

#         qs = (
#             Achat.objects
#             .select_related("fournisseur", "cancelled_by")
#             .only(
#                 "id", "created_at", "description",
#                 "frais_transport", "frais_douane", "note",
#                 "numero_achat", "montant_total_ht", "montant_total_ttc",
#                 "status", "cancel_reason", "cancelled_at", "cancelled_by_id",
#                 "fournisseur_id",
#             )
#         )

#         date_from_s = getf("date_from")
#         date_to_s   = getf("date_to")

#         if date_from_s and date_to_s:
#             df = datetime.strptime(date_from_s, "%Y-%m-%d").date()
#             dt = datetime.strptime(date_to_s, "%Y-%m-%d").date()
#             if df > dt:
#                 raise ValidationError({"detail": "date_from doit être ≤ date_to."})
#             qs = qs.filter(created_at__date__gte=df, created_at__date__lte=dt)
#         else:
#             # ✅ beaucoup plus robuste pour “année courante”
#             y = timezone.localdate().year
#             qs = qs.filter(created_at__year=y)

#         return qs.order_by(ordering)


# class LotListView(ListAPIView):
#     """
#     Liste des lots :
#     - par défaut : année courante (received_at)
#     - si date_from & date_to sont fournis : intervalle [date_from, date_to] (inclus)
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManager]
#     serializer_class = LotListSerializer
#     pagination_class = None  # pas de pagination

#     @swagger_auto_schema(
#         operation_summary="Lister les lots (année courante par défaut, sinon entre deux dates)",
#         operation_description=(
#             "• Si `date_from` **et** `date_to` sont fournis → filtre **inclusif**.\n"
#             "• Sinon → lots de l’**année courante** (champ `received_at`).\n"
#             "Formats attendus : `YYYY-MM-DD`."
#         ),
#         manual_parameters=[
#             openapi.Parameter(
#                 "date_from",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Borne min incluse (YYYY-MM-DD). À utiliser avec date_to.",
#             ),
#             openapi.Parameter(
#                 "date_to",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Borne max incluse (YYYY-MM-DD). À utiliser avec date_from.",
#             ),
#             openapi.Parameter(
#                 "ordering",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description=(
#                     "Tri: -received_at (défaut), received_at, "
#                     "numero_lot, -numero_lot, "
#                     "nb_lignes, -nb_lignes, "
#                     "quantite, -quantite, "
#                     "poids_total, -poids_total"
#                 ),
#             ),
#         ],
#         responses={200: LotListSerializer(many=True)},
#         tags=["Achats / Arrivages"],
#     )
#     def get(self, request, *args, **kwargs):
#         # Validation légère des dates (retourne 400 propre si invalide)
#         def _check_date(label, val):
#             if not val:
#                 return
#             try:
#                 datetime.strptime(val, "%Y-%m-%d").date()
#             except Exception:
#                 raise ValidationError({label: "Format invalide. Utiliser YYYY-MM-DD."})

#         _check_date("date_from", request.query_params.get("date_from"))
#         _check_date("date_to", request.query_params.get("date_to"))
#         return super().get(request, *args, **kwargs)

#     def get_queryset(self):
#         params = self.request.query_params
#         getf = params.get

#         # Tri autorisé
#         ordering = getf("ordering") or "-received_at"
#         allowed = {
#             "received_at", "-received_at",
#             "numero_lot", "-numero_lot",
#             "nb_lignes", "-nb_lignes",
#             "quantite", "-quantite",
#             "poids_total", "-poids_total",
#         }
#         if ordering not in allowed:
#             ordering = "-received_at"

#         # Base queryset (+ préchargements)
#         qs = (
#             Lot.objects
#             .select_related("achat", "achat__fournisseur")
#             .prefetch_related(
#                 Prefetch(
#                     "lignes",
#                     queryset=ProduitLine.objects.select_related("produit")
#                 )
#             )
#         )

#         # Filtres dates (année courante OU intervalle inclusif)
#         date_from_s = getf("date_from")
#         date_to_s   = getf("date_to")
#         if date_from_s and date_to_s:
#             df = datetime.strptime(date_from_s, "%Y-%m-%d").date()
#             dt = datetime.strptime(date_to_s, "%Y-%m-%d").date()
#             if df > dt:
#                 raise ValidationError({"detail": "date_from doit être ≤ date_to."})
#             qs = qs.filter(received_at__date__gte=df, received_at__date__lte=dt)
#         else:
#             y = timezone.localdate().year
#             qs = qs.filter(received_at__year=y)

#         # Agrégats
#         I0 = Value(0, output_field=IntegerField())
#         D0 = Value(Decimal("0.000"), output_field=DecimalField(max_digits=18, decimal_places=3))

#         poids_produit = Cast(
#             F("lignes__produit__poids"),
#             output_field=DecimalField(max_digits=18, decimal_places=3),
#         )
#         poids_par_ligne = ExpressionWrapper(
#             Coalesce(F("lignes__quantite"), I0) * Coalesce(poids_produit, D0),
#             output_field=DecimalField(max_digits=18, decimal_places=3),
#         )

#         qs = qs.annotate(
#             nb_lignes=Count("lignes", distinct=True),
#             quantite=Coalesce(
#                 Sum("lignes__quantite", output_field=IntegerField()),
#                 I0,
#             ),
#             poids_total=Coalesce(Sum(poids_par_ligne), D0),
#         )

#         return qs.order_by(ordering)



# class LotDetailView(RetrieveAPIView):
#     """
#     Détail d’un lot dans un format “affichage” :
#     - fournisseur
#     - frais
#     - numéro de lot
#     - lignes produits (produit_id, quantite, prix_achat_gramme)
#     """
#     queryset = (
#         Lot.objects
#         .select_related("achat", "achat__fournisseur")
#         .prefetch_related("lignes__produit")
#     )
#     serializer_class = LotDisplaySerializer
#     permission_classes = [IsAuthenticated, IsAdminOrManager]
#     lookup_field = "pk"  # facultatif, c’est le défaut

#     @swagger_auto_schema(
#         operation_id="Details_lot",
#         operation_summary="Détail d’un lot (format affichage personnalisé)",
#         tags=["Achats / Arrivages"],
#     )
#     def get(self, request, *args, **kwargs):
#         return super().get(request, *args, **kwargs)


# ========= VIEW ArrivageMetaUpdateView and ArrivageAdjustmentsView ======================
# ========== 1) META-ONLY ==========
# class ArrivageMetaUpdateView(APIView):
#     """
#     PATCH /api/purchase/arrivage/<lot_id>/meta/
    
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManager]
#     http_method_names = ["patch"]

#     @swagger_auto_schema(
#         operation_id="updateArrivageMeta",
#         operation_summary="MAJ META d’un arrivage (Achat/Lot) — sans toucher quantités/prix",
#         # operation_description=(
#         #     "Met à jour les métadonnées : achat (fournisseur, description, frais) "
#         #     "et lot (description, received_at). **Aucune** modification de quantités/prix/stock."
#         # ),
#         operation_description=dedent("""
#                                     Met à jour les métadonnées : achat (fournisseur, description, frais)
#                                     et lot (description, received_at). **Aucune** modification de quantités/prix/stock.
                                    
#                                     Payloads d’exemple
#                                     META-ONLY (PATCH)
                                    
#                                     ```json
#                                     {
#                                         "achat": {
#                                             "description": "MAJ description & frais",
#                                             "frais_transport": 100.00,
#                                             "frais_douane": 50.00,
#                                             "fournisseur": { "id": 12 }
#                                         },
#                                         "lot": {
#                                             "description": "Arrivage DXB révisé",
#                                             "received_at": "2025-10-28T10:00:00Z"
#                                         }
#                                     }
#                                     ```
#                                     """),
#         request_body=ArrivageMetaUpdateInSerializer,
#         responses={200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found"},
#         tags=["Achats / Arrivages"],
#     )
#     @transaction.atomic
#     def patch(self, request, lot_id: int):
#         lot = get_object_or_404(Lot.objects.select_related("achat", "achat__fournisseur"), pk=lot_id)
#         achat = lot.achat

#         s = ArrivageMetaUpdateInSerializer(data=request.data)
#         s.is_valid(raise_exception=True)
#         v = s.validated_data

#         # Achat
#         if "achat" in v:
#             a = v["achat"]
#             if "fournisseur" in a:
#                 achat.fournisseur = _get_or_upsert_fournisseur(a["fournisseur"])
#             if "description" in a:
#                 achat.description = a["description"]
#             if "frais_transport" in a:
#                 achat.frais_transport = a["frais_transport"]
#             if "frais_douane" in a:
#                 achat.frais_douane = a["frais_douane"]
#             achat.save(update_fields=["fournisseur", "description", "frais_transport", "frais_douane"])

#         # Lot
#         if "lot" in v:
#             lp = v["lot"]
#             if "description" in lp:
#                 lot.description = lp["description"]
#             if "received_at" in lp:
#                 lot.received_at = lp["received_at"]
#             lot.save(update_fields=["description", "received_at"])

#         # Recalc totaux (si frais modifiés)
#         _recalc_totaux_achat(achat)

#         return Response({"detail": "Meta mis à jour.", "lot_id": lot.id, "achat_id": achat.id}, status=200)

