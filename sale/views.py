# from weasyprint import HTML
# import weasyprint
from datetime import date, datetime
from datetime import time as dtime
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.timezone import now
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from openpyxl import Workbook
from openpyxl.styles import Font, numbers
from rest_framework import permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from sale.models import Client, Facture, Paiement, Vente, VenteProduit
from sale.serializers import (FactureSerializer, PaiementCreateSerializer,
                              PaiementSerializer, VenteCreateInSerializer,
                              VenteDetailSerializer, VenteListSerializer)
from sale.services import create_sale_out_movements_for_vente
from stock.models import VendorStock
from store.models import MarquePurete, Produit
from vendor.models import Vendor

# ----------- Helpers existants (repris de ton message) -----------

def _dec(v):
    from decimal import InvalidOperation
    try:
        if v in (None, "", 0, "0"):
            return None
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return None

def _user_profiles(user):
    vp = getattr(user, "staff_vendor_profile", None)
    mp = getattr(user, "staff_manager_profile", None)
    return vp, mp

def _ensure_role_and_bijouterie(user):
    vp, mp = _user_profiles(user)
    if vp and getattr(vp, "verifie", False) and vp.bijouterie_id:
        return vp.bijouterie, "vendor"
    if mp and getattr(mp, "verifie", False) and mp.bijouterie_id:
        return mp.bijouterie, "manager"
    return None, None

def _resolve_vendor_for_line(*, role, user, bijouterie, vendor_email: str | None):
    if role == "vendor":
        v = get_object_or_404(Vendor.objects.select_related("user", "bijouterie"), user=user)
        if not v.verifie:
            raise PermissionError("Votre compte vendor est désactivé.")
        if v.bijouterie_id != bijouterie.id:
            raise PermissionError("Le vendor n'appartient pas à votre bijouterie.")
        return v

    # role == manager
    email = (vendor_email or "").strip()
    if not email:
        raise ValueError("Pour un manager, 'vendor_email' est requis pour affecter la vente.")
    v = Vendor.objects.select_related("user", "bijouterie").filter(user__email__iexact=email).first()
    if not v:
        raise Vendor.DoesNotExist(f"Vendor '{email}' introuvable.")
    if not v.verifie:
        raise PermissionError(f"Le vendor '{email}' est désactivé.")
    if v.bijouterie_id != bijouterie.id:
        raise PermissionError(f"Le vendor '{email}' n'appartient pas à votre bijouterie.")
    return v

def _consume_vendor_stock_for_product(*, vendor: Vendor, produit: Produit, quantite: int):
    """
    Décrémente le stock vendeur pour un produit donné en FIFO par ProduitLine (lot).
    - décrémente VendorStock.quantite_disponible
    - décrémente ProduitLine.quantite_restante
    Retourne: liste de dicts {"pl_id": ..., "qte": ...}
    """
    remaining = int(quantite)
    if remaining <= 0:
        raise ValueError("Quantité à vendre doit être > 0")

    vstocks = (
        VendorStock.objects
        .select_for_update()
        .select_related("produit_line", "produit_line__lot")
        .filter(vendor=vendor, produit_line__produit=produit, quantite_disponible__gt=0)
        .order_by("produit_line__lot__received_at", "produit_line_id")
    )

    moves = []
    for vs in vstocks:
        if remaining == 0:
            break
        dispo = int(vs.quantite_disponible or 0)
        if dispo <= 0:
            continue
        take = min(dispo, remaining)

        # 1) décrémente la dispo vendeur (optimiste + verrou)
        updated_vs = VendorStock.objects.filter(pk=vs.pk, quantite_disponible__gte=take)\
                                        .update(quantite_disponible=F("quantite_disponible") - take)
        if not updated_vs:
            raise ValueError("Conflit de stock détecté, réessayez.")

        # 2) décrémente la quantité restante de la ProduitLine
        from purchase.models import ProduitLine
        updated_pl = ProduitLine.objects.filter(pk=vs.produit_line_id, quantite_restante__gte=take)\
                                        .update(quantite_restante=F("quantite_restante") - take)
        if not updated_pl:
            # rollback local VS pour rester cohérent
            VendorStock.objects.filter(pk=vs.pk).update(quantite_disponible=F("quantite_disponible") + take)
            raise ValueError("Stock de lot insuffisant (quantite_restante).")

        moves.append({"pl_id": vs.produit_line_id, "qte": take})
        remaining -= take

    if remaining > 0:
        raise ValueError(f"Stock vendeur insuffisant pour '{getattr(produit, 'nom', 'produit')}'. Manque {remaining}.")

    return moves

# ----------- Vue -----------

class VenteProduitCreateView(APIView):
    """
    Crée une vente, décrémente le stock vendor (FIFO par ProduitLine),
    met à jour ProduitLine.quantite_restante,
    puis génère une facture PROFORMA NON PAYÉE (numérotation par bijouterie).
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Créer une vente (stock FIFO + facture proforma)",
        request_body=VenteCreateInSerializer,  # ✅ utilise ton serializer d’entrée
        responses={201: openapi.Response("Créé", schema=None)},
        tags=["Ventes"]
    )
    @transaction.atomic
    def post(self, request):
        user = request.user

        # 1) Rôle + bijouterie
        bijouterie, role = _ensure_role_and_bijouterie(user)
        if role not in {"vendor", "manager"} or not bijouterie:
            return Response(
                {"error": "⛔ Accès refusé (vendor/manager vérifié rattaché à une bijouterie requis)."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 2) Valider payload
        in_ser = VenteCreateInSerializer(data=request.data)
        in_ser.is_valid(raise_exception=True)
        payload = in_ser.validated_data
        client_in = payload["client"]
        items = payload["produits"]

        # 3) Client (upsert: par téléphone si fourni, sinon nom+prénom)
        tel = (client_in.get("telephone") or "").strip()
        lookup = {"telephone": tel} if tel else {"nom": client_in["nom"], "prenom": client_in["prenom"]}
        client, _ = Client.objects.get_or_create(
            defaults={"nom": client_in["nom"], "prenom": client_in["prenom"]},
            **lookup
        )

        # 4) Précharge produits par slug
        slugs = [it["slug"] for it in items]
        produits = {
            p.slug: p
            for p in Produit.objects.select_related("marque", "purete").filter(slug__in=slugs)
        }
        missing = [s for s in set(slugs) if s not in produits]
        if missing:
            return Response({"error": f"Produits introuvables: {', '.join(missing)}"}, status=status.HTTP_404_NOT_FOUND)

        # 5) Tarifs (marque, pureté)
        pairs = {(p.marque_id, p.purete_id) for p in produits.values() if p.marque_id and p.purete_id}
        tarifs = {
            (mp.marque_id, mp.purete_id): Decimal(str(mp.prix))
            for mp in MarquePurete.objects.filter(
                marque_id__in=[m for (m, _) in pairs],
                purete_id__in=[r for (_, r) in pairs]
            )
        }

        # 6) Entête de vente
        vente = Vente.objects.create(client=client, created_by=user)

        # 7) Lignes
        for it in items:
            produit = produits[it["slug"]]
            qte = int(it["quantite"])

            # 7.a Vendor pour la ligne
            try:
                vendor = _resolve_vendor_for_line(
                    role=role, user=user, bijouterie=bijouterie, vendor_email=it.get("vendor_email")
                )
            except Vendor.DoesNotExist as e:
                return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
            except PermissionError as e:
                return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
            except ValueError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

            # 7.b Prix par gramme (input prioritaire > 0 ; sinon tarif MP)
            pvg = _dec(it.get("prix_vente_grammes"))
            if not pvg or pvg <= 0:
                key = (produit.marque_id, produit.purete_id)
                pvg = tarifs.get(key)
                if not pvg or pvg <= 0:
                    return Response({
                        "error": f"Tarif manquant pour {produit.nom}.",
                        "solution": "Fournir 'prix_vente_grammes' > 0 ou renseigner Marque/Pureté."
                    }, status=status.HTTP_400_BAD_REQUEST)

            remise = _dec(it.get("remise")) or Decimal("0.00")
            autres = _dec(it.get("autres")) or Decimal("0.00")
            tax    = _dec(it.get("tax")) or Decimal("0.00")

            # 7.c Consommer stock vendeur (FIFO) + MAJ ProduitLine
            try:
                fifo_moves = _consume_vendor_stock_for_product(
                    vendor=vendor, produit=produit, quantite=qte
                )
            except ValueError as e:
                return Response({"error": f"{produit.nom}: {str(e)}"}, status=status.HTTP_409_CONFLICT)

            # 7.d Créer la ligne de vente (les montants sont calculés dans le modèle)
            VenteProduit.objects.create(
                vente=vente, produit=produit, vendor=vendor,
                quantite=qte, prix_vente_grammes=pvg,
                remise=remise, autres=autres, tax=tax,
            )
            # TODO (optionnel) : journaliser fifo_moves en InventoryMovement (SALE_OUT)

        # 8) Totaux & facture proforma
        try:
            vente.mettre_a_jour_montant_total(base="ttc")
        except Exception:
            pass

        facture = Facture.objects.create(
            vente=vente,
            bijouterie=bijouterie,
            montant_total=vente.montant_total,
            status=Facture.STAT_NON_PAYE,
            type_facture=Facture.TYPE_PROFORMA,
            numero_facture=Facture.generer_numero_unique(bijouterie),
        )

        return Response(
            {"facture": FactureSerializer(facture).data,
             "vente": VenteDetailSerializer(vente).data},
            status=status.HTTP_201_CREATED
        )



# -------------------------ListFactureView---------------------------
# --------- Pagination ----------
class FacturePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200


# --------- Helpers ----------
def _user_role(user):
    return getattr(getattr(user, "user_role", None), "role", None)

def _user_bijouterie(user):
    """
    Retourne la bijouterie rattachée selon le profil (vendor/manager/cashier), sinon None.
    """
    vp = getattr(user, "vendor_profile", None)
    if vp and getattr(vp, "verifie", False) and vp.bijouterie_id:
        return vp.bijouterie

    mp = getattr(user, "staff_manager_profile", None)
    if mp and getattr(mp, "verifie", False) and mp.bijouterie_id:
        return mp.bijouterie

    cp = getattr(user, "staff_cashier_profile", None)  # si tu as un profil Cashier relié à user
    if cp and getattr(cp, "verifie", False) and cp.bijouterie_id:
        return cp.bijouterie

    return None

def _parse_date(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None
# -------------------------------END--------------------------------------


# helpers locaux
def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None

def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        # gère 29/02 -> 28/02
        return d.replace(month=2, day=28, year=d.year + years)

def _current_year_bounds_dates():
    today = timezone.localdate()
    y = today.year
    return date(y, 1, 1), date(y, 12, 31)


class ListFactureView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Lister les factures (règles de fenêtre par rôle, recherche, pagination, tri)",
        operation_description=(
            "- **Vendor / Cashier** : fenêtre maximale **3 ans**. Si aucune date fournie → **année en cours**.\n"
            "- **Admin / Manager** : filtrage libre (pas de limite), dates optionnelles.\n"
            "Paramètres optionnels :\n"
            "• `q` (search: n° facture, n° vente, client)\n"
            "• `status` (non_paye|paye)\n"
            "• `type_facture` (proforma|vente_directe|acompte|finale)\n"
            "• `date_from` / `date_to` (YYYY-MM-DD, inclusifs)\n"
            "• `bijouterie_id` (ADMIN uniquement)\n"
            "• `ordering` (-date_creation|date_creation|-montant_total|montant_total|numero_facture|-numero_facture)\n"
            "• `page`, `page_size`"
        ),
        manual_parameters=[
            openapi.Parameter("q", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Recherche: numéro facture, numéro vente, client (nom/prénom/téléphone)"),
            openapi.Parameter("status", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Statut: non_paye | paye"),
            openapi.Parameter("type_facture", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Type: proforma | vente_directe | acompte | finale"),
            openapi.Parameter("date_from", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Date min (YYYY-MM-DD) sur date_creation)"),
            openapi.Parameter("date_to", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Date max (YYYY-MM-DD) sur date_creation)"),
            openapi.Parameter("bijouterie_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="Filtrer par bijouterie (ADMIN uniquement)"),
            openapi.Parameter("ordering", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Tri: -date_creation (défaut), date_creation, "
                                          "-montant_total, montant_total, numero_facture, -numero_facture"),
            openapi.Parameter("page", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="Numéro de page"),
            openapi.Parameter("page_size", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="Taille de page"),
        ],
        responses={200: FactureSerializer(many=True)},
        tags=["Ventes / Factures"],
    )
    def get(self, request):
        user = request.user
        role = _user_role(user)
        if role not in {"admin", "manager", "vendor", "cashier"}:
            return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

        # Base queryset
        qs = (Facture.objects
              .select_related("vente", "vente__client", "bijouterie")
              .prefetch_related("paiements"))

        getf = request.GET.get

        # Portée par rôle (bijouterie)
        if role in {"manager", "vendor", "cashier"}:
            bij = _user_bijouterie(user)
            if not bij:
                return Response(
                    {"error": "Profil non rattaché à une bijouterie vérifiée."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            qs = qs.filter(bijouterie=bij)
        elif role == "admin":
            # admin : peut filtrer par bijouterie_id
            if getf("bijouterie_id"):
                qs = qs.filter(bijouterie_id=getf("bijouterie_id"))

        # Recherche plein texte
        q = (getf("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(numero_facture__icontains=q) |
                Q(vente__numero_vente__icontains=q) |
                Q(vente__client__nom__icontains=q) |
                Q(vente__client__prenom__icontains=q) |
                Q(vente__client__telephone__icontains=q)
            )

        # Filtres simples
        status_v = (getf("status") or "").strip()
        if status_v in {"non_paye", "paye"}:
            qs = qs.filter(status=status_v)

        tf = (getf("type_facture") or "").strip()
        if tf in {"proforma", "vente_directe", "acompte", "finale"}:
            qs = qs.filter(type_facture=tf)

        # --- Fenêtre temporelle ---
        df = _parse_date(getf("date_from"))
        dt = _parse_date(getf("date_to"))
        today = timezone.localdate()

        if role in {"vendor", "cashier"}:
            # défaut : année en cours si aucune borne fournie
            if not df and not dt:
                df, dt = _current_year_bounds_dates()
            elif df and not dt:
                # borne haute = min(from + 3 ans - 1 jour, aujourd’hui)
                dt_cap = min(_add_years(df, 3) - timedelta(days=1), today)
                dt = dt_cap
            elif dt and not df:
                # si seule 'to' fournie → restreint à l’année de 'to' (≤ 1 an)
                df = date(dt.year, 1, 1)

            # validations
            if df and dt and df > dt:
                return Response({"error": "`date_from` doit être ≤ `date_to`."},
                                status=status.HTTP_400_BAD_REQUEST)

            if df and dt:
                max_dt = _add_years(df, 3) - timedelta(days=1)
                if dt > max_dt:
                    return Response(
                        {"error": f"Fenêtre maximale de 3 ans pour ce rôle. `date_to` autorisé ≤ {max_dt}."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                dt = min(dt, today)  # pas au-delà d’aujourd’hui

            # applique filtres
            if df:
                qs = qs.filter(date_creation__date__gte=df)
            if dt:
                qs = qs.filter(date_creation__date__lte=dt)

        else:
            # Admin/Manager : filtrage libre si fourni (sinon pas de borne)
            if df:
                qs = qs.filter(date_creation__date__gte=df)
            if dt:
                qs = qs.filter(date_creation__date__lte=dt)

            # 👉 si tu veux aussi par défaut l’année en cours pour eux, décommente :
            if not df and not dt:
                d1, d2 = _current_year_bounds_dates()
                qs = qs.filter(date_creation__date__gte=d1, date_creation__date__lte=d2)

        # Tri
        ordering = getf("ordering") or "-date_creation"
        allowed = {
            "date_creation", "-date_creation",
            "montant_total", "-montant_total",
            "numero_facture", "-numero_facture",
        }
        if ordering not in allowed:
            ordering = "-date_creation"
        qs = qs.order_by(ordering)

        # Pagination
        paginator = FacturePagination()
        page = paginator.paginate_queryset(qs, request)
        ser = FactureSerializer(page, many=True)
        return paginator.get_paginated_response(ser.data)
# -------------------------END ListFactureView---------------------------


# --------------------------------------------------------------------------
# --- Helpers locaux (adapte si tu les as déjà ailleurs) ---
def _user_role(user) -> str | None:
    return getattr(getattr(user, "user_role", None), "role", None)

def _user_bijouterie(user):
    vp = getattr(user, "vendor_profile", None)
    if vp and getattr(vp, "verifie", False) and vp.bijouterie_id:
        return vp.bijouterie
    mp = getattr(user, "staff_manager_profile", None)
    if mp and getattr(mp, "verifie", False) and mp.bijouterie_id:
        return mp.bijouterie
    cp = getattr(user, "staff_cashier_profile", None)
    if cp and getattr(cp, "verifie", False) and cp.bijouterie_id:
        return cp.bijouterie
    return None


class PaiementFactureView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    ROLES_AUTORISES = {"manager", "cashier"}

    @swagger_auto_schema(
        operation_summary="Enregistrer un paiement sur une facture",
        operation_description=(
            "Enregistre un paiement partiel ou total sur une facture :\n"
            "- Seuls **manager** et **cashier** sont autorisés.\n"
            "- Conversion **PROFORMA → facture** au premier paiement.\n"
            "- **status = payé** uniquement si total payé ≥ montant_total."
        ),
        request_body=PaiementCreateSerializer,
        responses={
            201: "Paiement créé",
            400: "Requête invalide",
            403: "Accès refusé",
            404: "Facture introuvable",
        },
        tags=["Ventes", "Facturation"],
    )
    @transaction.atomic
    def post(self, request, facture_numero: str):
        # 1) Rôle
        role = _user_role(request.user)
        if role not in self.ROLES_AUTORISES:
            return Response({"detail": "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        # 2) Facture (verrou pessimiste)
        numero = (facture_numero or "").strip()
        try:
            facture = (
                Facture.objects
                .select_for_update()
                .select_related("bijouterie")
                .get(numero_facture__iexact=numero)
            )
        except Facture.DoesNotExist:
            return Response({"detail": "Facture introuvable."}, status=status.HTTP_404_NOT_FOUND)

        # 3) Contrôle bijouterie : ne payer que dans SA bijouterie
        user_shop = _user_bijouterie(request.user)
        if user_shop and facture.bijouterie_id != user_shop.id:
            return Response({"detail": "Cette facture n'appartient pas à votre bijouterie."},
                            status=status.HTTP_403_FORBIDDEN)

        # 4) Validation payload
        s = PaiementCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        montant: Decimal = s.validated_data["montant_paye"]
        mode = s.validated_data.get("mode_paiement") or getattr(Paiement, "MODE_CASH", "cash")

        if montant <= Decimal("0"):
            return Response({"detail": "Le montant doit être > 0."}, status=status.HTTP_400_BAD_REQUEST)

        total = facture.montant_total or Decimal("0.00")
        deja = facture.paiements.aggregate(t=Sum("montant_paye"))["t"] or Decimal("0.00")

        if deja >= total:
            return Response({"detail": "La facture est déjà soldée."}, status=status.HTTP_400_BAD_REQUEST)

        if deja + montant > total:
            reste = (total - deja).quantize(Decimal("0.01"))
            return Response({"detail": f"Surpaiement interdit. Reste à payer: {reste}."},
                            status=status.HTTP_400_BAD_REQUEST)

        # 5) Créer paiement (le modèle peut lier cashier via created_by → staff.Cashier)
        paiement = Paiement.objects.create(
            facture=facture,
            montant_paye=montant,
            mode_paiement=mode,
            created_by=request.user,
        )

        # 6) Mettre à jour la facture :
        #    - Au premier paiement, PROFORMA → FACTURE
        #    - Status 'paye' uniquement si total_paye >= montant_total
        maj_fields = []
        if getattr(facture, "type_facture", None) == getattr(Facture, "TYPE_PROFORMA", "proforma"):
            facture.type_facture = getattr(Facture, "TYPE_FACTURE", "facture")
            maj_fields.append("type_facture")

        total_paye = (deja + montant)
        if total_paye >= total and getattr(facture, "status", None) != getattr(Facture, "STAT_PAYE", "paye"):
            facture.status = getattr(Facture, "STAT_PAYE", "paye")
            maj_fields.append("status")

        if maj_fields:
            facture.save(update_fields=maj_fields)

        # 7) Réponse
        return Response({
            "message": "Paiement enregistré",
            "paiement": PaiementSerializer(paiement).data,
            "facture": {
                "numero_facture": facture.numero_facture,
                "type_facture": facture.type_facture,
                "status": facture.status,
                "montant_total": str(facture.montant_total),
                "total_paye": str(total_paye.quantize(Decimal("0.01"))),
                "reste_a_payer": str(max(total - total_paye, Decimal("0.00")).quantize(Decimal("0.01"))),
            }
        }, status=status.HTTP_201_CREATED)
# -------------------END PaiementFactureView-------------------

# -------------------Confirmer Livraison---------------------
# le vendeur confirme la livraison via ConfirmerLivraisonView, 
# ce qui déclenche la sortie de stock réelle (SALE_OUT)
ROLES_LIVRAISON = {"vendor", "manager"}

def _user_role(user):
    """Retourne 'vendor' / 'manager' ou None."""
    # adapte si tu as un autre système ; ici on détecte via présence des profils
    if getattr(user, "staff_vendor_profile", None):
        return "vendor"
    if getattr(user, "staff_manager_profile", None):
        return "manager"
    return None

def _user_bijouterie(user):
    """Bijouterie de l’utilisateur (vendor/manager vérifié), sinon None."""
    vp = getattr(user, "staff_vendor_profile", None)
    if vp and getattr(vp, "verifie", False) and vp.bijouterie_id:
        return vp.bijouterie
    mp = getattr(user, "staff_manager_profile", None)
    if mp and getattr(mp, "verifie", False) and mp.bijouterie_id:
        return mp.bijouterie
    return None

class ConfirmerLivraisonView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Confirmer la livraison (sortie réelle du stock)",
        operation_description=(
            "Marque la vente comme livrée et crée les mouvements d’inventaire **SALE_OUT** "
            "avec décrément du stock vendor. Requiert **facture payée**. "
            "Rôles autorisés : **vendor** / **manager**. "
            "La vente doit appartenir à la même bijouterie que l’utilisateur."
        ),
        responses={200: "OK", 400: "Erreur métier", 403: "Accès refusé", 404: "Introuvable"},
        tags=["Ventes"]
    )
    @transaction.atomic
    def post(self, request, vente_id: int):
        # 1) Rôle + bijouterie
        role = _user_role(request.user)
        if role not in ROLES_LIVRAISON:
            return Response({"error": "Accès refusé (vendor/manager requis)."}, status=status.HTTP_403_FORBIDDEN)

        user_shop = _user_bijouterie(request.user)
        if not user_shop:
            return Response({"error": "Profil non rattaché à une bijouterie vérifiée."},
                            status=status.HTTP_403_FORBIDDEN)

        # 2) Vente + facture
        try:
            vente = (Vente.objects
                     .select_related("facture_vente", "facture_vente__bijouterie")
                     .prefetch_related("produits__produit")
                     .select_for_update()  # verrou pour éviter double livraison concurrente
                     .get(pk=vente_id))
        except Vente.DoesNotExist:
            return Response({"error": "Vente introuvable."}, status=status.HTTP_404_NOT_FOUND)

        facture = getattr(vente, "facture_vente", None)
        if not facture:
            return Response({"error": "Aucune facture liée à cette vente."}, status=status.HTTP_400_BAD_REQUEST)

        # 3) Sécurité bijouterie
        if facture.bijouterie_id != user_shop.id:
            return Response({"error": "Cette vente n’appartient pas à votre bijouterie."},
                            status=status.HTTP_403_FORBIDDEN)

        # 4) Déjà livrée ?
        if vente.delivery_status == Vente.DELIV_DELIVERED:
            # idempotent : ne pas recréer les mouvements
            return Response({
                "message": "Déjà livrée — aucune action.",
                "mouvements_crees": 0,
                "vente": VenteDetailSerializer(vente).data,
                "facture": FactureSerializer(facture).data
            }, status=status.HTTP_200_OK)

        # 5) Facture payée obligatoire
        if facture.status != Facture.STAT_PAYE:
            return Response({"error": "Facture non payée : livraison impossible."},
                            status=status.HTTP_400_BAD_REQUEST)

        # 6) Mouvements + décrément stock + marquer livrée
        try:
            # À toi d’implémenter l’idempotence dans ce service si nécessaire
            created_count = create_sale_out_movements_for_vente(vente, request.user)
        except ValidationError as e:
            msg = getattr(e, "message", None) or (e.messages[0] if getattr(e, "messages", None) else str(e))
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Marquer livrée (timestamp + delivered_by si absent)
        vente.marquer_livree(by_user=request.user)

        # 7) Réponse
        vente.refresh_from_db()
        facture.refresh_from_db()
        return Response(
            {
                "message": "Livraison confirmée.",
                "mouvements_crees": created_count,
                "vente": VenteDetailSerializer(vente).data,
                "facture": FactureSerializer(facture).data,
            },
            status=status.HTTP_200_OK
        )
# --------------------End Confirmer Livraison------------------

# ----------------------Liste vente-------------------------
# ---------- Helpers ----------
def _parse_date_or_none(s: str | None) -> date | None:
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d").date()

def _aware_range(d_from: date, d_to: date, tz):
    """Retourne [start, end) à partir de deux dates inclusives."""
    start_dt = timezone.make_aware(datetime.combine(d_from, dtime.min), tz)
    end_dt   = timezone.make_aware(datetime.combine(d_to + timedelta(days=1), dtime.min), tz)
    return start_dt, end_dt

def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        # 29/02 -> 28/02 si besoin
        return d.replace(month=2, day=28, year=d.year + years)

def _current_year_bounds(tz):
    today = timezone.localdate()
    y = today.year
    return _aware_range(date(y, 1, 1), date(y, 12, 31), tz)


# ---------- View ----------
# --- helpers rôle ---
def _role(user):
    if getattr(user, "is_superuser", False) or user.groups.filter(name__in=["admin","manager"]).exists():
        return "admin" if user.is_superuser else "manager"
    if getattr(user, "staff_vendor_profile", None):
        return "vendor"
    if getattr(user, "staff_cashier_profile", None):
        return "cashier"
    return None

# --- helpers date ---
def _aware_range(d_from: date, d_to: date, tz):
    start_dt = timezone.make_aware(datetime.combine(d_from, dtime.min), tz)
    end_dt   = timezone.make_aware(datetime.combine(d_to + timedelta(days=1), dtime.min), tz)
    return start_dt, end_dt

def _parse_date_or_none(s):
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d").date()

def _bounds_current_year(tz):
    today = timezone.localdate()
    return _aware_range(date(today.year, 1, 1), date(today.year, 12, 31), tz)


class VenteListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Liste des ventes",
        operation_description=(
            "- **Vendor** : uniquement ses ventes (VenteProduit.vendor = lui), **année en cours seulement** (from/to ignorés).\n"
            "- **Cashier** : uniquement les ventes où il a encaissé ≥1 paiement, **année en cours seulement** (from/to ignorés).\n"
            "- **Admin/Manager** : tout le périmètre, **par défaut année en cours**, mais `?from=YYYY-MM-DD&to=YYYY-MM-DD` peuvent couvrir n’importe quelle plage (bornes inclusives)."
        ),
        manual_parameters=[
            openapi.Parameter("from", openapi.IN_QUERY, type=openapi.TYPE_STRING, format="date", required=False),
            openapi.Parameter("to",   openapi.IN_QUERY, type=openapi.TYPE_STRING, format="date", required=False),
        ],
        responses={200: openapi.Response('Liste des ventes', VenteListSerializer(many=True))}
    )
    def get(self, request):
        role = _role(request.user)
        if role is None:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        tz = timezone.get_current_timezone()

        # Base queryset selon rôle
        if role == "vendor":
            v = getattr(request.user, "staff_vendor_profile", None)
            if not v:
                return Response({"error": "Aucun profil vendor associé."}, status=400)
            qs = Vente.objects.filter(produits__vendor=v)
            # borne: année en cours (from/to ignorés)
            start_dt, end_dt = _bounds_current_year(tz)

        elif role == "cashier":
            qs = Vente.objects.filter(facture_vente__paiements__created_by=request.user)
            # borne: année en cours (from/to ignorés)
            start_dt, end_dt = _bounds_current_year(tz)

        else:  # admin / manager
            qs = Vente.objects.all()
            from_s = request.query_params.get("from")
            to_s   = request.query_params.get("to")

            if not from_s and not to_s:
                # par défaut: année en cours
                start_dt, end_dt = _bounds_current_year(tz)
            else:
                d_from = _parse_date_or_none(from_s)
                d_to   = _parse_date_or_none(to_s)
                if d_from and not d_to:
                    d_to = d_from  # si une seule date, on retourne ce jour
                if d_to and not d_from:
                    d_from = d_to  # idem
                if not d_from or not d_to:
                    return Response({"error": "Format de date invalide. Utiliser YYYY-MM-DD."}, status=400)
                if d_from > d_to:
                    return Response({"error": "`from` doit être ≤ `to`."}, status=400)
                start_dt, end_dt = _aware_range(d_from, d_to, tz)

        qs = (qs.filter(created_at__gte=start_dt, created_at__lt=end_dt)
                .distinct()
                .order_by("-created_at"))

        return Response(VenteListSerializer(qs, many=True).data, status=200)
# -----------------------End List vente----------------------

# ---------- -Rapport Ventes Mensuel-------------------------
def _aware_range_month(year: int, month: int, tz):
    first = date(year, month, 1)
    # dernier jour du mois
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    start_dt = timezone.make_aware(datetime.combine(first, datetime.min.time()), tz)
    end_dt   = timezone.make_aware(datetime.combine(last + timedelta(days=1), datetime.min.time()), tz)
    return start_dt, end_dt


class RapportVentesMensuelAPIView(APIView):
    
    """
        JSON (par défaut)
            GET /api/rapports/ventes-mensuel?mois=2025-10
        Excel export
            GET /api/rapports/ventes-mensuel?mois=2025-10&export=excel
            (optionnel) &vendor_id=42 ou &vendor_email=vendeur@ex.sn
    """
    permission_classes = [IsAuthenticated]
    allowed_roles = {"admin", "manager"}

    def _role(self, user):
        if getattr(user, "is_superuser", False) or user.groups.filter(name__in=["admin", "manager"]).exists():
            return "admin" if user.is_superuser else "manager"
        return None

    @swagger_auto_schema(
        operation_summary="Rapport mensuel des ventes (admin/manager)",
        operation_description=(
            "Filtre par `mois=YYYY-MM`. Optionnel : `vendor_id` **ou** `vendor_email`.\n"
            "Retourne JSON par défaut. Ajoute `?export=excel` pour télécharger un fichier .xlsx."
        ),
        manual_parameters=[
            openapi.Parameter("mois", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Mois au format YYYY-MM (ex: 2025-06)"),
            openapi.Parameter("vendor_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, required=False),
            openapi.Parameter("vendor_email", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=False),
            openapi.Parameter("export", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              enum=["excel"], required=False, description="Exporter en Excel"),
        ],
        responses={200: openapi.Response(description="Rapport JSON ou Excel")}
    )
    def get(self, request):
        if self._role(request.user) not in self.allowed_roles:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        # ---- 1) Mois
        today = timezone.localdate()
        mois_str = request.GET.get("mois") or today.strftime("%Y-%m")
        try:
            annee, mois_num = map(int, mois_str.split("-"))
        except Exception:
            return Response({"detail": "Format invalide. Utiliser YYYY-MM."}, status=400)

        tz = timezone.get_current_timezone()
        start_dt, end_dt = _aware_range_month(annee, mois_num, tz)

        # ---- 2) Base queryset
        lines = (VenteProduit.objects
                 .select_related("vente", "produit", "vendor__user", "vendor__bijouterie")
                 .filter(vente__created_at__gte=start_dt,
                         vente__created_at__lt=end_dt))

        # ---- 3) Filtre vendeur
        vendor_id = request.GET.get("vendor_id")
        vendor_email = request.GET.get("vendor_email")
        vendeur_nom = "Tous les vendeurs"

        if vendor_id and vendor_email:
            return Response({"detail": "Fournir soit vendor_id soit vendor_email, pas les deux."}, status=400)

        if vendor_id:
            v = get_object_or_404(Vendor.objects.select_related("user"), pk=vendor_id)
            lines = lines.filter(vendor=v)
            vendeur_nom = f"{getattr(v.user, 'username', '')} ({getattr(v.user, 'email', '')})".strip()
        elif vendor_email:
            v = get_object_or_404(Vendor.objects.select_related("user"), user__email__iexact=vendor_email.strip())
            lines = lines.filter(vendor=v)
            vendeur_nom = f"{getattr(v.user, 'username', '')} ({getattr(v.user, 'email', '')})".strip()

        # ---- 4) Agrégats
        total_ht  = lines.aggregate(t=Sum("sous_total_prix_vente_ht"))["t"] or Decimal("0.00")
        total_ttc = lines.aggregate(t=Sum("prix_ttc"))["t"] or Decimal("0.00")
        ventes_distinctes = lines.values("vente_id").distinct().count()

        # ---- 5) Export Excel ?
        if (request.GET.get("export") or "").lower() == "excel":
            filename = f"rapport_ventes_{mois_str.replace('-', '')}"
            if vendeur_nom != "Tous les vendeurs":
                # nettoie pour filename
                safe_vendor = vendeur_nom.replace(" ", "_").replace("@", "_at_").replace("(", "").replace(")", "")
                filename += f"_{safe_vendor}"
            filename += ".xlsx"
            return self._export_excel(
                mois_str, vendeur_nom, total_ht, total_ttc, ventes_distinctes, lines, filename
            )

        # ---- 6) JSON normal
        ventes_list = [{
            "date": l.vente.created_at.date().isoformat(),
            "produit": getattr(l.produit, "nom", "Produit supprimé"),
            "slug": getattr(l.produit, "slug", None),
            "quantite": l.quantite,
            "montant_ht": float(l.sous_total_prix_vente_ht or 0),
            "montant_ttc": float(l.prix_ttc or 0),
            "vendor": {
                "id": getattr(l.vendor, "id", None),
                "username": getattr(getattr(l.vendor, "user", None), "username", None),
                "email": getattr(getattr(l.vendor, "user", None), "email", None),
                "bijouterie": getattr(getattr(l.vendor, "bijouterie", None), "nom", None),
            } if l.vendor_id else None
        } for l in lines.order_by("vente__created_at", "id")]

        return Response({
            "mois": mois_str,
            "vendeur": vendeur_nom,
            "ventes_distinctes": ventes_distinctes,
            "total_ht": float(total_ht),
            "total_ttc": float(total_ttc),
            "lignes": ventes_list
        }, status=200)

    # ---------- Excel builder ----------
    def _export_excel(self, mois_str, vendeur_nom, total_ht, total_ttc, ventes_distinctes, lines_qs, filename):
        wb = Workbook()

        # ---- Sheet 1: Résumé
        ws = wb.active
        ws.title = "Résumé"
        bold = Font(bold=True)

        rows = [
            ("Mois", mois_str),
            ("Vendeur", vendeur_nom),
            ("Ventes distinctes", ventes_distinctes),
            ("Total HT", float(total_ht)),
            ("Total TTC", float(total_ttc)),
        ]
        ws.append(["Clé", "Valeur"])
        ws["A1"].font = ws["B1"].font = bold

        for r in rows:
            ws.append(r)

        # Formats
        ws["B4"].number_format = numbers.FORMAT_NUMBER_COMMA_SEPARATED1
        ws["B5"].number_format = numbers.FORMAT_NUMBER_COMMA_SEPARATED1

        # Ajuste largeur colonnes
        ws.column_dimensions["A"].width = 22
        ws.column_dimensions["B"].width = 40

        # ---- Sheet 2: Lignes
        ws2 = wb.create_sheet("Lignes")
        header = [
            "Date", "Vente #", "Produit", "Slug",
            "Quantité", "Montant HT", "Montant TTC",
            "Vendor", "Vendor Email", "Bijouterie",
        ]
        ws2.append(header)
        for c in range(1, len(header)+1):
            ws2.cell(row=1, column=c).font = bold

        for l in lines_qs.order_by("vente__created_at", "id"):
            ws2.append([
                l.vente.created_at.strftime("%Y-%m-%d"),
                getattr(l.vente, "numero_vente", ""),
                getattr(l.produit, "nom", "Produit supprimé"),
                getattr(l.produit, "slug", None),
                int(l.quantite or 0),
                float(l.sous_total_prix_vente_ht or 0),
                float(l.prix_ttc or 0),
                getattr(getattr(l.vendor, "user", None), "username", None),
                getattr(getattr(l.vendor, "user", None), "email", None),
                getattr(getattr(l.vendor, "bijouterie", None), "nom", None),
            ])

        # Formats + UI
        ws2.auto_filter.ref = ws2.dimensions
        ws2.freeze_panes = "A2"
        # colonnes: E=Quantité, F=HT, G=TTC
        ws2.column_dimensions["A"].width = 12
        ws2.column_dimensions["B"].width = 22
        ws2.column_dimensions["C"].width = 32
        ws2.column_dimensions["D"].width = 24
        ws2.column_dimensions["E"].width = 10
        ws2.column_dimensions["F"].width = 14
        ws2.column_dimensions["G"].width = 14
        ws2.column_dimensions["H"].width = 18
        ws2.column_dimensions["I"].width = 24
        ws2.column_dimensions["J"].width = 18

        for row in ws2.iter_rows(min_row=2, min_col=6, max_col=7):
            for cell in row:
                cell.number_format = numbers.FORMAT_NUMBER_COMMA_SEPARATED1

        # ---- Sheet 3: Par produit
        ws3 = wb.create_sheet("Par produit")
        ws3.append(["Produit", "Slug", "Quantité", "Total HT", "Total TTC"])
        for c in range(1, 6):
            ws3.cell(row=1, column=c).font = bold

        agg_prod = (lines_qs
                    .values("produit__nom", "produit__slug")
                    .annotate(q=Sum("quantite"),
                              ht=Sum("sous_total_prix_vente_ht"),
                              ttc=Sum("prix_ttc"))
                    .order_by("produit__nom"))
        for r in agg_prod:
            ws3.append([
                r["produit__nom"] or "Produit supprimé",
                r["produit__slug"],
                int(r["q"] or 0),
                float(r["ht"] or 0),
                float(r["ttc"] or 0),
            ])
        ws3.auto_filter.ref = ws3.dimensions
        ws3.freeze_panes = "A2"
        ws3.column_dimensions["A"].width = 32
        ws3.column_dimensions["B"].width = 24
        ws3.column_dimensions["C"].width = 10
        ws3.column_dimensions["D"].width = 16
        ws3.column_dimensions["E"].width = 16
        for row in ws3.iter_rows(min_row=2, min_col=4, max_col=5):
            for cell in row:
                cell.number_format = numbers.FORMAT_NUMBER_COMMA_SEPARATED1

        # ---- Sheet 4: Par vendeur
        ws4 = wb.create_sheet("Par vendeur")
        ws4.append(["Vendor", "Email", "Bijouterie", "Quantité", "Total HT", "Total TTC"])
        for c in range(1, 7):
            ws4.cell(row=1, column=c).font = bold

        agg_vendor = (lines_qs
                      .values("vendor__user__username", "vendor__user__email", "vendor__bijouterie__nom")
                      .annotate(q=Sum("quantite"),
                                ht=Sum("sous_total_prix_vente_ht"),
                                ttc=Sum("prix_ttc"))
                      .order_by("vendor__user__username"))
        for r in agg_vendor:
            ws4.append([
                r["vendor__user__username"],
                r["vendor__user__email"],
                r["vendor__bijouterie__nom"],
                int(r["q"] or 0),
                float(r["ht"] or 0),
                float(r["ttc"] or 0),
            ])
        ws4.auto_filter.ref = ws4.dimensions
        ws4.freeze_panes = "A2"
        ws4.column_dimensions["A"].width = 18
        ws4.column_dimensions["B"].width = 28
        ws4.column_dimensions["C"].width = 18
        ws4.column_dimensions["D"].width = 10
        ws4.column_dimensions["E"].width = 16
        ws4.column_dimensions["F"].width = 16
        for row in ws4.iter_rows(min_row=2, min_col=5, max_col=6):
            for cell in row:
                cell.number_format = numbers.FORMAT_NUMBER_COMMA_SEPARATED1

        # ---- Retour HTTP
        bio = BytesIO()
        wb.save(bio)
        bio.seek(0)

        resp = Response(bio.getvalue(),
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp
# -------------- End Rapport Ventes Mensuel ---------------------

