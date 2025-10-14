# 🛒 Billa Import System - Vollständige Anleitung

## 📋 Inhaltsverzeichnis
- [Überblick](#überblick)
- [Installation](#installation)
- [Workflow](#workflow)
- [Commands](#commands)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Überblick

Das Billa Import System analysiert PDF-Rechnungen von Billa und extrahiert:
- ✅ Header-Informationen (Datum, Filiale, Kassa, Re-Nr)
- ✅ Alle Artikel mit Preisen, Mengen und Rabatten
- ✅ MwSt-Kategorien und Ö-Punkte
- ✅ Gewichtsartikel und Mehrfachgebinde

---

## 🚀 Installation

### 1. Dateien hinzufügen

Erstelle folgende Dateien in deinem Django-Projekt:

```
finance/
├── billa_parser.py                          # Parser-Klasse
├── views_billa.py                          # Web-Upload View
├── templates/finance/
│   └── billa_import.html                   # Upload-Interface
└── management/commands/
    ├── import_billa.py                     # CLI-Import
    ├── reimport_all_billa.py               # Batch-Import
    ├── reset_billa_data.py                 # Daten löschen
    ├── check_duplikate.py                  # Duplikat-Check
    ├── update_filialen.py                  # Filialen verwalten
    └── billa_info.py                       # Datenbank-Info
```

### 2. Dependencies

Stelle sicher, dass `pdfplumber` installiert ist:

```bash
pip install pdfplumber
```

### 3. URLs einrichten

In `finance/urls.py`:

```python
from finance.views_billa import billa_import_upload

urlpatterns = [
    # ... andere URLs
    path('billa/import/', billa_import_upload, name='billa_import'),
]
```

---

## 🔄 Workflow

### Erstmaliger Import

```bash
# 1. Filialen-Stammdaten anlegen
python manage.py update_filialen

# 2. PDFs importieren
python manage.py reimport_all_billa /pfad/zu/deinen/pdfs/

# 3. Prüfe die Daten
python manage.py billa_info
```

### Regelmäßiger Import (neue Rechnungen)

**Option A: Web-Interface** (Empfohlen für Endbenutzer)
1. Gehe zu: `http://localhost:8000/finance/billa/import/`
2. Ziehe PDFs per Drag & Drop
3. Klick auf "Importieren"

**Option B: Command Line** (Für Entwickler/Automatisierung)
```bash
# Einzelne Datei
python manage.py import_billa rechnung.pdf

# Ganzes Verzeichnis
python manage.py import_billa /pfad/zu/neuen/pdfs/

# Mit Force (Duplikate überschreiben)
python manage.py import_billa /pfad/zu/pdfs/ --force
```

---

## 🛠️ Commands

### `import_billa` - Basis-Import

**Syntax:**
```bash
python manage.py import_billa <pfad> [--force]
```

**Beispiele:**
```bash
# Einzelne Datei
python manage.py import_billa rechnung_01.pdf

# Verzeichnis
python manage.py import_billa ~/Downloads/billa_rechnungen/

# Duplikate überschreiben
python manage.py import_billa ~/Downloads/ --force
```

**Ausgabe:**
```
======================================================================
📄 Billa PDF Import
======================================================================

📁 3 PDF-Dateien gefunden

✓ rechnung_01.pdf
✓ rechnung_02.pdf
⊘ rechnung_03.pdf (bereits vorhanden)

======================================================================
✓ Importiert: 2
⊘ Übersprungen: 1
✗ Fehler: 0
======================================================================
```

---

### `reimport_all_billa` - Batch-Import mit Reset

**Syntax:**
```bash
python manage.py reimport_all_billa <verzeichnis> [OPTIONS]
```

**Optionen:**
- `--reset` - Löscht alle Transaktionsdaten vor dem Import
- `--keep-products` - Behält Produkte bei (nur mit --reset)
- `--force` - Überschreibt Duplikate
- `--no-input` - Keine Bestätigung

**Beispiele:**

```bash
# Normaler Batch-Import (ohne Löschen)
python manage.py reimport_all_billa ~/Downloads/billa_rechnungen/

# Komplett-Reset und Neuimport (VORSICHT!)
python manage.py reimport_all_billa ~/Downloads/ --reset

# Reset mit Produkt-Erhalt
python manage.py reimport_all_billa ~/Downloads/ --reset --keep-products

# Automatisiert (keine Rückfrage)
python manage.py reimport_all_billa ~/Downloads/ --reset --no-input
```

**Use Cases:**

| Szenario | Command |
|----------|---------|
| Neue Rechnungen hinzufügen | `reimport_all_billa <pfad>` |
| Alles neu importieren (Fehlerkorrektur) | `reimport_all_billa <pfad> --reset` |
| Parser aktualisiert, Artikel neu parsen | `reimport_all_billa <pfad> --reset --keep-products` |

---

### `reset_billa_data` - Daten löschen

**Syntax:**
```bash
python manage.py reset_billa_data [OPTIONS]
```

**Optionen:**
- `--keep-products` - Behält Produkte
- `--delete-filialen` - Löscht auch Filialen (⚠️ ACHTUNG!)
- `--no-input` - Keine Bestätigung

**Beispiele:**

```bash
# Normale Reset (Filialen bleiben)
python manage.py reset_billa_data

# Reset mit Produkt-Erhalt
python manage.py reset_billa_data --keep-products

# Automatisiert
python manage.py reset_billa_data --no-input

# ALLES löschen (inkl. Filialen) - NUR IN NOTFÄLLEN!
python manage.py reset_billa_data --delete-filialen
```

**Was wird gelöscht?**

| Standard | --keep-products | --delete-filialen |
|----------|----------------|-------------------|
| ✓ Einkäufe | ✓ Einkäufe | ✓ Einkäufe |
| ✓ Artikel | ✓ Artikel | ✓ Artikel |
| ✓ Preishistorie | ✓ Preishistorie | ✓ Preishistorie |
| ✓ Produkte | ⊘ Produkte | ✓ Produkte |
| ⊘ Filialen | ⊘ Filialen | ✓ Filialen |

---

### `check_duplikate` - Duplikate finden & löschen

**Syntax:**
```bash
python manage.py check_duplikate [--fix]
```

**Beispiele:**

```bash
# Duplikate anzeigen
python manage.py check_duplikate

# Duplikate automatisch löschen (behält neueste)
python manage.py check_duplikate --fix
```

**Ausgabe:**
```
======================================================================
🔍 Duplikats-Check
======================================================================

⚠️  2 doppelte Rechnungsnummern gefunden:

Re-Nr: 6263-20250510-01-9196 (3x vorhanden)
  • ID 123: 2025-05-10 10:12 (€ 45.67)
  • ID 124: 2025-05-10 10:12 (€ 45.67)
  • ID 125: 2025-05-10 10:12 (€ 45.67)

======================================================================
ℹ️  Verwende --fix um Duplikate zu löschen
======================================================================
```

---

### `update_filialen` - Filialen-Stammdaten

**Syntax:**
```bash
python manage.py update_filialen
```

**Was macht das?**
- Erstellt/aktualisiert bekannte Filialen mit korrekten Namen
- Zeigt unbekannte Filialen an (zum Hinzufügen)

**Beispiel:**

```bash
$ python manage.py update_filialen

======================================================================
🏪 Billa Filialen Update
======================================================================
  ✓ Neu erstellt: 06263 - Josef-Pock-Straße
  ⟳ Aktualisiert: 06225 - Eggenberg
  ⟳ Aktualisiert: 06703 - Shopping Nord

⚠️  Unbekannte Filialen gefunden:
  • 06999 - Filiale 06999

  → Bitte in diesem Command hinzufügen!
```

**Neue Filiale hinzufügen:**

Editiere `finance/management/commands/update_filialen.py`:

```python
filialen_daten = {
    '06263': {'name': 'Josef-Pock-Straße', 'typ': 'billa_plus'},
    '06999': {'name': 'Meine neue Filiale', 'typ': 'billa'},  # NEU!
}
```

---

### `billa_info` - Datenbank-Übersicht

**Syntax:**
```bash
python manage.py billa_info
```

**Ausgabe:**

```
======================================================================
📊 Billa Datenbank-Übersicht
======================================================================

🏪 Filialen: 5
   🏬 [✓] 06263 - Josef-Pock-Straße (42 Einkäufe)
   🏬 [✓] 06225 - Eggenberg (28 Einkäufe)
   ...

🛒 Einkäufe: 127
   💰 Gesamtausgaben: € 5,432.10
   💸 Gesamt erspart: € 543.21
   🛍️  Ø Warenkorb: € 42.78
   📅 Zeitraum: 2024-01-15 bis 2025-05-10

   📍 Top 5 Filialen:
      1. 06263 - Josef-Pock-Straße: 42 Einkäufe (€ 1,823.45)
      ...

📦 Artikel: 1,234
   💶 Gesamtwert: € 5,432.10
   🏷️  Gesamt Rabatt: € 543.21

🏷️  Produkte: 456
   🔥 Top 10 meist gekauft:
      1. BILLA Vollmilch 3,5% (Ja! Natürlich): 12x (€ 1.49)
      ...
```

---

## 🔥 Häufige Szenarien

### Szenario 1: Neue Rechnungen importieren

```bash
# Web-UI verwenden ODER:
python manage.py import_billa ~/Downloads/neue_rechnungen/
```

### Szenario 2: Parser wurde verbessert, alles neu parsen

```bash
# 1. Backup (optional)
python manage.py dumpdata finance > backup.json

# 2. Reset & Reimport (Produkte bleiben)
python manage.py reimport_all_billa ~/alle_rechnungen/ --reset --keep-products
```

### Szenario 3: Komplett-Reset (z.B. nach Model-Änderung)

```bash
# Alles löschen und neu importieren
python manage.py reset_billa_data --no-input
python manage.py update_filialen
python manage.py reimport_all_billa ~/alle_rechnungen/
```

### Szenario 4: Duplikate aufräumen

```bash
# 1. Prüfen
python manage.py check_duplikate

# 2. Automatisch bereinigen
python manage.py check_duplikate --fix
```

### Szenario 5: Einzelne Rechnung nochmal importieren

```bash
# Mit --force Flag
python manage.py import_billa rechnung.pdf --force
```

---

## 🐛 Troubleshooting

### Problem: "Unique-Constraint Fehler"

**Ursache:** Rechnung bereits in DB

**Lösung:**
```bash
# Option 1: Überspringe Duplikate (Standard)
python manage.py import_billa rechnung.pdf

# Option 2: Überschreibe mit --force
python manage.py import_billa rechnung.pdf --force

# Option 3: Bereinige Duplikate
python manage.py check_duplikate --fix
```

### Problem: "Cannot assign '06263': filiale must be a BillaFiliale instance"

**Ursache:** Filiale existiert nicht in DB

**Lösung:**
```bash
# Filialen-Stammdaten anlegen
python manage.py update_filialen
```

### Problem: Parser erkennt Artikel nicht

**Ursache:** PDF-Format hat sich geändert oder ist beschädigt

**Lösung:**
1. Prüfe PDF manuell (ist es eine echte Billa-Rechnung?)
2. Aktiviere Debug-Modus um PDF-Vorschau zu sehen
3. Passe Parser-Patterns in `billa_parser.py` an

### Problem: Marken werden nicht erkannt

**Ursache:** `BrandMapper` muss trainiert werden

**Lösung:**
Editiere `finance/brand_mapper.py` und füge neue Marken hinzu.

### Problem: Import ist sehr langsam

**Ursache:** Zu viele einzelne DB-Queries

**Lösung:**
- Verwende `reimport_all_billa` statt einzelne `import_billa` Aufrufe
- Prüfe DB-Indizes
- Verwende PostgreSQL statt SQLite für Production

---

## 📚 Best Practices

### ✅ DO's

- **Regelmäßige Backups**: `python manage.py dumpdata finance > backup.json`
- **Filialen pflegen**: Halte `update_filialen.py` aktuell
- **Web-UI für User**: Endbenutzer sollten Web-UI verwenden
- **CLI für Batch**: Automatisierung über Commands
- **Duplikate prüfen**: Gelegentlich `check_duplikate` ausführen

### ❌ DON'Ts

- **Nicht `--delete-filialen` verwenden**: Filialen sind Stammdaten!
- **Nicht ohne Backup resetten**: Immer vorher `dumpdata`
- **Nicht Force bei allen Imports**: Nur bei Bedarf
- **Nicht manuell in DB editieren**: Nutze Commands

---

## 🎓 Technische Details

### Parser-Architektur

```
BillaReceiptParser
├── parse_pdf()           → Haupteinstieg
├── _extract_header()     → Header-Daten (Datum, Filiale, etc.)
├── _extract_artikel()    → Artikel mit Preisen/Rabatten
├── _ist_rabatt_zeile()   → Rabatt-Erkennung
├── _check_rabatt()       → Rabatt-Extraktion
└── _normalize_name()     → Produkt-Normalisierung
```

### Datenbank-Struktur

```
BillaFiliale (Stammdaten)
    ↓
BillaEinkauf ←─── BillaArtikel ───→ BillaProdukt
    ↓                ↓
    └────────────────┴──────────────→ BillaPreisHistorie
```

### Import-Flow

```
PDF → Parser → Validation → DB-Check → Transaction → Create Objects
```

---

## 📞 Support

Bei Problemen:
1. Führe `python manage.py billa_info` aus
2. Prüfe Logs
3. Teste mit einzelner PDF zuerst
4. Bei Parser-Problemen: PDF-Text extrahieren und analysieren

---

**Version:** 2.0  
**Letzte Aktualisierung:** 2025-01-14