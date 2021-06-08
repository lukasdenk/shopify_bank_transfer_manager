import csv
import logging
import os
import re
import sqlite3
from datetime import datetime
from typing import List, Set

import sqlalchemy

from main import utils
from main.conf import paths, settings
from main.db.orm import Transaction, OrderTransaction, Order, sess
from main.utils import Error
from main.utils import to_cent


class UnexpectedOrderAmountSum(Error):
    def __init__(self, msg):
        super(msg)


def import_transactions():
    filepath = get_trasaction_file()

    INDEX = 'Index'
    AMOUNT = 'Amount'
    PAYMENT_REFERENCE = 'Payment reference'
    NAME = 'Counterparty'
    IBAN = 'Account number'
    print(f'Transaktionen in Datei "{filepath}" werden importiert.')

    with open(filepath, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        print(f'Importiere alle Transaktionen.')
        for row in reader:
            index_ = int(row[INDEX])
            try:
                amount = convert_number(row[AMOUNT])
            except ValueError as e:
                print(f'CSV-Datei-Index {index_}: {row[AMOUNT]} konnte nicht zu einer Zahl formatiert werden.')
                raise e
            date_ = datetime.strptime(row['Valuta Date'], '%d/%m/%Y').date()
            if amount > 0:
                try:
                    transaction = Transaction()
                    transaction.amount = amount
                    transaction.reference = row[PAYMENT_REFERENCE]
                    transaction.name = row[NAME]
                    transaction.iban = row[IBAN]
                    transaction.date_ = date_
                    sess.add(transaction)
                    sess.commit()
                    logging.info(f'{transaction} hinzugefügt.')
                except (sqlite3.IntegrityError, sqlalchemy.exc.IntegrityError):
                    sess.rollback()
                    logging.info(f'{transaction} bereits importiert.')


def get_trasaction_file() -> str:
    TRANSACTION_FILE_KEYWORD = 'transaction'
    transaction_files = list(
        filter(lambda name: TRANSACTION_FILE_KEYWORD in name.lower(), os.listdir(paths['transactions'])))
    if not transaction_files:
        raise FileNotFoundError('Bitte speichere eine Datei, deren Namen {TRANSACTION_FILE_KEYWORD} enthält im Ordner '
                                '" ' + paths["transactions"] + '".')

    return f'{paths["transactions"]}/{transaction_files[0]}'


def associate_transactions() -> List[Transaction]:
    """
    Tries to automatically associate the database's transactions to the orders they paid for.
    It does so by analysing a transaction's reference.

    Returns:
        Transactions which could not be automatically imported AND have the associate flag set to True.

    """
    transactions: List[Transaction] = sess.query(Transaction).filter(
        Transaction.associated_completely == False,
        Transaction.associate == True).all()
    problematic_transactions = []
    for transaction in transactions:
        nrs = get_order_nrs(transaction.reference)
        orders = sess.query(Order).filter(Order.nr.in_(nrs)).all()
        if len(orders) == len(nrs):
            if len(orders) != 0:
                associate_transaction(transaction, orders, False)
                if transaction.unassociated_amount > 0:
                    logging.warning(
                        f'{transaction.unassociated_amount} Cent der Transaktion konnten keiner Bestellung zugewiesen werden.')
                    if transaction.unassociated_amount > 100:
                        problematic_transactions += [transaction]
            else:
                logging.info(f'In der Transaktion {transaction} konnte keine Bestellnr. gefunden werden.')
                problematic_transactions += [transaction]
        else:
            logging.info(f'Eine Bestellung in Transaktion {transaction} konnte nicht gefunden werden.'
                         f' Referenzierte Bestellungen: {nrs}.')
            problematic_transactions += [transaction]

    sess.commit()
    return problematic_transactions


def associate_transaction(transaction: Transaction, orders: List[Order], detailed=False, user_mode=True):
    remaining = transaction.unassociated_amount
    for order in orders:
        if remaining > 0 and order.unpaid_amount > 0:
            paying = min(order.unpaid_amount, remaining)
            remaining -= paying
            # order.uncovered changes when order_transaction.amount is added
            uncovered = order.unpaid_amount
            order_transaction = OrderTransaction()
            order_transaction.order = order
            order_transaction.amount = paying
            order_transaction.transaction = transaction
            sess.add(order_transaction)
            msg = f'\tTransaktion {transaction} bezahlt {paying} Cent für Bestellung {order}.'
            if detailed:
                print(f'INFO: {msg}')
            else:
                logging.info(msg)
            if paying != uncovered:
                # If the customer paid for an order except for a small amount, the remaining amount is decreed.
                # The amount can be set in settings -> "ignore_missing_payment_max"
                if order.unpaid_amount <= settings['ignore_missing_payment_max']:
                    order.decree = order.unpaid_amount
                    print(f'ACHTUNG: Der Bestellung {order} wurden {order.decree} Cent erlassen.')
                else:
                    print(
                        f'ACHTUNG: Transaktion {transaction} kann die Bestellung {order} nicht komplett bezahlen. Es '
                        f'fehlen noch {order.unpaid_amount} Cent.')
            sess.commit()
        elif order.unpaid_amount == 0:
            if user_mode:
                print(f'ACHTUNG: Bestellung {order} wurde bereits bezahlt.')
        elif transaction.unassociated_amount == 0:
            print(
                f'ACHTUNG: Bestellung {order} kann nicht mehr bezahlt werden. Die zur Transaktion zugewiesenen '
                f'Bestellungen schöpfen bereits den Betrag der Transaktion aus. Zugewiesene Bestellungen: '
                f'{utils.iterable_to_str(transaction.orders)}.')
        else:
            raise Error('Should not happen-Error.')
    sess.commit()


def set_associate_to_false(transaction: Transaction):
    transaction.associate = False
    sess.commit()


def convert_number(number):
    number = number.replace(',', '')
    return to_cent(number)


def get_order_nrs(reference) -> Set[str]:
    orders = set()
    if re.search(r"ABI\d{4}\d?", reference, re.IGNORECASE):
        orders |= set(re.findall(r"ABI\d{4}\d?", reference, re.IGNORECASE))
    if re.search(r"ABI \d{4}\d?", reference, re.IGNORECASE):
        order_nr = re.findall(r"ABI \d{4}d?", reference, re.IGNORECASE)
        orders |= set([o.replace(" ", "") for o in order_nr])
    if re.search(r"AB/\d{4}\d?", reference, re.IGNORECASE):
        order_nr = re.findall(r"AB/\d{4}d?", reference, re.IGNORECASE)
        orders |= set([o.replace("/", "I") for o in order_nr])
    if len(orders) != 0:
        return set(map(str.upper, orders))
    return orders
