from django.db import migrations

# Plan de départ, modifiable par le gérant dans « Comptes et réglages » > Tables
TABLES = [(f"Table {i}", 'salle', i) for i in range(1, 9)] + [(f"VIP {i}", 'vip', i) for i in range(1, 5)]


def creer_tables(apps, schema_editor):
    Table = apps.get_model('caisse', 'Table')
    for nom, zone, ordre in TABLES:
        Table.objects.get_or_create(nom=nom, defaults={'zone': zone, 'ordre': ordre})


class Migration(migrations.Migration):

    dependencies = [
        ('caisse', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(creer_tables, migrations.RunPython.noop),
    ]
