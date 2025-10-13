# finance/signals.py
"""
Automatische Gegenbuchungen für Transfer-Transaktionen
Wird nach dem Speichern einer Transaktion automatisch ausgeführt
"""
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

# ⚠️ WICHTIG: Account-Namen müssen EXAKT mit deiner DB übereinstimmen!
# Bitte hier deine echten Account-Namen eintragen:
# Du findest sie in: SELECT DISTINCT account FROM finance.dim_account;

# Mapping: Transfer-Payee → Ziel-Account-Name für Gegenbuchung
TRANSFER_MAPPING = {
    # Von Girokonto zu anderen Konten
    'Transfer : MasterCard': 'MasterCard',  # ← Anpassen an deinen echten Account-Namen
    'Transfer : Pensionsvorsorge Uniqa': 'Pensionsvorsorge Uniqa',
    'Transfer : OnlineSparen': 'OnlineSparen',
    'Transfer : ETF': 'ETF',
    'Transfer : Krypto & Aktien': 'Krypto & Aktien',
    'Transfer : Top4 Fonds & Green Invest': 'Top4 Fonds & Green Invest',
    'Transfer : Bausparer': 'Bausparer',
    'Transfer : Goldanlage': 'Goldanlage',
    'Transfer : Bargeld': 'Bargeld',
    'Transfer : Gutscheine': 'Gutscheine',

    # Rücktransfers zum Girokonto
    'Transfer : Girokonto': 'Girokonto',
}

# Gegenstück-Payees: Welcher Payee soll in der Gegenbuchung verwendet werden?
COUNTERPART_PAYEE_MAPPING = {
    # Von Giro zu anderen → Gegenbuchung bekommt "Transfer: Giro"
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

    # Von anderen zu Giro → Wird dynamisch gesetzt
    'Transfer : Girokonto': None,
}


def should_create_counterpart(instance):
    """
    Prüft ob für diese Transaktion eine Gegenbuchung erstellt werden soll

    Returns:
        bool: True wenn Gegenbuchung nötig
    """
    # Nur für Transfers
    if not instance.payee or not instance.payee.is_transfer:
        return False

    # Prüfe ob Payee in unserem Mapping ist
    payee_name = instance.payee.payee
    if payee_name not in TRANSFER_MAPPING:
        return False

    return True


def get_counterpart_account_id(payee_name):
    """
    Ermittelt die Account-ID für die Gegenbuchung basierend auf Payee

    Args:
        payee_name: Name des Payees (z.B. "Transfer: Master")

    Returns:
        int: Account-ID oder None
    """
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
    """
    Ermittelt den Payee für die Gegenbuchung

    Args:
        source_payee_name: Original Payee-Name (z.B. "Transfer : 💳 MasterCard")
        source_account: Original Account-Objekt

    Returns:
        int: Payee-ID oder None
    """
    # Standard-Mapping verwenden
    counterpart_payee_name = COUNTERPART_PAYEE_MAPPING.get(source_payee_name)

    # Spezialfall: "Transfer : 📱 Girokonto" → muss dynamisch sein
    # Reverse-Mapping: Account-Name → Transfer-Payee-Name
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
            logger.warning(
                f"Unbekannte Quelle für 'Transfer : 📱 Girokonto': {source_account.account}"
            )
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
    """
    Erstellt die Gegenbuchung für eine Transfer-Transaktion

    Args:
        instance: Die Original-Transaktion (FactTransactionsSigi oder FactTransactionsRobert)
    """
    # Ermittle Ziel-Account
    target_account_id = get_counterpart_account_id(instance.payee.payee)
    if not target_account_id:
        return

    # Ermittle Gegenstück-Payee
    counterpart_payee_id = get_counterpart_payee_id(
        instance.payee.payee,
        instance.account
    )
    if not counterpart_payee_id:
        return

    # Betrag invertieren: Outflow → Inflow und umgekehrt
    counterpart_outflow = Decimal('0')
    counterpart_inflow = Decimal('0')

    if instance.outflow and instance.outflow > 0:
        counterpart_inflow = instance.outflow
    elif instance.inflow and instance.inflow > 0:
        counterpart_outflow = instance.inflow

    # Erstelle Gegenbuchung
    counterpart_data = {
        'account_id': target_account_id,
        'flag_id': instance.flag_id,
        'date': instance.date,
        'payee_id': counterpart_payee_id,
        'category_id': None,  # Transfers haben keine Kategorie
        'memo': instance.memo or f'Gegenbuchung zu Transfer von {instance.account.account}',
        'outflow': counterpart_outflow,
        'inflow': counterpart_inflow,
    }

    # Entscheide in welche Tabelle geschrieben werden soll
    # Regel: Wenn Ziel-Account "MasterCard" ist → Robert-Tabelle
    # Alle anderen → Sigi-Tabelle
    target_account = DimAccount.objects.get(id=target_account_id)

    # ⚠️ WICHTIG: Passe diese Liste an deine Robert-Accounts an!
    # Robert's Account ID ist vermutlich 18, aber prüfe das:
    # SELECT id, account FROM finance.dim_account WHERE account LIKE '%Robert%' OR account LIKE '%Master%';
    robert_account_ids = [18]  # ← Hier deine Robert-Account-IDs eintragen
    robert_account_names = ['MasterCard', "Robert's Ausgaben"]  # ← Hier deine Robert-Account-Namen

    if target_account_id in robert_account_ids or target_account.account in robert_account_names:
        FactTransactionsRobert.objects.create(**counterpart_data)
        logger.info(f"Gegenbuchung erstellt in Robert-Tabelle: {counterpart_data}")
    else:
        FactTransactionsSigi.objects.create(**counterpart_data)
        logger.info(f"Gegenbuchung erstellt in Sigi-Tabelle: {counterpart_data}")


# Signal-Handler für Sigi-Transaktionen
@receiver(post_save, sender=FactTransactionsSigi)
def handle_sigi_transfer(sender, instance, created, **kwargs):
    """
    Erstellt automatisch Gegenbuchungen für Sigi-Transfers
    """
    # Nur bei neuen Transaktionen
    if not created:
        return

    # Verhindere Rekursion: Wenn bereits eine Gegenbuchung erstellt wird
    if getattr(instance, '_creating_counterpart', False):
        return

    # Prüfe ob Gegenbuchung nötig
    if not should_create_counterpart(instance):
        return

    # Setze Flag um Rekursion zu verhindern
    instance._creating_counterpart = True

    try:
        with transaction.atomic():
            create_transfer_counterpart(instance)
            logger.info(f"✓ Transfer-Gegenbuchung erstellt für Transaktion {instance.id}")
    except Exception as e:
        logger.error(f"✗ Fehler beim Erstellen der Gegenbuchung: {str(e)}")
    finally:
        instance._creating_counterpart = False


# Signal-Handler für Robert-Transaktionen
@receiver(post_save, sender=FactTransactionsRobert)
def handle_robert_transfer(sender, instance, created, **kwargs):
    """
    Erstellt automatisch Gegenbuchungen für Robert-Transfers
    """
    # Nur bei neuen Transaktionen
    if not created:
        return

    # Verhindere Rekursion
    if getattr(instance, '_creating_counterpart', False):
        return

    # Prüfe ob Gegenbuchung nötig
    if not should_create_counterpart(instance):
        return

    # Setze Flag um Rekursion zu verhindern
    instance._creating_counterpart = True

    try:
        with transaction.atomic():
            create_transfer_counterpart(instance)
            logger.info(f"✓ Transfer-Gegenbuchung erstellt für Transaktion {instance.id}")
    except Exception as e:
        logger.error(f"✗ Fehler beim Erstellen der Gegenbuchung: {str(e)}")
    finally:
        instance._creating_counterpart = False