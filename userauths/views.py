import json
from datetime import timedelta

from django.core.mail import send_mail
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from backend.renderers import UserRenderer

from .auth_backend import EmailPhoneUsernameAuthenticationBackend as EoP
from .models import Profile, Role, User
from .serializers import (ProfileSerializer, RoleSerializers,
                          UserChangePasswordSerializer, UserDetailSerializer,
                          UserLoginSerializer, UserRegistrationSerializer)


# Create your views here.
# Generate Token Manually
def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


# Create your views here.
class UserRegistrationView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [UserRenderer]
    
    @swagger_auto_schema(
        operation_description="Register a new user",
        request_body=UserRegistrationSerializer,
        responses={
            status.HTTP_201_CREATED: openapi.Response('User created successfully', UserDetailSerializer),
            status.HTTP_400_BAD_REQUEST: openapi.Response('Bad Request')
        }
        # responses={
        #     201: openapi.Response(
        #         description="User successfully created",
        #         schema=UserRegistrationSerializer
        #     ),
        #     400: "Bad Request - Invalid input data"
        # }
    )
    
    def post(self, request, format=None):
        serializer = UserRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response({'message':'Registration Successful', "data": serializer.data}, status=status.HTTP_201_CREATED)


class UserLoginView(APIView):
    # renderer_classes = [UserRenderer]
    permission_classes = [AllowAny]
    
    # @swagger_auto_schema(
    #     operation_description="User login with email and password",
    #     request_body=UserLoginSerializer,
    #     responses={
    #         200: openapi.Response("Login successful", openapi.Schema(type=openapi.TYPE_OBJECT, properties={"token": openapi.Schema(type=openapi.TYPE_STRING)})),
    #         400: openapi.Response("Bad request", openapi.Schema(type=openapi.TYPE_OBJECT, properties={"detail": openapi.Schema(type=openapi.TYPE_STRING)}))
    #     }
    # )
    
    @swagger_auto_schema(
        operation_description="Login using email and password",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'user': openapi.Schema(type=openapi.TYPE_STRING, description='User'),
                'password': openapi.Schema(type=openapi.TYPE_STRING, description='User password'),
            },
        ),
        responses={
            200: openapi.Response(
                description="Login successful",
                examples={
                    'application/json': {
                        'access_token': 'string',
                        'refresh_token': 'string',
                    }
                },
            ),
            400: "Bad request",
            401: "Invalid credentials",
        },
    )
    
    def post(self, request, format=None):
        serializer = UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.data.get('user')
        password = serializer.data.get('password')
        user = EoP.authenticate(request, username=email, password=password)
        if user is not None:
            token = get_tokens_for_user(user)
            return Response({'token':token,'User_id':user.id,'email': user.email, 'username': user.username, 'user_role': user.user_role.role if user.user_role else "", 'msg':'Login Success'}, status=status.HTTP_200_OK)
        else:
            return Response({'errors':{'non_field_errors':['Email or Password is not Valid']}}, status=status.HTTP_404_NOT_FOUND)


# class UserChangePasswordView(generics.UpdateAPIView):

#     queryset = User.objects.all()
#     serializer_class = UserChangePasswordSerializer


class ValidateTokenView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    def get(self,request):
        return Response({"message": "Success"}, status=status.HTTP_200_OK)

class UserDetailUpdateView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    def get(self,request,pk):
        if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin':
            return Response({"message": "Access Denied"})
        detail= User.objects.get(id=pk)
        serializer = UserDetailSerializer(detail)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self,request,pk):
        if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin':
            return Response({"message": "Access Denied"})
        detail= User.objects.get(id=pk)
        serializer = UserDetailSerializer(detail,request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors,status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, pk):
        if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin':
            return Response({"message": "Access Denied"})
        user = User.objects.get(id=pk)
        if user is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# User list
class UsersView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        responses={200: openapi.Response('response description', UserDetailSerializer)},
    )
    def get(self, request):
        if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin':
            return Response({"message": "Access Denied"})
        users = User.objects.all()
        serializer = UserDetailSerializer(users, many=True)
        return Response(serializer.data)

# link to reset password in email
# class PasswordResetAPIView(APIView):
#     permission_classes = [AllowAny]

#     def post(self, request):
#         email = request.data.get('email')
#         user = User.objects.filter(email=email).first()
#         if user:
#             # Send password reset email (Django will handle token generation)
#             # You could also use the built-in Django mechanism here
#             send_mail(
#                 'Password Reset Request',
#                 'Click the link to reset your password...',
#                 'from@example.com',
#                 [email],
#                 fail_silently=False,
#             )
#             return Response({"message": "Password reset email sent."}, status=status.HTTP_200_OK)
#         return Response({"error": "User with this email does not exist."}, status=status.HTTP_400_BAD_REQUEST)

class RoleListCreateAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        responses={200: openapi.Response('response description', RoleSerializers)},
    )
    # def get(self, request):
    #     if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
    #         return Response({"message": "Access Denied"})
    #     roles = Role.objects.all()
    #     serializer = RoleSerializers(roles, many=True)
    #     print(serializer.data)
    #     return Response({'message':'listes des roles', "data": serializer.data})
    #     # return Response({'message':'Registration Successful', "data": serializer.data}, status=status.HTTP_201_CREATED)

    def get(self, request):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        roles = Role.objects.all()
        serializer = RoleSerializers(roles, many=True)
        return Response(serializer.data)
    
    @swagger_auto_schema(
        operation_description="User login with email and password",
        request_body=RoleSerializers,
        responses={
            200: openapi.Response("Login successful", openapi.Schema(type=openapi.TYPE_OBJECT, properties={"token": openapi.Schema(type=openapi.TYPE_STRING)})),
            400: openapi.Response("Bad request", openapi.Schema(type=openapi.TYPE_OBJECT, properties={"detail": openapi.Schema(type=openapi.TYPE_STRING)}))
        }
    )
    def post(self, request):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
        #     return Response({"message": "Access Denied"})
        serializer = RoleSerializers(data=request.data)
        # if serializer.is_valid():
        #     serializer.save()
        #     return Response(serializer.data, status=status.HTTP_201_CREATED)
        # return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        if serializer.is_valid():
            try:
                # Saving the data
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            except Exception as e:
                # Log the error if something goes wrong
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RoleDetailAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    def get_object(self, pk):
        try:
            return Role.objects.get(pk=pk)
        except Role.DoesNotExist:
            return None

    def get(self, request, pk):
        role = self.get_object(pk)
        if role is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = RoleSerializers(role)
        return Response(serializer.data)

    def put(self, request, pk):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
        #     return Response({"message": "Access Denied"})
        role = self.get_object(pk)
        if role is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = RoleSerializers(role, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        if request.user.user_role is not None and request.user.user_role.role != 'admin':
            return Response({"message": "Access Denied"})
        # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
        #     return Response({"message": "Access Denied"})
        role = self.get_object(pk)
        if role is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        role.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# profile
class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        responses={200: openapi.Response('response description', ProfileSerializer)},
    )
    def get(self, request, format=None):
        # Get the current user's profile
        try:
            profile = Profile.objects.get(user=request.user)
        except Profile.DoesNotExist:
            return Response({"detail": "Profile not found."}, status=404)
        
        serializer = ProfileSerializer(profile)
        return Response(serializer.data)

    @swagger_auto_schema(
        responses={200: openapi.Response('response description', ProfileSerializer)},
    )
    def put(self, request, format=None):
        # Get the current user's profile
        try:
            profile = Profile.objects.get(user=request.user)
        except Profile.DoesNotExist:
            return Response({"detail": "Profile not found."}, status=404)
        
        # Deserialize the data and update the profile
        serializer = ProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)
# end profile


# This is a DRF view defined as a Python function using the @api_view decorator.
# @api_view(['GET'])
# def getRoutes(request):
#     # It defines a list of API routes that can be accessed.
#     routes = [
#         '/api/token/',
#         '/api/register/',
#         '/api/token/refresh/',
#         '/api/test/'
#     ]
#     # It returns a DRF Response object containing the list of routes.
#     return Response(routes)



# from django.contrib.auth import authenticate, get_user_model
# from django.shortcuts import render
# from drf_yasg import openapi
# from drf_yasg.utils import swagger_auto_schema
# from knox.models import AuthToken
# from rest_framework import permissions, viewsets
# from rest_framework.permissions import IsAuthenticated
# from rest_framework.response import Response
# from rest_framework.views import APIView

# from backend.renderers import UserRenderer

# from .models import *
# from .serializers import *

# User = get_user_model()

# class LoginViewset(viewsets.ViewSet):
#     # renderer_classes = [UserRenderer]
#     permission_classes = [permissions.AllowAny]
#     serializer_class = LoginSerializer
    
#     @swagger_auto_schema(
#         operation_description="Create an example object",
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             properties={
#                 'email': openapi.Schema(type=openapi.TYPE_STRING),
#                 'password': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_PASSWORD),
#             },
#         ),
#         responses={201: 'Object created successfully'}
#     )

#     def create(self, request): 
#         serializer = self.serializer_class(data=request.data)
#         if serializer.is_valid(): 
#             email = serializer.validated_data['email']
#             password = serializer.validated_data['password']
#             user = authenticate(request, email=email, password=password)
#             if user: 
#                 _, token = AuthToken.objects.create(user)
#                 return Response(
#                     {
#                         "user": self.serializer_class(user).data,
#                         "token": token
#                     }
#                 )
#             else: 
#                 return Response({"error":"Invalid credentials"}, status=401)    
#         else: 
#             return Response(serializer.errors,status=400)



# class RegisterViewset(viewsets.ViewSet):
#     # renderer_classes = [UserRenderer]
#     permission_classes = [permissions.AllowAny]
#     queryset = User.objects.all()
#     serializer_class = RegisterSerializer

#     def create(self,request):
#         serializer = self.serializer_class(data=request.data)
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data)
#         else: 
#             return Response(serializer.errors,status=400)


# class UserViewset(viewsets.ViewSet):
#     # renderer_classes = [UserRenderer]
#     permission_classes = [permissions.IsAuthenticated]
#     queryset = User.objects.all()
#     # serializer_class = RegisterSerializer
#     serializer_class = UserDetailSerializer

#     def list(self,request):
#         if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
#             return Response({"message": "Access Denied"})
#         queryset = User.objects.all()
#         serializer = self.serializer_class(queryset, many=True)
#         return Response(serializer.data)
    

# # # User list
# # class UsersView(APIView):
# #     renderer_classes = [UserRenderer]
# #     permission_classes = [IsAuthenticated]
# #     def get(self, request):
# #         if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
# #             return Response({"message": "Access Denied"})
# #         users = User.objects.all()
# #         serializer = UserDetailSerializer(users, many=True)
# #         return Response(serializer.data)