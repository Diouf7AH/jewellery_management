from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('order', '0003_initial'),
        ('vendor', '0001_initial'),
        ('sale', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='venteproduit',
            name='vendor',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='venteproduits_vendor',
                to='vendor.vendor'
            ),
        ),
        migrations.AddField(
            model_name='venteproduit',
            name='vente',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='produits',
                to='sale.vente'
            ),
        ),
        migrations.AddField(
            model_name='vente',
            name='client',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='ventes',
                to='sale.client'
            ),
        ),
        migrations.AddField(
            model_name='vente',
            name='commande_source',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='command_en_ventes',
                to='order.commandeclient'
            ),
        ),
        migrations.AddField(
            model_name='vente',
            name='created_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='ventes_creees',
                to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.AddField(
            model_name='paiement',
            name='created_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='paiements_validation',
                to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.AddField(
            model_name='paiement',
            name='facture',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='paiements',
                to='sale.facture'
            ),
        ),
        migrations.AddField(
            model_name='facture',
            name='vente',
            field=models.OneToOneField(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='facture_vente',
                to='sale.vente'
            ),
        ),
    ]