# -*- coding: utf-8 -*-
from pyrevit import DB
import sys
import os

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.revit_helpers import get_id_value as _get_id_value


def _log_debug(msg, exc=None):
    pass


class ClashLogic:
    """Core logic for Clash Detection"""
    
    def __init__(self, doc):
        self.doc = doc
        self._solid_cache = {}

    def clear_solid_cache(self):
        self._solid_cache.clear()

    def get_id_value(self, element_id):
        return _get_id_value(element_id)

    def get_element_solid(self, element):
        """Get solid geometry from element."""
        try:
            options = DB.Options()
            options.ComputeReferences = False
            options.IncludeNonVisibleObjects = False
            
            geom = element.get_Geometry(options)
            if not geom:
                return None
            
            for obj in geom:
                if isinstance(obj, DB.Solid) and obj.Volume > 0:
                    return obj
                elif isinstance(obj, DB.GeometryInstance):
                    instance_geom = obj.GetInstanceGeometry()
                    for inst_obj in instance_geom:
                        if isinstance(inst_obj, DB.Solid) and inst_obj.Volume > 0:
                            return inst_obj
            return None
        except Exception as ex:
            _log_debug("get_element_solid", ex)
            return None

    def get_element_bounding_box(self, element):
        """Get bounding box of element."""
        try:
            return element.get_BoundingBox(None)
        except Exception as ex:
            _log_debug("get_element_bounding_box", ex)
            return None

    def get_element_solid_cached(self, element):
        """Return solid geometry once per element (avoids repeated tessellation in clash loops)."""
        key = self.get_id_value(element.Id)
        if key not in self._solid_cache:
            self._solid_cache[key] = self.get_element_solid(element)
        return self._solid_cache[key]

    def bounding_boxes_intersect(self, bbox1, bbox2):
        """Check if two bounding boxes intersect."""
        if not bbox1 or not bbox2:
            return False
        
        # Check if boxes overlap in all three dimensions
        return (bbox1.Min.X <= bbox2.Max.X and bbox1.Max.X >= bbox2.Min.X and
                bbox1.Min.Y <= bbox2.Max.Y and bbox1.Max.Y >= bbox2.Min.Y and
                bbox1.Min.Z <= bbox2.Max.Z and bbox1.Max.Z >= bbox2.Min.Z)

    def solids_intersect(self, solid1, solid2):
        """Check if two solids intersect using Boolean operation."""
        return self.intersect_volume(solid1, solid2) > 0.001

    def intersect_volume(self, solid1, solid2):
        """Return intersection volume (ft³), or 0 if no intersection / error."""
        try:
            intersection = DB.BooleanOperationsUtils.ExecuteBooleanOperation(
                solid1, solid2, DB.BooleanOperationsType.Intersect
            )
            return intersection.Volume if intersection else 0.0
        except Exception as ex:
            _log_debug("intersect_volume", ex)
            return 0.0

    def get_element_info(self, element):
        """Get display info for an element."""
        try:
            category = element.Category.Name if element.Category else "Unknown"
            
            if hasattr(element, 'Symbol') and element.Symbol:
                family = element.Symbol.Family.Name if element.Symbol.Family else ""
                type_name = element.Name if hasattr(element, 'Name') else ""
                name = "{} : {}".format(family, type_name)
            elif hasattr(element, 'Name'):
                name = element.Name
            else:
                name = ""
            
            # Get Mark if available
            mark_param = element.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
            mark = mark_param.AsString() if mark_param else ""
            
            return {
                "id": self.get_id_value(element.Id),
                "category": category,
                "name": name,
                "mark": mark or "",
                "element": element
            }
        except Exception as e:
            return {
                "id": self.get_id_value(element.Id),
                "category": "Unknown",
                "name": "Error getting info",
                "mark": "",
                "element": element
            }

    def collect_elements_by_category(self, category):
        """Collect all elements of a category."""
        try:
            collector = DB.FilteredElementCollector(self.doc)\
                .OfCategory(category)\
                .WhereElementIsNotElementType()
            return list(collector)
        except Exception as ex:
            _log_debug("collect_elements_by_category", ex)
            return []
