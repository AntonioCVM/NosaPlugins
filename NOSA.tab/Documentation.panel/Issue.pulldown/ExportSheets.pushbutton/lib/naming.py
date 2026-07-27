# -*- coding: utf-8 -*-
import re
from config import Config
from utils import Utils
from Autodesk.Revit import DB
# Import ViewCollector - circular dependency?
# NamingBuilder uses ViewCollector.get_view_parameters
# I'll create ViewCollector in lib/view_collector.py first or stub it here?
# Better to put ViewCollector in its own file and import it.
# I'll delay NamingBuilder slightly or handle import inside method.

# ── NOSA standard naming presets ────────────────────────────────────────────
# Each preset is a list of parameter tokens that NamingBuilder.template should hold.
# Token format mirrors build_filename: plain name → literal value from sheet params.
# Use these with NamingBuilder().from_preset(name) to apply a standard template.
NAMING_PRESETS = {
    'NOSA Protocol':
        ['Sheet Number', 'Sheet Name'],
    'NOSA Full (Rev)':
        ['Sheet Number', 'Sheet Name', 'Current Revision'],
    'Number — Name':
        ['Sheet Number', 'Sheet Name'],
    'Originator — Number — Name':
        ['Originator', 'Sheet Number', 'Sheet Name'],
    'Discipline — Number — Name':
        ['Discipline', 'Sheet Number', 'Sheet Name'],
    'Number only':
        ['Sheet Number'],
}


class NamingBuilder:
    """Constructor de nomenclatura personalizada con soporte para funciones y regex"""
    
    def __init__(self):
        self.template = []
        self.separator = Config.DEFAULT_SEPARATOR
        self.functions = {
            'upper': lambda x: str(x).upper() if x else '',
            'lower': lambda x: str(x).lower() if x else '',
            'title': lambda x: str(x).title() if x else '',
            'strip': lambda x: str(x).strip() if x else '',
            'replace_space': lambda x: str(x).replace(' ', '_') if x else '',
            'replace_dash': lambda x: str(x).replace('-', '_') if x else '',
            'truncate_20': lambda x: str(x)[:20] if x else '',
            'truncate_30': lambda x: str(x)[:30] if x else '',
            'truncate_50': lambda x: str(x)[:50] if x else '',
        }
    
    def add_parameter(self, param_name):
        if param_name and param_name not in self.template:
            self.template.append(param_name)
    
    def remove_parameter(self, param_name):
        if param_name in self.template:
            self.template.remove(param_name)
    
    def clear(self):
        self.template = []
    
    def move_up(self, param_name):
        if param_name in self.template:
            idx = self.template.index(param_name)
            if idx > 0:
                self.template[idx], self.template[idx-1] = self.template[idx-1], self.template[idx]
    
    def move_down(self, param_name):
        if param_name in self.template:
            idx = self.template.index(param_name)
            if idx < len(self.template) - 1:
                self.template[idx], self.template[idx+1] = self.template[idx+1], self.template[idx]
    
    def _apply_function(self, value, function_name):
        """Aplica función a un valor"""
        if not value:
            return ""
        
        if function_name in self.functions:
            try:
                return self.functions[function_name](value)
            except Exception:
                return str(value)
        return str(value)
    
    def _apply_regex(self, value, pattern, replacement):
        """Aplica expresión regular a un valor"""
        if not value:
            return ""
        
        try:
            return re.sub(pattern, replacement, str(value))
        except Exception:
            return str(value)
    
    def _parse_template_item(self, item):
        """Parsea un item de template que puede contener funciones o regex
        Formato: param_name|function:upper o param_name|regex:pattern:replacement
        """
        if '|' not in item:
            return item, None, None
        
        parts = item.split('|')
        param_name = parts[0].strip()
        
        if len(parts) > 1:
            operation = parts[1].strip()
            
            if operation.startswith('function:'):
                function_name = operation.replace('function:', '').strip()
                return param_name, 'function', function_name
            elif operation.startswith('regex:'):
                regex_parts = operation.replace('regex:', '').split(':', 1)
                if len(regex_parts) == 2:
                    return param_name, 'regex', (regex_parts[0], regex_parts[1])
        
        return param_name, None, None
    
    def build_filename(self, element, project_params=None, is_view=False):
        """Build filename from naming template - Supports both sheets and views"""
        if not self.template:
            if is_view:
                return element.Name if hasattr(element, 'Name') else "View"
            return element.SheetNumber if hasattr(element, 'SheetNumber') else "Sheet"
        
        # Late import to avoid circular dependency
        from view_collector import ViewCollector
        
        # Get parameters based on element type
        if is_view:
            params = ViewCollector.get_view_parameters(element)
        else:
            params = Utils.get_sheet_parameters(element)
        
        if project_params:
            params.update(project_params)
        
        parts = []
        
        for template_item in self.template:
            param_name, operation_type, operation_value = self._parse_template_item(template_item)
            value = params.get(param_name, "")
            
            if value:
                # Aplicar función o regex si está especificado
                if operation_type == 'function':
                    value = self._apply_function(value, operation_value)
                elif operation_type == 'regex':
                    pattern, replacement = operation_value
                    value = self._apply_regex(value, pattern, replacement)
                else:
                    value = str(value)
                
                if value:
                    parts.append(value)
        
        if not parts:
            if is_view:
                return element.Name if hasattr(element, 'Name') else "View"
            return element.SheetNumber if hasattr(element, 'SheetNumber') else "Sheet"
        
        filename = self.separator.join(parts)
        return Utils.sanitize_filename(filename)
    
    def get_preview(self, element, project_params=None, is_view=False):
        return self.build_filename(element, project_params, is_view) + ".pdf"
    
    def to_dict(self):
        return {
            'template': self.template,
            'separator': self.separator,
            'version': '2.0'  # Versión con soporte de funciones
        }
    
    def from_dict(self, data):
        self.template = data.get('template', [])
        self.separator = data.get('separator', Config.DEFAULT_SEPARATOR)
        if data.get('version') != '2.0':
            pass

    def from_preset(self, preset_name):
        """Apply a NOSA naming preset by name (see NAMING_PRESETS dict)."""
        tokens = NAMING_PRESETS.get(preset_name)
        if tokens:
            self.template = list(tokens)
        return self

    @staticmethod
    def list_presets():
        """Return ordered list of preset names for UI display."""
        return list(NAMING_PRESETS.keys())

