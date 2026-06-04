"""Qlib projection manifest contract.

This module intentionally does not import pyqlib and does not write projection
files. It reexports the canonical temporal manifest dataclass.
"""

from backend.temporal.finance_models import QlibProjectionManifest

__all__ = ["QlibProjectionManifest"]
