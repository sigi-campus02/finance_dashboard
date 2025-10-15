# finance/utils.py
"""
Utility-Funktionen für das Finance-Modul
"""
from decimal import Decimal

# Icon-Mapping für verschiedene Account-Typen
ACCOUNT_ICON_MAPPING = {
    # Cash
    'giro': 'bank',
    'girokonto': 'bank',
    'bargeld': 'cash-stack',
    'cash': 'cash-stack',
    'onlinesparen': 'piggy-bank',
    'sparen': 'piggy-bank',
    'sparkonto': 'piggy-bank',
    'gutschein': 'gift',
    'gutscheine': 'gift',

    # Credit
    'mastercard': 'credit-card',
    'visa': 'credit-card',
    'kreditkarte': 'credit-card',
    'credit': 'credit-card',
    'kredit': 'credit-card',

    # MidtermInvest
    'etf': 'graph-up-arrow',
    'fonds': 'tree',
    'krypto': 'currency-bitcoin',
    'aktien': 'graph-up',
    'gold': 'gem',
    'goldanlage': 'gem',
    'wertpapier': 'briefcase',

    # LongtermInvest
    'pension': 'shield-check',
    'pensionskonto': 'shield-check',
    'rente': 'shield-check',
    'vorsorge': 'briefcase',
    'vorsorgekasse': 'piggy-bank-fill',
    'apk': 'building',
    'vbv': 'safe',
    'bvk': 'shield-check',
    'versicherung': 'shield-fill',
    'uniqa': 'shield-check',
}

# Kategorie-Konfiguration
CATEGORY_CONFIG = {
    'Cash': {
        'display_name': 'Cash',
        'order': 1,
        'color_class': 'text-success',
        'bg_class': 'bg-success',
        'icon': 'wallet2',
    },
    'Credit': {
        'display_name': 'Credit',
        'order': 2,
        'color_class': 'text-danger',
        'bg_class': 'bg-danger',
        'icon': 'credit-card',
    },
    'MidtermInvest': {
        'display_name': 'MidtermInvest',
        'order': 3,
        'color_class': 'text-primary',
        'bg_class': 'bg-primary',
        'icon': 'graph-up-arrow',
    },
    'LongtermInvest': {
        'display_name': 'LongtermInvest',
        'order': 4,
        'color_class': 'text-info',
        'bg_class': 'bg-info',
        'icon': 'shield-check',
    },
    'Sonstige': {
        'display_name': 'Sonstige',
        'order': 99,
        'color_class': 'text-secondary',
        'bg_class': 'bg-secondary',
        'icon': 'question-circle',
    }
}


def get_account_icon(account_name):
    """
    Gibt das passende Bootstrap Icon für einen Account zurück

    Args:
        account_name (str): Name des Accounts

    Returns:
        str: Bootstrap Icon Name (z.B. 'bank', 'credit-card')
    """
    if not account_name:
        return 'wallet2'

    account_lower = account_name.lower()

    # Suche nach exakten oder Teil-Übereinstimmungen
    for keyword, icon in ACCOUNT_ICON_MAPPING.items():
        if keyword in account_lower:
            return icon

    return 'wallet2'  # Standard-Icon


def calculate_account_balance(account_id, end_date):
    """
    Berechnet den Kontostand eines Accounts bis zu einem bestimmten Datum
    Saldo = Summe(Inflow) - Summe(Outflow)

    Args:
        account_id (int): ID des Accounts
        end_date (date): Stichtag für die Berechnung

    Returns:
        Decimal: Kontostand
    """
    from django.db.models import Sum
    from .models import FactTransactionsSigi

    transactions = FactTransactionsSigi.objects.filter(
        account_id=account_id,
        date__lte=end_date
    ).aggregate(
        total_inflow=Sum('inflow'),
        total_outflow=Sum('outflow')
    )

    inflow = transactions['total_inflow'] or Decimal('0')
    outflow = transactions['total_outflow'] or Decimal('0')

    return inflow - outflow


def format_currency(amount):
    """
    Formatiert einen Betrag als Währung

    Args:
        amount (Decimal/float): Betrag

    Returns:
        str: Formatierter Betrag (z.B. "1.234,56 €")
    """
    if amount is None:
        return "0,00 €"

    return f"{amount:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def calculate_percentage_change(current, previous):
    """
    Berechnet die prozentuale Veränderung

    Args:
        current (Decimal): Aktueller Wert
        previous (Decimal): Vorheriger Wert

    Returns:
        Decimal or None: Prozentuale Veränderung
    """
    if not previous or previous == 0:
        return None

    return ((current - previous) / abs(previous)) * 100