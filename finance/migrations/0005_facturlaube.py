from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0004_registereddevice'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                -- Lösche Tabelle falls sie existiert
                DROP TABLE IF EXISTS finance.fact_urlaube CASCADE;

                -- Erstelle Tabelle
                CREATE TABLE finance.fact_urlaube (
                    id SERIAL PRIMARY KEY,
                    datum DATE NOT NULL,
                    beschreibung VARCHAR(500) NOT NULL,
                    gesamt_ausgaben NUMERIC(18,2) NOT NULL,
                    anteil_robert NUMERIC(18,2) NOT NULL,
                    anteil_sigi NUMERIC(18,2) NOT NULL
                );

                -- Index für Performance
                CREATE INDEX idx_fact_urlaube_datum 
                    ON finance.fact_urlaube(datum);

                -- Kommentar
                COMMENT ON TABLE finance.fact_urlaube IS 
                    'Urlaubsausgaben mit Kostenaufteilung zwischen Robert und Sigi';
            """,
            reverse_sql="""
                DROP TABLE IF EXISTS finance.fact_urlaube CASCADE;
            """
        ),
    ]