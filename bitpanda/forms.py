# bitpanda/forms.py
from django import forms


class PriceUpdateForm(forms.Form):
    """Form für manuelle Preisaktualisierung"""

    def __init__(self, *args, holdings=None, **kwargs):
        super().__init__(*args, **kwargs)

        if holdings:
            for holding in holdings:
                # Dynamisches Feld für jedes Asset
                field_name = f'price_{holding.id}'
                self.fields[field_name] = forms.DecimalField(
                    label=f'{holding.asset}',
                    max_digits=20,
                    decimal_places=8,
                    required=False,
                    widget=forms.NumberInput(attrs={
                        'class': 'form-control',
                        'placeholder': 'Aktueller Preis',
                        'step': '0.00000001'
                    })
                )