# -*- coding: utf-8 -*-
import os
import sys
import json
import imp
import traceback

from Autodesk.Revit import DB
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from System.Collections.Generic import List

_PLUGIN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_ext_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                         '..', '..', '..', '..', '..', 'lib'))
if _ext_lib not in sys.path:
    sys.path.insert(0, _ext_lib)

from nosa_utils import geometry
from nosa_utils import unit_conversion as _uc10

MM_TO_FEET = _uc10.MM_TO_FT
FEET_TO_MM = _uc10.FT_TO_MM

CONFIG_PATH = os.path.join(_PLUGIN_DIR, 'config.json')

DEFAULT_CONFIG = {
    'default_intereje': 800,
    'default_ancho_nervio': 120,
    'default_canto': 300,
    'default_losa': 50,
    'radio_macizado_factor': 1.5
}


def load_config(output):
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                saved = json.load(f)
                result = DEFAULT_CONFIG.copy()
                result.update(saved)
                return result
    except (IOError, OSError, ValueError) as ex:
        output.print_md("⚠ Could not read config file, using defaults: {}".format(str(ex)))
    return DEFAULT_CONFIG.copy()


def save_config(config, output):
    try:
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)
    except (IOError, OSError, TypeError, ValueError) as ex:
        output.print_md("⚠ Could not save config: {}".format(str(ex)))


def validate_parameters(grid_spacing, rib_width, depth, topping_thickness):
    warnings = []

    if not (500 <= grid_spacing <= 1000):
        if grid_spacing <= 1500:
            warnings.append("Rib spacing {0} mm exceeds CTE limit (1000 mm) but within BS 8110".format(grid_spacing))
        else:
            return False, "Rib spacing out of range (500–1500 mm)", warnings

    if rib_width < 100:
        return False, "Rib width < 100 mm (below EHE-08)", warnings
    elif rib_width < 125:
        warnings.append("Rib width {0} mm < 125 mm (BS 8110 recommendation)".format(rib_width))

    if rib_width >= grid_spacing:
        return False, "Rib width must be less than rib spacing", warnings

    if depth < 250:
        return False, "Minimum total depth 250 mm", warnings

    if not (40 <= topping_thickness <= 100):
        return False, "Compression slab thickness: 40–100 mm", warnings
    elif topping_thickness < 50:
        warnings.append("Compression slab {0} mm < 50 mm (BS 8110 minimum)".format(topping_thickness))

    if topping_thickness >= depth:
        return False, "Compression slab must be thinner than total depth", warnings

    return True, "Parameters valid (CTE / BS / IStructE compatible)", warnings


def calculate_distance_2d(point1, point2):
    return geometry.calculate_distance_2d(point1, point2)


def _curve_samples_xy(curve):
    pts = []
    try:
        if isinstance(curve, DB.Line):
            p0 = curve.GetEndPoint(0)
            p1 = curve.GetEndPoint(1)
            pts.append((p0.X, p0.Y))
            pts.append((p1.X, p1.Y))
        elif isinstance(curve, DB.Arc):
            steps = 12
            for k in range(steps + 1):
                t = float(k) / steps
                p = curve.Evaluate(t, True)
                pts.append((p.X, p.Y))
        else:
            p0 = curve.GetEndPoint(0)
            p1 = curve.GetEndPoint(1)
            pts.append((p0.X, p0.Y))
            pts.append((p1.X, p1.Y))
    except Exception:
        pass
    return pts


def boundary_polygon_xy(boundary_curves):
    poly = []
    for c in boundary_curves:
        poly.extend(_curve_samples_xy(c))
    if len(poly) < 3:
        return None
    return poly


def point_in_polygon_xy(x, y, poly):
    if not poly or len(poly) < 3:
        return True
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        denom = (yj - yi)
        if abs(denom) < 1e-18:
            j = i
            continue
        if (yi > y) != (yj > y):
            xinters = (xj - xi) * (y - yi) / denom + xi
            if x < xinters:
                inside = not inside
        j = i
    return inside


def get_element_center(element):
    return geometry.get_element_center(element)


def _get_element_name(element):
    try:
        return element.Name
    except Exception:
        pass
    try:
        name_param = element.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
        if name_param:
            return name_param.AsString()
    except Exception:
        pass
    try:
        name_param = element.LookupParameter("Type Name")
        if name_param:
            return name_param.AsString()
    except Exception:
        pass
    return "Unknown"


def get_structural_floor_type(doc, output):
    floor_types = DB.FilteredElementCollector(doc)\
        .OfClass(DB.FloorType)\
        .WhereElementIsElementType()\
        .ToElements()

    if not floor_types:
        raise Exception(
            "No Floor Types found in project. "
            "Please load a Floor Type family before creating waffle slab."
        )

    for ft in floor_types:
        try:
            name = _get_element_name(ft).lower()
            if any(keyword in name for keyword in ['rc', 'concrete', 'structural', 'losa', 'hormigon']):
                output.print_md("Using Floor Type: **{}**".format(_get_element_name(ft)))
                return ft
        except Exception:
            continue

    first_type = floor_types[0]
    output.print_md("Using Floor Type: **{}**".format(_get_element_name(first_type)))
    return first_type


def create_floor_type_with_thickness(doc, thickness_mm, type_name, output):
    try:
        base_type = get_structural_floor_type(doc, output)

        existing_types = DB.FilteredElementCollector(doc)\
            .OfClass(DB.FloorType)\
            .WhereElementIsElementType()\
            .ToElements()

        for ft in existing_types:
            try:
                if _get_element_name(ft) == type_name:
                    output.print_md("Using existing FloorType: **{}**".format(type_name))
                    return ft
            except Exception:
                continue

        new_type = base_type.Duplicate(type_name)
        if isinstance(new_type, DB.ElementId):
            new_type = doc.GetElement(new_type)

        material_id = DB.ElementId.InvalidElementId
        old_structure = new_type.GetCompoundStructure()
        if old_structure:
            material_id = old_structure.GetMaterialId(max(0, old_structure.StructuralMaterialIndex))
        if material_id == DB.ElementId.InvalidElementId:
            for mat in DB.FilteredElementCollector(doc).OfClass(DB.Material).ToElements():
                if any(k in _get_element_name(mat).lower() for k in ('concrete', 'hormigon', 'structural')):
                    material_id = mat.Id
                    break

        structure = DB.CompoundStructure.CreateSingleLayerCompoundStructure(
            DB.MaterialFunctionAssignment.Structure, thickness_mm * MM_TO_FEET, material_id)
        structure.StructuralMaterialIndex = 0
        if old_structure:
            structure.EndCap = old_structure.EndCap
        new_type.SetCompoundStructure(structure)

        output.print_md("Created FloorType: **{}** with {}mm thickness".format(type_name, thickness_mm))
        return new_type

    except Exception as e:
        output.print_md("⚠ Error creating custom floor type: {}".format(str(e)))
        return get_structural_floor_type(doc, output)


class WaffleSlabBuilder:
    """Creates real waffle slab with Floor elements and openings"""

    def __init__(self, doc, params, output):
        self.grid_spacing = params['intereje']
        self.rib_width = params['ancho_nervio']
        self.total_depth = params['canto']
        self.topping_thickness = params['losa']
        self.radius_factor = params.get('radio_macizado_factor', 1.5)

        self.doc = doc
        self.output = output
        self.columns = []
        self.solid_zones = []

        self.main_slab = None
        self.topping_slab = None
        self.openings_created = 0
        self.openings_failed = 0

    def detect_columns(self, boundary_curves):
        points = []
        for curve in boundary_curves:
            points.append(curve.GetEndPoint(0))
            points.append(curve.GetEndPoint(1))

        min_x = min(p.X for p in points)
        max_x = max(p.X for p in points)
        min_y = min(p.Y for p in points)
        max_y = max(p.Y for p in points)

        margin = 10 * MM_TO_FEET

        col_filter = DB.ElementCategoryFilter(DB.BuiltInCategory.OST_StructuralColumns)
        all_columns = DB.FilteredElementCollector(self.doc)\
            .WherePasses(col_filter)\
            .WhereElementIsNotElementType()

        self.columns = []
        for col in all_columns:
            if hasattr(col.Location, 'Point'):
                pt = col.Location.Point
                if (min_x - margin <= pt.X <= max_x + margin and
                    min_y - margin <= pt.Y <= max_y + margin):
                    self.columns.append(col)

        return len(self.columns)

    def compute_solid_zones(self, mode='auto', global_radius=None, individual_radii=None):
        self.solid_zones = []

        for i, col in enumerate(self.columns):
            pt = col.Location.Point

            if mode == 'individual' and individual_radii and i in individual_radii:
                radius = individual_radii[i] * MM_TO_FEET
            elif mode == 'global' and global_radius:
                radius = global_radius * MM_TO_FEET
            else:
                bbox = col.get_BoundingBox(None)
                if bbox:
                    width = abs(bbox.Max.X - bbox.Min.X)
                    length = abs(bbox.Max.Y - bbox.Min.Y)
                    dim_max = max(width, length)
                    radius = dim_max * self.radius_factor
                else:
                    radius = 1.2 * MM_TO_FEET

            self.solid_zones.append({
                'centro': pt,
                'radio': radius,
                'columna': col
            })

    def point_in_solid_zone(self, point):
        for zone in self.solid_zones:
            dist = calculate_distance_2d(point, zone['centro'])
            if dist < zone['radio']:
                return True
        return False

    def create_slab_with_recesses(self, boundary_curves, void_positions, level, base_elevation):
        try:
            rib_height_mm = self.total_depth - self.topping_thickness
            floor_type = create_floor_type_with_thickness(
                self.doc, rib_height_mm, u"Waffle Ribs {}mm".format(rib_height_mm), self.output)

            if not floor_type:
                raise Exception("No valid floor type found")

            boundary_loop = DB.CurveLoop()
            for curve in boundary_curves:
                boundary_loop.Append(curve)

            if not boundary_loop.HasPlane():
                raise Exception("Boundary curves do not form a valid planar loop")

            curve_loops = List[DB.CurveLoop]()
            curve_loops.Add(boundary_loop)

            self.output.print_md("Adding {} void loops to floor sketch...".format(len(void_positions)))

            voids_added = 0
            for void_pos in void_positions:
                void_loop = self.create_void_loop(void_pos['centro'], void_pos['dim_x'], void_pos['dim_y'])
                if void_loop:
                    try:
                        curve_loops.Add(void_loop)
                        voids_added += 1
                        self.openings_created += 1
                    except Exception as e:
                        self.openings_failed += 1
                        if self.openings_failed <= 3:
                            self.output.print_md("⚠ Failed to add void {}: {}".format(voids_added, str(e)))
                else:
                    self.openings_failed += 1

            self.output.print_md("Successfully added {} voids to floor sketch".format(voids_added))

            floor = DB.Floor.Create(self.doc, curve_loops, floor_type.Id, level.Id)

            if not floor:
                raise Exception("Floor.Create returned None")

            try:
                name_param = floor.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                if name_param and not name_param.IsReadOnly:
                    name_param.Set("Waffle Slab")
            except Exception:
                pass

            param_offset = floor.get_Parameter(DB.BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)
            if param_offset and not param_offset.IsReadOnly:
                # rib top sits under the compression slab
                param_offset.Set(base_elevation - level.Elevation - self.topping_thickness * MM_TO_FEET)

            try:
                structural_param = floor.get_Parameter(DB.BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL)
                if structural_param and not structural_param.IsReadOnly:
                    structural_param.Set(1)
            except Exception:
                pass

            return floor

        except Exception as e:
            self.output.print_md("⚠ Error creating floor with voids: {}".format(str(e)))
            self.output.print_md("```\n{}\n```".format(traceback.format_exc()))
            return None

    def create_topping_slab(self, boundary_curves, level, base_elevation):
        try:
            floor_type_name = u"Compression Slab {}mm".format(self.topping_thickness)
            floor_type = create_floor_type_with_thickness(self.doc, self.topping_thickness, floor_type_name, self.output)

            if not floor_type:
                raise Exception("Could not create floor type for compression slab")

            boundary_loop = DB.CurveLoop()
            for curve in boundary_curves:
                boundary_loop.Append(curve)

            if not boundary_loop.HasPlane():
                raise Exception("Boundary curves do not form a valid planar loop")

            curve_loops = List[DB.CurveLoop]()
            curve_loops.Add(boundary_loop)

            floor = DB.Floor.Create(self.doc, curve_loops, floor_type.Id, level.Id)

            if not floor:
                raise Exception("Floor.Create returned None")

            try:
                name_param = floor.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                if name_param and not name_param.IsReadOnly:
                    name_param.Set("Waffle Slab - Compression Layer")
            except Exception:
                pass

            offset_compression = base_elevation - level.Elevation

            param_offset = floor.get_Parameter(DB.BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)
            if param_offset and not param_offset.IsReadOnly:
                param_offset.Set(offset_compression)

            try:
                structural_param = floor.get_Parameter(DB.BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL)
                if structural_param and not structural_param.IsReadOnly:
                    structural_param.Set(1)
            except Exception:
                pass

            return floor

        except Exception as e:
            self.output.print_md("⚠ Error creating compression slab: {}".format(str(e)))
            self.output.print_md("```\n{}\n```".format(traceback.format_exc()))
            return None

    def create_void_loop(self, centre, dim_x, dim_y):
        try:
            dx = dim_x * MM_TO_FEET / 2.0
            dy = dim_y * MM_TO_FEET / 2.0

            z = centre.Z

            p1 = DB.XYZ(centre.X - dx, centre.Y - dy, z)
            p2 = DB.XYZ(centre.X + dx, centre.Y - dy, z)
            p3 = DB.XYZ(centre.X + dx, centre.Y + dy, z)
            p4 = DB.XYZ(centre.X - dx, centre.Y + dy, z)

            void_loop = DB.CurveLoop()
            void_loop.Append(DB.Line.CreateBound(p1, p4))
            void_loop.Append(DB.Line.CreateBound(p4, p3))
            void_loop.Append(DB.Line.CreateBound(p3, p2))
            void_loop.Append(DB.Line.CreateBound(p2, p1))

            if void_loop.IsOpen():
                return None

            if not void_loop.HasPlane():
                return None

            return void_loop

        except Exception as e:
            if self.openings_failed == 0:
                self.output.print_md("⚠ Void loop error: {}".format(str(e)))
            return None

    def generate_waffle_slab(self, boundary_curves, level=None):
        try:
            from pyrevit import forms

            num_cols = self.detect_columns(boundary_curves)

            zone_mode = 'auto'
            global_radius = None

            if num_cols > 0:
                zone_config = forms.CommandSwitchWindow.show(
                    ['Automatic (from column size)', 'Custom global radius', 'Skip solid zones'],
                    message='Configure solid zones around {} columns:'.format(num_cols)
                )

                if zone_config == 'Custom global radius':
                    radius_str = forms.ask_for_string(
                        prompt='Enter solid zone radius in mm\n(distance from column center):',
                        default=str(int(self.grid_spacing * 1.5)),
                        title='Solid Zone Radius'
                    )
                    if radius_str:
                        try:
                            global_radius = int(radius_str)
                            zone_mode = 'global'
                        except ValueError:
                            self.output.print_md("⚠ Invalid radius, using automatic mode")
                elif zone_config == 'Skip solid zones':
                    zone_mode = 'skip'

            if zone_mode != 'skip':
                self.compute_solid_zones(mode=zone_mode, global_radius=global_radius)
                self.output.print_md("**Detected {} columns with solid zones ({})**".format(
                    num_cols,
                    "{}mm radius".format(global_radius) if zone_mode == 'global' else "automatic"
                ))
            else:
                self.output.print_md("**Detected {} columns (no solid zones)**".format(num_cols))

            points = []
            for c in boundary_curves:
                points.append(c.GetEndPoint(0))
                points.append(c.GetEndPoint(1))

            min_x = min(p.X for p in points)
            max_x = max(p.X for p in points)
            min_y = min(p.Y for p in points)
            max_y = max(p.Y for p in points)
            elev_base = min(p.Z for p in points)

            if not level:
                level = self.doc.ActiveView.GenLevel

            self.output.print_md("Calculating waffle void positions...")

            grid_spacing_ft = self.grid_spacing * MM_TO_FEET
            void_dim = self.grid_spacing - self.rib_width

            void_dim_ft = void_dim * MM_TO_FEET
            margin = (self.rib_width * MM_TO_FEET) + (void_dim_ft / 2.0)

            void_positions = []
            poly_xy = boundary_polygon_xy(boundary_curves)
            if poly_xy is None:
                self.output.print_md("⚠ Could not tessellate boundary; voids use axis-aligned bounds only.")

            void_y = min_y + grid_spacing_ft / 2.0 + margin
            while void_y < max_y - margin:
                void_x = min_x + grid_spacing_ft / 2.0 + margin
                while void_x < max_x - margin:
                    centre = DB.XYZ(void_x, void_y, elev_base)

                    if poly_xy is not None and not point_in_polygon_xy(centre.X, centre.Y, poly_xy):
                        void_x += grid_spacing_ft
                        continue

                    if not self.point_in_solid_zone(centre):
                        void_positions.append({
                            'centro': centre,
                            'dim_x': void_dim,
                            'dim_y': void_dim
                        })

                    void_x += grid_spacing_ft
                void_y += grid_spacing_ft

            self.output.print_md("Found {} void positions (inside boundary, excluding column zones)".format(len(void_positions)))

            self.output.print_md("Creating waffle slab floor with voids...")
            t1 = DB.Transaction(self.doc, "NOSA — Waffle main slab")
            t1.Start()
            try:
                self.main_slab = self.create_slab_with_recesses(
                    boundary_curves,
                    void_positions,
                    level,
                    elev_base
                )
                if not self.main_slab:
                    raise Exception("Failed to create waffle slab floor")
                t1.Commit()
            except Exception as e:
                t1.RollBack()
                self.output.print_md("❌ **Error**: {}".format(str(e)))
                self.output.print_md("```\n{}\n```".format(traceback.format_exc()))
                return False

            self.output.print_md("Creating compression slab ({} mm)...".format(self.topping_thickness))
            t2 = DB.Transaction(self.doc, "NOSA — Compression slab")
            t2.Start()
            try:
                self.topping_slab = self.create_topping_slab(boundary_curves, level, elev_base)
                if self.topping_slab and self.main_slab:
                    try:
                        self.doc.Regenerate()
                        DB.JoinGeometryUtils.JoinGeometry(
                            self.doc, self.main_slab, self.topping_slab)
                    except Exception as e:
                        # Cosmetic only — both floors still exist and work
                        # independently even if the seam between them stays
                        # visible.
                        self.output.print_md(
                            "⚠ Could not join main slab and compression slab "
                            "(both created, seam may remain visible): {}".format(str(e)))
                t2.Commit()
            except Exception as e:
                t2.RollBack()
                self.output.print_md("⚠ Compression slab failed (main waffle slab kept): {}".format(str(e)))
            else:
                if not self.topping_slab:
                    self.output.print_md("⚠ Warning: Compression slab was not created")

            return True

        except Exception as e:
            self.output.print_md("❌ **Error**: {}".format(str(e)))
            self.output.print_md("```\n{}\n```".format(traceback.format_exc()))
            return False


def select_boundary_curves(doc, uidoc):
    from pyrevit import forms

    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element,
            "Select lines defining slab perimeter (ESC to cancel)"
        )

        if not refs:
            return None

        curves = []
        for ref in refs:
            elem = doc.GetElement(ref)

            if hasattr(elem, 'GeometryCurve'):
                curve = elem.GeometryCurve
                if curve:
                    curves.append(curve)
            elif hasattr(elem, 'Location'):
                if isinstance(elem.Location, DB.LocationCurve):
                    curves.append(elem.Location.Curve)

        return curves if curves else None

    except OperationCanceledException:
        forms.alert("Selection cancelled.", exitscript=True)
        return None
    except Exception as e:
        forms.alert("Selection error: {}".format(str(e)), exitscript=True)
        return None


def create_rectangular_boundary(uidoc):
    from pyrevit import forms

    try:
        forms.alert(
            "Define rectangular area:\n\n"
            "1. Click first corner\n"
            "2. Click opposite corner",
            title="Rectangular Area"
        )

        pt_a = uidoc.Selection.PickPoint("Click first corner")
        pt_b = uidoc.Selection.PickPoint("Click opposite corner")

        p1 = DB.XYZ(pt_a.X, pt_a.Y, pt_a.Z)
        p2 = DB.XYZ(pt_b.X, pt_a.Y, pt_a.Z)
        p3 = DB.XYZ(pt_b.X, pt_b.Y, pt_b.Z)
        p4 = DB.XYZ(pt_a.X, pt_b.Y, pt_a.Z)

        curves = [
            DB.Line.CreateBound(p1, p2),
            DB.Line.CreateBound(p2, p3),
            DB.Line.CreateBound(p3, p4),
            DB.Line.CreateBound(p4, p1)
        ]

        return curves

    except OperationCanceledException:
        forms.alert("Selection cancelled.", exitscript=True)
        return None
    except Exception as e:
        forms.alert("Selection cancelled or error: {}".format(str(e)), exitscript=True)
        return None


def show_preview(doc, params, boundary, PreviewWindowClass):
    pts_m = []
    for c in boundary:
        p0 = c.GetEndPoint(0)
        p1 = c.GetEndPoint(1)
        pts_m.append((p0.X * _uc10.FT_TO_M, p0.Y * _uc10.FT_TO_M))
        pts_m.append((p1.X * _uc10.FT_TO_M, p1.Y * _uc10.FT_TO_M))
    min_x = min(p[0] for p in pts_m)
    max_x = max(p[0] for p in pts_m)
    min_y = min(p[1] for p in pts_m)
    max_y = max(p[1] for p in pts_m)
    bbox = (min_x, min_y, max_x, max_y)

    col_locs = []
    try:
        for col in DB.FilteredElementCollector(doc)\
                .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)\
                .WhereElementIsNotElementType().ToElements():
            if hasattr(col.Location, 'Point'):
                pt = col.Location.Point
                cx_m = pt.X * _uc10.FT_TO_M
                cy_m = pt.Y * _uc10.FT_TO_M
                if min_x - 1 <= cx_m <= max_x + 1 and min_y - 1 <= cy_m <= max_y + 1:
                    col_locs.append((cx_m, cy_m))
    except Exception:
        pass

    preview = PreviewWindowClass(params, bbox, col_locs)

    if not preview.ShowDialog():
        return False
    return True
