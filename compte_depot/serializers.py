# compte_depot/serializers.py

from rest_framework import serializers

from userauths.serializers import UserMiniSerializer

from .models import ClientDepot, CompteDepot, CompteDepotTransaction


# =========================
# CLIENT DEPOT
# =========================
class ClientDepotSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientDepot
        fields = [
            "id",
            "nom",
            "prenom",
            "telephone",
            "address",
            "CNI",
            "photo",
        ]

    def validate_telephone(self, value):
        if not value:
            raise serializers.ValidationError("Le téléphone est obligatoire.")
        value = str(value).strip()
        if not value.isdigit():
            raise serializers.ValidationError("Le téléphone doit contenir uniquement des chiffres.")
        if len(value) < 9:
            raise serializers.ValidationError("Le téléphone doit contenir au moins 9 chiffres.")
        return value


# =========================
# COMPTE DEPOT (LECTURE)
# =========================
class CompteDepotSerializer(serializers.ModelSerializer):
    client = ClientDepotSerializer(read_only=True)
    telephone = serializers.CharField(source="client.telephone", read_only=True)
    created_by = UserMiniSerializer(read_only=True)

    class Meta:
        model = CompteDepot
        fields = [
            "id",
            "client",
            "telephone",
            "numero_compte",
            "solde",
            "date_creation",
            "created_by",
        ]
        read_only_fields = fields


# =========================
# CREATE OR DEPOSIT INPUT
# =========================
class CreateOrDepositCompteSerializer(serializers.Serializer):
    client = ClientDepotSerializer()
    montant = serializers.DecimalField(max_digits=12, decimal_places=2)

    def validate_montant(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("Le montant doit être supérieur à 0.")
        return value


# =========================
# CREATE TRANSACTION INPUT
# =========================
class CompteDepotTransactionCreateSerializer(serializers.Serializer):
    montant = serializers.DecimalField(max_digits=12, decimal_places=2)
    reference = serializers.CharField(required=False, allow_blank=True)
    commentaire = serializers.CharField(required=False, allow_blank=True)

    def validate_montant(self, value):
        if value <= 0:
            raise serializers.ValidationError("Le montant doit être supérieur à 0.")
        return value


# =========================
# TRANSACTION OUTPUT
# =========================
class CompteDepotTransactionSerializer(serializers.ModelSerializer):
    compte_numero = serializers.CharField(source="compte.numero_compte", read_only=True)
    client_nom = serializers.CharField(source="compte.client.nom", read_only=True)
    client_prenom = serializers.CharField(source="compte.client.prenom", read_only=True)
    client_telephone = serializers.CharField(source="compte.client.telephone", read_only=True)
    type_transaction_label = serializers.CharField(source="get_type_transaction_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    user = UserMiniSerializer(read_only=True)

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
            "solde_avant",
            "solde_apres",
            "reference",
            "commentaire",
            "user",
        ]
        read_only_fields = fields
        


