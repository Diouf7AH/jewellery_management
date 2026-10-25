import re
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import serializers

from backend import settings
from store.models import (Bijouterie, Categorie, Gallery, Marque, MarquePurete,
                          MarquePuretePrixHistory, Modele, Produit, Purete)


class BijouterieSerializer(serializers.ModelSerializer):
    """
    Serializer de gestion des bijouteries Rio-Gold.

    Règles métier :
    - Nom obligatoire et unique.
    - NINEA facultatif et unique.
    - TVA configurable par bijouterie.
    - Conservation du taux configuré.
    - Taux effectif de 0 % si TVA désactivée.
    """

    taux_tva_effectif = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = Bijouterie

        fields = [
            # Identification
            "id",
            "nom",

            # Contacts
            "telephone_portable_1",
            "telephone_portable_2",
            "telephone_portable_3",
            "telephone_portable_4",
            "telephone_portable_5",
            "telephone_fix",
            "adresse",

            # Informations légales
            "ninea",

            # TVA
            "appliquer_tva",
            "taux_tva",
            "taux_tva_effectif",

            # Logos
            "logo_blanc",
            "logo_noir",

            # Web / réseaux sociaux
            "nom_de_domaine",
            "tiktok",
            "facebook",
            "instagram",

            # Dates
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "taux_tva_effectif",
        ]

        extra_kwargs = {
            "nom": {
                "required": True,
                "allow_blank": False,
            },
            "ninea": {
                "required": False,
                "allow_null": True,
                "allow_blank": True,
                "validators": [],
            },
            "taux_tva": {
                "required": False,
                "allow_null": True,
            },
        }

    # ========================================================
    # VALIDATION DU NOM
    # ========================================================

    def validate_nom(self, value):
        nom = value.strip()

        if not nom:
            raise serializers.ValidationError(
                "Le nom de la bijouterie est obligatoire."
            )

        queryset = Bijouterie.objects.filter(
            nom__iexact=nom
        )

        if self.instance is not None:
            queryset = queryset.exclude(
                pk=self.instance.pk
            )

        if queryset.exists():
            raise serializers.ValidationError(
                "Une bijouterie avec ce nom existe déjà."
            )

        return nom

    # ========================================================
    # VALIDATION DU NINEA
    # ========================================================

    def validate_ninea(self, value):
        ninea = (value or "").strip().upper()

        if not ninea:
            return None

        if not re.fullmatch(r"[A-Z0-9]+", ninea):
            raise serializers.ValidationError(
                "Le NINEA doit contenir uniquement "
                "des lettres et des chiffres."
            )

        queryset = Bijouterie.objects.filter(
            ninea__iexact=ninea
        )

        if self.instance is not None:
            queryset = queryset.exclude(
                pk=self.instance.pk
            )

        if queryset.exists():
            raise serializers.ValidationError(
                "Ce NINEA est déjà utilisé "
                "par une autre bijouterie."
            )

        return ninea

    # ========================================================
    # VALIDATION GLOBALE
    # ========================================================

    def validate(self, attrs):
        attrs = super().validate(attrs)

        appliquer_tva = attrs.get(
            "appliquer_tva",
            getattr(self.instance, "appliquer_tva", False),
        )

        taux_tva = attrs.get(
            "taux_tva",
            getattr(self.instance, "taux_tva", None),
        )

        # TVA activée : taux obligatoire.
        if appliquer_tva and taux_tva is None:
            raise serializers.ValidationError({
                "taux_tva": (
                    "Le taux de TVA est obligatoire "
                    "lorsque la TVA est activée."
                )
            })

        # Vérifier le taux, même si la TVA est désactivée.
        if taux_tva is not None:
            if not (
                Decimal("0.00")
                <= taux_tva
                <= Decimal("100.00")
            ):
                raise serializers.ValidationError({
                    "taux_tva": (
                        "Le taux de TVA doit être compris "
                        "entre 0 et 100."
                    )
                })

        # Ne jamais effacer le taux configuré.
        return attrs



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
        fields = ['id', 'marque', 'purete', 'purete_detail']
        # fields = ['id', 'marque', 'prix', 'purete', 'purete_detail']
    
    def get_purete_detail(self, obj):
        if not obj.purete:
            return None
        return {
                "id": obj.purete.id,
                "purete": obj.purete.purete
            }


class MarqueListSerializer(serializers.Serializer):
    marque = serializers.CharField()
    puretes = serializers.ListField()


class PuretePrixSerializer(serializers.Serializer):
    purete_id = serializers.IntegerField()
    purete = serializers.CharField(read_only=True)
    prix = serializers.DecimalField(max_digits=10, decimal_places=2)


class MarqueListSerializer(serializers.Serializer):
    marque = serializers.CharField()
    puretes = PuretePrixSerializer(many=True)
    

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

class GallerySerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Gallery
        fields = [
            "id",
            "image_url",
            "active",
            "date",
        ]

    def get_image_url(self, obj):
        if not obj.image:
            return None

        request = self.context.get("request")

        if request:
            return request.build_absolute_uri(obj.image.url)

        return obj.image.url
    

# Conserver les imports existants de :
# Produit, Categorie, Marque, Modele, Purete,
# GallerySerializer et MarquePurete.


# ============================================================
# POURCENTAGES OCCASION AUTORISÉS
# ============================================================
class ProduitSerializer(serializers.ModelSerializer):
    """
    Serializer du catalogue Rio-Gold.

    Identité du produit :
        categorie + modele + marque
        + purete + poids + taille

    Fonctionnement :
        - Création : recherche ou création sans doublon.
        - Produit existant : retourne sa référence.
        - Modification : identité non modifiable.
        - Lecture : relations détaillées, prix et galerie.

    L'état neuf/occasion est géré dans ProduitLine.
    """

    # ========================================================
    # 1. IDENTIFIANTS DES RELATIONS
    # ========================================================

    categorie_id = serializers.PrimaryKeyRelatedField(
        queryset=Categorie.objects.all(),
        source="categorie",
        required=True,
    )

    modele_id = serializers.PrimaryKeyRelatedField(
        queryset=Modele.objects.all(),
        source="modele",
        required=False,
        allow_null=True,
    )

    marque_id = serializers.PrimaryKeyRelatedField(
        queryset=Marque.objects.all(),
        source="marque",
        required=True,
    )

    purete_id = serializers.PrimaryKeyRelatedField(
        queryset=Purete.objects.all(),
        source="purete",
        required=True,
    )

    # ========================================================
    # 2. IDENTIFIANTS EN LECTURE
    # ========================================================

    id = serializers.IntegerField(
        read_only=True,
    )

    uuid = serializers.UUIDField(
        read_only=True,
    )

    sku = serializers.CharField(
        read_only=True,
    )

    slug = serializers.SlugField(
        read_only=True,
    )

    # ========================================================
    # 3. DÉTAILS DES RELATIONS
    # ========================================================

    categorie_detail = serializers.SerializerMethodField()

    modele_detail = serializers.SerializerMethodField()

    marque_detail = serializers.SerializerMethodField()

    purete_detail = serializers.SerializerMethodField()

    # ========================================================
    # 4. PRIX DE VENTE AU GRAMME
    # ========================================================

    prix_vente_gramme = serializers.SerializerMethodField()

    # ========================================================
    # 5. URL DU PRODUIT
    # ========================================================

    produit_url = serializers.SerializerMethodField()

    # ========================================================
    # 6. GALERIE
    # ========================================================

    gallery = GallerySerializer(
        source="produit_gallery",
        many=True,
        read_only=True,
    )

    # ========================================================
    # 7. META
    # ========================================================

    class Meta:
        model = Produit

        fields = (
            # Identifiants
            "id",
            "uuid",
            "sku",
            "slug",

            # Relations
            "categorie_id",
            "modele_id",
            "marque_id",
            "purete_id",

            # Caractéristiques
            "poids",
            "taille",
            "matiere",
            "genre",

            # Informations
            "nom",
            "description",
            "image",

            # Informations calculées
            "prix_vente_gramme",
            "produit_url",

            # Galerie
            "gallery",

            # Détails des relations
            "categorie_detail",
            "modele_detail",
            "marque_detail",
            "purete_detail",
        )

        read_only_fields = (
            "id",
            "uuid",
            "sku",
            "slug",
        )

        extra_kwargs = {
            "nom": {
                "required": False,
                "allow_blank": True,
            },
            "description": {
                "required": False,
                "allow_null": True,
                "allow_blank": True,
            },
            "image": {
                "required": False,
                "allow_null": True,
            },
            "taille": {
                "required": False,
                "allow_null": True,
            },
            "matiere": {
                "required": False,
            },
            "genre": {
                "required": False,
            },
        }

    # ========================================================
    # 8. VALIDATION GLOBALE
    # ========================================================

    def validate(self, attrs):
        """
        Vérifie :
        - le poids ;
        - la taille ;
        - la cohérence catégorie / modèle ;
        - l'immuabilité des six caractéristiques.

        La recherche du produit existant est effectuée
        dans create(), et non ici.
        """

        attrs = super().validate(attrs)

        errors = {}

        instance = self.instance

        # ----------------------------------------------------
        # VALEURS EFFECTIVES
        # ----------------------------------------------------

        categorie = attrs.get(
            "categorie",
            getattr(instance, "categorie", None),
        )

        modele = attrs.get(
            "modele",
            getattr(instance, "modele", None),
        )

        marque = attrs.get(
            "marque",
            getattr(instance, "marque", None),
        )

        purete = attrs.get(
            "purete",
            getattr(instance, "purete", None),
        )

        poids = attrs.get(
            "poids",
            getattr(instance, "poids", None),
        )

        taille = attrs.get(
            "taille",
            getattr(instance, "taille", None),
        )

        # ----------------------------------------------------
        # POIDS
        # ----------------------------------------------------

        if poids is not None and poids <= Decimal("0.00"):
            errors["poids"] = (
                "Le poids doit être strictement "
                "supérieur à zéro."
            )

        # ----------------------------------------------------
        # TAILLE
        # ----------------------------------------------------

        if taille is not None and taille < Decimal("0.00"):
            errors["taille"] = (
                "La taille ne peut pas être négative."
            )

        # ----------------------------------------------------
        # COHÉRENCE CATÉGORIE / MODÈLE
        # ----------------------------------------------------

        if categorie is not None and modele is not None:

            if modele.categorie_id != categorie.pk:
                errors["modele_id"] = (
                    "Le modèle sélectionné n'appartient "
                    "pas à la catégorie du produit."
                )

        # ----------------------------------------------------
        # PROTECTION DE L'IDENTITÉ EN MODIFICATION
        # ----------------------------------------------------

        if instance is not None:

            valeurs_actuelles = (
                instance.categorie_id,
                instance.modele_id,
                instance.marque_id,
                instance.purete_id,
                instance.poids,
                instance.taille,
            )

            valeurs_nouvelles = (
                categorie.pk if categorie else None,
                modele.pk if modele else None,
                marque.pk if marque else None,
                purete.pk if purete else None,
                poids,
                taille,
            )

            if valeurs_actuelles != valeurs_nouvelles:
                errors["produit"] = (
                    "Impossible de modifier les six "
                    "caractéristiques d'identification "
                    "d'un produit existant. "
                    "Veuillez créer une nouvelle "
                    "référence catalogue."
                )

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    # ========================================================
    # 9. CRÉATION OU RÉCUPÉRATION
    # ========================================================

    def create(self, validated_data):
        """
        Retourne :
            - un nouveau produit si inexistant ;
            - le produit existant sinon.

        self.produit_created :
            True  = nouveau produit
            False = produit déjà existant

        Le message d'information est construit
        par ProduitCreateAPIView.
        """

        data = validated_data.copy()

        categorie = data.pop("categorie")
        modele = data.pop("modele", None)
        marque = data.pop("marque")
        purete = data.pop("purete")

        poids = data.pop("poids")
        taille = data.pop("taille", None)

        try:
            produit, created = Produit.get_or_create_catalogue(
                categorie_id=categorie.pk,
                modele_id=(
                    modele.pk if modele else None
                ),
                marque_id=marque.pk,
                purete_id=purete.pk,
                poids=poids,
                taille=taille,
                **data,
            )

        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                exc.message_dict
                if hasattr(exc, "message_dict")
                else exc.messages
            )

        except IntegrityError:
            raise serializers.ValidationError({
                "produit": (
                    "Impossible d'enregistrer le produit "
                    "en raison d'un conflit d'unicité. "
                    "Veuillez réessayer ou vérifier "
                    "les références existantes."
                )
            })

        self.produit_created = created

        return produit

    # ========================================================
    # 10. MISE À JOUR
    # ========================================================

    def update(self, instance, validated_data):
        """
        Autorise les modifications documentaires :
            - nom
            - description
            - image
            - matiere
            - genre

        Les six caractéristiques d'identification
        restent inchangées.
        """

        try:
            return super().update(
                instance,
                validated_data,
            )

        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                exc.message_dict
                if hasattr(exc, "message_dict")
                else exc.messages
            )

        except IntegrityError:
            raise serializers.ValidationError({
                "produit": (
                    "Impossible de mettre à jour "
                    "le produit en raison d'un "
                    "conflit d'unicité."
                )
            })

    # ========================================================
    # 11. DÉTAIL CATÉGORIE
    # ========================================================

    def get_categorie_detail(self, obj):
        if not obj.categorie_id:
            return None

        return {
            "id": obj.categorie.id,
            "nom": obj.categorie.nom,
        }

    # ========================================================
    # 12. DÉTAIL MODÈLE
    # ========================================================

    def get_modele_detail(self, obj):
        if not obj.modele_id:
            return None

        return {
            "id": obj.modele.id,
            "modele": obj.modele.modele,
        }

    # ========================================================
    # 13. DÉTAIL MARQUE
    # ========================================================

    def get_marque_detail(self, obj):
        if not obj.marque_id:
            return None

        return {
            "id": obj.marque.id,
            "marque": obj.marque.marque,
        }

    # ========================================================
    # 14. DÉTAIL PURETÉ
    # ========================================================

    def get_purete_detail(self, obj):
        if not obj.purete_id:
            return None

        return {
            "id": obj.purete.id,
            "purete": obj.purete.purete,
        }

    # ========================================================
    # 15. URL DU PRODUIT
    # ========================================================

    def get_produit_url(self, obj):
        return obj.produit_url

    # ========================================================
    # 16. PRIX DE VENTE AU GRAMME
    # ========================================================

    def get_prix_vente_gramme(self, obj):
        """
        Récupère le prix de vente au gramme
        depuis MarquePurete.
        """

        if not obj.marque_id or not obj.purete_id:
            return None

        tarif = (
            MarquePurete.objects
            .filter(
                marque_id=obj.marque_id,
                purete_id=obj.purete_id,
            )
            .first()
        )

        if tarif is None:
            return None

        prix = getattr(
            tarif,
            "prix",
            None,
        )

        if prix is None:
            return None

        return str(prix)


class ProduitRechercheSerializer(serializers.ModelSerializer):
    categorie_id = serializers.IntegerField(read_only=True)
    categorie_nom = serializers.CharField(
        source="categorie.nom",
        read_only=True,
    )

    modele_id = serializers.IntegerField(read_only=True)
    modele_nom = serializers.CharField(
        source="modele.modele",
        read_only=True,
        allow_null=True,
    )

    marque_id = serializers.IntegerField(read_only=True)
    marque_nom = serializers.CharField(
        source="marque.marque",
        read_only=True,
    )

    purete_id = serializers.IntegerField(read_only=True)
    purete_nom = serializers.CharField(
        source="purete.purete",
        read_only=True,
    )

    class Meta:
        model = Produit

        fields = [
            "id",
            "uuid",
            "sku",
            "nom",
            "categorie_id",
            "categorie_nom",
            "modele_id",
            "modele_nom",
            "marque_id",
            "marque_nom",
            "purete_id",
            "purete_nom",
            "poids",
            "taille",
            "matiere",
            "genre",
            "image",
        ]

        read_only_fields = fields
        

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
    modifier_par_username = serializers.CharField(source="modifier_par.username", read_only=True)

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
            "modifier_par",
            "modifier_par_username",
            "date_modification",
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
    
# pour le backend/bijouteries.py
class BijouterieMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bijouterie
        fields = [
            "id",
            "nom",
        ]
        read_only_fields = fields