# finance/management/commands/transfer_setup_info.py
"""
Zeigt alle relevanten Informationen für das Transfer-Setup
"""
from django.core.management.base import BaseCommand
from finance.models import DimAccount, DimPayee


class Command(BaseCommand):
    help = 'Zeigt Informationen für Transfer-Setup (Account-IDs und Namen)'

    def handle(self, *args, **options):
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('📋 TRANSFER-SETUP INFORMATIONEN'))
        self.stdout.write('=' * 70)

        # Zeige alle Accounts
        self.stdout.write('\n' + self.style.WARNING('📁 ALLE ACCOUNTS IN DER DATENBANK:'))
        self.stdout.write('-' * 70)
        accounts = DimAccount.objects.all().order_by('account')

        for acc in accounts:
            self.stdout.write(f'  ID: {acc.id:3d} | {acc.account}')

        # Zeige Transfer-Payees
        self.stdout.write('\n' + self.style.WARNING('🔄 TRANSFER-PAYEES:'))
        self.stdout.write('-' * 70)
        transfer_payees = DimPayee.objects.filter(
            payee_type='transfer'
        ).order_by('payee')

        for payee in transfer_payees:
            self.stdout.write(f'  ID: {payee.id:3d} | {payee.payee}')

        # Gebe Mapping-Vorschlag
        self.stdout.write('\n' + self.style.SUCCESS('💡 EMPFOHLENE KONFIGURATION FÜR signals.py:'))
        self.stdout.write('-' * 70)

        # Versuche intelligentes Mapping
        account_mapping = {}
        for payee in transfer_payees:
            # Extrahiere Account-Name aus Payee
            # z.B. "Transfer : 💳 MasterCard" → "MasterCard"
            if ':' in payee.payee:
                parts = payee.payee.split(':', 1)
                if len(parts) == 2:
                    clean_name = parts[1].strip()
                    # Entferne Emojis für Matching
                    clean_name_no_emoji = ''.join(
                        c for c in clean_name
                        if c.isalnum() or c.isspace() or c in ['&', '-', '_']
                    ).strip()

                    # Suche passenden Account
                    for acc in accounts:
                        if clean_name_no_emoji.lower() in acc.account.lower() or \
                                acc.account.lower() in clean_name_no_emoji.lower():
                            account_mapping[payee.payee] = acc.account
                            break

        self.stdout.write('\nTRANSFER_MAPPING = {')
        for payee_name, account_name in account_mapping.items():
            self.stdout.write(f"    '{payee_name}': '{account_name}',")
        self.stdout.write('}')

        # Robert-Accounts identifizieren
        self.stdout.write('\n' + self.style.WARNING('\n👤 VERMUTLICHE ROBERT-ACCOUNTS:'))
        self.stdout.write('-' * 70)

        robert_keywords = ['robert', 'master', 'mastercard', 'kreditkarte']
        potential_robert_accounts = []

        for acc in accounts:
            if any(keyword in acc.account.lower() for keyword in robert_keywords):
                potential_robert_accounts.append(acc)
                self.stdout.write(f'  ID: {acc.id:3d} | {acc.account}')

        if potential_robert_accounts:
            self.stdout.write('\n' + self.style.SUCCESS('📝 Empfehlung für signals.py:'))
            ids = [str(acc.id) for acc in potential_robert_accounts]
            names = [f"'{acc.account}'" for acc in potential_robert_accounts]

            self.stdout.write(f'\nrobert_account_ids = [{", ".join(ids)}]')
            self.stdout.write(f'robert_account_names = [{", ".join(names)}]')

        # Prüfe ob Girokonto existiert
        self.stdout.write('\n' + self.style.WARNING('\n🏦 GIROKONTO-CHECK:'))
        self.stdout.write('-' * 70)

        giro_keywords = ['giro', 'girokonto']
        giro_accounts = [
            acc for acc in accounts
            if any(keyword in acc.account.lower() for keyword in giro_keywords)
        ]

        if giro_accounts:
            for acc in giro_accounts:
                self.stdout.write(self.style.SUCCESS(f'  ✓ Gefunden: ID {acc.id} | {acc.account}'))
        else:
            self.stdout.write(self.style.ERROR('  ✗ Kein Girokonto gefunden!'))

        # Zusammenfassung
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.SUCCESS('✅ NÄCHSTE SCHRITTE:'))
        self.stdout.write('=' * 70)
        self.stdout.write('''
1. Kopiere die obigen Mappings in finance/signals.py
2. Passe TRANSFER_MAPPING an (falls nötig)
3. Setze robert_account_ids und robert_account_names
4. Teste mit: python manage.py test finance.tests.test_transfers
5. Erstelle Gegenbuchungen für bestehende Transfers:
   python manage.py create_missing_counterparts --dry-run
        ''')
        self.stdout.write('=' * 70)