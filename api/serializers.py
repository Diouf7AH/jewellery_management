from rest_framework import serializers

from store.serializers import MarquePuretePrixUpdateItemSerializer


class CommercialSettingsSerializer(serializers.Serializer):
    bijouterie_id = serializers.IntegerField(
        label="ID de la bijouterie",
        help_text="Identifiant de la bijouterie à configurer",
    )

    appliquer_tva = serializers.BooleanField(
        required=False,
        label="Activer TVA",
        help_text="Active ou désactive l'application de la TVA pour la bijouterie",
    )

    taux_tva = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        allow_null=True,
        label="Taux TVA (%)",
        help_text="Taux de TVA à appliquer (ex: 18.00). Ignoré si TVA désactivée.",
    )

    prix_marque_purete = MarquePuretePrixUpdateItemSerializer(
        many=True,
        required=False,
        label="Liste des prix journaliers",
        help_text="Liste des prix à mettre à jour pour chaque combinaison marque/pureté"
    )

    def validate_taux_tva(self, value):
        if value is None:
            return value
        if value < 0:
            raise serializers.ValidationError("Le taux TVA ne peut pas être négatif.")
        if value > 100:
            raise serializers.ValidationError("Le taux TVA ne peut pas dépasser 100%.")
        return value

    def validate(self, attrs):
        appliquer_tva = attrs.get("appliquer_tva")
        taux_tva = attrs.get("taux_tva")

        if appliquer_tva is True and taux_tva is None:
            raise serializers.ValidationError({
                "taux_tva": "Le taux TVA est requis lorsque la TVA est activée."
            })

        return attrs 

        return attrs 
