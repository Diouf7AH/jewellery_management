from rest_framework import serializers

from store.models import (Bijouterie, Categorie, Gallery, HistoriquePrix,
                          Marque, Modele, Produit, Purete)


# Define a serializer for the Category model
class BijouterieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bijouterie
        fields = '__all__'
        

class CategorieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categorie
        fields = '__all__'


# class TypeSerializer(serializers.ModelSerializer):
    
#     class Meta:
#         model = Type
#         fields = ('id', 'type', 'categorie',)
#         # fields = '__all__'
        
#     def get_categorie(self, obj):
#         categorie = {
#             "id": obj.categorie.id,
#             "nom": obj.categorie.nom,
#             "image": obj.categorie.image.url,
#             "active": obj.categorie.active,
#             "slug": obj.categorie.slug,
#         }
#         return categorie
    
#     def to_representation(self, instance):
#         data = super().to_representation(instance)
#         data['categorie'] = self.get_categorie(instance)
#         return data


class ModeleSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Modele
        fields = '__all__'
    
    #JSON
    # def get_type(self, obj):
    #     type = {
    #         "id": obj.type.id,
    #         "type": obj.type.type,
    #         "categorie" : {
    #             "id": obj.categorie.id,
    #             "nom": obj.categorie.nom,
    #             "image": obj.categorie.image.url,
    #             "active": obj.categorie.active,
    #             "slug": obj.categorie.slug,
    #     }
    #     }
    #     return type
    
    def get_categorie(self, obj):
        categorie = {
            "id": obj.categorie.id,
            "nom": obj.categorie.nom,
            "image": obj.categorie.image.url,
            "active": obj.categorie.active,
            "slug": obj.categorie.slug,
        }
        return categorie

    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['categorie'] = self.get_categorie(instance)
        return data


class PureteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Purete
        fields = '__all__'


class MarqueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Marque
        # fields = ('id', 'marque', 'prix', 'purete', 'creation_date', 'modification_date')
        fields = '__all__'
        
    
    def get_purete(self, obj):
        modele = {
            "id": obj.purete.id,
            "purete": obj.purete.purete,
        }
        return modele

    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['purete'] = self.get_purete(instance)
        return data



        # Define a serializer for the Gallery model
class GallerySerializer(serializers.ModelSerializer):
    # Serialize the related Product model

    class Meta:
        model = Gallery
        fields = '__all__'


class ProduitSerializer(serializers.ModelSerializer):
    # prix_vente = serializers.DecimalField(max_digits=12, decimal_places=2)
    # prix_vente = serializers.DecimalField(max_digits=12, decimal_places=2)
    class Meta:
        model = Produit
        fields = ( "id", "nom", "image", "prix_vente_grammes", "prix_avec_tax", "description", "status", "genre", "marque", "modele", "purete", "matiere", "poids", "quantite_en_stock", "taille", 'categorie' ) 
        # fields = '__all__'
        
        #JSON
        # def get_categorie(self, obj):
        #     categorie = {
        #         "id": obj.categorie.id,
        #         "nom": obj.categorie.nom,
        #         "image": obj.categorie.image.url,
        #         "active": obj.categorie.active,
        #         "slug": obj.categorie.slug,
        #     }
        #     return categorie   
        
        # # def get_type(self, obj):
        # #     type = {
        # #         "id": obj.type.id,
        # #         "type": obj.type.type,
        # #         "categorie": obj.type.categorie.nom,
        # #     }
        # #     return type
        
        # def get_purete(self, obj):
        #     purete = {
        #         "id": obj.purete.id,
        #         "purete": obj.purete.purete,
        #     }
        #     return purete
        
        # def get_modele(self, obj):
        #     modele = {
        #         "id": obj.modele.id,
        #         "modele": obj.modele.modele,
        #         "categorie" : {
        #             "id": obj.categorie.id,
        #             "nom": obj.categorie.nom,
        #             # "image": obj.categorie.image,
        #             "active": obj.categorie.active,
        #             "slug": obj.categorie.slug,
        #         }
        #     }
        #     return modele
        
        # def get_marque(self, obj):
        #     marque = {
        #         "id": obj.marque.id,
        #         "marque": obj.marque.marque,
        #         "prix": obj.marque.prix,
        #         "creation_date": obj.marque.creation_date,
        #         "modification_date": obj.marque.modification_date,
        #         "purete" : {
        #             "id": obj.purete.id,
        #             "purete": obj.purete.purete,
        #         }
        #     }
        #     return marque
        
        # def to_representation(self, instance):
        #     data = super().to_representation(instance)
        #     data['categorie'] = self.get_categorie(instance)
        #     # data['type'] = self.get_type(instance)
        #     data['purete'] = self.get_purete(instance)
        #     data['marque'] = self.get_marque(instance)
        #     data['modele'] = self.get_modele(instance)
        #     return data
        

class HistoriquePrixSerializer(serializers.ModelSerializer):
    marque = MarqueSerializer()

    class Meta:
        model = HistoriquePrix
        fields = '__all__'