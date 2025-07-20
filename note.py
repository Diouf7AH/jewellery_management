Connecte-toi à MySQL et exécute             
ALTER DATABASE jewellery_management CHARACTER SET utf8 COLLATE utf8_general_ci;
Tu peux aussi modifier la table concernée si elle existe déjà :
ALTER TABLE token_blacklist_blacklistedtoken CONVERT TO CHARACTER SET utf8 COLLATE utf8_general_ci;

dans le projet store->views.py decomonte # if role not in ['admin', 'manager']:
et comment if role not in ['admin', 'manager', 'vendor']:

dans sale views.py decommente # pour verifier si utlisateur est bien un vendeur
            # try:
            #     vendor = Vendor.objects.get(user=user)
            # except Vendor.DoesNotExist:
            #     return Response({"error": "Vous n'êtes pas associé à un compte vendeur."}, status=400)
pour assurer l'accée au vendeur seulment


je veux un model qui corespond a ça est-ce mon system corespond a cette exemple 🔸 Exemple concret
Catégorie : "Bagues"
                    Marques :
                        Cartier
                            Model:
                                Bagues solitaire pavé
                                Bagues Halo
                            Chanel
                            Dior

Catégorie : "Montres"
                    Marques :
                        Rolex
                            modele :
                        Casio
                        Omega
                    


class Categorie(models.Model):
    nom = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nom


class Categorie(models.Model):
    nom = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nom


class Marque(models.Model):
    nom = models.CharField(max_length=100, unique=True)
    categories = models.ManyToManyField(Categorie, related_name='marques')

    def __str__(self):
        return self.nom



est-ce que dans une application ERP on peut avoir deux façon de facture 
les facture pour les ventes direct et les factures pour les ventes avec commend qui doit avoir un acompte