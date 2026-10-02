# -*- coding: utf-8 -*-
from Autodesk.Revit import DB
from pyrevit import revit
import math

from nosa_utils import unit_conversion as _uc10
from nosa_utils.pilecap_utils import ungroup_targets as _ungroup_targets
from nosa_utils.pilecap_utils import regroup_restore as _regroup_restore


class CoordinateLogic:
    def __init__(self, doc):
        self.doc = doc

    def _get_inverse_total_transform(self):
        """
        Inverse of the active project location's total transform.
        Maps a model-space point (internal coordinates) into the shared
        coordinate system — aligned with Revit's project positioning / links.
        Returns None if unavailable.
        """
        try:
            loc = self.doc.ActiveProjectLocation
            if not loc:
                return None
            t = loc.GetTotalTransform()
            if t is None:
                return None
            return t.Inverse
        except Exception:
            return None

    def _get_base_point_by_category(self, built_in_category):
        """Return first element of Project Base Point or Survey Point category."""
        try:
            col = (
                DB.FilteredElementCollector(self.doc)
                .OfCategory(built_in_category)
                .WhereElementIsNotElementType()
            )
            for e in col:
                return e
        except Exception:
            pass
        return None

    def _get_project_base_point(self):
        return self._get_base_point_by_category(DB.BuiltInCategory.OST_ProjectBasePoint)

    def _get_survey_point(self):
        return self._get_base_point_by_category(DB.BuiltInCategory.OST_SharedBasePoint)

    @staticmethod
    def _base_point_model_xyz(base_point_element):
        """Position of a Survey / Project Base Point in model coordinates (internal)."""
        if not base_point_element:
            return None
        try:
            return base_point_element.Position
        except Exception:
            try:
                loc = base_point_element.Location
                if isinstance(loc, DB.LocationPoint):
                    return loc.Point
            except Exception:
                pass
        return None

    @staticmethod
    def _get_length_param_internal(element, built_in_param):
        p = element.get_Parameter(built_in_param)
        if p and p.HasValue and p.StorageType == DB.StorageType.Double:
            return p.AsDouble()
        return 0.0

    def compute_reporting_point(self, model_xyz, coord_mode, inv_transform):
        """
        coord_mode: 'coordination' | 'survey' | 'project_base'

        - coordination: absolute coordinates in Revit's shared system (inverse total
          transform). Same basis as linked-model coordination.
        - survey: same convention as Spot Coordinates relative to Survey (offset from
          survey location plus survey E/W, N/S, Elev parameters).
        - project_base: same convention as Spot relative to Project Base Point.
        If inv_transform is None, returns raw model XYZ (internal feet).
        """
        inv = inv_transform
        if inv is None:
            return model_xyz

        p_shared = inv.OfPoint(model_xyz)

        if coord_mode == "coordination":
            return p_shared

        if coord_mode == "survey":
            surv = self._get_survey_point()
            if not surv:
                return p_shared
            s_model = self._base_point_model_xyz(surv)
            if s_model is None:
                return p_shared
            s_shared = inv.OfPoint(s_model)
            ew = self._get_length_param_internal(surv, DB.BuiltInParameter.BASEPOINT_EASTWEST_PARAM)
            ns = self._get_length_param_internal(surv, DB.BuiltInParameter.BASEPOINT_NORTHSOUTH_PARAM)
            elv = self._get_length_param_internal(surv, DB.BuiltInParameter.BASEPOINT_ELEVATION_PARAM)
            return DB.XYZ(
                p_shared.X - s_shared.X + ew,
                p_shared.Y - s_shared.Y + ns,
                p_shared.Z - s_shared.Z + elv,
            )

        if coord_mode == "project_base":
            pbp = self._get_project_base_point()
            if not pbp:
                return p_shared
            b_model = self._base_point_model_xyz(pbp)
            if b_model is None:
                return p_shared
            b_shared = inv.OfPoint(b_model)
            ew = self._get_length_param_internal(pbp, DB.BuiltInParameter.BASEPOINT_EASTWEST_PARAM)
            ns = self._get_length_param_internal(pbp, DB.BuiltInParameter.BASEPOINT_NORTHSOUTH_PARAM)
            elv = self._get_length_param_internal(pbp, DB.BuiltInParameter.BASEPOINT_ELEVATION_PARAM)
            return DB.XYZ(
                p_shared.X - b_shared.X + ew,
                p_shared.Y - b_shared.Y + ns,
                p_shared.Z - b_shared.Z + elv,
            )

        return p_shared

    @staticmethod
    def _format_grouped_decimals(value, decimals=3):
        """US-style grouping: 1,000,000,000.254 (comma thousands, dot decimals)."""
        if decimals == 3:
            return "{0:,.3f}".format(value)
        return ("{0:,." + str(decimals) + "f}").format(value)

    def _internal_length_to_mm(self, value_internal_feet):
        """Coordinate ordinates are internal length units (feet)."""
        try:
            return DB.UnitUtils.ConvertFromInternalUnits(
                value_internal_feet, DB.UnitTypeId.Millimeters
            )
        except Exception:
            try:
                return DB.UnitUtils.ConvertFromInternalUnits(
                    value_internal_feet, DB.DisplayUnitType.DUT_MILLIMETERS
                )
            except Exception:
                return value_internal_feet * _uc10.FT_TO_MM

    def _coord_mm_display(self, internal_feet_ord):
        """Formatted mm string with thousands separators and 3 decimals."""
        mm = self._internal_length_to_mm(internal_feet_ord)
        return self._format_grouped_decimals(mm, 3)

    def _set_coord_parameter(self, param, internal_feet_ord):
        """
        Write coordinate: Text params get formatted mm (1,000,000.254).
        Legacy Length (double) params keep internal feet for Revit length storage.
        """
        if not param or param.IsReadOnly:
            return
        if param.StorageType == DB.StorageType.String:
            param.Set(self._coord_mm_display(internal_feet_ord))
        elif param.StorageType == DB.StorageType.Double:
            param.Set(internal_feet_ord)

    def get_element_center(self, element):
        """Get the center point of the element."""
        loc = element.Location
        if isinstance(loc, DB.LocationPoint):
            return loc.Point
        # Fallback to BoundingBox if needed
        bbox = element.get_BoundingBox(None)
        if bbox:
            return (bbox.Min + bbox.Max) / 2.0
        return None

    def get_rotation_angle(self, element, inv_transform=None):
        """
        Rotation of the instance local X axis in the reporting plane (radians).
        When inv_transform is set (shared mode), BasisX is expressed in the same
        shared axes as X/Y coordinates so angles match plan / project north.
        """
        try:
            transform = element.GetTransform()
            basis_x = transform.BasisX
            if inv_transform is not None:
                basis_x = inv_transform.OfVector(basis_x)
            return math.atan2(basis_x.Y, basis_x.X)
        except Exception:
            return 0.0

    def ensure_parameters(self, param_definitions):
        """
        Ensure parameter definitions exist.
        param_definitions: dict { 'Name': SpecTypeId/ParameterType }
        """
        app = self.doc.Application
        
        # 1. Check if all exist to avoid overhead
        iterator = self.doc.ParameterBindings.ForwardIterator()
        existing_names = set()
        while iterator.MoveNext():
            if iterator.Key:
                existing_names.add(iterator.Key.Name)
                
        missing = {name: ptype for name, ptype in param_definitions.items() if name not in existing_names}
        if not missing:
            return 0, None
            
        # 2. Setup Shared Param File logic (Reused from logic_sheets)
        import os
        import tempfile
        
        original_file = app.SharedParametersFilename
        temp_file = None
        
        try:
            if not original_file or not os.path.exists(original_file):
                tf = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
                tf.close()
                temp_file = tf.name
                app.SharedParametersFilename = temp_file
            
            def_file = app.OpenSharedParameterFile()
            if not def_file:
                # Force temp
                tf = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
                tf.close()
                temp_file = tf.name
                app.SharedParametersFilename = temp_file
                def_file = app.OpenSharedParameterFile()
                
            if not def_file:
                return 0, "Could not open Shared Parameter file"

            grp = def_file.Groups.get_Item("NOSA_Coordinates")
            if not grp:
                grp = def_file.Groups.Create("NOSA_Coordinates")
                
            with revit.Transaction(u"NOSA — Create Coordinate Parameters"):
                cats = app.Create.NewCategorySet()
                cat = self.doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_StructuralFoundation)
                cats.Insert(cat)
                binding = app.Create.NewInstanceBinding(cats)
                
                # Determine Group (Data)
                try:
                    group_id = DB.GroupTypeId.Data
                except AttributeError:
                    group_id = DB.BuiltInParameterGroup.PG_DATA

                for name, req_type in missing.items():
                    defn = grp.Definitions.get_Item(name)
                    if not defn:
                        # Create definition
                        try:
                            # 2022+ support (ForgeTypeId/SpecTypeId)
                            # check if req_type is SpecTypeId (property of class)
                            # or just try/except
                            opt = DB.ExternalDefinitionCreationOptions(name, req_type)
                            defn = grp.Definitions.Create(opt)
                        except Exception as e:
                            # Fallback for older revit if req_type passed was SpecTypeId
                            # We need to map SpecTypeId back to ParameterType if we are in old Revit
                            # But here I assume I pass valid types for the running version in the caller
                            # Or I handle it here.
                            pass

                    if defn and not self.doc.ParameterBindings.Contains(defn):
                        self.doc.ParameterBindings.Insert(defn, binding, group_id)
                        
        except Exception as e:
            return 0, str(e)
        finally:
             if original_file: app.SharedParametersFilename = original_file
             if temp_file and os.path.exists(temp_file):
                 try: os.remove(temp_file)
                 except Exception: pass
                 
        return len(missing), None

    def _write_coords_to_element(self, el, param_x_name, param_y_name, param_rot_name,
                                  coord_mode, update_rotation, inv):
        """
        Write X/Y/Rotation to a single element.

        Does NOT open a Transaction — caller must already be inside one,
        or this must be called from a DMU Execute() context (which is always
        inside Revit's own transaction).  Returns True on success.
        """
        try:
            center = self.get_element_center(el)
            if not center:
                return False
            pt = self.compute_reporting_point(center, coord_mode, inv)
            p_x = el.LookupParameter(param_x_name)
            p_y = el.LookupParameter(param_y_name)
            self._set_coord_parameter(p_x, pt.X)
            self._set_coord_parameter(p_y, pt.Y)
            if update_rotation:
                p_rot = el.LookupParameter(param_rot_name)
                if p_rot and not p_rot.IsReadOnly:
                    p_rot.Set(self.get_rotation_angle(el, inv))
            return True
        except Exception:
            return False

    def update_coordinates(
        self,
        elements,
        param_x_name,
        param_y_name,
        param_rot_name,
        update_rotation=False,
        coord_mode="coordination",
    ):
        """
        Update X, Y, and rotation parameters for a list of elements.

        coord_mode:
          - 'coordination': absolute shared coordinates (recommended for BIM links).
          - 'survey': Spot-style relative to Survey Point (uses survey E/W, N/S, Elev).
          - 'project_base': Spot-style relative to Project Base Point.

        X and Y are written as mm text with comma grouping and 3 decimal places.
        Returns (success_count, fail_count).
        """
        try:
            spec_text = DB.SpecTypeId.String.Text
        except AttributeError:
            try:
                spec_text = DB.SpecTypeId.Text
            except AttributeError:
                spec_text = DB.ParameterType.Text
        try:
            spec_angle = DB.SpecTypeId.Angle
        except AttributeError:
            spec_angle = DB.ParameterType.Angle

        self.ensure_parameters({
            param_x_name:   spec_text,
            param_y_name:   spec_text,
            param_rot_name: spec_angle,
        })

        success = 0
        fail    = 0
        inv     = self._get_inverse_total_transform()

        with revit.Transaction(u"NOSA — Update Pile Coordinates"):
            restore = _ungroup_targets(self.doc, elements)
            for el in elements:
                if self._write_coords_to_element(
                    el, param_x_name, param_y_name, param_rot_name,
                    coord_mode, update_rotation, inv
                ):
                    success += 1
                else:
                    fail += 1
            if restore:
                _regroup_restore(self.doc, restore)

        return success, fail
