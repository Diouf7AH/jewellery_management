from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('store', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Employee',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(blank=True, help_text='Shop Name', max_length=100, null=True)),
                ('phone', models.CharField(max_length=20, null=True, unique=True)),
                ('image', models.ImageField(blank=True, upload_to='user-images/')),
                ('description', models.TextField(blank=True, null=True)),
                ('active', models.BooleanField(default=True)),
                ('date', models.DateTimeField(auto_now_add=True)),
                ('bijoterie', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='vendor_bijoutrie', to='store.bijouterie')),
            ],
            options={
                'verbose_name_plural': 'Employees',
            },
        ),
    ]
