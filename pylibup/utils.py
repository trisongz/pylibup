import os
from pathlib import Path
from logz import get_cls_logger

from .types import *

get_logger = get_cls_logger('pylib', 'info')

def exec_shell(cmd): return os.system(cmd)
def get_parent_path(p: str) -> Path: return Path(p).parent
def to_camelcase(string: str) -> str: return ''.join(word.capitalize() for word in string.split('_'))

def to_path(path: Union[str, Path], resolve: bool = True) -> Path:
    if isinstance(path, str): path = Path(path)
    if resolve: path.resolve()
    return path

def set_to_many(value: AnyMany) -> List[Any]:
    if not isinstance(value, list): value = [value]
    return value

def does_text_validate(text: str, include: List[str] = [], exclude: List[str] = [], exact: bool = False, **kwargs) -> bool:
    if not include and not exclude: return True
    _valid = False
    if exclude:
        for ex in exclude:
            if ((exact and ex == text)  or not exact and (ex in text or text in ex)): return False
        _valid = True
    if include:
        for inc in include:
            if ((exact and inc == text) or not exact and (inc in text or text in inc)): return True
    return _valid

def does_text_match(text: str, items: TextMany, exact: bool = False, valArgs: ValidatorArgs = None, **kwargs):
    items = set_to_many(items)
    for i in items:
        if exact and i == text or (text in i or i in text):
            if valArgs: return does_text_validate(i, exact=exact, **ValidatorArgs.dict())
            return True
    return False


__all__ = [
    'get_logger',
    'exec_shell',
    'get_parent_path',
    'to_camelcase',
    'to_path',
    'Path',
    'set_to_many',
    'does_text_match',
    'does_text_validate'
]

