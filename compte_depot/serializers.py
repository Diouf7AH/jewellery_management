# compte_depot/serializers.py

from decimal import Decimal

from rest_framework import serializers

from userauths.serializers import UserMiniSerializer

from .models import ClientDepot, CompteDepot, CompteDepotTransaction


class ClientDepotSerializer(serializers.ModelSerializer):

    class Meta:
        model = ClientDepot
        fields = [
            "id",
            "nom",
            "prenom",
            "telephone",
            "photo",
        ]

    def validate_telephone(self, value):
        if not value:
            raise serializers.ValidationError(
                "Le téléphone est obligatoire."
            )

        value = str(value).strip()

        if not value.isdigit():
            raise serializers.ValidationError(
                "Le téléphone doit contenir uniquement des chiffres."
            )

        if len(value) < 9:
            raise serializers.ValidationError(
                "Le téléphone doit contenir au moins 9 chiffres."
            )

        return value
    
    


# ============================================================
# CLIENT DEPOT - OUVERTURE DE COMPTE
# ============================================================

class ClientDepotOuvertureSerializer(serializers.Serializer):
    nom = serializers.CharField(max_length=100)
    prenom = serializers.CharField(max_length=100)
    telephone = serializers.CharField(max_length=15)

    def validate_telephone(self, value):
        value = str(value).strip()

        if not value.isdigit() or len(value) < 9:
            raise serializers.ValidationError(
                "Numéro de téléphone invalide."
            )

        return value

# =========================
# COMPTE DEPOT (LECTURE)
# =========================
class CompteDepotSerializer(serializers.ModelSerializer):
    client = ClientDepotSerializer(read_only=True)

    telephone = serializers.CharField(
        source="client.telephone",
        read_only=True,
    )

    created_by = UserMiniSerializer(
        read_only=True,
    )

    bijouterie_id = serializers.IntegerField(
        source="client.bijouterie_id",
        read_only=True,
    )

    bijouterie_nom = serializers.CharField(
        source="client.bijouterie.nom",
        read_only=True,
    )

    class Meta:
        model = CompteDepot
        fields = [
            "id",
            "client",
            "telephone",
            "numero_compte",
            "solde",
            "bijouterie_id",
            "bijouterie_nom",
            "created_at",
            "created_by",
        ]

        read_only_fields = fields


class ClientRechercheDepotSerializer(serializers.Serializer):
    client_existe = serializers.BooleanField()
    compte_existe = serializers.BooleanField()
    client = serializers.DictField(
        allow_null=True
    )
    compte = serializers.DictField(
        allow_null=True
    )


# ============================================================
# CREATE OR DEPOSIT INPUT
# ============================================================


class CreateOrDepotCompteSerializer(serializers.Serializer):
    client = ClientDepotOuvertureSerializer()

    montant = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )

    bijouterie_id = serializers.IntegerField(
        required=False,
        allow_null=True,
    )

# =========================
# TRANSACTION OUTPUT
# =========================
class CompteDepotTransactionSerializer(serializers.ModelSerializer):
    compte_numero = serializers.CharField(
        source="compte.numero_compte",
        read_only=True,
    )

    client_nom = serializers.CharField(
        source="compte.client.nom",
        read_only=True,
    )

    client_prenom = serializers.CharField(
        source="compte.client.prenom",
        read_only=True,
    )

    client_telephone = serializers.CharField(
        source="compte.client.telephone",
        read_only=True,
    )

    bijouterie_id = serializers.IntegerField(
        source="compte.client.bijouterie_id",
        read_only=True,
    )

    bijouterie_nom = serializers.CharField(
        source="compte.client.bijouterie.nom",
        read_only=True,
    )

    type_transaction_label = serializers.CharField(
        source="get_type_transaction_display",
        read_only=True,
    )

    statut_label = serializers.CharField(
        source="get_statut_display",
        read_only=True,
    )

    user = UserMiniSerializer(
        read_only=True,
    )

    class Meta:
        model = CompteDepotTransaction

        fields = [
            "id",

            "type_transaction",
            "type_transaction_label",

            "montant",
            "date_transaction",

            "statut",
            "statut_label",

            "compte",
            "compte_numero",

            "client_nom",
            "client_prenom",
            "client_telephone",

            "bijouterie_id",
            "bijouterie_nom",

            "solde_avant",
            "solde_apres",

            "reference",
            "commentaire",

            "user",
        ]

        read_only_fields = fields

# =========================
# DEPOT / RETRAIT VIA TELEPHONE
# =========================
class CompteDepotTelephoneTransactionSerializer(serializers.Serializer):
    telephone = serializers.CharField()

    montant = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    def validate_telephone(self, value):
        value = str(value).strip()

        if not value:
            raise serializers.ValidationError(
                "Le téléphone est obligatoire."
            )

        if not value.isdigit():
            raise serializers.ValidationError(
                "Le téléphone doit contenir uniquement des chiffres."
            )

        if len(value) < 9:
            raise serializers.ValidationError(
                "Le téléphone doit contenir au moins 9 chiffres."
            )

        return value

    def validate_montant(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError(
                "Le montant doit être supérieur à 0."
            )

        return value
    
    
