from decimal import ROUND_HALF_UP, Decimal

from rest_framework import serializers

from e_commerce.models import (CommandeEcommerce, CommandeEcommerceLigne,
                               EcommerceBanner, EcommerceBannerNouveauArrivage,
                               LivraisonEcommerce, PaiementEcommerce)
from e_commerce.services.create_order import create_ecommerce_order
from e_commerce.services.tarification import calculer_totaux_ecommerce
from purchase.models import ProduitLine
from sale.models import Client
from stock.models import Stock
from store.models import Bijouterie, MarquePurete

TWOPLACES = Decimal("0.01")
ZERO = Decimal("0.00")


class CommandeEcommerceLigneInputSerializer(serializers.Serializer):
    produit_line_id = serializers.IntegerField()
    quantite = serializers.IntegerField(min_value=1)


class CommandeEcommerceCreateSerializer(serializers.Serializer):
    bijouterie_id = serializers.IntegerField()

    nom_client = serializers.CharField(
        max_length=150,
    )

    telephone_client = serializers.CharField(
        max_length=30,
    )

    email_client = serializers.EmailField()

    adresse_livraison = serializers.CharField()

    mode_paiement = serializers.ChoiceField(
        choices=PaiementEcommerce.MODE_CHOICES,
    )

    lignes = CommandeEcommerceLigneInputSerializer(
        many=True,
    )

    # ============================================================
    # VALIDATION
    # ============================================================

    def validate(self, attrs):
        request = self.context.get("request")

        # ========================================================
        # 1. UTILISATEUR CONNECTÉ
        # ========================================================

        if (
            request is None
            or not request.user
            or not request.user.is_authenticated
        ):
            raise serializers.ValidationError({
                "client": (
                    "Vous devez être connecté "
                    "pour passer une commande."
                )
            })

        # ========================================================
        # 2. PROFIL CLIENT DU COMPTE CONNECTÉ
        # ========================================================

        try:
            client = request.user.client

        except Client.DoesNotExist:
            raise serializers.ValidationError({
                "client": (
                    "Aucun profil client n'est associé "
                    "à ce compte."
                )
            })

        attrs["client"] = client

        # ========================================================
        # 3. INFORMATIONS CHECKOUT
        # ========================================================

        nom_client = (
            attrs.get("nom_client") or ""
        ).strip()

        telephone_client = (
            attrs.get("telephone_client") or ""
        ).strip()

        email_client = (
            attrs.get("email_client") or ""
        ).strip()

        adresse_livraison = (
            attrs.get("adresse_livraison") or ""
        ).strip()

        if not nom_client:
            raise serializers.ValidationError({
                "nom_client": (
                    "Le nom du client est obligatoire."
                )
            })

        if not telephone_client:
            raise serializers.ValidationError({
                "telephone_client": (
                    "Le numéro de téléphone est obligatoire."
                )
            })

        if not email_client:
            raise serializers.ValidationError({
                "email_client": (
                    "L'adresse email est obligatoire."
                )
            })

        if not adresse_livraison:
            raise serializers.ValidationError({
                "adresse_livraison": (
                    "L'adresse de livraison est obligatoire."
                )
            })

        attrs["nom_client"] = nom_client
        attrs["telephone_client"] = telephone_client
        attrs["email_client"] = email_client
        attrs["adresse_livraison"] = adresse_livraison

        # ========================================================
        # 4. BIJOUTERIE
        # ========================================================

        bijouterie_id = attrs["bijouterie_id"]

        try:
            bijouterie = Bijouterie.objects.get(
                id=bijouterie_id
            )
        except Bijouterie.DoesNotExist:
            raise serializers.ValidationError({
                "bijouterie_id": (
                    "Bijouterie introuvable."
                )
            })

        attrs["bijouterie"] = bijouterie

        # ========================================================
        # 5. LIGNES
        # ========================================================

        lignes = attrs["lignes"]
        mode_paiement = attrs["mode_paiement"]

        if not lignes:
            raise serializers.ValidationError({
                "lignes": (
                    "La commande doit contenir "
                    "au moins un produit."
                )
            })

        produit_line_ids = [
            ligne["produit_line_id"]
            for ligne in lignes
        ]

        # --------------------------------------------------------
        # Empêcher les doublons ProduitLine
        # --------------------------------------------------------

        if len(produit_line_ids) != len(
            set(produit_line_ids)
        ):
            raise serializers.ValidationError({
                "lignes": (
                    "Un même ProduitLine ne peut apparaître "
                    "qu'une seule fois dans la commande."
                )
            })

        # ========================================================
        # 6. CHARGER LES PRODUITLINE
        # ========================================================

        produit_lines = {
            pl.id: pl
            for pl in (
                ProduitLine.objects
                .select_related(
                    "produit",
                    "produit__marque",
                    "produit__purete",
                )
                .filter(
                    id__in=produit_line_ids
                )
            )
        }

        # ========================================================
        # 7. CHARGER LE STOCK DE LA BIJOUTERIE
        #
        # IMPORTANT :
        # - aucune réservation ;
        # - aucune diminution ;
        # - première vérification uniquement.
        # ========================================================

        stocks = {
            stock.produit_line_id: stock
            for stock in (
                Stock.objects
                .select_related(
                    "produit_line",
                    "produit_line__produit",
                )
                .filter(
                    produit_line_id__in=produit_line_ids,
                    bijouterie=bijouterie,
                )
            )
        }

        lignes_validees = []
        montant_ht = ZERO

        # ========================================================
        # 8. VALIDATION DE CHAQUE LIGNE
        # ========================================================

        for ligne in lignes:
            produit_line_id = ligne[
                "produit_line_id"
            ]

            quantite = ligne["quantite"]

            produit_line = produit_lines.get(
                produit_line_id
            )

            if not produit_line:
                raise serializers.ValidationError({
                    "lignes": (
                        f"ProduitLine "
                        f"{produit_line_id} introuvable."
                    )
                })

            produit = produit_line.produit

            # ----------------------------------------------------
            # Produit publié
            # ----------------------------------------------------

            if produit.status != "publié":
                raise serializers.ValidationError({
                    "lignes": (
                        f"Le produit {produit} "
                        "n'est pas disponible "
                        "sur l'e-commerce."
                    )
                })

            # ----------------------------------------------------
            # Première vérification Stock.en_stock
            # ----------------------------------------------------

            stock = stocks.get(
                produit_line_id
            )

            if not stock:
                raise serializers.ValidationError({
                    "stock": (
                        "Aucun stock disponible dans "
                        f"{bijouterie} pour {produit}."
                    )
                })

            if stock.en_stock < quantite:
                raise serializers.ValidationError({
                    "stock": (
                        f"Stock insuffisant pour {produit}. "
                        f"Disponible : {stock.en_stock}. "
                        f"Demandé : {quantite}."
                    )
                })

            # ----------------------------------------------------
            # Marque / Pureté
            # ----------------------------------------------------

            if (
                not produit.marque_id
                or not produit.purete_id
            ):
                raise serializers.ValidationError({
                    "lignes": (
                        "Marque ou pureté manquante "
                        f"pour {produit}."
                    )
                })

            # ----------------------------------------------------
            # Prix par gramme
            # ----------------------------------------------------

            marque_purete = (
                MarquePurete.objects
                .filter(
                    marque_id=produit.marque_id,
                    purete_id=produit.purete_id,
                )
                .first()
            )

            if not marque_purete:
                raise serializers.ValidationError({
                    "lignes": (
                        "Aucun prix configuré pour "
                        f"{produit.marque} / "
                        f"{produit.purete}."
                    )
                })

            prix_gramme = Decimal(
                str(
                    marque_purete.prix
                    or ZERO
                )
            )

            if prix_gramme <= ZERO:
                raise serializers.ValidationError({
                    "lignes": (
                        "Prix de vente invalide "
                        f"pour {produit}."
                    )
                })

            # ----------------------------------------------------
            # Poids
            # ----------------------------------------------------

            poids = Decimal(
                str(
                    produit.poids
                    or ZERO
                )
            )

            if poids <= ZERO:
                raise serializers.ValidationError({
                    "lignes": (
                        f"Poids invalide pour {produit}."
                    )
                })

            # ----------------------------------------------------
            # Total ligne
            #
            # prix gramme × poids × quantité
            # ----------------------------------------------------

            montant_ligne = (
                prix_gramme
                * poids
                * Decimal(str(quantite))
            ).quantize(
                TWOPLACES,
                rounding=ROUND_HALF_UP,
            )

            lignes_validees.append({
                "produit_line": produit_line,
                "produit": produit,
                "quantite": quantite,

                # Correspond à VenteProduit.prix_vente_grammes
                "prix_gramme": prix_gramme,

                "montant_total": montant_ligne,
            })

            montant_ht += montant_ligne

        montant_ht = montant_ht.quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )

        # ========================================================
        # 9. FRAIS TRANSACTION
        # ========================================================

        frais_transaction = (
            self._calculer_frais_transaction(
                mode_paiement=mode_paiement,
                montant=montant_ht,
            )
        )

        # ========================================================
        # 10. TVA + TOTAL FINAL
        # ========================================================

        totaux = calculer_totaux_ecommerce(
            montant_ht=montant_ht,
            appliquer_tva=bijouterie.appliquer_tva,
            taux_tva=bijouterie.taux_tva,
            frais_transaction=frais_transaction,
        )

        # ========================================================
        # 11. DONNÉES TRANSMISES AU SERVICE CREATE_ORDER
        # ========================================================

        attrs["lignes_validees"] = (
            lignes_validees
        )

        attrs["appliquer_tva"] = (
            bijouterie.appliquer_tva
        )

        attrs["taux_tva"] = (
            bijouterie.taux_tva
            if bijouterie.appliquer_tva
            else None
        )

        attrs["montant_tva"] = (
            totaux["montant_tva"]
        )

        attrs["montant_total"] = (
            totaux["montant_total"]
        )

        attrs["frais_transaction"] = (
            totaux["frais_transaction"]
        )

        attrs["montant_a_payer"] = (
            totaux["montant_a_payer"]
        )

        return attrs

    # ============================================================
    # FRAIS TRANSACTION
    # ============================================================

    def _calculer_frais_transaction(
        self,
        *,
        mode_paiement,
        montant,
    ):
        """
        Taux provisoires.

        À remplacer plus tard par les vrais frais
        Wave / Orange Money / Carte.
        """

        montant = Decimal(
            str(
                montant
                or ZERO
            )
        )

        taux = ZERO

        if (
            mode_paiement
            == PaiementEcommerce.MODE_WAVE
        ):
            taux = Decimal("0.00")

        elif (
            mode_paiement
            == PaiementEcommerce.MODE_ORANGE
        ):
            taux = Decimal("0.00")

        elif (
            mode_paiement
            == PaiementEcommerce.MODE_CARTE
        ):
            taux = Decimal("0.00")

        return (
            montant
            * taux
            / Decimal("100")
        ).quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )

    # ============================================================
    # CREATE
    # ============================================================

    def create(self, validated_data):
        # Ces champs ne correspondent pas directement
        # à CommandeEcommerce.
        validated_data.pop(
            "lignes",
            None,
        )

        validated_data.pop(
            "bijouterie_id",
            None,
        )

        commande, paiement = (
            create_ecommerce_order(
                validated_data=validated_data
            )
        )

        return commande

class CommandeEcommerceLigneSerializer(
    serializers.ModelSerializer
):
    produit_nom = serializers.CharField(
        source="produit.nom",
        read_only=True,
    )

    produit_line_id = serializers.IntegerField(
        source="produit_line.id",
        read_only=True,
    )

    class Meta:
        model = CommandeEcommerceLigne

        fields = [
            "id",
            "produit_line_id",
            "produit",
            "produit_nom",
            "quantite",
            "prix_gramme",
            "montant_total",
        ]
        

class PaiementEcommerceSerializer(
    serializers.ModelSerializer
):
    class Meta:
        model = PaiementEcommerce

        fields = [
            "id",
            "uuid",
            "mode",
            "status",
            "montant",
            "frais_transaction",

            # Références
            "reference_paiement",
            "transaction_id",
            "provider_reference",

            # Paiement provider
            "checkout_url",

            # Dates
            "created_at",
            "confirmed_at",
        ]

        read_only_fields = fields
        
class CommandeEcommerceDetailSerializer(
    serializers.ModelSerializer
):
    lignes = CommandeEcommerceLigneSerializer(
        many=True,
        read_only=True,
    )

    paiements = PaiementEcommerceSerializer(
        many=True,
        read_only=True,
    )

    client_nom = serializers.SerializerMethodField()

    bijouterie_nom = serializers.CharField(
        source="bijouterie.nom",
        read_only=True,
    )

    class Meta:
        model = CommandeEcommerce

        fields = [
            "id",
            "uuid",

            "client",
            "client_nom",

            "bijouterie",
            "bijouterie_nom",

            "nom_client",
            "telephone_client",
            "email_client",
            "adresse_livraison",

            "status",

            "montant_total",
            "appliquer_tva",
            "taux_tva",
            "montant_tva",
            "frais_transaction",
            "montant_a_payer",

            "vente",
            "facture",

            "lignes",
            "paiements",

            "created_at",
            "updated_at",
            "paid_at",
        ]

        read_only_fields = fields

    def get_client_nom(self, obj):
        return (
            f"{obj.client.prenom} "
            f"{obj.client.nom}"
        ).strip()
        

class EcommerceProduitListSerializer(serializers.ModelSerializer):
    produit_line_id = serializers.IntegerField(
        source="produit_line.id",
        read_only=True,
    )

    produit_id = serializers.IntegerField(
        source="produit_line.produit.id",
        read_only=True,
    )

    uuid = serializers.UUIDField(
        source="produit_line.produit.uuid",
        read_only=True,
    )
    
    bijouterie_id = serializers.IntegerField(
        source="bijouterie.id",
        read_only=True,
    )

    bijouterie_nom = serializers.CharField(
        source="bijouterie.nom",
        read_only=True,
    )

    slug = serializers.CharField(
        source="produit_line.produit.slug",
        read_only=True,
    )

    nom = serializers.CharField(
        source="produit_line.produit.nom",
        read_only=True,
    )

    sku = serializers.CharField(
        source="produit_line.produit.sku",
        read_only=True,
    )

    image = serializers.ImageField(
        source="produit_line.produit.image",
        read_only=True,
    )

    poids = serializers.DecimalField(
        source="produit_line.produit.poids",
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    purete = serializers.CharField(
        source="produit_line.produit.purete.purete",
        read_only=True,
    )

    prix_gramme = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    prix_produit = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    stock_disponible = serializers.IntegerField(
        source="en_stock",
        read_only=True,
    )

    class Meta:
        model = Stock
        fields = [
            "id",
            "produit_line_id",
            "produit_id",
            "bijouterie_id",
            "bijouterie_nom",
            "uuid",
            "slug",
            "nom",
            "sku",
            "image",
            "poids",
            "purete",
            "prix_gramme",
            "prix_produit",
            "stock_disponible",
        ]


class EcommerceProduitDetailSerializer(
    EcommerceProduitListSerializer
):
    description = serializers.CharField(
        source="produit_line.produit.description",
        read_only=True,
    )

    categorie = serializers.CharField(
        source="produit_line.produit.categorie.nom",
        read_only=True,
    )

    marque = serializers.CharField(
        source="produit_line.produit.marque.marque",
        read_only=True,
    )

    modele = serializers.CharField(
        source="produit_line.produit.modele.modele",
        read_only=True,
    )

    class Meta(EcommerceProduitListSerializer.Meta):
        fields = (
            EcommerceProduitListSerializer.Meta.fields
            + [
                "description",
                "categorie",
                "marque",
                "modele",
            ]
        )
        
class EcommerceDashboardQuerySerializer(
    serializers.Serializer
):
    bijouterie_id = serializers.IntegerField(
        required=False,
        min_value=1,
    )

    start_date = serializers.DateField(
        required=False,
    )

    end_date = serializers.DateField(
        required=False,
    )

    def validate(self, attrs):
        start_date = attrs.get("start_date")
        end_date = attrs.get("end_date")

        if (
            start_date
            and end_date
            and start_date > end_date
        ):
            raise serializers.ValidationError({
                "end_date": (
                    "La date de fin doit être "
                    "supérieure ou égale à la date de début."
                )
            })

        return attrs
    


class LivraisonEcommerceSerializer(
    serializers.ModelSerializer
):
    class Meta:
        model = LivraisonEcommerce

        fields = [
            "id",
            "commande",
            "adresse_livraison",
            "telephone_client",
            "status",
            "numero_suivi",
            "transporteur",
            "note",
            "created_at",
            "updated_at",
            "prepared_at",
            "shipped_at",
            "delivered_at",
            "cancelled_at",
        ]

        read_only_fields = [
            "id",
            "commande",
            "created_at",
            "updated_at",
            "prepared_at",
            "shipped_at",
            "delivered_at",
            "cancelled_at",
        ]
        

class EcommerceBannerSerializer(
    serializers.ModelSerializer
):
    """
    Serializer de la bannière principale
    de la page d'accueil e-commerce.
    """

    class Meta:
        model = EcommerceBanner

        fields = [
            "id",
            "titre",
            "sous_titre",
            "description",
            "image",
            "texte_bouton",
            "lien_action",
            "ordre_affichage",
            "active",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]



class EcommerceBannerNouveauArrivageSerializer(
    serializers.ModelSerializer
):
    """
    Serializer des médias du bloc
    "Nouveaux arrivages".

    Un élément peut être :
    - une image ;
    - ou une vidéo.
    """

    class Meta:
        model = EcommerceBannerNouveauArrivage

        fields = [
            "id",
            "titre",
            "sous_titre",
            "description",
            "type_media",
            "image",
            "video",
            "texte_bouton",
            "lien_action",
            "ordre_affichage",
            "active",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]
        

