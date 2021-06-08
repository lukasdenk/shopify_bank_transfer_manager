from sqlalchemy.orm import Query
import sqlite3

from main.db.orm import sess
from main import conf


def exists(model, **kwargs) -> bool:
    return get(model,  **kwargs) is not None


def get(model, require_result=False, autoflush=True, **kwargs):
    q = Query((model,),sess).filter_by(**kwargs)
    if not autoflush:
        q.autoflush(False)
    if require_result:
        return q.one()
    else:
        return q.first()


def get_or_create(model,**kwargs):
    instance = get(model,**kwargs)
    if not instance:
        instance = model(**kwargs)
        sess.add(instance)
    return instance


def count(model) -> int:
    return len(sess.query(model).all())
