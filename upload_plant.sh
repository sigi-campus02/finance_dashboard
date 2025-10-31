#!/bin/bash
# upload_plants.sh - Praktisches Script für Pflanzen Bulk-Upload

set -e  # Stoppe bei Fehlern

# === KONFIGURATION ===
PHOTOS_DIR="C:/Users/siegl/Downloads/Pflanzen_Fotos"  # ANPASSEN!
MAPPING_FILE="plant_groups_mapping.json"
DRY_RUN=false

# === FARBEN ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# === FUNKTIONEN ===
print_header() {
    echo -e "${GREEN}================================================${NC}"
    echo -e "${GREEN}🌱 Pflanzen Bulk-Upload${NC}"
    echo -e "${GREEN}================================================${NC}"
    echo ""
}

check_requirements() {
    echo -e "${YELLOW}📋 Prüfe Voraussetzungen...${NC}"

    # Django Projekt
    if [ ! -f "manage.py" ]; then
        echo -e "${RED}❌ manage.py nicht gefunden!${NC}"
        echo "Führe dieses Script im Django Projekt-Root aus."
        exit 1
    fi

    # Mapping-Datei
    if [ ! -f "$MAPPING_FILE" ]; then
        echo -e "${RED}❌ $MAPPING_FILE nicht gefunden!${NC}"
        echo "Erstelle zuerst die Gruppen-Mapping-Datei."
        exit 1
    fi

    # Fotos-Verzeichnis
    if [ ! -d "$PHOTOS_DIR" ]; then
        echo -e "${RED}❌ Fotos-Verzeichnis nicht gefunden: $PHOTOS_DIR${NC}"
        echo "Passe PHOTOS_DIR im Script an."
        exit 1
    fi

    # Zähle Bilder
    PHOTO_COUNT=$(find "$PHOTOS_DIR" -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" \) | wc -l)

    if [ "$PHOTO_COUNT" -eq 0 ]; then
        echo -e "${RED}❌ Keine Bilder gefunden in: $PHOTOS_DIR${NC}"
        exit 1
    fi

    echo -e "${GREEN}✅ Alle Checks erfolgreich!${NC}"
    echo ""
    echo "📁 Fotos-Verzeichnis: $PHOTOS_DIR"
    echo "🖼️  Gefundene Bilder: $PHOTO_COUNT"
    echo "📋 Mapping-Datei: $MAPPING_FILE"
    echo ""
}

validate_json() {
    echo -e "${YELLOW}🔍 Validiere JSON-Mapping...${NC}"

    if python -m json.tool "$MAPPING_FILE" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ JSON ist valide${NC}"

        # Zeige Gruppen-Info
        GROUPS=$(python -c "import json; data = json.load(open('$MAPPING_FILE')); print(len(data.get('groups', {})))")
        echo "🏷️  Gruppen definiert: $GROUPS"
    else
        echo -e "${RED}❌ JSON-Syntax-Fehler in $MAPPING_FILE${NC}"
        exit 1
    fi
    echo ""
}

run_dry_run() {
    echo -e "${YELLOW}🧪 Führe Dry-Run durch...${NC}"
    echo ""

    python manage.py bulk_upload_photos "$PHOTOS_DIR" \
        --group-mapping "$MAPPING_FILE" \
        --create-missing \
        --dry-run

    echo ""
}

confirm_upload() {
    echo ""
    echo -e "${YELLOW}⚠️  ACHTUNG: Gleich werden $PHOTO_COUNT Bilder hochgeladen!${NC}"
    echo ""
    read -p "Fortfahren? (y/N): " -n 1 -r
    echo ""

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Upload abgebrochen."
        exit 0
    fi
}

run_upload() {
    echo ""
    echo -e "${GREEN}🚀 Starte Upload...${NC}"
    echo ""

    python manage.py bulk_upload_photos "$PHOTOS_DIR" \
        --group-mapping "$MAPPING_FILE" \
        --create-missing

    echo ""
    echo -e "${GREEN}✅ Upload abgeschlossen!${NC}"
}

# === HAUPTPROGRAMM ===
main() {
    print_header
    check_requirements
    validate_json

    if [ "$DRY_RUN" = true ]; then
        run_dry_run
        echo -e "${YELLOW}ℹ️  Dry-Run abgeschlossen. Setze DRY_RUN=false für echten Upload.${NC}"
    else
        run_dry_run
        confirm_upload
        run_upload
    fi
}

# === HELP ===
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Verwendung: ./upload_plants.sh"
    echo ""
    echo "Konfiguration:"
    echo "  PHOTOS_DIR      - Pfad zum Ordner mit Fotos"
    echo "  MAPPING_FILE    - Pfad zur Gruppen-Mapping JSON"
    echo "  DRY_RUN=true    - Nur Test, keine Uploads"
    echo ""
    echo "Beispiel:"
    echo "  DRY_RUN=true ./upload_plants.sh   # Test-Lauf"
    echo "  ./upload_plants.sh                 # Echter Upload"
    exit 0
fi

# Script ausführen
main