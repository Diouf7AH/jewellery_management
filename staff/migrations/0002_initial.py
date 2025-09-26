from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings

class Migration(migrations.Migration):

    dependencies = [
        ('staff', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='cashier',
            name='user',
            field=models.OneToOneField(
                to=settings.AUTH_USER_MODEL,
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,                      # pratique si des Cashier existent déjà
                related_name='cashier_profile', # PAS de placeholder dans une migration
                db_index=True,
            ),
        ),
        migrations.AddIndex(
            model_name='cashier',
            index=models.Index(fields=['verifie'], name='staff_cashier_verifie_idx'),
        ),
    ]