# -*- coding: utf-8 -*-
"""
NOSA Utils - Shared utility library for NOSA pyRevit Extension
Version: 1.0.0
Author: Antonio Viñas

This package provides common functionality used across multiple NOSA scripts.
"""

__version__ = "1.0.0"
__author__ = "Antonio Viñas"

# Import main modules for easy access
from . import geometry
from . import unit_conversion
from . import ui_helpers
from . import revit_helpers
from . import config_manager
from . import text_utils
from . import loader

__all__ = [
    'geometry',
    'unit_conversion',
    'ui_helpers',
    'revit_helpers',
    'config_manager',
    'text_utils',
    'loader',
]
