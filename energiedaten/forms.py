from django import forms


class StromverbrauchImportForm(forms.Form):
    """Formular zum Hochladen einer Excel-Datei mit Stromverbrauchsdaten."""

    file = forms.FileField(
        label="Excel-Datei (.xlsx)",
        widget=forms.FileInput(attrs={"accept": ".xlsx", "class": "form-control"}),
        help_text="Bitte eine Datei im XLSX-Format mit Zeitstempeln in Spalte A und kWh-Werten in Spalte D hochladen.",
    )

    def clean_file(self):
        uploaded_file = self.cleaned_data["file"]
        if not uploaded_file.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Nur Dateien im XLSX-Format werden unterstützt.")
        return uploaded_file
