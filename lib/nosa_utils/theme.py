# -*- coding: utf-8 -*-
import os
import json
import clr
from nosa_utils.telemetry import log_swallowed
_LOG = u'nosa_utils.theme'

try:
    clr.AddReference('System.Drawing')
    from System.Drawing import Color
except Exception:  # nosa-lint: disable=NOSA006 - optional at import time
    pass # Handle cases where System.Drawing might not be available immediately

class ThemeManager:
    """Gestor de temas (Light/Dark) con colores corporativos NOSA"""
    
    # NOSA Corporate Colors
    COLOR_ORANGE = Color.FromArgb(255, 95, 0)      # #FF5F00
    COLOR_ORANGE_LIGHT = Color.FromArgb(255, 192, 155) # #FFC09B
    COLOR_GREY = Color.FromArgb(65, 64, 66)        # #414042
    COLOR_GREY_LIGHT = Color.FromArgb(192, 192, 192)   # #C0C0C0
    
    # Semantic Colors (Light Mode)
    COLOR_BG = Color.FromArgb(250, 250, 250)
    COLOR_PANEL = Color.White
    COLOR_TEXT = Color.Black
    COLOR_BORDER = Color.FromArgb(220, 220, 220)
    
    # Semantic Colors (Dark Mode)
    COLOR_DARK_BG = Color.FromArgb(30, 30, 30)
    COLOR_DARK_PANEL = Color.FromArgb(45, 45, 48)
    COLOR_DARK_TEXT = Color.FromArgb(220, 220, 220)
    COLOR_DARK_BORDER = Color.FromArgb(60, 60, 60)
    
    @staticmethod
    def _get_default_config_file():
        return os.path.join(
            os.getenv('APPDATA'), 
            'pyRevit', 
            'Extensions', 
            'NOSA.extension', 
            'NOSA_Configs',
            '_theme_settings.json'
        )

    @staticmethod
    def load_theme(config_file=None):
        try:
            target_file = config_file if config_file else ThemeManager._get_default_config_file()
            if os.path.exists(target_file):
                with open(target_file, 'r') as f:
                    data = json.load(f)
                    return data.get('dark_mode', False)
        except Exception:
            log_swallowed(_LOG, u'load_theme')
        return False
    
    @staticmethod
    def save_theme(dark_mode, config_file=None):
        try:
            target_file = config_file if config_file else ThemeManager._get_default_config_file()
            directory = os.path.dirname(target_file)
            if not os.path.exists(directory):
                os.makedirs(directory)
                
            with open(target_file, 'w') as f:
                json.dump({'dark_mode': dark_mode}, f)
        except Exception:
            log_swallowed(_LOG, u'save_theme')
    
    @staticmethod
    def get_colors(dark_mode=None):
        if dark_mode is None:
            dark_mode = ThemeManager.load_theme()
            
        if dark_mode:
            return {
                'bg': ThemeManager.COLOR_DARK_BG,
                'panel': ThemeManager.COLOR_DARK_PANEL,
                'text': ThemeManager.COLOR_DARK_TEXT,
                'text_secondary': ThemeManager.COLOR_GREY_LIGHT,
                'border': ThemeManager.COLOR_DARK_BORDER,
                'primary': ThemeManager.COLOR_ORANGE,
                'secondary': ThemeManager.COLOR_ORANGE_LIGHT,
                'neutral': ThemeManager.COLOR_GREY,
                # UI Specifics
                'button_bg': ThemeManager.COLOR_ORANGE,
                'button_text': Color.White,
                'header_bg': ThemeManager.COLOR_GREY,
                'header_text': Color.White,
                'success': ThemeManager.COLOR_ORANGE, 
                'danger': Color.Red,
                'warning': ThemeManager.COLOR_ORANGE_LIGHT,
                'accent': ThemeManager.COLOR_ORANGE  # Added accent color
            }
        else:
            return {
                'bg': ThemeManager.COLOR_BG,
                'panel': ThemeManager.COLOR_PANEL,
                'text': ThemeManager.COLOR_TEXT,
                'text_secondary': ThemeManager.COLOR_GREY,
                'border': ThemeManager.COLOR_BORDER,
                'primary': ThemeManager.COLOR_ORANGE,
                'secondary': ThemeManager.COLOR_ORANGE_LIGHT,
                'neutral': ThemeManager.COLOR_GREY,
                # UI Specifics
                'button_bg': ThemeManager.COLOR_ORANGE,
                'button_text': Color.White,
                'header_bg': ThemeManager.COLOR_GREY,
                'header_text': Color.White,
                'success': ThemeManager.COLOR_ORANGE,
                'danger': Color.Red,
                'warning': ThemeManager.COLOR_ORANGE_LIGHT,
                'accent': ThemeManager.COLOR_ORANGE  # Added accent color
            }
    
    @staticmethod
    def get_hex(color):
        """Returns hex string for a Color object"""
        return "#{:02X}{:02X}{:02X}".format(color.R, color.G, color.B)
