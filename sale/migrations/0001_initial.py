from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('store', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Client',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('prenom', models.CharField(max_length=100)),
                ('nom', models.CharField(max_length=100)),
                ('telephone', models.CharField(blank=True, max_length=15, null=True, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='Facture',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero_facture', models.CharField(editable=False, max_length=20, unique=True)),
                ('date_creation', models.DateTimeField(auto_now_add=True)),
                ('montant_total', models.DecimalField(decimal_places=2, default=0.0, max_digits=12, null=True)),
                ('status', models.CharField(choices=[('Non Payé', 'Non Payé'), ('Payé', 'Payé')], default='Non Payé', max_length=20)),
                ('fichier_pdf', models.FileField(blank=True, null=True, upload_to='factures/')),
            ],
            options={
                'verbose_name_plural': 'Factures',
                'ordering': ['-id'],
            },
        ),
        migrations.CreateModel(
            name='Paiement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('montant_paye', models.DecimalField(decimal_places=2, max_digits=10)),
                ('mode_paiement', models.CharField(choices=[('cash', 'Cash'), ('mobile', 'Mobile')], max_length=20)),
                ('date_paiement', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Paiement',
                'verbose_name_plural': 'Paiements',
                'ordering': ['-date_paiement'],
            },
        ),
        migrations.CreateModel(
            name='Vente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero_vente', models.CharField(blank=True, editable=False, max_length=30, null=True, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('montant_total', models.DecimalField(decimal_places=2, default=0.0, max_digits=12, null=True)),
            ],
            options={
                'verbose_name': 'Vente',
                'verbose_name_plural': 'Ventes',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='VenteProduit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantite', models.PositiveIntegerField(default=1)),
                ('prix_vente_grammes', models.DecimalField(decimal_places=2, default=0.0, max_digits=12)),
                ('sous_total_prix_vente_ht', models.DecimalField(decimal_places=2, default=0.0, max_digits=12)),
                ('tax', models.DecimalField(blank=True, decimal_places=2, default=0.0, max_digits=12, null=True)),
                ('prix_ttc', models.DecimalField(decimal_places=2, default=0.0, max_digits=12, null=True)),
                ('remise', models.DecimalField(blank=True, decimal_places=2, default=0.0, help_text='Discount', max_digits=5, null=True)),
                ('autres', models.DecimalField(decimal_places=2, default=0.0, help_text='Additional info', max_digits=5)),
                ('produit', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='venteProduit_produit', to='store.produit')),
            ],
        ),
    ]
