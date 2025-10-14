# finance/brand_mapper.py
"""
Marken-Mapper für Billa-Produkte
Erkennt Marken aus Produktnamen analog zum Produktgruppen-Mapper
"""
import re


class BrandMapper:
    """Hauptklasse für Markenzuordnung"""

    # Marken-Muster in Prioritätsreihenfolge
    BRAND_PATTERNS = [
        # Eigenmarken (höchste Priorität)
        # Billa Bio vor Billa, damit es spezifischer matcht
        (r'^@?\s*(Billa|BILLA)\s+Bio\s', 'Billa Bio'),
        (r'^@?\s*(Ja!Bio)\s', 'Ja!Bio'),  # neu (spezifischer als Ja!)
        (r'^@?\s*(Ja!|JA!)\s', 'Ja!'),
        (r'^@?\s*(Billa|BILLA)\s', 'Billa'),
        (r'^@?\s*Clever\s', 'Clever'),
        (r'^@?\s*RM\s', 'Regional'),

        # Bio-Marken
        (r'^@?\s*Bio\s+Gourmet', 'Bio Gourmet'),
        (r'^@?\s*(Alnatura|ALN)\s', 'Alnatura'),
        (r'^@?\s*Simply\s+Good', 'Simply Good'),
        (r'^@?\s*Best\s+Foodies', 'Best Foodies'),

        # Getränke
        (r'^@?\s*Red\s+Bull\s', 'Red Bull'),  # neu
        (r'^@?\s*Happy\s+Day', 'Happy Day'),
        (r'^@?\s*Vöslauer\s', 'Vöslauer'),
        (r'^@?\s*Pona\s', 'Pona'),
        (r'^@?\s*Römerquelle\s', 'Römerquelle'),

        # Milchprodukte & Käse
        (r'^@?\s*Mini\s+Babybel\s', 'Mini Babybel'),  # neu (spezifisch)
        (r'^@?\s*Babybel\s', 'Babybel'),  # neu (generisch)
        (r'^@?\s*Nöm\s', 'NÖM'),
        (r'^@?\s*Landliebe\s', 'Landliebe'),
        (r'^@?\s*Oatly\s', 'Oatly'),
        (r'^@?\s*Free\s', 'Free'),
        (r'^@?\s*Stainzer\s', 'Stainzer'),
        (r'^@?\s*Schärdinger\s', 'Schärdinger'),
        (r'^@?\s*Lattella\s', 'Lattella'),
        (r'^@?\s*Desserta\s', 'Desserta'),  # neu

        # Tiefkühl
        (r'^@?\s*Eskimo\s', 'Eskimo'),  # neu
        (r'^@?\s*Iglo\s', 'Iglo'),
        (r'^@?\s*Bonduelle\s', 'Bonduelle'),
        (r'^@?\s*FzT\s', 'FzT'),

        # Pasta & Grundnahrung
        (r'^@?\s*Wolf\s', 'Wolf'),  # neu (Wolf Nudeln)
        (r'^@?\s*Mutti\s', 'Mutti'),  # neu (Tomatenprodukte)
        (r'^@?\s*Barilla\s', 'Barilla'),
        (r'^@?\s*Rana\s', 'Rana'),
        (r'^@?\s*Finis\s', 'Finis'),
        (r'^@?\s*Recheis\s', 'Recheis'),

        # Gewürze
        (r'^@?\s*Kotanyi\s', 'Kotanyi'),  # neu (korrekte Schreibweise)
        (r'^@?\s*Kotany\s', 'Kotany'),  # bestehender Fallback
        (r'^@?\s*Kot\.\s', 'Kotany'),

        # Süßwaren & Snacks
        (r'^@?\s*Milka\s', 'Milka'),
        (r'^@?\s*Kelly\'s\s', "Kelly's"),
        (r'^@?\s*Barebells\s', 'Barebells'),
        (r'^@?\s*Suchard\s', 'Suchard'),
        (r'^@?\s*Knusperli\s', 'Knusperli'),
        (r'^@?\s*Manner\s', 'Manner'),
        (r'^@?\s*Lindt\s', 'Lindt'),

        # Obst & Gemüse (Marken/Erzeuger – nur wenn klar erkennbar)
        (r'^@?\s*SanLucar\s', 'SanLucar'),

        # Eier & Frische-Marken
        (r'^@?\s*Tonis\s', "Toni's"),  # neu (Toni’s Freilandeier)
        (r'^@?\s*Tonis\s+Fl-?Eier', "Toni's"),  # neu (Variante)

        # Kaffee & Tee
        (r'^@?\s*Hornig\s', 'Hornig'),
        (r'^@?\s*WD\s', 'Westminster'),
        (r'^@?\s*Jacobs\s', 'Jacobs'),
        (r'^@?\s*Tchibo\s', 'Tchibo'),

        # Backwaren & Fleisch/Wurst
        (r'^@?\s*Sorger\s', 'Sorger'),  # neu
        (r'^@?\s*Oetker\s', 'Dr. Oetker'),
        (r'^@?\s*Hofstädter\s', 'Hofstädter'),
        (r'^@?\s*Ölz\s', 'Ölz'),

        # Würzmittel & Saucen
        (r'^@?\s*Rama\s', 'Rama'),
        (r'^@?\s*Knorr\s', 'Knorr'),
        (r'^@?\s*Maggi\s', 'Maggi'),
        (r'^@?\s*Thomy\s', 'Thomy'),

        # Haushalt & Pflege
        (r'^@?\s*Head\s*&\s*Shoulders', 'Head & Shoulders'),  # neu
        (r'^@?\s*H&S\s', 'Head & Shoulders'),  # neu (Kurzform)
        (r'^@?\s*Sensodyne\s', 'Sensodyne'),  # neu
        (r'^@?\s*Bi\s+Home\s', 'Bi Home'),  # neu
        (r'^@?\s*Frosch\s', 'Frosch'),
        (r'^@?\s*Nivea\s', 'Nivea'),
        (r'^@?\s*Axe\s', 'Axe'),
        (r'^@?\s*Toppits\s', 'Toppits'),
        (r'^@?\s*Swirl\s', 'Swirl'),
        (r'^@?\s*Bellawa\s', 'Bellawa'),
        (r'^@?\s*Formil\s', 'Formil'),
        (r'^@?\s*Silan\s', 'Silan'),
        (r'^@?\s*Softis\s', 'Softis'),
        (r'^@?\s*Tetesept\s', 'Tetesept'),
        (r'^@?\s*Persil\s', 'Persil'),
        (r'^@?\s*Ariel\s', 'Ariel'),

        # Brot & Knäckebrot
        (r'^@?\s*Wasa\s', 'Wasa'),

        # Fertiggerichte & Convenience
        (r'^@?\s*Uncle\s+Ben\'s', "Uncle Ben's"),

        # Diverse Marken
        (r'^@?\s*Today\s', 'Today'),
        (r'^@?\s*Bi\s+Good', 'Bi Good'),
        (r'^@?\s*Cornetto\s', 'Cornetto'),
        (r'^@?\s*Galbani\s', 'Galbani'),
        (r'^@?\s*Grana\s+Padano', 'Grana Padano'),
        (r'^@?\s*Marca\s+Italia', 'Marca Italia'),
        (r'^@?\s*Nestlé\s', 'Nestlé'),
        (r'^@?\s*Kellogg\'s', "Kellogg's"),

        # Sonstige aus der Liste (seltene, aber klar erkennbare)
        (r'^@?\s*Mälzer&Fu', 'Mälzer&Fu'),  # neu (z. B. Cereals)

        # Haushalt / Spülmaschinen
        (r'^@?\s*(Finish|FINISH)\s', 'Finish'),
        (r'^@?\s*Somat\s', 'Somat'),

        # Zahnpflege
        (r'^@?\s*Colgate\s', 'Colgate'),
        (r'^@?\s*(Elmex|ELMEX)\s', 'Elmex'),
        (r'^@?\s*(?:Blend-?a-?Med|BLEND-?A-?MED)\s', 'Blend-a-med'),

        # Haushalt / Tücher, Schwämme
        (r'^@?\s*(Tempo|TEMPO)\s', 'Tempo'),
        (r'^@?\s*Vileda\s', 'Vileda'),

        # Wurst/Fleisch
        (r'^@?\s*Berger\s', 'Berger'),

        # Käse (Schärdinger Abkürzung trifft bei dir 2x zu)
        (r'^@?\s*Schärd\.\s', 'Schärdinger'),

    ]

    # Generische Produkte (Obst/Gemüse ohne Marke)
    GENERIC_PRODUCTS_PATTERN = r'^(Paprika|Gurke|Tomate|Zwiebel|Zucchini|Karotte|Brokkoli|Blumenkohl|Salat|Kartoffel|Erdäpfel|Birne|Apfel|Banane|Orange|Zitrone|Limette|Avocado|Mango|Ananas|Beeren|Trauben|Kirschen|Pfirsich|Nektarine|Kiwi|Melone|Granatapfel|Brombeeren|Himbeeren|Erdbeeren|Heidelbeeren|Champignons|Petersilie|Schnittlauch|Basilikum|Koriander|Minze|Rosmarin|Thymian|Salbei|Lauch|Kohlrabi|Sellerie|Radieschen|Fenchel|Aubergine|Kürbis|Rucola|Spinat|Mangold|Kohl|Porree|Ingwer|Knoblauch|Rüben|Germ)\s'

    @staticmethod
    def extract_brand(product_name):
        """
        Extrahiert die Marke aus einem Produktnamen

        Args:
            product_name: Der Original-Produktname

        Returns:
            str: Standardisierter Markenname oder None
        """
        if not product_name:
            return None

        # Prüfe alle bekannten Marken-Muster
        for pattern, brand in BrandMapper.BRAND_PATTERNS:
            if re.search(pattern, product_name, re.IGNORECASE):
                return brand

        # Prüfe ob es ein generisches Produkt ist (ohne Marke)
        if re.search(BrandMapper.GENERIC_PRODUCTS_PATTERN, product_name, re.IGNORECASE):
            return None  # Keine Marke = NULL in DB

        # Wenn nichts passt, auch NULL (kein "Unbekannt" in DB)
        return None

    @staticmethod
    def update_product_brand(produkt):
        """
        Aktualisiert die Marke eines BillaProdukt-Objekts

        Args:
            produkt: BillaProdukt Instanz

        Returns:
            bool: True wenn Marke gesetzt wurde, False sonst
        """
        marke = BrandMapper.extract_brand(produkt.name_original)

        if marke:
            produkt.marke = marke
            return True

        return False