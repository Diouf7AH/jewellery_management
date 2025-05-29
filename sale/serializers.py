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
#     #     fields = ['id', 'produit', 'quantite', 'prix_vente_grammes', 'sous_total_prix_vent', 'tax', 'prix_ttc']
#     produit_id = serializers.IntegerField()
#     quantite = serializers.IntegerField(min_value=1)
#     prix_vente_grammes = serializers.FloatField(required=False)
#     # remise = serializers.FloatField(required=False, min_value=0.0, max_value=100.0)
#     class Meta:
#         model = VenteProduit
#         fields = ['id', 'produit', 'produit_id', 'quantite', 'prix_vente_grammes', 'sous_total_prix_vent', 'tax', 'prix_ttc']


# class FactureSerializers(serializers.ModelSerializer):
#     vente = VenteSerializer()
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
    
from django.db.models import Sum
from rest_framework import serializers
from .models import Client, Vente, VenteProduit, Facture, Paiement
from store.serializers import ProduitSerializer
from django.db import models

# class ProduitMiniSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Produit
#         fields = ['id', 'nom', 'slug', 'poids']

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ['id', 'nom', 'prenom',]


class VenteProduitSerializer(serializers.ModelSerializer):
    produit_nom = serializers.SerializerMethodField()
    produit_slug = serializers.SerializerMethodField()
    # produit = ProduitSerializer()
    # prix_vente_grammes = serializers.DecimalField(max_digits=12, decimal_places=2)
    # remise = serializers.DecimalField(max_digits=5, decimal_places=2)
    # autres = serializers.DecimalField(max_digits=5, decimal_places=2)
    # sous_total_prix_vent = serializers.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        model = VenteProduit
        fields = [
            'produit',
            'produit_nom',
            'produit_slug',
            'vendor',
            'quantite',
            'prix_vente_grammes',
            'tax',
            'prix_ttc',
            'remise',
            'autres',
            'sous_total_prix_vente_ht',
        ]
    
    def get_produit_nom(self, obj):
        return obj.produit.nom if obj.produit else None
    
    def get_produit_slug(self, obj):
        return obj.produit.slug if obj.produit else None


# class VenteProduitSerializer(serializers.ModelSerializer):
#     produit_nom = serializers.SerializerMethodField()
#     produit_slug = serializers.SerializerMethodField()

#     class Meta:
#         model = VenteProduit
#         fields = [
#             'id', 'produit', 'quantite', 'prix_vente_grammes',
#             'sous_total_prix_vente_ht', 'tax', 'prix_ttc',
#             'produit_nom', 'produit_slug',
#         ]

#     def get_produit_nom(self, obj):
#         return obj.produit.nom if obj.produit else None
    

#     def get_produit_slug(self, obj):
#         return obj.produit.slug if obj.produit else None


class VenteSerializer(serializers.ModelSerializer):
    client = ClientSerializer()
    produits = VenteProduitSerializer(many=True)
    class Meta:
        model = Vente
        fields = ['id', 'numero_vente', 'client', 'created_by', 'produits', 'created_at', 'montant_total',]


class FactureSerializer(serializers.ModelSerializer):
    total_paye = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, coerce_to_string=True)
    reste_a_payer = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, coerce_to_string=True)
    date_creation = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    vente = serializers.SerializerMethodField()
    client = serializers.SerializerMethodField()

    class Meta:
        model = Facture
        fields = [
            'numero_facture', 'vente', 'montant_total', 'total_paye',
            'reste_a_payer', 'status', 'date_creation', 'client', 'fichier_pdf',
        ]

    def get_client(self, obj):
        if obj.vente and obj.vente.client:
            client = obj.vente.client
            return {
                "nom": client.nom,
                "prenom": client.prenom,
                "telephone": client.telephone
            }
        return None
    
    def get_vente(self, obj):
        vente = obj.vente
        if vente:
            return {
                "id": vente.id,
                "numero_vente": vente.numero_vente
            }
        return None
    
    
    def to_representation(self, instance):
            data = super().to_representation(instance)
            # Réassigner les champs enrichis
            data['client'] = self.get_client(instance)
            data['vente'] = self.get_vente(instance)
            return data


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ['nom', 'prenom', 'telephone']

class VenteDetailSerializer(serializers.ModelSerializer):
    client = serializers.SerializerMethodField()
    produits = serializers.SerializerMethodField()
    vente = serializers.SerializerMethodField()
    facture = serializers.SerializerMethodField()
    total_remise = serializers.SerializerMethodField()
    total_ht = serializers.SerializerMethodField()
    total_ttc = serializers.SerializerMethodField()
    total_taxes = serializers.SerializerMethodField()
    total_autres = serializers.SerializerMethodField()
    totaux = serializers.SerializerMethodField()

    class Meta:
        model = Vente
        fields = ['id', 'client', 'produits', 'vente', 'facture', 'montant_total', 'total_autres','total_ttc', 'total_remise', 'total_taxes', 'total_ht',  'totaux']

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
                "sous_total_prix_vente_ht": str(p.sous_total_prix_vente_ht),
                "remise": str(p.remise),
                "autres": str(p.autres),
                "prix_ttc": str(p.prix_ttc)
            }
            for p in obj.produits.all()
        ]

    def get_vente(self, obj):
        return {
            "id": obj.id,
            "numero_vente": obj.numero_vente
        }
    
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
        
    def get_total_remise(self, obj):
        return str(obj.produits.aggregate(
            total=models.Sum('remise')
        )['total'] or 0)
        
    def get_total_ht(self, obj):
        return obj.produits.aggregate(total=Sum('sous_total_prix_vente_ht'))['total'] or 0

    def get_total_ttc(self, obj):
        return obj.produits.aggregate(total=Sum('prix_ttc'))['total'] or 0

    def get_total_taxes(self, obj):
        return obj.produits.aggregate(total=Sum('tax'))['total'] or 0

    def get_total_autres(self, obj):
        return obj.produits.aggregate(total=Sum('autres'))['total'] or 0
    
    def get_totaux(self, obj):
        return {
            "total_ht": self.get_total_ht(obj),
            "total_ttc": self.get_total_ttc(obj),
            "total_taxes": self.get_total_taxes(obj),
            "total_remise": self.get_total_remise(obj),
            "total_autres": self.get_total_autres(obj),
            "montant_total": obj.montant_total,
        }
    
        
class PaiementSerializer(serializers.ModelSerializer):
    reste_a_payer = serializers.SerializerMethodField()
    facture = serializers.SerializerMethodField()
    class Meta:
        model = Paiement
        fields = ("id", "facture", "montant_paye", "mode_paiement", "date_paiement", "reste_a_payer")
        read_only_fields = ("created_by",)  # 👈 NE PAS inclure dans Swagger POST
        
    def validate_montant_paye(self, value):
        if value <= 0:
            raise serializers.ValidationError("Le montant payé doit être un montant positif.")
        return value

    def validate_mode_paiement(self, value):
        MODES_VALIDES = dict(Paiement._meta.get_field('mode_paiement').choices).keys()
        if value not in MODES_VALIDES:
            raise serializers.ValidationError(f"Mode de paiement invalide. Choix valides : {', '.join(MODES_VALIDES)}")
        return value
    
    def get_facture(self, obj):
        facture = obj.facture
        if not facture:
            return None

        return {
            "id": facture.id,
            "numero_facture": facture.numero_facture,
            "vente": {
                "id": facture.vente.id,
                "numero_vente": facture.vente.numero_vente,
                "client": facture.vente.client.full_name if facture.vente.client else None,
            } if facture.vente else None,
            "montant_total": facture.montant_total,
            "status": facture.status,
            "date_creation": facture.date_creation,
        }
        
    def get_reste_a_payer(self, obj):
        facture = obj.facture
        return facture.reste_a_payer if facture else None
    
    def get_created_by(self, obj):
        user = obj.created_by
        if not user:
            return None
        return {
            "id": user.id,
            "nom": user.get_full_name() or user.username
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['created_by'] = self.get_created_by(instance)
        return data