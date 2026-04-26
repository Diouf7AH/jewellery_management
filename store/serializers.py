from rest_framework import serializers

from store.models import (Bijouterie, Categorie, Gallery, Marque, MarquePurete,
                          MarquePuretePrixHistory, Modele, Produit, Purete)


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


# class MarqueSerializer(serializers.ModelSerializer):
#     # Utilisé pour la création via le nom de catégorie
#     purete = serializers.SlugRelatedField(
#         queryset=Purete.objects.all(),
#         slug_field='purete',
#         write_only=True
#     )
#     # Affichage détaillé de la catégorie
#     purete_detail = serializers.SerializerMethodField(read_only=True)

#     class Meta:
#         model = Marque
#         fields = ['id', 'marque', 'purete', 'purete_detail']
#         # fields = ['id', 'marque', 'prix', 'purete', 'purete_detail']
    
#     def get_purete_detail(self, obj):
#         if not obj.purete:
#             return None
#         return {
#                 "id": obj.purete.id,
#                 "purete": obj.purete.purete
#             }


class MarqueListSerializer(serializers.Serializer):
    marque = serializers.CharField()
    puretes = serializers.ListField()

#marque purete

class MarquePureteListSerializer(serializers.ModelSerializer):
    marque = serializers.SerializerMethodField()
    purete = serializers.SerializerMethodField()

    class Meta:
        model = MarquePurete
        fields = ['id', 'marque', 'purete', 'prix', 'date_ajout']

    def get_marque(self, obj):
        return {
            "id": obj.marque.id,
            "nom": obj.marque.marque
        }

    def get_purete(self, obj):
        return {
            "id": obj.purete.id,
            "purete": obj.purete.purete
        }

class PuretePrixInputSerializer(serializers.Serializer):
    purete_id = serializers.IntegerField()
    prix = serializers.DecimalField(max_digits=10, decimal_places=2)

    def validate_prix(self, value):
        """S'assure que le prix est positif ou nul."""
        if value < 0:
            raise serializers.ValidationError("Le prix doit être supérieur ou égal à 0.")
        return value


class MarquePureteSerializer(serializers.Serializer):
    # modele = serializers.CharField(max_length=100)
    marque = serializers.CharField(max_length=100)
    puretes = PuretePrixInputSerializer(many=True)

    # def validate_modele(self, value):
    #     """Nettoie et formate le nom du modèle."""
    #     return value.strip().title()

    def validate_marque(self, value):
        """Nettoie et formate le nom de la marque."""
        return value.strip().title()

    def validate(self, data):
        """Validation globale."""
        if not data.get("puretes"):
            raise serializers.ValidationError({"puretes": "Au moins une pureté est requise."})

        # Vérifie que les purete_id sont uniques dans la requête
        ids = [p["purete_id"] for p in data["puretes"]]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError({"puretes": "Les pureté_id doivent être uniques."})

        return data

#marque purete


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
            # "prix": obj.marque.prix,
            # "creation_date": obj.marque.creation_date,
            # "modification_date": obj.marque.modification_date,
            # "purete": {
            #     "id": obj.marque.purete.id if obj.marque.purete else None,
            #     "purete": obj.marque.purete.purete if obj.marque.purete else None,
            # } if obj.marque.purete else None
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
    purete_purete = serializers.CharField(source='purete.purete', read_only=True)

    class Meta:
        model = Produit
        fields = [
            'id', 'nom', 'sku', 'etat', 'status',
            'poids', 'taille',
            'categorie_nom', 'marque_nom', 'modele_nom', 'purete_purete',
            'image', 'description', 'date_ajout', 'date_modification',
            'galleries'
        ]

# class HistoriquePrixSerializer(serializers.ModelSerializer):
#     marque = MarqueSerializer()

#     class Meta:
#         model = MarquePuretePrixHistory
#         fields = '__all__'



class MarquePuretePrixUpdateItemSerializer(serializers.Serializer):
    marque = serializers.CharField(
        label="Nom de la marque",
        help_text="Nom de la marque (ex: local, dubai, italie)",
    )

    purete = serializers.CharField(
        label="Pureté",
        help_text="Pureté de la pureté (ex: 18, 21, 24)",
    )

    prix = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        label="Prix journalier",
        help_text="Prix par gramme pour cette combinaison marque/pureté",
    )

    def validate_marque(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("La marque est obligatoire.")
        return value

    def validate_purete(self, value):
        value = str(value).strip()
        if not value:
            raise serializers.ValidationError("La pureté est obligatoire.")
        return value

    def validate_prix(self, value):
        if value < 0:
            raise serializers.ValidationError("Le prix ne peut pas être négatif.")
        return value


# class CommercialSettingsSerializer(serializers.Serializer):
#     bijouterie_id = serializers.IntegerField(
#         label="ID de la bijouterie",
#         help_text="Identifiant de la bijouterie à configurer",
#     )

#     appliquer_tva = serializers.BooleanField(
#         required=False,
#         label="Activer TVA",
#         help_text="Active ou désactive l'application de la TVA pour la bijouterie",
#     )

#     taux_tva = serializers.DecimalField(
#         max_digits=5,
#         decimal_places=2,
#         required=False,
#         allow_null=True,
#         label="Taux TVA (%)",
#         help_text="Taux de TVA à appliquer (ex: 18.00). Ignoré si TVA désactivée.",
#     )

#     prix_marque_purete = MarquePuretePrixUpdateItemSerializer(
#         many=True,
#         required=False,
#         label="Liste des prix journaliers",
#         help_text="Liste des prix à mettre à jour pour chaque combinaison marque/pureté"
#     )

#     def validate_taux_tva(self, value):
#         if value is None:
#             return value
#         if value < 0:
#             raise serializers.ValidationError("Le taux TVA ne peut pas être négatif.")
#         if value > 100:
#             raise serializers.ValidationError("Le taux TVA ne peut pas dépasser 100%.")
#         return value

#     def validate(self, attrs):
#         appliquer_tva = attrs.get("appliquer_tva")
#         taux_tva = attrs.get("taux_tva")

#         if appliquer_tva is True and taux_tva is None:
#             raise serializers.ValidationError({
#                 "taux_tva": "Le taux TVA est requis lorsque la TVA est activée."
#             })

#         return attrs 


class MarquePuretePrixHistorySerializer(serializers.ModelSerializer):
    marque_nom = serializers.CharField(source="marque.marque", read_only=True)
    purete_nom = serializers.CharField(source="purete.purete", read_only=True)
    bijouterie_nom = serializers.CharField(source="bijouterie.nom", read_only=True)
    changed_by_username = serializers.CharField(source="changed_by.username", read_only=True)

    class Meta:
        model = MarquePuretePrixHistory
        fields = [
            "id",
            "marque_purete",
            "marque",
            "marque_nom",
            "purete",
            "purete_nom",
            "bijouterie",
            "bijouterie_nom",
            "ancien_prix",
            "nouveau_prix",
            "changed_by",
            "changed_by_username",
            "changed_at",
            "source",
            "note",
        ]
    

class MarquePuretePrixEvolutionPointSerializer(serializers.Serializer):
    date = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    prix = serializers.DecimalField(max_digits=12, decimal_places=2)

# class MarquePuretePrixEvolutionPointSerializer(serializers.Serializer):
#     date = serializers.DateTimeField()
#     prix = serializers.DecimalField(max_digits=14, decimal_places=2)
#     marque = serializers.CharField(required=False)
#     purete = serializers.CharField(required=False)
#     source = serializers.CharField(required=False, allow_null=True)
    

