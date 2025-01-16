from io import BytesIO

import qrcode
from django.http import HttpResponse
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from knox.auth import TokenAuthentication
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.renderers import UserRenderer
from store.models import Bijouterie, Categorie, Marque, Modele, Produit, Purete
from store.serializers import (BijouterieSerializer, CategorieSerializer,
                               MarqueSerializer, ModeleSerializer,
                               ProduitSerializer, PureteSerializer)


# Create your views here.
class BijouterieListCreateAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        responses={200: openapi.Response('response description', BijouterieSerializer)},
        )
    def get(self, request):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        bijouteries = Bijouterie.objects.all()
        serializer = BijouterieSerializer(bijouteries, many=True)
        return Response(serializer.data)
    
    @swagger_auto_schema(
        operation_description="Register a new user",
        request_body=BijouterieSerializer,
        responses={
            status.HTTP_201_CREATED: openapi.Response('User created successfully', BijouterieSerializer),
            status.HTTP_400_BAD_REQUEST: openapi.Response('Bad Request')
        }
    )
    def post(self, request):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
        #     return Response({"message": "Access Denied"})
        serializer = BijouterieSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BijouterieDetailAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    def get_object(self, pk):
        try:
            return Bijouterie.objects.get(pk=pk)
        except Bijouterie.DoesNotExist:
            return None

    def get(self, request, pk):
        bijouterie = self.get_object(pk)
        if bijouterie is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = BijouterieSerializer(bijouterie)
        return Response(serializer.data)

    def put(self, request, pk):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
        #     return Response({"message": "Access Denied"})
        bijouterie = self.get_object(pk)
        if bijouterie is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = BijouterieSerializer(bijouterie, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
        #     return Response({"message": "Access Denied"})
        bijouterie = self.get_object(pk)
        if bijouterie is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        bijouterie.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CategorieListCreateAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        responses={200: openapi.Response('response description', CategorieSerializer)},
        )
    def get(self, request):
        categories = Categorie.objects.all()
        serializer = CategorieSerializer(categories, many=True)
        return Response(serializer.data)
    
    @swagger_auto_schema(
        operation_description="Register a new user",
        request_body=CategorieSerializer,
        responses={
            status.HTTP_201_CREATED: openapi.Response('User created successfully', CategorieSerializer),
            status.HTTP_400_BAD_REQUEST: openapi.Response('Bad Request')
        }
    )
    def post(self, request):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
        #     return Response({"message": "Access Denied"})
        serializer = CategorieSerializer(data=request.data)
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
    


class CategorieDetailAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    def get_object(self, slug):
        try:
            return Categorie.objects.get(slug=slug)
        except Categorie.DoesNotExist:
            return None

    def get(self, request, slug):
        categorie = self.get_object(slug)
        if categorie is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = CategorieSerializer(categorie)
        return Response(serializer.data)

    def put(self, request, slug):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
        #     return Response({"message": "Access Denied"})
        categorie = self.get_object(slug)
        if categorie is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = CategorieSerializer(categorie, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, slug):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
        #     return Response({"message": "Access Denied"})
        categorie = self.get_object(slug)
        if categorie is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        categorie.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# class TypeListCreateAPIView(APIView):
#     # renderer_classes = [UserRenderer]
#     # permission_classes = [IsAuthenticated]
#     def get(self, request):
#         types = Type.objects.all()
#         serializer = TypeSerializer(types, many=True)
#         return Response(serializer.data)

#     def post(self, request):
#         # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
#         #     return Response({"message": "Access Denied"})
#         serializer = TypeSerializer(data=request.data)
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data, status=status.HTTP_201_CREATED)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# class TypeDetailAPIView(APIView):
#     # renderer_classes = [UserRenderer]
#     # permission_classes = [IsAuthenticated]
#     def get_object(self, pk):
#         try:
#             return Type.objects.get(pk=pk)
#         except Type.DoesNotExist:
#             return None

#     def get(self, request, pk):
#         type_instance = self.get_object(pk)
#         if type_instance is None:
#             return Response(status=status.HTTP_404_NOT_FOUND)
#         serializer = TypeSerializer(type_instance)
#         return Response(serializer.data)

#     def put(self, request, pk):
#         # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
#         #     return Response({"message": "Access Denied"})
#         type_instance = self.get_object(pk)
#         if type_instance is None:
#             return Response(status=status.HTTP_404_NOT_FOUND)
#         serializer = TypeSerializer(type_instance, data=request.data)
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#     def delete(self, request, pk):
#         # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
#             # return Response({"message": "Access Denied"})
#         type_instance = self.get_object(pk)
#         if type_instance is None:
#             return Response(status=status.HTTP_404_NOT_FOUND)
#         type_instance.delete()
#         return Response(status=status.HTTP_204_NO_CONTENT)


class PureteListCreateAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        responses={200: openapi.Response('response description', PureteSerializer)},
        )
    def get(self, request):
        puretes = Purete.objects.all()
        serializer = PureteSerializer(puretes, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description="Register a new user",
        request_body=PureteSerializer,
        responses={
            status.HTTP_201_CREATED: openapi.Response('User created successfully', PureteSerializer),
            status.HTTP_400_BAD_REQUEST: openapi.Response('Bad Request')
        }
    )
    def post(self, request):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
        #     return Response({"message": "Access Denied"})
        serializer = PureteSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PureteDetailAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    def get_object(self, pk):
        try:
            return Purete.objects.get(pk=pk)
        except Purete.DoesNotExist:
            return None

    def get(self, request, pk):
        purete = self.get_object(pk)
        if purete is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = PureteSerializer(purete)
        return Response(serializer.data)

    def put(self, request, pk):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
        #     return Response({"message": "Access Denied"})
        purete = self.get_object(pk)
        if purete is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = PureteSerializer(purete, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        if request.user.user_role is not None and request.user.user_role.role != 'admin':
            return Response({"message": "Access Denied"})
        # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
        #     return Response({"message": "Access Denied"})
        purete = self.get_object(pk)
        if purete is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        purete.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MarqueListCreateAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        responses={200: openapi.Response('response description', BijouterieSerializer)},
        )
    def get(self, request):
        marques = Marque.objects.all()
        serializer = MarqueSerializer(marques, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description="Register a new user",
        request_body=MarqueSerializer,
        responses={
            status.HTTP_201_CREATED: openapi.Response('User created successfully', BijouterieSerializer),
            status.HTTP_400_BAD_REQUEST: openapi.Response('Bad Request')
        }
    )
    def post(self, request):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
        #     return Response({"message": "Access Denied"})
        serializer = MarqueSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class MarqueDetailAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    def get_object(self, pk):
        try:
            return Marque.objects.get(pk=pk)
        except Marque.DoesNotExist:
            return None

    def get(self, request, pk):
        marque = self.get_object(pk)
        if marque is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = MarqueSerializer(marque)
        return Response(serializer.data)

    def put(self, request, pk):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
        #     return Response({"message": "Access Denied"})
        marque = self.get_object(pk)
        if marque is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = MarqueSerializer(marque, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        if request.user.user_role is not None and request.user.user_role.role != 'admin':
            return Response({"message": "Access Denied"})
        # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
        #     return Response({"message": "Access Denied"})
        marque = self.get_object(pk)
        if marque is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        marque.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ModeleListCreateAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        responses={200: openapi.Response('response description', BijouterieSerializer)},
        )
    def get(self, request):
        modeles = Modele.objects.all()
        serializer = ModeleSerializer(modeles, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description="Register a new user",
        request_body=ModeleSerializer,
        responses={
            status.HTTP_201_CREATED: openapi.Response('User created successfully', BijouterieSerializer),
            status.HTTP_400_BAD_REQUEST: openapi.Response('Bad Request')
        }
    )
    def post(self, request):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
        #     return Response({"message": "Access Denied"})
        serializer = ModeleSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ModeleDetailAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    def get_object(self, pk):
        try:
            return Modele.objects.get(pk=pk)
        except Modele.DoesNotExist:
            return None

    def get(self, request, pk):
        modele_instance = self.get_object(pk)
        if modele_instance is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = ModeleSerializer(modele_instance)
        return Response(serializer.data)

    def put(self, request, pk):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
        #     return Response({"message": "Access Denied"})
        modele_instance = self.get_object(pk)
        if modele_instance is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = ModeleSerializer(modele_instance, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        if request.user.user_role is not None and request.user.user_role.role != 'admin':
            return Response({"message": "Access Denied"})
        if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
            return Response({"message": "Access Denied"})
        modele_instance = self.get_object(pk)
        if modele_instance is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        modele_instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProduitListCreateAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        responses={200: openapi.Response('response description', BijouterieSerializer)},
        )
    def get(self, request):
        produits = Produit.objects.all()
        serializer = ProduitSerializer(produits, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description="Register a new user",
        request_body=ProduitSerializer,
        responses={
            status.HTTP_201_CREATED: openapi.Response('User created successfully', ProduitSerializer),
            status.HTTP_400_BAD_REQUEST: openapi.Response('Bad Request')
        }
    )
    def post(self, request):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
        #     return Response({"message": "Access Denied"})
        serializer = ProduitSerializer(data=request.data)
        if serializer.is_valid():
            produit = serializer.save()
            produit.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ProduitDetailAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    def get_object(self, pk):
        try:
            return Produit.objects.get(pk=pk)
        except Produit.DoesNotExist:
            return None

    def get(self, request, pk):
        produit = self.get_object(pk)
        if produit is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = ProduitSerializer(produit)
        return Response(serializer.data)

    def put(self, request, pk):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
        #     return Response({"message": "Access Denied"})
        produit = self.get_object(pk)
        if produit is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = ProduitSerializer(produit, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager':
            return Response({"message": "Access Denied"})
        # if request.user.is_authenticated and request.user.user_role and not request.user.user_role.role == 'admin' and not request.user.user_role.role == 'manager' and not request.user.user_role.role == 'seller':
        #     return Response({"message": "Access Denied"})
        produit = self.get_object(pk)
        if produit is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        produit.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)



class QRCodeView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        responses={200: openapi.Response('response description', BijouterieSerializer)},
        )
    def get(self, request, slug, format=None):
        try:
            # Retrieve the produit by its ID
            produit = Produit.objects.get(slug=slug)
            
            # Generate QR code data, e.g., produit URL or information
            qr_data = f"Produit Nom: {produit.categorie.nom} {produit.modele} {produit.marque} {produit.purete}\nPrix gramme: {produit.marque.prix}\nPrix vente: {produit.prix_vente}\nDescription: {produit.description}\nSlug: {produit.slug} "
            
            # Create a QR code
            qr = qrcode.make(qr_data)
            
            # Save the QR code in a BytesIO object
            img_io = BytesIO()
            qr.save(img_io)
            img_io.seek(0)
            
            # Return the image as an HTTP response
            return HttpResponse(img_io, content_type="image/png")
        
        except Produit.DoesNotExist:
            return Response({"error": "Produit not found"}, status=status.HTTP_404_NOT_FOUND)