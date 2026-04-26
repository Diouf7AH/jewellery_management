# from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# from django.shortcuts import get_object_or_404
# from django.db.models import F, Sum, DecimalField, ExpressionWrapper, Value
# from django.db.models.functions import Coalesce

# from purchase.models import Achat, Fournisseur
# from purchase.models import ProduitLine


# Q2 = Decimal("0.01")  # 2 décimales


# def _D(v) -> Decimal:
#     """Decimal safe (évite float). None -> 0.00"""
#     if v in (None, "", "null"):
#         return Decimal("0.00")
#     try:
#         return Decimal(str(v))
#     except (InvalidOperation, TypeError, ValueError):
#         return Decimal("0.00")


# def _q2(v: Decimal) -> Decimal:
#     """Force 2 décimales."""
#     return (v or Decimal("0.00")).quantize(Q2, rounding=ROUND_HALF_UP)


# def _recalc_totaux_achat(achat: Achat, *, save: bool = True) -> Achat:
#     """
#     base_ht = Σ(quantite * poids_produit * prix_achat_gramme)
#     ht      = base_ht + frais_transport + frais_douane
#     ttc     = ht (TVA=0)
#     """
#     # ✅ Version ORM (rapide, évite boucle Python)
#     line_total = ExpressionWrapper(
#         F("quantite") * F("produit__poids") * F("prix_achat_gramme"),
#         output_field=DecimalField(max_digits=20, decimal_places=6),  # précision interne
#     )

#     base_ht = (
#         ProduitLine.objects
#         .filter(lot__achat=achat, prix_achat_gramme__isnull=False)
#         .aggregate(total=Coalesce(Sum(line_total), Value(Decimal("0.00"))))
#         ["total"]
#     )

#     base_ht = _D(base_ht)
#     frais_transport = _D(achat.frais_transport)
#     frais_douane = _D(achat.frais_douane)

#     ht = base_ht + frais_transport + frais_douane

#     achat.montant_total_ht = _q2(ht)
#     achat.montant_total_ttc = _q2(ht)

#     if save:
#         achat.full_clean()
#         achat.save(update_fields=["montant_total_ht", "montant_total_ttc"])

#     return achat


# def _get_or_upsert_fournisseur(data):
#     """data = {id|nom/prenom/telephone}. Priorité à id, sinon upsert par téléphone si fourni."""
#     if not data:
#         return None
#     if data.get("id"):
#         return get_object_or_404(Fournisseur, pk=data["id"])

#     tel = (data.get("telephone") or "").strip() or None
#     if tel:
#         obj, _ = Fournisseur.objects.get_or_create(
#             telephone=tel,
#             defaults={
#                 "nom": data.get("nom", "") or "",
#                 "prenom": data.get("prenom", "") or "",
#             },
#         )
#         return obj

#     return Fournisseur.objects.create(
#         nom=data.get("nom", "") or "",
#         prenom=data.get("prenom", "") or "",
#         telephone=None,
#     )

