from django.shortcuts import render, redirect
from django.http import JsonResponse
import json
from django.contrib.auth import logout
import numpy as np
from django.db.models import Sum, Count, Q, Value, CharField, Min
from django.db.models.functions import TruncMonth
from datetime import datetime, timedelta, date
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import (
    FactTransactionsSigi, FactTransactionsRobert,
    DimAccount, DimCategory, DimPayee, DimCategoryGroup, DimFlag,
    ScheduledTransaction, RegisteredDevice
)
from .forms import TransactionForm
from collections import defaultdict
from decimal import Decimal
from .utils import get_account_icon, calculate_account_balance, CATEGORY_CONFIG

from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings
import logging
from .receipt_analyzer import ReceiptAnalyzer

logger = logging.getLogger(__name__)


def user_is_not_robert(user):
    """Prüft ob User NICHT robert ist"""
    return user.username != 'robert'


# Zentrale Farbdefinitionen für Kategorien
CATEGORY_COLORS = {
    'Cash': {
        'rgb': (75, 192, 192),  # Türkis
        'name': 'Cash'
    },
    'Credit': {
        'rgb': (255, 99, 132),  # Rot
        'name': 'Credit'
    },
    'MidtermInvest': {
        'rgb': (54, 162, 235),  # Blau
        'name': 'Mittelfristige Investments'
    },
    'LongtermInvest': {
        'rgb': (153, 102, 255),  # Lila
        'name': 'Langfristige Investments'
    },
}


@login_required
def manage_devices(request):
    """Zeigt alle registrierten Geräte des Users"""
    devices = request.user.devices.all().order_by('-last_used')
    current_device_token = request.session.get('device_token')

    if request.method == 'POST':
        device_id = request.POST.get('device_id')
        action = request.POST.get('action')

        try:
            device = RegisteredDevice.objects.get(id=device_id, user=request.user)

            if action == 'rename':
                new_name = request.POST.get('new_name', '').strip()
                if new_name:
                    device.device_name = new_name
                    device.save()
                    messages.success(request, f'Gerät umbenannt zu: {new_name}')

            elif action == 'deactivate':
                # Verhindere, dass User sich selbst aussperrt
                if str(device.device_token) == current_device_token:
                    messages.error(request, 'Du kannst das aktuelle Gerät nicht deaktivieren!')
                else:
                    device.is_active = False
                    device.save()
                    messages.warning(request, f'Gerät "{device.device_name}" wurde deaktiviert')

            elif action == 'activate':
                device.is_active = True
                device.save()
                messages.success(request, f'Gerät "{device.device_name}" wurde aktiviert')

        except RegisteredDevice.DoesNotExist:
            messages.error(request, 'Gerät nicht gefunden')

        return redirect('finance:manage_devices')

    return render(request, 'finance/manage_devices.html', {
        'devices': devices,
        'current_device_token': current_device_token
    })


@login_required
def delete_device(request, device_id):
    """Löscht ein Gerät (nicht das aktuelle)"""
    current_device_token = request.session.get('device_token')

    try:
        device = RegisteredDevice.objects.get(id=device_id, user=request.user)

        if str(device.device_token) == current_device_token:
            messages.error(request, 'Du kannst das aktuelle Gerät nicht löschen!')
        else:
            device_name = device.device_name
            device.delete()
            messages.success(request, f'Gerät "{device_name}" wurde entfernt')
    except RegisteredDevice.DoesNotExist:
        messages.error(request, 'Gerät nicht gefunden')

    return redirect('finance:manage_devices')


@login_required
def custom_logout(request):
    """Logout und lösche Device Cookie"""
    logout(request)
    response = redirect('login')
    response.delete_cookie('device_id')
    return response


def home(request):
    """Startseite mit Übersicht aller Bereiche"""
    return render(request, 'finance/home.html')

def generate_color_shades(rgb_tuple, num_shades=5):
    """
    Alternative Implementierung mit maximalen Kontrasten
    Nutzt verschiedene Helligkeits- und Sättigungsstufen
    """
    r, g, b = rgb_tuple
    shades = []

    # Vordefinierte Faktoren für maximale Unterscheidbarkeit
    # Diese Werte wurden optimiert um große visuelle Unterschiede zu erzeugen
    contrast_factors = [
        0.4,  # Sehr dunkel
        0.6,  # Dunkel
        0.8,  # Mittel
        1.0,  # Normal
        1.2,  # Hell (mit Weißmischung)
        1.4,  # Sehr hell
        1.6,  # Pastell
        1.8,  # Sehr pastell
    ]

    for i in range(min(num_shades, len(contrast_factors))):
        factor = contrast_factors[i]

        if factor <= 1.0:
            # Dunkle Töne: Reduziere RGB-Werte
            new_r = int(r * factor)
            new_g = int(g * factor)
            new_b = int(b * factor)
        else:
            # Helle Töne: Mische mit Weiß
            white_mix = (factor - 1.0) / 0.8  # Normalisiere auf 0-1
            new_r = int(r + (255 - r) * white_mix)
            new_g = int(g + (255 - g) * white_mix)
            new_b = int(b + (255 - b) * white_mix)

        # Stelle sicher, dass Werte im gültigen Bereich liegen
        new_r = max(0, min(255, new_r))
        new_g = max(0, min(255, new_g))
        new_b = max(0, min(255, new_b))

        shades.append({
            'border': f'rgb({new_r}, {new_g}, {new_b})',
            'fill': f'rgba({new_r}, {new_g}, {new_b}, 0.5)'
        })

    return shades


@login_required
def dashboard(request):
    """Haupt-Dashboard mit Übersicht und KPIs"""
    # Robert wird zu Transaktionen Haushalt weitergeleitet
    if request.user.username == 'robert':
        return redirect('finance:household_transactions')

    # Jahr-Filter aus GET-Parameter, Standard ist aktuelles Jahr
    selected_year = request.GET.get('year', datetime.now().year)
    selected_year = int(selected_year)

    # Verfügbare Jahre für Dropdown (von aktuell bis 2020)
    current_year_now = datetime.now().year
    available_years = range(current_year_now, 2019, -1)

    transactions = FactTransactionsSigi.objects.filter(date__year=selected_year)

    total_inflow = transactions.aggregate(Sum('inflow'))['inflow__sum'] or 0
    total_outflow = transactions.aggregate(Sum('outflow'))['outflow__sum'] or 0
    netto = total_inflow - total_outflow
    transaction_count = transactions.count()

    last_month = datetime.now() - timedelta(days=30)
    last_month_outflow = transactions.filter(
        date__gte=last_month
    ).aggregate(Sum('outflow'))['outflow__sum'] or 0

    # Top Payees statt Top Kategorien
    top_payees = transactions.filter(
        outflow__gt=0
    ).values(
        'payee__payee'
    ).exclude(
        category__categorygroup__category_group__iexact='NoCategory'
    ).exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).annotate(
        total=Sum('outflow'),
        count=Count('id')
    ).order_by('-total')[:10]

    recent_transactions = transactions.select_related(
        'account', 'payee', 'category', 'flag'
    )[:10]

    context = {
        'current_year': selected_year,  # Das ausgewählte Jahr
        'available_years': available_years,  # Für Dropdown
        'total_inflow': total_inflow,
        'total_outflow': total_outflow,
        'netto': netto,
        'transaction_count': transaction_count,
        'last_month_outflow': last_month_outflow,
        'top_payees': top_payees,
        'recent_transactions': recent_transactions
    }

    return render(request, 'finance/dashboard.html', context)


@login_required
def transactions_list(request):
    """Liste aller Transaktionen mit Filter"""
    # Robert darf nicht auf alle Transaktionen zugreifen
    if request.user.username == 'robert':
        messages.warning(request, 'Du hast keine Berechtigung für diese Seite.')
        return redirect('finance:household_transactions')

    transactions = FactTransactionsSigi.objects.select_related(
        'account', 'payee', 'category', 'category__categorygroup', 'flag'
    ).all()

    year = request.GET.get('year', '')
    month = request.GET.get('month', '')
    account_id = request.GET.get('account', '')
    category_id = request.GET.get('category', '')
    search = request.GET.get('search', '')

    if year:
        transactions = transactions.filter(date__year=int(year))
    if month:
        transactions = transactions.filter(date__month=int(month))
    if account_id:
        transactions = transactions.filter(account_id=int(account_id))
    if category_id:
        transactions = transactions.filter(category_id=int(category_id))
    if search:
        transactions = transactions.filter(
            Q(payee__payee__icontains=search) |
            Q(memo__icontains=search)
        )

    # Statistiken berechnen mit allen Ausschlüssen
    transactions_for_stats = transactions.exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).exclude(
        category_id=1
    )

    total_inflow = transactions.exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).filter(
        category_id=1
    ).aggregate(Sum('inflow'))['inflow__sum'] or 0

    stats_aggregate = transactions_for_stats.aggregate(
        sum_inflow=Sum('inflow'),
        sum_outflow=Sum('outflow')
    )
    category_inflow = stats_aggregate['sum_inflow'] or 0
    category_outflow = stats_aggregate['sum_outflow'] or 0
    total_outflow_netto = category_outflow - category_inflow

    netto = total_inflow - total_outflow_netto

    transaction_count = transactions.count()
    transfer_count = transactions.filter(payee__payee_type='transfer').count()
    kursschwankung_count = transactions.filter(payee__payee_type='kursschwankung').count()
    excluded_count = transfer_count + kursschwankung_count

    accounts = DimAccount.objects.all()
    categories = DimCategory.objects.select_related('categorygroup').all()
    years = range(datetime.now().year, 2019, -1)

    transactions = transactions[:100]

    context = {
        'transactions': transactions,
        'accounts': accounts,
        'categories': categories,
        'years': years,
        'selected_year': year,
        'selected_month': month,
        'selected_account': account_id,
        'selected_category': category_id,
        'search_query': search,
        'total_inflow': total_inflow,
        'total_outflow': total_outflow_netto,
        'transaction_count': transaction_count,
        'transfer_count': transfer_count,
        'kursschwankung_count': kursschwankung_count,
        'excluded_count': excluded_count,
        'netto': netto,
        'category_groups': DimCategoryGroup.objects.all(),
        'payees': DimPayee.objects.all(),
        'flags': DimFlag.objects.all(),  # für Nicht-Robert
        'is_robert': request.user.username == 'robert',
        'today': date.today(),
    }

    return render(request, 'finance/transactions.html', context)


@login_required
def household_transactions(request):
    """Haushalt-Transaktionen"""
    sigi_base = FactTransactionsSigi.objects.filter(flag_id=5)
    robert_base = FactTransactionsRobert.objects.all()

    sigi_transactions = FactTransactionsSigi.objects.filter(
        flag_id=5
    ).select_related(
        'account', 'payee', 'category', 'category__categorygroup', 'flag'
    ).annotate(
        person=Value('Sigi', output_field=CharField())
    )

    robert_transactions = FactTransactionsRobert.objects.select_related(
        'account', 'payee', 'category', 'category__categorygroup', 'flag'
    ).annotate(
        person=Value('Robert', output_field=CharField())
    )

    year = request.GET.get('year', '')
    month = request.GET.get('month', '')
    account_id = request.GET.get('account', '')
    category_id = request.GET.get('category', '')
    person_filter = request.GET.get('person', '')
    search = request.GET.get('search', '')

    if year:
        sigi_transactions = sigi_transactions.filter(date__year=int(year))
        robert_transactions = robert_transactions.filter(date__year=int(year))
    if month:
        sigi_transactions = sigi_transactions.filter(date__month=int(month))
        robert_transactions = robert_transactions.filter(date__month=int(month))
    if account_id:
        sigi_transactions = sigi_transactions.filter(account_id=int(account_id))
        robert_transactions = robert_transactions.filter(account_id=int(account_id))
    if category_id:
        sigi_transactions = sigi_transactions.filter(category_id=int(category_id))
        robert_transactions = robert_transactions.filter(category_id=int(category_id))
    if search:
        sigi_transactions = sigi_transactions.filter(
            Q(payee__payee__icontains=search) |
            Q(memo__icontains=search)
        )
        robert_transactions = robert_transactions.filter(
            Q(payee__payee__icontains=search) |
            Q(memo__icontains=search)
        )

    sigi_for_stats = sigi_transactions.exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).exclude(
        category_id=1
    )
    robert_for_stats = robert_transactions.exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).exclude(
        category_id=1
    )

    sigi_stats = sigi_for_stats.aggregate(
        sum_inflow=Sum('inflow'),
        sum_outflow=Sum('outflow')
    )
    sigi_inflow = sigi_stats['sum_inflow'] or 0
    sigi_outflow_gross = sigi_stats['sum_outflow'] or 0
    sigi_outflow = sigi_outflow_gross - sigi_inflow

    robert_stats = robert_for_stats.aggregate(
        sum_inflow=Sum('inflow'),
        sum_outflow=Sum('outflow')
    )
    robert_inflow = robert_stats['sum_inflow'] or 0
    robert_outflow_gross = robert_stats['sum_outflow'] or 0
    robert_outflow = robert_outflow_gross - robert_inflow

    total_outflow = sigi_outflow + robert_outflow

    sigi_list_full = list(sigi_transactions)
    robert_list_full = list(robert_transactions)

    if person_filter == 'sigi':
        transactions_full = sigi_list_full
    elif person_filter == 'robert':
        transactions_full = robert_list_full
    else:
        transactions_full = sigi_list_full + robert_list_full

    transactions_full.sort(key=lambda x: x.date, reverse=True)

    robert_percentage = (robert_outflow / total_outflow * 100) if total_outflow > 0 else 0
    sigi_percentage = (sigi_outflow / total_outflow * 100) if total_outflow > 0 else 0

    transaction_count = len(transactions_full)
    transfer_count = sum(1 for t in transactions_full if t.payee and t.payee.payee_type == 'transfer')
    kursschwankung_count = sum(1 for t in transactions_full if t.payee and t.payee.payee_type == 'kursschwankung')
    excluded_count = transfer_count + kursschwankung_count

    transactions = transactions_full[:100]

    from django.db.models import functions
    sigi_account_ids = sigi_base.values_list('account_id', flat=True).distinct()
    robert_account_ids = robert_base.values_list('account_id', flat=True).distinct()
    available_account_ids = set(sigi_account_ids) | set(robert_account_ids)
    accounts = DimAccount.objects.filter(id__in=available_account_ids).order_by('account')

    sigi_category_ids = sigi_base.values_list('category_id', flat=True).distinct()
    robert_category_ids = robert_base.values_list('category_id', flat=True).distinct()
    available_category_ids = set(sigi_category_ids) | set(robert_category_ids)
    categories = DimCategory.objects.filter(
        id__in=available_category_ids
    ).select_related('categorygroup').order_by('category')

    sigi_years = sigi_base.annotate(
        year=functions.ExtractYear('date')
    ).values_list('year', flat=True).distinct()
    robert_years = robert_base.annotate(
        year=functions.ExtractYear('date')
    ).values_list('year', flat=True).distinct()
    available_years = sorted(set(sigi_years) | set(robert_years), reverse=True)

    context = {
        'transactions': transactions,
        'accounts': accounts,
        'categories': categories,
        'years': available_years,
        'selected_year': year,
        'selected_month': month,
        'selected_account': account_id,
        'selected_category': category_id,
        'selected_person': person_filter,
        'search_query': search,
        'total_outflow': total_outflow,
        'robert_outflow': robert_outflow,
        'sigi_outflow': sigi_outflow,
        'robert_percentage': robert_percentage,
        'sigi_percentage': sigi_percentage,
        'transaction_count': transaction_count,
        'transfer_count': transfer_count,
        'kursschwankung_count': kursschwankung_count,
        'excluded_count': excluded_count,
    }

    return render(request, 'finance/household_transactions.html', context)


@login_required
def api_monthly_spending(request):
    """API: Monatliche Ausgaben für Chart"""
    if request.user.username == 'robert':
        return JsonResponse({'error': 'Keine Berechtigung'}, status=403)

    year = request.GET.get('year', datetime.now().year)

    monthly_data = FactTransactionsSigi.objects.filter(
        date__year=year
    ).annotate(
        month=TruncMonth('date')
    ).values('month').annotate(
        inflow=Sum('inflow'),
        outflow=Sum('outflow')
    ).order_by('month')

    labels = []
    inflow_data = []
    outflow_data = []

    for item in monthly_data:
        labels.append(item['month'].strftime('%B'))
        inflow_data.append(float(item['inflow'] or 0))
        outflow_data.append(float(item['outflow'] or 0))

    return JsonResponse({
        'labels': labels,
        'datasets': [
            {
                'label': 'Einnahmen',
                'data': inflow_data,
                'backgroundColor': 'rgba(75, 192, 192, 0.6)',
                'borderColor': 'rgba(75, 192, 192, 1)',
                'borderWidth': 2
            },
            {
                'label': 'Ausgaben',
                'data': outflow_data,
                'backgroundColor': 'rgba(255, 99, 132, 0.6)',
                'borderColor': 'rgba(255, 99, 132, 1)',
                'borderWidth': 2
            }
        ]
    })


@login_required
def api_category_breakdown(request):
    """API: Ausgaben nach Kategorie für Pie Chart"""
    if request.user.username == 'robert':
        return JsonResponse({'error': 'Keine Berechtigung'}, status=403)

    year = request.GET.get('year', datetime.now().year)

    category_data = FactTransactionsSigi.objects.filter(
        date__year=year,
        outflow__gt=0
    ).values(
        'category__categorygroup__category_group'
    ).exclude(
        category__categorygroup__category_group__iexact='NoCategory'
    ).exclude(
        category__categorygroup__category_group__iexact='Inflow'
    ).annotate(
        total=Sum('outflow')
    ).order_by('-total')[:10]

    labels = []
    data = []

    for item in category_data:
        category_name = item['category__categorygroup__category_group'] or 'Unbekannt'
        labels.append(category_name)
        data.append(float(item['total'] or 0))

    colors = [
        'rgba(255, 99, 132, 0.8)',
        'rgba(54, 162, 235, 0.8)',
        'rgba(255, 206, 86, 0.8)',
        'rgba(75, 192, 192, 0.8)',
        'rgba(153, 102, 255, 0.8)',
        'rgba(255, 159, 64, 0.8)',
        'rgba(199, 199, 199, 0.8)',
        'rgba(83, 102, 255, 0.8)',
        'rgba(255, 99, 255, 0.8)',
        'rgba(99, 255, 132, 0.8)',
    ]

    return JsonResponse({
        'labels': labels,
        'datasets': [{
            'data': data,
            'backgroundColor': colors[:len(data)],
            'borderWidth': 1
        }]
    })


@login_required
def api_top_payees(request):
    """API: Top Zahlungsempfänger"""
    if request.user.username == 'robert':
        return JsonResponse({'error': 'Keine Berechtigung'}, status=403)

    year = request.GET.get('year', datetime.now().year)

    payee_data = FactTransactionsSigi.objects.filter(
        date__year=year,
        outflow__gt=0
    ).values(
        'payee__payee'
    ).annotate(
        total=Sum('outflow'),
        count=Count('id')
    ).order_by('-total')[:10]

    labels = []
    data = []

    for item in payee_data:
        payee_name = item['payee__payee'] or 'Unbekannt'
        labels.append(payee_name)
        data.append(float(item['total'] or 0))

    return JsonResponse({
        'labels': labels,
        'datasets': [{
            'label': 'Ausgaben (€)',
            'data': data,
            'backgroundColor': 'rgba(54, 162, 235, 0.6)',
            'borderColor': 'rgba(54, 162, 235, 1)',
            'borderWidth': 2
        }]
    })


@login_required
def asset_overview(request):
    """Vermögensübersicht"""
    if request.user.username == 'robert':
        messages.warning(request, 'Du hast keine Berechtigung für diese Seite.')
        return redirect('finance:household_transactions')

    selected_date = request.GET.get('date')
    if selected_date:
        try:
            current_date = datetime.strptime(selected_date, '%Y-%m').date()
        except ValueError:
            current_date = datetime.now().date()
    else:
        current_date = datetime.now().date()

    if current_date.month == 12:
        current_date = current_date.replace(day=31)
    else:
        next_month = current_date.replace(month=current_date.month + 1, day=1)
        current_date = next_month - timedelta(days=1)

    prev_month_temp = (current_date.replace(day=1) - timedelta(days=1))
    if prev_month_temp.month == 12:
        prev_month = prev_month_temp.replace(day=31)
    else:
        next_month = prev_month_temp.replace(month=prev_month_temp.month + 1, day=1)
        prev_month = next_month - timedelta(days=1)

    try:
        prev_year = current_date.replace(year=current_date.year - 1)
    except ValueError:
        prev_year = current_date.replace(year=current_date.year - 1, day=28)

    accounts = DimAccount.objects.select_related('accounttype').all()

    categories_dict = defaultdict(lambda: {
        'positions': [],
        'total_current': Decimal('0'),
        'total_prev_month': Decimal('0'),
        'total_prev_year': Decimal('0'),
        'display_name': '',
        'order': 99,
        'color_class': '',
    })

    for account in accounts:
        # **NEU: Hole Kategorie direkt aus Datenbank**
        if account.accounttype and account.accounttype.accounttypes:
            category_name = account.accounttype.accounttypes
        else:
            category_name = 'Sonstige'

        # Hole Konfiguration für diese Kategorie
        category_config = CATEGORY_CONFIG.get(category_name, CATEGORY_CONFIG['Sonstige'])

        # Icon weiterhin aus Account-Namen ableiten (für Details)
        icon = get_account_icon(account.account)

        current_balance = calculate_account_balance(account.id, current_date)
        prev_month_balance = calculate_account_balance(account.id, prev_month)
        prev_year_balance = calculate_account_balance(account.id, prev_year)

        if current_balance == 0 and prev_month_balance == 0 and prev_year_balance == 0:
            continue

        delta_month = None
        if prev_month_balance != 0:
            delta_month = ((current_balance - prev_month_balance) / abs(prev_month_balance) * 100)

        delta_year = None
        if prev_year_balance != 0:
            delta_year = ((current_balance - prev_year_balance) / abs(prev_year_balance) * 100)

        position_info = {
            'name': account.account,
            'icon': icon,
            'current_balance': current_balance,
            'prev_month_balance': prev_month_balance,
            'prev_year_balance': prev_year_balance,
            'delta_month': delta_month,
            'delta_year': delta_year,
        }

        categories_dict[category_name]['positions'].append(position_info)
        categories_dict[category_name]['total_current'] += current_balance
        categories_dict[category_name]['total_prev_month'] += prev_month_balance
        categories_dict[category_name]['total_prev_year'] += prev_year_balance
        categories_dict[category_name]['display_name'] = category_config['display_name']
        categories_dict[category_name]['order'] = category_config['order']
        categories_dict[category_name]['color_class'] = category_config['color_class']

    categories_data = []
    for category_name, data in categories_dict.items():
        if data['total_prev_month'] != 0:
            data['delta_month'] = (
                    (data['total_current'] - data['total_prev_month'])
                    / abs(data['total_prev_month']) * 100
            )
        else:
            data['delta_month'] = None

        if data['total_prev_year'] != 0:
            data['delta_year'] = (
                    (data['total_current'] - data['total_prev_year'])
                    / abs(data['total_prev_year']) * 100
            )
        else:
            data['delta_year'] = None

        data['positions'].sort(key=lambda x: x['name'])

        categories_data.append({
            'name': category_name,
            **data
        })

    categories_data.sort(key=lambda x: x['order'])

    # Füge Farbinformationen zu jeder Kategorie hinzu
    for category in categories_data:
        cat_name = category['name']
        if cat_name in CATEGORY_COLORS:
            r, g, b = CATEGORY_COLORS[cat_name]['rgb']
            category['color_rgb'] = f'rgb({r}, {g}, {b})'
            category['color_rgba'] = f'rgba({r}, {g}, {b}, 0.15)'


    total_current = sum(cat['total_current'] for cat in categories_data)
    total_prev_month = sum(cat['total_prev_month'] for cat in categories_data)
    total_prev_year = sum(cat['total_prev_year'] for cat in categories_data)

    total_delta_month = None
    if total_prev_month != 0:
        total_delta_month = ((total_current - total_prev_month) / abs(total_prev_month) * 100)

    total_delta_year = None
    if total_prev_year != 0:
        total_delta_year = ((total_current - total_prev_year) / abs(total_prev_year) * 100)

    context = {
        'current_date': current_date,
        'prev_month': prev_month,
        'prev_year': prev_year,
        'categories': categories_data,
        'total_current': total_current,
        'total_prev_month': total_prev_month,
        'total_prev_year': total_prev_year,
        'total_delta_month': total_delta_month,
        'total_delta_year': total_delta_year,
    }

    return render(request, 'finance/asset_overview.html', context)


@login_required
def add_transaction(request):
    """Formular zum Hinzufügen einer neuen Transaktion"""
    if request.method == 'POST':
        form = TransactionForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                transaction = form.save()
                messages.success(request, 'Transaktion erfolgreich gespeichert!')
                form = TransactionForm(user=request.user, initial={'date': date.today()})
            except Exception as e:
                messages.error(request, f'Fehler beim Speichern: {str(e)}')
        else:
            messages.error(request, 'Bitte überprüfe deine Eingaben.')
    else:
        form = TransactionForm(user=request.user, initial={'date': date.today()})

    payees = DimPayee.objects.all().order_by('payee')
    category_groups = DimCategoryGroup.objects.all().order_by('category_group')
    categories = DimCategory.objects.select_related('categorygroup').all().order_by('category')

    context = {
        'form': form,
        'payees': payees,
        'category_groups': category_groups,
        'categories': categories,
        'is_robert': request.user.username == 'robert',
    }

    return render(request, 'finance/transaction_form.html', context)


@login_required
def delete_transaction(request, pk):
    """Löscht eine Transaktion mit Undo-Möglichkeit"""
    if request.method != 'POST':
        return redirect('finance:transactions')

    # Hole die Transaktion - unterscheide zwischen Robert und Sigi
    transaction = None
    is_robert_transaction = False

    # Versuche erst in Robert's Tabelle zu finden
    try:
        transaction = FactTransactionsRobert.objects.get(pk=pk)
        is_robert_transaction = True
    except FactTransactionsRobert.DoesNotExist:
        pass

    # Falls nicht gefunden, suche in Sigi's Tabelle
    if not transaction:
        try:
            transaction = FactTransactionsSigi.objects.get(pk=pk)
            is_robert_transaction = False
        except FactTransactionsSigi.DoesNotExist:
            messages.error(request, 'Transaktion nicht gefunden.')
            return redirect(request.META.get('HTTP_REFERER', 'finance:transactions'))

    # Berechtigungsprüfung
    # Fall 1: Robert versucht Sigi-Transaktion zu löschen
    if request.user.username == 'robert' and not is_robert_transaction:
        messages.error(request, 'Du darfst nur deine eigenen Transaktionen löschen.')
        return redirect(request.META.get('HTTP_REFERER', 'finance:household_transactions'))

    # Fall 2: Nicht-Robert User versucht Robert-Transaktion zu löschen
    if request.user.username != 'robert' and is_robert_transaction:
        messages.error(request, 'Du darfst Roberts Transaktionen nicht löschen.')
        return redirect(request.META.get('HTTP_REFERER', 'finance:transactions'))

    # Speichere Transaktionsdaten für Undo in Session
    undo_data = {
        'table': 'robert' if is_robert_transaction else 'sigi',
        'account_id': transaction.account_id,
        'flag_id': transaction.flag_id,
        'date': str(transaction.date),
        'payee_id': transaction.payee_id,
        'category_id': transaction.category_id,
        'memo': transaction.memo,
        'outflow': str(transaction.outflow) if transaction.outflow else None,
        'inflow': str(transaction.inflow) if transaction.inflow else None,
        'payee_name': str(transaction.payee) if transaction.payee else 'Unbekannt',
        'amount': str(transaction.outflow or transaction.inflow or 0),
    }

    # Speichere in Session für Undo
    request.session['undo_transaction'] = undo_data
    request.session['undo_expires'] = (datetime.now() + timedelta(seconds=30)).isoformat()

    # Lösche die Transaktion
    transaction.delete()

    # Success Message mit Undo-Hinweis
    messages.success(
        request,
        f'Transaktion gelöscht: {undo_data["payee_name"]} - €{undo_data["amount"]}',
        extra_tags='deletable'  # Marker für Toast mit Undo-Button
    )

    # Redirect zurück zur vorherigen Seite
    return redirect(request.META.get('HTTP_REFERER', 'finance:transactions'))


@login_required
def undo_delete(request):
    """Stellt eine gelöschte Transaktion wieder her"""
    if request.method != 'POST':
        return redirect('finance:transactions')

    undo_data = request.session.get('undo_transaction')
    undo_expires = request.session.get('undo_expires')

    if not undo_data or not undo_expires:
        messages.error(request, 'Keine Transaktion zum Wiederherstellen verfügbar.')
        return redirect(request.META.get('HTTP_REFERER', 'finance:transactions'))

    # Prüfe Zeitfenster
    from dateutil import parser
    if datetime.now() > parser.parse(undo_expires):
        del request.session['undo_transaction']
        del request.session['undo_expires']
        messages.error(request, 'Undo-Zeitfenster ist abgelaufen.')
        return redirect(request.META.get('HTTP_REFERER', 'finance:transactions'))

    # Wiederherstellen
    try:
        if undo_data['table'] == 'robert':
            FactTransactionsRobert.objects.create(
                account_id=undo_data['account_id'],
                flag_id=undo_data['flag_id'],
                date=undo_data['date'],
                payee_id=undo_data['payee_id'],
                category_id=undo_data['category_id'],
                memo=undo_data['memo'],
                outflow=Decimal(undo_data['outflow']) if undo_data['outflow'] else None,
                inflow=Decimal(undo_data['inflow']) if undo_data['inflow'] else None,
            )
        else:
            FactTransactionsSigi.objects.create(
                account_id=undo_data['account_id'],
                flag_id=undo_data['flag_id'],
                date=undo_data['date'],
                payee_id=undo_data['payee_id'],
                category_id=undo_data['category_id'],
                memo=undo_data['memo'],
                outflow=Decimal(undo_data['outflow']) if undo_data['outflow'] else None,
                inflow=Decimal(undo_data['inflow']) if undo_data['inflow'] else None,
            )

        del request.session['undo_transaction']
        del request.session['undo_expires']

        messages.success(request, f'Transaktion wiederhergestellt: {undo_data["payee_name"]}')

    except Exception as e:
        messages.error(request, f'Fehler beim Wiederherstellen: {str(e)}')

    return redirect(request.META.get('HTTP_REFERER', 'finance:transactions'))


@login_required
def api_get_payee_suggestions(request):
    """
    API: Gibt Kategorie-Vorschläge basierend auf historischen Transaktionen zurück
    """
    payee_name = request.GET.get('payee', '').strip()

    if not payee_name:
        return JsonResponse({'error': 'Kein Payee angegeben'}, status=400)

    try:
        # Finde den Payee
        payee = DimPayee.objects.filter(payee__iexact=payee_name).first()

        if not payee:
            return JsonResponse({
                'found': False,
                'message': 'Payee noch nicht in Datenbank'
            })

        # Suche in beiden Tabellen nach den letzten Transaktionen mit diesem Payee
        # und finde die am häufigsten verwendete Kategorie

        # Sigi Transaktionen
        sigi_categories = FactTransactionsSigi.objects.filter(
            payee=payee
        ).exclude(
            category__isnull=True
        ).values(
            'category_id',
            'category__category',
            'category__categorygroup_id',
            'category__categorygroup__category_group'
        ).annotate(
            count=Count('id')
        ).order_by('-count')[:1]

        # Robert Transaktionen
        robert_categories = FactTransactionsRobert.objects.filter(
            payee=payee
        ).exclude(
            category__isnull=True
        ).values(
            'category_id',
            'category__category',
            'category__categorygroup_id',
            'category__categorygroup__category_group'
        ).annotate(
            count=Count('id')
        ).order_by('-count')[:1]

        # Kombiniere und finde die häufigste
        all_suggestions = list(sigi_categories) + list(robert_categories)

        if not all_suggestions:
            return JsonResponse({
                'found': False,
                'message': 'Keine historischen Transaktionen gefunden'
            })

        # Sortiere nach count und nimm die häufigste
        best_suggestion = max(all_suggestions, key=lambda x: x['count'])

        return JsonResponse({
            'found': True,
            'category_id': best_suggestion['category_id'],
            'category_name': best_suggestion['category__category'],
            'categorygroup_id': best_suggestion['category__categorygroup_id'],
            'categorygroup_name': best_suggestion['category__categorygroup__category_group'],
            'usage_count': best_suggestion['count']
        })

    except Exception as e:
        return JsonResponse({
            'error': f'Fehler: {str(e)}'
        }, status=500)


@login_required
def scheduled_transactions_list(request):
    """Liste aller Scheduled Transactions"""
    # Robert sieht nur seine eigenen
    if request.user.username == 'robert':
        scheduled = ScheduledTransaction.objects.filter(
            target_table='robert'
        ).select_related(
            'account', 'payee', 'category', 'category__categorygroup', 'flag'
        ).all()
    else:
        scheduled = ScheduledTransaction.objects.select_related(
            'account', 'payee', 'category', 'category__categorygroup', 'flag'
        ).all()

    # Statistiken
    active_count = scheduled.filter(is_active=True).count()
    overdue_count = scheduled.filter(
        is_active=True,
        next_execution_date__lt=date.today()
    ).count()

    context = {
        'scheduled_transactions': scheduled,
        'active_count': active_count,
        'overdue_count': overdue_count,
        'is_robert': request.user.username == 'robert',
    }

    return render(request, 'finance/scheduled_transactions.html', context)


@login_required
def scheduled_transaction_create(request):
    """Neue Scheduled Transaction erstellen"""
    if request.method == 'POST':
        try:
            # Payee holen oder erstellen
            payee_name = request.POST.get('payee').strip()
            payee, _ = DimPayee.objects.get_or_create(payee=payee_name)

            # Betrag und Typ
            amount = Decimal(request.POST.get('amount'))
            transaction_type = request.POST.get('transaction_type')

            outflow = amount if transaction_type == 'outflow' else None
            inflow = amount if transaction_type == 'inflow' else None

            # Target Table: Für Robert immer 'robert', sonst aus Form
            if request.user.username == 'robert':
                target_table = 'robert'
            else:
                target_table = request.POST.get('target_table', 'sigi')

            # Erstelle Scheduled Transaction
            scheduled = ScheduledTransaction.objects.create(
                target_table=target_table,
                account_id=request.POST.get('account'),
                flag_id=request.POST.get('flag') or None,
                payee=payee,
                category_id=request.POST.get('category'),
                memo=request.POST.get('memo', ''),
                outflow=outflow,
                inflow=inflow,
                frequency=request.POST.get('frequency'),
                start_date=request.POST.get('start_date'),
                end_date=request.POST.get('end_date') or None,
                next_execution_date=request.POST.get('start_date'),
                created_by=request.user.username,
            )

            messages.success(
                request,
                f'Scheduled Transaction erstellt: {scheduled.payee} - '
                f'{scheduled.get_frequency_display()}'
            )
            return redirect('finance:scheduled_transactions')

        except Exception as e:
            messages.error(request, f'Fehler beim Erstellen: {str(e)}')

    # Daten für Formular
    # Robert sieht nur Roberts Account (ID 18)
    if request.user.username == 'robert':
        accounts = DimAccount.objects.filter(id=18)
    else:
        accounts = DimAccount.objects.all()

    flags = DimFlag.objects.all()
    payees = DimPayee.objects.all().order_by('payee')
    category_groups = DimCategoryGroup.objects.all().order_by('category_group')
    categories = DimCategory.objects.select_related('categorygroup').all()

    context = {
        'accounts': accounts,
        'flags': flags,
        'payees': payees,
        'category_groups': category_groups,
        'categories': categories,
        'today': date.today(),
        'is_robert': request.user.username == 'robert',
    }

    return render(request, 'finance/scheduled_transaction_form.html', context)


@login_required
def scheduled_transaction_edit(request, pk):
    """Scheduled Transaction bearbeiten"""
    # Hole Scheduled Transaction
    scheduled = ScheduledTransaction.objects.get(pk=pk)

    # Berechtigungsprüfung: Robert darf nur seine eigenen bearbeiten
    if request.user.username == 'robert' and scheduled.target_table != 'robert':
        messages.error(request, 'Du darfst nur deine eigenen Scheduled Transactions bearbeiten.')
        return redirect('finance:scheduled_transactions')

    if request.method == 'POST':
        try:
            # Payee holen oder erstellen
            payee_name = request.POST.get('payee').strip()
            payee, _ = DimPayee.objects.get_or_create(payee=payee_name)

            # Betrag und Typ
            amount = Decimal(request.POST.get('amount'))
            transaction_type = request.POST.get('transaction_type')

            # Update Felder
            # Target Table: Für Robert immer 'robert', sonst aus Form
            if request.user.username == 'robert':
                scheduled.target_table = 'robert'
            else:
                scheduled.target_table = request.POST.get('target_table', 'sigi')

            scheduled.account_id = request.POST.get('account')
            scheduled.flag_id = request.POST.get('flag') or None
            scheduled.payee = payee
            scheduled.category_id = request.POST.get('category')
            scheduled.memo = request.POST.get('memo', '')
            scheduled.outflow = amount if transaction_type == 'outflow' else None
            scheduled.inflow = amount if transaction_type == 'inflow' else None
            scheduled.frequency = request.POST.get('frequency')
            scheduled.start_date = request.POST.get('start_date')
            scheduled.end_date = request.POST.get('end_date') or None
            scheduled.next_execution_date = request.POST.get('next_execution_date')

            scheduled.save()

            messages.success(request, 'Scheduled Transaction aktualisiert!')
            return redirect('finance:scheduled_transactions')

        except Exception as e:
            messages.error(request, f'Fehler beim Aktualisieren: {str(e)}')

    # Daten für Formular
    # Robert sieht nur Roberts Account (ID 18)
    if request.user.username == 'robert':
        accounts = DimAccount.objects.filter(id=18)
    else:
        accounts = DimAccount.objects.all()

    flags = DimFlag.objects.all()
    payees = DimPayee.objects.all().order_by('payee')
    category_groups = DimCategoryGroup.objects.all().order_by('category_group')
    categories = DimCategory.objects.select_related('categorygroup').all()

    context = {
        'scheduled': scheduled,
        'accounts': accounts,
        'flags': flags,
        'payees': payees,
        'category_groups': category_groups,
        'categories': categories,
        'is_edit': True,
        'is_robert': request.user.username == 'robert',
    }

    return render(request, 'finance/scheduled_transaction_form.html', context)


@login_required
def scheduled_transaction_toggle(request, pk):
    """Toggle Active/Inactive Status"""
    if request.method != 'POST':
        return redirect('finance:scheduled_transactions')

    scheduled = ScheduledTransaction.objects.get(pk=pk)

    # Berechtigungsprüfung: Robert darf nur seine eigenen togglen
    if request.user.username == 'robert' and scheduled.target_table != 'robert':
        messages.error(request, 'Du darfst nur deine eigenen Scheduled Transactions verwalten.')
        return redirect('finance:scheduled_transactions')

    scheduled.is_active = not scheduled.is_active
    scheduled.save()

    status = 'aktiviert' if scheduled.is_active else 'deaktiviert'
    messages.success(request, f'Scheduled Transaction {status}: {scheduled.payee}')

    return redirect('finance:scheduled_transactions')


@login_required
def scheduled_transaction_delete(request, pk):
    """Scheduled Transaction löschen"""
    if request.method != 'POST':
        return redirect('finance:scheduled_transactions')

    try:
        scheduled = ScheduledTransaction.objects.get(pk=pk)

        # Berechtigungsprüfung: Robert darf nur seine eigenen löschen
        if request.user.username == 'robert' and scheduled.target_table != 'robert':
            messages.error(request, 'Du darfst nur deine eigenen Scheduled Transactions löschen.')
            return redirect('finance:scheduled_transactions')

        payee_name = str(scheduled.payee)
        scheduled.delete()

        messages.success(request, f'Scheduled Transaction gelöscht: {payee_name}')
    except Exception as e:
        messages.error(request, f'Fehler beim Löschen: {str(e)}')

    return redirect('finance:scheduled_transactions')


@login_required
def scheduled_transaction_execute_now(request, pk):
    """Führt eine Scheduled Transaction sofort aus"""
    if request.method != 'POST':
        return redirect('finance:scheduled_transactions')

    try:
        scheduled = ScheduledTransaction.objects.get(pk=pk)

        # Berechtigungsprüfung: Robert darf nur seine eigenen ausführen
        if request.user.username == 'robert' and scheduled.target_table != 'robert':
            messages.error(request, 'Du darfst nur deine eigenen Scheduled Transactions ausführen.')
            return redirect('finance:scheduled_transactions')

        transaction = scheduled.execute()

        if transaction:
            messages.success(
                request,
                f'Transaktion erstellt: {scheduled.payee} - '
                f'€{scheduled.outflow or scheduled.inflow}'
            )
        else:
            messages.warning(request, 'Transaktion konnte nicht erstellt werden.')

    except Exception as e:
        messages.error(request, f'Fehler: {str(e)}')

    return redirect('finance:scheduled_transactions')


@csrf_exempt
@require_POST
def process_scheduled_transactions(request):
    """
    Endpoint für Cron-Job um geplante Transaktionen zu verarbeiten
    Wird von cron-job.org aufgerufen
    """
    # Token-Authentifizierung
    provided_token = request.headers.get('X-Cron-Token')

    if not provided_token or provided_token != settings.CRON_SECRET_TOKEN:
        logger.warning('Unauthorized cron job attempt')
        return HttpResponseForbidden('Invalid token')

    today = date.today()

    # Hole alle aktiven scheduled transactions, die heute oder früher fällig sind
    due_transactions = ScheduledTransaction.objects.filter(
        is_active=True,
        next_execution_date__lte=today
    )

    executed_count = 0
    failed_count = 0
    results = []

    for scheduled_tx in due_transactions:
        try:
            transaction = scheduled_tx.execute()
            if transaction:
                executed_count += 1
                results.append(f"✓ {scheduled_tx.payee} - €{scheduled_tx.outflow or scheduled_tx.inflow}")
                logger.info(f'Executed scheduled transaction: {scheduled_tx}')
            else:
                # Transaction war nicht fällig oder deaktiviert
                if not scheduled_tx.is_active:
                    results.append(f"○ {scheduled_tx.payee} (deactivated/expired)")
        except Exception as e:
            failed_count += 1
            results.append(f"✗ {scheduled_tx.payee}: {str(e)}")
            logger.error(f'Failed to execute scheduled transaction {scheduled_tx}: {str(e)}')

    response_text = f"""Scheduled Transactions Processing Complete

Date: {today}
Executed: {executed_count}
Failed: {failed_count}
Total processed: {len(due_transactions)}

Details:
{chr(10).join(results) if results else 'No transactions due'}
"""

    logger.info(f'Cron job completed: {executed_count} executed, {failed_count} failed')

    return HttpResponse(response_text, content_type='text/plain')


@login_required
@require_POST
def analyze_receipt_image(request):
    """
    API Endpoint: Analysiert hochgeladenes Rechnungsbild
    """
    if 'receipt_image' not in request.FILES:
        return JsonResponse({
            'success': False,
            'error': 'Kein Bild hochgeladen'
        })

    try:
        image_file = request.FILES['receipt_image']
        image_bytes = image_file.read()

        # Größenlimit prüfen (z.B. 10MB)
        if len(image_bytes) > 10 * 1024 * 1024:
            return JsonResponse({
                'success': False,
                'error': 'Bild zu groß (max. 10MB)'
            })

        # Analysiere mit KI
        analyzer = ReceiptAnalyzer()
        result = analyzer.analyze_receipt(image_bytes)

        if not result['success']:
            return JsonResponse(result)

        # Finde passende Kategorie
        all_categories = DimCategory.objects.select_related('categorygroup').all()
        suggested_category = analyzer.suggest_category(
            result['category_suggestion'],
            all_categories
        )

        # Formatiere Antwort
        response = {
            'success': True,
            'data': {
                'date': result['date'].strftime('%Y-%m-%d'),
                'payee': result['payee'],
                'amount': str(result['amount']),
                'memo': result['memo'],
                'category_id': suggested_category.id if suggested_category else None,
                'category_name': suggested_category.category if suggested_category else None,
                'categorygroup_id': suggested_category.categorygroup.id if suggested_category else None,
                'categorygroup_name': suggested_category.categorygroup.category_group if suggested_category else None,
                'category_suggestion_text': result['category_suggestion'],
                'currency': result.get('currency', 'EUR')
            }
        }

        return JsonResponse(response)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Fehler bei der Verarbeitung: {str(e)}'
        })


@login_required
def analyze_receipt_page(request):
    """
    Separate Seite für Receipt Upload und Analyse
    """
    if request.method == 'POST' and 'confirm_transaction' in request.POST:
        # User hat analysierte Daten bestätigt und möchte speichern
        form = TransactionForm(request.POST, user=request.user)
        if form.is_valid():
            transaction = form.save()
            messages.success(request, 'Transaktion erfolgreich gespeichert!')
            return redirect('finance:add_transaction')
        else:
            messages.error(request, 'Fehler beim Speichern der Transaktion')

    context = {
        'accounts': DimAccount.objects.all().order_by('account'),
        'flags': DimFlag.objects.all(),
        'payees': DimPayee.objects.all().order_by('payee'),
        'category_groups': DimCategoryGroup.objects.all().order_by('category_group'),
        'categories': DimCategory.objects.select_related('categorygroup').all(),
        'is_robert': request.user.username == 'robert',
    }

    return render(request, 'finance/receipt_upload.html', context)


@login_required
@require_POST
def update_transaction_date(request, pk):
    """Aktualisiert nur das Datum einer Transaktion"""

    try:
        # Hole Transaktion aus beiden Tabellen
        transaction = None
        is_robert_transaction = False

        try:
            transaction = FactTransactionsRobert.objects.get(pk=pk)
            is_robert_transaction = True
        except FactTransactionsRobert.DoesNotExist:
            pass

        if not transaction:
            try:
                transaction = FactTransactionsSigi.objects.get(pk=pk)
            except FactTransactionsSigi.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Transaktion nicht gefunden'
                }, status=404)

        # Berechtigungsprüfung
        if request.user.username == 'robert' and not is_robert_transaction:
            return JsonResponse({
                'success': False,
                'error': 'Keine Berechtigung'
            }, status=403)

        if request.user.username != 'robert' and is_robert_transaction:
            return JsonResponse({
                'success': False,
                'error': 'Keine Berechtigung'
            }, status=403)

        # Neues Datum aus Request holen
        data = json.loads(request.body)
        new_date_str = data.get('date')

        if not new_date_str:
            return JsonResponse({
                'success': False,
                'error': 'Kein Datum angegeben'
            }, status=400)

        # Datum parsen
        from datetime import datetime
        new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()

        # Datum aktualisieren
        old_date = transaction.date
        transaction.date = new_date
        transaction.save()

        return JsonResponse({
            'success': True,
            'message': f'Datum geändert von {old_date.strftime("%d.%m.%Y")} auf {new_date.strftime("%d.%m.%Y")}',
            'new_date': new_date.strftime('%d.%m.%Y')
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_POST
def create_transaction_inline(request):
    """Erstellt eine neue Transaktion via AJAX (Inline-Add)"""
    try:
        data = json.loads(request.body)

        # Validierung
        required_fields = ['date', 'payee', 'category', 'amount', 'transaction_type']
        for field in required_fields:
            if not data.get(field):
                return JsonResponse({
                    'success': False,
                    'error': f'Pflichtfeld fehlt: {field}'
                }, status=400)

        # Payee holen oder erstellen
        payee_name = data['payee'].strip()
        try:
            payee = DimPayee.objects.get(payee__iexact=payee_name)
        except DimPayee.DoesNotExist:
            # Neuen Payee erstellen
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO finance.dim_payee (payee, payee_type) VALUES (%s, %s) RETURNING id",
                    [payee_name, None]
                )
                payee_id = cursor.fetchone()[0]
            payee = DimPayee.objects.get(id=payee_id)

        # Betrag aufteilen
        amount = Decimal(data['amount'])
        transaction_type = data['transaction_type']

        outflow = amount if transaction_type == 'outflow' else Decimal('0')
        inflow = amount if transaction_type == 'inflow' else Decimal('0')

        # Account bestimmen
        account_id = data.get('account')
        if not account_id:
            # Für Robert: Standard Account (ID 18)
            if request.user.username == 'robert':
                account_id = 18
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Konto muss ausgewählt werden'
                }, status=400)

        # Flag (optional)
        flag_id = data.get('flag') or None

        # Entscheide Zieltabelle
        # Robert (Account 18) → Robert-Tabelle, sonst Sigi
        if int(account_id) == 18 or request.user.username == 'robert':
            transaction = FactTransactionsRobert.objects.create(
                account_id=account_id,
                flag_id=flag_id,
                date=data['date'],
                payee=payee,
                category_id=data['category'],
                memo=data.get('memo', ''),
                outflow=outflow,
                inflow=inflow,
            )
            table = 'robert'
        else:
            transaction = FactTransactionsSigi.objects.create(
                account_id=account_id,
                flag_id=flag_id,
                date=data['date'],
                payee=payee,
                category_id=data['category'],
                memo=data.get('memo', ''),
                outflow=outflow,
                inflow=inflow,
            )
            table = 'sigi'

        # Hole die erstellte Transaktion mit allen Relationen
        if table == 'robert':
            transaction = FactTransactionsRobert.objects.select_related(
                'account', 'payee', 'category', 'category__categorygroup', 'flag'
            ).get(pk=transaction.id)
        else:
            transaction = FactTransactionsSigi.objects.select_related(
                'account', 'payee', 'category', 'category__categorygroup', 'flag'
            ).get(pk=transaction.id)

        # Formatiere Antwort
        return JsonResponse({
            'success': True,
            'message': f'Transaktion erstellt: {transaction.payee}',
            'transaction': {
                'id': transaction.id,
                'date': transaction.date.strftime('%d.%m.%Y'),
                'date_iso': transaction.date.strftime('%Y-%m-%d'),
                'account': transaction.account.account if transaction.account else '-',
                'payee': transaction.payee.payee if transaction.payee else '-',
                'category': transaction.category.category if transaction.category else '-',
                'categorygroup': transaction.category.categorygroup.category_group if transaction.category and transaction.category.categorygroup else '-',
                'memo': transaction.memo or '-',
                'outflow': str(transaction.outflow) if transaction.outflow else None,
                'inflow': str(transaction.inflow) if transaction.inflow else None,
                'table': table
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Fehler beim Erstellen: {str(e)}'
        }, status=500)


@login_required
def adjust_investments(request):
    """Ansicht zum Anpassen von Investment-Kontenständen mit Kursschwankungstransaktionen"""
    # Robert hat keinen Zugriff
    if request.user.username == 'robert':
        messages.warning(request, 'Du hast keine Berechtigung für diese Seite.')
        return redirect('finance:household_transactions')

    # Aktuelles Datum
    today = date.today()

    # Hole alle relevanten Accounts mit ihren aktuellen Ständen
    accounts_data = []

    # MidtermInvest Accounts
    midterm_accounts = [
        {'name': 'ETF', 'account_names': ['ETF'], 'input_type': 'single'},
        {'name': 'Top4 Fonds & Green Invest', 'account_names': ['Top4 Fonds & Green Invest'], 'input_type': 'single'},
        {'name': 'Krypto & Aktien', 'account_names': ['Krypto & Aktien'], 'input_type': 'multi',
         'fields': [
             {'label': 'Krypto', 'multiplier': 1},
             {'label': 'Aktien', 'multiplier': 1},
             {'label': 'Indizes', 'multiplier': 1},
             {'label': 'Cash', 'multiplier': 1},
             {'label': 'Rohstoffe', 'multiplier': 1}
         ]},
        {'name': 'Goldanlage', 'account_names': ['Goldanlage'], 'input_type': 'gold',
         'fields': [
             {'label': '€ je oz', 'multiplier': 7},  # ← 7 Unzen
             {'label': '€ je 1/25 oz', 'multiplier': 1}  # ← Bereits Gesamtwert
         ]},
    ]

    # LongtermInvest Accounts
    longterm_accounts = [
        {'name': 'Pensionskonto', 'account_names': ['Pensionskonto', 'BVK'], 'input_type': 'single'},
        {'name': 'APK Vorsorgekasse (Energie)', 'account_names': ['APK Vorsorgekasse'], 'input_type': 'single'},
        {'name': 'Vorsorgekasse (Legero)', 'account_names': ['Vorsorgekasse'], 'input_type': 'single'},
    ]

    def safe_field_name(name):
        """Konvertiert Namen in sichere Feldnamen"""
        import re
        safe = re.sub(r'[^\w\s-]', '', name)
        safe = re.sub(r'[-\s]+', '_', safe)
        return safe.lower()

    # Lade aktuelle Kontostände
    for category in [('MidtermInvest', midterm_accounts), ('LongtermInvest', longterm_accounts)]:
        category_name, account_list = category

        for acc_config in account_list:
            # Finde Account(s) in DB
            accounts = DimAccount.objects.filter(
                account__in=acc_config['account_names']
            )

            if not accounts.exists():
                continue

            # Berechne Gesamtsaldo über alle passenden Accounts
            total_balance = Decimal('0')
            account_ids = []

            for account in accounts:
                balance = calculate_account_balance(account.id, today)
                total_balance += balance
                account_ids.append(account.id)

            # Generiere sichere Feldnamen
            field_prefix = safe_field_name(acc_config['name'])

            # Verarbeite Felder für multi/gold types
            processed_fields = []
            if acc_config.get('fields'):
                for field in acc_config['fields']:
                    # field ist jetzt ein Dict mit 'label' und 'multiplier'
                    label = field['label'] if isinstance(field, dict) else field
                    multiplier = field.get('multiplier', 1) if isinstance(field, dict) else 1

                    processed_fields.append({
                        'label': label,
                        'name': safe_field_name(label),
                        'multiplier': multiplier  # ← NEU
                    })

            accounts_data.append({
                'category': category_name,
                'name': acc_config['name'],
                'field_prefix': field_prefix,
                'account_ids': account_ids,
                'current_balance': total_balance,
                'input_type': acc_config['input_type'],
                'fields': processed_fields,
            })

    # POST: Erstelle Kursschwankungstransaktionen
    if request.method == 'POST':
        try:
            # Hole oder erstelle Kursschwankung Payee
            kursschwankung_payee, _ = DimPayee.objects.get_or_create(
                payee='Kursschwankung',
                defaults={'payee_type': 'kursschwankung'}
            )

            # Zähler für Statistik
            created_count = 0
            total_adjustment = Decimal('0')

            # Verarbeite jeden Account
            for acc_data in accounts_data:
                field_prefix = acc_data['field_prefix']

                # Berechne neuen Saldo basierend auf Input-Type
                new_balance = Decimal('0')

                if acc_data['input_type'] == 'single':
                    value = request.POST.get(f'{field_prefix}_value', '').strip()
                    if value:
                        new_balance = Decimal(value)

                elif acc_data['input_type'] in ['multi', 'gold']:
                    # Summiere alle Felder MIT Multiplikatoren ← NEU
                    for field in acc_data['fields']:
                        field_name = f'{field_prefix}_{field["name"]}'
                        value = request.POST.get(field_name, '').strip()
                        if value:
                            # Multipliziere Wert mit Multiplikator
                            new_balance += Decimal(value) * Decimal(field['multiplier'])

                # Berechne Differenz
                difference = new_balance - acc_data['current_balance']

                # Erstelle Transaktion nur wenn Differenz != 0
                if difference != 0:
                    # Für jeden Account-ID eine Transaktion erstellen
                    for account_id in acc_data['account_ids']:
                        # Differenz gleichmäßig auf alle Accounts verteilen (falls mehrere)
                        adjusted_diff = difference / len(acc_data['account_ids'])

                        if adjusted_diff > 0:
                            # Positive Differenz = Inflow
                            FactTransactionsSigi.objects.create(
                                account_id=account_id,
                                date=today,
                                payee=kursschwankung_payee,
                                category_id=None,
                                memo=f'Kursschwankung {acc_data["name"]} - Anpassung auf €{new_balance}',
                                outflow=Decimal('0'),
                                inflow=adjusted_diff,
                            )
                        else:
                            # Negative Differenz = Outflow
                            FactTransactionsSigi.objects.create(
                                account_id=account_id,
                                date=today,
                                payee=kursschwankung_payee,
                                category_id=None,
                                memo=f'Kursschwankung {acc_data["name"]} - Anpassung auf €{new_balance}',
                                outflow=abs(adjusted_diff),
                                inflow=Decimal('0'),
                            )

                        created_count += 1
                        total_adjustment += adjusted_diff

            if created_count > 0:
                messages.success(
                    request,
                    f'{created_count} Kursschwankungstransaktion(en) erstellt. '
                    f'Gesamtanpassung: €{total_adjustment:+,.2f}'
                )
            else:
                messages.info(request, 'Keine Anpassungen notwendig (alle Differenzen = 0)')

            return redirect('finance:adjust_investments')

        except Exception as e:
            messages.error(request, f'Fehler beim Erstellen der Transaktionen: {str(e)}')

    context = {
        'accounts_data': accounts_data,
        'today': today,
    }

    return render(request, 'finance/adjust_investments.html', context)


@login_required
def api_spending_trend(request):
    """API: Historische Ausgaben und Einnahmen über alle Monate für Trendlinie"""
    if request.user.username == 'robert':
        return JsonResponse({'error': 'Keine Berechtigung'}, status=403)

    # Ausgaben: Alle Transaktionen außer Ready to Assign, Transfers, etc.
    monthly_spending = FactTransactionsSigi.objects.exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).exclude(
        category_id=1  # Ready to Assign
    ).exclude(
        category__categorygroup__category_group__iexact='Inflow'
    ).exclude(
        category__categorygroup__category_group__iexact='Longterm Savings'
    ).exclude(
        category__categorygroup__category_group__iexact='NoCategory'
    ).annotate(
        month=TruncMonth('date')
    ).values('month').annotate(
        outflow=Sum('outflow'),
        inflow=Sum('inflow')
    ).order_by('month')

    # Einnahmen: Nur Ready to Assign (category_id=1)
    monthly_income = FactTransactionsSigi.objects.exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).filter(
        category_id=1  # Ready to Assign
    ).annotate(
        month=TruncMonth('date')
    ).values('month').annotate(
        total_inflow=Sum('inflow')
    ).order_by('month')

    # Erstelle Dictionaries für einfacheren Zugriff
    income_by_month = {item['month']: float(item['total_inflow'] or 0) for item in monthly_income}

    labels = []
    spending_data = []
    income_data = []

    for item in monthly_spending:
        month = item['month']

        # Formatiere Label als "Jan 2023"
        labels.append(month.strftime('%b %Y'))

        # Netto-Ausgaben (Outflow - Inflow)
        outflow = float(item['outflow'] or 0)
        inflow = float(item['inflow'] or 0)
        net_spending = outflow - inflow
        spending_data.append(net_spending)

        # Einnahmen für diesen Monat
        income_data.append(income_by_month.get(month, 0))

    # Berechne Trendlinie nur für Ausgaben (lineare Regression)
    if len(spending_data) >= 2:
        x = np.arange(len(spending_data))
        y = np.array(spending_data)

        # Lineare Regression: y = mx + b
        m, b = np.polyfit(x, y, 1)
        trend_data = [m * i + b for i in x]
    else:
        trend_data = spending_data

    return JsonResponse({
        'labels': labels,
        'spending': spending_data,  # Geändert von 'data' zu 'spending'
        'income': income_data,  # NEU
        'trend': trend_data
    })


@login_required
def api_asset_history(request):
    """API: Historische Vermögensentwicklung über alle Kategorien"""
    if request.user.username == 'robert':
        return JsonResponse({'error': 'Keine Berechtigung'}, status=403)

    from dateutil.relativedelta import relativedelta

    # Zeitraum: Vom ersten Datensatz bis heute
    end_date = datetime.now().date()
    if end_date.month == 12:
        end_date = end_date.replace(day=31)
    else:
        next_month = end_date.replace(month=end_date.month + 1, day=1)
        end_date = next_month - timedelta(days=1)

    # Finde früheste Transaktion
    earliest_sigi = FactTransactionsSigi.objects.order_by('date').first()
    earliest_robert = FactTransactionsRobert.objects.order_by('date').first()

    earliest_dates = []
    if earliest_sigi:
        earliest_dates.append(earliest_sigi.date)
    if earliest_robert:
        earliest_dates.append(earliest_robert.date)

    if not earliest_dates:
        # Keine Transaktionen, Fallback auf letztes Jahr
        start_date = end_date - relativedelta(months=12)
    else:
        start_date = min(earliest_dates)
        # Setze auf ersten Tag des Monats
        start_date = start_date.replace(day=1)

    # Generiere Liste aller Monate
    months = []
    current = start_date
    while current <= end_date:
        # Letzter Tag des Monats
        if current.month == 12:
            month_end = current.replace(day=31)
        else:
            next_month = current.replace(month=current.month + 1, day=1)
            month_end = next_month - timedelta(days=1)

        months.append(month_end)
        current = current + relativedelta(months=1)

    # Hole alle Accounts
    accounts = DimAccount.objects.select_related('accounttype').all()

    # Datenstruktur für Kategorien (in fester Reihenfolge für Stacking)
    category_order = ['Cash', 'Credit', 'MidtermInvest', 'LongtermInvest']
    category_data = {cat: [] for cat in category_order}

    labels = []

    # Für jeden Monat: Berechne Kontostände pro Kategorie
    for month_end in months:
        labels.append(month_end.strftime('%b %Y'))

        # Reset für diesen Monat
        monthly_totals = {cat: Decimal('0') for cat in category_order}

        for account in accounts:
            # Kategorie bestimmen
            if account.accounttype and account.accounttype.accounttypes:
                category_name = account.accounttype.accounttypes
            else:
                category_name = 'Sonstige'

            # Nur relevante Kategorien
            if category_name not in monthly_totals:
                continue

            # Berechne Kontostand für diesen Monat
            balance = calculate_account_balance(account.id, month_end)
            monthly_totals[category_name] += balance

        # Füge zu category_data hinzu
        for cat_name in category_order:
            category_data[cat_name].append(float(monthly_totals[cat_name]))

    # Berechne Gesamtwert (Summe aller Kategorien)
    total_data = []
    for i in range(len(labels)):
        total = sum(category_data[cat][i] for cat in category_order)
        total_data.append(total)

    # Erstelle datasets mit zentralen Farben
    datasets = []

    for cat_name in reversed(category_order):
        if cat_name in CATEGORY_COLORS:
            cat_config = CATEGORY_COLORS[cat_name]
            r, g, b = cat_config['rgb']

            # Hole Display-Name aus CATEGORY_CONFIG
            display_name = CATEGORY_CONFIG.get(cat_name, {}).get('display_name', cat_name)

            datasets.append({
                'label': display_name,
                'data': category_data[cat_name],
                'borderColor': f'rgb({r}, {g}, {b})',
                'backgroundColor': f'rgba({r}, {g}, {b}, 0.2)',
                'borderWidth': 2,
                'tension': 0.4,
                'fill': True,
                'pointRadius': 0,
                'pointHoverRadius': 5,
                'pointHoverBackgroundColor': f'rgb({r}, {g}, {b})',
            })

    # Gesamtwert als separate dicke Linie (NICHT gestackt)
    datasets.append({
        'label': 'Gesamt',
        'data': total_data,
        'borderColor': 'rgb(255, 206, 86)',
        'backgroundColor': 'transparent',
        'borderWidth': 3,
        'tension': 0.4,
        'fill': False,
        'pointRadius': 3,
        'pointHoverRadius': 6,
        'borderDash': [5, 5],
        'stack': 'total',
    })

    return JsonResponse({
        'labels': labels,
        'datasets': datasets
    })


@login_required
def api_asset_category_details(request):
    """API: Detaillierte Vermögensentwicklung pro Kategorie mit einzelnen Accounts"""
    if request.user.username == 'robert':
        return JsonResponse({'error': 'Keine Berechtigung'}, status=403)

    from dateutil.relativedelta import relativedelta

    # Zeitraum: Vom ersten Datensatz bis heute
    end_date = datetime.now().date()
    if end_date.month == 12:
        end_date = end_date.replace(day=31)
    else:
        next_month = end_date.replace(month=end_date.month + 1, day=1)
        end_date = next_month - timedelta(days=1)

    # Finde früheste Transaktion
    earliest_sigi = FactTransactionsSigi.objects.order_by('date').first()
    earliest_robert = FactTransactionsRobert.objects.order_by('date').first()

    earliest_dates = []
    if earliest_sigi:
        earliest_dates.append(earliest_sigi.date)
    if earliest_robert:
        earliest_dates.append(earliest_robert.date)

    if not earliest_dates:
        # Keine Transaktionen, Fallback auf letztes Jahr
        start_date = end_date - relativedelta(months=12)
    else:
        start_date = min(earliest_dates)
        # Setze auf ersten Tag des Monats
        start_date = start_date.replace(day=1)

    # Generiere Liste aller Monate
    months = []
    current = start_date
    while current <= end_date:
        if current.month == 12:
            month_end = current.replace(day=31)
        else:
            next_month = current.replace(month=current.month + 1, day=1)
            month_end = next_month - timedelta(days=1)

        months.append(month_end)
        current = current + relativedelta(months=1)

    labels = [month.strftime('%b %Y') for month in months]

    # Hole alle Accounts gruppiert nach Kategorie
    accounts = DimAccount.objects.select_related('accounttype').all()

    # Gruppiere Accounts nach Kategorie
    category_accounts = {
        'Cash': [],
        'MidtermInvest': [],
        'LongtermInvest': []
    }

    for account in accounts:
        if account.accounttype and account.accounttype.accounttypes:
            category_name = account.accounttype.accounttypes
            if category_name in category_accounts:
                category_accounts[category_name].append(account)

    # Generiere Farbpaletten basierend auf den Hauptfarben
    color_palettes = {}
    for category_name in category_accounts.keys():
        if category_name in CATEGORY_COLORS:
            rgb = CATEGORY_COLORS[category_name]['rgb']
            # Generiere 8 Schattierungen (sollte für die meisten Accounts reichen)
            color_palettes[category_name] = generate_color_shades(rgb, num_shades=8)

    # Erstelle Datasets für jede Kategorie
    result = {}

    for category_name, accounts_list in category_accounts.items():
        if not accounts_list:
            continue

        datasets = []
        colors = color_palettes.get(category_name, [])

        # Sortiere Accounts nach Namen für konsistente Darstellung
        accounts_list.sort(key=lambda x: x.account)

        # Für jeden Account: Berechne historische Daten
        for idx, account in enumerate(accounts_list):
            account_data = []

            for month_end in months:
                balance = calculate_account_balance(account.id, month_end)
                account_data.append(float(balance))

            # Überspringe Accounts die immer 0 sind
            if all(val == 0 for val in account_data):
                continue

            # Wähle Farbe aus den Schattierungen
            color = colors[idx % len(colors)] if colors else {
                'border': f'rgb({(idx * 50) % 255}, {(idx * 80) % 255}, {(idx * 120) % 255})',
                'fill': f'rgba({(idx * 50) % 255}, {(idx * 80) % 255}, {(idx * 120) % 255}, 0.5)'
            }

            datasets.append({
                'label': account.account,
                'data': account_data,
                'borderColor': color['border'],
                'backgroundColor': color['fill'],
                'borderWidth': 2,
                'tension': 0.4,
                'fill': True,
                'pointRadius': 0,
                'pointHoverRadius': 4,
                'pointHoverBackgroundColor': color['border'],
            })

        # Reverse für korrektes Stacking
        datasets.reverse()

        result[category_name] = {
            'labels': labels,
            'datasets': datasets
        }

    return JsonResponse(result)


@login_required
def api_income_payees(request):
    """API: Einnahmen nach Payee für gestapeltes Balkendiagramm"""
    if request.user.username == 'robert':
        return JsonResponse({'error': 'Keine Berechtigung'}, status=403)

    year = request.GET.get('year', datetime.now().year)

    from django.db.models import Q
    from collections import defaultdict

    # Hole alle relevanten Transaktionen ohne Gruppierung
    transactions = FactTransactionsSigi.objects.filter(
        date__year=year
    ).filter(
        Q(category_id=1) |  # Ready to Assign
        Q(payee__payee__icontains='Robert', inflow__gt=0)  # Robert Inflows
    ).exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).select_related('payee')

    # Manuelle Gruppierung mit defaultdict
    payees_data = defaultdict(lambda: defaultdict(float))
    all_months = set()

    for trans in transactions:
        # Extrahiere Monat (als datetime Objekt)
        month = trans.date.replace(day=1)
        all_months.add(month)

        # Bestimme Payee-Name (fasse alle Robert zusammen)
        original_payee = trans.payee.payee if trans.payee else 'Unbekannt'

        if 'robert' in original_payee.lower():
            payee_name = 'Robert (gesamt)'
        else:
            payee_name = original_payee

        # Summiere Inflow für diesen Payee und Monat
        payees_data[payee_name][month] += float(trans.inflow or 0)

    # Sortiere Monate
    sorted_months = sorted(list(all_months))
    labels = [month.strftime('%b %Y') for month in sorted_months]

    # Erstelle Datasets für jeden Payee
    datasets = []
    colors = generate_distinct_colors(len(payees_data))

    for idx, (payee, month_data) in enumerate(sorted(payees_data.items())):
        # Erstelle Daten-Array in richtiger Reihenfolge
        data = [month_data.get(month, 0) for month in sorted_months]

        datasets.append({
            'label': payee,
            'data': data,
            'backgroundColor': colors[idx]['fill'],
            'borderColor': colors[idx]['border'],
            'borderWidth': 1
        })

    return JsonResponse({
        'labels': labels,
        'datasets': datasets
    })


def generate_distinct_colors(num_colors):
    """Generiere unterscheidbare Farben für Payees"""
    # Vordefinierte Farbpalette für gute Unterscheidbarkeit
    base_colors = [
        (255, 99, 132),  # Rot
        (54, 162, 235),  # Blau
        (255, 206, 86),  # Gelb
        (75, 192, 192),  # Türkis
        (153, 102, 255),  # Lila
        (255, 159, 64),  # Orange
        (199, 199, 199),  # Grau
        (83, 102, 255),  # Indigo
        (255, 99, 255),  # Pink
        (99, 255, 132),  # Grün
        (255, 183, 77),  # Gold
        (77, 208, 225),  # Cyan
        (240, 98, 146),  # Rosa
        (139, 195, 74),  # Lime
        (121, 85, 72),  # Braun
    ]

    colors = []
    for i in range(num_colors):
        rgb = base_colors[i % len(base_colors)]
        colors.append({
            'border': f'rgb({rgb[0]}, {rgb[1]}, {rgb[2]})',
            'fill': f'rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, 0.7)'
        })

    return colors


# Füge diese Views zu deiner finance/views.py hinzu

@login_required
def household_dashboard(request):
    """Dashboard für Haushaltsausgaben - zeigt Visualisierungen"""
    # Verfügbare Jahre ermitteln
    sigi_base = FactTransactionsSigi.objects.filter(flag_id=5)
    robert_base = FactTransactionsRobert.objects.all()

    from django.db.models import functions
    sigi_years = sigi_base.annotate(
        year=functions.ExtractYear('date')
    ).values_list('year', flat=True).distinct()
    robert_years = robert_base.annotate(
        year=functions.ExtractYear('date')
    ).values_list('year', flat=True).distinct()
    available_years = sorted(set(sigi_years) | set(robert_years), reverse=True)

    context = {
        'available_years': available_years,
        'current_year': datetime.now().year,
    }

    return render(request, 'finance/household_dashboard.html', context)


@login_required
def api_household_monthly_spending(request):
    """API: Monatliche Haushaltsausgaben (Gestapelt nach Person)"""
    year = request.GET.get('year', datetime.now().year)
    year = int(year)

    # Sigi: Nur mit Flag "Relevant für Haushaltsbudget" (flag_id=5)
    sigi_transactions = FactTransactionsSigi.objects.filter(
        flag_id=5,
        date__year=year
    ).exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).exclude(
        category_id=1  # "Ready to Assign" ausschließen
    )

    # Robert: Alle Transaktionen
    robert_transactions = FactTransactionsRobert.objects.filter(
        date__year=year
    ).exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).exclude(
        category_id=1
    )

    # Monatliche Aggregation für Sigi
    sigi_monthly = sigi_transactions.annotate(
        month=TruncMonth('date')
    ).values('month').annotate(
        inflow=Sum('inflow'),
        outflow=Sum('outflow')
    ).order_by('month')

    # Monatliche Aggregation für Robert
    robert_monthly = robert_transactions.annotate(
        month=TruncMonth('date')
    ).values('month').annotate(
        inflow=Sum('inflow'),
        outflow=Sum('outflow')
    ).order_by('month')

    # Erstelle vollständige Monatsliste
    months_labels = [
        'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
        'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
    ]

    # Initialisiere Daten-Arrays
    sigi_data = [0] * 12
    robert_data = [0] * 12

    # Fülle Sigi-Daten
    for item in sigi_monthly:
        month_index = item['month'].month - 1
        netto = float((item['outflow'] or 0) - (item['inflow'] or 0))
        sigi_data[month_index] = netto

    # Fülle Robert-Daten
    for item in robert_monthly:
        month_index = item['month'].month - 1
        netto = float((item['outflow'] or 0) - (item['inflow'] or 0))
        robert_data[month_index] = netto

    return JsonResponse({
        'labels': months_labels,
        'datasets': [
            {
                'label': 'Robert',
                'data': robert_data,
                'backgroundColor': 'rgba(0, 176, 240, 0.8)',  # #00B0F0
                'borderColor': 'rgba(0, 176, 240, 1)',
                'borderWidth': 1
            },
            {
                'label': 'Sigi',
                'data': sigi_data,
                'backgroundColor': 'rgba(0, 242, 196, 0.8)',  # #00F2C4
                'borderColor': 'rgba(0, 242, 196, 1)',
                'borderWidth': 1
            }
        ]
    })


@login_required
def api_household_category_breakdown(request):
    """API: Ausgaben nach CategoryGroup für Tortendiagramm"""
    year = request.GET.get('year', datetime.now().year)
    year = int(year)

    # Definiere die gewünschten CategoryGroups mit Farben
    category_config = {
        2: {'name': 'Haushaltsausgaben', 'color': 'rgb(91, 155, 213)'},  # #5B9BD5
        3: {'name': 'Wohnung', 'color': 'rgb(237, 125, 49)'},  # #ED7D31
        4: {'name': 'Restaurant & Lieferservice', 'color': 'rgb(132, 151, 176)'},  # #8497B0
        5: {'name': 'Ärzte & Gesundheit', 'color': 'rgb(255, 192, 0)'},  # #FFC000
        6: {'name': 'Freizeit & Hobby & Urlaub', 'color': 'rgb(112, 173, 71)'},  # #70AD47
        7: {'name': 'Geschenke', 'color': 'rgb(68, 114, 196)'},  # #4472C4
        10: {'name': 'KFZ', 'color': 'rgb(255, 0, 102)'}  # #FF0066
    }

    # Sigi: Nur mit Flag "Relevant für Haushaltsbudget"
    sigi_transactions = FactTransactionsSigi.objects.filter(
        flag_id=5,
        date__year=year,
        outflow__gt=0
    ).exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).exclude(
        category_id=1  # "Ready to Assign"
    )

    # Robert: Alle Transaktionen
    robert_transactions = FactTransactionsRobert.objects.filter(
        date__year=year,
        outflow__gt=0
    ).exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).exclude(
        category_id=1
    )

    # Aggregiere nach CategoryGroup für Sigi
    sigi_by_group = sigi_transactions.values(
        'category__categorygroup_id',
        'category__categorygroup__category_group'
    ).annotate(
        inflow=Sum('inflow'),
        outflow=Sum('outflow')
    )

    # Aggregiere nach CategoryGroup für Robert
    robert_by_group = robert_transactions.values(
        'category__categorygroup_id',
        'category__categorygroup__category_group'
    ).annotate(
        inflow=Sum('inflow'),
        outflow=Sum('outflow')
    )

    # Kombiniere beide und berechne Netto pro CategoryGroup
    category_totals = {}

    for item in sigi_by_group:
        group_id = item['category__categorygroup_id']
        if group_id in category_config:
            netto = float((item['outflow'] or 0) - (item['inflow'] or 0))
            category_totals[group_id] = category_totals.get(group_id, 0) + netto

    for item in robert_by_group:
        group_id = item['category__categorygroup_id']
        if group_id in category_config:
            netto = float((item['outflow'] or 0) - (item['inflow'] or 0))
            category_totals[group_id] = category_totals.get(group_id, 0) + netto

    # Bereite Daten für Chart.js vor
    labels = []
    data = []
    colors = []

    for group_id in sorted(category_config.keys()):
        if group_id in category_totals and category_totals[group_id] > 0:
            labels.append(category_config[group_id]['name'])
            data.append(category_totals[group_id])
            colors.append(category_config[group_id]['color'])

    return JsonResponse({
        'labels': labels,
        'datasets': [{
            'data': data,
            'backgroundColor': colors,
            'borderColor': colors,
            'borderWidth': 1
        }]
    })


@login_required
def api_categorygroup_monthly_trend(request):
    """API: Monatliche Ausgaben-Entwicklung pro CategoryGroup mit Trendlinie"""
    group_id = request.GET.get('group_id')
    if not group_id:
        return JsonResponse({'error': 'group_id required'}, status=400)

    group_id = int(group_id)

    # Hole Daten für 2024 und 2025
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2025, 12, 31)
    current_month = datetime.now().replace(day=1)

    # Sigi: Nur mit Flag "Relevant für Haushaltsbudget"
    sigi_data = FactTransactionsSigi.objects.filter(
        flag_id=5,
        date__gte=start_date,
        date__lte=end_date,
        category__categorygroup_id=group_id
    ).exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).exclude(
        category_id=1
    ).annotate(
        month=TruncMonth('date')
    ).values('month').annotate(
        inflow=Sum('inflow'),
        outflow=Sum('outflow')
    ).order_by('month')

    # Robert: Alle Transaktionen
    robert_data = FactTransactionsRobert.objects.filter(
        date__gte=start_date,
        date__lte=end_date,
        category__categorygroup_id=group_id
    ).exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).exclude(
        category_id=1
    ).annotate(
        month=TruncMonth('date')
    ).values('month').annotate(
        inflow=Sum('inflow'),
        outflow=Sum('outflow')
    ).order_by('month')

    # Aggregiere Daten nach Monat (verwende Tuple aus Jahr und Monat als Key!)
    monthly_totals = {}

    for item in sigi_data:
        month = item['month']
        # Verwende (Jahr, Monat) als Key statt datetime-Objekt
        key = (month.year, month.month)
        netto = float((item['outflow'] or 0) - (item['inflow'] or 0))
        monthly_totals[key] = monthly_totals.get(key, 0) + netto

    for item in robert_data:
        month = item['month']
        key = (month.year, month.month)
        netto = float((item['outflow'] or 0) - (item['inflow'] or 0))
        monthly_totals[key] = monthly_totals.get(key, 0) + netto

    # Erstelle Monatsliste für 2024 und 2025 BIS ZUM AKTUELLEN MONAT
    labels = []
    data = []

    current_year = 2024
    current_month_num = 1

    # Aktuelles Jahr und Monat für Vergleich
    now = datetime.now()
    current_year_now = now.year
    current_month_now = now.month

    # GEÄNDERT: Schleife nur bis zum aktuellen Monat
    while (current_year < current_year_now) or (
            current_year == current_year_now and current_month_num <= current_month_now):
        month_date = datetime(current_year, current_month_num, 1)
        labels.append(month_date.strftime('%b %Y'))

        # Hole Wert mit (Jahr, Monat) Key
        key = (current_year, current_month_num)
        value = monthly_totals.get(key, 0)
        data.append(value)

        # Nächster Monat
        if current_month_num == 12:
            current_year += 1
            current_month_num = 1
        else:
            current_month_num += 1

    # Berechne Trendlinie (nur mit vollständigen Monaten, exkl. aktueller Monat)
    current_month_key = (now.year, now.month)

    complete_data_points = []
    complete_indices = []

    for i, value in enumerate(data):
        # Berechne Jahr und Monat für diesen Index
        year = 2024 + (i // 12)
        month = (i % 12) + 1

        # Nur vollständige Monate (nicht der aktuelle)
        if (year, month) < current_month_key:
            complete_data_points.append(value)
            complete_indices.append(i)

    # Lineare Regression für Trendlinie
    trend_data = []
    if len(complete_data_points) >= 2:
        try:
            import numpy as np
            x = np.array(complete_indices)
            y = np.array(complete_data_points)

            # Berechne Steigung und Y-Achsenabschnitt
            m, b = np.polyfit(x, y, 1)

            # Erstelle Trendlinie
            for i in range(len(data)):
                year = 2024 + (i // 12)
                month = (i % 12) + 1

                if (year, month) < current_month_key:
                    trend_data.append(float(m * i + b))
                else:
                    trend_data.append(None)
        except ImportError:
            trend_data = [None] * len(data)
    else:
        trend_data = [None] * len(data)

    return JsonResponse({
        'labels': labels,
        'data': data,
        'trend_data': trend_data
    })


@login_required
def api_categorygroup_year_comparison(request):
    """API: Monatsvergleich 2024 vs 2025 pro CategoryGroup"""
    group_id = request.GET.get('group_id')
    if not group_id:
        return JsonResponse({'error': 'group_id required'}, status=400)

    group_id = int(group_id)

    months_labels = [
        'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun',
        'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'
    ]

    data_2024 = [0] * 12
    data_2025 = [0] * 12

    # Daten für beide Jahre sammeln
    for year, data_array in [(2024, data_2024), (2025, data_2025)]:
        # Sigi
        sigi_monthly = FactTransactionsSigi.objects.filter(
            flag_id=5,
            date__year=year,
            category__categorygroup_id=group_id,
            outflow__gt=0
        ).exclude(
            payee__payee_type__in=['transfer', 'kursschwankung']
        ).exclude(
            category_id=1
        ).annotate(
            month=TruncMonth('date')
        ).values('month').annotate(
            inflow=Sum('inflow'),
            outflow=Sum('outflow')
        )

        # Robert
        robert_monthly = FactTransactionsRobert.objects.filter(
            date__year=year,
            category__categorygroup_id=group_id,
            outflow__gt=0
        ).exclude(
            payee__payee_type__in=['transfer', 'kursschwankung']
        ).exclude(
            category_id=1
        ).annotate(
            month=TruncMonth('date')
        ).values('month').annotate(
            inflow=Sum('inflow'),
            outflow=Sum('outflow')
        )

        # Fülle Daten
        for item in sigi_monthly:
            month_index = item['month'].month - 1
            netto = float((item['outflow'] or 0) - (item['inflow'] or 0))
            data_array[month_index] += netto

        for item in robert_monthly:
            month_index = item['month'].month - 1
            netto = float((item['outflow'] or 0) - (item['inflow'] or 0))
            data_array[month_index] += netto

    return JsonResponse({
        'labels': months_labels,
        'data_2024': data_2024,
        'data_2025': data_2025
    })


@login_required
def api_categorygroup_quarterly_breakdown(request):
    """API: Quartalsweise gestapelte Ausgaben nach Kategorien"""
    group_id = request.GET.get('group_id')
    if not group_id:
        return JsonResponse({'error': 'group_id required'}, status=400)

    group_id = int(group_id)

    # Hole alle Kategorien dieser CategoryGroup
    categories = DimCategory.objects.filter(
        categorygroup_id=group_id
    ).exclude(
        id=1  # "Ready to Assign"
    )

    # Definiere Quartale für 2024 und 2025
    # GEÄNDERT: Nur vollständige Quartale anzeigen
    now = datetime.now()
    current_quarter_start = datetime(now.year, ((now.month - 1) // 3) * 3 + 1, 1)

    all_quarters = [
        ('Q1 2024', datetime(2024, 1, 1), datetime(2024, 3, 31)),
        ('Q2 2024', datetime(2024, 4, 1), datetime(2024, 6, 30)),
        ('Q3 2024', datetime(2024, 7, 1), datetime(2024, 9, 30)),
        ('Q4 2024', datetime(2024, 10, 1), datetime(2024, 12, 31)),
        ('Q1 2025', datetime(2025, 1, 1), datetime(2025, 3, 31)),
        ('Q2 2025', datetime(2025, 4, 1), datetime(2025, 6, 30)),
        ('Q3 2025', datetime(2025, 7, 1), datetime(2025, 9, 30)),
        ('Q4 2025', datetime(2025, 10, 1), datetime(2025, 12, 31)),
    ]

    # Filtere nur vollständige Quartale (Start-Datum vor dem aktuellen Quartal)
    quarters = [q for q in all_quarters if q[1] < current_quarter_start]

    labels = [q[0] for q in quarters]

    # Erstelle Datasets für jede Kategorie
    datasets = []

    # Farbpalette für deutliche Unterscheidung
    colors = [
        'rgb(130, 177, 255)',  # Helles Blau
        'rgb(158, 206, 154)',  # Mintgrün
        'rgb(255, 183, 178)',  # Lachs/Koralle
        'rgb(189, 178, 255)',  # Lavendel
        'rgb(255, 218, 121)',  # Helles Gelb
        'rgb(174, 214, 241)',  # Baby Blau
        'rgb(255, 195, 160)',  # Pfirsich
        'rgb(162, 217, 206)',  # Aquamarin
        'rgb(229, 152, 155)',  # Altrosa
        'rgb(197, 202, 233)',  # Periwinkle (Blaugrau-hell)
    ]

    color_idx = 0  # Zähler für Farben (nur für Kategorien mit Daten)

    for category in categories:
        category_data = []
        has_data = False  # GEÄNDERT: Flag um zu prüfen ob Kategorie Daten hat

        for quarter_label, start_date, end_date in quarters:
            # Sigi
            sigi_total = FactTransactionsSigi.objects.filter(
                flag_id=5,
                date__gte=start_date,
                date__lte=end_date,
                category_id=category.id,
                outflow__gt=0
            ).exclude(
                payee__payee_type__in=['transfer', 'kursschwankung']
            ).aggregate(
                total_inflow=Sum('inflow'),
                total_outflow=Sum('outflow')
            )

            # Robert
            robert_total = FactTransactionsRobert.objects.filter(
                date__gte=start_date,
                date__lte=end_date,
                category_id=category.id,
                outflow__gt=0
            ).exclude(
                payee__payee_type__in=['transfer', 'kursschwankung']
            ).aggregate(
                total_inflow=Sum('inflow'),
                total_outflow=Sum('outflow')
            )

            sigi_netto = float((sigi_total['total_outflow'] or 0) - (sigi_total['total_inflow'] or 0))
            robert_netto = float((robert_total['total_outflow'] or 0) - (robert_total['total_inflow'] or 0))

            total = sigi_netto + robert_netto
            category_data.append(total)

            # GEÄNDERT: Prüfe ob mindestens ein Wert > 0
            if total > 0:
                has_data = True

        # GEÄNDERT: Nur hinzufügen wenn Kategorie tatsächlich Daten hat
        if has_data:
            # Wähle Farbe
            color = colors[color_idx % len(colors)]
            color_idx += 1  # Erhöhe nur bei tatsächlich verwendeten Farben

            datasets.append({
                'label': category.category,
                'data': category_data,
                'backgroundColor': color,
                'borderColor': color,
                'borderWidth': 1
            })

    return JsonResponse({
        'labels': labels,
        'datasets': datasets
    })


@login_required
def api_categorygroup_stats(request):
    """API: Statistiken für CategoryGroup (z.B. monthly average)"""
    group_id = request.GET.get('group_id')
    if not group_id:
        return JsonResponse({'error': 'group_id required'}, status=400)

    group_id = int(group_id)

    # Berechne Monthly Average (nur vollständige Monate)
    current_month_start = datetime.now().replace(day=1)
    start_date = datetime(2024, 1, 1)

    # Sigi
    sigi_data = FactTransactionsSigi.objects.filter(
        flag_id=5,
        date__gte=start_date,
        date__lt=current_month_start,  # Exkl. aktueller Monat
        category__categorygroup_id=group_id,
        outflow__gt=0
    ).exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).exclude(
        category_id=1
    ).annotate(
        month=TruncMonth('date')
    ).values('month').annotate(
        inflow=Sum('inflow'),
        outflow=Sum('outflow')
    )

    # Robert
    robert_data = FactTransactionsRobert.objects.filter(
        date__gte=start_date,
        date__lt=current_month_start,
        category__categorygroup_id=group_id,
        outflow__gt=0
    ).exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).exclude(
        category_id=1
    ).annotate(
        month=TruncMonth('date')
    ).values('month').annotate(
        inflow=Sum('inflow'),
        outflow=Sum('outflow')
    )

    # Aggregiere nach Monat
    monthly_totals = {}

    for item in sigi_data:
        month = item['month']
        netto = float((item['outflow'] or 0) - (item['inflow'] or 0))
        monthly_totals[month] = monthly_totals.get(month, 0) + netto

    for item in robert_data:
        month = item['month']
        netto = float((item['outflow'] or 0) - (item['inflow'] or 0))
        monthly_totals[month] = monthly_totals.get(month, 0) + netto

    # Berechne Durchschnitt
    if monthly_totals:
        total_spending = sum(monthly_totals.values())
        num_months = len(monthly_totals)
        monthly_average = total_spending / num_months if num_months > 0 else 0
    else:
        monthly_average = 0

    return JsonResponse({
        'monthly_average': round(monthly_average, 2),
        'num_months': len(monthly_totals),
        'total_spending': round(sum(monthly_totals.values()), 2) if monthly_totals else 0
    })


# ===== SUPERMARKT-BEREICH API VIEWS (KORRIGIERT) =====

@login_required
def api_supermarket_monthly_trend(request):
    """API: Monatliche Entwicklung für Supermarkt-Kategorie (id=5) mit Trendlinie - nur 2024-2025"""
    category_id = 5  # 1.4. Supermarkt

    # Zeitraum: 2024-2025, aber nur bis aktueller Monat
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2025, 12, 31)
    current_month = datetime.now().replace(day=1)

    # Sigi: Nur mit Flag "Relevant für Haushaltsbudget"
    sigi_transactions = FactTransactionsSigi.objects.filter(
        flag_id=5,
        category_id=category_id,
        date__gte=start_date,
        date__lte=end_date
    ).exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).exclude(
        category_id=1  # "Ready to Assign" ausschließen
    ).values(
        'date__year', 'date__month'
    ).annotate(
        total_outflow=Sum('outflow'),
        total_inflow=Sum('inflow')
    ).order_by('date__year', 'date__month')

    # Robert: Alle Transaktionen
    robert_transactions = FactTransactionsRobert.objects.filter(
        category_id=category_id,
        date__gte=start_date,
        date__lte=end_date
    ).exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).exclude(
        category_id=1  # "Ready to Assign" ausschließen
    ).values(
        'date__year', 'date__month'
    ).annotate(
        total_outflow=Sum('outflow'),
        total_inflow=Sum('inflow')
    ).order_by('date__year', 'date__month')

    # Kombiniere beide Datensätze - verwende (Jahr, Monat) als Key
    monthly_data = {}

    for item in sigi_transactions:
        key = (item['date__year'], item['date__month'])
        if key not in monthly_data:
            monthly_data[key] = {'outflow': 0, 'inflow': 0}
        monthly_data[key]['outflow'] += float(item['total_outflow'] or 0)
        monthly_data[key]['inflow'] += float(item['total_inflow'] or 0)

    for item in robert_transactions:
        key = (item['date__year'], item['date__month'])
        if key not in monthly_data:
            monthly_data[key] = {'outflow': 0, 'inflow': 0}
        monthly_data[key]['outflow'] += float(item['total_outflow'] or 0)
        monthly_data[key]['inflow'] += float(item['total_inflow'] or 0)

    # Erstelle Monatsliste von 2024-01 bis aktueller Monat
    labels = []
    data = []
    month_names = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

    current_year = 2024
    current_month_num = 1

    # Aktuelles Jahr und Monat für Vergleich
    now = datetime.now()
    current_year_now = now.year
    current_month_now = now.month

    # Schleife nur bis zum aktuellen Monat
    while (current_year < current_year_now) or (
            current_year == current_year_now and current_month_num <= current_month_now):

        labels.append(f"{month_names[current_month_num - 1]} {current_year}")

        # Hole Wert mit (Jahr, Monat) Key
        key = (current_year, current_month_num)
        values = monthly_data.get(key, {'outflow': 0, 'inflow': 0})

        # Netto = Outflow - Inflow
        netto = values['outflow'] - values['inflow']
        data.append(round(netto, 2))

        # Nächster Monat
        if current_month_num == 12:
            current_year += 1
            current_month_num = 1
        else:
            current_month_num += 1

    # Berechne Trendlinie (nur mit vollständigen Monaten, exkl. aktueller Monat)
    current_month_key = (now.year, now.month)

    complete_data_points = []
    complete_indices = []

    for i, value in enumerate(data):
        # Berechne Jahr und Monat für diesen Index
        year = 2024 + (i // 12)
        month = (i % 12) + 1

        # Nur vollständige Monate (nicht der aktuelle)
        if (year, month) < current_month_key:
            complete_data_points.append(value)
            complete_indices.append(i)

    # Lineare Regression für Trendlinie
    trend_data = []
    if len(complete_data_points) >= 2:
        # Berechne Trendlinie mit einfacher linearer Regression
        x = complete_indices
        y = complete_data_points
        n = len(x)

        # Berechne Durchschnitte
        x_mean = sum(x) / n
        y_mean = sum(y) / n

        # Berechne Steigung und Achsenabschnitt
        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator != 0:
            slope = numerator / denominator
            intercept = y_mean - slope * x_mean

            # Erstelle Trendlinie für alle Monate (auch aktuellen)
            for i in range(len(data)):
                year = 2024 + (i // 12)
                month = (i % 12) + 1

                if (year, month) < current_month_key:
                    # Vollständige Monate: Zeige Trendlinie
                    trend_data.append(round(slope * i + intercept, 2))
                else:
                    # Aktueller Monat: Keine Trendlinie
                    trend_data.append(None)
        else:
            trend_data = [None] * len(data)
    else:
        trend_data = [None] * len(data)

    return JsonResponse({
        'labels': labels,
        'data': data,
        'trend_data': trend_data
    })


@login_required
def api_supermarket_year_comparison(request):
    """API: Jahresvergleich 2024 vs 2025 für Supermarkt-Kategorie"""
    category_id = 5  # 1.4. Supermarkt
    years = [2024, 2025]

    comparison_data = {}

    for year in years:
        # Sigi - KORRIGIERT: Keine outflow__gt=0 Filterung
        sigi_data = FactTransactionsSigi.objects.filter(
            flag_id=5,
            category_id=category_id,
            date__year=year
        ).exclude(
            payee__payee_type__in=['transfer', 'kursschwankung']
        ).exclude(
            category_id=1
        ).values(
            'date__month'
        ).annotate(
            total_outflow=Sum('outflow'),
            total_inflow=Sum('inflow')
        )

        # Robert - KORRIGIERT: Keine outflow__gt=0 Filterung
        robert_data = FactTransactionsRobert.objects.filter(
            category_id=category_id,
            date__year=year
        ).exclude(
            payee__payee_type__in=['transfer', 'kursschwankung']
        ).exclude(
            category_id=1
        ).values(
            'date__month'
        ).annotate(
            total_outflow=Sum('outflow'),
            total_inflow=Sum('inflow')
        )

        # Kombiniere
        monthly_totals = {i: 0 for i in range(1, 13)}

        for item in sigi_data:
            month = item['date__month']
            netto = float((item['total_outflow'] or 0) - (item['total_inflow'] or 0))
            monthly_totals[month] += netto

        for item in robert_data:
            month = item['date__month']
            netto = float((item['total_outflow'] or 0) - (item['total_inflow'] or 0))
            monthly_totals[month] += netto

        comparison_data[year] = [round(monthly_totals[i], 2) for i in range(1, 13)]

    month_labels = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

    # KORRIGIERT: Farben und Reihenfolge wie bei anderen CategoryGroups
    return JsonResponse({
        'labels': month_labels,
        'datasets': [
            {
                'label': '2025',
                'data': comparison_data.get(2025, [0] * 12),
                'backgroundColor': 'rgba(52, 168, 83, 0.7)',  # Blau
                'borderColor': 'rgba(52, 168, 83, 1)',
                'borderWidth': 1
            },
            {
                'label': '2024',
                'data': comparison_data.get(2024, [0] * 12),
                'backgroundColor': 'rgba(52, 168, 83, 0.25)',  # Grau
                'borderColor': 'rgba(52, 168, 83, 1)',
                'borderWidth': 1
            }
        ]
    })


@login_required
def api_supermarket_stats(request):
    """API: Statistiken für Supermarkt-Kategorie"""
    category_id = 5  # 1.4. Supermarkt

    # Sigi - KORRIGIERT: Keine outflow__gt=0 Filterung
    sigi_data = FactTransactionsSigi.objects.filter(
        flag_id=5,
        category_id=category_id
    ).exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).exclude(
        category_id=1
    ).aggregate(
        total_outflow=Sum('outflow'),
        total_inflow=Sum('inflow'),
        earliest=Min('date')
    )

    # Robert - KORRIGIERT: Keine outflow__gt=0 Filterung
    robert_data = FactTransactionsRobert.objects.filter(
        category_id=category_id
    ).exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).exclude(
        category_id=1
    ).aggregate(
        total_outflow=Sum('outflow'),
        total_inflow=Sum('inflow'),
        earliest=Min('date')
    )

    # Kombiniere
    total_outflow = float((sigi_data['total_outflow'] or 0) + (robert_data['total_outflow'] or 0))
    total_inflow = float((sigi_data['total_inflow'] or 0) + (robert_data['total_inflow'] or 0))
    # KORRIGIERT: Netto-Ausgaben = Outflow - Inflow
    total_spending = total_outflow - total_inflow

    # Berechne Anzahl Monate
    earliest_date = min(
        sigi_data['earliest'] or datetime.now().date(),
        robert_data['earliest'] or datetime.now().date()
    )

    today = datetime.now().date()
    num_months = ((today.year - earliest_date.year) * 12 +
                  today.month - earliest_date.month + 1)

    monthly_average = total_spending / num_months if num_months > 0 else 0

    return JsonResponse({
        'total_spending': round(total_spending, 2),
        'monthly_average': round(monthly_average, 2),
        'num_months': num_months
    })


@login_required
def api_billa_combined_chart(request):
    """API: Kombiniertes Diagramm - Anzahl Billa-Einkäufe + Durchschnittliche Einkaufshöhe"""
    category_id = 5  # 1.4. Supermarkt

    # Finde alle Payees die "Billa" enthalten
    billa_payees = DimPayee.objects.filter(
        payee__icontains='Billa'
    ).exclude(
        payee_type__in=['transfer', 'kursschwankung']
    ).values_list('id', flat=True)

    # Sigi: Nur mit Flag "Relevant für Haushaltsbudget"
    # KORRIGIERT: Wir wollen alle Transaktionen (auch Inflows wie Pfandgeld)
    # Aber für die Anzahl zählen wir nur "echte Einkäufe" (mit Outflow > 0)
    sigi_transactions = FactTransactionsSigi.objects.filter(
        flag_id=5,
        category_id=category_id,
        payee_id__in=billa_payees
    ).exclude(
        Q(outflow__isnull=True) | Q(outflow=0)  # Nur echte Einkäufe zählen
    ).values(
        'date__year', 'date__month'
    ).annotate(
        count=Count('id'),
        total_outflow=Sum('outflow'),
        total_inflow=Sum('inflow')
    ).order_by('date__year', 'date__month')

    # Robert
    robert_transactions = FactTransactionsRobert.objects.filter(
        category_id=category_id,
        payee_id__in=billa_payees
    ).exclude(
        Q(outflow__isnull=True) | Q(outflow=0)  # Nur echte Einkäufe zählen
    ).values(
        'date__year', 'date__month'
    ).annotate(
        count=Count('id'),
        total_outflow=Sum('outflow'),
        total_inflow=Sum('inflow')
    ).order_by('date__year', 'date__month')

    # Kombiniere beide Datensätze
    monthly_data = {}

    for item in sigi_transactions:
        key = f"{item['date__year']}-{item['date__month']:02d}"
        if key not in monthly_data:
            monthly_data[key] = {'count': 0, 'outflow': 0, 'inflow': 0}
        monthly_data[key]['count'] += item['count']
        monthly_data[key]['outflow'] += float(item['total_outflow'] or 0)
        monthly_data[key]['inflow'] += float(item['total_inflow'] or 0)

    for item in robert_transactions:
        key = f"{item['date__year']}-{item['date__month']:02d}"
        if key not in monthly_data:
            monthly_data[key] = {'count': 0, 'outflow': 0, 'inflow': 0}
        monthly_data[key]['count'] += item['count']
        monthly_data[key]['outflow'] += float(item['total_outflow'] or 0)
        monthly_data[key]['inflow'] += float(item['total_inflow'] or 0)

    # Sortiere und erstelle Ausgabe
    sorted_data = sorted(monthly_data.items())

    labels = []
    count_data = []
    avg_data = []
    month_names = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

    for key, values in sorted_data:
        year, month = key.split('-')
        month_num = int(month)
        labels.append(f"{month_names[month_num - 1]} {year}")

        count_data.append(values['count'])

        # KORRIGIERT: Durchschnittliche NETTO-Ausgabe pro Einkauf
        netto_total = values['outflow'] - values['inflow']
        avg_purchase = netto_total / values['count'] if values['count'] > 0 else 0
        avg_data.append(round(avg_purchase, 2))

    return JsonResponse({
        'labels': labels,
        'count_data': count_data,
        'avg_data': avg_data
    })


# Füge diesen Debug-View zu finance/views.py hinzu
# WICHTIG: Stelle sicher dass Q importiert ist:
# from django.db.models import Q

@login_required
def api_supermarket_transactions_detail(request):
    """
    DEBUG: Zeigt alle Transaktionen die in Supermarkt-Berechnungen verwendet werden
    Optional: Filter nach Jahr und Monat mit ?year=2024&month=10
    """
    category_id = 5  # 1.4. Supermarkt

    # Optionale Filter
    year = request.GET.get('year')
    month = request.GET.get('month')

    # Basis-Query für Sigi
    # KORRIGIERT: Keine outflow__gt=0 Filterung - wir wollen ALLE Transaktionen
    sigi_query = FactTransactionsSigi.objects.filter(
        flag_id=5,
        category_id=category_id
    ).exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).exclude(
        category_id=1  # "Ready to Assign" ausschließen
    ).select_related('payee', 'category', 'account')

    # Basis-Query für Robert
    # KORRIGIERT: Keine outflow__gt=0 Filterung
    robert_query = FactTransactionsRobert.objects.filter(
        category_id=category_id
    ).exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).exclude(
        category_id=1  # "Ready to Assign" ausschließen
    ).select_related('payee', 'category', 'account')

    # Filter nach Jahr/Monat wenn angegeben
    if year:
        sigi_query = sigi_query.filter(date__year=int(year))
        robert_query = robert_query.filter(date__year=int(year))
    if month:
        sigi_query = sigi_query.filter(date__month=int(month))
        robert_query = robert_query.filter(date__month=int(month))

    # Sortiere nach Datum
    sigi_query = sigi_query.order_by('-date')
    robert_query = robert_query.order_by('-date')

    # Erstelle Response-Daten
    sigi_transactions = []
    for t in sigi_query:
        sigi_transactions.append({
            'id': t.id,
            'date': t.date.strftime('%Y-%m-%d'),
            'year': t.date.year,
            'month': t.date.month,
            'payee': t.payee.payee if t.payee else 'N/A',
            'category': t.category.category if t.category else 'N/A',
            'account': t.account.account if t.account else 'N/A',
            'outflow': float(t.outflow or 0),
            'inflow': float(t.inflow or 0),
            'netto': float((t.outflow or 0) - (t.inflow or 0)),
            'memo': t.memo or '',
            'source': 'Sigi'
        })

    robert_transactions = []
    for t in robert_query:
        robert_transactions.append({
            'id': t.id,
            'date': t.date.strftime('%Y-%m-%d'),
            'year': t.date.year,
            'month': t.date.month,
            'payee': t.payee.payee if t.payee else 'N/A',
            'category': t.category.category if t.category else 'N/A',
            'account': t.account.account if t.account else 'N/A',
            'outflow': float(t.outflow or 0),
            'inflow': float(t.inflow or 0),
            'netto': float((t.outflow or 0) - (t.inflow or 0)),
            'memo': t.memo or '',
            'source': 'Robert'
        })

    # Kombiniere beide Listen
    all_transactions = sigi_transactions + robert_transactions

    # Sortiere nach Datum (neueste zuerst)
    all_transactions.sort(key=lambda x: x['date'], reverse=True)

    # Berechne Statistiken
    total_sigi = sum(t['netto'] for t in sigi_transactions)
    total_robert = sum(t['netto'] for t in robert_transactions)
    total_all = total_sigi + total_robert

    # Gruppiere nach Monat
    monthly_summary = {}
    for t in all_transactions:
        key = f"{t['year']}-{t['month']:02d}"
        if key not in monthly_summary:
            monthly_summary[key] = {
                'count': 0,
                'total': 0,
                'sigi_count': 0,
                'robert_count': 0
            }
        monthly_summary[key]['count'] += 1
        monthly_summary[key]['total'] += t['netto']
        if t['source'] == 'Sigi':
            monthly_summary[key]['sigi_count'] += 1
        else:
            monthly_summary[key]['robert_count'] += 1

    return JsonResponse({
        'filters': {
            'category_id': category_id,
            'category_name': '1.4. Supermarkt',
            'year': year,
            'month': month
        },
        'statistics': {
            'total_transactions': len(all_transactions),
            'sigi_transactions': len(sigi_transactions),
            'robert_transactions': len(robert_transactions),
            'total_sigi': round(total_sigi, 2),
            'total_robert': round(total_robert, 2),
            'total_all': round(total_all, 2)
        },
        'monthly_summary': {
            k: {
                'count': v['count'],
                'total': round(v['total'], 2),
                'sigi_count': v['sigi_count'],
                'robert_count': v['robert_count']
            }
            for k, v in sorted(monthly_summary.items())
        },
        'transactions': all_transactions
    })


@login_required
def api_billa_transactions_detail(request):
    """
    DEBUG: Zeigt alle Billa-Transaktionen
    Optional: Filter nach Jahr und Monat mit ?year=2024&month=10
    """
    category_id = 5  # 1.4. Supermarkt

    # Finde alle Payees die "Billa" enthalten
    billa_payees = DimPayee.objects.filter(
        payee__icontains='Billa'
    ).exclude(
        payee_type__in=['transfer', 'kursschwankung']
    )

    billa_payee_ids = list(billa_payees.values_list('id', flat=True))
    billa_payee_names = list(billa_payees.values_list('payee', flat=True))

    # Optionale Filter
    year = request.GET.get('year')
    month = request.GET.get('month')

    # Sigi - KORRIGIERT: Nur echte Einkäufe (mit Outflow), aber inkl. Inflows für Netto-Berechnung
    sigi_query = FactTransactionsSigi.objects.filter(
        flag_id=5,
        category_id=category_id,
        payee_id__in=billa_payee_ids
    ).exclude(
        Q(outflow__isnull=True) | Q(outflow=0)  # Nur Transaktionen mit Outflow
    ).select_related('payee', 'category', 'account')

    # Robert - KORRIGIERT
    robert_query = FactTransactionsRobert.objects.filter(
        category_id=category_id,
        payee_id__in=billa_payee_ids
    ).exclude(
        Q(outflow__isnull=True) | Q(outflow=0)  # Nur Transaktionen mit Outflow
    ).select_related('payee', 'category', 'account')

    # Filter nach Jahr/Monat
    if year:
        sigi_query = sigi_query.filter(date__year=int(year))
        robert_query = robert_query.filter(date__year=int(year))
    if month:
        sigi_query = sigi_query.filter(date__month=int(month))
        robert_query = robert_query.filter(date__month=int(month))

    sigi_query = sigi_query.order_by('-date')
    robert_query = robert_query.order_by('-date')

    # Erstelle Response
    transactions = []

    for t in sigi_query:
        transactions.append({
            'id': t.id,
            'date': t.date.strftime('%Y-%m-%d'),
            'year': t.date.year,
            'month': t.date.month,
            'payee': t.payee.payee if t.payee else 'N/A',
            'outflow': float(t.outflow or 0),
            'memo': t.memo or '',
            'source': 'Sigi'
        })

    for t in robert_query:
        transactions.append({
            'id': t.id,
            'date': t.date.strftime('%Y-%m-%d'),
            'year': t.date.year,
            'month': t.date.month,
            'payee': t.payee.payee if t.payee else 'N/A',
            'outflow': float(t.outflow or 0),
            'memo': t.memo or '',
            'source': 'Robert'
        })

    transactions.sort(key=lambda x: x['date'], reverse=True)

    # Monatliche Zusammenfassung
    monthly_summary = {}
    for t in transactions:
        key = f"{t['year']}-{t['month']:02d}"
        if key not in monthly_summary:
            monthly_summary[key] = {
                'count': 0,
                'total': 0,
                'avg': 0
            }
        monthly_summary[key]['count'] += 1
        monthly_summary[key]['total'] += t['outflow']

    # Berechne Durchschnitte
    for key in monthly_summary:
        count = monthly_summary[key]['count']
        total = monthly_summary[key]['total']
        monthly_summary[key]['avg'] = round(total / count if count > 0 else 0, 2)
        monthly_summary[key]['total'] = round(total, 2)

    return JsonResponse({
        'filters': {
            'year': year,
            'month': month,
            'billa_payees': billa_payee_names
        },
        'statistics': {
            'total_transactions': len(transactions),
            'total_amount': round(sum(t['outflow'] for t in transactions), 2),
            'avg_purchase': round(sum(t['outflow'] for t in transactions) / len(transactions) if transactions else 0, 2)
        },
        'monthly_summary': {k: v for k, v in sorted(monthly_summary.items())},
        'transactions': transactions
    })


