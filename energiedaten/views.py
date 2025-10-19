# views.py
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import BytesIO
from datetime import datetime, timedelta, date
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree as ET

from dateutil import parser as date_parser
from django.contrib import messages
from django.shortcuts import render, redirect
from django.db.models import Sum, Avg, Max, Min, Count
from django.db.models.functions import (
    TruncMonth,
    ExtractWeek,
    ExtractYear,
)

from .forms import StromverbrauchImportForm
from .models import Stromverbrauch


XLSX_NAMESPACE = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def _column_to_index(cell_reference: str | None) -> int | None:
    if not cell_reference:
        return None

    letters = []
    for char in cell_reference:
        if char.isalpha():
            letters.append(char)
        else:
            break

    if not letters:
        return None

    index = 0
    for char in letters:
        index = index * 26 + (ord(char.upper()) - ord('A') + 1)

    return index - 1


def _read_xlsx_rows(file_bytes: bytes) -> list[dict[int, str | None]]:
    """Lese die Werte einer XLSX-Datei ohne externe Abhängigkeiten."""

    try:
        with ZipFile(BytesIO(file_bytes)) as archive:
            shared_strings: list[str] = []
            if 'xl/sharedStrings.xml' in archive.namelist():
                shared_tree = ET.fromstring(archive.read('xl/sharedStrings.xml'))
                for item in shared_tree.findall('.//main:si', XLSX_NAMESPACE):
                    text_fragments = [node.text or '' for node in item.findall('.//main:t', XLSX_NAMESPACE)]
                    shared_strings.append(''.join(text_fragments))

            sheet_name = 'xl/worksheets/sheet1.xml'
            if sheet_name not in archive.namelist():
                sheet_name = next(
                    (name for name in archive.namelist() if name.startswith('xl/worksheets/sheet')),
                    None,
                )
                if not sheet_name:
                    raise ValueError('worksheet not found')

            sheet_tree = ET.fromstring(archive.read(sheet_name))
            rows: list[dict[int, str | None]] = []

            for row in sheet_tree.findall('.//main:row', XLSX_NAMESPACE):
                row_data: dict[int, str | None] = {}
                for cell in row.findall('main:c', XLSX_NAMESPACE):
                    column_index = _column_to_index(cell.get('r'))
                    if column_index is None:
                        continue

                    cell_type = cell.get('t')
                    value: str | None = None

                    if cell_type == 'inlineStr':
                        inline = cell.find('main:is/main:t', XLSX_NAMESPACE)
                        value = inline.text if inline is not None else None
                    else:
                        raw_value = cell.find('main:v', XLSX_NAMESPACE)
                        if raw_value is not None:
                            cell_text = raw_value.text
                            if cell_type == 's' and cell_text is not None:
                                try:
                                    shared_index = int(cell_text)
                                except (TypeError, ValueError):
                                    value = None
                                else:
                                    value = shared_strings[shared_index] if shared_index < len(shared_strings) else None
                            else:
                                value = cell_text

                    row_data[column_index] = value

                rows.append(row_data)

            return rows
    except (BadZipFile, KeyError, ET.ParseError, ValueError):
        raise ValueError('invalid xlsx')


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convert a hex color like ``#0d6efd`` to an rgba string with custom alpha."""

    hex_value = hex_color.lstrip('#')
    if len(hex_value) != 6:
        return hex_color

    r = int(hex_value[0:2], 16)
    g = int(hex_value[2:4], 16)
    b = int(hex_value[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _parse_excel_date(raw_value):
    """Konvertiere einen Wert aus der Excel-Datei in ein ``date`` Objekt."""

    if raw_value is None:
        return None

    if isinstance(raw_value, datetime):
        return raw_value.date()

    if isinstance(raw_value, date):
        return raw_value

    if isinstance(raw_value, (int, float, Decimal)):
        try:
            origin = datetime(1899, 12, 30)
            return (origin + timedelta(days=float(raw_value))).date()
        except (TypeError, ValueError, OverflowError):
            return None

    try:
        # Strings wie "2.10.2025" oder "2025-10-02"
        return date_parser.parse(str(raw_value), dayfirst=True).date()
    except (ValueError, TypeError, OverflowError):
        return None


def _parse_excel_decimal(raw_value):
    """Konvertiere einen Wert aus der Excel-Datei in eine ``Decimal``."""

    if raw_value in (None, ""):
        return None

    if isinstance(raw_value, Decimal):
        value = raw_value
    elif isinstance(raw_value, (int, float)):
        value = Decimal(str(raw_value))
    else:
        try:
            normalized = str(raw_value).replace(",", ".")
            value = Decimal(normalized)
        except (InvalidOperation, ValueError, TypeError):
            return None

    try:
        return value.quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def energiedaten_dashboard(request):
    """Dashboard mit Übersicht und Statistiken zum Stromverbrauch"""

    if request.method == 'POST':
        form = StromverbrauchImportForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = form.cleaned_data['file']

            try:
                rows = _read_xlsx_rows(uploaded_file.read())
            except ValueError:
                messages.error(request, "Die Datei konnte nicht gelesen werden. Bitte eine gültige XLSX-Datei hochladen.")
                return redirect('energiedaten:dashboard')

            parsed_rows = []
            invalid_rows = 0

            for row_data in rows[1:]:  # Erste Zeile enthält normalerweise die Überschriften
                datum = _parse_excel_date(row_data.get(0))
                verbrauch = _parse_excel_decimal(row_data.get(3))

                if not datum or verbrauch is None:
                    invalid_rows += 1
                    continue

                parsed_rows.append((datum, verbrauch))

            if not parsed_rows:
                messages.warning(request, "Die Datei enthielt keine gültigen Datensätze zum Import.")
                return redirect('energiedaten:dashboard')

            unique_dates = {datum for datum, _ in parsed_rows}
            existing_dates = set(
                Stromverbrauch.objects.filter(datum__in=unique_dates).values_list('datum', flat=True)
            )

            entries_to_create = {}
            skipped_existing = 0

            for datum, verbrauch in parsed_rows:
                if datum in existing_dates:
                    skipped_existing += 1
                    continue
                if datum in entries_to_create:
                    skipped_existing += 1
                    continue
                entries_to_create[datum] = verbrauch

            new_entries = [
                Stromverbrauch(datum=datum, verbrauch_kwh=verbrauch)
                for datum, verbrauch in entries_to_create.items()
            ]

            if new_entries:
                Stromverbrauch.objects.bulk_create(new_entries)

            created_count = len(new_entries)

            if created_count:
                messages.success(
                    request,
                    f"{created_count} neue Datensätze importiert. {skipped_existing} bereits vorhandene Einträge übersprungen."
                )
            else:
                messages.info(
                    request,
                    "Es wurden keine neuen Datensätze importiert, da alle Werte bereits vorhanden waren."
                )

            if invalid_rows:
                messages.warning(
                    request,
                    f"{invalid_rows} Zeilen konnten nicht verarbeitet werden und wurden übersprungen."
                )

        else:
            messages.error(request, "Bitte eine gültige Excel-Datei auswählen.")

        return redirect('energiedaten:dashboard')

    form = StromverbrauchImportForm()

    # Zeitraum-Filter aus GET-Parameter
    zeitraum = request.GET.get('zeitraum', '30')  # Standard: 30 Tage

    if zeitraum == 'alle':
        daten = Stromverbrauch.objects.all()
        titel = "Alle Daten"
    else:
        tage = int(zeitraum)
        datum_von = datetime.now().date() - timedelta(days=tage)
        daten = Stromverbrauch.objects.filter(datum__gte=datum_von)
        titel = f"Letzte {tage} Tage"

    # Gesamtstatistiken
    stats = daten.aggregate(
        gesamt=Sum('verbrauch_kwh'),
        durchschnitt=Avg('verbrauch_kwh'),
        maximum=Max('verbrauch_kwh'),
        minimum=Min('verbrauch_kwh'),
        anzahl_tage=Count('id')
    )

    # Monatliche Aggregation
    monatlich = daten.annotate(
        monat=TruncMonth('datum')
    ).values('monat').annotate(
        verbrauch=Sum('verbrauch_kwh'),
        durchschnitt=Avg('verbrauch_kwh'),
        tage=Count('id')
    ).order_by('-monat')[:12]

    # Wöchentliche Aggregation für Chart (Kalenderwochen nach Jahr)
    woechentlich = daten.annotate(
        jahr=ExtractYear('datum'),
        kw=ExtractWeek('datum')
    ).values('jahr', 'kw').annotate(
        verbrauch=Sum('verbrauch_kwh')
    ).order_by('jahr', 'kw')

    # Verbrauch nach Wochentag
    wochentage = []
    wochentag_namen = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']

    for tag_nr in range(1, 8):
        tag_daten = [d for d in daten if d.wochentag == tag_nr]
        if tag_daten:
            durchschnitt = sum(d.verbrauch_kwh for d in tag_daten) / len(tag_daten)
            wochentage.append({
                'tag': wochentag_namen[tag_nr - 1],
                'durchschnitt': round(durchschnitt, 2),
                'anzahl': len(tag_daten)
            })

    # Aktuelle Daten für Tabelle (letzte 30 Einträge)
    aktuelle_daten = daten.order_by('-datum')[:30]

    # Daten für Charts vorbereiten
    kw_labels = sorted({eintrag['kw'] for eintrag in woechentlich})
    jahre = sorted({eintrag['jahr'] for eintrag in woechentlich})

    chart_labels = [f"KW {kw:02d}" for kw in kw_labels]

    farben = [
        '#0d6efd',  # Blau
        '#20c997',  # Grün
        '#ffc107',  # Gelb
        '#dc3545',  # Rot
        '#6f42c1',  # Lila
        '#198754',  # Dunkelgrün
        '#fd7e14',  # Orange
    ]

    jahreswerte = {}
    for eintrag in woechentlich:
        jahr = eintrag['jahr']
        kw = eintrag['kw']
        jahreswerte.setdefault(jahr, {})[kw] = float(eintrag['verbrauch'])

    chart_datasets = []
    aktuelles_jahr = max(jahre) if jahre else None
    transparente_alpha = 0.35
    for index, jahr in enumerate(jahre):
        farbe = farben[index % len(farben)]
        werte = []
        for kw in kw_labels:
            wert = jahreswerte[jahr].get(kw)
            werte.append(round(wert, 2) if wert is not None else None)

        ist_aktuelles_jahr = jahr == aktuelles_jahr
        border_color = farbe if ist_aktuelles_jahr else _hex_to_rgba(farbe, transparente_alpha)
        background_color = farbe if ist_aktuelles_jahr else _hex_to_rgba(farbe, transparente_alpha)

        dataset = {
            'label': str(jahr),
            'data': werte,
            'borderColor': border_color,
            'backgroundColor': background_color,
            'borderWidth': 3 if ist_aktuelles_jahr else 2,
            'tension': 0.35,
            'fill': False,
            'pointRadius': 0,
            'pointHoverRadius': 0,
            'order': 1 if ist_aktuelles_jahr else 0,
        }

        chart_datasets.append(dataset)

    context = {
        'titel': titel,
        'zeitraum': zeitraum,
        'stats': stats,
        'monatlich': monatlich,
        'wochentage': wochentage,
        'aktuelle_daten': aktuelle_daten,
        'chart_labels': chart_labels,
        'chart_datasets': chart_datasets,
        'import_form': form,
    }

    return render(request, 'energiedaten/dashboard.html', context)


def energiedaten_detail(request):
    """Detaillierte Tabellenansicht aller Daten"""

    # Sortierung
    sortierung = request.GET.get('sort', '-datum')

    # Alle Daten mit Sortierung
    daten = Stromverbrauch.objects.all().order_by(sortierung)

    # Pagination könnte hier hinzugefügt werden

    context = {
        'daten': daten,
        'sortierung': sortierung,
    }

    return render(request, 'energiedaten/detail.html', context)