# finance/migrations/0014_remove_billaeinkauf_billa_einka_filiale_idx_and_more.py
from django.db import migrations, models


def check_and_remove_index(apps, schema_editor):
    """
    Entfernt Indizes nur wenn sie existieren - Database-agnostic
    """
    connection = schema_editor.connection

    # SQLite verwendet eine andere Methode zum Prüfen von Indizes
    if connection.vendor == 'sqlite':
        with connection.cursor() as cursor:
            # SQLite: Prüfe sqlite_master Tabelle
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='index' 
                AND name='billa_einka_filiale_idx'
            """)
            if cursor.fetchone():
                cursor.execute("DROP INDEX IF EXISTS billa_einka_filiale_idx")

    elif connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            # PostgreSQL: Prüfe pg_indexes
            cursor.execute("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = 'billa_einkauf' 
                AND indexname = 'billa_einka_filiale_idx'
            """)
            if cursor.fetchone():
                cursor.execute("DROP INDEX IF EXISTS billa_einka_filiale_idx")


def check_and_rename_index(apps, schema_editor):
    """
    Benennt Index nur um wenn er existiert - Database-agnostic
    """
    connection = schema_editor.connection

    # SQLite unterstützt kein ALTER INDEX RENAME, daher überspringen
    if connection.vendor == 'sqlite':
        return  # SQLite kann Indizes nicht umbenennen, muss neu erstellt werden

    elif connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = 'billa_einkauf' 
                AND indexname = 'billa_einka_datum_5f130f_idx'
            """)
            if cursor.fetchone():
                cursor.execute("""
                    ALTER INDEX billa_einka_datum_5f130f_idx 
                    RENAME TO billa_einka_datum_641dea_idx
                """)


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0013_preishistorie_filiale_fk'),
    ]

    operations = [
        # Entferne den problematischen Index-Namen (wenn er existiert)
        migrations.RunPython(
            check_and_remove_index,
            migrations.RunPython.noop
        ),

        # Versuche den anderen Index umzubenennen (wenn er existiert)
        migrations.RunPython(
            check_and_rename_index,
            migrations.RunPython.noop
        ),

        # Füge den neuen Index hinzu
        migrations.AddIndex(
            model_name='billapreishistorie',
            index=models.Index(fields=['filiale'], name='billa_preis_filiale_d202d1_idx'),
        ),
    ]