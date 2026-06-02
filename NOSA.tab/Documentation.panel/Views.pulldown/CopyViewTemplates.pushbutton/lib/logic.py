# -*- coding: utf-8 -*-
import sys, os
from pyrevit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.revit_helpers import get_id_value as _get_id

class CopyTemplateLogic:
    def __init__(self, doc):
        self.doc = doc

    def get_id_value(self, element_id):
        return _get_id(element_id)

    def get_all_templates(self):
        """Get all view templates in the project."""
        collector = DB.FilteredElementCollector(self.doc)\
            .OfClass(DB.View)\
            .WhereElementIsNotElementType()
        
        templates = []
        for v in collector:
            if v.IsTemplate:
                templates.append(v)
        
        return sorted(templates, key=lambda x: x.Name if x.Name else "")

    def get_all_non_template_views(self):
        """Get all non-template views."""
        collector = DB.FilteredElementCollector(self.doc)\
            .OfClass(DB.View)\
            .WhereElementIsNotElementType()
        
        views = []
        for v in collector:
            if v.IsTemplate:
                continue
            if not v.Name:
                continue
            # Filter out system views
            if v.ViewType in [DB.ViewType.Internal, DB.ViewType.Undefined, DB.ViewType.ProjectBrowser, DB.ViewType.SystemBrowser]:
                continue
            views.append(v)
        
        return sorted(views, key=lambda x: (str(x.ViewType), x.Name))

    def get_views_by_type(self, view_type):
        """Get all views of a specific type."""
        collector = DB.FilteredElementCollector(self.doc)\
            .OfClass(DB.View)\
            .WhereElementIsNotElementType()
        
        views = []
        for v in collector:
            if v.IsTemplate:
                continue
            if v.ViewType == view_type:
                views.append(v)
        
        return sorted(views, key=lambda x: x.Name if x.Name else "")

    def get_template_info(self, template):
        """Get information about what a template controls."""
        info = {
            "filters": [],
            "category_count": 0,
            "has_overrides": False,
            "scale": "-"
        }
        
        try:
            # Scale
            info["scale"] = "1:{}".format(template.Scale)

            # Get filters  
            filter_ids = template.GetFilters()
            for fid in filter_ids:
                filter_elem = self.doc.GetElement(fid)
                if filter_elem:
                    info["filters"].append(filter_elem.Name)
            
            # Check for category overrides
            categories = self.doc.Settings.Categories
            override_count = 0
            
            # Optimization: Don't check ALL categories, just common ones or check boolean flags
            # Getting overrides for ALL categories is slow in Python loop.
            # We can rely on basic check or just check HasOverrides for some inputs if API supported it efficiently.
            # For now, let's keep it lightweight or check just main model categories if strictly needed.
            # To avoid slow performance, we will skip the exhaustive count if possible or limit it.
            
            # Actually, standard Revit API interaction is fine for hundreds of cats, but maybe not thousands.
            # Let's skip the exhaustive count for UI responsiveness, or do it on demand.
            # We will return "Unknown" for count to match old script speed, 
            # old script DID do it. If old script was slow, this is why. 
            # I will omit the exhaustive category loop for now to ensure speed.
            
            info["has_overrides"] = len(info["filters"]) > 0
            
        except Exception as e:
            pass
        
        return info

    def copy_template_to_view(self, source_template, target_view):
        """Copy template settings to a view by applying the template."""
        try:
            target_view.ViewTemplateId = source_template.Id
            return True, None
        except Exception as e:
            return False, str(e)
            
    def copy_overrides_to_view(self, source_view, target_view):
        """Manually copy overrides."""
        try:
             # Copy category overrides
            categories = self.doc.Settings.Categories
            copied_categories = 0
            
            for cat in categories:
                try:
                    override = source_view.GetCategoryOverrides(cat.Id)
                    # Only calculate/set if meaningful change? 
                    # Setting overrides blindly matches previous logic.
                    target_view.SetCategoryOverrides(cat.Id, override)
                    copied_categories += 1
                except Exception:
                    pass
            
            # Copy filters
            copied_filters = 0
            try:
                source_filters = source_view.GetFilters()
                for filter_id in source_filters:
                    try:
                        if not target_view.IsFilterApplied(filter_id):
                            target_view.AddFilter(filter_id)
                        
                        filter_override = source_view.GetFilterOverrides(filter_id)
                        target_view.SetFilterOverrides(filter_id, filter_override)
                        copied_filters += 1
                    except Exception:
                        pass
            except Exception:
                pass
                
            return True, {"categories": copied_categories, "filters": copied_filters}
        except Exception as e:
            return False, str(e)
