from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import *

User = get_user_model()

class RoleSerializers(serializers.Serializer):
    class Meta:
        model = Role
        fields = '__all__'

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret.pop('password', None)
        return ret


class RegisterSerializer(serializers.ModelSerializer):
    class Meta: 
        model = User
        fields = ('id','email','password')
        extra_kwargs = { 'password': {'write_only':True}}
    
    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user
    
    
class UserDetailSerializer(serializers.ModelSerializer):
  class Meta:
    model = User
    fields = ['id', 'email', 'dateNaiss', 'username', 'first_name', 'last_name', 'phone', 'address', 'user_role', 'is_active', 'is_admin', 'created_at', 'updated_at', 'updated_at']

  def get_role(self, obj):
    role = {}
    if obj.user_role:
        role = {
            "id": obj.user_role.id,
            "name": obj.user_role.role,
        }
    return role

  def to_representation(self, instance):
    data = super().to_representation(instance)
    data['user_role'] = self.get_role(instance)
    return data