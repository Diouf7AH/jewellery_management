# from weasyprint import HTML
# import weasyprint
from datetime import date, datetime
from datetime import time as dtime
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, Paginator
from django.db import transaction
from django.db.models import F, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from openpyxl import Workbook
from openpyxl.styles import Font, numbers
from rest_framework import permissions, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.permissions import get_role_name
from backend.renderers import UserRenderer
from sale.models import Client, Facture, Paiement, Vente, VenteProduit
from sale.serializers import (FactureSerializer, PaiementCreateSerializer,
                              PaiementSerializer, VenteCreateInSerializer,
                              VenteDetailSerializer, VenteListSerializer)
from sale.services import create_sale_out_movements_for_vente
from store.models import Bijouterie, MarquePurete, Produit
from vendor.models import Vendor

from .serializers import FactureListSerializer
from .utils import (_ensure_role_and_bijouterie, _user_bijouterie_facture,
                    subtract_months)

# ----------- Helpers existants (repris de ton message) -----------

def _dec(v):
    from decimal import InvalidOperation
    try:
        if v in (None, "", 0, "0"):
            return None
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return None

# def _user_profiles(user):
#     vp = getattr(user, "staff_vendor_profile", None)
#     mp = getattr(user, "staff_manager_profile", None)
#     return vp, mp

# def _ensure_role_and_bijouterie(user):
#     vp, mp = _user_profiles(user)
#     if vp and getattr(vp, "verifie", False) and vp.bijouterie_id:
#         return vp.bijouterie, "vendor"
#     if mp and getattr(mp, "verifie", False) and mp.bijouterie_id:
#         return mp.bijouterie, "manager"
#     return None, None

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

# ----------- Vue -----------


# class VenteProduitCreateView(APIView):
#     """
#     Crée une vente (lignes + client), 
#     puis génère une facture PROFORMA NON PAYÉE (numérotation par bijouterie).
#     Le stock vendeur sera consommé plus tard, au moment de la livraison/paiement confirmé.
#     """
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Créer une vente (stock FIFO + facture proforma)",
#         request_body=VenteCreateInSerializer,
#         responses={201: openapi.Response("Créé", schema=None)},
#         tags=["Ventes"],
#     )
#     @transaction.atomic
#     def post(self, request):
#         role = _user_role(request.user)

#         if role not in {"admin","manager","vendor","cashier"}:
#             return Response({"message": "⛔ Accès refusé"}, status=403)

#         qs = Facture.objects.select_related("vente","vente__client","bijouterie")

#         if role in {"manager","vendor","cashier"}:
#             bij = _user_bijouterie_facture(request.user)
#             if not bij:
#                 return Response({"error": "Profil non rattaché à une bijouterie vérifiée."}, status=400)
#             qs = qs.filter(bijouterie=bij)

#         # 2) Valider payload
#         in_ser = VenteCreateInSerializer(data=request.data)
#         in_ser.is_valid(raise_exception=True)
#         payload = in_ser.validated_data
#         client_in = payload["client"]
#         items = payload["produits"]

#         # 3) Client (upsert: par téléphone si fourni, sinon nom+prénom)
#         tel = (client_in.get("telephone") or "").strip()
#         if tel:
#             lookup = {"telephone": tel}
#         else:
#             lookup = {"nom": client_in["nom"], "prenom": client_in["prenom"]}

#         client, _ = Client.objects.get_or_create(
#             defaults={"nom": client_in["nom"], "prenom": client_in["prenom"]},
#             **lookup,
#         )

#         # 4) Précharge produits par slug
#         slugs = [it["slug"] for it in items]
#         produits = {
#             p.slug: p
#             for p in Produit.objects.select_related("marque", "purete").filter(slug__in=slugs)
#         }
#         missing = [s for s in set(slugs) if s not in produits]
#         if missing:
#             return Response(
#                 {"error": f"Produits introuvables: {', '.join(missing)}"},
#                 status=status.HTTP_404_NOT_FOUND,
#             )

#         # 5) Tarifs (marque, pureté)
#         pairs = {
#             (p.marque_id, p.purete_id)
#             for p in produits.values()
#             if p.marque_id and p.purete_id
#         }
#         tarifs = {
#             (mp.marque_id, mp.purete_id): Decimal(str(mp.prix))
#             for mp in MarquePurete.objects.filter(
#                 marque_id__in=[m for (m, _) in pairs],
#                 purete_id__in=[r for (_, r) in pairs],
#             )
#         }

#         # 6) Entête de vente
#         vente = Vente.objects.create(
#             client=client,
#             created_by=user,
#             bijouterie=bijouterie,  # 💡 important
#         )

#         # 7) Lignes
#         for it in items:
#             produit = produits[it["slug"]]
#             qte = int(it["quantite"])

#             # 7.a Vendor pour la ligne
#             try:
#                 vendor = _resolve_vendor_for_line(
#                     role=role,
#                     user=user,
#                     bijouterie=bijouterie,
#                     vendor_email=it.get("vendor_email"),
#                 )
#             except Vendor.DoesNotExist as e:
#                 return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
#             except PermissionError as e:
#                 return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
#             except ValueError as e:
#                 return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

#             # 7.b Prix par gramme (input prioritaire > 0 ; sinon tarif MP)
#             pvg = _dec(it.get("prix_vente_grammes"))
#             if not pvg or pvg <= 0:
#                 key = (produit.marque_id, produit.purete_id)
#                 pvg = tarifs.get(key)
#                 if not pvg or pvg <= 0:
#                     return Response(
#                         {
#                             "error": f"Tarif manquant pour {produit.nom}.",
#                             "solution": "Fournir 'prix_vente_grammes' > 0 ou renseigner Marque/Pureté.",
#                         },
#                         status=status.HTTP_400_BAD_REQUEST,
#                     )

#             remise = _dec(it.get("remise")) or Decimal("0.00")
#             autres = _dec(it.get("autres")) or Decimal("0.00")
#             tax = _dec(it.get("tax")) or Decimal("0.00")


#             # 7.d Créer la ligne de vente
#             VenteProduit.objects.create(
#                 vente=vente,
#                 produit=produit,
#                 vendor=vendor,
#                 quantite=qte,
#                 prix_vente_grammes=pvg,
#                 remise=remise,
#                 autres=autres,
#                 tax=tax,
#             )
#             # TODO: le SALE_OUT et le journal d’inventaire seront gérés dans ConfirmerLivraisonView.

#         # 8) Totaux & facture proforma
#         try:
#             vente.mettre_a_jour_montant_total(base="ttc")
#         except Exception:
#             # on évite de casser la vente pour un problème de calculeur
#             pass

#         facture = Facture.objects.create(
#             vente=vente,
#             bijouterie=bijouterie,
#             montant_total=vente.montant_total,
#             status=Facture.STAT_NON_PAYE,
#             type_facture=Facture.TYPE_PROFORMA,
#             numero_facture=Facture.generer_numero_unique(bijouterie),
#         )

#         return Response(
#             {
#                 "facture": FactureSerializer(facture).data,
#                 "vente": VenteDetailSerializer(vente).data,
#             },
#             status=status.HTTP_201_CREATED,
#         )

class VenteProduitCreateView(APIView):
    """
    Crée une vente (lignes + client),
    puis génère une facture PROFORMA NON PAYÉE (numérotation par bijouterie).
    Le stock vendeur sera consommé plus tard (livraison/paiement confirmé).
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Créer une vente + facture proforma",
        request_body=VenteCreateInSerializer,
        responses={201: openapi.Response("Créé")},
        tags=["Ventes"],
    )
    @transaction.atomic
    def post(self, request):
        user = request.user

        # 1) Rôle + bijouterie
        bijouterie, role = _ensure_role_and_bijouterie(user)
        if role not in {"vendor", "manager"} or not bijouterie:
            return Response(
                {"error": "⛔ Accès refusé ou bijouterie manquante."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 2) Valider payload
        in_ser = VenteCreateInSerializer(data=request.data)
        in_ser.is_valid(raise_exception=True)
        payload = in_ser.validated_data
        client_in = payload["client"]
        items = payload["produits"]

        # 3) Client (upsert: téléphone si fourni sinon nom+prénom)
        tel = (client_in.get("telephone") or "").strip()
        lookup = {"telephone": tel} if tel else {"nom": client_in["nom"], "prenom": client_in["prenom"]}

        client, _ = Client.objects.get_or_create(
            defaults={"nom": client_in["nom"], "prenom": client_in["prenom"], "telephone": tel or None},
            **lookup,
        )

        # 4) Précharger produits (par slug)
        slugs = [it["slug"] for it in items]
        produits_qs = Produit.objects.select_related("marque", "purete").filter(slug__in=slugs)
        produits = {p.slug: p for p in produits_qs}

        missing = [s for s in set(slugs) if s not in produits]
        if missing:
            return Response(
                {"error": f"Produits introuvables: {', '.join(missing)}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 5) Charger tarifs MarquePurete (fallback prix_vente_grammes)
        pairs = {(p.marque_id, p.purete_id) for p in produits.values() if p.marque_id and p.purete_id}
        tarifs = {
            (mp.marque_id, mp.purete_id): Decimal(str(mp.prix))
            for mp in MarquePurete.objects.filter(
                marque_id__in=[m for (m, _) in pairs],
                purete_id__in=[r for (_, r) in pairs],
            )
        }

        # 6) Créer vente
        vente = Vente.objects.create(
            client=client,
            created_by=user,
            bijouterie=bijouterie,
        )

        # 7) Créer lignes
        for it in items:
            produit = produits[it["slug"]]
            qte = int(it["quantite"])

            # vendor de la ligne
            try:
                vendor = _resolve_vendor_for_line(
                    role=role,
                    user=user,
                    bijouterie=bijouterie,
                    vendor_email=it.get("vendor_email"),
                )
            except Vendor.DoesNotExist as e:
                return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
            except PermissionError as e:
                return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
            except ValueError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

            # prix/gramme
            pvg = _dec(it.get("prix_vente_grammes"))
            if not pvg or pvg <= 0:
                key = (produit.marque_id, produit.purete_id)
                pvg = tarifs.get(key)
                if not pvg or pvg <= 0:
                    return Response(
                        {"error": f"Tarif manquant pour {produit.nom}."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            VenteProduit.objects.create(
                vente=vente,
                produit=produit,
                vendor=vendor,
                quantite=qte,
                prix_vente_grammes=pvg,
                remise=_dec(it.get("remise")) or Decimal("0.00"),
                autres=_dec(it.get("autres")) or Decimal("0.00"),
                tax=_dec(it.get("tax")) or Decimal("0.00"),
            )

        # 8) Totaux + facture proforma
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
            {
                "facture": FactureSerializer(facture).data,
                "vente": VenteDetailSerializer(vente).data,
            },
            status=status.HTTP_201_CREATED,
        )

# -------------------------ListFactureView---------------------------

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


# class ListFactureView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Lister les factures (règles de fenêtre par rôle, recherche, tri)",
#         operation_description=(
#             "- **Vendor / Cashier** : factures de leur bijouterie, fenêtre maximale **3 ans**. "
#             "Si aucune date fournie → **année en cours**.\n"
#             "- **Admin / Manager** : filtrage libre (pas de limite de durée), dates optionnelles.\n\n"
#             "Paramètres optionnels :\n"
#             "• `q` (search: n° facture, n° vente, client)\n"
#             "• `status` (non_paye|paye)\n"
#             "• `type_facture` (proforma|facture|acompte|finale)\n"
#             "• `date_from` / `date_to` (YYYY-MM-DD, inclusifs, appliqués sur `date_creation`)\n"
#             "• `bijouterie_id` (ADMIN uniquement)\n"
#             "• `ordering` (-date_creation|date_creation|-montant_total|montant_total|numero_facture|-numero_facture)\n"
#             "\n⚠️ Pas de pagination : toutes les factures correspondant aux filtres sont renvoyées."
#         ),
#         manual_parameters=[
#             openapi.Parameter(
#                 "q",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Recherche: numéro facture, numéro vente, client (nom/prénom/téléphone)",
#             ),
#             openapi.Parameter(
#                 "status",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Statut: non_paye | paye",
#             ),
#             openapi.Parameter(
#                 "type_facture",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Type: proforma | facture | acompte | finale",
#             ),
#             openapi.Parameter(
#                 "date_from",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Date min (YYYY-MM-DD) sur date_creation",
#             ),
#             openapi.Parameter(
#                 "date_to",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Date max (YYYY-MM-DD) sur date_creation",
#             ),
#             openapi.Parameter(
#                 "bijouterie_id",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_INTEGER,
#                 description="Filtrer par bijouterie (ADMIN uniquement)",
#             ),
#             openapi.Parameter(
#                 "ordering",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description=(
#                     "Tri: -date_creation (défaut), date_creation, "
#                     "-montant_total, montant_total, numero_facture, -numero_facture"
#                 ),
#             ),
#         ],
#         responses={200: FactureSerializer(many=True)},
#         tags=["Ventes / Factures"],
#     )
#     def get(self, request):
#         role = get_role_name(request.user)
#         if role not in {"admin", "manager", "vendor", "cashier"}:
#             return Response({"message": "⛔ Accès refusé"}, status=403)
        
#         qs = (
#             Facture.objects
#             .select_related("vente", "vente__client", "bijouterie")
#             .prefetch_related("paiements")
#         )

#         getf = request.GET.get

#         # --- Portée bijouterie par rôle ---
#         if role in {"manager", "vendor", "cashier"}:
#             bij = _user_bijouterie(request.user)
#             if not bij:
#                 return Response(
#                     {"error": "Profil non rattaché à une bijouterie vérifiée."},
#                     status=status.HTTP_400_BAD_REQUEST,
#                 )
#             qs = qs.filter(bijouterie=bij)

#         elif role == "admin":
#             bij_id = getf("bijouterie_id")
#             if bij_id:
#                 try:
#                     bij_id = int(bij_id)
#                 except ValueError:
#                     return Response(
#                         {"bijouterie_id": "Doit être un entier."},
#                         status=status.HTTP_400_BAD_REQUEST,
#                     )
#                 qs = qs.filter(bijouterie_id=bij_id)

#         # --- Recherche plein texte ---
#         q = (getf("q") or "").strip()
#         if q:
#             qs = qs.filter(
#                 Q(numero_facture__icontains=q)
#                 | Q(vente__numero_vente__icontains=q)
#                 | Q(vente__client__nom__icontains=q)
#                 | Q(vente__client__prenom__icontains=q)
#                 | Q(vente__client__telephone__icontains=q)
#             )

#         # --- Filtres simples (status, type_facture) ---
#         status_v = (getf("status") or "").strip()
#         if status_v in {"non_paye", "paye"}:
#             qs = qs.filter(status=status_v)

#         tf = (getf("type_facture") or "").strip()
#         if tf in {"proforma", "facture", "acompte", "finale"}:
#             qs = qs.filter(type_facture=tf)

#         # --- Fenêtre temporelle ---
#         df = _parse_date(getf("date_from"))
#         dt = _parse_date(getf("date_to"))
#         today = timezone.localdate()

#         if role in {"vendor", "cashier"}:
#             # Si aucune date → année en cours
#             if not df and not dt:
#                 df, dt = _current_year_bounds_dates()
#             elif df and not dt:
#                 # dt = min(df + 3 ans - 1 jour, aujourd'hui)
#                 dt_cap = min(_add_years(df, 3) - timedelta(days=1), today)
#                 dt = dt_cap
#             elif dt and not df:
#                 # si seulement date_to → max 3 ans en arrière ou début d’année
#                 df = max(_add_years(dt, -3), date(dt.year, 1, 1))

#             if df and dt and df > dt:
#                 return Response(
#                     {"error": "`date_from` doit être ≤ `date_to`."},
#                     status=status.HTTP_400_BAD_REQUEST,
#                 )

#             if df and dt:
#                 max_dt = _add_years(df, 3) - timedelta(days=1)
#                 if dt > max_dt:
#                     return Response(
#                         {
#                             "error": (
#                                 "Fenêtre maximale de 3 ans pour ce rôle. "
#                                 f"`date_to` autorisé ≤ {max_dt}."
#                             )
#                         },
#                         status=status.HTTP_400_BAD_REQUEST,
#                     )
#                 dt = min(dt, today)

#             if df:
#                 qs = qs.filter(date_creation__date__gte=df)
#             if dt:
#                 qs = qs.filter(date_creation__date__lte=dt)

#         else:  # admin / manager
#             if df:
#                 qs = qs.filter(date_creation__date__gte=df)
#             if dt:
#                 qs = qs.filter(date_creation__date__lte=dt)
#             # pas de restriction auto si df/dt absents

#         # --- Tri ---
#         ordering = getf("ordering") or "-date_creation"
#         allowed = {
#             "date_creation",
#             "-date_creation",
#             "montant_total",
#             "-montant_total",
#             "numero_facture",
#             "-numero_facture",
#         }
#         if ordering not in allowed:
#             ordering = "-date_creation"
#         qs = qs.order_by(ordering)

#         ser = FactureSerializer(qs, many=True)
#         return Response(ser.data, status=status.HTTP_200_OK)

# class ListFactureView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Lister les factures (règles de fenêtre par rôle, recherche, tri)",
#         operation_description=(
#             "- **Vendor / Cashier** : factures de leur bijouterie, fenêtre maximale **3 ans**. "
#             "Si aucune date fournie → **année en cours**.\n"
#             "- **Admin / Manager** : filtrage libre (pas de limite de durée), dates optionnelles.\n\n"
#             "Paramètres optionnels :\n"
#             "• `q` (search: n° facture, n° vente, client)\n"
#             "• `status` (non_paye|paye)\n"
#             "• `type_facture` (proforma|facture|acompte|finale)\n"
#             "• `date_from` / `date_to` (YYYY-MM-DD, inclusifs, appliqués sur `date_creation`)\n"
#             "• `bijouterie_id` (ADMIN uniquement)\n"
#             "• `ordering` (-date_creation|date_creation|-montant_total|montant_total|numero_facture|-numero_facture)\n"
#             "\n⚠️ Pas de pagination : toutes les factures correspondant aux filtres sont renvoyées."
#         ),
#         manual_parameters=[
#         openapi.Parameter("q", openapi.IN_QUERY, type=openapi.TYPE_STRING,
#                           description="Recherche: numéro facture, numéro vente, client"),
#         openapi.Parameter("status", openapi.IN_QUERY, type=openapi.TYPE_STRING,
#                           description="Statut: non_paye | paye"),
#         openapi.Parameter("type_facture", openapi.IN_QUERY, type=openapi.TYPE_STRING,
#                           description="Type: proforma | facture | acompte | finale"),
#         openapi.Parameter("date_from", openapi.IN_QUERY, type=openapi.TYPE_STRING,
#                           description="Date min (YYYY-MM-DD) sur date_creation"),
#         openapi.Parameter("date_to", openapi.IN_QUERY, type=openapi.TYPE_STRING,
#                           description="Date max (YYYY-MM-DD) sur date_creation"),
#         openapi.Parameter("bijouterie_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
#                           description="Filtrer par bijouterie (ADMIN uniquement)"),
#         openapi.Parameter("ordering", openapi.IN_QUERY, type=openapi.TYPE_STRING,
#                           description="Tri: -date_creation, date_creation, -montant_total, montant_total, ..."),
#     ],
#     responses={200: FactureSerializer(many=True)},
#     tags=["Ventes / Factures"],
#     )
#     def get(self, request):
#         role = get_role_name(request.user)
#         if role not in {"admin", "manager", "vendor", "cashier"}:
#             return Response({"message": "⛔ Accès refusé"}, status=403)

#         qs = Facture.objects.select_related("vente", "vente__client", "bijouterie")
#         getf = request.GET.get  # ✅ IMPORTANT
#         # ---degub---
#         print("DEBUG GET params:", dict(request.GET))
#         print("DEBUG role:", role)
#         # ---debug---

#         # --- Portée bijouterie ---
#         if role in {"manager", "vendor", "cashier"}:
#             # ---degub---
#             import inspect

#             from staff.models import Cashier

#             print("DEBUG user:", request.user.id, request.user.email)
#             print("DEBUG role:", get_role_name(request.user))
#             print("DEBUG cashier exists:",
#                 list(Cashier.objects.filter(user=request.user, verifie=True).values("id","bijouterie_id")))
#             print("DEBUG _user_bijouterie file:", inspect.getsourcefile(_user_bijouterie))
#             # ---debug---
#             bij = _user_bijouterie(request.user)
#             if not bij:
#                 return Response(
#                     {"error": "Profil non rattaché à une bijouterie vérifiée."},
#                     status=400,
#                 )
#             qs = qs.filter(bijouterie=bij)

#         elif role == "admin":
#             bij_id = getf("bijouterie_id")
#             if bij_id:
#                 try:
#                     bij_id = int(bij_id)
#                 except ValueError:
#                     return Response({"bijouterie_id": "Doit être un entier."}, status=400)
#                 qs = qs.filter(bijouterie_id=bij_id)

#         # --- Recherche ---
#         q = (getf("q") or "").strip()
#         if q:
#             qs = qs.filter(
#                 Q(numero_facture__icontains=q)
#                 | Q(vente__numero_vente__icontains=q)
#                 | Q(vente__client__nom__icontains=q)
#                 | Q(vente__client__prenom__icontains=q)
#                 | Q(vente__client__telephone__icontains=q)
#             )

#         # --- Filtres ---
#         status_v = (getf("status") or "").strip()
#         if status_v in {"non_paye", "paye"}:
#             qs = qs.filter(status=status_v)

#         tf = (getf("type_facture") or "").strip()
#         if tf in {"proforma", "facture", "acompte", "finale"}:
#             qs = qs.filter(type_facture=tf)

#         # --- Dates ---
#         df = _parse_date(getf("date_from"))
#         dt = _parse_date(getf("date_to"))
#         today = timezone.localdate()

#         if role in {"vendor", "cashier"}:
#             if not df and not dt:
#                 df, dt = _current_year_bounds_dates()
#             elif df and not dt:
#                 dt = min(_add_years(df, 3) - timedelta(days=1), today)
#             elif dt and not df:
#                 df = max(_add_years(dt, -3), date(dt.year, 1, 1))

#             if df and dt and df > dt:
#                 return Response({"error": "`date_from` doit être ≤ `date_to`."}, status=400)

#             if df and dt:
#                 max_dt = _add_years(df, 3) - timedelta(days=1)
#                 if dt > max_dt:
#                     return Response(
#                         {"error": f"Fenêtre maximale de 3 ans. `date_to` autorisé ≤ {max_dt}."},
#                         status=400,
#                     )
#                 dt = min(dt, today)

#             if df:
#                 qs = qs.filter(date_creation__date__gte=df)
#             if dt:
#                 qs = qs.filter(date_creation__date__lte=dt)

#         else:  # admin / manager
#             if df:
#                 qs = qs.filter(date_creation__date__gte=df)
#             if dt:
#                 qs = qs.filter(date_creation__date__lte=dt)

#         # --- Tri ---
#         ordering = getf("ordering") or "-date_creation"
#         allowed = {
#             "date_creation", "-date_creation",
#             "montant_total", "-montant_total",
#             "numero_facture", "-numero_facture",
#         }
#         if ordering not in allowed:
#             ordering = "-date_creation"

#         qs = qs.order_by(ordering)

#         return Response(FactureSerializer(qs, many=True).data, status=200)

# class ListFactureView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Lister les factures (filtre numero_facture)",
#         operation_description=(
#             "- **Admin** : toutes les factures (toutes bijouteries)\n"
#             "- **Manager / Vendor / Cashier** : uniquement les factures de leur bijouterie\n"
#             "- Filtre unique : `numero_facture` (partiel accepté)"
#         ),
#         manual_parameters=[
#             openapi.Parameter(
#                 "numero_facture",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Numéro exact ou partiel de la facture",
#             ),
#         ],
#         responses={200: FactureSerializer(many=True)},
#         tags=["Ventes / Factures"],
#     )
#     def get(self, request):
#         role = get_role_name(request.user)

#         if role not in {"admin", "manager", "vendor", "cashier"}:
#             return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

#         qs = Facture.objects.select_related("bijouterie", "vente", "vente__client")

#         # ✅ Scope bijouterie pour manager/vendor/cashier
#         if role in {"manager", "vendor", "cashier"}:
#             bij = _user_bijouterie_facture(request.user)
#             if not bij:
#                 return Response(
#                     {"error": "Profil non rattaché à une bijouterie vérifiée."},
#                     status=status.HTTP_400_BAD_REQUEST,
#                 )
#             qs = qs.filter(bijouterie=bij)

#         # ✅ Filtre unique
#         numero = (request.GET.get("numero_facture") or "").strip()
#         if numero:
#             qs = qs.filter(numero_facture__icontains=numero)

#         qs = qs.order_by("-date_creation")
#         return Response(FactureSerializer(qs, many=True).data, status=status.HTTP_200_OK)


DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100

class ListFactureView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Lister les factures (status + fenêtre 18 mois / 3 ans + pagination)",
        manual_parameters=[
            openapi.Parameter("status", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="non_paye | paye (optionnel)"),
            openapi.Parameter("numero_facture", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Numéro partiel (optionnel)"),
            openapi.Parameter("page", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="Page (optionnel)"),
            openapi.Parameter("page_size", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="Taille page (optionnel, max 100)"),
        ],
        responses={200: FactureListSerializer(many=True)},
        tags=["Ventes / Factures"],
    )
    def get(self, request):
        user = request.user
        role = get_role_name(user)

        if role not in {"admin", "manager", "vendor", "cashier"}:
            return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

        qs = Facture.objects.select_related("bijouterie", "vente", "vente__client")

        # scope bijouterie
        if role in {"manager", "vendor", "cashier"}:
            bij = _user_bijouterie_facture(user)
            if not bij:
                return Response({"error": "Profil non rattaché à une bijouterie vérifiée."}, status=400)
            qs = qs.filter(bijouterie=bij)

        # fenêtre automatique
        # today = timezone.localdate()
        # months = 36 if role == "admin" else 18
        # min_date = subtract_months(today, months)
        # qs = qs.filter(date_creation__date__gte=min_date)
        
        now = timezone.now()
        months = 36 if role == "admin" else 18
        min_datetime = now - timedelta(days=months * 30)
        qs = qs.filter(date_creation__gte=min_datetime)

        # filtre status optionnel
        status_q = (request.GET.get("status") or "").strip().lower()
        if status_q in {"non_paye", "paye"}:
            qs = qs.filter(status=status_q)

        # filtre numero_facture optionnel
        numero = (request.GET.get("numero_facture") or "").strip()
        if numero:
            qs = qs.filter(numero_facture__icontains=numero)

        qs = qs.order_by("-date_creation")

        # pagination
        try:
            page = int(request.GET.get("page", 1))
        except ValueError:
            page = 1
        try:
            page_size = int(request.GET.get("page_size", DEFAULT_PAGE_SIZE))
        except ValueError:
            page_size = DEFAULT_PAGE_SIZE
        page_size = max(1, min(page_size, MAX_PAGE_SIZE))

        paginator = Paginator(qs, page_size)
        try:
            page_obj = paginator.page(page)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)

        return Response(
            {
                "count": paginator.count,
                "page": page_obj.number,
                "page_size": page_size,
                "num_pages": paginator.num_pages,
                "results": FactureListSerializer(page_obj.object_list, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


# -------------------------END ListFactureView---------------------------

# --------------------------ListFacturesAPayerView---------------------------
# class ListFacturesAPayerView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Lister les factures à payer (NON PAYÉES)",
#         operation_description=(
#             "- **Vendor / Cashier** : factures NON PAYÉES de leur bijouterie, fenêtre maximale **3 ans**. "
#             "Si aucune date fournie → **année en cours**.\n"
#             "- **Admin / Manager** : factures NON PAYÉES, filtrage libre (dates optionnelles).\n\n"
#             "Paramètres optionnels :\n"
#             "• `q` (search: n° facture, n° vente, client)\n"
#             "• `type_facture` (proforma|facture|acompte|finale)\n"
#             "• `date_from` / `date_to` (YYYY-MM-DD, inclusifs, appliqués sur `date_creation`)\n"
#             "• `bijouterie_id` (ADMIN uniquement)\n"
#             "• `ordering` (-date_creation|date_creation|-montant_total|montant_total|numero_facture|-numero_facture)\n"
#         ),
#         tags=["Ventes / Factures"],
#         responses={200: FactureSerializer(many=True)},
#     )
#     def get(self, request):
#         user = request.user
#         role = _user_role(user)

#         # 🔐 rôles autorisés (cashier inclus)
#         if role not in {"admin", "manager", "vendor", "cashier"}:
#             return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

#         qs = (
#             Facture.objects
#             .select_related("vente", "vente__client", "bijouterie")
#             .prefetch_related("paiements")
#             .filter(status=Facture.STAT_NON_PAYE)  # 💡 seulement NON PAYÉES
#         )

#         getf = request.GET.get

#         # --- Portée bijouterie par rôle ---
#         if role in {"manager", "vendor", "cashier"}:
            
#             bij = _user_bijouterie_facture(user)
#             if not bij:
#                 return Response(
#                     {"error": "Profil non rattaché à une bijouterie vérifiée."},
#                     status=status.HTTP_400_BAD_REQUEST,
#                 )
#             qs = qs.filter(bijouterie=bij)

#         elif role == "admin":
#             bij_id = getf("bijouterie_id")
#             if bij_id:
#                 try:
#                     bij_id = int(bij_id)
#                 except ValueError:
#                     return Response(
#                         {"bijouterie_id": "Doit être un entier."},
#                         status=status.HTTP_400_BAD_REQUEST,
#                     )
#                 qs = qs.filter(bijouterie_id=bij_id)

#         # --- Recherche plein texte ---
#         q = (getf("q") or "").strip()
#         if q:
#             qs = qs.filter(
#                 Q(numero_facture__icontains=q)
#                 | Q(vente__numero_vente__icontains=q)
#                 | Q(vente__client__nom__icontains=q)
#                 | Q(vente__client__prenom__icontains=q)
#                 | Q(vente__client__telephone__icontains=q)
#             )

#         # --- Type facture (optionnel) ---
#         tf = (getf("type_facture") or "").strip()
#         if tf in {"proforma", "facture", "acompte", "finale"}:
#             qs = qs.filter(type_facture=tf)

#         # --- Fenêtre temporelle (même logique que ListFactureView) ---
#         df = _parse_date(getf("date_from"))
#         dt = _parse_date(getf("date_to"))
#         today = timezone.localdate()

#         if role in {"vendor", "cashier"}:
#             # Si aucune date → année en cours
#             if not df and not dt:
#                 df, dt = _current_year_bounds_dates()
#             elif df and not dt:
#                 dt_cap = min(_add_years(df, 3) - timedelta(days=1), today)
#                 dt = dt_cap
#             elif dt and not df:
#                 df = max(_add_years(dt, -3), date(dt.year, 1, 1))

#             if df and dt and df > dt:
#                 return Response(
#                     {"error": "`date_from` doit être ≤ `date_to`."},
#                     status=status.HTTP_400_BAD_REQUEST,
#                 )

#             if df and dt:
#                 max_dt = _add_years(df, 3) - timedelta(days=1)
#                 if dt > max_dt:
#                     return Response(
#                         {
#                             "error": (
#                                 "Fenêtre maximale de 3 ans pour ce rôle. "
#                                 f"`date_to` autorisé ≤ {max_dt}."
#                             )
#                         },
#                         status=status.HTTP_400_BAD_REQUEST,
#                     )
#                 dt = min(dt, today)

#             if df:
#                 qs = qs.filter(date_creation__date__gte=df)
#             if dt:
#                 qs = qs.filter(date_creation__date__lte=dt)

#         else:  # admin / manager
#             if df:
#                 qs = qs.filter(date_creation__date__gte=df)
#             if dt:
#                 qs = qs.filter(date_creation__date__lte=dt)

#         # --- Tri ---
#         ordering = getf("ordering") or "-date_creation"
#         allowed = {
#             "date_creation",
#             "-date_creation",
#             "montant_total",
#             "-montant_total",
#             "numero_facture",
#             "-numero_facture",
#         }
#         if ordering not in allowed:
#             ordering = "-date_creation"
#         qs = qs.order_by(ordering)

#         ser = FactureSerializer(qs, many=True)
#         return Response(ser.data, status=status.HTTP_200_OK)

class ListFacturesAPayerView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Lister les factures NON PAYÉES",
        operation_description=(
            "- **Vendor / Cashier / Manager** : factures NON PAYÉES de leur bijouterie "
            "sur une fenêtre de **18 mois**.\n"
            "- **Admin** : factures NON PAYÉES toutes bijouteries "
            "sur une fenêtre de **36 mois**.\n\n"
            "Filtres optionnels :\n"
            "• `numero_facture`\n"
            "• `page`\n"
            "• `page_size` (max 100)\n"
        ),
        manual_parameters=[
            openapi.Parameter(
                "numero_facture",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Numéro de facture (partiel)"
            ),
            openapi.Parameter(
                "page",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                description="Numéro de page"
            ),
            openapi.Parameter(
                "page_size",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                description="Taille de page (max 100)"
            ),
        ],
        responses={200: FactureListSerializer(many=True)},
        tags=["Ventes / Factures"],
    )
    def get(self, request):
        user = request.user
        role = get_role_name(user)

        if role not in {"admin", "manager", "vendor", "cashier"}:
            return Response(
                {"message": "⛔ Accès refusé"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 🔹 Base queryset : UNIQUEMENT NON PAYÉES
        qs = (
            Facture.objects
            .select_related("bijouterie", "vente", "vente__client")
            .filter(status=Facture.STAT_NON_PAYE)
        )

        # 🔹 Portée bijouterie
        if role in {"manager", "vendor", "cashier"}:
            bij = _user_bijouterie_facture(user)
            if not bij:
                return Response(
                    {"error": "Profil non rattaché à une bijouterie vérifiée."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(bijouterie=bij)

        # 🔹 Fenêtre temporelle automatique
        now = timezone.now()
        months = 36 if role == "admin" else 18
        min_datetime = now - timedelta(days=months * 30)
        qs = qs.filter(date_creation__gte=min_datetime)

        # 🔹 Filtre numero_facture (optionnel)
        numero = (request.GET.get("numero_facture") or "").strip()
        if numero:
            qs = qs.filter(numero_facture__icontains=numero)

        # 🔹 Tri
        qs = qs.order_by("-date_creation")

        # 🔹 Pagination
        try:
            page = int(request.GET.get("page", 1))
        except ValueError:
            page = 1

        try:
            page_size = int(request.GET.get("page_size", DEFAULT_PAGE_SIZE))
        except ValueError:
            page_size = DEFAULT_PAGE_SIZE

        page_size = max(1, min(page_size, MAX_PAGE_SIZE))

        paginator = Paginator(qs, page_size)
        try:
            page_obj = paginator.page(page)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)

        return Response(
            {
                "count": paginator.count,
                "page": page_obj.number,
                "page_size": page_size,
                "num_pages": paginator.num_pages,
                "results": FactureListSerializer(
                    page_obj.object_list,
                    many=True
                ).data,
            },
            status=status.HTTP_200_OK,
        )
# --------------------------------END ListFacturesAPayerView---------------------------

# --------------------------------------------------------------------------
# --- Helpers locaux (adapte si tu les as déjà ailleurs) ---
# def _user_role(user) -> str | None:
#     return getattr(getattr(user, "user_role", None), "role", None)

# def _user_bijouterie(user):
#     vp = getattr(user, "staff_vendor_profile", None)
#     if vp and getattr(vp, "verifie", False) and vp.bijouterie_id:
#         return vp.bijouterie
#     mp = getattr(user, "staff_manager_profile", None)
#     if mp and getattr(mp, "verifie", False) and mp.bijouterie_id:
#         return mp.bijouterie
#     cp = getattr(user, "staff_cashier_profile", None)
#     if cp and getattr(cp, "verifie", False) and cp.bijouterie_id:
#         return cp.bijouterie
#     return None


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
        tags=["Paiements / Factures"],
    )
    @transaction.atomic
    def post(self, request, facture_numero: str):
        # 1) Rôle
        # role = _user_role(request.user)
        # if role not in self.ROLES_AUTORISES:
        #     return Response({"detail": "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        user = request.user
        role = get_role_name(user)

        if role not in {"admin", "manager", "cashier"}:
            return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

    
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
        user_shop = _user_bijouterie_facture(request.user)
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


# def _user_role(user):
#     """Retourne 'vendor' / 'manager' ou None."""
#     # adapte si tu as un autre système ; ici on détecte via présence des profils
#     if getattr(user, "staff_vendor_profile", None):
#         return "vendor"
#     if getattr(user, "staff_manager_profile", None):
#         return "manager"
#     return None

# def _user_bijouterie(user):
#     """Bijouterie de l’utilisateur (vendor/manager vérifié), sinon None."""
#     vp = getattr(user, "staff_vendor_profile", None)
#     if vp and getattr(vp, "verifie", False) and vp.bijouterie_id:
#         return vp.bijouterie
#     mp = getattr(user, "staff_manager_profile", None)
#     if mp and getattr(mp, "verifie", False) and mp.bijouterie_id:
#         return mp.bijouterie
#     return None

# ROLES_LIVRAISON = {"vendor", "manager"}

class ConfirmerLivraisonView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Confirmer la livraison (sortie réelle du stock)",
        operation_description=(
            "Marque la vente comme livrée et crée les mouvements d’inventaire **SALE_OUT** "
            "avec décrément du stock vendor. Requiert **facture payée**. "
            "Rôles autorisés : **vendor** / **manager**. "
            "La vente doit appartenir à la même bijouterie que l’utilisateur.\n\n"
            "- Vendor: peut livrer uniquement ses propres ventes (au moins une ligne avec son vendor).\n"
            "- Manager: peut livrer toute vente de sa bijouterie."
        ),
        responses={200: "OK", 400: "Erreur métier", 403: "Accès refusé", 404: "Introuvable"},
        tags=["Ventes"]
    )
    @transaction.atomic
    def post(self, request, vente_id: int):
        user = request.user
        role = get_role_name(user)

        if role not in {"manager", "vendor"}:
            return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

        # ✅ bijouterie utilisateur (obligatoire)
        user_shop = _user_bijouterie_facture(user)
        if not user_shop:
            return Response(
                {"error": "Profil non rattaché à une bijouterie vérifiée."},
                status=status.HTTP_403_FORBIDDEN
            )

        # ✅ charger la vente d'abord
        try:
            vente = (
                Vente.objects
                .select_related("facture_vente", "facture_vente__bijouterie")
                .prefetch_related("produits__produit", "produits__vendor")
                .select_for_update()
                .get(pk=vente_id)
            )
        except Vente.DoesNotExist:
            return Response({"error": "Vente introuvable."}, status=status.HTTP_404_NOT_FOUND)

        facture = getattr(vente, "facture_vente", None)
        if not facture:
            return Response({"error": "Aucune facture liée à cette vente."}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ sécurité bijouterie
        if facture.bijouterie_id != user_shop.id:
            return Response({"error": "Cette vente n’appartient pas à votre bijouterie."},
                            status=status.HTTP_403_FORBIDDEN)

        # ✅ restriction vendor : seulement ses ventes
        if role == "vendor":
            my_vendor = getattr(user, "staff_vendor_profile", None)
            if not my_vendor:
                return Response({"error": "Profil vendeur introuvable."}, status=status.HTTP_403_FORBIDDEN)

            if not vente.produits.filter(vendor=my_vendor).exists():
                return Response({"error": "Vous ne pouvez livrer que vos propres ventes."},
                                status=status.HTTP_403_FORBIDDEN)

        # ✅ déjà livrée ?
        if vente.delivery_status == Vente.DELIV_DELIVERED:
            return Response({
                "message": "Déjà livrée — aucune action.",
                "mouvements_crees": 0,
                "vente": VenteDetailSerializer(vente).data,
                "facture": FactureSerializer(facture).data
            }, status=status.HTTP_200_OK)

        # ✅ facture payée obligatoire
        if facture.status != Facture.STAT_PAYE:
            return Response({"error": "Facture non payée : livraison impossible."},
                            status=status.HTTP_400_BAD_REQUEST)

        # ✅ mouvements + décrément stock (service idempotent)
        try:
            created_count = create_sale_out_movements_for_vente(vente, request.user)
        except ValidationError as e:
            msg = getattr(e, "message", None) or (e.messages[0] if getattr(e, "messages", None) else str(e))
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

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

