# -*- coding: utf-8 -*-
import sys, os
from pyrevit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.revit_helpers import get_id_value as _get_id

class AlignLogic:
    def __init__(self, doc):
        self.doc = doc

    def get_all_sheets(self):
        """Get all sheets in the project."""
        return list(DB.FilteredElementCollector(self.doc).OfClass(DB.ViewSheet))

    def get_id_value(self, element_id):
        return _get_id(element_id)

    def get_sheet_sets(self):
        """Get unique sheet set names from sheets."""
        sheets = self.get_all_sheets()
        sheet_sets = set()
        for sheet in sheets:
            param = sheet.LookupParameter("Sheet Set")
            if param and param.AsString():
                sheet_sets.add(param.AsString())
        return sorted(list(sheet_sets)) if sheet_sets else []

    def get_viewports_on_sheet(self, sheet):
        """Get all viewports on a sheet."""
        viewports = []
        for vp_id in sheet.GetAllViewports():
            vp = self.doc.GetElement(vp_id)
            if isinstance(vp, DB.Viewport):
                viewports.append(vp)
        return viewports

    def get_matching_viewports(self, ref_view, filter_sets=None):
        """Find all viewports matching the reference scale and ViewType."""
        matching = []
        debug_lines = []
        
        try:
            ref_scale = ref_view.Scale
            ref_view_type = ref_view.ViewType
            ref_view_id_value = self.get_id_value(ref_view.Id)
            
            # Define compatible Plan types
            PLAN_TYPES = [
                DB.ViewType.FloorPlan,
                DB.ViewType.EngineeringPlan,
                DB.ViewType.AreaPlan,
                DB.ViewType.CeilingPlan
            ]
            
            is_ref_plan = ref_view_type in PLAN_TYPES
            
            debug_lines.append("Reference: '{}' (Scale 1:{}, Type: {})".format(ref_view.Name, ref_scale, ref_view_type))
            debug_lines.append("Is Plan Type: {}".format(is_ref_plan))
            
            all_sheets = self.get_all_sheets()
            target_sheets = []
            
            if filter_sets:
                for sheet in all_sheets:
                    param = sheet.LookupParameter("Sheet Set")
                    if param and param.AsString() in filter_sets:
                        target_sheets.append(sheet)
                debug_lines.append("Filtering active: {} sheets selected".format(len(target_sheets)))
            else:
                target_sheets = all_sheets
                debug_lines.append("No filter: Scanning all {} sheets".format(len(target_sheets)))
                
            scanned_count = 0
            rejected_scale = 0
            rejected_type = 0
            
            for sheet in target_sheets:
                # debug_lines.append("Checking Sheet: {}".format(sheet.SheetNumber))
                for vp in self.get_viewports_on_sheet(sheet):
                    view = self.doc.GetElement(vp.ViewId)
                    if not view or not hasattr(view, "Scale"):
                        continue
                    
                    # Skip self
                    if self.get_id_value(view.Id) == ref_view_id_value:
                        continue

                    scanned_count += 1
                    try:
                        # Scale match is mandatory
                        if view.Scale != ref_scale:
                            rejected_scale += 1
                            # debug_lines.append("  Reject {}: Scale {} != {}".format(view.Name, view.Scale, ref_scale))
                            continue
                            
                        # Type match
                        is_match = False
                        if is_ref_plan:
                            if view.ViewType in PLAN_TYPES:
                                is_match = True
                        else:
                            if view.ViewType == ref_view_type:
                                is_match = True
                                
                        if is_match:
                            matching.append({
                                "viewport": vp,
                                "view": view,
                                "sheet": sheet,
                                "sheet_num": sheet.SheetNumber,
                                "view_name": view.Name
                            })
                        else:
                            rejected_type += 1
                            # debug_lines.append("  Reject {}: Type {} incompatible".format(view.Name, view.ViewType))

                    except Exception as e:
                        debug_lines.append("Error checking vp: " + str(e))
            
            summary = "\nScan Summary:\n- Scanned Viewports: {}\n- Matches Found: {}\n- Rejected (Wrong Scale): {}\n- Rejected (Wrong Type): {}".format(
                scanned_count, len(matching), rejected_scale, rejected_type
            )
            debug_lines.append(summary)
            
            return matching, "\n".join(debug_lines)
            
        except Exception as e:
            return [], "Critical Error in logic: " + str(e)

    def calculate_aligned_offset(self, ref_offset, ref_vp, target_vp, alignment_mode, align_vertical):
        """Calculate offset based on alignment mode."""
        if alignment_mode == 'Same as Reference':
            return ref_offset
        
        try:
            ref_outline = ref_vp.GetBoxOutline()
            target_outline = target_vp.GetBoxOutline()
            
            ref_width = ref_outline.MaximumPoint.X - ref_outline.MinimumPoint.X
            target_width = target_outline.MaximumPoint.X - target_outline.MinimumPoint.X
            
            half_ref = ref_width / 2.0
            half_target = target_width / 2.0
            
            if alignment_mode == 'Left':
                x_offset = ref_offset.X - half_ref + half_target
            elif alignment_mode == 'Right':
                x_offset = ref_offset.X + half_ref - half_target
            elif alignment_mode == 'Center':
                x_offset = ref_offset.X
            else:
                x_offset = ref_offset.X
            
            y_offset = ref_offset.Y if align_vertical else target_vp.LabelOffset.Y
            
            return DB.XYZ(x_offset, y_offset, ref_offset.Z)
        except Exception:
            return ref_offset
