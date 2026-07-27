# -*- coding: utf-8 -*-
"""
NOSA Utils — shared utility library for the NOSA pyRevit Extension.
"""

__version__ = "2.0.0"
__author__  = "A. Viñas"

# Core infrastructure (Bloque 1)
from . import bootstrap
from . import compat
from . import collectors
from . import transactions
from . import telemetry
from . import progress

# Revit API helpers
from . import revit_helpers

# Config / state
from . import config_manager
from . import export_io

# UI
from . import base_window
from . import theme

# Shared domain helpers
from . import sheet_protocol
from . import param_element_ops
from . import text_utils
from . import unit_conversion
from . import geometry

# Logging / usage
from . import logging        # legacy name kept for compatibility
from . import usage

# Misc
from . import ui_helpers
from . import loader         # kept for backward compat (wraps bootstrap)

__all__ = [
    # Bloque 1 infrastructure
    'bootstrap', 'compat', 'collectors', 'transactions', 'telemetry', 'progress',
    # Revit
    'revit_helpers',
    # Config
    'config_manager', 'export_io',
    # UI
    'base_window', 'theme',
    # Domain
    'sheet_protocol', 'param_element_ops', 'text_utils', 'unit_conversion', 'geometry',
    # Logging
    'logging', 'usage',
    # Misc
    'ui_helpers', 'loader',
]
