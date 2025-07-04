# Generated by Django 4.2 on 2025-07-01 04:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order', '0003_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='commandeproduitclient',
            options={},
        ),
        migrations.AddField(
            model_name='commandeproduitclient',
            name='categorie_personnalisee',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='commandeproduitclient',
            name='marque_personnalisee',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='commandeproduitclient',
            name='poids_prevu',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='commandeproduitclient',
            name='type_personnalise',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
