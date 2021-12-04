from . import base
from . import app

from .base import baseCli
from .app import repoCli, stateCli

baseCli.add_typer(repoCli)
baseCli.add_typer(stateCli)
