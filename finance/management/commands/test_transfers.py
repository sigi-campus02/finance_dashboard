# finance/management/commands/test_transfers.py
"""
Manuelles Test-Script für Transfer-Gegenbuchungen
Testet gegen die echte Datenbank (kein managed=False Problem)
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from finance.models import (
    FactTransactionsSigi,
    FactTransactionsRobert,
    DimAccount,
    DimPayee
)
from finance.signals import should_create_counterpart, get_counterpart_account_id
from decimal import Decimal
from datetime import date


class Command(BaseCommand):
    help = 'Testet Transfer-Gegenbuchungen (gegen echte DB)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Löscht Test-Transaktionen nach dem Test',
        )

    def handle(self, *args, **options):
        cleanup = options['cleanup']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('🧪 TRANSFER-GEGENBUCHUNGEN TESTEN'))
        self.stdout.write('=' * 70)

        # Test-Transaktionen tracken
        test_transactions = []

        try:
            # 1. Setup prüfen
            self.stdout.write('\n' + self.style.WARNING('📋 SETUP ÜBERPRÜFEN'))
            self.stdout.write('-' * 70)

            # Finde Giro
            giro = DimAccount.objects.filter(account__icontains='giro').first()
            if not giro:
                self.stdout.write(self.style.ERROR('❌ Girokonto nicht gefunden!'))
                return
            self.stdout.write(self.style.SUCCESS(f'✓ Girokonto gefunden: {giro.account} (ID: {giro.id})'))

            # Finde Transfer-Payee
            transfer_master = DimPayee.objects.filter(
                payee='Transfer : MasterCard'
            ).first()
            if not transfer_master:
                self.stdout.write(self.style.ERROR('❌ Transfer : MasterCard nicht gefunden!'))
                self.stdout.write('   Verfügbare Transfer-Payees:')
                for p in DimPayee.objects.filter(payee_type='transfer'):
                    self.stdout.write(f'     - {p.payee}')
                return
            self.stdout.write(self.style.SUCCESS(f'✓ Transfer-Payee gefunden: {transfer_master.payee}'))

            # Finde MasterCard Account
            master = DimAccount.objects.filter(account__icontains='master').first()
            if not master:
                self.stdout.write(self.style.ERROR('❌ MasterCard Account nicht gefunden!'))
                return
            self.stdout.write(self.style.SUCCESS(f'✓ MasterCard gefunden: {master.account} (ID: {master.id})'))

            # 2. TEST 1: Giro → Master Transfer
            self.stdout.write('\n' + self.style.WARNING('TEST 1: Giro → MasterCard (Outflow)'))
            self.stdout.write('-' * 70)

            with transaction.atomic():
                trans1 = FactTransactionsSigi.objects.create(
                    account=giro,
                    date=date.today(),
                    payee=transfer_master,
                    outflow=Decimal('99.99'),
                    inflow=Decimal('0.00'),
                    memo='TEST Transfer Giro→Master - BITTE LÖSCHEN'
                )
                test_transactions.append(('sigi', trans1.id))

                self.stdout.write(f'  ✓ Haupttransaktion erstellt: ID {trans1.id}')

                # Prüfe Gegenbuchung
                counterpart1 = FactTransactionsRobert.objects.filter(
                    account=master,
                    date=trans1.date,
                    inflow=Decimal('99.99'),
                    memo__icontains='TEST'
                ).first()

                if counterpart1:
                    test_transactions.append(('robert', counterpart1.id))
                    self.stdout.write(self.style.SUCCESS(
                        f'  ✅ ERFOLG: Gegenbuchung erstellt (ID: {counterpart1.id})'
                    ))
                    self.stdout.write(f'     Account: {counterpart1.account.account}')
                    self.stdout.write(f'     Payee: {counterpart1.payee.payee}')
                    self.stdout.write(f'     Inflow: €{counterpart1.inflow}')
                else:
                    self.stdout.write(self.style.ERROR('  ❌ FEHLER: Keine Gegenbuchung gefunden!'))
                    self.stdout.write('     Debug Info:')
                    self.stdout.write(f'       should_create: {should_create_counterpart(trans1)}')
                    self.stdout.write(f'       target_account_id: {get_counterpart_account_id(trans1.payee.payee)}')

            # 3. TEST 2: Prüfe ob normale Transaktionen keine Gegenbuchung erstellen
            self.stdout.write('\n' + self.style.WARNING('TEST 2: Normale Transaktion (keine Gegenbuchung)'))
            self.stdout.write('-' * 70)

            normal_payee = DimPayee.objects.exclude(payee_type='transfer').first()
            if normal_payee:
                with transaction.atomic():
                    initial_count = FactTransactionsRobert.objects.count()

                    trans2 = FactTransactionsSigi.objects.create(
                        account=giro,
                        date=date.today(),
                        payee=normal_payee,
                        outflow=Decimal('10.00'),
                        memo='TEST Normale Transaktion - BITTE LÖSCHEN'
                    )
                    test_transactions.append(('sigi', trans2.id))

                    new_count = FactTransactionsRobert.objects.count()

                    if new_count == initial_count:
                        self.stdout.write(self.style.SUCCESS(
                            '  ✅ ERFOLG: Keine Gegenbuchung erstellt (wie erwartet)'
                        ))
                    else:
                        self.stdout.write(self.style.ERROR(
                            '  ❌ FEHLER: Unerwartete Gegenbuchung erstellt!'
                        ))

            # 4. TEST 3: Prüfe OnlineSparen → Giro
            self.stdout.write('\n' + self.style.WARNING('TEST 3: OnlineSparen → Giro'))
            self.stdout.write('-' * 70)

            saving = DimAccount.objects.filter(account__icontains='sparen').first()
            transfer_giro = DimPayee.objects.filter(payee='Transfer : Girokonto').first()

            if saving and transfer_giro:
                with transaction.atomic():
                    trans3 = FactTransactionsSigi.objects.create(
                        account=saving,
                        date=date.today(),
                        payee=transfer_giro,
                        outflow=Decimal('50.00'),
                        memo='TEST Transfer Saving→Giro - BITTE LÖSCHEN'
                    )
                    test_transactions.append(('sigi', trans3.id))

                    self.stdout.write(f'  ✓ Haupttransaktion erstellt: ID {trans3.id}')

                    # Prüfe Gegenbuchung
                    counterpart3 = FactTransactionsSigi.objects.filter(
                        account=giro,
                        date=trans3.date,
                        inflow=Decimal('50.00'),
                        memo__icontains='TEST'
                    ).exclude(id=trans3.id).first()

                    if counterpart3:
                        test_transactions.append(('sigi', counterpart3.id))
                        self.stdout.write(self.style.SUCCESS(
                            f'  ✅ ERFOLG: Gegenbuchung erstellt (ID: {counterpart3.id})'
                        ))
                        self.stdout.write(f'     Payee: {counterpart3.payee.payee}')
                    else:
                        self.stdout.write(self.style.ERROR('  ❌ FEHLER: Keine Gegenbuchung gefunden!'))
            else:
                self.stdout.write(
                    self.style.WARNING('  ⊘ Test übersprungen (OnlineSparen oder Transfer-Payee nicht gefunden)'))

            # Zusammenfassung
            self.stdout.write('\n' + '=' * 70)
            self.stdout.write(self.style.SUCCESS('📊 TEST-ZUSAMMENFASSUNG'))
            self.stdout.write('=' * 70)
            self.stdout.write(f'Erstellte Test-Transaktionen: {len(test_transactions)}')

            # Aufräumen
            if cleanup:
                self.stdout.write('\n' + self.style.WARNING('🗑️  AUFRÄUMEN...'))
                with transaction.atomic():
                    for table, trans_id in test_transactions:
                        if table == 'sigi':
                            FactTransactionsSigi.objects.filter(id=trans_id).delete()
                        else:
                            FactTransactionsRobert.objects.filter(id=trans_id).delete()
                        self.stdout.write(f'  ✓ Gelöscht: {table} ID {trans_id}')

                self.stdout.write(self.style.SUCCESS('\n✅ Alle Test-Transaktionen gelöscht!'))
            else:
                self.stdout.write('\n' + self.style.WARNING('⚠️  Test-Transaktionen NICHT gelöscht!'))
                self.stdout.write('   IDs zum manuellen Löschen:')
                for table, trans_id in test_transactions:
                    self.stdout.write(f'     - {table}: {trans_id}')
                self.stdout.write('\n   Automatisch löschen mit: python manage.py test_transfers --cleanup')

            self.stdout.write('\n' + '=' * 70)

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ FEHLER: {str(e)}'))

            if test_transactions and not cleanup:
                self.stdout.write('\n⚠️  Aufräumen mit: python manage.py test_transfers --cleanup')