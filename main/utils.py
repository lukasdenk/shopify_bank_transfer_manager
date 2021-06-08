import logging
import os
import re
from typing import Iterable, List


class Error(Exception):
    def __init__(self, msg=''):
        self.msg = msg

    def __str__(self):
        return self.msg


def iterable_to_str(iter: Iterable):
    if iter:
        return ','.join(map(object.__str__, iter))
    else:
        return '<leer>'


def get_error_arg(e):
    if e.args:
        return e.args[0]
    else:
        return ''


def strip_me(obj):
    """
    Removes whitespaces from a string or elements in a list or dict

    """
    if isinstance(obj, List):
        return [strip_me(o) for o in obj]
    if isinstance(obj, str):
        return obj.strip()
    if isinstance(obj, dict):
        for var, val in vars(obj).items():
            if isinstance(val, str):
                setattr(obj, var, val.strip())
    return obj


def import_list(file, to_lower=True):
    if '.list' != file[-5:]:
        raise ValueError(f'{file} is no "*.list" file')
    format_ = str.strip
    if to_lower:
        format_ = lambda s: s.strip().lower()
    with open(file, encoding='utf-8') as f:
        return set(map(format_, filter(lambda s: s and not s.isspace(), f.readlines())))


def to_cent(nr) -> int:
    match = re.match(r'-?(\d+)(\.(\d)(\d)?)?', nr)
    val = int(match.group(1)) * 100
    if match.group(3):
        val += int(match.group(3)) * 10
        if match.group(4):
            val += int(match.group(4))
    if nr[0] == '-':
        sign = -1
    else:
        sign = 1
    return sign * val
