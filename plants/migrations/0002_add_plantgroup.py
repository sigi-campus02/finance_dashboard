# plants/migrations/0002_add_plantgroup.py
# Generiere mit: python manage.py makemigrations plants

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('plants', '0001_initial'),
    ]

    operations = [
        # 1. PlantGroup Model erstellen
        migrations.CreateModel(
            name='PlantGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='Gruppenname')),
                ('description', models.TextField(blank=True, verbose_name='Beschreibung')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Pflanzengruppe',
                'verbose_name_plural': 'Pflanzengruppen',
                'ordering': ['name'],
            },
        ),

        # 2. Unique constraint für name + user
        migrations.AddConstraint(
            model_name='plantgroup',
            constraint=models.UniqueConstraint(fields=['name', 'user'], name='unique_plantgroup_per_user'),
        ),

        # 3. Group ForeignKey zu Plant hinzufügen
        migrations.AddField(
            model_name='plant',
            name='group',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='plants',
                to='plants.plantgroup',
                verbose_name='Gruppe'
            ),
        ),

        # 4. Plant ordering anpassen
        migrations.AlterModelOptions(
            name='plant',
            options={
                'ordering': ['group__name', 'name'],
                'verbose_name': 'Pflanze',
                'verbose_name_plural': 'Pflanzen'
            },
        ),
    ]