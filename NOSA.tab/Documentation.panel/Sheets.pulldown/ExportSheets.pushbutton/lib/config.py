# -*- coding: utf-8 -*-
import os
import json
from pyrevit import DB
from System.Drawing import Color

class Config:
    """Configuración global optimizada para Export Sheets Pro"""
    VERSION = "4.2.0-OPTIMIZED"
    
    PROFILES_DIR = os.path.join(
        os.getenv('APPDATA'), 
        'pyRevit', 
        'Extensions', 
        'ExportSheetsPro', 
        'Profiles'
    )
    
    VIEWSETS_DIR = os.path.join(
        os.getenv('APPDATA'), 
        'pyRevit', 
        'Extensions', 
        'ExportSheetsPro', 
        'ViewSets'
    )
    
    NAMING_PROFILES_DIR = os.path.join(
        os.getenv('APPDATA'), 
        'pyRevit', 
        'Extensions', 
        'ExportSheetsPro', 
        'NamingProfiles'
    )
    
    EXPORT_PROFILES_DIR = os.path.join(
        os.getenv('APPDATA'), 
        'pyRevit', 
        'Extensions', 
        'ExportSheetsPro', 
        'ExportProfiles'
    )
    
    LAST_CONFIG_FILE = os.path.join(PROFILES_DIR, "_last_config.json")
    RECENT_EXPORTS_FILE = os.path.join(PROFILES_DIR, "_recent_exports.json")
    THEME_FILE = os.path.join(PROFILES_DIR, "_theme_settings.json")
    LANGUAGE_FILE = os.path.join(PROFILES_DIR, "_language_settings.json")
    
    # Ensure directories exist
    @classmethod
    def ensure_dirs(cls):
        for dir_path in [cls.PROFILES_DIR, cls.VIEWSETS_DIR, cls.NAMING_PROFILES_DIR, cls.EXPORT_PROFILES_DIR]:
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
    
    # Presets optimizados basados en Diroots Prosheets
    PRESET_QUICK = {
        'name': 'Quick',
        'pdf_raster_quality': DB.RasterQualityType.Presentation,
        'pdf_color_depth': DB.ColorDepthType.Color,
        'dwg_version': DB.ACADVersion.R2013,
        'dwg_colors': DB.ExportColorMode.TrueColor
    }
    
    PRESET_STANDARD = {
        'name': 'Standard',
        'pdf_raster_quality': DB.RasterQualityType.High,
        'pdf_color_depth': DB.ColorDepthType.Color,
        'dwg_version': DB.ACADVersion.R2018,
        'dwg_colors': DB.ExportColorMode.TrueColorPerView
    }
    
    PRESET_PRINT = {
        'name': 'Print',
        'pdf_raster_quality': DB.RasterQualityType.Presentation,
        'pdf_color_depth': DB.ColorDepthType.Color,
        'dwg_version': DB.ACADVersion.R2018,
        'dwg_colors': DB.ExportColorMode.TrueColorPerView
    }

# Run directory check on import
Config.ensure_dirs()
