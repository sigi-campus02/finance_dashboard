from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.db.models import Sum, Count, Q, Value, CharField
from django.db.models.functions import TruncMonth
from datetime import datetime, timedelta
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import (
    FactTransactionsSigi, FactTransactionsRobert,
    DimAccount, DimCategory, DimPayee, DimCategoryGroup
)
from collections import defaultdict
from decimal import Decimal
from .utils import get_account_category, calculate_account_balance, CATEGORY_CONFIG


def user_is_not_robert(user):
    """Prüft ob User NICHT robert ist"""
    return user.username != 'robert'


@login_required
def dashboard(request):
    """Haupt-Dashboard mit Übersicht und KPIs"""
    # Robert wird zu Transaktionen Haushalt weitergeleitet
    if request.user.username == 'robert':
        return redirect('finance:household_transactions')

    current_year = datetime.now().year
    transactions = FactTransactionsSigi.objects.filter(date__year=current_year)

    total_inflow = transactions.aggregate(Sum('inflow'))['inflow__sum'] or 0
    total_outflow = transactions.aggregate(Sum('outflow'))['outflow__sum'] or 0
    netto = total_inflow - total_outflow
    transaction_count = transactions.count()

    last_month = datetime.now() - timedelta(days=30)
    last_month_outflow = transactions.filter(
        date__gte=last_month
    ).aggregate(Sum('outflow'))['outflow__sum'] or 0

    top_categories = transactions.filter(
        outflow__gt=0
    ).values(
        'category__category',
        'category__categorygroup__category_group'
    ).annotate(
        total=Sum('outflow')
    ).order_by('-total')[:5]

    recent_transactions = transactions.select_related(
        'account', 'payee', 'category', 'flag'
    )[:10]

    context = {
        'current_year': current_year,
        'total_inflow': total_inflow,
        'total_outflow': total_outflow,
        'netto': netto,
        'transaction_count': transaction_count,
        'last_month_outflow': last_month_outflow,
        'top_categories': top_categories,
        'recent_transactions': recent_transactions,
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
    # Ausschlüsse: Transfers, Kursschwankungen, category_id=1
    transactions_for_stats = transactions.exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).exclude(
        category_id=1
    )

    # Einnahmen: Nur category_id = 1 (Inflow - Ready to Assign)
    total_inflow = transactions.exclude(
        payee__payee_type__in=['transfer', 'kursschwankung']
    ).filter(
        category_id=1
    ).aggregate(Sum('inflow'))['inflow__sum'] or 0

    # Ausgaben NETTO: Inflow - Outflow (für alle relevanten Transaktionen)
    # Das sind quasi "Ausgabenkategorien" die manchmal Rückerstattungen haben können
    stats_aggregate = transactions_for_stats.aggregate(
        sum_inflow=Sum('inflow'),
        sum_outflow=Sum('outflow')
    )
    category_inflow = stats_aggregate['sum_inflow'] or 0
    category_outflow = stats_aggregate['sum_outflow'] or 0
    total_outflow_netto = category_outflow - category_inflow  # Netto-Ausgaben

    # Saldo = Echte Einnahmen - Netto-Ausgaben
    netto = total_inflow - total_outflow_netto

    # Anzahl ALLER Transaktionen (inkl. Transfers & Kursschwankungen)
    transaction_count = transactions.count()
    transfer_count = transactions.filter(payee__payee_type='transfer').count()
    kursschwankung_count = transactions.filter(payee__payee_type='kursschwankung').count()
    excluded_count = transfer_count + kursschwankung_count

    accounts = DimAccount.objects.all()
    categories = DimCategory.objects.select_related('categorygroup').all()
    years = range(datetime.now().year, 2019, -1)

    # Limitierung für Anzeige (ALLE Transaktionen inkl. Transfers)
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
    }

    return render(request, 'finance/transactions.html', context)


@login_required
def household_transactions(request):
    """
    Haushalt-Transaktionen:
    - Alle Transaktionen von Robert
    - Transaktionen von Sigi mit flag_id = 5 (Relevant für Haushaltsbudget)
    """
    # Basis-Querysets (OHNE Filter für die Dropdown-Optionen)
    sigi_base = FactTransactionsSigi.objects.filter(flag_id=5)
    robert_base = FactTransactionsRobert.objects.all()

    # Sigi Transaktionen - nur mit flag_id = 5
    sigi_transactions = FactTransactionsSigi.objects.filter(
        flag_id=5  # Relevant für Haushaltsbudget
    ).select_related(
        'account', 'payee', 'category', 'category__categorygroup', 'flag'
    ).annotate(
        person=Value('Sigi', output_field=CharField())
    )

    # Robert Transaktionen - alle
    robert_transactions = FactTransactionsRobert.objects.select_related(
        'account', 'payee', 'category', 'category__categorygroup', 'flag'
    ).annotate(
        person=Value('Robert', output_field=CharField())
    )

    # Filter anwenden
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

    # Statistiken berechnen mit allen Ausschlüssen
    # Ausschlüsse: Transfers, Kursschwankungen, category_id=1
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

    # Ausgaben NETTO für Sigi: Outflow - Inflow
    sigi_stats = sigi_for_stats.aggregate(
        sum_inflow=Sum('inflow'),
        sum_outflow=Sum('outflow')
    )
    sigi_inflow = sigi_stats['sum_inflow'] or 0
    sigi_outflow_gross = sigi_stats['sum_outflow'] or 0
    sigi_outflow = sigi_outflow_gross - sigi_inflow  # Netto

    # Ausgaben NETTO für Robert: Outflow - Inflow
    robert_stats = robert_for_stats.aggregate(
        sum_inflow=Sum('inflow'),
        sum_outflow=Sum('outflow')
    )
    robert_inflow = robert_stats['sum_inflow'] or 0
    robert_outflow_gross = robert_stats['sum_outflow'] or 0
    robert_outflow = robert_outflow_gross - robert_inflow  # Netto

    # Gesamt-Ausgaben NETTO
    total_outflow = sigi_outflow + robert_outflow

    # Listen für Anzeige (ALLE Transaktionen inkl. Transfers)
    sigi_list_full = list(sigi_transactions)
    robert_list_full = list(robert_transactions)

    # Nach Person filtern
    if person_filter == 'sigi':
        transactions_full = sigi_list_full
    elif person_filter == 'robert':
        transactions_full = robert_list_full
    else:
        # Beide kombinieren
        transactions_full = sigi_list_full + robert_list_full

    # Nach Datum sortieren (neueste zuerst)
    transactions_full.sort(key=lambda x: x.date, reverse=True)

    # Prozentanteile (basierend auf Ausgaben ohne Transfers)
    robert_percentage = (robert_outflow / total_outflow * 100) if total_outflow > 0 else 0
    sigi_percentage = (sigi_outflow / total_outflow * 100) if total_outflow > 0 else 0

    # Anzahl Transaktionen (inkl. Transfers & Kursschwankungen)
    transaction_count = len(transactions_full)

    # Transfer- und Kursschwankung-Anzahl
    transfer_count = sum(1 for t in transactions_full if t.payee and t.payee.payee_type == 'transfer')
    kursschwankung_count = sum(1 for t in transactions_full if t.payee and t.payee.payee_type == 'kursschwankung')
    excluded_count = transfer_count + kursschwankung_count

    # Limitieren für Anzeige
    transactions = transactions_full[:100]

    # Dynamische Filter-Optionen (nur Werte die tatsächlich vorkommen)
    # Accounts: Union von Sigi und Robert Account IDs
    sigi_account_ids = sigi_base.values_list('account_id', flat=True).distinct()
    robert_account_ids = robert_base.values_list('account_id', flat=True).distinct()
    available_account_ids = set(sigi_account_ids) | set(robert_account_ids)
    accounts = DimAccount.objects.filter(id__in=available_account_ids).order_by('account')

    # Categories: Union von Sigi und Robert Category IDs
    sigi_category_ids = sigi_base.values_list('category_id', flat=True).distinct()
    robert_category_ids = robert_base.values_list('category_id', flat=True).distinct()
    available_category_ids = set(sigi_category_ids) | set(robert_category_ids)
    categories = DimCategory.objects.filter(
        id__in=available_category_ids
    ).select_related('categorygroup').order_by('category')

    # Jahre: Union von Sigi und Robert Jahren
    from django.db.models import functions
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
    # Robert darf nicht auf API zugreifen
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
    # Robert darf nicht auf API zugreifen
    if request.user.username == 'robert':
        return JsonResponse({'error': 'Keine Berechtigung'}, status=403)

    year = request.GET.get('year', datetime.now().year)

    category_data = FactTransactionsSigi.objects.filter(
        date__year=year,
        outflow__gt=0
    ).values(
        'category__categorygroup__category_group'
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
    # Robert darf nicht auf API zugreifen
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
    """
    Vermögensübersicht berechnet aus fact_transactions_sigi
    """
    # Robert darf nicht auf Vermögensübersicht zugreifen
    if request.user.username == 'robert':
        messages.warning(request, 'Du hast keine Berechtigung für diese Seite.')
        return redirect('finance:household_transactions')

    # Datum-Parameter
    selected_date = request.GET.get('date')
    if selected_date:
        try:
            current_date = datetime.strptime(selected_date, '%Y-%m').date()
        except ValueError:
            current_date = datetime.now().date()
    else:
        current_date = datetime.now().date()

    # Letzter Tag des ausgewählten Monats
    if current_date.month == 12:
        current_date = current_date.replace(day=31)
    else:
        next_month = current_date.replace(month=current_date.month + 1, day=1)
        current_date = next_month - timedelta(days=1)

    # Vormonat und Vorjahr berechnen
    prev_month_temp = (current_date.replace(day=1) - timedelta(days=1))
    if prev_month_temp.month == 12:
        prev_month = prev_month_temp.replace(day=31)
    else:
        next_month = prev_month_temp.replace(month=prev_month_temp.month + 1, day=1)
        prev_month = next_month - timedelta(days=1)

    # Vorjahr: gleiches Monat, Vorjahr
    try:
        prev_year = current_date.replace(year=current_date.year - 1)
    except ValueError:
        # Falls 29. Februar
        prev_year = current_date.replace(year=current_date.year - 1, day=28)

    # Hole alle Accounts
    accounts = DimAccount.objects.all()

    # Kategorien-Dict vorbereiten
    categories_dict = defaultdict(lambda: {
        'positions': [],
        'total_current': Decimal('0'),
        'total_prev_month': Decimal('0'),
        'total_prev_year': Decimal('0'),
        'display_name': '',
        'order': 99,
        'color_class': '',
    })

    # Für jeden Account: Berechne Saldo zu den drei Zeitpunkten
    for account in accounts:
        account_name = account.account
        account_type = account.accounttype.accounttypes if account.accounttype else None

        # Kategorisiere Account
        category, display_name, order, color_class, icon = get_account_category(
            account_name, account_type
        )

        # Berechne Salden
        current_balance = calculate_account_balance(account.id, current_date)
        prev_month_balance = calculate_account_balance(account.id, prev_month)
        prev_year_balance = calculate_account_balance(account.id, prev_year)

        # Überspringe Accounts mit allen Salden bei 0
        if current_balance == 0 and prev_month_balance == 0 and prev_year_balance == 0:
            continue

        # Delta berechnen
        delta_month = None
        if prev_month_balance != 0:
            delta_month = ((current_balance - prev_month_balance) / abs(prev_month_balance) * 100)

        delta_year = None
        if prev_year_balance != 0:
            delta_year = ((current_balance - prev_year_balance) / abs(prev_year_balance) * 100)

        # Position hinzufügen
        position_info = {
            'name': account_name,
            'icon': icon,
            'current_balance': current_balance,
            'prev_month_balance': prev_month_balance,
            'prev_year_balance': prev_year_balance,
            'delta_month': delta_month,
            'delta_year': delta_year,
        }

        # Zur Kategorie hinzufügen
        categories_dict[category]['positions'].append(position_info)
        categories_dict[category]['total_current'] += current_balance
        categories_dict[category]['total_prev_month'] += prev_month_balance
        categories_dict[category]['total_prev_year'] += prev_year_balance
        categories_dict[category]['display_name'] = display_name
        categories_dict[category]['order'] = order
        categories_dict[category]['color_class'] = color_class

    # Konvertiere zu sortierter Liste
    categories_data = []
    for category_name, data in categories_dict.items():
        # Kategorie-Deltas berechnen
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

        # Sortiere Positionen alphabetisch
        data['positions'].sort(key=lambda x: x['name'])

        categories_data.append({
            'name': category_name,
            **data
        })

    # Sortiere Kategorien nach Order
    categories_data.sort(key=lambda x: x['order'])

    # Gesamtsummen
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