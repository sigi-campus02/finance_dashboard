# finance/signals.py - DEBUG VERSION

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from decimal import Decimal
import logging

from .models import (
    FactTransactionsSigi,
    FactTransactionsRobert,
    DimPayee,
    DimAccount
)

logger = logging.getLogger(__name__)

# Mapping bleibt gleich...
TRANSFER_MAPPING = {
    'Transfer : MasterCard': 'MasterCard',
    'Transfer : Pensionsvorsorge Uniqa': 'Pensionsvorsorge Uniqa',
    'Transfer : OnlineSparen': 'OnlineSparen',
    'Transfer : ETF': 'ETF',
    'Transfer : Krypto & Aktien': 'Krypto & Aktien',
    'Transfer : Top4 Fonds & Green Invest': 'Top4 Fonds & Green Invest',
    'Transfer : Bausparer': 'Bausparer',
    'Transfer : Goldanlage': 'Goldanlage',
    'Transfer : Bargeld': 'Bargeld',
    'Transfer : Gutscheine': 'Gutscheine',
    'Transfer : Girokonto': 'Girokonto',
}

COUNTERPART_PAYEE_MAPPING = {
    'Transfer : MasterCard': 'Transfer : Girokonto',
    'Transfer : Pensionsvorsorge Uniqa': 'Transfer : Girokonto',
    'Transfer : OnlineSparen': 'Transfer : Girokonto',
    'Transfer : ETF': 'Transfer : Girokonto',
    'Transfer : Krypto & Aktien': 'Transfer : Girokonto',
    'Transfer : Top4 Fonds & Green Invest': 'Transfer : Girokonto',
    'Transfer : Bausparer': 'Transfer : Girokonto',
    'Transfer : Goldanlage': 'Transfer : Girokonto',
    'Transfer : Bargeld': 'Transfer : Girokonto',
    'Transfer : Gutscheine': 'Transfer : Girokonto',
    'Transfer : Girokonto': None,
}


def should_create_counterpart(instance):
    """Prüft ob Gegenbuchung erstellt werden soll"""
    print("\n" + "=" * 70)
    print("🔍 PRÜFE OB GEGENBUCHUNG ERSTELLT WERDEN SOLL")
    print("=" * 70)

    print(f"📝 Transaktion ID: {instance.id}")
    print(f"📅 Datum: {instance.date}")
    print(f"🏦 Account: {instance.account}")
    print(f"💰 Betrag: Outflow={instance.outflow}, Inflow={instance.inflow}")
    print(f"📌 Memo: '{instance.memo}'")

    # CHECK 1: Auto-Gegenbuchung?
    print("\n🔸 CHECK 1: Ist es bereits eine Auto-Gegenbuchung?")
    if instance.memo and '[Auto-Gegenbuchung]' in instance.memo:
        print("   ❌ JA → Abbruch (verhindert Endlos-Loop)")
        return False
    print("   ✅ NEIN → Weiter")

    # CHECK 2: Hat die Transaktion einen Payee?
    print("\n🔸 CHECK 2: Hat die Transaktion einen Payee?")
    if not instance.payee:
        print("   ❌ NEIN → Abbruch")
        return False
    print(f"   ✅ JA → Payee: '{instance.payee.payee}'")

    # CHECK 3: Ist der Payee ein Transfer?
    print("\n🔸 CHECK 3: Ist der Payee als Transfer markiert?")
    print(f"   Payee-Type: '{instance.payee.payee_type}'")
    if not instance.payee.is_transfer:
        print("   ❌ NEIN (payee_type != 'transfer') → Abbruch")
        print("   💡 HINWEIS: Payee muss payee_type='transfer' haben!")
        return False
    print("   ✅ JA → Ist ein Transfer")

    # CHECK 4: Ist der Payee im Mapping?
    payee_name = instance.payee.payee
    print(f"\n🔸 CHECK 4: Ist '{payee_name}' im TRANSFER_MAPPING?")
    if payee_name not in TRANSFER_MAPPING:
        print("   ❌ NEIN → Abbruch")
        print(f"   Verfügbare Payees im Mapping:")
        for key in TRANSFER_MAPPING.keys():
            print(f"      - {key}")
        return False
    print(f"   ✅ JA → Ziel-Account: '{TRANSFER_MAPPING[payee_name]}'")

    print("\n" + "=" * 70)
    print("✅ ALLE CHECKS BESTANDEN → GEGENBUCHUNG WIRD ERSTELLT")
    print("=" * 70 + "\n")

    return True


def get_counterpart_account_id(payee_name):
    """Ermittelt Account-ID für Gegenbuchung"""
    print("\n🎯 ERMITTLE ZIEL-ACCOUNT")
    print("-" * 70)

    target_account_name = TRANSFER_MAPPING.get(payee_name)
    print(f"📋 Payee: '{payee_name}'")
    print(f"🎯 Ziel-Account Name: '{target_account_name}'")

    if not target_account_name:
        print("❌ FEHLER: Kein Ziel-Account im Mapping gefunden!")
        logger.warning(f"Kein Ziel-Account für Transfer-Payee '{payee_name}' gefunden")
        return None

    try:
        account = DimAccount.objects.get(account=target_account_name)
        print(f"✅ Account gefunden: ID={account.id}, Name='{account.account}'")
        return account.id
    except DimAccount.DoesNotExist:
        print(f"❌ FEHLER: Account '{target_account_name}' existiert nicht in der DB!")
        logger.error(f"Account '{target_account_name}' nicht gefunden")
        return None
    except DimAccount.MultipleObjectsReturned:
        print(f"❌ FEHLER: Mehrere Accounts mit Namen '{target_account_name}' gefunden!")
        logger.error(f"Mehrere Accounts mit Namen '{target_account_name}' gefunden")
        return None


def get_counterpart_payee_id(source_payee_name, source_account):
    """Ermittelt Payee für Gegenbuchung"""
    print("\n🔄 ERMITTLE GEGENBUCHUNGS-PAYEE")
    print("-" * 70)
    print(f"📋 Original Payee: '{source_payee_name}'")
    print(f"🏦 Quell-Account: '{source_account.account}'")

    counterpart_payee_name = COUNTERPART_PAYEE_MAPPING.get(source_payee_name)
    print(f"🔍 Lookup im COUNTERPART_PAYEE_MAPPING...")

    # Spezialfall: Transfer : Girokonto
    if counterpart_payee_name is None and source_payee_name == "Transfer : Girokonto":
        print("⚠️  Spezialfall: 'Transfer : Girokonto' → Reverse Lookup")

        reverse_mapping = {
            'MasterCard': 'Transfer : MasterCard',
            'Pensionsvorsorge Uniqa': 'Transfer : Pensionsvorsorge Uniqa',
            'OnlineSparen': 'Transfer : OnlineSparen',
            'ETF': 'Transfer : ETF',
            'Krypto & Aktien': 'Transfer : Krypto & Aktien',
            'Top4 Fonds & Green Invest': 'Transfer : Top4 Fonds & Green Invest',
            'Bausparer': 'Transfer : Bausparer',
            'Goldanlage': 'Transfer : Goldanlage',
            'Bargeld': 'Transfer : Bargeld',
            'Gutscheine': 'Transfer : Gutscheine',
        }

        counterpart_payee_name = reverse_mapping.get(source_account.account)
        print(f"🔄 Reverse Mapping: '{source_account.account}' → '{counterpart_payee_name}'")

        if not counterpart_payee_name:
            print(f"❌ FEHLER: Keine Reverse-Mapping für '{source_account.account}'!")
            logger.warning(f"Unbekannte Quelle für 'Transfer : Girokonto': {source_account.account}")
            return None

    if not counterpart_payee_name:
        print(f"❌ FEHLER: Kein Gegenstück-Payee definiert!")
        logger.warning(f"Kein Gegenstück-Payee für '{source_payee_name}' definiert")
        return None

    print(f"🎯 Gegenbuchungs-Payee Name: '{counterpart_payee_name}'")

    try:
        payee = DimPayee.objects.get(payee=counterpart_payee_name)
        print(f"✅ Payee gefunden: ID={payee.id}, Name='{payee.payee}'")
        return payee.id
    except DimPayee.DoesNotExist:
        print(f"❌ FEHLER: Payee '{counterpart_payee_name}' existiert nicht in der DB!")
        logger.error(f"Payee '{counterpart_payee_name}' nicht gefunden")
        return None


def create_transfer_counterpart(instance):
    """Erstellt Gegenbuchung für Transfer"""
    print("\n" + "🚀 " * 35)
    print("STARTE ERSTELLUNG DER GEGENBUCHUNG")
    print("🚀 " * 35)

    # Schritt 1: Ziel-Account ermitteln
    target_account_id = get_counterpart_account_id(instance.payee.payee)
    if not target_account_id:
        print("\n❌ ABBRUCH: Ziel-Account konnte nicht ermittelt werden")
        return

    # Schritt 2: Gegenbuchungs-Payee ermitteln
    counterpart_payee_id = get_counterpart_payee_id(
        instance.payee.payee,
        instance.account
    )
    if not counterpart_payee_id:
        print("\n❌ ABBRUCH: Gegenbuchungs-Payee konnte nicht ermittelt werden")
        return

    # Schritt 3: Betrag invertieren
    print("\n💰 INVERTIERE BETRAG")
    print("-" * 70)
    print(f"Original: Outflow={instance.outflow}, Inflow={instance.inflow}")

    counterpart_outflow = Decimal('0')
    counterpart_inflow = Decimal('0')

    if instance.outflow and instance.outflow > 0:
        counterpart_inflow = instance.outflow
        print(f"🔄 Outflow → Inflow: €{instance.outflow} wird zu Inflow €{counterpart_inflow}")
    elif instance.inflow and instance.inflow > 0:
        counterpart_outflow = instance.inflow
        print(f"🔄 Inflow → Outflow: €{instance.inflow} wird zu Outflow €{counterpart_outflow}")

    print(f"✅ Gegenbuchung: Outflow={counterpart_outflow}, Inflow={counterpart_inflow}")

    # Schritt 4: Memo erstellen
    print("\n📝 ERSTELLE MEMO")
    print("-" * 70)
    if instance.memo:
        counterpart_memo = f'{instance.memo} [Auto-Gegenbuchung]'
        print(f"Original Memo: '{instance.memo}'")
    else:
        counterpart_memo = f'Gegenbuchung zu Transfer von {instance.account.account} [Auto-Gegenbuchung]'
        print("Original Memo: (leer)")
    print(f"Neues Memo: '{counterpart_memo}'")

    # Schritt 5: Daten zusammenstellen
    counterpart_data = {
        'account_id': target_account_id,
        'flag_id': instance.flag_id,
        'date': instance.date,
        'payee_id': counterpart_payee_id,
        'category_id': None,
        'memo': counterpart_memo,
        'outflow': counterpart_outflow,
        'inflow': counterpart_inflow,
    }

    print("\n📦 GEGENBUCHUNGS-DATEN")
    print("-" * 70)
    for key, value in counterpart_data.items():
        print(f"   {key:15s}: {value}")

    # Schritt 6: IMMER in die GLEICHE Tabelle wie die Original-Transaktion!
    target_account = DimAccount.objects.get(id=target_account_id)

    print("\n🎯 ERMITTLE ZIELTABELLE")
    print("-" * 70)
    print(f"Ziel-Account: ID={target_account_id}, Name='{target_account.account}'")

    # NEUE LOGIK: Gegenbuchung immer in die GLEICHE Tabelle wie Original!
    if isinstance(instance, FactTransactionsSigi):
        target_table = "fact_transactions_sigi"
        print(f"✅ Original in SIGI → Gegenbuchung auch in SIGI-TABELLE")

        print(f"\n💾 ERSTELLE GEGENBUCHUNG IN {target_table.upper()}")
        print("-" * 70)

        print("⏸️  Deaktiviere Sigi-Signal...")
        post_save.disconnect(handle_sigi_transfer, sender=FactTransactionsSigi)
        try:
            new_transaction = FactTransactionsSigi.objects.create(**counterpart_data)
            print(f"✅ Gegenbuchung erstellt! ID={new_transaction.id}")
            logger.info(f"Gegenbuchung erstellt in Sigi-Tabelle: ID={new_transaction.id}")
        finally:
            print("▶️  Reaktiviere Sigi-Signal...")
            post_save.connect(handle_sigi_transfer, sender=FactTransactionsSigi)

    elif isinstance(instance, FactTransactionsRobert):
        target_table = "fact_transactions_robert"
        print(f"✅ Original in ROBERT → Gegenbuchung auch in ROBERT-TABELLE")

        print(f"\n💾 ERSTELLE GEGENBUCHUNG IN {target_table.upper()}")
        print("-" * 70)

        print("⏸️  Deaktiviere Robert-Signal...")
        post_save.disconnect(handle_robert_transfer, sender=FactTransactionsRobert)
        try:
            new_transaction = FactTransactionsRobert.objects.create(**counterpart_data)
            print(f"✅ Gegenbuchung erstellt! ID={new_transaction.id}")
            logger.info(f"Gegenbuchung erstellt in Robert-Tabelle: ID={new_transaction.id}")
        finally:
            print("▶️  Reaktiviere Robert-Signal...")
            post_save.connect(handle_robert_transfer, sender=FactTransactionsRobert)

    print("\n" + "🎉 " * 35)
    print("GEGENBUCHUNG ERFOLGREICH ERSTELLT!")
    print("🎉 " * 35 + "\n")


@receiver(post_save, sender=FactTransactionsSigi)
def handle_sigi_transfer(sender, instance, created, **kwargs):
    """Erstellt automatisch Gegenbuchungen für Sigi-Transfers"""
    print("\n" + "🔔 " * 35)
    print("SIGNAL EMPFANGEN: FactTransactionsSigi")
    print("🔔 " * 35)
    print(f"Transaktion ID: {instance.id}")
    print(f"Created: {created}")
    print(f"Sender: {sender.__name__}")

    if not created:
        print("⏭️  SKIP: Transaktion wurde nur aktualisiert (created=False)")
        return

    print("✅ Neue Transaktion erstellt → Prüfe auf Transfer...")

    if not should_create_counterpart(instance):
        print("\n⏭️  SKIP: Keine Gegenbuchung nötig")
        return

    try:
        with transaction.atomic():
            create_transfer_counterpart(instance)
            logger.info(f"✓ Transfer-Gegenbuchung erstellt für Transaktion {instance.id}")
    except Exception as e:
        print(f"\n❌❌❌ FEHLER: {str(e)}")
        logger.error(f"✗ Fehler beim Erstellen der Gegenbuchung: {str(e)}")
        import traceback
        traceback.print_exc()


@receiver(post_save, sender=FactTransactionsRobert)
def handle_robert_transfer(sender, instance, created, **kwargs):
    """Erstellt automatisch Gegenbuchungen für Robert-Transfers"""
    print("\n" + "🔔 " * 35)
    print("SIGNAL EMPFANGEN: FactTransactionsRobert")
    print("🔔 " * 35)
    print(f"Transaktion ID: {instance.id}")
    print(f"Created: {created}")
    print(f"Sender: {sender.__name__}")

    if not created:
        print("⏭️  SKIP: Transaktion wurde nur aktualisiert (created=False)")
        return

    print("✅ Neue Transaktion erstellt → Prüfe auf Transfer...")

    if not should_create_counterpart(instance):
        print("\n⏭️  SKIP: Keine Gegenbuchung nötig")
        return

    try:
        with transaction.atomic():
            create_transfer_counterpart(instance)
            logger.info(f"✓ Transfer-Gegenbuchung erstellt für Transaktion {instance.id}")
    except Exception as e:
        print(f"\n❌❌❌ FEHLER: {str(e)}")
        logger.error(f"✗ Fehler beim Erstellen der Gegenbuchung: {str(e)}")
        import traceback
        traceback.print_exc()