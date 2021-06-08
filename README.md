# Shopify bank transaction manager
## General
This is a command line client for the [Shopify API](https://shopify.dev/docs/admin-api/rest/reference). It associates incoming bank transactions from customers with the shopify orders they paid for.

The tool manages the orders and transactions in an internal database. It does never write anything to the shopify shop.

### Use case
When a customer pays for an order on a shopify shop, shopify automatically marks the order as paid. 
However, these options (to my knowledge) usually cost a fee and thus a shop owner might want to manage payments by her/himself by only allowing bank transactions. 

The client was written for a small shop which mainly sells clothes.




## Installation
1. Clone this repository.
2. Install [Python 3.9](https://www.python.org/downloads/release/python-390/).
3. Create a [Python virtual environment](https://docs.python.org/3.8/library/venv.html) and activate it.
4. Install the dependencies with `pip install -r <path-to-this-project>/resources/requirements.txt`.

## Configuration
`./resources/settings.json` stores the configurations. Here, you must specify your shop's web address. Also, you need to create a [Shopify private app](https://help.shopify.com/en/manual/apps/private-apps) and store its password in the `settings.json` file. 

## Start
To start the tool, first make sure that the virtual environment is still activated and you are in the directory of this project. Now type `python -m main.shopify_bank_transfer_manager`.  
To see all of the tool's commands, type `help`. To get a more detailed description of a command, type `help <command>`.

## Commands

### Update
Does the following:
1. Downloads the orders from the Shopify API and imports the bank transactions given in a CSV file.
2. Internally stores both, the orders and transactions, in a SQLite database.
3. Tries to retrieve order IDs from the transactions' references. It does so by matching certain patterns. These patterns can be modified in `importer.transactions_importer::get_order_nrs`.  
   If it can retrieve any order IDs, it tries to mark these orders as paid by the transaction.    
   To do so, it creates an association in the database, consisting of the order ID, the transaction ID and an amount. The association means that transaction ``x`` pays amount ``y`` to order ``z``. Of course, the amount associated to a transaction can never exceed the amount of the transaction.
4. Finally, it asks the user to manually associate the remaining transactions. These are all the transactions, which could not be associated automatically. 

### Associate
Allows the user to manually associate a transaction with one or more orders.

### Exit
Exits the program.

## Querying the database
Some useful queries are already prepared in `./queries.sql`.


## Credits
Lukas Denk (lukasdenk@web.de)
