from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.permissions import IsAdminOrManager
from inventory.models import Bucket, InventoryMovement, MovementType
from stock.models import Stock
from store.models import Produit

from .models import Achat, Fournisseur, Lot, ProduitLine
from .serializers import (AchatCreateResponseSerializer, AchatSerializer,
                          ArrivageAdjustmentsInSerializer,
                          ArrivageCreateInSerializer,
                          ArrivageMetaUpdateInSerializer, LotListSerializer)

# def generate_numero_lot() -> str:
#     """Génère LOT-YYYYMMDD-XXXX ; XXXX repart à 0001 chaque jour."""
#     today = timezone.localdate().strftime("%Y%m%d")
#     prefix = f"LOT-{today}-"
#     last = (
#         Lot.objects
#         .filter(numero_lot__startswith=prefix)
#         .order_by("-numero_lot")
#         .values_list("numero_lot", flat=True)
#         .first()
#     )
#     if last:
#         try:
#             seq = int(last.rsplit("-", 1)[-1]) + 1
#         except ValueError:
#             seq = 1
#     else:
#         seq = 1
#     return f"{prefix}{seq:04d}"


# class ArrivageCreateView(APIView):
#     """
#     Création d’un arrivage simple :

#     - Crée un Achat (fournisseur + frais)
#     - Crée 1 Lot rattaché à cet achat, avec numero_lot auto (LOT-YYYYMMDD-XXXX)
#     - Crée les ProduitLine (quantité achetée, prix_achat_gramme)
#     - Pousse 100% de la quantité en stock "Réserve"
#     - Log automatiquement un mouvement d’inventaire PURCHASE_IN (EXTERNAL -> RESERVED)
#     - Recalcule les totaux de l’achat via Achat.update_total()
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManager]
#     http_method_names = ["post"]

#     @swagger_auto_schema(
#         operation_id="createArrivage",
#         operation_summary="Créer un arrivage (lot auto-numéroté) et initialiser l'inventaire",
#         operation_description=(
#             "Crée un Achat, un Lot avec un numéro auto (LOT-YYYYMMDD-XXXX), les lignes produits (quantités), "
#             "pousse 100% du stock en Réserve, log un mouvement PURCHASE_IN (EXTERNAL → RESERVED) "
#             "et valorise l'achat au gramme si fourni."
#         ),
#         request_body=ArrivageCreateInSerializer,
#         responses={
#             201: AchatCreateResponseSerializer,
#             400: "Bad Request",
#             401: "Unauthorized",
#             403: "Forbidden",
#         },
#         tags=["Achats / Arrivages"],
#     )
#     @transaction.atomic
#     def post(self, request):
#         s = ArrivageCreateInSerializer(data=request.data)
#         s.is_valid(raise_exception=True)
#         v = s.validated_data

#         lots_in = v["lots"]

#         # --------- Validation produits ---------
#         pids = {row["produit_id"] for row in lots_in}
#         exists = set(Produit.objects.filter(id__in=pids).values_list("id", flat=True))
#         missing = pids - exists
#         if missing:
#             return Response(
#                 {"lots": f"Produit(s) introuvable(s): {sorted(list(missing))}."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         missing_weight = list(
#             Produit.objects
#             .filter(id__in=pids, poids__isnull=True)
#             .values_list("id", flat=True)
#         )
#         if missing_weight:
#             return Response(
#                 {"lots": f"Produit(s) sans poids: {missing_weight}."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         # --------- Fournisseur ---------
#         f = v["fournisseur"]
#         fournisseur, _ = Fournisseur.objects.get_or_create(
#             telephone=(f.get("telephone") or "").strip() or None,
#             defaults={
#                 "nom": f["nom"],
#                 "prenom": f.get("prenom", ""),
#             },
#         )

#         # --------- Achat ---------
#         achat = Achat.objects.create(
#             fournisseur=fournisseur,
#             description=v.get("description", ""),
#             frais_transport=v.get("frais_transport", Decimal("0")),
#             frais_douane=v.get("frais_douane", Decimal("0")),
#         )

#         # --------- Lot (header) ---------
#         for _ in range(5):
#             numero_lot = generate_numero_lot()
#             try:
#                 lot = Lot.objects.create(
#                     achat=achat,
#                     numero_lot=numero_lot,
#                     description=v.get("description", ""),
#                     received_at=timezone.now(),
#                 )
#                 break
#             except IntegrityError:
#                 continue
#         else:
#             return Response(
#                 {"detail": "Impossible de générer un numéro de lot unique."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         # --------- Lignes produit + Stock Réserve + Mouvements ---------
#         produits_by_id = {
#             p.id: p
#             for p in Produit.objects.filter(id__in=pids).only("id", "poids", "nom")
#         }

#         for row in lots_in:
#             produit = produits_by_id[row["produit_id"]]
#             qte = int(row["quantite"])
#             prix_achat_gramme = row.get("prix_achat_gramme")

#             # ✅ ProduitLine cohérente avec ton modèle
#             pl = ProduitLine.objects.create(
#                 lot=lot,
#                 produit=produit,
#                 prix_achat_gramme=prix_achat_gramme,
#                 quantite=qte,
#             )

#             # ✅ Stock initial en Réserve (bijouterie=None = bucket RESERVED)
#             Stock.objects.create(
#                 produit_line=pl,
#                 bijouterie=None,
#                 quantite_allouee=qte,
#                 quantite_disponible=qte,
#             )

#             # ✅ Mouvement d’inventaire : EXTERNAL -> RESERVED
#             unit_cost = None
#             if prix_achat_gramme is not None and produit.poids is not None:
#                 try:
#                     unit_cost = (
#                         Decimal(str(prix_achat_gramme)) * Decimal(str(produit.poids))
#                     ).quantize(Decimal("0.01"))
#                 except (InvalidOperation, TypeError, ValueError):
#                     unit_cost = None

#             InventoryMovement.objects.create(
#                 produit=produit,
#                 movement_type=MovementType.PURCHASE_IN,
#                 qty=qte,
#                 unit_cost=unit_cost,
#                 lot=lot,
#                 reason="Arrivage initial",
#                 src_bucket=Bucket.EXTERNAL,
#                 dst_bucket=Bucket.RESERVED,
#                 achat=achat,
#                 occurred_at=timezone.now(),
#                 created_by=request.user,
#             )

#         # --------- Totaux Achat via logique centrale ---------
#         achat.update_total(save=True)

#         # ✅ Réponse : détail du lot + infos achat “aplaties”
#         # out = AchatCreateResponseSerializer(lot).data
#         # return Response(out, status=status.HTTP_201_CREATED)
#         return Response("ok", status=status.HTTP_201_CREATED)


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


# 👇 ton exemple de payload
ARRIVAGE_CREATE_EXAMPLE = {
    "fournisseur": {
        "nom": "Fournisseur Test",
        "prenom": "Alpha",
        "telephone": "770000000"
    },
    "description": "Arrivage test",
    "frais_transport": "5000.00",
    "frais_douane": "0.00",
    "lots": [
        {
            "produit_id": 1,
            "quantite": 10,
            "prix_achat_gramme": "42000.00"
        }
    ]
}


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
        # soit tu laisses le serializer :
        # request_body=ArrivageCreateInSerializer,
        # soit tu forces un schema + example détaillé :
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["fournisseur", "lots"],
            properties={
                "fournisseur": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "nom": openapi.Schema(type=openapi.TYPE_STRING),
                        "prenom": openapi.Schema(type=openapi.TYPE_STRING),
                        "telephone": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
                "description": openapi.Schema(type=openapi.TYPE_STRING),
                "frais_transport": openapi.Schema(type=openapi.TYPE_STRING, example="5000.00"),
                "frais_douane": openapi.Schema(type=openapi.TYPE_STRING, example="0.00"),
                "lots": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        required=["produit_id", "quantite"],
                        properties={
                            "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER, example=1),
                            "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, example=10),
                            "prix_achat_gramme": openapi.Schema(
                                type=openapi.TYPE_STRING,
                                example="42000.00",
                            ),
                        },
                    ),
                ),
            },
            example=ARRIVAGE_CREATE_EXAMPLE,
        ),
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

            pl = ProduitLine.objects.create(
                lot=lot,
                produit=produit,
                prix_achat_gramme=prix_achat_gramme,
                quantite=qte,
            )

            Stock.objects.create(
                produit_line=pl,
                bijouterie=None,
                quantite_allouee=qte,
                quantite_disponible=qte,
            )

            unit_cost = None
            if prix_achat_gramme is not None and produit.poids is not None:
                try:
                    unit_cost = (
                        Decimal(str(prix_achat_gramme)) * Decimal(str(produit.poids))
                    ).quantize(Decimal("0.01"))
                except (InvalidOperation, TypeError, ValueError):
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

        achat.update_total(save=True)

        out = AchatCreateResponseSerializer(lot).data
        return Response(out, status=status.HTTP_201_CREATED)


class LotListView(ListAPIView):
    """
    Liste des lots :
    - par défaut : année courante (sur received_at)
    - si date_from & date_to sont fournis : intervalle [date_from, date_to] (inclus)
    Filtres optionnels :
    - numero_lot (contient)
    - numero_achat (exact)
    - fournisseur_id
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]
    serializer_class = LotListSerializer
    # pagination_class = None  # si tu veux tout sans pagination

    @swagger_auto_schema(
        operation_id="listLots",
        operation_summary="Lister les lots avec filtres",
        operation_description=(
            "• Si `date_from` **et** `date_to` sont fournis → filtre inclusif sur `received_at`.\n"
            "• Sinon → lots de l’**année courante** (received_at).\n\n"
            "Filtres supplémentaires :\n"
            "- `numero_lot` (recherche partielle, icontains)\n"
            "- `numero_achat` (exact)\n"
            "- `fournisseur_id` (id du fournisseur de l'achat)\n\n"
            "Formats de date : `YYYY-MM-DD`."
        ),
        manual_parameters=[
            openapi.Parameter(
                "date_from",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Borne min incluse sur received_at (YYYY-MM-DD). Avec date_to.",
            ),
            openapi.Parameter(
                "date_to",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Borne max incluse sur received_at (YYYY-MM-DD). Avec date_from.",
            ),
            openapi.Parameter(
                "numero_lot",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Recherche partielle sur le numéro de lot (icontains).",
            ),
            openapi.Parameter(
                "numero_achat",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Filtre exact sur le numéro d'achat.",
            ),
            openapi.Parameter(
                "fournisseur_id",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                description="Filtre sur l'id du fournisseur.",
            ),
            openapi.Parameter(
                "ordering",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Tri: -received_at (défaut), received_at, numero_lot, -numero_lot",
            ),
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
        _check_date("date_from", qp.get("date_from"))
        _check_date("date_to", qp.get("date_to"))

        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        params = self.request.query_params
        getf = params.get

        # --------- Tri ---------
        ordering = getf("ordering") or "-received_at"
        allowed = {"received_at", "-received_at", "numero_lot", "-numero_lot"}
        if ordering not in allowed:
            ordering = "-received_at"

        # --------- Base queryset + agrégats ---------
        qs = (
            Lot.objects
            .select_related("achat", "achat__fournisseur")
            .annotate(
                nb_lignes=Coalesce(Count("lignes", distinct=True), 0),
                quantite_total=Coalesce(Sum("lignes__quantite"), 0),
            )
        )

        # --------- Filtre par dates (sur received_at) ---------
        date_from_s = getf("date_from")
        date_to_s = getf("date_to")

        if date_from_s and date_to_s:
            df = datetime.strptime(date_from_s, "%Y-%m-%d").date()
            dt = datetime.strptime(date_to_s, "%Y-%m-%d").date()
            if df > dt:
                raise ValidationError({"detail": "date_from doit être ≤ date_to."})
            qs = qs.filter(received_at__date__gte=df, received_at__date__lte=dt)
        else:
            # année courante sur received_at
            y = timezone.localdate().year
            qs = qs.filter(received_at__year=y)

        # --------- Autres filtres ---------
        numero_lot = getf("numero_lot")
        if numero_lot:
            qs = qs.filter(numero_lot__icontains=numero_lot)

        numero_achat = getf("numero_achat")
        if numero_achat:
            qs = qs.filter(achat__numero_achat=numero_achat)

        fournisseur_id = getf("fournisseur_id")
        if fournisseur_id:
            try:
                fid = int(fournisseur_id)
                if fid > 0:
                    qs = qs.filter(achat__fournisseur_id=fid)
            except ValueError:
                # on ignore un id non entier plutôt que lever une 500
                pass

        return qs.order_by(ordering)


class AchatListView(ListAPIView):
    """
    Liste des achats :
    - par défaut : année courante
    - si date_from & date_to sont fournis : intervalle [date_from, date_to] (inclus)
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]
    serializer_class = AchatSerializer
    # pagination_class = None  # si tu veux désactiver la pagination DRF

    @swagger_auto_schema(
        operation_id="listAchats",
        operation_summary="Lister les achats (année courante par défaut, sinon entre deux dates)",
        operation_description=(
            "• Si `date_from` **et** `date_to` sont fournis → filtre inclusif sur `created_at__date`.\n"
            "• Sinon → achats de l’**année courante** (basé sur la date serveur).\n\n"
            "Formats attendus : `YYYY-MM-DD`."
        ),
        manual_parameters=[
            openapi.Parameter(
                "date_from",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Borne min incluse (YYYY-MM-DD). Utiliser avec `date_to`."
            ),
            openapi.Parameter(
                "date_to",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Borne max incluse (YYYY-MM-DD). Utiliser avec `date_from`."
            ),
            openapi.Parameter(
                "ordering",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
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
                datetime.datetime.strptime(val, "%Y-%m-%d").date()
            except Exception:
                raise ValidationError({label: "Format invalide. Utiliser YYYY-MM-DD."})

        _check_date("date_from", request.query_params.get("date_from"))
        _check_date("date_to", request.query_params.get("date_to"))
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        params = self.request.query_params
        getf = params.get

        # -------- Tri --------
        ordering = getf("ordering") or "-created_at"
        allowed = {"created_at", "-created_at", "numero_achat", "-numero_achat"}
        if ordering not in allowed:
            ordering = "-created_at"

        # -------- Base queryset --------
        qs = (
            Achat.objects
            .select_related("fournisseur")
            .prefetch_related("lots__lignes__produit")
        )

        # -------- Filtre dates --------
        date_from_s = getf("date_from")
        date_to_s = getf("date_to")

        if date_from_s and date_to_s:
            df = datetime.datetime.strptime(date_from_s, "%Y-%m-%d").date()
            dt = datetime.datetime.strptime(date_to_s, "%Y-%m-%d").date()
            if df > dt:
                raise ValidationError({"detail": "date_from doit être ≤ date_to."})
            qs = qs.filter(created_at__date__gte=df, created_at__date__lte=dt)
        else:
            # Année courante basée sur la date serveur
            year = timezone.localdate().year
            qs = qs.filter(created_at__year=year)

        return qs.order_by(ordering)


class ArrivageMetaUpdateView(APIView):
    """
    PATCH /api/achat/arrivage/{lot_id}/meta/

    Met à jour UNIQUEMENT les informations documentaires :
    - côté Achat : description, frais_transport, frais_douane, fournisseur
    - côté Lot   : description, received_at

    ❌ Aucun impact sur le stock ou les mouvements d'inventaire.
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
            200: AchatCreateResponseSerializer,
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
            Lot.objects.select_related("achat", "achat__fournisseur"),
            pk=lot_id,
        )
        achat = lot.achat

        # ----- Validation payload -----
        s = ArrivageMetaUpdateInSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        # ====================
        #  MAJ côté Achat
        # ====================
        achat_data = data.get("achat")
        if achat_data:
            # description
            if "description" in achat_data:
                achat.description = achat_data.get("description") or ""

            # frais
            if "frais_transport" in achat_data:
                achat.frais_transport = achat_data["frais_transport"]
            if "frais_douane" in achat_data:
                achat.frais_douane = achat_data["frais_douane"]

            # fournisseur (ref / upsert)
            fournisseur_data = achat_data.get("fournisseur")
            if fournisseur_data:
                fournisseur_obj = None

                # 1) on privilégie l'id s'il est fourni
                fid = fournisseur_data.get("id")
                if fid:
                    fournisseur_obj = get_object_or_404(Fournisseur, pk=fid)
                else:
                    # 2) sinon upsert par téléphone
                    tel = (fournisseur_data.get("telephone") or "").strip() or None
                    if tel:
                        fournisseur_obj, _ = Fournisseur.objects.get_or_create(
                            telephone=tel,
                            defaults={
                                "nom": fournisseur_data.get("nom") or "",
                                "prenom": fournisseur_data.get("prenom") or "",
                                "address": "",
                            },
                        )

                if fournisseur_obj:
                    achat.fournisseur = fournisseur_obj

            # on recalculera les totaux plus bas
            achat.save()

        # ====================
        #  MAJ côté Lot
        # ====================
        lot_data = data.get("lot")
        if lot_data:
            update_fields = []
            if "description" in lot_data:
                lot.description = lot_data.get("description") or ""
                update_fields.append("description")
            if "received_at" in lot_data:
                lot.received_at = lot_data["received_at"]
                update_fields.append("received_at")

            if update_fields:
                lot.save(update_fields=update_fields)

        # Recalcul des totaux achat (car frais peuvent avoir changé)
        if achat_data:
            achat.update_total(save=True)

        # ----- Réponse : même format que ArrivageCreateView -----
        out = AchatCreateResponseSerializer(lot).data
        return Response(out, status=status.HTTP_200_OK)
    



# ---------------------------Adjustement-----------------------------
class ArrivageAdjustmentsView(APIView):
    """
    Ajustements d’un arrivage (lot) :

    - PURCHASE_IN :
        * ajoute une nouvelle ProduitLine au lot
        * crédite le stock RÉSERVE (bijouterie=None)
        * log un mouvement d’inventaire PURCHASE_IN (EXTERNAL -> RESERVED)

    - CANCEL_PURCHASE :
        * retire une partie de la quantité d’une ProduitLine existante
        * déverse la quantité de la RÉSERVE vers EXTERNAL
        * interdit le retrait si des allocations bijouterie existent
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
            "- `PURCHASE_IN` : `produit_id`, `quantite`, `prix_achat_gramme` (optionnel)\n"
            "- `CANCEL_PURCHASE` : `produit_line_id`, `quantite`\n\n"
            "**Règles :**\n"
            "- Les ajouts vont en bucket RÉSERVE (bijouterie=None).\n"
            "- Les retraits ne peuvent porter que sur la quantité disponible en RÉSERVE.\n"
            "- Si des allocations bijouterie existent pour la ligne, le retrait est refusé."
        ),
        request_body=ArrivageAdjustmentsInSerializer,
        responses={
            200: openapi.Response(
                description="Ajustements appliqués.",
                examples={
                    "application/json": {
                        "detail": "Ajustements appliqués.",
                        "lot_id": 1,
                        "achat_id": 3,
                    }
                },
            ),
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
        },
        tags=["Achats / Arrivages"],
    )
    @transaction.atomic
    def post(self, request, lot_id: int):
        lot = get_object_or_404(Lot.objects.select_related("achat"), pk=lot_id)
        achat = lot.achat

        s = ArrivageAdjustmentsInSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        actions = s.validated_data["actions"]

        for idx, act in enumerate(actions):
            t = act["type"]
            q = int(act["quantite"])
            reason = act.get("reason") or ""

            # ------------- PURCHASE_IN : ajout d’une nouvelle ligne -------------
            if t == "PURCHASE_IN":
                pid = int(act["produit_id"])
                produit = get_object_or_404(Produit.objects.only("id", "poids"), pk=pid)
                prix_achat_gramme = act.get("prix_achat_gramme")

                pl = ProduitLine.objects.create(
                    lot=lot,
                    produit=produit,
                    prix_achat_gramme=prix_achat_gramme,
                    quantite=q,
                )

                # Stock en RÉSERVE (bijouterie=None)
                Stock.objects.create(
                    produit_line=pl,
                    bijouterie=None,
                    quantite_allouee=q,
                    quantite_disponible=q,
                )

                # Valorisation unitaire éventuelle
                unit_cost = None
                if prix_achat_gramme is not None and produit.poids is not None:
                    try:
                        unit_cost = (
                            Decimal(str(prix_achat_gramme)) * Decimal(str(produit.poids))
                        ).quantize(Decimal("0.01"))
                    except (InvalidOperation, TypeError, ValueError):
                        unit_cost = None

                InventoryMovement.objects.create(
                    produit=produit,
                    movement_type=MovementType.PURCHASE_IN,
                    qty=q,
                    unit_cost=unit_cost,
                    lot=lot,
                    reason=reason or "Ajout ligne (arrivage)",
                    src_bucket=Bucket.EXTERNAL,
                    dst_bucket=Bucket.RESERVED,
                    achat=achat,
                    occurred_at=timezone.now(),
                    created_by=request.user,
                )

            # ------------- CANCEL_PURCHASE : retrait partiel d’une ligne -------------
            elif t == "CANCEL_PURCHASE":
                pl_id = int(act["produit_line_id"])
                pl = get_object_or_404(
                    ProduitLine.objects.select_related("produit", "lot"),
                    pk=pl_id,
                )
                if pl.lot_id != lot.id:
                    return Response(
                        {
                            f"actions[{idx}]": (
                                f"ProduitLine {pl_id} n'appartient pas au lot {lot.id}."
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # interdit si allocations bijouterie existent
                has_alloc = Stock.objects.filter(
                    produit_line=pl,
                    bijouterie__isnull=False,
                    quantite_allouee__gt=0,
                ).exists()
                if has_alloc:
                    return Response(
                        {
                            f"actions[{idx}]": (
                                f"Ligne {pl_id}: des allocations bijouterie existent, "
                                "retrait interdit."
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # cherche la réserve
                reserve = Stock.objects.filter(
                    produit_line=pl, bijouterie__isnull=True
                ).first()
                disponible = int(reserve.quantite_disponible or 0) if reserve else 0
                if q > disponible:
                    return Response(
                        {
                            f"actions[{idx}]": (
                                f"Réduction {q} > disponible en réserve ({disponible}) "
                                f"pour la ligne {pl_id}."
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # met à jour la ligne
                pl.quantite = max(0, int((pl.quantite or 0) - q))
                pl.save(update_fields=["quantite"])

                # met à jour le stock de réserve
                if reserve:
                    reserve.quantite_allouee = max(
                        0, int((reserve.quantite_allouee or 0) - q)
                    )
                    reserve.quantite_disponible = max(
                        0, int((reserve.quantite_disponible or 0) - q)
                    )
                    reserve.save(
                        update_fields=["quantite_allouee", "quantite_disponible"]
                    )

                # mouvement inventaire : RESERVED -> EXTERNAL
                InventoryMovement.objects.create(
                    produit=pl.produit,
                    movement_type=MovementType.CANCEL_PURCHASE,
                    qty=q,
                    unit_cost=None,
                    lot=lot,
                    reason=reason or "Retrait partiel (arrivage)",
                    src_bucket=Bucket.RESERVED,
                    dst_bucket=Bucket.EXTERNAL,
                    achat=achat,
                    occurred_at=timezone.now(),
                    created_by=request.user,
                )

            else:
                return Response(
                    {f"actions[{idx}]": f"Type inconnu: {t}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Recalcule les totaux de l'achat après ajustements
        achat.update_total(save=True)

        return Response(
            {"detail": "Ajustements appliqués.", "lot_id": lot.id, "achat_id": achat.id},
            status=status.HTTP_200_OK,
        )