"""Compatibility import for :mod:`defirisk.data.peg`."""
from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module(".data.peg", __package__)
