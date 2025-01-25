from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from userauths.serializers import UserRegistrationSerializer

from .models import Vendor
from .serializer import VendorSerializer

# Create your views here.

class CreateVendorView(APIView):

    def post(self, request, *args, **kwargs):
        # First, create the User
        user_serializer = UserRegistrationSerializer(data=request.data['user'])
        if user_serializer.is_valid():
            user = user_serializer.save()  # Create the user

            # Then, create the Vendor associated with the User
            vendor_data = request.data['vendor']
            vendor_data['user'] = user.id  # Associate the user with the vendor
            vendor_serializer = VendorSerializer(data=vendor_data)
            if vendor_serializer.is_valid():
                vendor_serializer.save()  # Create the vendor
                return Response(vendor_serializer.data, status=status.HTTP_201_CREATED)
            else:
                return Response(vendor_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(user_serializer.errors, status=status.HTTP_400_BAD_REQUEST)