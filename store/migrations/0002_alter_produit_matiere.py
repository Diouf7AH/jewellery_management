# Generated by Django 4.2 on 2025-07-01 04:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='produit',
            name='matiere',
            field=models.CharField(blank=True, choices=[('or', 'Or'), ('argent', 'Argent'), ('mixte', 'Mixte')], default='or', max_length=50, null=True),
        ),
    ]
