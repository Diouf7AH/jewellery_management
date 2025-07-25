from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('store', '0001_initial'),
        ('employee', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Vendor',
            fields=[
                ('employee_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='employee.employee')),
                ('verifie', models.BooleanField(default=True)),
                ('raison_desactivation', models.TextField(blank=True, null=True)),
                ('slug', models.SlugField(blank=True, max_length=20, null=True, unique=True)),
                ('bijouterie', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='bijouterie', to='store.bijouterie')),
                ('user', models.OneToOneField(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='user_vendor', to=settings.AUTH_USER_MODEL)),
            ],
            bases=('employee.employee',),
        ),
        migrations.CreateModel(
            name='VendorProduit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantite', models.PositiveIntegerField()),
                ('produit', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='vendor_vendors', to='store.produit')),
                ('vendor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='vendor_produits', to='vendor.vendor')),
            ],
            options={
                'unique_together': {('vendor', 'produit')},
            },
        ),
    ]
