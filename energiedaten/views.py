# views.py
from django.shortcuts import render
from django.db.models import Sum, Avg, Max, Min, Count
from django.db.models.functions import TruncMonth, TruncWeek, TruncYear
from datetime import datetime, timedelta
from .models import Stromverbrauch


def energiedaten_dashboard(request):
    """Dashboard mit Übersicht und Statistiken zum Stromverbrauch"""

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

    # Wöchentliche Aggregation für Chart
    woechentlich = daten.annotate(
        woche=TruncWeek('datum')
    ).values('woche').annotate(
        verbrauch=Sum('verbrauch_kwh')
    ).order_by('woche')

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
    chart_labels = [w['woche'].strftime('%d.%m.%Y') for w in woechentlich]
    chart_werte = [float(w['verbrauch']) for w in woechentlich]

    context = {
        'titel': titel,
        'zeitraum': zeitraum,
        'stats': stats,
        'monatlich': monatlich,
        'wochentage': wochentage,
        'aktuelle_daten': aktuelle_daten,
        'chart_labels': chart_labels,
        'chart_werte': chart_werte,
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