# sale/services/facture_pdf_data_service.py
from __future__ import annotations

from decimal import Decimal


def _s(v):
    return "" if v is None else str(v)


def _shop_phone(bijouterie) -> str:
    return (
        getattr(bijouterie, "telephone_portable_1", None)
        or getattr(bijouterie, "telephone", None)
        or ""
    )


def _shop_ninea(bijouterie) -> str:
    ninea = getattr(bijouterie, "ninea", None) or ""
    return f"NINEA : {ninea}" if ninea else ""


def _shop_address(bijouterie) -> str:
    return getattr(bijouterie, "adresse", None) or ""


def _client_name(client) -> str:
    if not client:
        return "Client non renseigné"
    return f"{getattr(client, 'prenom', '')} {getattr(client, 'nom', '')}".strip()


def _vendor_name(vente) -> str:
    vendor = getattr(vente, "vendor", None)
    if not vendor:
        return ""
    user = getattr(vendor, "user", None)
    if user:
        full = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
        if full:
            return full
    return str(vendor)


def _cashier_name(facture) -> str:
    paiement = (
        facture.paiements
        .select_related("cashier", "cashier__user")
        .order_by("-date_paiement", "-id")
        .first()
    )
    if not paiement:
        return ""

    cashier = getattr(paiement, "cashier", None)
    if not cashier:
        return ""

    user = getattr(cashier, "user", None)
    if user:
        full = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
        if full:
            return full

    return str(cashier)


def _build_lines(vente):
    lines = []

    if not vente:
        return lines

    for ligne in vente.lignes.select_related("produit", "produit__purete").all().order_by("id"):
        produit = getattr(ligne, "produit", None)

        nom = getattr(produit, "nom", "") or "Produit"
        purete_obj = getattr(produit, "purete", None)
        purete = getattr(purete_obj, "nom", None) or getattr(purete_obj, "titre", None) or ""
        poids = getattr(produit, "poids", None) or getattr(produit, "poids_grammes", None) or ""

        desc_parts = [nom]
        if purete:
            desc_parts.append(str(purete))
        if poids not in ("", None):
            desc_parts.append(f"poids {poids}g")

        lines.append({
            "label": " ".join(desc_parts).strip(),
            "qty": ligne.quantite or 0,
            "pu": ligne.prix_vente_grammes or Decimal("0.00"),
            "ht": ligne.montant_ht or Decimal("0.00"),
            "ttc": ligne.montant_total or Decimal("0.00"),
        })

    return lines


def build_facture_pdf_data(facture):
    facture = (
        facture.__class__.objects
        .select_related("vente", "vente__client", "vente__vendor", "vente__vendor__user", "bijouterie")
        .prefetch_related("vente__lignes__produit", "vente__lignes__produit__purete", "paiements")
        .get(pk=facture.pk)
    )

    vente = getattr(facture, "vente", None)
    client = getattr(vente, "client", None) if vente else None
    bijouterie = getattr(facture, "bijouterie", None)

    lines = _build_lines(vente)

    total_ht = facture.montant_ht or Decimal("0.00")
    taux_tva = facture.taux_tva or Decimal("0.00")
    montant_tva = facture.montant_tva or Decimal("0.00")
    total_ttc = facture.montant_total or Decimal("0.00")

    total_paye = facture.total_paye or Decimal("0.00")
    reste = facture.reste_a_payer or Decimal("0.00")

    document_type = (facture.type_facture or "").upper()

    deposit_amount = Decimal("0.00")
    if facture.type_facture == facture.TYPE_ACOMPTE:
        deposit_amount = total_paye

    order_no = ""
    delivery_date = ""

    return {
        "shop_name": getattr(bijouterie, "nom", None) or "Bijouterie Rio-Gold",
        "shop_phone": _shop_phone(bijouterie),
        "shop_ninea": _shop_ninea(bijouterie),
        "shop_address": _shop_address(bijouterie),

        "title": "FACTURE",
        "invoice_no": facture.numero_facture,
        "date": facture.date_creation.strftime("%d/%m/%Y") if facture.date_creation else "",
        "document_type": document_type,
        "order_no": order_no,
        "delivery_date": delivery_date,

        "client_name": _client_name(client),
        "client_phone": getattr(client, "telephone", None) or "",
        "client_address": getattr(client, "adresse", None) or "",

        "vendor": _vendor_name(vente) if vente else "",
        "cashier": _cashier_name(facture),
        "sale_no": getattr(vente, "numero_vente", None) or "",
        "status": facture.status,

        "lines": lines,

        "total_ht": total_ht,
        "taux_tva": taux_tva,
        "total_tax": montant_tva,
        "total_ttc": total_ttc,

        "amount_paid": total_paye,
        "deposit_amount": deposit_amount,
        "remaining_amount": reste,

        "thanks": "Merci pour votre confiance.",
        "footer_note": "Bijouterie Rio-Gold - L'excellence en or.",
    }
    
    


