from decimal import Decimal

from django.shortcuts import get_object_or_404

from purchase.models import Achat, Fournisseur, Lot, ProduitLine


# ---------------------Update and Adjustement--------------------------
# --------- helpers communs ----------
def _recalc_totaux_achat(achat: Achat):
    """Recalcule HT/TTC depuis les ProduitLine du/des lots de l'achat (au gramme si dispo)."""
    total_ht = Decimal("0.00")
    lignes = (ProduitLine.objects
              .filter(lot__achat=achat)
              .select_related("produit", "lot"))
    for pl in lignes:
        if pl.prix_gramme_achat:
            p_po = Decimal(pl.produit.poids or 0)
            q   = Decimal(pl.quantite_total or 0)
            total_ht += p_po * q * Decimal(pl.prix_gramme_achat)
    achat.montant_total_ht = total_ht + Decimal(achat.frais_transport or 0) + Decimal(achat.frais_douane or 0) - Decimal(achat.frais_transport or 0) - Decimal(achat.frais_douane or 0)
    # ci-dessus: on ne double pas les frais; la ligne sert juste d'explicitation
    achat.montant_total_ht = total_ht + Decimal(achat.frais_transport or 0) + Decimal(achat.frais_douane or 0)
    achat.montant_total_ttc = achat.montant_total_ht  # TAX=0 par défaut (adapter si TVA)
    achat.full_clean()
    achat.save(update_fields=["montant_total_ht", "montant_total_ttc"])


def _get_or_upsert_fournisseur(data):
    """data = {id|nom/prenom/telephone}. Priorité à id, sinon upsert par téléphone si fourni."""
    if not data:
        return None
    if "id" in data:
        return get_object_or_404(Fournisseur, pk=data["id"])
    tel = (data.get("telephone") or "").strip() or None
    if tel:
        obj, _ = Fournisseur.objects.get_or_create(
            telephone=tel,
            defaults={"nom": data.get("nom", "") or "", "prenom": data.get("prenom", "") or ""},
        )
        return obj
    return Fournisseur.objects.create(
        nom=data.get("nom", "") or "", prenom=data.get("prenom", "") or "", telephone=None
    )


# ---------------------And Update and Adjustement----------------------