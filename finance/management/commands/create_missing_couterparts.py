# finance/management/commands/create_missing_counterparts.py
"""
Management Command um fehlende Gegenbuchungen für bestehende Transfers zu erstellen
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from finance.models import FactTransactionsSigi, FactTransactionsRobert
from finance.signals import should_create_counterpart, create_transfer_counterpart


class Command(BaseCommand):
    help = 'Erstellt fehlende Transfer-Gegenbuchungen für bestehende Transaktionen'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Zeigt nur an was erstellt würde, ohne tatsächlich zu erstellen',
        )
        parser.add_argument(
            '--table',
            type=str,
            choices=['sigi', 'robert', 'both'],
            default='both',
            help='Welche Tabelle soll verarbeitet werden (default: both)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        table_filter = options['table']

        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - Keine Änderungen werden vorgenommen'))

        sigi_count = 0
        robert_count = 0

        # Sigi-Transaktionen verarbeiten
        if table_filter in ['sigi', 'both']:
            self.stdout.write('\n📊 Verarbeite Sigi-Transaktionen...')
            sigi_transfers = FactTransactionsSigi.objects.filter(
                payee__payee_type='transfer'
            ).select_related('account', 'payee', 'flag').order_by('date')

            self.stdout.write(f'Gefunden: {sigi_transfers.count()} Transfer-Transaktionen')

            for trans in sigi_transfers:
                if should_create_counterpart(trans):
                    if dry_run:
                        self.stdout.write(
                            f'  [DRY-RUN] Würde Gegenbuchung erstellen für: '
                            f'{trans.date} | {trans.account} → {trans.payee} | '
                            f'€{trans.outflow or trans.inflow}'
                        )
                    else:
                        try:
                            with transaction.atomic():
                                create_transfer_counterpart(trans)
                                sigi_count += 1
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f'  ✓ Gegenbuchung erstellt: {trans.date} | '
                                        f'{trans.account} → {trans.payee}'
                                    )
                                )
                        except Exception as e:
                            self.stdout.write(
                                self.style.ERROR(
                                    f'  ✗ Fehler bei {trans.id}: {str(e)}'
                                )
                            )

        # Robert-Transaktionen verarbeiten
        if table_filter in ['robert', 'both']:
            self.stdout.write('\n📊 Verarbeite Robert-Transaktionen...')
            robert_transfers = FactTransactionsRobert.objects.filter(
                payee__payee_type='transfer'
            ).select_related('account', 'payee', 'flag').order_by('date')

            self.stdout.write(f'Gefunden: {robert_transfers.count()} Transfer-Transaktionen')

            for trans in robert_transfers:
                if should_create_counterpart(trans):
                    if dry_run:
                        self.stdout.write(
                            f'  [DRY-RUN] Würde Gegenbuchung erstellen für: '
                            f'{trans.date} | {trans.account} → {trans.payee} | '
                            f'€{trans.outflow or trans.inflow}'
                        )
                    else:
                        try:
                            with transaction.atomic():
                                create_transfer_counterpart(trans)
                                robert_count += 1
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f'  ✓ Gegenbuchung erstellt: {trans.date} | '
                                        f'{trans.account} → {trans.payee}'
                                    )
                                )
                        except Exception as e:
                            self.stdout.write(
                                self.style.ERROR(
                                    f'  ✗ Fehler bei {trans.id}: {str(e)}'
                                )
                            )

        # Zusammenfassung
        self.stdout.write('\n' + '=' * 60)
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    '🔍 DRY RUN abgeschlossen - Keine Daten wurden geändert'
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS('✅ Verarbeitung abgeschlossen!'))
            self.stdout.write(f'  • Sigi-Gegenbuchungen erstellt: {sigi_count}')
            self.stdout.write(f'  • Robert-Gegenbuchungen erstellt: {robert_count}')
            self.stdout.write(f'  • Gesamt: {sigi_count + robert_count}')
        self.stdout.write('=' * 60)