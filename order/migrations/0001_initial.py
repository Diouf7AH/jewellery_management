from django.db import migrations, models
import django.db.models.deletion
import store.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('store', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CommandeClient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero_commande', models.CharField(editable=False, max_length=30, unique=True)),
                ('statut', models.CharField(
                    choices=[
                        ('en_attente', 'En attente'),
                        ('en_preparation', 'En préparation'),
                        ('livree', 'Livrée'),
                        ('annulee', 'Annulée')
                    ],
                    default='en_attente',
                    max_length=20
                )),
                ('date_commande', models.DateTimeField(auto_now_add=True)),
                ('commentaire', models.TextField(blank=True, null=True)),
                ('image', models.ImageField(
                    blank=True,
                    default='order-client.jpg',
                    null=True,
                    upload_to='orders/client'
                )),
            ],
        ),
        migrations.CreateModel(
            name='CommandeProduitClient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('produit', models.CharField(blank=True, max_length=255, null=True)),
                ('genre', models.CharField(blank=True, max_length=10, null=True)),
                ('taille', models.CharField(blank=True, max_length=7, null=True)),
                ('matiere', models.CharField(
                    blank=True,
                    choices=[
                        ('or', 'Or'),
                        ('argent', 'Argent'),
                        ('mixte', 'Mixte')
                    ],
                    default='or',
                    max_length=50,
                    null=True
                )),
                ('poids', models.DecimalField(decimal_places=2, max_digits=6)),
                ('prix_gramme', models.DecimalField(decimal_places=2, default=0.0, max_digits=12)),
                ('personnalise', models.BooleanField(default=False, help_text='Cochez si ce produit est personnalisé (et non un produit officiel)')),
                ('creation_date', models.DateTimeField(auto_now_add=True)),
                ('modification_date', models.DateTimeField(auto_now=True)),
                ('quantite', models.PositiveIntegerField()),
                ('prix_prevue', models.DecimalField(decimal_places=2, max_digits=10)),
                ('sous_total', models.DecimalField(decimal_places=2, editable=False, max_digits=12)),

                # Relations
                ('categorie', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='store.categorie'
                )),
                ('marque', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='store.marque'
                )),
                ('modele', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='store.modele'
                )),
                ('purete', models.ForeignKey(
                    blank=True,
                    default=store.models.get_default_purete,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='commande_produits_purete',
                    to='store.purete'
                )),
                ('commande_client', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='commandes_produits_client',
                    to='order.commandeclient'
                )),
            ],
        ),
    ]