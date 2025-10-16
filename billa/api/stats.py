from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from billa.models import BillaEinkauf, BillaProdukt


@login_required
def billa_api_preisverlauf(request, produkt_id):
    """API: Preisverlauf eines Produkts"""
    produkt = get_object_or_404(BillaProdukt, pk=produkt_id)

    preis_historie = produkt.preishistorie.order_by('datum').values(
        'datum', 'preis', 'filiale'
    )

    data = {
        'produkt': produkt.name_korrigiert,
        'historie': list(preis_historie)
    }

    return JsonResponse(data)


@login_required
def billa_api_stats(request):
    """API: Aktuelle Statistiken"""

    heute = datetime.now().date()
    vor_30_tagen = heute - timedelta(days=30)

    einkaufe = BillaEinkauf.objects.filter(datum__gte=vor_30_tagen)

    stats = einkaufe.aggregate(
        anzahl=Count('id'),
        ausgaben=Sum('gesamt_preis'),
        ersparnis=Sum('gesamt_ersparnis')
    )

    return JsonResponse(stats)
