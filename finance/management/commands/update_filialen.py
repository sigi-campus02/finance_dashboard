# finance/management/commands/update_filialen.py

from django.core.management.base import BaseCommand
from finance.models import BillaFiliale


class Command(BaseCommand):
    help = 'Aktualisiert die Namen der Billa-Filialen'

    def handle(self, *args, **options):
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('🏪 Billa Filialen Update'))
        self.stdout.write('=' * 70)

        # Bekannte Filialen mit korrekten Namen
        filialen_daten = {
            '06263': {'name': 'Josef-Pock-Straße', 'typ': 'billa_plus'},
            '06225': {'name': 'Eggenberg', 'typ': 'billa_plus'},
            '06703': {'name': 'Shopping Nord', 'typ': 'billa_plus'},
            '06816': {'name': 'Körösistraße', 'typ': 'billa'},
            '06521': {'name': 'Anton-Kleinoscheg', 'typ': 'billa'},
        }

        updates = 0
        created = 0

        for filial_nr, daten in filialen_daten.items():
            filiale, is_new = BillaFiliale.objects.update_or_create(
                filial_nr=filial_nr,
                defaults={
                    'name': daten['name'],
                    'typ': daten['typ'],
                    'aktiv': True
                }
            )

            if is_new:
                created += 1
                self.stdout.write(
                    self.style.SUCCESS(f'  ✓ Neu erstellt: {filial_nr} - {daten["name"]}')
                )
            else:
                updates += 1
                self.stdout.write(
                    self.style.WARNING(f'  ⟳ Aktualisiert: {filial_nr} - {daten["name"]}')
                )

        # Zeige unbekannte Filialen
        bekannte_nummern = set(filialen_daten.keys())
        alle_filialen = BillaFiliale.objects.all()
        unbekannte = [f for f in alle_filialen if f.filial_nr not in bekannte_nummern]

        if unbekannte:
            self.stdout.write('\n' + self.style.WARNING('⚠️  Unbekannte Filialen gefunden:'))
            for filiale in unbekannte:
                self.stdout.write(f'  • {filiale.filial_nr} - {filiale.name}')
            self.stdout.write('\n  → Bitte in diesem Command hinzufügen!')

        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(f'✓ {created} neu erstellt')
        self.stdout.write(f'⟳ {updates} aktualisiert')
        self.stdout.write('=' * 70)