from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    initial = True
    
    dependencies = [
        ('store', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='cashier',
            name='user',
            field=models.OneToOneField(
                to=settings.AUTH_USER_MODEL,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='cashier_profile',  # vient de "%(class)s_profile"
                null=True,                       # temporaire si des lignes existent déjà
                db_index=True,
            ),
        ),
        migrations.AddField(
            model_name='cashier',
            name='bijouterie',
            field=models.ForeignKey(
                to='store.bijouterie',
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='cashiers',         # vient de "%(class)ss"
                null=True, blank=True,
            ),
        ),
        # index hérité de la Meta de la classe abstraite sur "verifie"
        migrations.AddIndex(
            model_name='cashier',
            index=models.Index(fields=['verifie'], name='staff_cashier_verifie_idx'),
        ),
    ]