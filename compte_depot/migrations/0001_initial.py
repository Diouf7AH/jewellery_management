from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('sale', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClientDepot',
            fields=[
                ('client_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='sale.client')),
                ('CNI', models.CharField(blank=True, max_length=50, null=True)),
                ('address', models.CharField(blank=True, max_length=255, null=True)),
                ('photo', models.ImageField(blank=True, default='client.jpg', null=True, upload_to='client/')),
            ],
            bases=('sale.client',),
        ),
        migrations.CreateModel(
            name='CompteDepot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero_compte', models.CharField(max_length=30, unique=True)),
                ('solde', models.DecimalField(decimal_places=2, default=0.0, max_digits=12)),
                ('date_creation', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='Transaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type_transaction', models.CharField(choices=[('Depot', 'Dépôt'), ('Retrait', 'Retrait')], max_length=10)),
                ('montant', models.DecimalField(decimal_places=2, max_digits=12)),
                ('date_transaction', models.DateTimeField(auto_now_add=True)),
                ('statut', models.CharField(choices=[('Terminé', 'Terminé'), ('Échoué', 'Échoué'), ('En attente', 'En attente')], default='Terminé', max_length=20)),
                ('compte', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transactions', to='compte_depot.comptedepot')),
            ],
            options={
                'verbose_name': 'Transaction',
                'verbose_name_plural': 'Transactions',
                'ordering': ['-date_transaction'],
            },
        ),
    ]
