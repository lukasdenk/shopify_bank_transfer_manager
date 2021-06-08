from sqlalchemy import Column, String, Boolean, ForeignKey, Integer, Date, Enum, text, UniqueConstraint
from sqlalchemy import create_engine, select, event
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship, sessionmaker, scoped_session
from main import utils
import datetime, enum

from main.conf import paths, settings

table_names = {'OrderTransaction': 'order_transactions'}

config_url = f'sqlite:///{paths["sqlite"]}?check_same_thread=False'
engine = create_engine(config_url, echo=False)
if 'sqlite' in config_url:
    def _fk_pragma_on_connect(dbapi_con, con_record):  # noqa
        dbapi_con.execute('PRAGMA FOREIGN_KEYS=ON')


    event.listen(engine, 'connect', _fk_pragma_on_connect)

size_names = utils.import_list(f'{paths["resources"]}/sizes.list')
color_names = utils.import_list(f'{paths["resources"]}/colors.list')

Base = declarative_base()


class Sex(enum.Enum):
    FEMALE = 0
    DIVERS = 1
    MALE = 2


# superclass for classes which's name is printed to the user
class NamedClass:
    class_name = 'Stub Name'


class School(Base):
    __tablename__ = 'schools'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)

    products = relationship('Product', back_populates='school')

    def __repr__(self):
        return self.name


class Customer(Base):
    __tablename__ = 'customers'
    id = Column(Integer, primary_key=True, autoincrement=True)
    sex = Column(Enum(Sex))
    shopify_id = Column(Integer, unique=True, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True)

    orders = relationship('Order', back_populates='customer')

    def __repr__(self):
        return self.email


class Address(Base):
    __tablename__ = 'addresses'
    id = Column(Integer, primary_key=True, autoincrement=True)
    # address name may differ from customer.name
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    city = Column(String, nullable=False)
    zip_ = Column(String, nullable=False)
    street = Column(String, nullable=False)
    # house nr is written in additional
    additional = Column(String)

    orders = relationship('Order', back_populates='address')

    def __repr__(self):
        return f'{self.first_name} {self.last_name} {self.city}'


class Order(Base, NamedClass):
    __tablename__ = 'orders'
    class_name = 'Bestellung'

    id = Column(Integer, primary_key=True, autoincrement=True)
    nr = Column(String, unique=True, nullable=False)
    customer_id = Column(Integer, ForeignKey(f'{Customer.__tablename__}.id'), nullable=False)
    address_id = Column(Integer, ForeignKey(f'{Address.__tablename__}.id'), nullable=False)
    created_at = Column(Date, nullable=False)
    discount = Column(Integer, default=0)
    note = Column(String)
    shipping = Column(Integer, default=0)
    decree = Column(Integer, default=0)

    customer = relationship('Customer', back_populates='orders')
    order_transactions = relationship('OrderTransaction', back_populates='order', cascade="all, delete-orphan")
    transactions = relationship("Transaction", secondary=table_names['OrderTransaction'], viewonly=True)
    address = relationship('Address', back_populates='orders')
    line_items = relationship('LineItem', back_populates='order', cascade="all, delete-orphan")
    reminders = relationship('Reminder', back_populates='order', cascade='all, delete-orphan')

    def __init__(self):
        self.discount = 0

    def __repr__(self):
        return self.nr

    @hybrid_property
    def amount(self) -> int:
        return sum(map(lambda li: li.amount * li.quantity, self.line_items)) - self.discount + self.shipping

    @amount.expression
    def amount(cls) -> int:
        select1 = select([func.total(LineItem.amount * LineItem.quantity)]).where(
            LineItem.order_id == cls.id).correlate_except(LineItem).label('amount')
        return select1 - cls.discount + cls.shipping

    @hybrid_property
    def paid_amount(self) -> int:
        return sum(map(lambda to: to.amount, self.order_transactions)) + self.decree

    @paid_amount.expression
    def paid_amount(cls):
        return select([func.total(OrderTransaction.amount)]).where(
            OrderTransaction.order_id == cls.id).correlate_except(OrderTransaction).label('covered') + cls.decree

    @hybrid_property
    def is_paid(self) -> bool:
        return self.paid_amount >= self.amount

    @hybrid_property
    def unpaid_amount(self) -> int:
        return self.amount - self.paid_amount


class Transaction(Base, NamedClass):
    class_name = 'Transaktion'

    __tablename__ = 'transactions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    iban = Column(String, nullable=False)
    reference = Column(String, nullable=False)
    amount = Column(Integer, nullable=False)
    date_ = Column(Date, nullable=False)
    associate = Column(Boolean, default=True)

    __table_args__ = (UniqueConstraint('name', 'iban', 'reference', 'date_', 'amount'),
                      )

    order_transactions = relationship('OrderTransaction', back_populates='transaction', cascade="all, delete-orphan")
    orders = relationship('Order', secondary=table_names['OrderTransaction'], viewonly=True)

    def __str__(self):
        return f'({self.id},{self.name},{self.date_})'

    def __repr__(self):
        return f'({self.name},{self.iban},{self.date_},{self.reference},{self.amount})'

    def __hash__(self):
        return hash(repr(self))

    def __eq__(self, other):
        return type(other) == type(self) and hash(self) == hash(other)

    @hybrid_property
    def associated_amount(self) -> int:
        return sum(map(lambda ot: ot.amount, self.order_transactions))

    @associated_amount.expression
    def associated_amount(cls):
        return select([func.total(OrderTransaction.amount)]).where(OrderTransaction.transaction_id == cls.id).label(
            'associated_amount')

    @hybrid_property
    def associated_completely(self) -> bool:
        if self.amount < self.associated_amount:
            raise ValueError('Transaction associated too much.')
        return self.amount - self.associated_amount == 0

    @associated_completely.expression
    def associated_completely(cls):
        return cls.amount - cls.associated_amount == 0

    @hybrid_property
    def unassociated_amount(self) -> int:
        return self.amount - self.associated_amount

    @property
    def description(self) -> str:
        desc = f'###################\n' \
               f'Transaktion {self}\n' \
               f'\tName: {self.name}\n' \
               f'\tReferenz: {self.reference}\n' \
               f'\tBetrag: {self.amount}'
        if self.orders:
            desc += f'\n\tZugewiesene Bestellungen:'
            details = [f'{order_transaction.order} (Zugewiesen: {order_transaction.amount} Cent)' for order_transaction
                       in self.order_transactions]
            desc += ','.join(details)
        desc += '\n###################'
        return desc


class OrderTransaction(Base, NamedClass):
    class_name = 'Zuweisung'

    __tablename__ = table_names['OrderTransaction']
    order_id = Column(Integer, ForeignKey(f'{Order.__tablename__}.id'), primary_key=True)
    transaction_id = Column(Integer, ForeignKey(f'{Transaction.__tablename__}.id'), primary_key=True)
    amount = Column(Integer, nullable=False)

    order = relationship('Order', back_populates='order_transactions')
    transaction = relationship('Transaction', back_populates='order_transactions')

    def __repr__(self):
        return f'{self.order}-{self.transaction}'


class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True, autoincrement=True)
    school_id = Column(Integer, ForeignKey(f'{School.__tablename__}.id'))
    shopify_id = Column(Integer, unique=True)
    name = Column(String, nullable=False)
    created_at = Column(Date, nullable=False)
    type_ = Column(String)
    active = Column(Boolean, nullable=False)
    # active=Column(Boolean,nullable=False)

    variants = relationship('Variant', back_populates='product', cascade="all, delete-orphan")
    school = relationship('School', back_populates='products')

    def __repr__(self):
        return f'{self.name}'


class Variant(Base):
    __tablename__ = 'variants'
    id = Column(Integer, primary_key=True, autoincrement=True)
    shopify_id = Column(Integer, unique=True)
    product_id = Column(Integer, ForeignKey(f'{Product.__tablename__}.id'), nullable=False)
    size = Column(String)
    color = Column(String)
    active = Column(Boolean, nullable=False)

    product = relationship('Product', back_populates='variants')
    line_items = relationship('LineItem', back_populates='variant')

    def __repr__(self):
        return f'{self.product}-{self.size if self.size is not None else "<keine Größe>"}/{self.color if self.color is not None else "<keine Farbe>"}'

    def __hash__(self):
        return self.shopify_id

    def __eq__(self, other):
        return hash(self) == hash(other) and type(self) == type(other)

    @hybrid_property
    def quantity(self):
        return sum(map(lambda li: li.quantity, self.line_items))

    @quantity.expression
    def quantity(cls):
        return select([func.total(LineItem.quantity)]).where(LineItem.variant_id == cls.id).correlate_except(
            LineItem).label('quantity')


class LineItem(Base):
    __tablename__ = 'line_items'
    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey(f'{Order.__tablename__}.id'), nullable=False)
    variant_id = Column(Integer, ForeignKey(f'{Variant.__tablename__}.id'), nullable=False)
    quantity = Column(Integer, default=1)
    amount = Column(Integer, nullable=False)

    order = relationship('Order', back_populates='line_items')
    variant = relationship('Variant', back_populates='line_items')

    def __init__(self):
        self.quantity = 1

    def __repr__(self):
        return f'{self.order}:{self.variant}'

    @hybrid_property
    def total(self):
        return self.amount * self.quantity


class Reminder(Base):
    __tablename__ = 'reminders'
    id = Column(Integer, primary_key=True, autoincrement=True, )
    date = Column(Date, default=datetime.date.today(), server_default=text("(date('now'))"))
    order_id = Column(Integer, ForeignKey(f'{Order.__tablename__}.id'))

    order = relationship('Order', back_populates='reminders')


def update_schemas():
    Base.metadata.create_all(engine)


session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)
sess = Session()
sess.commit()
