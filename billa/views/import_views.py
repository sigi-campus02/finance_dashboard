import os
import tempfile
from django.contrib import messages
from django.shortcuts import redirect
from billa.services.brand_mapper import BrandMapper
from django.db import transaction
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from billa.models import (
    BillaEinkauf, BillaArtikel, BillaProdukt,
    BillaPreisHistorie, BillaFiliale
)
from billa.services.parser import BillaReceiptParser


@login_required
def billa_import_upload(request):
    """Upload-Formular für Billa-Rechnungen"""

    if request.method == 'POST' and request.FILES.getlist('pdf_files'):
        pdf_files = request.FILES.getlist('pdf_files')
        # WICHTIG: Checkbox gibt 'on' zurück wenn aktiviert, sonst existiert der Key nicht
        force = bool(request.POST.get('force'))

        stats = {
            'total': len(pdf_files),
            'imported': 0,
            'skipped': 0,
            'errors': 0,
            'error_details': []
        }

        parser = BillaReceiptParser()

        for pdf_file in pdf_files:
            # Speichere Datei temporär
            temp_dir = tempfile.mkdtemp()
            temp_path = os.path.join(temp_dir, pdf_file.name)

            try:
                # Schreibe Datei
                with open(temp_path, 'wb+') as destination:
                    for chunk in pdf_file.chunks():
                        destination.write(chunk)

                # Parse PDF (verwendet jetzt die konsolidierte Logik)
                data = parser.parse_pdf(temp_path)

                # Prüfe ob bereits importiert (VOR der Transaktion!)
                if not force and data.get('re_nr'):
                    if BillaEinkauf.objects.filter(re_nr=data['re_nr']).exists():
                        stats['skipped'] += 1
                        stats['error_details'].append({
                            'file': pdf_file.name,
                            'error': f'Rechnung bereits vorhanden (Re-Nr: {data["re_nr"]}). Aktiviere "Erneut importieren" um zu überschreiben.'
                        })
                        continue

                # Jedes PDF in eigener Transaktion!
                with transaction.atomic():
                    # Bei force: Alte Rechnung löschen
                    if force and data.get('re_nr'):
                        BillaEinkauf.objects.filter(re_nr=data['re_nr']).delete()

                    # Erstelle Einkauf und Artikel
                    _create_einkauf_with_artikel(data)

                stats['imported'] += 1

            except Exception as e:
                stats['errors'] += 1
                error_msg = str(e)

                # Debug-Info bei Parsing-Fehlern
                if "konnte nicht" in error_msg or "NULL" in error_msg:
                    try:
                        import pdfplumber
                        with pdfplumber.open(temp_path) as pdf:
                            first_page_text = pdf.pages[0].extract_text()
                            preview = first_page_text[:500] if first_page_text else "Kein Text extrahierbar"
                            error_msg += f"\n\nPDF-Vorschau (erste 500 Zeichen):\n{preview}"
                    except:
                        pass

                stats['error_details'].append({
                    'file': pdf_file.name,
                    'error': error_msg
                })

            finally:
                # Lösche temporäre Datei
                try:
                    os.remove(temp_path)
                    os.rmdir(temp_dir)
                except:
                    pass

        # Feedback-Nachrichten
        if stats['imported'] > 0:
            messages.success(request, f"✓ {stats['imported']} Rechnung(en) erfolgreich importiert")

        if stats['skipped'] > 0:
            messages.warning(request, f"⊘ {stats['skipped']} Rechnung(en) übersprungen (bereits vorhanden)")
            # Zeige Details für übersprungene Rechnungen
            for error in [e for e in stats['error_details'] if 'bereits vorhanden' in e.get('error', '')]:
                messages.info(request, f"  • {error['file']}")

        if stats['errors'] > 0:
            messages.error(request, f"✗ {stats['errors']} Fehler beim Import")
            # Zeige nur echte Fehler (nicht die Duplikate)
            for error in [e for e in stats['error_details'] if 'bereits vorhanden' not in e.get('error', '')]:
                messages.error(request, f"  • {error['file']}: {error['error']}")

        return redirect('billa:billa_dashboard')

    context = {}
    return render(request, 'billa/billa_import.html', context)




def _create_einkauf_with_artikel(data):
    """
    Gemeinsame Logik für Einkauf-Erstellung.
    Wird von View und Command verwendet.

    WICHTIG: Wandelt filiale von String → ForeignKey-Objekt um!
    """
    # Erstelle/finde Filiale
    filial_nr = data.pop('filiale', None)
    if not filial_nr:
        raise ValueError("Keine Filial-Nummer gefunden")

    filiale_obj, created = BillaFiliale.objects.get_or_create(
        filial_nr=filial_nr,
        defaults={
            'name': f'Filiale {filial_nr}',  # Fallback-Name
            'typ': 'billa',  # Default-Typ
            'aktiv': True
        }
    )

    if created:
        print(f"ℹ️  Neue Filiale {filial_nr} automatisch erstellt")

    # Erstelle Einkauf
    artikel_liste = data.pop('artikel')
    data['filiale'] = filiale_obj  # ForeignKey-Objekt statt String!
    einkauf = BillaEinkauf.objects.create(**data)

    # Erstelle Artikel
    for artikel_data in artikel_liste:
        artikel_data['einkauf'] = einkauf

        produkt_name_norm = artikel_data['produkt_name_korrigiert']
        produkt_name_original = artikel_data['produkt_name']

        # Finde oder erstelle Produkt
        produkt, created = BillaProdukt.objects.get_or_create(
            name_korrigiert=produkt_name_norm,
            defaults={
                'name_original': produkt_name_original,
                'letzter_preis': artikel_data['gesamtpreis'],
                'marke': BrandMapper.extract_brand(produkt_name_original)
            }
        )

        # Aktualisiere Marke falls noch nicht gesetzt
        if not created and not produkt.marke:
            produkt.marke = BrandMapper.extract_brand(produkt_name_original)
            produkt.save(update_fields=['marke'])

        # Aktualisiere Original-Namen (kürzeste Variante bevorzugen)
        if not created:
            if len(produkt_name_original) < len(produkt.name_original):
                produkt.name_original = produkt_name_original
                produkt.save(update_fields=['name_original'])

        artikel_data['produkt'] = produkt
        artikel = BillaArtikel.objects.create(**artikel_data)

        # Erstelle Preishistorie (filiale ist jetzt ein ForeignKey-Objekt!)
        BillaPreisHistorie.objects.create(
            produkt=produkt,
            artikel=artikel,
            datum=einkauf.datum,
            preis=artikel.preis_pro_einheit,
            menge=artikel.menge,
            einheit=artikel.einheit,
            filiale=einkauf.filiale  # Verwendet das Filiale-Objekt vom Einkauf
        )

        # Aktualisiere Produkt-Statistiken
        produkt.update_statistiken()

    return einkauf
