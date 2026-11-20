from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from reparation.models import PaiementReparation, Reparation, ReparationBijou
from reparation.services.reparation_service import creer_reparation

# ============================================================
# BIJOU D'UNE RÉPARATION — LECTURE
# ============================================================

class ReparationBijouSerializer(serializers.ModelSerializer):

    class Meta:
        model = ReparationBijou

        fields = [
            "id",
            "numero_ligne",
            "type_bijou",
            "description_bijou",
            "poids",
            "purete",
            "etat_reception",
            "travail_demande",
            "travail_effectue",
            "prix_reparation",
        ]

        read_only_fields = fields


# ============================================================
# BIJOU D'UNE RÉPARATION — CRÉATION
# ============================================================

class ReparationBijouCreateSerializer(serializers.Serializer):

    type_bijou = serializers.CharField(
        max_length=100,
    )

    description_bijou = serializers.CharField()

    poids = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        required=False,
        allow_null=True,
    )

    purete = serializers.CharField(
        max_length=30,
        required=False,
        allow_blank=True,
        default="",
    )

    etat_reception = serializers.CharField()

    travail_demande = serializers.CharField()

    prix_reparation = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )

    def validate_poids(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError(
                "Le poids doit être supérieur à zéro."
            )

        return value


# ============================================================
# PAIEMENT — LECTURE
# ============================================================

class PaiementReparationSerializer(serializers.ModelSerializer):

    mode_paiement = serializers.CharField(
        source="mode_paiement.code",
        read_only=True,
    )

    numero_compte_depot = serializers.CharField(
        source="compte_depot.numero_compte",
        read_only=True,
        default=None,
    )

    class Meta:
        model = PaiementReparation

        fields = [
            "id",
            "mode_paiement",
            "montant_paye",
            "numero_compte_depot",
            "reference",
            "date_paiement",
        ]

        read_only_fields = fields


# ============================================================
# RÉPARATION — LISTE
# ============================================================

class ReparationListSerializer(serializers.ModelSerializer):

    bijouterie_nom = serializers.CharField(
        source="bijouterie.nom",
        read_only=True,
    )

    nombre_bijoux = serializers.IntegerField(
        read_only=True,
    )

    paiement_effectue = serializers.BooleanField(
        read_only=True,
    )

    est_restituee = serializers.BooleanField(
        read_only=True,
    )

    class Meta:
        model = Reparation

        fields = [
            "id",
            "uuid",
            "numero_reparation",
            "bijouterie",
            "bijouterie_nom",
            "client",
            "vendeur",
            "nombre_bijoux",
            "prix_convenu",
            "date_depot",
            "date_prevue",
            "statut",
            "paiement_effectue",
            "est_restituee",
        ]

        read_only_fields = fields


# ============================================================
# RÉPARATION — DÉTAIL COMPLET
# ============================================================

class ReparationDetailSerializer(serializers.ModelSerializer):

    bijouterie_nom = serializers.CharField(
        source="bijouterie.nom",
        read_only=True,
    )

    bijoux = ReparationBijouSerializer(
        many=True,
        read_only=True,
    )

    paiement = PaiementReparationSerializer(
        read_only=True,
        default=None,
    )

    nombre_bijoux = serializers.IntegerField(
        read_only=True,
    )

    montant_total_bijoux = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    paiement_effectue = serializers.BooleanField(
        read_only=True,
    )

    est_restituee = serializers.BooleanField(
        read_only=True,
    )

    class Meta:
        model = Reparation

        fields = [
            "id",
            "uuid",
            "numero_reparation",
            "bijouterie",
            "bijouterie_nom",
            "client",
            "vendeur",
            "bijoux",
            "nombre_bijoux",
            "prix_convenu",
            "montant_total_bijoux",
            "date_depot",
            "date_prevue",
            "statut",
            "paiement_effectue",
            "paiement",
            "date_restitution",
            "restitue_par",
            "est_restituee",
        ]

        read_only_fields = fields


# ============================================================
# RÉPARATION — CRÉATION AVEC PLUSIEURS BIJOUX
# ============================================================

class ReparationCreateSerializer(serializers.Serializer):

    bijouterie_id = serializers.IntegerField(
        min_value=1,
    )

    client_id = serializers.IntegerField(
        min_value=1,
    )

    vendeur_id = serializers.IntegerField(
        min_value=1,
    )

    date_prevue = serializers.DateField(
        required=False,
        allow_null=True,
    )

    bijoux = ReparationBijouCreateSerializer(
        many=True,
        allow_empty=False,
    )

    def validate_bijoux(self, value):
        if not value:
            raise serializers.ValidationError(
                "Ajoutez au moins un bijou."
            )

        return value

    def validate(self, attrs):
        bijoux = attrs["bijoux"]

        total = sum(
            (
                bijou["prix_reparation"]
                for bijou in bijoux
            ),
            Decimal("0.00"),
        )

        if total <= 0:
            raise serializers.ValidationError({
                "bijoux": (
                    "Le montant total doit être positif."
                )
            })

        # Le montant total est uniquement indicatif ici.
        # Le service doit le recalculer lui-même.
        return attrs

    def create(self, validated_data):
        """
        Délègue la création au service métier.

        Le service doit :
        - vérifier les permissions ;
        - vérifier le client et le vendeur ;
        - calculer le total ;
        - créer le dossier ;
        - créer les bijoux ;
        - vérifier la cohérence du total ;
        - effectuer toutes les écritures atomiquement.
        """

        request = self.context.get("request")

        if request is None:
            raise serializers.ValidationError(
                "Le contexte de la requête est obligatoire."
            )

        try:
            return creer_reparation(
                bijouterie_id=validated_data["bijouterie_id"],
                client_id=validated_data["client_id"],
                vendeur_id=validated_data["vendeur_id"],
                date_prevue=validated_data.get("date_prevue"),
                bijoux_data=validated_data["bijoux"],
                user=request.user,
            )

        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise serializers.ValidationError(
                    exc.message_dict
                ) from exc

            raise serializers.ValidationError(
                exc.messages
            ) from exc


# ============================================================
# SUIVI — MODIFICATION DU STATUT
# ============================================================

class ReparationStatutSerializer(serializers.Serializer):

    nouveau_statut = serializers.ChoiceField(
        choices=[
            Reparation.Statut.EN_COURS,
            Reparation.Statut.PRET,
            Reparation.Statut.ANNULE,
        ]
    )


# ============================================================
# TRAVAUX EFFECTUÉS SUR CHAQUE BIJOU
# ============================================================

class ReparationBijouTravailSerializer(serializers.Serializer):

    bijou_id = serializers.IntegerField(
        min_value=1,
    )

    travail_effectue = serializers.CharField(
        allow_blank=False,
        trim_whitespace=True,
    )


class ReparationTravauxSerializer(serializers.Serializer):

    bijoux = ReparationBijouTravailSerializer(
        many=True,
        allow_empty=False,
    )

    def validate_bijoux(self, value):
        ids = [
            ligne["bijou_id"]
            for ligne in value
        ]

        if len(ids) != len(set(ids)):
            raise serializers.ValidationError(
                "Un bijou ne peut apparaître "
                "qu'une seule fois."
            )

        return value


# ============================================================
# PAIEMENT — UNE SEULE LIGNE
# ============================================================

class PaiementReparationLigneSerializer(serializers.Serializer):

    mode_paiement = serializers.CharField(
        max_length=50,
    )

    montant_paye = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )

    numero_compte_depot = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )

    reference = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
        default="",
    )


class PaiementReparationCreateSerializer(serializers.Serializer):

    lignes = PaiementReparationLigneSerializer(
        many=True,
        allow_empty=False,
    )

    idempotency_key = serializers.UUIDField()

    def validate_lignes(self, value):
        if len(value) != 1:
            raise serializers.ValidationError(
                "Le paiement d'une réparation "
                "doit utiliser exactement "
                "un seul mode de paiement."
            )

        ligne = value[0]

        if (
            ligne["mode_paiement"] == "depot"
            and not ligne.get("numero_compte_depot")
        ):
            raise serializers.ValidationError(
                "Le numéro de compte dépôt est obligatoire."
            )

        return value


# ============================================================
# RESTITUTION
# ============================================================
class ReparationRestitutionSerializer(serializers.Serializer):

    remise_confirmee = serializers.BooleanField(
        required=True,
    )

    def validate_remise_confirmee(self, value):
        if value is not True:
            raise serializers.ValidationError(
                "La remise physique de tous les bijoux "
                "doit être confirmée."
            )

        return value
    
    
