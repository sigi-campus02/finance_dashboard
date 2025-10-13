# finance/management/commands/import_billa.py

from django.core.management.base import BaseCommand
from django.db import transaction
from pathlib import Path
import pdfplumber
import re
from datetime import datetime
from decimal import Decimal
from finance.models import (
    BillaEinkauf, BillaArtikel, BillaProdukt,
    BillaPreisHistorie, BillaKategorieMapping
)


class Command(BaseCommand):
    help = 'Importiert Billa-Rechnungen aus PDF-Dateien'

    def add_arguments(self, parser):
        parser.add_argument(
            'pdf_path',
            type=str,
            help='Pfad zur PDF-Datei oder Verzeichnis mit PDFs'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Überschreibt existierende Rechnungen'
        )

    def handle(self, *args, **options):
        pdf_path = options['pdf_path']
        force = options['force']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('📄 Billa PDF Import'))
        self.stdout.write('=' * 70)

        path = Path(pdf_path)

        if path.is_file():
            pdf_files = [path]
        elif path.is_dir():
            pdf_files = list(path.glob('*.pdf'))
        else:
            self.stdout.write(self.style.ERROR(f'✗ Pfad nicht gefunden: {pdf_path}'))
            return

        stats = {
            'total': len(pdf_files),
            'imported': 0,
            'skipped': 0,
            'errors': 0
        }

        self.stdout.write(f'\n📁 {stats["total"]} PDF-Dateien gefunden\n')

        for pdf_file in pdf_files:
            try:
                result = self.import_pdf(str(pdf_file), force)
                if result:
                    stats['imported'] += 1
                    self.stdout.write(self.style.SUCCESS(f'✓ {pdf_file.name}'))
                else:
                    stats['skipped'] += 1
                    self.stdout.write(self.style.WARNING(f'⊘ {pdf_file.name} (bereits vorhanden)'))
            except Exception as e:
                stats['errors'] += 1
                self.stdout.write(self.style.ERROR(f'✗ {pdf_file.name}: {str(e)}'))

        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(f'✓ Importiert: {stats["imported"]}')
        self.stdout.write(f'⊘ Übersprungen: {stats["skipped"]}')
        self.stdout.write(f'✗ Fehler: {stats["errors"]}')
        self.stdout.write('=' * 70)

    @transaction.atomic
    def import_pdf(self, pdf_path, force=False):
        """Importiert eine einzelne PDF-Datei"""
        parser = BillaReceiptParser()
        data = parser.parse_pdf(pdf_path)

        # Prüfe ob bereits importiert
        if not force and data['re_nr']:
            if BillaEinkauf.objects.filter(re_nr=data['re_nr']).exists():
                return False

        # Erstelle Einkauf
        artikel_liste = data.pop('artikel')
        einkauf = BillaEinkauf.objects.create(**data)

        # Erstelle Artikel
        for artikel_data in artikel_liste:
            artikel_data['einkauf'] = einkauf

            # Finde oder erstelle Produkt basierend auf NORMALISIERTEM Namen
            produkt_name_norm = artikel_data['produkt_name_normalisiert']
            produkt_name_original = artikel_data['produkt_name']

            # ✅ GEÄNDERT: get_or_create jetzt mit name_normalisiert
            produkt, created = BillaProdukt.objects.get_or_create(
                name_normalisiert=produkt_name_norm,  # ← FIX: normalisiert statt original
                defaults={
                    'name_original': produkt_name_original,
                    'letzter_preis': artikel_data['gesamtpreis']
                }
            )

            # Falls das Produkt bereits existiert, aber unter anderem Original-Namen,
            # aktualisiere den Original-Namen auf die häufigste Variante
            if not created:
                # Optionales Update: Behalte den kürzesten/häufigsten Original-Namen
                if len(produkt_name_original) < len(produkt.name_original):
                    produkt.name_original = produkt_name_original
                    produkt.save(update_fields=['name_original'])

            # Automatische Kategorisierung
            if created or not produkt.kategorie:
                kategorie = self.auto_kategorisieren(produkt_name_norm)
                if kategorie:
                    produkt.kategorie = kategorie
                    produkt.save()

            artikel_data['produkt'] = produkt
            artikel = BillaArtikel.objects.create(**artikel_data)

            # Erstelle Preishistorie
            BillaPreisHistorie.objects.create(
                produkt=produkt,
                artikel=artikel,
                datum=einkauf.datum,
                preis=artikel.preis_pro_einheit,
                menge=artikel.menge,
                einheit=artikel.einheit,
                filiale=einkauf.filiale
            )

            # Aktualisiere Produkt-Statistiken
            produkt.update_statistiken()

        return True

    def auto_kategorisieren(self, produkt_name):
        """Automatische Kategorisierung basierend auf Suchbegriffen"""
        # Prüfe manuelle Mappings
        for mapping in BillaKategorieMapping.objects.all():
            if mapping.suchbegriff.lower() in produkt_name.lower():
                return mapping.kategorie

        # Fallback: Einfache Keyword-basierte Kategorisierung
        name_lower = produkt_name.lower()

        if any(x in name_lower for x in ['orangen', 'bananen', 'apfel', 'äpfel', 'avocado', 'zitrone',
                                         'mango', 'granatapfel', 'beeren', 'erdäpfel', 'zwiebel',
                                         'paprika', 'tomate', 'salat', 'gurke', 'karotte', 'spargel']):
            return 'obst_gemuese'

        if any(x in name_lower for x in ['milch', 'butter', 'käse', 'joghurt', 'topfen', 'schlagobers',
                                         'mascarpone', 'mozzarella', 'emmentaler', 'creme']):
            return 'milchprodukte'

        if any(x in name_lower for x in ['schinken', 'fleisch', 'wurst', 'fisch', 'scholle',
                                         'hendl', 'pute', 'faschiertes', 'karree']):
            return 'fleisch_fisch'

        if any(x in name_lower for x in ['brot', 'toast', 'semmel', 'gebäck', 'mehl', 'teig']):
            return 'brot_backwaren'

        if any(x in name_lower for x in ['red bull', 'cola', 'saft', 'wasser', 'kaffee', 'tee',
                                         'getränk', 'drink', 'mineralwasser']):
            return 'getraenke'

        if any(x in name_lower for x in ['iglo', 'spinat', 'tiefkühl', 'gefr', 'eis']):
            return 'tiefkuehl'

        if any(x in name_lower for x in ['dose', 'konserve', 'ravioli', 'mais', 'bohnen']):
            return 'konserven'

        if any(x in name_lower for x in ['schokolade', 'snack', 'chips', 'keks', 'süß', 'bonbon',
                                         'riegel', 'müsli', 'nuss']):
            return 'suesses'

        if any(x in name_lower for x in ['toilettenpapier', 'reinig', 'spülmittel', 'schwamm',
                                         'waschmittel', 'frosch', 'somat', 'clever']):
            return 'haushalt'

        if any(x in name_lower for x in ['shampoo', 'seife', 'creme', 'deo', 'zahnpasta',
                                         'pflege', 'bad', 'kneipp']):
            return 'koerperpflege'

        return 'sonstiges'


class BillaReceiptParser:
    """Parser für Billa-Rechnungen"""

    def __init__(self):
        self.artikel_pattern = re.compile(r'^(.+?)\s+([ABCDG])\s+([\d.,-]+)\s*$')
        self.gewicht_pattern = re.compile(r'^\s*([\d.]+)\s*kg\s*(?:\(N\))?\s*x\s*([\d.]+)\s*EUR/kg\s*$')
        self.menge_pattern = re.compile(r'^\s*(\d+)\s*x\s*([\d.]+)\s*$')
        self.rabatt_pattern = re.compile(
            r'^(NIMM MEHR|EXTREM AKTION|GRATIS AKTION|AKTIONSNACHLASS|'
            r'FILIALAKTION|Preiskorrektur|Jö Äpp Extrem Bon)\s+([ABCDG])?\s*([\d.,-]+)\s*$'
        )

    def parse_pdf(self, pdf_path):
        """Parst eine PDF-Rechnung"""
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() + "\n"

        lines = text.split('\n')

        data = {
            'datum': None,
            'zeit': None,
            'filiale': None,
            'kassa': None,
            'bon_nr': None,
            're_nr': None,
            'gesamt_preis': None,
            'gesamt_ersparnis': Decimal('0'),
            'zwischensumme': None,
            'mwst_b': None,
            'mwst_c': None,
            'mwst_g': None,
            'mwst_d': None,
            'oe_punkte_gesammelt': 0,
            'oe_punkte_eingeloest': 0,
            'pdf_datei': pdf_path,
            'artikel': []
        }

        data.update(self._extract_header(lines))
        data['artikel'] = self._extract_artikel(lines)

        return data

    def _extract_header(self, lines):
        """Extrahiert Header-Informationen"""
        info = {}

        for line in lines:
            # Datum und Zeit
            m = re.search(r'Datum:\s*(\d{2}\.\d{2}\.\d{4})\s+Zeit:\s*(\d{2}:\d{2})', line)
            if m:
                info['datum'] = datetime.strptime(m.group(1), '%d.%m.%Y').date()
                info['zeit'] = datetime.strptime(m.group(2), '%H:%M').time()

            # Filiale
            m = re.search(r'Filiale:\s*(\d+)', line)
            if m:
                info['filiale'] = m.group(1)

            # Kassa
            m = re.search(r'Kassa:\s*(\d+)', line)
            if m:
                info['kassa'] = int(m.group(1))

            # Bon-Nr
            m = re.search(r'Bon-Nr:\s*(\d+)', line)
            if m:
                info['bon_nr'] = m.group(1)

            # Re-Nr
            m = re.search(r'Re-Nr:\s*([\d-]+)', line)
            if m:
                info['re_nr'] = m.group(1)

            # Ersparnis
            m = re.search(r'HEUTE GESPART\s+([\d.,]+)\s*EUR', line)
            if m:
                info['gesamt_ersparnis'] = Decimal(m.group(1).replace(',', '.'))

            # Summe
            if line.startswith('Summe') and 'EUR' in line:
                m = re.search(r'([\d.,]+)$', line)
                if m:
                    info['gesamt_preis'] = Decimal(m.group(1).replace(',', '.'))

            # MwSt
            m = re.search(r'B:\s*10%\s*MwSt.*?=\s*([\d.,]+)', line)
            if m:
                info['mwst_b'] = Decimal(m.group(1).replace(',', '.'))

            m = re.search(r'C:\s*20%\s*MwSt.*?=\s*([\d.,]+)', line)
            if m:
                info['mwst_c'] = Decimal(m.group(1).replace(',', '.'))

            # Ö-Punkte
            m = re.search(r'Jetzt gesammelt:\s*(\d+)', line)
            if m:
                info['oe_punkte_gesammelt'] = int(m.group(1))

            m = re.search(r'Jetzt eingelöst:\s*(-?\d+)', line)
            if m:
                info['oe_punkte_eingeloest'] = abs(int(m.group(1)))

        return info

    def _extract_artikel(self, lines):
        """Extrahiert Artikel aus den Zeilen"""
        artikel_liste = []
        position = 0

        # Finde Start/Ende
        start_idx = 0
        end_idx = len(lines)

        for idx, line in enumerate(lines):
            if re.search(r'Datum:\s*\d{2}\.\d{2}\.\d{4}', line):
                start_idx = idx + 1
            if 'Zwischensumme' in line and 'EUR' in line:
                end_idx = idx
                break

        i = start_idx
        while i < end_idx:
            line = lines[i].strip()

            if not line or any(x in line for x in ['BILLA BON', 'JÖ', 'x-FACH', 'TEUERSTES']):
                i += 1
                continue

            # NEU: Überspringe Rabatt-Zeilen (werden beim vorherigen Artikel verarbeitet)
            if self._ist_rabatt_zeile(line):
                i += 1
                continue

            # Gewichtsartikel
            gewicht_match = self.gewicht_pattern.match(line)
            if gewicht_match and i + 1 < end_idx:
                gewicht = Decimal(gewicht_match.group(1))
                einzelpreis = Decimal(gewicht_match.group(2))

                i += 1
                artikel_line = lines[i].strip()
                artikel_match = self.artikel_pattern.match(artikel_line)

                if artikel_match:
                    artikel = self._create_artikel(
                        artikel_match, position,
                        menge=gewicht, einheit='kg',
                        einzelpreis=einzelpreis,
                        ist_gewichtsartikel=True
                    )

                    if i + 1 < end_idx:
                        rabatt = self._check_rabatt(lines[i + 1])
                        if rabatt:
                            artikel.update(rabatt)
                            i += 1

                    artikel_liste.append(artikel)
                    position += 1

                i += 1
                continue

            # Mengenartikel
            menge_match = self.menge_pattern.match(line)
            if menge_match and i + 1 < end_idx:
                anzahl = Decimal(menge_match.group(1))
                einzelpreis = Decimal(menge_match.group(2))

                i += 1
                artikel_line = lines[i].strip()
                artikel_match = self.artikel_pattern.match(artikel_line)

                if artikel_match:
                    artikel = self._create_artikel(
                        artikel_match, position,
                        menge=anzahl, einheit='Stk',
                        einzelpreis=einzelpreis
                    )

                    if i + 1 < end_idx:
                        rabatt = self._check_rabatt(lines[i + 1])
                        if rabatt:
                            artikel.update(rabatt)
                            i += 1

                    artikel_liste.append(artikel)
                    position += 1

                i += 1
                continue

            # Normaler Artikel
            artikel_match = self.artikel_pattern.match(line)
            if artikel_match:
                artikel = self._create_artikel(artikel_match, position)

                if i + 1 < end_idx:
                    rabatt = self._check_rabatt(lines[i + 1])
                    if rabatt:
                        artikel.update(rabatt)
                        i += 1

                artikel_liste.append(artikel)
                position += 1

            i += 1

        return artikel_liste

    def _create_artikel(self, match, position, **kwargs):
        """Erstellt ein Artikel-Dictionary"""
        name = match.group(1).strip()
        preis = Decimal(match.group(3).replace(',', '.'))

        artikel = {
            'position': position,
            'produkt_name': name,
            'produkt_name_normalisiert': self._normalize_name(name),
            'menge': kwargs.get('menge', Decimal('1')),
            'einheit': kwargs.get('einheit', 'Stk'),
            'einzelpreis': kwargs.get('einzelpreis', preis),
            'gesamtpreis': preis,
            'rabatt': Decimal('0'),
            'rabatt_typ': None,
            'mwst_kategorie': match.group(2),
            'ist_gewichtsartikel': kwargs.get('ist_gewichtsartikel', False),
            'ist_mehrfachgebinde': name.startswith('@')
        }

        return artikel

    def _ist_rabatt_zeile(self, line):
        """Prüft, ob eine Zeile ein Rabatt ist (ohne den Rabatt zu extrahieren)"""
        line_stripped = line.strip()

        # Rabatte mit Prozentsatz (flexibles Pattern für alle Typen)
        # Beispiele: "FILIALAKTION 25%", "Verbilligung -25%", "ABVERKAUF 25%",
        #            "Preiskorrektur 50%", "Free Schlagobers 36%"
        if re.match(r'^[A-Za-zäöüÄÖÜ\s]+-?\d+%\s+([ABCDG])?\s*-?[\d.,-]+\s*$', line_stripped):

            return True

        # Standard-Rabatte ohne Prozentsatz
        if self.rabatt_pattern.match(line_stripped):
            return True

        return False

    def _check_rabatt(self, line):
        """Prüft auf Rabatt in der Zeile und extrahiert ihn"""
        line_stripped = line.strip()

        # Rabatte mit Prozentsatz (alle Varianten)
        # Beispiele:
        # - "FILIALAKTION 25%        B   -1,17"
        # - "Verbilligung -25%       B   -0,23"
        # - "ABVERKAUF 25%           B   -1,17"
        # - "Preiskorrektur 50%      B   -1,75"
        # - "Free Schlagobers 36%    B    1,79"
        prozent_match = re.match(r'^(.+?)\s+(-?\d+)%\s+([ABCDG])?\s*([\d.,-]+)\s*', line_stripped)
        if prozent_match:
            rabatt_name = prozent_match.group(1).strip()
            prozent = prozent_match.group(2)
            betrag = prozent_match.group(4).replace(',', '.')
            return {
                'rabatt_typ': f'{rabatt_name} {prozent}%',
                'rabatt': abs(Decimal(betrag))
            }

        # Standard-Rabatte ohne Prozentsatz (EXTREM AKTION, AKTIONSNACHLASS, etc.)
        match = self.rabatt_pattern.match(line_stripped)
        if match:
            betrag = match.group(3).replace(',', '.')
            return {
                'rabatt_typ': match.group(1),
                'rabatt': abs(Decimal(betrag))
            }

        return None

    def _normalize_name(self, name):
        """Normalisiert Produktnamen"""
        return name.lstrip('@').strip().lower()