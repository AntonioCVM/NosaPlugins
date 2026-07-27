# -*- coding: utf-8 -*-
import os
import re
import time
import datetime
import subprocess
from Autodesk.Revit import DB
from config import Config
from nosa_utils.logging import Logger
from nosa_utils.revit_helpers import get_id_value

logger = Logger()

class Utils:
    """Funciones utilitarias optimizadas con caché"""
    
    # Caché para parámetros (evita múltiples lecturas)
    _param_cache = {}
    _cache_timestamp = {}
    CACHE_TIMEOUT = 300  # 5 minutos
    
    @staticmethod
    def _get_element_id_value(element_id):
        """Integer value from ElementId — Revit 2024–2027."""
        return get_id_value(element_id)
    
    @staticmethod
    def _get_cache_key(element_id, is_view=False):
        """Genera clave de caché"""
        id_value = Utils._get_element_id_value(element_id)
        return "{}_{}".format(id_value, "view" if is_view else "sheet")
    
    @staticmethod
    def _is_cache_valid(cache_key):
        """Verifica si el caché es válido"""
        if cache_key not in Utils._cache_timestamp:
            return False
        elapsed = time.time() - Utils._cache_timestamp[cache_key]
        return elapsed < Utils.CACHE_TIMEOUT
    
    @staticmethod
    def clear_cache():
        """Limpia el caché"""
        Utils._param_cache.clear()
        Utils._cache_timestamp.clear()
    
    @staticmethod
    def mm_to_feet(mm):
        return mm / 304.8
    
    @staticmethod
    def feet_to_mm(feet):
        return feet * 304.8
    
    @staticmethod
    def sanitize_filename(filename):
        """Sanitise filename, removing invalid characters."""
        invalid = r'[<>:"/\\|?*]'
        clean = re.sub(invalid, '_', filename)
        clean = clean.strip()
        if len(clean) > 200:
            clean = clean[:200]
        return clean if clean else "unnamed"
    
    @staticmethod
    def get_sheet_parameters(sheet):
        """Obtiene todos los parámetros de un sheet incluyendo Current Revision (con caché)"""
        cache_key = Utils._get_cache_key(sheet.Id, False)
        
        # Verificar caché
        if Utils._is_cache_valid(cache_key) and cache_key in Utils._param_cache:
            return Utils._param_cache[cache_key].copy()
        
        params = {}
        
        # Obtener todos los parámetros estándar
        for param in sheet.Parameters:
            try:
                name = param.Definition.Name
                if param.HasValue:
                    if param.StorageType == DB.StorageType.String:
                        value = param.AsString()
                    elif param.StorageType == DB.StorageType.Integer:
                        value = str(param.AsInteger())
                    elif param.StorageType == DB.StorageType.Double:
                        value = str(param.AsDouble())
                    else:
                        value = param.AsValueString()
                    
                    if value:
                        params[name] = str(value).strip()
                else:
                    params[name] = ""
            except Exception:
                continue
        
        # Save PROPIEDADES NATIVAS EXPLICITAMENTE
        # A veces no aparecen en el iterador de parámetros
        try:
             params["Sheet Name"] = sheet.Name
             params["Sheet Number"] = sheet.SheetNumber
        except Exception:
             pass

        # CRÍTICO: Asegurar que Current Revision esté incluido
        try:
            current_rev_param = sheet.LookupParameter("Current Revision")
            if current_rev_param and current_rev_param.HasValue:
                params["Current Revision"] = current_rev_param.AsString() or ""
            else:
                params["Current Revision"] = ""
        except Exception:
            params["Current Revision"] = ""
            
        # EXTRA: Intentar obtener cualquier otro parámetro que un usuario pudiera haber pedido 
        # pero que no apareció en la iteración normal (raro pero posible)
        # No podemos iterar "todos los posibles", basic characters are always allowed.
        
        # Save en caché
        Utils._param_cache[cache_key] = params.copy()
        Utils._cache_timestamp[cache_key] = time.time()
        
        return params
    
    @staticmethod
    def get_project_parameters(doc):
        """Return project parameters."""
        params = {}
        try:
            proj_info = doc.ProjectInformation
            
            param_names = [
                "Project Number",
                "Project Name", 
                "Project Address",
                "Project Status",
                "Client Name",
                "Organization Name",
                "Organization Description",
                "Building Name",
                "Author",
                "Issue Date"
            ]
            
            for param_name in param_names:
                try:
                    param = proj_info.LookupParameter(param_name)
                    if param and param.HasValue:
                        if param.StorageType == DB.StorageType.String:
                            value = param.AsString()
                        else:
                            value = param.AsValueString()
                        
                        if value:
                            params["PROJECT: " + param_name] = str(value).strip()
                except Exception:
                    continue
            
            if doc.Title:
                params["PROJECT: File Name"] = doc.Title.replace('.rvt', '')
            
        except Exception as e:
            logger.warning("Error retrieving project parameters", e)
        
        return params
    
    @staticmethod
    def open_folder(folder_path):
        """Abre carpeta en el explorador"""
        try:
            if os.path.exists(folder_path):
                subprocess.Popen(['explorer', folder_path])
        except Exception:
            pass
    
    @staticmethod
    def get_paper_size_from_sheet(sheet, doc):
        """Auto-detecta tamaño de papel desde titleblock"""
        try:
            titleblock_ids = sheet.GetAllViewports() # ERROR: Sheets don't have viewports? wait. 
            # Original code said GetAllViewports? sheets have GetAllPlacedViews?
            # Wait, sheet.GetAllViewports() returns viewport IDs. But we need TitleBlocks.
            # Titleblocks are elements in the view (sheet).
            
            # Correction: FilteredElementCollector on the sheet view.
            titleblock = None
            
            collector = DB.FilteredElementCollector(doc, sheet.Id).OfCategory(DB.BuiltInCategory.OST_TitleBlocks).WhereElementIsNotElementType()
            titleblock = collector.FirstElement()
            
            if not titleblock:
                return None, None
            
            width_param = titleblock.LookupParameter("Sheet Width") or titleblock.LookupParameter("Width")
            height_param = titleblock.LookupParameter("Sheet Height") or titleblock.LookupParameter("Height")
            
            if not width_param or not height_param:
                return None, None
            
            width_mm = Utils.feet_to_mm(width_param.AsDouble())
            height_mm = Utils.feet_to_mm(height_param.AsDouble())
            
            if width_mm > height_mm:
                orientation = "Landscape"
                paper_width = width_mm
                paper_height = height_mm
            else:
                orientation = "Portrait"
                paper_width = width_mm
                paper_height = height_mm
            
            detected_size = None
            min_diff = float('inf')
            
            for size_name, (std_width, std_height) in Config.PAPER_SIZES.items():
                diff1 = abs(paper_width - std_width) + abs(paper_height - std_height)
                diff2 = abs(paper_width - std_height) + abs(paper_height - std_width)
                
                current_diff = min(diff1, diff2)
                if current_diff < min_diff:
                    min_diff = current_diff
                    detected_size = size_name
            
            if min_diff > 50:
                detected_size = "Custom ({:.0f}x{:.0f}mm)".format(paper_width, paper_height)
            
            return detected_size, orientation
            
        except Exception as e:
            logger.warning("Error detectando papel", e)
            return None, None
    
    @staticmethod
    def expand_path_variables(path, doc):
        """Expande variables de entorno en rutas"""
        try:
            now = datetime.datetime.now()
            
            variables = {
                '%UserName%': os.getenv('USERNAME', 'User'),
                '%ProjectName%': doc.Title.replace('.rvt', ''),
                '%ProjectPath%': os.path.dirname(doc.PathName) if doc.PathName else '',
                '%Year%': now.strftime('%Y'),
                '%Y%': now.strftime('%Y'),
                '%Month%': now.strftime('%m'),
                '%m%': now.strftime('%m'),
                '%Day%': now.strftime('%d'),
                '%d%': now.strftime('%d'),
                '%Hour%': now.strftime('%H'),
                '%H%': now.strftime('%H'),
                '%Minute%': now.strftime('%M'),
                '%M%': now.strftime('%M'),
                '%Second%': now.strftime('%S'),
                '%S%': now.strftime('%S'),
                '%Date%': now.strftime('%Y-%m-%d'),
                '%DateTime%': now.strftime('%Y-%m-%d_%H-%M-%S'),
                '%Time%': now.strftime('%H-%M-%S'),
            }
            
            result = path
            for var, value in variables.items():
                result = result.replace(var, value)
            
            return result
        except Exception:
            return path

