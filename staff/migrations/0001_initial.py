from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        # AUCUNE dépendance externe ici
    ]

    operations = [
        migrations.CreateModel(
            name='Cashier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('verifie', models.BooleanField(default=True)),
                ('raison_desactivation', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Caissier',
                'verbose_name_plural': 'Caissiers',
                'ordering': ['-id'],
            },
        ),
        migrations.AddIndex(
            model_name='cashier',
            index=models.Index(fields=['verifie'], name='staff_cashier_verifie_idx'),
        ),
    ]