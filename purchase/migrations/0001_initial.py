import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('store', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Achat',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('montant_total_ht', models.DecimalField(decimal_places=2, default=0.0, max_digits=12, null=True)),
                ('montant_total_ttc', models.DecimalField(decimal_places=2, default=0.0, max_digits=12, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Fournisseur',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(blank=True, max_length=100, null=True)),
                ('prenom', models.CharField(blank=True, max_length=100, null=True)),
                ('address', models.CharField(blank=True, max_length=100, null=True)),
                ('telephone', models.CharField(blank=True, max_length=15, null=True, unique=True)),
                ('slug', models.SlugField(blank=True, max_length=30, null=True, unique=True)),
                ('date_ajout', models.DateTimeField(auto_now_add=True)),
                ('date_modification', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='AchatProduit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero_achat_produit', models.CharField(blank=True, max_length=25, null=True, unique=True)),
                ('quantite', models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(1)])),
                ('prix_achat_gramme', models.DecimalField(decimal_places=2, default=0.0, max_digits=12)),
                ('tax', models.DecimalField(blank=True, decimal_places=2, default=0.0, max_digits=12, null=True)),
                ('sous_total_prix_achat', models.DecimalField(decimal_places=2, default=0.0, max_digits=12, null=True)),
                ('achat', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='produits', to='purchase.achat')),
                ('fournisseur', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='purchase.fournisseur')),
                ('produit', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='achats_produits', to='store.produit')),
            ],
            options={
                'verbose_name': 'Produit acheté',
                'verbose_name_plural': 'Produits achetés',
            },
        ),
        migrations.AddField(
            model_name='achat',
            name='fournisseur',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='achat', to='purchase.fournisseur'),
        ),
    ]
