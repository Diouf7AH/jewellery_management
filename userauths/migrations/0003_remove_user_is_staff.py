# Generated by Django 4.2 on 2025-05-16 09:17

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('userauths', '0002_user_is_staff'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='user',
            name='is_staff',
        ),
    ]
