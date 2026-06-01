# stock_matiere_premiere/serializers.py

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from purchase.models import Fournisseur
from sale.models import Client
from store.models import MATIERE, Purete

from .models import (AchatMatierePremiere, AchatMatierePremiereItem,
                     MatierePremiereStock, RachatClient, RachatClientItem,
                     VenteMatierePremiere)


def generate_ticket_number(prefix, model_class):
    today = timezone.localdate()
    date_part = today.strftime("%Y%m%d")
    base = f"{prefix}-{date_part}"

    last = (
        model_class.objects
        .filter(numero_ticket__startswith=base)
        .order_by("-id")
        .first()
    )

    if not last:
        next_number = 1
    else:
        try:
            next_number = int(last.numero_ticket.split("-")[-1]) + 1
        except Exception:
            next_number = 1

    return f"{base}-{next_number:04d}"


# class ClientRachatSerializer(serializers.Serializer):
#     nom = serializers.CharField(required=True, allow_blank=False)
#     prenom = serializers.CharField(required=True, allow_blank=False)
#     telephone = serializers.CharField(required=True, allow_blank=False)
#     address = serializers.CharField(required=True, allow_blank=False)


# class RachatClientItemInputSerializer(serializers.Serializer):
#     description = serializers.CharField()
#     matiere = serializers.ChoiceField(choices=MATIERE)
#     purete = serializers.SlugRelatedField(slug_field="purete",queryset=Purete.objects.all(),)
#     poids = serializers.DecimalField(max_digits=14,decimal_places=3,min_value=Decimal("0.001"),)



# class RachatClientCreateSerializer(serializers.Serializer):
#     # bijouterie_id = serializers.IntegerField(required=False)
#     bijouterie = serializers.CharField(required=False, allow_blank=True)
#     client = ClientRachatSerializer()
#     cni_client = serializers.CharField(
#         required=False,
#         allow_blank=True,
#         allow_null=True
#     )

#     montant_total = serializers.DecimalField(
#         max_digits=16,
#         decimal_places=2,
#         min_value=Decimal("0.01"),
#     )
#     mode_paiement = serializers.CharField(default="especes")
#     mention = serializers.CharField(required=False, allow_blank=True, allow_null=True)
#     items = RachatClientItemInputSerializer(many=True)

#     def validate(self, attrs):
#         if not attrs.get("items"):
#             raise serializers.ValidationError({
#                 "items": "Au moins une ligne de rachat est obligatoire."
#             })
#         return attrs

#     def _get_or_create_client(self, client_data):
#         telephone = client_data["telephone"]
#         nom = client_data["nom"]
#         prenom = client_data["prenom"]
#         address = client_data["address"]

#         client = Client.objects.filter(telephone=telephone).first()

#         if client:
#             updated_fields = []

#             if not getattr(client, "nom", None):
#                 client.nom = nom
#                 updated_fields.append("nom")

#             if not getattr(client, "prenom", None):
#                 client.prenom = prenom
#                 updated_fields.append("prenom")

#             if hasattr(client, "address") and not getattr(client, "address", None):
#                 client.address = address
#                 updated_fields.append("address")

#             if updated_fields:
#                 client.save(update_fields=updated_fields)

#             return client

#         create_data = {
#             "nom": nom,
#             "prenom": prenom,
#             "telephone": telephone,
#         }

#         if hasattr(Client, "address"):
#             create_data["address"] = address

#         return Client.objects.create(**create_data)

#     @transaction.atomic
#     def create(self, validated_data):
#         bijouterie = self.context["bijouterie"]
        
#         # champ utilisé seulement pour Swagger / input
#         validated_data.pop("bijouterie", None)

#         client_data = validated_data.pop("client")
#         items_data = validated_data.pop("items")

#         client = self._get_or_create_client(client_data)

#         rachat = RachatClient.objects.create(
#             numero_ticket=generate_ticket_number("RCH", RachatClient),
#             client=client,
#             bijouterie=bijouterie,
#             montant_total=validated_data["montant_total"],
#             mode_paiement=validated_data.get("mode_paiement", "especes"),
#             adresse_client=client_data["address"],
#             mention=validated_data.get("mention"),
#             cni_client=validated_data.get("cni_client"),
#             payment_status=RachatClient.PAYMENT_PENDING,
#         )

#         for item_data in items_data:
#             RachatClientItem.objects.create(
#                 rachat=rachat,
#                 description=item_data["description"],
#                 matiere=item_data["matiere"],
#                 purete=item_data["purete"],
#                 poids=item_data["poids"],
#             )

#         return rachat



class ClientRachatSerializer(serializers.Serializer):
    nom = serializers.CharField(required=True, allow_blank=False)
    prenom = serializers.CharField(required=True, allow_blank=False)
    telephone = serializers.CharField(required=True, allow_blank=False)
    address = serializers.CharField(required=True, allow_blank=False)


class RachatClientItemInputSerializer(serializers.Serializer):
    description = serializers.CharField()
    matiere = serializers.ChoiceField(choices=MATIERE)
    purete = serializers.SlugRelatedField(
        slug_field="purete",
        queryset=Purete.objects.all(),
    )
    poids = serializers.DecimalField(
        max_digits=14,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )


class RachatClientCreateSerializer(serializers.Serializer):
    bijouterie = serializers.CharField(required=False, allow_blank=True)
    client = ClientRachatSerializer()
    cni_client = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    montant_total = serializers.DecimalField(
        max_digits=16,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    mode_paiement = serializers.CharField(default="especes")
    mention = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    items = RachatClientItemInputSerializer(many=True)

    def validate(self, attrs):
        if not attrs.get("items"):
            raise serializers.ValidationError({
                "items": "Au moins une ligne de rachat est obligatoire."
            })
        return attrs

    def _get_or_create_client(self, client_data):
        telephone = client_data["telephone"]
        nom = client_data["nom"]
        prenom = client_data["prenom"]
        address = client_data["address"]

        client = Client.objects.filter(telephone=telephone).first()

        if client:
            updated_fields = []

            if not getattr(client, "nom", None):
                client.nom = nom
                updated_fields.append("nom")

            if not getattr(client, "prenom", None):
                client.prenom = prenom
                updated_fields.append("prenom")

            if hasattr(client, "address") and not getattr(client, "address", None):
                client.address = address
                updated_fields.append("address")

            if updated_fields:
                client.save(update_fields=updated_fields)

            return client

        create_data = {
            "nom": nom,
            "prenom": prenom,
            "telephone": telephone,
        }

        if hasattr(Client, "address"):
            create_data["address"] = address

        return Client.objects.create(**create_data)

    @transaction.atomic
    def create(self, validated_data):
        bijouterie = self.context["bijouterie"]

        validated_data.pop("bijouterie", None)

        client_data = validated_data.pop("client")
        items_data = validated_data.pop("items")

        client = self._get_or_create_client(client_data)

        rachat = RachatClient.objects.create(
            numero_ticket=generate_ticket_number("RCH", RachatClient),
            client=client,
            bijouterie=bijouterie,
            montant_total=validated_data["montant_total"],
            mode_paiement=validated_data.get("mode_paiement", "especes"),
            adresse_client=client_data["address"],
            mention=validated_data.get("mention"),
            cni_client=validated_data.get("cni_client"),
            payment_status=RachatClient.PAYMENT_PENDING,
        )

        for item_data in items_data:
            RachatClientItem.objects.create(
                rachat=rachat,
                description=item_data["description"],
                matiere=item_data["matiere"],
                purete=item_data["purete"],
                poids=item_data["poids"],
            )

        return rachat
    


class RaffinageCreateSerializer(serializers.Serializer):
    matiere = serializers.ChoiceField(choices=MATIERE)

    purete_avant = serializers.SlugRelatedField(
        slug_field="purete",
        queryset=Purete.objects.all(),
    )

    purete_apres = serializers.SlugRelatedField(
        slug_field="purete",
        queryset=Purete.objects.all(),
    )

    poids_entree = serializers.DecimalField(
        max_digits=14,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )

    poids_sortie = serializers.DecimalField(
        max_digits=14,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )

    description = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    def validate(self, attrs):
        if attrs["poids_sortie"] > attrs["poids_entree"]:
            raise serializers.ValidationError({
                "poids_sortie": "Le poids sortie ne peut pas être supérieur au poids entrée."
            })
        return attrs


# class RachatClientItemOutputSerializer(serializers.ModelSerializer):
#     purete = serializers.StringRelatedField()
#     movement_id = serializers.IntegerField(source="movement.id", read_only=True)

#     class Meta:
#         model = RachatClientItem
#         fields = [
#             "id",
#             "description",
#             "matiere",
#             "purete",
#             "poids",
#             "movement_id",
#         ]

class RachatClientItemOutputSerializer(serializers.ModelSerializer):
    purete = serializers.StringRelatedField()
    movement = serializers.SerializerMethodField()

    class Meta:
        model = RachatClientItem
        fields = [
            "id",
            "description",
            "matiere",
            "purete",
            "poids",
            "movement",
        ]

    def get_movement(self, obj):
        if not obj.movement:
            return None

        return {
            "id": obj.movement.id,
            "uuid": str(obj.movement.uuid) if getattr(obj.movement, "uuid", None) else None,
            "source": obj.movement.source,
            "source_display": obj.movement.get_source_display(),
            "created_at": obj.movement.created_at,
        }


# class RachatClientDetailSerializer(serializers.ModelSerializer):
#     client = serializers.StringRelatedField()
#     bijouterie = serializers.StringRelatedField()
#     items = RachatClientItemOutputSerializer(many=True, read_only=True)

#     class Meta:
#         model = RachatClient
#         fields = [
#             "id",
#             "numero_ticket",
#             "client",
#             "cni_client",
#             "bijouterie",
#             "montant_total",
#             "mode_paiement",
#             "adresse_client",
#             "mention",
#             "payment_status",
#             "paid_at",
#             "paid_by",
#             "status",
#             "created_at",
#             "items",
#         ]

class RachatClientDetailSerializer(serializers.ModelSerializer):
    client = serializers.StringRelatedField()
    bijouterie = serializers.StringRelatedField()
    attestation_url = serializers.SerializerMethodField()
    ticket_url = serializers.SerializerMethodField()

    paid_by = serializers.StringRelatedField(read_only=True)
    cancelled_by = serializers.StringRelatedField(read_only=True)
    payment_status_display = serializers.CharField(source="get_payment_status_display",read_only=True,)
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    items = RachatClientItemOutputSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = RachatClient
        fields = [
                "id",
                "uuid",
                "numero_ticket",
                "client",
                "cni_client",
                "bijouterie",
                "montant_total",
                "mode_paiement",
                "adresse_client",
                "mention",

                "payment_status",
                "payment_status_display",
                "paid_at",
                "paid_by",

                "status",
                "status_display",

                "cancelled_at",
                "cancelled_by",
                "cancel_reason",
                "created_at",

                "ticket_url",
                "attestation_url",
                "items",
            ]

    def get_ticket_url(self, obj):
        request = self.context.get("request")

        if not request:
            return None

        return request.build_absolute_uri(
            f"/api/rachats-clients/{obj.uuid}/ticket-58mm/"
        )

    def get_attestation_url(self, obj):
        request = self.context.get("request")

        if not request:
            return None

        if obj.payment_status != RachatClient.PAYMENT_PAID:
            return None

        return request.build_absolute_uri(
            f"/api/rachats-clients/{obj.uuid}/attestation/"
        )



class CancelRachatClientSerializer(serializers.Serializer):
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Motif de l'annulation."
    )


class ReverseRachatClientSerializer(serializers.Serializer):
    reason = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=500,
        help_text="Motif obligatoire de la correction après paiement."
    )

    def validate_reason(self, value):
        value = value.strip()

        if len(value) < 5:
            raise serializers.ValidationError(
                "Le motif doit contenir au moins 5 caractères."
            )

        return value

class FournisseurInputSerializer(serializers.Serializer):
    nom = serializers.CharField(required=True, allow_blank=False)
    prenom = serializers.CharField(required=True, allow_blank=False)
    telephone = serializers.CharField(required=True, allow_blank=False)
    address = serializers.CharField(required=True, allow_blank=False)


class AchatMatierePremiereItemInputSerializer(serializers.Serializer):
    description = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    matiere = serializers.ChoiceField(
        choices=MATIERE
    )

    purete = serializers.SlugRelatedField(
        slug_field="purete",
        queryset=Purete.objects.all(),
    )

    poids = serializers.DecimalField(
        max_digits=14,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )


class AchatMatierePremiereCreateSerializer(serializers.Serializer):
    fournisseur = FournisseurInputSerializer()
    montant_total = serializers.DecimalField(
        max_digits=16,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    bijouterie_id = serializers.IntegerField(required=False)
    mode_paiement = serializers.CharField(default="especes")
    items = AchatMatierePremiereItemInputSerializer(many=True)

    def validate(self, attrs):
        if not attrs.get("items"):
            raise serializers.ValidationError({
                "items": "Au moins une ligne d'achat est obligatoire."
            })
        return attrs

    def _get_or_create_fournisseur(self, data):
        telephone = data["telephone"]
        nom = data["nom"]
        prenom = data["prenom"]
        address = data["address"]

        fournisseur = Fournisseur.objects.filter(telephone=telephone).first()

        if fournisseur:
            updated_fields = []

            if not getattr(fournisseur, "nom", None):
                fournisseur.nom = nom
                updated_fields.append("nom")

            if not getattr(fournisseur, "prenom", None):
                fournisseur.prenom = prenom
                updated_fields.append("prenom")

            if hasattr(fournisseur, "address") and not getattr(fournisseur, "address", None):
                fournisseur.address = address
                updated_fields.append("address")

            if updated_fields:
                fournisseur.save(update_fields=updated_fields)

            return fournisseur

        create_data = {
            "nom": nom,
            "prenom": prenom,
            "telephone": telephone,
        }

        if hasattr(Fournisseur, "address"):
            create_data["address"] = address

        return Fournisseur.objects.create(**create_data)

    @transaction.atomic
    def create(self, validated_data):
        bijouterie = self.context["bijouterie"]

        fournisseur_data = validated_data.pop("fournisseur")
        items_data = validated_data.pop("items")

        fournisseur = self._get_or_create_fournisseur(fournisseur_data)

        achat = AchatMatierePremiere.objects.create(
            numero_ticket=generate_ticket_number("ACHMP", AchatMatierePremiere),
            fournisseur=fournisseur,
            bijouterie=bijouterie,
            montant_total=validated_data["montant_total"],
            mode_paiement=validated_data.get("mode_paiement", "especes"),
            adresse_fournisseur=fournisseur_data["address"],
            payment_status=AchatMatierePremiere.PAYMENT_PENDING,
        )

        for item_data in items_data:
            AchatMatierePremiereItem.objects.create(
                achat=achat,
                description=item_data.get("description"),
                matiere=item_data["matiere"],
                purete_id=item_data["purete_id"],
                poids=item_data["poids"],
            )

        return achat


class AchatMatierePremiereItemOutputSerializer(serializers.ModelSerializer):
    purete = serializers.StringRelatedField()
    movement_id = serializers.IntegerField(source="movement.id", read_only=True)

    class Meta:
        model = AchatMatierePremiereItem
        fields = [
            "id",
            "description",
            "matiere",
            "purete",
            "poids",
            "movement_id",
        ]


class AchatMatierePremiereDetailSerializer(serializers.ModelSerializer):
    fournisseur = serializers.StringRelatedField()
    bijouterie = serializers.StringRelatedField()
    items = AchatMatierePremiereItemOutputSerializer(many=True, read_only=True)

    class Meta:
        model = AchatMatierePremiere
        fields = [
            "id",
            "numero_ticket",
            "fournisseur",
            "bijouterie",
            "montant_total",
            "mode_paiement",
            "adresse_fournisseur",
            "payment_status",
            "paid_at",
            "paid_by",
            "status",
            "created_at",
            "items",
        ]


class ReverseAchatMatierePremiereSerializer(serializers.Serializer):
    reason = serializers.CharField(
        required=True,
        allow_blank=False,
        help_text="Motif obligatoire de la correction."
    )
    
################################################################
#####################   Rafinage   #############################
################################################################
class RaffinageCreateSerializer(serializers.Serializer):
    matiere = serializers.ChoiceField(
        choices=MATIERE
    )

    purete_avant = serializers.SlugRelatedField(
        slug_field="purete",
        queryset=Purete.objects.all(),
    )

    purete_apres = serializers.SlugRelatedField(
        slug_field="purete",
        queryset=Purete.objects.all(),
    )

    poids_entree = serializers.DecimalField(
        max_digits=14,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )

    poids_sortie = serializers.DecimalField(
        max_digits=14,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )

    description = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    def validate(self, attrs):
        if attrs["poids_sortie"] > attrs["poids_entree"]:
            raise serializers.ValidationError({
                "poids_sortie": (
                    "Le poids sortie ne peut pas être supérieur au poids entrée."
                )
            })

        if attrs["purete_avant"] == attrs["purete_apres"]:
            raise serializers.ValidationError({
                "purete_apres": (
                    "La pureté après raffinage doit être différente de la pureté avant."
                )
            })

        return attrs


###################################################################
#####################  Vente de matiere premiere###################
###################################################################
class VenteMatierePremiereCreateSerializer(serializers.Serializer):
    source_stock = serializers.ChoiceField(
        choices=VenteMatierePremiere.SOURCE_CHOICES
    )

    client = serializers.SlugRelatedField(
        slug_field="telephone",
        queryset=Client.objects.all(),
        required=False,
        allow_null=True,
    )

    matiere = serializers.ChoiceField(
        choices=MATIERE
    )

    purete = serializers.SlugRelatedField(
        slug_field="purete",
        queryset=Purete.objects.all(),
    )

    poids = serializers.DecimalField(
        max_digits=14,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )

    prix_gramme = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )

    def validate(self, attrs):
        attrs["montant_total"] = attrs["poids"] * attrs["prix_gramme"]
        return attrs


####################################################################
