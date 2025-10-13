# finance/signals.py - AKTUALISIERTE VERSION

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
    # WICHTIG: Prüfe ob es bereits eine automatisch erstellte Gegenbuchung ist
    if instance.memo and '[Auto-Gegenbuchung]' in instance.memo:  # ← GEÄNDERT
        return False

    if not instance.payee or not instance.payee.is_transfer:
        return False

    payee_name = instance.payee.payee
    if payee_name not in TRANSFER_MAPPING:
        return False

    return True


def get_counterpart_account_id(payee_name):
    """Ermittelt Account-ID für Gegenbuchung"""
    target_account_name = TRANSFER_MAPPING.get(payee_name)

    if not target_account_name:
        logger.warning(f"Kein Ziel-Account für Transfer-Payee '{payee_name}' gefunden")
        return None

    try:
        account = DimAccount.objects.get(account=target_account_name)
        return account.id
    except DimAccount.DoesNotExist:
        logger.error(f"Account '{target_account_name}' nicht gefunden")
        return None
    except DimAccount.MultipleObjectsReturned:
        logger.error(f"Mehrere Accounts mit Namen '{target_account_name}' gefunden")
        return None


def get_counterpart_payee_id(source_payee_name, source_account):
    """Ermittelt Payee für Gegenbuchung"""
    counterpart_payee_name = COUNTERPART_PAYEE_MAPPING.get(source_payee_name)

    if counterpart_payee_name is None and source_payee_name == "Transfer : Girokonto":
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

        if not counterpart_payee_name:
            logger.warning(f"Unbekannte Quelle für 'Transfer : Girokonto': {source_account.account}")
            return None

    if not counterpart_payee_name:
        logger.warning(f"Kein Gegenstück-Payee für '{source_payee_name}' definiert")
        return None

    try:
        payee = DimPayee.objects.get(payee=counterpart_payee_name)
        return payee.id
    except DimPayee.DoesNotExist:
        logger.error(f"Payee '{counterpart_payee_name}' nicht gefunden")
        return None


def create_transfer_counterpart(instance):
    """Erstellt Gegenbuchung für Transfer"""
    target_account_id = get_counterpart_account_id(instance.payee.payee)
    if not target_account_id:
        return

    counterpart_payee_id = get_counterpart_payee_id(
        instance.payee.payee,
        instance.account
    )
    if not counterpart_payee_id:
        return

    # Betrag invertieren
    counterpart_outflow = Decimal('0')
    counterpart_inflow = Decimal('0')

    if instance.outflow and instance.outflow > 0:
        counterpart_inflow = instance.outflow
    elif instance.inflow and instance.inflow > 0:
        counterpart_outflow = instance.inflow

    # Memo: Original-Memo beibehalten + Hinweis auf Auto-Gegenbuchung
    if instance.memo:
        counterpart_memo = f'{instance.memo} [Auto-Gegenbuchung]'
    else:
        counterpart_memo = f'Gegenbuchung zu Transfer von {instance.account.account}'

    # Erstelle Gegenbuchung
    counterpart_data = {
        'account_id': target_account_id,
        'flag_id': instance.flag_id,
        'date': instance.date,
        'payee_id': counterpart_payee_id,
        'category_id': None,
        'memo': counterpart_memo,  # ← GEÄNDERT
        'outflow': counterpart_outflow,
        'inflow': counterpart_inflow,
    }

    # Entscheide Zieltabelle
    target_account = DimAccount.objects.get(id=target_account_id)
    robert_account_ids = [18]
    robert_account_names = ['MasterCard', "Robert's Ausgaben"]

    # KRITISCH: Deaktiviere Signals während der Erstellung!
    if target_account_id in robert_account_ids or target_account.account in robert_account_names:
        post_save.disconnect(handle_robert_transfer, sender=FactTransactionsRobert)
        try:
            FactTransactionsRobert.objects.create(**counterpart_data)
            logger.info(f"Gegenbuchung erstellt in Robert-Tabelle")
        finally:
            post_save.connect(handle_robert_transfer, sender=FactTransactionsRobert)
    else:
        post_save.disconnect(handle_sigi_transfer, sender=FactTransactionsSigi)
        try:
            FactTransactionsSigi.objects.create(**counterpart_data)
            logger.info(f"Gegenbuchung erstellt in Sigi-Tabelle")
        finally:
            post_save.connect(handle_sigi_transfer, sender=FactTransactionsSigi)

@receiver(post_save, sender=FactTransactionsSigi)
def handle_sigi_transfer(sender, instance, created, **kwargs):
    """Erstellt automatisch Gegenbuchungen für Sigi-Transfers"""
    if not created:
        return

    if not should_create_counterpart(instance):
        return

    try:
        with transaction.atomic():
            create_transfer_counterpart(instance)
            logger.info(f"✓ Transfer-Gegenbuchung erstellt für Transaktion {instance.id}")
    except Exception as e:
        logger.error(f"✗ Fehler beim Erstellen der Gegenbuchung: {str(e)}")


@receiver(post_save, sender=FactTransactionsRobert)
def handle_robert_transfer(sender, instance, created, **kwargs):
    """Erstellt automatisch Gegenbuchungen für Robert-Transfers"""
    if not created:
        return

    if not should_create_counterpart(instance):
        return

    try:
        with transaction.atomic():
            create_transfer_counterpart(instance)
            logger.info(f"✓ Transfer-Gegenbuchung erstellt für Transaktion {instance.id}")
    except Exception as e:
        logger.error(f"✗ Fehler beim Erstellen der Gegenbuchung: {str(e)}")