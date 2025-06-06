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
    # Utilisé pour la création via le nom de catégorie
    categorie = serializers.SlugRelatedField(
        queryset=Categorie.objects.all(),
        slug_field='nom',
        write_only=True
    )
    # Affichage détaillé de la catégorie
    categorie_detail = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Modele
        fields = ['id', 'modele', 'categorie', 'categorie_detail']

    def get_categorie_detail(self, obj):
        if not obj.categorie:
            return None
        return {
            "id": obj.categorie.id,
            "nom": obj.categorie.nom,
            "image": obj.categorie.image.url if obj.categorie.image else None,
        }

# class ModeleSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Modele
#         fields = ['id', 'modele', 'categorie']
    
#     def get_categorie(self, obj):
#         if not obj.categorie:
#             return None
#         return {
#             "id": obj.categorie.id,
#             "nom": obj.categorie.nom,
#             "image": obj.categorie.image.url if obj.categorie.image else None,
#         }
    
#     def to_representation(self, instance):
#         data = super().to_representation(instance)
#         data['categorie'] = self.get_categorie(instance)
#         return data


class PureteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Purete
        fields = '__all__'


# class MarqueSerializer(serializers.ModelSerializer):
    
#     class Meta:
#         model = Marque
#         # fields = ('id', 'marque', 'prix', 'purete', 'creation_date', 'modification_date')
#         fields = '__all__'
        
    
#     def get_purete(self, obj):
#         modele = {
#             "id": obj.purete.id,
#             "purete": obj.purete.purete,
#         }
#         return modele

    
#     def to_representation(self, instance):
#         data = super().to_representation(instance)
#         data['purete'] = self.get_purete(instance)
#         return data


class MarqueSerializer(serializers.ModelSerializer):
    # Utilisé pour la création via le nom de catégorie
    purete = serializers.SlugRelatedField(
        queryset=Purete.objects.all(),
        slug_field='purete',
        write_only=True
    )
    # Affichage détaillé de la catégorie
    purete_detail = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Marque
        fields = ['id', 'marque', 'prix', 'purete', 'purete_detail']
    
    def get_purete_detail(self, obj):
        if not obj.purete:
            return None
        return {
                "id": obj.purete.id,
                "purete": obj.purete.purete
            }


class ProduitSerializer(serializers.ModelSerializer):
    # Utilisé pour la création via le nom de catégorie
    categorie = serializers.SlugRelatedField(
        queryset=Categorie.objects.all(),
        slug_field='nom',
        write_only=True
    )
    # Affichage détaillé de la catégorie
    categorie_detail = serializers.SerializerMethodField(read_only=True)
    
    # Utilisé pour la création via le nom de marque
    marque = serializers.SlugRelatedField(
        queryset=Marque.objects.all(),
        slug_field='marque',
        write_only=True
    )
    # Affichage détaillé de la marque
    marque_detail = serializers.SerializerMethodField(read_only=True)
    
    # Utilisé pour la création via le nom de modele
    modele = serializers.SlugRelatedField(
        queryset=Modele.objects.all(),
        slug_field='modele',
        write_only=True
    )
    # Affichage détaillé de la modele
    modele_detail = serializers.SerializerMethodField(read_only=True)
    
    # Utilisé pour la création via le nom de marque
    purete = serializers.SlugRelatedField(
        queryset=Purete.objects.all(),
        slug_field='purete',
        write_only=True
    )
    # Affichage détaillé de la catégorie
    purete_detail = serializers.SerializerMethodField(read_only=True)
    
    produit_url = serializers.SerializerMethodField()
    qr_code_url = serializers.SerializerMethodField()

    class Meta:
        model = Produit
        fields = (
            "id", "slug", "categorie", "categorie_detail", "nom", "produit_url", "sku", "qr_code_url", "image", "description",
            "status", "genre", "marque", "marque_detail", "modele", "modele_detail", "purete", "purete_detail", "matiere", "poids", "taille", "etat"
        )

    def get_categorie_detail(self, obj):
        if not obj.categorie:
            return None
        return {
            "id": obj.categorie.id,
            "nom": obj.categorie.nom,
            "image": obj.categorie.image.url if obj.categorie.image else None,
        }

    def get_marque_detail(self, obj):
        if not obj.marque:
            return None
        return {
            "id": obj.marque.id,
            "marque": obj.marque.marque,
            "prix": obj.marque.prix,
            "creation_date": obj.marque.creation_date,
            "modification_date": obj.marque.modification_date,
            "purete": {
                "id": obj.marque.purete.id if obj.marque.purete else None,
                "purete": obj.marque.purete.purete if obj.marque.purete else None,
            } if obj.marque.purete else None
        }

    def get_modele_detail(self, obj):
        if not obj.modele:
            return None
        return {
            "id": obj.modele.id,
            "modele": obj.modele.modele,
            "categorie": {
                "id": obj.modele.categorie.id if obj.modele.categorie else None,
                "nom": obj.modele.categorie.nom if obj.modele.categorie else None,
                "image": obj.modele.categorie.image.url if obj.modele.categorie and obj.modele.categorie.image else None,
            } if obj.modele.categorie else None
        }
    
    def get_purete_detail(self, obj):
        if not obj.purete:
            return None
        return {
            "id": obj.purete.id,
            "purete": obj.purete.purete
        }
    def get_produit_url(self, obj):
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(f"/produit/{obj.slug}")
        return f"https://www.rio-gold.com/produit/{obj.slug}" if obj.slug else None

    # def get_qr_code_url(self, obj):
    #     request = self.context.get('request')
    #     if obj.qr_code and request:
    #         return request.build_absolute_uri(obj.qr_code.url)
    #     elif obj.qr_code:
    #         return obj.qr_code.url
    #     return None
    
    def get_qr_code_url(self, obj):
        request = self.context.get('request')
        if obj.qr_code and request:
            return request.build_absolute_uri(obj.qr_code.url)
        elif obj.qr_code:
            return obj.qr_code.url
        return None


    

# class ProduitSerializer(serializers.ModelSerializer):
#     # Utilisé pour la création via le nom de catégorie
#     categorie = serializers.SlugRelatedField(
#         queryset=Categorie.objects.all(),
#         slug_field='nom',
#         write_only=True
#     )
#     # Affichage détaillé de la catégorie
#     categorie_detail = serializers.SerializerMethodField(read_only=True)
    
#     # Utilisé pour la création via le nom de marque
#     marque = serializers.SlugRelatedField(
#         queryset=Marque.objects.all(),
#         slug_field='marque',
#         write_only=True
#     )
#     # Affichage détaillé de la marque
#     marque_detail = serializers.SerializerMethodField(read_only=True)
    
#     # Utilisé pour la création via le nom de modele
#     modele = serializers.SlugRelatedField(
#         queryset=Modele.objects.all(),
#         slug_field='modele',
#         write_only=True
#     )
#     # Affichage détaillé de la modele
#     modele_detail = serializers.SerializerMethodField(read_only=True)
    
#     # Utilisé pour la création via le nom de marque
#     purete = serializers.SlugRelatedField(
#         queryset=Purete.objects.all(),
#         slug_field='purete',
#         write_only=True
#     )
#     # Affichage détaillé de la catégorie
#     purete_detail = serializers.SerializerMethodField(read_only=True)
    
#     produit_url = serializers.SerializerMethodField()
#     qr_code_url = serializers.SerializerMethodField()
#     categorie = serializers.SerializerMethodField()
#     marque = serializers.SerializerMethodField()
#     modele = serializers.SerializerMethodField()
#     purete = serializers.SerializerMethodField()

#     class Meta:
#         model = Produit
#         fields = (
#             "id", "categorie", "categorie_detail", "nom", "produit_url", "sku", "qr_code_url", "image", "description",
#             "status", "genre", "marque", "modele", "purete", "matiere", "poids", "taille", "etat"
#         )

#     def get_categorie_detail(self, obj):
#         if not obj.categorie:
#             return None
#         return {
#             "id": obj.categorie.id,
#             "nom": obj.categorie.nom,
#             "image": obj.categorie.image.url if obj.categorie.image else None,
#         }

#     def get_marque_detail(self, obj):
#         if not obj.marque:
#             return None
#         return {
#             "id": obj.marque.id,
#             "marque": obj.marque.marque,
#             "prix": obj.marque.prix,
#             "creation_date": obj.marque.creation_date,
#             "modification_date": obj.marque.modification_date,
#             "purete": {
#                 "id": obj.purete.id if obj.purete else None,
#                 "purete": obj.purete.purete if obj.purete else None,
#             } if obj.purete else None
#         }

#     def get_modele_detail(self, obj):
#         if not obj.modele:
#             return None
#         return {
#             "id": obj.modele.id,
#             "modele": obj.modele.modele,
#             "categorie": {
#                 "id": obj.categorie.id if obj.categorie else None,
#                 "nom": obj.categorie.nom if obj.categorie else None,
#                 "image": obj.categorie.image.url if obj.categorie.image else None,
#             } if obj.categorie else None
#         }

#     def get_purete_detail(self, obj):
#         if not obj.purete:
#             return None
#         return {
#             "id": obj.purete.id,
#             "purete": obj.purete.purete
#         }
#     def get_produit_url(self, obj):
#         request = self.context.get('request')
#         if request:
#             return request.build_absolute_uri(f"/produit/{obj.slug}")
#         return f"https://www.rio-gold.com/produit/{obj.slug}" if obj.slug else None

#     # def get_qr_code_url(self, obj):
#     #     request = self.context.get('request')
#     #     if obj.qr_code and request:
#     #         return request.build_absolute_uri(obj.qr_code.url)
#     #     elif obj.qr_code:
#     #         return obj.qr_code.url
#     #     return None
    
#     def get_qr_code_url(self, obj):
#         request = self.context.get('request')
#         if obj.qr_code and request:
#             return request.build_absolute_uri(obj.qr_code.url)
#         elif obj.qr_code:
#             return obj.qr_code.url
#         return None

#     def to_representation(self, instance):
#         data = super().to_representation(instance)
#         # Réassigner les champs enrichis
#         data['categorie'] = self.get_categorie(instance)
#         data['produit_url'] = self.get_produit_url(instance)
#         data['qr_code_url'] = self.get_qr_code_url(instance)
#         data['purete'] = self.get_purete(instance)
#         data['marque'] = self.get_marque(instance)
#         data['modele'] = self.get_modele(instance)
#         return data



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

