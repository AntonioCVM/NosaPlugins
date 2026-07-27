# -*- coding: utf-8 -*-
import time
from Autodesk.Revit import DB
from nosa_utils.logging import Logger
from utils import Utils

logger = Logger()

class ViewCollector:
    """Clase para recolectar vistas y hojas de Revit"""
    
    @staticmethod
    def get_view_type_name(view):
        try:
            view_type = view.ViewType
            type_names = {
                DB.ViewType.FloorPlan: "FloorPlan",
                DB.ViewType.CeilingPlan: "CeilingPlan",
                DB.ViewType.ThreeD: "3D",
                DB.ViewType.Section: "Section",
                DB.ViewType.Elevation: "Elevation",
                DB.ViewType.Detail: "Detail",
                DB.ViewType.DraftingView: "Drafting",
                DB.ViewType.Rendering: "Rendering",
                DB.ViewType.AreaPlan: "AreaPlan",
                DB.ViewType.EngineeringPlan: "EngineeringPlan"
            }
            return type_names.get(view_type, str(view_type))
        except Exception:
            return "Unknown"
    
    @staticmethod
    def get_view_discipline_name(view):
        try:
            discipline = getattr(view, 'Discipline', None)
            if discipline is None:
                return "-"
            return str(discipline)
        except Exception:
            return "-"
    
    @staticmethod
    def get_level_name(view):
        try:
            if hasattr(view, 'GenLevel') and view.GenLevel:
                level = view.GenLevel
                if level:
                    return level.Name
            param = view.LookupParameter("Associated Level")
            if param and param.HasValue:
                value = param.AsString()
                if value:
                    return value
        except Exception:
            pass
        return "Unassigned"
    
    @staticmethod
    def is_view_on_sheet(view):
        try:
            if hasattr(view, 'SheetId') and view.SheetId:
                sheet_id = view.SheetId
                try:
                    return Utils._get_element_id_value(sheet_id) > 0
                except Exception:
                    return False
        except Exception:
            pass
        return False
    
    @staticmethod
    def get_view_parameters(view):
        """Get all parameters from a view (with cache)"""
        cache_key = Utils._get_cache_key(view.Id, True)
        
        # Verificar caché - accessing Utils._param_cache directly which is protected but python allows it
        if Utils._is_cache_valid(cache_key) and cache_key in Utils._param_cache:
            return Utils._param_cache[cache_key].copy()
        
        params = {}
        try:
            for param in view.Parameters:
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
            
            # Add view-specific properties
            params["View Name"] = view.Name or ""
            params["View Type"] = ViewCollector.get_view_type_name(view)
            params["View Number"] = getattr(view, 'ViewNumber', '') or ""
            params["Discipline"] = ViewCollector.get_view_discipline_name(view)
            params["Level"] = ViewCollector.get_level_name(view)
            
        except Exception as e:
            logger.warning("Error getting view parameters", e)
        
        # Guardar en caché via Utils
        Utils._param_cache[cache_key] = params.copy()
        Utils._cache_timestamp[cache_key] = time.time()
        
        return params

    @staticmethod
    def get_all_views(doc, include_templates=False, include_sheet_views=True):
        """Get all views from document"""
        try:
            collector = DB.FilteredElementCollector(doc)\
                .OfClass(DB.View)\
                .WhereElementIsNotElementType()
            
            all_views = list(collector)
            filtered_views = []
            
            for view in all_views:
                try:
                    # Excluir vistas plantilla si no se solicitan
                    if not include_templates and view.IsTemplate:
                        continue
                    
                    # Filtros adicionales
                    if hasattr(view, 'CanBePrinted') and view.CanBePrinted:
                         # Si include_sheet_views es False, excluir vistas que están en planos
                        if not include_sheet_views and ViewCollector.is_view_on_sheet(view):
                            continue
                        filtered_views.append(view)
                    elif not hasattr(view, 'CanBePrinted'):
                         # Algunas vistas pueden no tener CanBePrinted, incluirlas de todas formas
                        filtered_views.append(view)
                except Exception as e:
                    logger.warning("Error procesando vista: {}".format(str(e)))
                    continue
            
            logger.info("Vistas encontradas: {} (de {} totales)".format(
                len(filtered_views), len(all_views)
            ))
            return filtered_views
        except Exception as e:
            logger.error("Error collecting views", e)
            return []

    @staticmethod
    def get_all_sheets(doc):
        """Get all sheets from document"""
        try:
            collector = DB.FilteredElementCollector(doc)\
                .OfClass(DB.ViewSheet)\
                .WhereElementIsNotElementType()
            
            # Filter out placeholder sheets or other non-printable sheets if necessary
            # For now, return all sheets found
            sheets = []
            for s in collector:
                try:
                    # Check if sheet is valid (has a number)
                    if s.SheetNumber:
                        sheets.append(s)
                except Exception:
                    continue
                    
            # Sort by Sheet Number
            try:
                sheets.sort(key=lambda x: x.SheetNumber)
            except Exception:
                pass
                
            return sheets
        except Exception as e:
            logger.error("Error collecting sheets", e)
            return []
