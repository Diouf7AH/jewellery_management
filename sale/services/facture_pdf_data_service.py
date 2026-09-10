# sale/services/facture_pdf_data_service.py

from __future__ import annotations

from django.utils import timezone


def build_facture_pdf_data(facture) -> dict:
    """
    Construit toutes les données nécessaires à la facture PDF.

    Ce service est la source UNIQUE des données utilisées par :

    - FactureA5PaysageView
    - generate_facture_pdf()
    - build_facture_a5_paysage_pdf()

    Aucun serializer n'est nécessaire.
    """

    vente = getattr(
        facture,
        "vente",
        None,
    )

    client = (
        getattr(
            vente,
            "client",
            None,
        )
        if vente
        else None
    )

    bijouterie = getattr(
        facture,
        "bijouterie",
        None,
    )

    # =========================================================
    # LIGNES PRODUITS
    # =========================================================

    lines = []

    if vente:

        for vp in vente.lignes.all():

            produit = getattr(
                vp,
                "produit",
                None,
            )

            # -------------------------------------------------
            # Nom produit
            # -------------------------------------------------

            produit_nom = (
                getattr(
                    produit,
                    "nom",
                    None,
                )
                or "Produit supprimé"
            )

            # -------------------------------------------------
            # Poids
            # -------------------------------------------------

            poids = ""

            if (
                produit
                and getattr(
                    produit,
                    "poids",
                    None,
                ) is not None
            ):
                poids = str(
                    produit.poids
                )

            # -------------------------------------------------
            # Pureté
            # -------------------------------------------------

            purete = ""

            if produit:

                purete_obj = getattr(
                    produit,
                    "purete",
                    None,
                )

                if purete_obj:

                    purete = (
                        getattr(
                            purete_obj,
                            "purete",
                            None,
                        )
                        or getattr(
                            purete_obj,
                            "nom",
                            None,
                        )
                        or str(
                            purete_obj
                        )
                    )

            # -------------------------------------------------
            # État
            # -------------------------------------------------

            etat = ""

            if produit:

                if hasattr(
                    produit,
                    "get_etat_display",
                ):
                    etat = (
                        produit.get_etat_display()
                        or ""
                    )

                else:
                    etat = (
                        getattr(
                            produit,
                            "etat",
                            "",
                        )
                        or ""
                    )

            # -------------------------------------------------
            # Réduction occasion
            # -------------------------------------------------

            pourcentage_occasion = getattr(
                vp,
                "pourcentage_occasion",
                None,
            )

            if pourcentage_occasion in (
                None,
                "",
            ):
                pourcentage_occasion = (
                    getattr(
                        produit,
                        "pourcentage_occasion",
                        0,
                    )
                    if produit
                    else 0
                )

            reduction_occasion = getattr(
                vp,
                "reduction_occasion",
                0,
            )

            # -------------------------------------------------
            # Ligne finale
            # -------------------------------------------------

            lines.append(
                {
                    "label": produit_nom,

                    "poids": poids,

                    "qty": (
                        vp.quantite
                        or 0
                    ),

                    # Prix par gramme
                    "prix_gramme": (
                        vp.prix_vente_grammes
                        or 0
                    ),

                    # Total réel de la ligne
                    "total": (
                        vp.montant_total
                        or 0
                    ),

                    "purete": purete,

                    "etat": etat,

                    "pourcentage_occasion": (
                        pourcentage_occasion
                        or 0
                    ),

                    "reduction_occasion": (
                        reduction_occasion
                        or 0
                    ),
                }
            )

    # =========================================================
    # BIJOUTERIE
    # =========================================================

    shop_name = (
        getattr(
            bijouterie,
            "nom",
            None,
        )
        or "RIO GOLD"
    )

    shop_phone = ""

    if bijouterie:

        shop_phone = (
            getattr(
                bijouterie,
                "telephone_portable_1",
                None,
            )
            or getattr(
                bijouterie,
                "telephone_portable_2",
                None,
            )
            or getattr(
                bijouterie,
                "telephone_fix",
                None,
            )
            or ""
        )

    shop_ninea = ""

    if bijouterie:

        shop_ninea = (
            getattr(
                bijouterie,
                "ninea",
                None,
            )
            or getattr(
                bijouterie,
                "ninenea",
                None,
            )
            or ""
        )

    shop_address = (
        getattr(
            bijouterie,
            "adresse",
            "",
        )
        or ""
        if bijouterie
        else ""
    )

    # =========================================================
    # CLIENT
    # =========================================================

    client_name = ""
    client_phone = ""
    client_address = ""

    if client:

        client_name = (
            f"{getattr(client, 'prenom', '') or ''} "
            f"{getattr(client, 'nom', '') or ''}"
        ).strip()

        client_phone = (
            getattr(
                client,
                "telephone",
                "",
            )
            or ""
        )

        client_address = (
            getattr(
                client,
                "adresse",
                "",
            )
            or ""
        )

    # =========================================================
    # VENDEUR
    # =========================================================

    vendor_name = ""

    if (
        vente
        and getattr(
            vente,
            "vendor",
            None,
        )
    ):

        vendor = vente.vendor

        vendor_user = getattr(
            vendor,
            "user",
            None,
        )

        if vendor_user:

            full_name = ""

            if hasattr(
                vendor_user,
                "get_full_name",
            ):
                full_name = (
                    vendor_user
                    .get_full_name()
                    .strip()
                )

            vendor_name = (
                full_name
                or getattr(
                    vendor_user,
                    "email",
                    "",
                )
            )

        if not vendor_name:
            vendor_name = str(
                vendor
            )

    # =========================================================
    # MODES DE PAIEMENT
    # =========================================================

    modes = []

    try:

        paiements = facture.paiements.all()

    except Exception:

        paiements = []

    for paiement in paiements:

        try:

            paiement_lignes = (
                paiement.lignes.all()
            )

        except Exception:

            paiement_lignes = []

        for ligne in paiement_lignes:

            mode_obj = getattr(
                ligne,
                "mode_paiement",
                None,
            )

            if not mode_obj:
                continue

            mode_nom = (
                getattr(
                    mode_obj,
                    "nom",
                    None,
                )
                or getattr(
                    mode_obj,
                    "code",
                    None,
                )
                or str(
                    mode_obj
                )
            )

            if (
                mode_nom
                and mode_nom not in modes
            ):
                modes.append(
                    mode_nom
                )

    payment_mode = ", ".join(
        modes
    )

    # =========================================================
    # DATE
    # =========================================================

    date_creation = getattr(
        facture,
        "date_creation",
        None,
    )

    if (
        date_creation
        and timezone.is_aware(
            date_creation
        )
    ):
        date_creation = (
            timezone.localtime(
                date_creation
            )
        )

    date_txt = (
        date_creation.strftime(
            "%d/%m/%Y %H:%M"
        )
        if date_creation
        else ""
    )

    # =========================================================
    # QR CODE
    # =========================================================

    qr_code_path = None

    qr_field = getattr(
        facture,
        "qr_code_image",
        None,
    )

    if qr_field:

        try:

            qr_code_path = (
                qr_field.path
            )

        except Exception:

            qr_code_path = None

    # =========================================================
    # DATA FINALES
    # =========================================================

    return {

        # -----------------------------------------------------
        # BIJOUTERIE
        # -----------------------------------------------------

        "shop_name":
            shop_name,

        "shop_phone":
            shop_phone,

        "shop_ninea":
            shop_ninea,

        "shop_address":
            shop_address,

        # -----------------------------------------------------
        # FACTURE
        # -----------------------------------------------------

        "title":
            "FACTURE",

        "invoice_no":
            facture.numero_facture,

        "invoice_type":
            facture.type_facture,

        "status":
            facture.status,

        "date":
            date_txt,

        "qr_code_path":
            qr_code_path,

        # -----------------------------------------------------
        # CLIENT
        # -----------------------------------------------------

        "client_name":
            client_name,

        "client_phone":
            client_phone,

        "client_address":
            client_address,

        # -----------------------------------------------------
        # VENTE
        # -----------------------------------------------------

        "vendor":
            vendor_name,

        "cashier":
            "",

        "sale_no": (
            vente.numero_vente
            if vente
            else ""
        ),

        # -----------------------------------------------------
        # PAIEMENT
        # -----------------------------------------------------

        "payment_mode":
            payment_mode,

        # -----------------------------------------------------
        # PRODUITS
        # -----------------------------------------------------

        "lines":
            lines,

        # -----------------------------------------------------
        # TOTAUX
        # -----------------------------------------------------

        "total_ht": (
            facture.montant_ht
            or 0
        ),

        "taux_tva":
            facture.taux_tva,

        "montant_tva": (
            facture.montant_tva
            or 0
        ),

        "total_ttc": (
            facture.montant_total
            or 0
        ),

        "amount_paid": (
            facture.total_paye
            or 0
        ),

        "remaining_amount": (
            facture.reste_a_payer
            or 0
        ),

        "deposit_amount":
            0,

        # -----------------------------------------------------
        # FOOTER
        # -----------------------------------------------------

        "thanks":
            "Merci pour votre confiance.",

        "footer_note": (
            "Bijouterie Rio-Gold "
            "- L'excellence en or."
        ),
    }
    


