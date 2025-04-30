from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import CompteBancaire, Transaction
from .permissions import IsCaissier
from django.template.loader import render_to_string
from weasyprint import HTML
from django.http import HttpResponse

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status

from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from sale.serializers import BanqueSerializer,

class DepotView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        numero_compte = request.data.get('numero_compte')
        montant = float(request.data.get('montant'))

        try:
            compte = CompteBancaire.objects.get(numero_compte=numero_compte)
            compte.solde += montant
            compte.save()

            transaction = Transaction.objects.create(
                compte=compte,
                type_transaction="Depot",
                montant=montant,
                caissier=request.user
            )
            return self.generer_recu(transaction)

        except CompteBancaire.DoesNotExist:
            return Response({"error": "Compte non trouvé"}, status=status.HTTP_404_NOT_FOUND)

    def generer_recu(self, transaction):
        html_string = render_to_string('bank_app/recu_transaction.html', {'transaction': transaction})
        html = HTML(string=html_string)
        pdf = html.write_pdf()

        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = 'inline; filename="recu_transaction.pdf"'
        return response

class RetraitView(APIView):
    permission_classes = [IsCaissier]

    def post(self, request):
        numero_compte = request.data.get('numero_compte')
        montant = float(request.data.get('montant'))

        try:
            compte = CompteBancaire.objects.get(numero_compte=numero_compte)
            if compte.solde < montant:
                return Response({"error": "Solde insuffisant"}, status=status.HTTP_400_BAD_REQUEST)

            compte.solde -= montant
            compte.save()

            transaction = Transaction.objects.create(
                compte=compte,
                type_transaction="Retrait",
                montant=montant,
                caissier=request.user
            )
            return self.generer_recu(transaction)

        except CompteBancaire.DoesNotExist:
            return Response({"error": "Compte non trouvé"}, status=status.HTTP_404_NOT_FOUND)

    def generer_recu(self, transaction):
        html_string = render_to_string('bank_app/recu_transaction.html', {'transaction': transaction})
        html = HTML(string=html_string)
        pdf = html.write_pdf()

        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = 'inline; filename="recu_transaction.pdf"'
        return response