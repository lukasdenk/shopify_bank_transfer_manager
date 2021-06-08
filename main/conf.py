import json
import logging
import os
from datetime import datetime, timedelta, date

UPDATE_AFTER = 'update_after'

# project paths
paths = {'project': os.path.abspath(f'{os.path.dirname(__file__)}/..')}
paths['resources'] = f'{paths["project"]}/resources'
paths['main'] = f'{paths["project"]}/main'
paths['sqlite'] = f'{paths["resources"]}/db.sqlite'
paths['internal_paras'] = f'{paths["resources"]}/internal_paras.json'
paths['settings'] = f'{paths["resources"]}/settings.json'
paths['transactions'] = f'{paths["resources"]}/transactions'

# project settings
with open(paths['internal_paras'], encoding='utf-8') as f:
    settings = json.load(f)
with open(paths['settings'], encoding='utf-8') as f:
    # overwrites internal paras if there are duplicates
    settings = dict(settings, **json.load(f))

update_after = settings['update_after']
password = settings['password']

# config loggers
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.CRITICAL)
console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
file_handler = logging.FileHandler(f'{paths["resources"]}/logging.log', 'w')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s: %(levelname)s: %(message)s'))
handlers = [console_handler, file_handler]

logging.basicConfig(handlers=handlers, level=logging.INFO)


def to_date(date_str) -> date:
    return datetime.strptime(date_str, '%Y-%m-%d').date()


def update_update_after():
    internal_paras = {UPDATE_AFTER: (date.today() - timedelta(2)).strftime('%Y-%m-%d')}
    with open(paths['internal_paras'], 'w', encoding='utf-8') as f:
        json.dump(internal_paras, f)
