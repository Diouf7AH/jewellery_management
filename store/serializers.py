from rest_framework import serializers

from store.models import (Bijouterie, Categorie, Gallery, HistoriquePrix,
                        Marque, Modele, Produit, Purete)


# Define a serializer for the Category model
class BijouterieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bijouterie
        fields = ['id', 'nom', 'telephone_portable_1', 'telephone_portable_2', 'telephone_portable_3', 'telephone_portable_4', 'telephone_portable_5', 'telephone_fix', 'adresse', 'logo_blanc', 'logo_noir', 'nom_de_domaine', 'tiktok', 'facebook', 'instagram']
        

class CategorieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categorie
        fields = ['id', 'nom', 'image',]


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
    
    # def get_categorie(self, obj):
    #     categorie = {
    #         "id": obj.categorie.id,
    #         "nom": obj.categorie.nom,
    #         "image": obj.categorie.image.url,
    #         "active": obj.categorie.active,
    #         "slug": obj.categorie.slug,
    #     }
    #     return categorie

    
    # def to_representation(self, instance):
    #     data = super().to_representation(instance)
    #     data['categorie'] = self.get_categorie(instance)
    #     return data


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


class ProduitSerializer(serializers.ModelSerializer):
    categorie = serializers.SerializerMethodField()
    marque = serializers.SerializerMethodField()
    modele = serializers.SerializerMethodField()
    purete = serializers.SerializerMethodField()
    
    class Meta:
        model = Produit
        fields = ( "id", 'categorie' , "nom", "sku", "image", "description", "status", "genre", "marque", "modele", "purete", "matiere", "poids", "taille", "etat") 
        # fields = '__all__'
        
        def get_categorie(self, obj):
            return obj.categorie.nom if obj.categorie else None

        def get_marque(self, obj):
            return obj.marque.nom if obj.marque else None

        def get_modele(self, obj):
            return obj.modele.nom if obj.modele else None

        def get_purete(self, obj):
            return obj.purete.purete if obj.purete else None
        
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
        


class GallerySerializer(serializers.ModelSerializer):
    produit_nom = serializers.CharField(source='produit.nom', read_only=True)
    image_url = serializers.SerializerMethodField()
    class Meta:
        model = Gallery
        fields = ['id', 'produit_nom', 'image', 'active', 'image_url', 'date']
        
    def get_image_url(self, obj):
        request = self.context.get('request')
        if request is not None and obj.image:
            return request.build_absolute_uri(obj.image.url)
        return obj.image.url if obj.image else None

class ProduitWithGallerySerializer(serializers.ModelSerializer):
    galleries = GallerySerializer(source='produit_gallery', many=True, read_only=True)
    categorie_nom = serializers.CharField(source='categorie.nom', read_only=True)
    marque_nom = serializers.CharField(source='marque.marque', read_only=True)
    modele_nom = serializers.CharField(source='modele.modele', read_only=True)
    purete_valeur = serializers.CharField(source='purete.purete', read_only=True)

    class Meta:
        model = Produit
        fields = [
            'id', 'nom', 'sku', 'etat', 'status',
            'poids', 'taille',
            'categorie_nom', 'marque_nom', 'modele_nom', 'purete_valeur',
            'image', 'description', 'date_ajout', 'date_modification',
            'galleries'
        ]

class HistoriquePrixSerializer(serializers.ModelSerializer):
    marque = MarqueSerializer()

    class Meta:
        model = HistoriquePrix
        fields = '__all__'