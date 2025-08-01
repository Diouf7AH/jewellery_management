from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('order', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='commandeclient',
            name='created_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.AddIndex(
            model_name='commandeclient',
            index=models.Index(fields=['date_commande'], name='order_comma_date_co_ed86eb_idx'),
        ),
        migrations.AddIndex(
            model_name='commandeclient',
            index=models.Index(fields=['statut'], name='order_comma_statut_800ecb_idx'),
        ),
    ]