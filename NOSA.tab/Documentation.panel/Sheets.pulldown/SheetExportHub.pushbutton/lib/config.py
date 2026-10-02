# -*- coding: utf-8 -*-
import os
import json
from Autodesk.Revit import DB
from System.Drawing import Color

class Config:
    """Configuración global para SheetExportHub"""
    VERSION = "1.0.0"

    PROFILES_DIR = os.path.join(
        os.getenv('APPDATA'),
        'pyRevit',
        'Extensions',
        'NOSA.extension',
        'NOSA_Configs',
        'SheetExportHub',
        'Profiles'
    )

    VIEWSETS_DIR = os.path.join(
        os.getenv('APPDATA'),
        'pyRevit',
        'Extensions',
        'NOSA.extension',
        'NOSA_Configs',
        'SheetExportHub',
        'ViewSets'
    )

    NAMING_PROFILES_DIR = os.path.join(
        os.getenv('APPDATA'),
        'pyRevit',
        'Extensions',
        'NOSA.extension',
        'NOSA_Configs',
        'SheetExportHub',
        'NamingProfiles'
    )

    EXPORT_PRESETS_DIR = os.path.join(
        os.getenv('APPDATA'),
        'pyRevit',
        'Extensions',
        'NOSA.extension',
        'NOSA_Configs',
        'SheetExportHub',
        'ExportPresets'
    )

    COLUMN_PRESETS_DIR = os.path.join(
        os.getenv('APPDATA'),
        'pyRevit',
        'Extensions',
        'NOSA.extension',
        'NOSA_Configs',
        'SheetExportHub',
        'ColumnPresets'
    )

    LAST_CONFIG_FILE = os.path.join(PROFILES_DIR, "_last_config.json")
    RECENT_EXPORTS_FILE = os.path.join(PROFILES_DIR, "_recent_exports.json")
    THEME_FILE = os.path.join(PROFILES_DIR, "_theme_settings.json")
    LANGUAGE_FILE = os.path.join(PROFILES_DIR, "_language_settings.json")

    # Ensure directories exist
    @classmethod
    def ensure_dirs(cls):
        for dir_path in [cls.PROFILES_DIR, cls.VIEWSETS_DIR, cls.NAMING_PROFILES_DIR,
                          cls.EXPORT_PRESETS_DIR, cls.COLUMN_PRESETS_DIR]:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)

    DEFAULT_SEPARATOR = "-"

    PAPER_SIZES = {
        "A0": (841, 1189),
        "A1": (594, 841),
        "A2": (420, 594),
        "A3": (297, 420),
        "A4": (210, 297),
        "A5": (148, 210),
        "Letter": (216, 279),
        "Legal": (216, 356),
        "Tabloid": (279, 432),
        "Arch A": (229, 305),
        "Arch B": (305, 457),
        "Arch C": (457, 610),
        "Arch D": (610, 914),
        "Arch E": (914, 1219),
        "Arch E1": (762, 1067)
    }

    # Presets optimizados basados en Diroots Prosheets.
    # Enum member names only: Revit enums are resolved in preset(), never at import time.
    _PRESET_SPECS = {
        'Quick':    ('Presentation', 'R2013', 'TrueColor'),
        'Standard': ('High',         'R2018', 'TrueColorPerView'),
        'Print':    ('Presentation', 'R2018', 'TrueColorPerView'),
    }

    @classmethod
    def preset(cls, name):
        """Export settings for a preset name; unknown names fall back to Standard."""
        if name not in cls._PRESET_SPECS:
            name = 'Standard'
        quality, acad, colors = cls._PRESET_SPECS[name]
        return {
            'name': name,
            'pdf_raster_quality': getattr(DB.RasterQualityType, quality),
            'pdf_color_depth': DB.ColorDepthType.Color,
            'dwg_version': getattr(DB.ACADVersion, acad),
            'dwg_colors': getattr(DB.ExportColorMode, colors),
        }

# Run directory check on import (plain filesystem, no Revit API); never break the import
try:
    Config.ensure_dirs()
except Exception:  # nosa-lint: disable=NOSA006 - each save reports its own IO error
    pass
