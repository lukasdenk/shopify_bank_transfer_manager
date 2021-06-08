import cmd
import logging
import os
import sqlite3
import traceback
from typing import List

from sqlalchemy.orm.exc import NoResultFound

from main.conf import paths
from main import utils, conf
from main.importer import shopify_importer, transactions_importer
from main.db.orm import Transaction, OrderTransaction, Order, update_schemas
from main.importer.shopify_importer import OrderNrNotFound
from main.db.sqlalchemy_utils import count, get
from main.utils import Error


# exceptions
class DBInitError(Error):
    pass


# exceptions (ab)used for processing the user's navigation
class UserExit(Error):
    pass


class UserNextTransaction(Error):
    pass


class IgnoreTransaction(Error):
    pass


class CmdTool(cmd.Cmd):
    intro = 'Programm gestartet. Bitte gib ein Kommando ein. Für Hilfe tippe "help" oder "?"'
    prompt = '-->'

    def __init__(self):
        super().__init__()

    def do_exit(self, arg):
        """Beendet das Programm."""
        return True

    def do_update(self, args):
        """Aktualisiert und downloadet alle Bestellungen, die ab dem Datum "update_after" (in
        main/resources/internal_paras.json) geändert wurden. """
        self.init_db()
        try:
            self.update_orders()
            self.import_transactions()

            suspicious: List[Transaction] = transactions_importer.associate_transactions()
            print()
            try:
                self.user_associate_transactions(suspicious)
            except UserExit:
                pass
            conf.update_update_after()
        except (sqlite3.Error, utils.Error) as e:
            sqlite_msg = ''
            if isinstance(e, sqlite3.Error):
                sqlite_msg = 'SQLite-'
            error_arg = utils.get_error_arg(e)
            msg = f'Ein {sqlite_msg}Fehler wurde entdeckt: ' + error_arg + '.\n' \
                  'ACHTUNG: Einige Änderungen sind eventuell nicht eingearbeitet. Behebe den Fehler ' \
                    'und versuche es erneut.'
            logging.error(f'msg {error_arg}. Traceback:\n'
                          f'{traceback.print_exc()}')
            print(msg)

    def do_associate(self, args):
        """Weise Transaktionen eine oder mehrere Bestellungen zu."""
        self.init_db()
        try:
            print('Weise den Transaktionen Bestellungen zu. Beende mit "s".')
            while True:
                transaction = self.user_get_transaction()
                self.handle_transaction(transaction)
        except UserExit:
            return

    def number_imported_msg(self, model, before):
        print(f'Es wurden {count(model) - before} {model.class_name}en importiert.')

    def update_orders(self):
        before = count(Order)
        shopify_importer.import_all()
        self.number_imported_msg(Order, before)

    def import_transactions(self):
        count_ = count(Transaction)
        try:
            transactions_importer.import_transactions()
        except FileNotFoundError as e:
            print(f'Fehler entdeckt: {utils.get_error_arg(e)}')
        self.number_imported_msg(Transaction, count_)


    def user_associate_transactions(self, unassociated_transactions):
        before = count(OrderTransaction)
        print(
            f'{len(unassociated_transactions)} Transaktionen konnten keiner Bestellung zugeordnet werden. Bitte ordne '
            f'sie manuell zu. Gib die Ordernummer(n) ein, für die die Transaktion bezahlt, z.B. "1000". Um der '
            f'Transaktionen mehrere Bestellungen zuzuweisen, trenne die Nummern mit einem Leerzeichen, z.B.: "1000 '
            f'1001".\n '
            f'Um eine Transaktion zu überspringen, gib "w" ein. Um in Zukunft nicht mehr nach einer Transaktion '
            f'gefragt zu werden, gib "i" ein. '
            f'Um den Vorgang vorzeitig abzuschließen, gib "s" ein.')
        for transaction in unassociated_transactions:
            self.handle_transaction(transaction)
        self.number_imported_msg(OrderTransaction, before)

    def handle_transaction(self, transaction: Transaction):
        print(transaction.description)
        try:
            print(f'Bitte gib die Bestellungen an, die du der Transaktion zuweisen möchtest.')
            while True:
                orders = self.user_get_orders()
                transactions_importer.associate_transaction(transaction, orders, True)
                if transaction.associated_completely:
                    return
                else:
                    print(
                        f'Nur {transaction.associated_amount} Cent der Transaktion wurden zugewiesen, um Bestellungen '
                        f'zu bezahlen. Dabei sind {transaction.unassociated_amount} Cent noch nicht zugewiesen.\n '
                        f'Bitte weise der Transaktion weitere Bestellungen zu oder gib "w" ein, um mit der nächsten '
                        f'Transaktion fortzufahren.')
        except IgnoreTransaction:
            transactions_importer.set_associate_to_false(transaction)
            print(f'Transaktion {transaction} wird in Zukunft beim Zuweisen ignoriert.')
            return
        except UserNextTransaction:
            return

    def user_get_orders(self) -> List[Order]:
        while True:
            answer = input('--> ABI')
            try:
                self.check_user_exit(answer)
                if answer == 'w':
                    print('Nächste Transaktion...')
                    raise UserNextTransaction
                if answer == 'i':
                    raise IgnoreTransaction
                nrs = utils.strip_me(answer.split())
                return shopify_importer.get_orders(nrs)
            except OrderNrNotFound as e:
                print(utils.get_error_arg(e))

    def user_get_transaction(self) -> Transaction:
        print('Welcher Transaktion möchtest du Bestellungen zuweisen?')
        while True:
            answer = input('--> Id (s. Transaktions-Tabelle): ')
            self.check_user_exit(answer)
            try:
                id = int(answer)
                transaction: Transaction = get(Transaction, require_result=True, id=id)
                if transaction.associated_completely:
                    print('Der Betrag der Transaktion wurde bereits komplett zu anderen Bestellungen zugewiesen.')
                else:
                    return transaction
            except (ValueError, NoResultFound) as e:
                logging.error(f'do_zuweisen: {utils.get_error_arg(e)}')
                print(f'"{answer}" ist keine Transaktion')

    def check_user_exit(self, answer):
        if answer == 's':
            print('Zurück zum Hauptmenü.')
            raise UserExit
        
    def init_db(self):
        if not os.path.exists(paths['sqlite']):
            try:
                print(f'Erstelle sqlite-Datenbank in Datei "{paths["sqlite"]}".')
                update_schemas()
            except Exception as e:
                print(f'Erstellen der Datenbank fehlgeschlagen. Fehlermeldung: {utils.get_error_arg(e)}.')
                raise DBInitError()


tool = CmdTool()
tool.cmdloop()

print("Script beendet.")
