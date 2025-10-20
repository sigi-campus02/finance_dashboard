from django import forms
from .models import (
    FactTransactionsSigi, FactTransactionsRobert,
    DimAccount, DimFlag, DimPayee, DimCategory, DimCategoryGroup
)
from decimal import Decimal


class TransactionForm(forms.Form):
    """Formular für neue Transaktionen"""

    # Account (nur für Nicht-Robert-User)
    account = forms.ModelChoiceField(
        queryset=DimAccount.objects.all(),
        required=True,
        label="Konto",
        widget=forms.Select(attrs={
            'class': 'form-select',
        })
    )

    # Flag (nur für Nicht-Robert-User)
    flag = forms.ModelChoiceField(
        queryset=DimFlag.objects.all(),
        required=False,
        label="Flag",
        widget=forms.Select(attrs={
            'class': 'form-select',
        })
    )

    # Datum
    date = forms.DateField(
        required=True,
        label="Datum",
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
        })
    )

    # Payee (mit Autocomplete)
    payee = forms.CharField(
        required=True,
        label="Zahlungsempfänger",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'list': 'payee-list',
            'autocomplete': 'off',
        })
    )

    # Neuer Payee (falls nicht in Liste)
    new_payee = forms.CharField(
        required=False,
        label="Neuer Zahlungsempfänger",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Falls nicht in Liste vorhanden',
        })
    )

    # Category Group
    category_group = forms.ModelChoiceField(
        queryset=DimCategoryGroup.objects.all(),
        required=True,
        label="Kategoriegruppe",
        widget=forms.Select(attrs={
            'class': 'form-select',
            'onchange': 'updateCategories()',
        })
    )

    # Category (wird dynamisch gefiltert)
    category = forms.ModelChoiceField(
        queryset=DimCategory.objects.all(),
        required=True,
        label="Kategorie",
        widget=forms.Select(attrs={
            'class': 'form-select',
        })
    )

    # Memo
    memo = forms.CharField(
        required=False,
        label="Notiz",
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Optional: Weitere Details zur Transaktion',
        })
    )

    # Betrag (nur ein Feld, wird dann als Outflow oder Inflow gespeichert)
    amount = forms.DecimalField(
        required=True,
        label="Betrag (€)",
        max_digits=18,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'placeholder': '0.00',
        })
    )

    # Typ: Ausgabe oder Einnahme (nur für Nicht-Robert-User)
    transaction_type = forms.ChoiceField(
        required=True,
        label="Typ",
        choices=[
            ('outflow', 'Ausgabe'),
            ('inflow', 'Einnahme'),
        ],
        initial='outflow',
        widget=forms.RadioSelect(attrs={
            'class': 'form-check-input',
        })
    )

    def __init__(self, *args, user=None, instance=None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        self.user = user

        # Für Robert: Felder anpassen
        if user and user.username == 'robert':
            # Account auf "Robert's Ausgaben" setzen und verstecken
            self.fields['account'].initial = 18  # Roberts Account ID
            self.fields['account'].widget = forms.HiddenInput()

            # Flag verstecken
            self.fields['flag'].widget = forms.HiddenInput()
            self.fields['flag'].required = False

            # Nur Ausgaben erlauben
            self.fields['transaction_type'].widget = forms.HiddenInput()
            self.fields['transaction_type'].initial = 'outflow'

    def clean(self):
        cleaned_data = super().clean()

        # Prüfe ob Payee existiert oder neu angelegt werden soll
        payee_name = cleaned_data.get('payee')
        new_payee = cleaned_data.get('new_payee')

        if new_payee:
            # Neuer Payee soll angelegt werden
            cleaned_data['payee'] = new_payee

        return cleaned_data

    def save(self):
        """Speichert die Transaktion in der richtigen Tabelle"""
        from django.db import connection

        data = self.cleaned_data

        # Payee holen oder erstellen
        payee_name = data['payee'].strip()  # Whitespace entfernen

        # Versuche erst, den Payee zu finden (case-insensitive)
        try:
            payee = DimPayee.objects.get(payee__iexact=payee_name)
            created = False
        except DimPayee.DoesNotExist:
            # Payee existiert nicht, neu anlegen mit Raw SQL
            # Das umgeht das Problem mit managed=False
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO finance.dim_payee (payee, payee_type) VALUES (%s, %s) RETURNING id",
                    [payee_name, None]
                )
                payee_id = cursor.fetchone()[0]

            # Jetzt das Objekt laden
            payee = DimPayee.objects.get(id=payee_id)
            created = True
        except DimPayee.MultipleObjectsReturned:
            # Falls mehrere existieren, nimm den ersten
            payee = DimPayee.objects.filter(payee__iexact=payee_name).first()
            created = False

        # Betrag aufteilen in Outflow/Inflow
        amount = data['amount']
        transaction_type = data['transaction_type']

        if transaction_type == 'outflow':
            outflow = amount
            inflow = Decimal('0.00')
        else:
            outflow = Decimal('0.00')
            inflow = amount

        # Entscheide in welche Tabelle gespeichert wird
        account = data.get('account')
        account_id = account.id if account else 18

        # Update bestehende Transaktion
        if self.instance:
            transaction = self.instance
            transaction.account_id = account_id
            transaction.flag_id = data['flag'].id if data.get('flag') else None
            transaction.date = data['date']
            transaction.payee = payee
            transaction.category = data['category']
            transaction.memo = data.get('memo', '')
            transaction.outflow = outflow
            transaction.inflow = inflow
            transaction.save()
        else:
            # Robert's Account (ID 18) → fact_transactions_robert
            # Alle anderen → fact_transactions_sigi
            if account_id == 18 or (self.user and self.user.username == 'robert'):
                transaction = FactTransactionsRobert.objects.create(
                    account_id=account_id,
                    flag_id=data['flag'].id if data.get('flag') else None,
                    date=data['date'],
                    payee=payee,
                    category=data['category'],
                    memo=data.get('memo', ''),
                    outflow=outflow,
                    inflow=inflow,
                )
            else:
                transaction = FactTransactionsSigi.objects.create(
                    account_id=account_id,
                    flag_id=data['flag'].id if data.get('flag') else None,
                    date=data['date'],
                    payee=payee,
                    category=data['category'],
                    memo=data.get('memo', ''),
                    outflow=outflow,
                    inflow=inflow,
                )

        return transaction