from django.shortcuts import render, get_object_or_404
from django.db.models import Count, Sum, Avg
from django.contrib.auth.decorators import login_required
from billa.models import (
    BillaEinkauf, BillaFiliale
)


@login_required
def billa_einkauefe_liste(request):
    """Übersicht aller Einkäufe"""

    # Filter aus GET-Parametern
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    filiale_id = request.GET.get('filiale')

    # Basis-Queryset
    einkaufe = BillaEinkauf.objects.select_related('filiale')

    # Datum-Filter
    if start_date:
        einkaufe = einkaufe.filter(datum__gte=start_date)
    if end_date:
        einkaufe = einkaufe.filter(datum__lte=end_date)

    # Filialen-Filter
    if filiale_id and filiale_id != 'alle':
        einkaufe = einkaufe.filter(filiale__filial_nr=filiale_id)

    # Sortierung
    einkaufe = einkaufe.order_by('-datum', '-zeit')

    # Statistiken
    stats = einkaufe.aggregate(
        anzahl=Count('id'),
        gesamt_ausgaben=Sum('gesamt_preis'),
        gesamt_ersparnis=Sum('gesamt_ersparnis'),
        avg_warenkorb=Avg('gesamt_preis')
    )

    # Filialen für Filter
    filialen = BillaFiliale.objects.filter(aktiv=True).order_by('filial_nr')

    context = {
        'einkaufe': einkaufe,
        'stats': stats,
        'filialen': filialen,
        'selected_filiale': filiale_id or 'alle',
        'start_date': start_date,
        'end_date': end_date,
    }

    return render(request, 'billa/billa_einkauefe_liste.html', context)

@login_required
def billa_einkauf_detail(request, einkauf_id):
    """Detail-Ansicht eines Einkaufs"""
    einkauf = get_object_or_404(BillaEinkauf, pk=einkauf_id)
    artikel = einkauf.artikel.select_related('produkt').order_by('position')

    context = {
        'einkauf': einkauf,
        'artikel': artikel
    }

    return render(request, 'billa/billa_einkauf_detail.html', context)
