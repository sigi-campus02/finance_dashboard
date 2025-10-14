# Billa Price Crawler

Dieses Modul erweitert das Finance-Dashboard um einen automatisierten Preisabgleich mit dem Billa-Onlineshop. Es besteht aus drei Hauptkomponenten:

1. **Management Command** `crawl_billa_prices`
2. **Service-Layer** für Scraping (`finance/services/billa_scraper.py`) und Matching (`finance/services/product_matcher.py`)
3. **Hilfsfunktionen** und Caching (`finance/utils/billa_helpers.py`)

## Voraussetzungen

- Aktivierte Django-Umgebung (`DJANGO_SETTINGS_MODULE=config.settings`)
- Zugriff auf die Produktionsdatenbank (z. B. Render.com / PostgreSQL)
- Neue Python-Dependencies (siehe `requirements.txt`):
  - `requests`
  - `beautifulsoup4`
  - `rapidfuzz`

Installiere die Abhängigkeiten lokal via

```bash
pip install -r requirements.txt
```

## Management Command

Das Command lädt die am häufigsten gekauften Produkte, matcht sie gegen den Billa-Webshop und aktualisiert die Preishistorie.

```bash
python manage.py crawl_billa_prices --limit 50 --filial-nr 1330 --export-csv data/price_updates.csv
```

### Wichtige Optionen

| Option | Beschreibung |
| ------ | ------------ |
| `--limit` | Anzahl der Produkte (Standard: 50) |
| `--dry-run` | Führt alle Schritte ohne Datenbank- oder Cache-Update aus |
| `--min-confidence` | Mindest-Matching-Score in % (Standard: 80) |
| `--batch-size` | Produkte werden in Batches verarbeitet (Standard: 10) |
| `--delay` | Wartezeit zwischen HTTP-Requests in Sekunden (Standard: 1.8) |
| `--filial-nr` | Billa-Filialnummer für regionale Preise (Standard: 1330) |
| `--exclude-category` | Überkategorien ausschließen (mehrfach verwendbar) |
| `--include-category` | Nur bestimmte Überkategorien berücksichtigen |
| `--export-csv` | Speichert Preisänderungen als CSV |
| `--min-purchases` | Mindestanzahl vergangener Käufe |

### Dry-Run

```
python manage.py crawl_billa_prices --limit 5 --dry-run
```

Dieser Modus eignet sich für Tests: Es werden Konsolenausgaben und Logs erzeugt, aber keine Daten gespeichert.

### Logs & Caching

- Logs werden in `logs/billa_price_crawler_<timestamp>.log` abgelegt (oder in den mit `--log-file` angegebenen Pfad).
- Gematchte Produkt-URLs und SKUs werden in `data/billa_product_cache.json` gespeichert, sodass spätere Läufe schneller sind.

### Output & Zusammenfassung

Der Konsolenoutput zeigt pro Produkt Matching-Status und Preisänderungen. Am Ende wird eine Zusammenfassung mit Laufzeit, Match-Anzahl und durchschnittlicher Confidence ausgegeben.

Beispiel:

```
Lade Top 10 Produkte...
Matching Produkt 1/10: "ja natuerlich bio milch vollmilch 1l"
  → Match gefunden: Ja! Natürlich Bio-Vollmilch 1L (89% confidence)
  → Preis aktualisiert: €1.49 (vorher: €1.39)
...
===== Billa Price Crawl Summary =====
Produkte verarbeitet: 10
Erfolgreiche Matches: 8
Preise aktualisiert: 6
Übersprungen: 2
Fehler: 0
Durchschnittliche Matching-Confidence: 87.5%
Laufzeit: 0:02:14
```

## Service-Layer

- `BillaScraper` kapselt HTTP-Requests, behandelt Rate Limiting, Robots.txt und kann via API oder HTML-Parsen aktuelle Produktpreise auslesen.
- `ProductMatcher` nutzt RapidFuzz zur intelligenten Zuordnung von lokal normalisierten Produktnamen zu Online-Shop-Produkten. Numerische Angaben (z. B. 500g, 1L) werden besonders berücksichtigt.

## Datenbankintegration

- Aktualisierte Preise werden in `BillaProdukt.letzter_preis` geschrieben.
- Pro Tag und Filiale wird genau ein Eintrag in `BillaPreisHistorie` erstellt bzw. aktualisiert.
- Ist kein passender `BillaArtikel` vorhanden, wird das Anlegen eines Historien-Eintrags übersprungen.

## Fehlerbehandlung & Monitoring

- Netzwerkfehler werden automatisch bis zu drei Mal erneut versucht.
- Der `--dry-run` Modus erlaubt Tests ohne Seiteneffekte.
- Preisänderungen > 20 % werden hervorgehoben.
- Ausführliche Logs unterstützen beim Debugging und bei manueller Kontrolle.

## Pflege & Anpassungen

- Die HTML-/API-Struktur von shop.billa.at kann sich ändern. Passe bei Bedarf die Parser in `finance/services/billa_scraper.py` an.
- Ergänze neue heuristische Regeln im `ProductMatcher`, falls spezielle Produktbezeichnungen nicht korrekt erkannt werden.
- Über die Beispielkonfiguration (siehe `config/billa_crawler.example.yml`) lassen sich wiederverwendbare Szenarien dokumentieren.

## Rechtliche Hinweise

- Beachte die Nutzungsbedingungen von Billa und prüfe regelmäßig die `robots.txt`.
- Halte dich an moderate Crawling-Raten (Standard: 1.8 s zwischen Requests).

## Troubleshooting

| Problem | Lösung |
| ------- | ------ |
| Keine Matches | Schwellenwert `--min-confidence` reduzieren oder Produktnamen prüfen |
| HTTP 429 (Rate Limit) | Delay erhöhen (`--delay 3.0`) |
| Fehlende Filiale | Sicherstellen, dass `BillaFiliale` mit entsprechender Nummer existiert |
| Keine Preishistorie | Prüfen, ob mindestens ein Einkauf/Artikel für das Produkt vorhanden ist |

## Weiterführende Ideen

- Integration eines Benachrichtigungssystems bei starken Preisänderungen
- Automatisierter nächtlicher Run via Cron/Scheduler
- Erweiterung um weitere Händler oder APIs
