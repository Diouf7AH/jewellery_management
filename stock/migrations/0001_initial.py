# Generated by Django 5.1.3 on 2024-12-29 15:18

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('store', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Fournisseur',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(max_length=100)),
                ('prenom', models.CharField(max_length=100)),
                ('address', models.CharField(blank=True, max_length=100, null=True)),
                ('telephone', models.CharField(blank=True, max_length=15, null=True, unique=True)),
                ('slug', models.SlugField(blank=True, max_length=30, null=True, unique=True)),
                ('date_ajout', models.DateTimeField(auto_now_add=True)),
                ('date_modification', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='Stock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantite', models.PositiveIntegerField(default=0)),
                ('prix_achat_gramme', models.DecimalField(decimal_places=2, default=0.0, max_digits=12)),
                ('date_ajout', models.DateTimeField(auto_now_add=True)),
                ('date_modification', models.DateTimeField(auto_now=True)),
                ('fournisseur', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stock_fornisseur', to='stock.fournisseur')),
                ('produit', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stock_produit', to='store.produit')),
            ],
        ),
    ]
