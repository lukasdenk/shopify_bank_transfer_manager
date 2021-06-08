import datetime
import logging
from typing import Dict
from typing import Union, List

import shopify
from sqlalchemy.orm.exc import NoResultFound

from main import utils
from main.conf import settings, paths
from main.db.orm import sess, Order, Customer, Address, Product, Variant, LineItem, School, size_names, \
    color_names
from main.db.sqlalchemy_utils import get, get_or_create
from main.utils import to_cent, Error


def activate_shopify_sess():
    shop_url = settings['shop_url']
    api_version = '2020-10'
    password = settings['password']

    shopify_sess = shopify.Session(shop_url, api_version, password)
    shopify.ShopifyResource.activate_session(shopify_sess)


activate_shopify_sess()


class ProductVariantMissing(Error):
    def __init__(self, msg=''):
        super().__init__(msg)


class OrderNrNotFound(Error):
    def __init__(self, msg, nr):
        super().__init__(msg)
        self.nr = nr


def import_all():
    import_products()
    archive_products()
    import_orders()
    void_orders()


def import_products():
    shopify_products: List[shopify.Product] = get_shopify_resources(shopify.Product, status='active')
    for shopify_product in shopify_products:
        update_or_create_product(shopify_product)


def archive_products():
    shopify_products: List[shopify.Product] = get_shopify_resources(shopify.Product, status='archived')
    for shopify_product in shopify_products:
        update_or_create_product(shopify_product, active=False)
    sess.commit()


def import_orders():
    ORDER_NR = 'name'
    AMOUNT = 'total_price'

    shopify_orders = get_shopify_resources(shopify.Order)

    for shopify_order in shopify_orders:
        attributes = shopify_order.attributes
        nr = attributes[ORDER_NR]
        order = get(Order, nr=nr)
        try:
            address = get_or_create_address(attributes['billing_address'])
            if not order:
                customer = get_or_create_customer(shopify_order)
                order = Order()
                order.nr = nr
                order.customer = customer
                order.created_at = to_date(attributes['created_at'])
                order.address = address
                add_line_items(order, shopify_order)
                sess.add(order)
            order.discount = to_cent(attributes.get('total_discounts', 0))
            order.address = address
            order.shipping = to_cent(
                attributes['total_shipping_price_set'].attributes['shop_money'].attributes['amount'])
            tags = get_tags_with_keywords(attributes['tags'])
            # a note the shop owner can make
            if 'name' in tags:
                order.note = tags['name']
            # a note the customer can make
            else:
                NOTE = 'note'
                if NOTE in attributes:
                    order.note = attributes[NOTE]
            sess.commit()
        except ProductVariantMissing as e:
            msg = f'Die Produktvariante der Bestellung {nr} konnte nicht gefunden werden. Die Bestellung wird nicht ' \
                  f'importiert und nicht geupdated. '
            logging.error(msg)
            sess.rollback()
            print(f'ACHTUNG: {msg}\n'
                  f'Grund: {utils.get_error_arg(e)}')


def void_orders():
    shopify_orders = get_shopify_resources(shopify.Order, status='cancelled')
    for shopify_order in shopify_orders:
        name_ = shopify_order.attributes['name']
        try:
            sess.query(Order).filter(Order.nr == name_).delete()
        except Exception as e:
            print(e)
        print(f'Bestellung {name_} hat Status "cancelled" und wird gelöscht.')
        sess.commit()


def get_shopify_resources(shopify_resource, update_after=settings['update_after'], **kwargs) -> List[shopify.ShopifyResource]:
    next_page_url = None
    first = True
    resources = []
    i = 0
    while next_page_url is not None or first:
        if i % 5 == 0 and i != 0:
            print('Downloading resources from Shopify...')
        i += 1

        if first:
            collection = shopify_resource.find(updated_at_min=update_after, **kwargs)
            first = False
        else:
            collection = shopify_resource.find(from_=next_page_url)
        next_page_url = collection.next_page_url
        resources += list(collection)
    return resources


def get_or_create_customer(shopify_order) -> Customer:
    EMAIL = 'email'

    shopify_customer = shopify_order.attributes['customer']
    attributes = shopify_customer.attributes
    customer = get(Customer, shopify_id=shopify_customer.id)
    if customer is None:
        customer = Customer()
        customer.shopify_id = shopify_customer.id
        customer.email = attributes[EMAIL]
        customer.first_name = attributes['first_name']
        customer.last_name = attributes['last_name']

        utils.strip_me(customer)
    return customer


def get_or_create_address(shopify_address: shopify.Address) -> Address:
    attributes = shopify_address.attributes

    first_name = utils.strip_me(attributes['first_name'])
    last_name = utils.strip_me(attributes['last_name'])
    street = utils.strip_me(attributes['address1'])
    address2 = utils.strip_me(attributes['address2'])
    additional = None
    if address2:
        additional = address2
    city = utils.strip_me(attributes['city'])
    zip_ = utils.strip_me(attributes['zip'])
    address = get_or_create(Address, first_name=first_name,
                            last_name=last_name,
                            street=street,
                            additional=additional,
                            city=city,
                            zip_=zip_)
    utils.strip_me(address)

    return address


def get_tags(tag_string) -> List[str]:
    return list(map(str.strip, tag_string.split(',')))


def get_tags_with_keywords(tag_string) -> Dict[str, str]:
    tags = {}
    tags_list = get_tags(tag_string)
    for tag in tags_list:
        if 'name: ' in tag[:6].lower():
            tags['name'] = tag[6:]
        else:
            tags['-'] = tag
    return tags


def get_orders(nrs: List[str]) -> List[Order]:
    if not nrs:
        raise ValueError(f'nrs Parameter darf nicht leer oder None sein.')
    orders = []
    for nr in nrs:
        order_nr = f'ABI{nr}'
        try:
            order = get(Order, require_result=True, nr=order_nr)
            orders += [order]
        except NoResultFound:
            msg = f'Bestellung "{order_nr}" existiert nicht.'
            raise OrderNrNotFound(msg, order_nr)
    return orders


def get_school(shopify_order: shopify.Order) -> Union[School, None]:
    for shopify_line_item in shopify_order.attributes['line_items']:
        product_id = shopify_line_item.attributes['product_id']
        if product_id:
            product: Product = get(Product, shopify_id=int(product_id))
            if product:
                return product.school
    return None


def assure_products(shopify_order: shopify.Order):
    """
    Makes sure that the products in this shopify_order are still existing
    in the shopify database. Otherwise creates a stub.

    """
    for shopify_line_item in shopify_order.attributes['line_items']:
        attributes = shopify_line_item.attributes
        product_id = attributes['product_id']
        title = attributes['title']
        product = get_product(attributes, False)
        if product is None:
            product = Product()
            product.shopify_id = product_id
            if title:
                product.name = title
            else:
                product.name = 'stub'
                stub_msg = f'Für Product "{product}" wurde ein Stub generiert.'
                logging.warning(stub_msg)
                print(f'ACHTUNG: {stub_msg}')
            product.active = False
            product.created_at = datetime.date.today()
            product.school = get_school(shopify_order)

            product.type_ = attributes.get('product_type', None)

            sess.add(product)
            sess.commit()


def assure_variants(shopify_order: shopify.Order):
    """
        Makes sure that the variants in this shopify_order are still existing
        in the shopify database. Otherwise creates a stub.

    """
    for shopify_line_item in shopify_order.attributes['line_items']:
        attributes = shopify_line_item.attributes
        variant = get_variant(attributes, False)
        if variant is None:
            product = get_product(attributes, require_result=True)
            variant = Variant()
            variant_id = attributes['variant_id']
            variant.shopify_id = variant_id
            variant.active = False
            variant.product = product
            variant.size = 'stub'
            variant.color = 'stub'
            sess.add(variant)
            sess.commit()

            stub_msg = f'Für Variante {variant_id} von Product {variant.product} wurde ein Stub generiert.'
            logging.warning(stub_msg)
            print(f'ACHTUNG: {stub_msg}')


def get_variant(attributes, require_result=False):
    variant_id = attributes['variant_id']
    if variant_id:
        variant = get(Variant, require_result=require_result, shopify_id=variant_id)
    # sometimes a variant does not have an id in the shopify db
    else:
        product = get_product(attributes, True)
        variant = get(Variant, require_result=require_result, product=product)
    return variant


def get_product(attributes, require_result=False):
    product_id = attributes['product_id']
    if product_id:
        product = get(Product, require_result=require_result, shopify_id=product_id)
    else:
        product = get(Product, require_result=require_result, name=attributes['title'])
    return product


def add_line_items(order: Order, shopify_order: shopify.Order):
    assure_products(shopify_order)
    assure_variants(shopify_order)
    for shopify_line_item in shopify_order.attributes['line_items']:
        try:
            attributes = shopify_line_item.attributes
            line_item = LineItem()
            line_item.quantity = int(attributes['quantity'])
            line_item.amount = to_cent(attributes['price'])
            variant = get_variant(attributes)
            line_item.variant = variant
            line_item.order = order
        except NoResultFound as e:
            msg = f'Produktvariante konnte nicht gefunden werden. ShopifyID der Variante: {attributes["variant_id"]}.'
            logging.warning(msg)
            print(f'ACHTUNG: {msg}')
            raise e


def update_or_create_product(shopify_product, active=True):
    attributes = shopify_product.attributes
    if shopify_product.id:
        product = get(Product, shopify_id=shopify_product.id)
    else:
        product = get(Product, name=attributes['title'])
    with sess.no_autoflush:
        if product is None:
            product = Product()
            product.shopify_id = shopify_product.id
            sess.add(product)
        product.name = attributes['title']
        product.type_ = attributes['product_type']
        # 'status' is not always in shopify_product.attributes
        product.active = active
        product.created_at = to_date(attributes['created_at'])
        product.variants = get_and_update_or_create_variants(shopify_product, product.variants)
        tags = get_tags(attributes['tags'])
        if len(tags) != 0:
            product.school = get_or_create(School, name=tags[0])
        else:
            print(f'ACHTUNG: No school for product {product}.')
    sess.commit()
    return product


def get_and_update_or_create_variants(shopify_product: shopify.Product, variants: List[Variant]) -> List[Variant]:
    active_variants = set()
    shopify_variants = shopify_product.attributes['variants']
    for shopify_variant in shopify_variants:
        variant = get(Variant, shopify_id=shopify_variant.id)
        if not variant:
            variant = Variant()
            variant.shopify_id = shopify_variant.id

        variant_attributes = shopify_variant.attributes
        # the size (color) of a garment is usually stored in option1(2)
        option1 = variant_attributes['option1']
        option2 = variant_attributes['option2']
        warn_msg = f'ACHTUNG: "{{option}}" in Lineitem "{variant}" ist nicht in "{paths["resources"]}/{{list_}}.list". ' \
                   f'"{{option}}" wird daher nicht als {{attribute}} eingetragen. Ist "{{option}}" doch eine {{' \
                   f'attribute}}, so trage sie bitte in die Liste ein und aktualisiere die Daten erneut. '
        if option1:
            if option1.lower() in size_names:
                variant.size = option1.lower()
            else:
                print(warn_msg.format(option=option1, attribute="Größe", list_='sizes'))
        if option2:
            if option2.lower() in color_names:
                variant.color = option2.lower()
            else:
                print(warn_msg.format(option=option2, attribute='Farbe', list_='colors'))
        variant.active = True
        active_variants |= {variant}
    variants_set = set(variants)
    inactive_variants = variants_set - active_variants
    for variant in inactive_variants:
        variant.active = False

    return list(active_variants | variants_set)


def to_date(date_str: str) -> datetime.date:
    return datetime.date.fromisoformat(date_str[:date_str.find('T')])
