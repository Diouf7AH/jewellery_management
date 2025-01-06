from django.contrib.auth import authenticate, get_user_model
from django.shortcuts import render
from knox.models import AuthToken
from rest_framework import permissions, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.renderers import UserRenderer

from .models import *
from .serializers import *

User = get_user_model()

class LoginViewset(viewsets.ViewSet):
    renderer_classes = [UserRenderer]
    permission_classes = [permissions.AllowAny]
    serializer_class = LoginSerializer

    def create(self, request): 
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid(): 
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']
            user = authenticate(request, email=email, password=password)
            if user: 
                _, token = AuthToken.objects.create(user)
                return Response(
                    {
                        "user": self.serializer_class(user).data,
                        "token": token
                    }
                )
            else: 
                return Response({"error":"Invalid credentials"}, status=401)    
        else: 
            return Response(serializer.errors,status=400)



class RegisterViewset(viewsets.ViewSet):
    renderer_classes = [UserRenderer]
    permission_classes = [permissions.AllowAny]
    queryset = User.objects.all()
    serializer_class = RegisterSerializer

    def create(self,request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        else: 
            return Response(serializer.errors,status=400)


class UserViewset(viewsets.ViewSet):
    renderer_classes = [UserRenderer]
    permission_classes = [permissions.IsAuthenticated]
    queryset = User.objects.all()
    # serializer_class = RegisterSerializer
    serializer_class = UserDetailSerializer

    def list(self,request):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        queryset = User.objects.all()
        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data)
    

# # User list
# class UsersView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]
#     def get(self, request):
#         if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
#             return Response({"message": "Access Denied"})
#         users = User.objects.all()
#         serializer = UserDetailSerializer(users, many=True)
#         return Response(serializer.data)