# finance/parser.py
"""
Konsolidierter Parser für Billa-Rechnungen.
Wird sowohl von der View als auch vom Management Command verwendet.
"""

import re
import pdfplumber
from datetime import datetime
from decimal import Decimal
import logging
logger = logging.getLogger(__name__)

class BillaReceiptParser:
    """
    Parser für Billa-Rechnungen (PDF).

    Features:
    - Extraktion von Header-Informationen (Datum, Filiale, Kassa, etc.)
    - Artikelerkennung mit Gewicht, Menge, Rabatt
    - Robuste Fehlerbehandlung
    """

    def __init__(self):
        # Basis-Patterns
        self.artikel_pattern = re.compile(r'^(.+?)\s+([ABCDG])\s+([\d.,-]+)\s*$')
        self.gewicht_pattern = re.compile(r'^\s*([\d.]+)\s*kg\s*(?:\(N\))?\s*x\s*([\d.]+)\s*EUR/kg\s*$')
        self.menge_pattern = re.compile(r'^\s*(\d+)\s*x\s*([\d.]+)\s*$')

        # Rabatt-Pattern für Standard-Aktionen
        self.rabatt_pattern = re.compile(
            r'^(?:(\d+)\s+x\s+)?'  # ← NEU: Optional "24 x "
            r'(NIMM MEHR|EXTREM AKTION|GRATIS AKTION|AKTIONSNACHLASS|'
            r'FILIALAKTION|Preiskorrektur|Jö Äpp Extrem Bon|ABVERKAUF)\s+'
            r'([ABCDG])?\s*'
            r'([-]?[\d.,-]+)\s*$'
        )

    def parse_pdf(self, pdf_path):
        """
        Parst eine Billa-Rechnung aus einer PDF-Datei.

        Args:
            pdf_path: Pfad zur PDF-Datei

        Returns:
            dict mit allen extrahierten Daten

        Raises:
            ValueError: Bei fehlenden Pflichtfeldern
        """
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

        if not text.strip():
            raise ValueError("PDF enthält keinen extrahierbaren Text")

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

        # Extrahiere Header und Artikel
        data.update(self._extract_header(lines))
        data['artikel'] = self._extract_artikel(lines)

        # Validierung
        self._validate_data(data)

        return data

    def _validate_data(self, data):
        """Validiert die extrahierten Pflichtfelder"""
        if not data.get('datum'):
            raise ValueError("Datum konnte nicht aus dem PDF extrahiert werden")
        if not data.get('re_nr'):
            raise ValueError("Rechnungsnummer konnte nicht gefunden werden")
        if not data.get('gesamt_preis'):
            raise ValueError("Gesamtpreis konnte nicht ermittelt werden")

    def _extract_header(self, lines):
        """
        Extrahiert Header-Informationen aus den Zeilen.

        Sucht nach:
        - Datum & Zeit
        - Filiale & Kassa
        - Bon-Nr & Re-Nr
        - Gesamtpreis & Ersparnis
        - MwSt-Beträge (B, C, G, D)
        - Ö-Punkte
        """
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

            # Re-Nr (wichtig für Duplikatserkennung)
            m = re.search(r'Re-Nr:\s*([\d-]+)', line)
            if m:
                info['re_nr'] = m.group(1)

            # Ersparnis
            m = re.search(r'HEUTE GESPART\s+([\d.,]+)\s*EUR', line)
            if m:
                info['gesamt_ersparnis'] = Decimal(m.group(1).replace(',', '.'))

            # Gesamtpreis
            if line.startswith('Summe') and 'EUR' in line:
                m = re.search(r'([\d.,]+)$', line)
                if m:
                    info['gesamt_preis'] = Decimal(m.group(1).replace(',', '.'))

            # MwSt B (10%)
            m = re.search(r'B:\s*10%\s*MwSt.*?=\s*([\d.,]+)', line)
            if m:
                info['mwst_b'] = Decimal(m.group(1).replace(',', '.'))

            # MwSt C (20%)
            m = re.search(r'C:\s*20%\s*MwSt.*?=\s*([\d.,]+)', line)
            if m:
                info['mwst_c'] = Decimal(m.group(1).replace(',', '.'))

            # MwSt G (13%) - oft vergessen!
            m = re.search(r'G:\s*13%\s*MwSt.*?=\s*([\d.,]+)', line)
            if m:
                info['mwst_g'] = Decimal(m.group(1).replace(',', '.'))

            # MwSt D (falls vorhanden)
            m = re.search(r'D:\s*\d+%\s*MwSt.*?=\s*([\d.,]+)', line)
            if m:
                info['mwst_d'] = Decimal(m.group(1).replace(',', '.'))

            # Ö-Punkte (spezifischere Patterns!)
            m = re.search(r'Jetzt gesammelt:\s*(\d+)', line)
            if m:
                info['oe_punkte_gesammelt'] = int(m.group(1))

            m = re.search(r'Jetzt eingelöst:\s*(-?\d+)', line)
            if m:
                info['oe_punkte_eingeloest'] = abs(int(m.group(1)))

        return info

    def _extract_artikel(self, lines):
        """
        Extrahiert Artikel aus den Zeilen.

        Wichtig:
        - Liest ALLE Artikelbereiche (auch nach Zwischensummen)
        - Stoppt erst bei "Summe EUR"
        - Überspringt allgemeine Rabatte (erkennbar an Prozent-Pattern)
        """
        artikel_liste = []
        position = 0

        # Finde Artikel-Bereich
        start_idx = 0
        end_idx = len(lines)

        for idx, line in enumerate(lines):
            # Start: Nach Datum-Zeile
            if re.search(r'Datum:\s*\d{2}\.\d{2}\.\d{4}', line):
                start_idx = idx + 1
            # Ende: Bei finaler Summe (nicht bei Zwischensumme!)
            if line.strip().startswith('Summe') and 'EUR' in line:
                end_idx = idx
                break

        # Verarbeite Zeilen
        i = start_idx
        while i < end_idx:
            line = lines[i].strip()

            # Überspringe leere Zeilen
            if not line:
                i += 1
                continue

            # ===== NEU: Überspringe allgemeine Rabatte =====
            # Erkennbar an: "X% -Betrag" am Ende (z.B. "Lieblingsprodukt 25% -1.65")
            if re.search(r'\d+%\s+-?[\d.,]+\s*$', line):
                i += 1
                continue

            # Überspringe bekannte allgemeine Rabatt-Patterns
            if any(pattern in line for pattern in [
                'x Lieblingsprodukt',
                'Marke Clever',
                'Ja! Natürlich Bon',
                'Fleisch Rabatt',
                'das teuersteProdukt',
                'auf Alles',
                'x-FACH'
            ]):
                i += 1
                continue

            # ===== NEU: Überspringe Zwischensummen =====
            if 'Zwischensumme' in line and 'EUR' in line:
                i += 1
                continue

            # Überspringe irrelevante Zeilen
            if any(x in line for x in ['BILLA BON', 'JÖ', 'LIEBLINGSPRODUKT', 'TEUERSTES']):
                i += 1
                continue

            # Überspringe reine Rabatt-Zeilen (werden beim Artikel verarbeitet)
            if self._ist_rabatt_zeile(line):
                i += 1
                continue

            # Fall 1: Gewichtsartikel (z.B. "1.234 kg (N) x 5.99 EUR/kg")
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

                    # Prüfe auf Rabatt in nächster Zeile
                    if i + 1 < end_idx:
                        rabatt_info = self._check_rabatt(lines[i + 1])
                        if rabatt_info:
                            # Prüfe ob Mengenrabatt
                            if 'rabatt_menge' in rabatt_info:
                                # Mengenrabatt: Prüfe ob Menge stimmt
                                if rabatt_info['rabatt_menge'] == int(menge):
                                    artikel['rabatt'] = rabatt_info['rabatt']
                                    artikel[
                                        'rabatt_typ'] = f"{rabatt_info['rabatt_menge']}x {rabatt_info['rabatt_typ']}"
                                    i += 1  # Überspringe Rabattzeile
                                else:
                                    # Warnung bei Mismatch
                                    logger.warning(
                                        f"Mengenrabatt {rabatt_info['rabatt_menge']} != "
                                        f"Menge {menge} bei {artikel['produkt_name']}"
                                    )
                            else:
                                # Normaler Rabatt
                                artikel['rabatt'] = rabatt_info['rabatt']
                                artikel['rabatt_typ'] = rabatt_info['rabatt_typ']
                                i += 1

                    artikel_liste.append(artikel)
                    position += 1

                i += 1
                continue

            # Fall 2: Mengenartikel (z.B. "2 x 3.99")
            menge_match = self.menge_pattern.match(line)
            if menge_match and i + 1 < end_idx:
                menge = Decimal(menge_match.group(1))
                einzelpreis = Decimal(menge_match.group(2).replace(',', '.'))

                i += 1
                artikel_line = lines[i].strip()
                artikel_match = self.artikel_pattern.match(artikel_line)

                if artikel_match:
                    artikel = self._create_artikel(
                        artikel_match, position,
                        menge=menge, einheit='Stk',
                        einzelpreis=einzelpreis,
                        ist_gewichtsartikel=False
                    )

                    # Prüfe auf Rabatt
                    if i + 1 < end_idx:
                        rabatt_info = self._check_rabatt(lines[i + 1])
                        if rabatt_info:
                            # Prüfe ob Mengenrabatt
                            if 'rabatt_menge' in rabatt_info:
                                # Mengenrabatt: Prüfe ob Menge stimmt
                                if rabatt_info['rabatt_menge'] == int(menge):
                                    artikel['rabatt'] = rabatt_info['rabatt']
                                    artikel[
                                        'rabatt_typ'] = f"{rabatt_info['rabatt_menge']}x {rabatt_info['rabatt_typ']}"
                                    i += 1  # Überspringe Rabattzeile
                                else:
                                    # Warnung bei Mismatch
                                    logger.warning(
                                        f"Mengenrabatt {rabatt_info['rabatt_menge']} != "
                                        f"Menge {menge} bei {artikel['produkt_name']}"
                                    )
                            else:
                                # Normaler Rabatt
                                artikel['rabatt'] = rabatt_info['rabatt']
                                artikel['rabatt_typ'] = rabatt_info['rabatt_typ']
                                i += 1

                    artikel_liste.append(artikel)
                    position += 1

                i += 1
                continue

            # Fall 3: Standard-Artikel
            artikel_match = self.artikel_pattern.match(line)
            if artikel_match:
                artikel = self._create_artikel(artikel_match, position)

                # Prüfe auf Rabatt in nächster Zeile
                if i + 1 < end_idx:
                    rabatt_info = self._check_rabatt(lines[i + 1])
                    if rabatt_info:
                        # Auch hier Mengenrabatt-Check (falls relevant)
                        if 'rabatt_menge' in rabatt_info:
                            # Bei Standard-Artikeln (Menge=1) ist Mengenrabatt unwahrscheinlich
                            # aber für Konsistenz trotzdem prüfen
                            logger.warning(
                                f"Mengenrabatt bei Standard-Artikel: {artikel['produkt_name']}"
                            )
                        # Normaler Rabatt
                        artikel['rabatt'] = rabatt_info['rabatt']
                        artikel['rabatt_typ'] = rabatt_info['rabatt_typ']
                        i += 1

                artikel_liste.append(artikel)
                position += 1

            i += 1

        return artikel_liste

    def _create_artikel(self, match, position, **kwargs):
        """Erstellt ein Artikel-Dictionary aus einem Regex-Match"""
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
        """
        Prüft, ob eine Zeile ein Rabatt ist (ohne ihn zu extrahieren).

        Erkennt:
        - Prozent-Rabatte: "FILIALAKTION 25%", "Verbilligung -25%"
        - Standard-Aktionen: "EXTREM AKTION", "AKTIONSNACHLASS"
        """
        line_stripped = line.strip()

        # Prozent-Rabatte (flexibles Pattern)
        if re.match(r'^[A-Za-zäöüÄÖÜ\s]+-?\d+%\s+([ABCDG])?\s*-?[\d.,-]+\s*$', line_stripped):
            return True

        # Standard-Rabatte
        if self.rabatt_pattern.match(line_stripped):
            return True

        return False

    def _check_rabatt(self, line):
        """
        Extrahiert Rabatt-Informationen aus einer Zeile.

        Returns:
            dict mit 'rabatt_typ' und 'rabatt' oder None
        """
        line_stripped = line.strip()

        # Prozent-Rabatte (z.B. "FILIALAKTION 25% B -1,17")
        prozent_match = re.match(
            r'^(.+?)\s+(-?\d+)%\s+([ABCDG])?\s*([\d.,-]+)\s*',
            line_stripped
        )
        if prozent_match:
            rabatt_name = prozent_match.group(1).strip()
            prozent = prozent_match.group(2)
            betrag = prozent_match.group(4).replace(',', '.')
            return {
                'rabatt_typ': f'{rabatt_name} {prozent}%',
                'rabatt': abs(Decimal(betrag))
            }

        # Standard-Rabatte
        match = self.rabatt_pattern.match(line_stripped)
        if match:
            menge = match.group(1)  # NEU: "24" oder None
            rabatt_name = match.group(2)  # "EXTREM AKTION"
            betrag_str = match.group(4)  # "-14.40"
            betrag_gesamt = abs(Decimal(betrag_str.replace(',', '.')))

            result = {
                'rabatt_typ': rabatt_name,
                'rabatt': betrag_gesamt
            }

            # NEU: Wenn Mengenrabatt
            if menge:
                result['rabatt_menge'] = int(menge)
                result['rabatt_pro_stueck'] = betrag_gesamt / Decimal(menge)

            return result

        return None

    def _normalize_name(self, name):
        """
        Normalisiert Produktnamen für Duplikatserkennung.

        Entfernt:
        - "@" Prefix (Mehrfachgebinde)
        - Führende/nachfolgende Leerzeichen
        - Konvertiert zu lowercase
        """
        return name.lstrip('@').strip().lower()