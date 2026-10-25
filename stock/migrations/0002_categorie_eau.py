from django.db import migrations


def ajouter_eau(apps, schema_editor):
    # Eau minérale (Céleste…) : affichée après les bières, comme prévu dans l'ordre des catégories
    Categorie = apps.get_model('stock', 'Categorie')
    base = Categorie.objects.using(schema_editor.connection.alias)
    if not base.filter(nom__iexact='Eau').exists():
        base.create(nom='Eau', ordre=14)


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(ajouter_eau, migrations.RunPython.noop),
    ]
