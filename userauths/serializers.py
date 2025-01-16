from rest_framework import serializers

from .models import Role, User


class UserRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields=['email', 'username', 'firstname', 'lastname', 'phone', 'address', 'password', 'user_role']
        extra_kwargs={
            'password':{'write_only':True}
        }

    # def get_username(self, obj):
    #     return obj.user.username
    
    def create(self, validate_data):
        return User.objects.create_user(**validate_data)


class UserLoginSerializer(serializers.ModelSerializer):
    # email = serializers.EmailField(max_length=255)
    user = serializers.CharField(max_length=100)
    class Meta:
        model = User
        fields = ['user', 'password']


# change password
class UserChangePasswordSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    class Meta:
        model = User
        fields = ['password']
    
    def update(self, instance, validated_data):

        instance.set_password(validated_data['password'])
        instance.save()

        return instance



class UserDetailSerializer(serializers.ModelSerializer):
  class Meta:
    model = User
    fields = ['id', 'email', 'username', 'firstname', 'lastname', 'phone', 'address', 'user_role']

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

class RoleSerializers(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = '__all__'


# from django.contrib.auth import get_user_model
# from rest_framework import serializers

# from .models import *

# User = get_user_model()



# class LoginSerializer(serializers.Serializer):
#     email = serializers.EmailField()
#     password = serializers.CharField()

#     def to_representation(self, instance):
#         ret = super().to_representation(instance)
#         ret.pop('password', None)
#         return ret


# class RegisterSerializer(serializers.ModelSerializer):
#     class Meta: 
#         model = User
#         fields = ('id','email','password')
#         extra_kwargs = { 'password': {'write_only':True}}
    
#     def create(self, validated_data):
#         user = User.objects.create_user(**validated_data)
#         return user
    
    
# class UserDetailSerializer(serializers.ModelSerializer):
#   class Meta:
#     model = User
#     fields = ['id', 'email', 'dateNaiss', 'username', 'first_name', 'last_name', 'phone', 'address', 'user_role', 'is_active', 'is_admin', 'created_at', 'updated_at', 'updated_at']

#   def get_role(self, obj):
#     role = {}
#     if obj.user_role:
#         role = {
#             "id": obj.user_role.id,
#             "name": obj.user_role.role,
#         }
#     return role

#   def to_representation(self, instance):
#     data = super().to_representation(instance)
#     data['user_role'] = self.get_role(instance)
#     return data