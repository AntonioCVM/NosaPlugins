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


def validar_parametros_multinormativa(intereje, ancho_nervio, canto, espesor_losa):
    warnings = []

    if not (500 <= intereje <= 1000):
        if intereje <= 1500:
            warnings.append("Rib spacing {0} mm exceeds CTE limit (1000 mm) but within BS 8110".format(intereje))
        else:
            return False, "Rib spacing out of range (500–1500 mm)", warnings

    if ancho_nervio < 100:
        return False, "Rib width < 100 mm (below EHE-08)", warnings
    elif ancho_nervio < 125:
        warnings.append("Rib width {0} mm < 125 mm (BS 8110 recommendation)".format(ancho_nervio))

    if ancho_nervio >= intereje:
        return False, "Rib width must be less than rib spacing", warnings

    if canto < 250:
        return False, "Minimum total depth 250 mm", warnings

    if not (40 <= espesor_losa <= 100):
        return False, "Compression slab thickness: 40–100 mm", warnings
    elif espesor_losa < 50:
        warnings.append("Compression slab {0} mm < 50 mm (BS 8110 minimum)".format(espesor_losa))

    if espesor_losa >= canto:
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


def obtener_floor_type_estructural(doc, output):
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


def crear_floor_type_con_espesor(doc, espesor_mm, nombre_tipo, output):
    try:
        base_type = obtener_floor_type_estructural(doc, output)

        existing_types = DB.FilteredElementCollector(doc)\
            .OfClass(DB.FloorType)\
            .WhereElementIsElementType()\
            .ToElements()

        for ft in existing_types:
            try:
                if _get_element_name(ft) == nombre_tipo:
                    output.print_md("Using existing FloorType: **{}**".format(nombre_tipo))
                    return ft
            except Exception:
                continue

        new_type_id = base_type.Duplicate(nombre_tipo)
        new_type = doc.GetElement(new_type_id)

        compound_structure = new_type.GetCompoundStructure()

        if compound_structure:
            layer_count = compound_structure.LayerCount

            for i in range(layer_count - 1, -1, -1):
                compound_structure.DeleteLayer(i)

            material_id = None
            materials = DB.FilteredElementCollector(doc).OfClass(DB.Material).ToElements()
            for mat in materials:
                mat_name = _get_element_name(mat).lower() if hasattr(mat, 'Name') else ""
                if any(keyword in mat_name for keyword in ['concrete', 'hormigon', 'structural']):
                    material_id = mat.Id
                    break

            if not material_id and materials:
                material_id = materials[0].Id

            espesor_feet = espesor_mm * MM_TO_FEET
            compound_structure.SetLayerWidth(
                compound_structure.AppendLayer(
                    espesor_feet,
                    material_id if material_id else DB.ElementId.InvalidElementId,
                    0
                ),
                espesor_feet
            )

            compound_structure.StructuralMaterialIndex = 0
            compound_structure.SetNumberOfShellLayers(DB.ShellLayerType.Exterior, 0)
            compound_structure.SetNumberOfShellLayers(DB.ShellLayerType.Interior, 0)

            new_type.SetCompoundStructure(compound_structure)

            output.print_md("Created FloorType: **{}** with {}mm thickness".format(nombre_tipo, espesor_mm))
            return new_type
        else:
            output.print_md("⚠ Could not modify thickness, using duplicated type")
            return new_type

    except Exception as e:
        output.print_md("⚠ Error creating custom floor type: {}".format(str(e)))
        return obtener_floor_type_estructural(doc, output)


class ForjadoReticularReal:
    """Creates real waffle slab with Floor elements and openings"""

    def __init__(self, doc, params, output):
        self.intereje = params['intereje']
        self.ancho_nervio = params['ancho_nervio']
        self.canto_total = params['canto']
        self.espesor_losa = params['losa']
        self.radio_factor = params.get('radio_macizado_factor', 1.5)

        self.doc = doc
        self.output = output
        self.columnas = []
        self.zonas_macizadas = []

        self.forjado_principal = None
        self.losa_compresion = None
        self.openings_creados = 0
        self.openings_fallidos = 0

    def detectar_columnas(self, boundary_curves):
        puntos = []
        for curve in boundary_curves:
            puntos.append(curve.GetEndPoint(0))
            puntos.append(curve.GetEndPoint(1))

        min_x = min(p.X for p in puntos)
        max_x = max(p.X for p in puntos)
        min_y = min(p.Y for p in puntos)
        max_y = max(p.Y for p in puntos)

        margin = 10 * MM_TO_FEET

        col_filter = DB.ElementCategoryFilter(DB.BuiltInCategory.OST_StructuralColumns)
        columnas_todas = DB.FilteredElementCollector(self.doc)\
            .WherePasses(col_filter)\
            .WhereElementIsNotElementType()

        self.columnas = []
        for col in columnas_todas:
            if hasattr(col.Location, 'Point'):
                pt = col.Location.Point
                if (min_x - margin <= pt.X <= max_x + margin and
                    min_y - margin <= pt.Y <= max_y + margin):
                    self.columnas.append(col)

        return len(self.columnas)

    def calcular_zonas_macizadas(self, modo='auto', radio_global=None, radios_individuales=None):
        self.zonas_macizadas = []

        for i, col in enumerate(self.columnas):
            pt = col.Location.Point

            if modo == 'individual' and radios_individuales and i in radios_individuales:
                radio = radios_individuales[i] * MM_TO_FEET
            elif modo == 'global' and radio_global:
                radio = radio_global * MM_TO_FEET
            else:
                bbox = col.get_BoundingBox(None)
                if bbox:
                    ancho = abs(bbox.Max.X - bbox.Min.X)
                    largo = abs(bbox.Max.Y - bbox.Min.Y)
                    dim_max = max(ancho, largo)
                    radio = dim_max * self.radio_factor
                else:
                    radio = 1.2 * MM_TO_FEET

            self.zonas_macizadas.append({
                'centro': pt,
                'radio': radio,
                'columna': col
            })

    def punto_en_zona_macizada(self, punto):
        for zona in self.zonas_macizadas:
            dist = calculate_distance_2d(punto, zona['centro'])
            if dist < zona['radio']:
                return True
        return False

    def crear_forjado_con_rebajes(self, boundary_curves, void_positions, nivel, elevacion_base):
        try:
            floor_type = obtener_floor_type_estructural(self.doc, self.output)

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
                void_loop = self.crear_void_loop(void_pos['centro'], void_pos['dim_x'], void_pos['dim_y'])
                if void_loop:
                    try:
                        curve_loops.Add(void_loop)
                        voids_added += 1
                        self.openings_creados += 1
                    except Exception as e:
                        self.openings_fallidos += 1
                        if self.openings_fallidos <= 3:
                            self.output.print_md("⚠ Failed to add void {}: {}".format(voids_added, str(e)))
                else:
                    self.openings_fallidos += 1

            self.output.print_md("Successfully added {} voids to floor sketch".format(voids_added))

            floor = DB.Floor.Create(self.doc, curve_loops, floor_type.Id, nivel.Id)

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
                param_offset.Set(elevacion_base)

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

    def crear_losa_compresion(self, boundary_curves, nivel, elevacion_base):
        try:
            tipo_nombre = "Losa Compresión {}mm".format(self.espesor_losa)
            floor_type = crear_floor_type_con_espesor(self.doc, self.espesor_losa, tipo_nombre, self.output)

            if not floor_type:
                raise Exception("Could not create floor type for compression slab")

            boundary_loop = DB.CurveLoop()
            for curve in boundary_curves:
                boundary_loop.Append(curve)

            if not boundary_loop.HasPlane():
                raise Exception("Boundary curves do not form a valid planar loop")

            curve_loops = List[DB.CurveLoop]()
            curve_loops.Add(boundary_loop)

            floor = DB.Floor.Create(self.doc, curve_loops, floor_type.Id, nivel.Id)

            if not floor:
                raise Exception("Floor.Create returned None")

            try:
                name_param = floor.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                if name_param and not name_param.IsReadOnly:
                    name_param.Set("Waffle Slab - Compression Layer")
            except Exception:
                pass

            altura_nervios = (self.canto_total - self.espesor_losa) * MM_TO_FEET
            offset_compression = elevacion_base + altura_nervios

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

    def crear_void_loop(self, centro, dim_x, dim_y):
        try:
            dx = dim_x * MM_TO_FEET / 2.0
            dy = dim_y * MM_TO_FEET / 2.0

            z = centro.Z

            p1 = DB.XYZ(centro.X - dx, centro.Y - dy, z)
            p2 = DB.XYZ(centro.X + dx, centro.Y - dy, z)
            p3 = DB.XYZ(centro.X + dx, centro.Y + dy, z)
            p4 = DB.XYZ(centro.X - dx, centro.Y + dy, z)

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
            if self.openings_fallidos == 0:
                self.output.print_md("⚠ Void loop error: {}".format(str(e)))
            return None

    def generar_forjado(self, boundary_curves, nivel=None):
        try:
            from pyrevit import forms

            num_cols = self.detectar_columnas(boundary_curves)

            zona_modo = 'auto'
            radio_global = None

            if num_cols > 0:
                zona_config = forms.CommandSwitchWindow.show(
                    ['Automatic (from column size)', 'Custom global radius', 'Skip solid zones'],
                    message='Configure solid zones around {} columns:'.format(num_cols)
                )

                if zona_config == 'Custom global radius':
                    radio_str = forms.ask_for_string(
                        prompt='Enter solid zone radius in mm\n(distance from column center):',
                        default=str(int(self.intereje * 1.5)),
                        title='Solid Zone Radius'
                    )
                    if radio_str:
                        try:
                            radio_global = int(radio_str)
                            zona_modo = 'global'
                        except ValueError:
                            self.output.print_md("⚠ Invalid radius, using automatic mode")
                elif zona_config == 'Skip solid zones':
                    zona_modo = 'skip'

            if zona_modo != 'skip':
                self.calcular_zonas_macizadas(modo=zona_modo, radio_global=radio_global)
                self.output.print_md("**Detected {} columns with solid zones ({})**".format(
                    num_cols,
                    "{}mm radius".format(radio_global) if zona_modo == 'global' else "automatic"
                ))
            else:
                self.output.print_md("**Detected {} columns (no solid zones)**".format(num_cols))

            puntos = []
            for c in boundary_curves:
                puntos.append(c.GetEndPoint(0))
                puntos.append(c.GetEndPoint(1))

            min_x = min(p.X for p in puntos)
            max_x = max(p.X for p in puntos)
            min_y = min(p.Y for p in puntos)
            max_y = max(p.Y for p in puntos)
            elev_base = min(p.Z for p in puntos)

            if not nivel:
                nivel = self.doc.ActiveView.GenLevel

            self.output.print_md("Calculating waffle void positions...")

            intereje_ft = self.intereje * MM_TO_FEET
            dim_caseton = self.intereje - self.ancho_nervio

            dim_caseton_ft = dim_caseton * MM_TO_FEET
            margin = (self.ancho_nervio * MM_TO_FEET) + (dim_caseton_ft / 2.0)

            void_positions = []
            poly_xy = boundary_polygon_xy(boundary_curves)
            if poly_xy is None:
                self.output.print_md("⚠ Could not tessellate boundary; voids use axis-aligned bounds only.")

            y_cas = min_y + intereje_ft / 2.0 + margin
            while y_cas < max_y - margin:
                x_cas = min_x + intereje_ft / 2.0 + margin
                while x_cas < max_x - margin:
                    centro = DB.XYZ(x_cas, y_cas, elev_base)

                    if poly_xy is not None and not point_in_polygon_xy(centro.X, centro.Y, poly_xy):
                        x_cas += intereje_ft
                        continue

                    if not self.punto_en_zona_macizada(centro):
                        void_positions.append({
                            'centro': centro,
                            'dim_x': dim_caseton,
                            'dim_y': dim_caseton
                        })

                    x_cas += intereje_ft
                y_cas += intereje_ft

            self.output.print_md("Found {} void positions (inside boundary, excluding column zones)".format(len(void_positions)))

            self.output.print_md("Creating waffle slab floor with voids...")
            t1 = DB.Transaction(self.doc, "NOSA — Waffle main slab")
            t1.Start()
            try:
                self.forjado_principal = self.crear_forjado_con_rebajes(
                    boundary_curves,
                    void_positions,
                    nivel,
                    elev_base
                )
                if not self.forjado_principal:
                    raise Exception("Failed to create waffle slab floor")
                t1.Commit()
            except Exception as e:
                t1.RollBack()
                self.output.print_md("❌ **Error**: {}".format(str(e)))
                self.output.print_md("```\n{}\n```".format(traceback.format_exc()))
                return False

            self.output.print_md("Creating compression slab ({} mm)...".format(self.espesor_losa))
            t2 = DB.Transaction(self.doc, "NOSA — Compression slab")
            t2.Start()
            try:
                self.losa_compresion = self.crear_losa_compresion(boundary_curves, nivel, elev_base)
                if self.losa_compresion and self.forjado_principal:
                    try:
                        DB.JoinGeometryUtils.JoinGeometry(
                            self.doc, self.forjado_principal, self.losa_compresion)
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
                if not self.losa_compresion:
                    self.output.print_md("⚠ Warning: Compression slab was not created")

            return True

        except Exception as e:
            self.output.print_md("❌ **Error**: {}".format(str(e)))
            self.output.print_md("```\n{}\n```".format(traceback.format_exc()))
            return False


def seleccionar_boundary_curves(doc, uidoc):
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


def crear_boundary_rectangular(uidoc):
    from pyrevit import forms

    try:
        forms.alert(
            "Define rectangular area:\n\n"
            "1. Click first corner\n"
            "2. Click opposite corner",
            title="Rectangular Area"
        )

        punto1 = uidoc.Selection.PickPoint("Click first corner")
        punto2 = uidoc.Selection.PickPoint("Click opposite corner")

        p1 = DB.XYZ(punto1.X, punto1.Y, punto1.Z)
        p2 = DB.XYZ(punto2.X, punto1.Y, punto1.Z)
        p3 = DB.XYZ(punto2.X, punto2.Y, punto2.Z)
        p4 = DB.XYZ(punto1.X, punto2.Y, punto1.Z)

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
        pts_m.append((p0.X * 304.8 / 1000.0, p0.Y * 304.8 / 1000.0))
        pts_m.append((p1.X * 304.8 / 1000.0, p1.Y * 304.8 / 1000.0))
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
                cx_m = pt.X * 304.8 / 1000.0
                cy_m = pt.Y * 304.8 / 1000.0
                if min_x - 1 <= cx_m <= max_x + 1 and min_y - 1 <= cy_m <= max_y + 1:
                    col_locs.append((cx_m, cy_m))
    except Exception:
        pass

    preview = PreviewWindowClass(params, bbox, col_locs)

    if not preview.ShowDialog():
        return False
    return True
