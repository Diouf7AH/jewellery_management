from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('staff', '0002_initial'),
        # ('store', '0001_initial'),     # on attend que 'bijouterie' existe
    ]

    operations = [
        migrations.AddField(
            model_name='cashier',
            name='bijouterie',
            field=models.ForeignKey(
                to='store.bijouterie',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True,
                related_name='cashiers',      # valeur figée (pas de '%(class)ss')
            ),
        ),
    ]