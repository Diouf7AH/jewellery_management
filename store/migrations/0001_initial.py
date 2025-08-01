from django.db import migrations, models
import django.db.models.deletion
import store.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Bijouterie',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(max_length=30, null=True, unique=True)),
                ('telephone_portable_1', models.CharField(blank=True, max_length=30, null=True)),
                ('telephone_portable_2', models.CharField(blank=True, max_length=30, null=True)),
                ('telephone_portable_3', models.CharField(blank=True, max_length=30, null=True)),
                ('telephone_portable_4', models.CharField(blank=True, max_length=30, null=True)),
                ('telephone_portable_5', models.CharField(blank=True, max_length=30, null=True)),
                ('telephone_fix', models.CharField(blank=True, max_length=30, null=True)),
                ('adresse', models.CharField(blank=True, max_length=255, null=True)),
                ('logo_blanc', models.ImageField(blank=True, default='logo_blanc.jpg', null=True, upload_to='logo/')),
                ('logo_noir', models.ImageField(blank=True, default='logo_noir.jpg', null=True, upload_to='logo/')),
                ('nom_de_domaine', models.URLField(blank=True, null=True)),
                ('tiktok', models.URLField(blank=True, null=True)),
                ('facebook', models.URLField(blank=True, null=True)),
                ('instagram', models.URLField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name_plural': 'Bijouteries',
            },
        ),
        migrations.CreateModel(
            name='Categorie',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(blank=True, default='', max_length=30, unique=True)),
                ('image', models.ImageField(blank=True, default='category.jpg', null=True, upload_to='categorie/')),
            ],
            options={
                'verbose_name_plural': 'Catégories',
                'ordering': ['nom'],
            },
        ),
        migrations.CreateModel(
            name='Marque',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('marque', models.CharField(blank=True, max_length=25, null=True, unique=True)),
                ('prix', models.DecimalField(decimal_places=2, default=0.0, max_digits=12)),
                ('creation_date', models.DateTimeField(auto_now_add=True)),
                ('modification_date', models.DateTimeField(auto_now=True)),
                ('categorie', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='marques_categorie', to='store.categorie')),
            ],
            options={
                'verbose_name_plural': 'Marques',
            },
        ),
        migrations.CreateModel(
            name='Modele',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('modele', models.CharField(max_length=55, null=True, unique=True)),
                ('marque', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='modele_marque', to='store.marque')),
            ],
            options={
                'verbose_name': 'Modèle',
                'verbose_name_plural': 'Modèles',
                'ordering': ['modele'],
            },
        ),
        migrations.CreateModel(
            name='Purete',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('purete', models.CharField(max_length=5, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='Produit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(blank=True, default='', max_length=100)),
                ('image', models.ImageField(blank=True, null=True, upload_to='produits/')),
                ('description', models.TextField(blank=True, null=True)),
                ('qr_code', models.ImageField(blank=True, null=True, upload_to='qr_codes/')),
                ('matiere', models.CharField(blank=True, choices=[('or', 'Or'), ('argent', 'Argent'), ('mixte', 'Mixte')], default='or', max_length=50, null=True)),
                ('poids', models.DecimalField(decimal_places=2, default=0.0, max_digits=12)),
                ('taille', models.DecimalField(blank=True, decimal_places=2, default=0.0, max_digits=12, null=True)),
                ('genre', models.CharField(blank=True, choices=[('H', 'Homme'), ('F', 'Femme'), ('E', 'Enfant')], default='F', max_length=10, null=True)),
                ('status', models.CharField(blank=True, choices=[('désactivé', 'Désactivé'), ('rejetée', 'Rejetée'), ('en_revue', 'En Revue'), ('publié', 'Publié')], default='publié', max_length=10, null=True)),
                ('etat', models.CharField(blank=True, choices=[('N', 'Neuf'), ('R', 'Retour')], default='N', max_length=10, null=True)),
                ('sku', models.SlugField(blank=True, max_length=100, null=True, unique=True)),
                ('slug', models.SlugField(blank=True, max_length=100, null=True, unique=True)),
                ('date_ajout', models.DateTimeField(auto_now_add=True)),
                ('date_modification', models.DateTimeField(auto_now=True)),
                ('categorie', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='categorie_produit', to='store.categorie')),
                ('marque', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='marque_produit', to='store.marque')),
                ('modele', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='modele_produit', to='store.modele')),
                ('purete', models.ForeignKey(blank=True, default=store.models.get_default_purete, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='purete_produit', to='store.purete')),
            ],
            options={
                'verbose_name_plural': 'Produits',
                'ordering': ['-id'],
            },
        ),
        migrations.AddField(
            model_name='marque',
            name='purete',
            field=models.ForeignKey(blank=True, default=store.models.get_default_purete, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='marques_purete', to='store.purete'),
        ),
        migrations.CreateModel(
            name='HistoriquePrix',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('prix_achat', models.DecimalField(decimal_places=2, default=0.0, max_digits=12)),
                ('prix_vente', models.DecimalField(decimal_places=2, default=0.0, max_digits=12)),
                ('creation_date', models.DateTimeField(auto_now_add=True)),
                ('modification_date', models.DateTimeField(auto_now=True)),
                ('marque', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='store.marque')),
            ],
        ),
        migrations.CreateModel(
            name='Gallery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to='produit_gallery/')),
                ('active', models.BooleanField(default=True)),
                ('date', models.DateTimeField(auto_now_add=True)),
                ('produit', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='produit_gallery', to='store.produit')),
            ],
            options={
                'verbose_name_plural': 'Galerie',
                'ordering': ['-date'],
            },
        ),
    ]
