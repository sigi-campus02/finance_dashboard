# Speichere unter: finance/management/commands/execute_scheduled_transactions.py

from django.core.management.base import BaseCommand
from finance.models import ScheduledTransaction
from datetime import date


class Command(BaseCommand):
    help = 'Führt fällige Scheduled Transactions aus'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Zeigt nur an was ausgeführt würde, ohne tatsächlich zu erstellen',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        today = date.today()

        # Hole alle aktiven Scheduled Transactions die fällig sind
        scheduled = ScheduledTransaction.objects.filter(
            is_active=True,
            next_execution_date__lte=today
        )

        if not scheduled.exists():
            self.stdout.write(
                self.style.SUCCESS('✓ Keine fälligen Scheduled Transactions gefunden.')
            )
            return

        self.stdout.write(
            self.style.WARNING(f'📅 Gefunden: {scheduled.count()} fällige Scheduled Transaction(s)')
        )

        executed_count = 0
        failed_count = 0

        for scheduled_transaction in scheduled:
            try:
                if dry_run:
                    self.stdout.write(
                        f'  [DRY-RUN] Würde erstellen: {scheduled_transaction}'
                    )
                else:
                    transaction = scheduled_transaction.execute()

                    if transaction:
                        executed_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'  ✓ Erstellt: {scheduled_transaction.payee} - '
                                f'€{scheduled_transaction.outflow or scheduled_transaction.inflow} '
                                f'(Nächste: {scheduled_transaction.next_execution_date})'
                            )
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f'  ⊘ Übersprungen: {scheduled_transaction} '
                                f'(Enddatum erreicht oder bereits ausgeführt)'
                            )
                        )

            except Exception as e:
                failed_count += 1
                self.stdout.write(
                    self.style.ERROR(
                        f'  ✗ Fehler bei {scheduled_transaction}: {str(e)}'
                    )
                )

        # Zusammenfassung
        if not dry_run:
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('=' * 50))
            self.stdout.write(
                self.style.SUCCESS(f'✓ Erfolgreich erstellt: {executed_count}')
            )
            if failed_count > 0:
                self.stdout.write(
                    self.style.ERROR(f'✗ Fehler: {failed_count}')
                )
            self.stdout.write(self.style.SUCCESS('=' * 50))