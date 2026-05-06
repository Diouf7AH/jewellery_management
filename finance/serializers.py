# finance/serializers.py
from rest_framework import serializers

from .models import Depense


class DepenseSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField(read_only=True)
    paid_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Depense
        fields = "__all__"
        read_only_fields = [
            "status",
            "created_by",
            "paid_by",
            "paid_at",
            "cancelled_by",
            "cancelled_at",
        ]
        
        

