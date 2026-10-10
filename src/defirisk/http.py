"""Compatibility import for :mod:`defirisk.data.http`."""
from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module(".data.http", __package__)
