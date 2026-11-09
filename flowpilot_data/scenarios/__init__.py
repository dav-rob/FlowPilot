"""Scenario families. Importing this package registers all families."""
from . import base  # noqa: F401
from .base import FAMILIES  # noqa: F401
import importlib

for _m in ("fraud", "compliance", "gdpr", "itasset", "contract", "cross", "distractor"):
    try:
        importlib.import_module(f"{__name__}.{_m}")
    except ModuleNotFoundError as e:  # during incremental development only
        if e.name != f"{__name__}.{_m}":
            raise
