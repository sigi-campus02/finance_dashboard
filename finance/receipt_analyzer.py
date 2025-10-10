# finance/receipt_analyzer.py
"""
KI-basierte Rechnungsanalyse mit OpenAI Vision API
"""
import base64
import json
from datetime import datetime
from decimal import Decimal
import os
from openai import OpenAI


class ReceiptAnalyzer:
    """Analysiert Rechnungsbilder und extrahiert Transaktionsdaten"""

    def __init__(self):
        self.client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

    def analyze_receipt(self, image_path_or_bytes):
        """
        Analysiert ein Rechnungsbild und gibt strukturierte Daten zurück

        Args:
            image_path_or_bytes: Dateipfad oder Bytes des Bildes

        Returns:
            dict mit: date, payee, amount, category_suggestion, memo
        """
        # Bild zu Base64 konvertieren
        if isinstance(image_path_or_bytes, bytes):
            base64_image = base64.b64encode(image_path_or_bytes).decode('utf-8')
        else:
            with open(image_path_or_bytes, 'rb') as f:
                base64_image = base64.b64encode(f.read()).decode('utf-8')

        # Prompt für GPT-4 Vision
        prompt = """
        Analysiere diese Rechnung und extrahiere folgende Informationen im JSON-Format:

        {
            "date": "YYYY-MM-DD",
            "payee": "Name des Geschäfts/Unternehmens",
            "amount": 123.45,
            "category": "Vorschlag für Kategorie (z.B. Lebensmittel, Transport, Restaurant, etc.)",
            "memo": "Kurze Beschreibung der wichtigsten gekauften Items",
            "currency": "EUR oder andere Währung"
        }

        Wichtig:
        - Datum im Format YYYY-MM-DD
        - Betrag als Zahl (ohne Währungssymbol)
        - Falls Information nicht verfügbar: null
        - Sei präzise und zuverlässig
        """

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",  # oder "gpt-4-vision-preview"
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500,
                temperature=0.1  # Niedrig für konsistente Ergebnisse
            )

            # Extrahiere JSON aus Response
            content = response.choices[0].message.content

            # Parse JSON (manchmal ist es in Markdown-Code-Block)
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content.strip()

            data = json.loads(json_str)

            # Validierung und Aufbereitung
            result = {
                'success': True,
                'date': self._parse_date(data.get('date')),
                'payee': data.get('payee', '').strip(),
                'amount': self._parse_amount(data.get('amount')),
                'category_suggestion': data.get('category', ''),
                'memo': data.get('memo', '').strip(),
                'currency': data.get('currency', 'EUR'),
                'raw_response': data  # Für Debugging
            }

            return result

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Fehler bei der Analyse des Bildes'
            }

    def _parse_date(self, date_str):
        """Parst und validiert Datum"""
        if not date_str:
            return datetime.now().date()

        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except:
            return datetime.now().date()

    def _parse_amount(self, amount):
        """Parst und validiert Betrag"""
        if not amount:
            return Decimal('0.00')

        try:
            return Decimal(str(amount)).quantize(Decimal('0.01'))
        except:
            return Decimal('0.00')

    def suggest_category(self, category_name, all_categories):
        """
        Matched den KI-Vorschlag mit vorhandenen Kategorien

        Args:
            category_name: KI-Vorschlag
            all_categories: Liste aller verfügbaren Kategorien

        Returns:
            DimCategory-Objekt oder None
        """
        if not category_name:
            return None

        category_lower = category_name.lower()

        # Einfaches Keyword-Matching
        category_keywords = {
            'lebensmittel': ['lebensmittel', 'groceries', 'supermarkt', 'food'],
            'restaurant': ['restaurant', 'essen', 'dining', 'café', 'bar'],
            'transport': ['transport', 'taxi', 'uber', 'öffi', 'öffentlich'],
            'kleidung': ['kleidung', 'fashion', 'clothing', 'mode'],
            'gesundheit': ['gesundheit', 'apotheke', 'arzt', 'health', 'medical'],
            'elektronik': ['elektronik', 'tech', 'computer', 'handy'],
            'haushalt': ['haushalt', 'möbel', 'einrichtung', 'household'],
        }

        for category in all_categories:
            cat_name_lower = category.category.lower()

            # Direkte Übereinstimmung
            if category_lower in cat_name_lower or cat_name_lower in category_lower:
                return category

            # Keyword-Matching
            for keywords in category_keywords.values():
                if any(keyword in category_lower for keyword in keywords):
                    if any(keyword in cat_name_lower for keyword in keywords):
                        return category

        return None
