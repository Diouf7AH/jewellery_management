from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0002_alter_produit_matiere'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='marque',
            name='categorie',
        ),
        migrations.AlterField(
            model_name='categorie',
            name='nom',
            field=models.CharField(max_length=30, unique=True),
        ),
        migrations.AlterField(
            model_name='marque',
            name='marque',
            field=models.CharField(max_length=25, unique=True),
        ),
        migrations.CreateModel(
            name='CategorieMarque',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_liaison', models.DateTimeField(auto_now_add=True)),
                ('categorie', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='categorie_marques', to='store.categorie')),
                ('marque', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='marque_categories', to='store.marque')),
            ],
            options={
                'unique_together': {('categorie', 'marque')},
            },
        ),
    ]
