import copy
from datetime import date, time
from decimal import Decimal

from django.test import TestCase

from billa.models import (
    BillaArtikel,
    BillaEinkauf,
    BillaFiliale,
    BillaPreisHistorie,
    BillaProdukt,
)
from billa.views.import_views import _create_einkauf_with_artikel


class BillaImportTests(TestCase):
    def setUp(self):
        # Sicherstellen, dass keine Daten vorhanden sind
        BillaEinkauf.objects.all().delete()

    def test_import_erstellt_produkt_ueber_normalisierten_namen(self):
        basis_daten = {
            'datum': date(2024, 12, 24),
            'zeit': time(18, 30),
            'filiale': '1234',
            'kassa': 3,
            'bon_nr': '9876',
            're_nr': '2024-12-24-0001',
            'gesamt_preis': Decimal('10.00'),
            'gesamt_ersparnis': Decimal('0.00'),
            'zwischensumme': Decimal('10.00'),
            'mwst_b': Decimal('0.91'),
            'mwst_c': None,
            'mwst_g': None,
            'mwst_d': None,
            'oe_punkte_gesammelt': 5,
            'oe_punkte_eingeloest': 0,
            'pdf_datei': 'rechnung.pdf',
            'artikel': [
                {
                    'position': 0,
                    'produkt_name': 'BILLA Bio Apfel',
                    'produkt_name_normalisiert': 'billa bio apfel',
                    'menge': Decimal('1.000'),
                    'einheit': 'Stk',
                    'einzelpreis': Decimal('10.00'),
                    'gesamtpreis': Decimal('10.00'),
                    'rabatt': Decimal('0.00'),
                    'rabatt_typ': None,
                    'mwst_kategorie': 'B',
                    'ist_gewichtsartikel': False,
                    'ist_mehrfachgebinde': False,
                }
            ],
        }

        einkauf = _create_einkauf_with_artikel(copy.deepcopy(basis_daten))

        self.assertIsNotNone(einkauf.pk)
        self.assertEqual(BillaEinkauf.objects.count(), 1)
        self.assertEqual(BillaArtikel.objects.count(), 1)
        self.assertEqual(BillaPreisHistorie.objects.count(), 1)
        self.assertTrue(BillaFiliale.objects.filter(filial_nr='1234').exists())

        produkt = BillaProdukt.objects.get()
        self.assertEqual(produkt.name_normalisiert, 'billa bio apfel')
        self.assertEqual(produkt.name_original, 'BILLA Bio Apfel')
        self.assertEqual(produkt.marke, 'Billa Bio')
        self.assertEqual(produkt.anzahl_kaeufe, 1)
        self.assertEqual(produkt.durchschnittspreis, Decimal('10.00'))
        self.assertEqual(produkt.letzter_preis, Decimal('10.00'))

        artikel = produkt.artikel.get()
        self.assertEqual(artikel.produkt_name_normalisiert, 'billa bio apfel')
        self.assertEqual(artikel.produkt, produkt)
