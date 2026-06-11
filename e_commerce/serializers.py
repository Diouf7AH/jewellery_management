from decimal import Decimal

from django.db.models import Sum
from rest_framework import serializers

from purchase.models import ProduitLine
from sale.models import Client
from stock.models import Stock
from store.models import Bijouterie

from .models import (CommandeEcommerce, CommandeEcommerceLigne,
                     EcommerceBanner, LivraisonEcommerce, PaiementEcommerce)


class CommandeEcommerceLigneInputSerializer(serializers.Serializer):
    produit_line_id = serializers.IntegerField()
    quantite = serializers.IntegerField(min_value=1)


class CommandeEcommerceCreateSerializer(serializers.Serializer):
    bijouterie_id = serializers.IntegerField()
    client_id = serializers.IntegerField(required=False, allow_null=True)

    nom_client = serializers.CharField(max_length=150)
    telephone_client = serializers.CharField(max_length=30)
    email_client = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    adresse_livraison = serializers.CharField(required=False, allow_blank=True)

    mode_paiement = serializers.ChoiceField(
        choices=PaiementEcommerce.MODE_CHOICES
    )

    lignes = CommandeEcommerceLigneInputSerializer(many=True)

    def validate(self, attrs):
        bijouterie_id = attrs["bijouterie_id"]
        lignes = attrs["lignes"]

        try:
            bijouterie = Bijouterie.objects.get(id=bijouterie_id)
        except Bijouterie.DoesNotExist:
            raise serializers.ValidationError({
                "bijouterie_id": "Bijouterie introuvable."
            })

        attrs["bijouterie"] = bijouterie

        if attrs.get("client_id"):
            try:
                attrs["client"] = Client.objects.get(id=attrs["client_id"])
            except Client.DoesNotExist:
                raise serializers.ValidationError({
                    "client_id": "Client introuvable."
                })
        else:
            attrs["client"] = None

        produit_line_ids = [ligne["produit_line_id"] for ligne in lignes]

        produit_lines = {
            pl.id: pl
            for pl in ProduitLine.objects.select_related("produit").filter(
                id__in=produit_line_ids
            )
        }

        lignes_validees = []
        montant_total = Decimal("0.00")

        for ligne in lignes:
            produit_line_id = ligne["produit_line_id"]
            quantite = ligne["quantite"]

            produit_line = produit_lines.get(produit_line_id)

            if not produit_line:
                raise serializers.ValidationError({
                    "lignes": f"ProduitLine {produit_line_id} introuvable."
                })

            stock = Stock.objects.filter(
                produit_line=produit_line,
                bijouterie=bijouterie,
                is_reserve=False,
            ).first()

            if not stock:
                raise serializers.ValidationError({
                    "stock": f"Aucun stock bijouterie trouvé pour ProduitLine {produit_line_id}."
                })

            if stock.en_stock < quantite:
                raise serializers.ValidationError({
                    "stock": f"Stock insuffisant pour {produit_line.produit}. Disponible: {stock.en_stock}."
                })

            prix_unitaire = getattr(produit_line.produit, "prix_vente", Decimal("0.00"))

            montant_ligne = prix_unitaire * Decimal(quantite)

            lignes_validees.append({
                "produit_line": produit_line,
                "produit": produit_line.produit,
                "quantite": quantite,
                "prix_unitaire": prix_unitaire,
                "montant_total": montant_ligne,
            })

            montant_total += montant_ligne

        attrs["lignes_validees"] = lignes_validees
        attrs["montant_total"] = montant_total

        return attrs

    def create(self, validated_data):
        lignes_validees = validated_data.pop("lignes_validees")
        mode_paiement = validated_data.pop("mode_paiement")

        validated_data.pop("lignes", None)
        validated_data.pop("bijouterie_id", None)
        validated_data.pop("client_id", None)

        montant_total = validated_data.pop("montant_total")

        # À adapter selon tes frais Wave / Orange Money / Carte
        frais_transaction = Decimal("0.00")
        montant_a_payer = montant_total + frais_transaction

        commande = CommandeEcommerce.objects.create(
            **validated_data,
            montant_total=montant_total,
            frais_transaction=frais_transaction,
            montant_a_payer=montant_a_payer,
            status=CommandeEcommerce.STATUS_PENDING,
        )

        for ligne in lignes_validees:
            CommandeEcommerceLigne.objects.create(
                commande=commande,
                **ligne,
            )

        PaiementEcommerce.objects.create(
            commande=commande,
            mode=mode_paiement,
            status=PaiementEcommerce.STATUS_PENDING,
            montant=montant_a_payer,
            frais_transaction=frais_transaction,
        )

        return commande


class CommandeEcommerceLigneSerializer(serializers.ModelSerializer):
    produit_nom = serializers.CharField(source="produit.nom", read_only=True)
    produit_line_id = serializers.IntegerField(source="produit_line.id", read_only=True)

    class Meta:
        model = CommandeEcommerceLigne
        fields = [
            "id",
            "produit_line_id",
            "produit",
            "produit_nom",
            "quantite",
            "prix_unitaire",
            "montant_total",
        ]


class PaiementEcommerceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaiementEcommerce
        fields = [
            "id",
            "uuid",
            "mode",
            "status",
            "montant",
            "frais_transaction",
            "reference_paiement",
            "transaction_id",
            "created_at",
            "confirmed_at",
        ]


class CommandeEcommerceDetailSerializer(serializers.ModelSerializer):
    lignes = CommandeEcommerceLigneSerializer(many=True, read_only=True)
    paiements = PaiementEcommerceSerializer(many=True, read_only=True)

    client_nom = serializers.SerializerMethodField()
    bijouterie_nom = serializers.CharField(source="bijouterie.nom", read_only=True)

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

    def get_client_nom(self, obj):
        if obj.client:
            return f"{obj.client.nom} {obj.client.prenom}".strip()
        return obj.nom_client


class EcommerceProductListSerializer(serializers.ModelSerializer):
    produit_line_id = serializers.IntegerField(source="produit_line.id", read_only=True)
    produit_id = serializers.IntegerField(source="produit_line.produit.id", read_only=True)
    nom = serializers.CharField(source="produit_line.produit.nom", read_only=True)
    sku = serializers.CharField(source="produit_line.produit.sku", read_only=True)
    image = serializers.ImageField(source="produit_line.produit.image", read_only=True)
    poids = serializers.DecimalField(source="produit_line.produit.poids", max_digits=10, decimal_places=3, read_only=True)
    prix_vente = serializers.DecimalField(source="produit_line.produit.prix_vente", max_digits=14, decimal_places=2, read_only=True)
    stock_disponible = serializers.IntegerField(source="en_stock", read_only=True)

    class Meta:
        model = Stock
        fields = [
            "id",
            "produit_line_id",
            "produit_id",
            "nom",
            "sku",
            "image",
            "poids",
            "prix_vente",
            "stock_disponible",
        ]


class EcommerceProductDetailSerializer(EcommerceProductListSerializer):
    description = serializers.CharField(source="produit_line.produit.description", read_only=True)
    categorie = serializers.CharField(source="produit_line.produit.categorie.nom", read_only=True)
    marque = serializers.CharField(source="produit_line.produit.marque.nom", read_only=True)
    modele = serializers.CharField(source="produit_line.produit.modele.nom", read_only=True)
    purete = serializers.CharField(source="produit_line.produit.purete.nom", read_only=True)

    class Meta(EcommerceProductListSerializer.Meta):
        fields = EcommerceProductListSerializer.Meta.fields + [
            "description",
            "categorie",
            "marque",
            "modele",
            "purete",
        ]
        


from rest_framework import serializers


class EcommerceDashboardQuerySerializer(serializers.Serializer):
    bijouterie_id = serializers.IntegerField(required=False)
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    

class LivraisonEcommerceSerializer(serializers.ModelSerializer):
    class Meta:
        model = LivraisonEcommerce
        fields = "__all__"
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
        


class EcommerceBannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = EcommerceBanner
        fields = [
            "uuid",
            "titre",
            "description",
            "type_media",
            "image",
            "video",
            "lien_action",
            "texte_bouton",
            "active",
            "ordre_affichage",
        ]
        

