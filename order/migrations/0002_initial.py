<<<<<<< HEAD
# Generated by Django 4.2 on 2025-07-03 08:26
=======
# Generated by Django 4.2 on 2025-06-28 01:44
>>>>>>> d77abd2 (sauvegard les changement au niveau du order)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
<<<<<<< HEAD
        ('sale', '0001_initial'),
        ('order', '0001_initial'),
=======
        ('order', '0001_initial'),
        ('sale', '0001_initial'),
>>>>>>> d77abd2 (sauvegard les changement au niveau du order)
    ]

    operations = [
        migrations.AddField(
            model_name='commandeclient',
            name='client',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='commandes_client', to='sale.client'),
        ),
    ]
