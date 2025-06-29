# Generated by Django 4.2 on 2025-06-13 17:46

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('compte_depot', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='transactions_effectuees', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='comptebancaire',
            name='client',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='client_banque', to='compte_depot.clientbanque'),
        ),
        migrations.AddField(
            model_name='comptebancaire',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='comptes_crees', to=settings.AUTH_USER_MODEL),
        ),
    ]
