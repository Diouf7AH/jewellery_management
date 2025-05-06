dans le projet store->views.py decomonte # if role not in ['admin', 'manager']:
et comment if role not in ['admin', 'manager', 'vendor']:

dans sale views.py decommente # pour verifier si utlisateur est bien un vendeur
            # try:
            #     vendor = Vendor.objects.get(user=user)
            # except Vendor.DoesNotExist:
            #     return Response({"error": "Vous n'êtes pas associé à un compte vendeur."}, status=400)
pour assurer l'accée au vendeur seulment