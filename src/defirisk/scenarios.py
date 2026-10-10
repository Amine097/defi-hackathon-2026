"""Compatibility import for :mod:`defirisk.core.scenarios`."""
from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module(".core.scenarios", __package__)
