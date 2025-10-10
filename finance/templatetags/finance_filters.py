# finance/templatetags/finance_filters.py
"""
Custom Template-Filter für das Finance-Modul
"""
from django import template
from finance.utils import get_account_icon, format_currency

register = template.Library()


@register.filter(name='account_icon')
def account_icon(account_name):
    """
    Template-Filter: Gibt das Icon für einen Account zurück

    Verwendung: {{ account.account|account_icon }}
    Ergebnis: 'bank' (Bootstrap Icon Name)
    """
    return get_account_icon(account_name)


@register.filter(name='currency')
def currency(amount):
    """
    Template-Filter: Formatiert einen Betrag als Währung

    Verwendung: {{ amount|currency }}
    Ergebnis: '1.234,56 €'
    """
    return format_currency(amount)


@register.simple_tag
def icon_tag(icon_name, css_class=''):
    """
    Template-Tag: Rendert ein Bootstrap Icon

    Verwendung: {% icon_tag 'bank' 'text-primary' %}
    Ergebnis: <i class="bi bi-bank text-primary"></i>
    """
    return f'<i class="bi bi-{icon_name} {css_class}"></i>'


@register.filter(name='abs')
def abs_filter(value):
    """
    Template-Filter: Gibt den Absolutwert zurück

    Verwendung: {{ number|abs }}
    Ergebnis: Positive Zahl
    """
    try:
        return abs(value)
    except (ValueError, TypeError):
        return value