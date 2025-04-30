class CompteBancaireSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompteBancaire
        fields = ['id', 'client_banque', 'numero_compte', 'solde', 'date_creation',]
        


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ['id', 'compte', 'type_transaction', 'montant', 'date_transaction', 'user']