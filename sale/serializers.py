# from rest_framework import serializers
# from .models import Client, Vente, VenteProduit, Facture, Paiement
# from store.serializers import ProduitSerializer
# class ClientSerializers(serializers.ModelSerializer):
#     class Meta:
#         model = Client
#         fields = ['id', 'nom', 'prenom',]


# class VenteProduitSerializer(serializers.ModelSerializer):
#     # produit = ProduitSerializer()
#     # class Meta:
#     #     model = VenteProduit
#     #     fields = ['id', 'produit', 'quantite', 'prix_vente_grammes', 'sous_total_prix_vent', 'tax', 'tax_inclue']
#     produit_id = serializers.IntegerField()
#     quantite = serializers.IntegerField(min_value=1)
#     prix_vente_grammes = serializers.FloatField(required=False)
#     # remise = serializers.FloatField(required=False, min_value=0.0, max_value=100.0)
#     class Meta:
#         model = VenteProduit
#         fields = ['id', 'produit', 'produit_id', 'quantite', 'prix_vente_grammes', 'sous_total_prix_vent', 'tax', 'tax_inclue']
    
    
# class VenteSerializers(serializers.ModelSerializer):
#     client = ClientSerializers()
#     produits = VenteProduitSerializer(many=True)
#     class Meta:
#         model = Vente
#         fields = ['id', 'client', 'produits', 'created_at', 'montant_total',]


# class FactureSerializers(serializers.ModelSerializer):
#     vente = VenteSerializers()
#     class Meta:
#         model = Facture
#         fields = ['id', 'numero_facture', 'vente', 'date_creation', 'montant_total']


# class PaiementSerializers(serializers.ModelSerializer):
#     # facture = FactureSerializers()
#     facture = serializers.SerializerMethodField()
#     class Meta:
#         model = Paiement
#         fields = ("id", "facture", "montant_paye", "mode_paiement", "date_paiement")
        
#     def get_facture(self, obj):
#         if not obj.facture:
#             return None
#         return {
#             "id": obj.facture.id,
#             "numero_facture": obj.facture.numero_facture,
#             "vente": obj.facture.vente,
#             "montant_total": obj.facture.montant_total,
#             "status": obj.facture.status,
#             "date_creation": obj.facture.date_creation,
#         }
        
#     def to_representation(self, instance):
#         data = super().to_representation(instance)
#         # Réassigner les champs enrichis
#         data['facture'] = self.get_facture(instance)
#         return data
    
    
from rest_framework import serializers
from .models import Client, Vente, VenteProduit, Facture, Paiement
from store.serializers import ProduitSerializer

# class ProduitMiniSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Produit
#         fields = ['id', 'nom', 'slug', 'poids']

class VenteProduitSerializer(serializers.ModelSerializer):
    produit = ProduitSerializer()
    prix_vente_grammes = serializers.DecimalField(max_digits=12, decimal_places=2)
    remise = serializers.DecimalField(max_digits=5, decimal_places=2)
    autres = serializers.DecimalField(max_digits=5, decimal_places=2)
    sous_total_prix_vent = serializers.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        model = VenteProduit
        fields = [
            'produit',
            'quantite',
            'prix_vente_grammes',
            'remise',
            'autres',
            'sous_total_prix_vent',
        ]

class FactureSerializer(serializers.ModelSerializer):
    total_paye = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, coerce_to_string=True)
    reste_a_payer = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, coerce_to_string=True)
    date_creation = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    class Meta:
        model = Facture
        fields = ['numero_facture', 'montant_total', 'total_paye', 'reste_a_payer', 'status', 'date_creation']

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ['nom', 'prenom', 'telephone']

class VenteDetailSerializer(serializers.ModelSerializer):
    client = serializers.SerializerMethodField()
    produits = serializers.SerializerMethodField()
    facture = serializers.SerializerMethodField()

    class Meta:
        model = Vente
        fields = ['id', 'client', 'produits', 'montant_total', 'facture']

    def get_client(self, obj):
        client = obj.client
        return {
            "nom": client.nom,
            "prenom": client.prenom,
            "telephone": client.telephone
        } if client else None

    def get_produits(self, obj):
        return [
            {
                "nom": p.produit.nom if p.produit else "Produit supprimé",
                "quantite": p.quantite,
                "prix_vente_grammes": str(p.prix_vente_grammes),
                "sous_total_prix_vent": str(p.sous_total_prix_vent),
                "remise": str(p.remise),
                "autres": str(p.autres)
            }
            for p in obj.produits.all()
        ]

    def get_facture(self, obj):
        facture = getattr(obj, "facture_vente", None)
        if not facture:
            return None
        return {
            "numero_facture": facture.numero_facture,
            "montant_total": str(facture.montant_total),
            "status": facture.status,
            "date": facture.date_creation
        }
        
class PaiementSerializer(serializers.ModelSerializer):
    # facture = FactureSerializer()
    facture = serializers.SerializerMethodField()
    class Meta:
        model = Paiement
        fields = ("id", "facture", "montant_paye", "mode_paiement", "date_paiement")
        
    def get_facture(self, obj):
        if not obj.facture:
            return None
        return {
            "id": obj.facture.id,
            "numero_facture": obj.facture.numero_facture,
            "vente": obj.facture.vente,
            "montant_total": obj.facture.montant_total,
            "status": obj.facture.status,
            "date_creation": obj.facture.date_creation,
        }
        
    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Réassigner les champs enrichis
        data['facture'] = self.get_facture(instance)
        return data