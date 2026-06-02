# -*- coding: utf-8 -*-
__title__ = "Waffle\\nSlab"
__doc__ = """Creates real waffle slab (forjado reticular) with actual voids.

FEATURES v2.0:
✓ Real Floor elements (not DirectShape)
✓ Compression slab layer
✓ Actual openings/voids in base slab
✓ Interactive parameter UI
✓ Multi-standard validation (CTE/BS/IStructE)
✓ Auto-detection of columns
✓ Solid zones around columns
"""
__author__ = "Antonio Viñas - NOSA Engineering"
__version__ = "2.2"

from pyrevit import revit, forms, script, DB
import sys
import os
import json

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from System.Collections.Generic import List

doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()

# =============================================================================
# CONSTANTS
# =============================================================================

MM_TO_FEET = 0.00328084  # 1/304.8
FEET_TO_MM = 304.8

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')

DEFAULT_CONFIG = {
    'default_intereje': 800,
    'default_ancho_nervio': 120,
    'default_canto': 300,
    'default_losa': 50,
    'radio_macizado_factor': 1.5
}

# =============================================================================
# CONFIGURATION
# =============================================================================

def load_config():
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

def save_config(config):
    try:
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)
    except (IOError, OSError, TypeError, ValueError) as ex:
        output.print_md("⚠ Could not save config: {}".format(str(ex)))

# =============================================================================
# MULTI-STANDARD VALIDATION (CTE + BS + IStructE)
# =============================================================================

def validar_parametros_multinormativa(intereje, ancho_nervio, canto, espesor_losa):
    """
    Validates parameters according to:
    - CTE DB-SE-AE (Spain)
    - BS 8110 (UK)
    - IStructE recommendations
    
    Returns: (valid: bool, message: str, warnings: list)
    """
    warnings = []
    
    # Intereje validation
    # CTE: ≤1000mm, BS: ≤1500mm typically, IStructE: ≤1000mm preferred
    if not (500 <= intereje <= 1000):
        if intereje <= 1500:
            warnings.append("Rib spacing {0} mm exceeds CTE limit (1000 mm) but within BS 8110".format(intereje))
        else:
            return False, "Rib spacing out of range (500–1500 mm)", warnings
    
    # Rib width — EHE ≥100 mm, BS 8110 recommends ≥125 mm
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

# =============================================================================
# GEOMETRY HELPERS
# =============================================================================

def calculate_distance_2d(point1, point2):
    import math
    return math.sqrt(
        (point1.X - point2.X) ** 2 +
        (point1.Y - point2.Y) ** 2
    )


def _curve_samples_xy(curve):
    """Sample boundary curve to XY vertices for inclusion tests (lines + arcs)."""
    pts = []
    try:
        if isinstance(curve, Line):
            p0 = curve.GetEndPoint(0)
            p1 = curve.GetEndPoint(1)
            pts.append((p0.X, p0.Y))
            pts.append((p1.X, p1.Y))
        elif isinstance(curve, Arc):
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
    """Build closed 2D polygon from slab boundary curves (for point-in-polygon)."""
    poly = []
    for c in boundary_curves:
        poly.extend(_curve_samples_xy(c))
    if len(poly) < 3:
        return None
    return poly


def point_in_polygon_xy(x, y, poly):
    """Ray casting; poly is list of (x,y). If invalid poly, returns True (fail-open)."""
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
    location = element.Location
    if isinstance(location, LocationPoint):
        return location.Point
    elif isinstance(location, LocationCurve):
        curve = location.Curve
        return curve.Evaluate(0.5, True)
    return None

# =============================================================================
# FLOOR TYPE MANAGEMENT
# =============================================================================

def _get_element_name(element):
    """Safely get element name — module-level helper used by floor type functions."""
    try:
        return element.Name
    except Exception:
        pass
    try:
        name_param = element.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
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


def obtener_floor_type_estructural(doc):
    """Get appropriate structural FloorType"""
    floor_types = FilteredElementCollector(doc)\
        .OfClass(FloorType)\
        .WhereElementIsElementType()\
        .ToElements()
    
    if not floor_types:
        raise Exception(
            "No Floor Types found in project. "
            "Please load a Floor Type family before creating waffle slab."
        )
    
    # Try to find structural/concrete floor type
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

def crear_floor_type_con_espesor(doc, espesor_mm, nombre_tipo):
    """Create or get a FloorType with specific thickness"""
    try:
        # Get base floor type
        base_type = obtener_floor_type_estructural(doc)
        
        # Check if a type with this name already exists
        existing_types = FilteredElementCollector(doc)\
            .OfClass(FloorType)\
            .WhereElementIsElementType()\
            .ToElements()
        
        for ft in existing_types:
            try:
                if _get_element_name(ft) == nombre_tipo:
                    output.print_md("Using existing FloorType: **{}**".format(nombre_tipo))
                    return ft
            except Exception:
                continue
        
        # Duplicate the base type
        new_type_id = base_type.Duplicate(nombre_tipo)
        new_type = doc.GetElement(new_type_id)
        
        # Modify compound structure to have correct thickness
        compound_structure = new_type.GetCompoundStructure()
        
        if compound_structure:
            # Get the structural layer (usually the main layer)
            layer_count = compound_structure.LayerCount
            
            # Clear all layers and create a single structural layer
            for i in range(layer_count - 1, -1, -1):
                compound_structure.DeleteLayer(i)
            
            # Get a material for the layer (use first available structural material)
            material_id = None
            materials = FilteredElementCollector(doc).OfClass(Material).ToElements()
            for mat in materials:
                mat_name = _get_element_name(mat).lower() if hasattr(mat, 'Name') else ""
                if any(keyword in mat_name for keyword in ['concrete', 'hormigon', 'structural']):
                    material_id = mat.Id
                    break
            
            if not material_id and materials:
                material_id = materials[0].Id
            
            # Add single layer with correct thickness
            espesor_feet = espesor_mm * MM_TO_FEET
            compound_structure.SetLayerWidth(
                compound_structure.AppendLayer(
                    espesor_feet,
                    material_id if material_id else ElementId.InvalidElementId,
                    0  # Density (0 for structural)
                ),
                espesor_feet
            )
            
            # Set as structural deck
            compound_structure.StructuralMaterialIndex = 0
            compound_structure.SetNumberOfShellLayers(ShellLayerType.Exterior, 0)
            compound_structure.SetNumberOfShellLayers(ShellLayerType.Interior, 0)
            
            # Apply the modified structure
            new_type.SetCompoundStructure(compound_structure)
            
            output.print_md("Created FloorType: **{}** with {}mm thickness".format(nombre_tipo, espesor_mm))
            return new_type
        else:
            # If no compound structure, just return the duplicated type
            output.print_md("⚠ Could not modify thickness, using duplicated type")
            return new_type
            
    except Exception as e:
        output.print_md("⚠ Error creating custom floor type: {}".format(str(e)))
        # Fallback to base type
        return obtener_floor_type_estructural(doc)


# =============================================================================
# WAFFLE SLAB CREATOR CLASS (REAL FLOORS)
# =============================================================================

class ForjadoReticularReal:
    """Creates real waffle slab with Floor elements and openings"""
    
    def __init__(self, params):
        self.intereje = params['intereje']
        self.ancho_nervio = params['ancho_nervio']
        self.canto_total = params['canto']
        self.espesor_losa = params['losa']
        self.radio_factor = params.get('radio_macizado_factor', 1.5)
        
        self.doc = doc
        self.columnas = []
        self.zonas_macizadas = []
        
        # Results
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
        
        col_filter = ElementCategoryFilter(BuiltInCategory.OST_StructuralColumns)
        columnas_todas = FilteredElementCollector(self.doc)\
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
        """
        Calculate solid zones around columns
        modo: 'auto', 'global', 'individual'
        radio_global: radius in mm for 'global' mode
        radios_individuales: dict {column_id: radius_mm} for 'individual' mode
        """
        self.zonas_macizadas = []
        
        for i, col in enumerate(self.columnas):
            pt = col.Location.Point
            
            if modo == 'individual' and radios_individuales and i in radios_individuales:
                # Use individual radius specified by user
                radio = radios_individuales[i] * MM_TO_FEET
            elif modo == 'global' and radio_global:
                # Use global radius for all columns
                radio = radio_global * MM_TO_FEET
            else:
                # Auto mode: calculate from column size
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
        """Create floor with void boundaries in sketch for waffle pattern"""
        try:
            floor_type = obtener_floor_type_estructural(self.doc)
            
            if not floor_type:
                raise Exception("No valid floor type found")
            
            # Create CurveLoop from boundary curves (Revit 2024+ compatible)
            boundary_loop = CurveLoop()
            for curve in boundary_curves:
                boundary_loop.Append(curve)
            
            # Validate curve loop
            if not boundary_loop.HasPlane():
                raise Exception("Boundary curves do not form a valid planar loop")
            
            # Create IList[CurveLoop] - boundary + voids
            curve_loops = List[CurveLoop]()
            curve_loops.Add(boundary_loop)
            
            # Add void loops for each casetón position
            output.print_md("Adding {} void loops to floor sketch...".format(len(void_positions)))
            
            voids_added = 0
            for void_pos in void_positions:
                void_loop = self.crear_void_loop(void_pos['centro'], void_pos['dim_x'], void_pos['dim_y'])
                if void_loop:
                    try:
                        # Validate void loop doesn't intersect with others before adding
                        curve_loops.Add(void_loop)
                        voids_added += 1
                        self.openings_creados += 1
                    except Exception as e:
                        self.openings_fallidos += 1
                        if self.openings_fallidos <= 3:
                            output.print_md("⚠ Failed to add void {}: {}".format(voids_added, str(e)))
                else:
                    self.openings_fallidos += 1
            
            output.print_md("Successfully added {} voids to floor sketch".format(voids_added))
            
            # Create floor with boundary and voids using static Floor.Create method
            floor = Floor.Create(self.doc, curve_loops, floor_type.Id, nivel.Id)
            
            if not floor:
                raise Exception("Floor.Create returned None")
            
            # Set name parameter
            try:
                name_param = floor.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                if name_param and not name_param.IsReadOnly:
                    name_param.Set("Waffle Slab")
            except Exception:
                pass
            
            # Set height offset to base elevation
            param_offset = floor.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)
            if param_offset and not param_offset.IsReadOnly:
                param_offset.Set(elevacion_base)
            
            # Set structural parameter
            try:
                structural_param = floor.get_Parameter(BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL)
                if structural_param and not structural_param.IsReadOnly:
                    structural_param.Set(1)
            except Exception:
                pass
            
            return floor
            
        except Exception as e:
            import traceback
            output.print_md("⚠ Error creating floor with voids: {}".format(str(e)))
            output.print_md("```\n{}\n```".format(traceback.format_exc()))
            return None
    
    def crear_losa_compresion(self, boundary_curves, nivel, elevacion_base):
        """Create thin compression slab on top"""
        try:
            # Create or get FloorType with correct thickness
            tipo_nombre = "Losa Compresión {}mm".format(self.espesor_losa)
            floor_type = crear_floor_type_con_espesor(self.doc, self.espesor_losa, tipo_nombre)
            
            if not floor_type:
                raise Exception("Could not create floor type for compression slab")
            
            # Create CurveLoop from boundary curves
            boundary_loop = CurveLoop()
            for curve in boundary_curves:
                boundary_loop.Append(curve)
            
            if not boundary_loop.HasPlane():
                raise Exception("Boundary curves do not form a valid planar loop")
            
            # Create floor
            curve_loops = List[CurveLoop]()
            curve_loops.Add(boundary_loop)
            
            floor = Floor.Create(self.doc, curve_loops, floor_type.Id, nivel.Id)
            
            if not floor:
                raise Exception("Floor.Create returned None")
            
            # Set name
            try:
                name_param = floor.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                if name_param and not name_param.IsReadOnly:
                    name_param.Set("Waffle Slab - Compression Layer")
            except Exception:
                pass
            
            # Calculate elevation for BOTTOM FACE of compression slab
            # Bottom face should align with top face of main floor
            # Main floor top = elevacion_base + canto_total
            # Since compression slab has thickness espesor_losa, and FLOOR_HEIGHTABOVELEVEL 
            # is measured to BOTTOM face, we set it to the top of the ribs
            altura_nervios = (self.canto_total - self.espesor_losa) * MM_TO_FEET
            offset_compression = elevacion_base + altura_nervios
            
            # Set height offset for BOTTOM FACE
            param_offset = floor.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)
            if param_offset and not param_offset.IsReadOnly:
                param_offset.Set(offset_compression)
            
            # Set structural
            try:
                structural_param = floor.get_Parameter(BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL)
                if structural_param and not structural_param.IsReadOnly:
                    structural_param.Set(1)
            except Exception:
                pass
            
            return floor
            
        except Exception as e:
            import traceback
            output.print_md("⚠ Error creating compression slab: {}".format(str(e)))
            output.print_md("```\n{}\n```".format(traceback.format_exc()))
            return None
    
    def crear_void_loop(self, centro, dim_x, dim_y):
        """Create a CurveLoop for a void boundary (casetón)
        
        CRITICAL: Inner loops (voids) must be oriented CLOCKWISE (opposite to outer boundary)
        All curves must be in the same horizontal plane (Z must match boundary)
        """
        try:
            dx = dim_x * MM_TO_FEET / 2.0
            dy = dim_y * MM_TO_FEET / 2.0
            
            # Use same Z as boundary (voids are defined in same plane as floor sketch)
            z = centro.Z
            
            p1 = XYZ(centro.X - dx, centro.Y - dy, z)
            p2 = XYZ(centro.X + dx, centro.Y - dy, z)
            p3 = XYZ(centro.X + dx, centro.Y + dy, z)
            p4 = XYZ(centro.X - dx, centro.Y + dy, z)
            
            # Create void loop - CLOCKWISE orientation (p1→p4→p3→p2→p1)
            # This is OPPOSITE to the counterclockwise outer boundary
            void_loop = CurveLoop()
            void_loop.Append(Line.CreateBound(p1, p4))
            void_loop.Append(Line.CreateBound(p4, p3))
            void_loop.Append(Line.CreateBound(p3, p2))
            void_loop.Append(Line.CreateBound(p2, p1))
            
            # Validate the loop
            if void_loop.IsOpen():
                return None
            
            # Additional validation: must be planar and parallel to XY plane
            if not void_loop.HasPlane():
                return None
            
            return void_loop
            
        except Exception as e:
            if self.openings_fallidos == 0:
                output.print_md("⚠ Void loop error: {}".format(str(e)))
            return None
    
    def generar_forjado(self, boundary_curves, nivel=None):
        """Generate complete real waffle slab (two transactions: ribs/base, then compression)."""
        try:
            # Detect columns
            num_cols = self.detectar_columnas(boundary_curves)
            
            # Ask user for solid zone configuration
            zona_modo = 'auto'
            radio_global = None
            
            if num_cols > 0:
                from pyrevit import forms
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
                            output.print_md("⚠ Invalid radius, using automatic mode")
                elif zona_config == 'Skip solid zones':
                    zona_modo = 'skip'
            
            # Calculate solid zones
            if zona_modo != 'skip':
                self.calcular_zonas_macizadas(modo=zona_modo, radio_global=radio_global)
                output.print_md("**Detected {} columns with solid zones ({})**".format(
                    num_cols, 
                    "{}mm radius".format(radio_global) if zona_modo == 'global' else "automatic"
                ))
            else:
                output.print_md("**Detected {} columns (no solid zones)**".format(num_cols))
            
            # Calculate area limits
            puntos = []
            for c in boundary_curves:
                puntos.append(c.GetEndPoint(0))
                puntos.append(c.GetEndPoint(1))
            
            min_x = min(p.X for p in puntos)
            max_x = max(p.X for p in puntos)
            min_y = min(p.Y for p in puntos)
            max_y = max(p.Y for p in puntos)
            elev_base = min(p.Z for p in puntos)
            
            # Get or use active level
            if not nivel:
                nivel = self.doc.ActiveView.GenLevel
            
            # CALCULATE VOID POSITIONS (casetones)
            output.print_md("Calculating waffle void positions...")
            
            intereje_ft = self.intereje * MM_TO_FEET
            dim_caseton = self.intereje - self.ancho_nervio
            
            # Add substantial margin to avoid voids too close to edges
            # Need extra margin to account for void half-dimensions
            dim_caseton_ft = dim_caseton * MM_TO_FEET
            margin = (self.ancho_nervio * MM_TO_FEET) + (dim_caseton_ft / 2.0)
            
            void_positions = []
            poly_xy = boundary_polygon_xy(boundary_curves)
            if poly_xy is None:
                output.print_md("⚠ Could not tessellate boundary; voids use axis-aligned bounds only.")
            
            # Start grid with proper offset from boundaries
            y_cas = min_y + intereje_ft / 2.0 + margin
            while y_cas < max_y - margin:
                x_cas = min_x + intereje_ft / 2.0 + margin
                while x_cas < max_x - margin:
                    centro = XYZ(x_cas, y_cas, elev_base)
                    
                    if poly_xy is not None and not point_in_polygon_xy(centro.X, centro.Y, poly_xy):
                        x_cas += intereje_ft
                        continue
                    
                    # Skip if in solid zone around columns
                    if not self.punto_en_zona_macizada(centro):
                        void_positions.append({
                            'centro': centro,
                            'dim_x': dim_caseton,
                            'dim_y': dim_caseton
                        })
                    
                    x_cas += intereje_ft
                y_cas += intereje_ft
            
            output.print_md("Found {} void positions (inside boundary, excluding column zones)".format(len(void_positions)))
            
            # CREATE FLOOR WITH VOIDS (transaction 1 — avoids rolling back main slab if compression fails)
            output.print_md("Creating waffle slab floor with voids...")
            t1 = Transaction(self.doc, "NOSA — Waffle main slab")
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
                output.print_md("❌ **Error**: {}".format(str(e)))
                import traceback
                output.print_md("```\n{}\n```".format(traceback.format_exc()))
                return False
            
            # CREATE COMPRESSION SLAB (transaction 2)
            output.print_md("Creating compression slab ({} mm)...".format(self.espesor_losa))
            t2 = Transaction(self.doc, "NOSA — Compression slab")
            t2.Start()
            try:
                self.losa_compresion = self.crear_losa_compresion(boundary_curves, nivel, elev_base)
                t2.Commit()
            except Exception as e:
                t2.RollBack()
                output.print_md("⚠ Compression slab failed (main waffle slab kept): {}".format(str(e)))
            else:
                if not self.losa_compresion:
                    output.print_md("⚠ Warning: Compression slab was not created")
            
            return True
            
        except Exception as e:
            output.print_md("❌ **Error**: {}".format(str(e)))
            import traceback
            output.print_md("```\n{}\n```".format(traceback.format_exc()))
            return False

# =============================================================================
# UI FUNCTIONS
# =============================================================================

def solicitar_parametros_interactivos():
    """Interactive parameter input using sequential prompts"""
    config = load_config()
    
    # Rib spacing
    intereje_str = forms.ask_for_string(
        prompt="Enter rib spacing in mm:",
        default=str(config['default_intereje']),
        title="Waffle Slab - Rib Spacing (Intereje)"


    )
    if not intereje_str:
        return None
    
    # Rib width
    ancho_str = forms.ask_for_string(
        prompt="Enter rib width in mm:",
        default=str(config['default_ancho_nervio']),
        title="Waffle Slab - Rib Width"
    )
    if not ancho_str:
        return None
    
    # Total depth
    canto_str = forms.ask_for_string(
        prompt="Enter total slab depth in mm:",
        default=str(config['default_canto']),
        title="Waffle Slab - Total Depth (Canto)"
    )
    if not canto_str:
        return None
    
    # Compression slab
    losa_str = forms.ask_for_string(
        prompt="Enter compression slab thickness in mm:",
        default=str(config['default_losa']),
        title="Waffle Slab - Compression Slab"
    )
    if not losa_str:
        return None
    
    # Validate and convert
    try:
        params = {
            'intereje': int(intereje_str),
            'ancho_nervio': int(ancho_str),
            'canto': int(canto_str),
            'losa': int(losa_str),
            'radio_macizado_factor': config.get('radio_macizado_factor', 1.5)
        }
        return params
    except ValueError:
        forms.alert("Invalid numeric values. Please enter only whole numbers.", exitscript=True)
        return None

def seleccionar_boundary_curves():
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
                if isinstance(elem.Location, LocationCurve):
                    curves.append(elem.Location.Curve)
        
        return curves if curves else None
        
    except OperationCanceledException:
        forms.alert("Selection cancelled.", exitscript=True)
        return None
    except Exception as e:
        forms.alert("Selection error: {}".format(str(e)), exitscript=True)
        return None

def crear_boundary_rectangular():
    try:
        forms.alert(
            "Define rectangular area:\n\n"
            "1. Click first corner\n"
            "2. Click opposite corner",
            title="Rectangular Area"
        )
        
        punto1 = uidoc.Selection.PickPoint("Click first corner")
        punto2 = uidoc.Selection.PickPoint("Click opposite corner")
        
        p1 = XYZ(punto1.X, punto1.Y, punto1.Z)
        p2 = XYZ(punto2.X, punto1.Y, punto1.Z)
        p3 = XYZ(punto2.X, punto2.Y, punto2.Z)
        p4 = XYZ(punto1.X, punto2.Y, punto1.Z)
        
        curves = [
            Line.CreateBound(p1, p2),
            Line.CreateBound(p2, p3),
            Line.CreateBound(p3, p4),
            Line.CreateBound(p4, p1)
        ]
        
        return curves
        
    except OperationCanceledException:
        forms.alert("Selection cancelled.", exitscript=True)
        return None
    except Exception as e:
        forms.alert("Selection cancelled or error: {}".format(str(e)), exitscript=True)
        return None

# =============================================================================
# MAIN FUNCTION
# =============================================================================

def main():
    output.print_md("# 🏗 Real Waffle Slab Creator v2.2")
    output.print_md("")
    output.print_md("*Creates real Floor elements with actual voids*")
    output.print_md("")
    
    # Get parameters interactively
    params = solicitar_parametros_interactivos()
    
    if not params:
        forms.alert("Operation cancelled", exitscript=True)
        return
    save_config({
        'default_intereje': params['intereje'],
        'default_ancho_nervio': params['ancho_nervio'],
        'default_canto': params['canto'],
        'default_losa': params['losa'],
        'radio_macizado_factor': params.get('radio_macizado_factor', 1.5)
    })
    
    # Validate parameters with multi-standard check
    valido, mensaje, warnings = validar_parametros_multinormativa(
        params['intereje'],
        params['ancho_nervio'],
        params['canto'],
        params['losa']
    )
    
    if not valido:
        forms.alert(
            "Invalid parameters:\n\n{}".format(mensaje),
            title="Validation Error",
            exitscript=True
        )
        return
    
    output.print_md("✓ **Validation**: {}".format(mensaje))
    
    if warnings:
        output.print_md("")
        output.print_md("**Warnings**:")
        for warn in warnings:
            output.print_md("- ⚠ {}".format(warn))
    
    output.print_md("")
    output.print_md("**Parameters**:")
    output.print_md("- Rib spacing: {} mm".format(params['intereje']))
    output.print_md("- Rib width: {} mm".format(params['ancho_nervio']))
    output.print_md("- Total depth: {} mm".format(params['canto']))
    output.print_md("- Compression slab: {} mm".format(params['losa']))
    output.print_md("")
    
    # Select area definition method
    area_method = forms.CommandSwitchWindow.show(
        ['Rectangular area', 'Select existing lines'],
        message='How to define slab area?'
    )
    
    if area_method == 'Rectangular area':
        boundary = crear_boundary_rectangular()
    elif area_method == 'Select existing lines':
        boundary = seleccionar_boundary_curves()
    else:
        forms.alert("Operation cancelled", exitscript=True)
        return
    
    if not boundary:
        forms.alert("Could not get perimeter", exitscript=True)
        return
    
    output.print_md("**Area defined with {} curves**".format(len(boundary)))
    output.print_md("")
    
    # Create waffle slab
    creator = ForjadoReticularReal(params)
    success = creator.generar_forjado(boundary)
    
    if success:
        output.print_md("")
        output.print_md("---")
        output.print_md("# ✅ Real Waffle Slab Created Successfully!")
        output.print_md("")
        output.print_md("**Elements created**:")
        
        if creator.forjado_principal:
            output.print_md("- ✓ Main floor with voids (waffle pattern)")
        else:
            output.print_md("- ✗ Main floor failed")
        
        if creator.losa_compresion:
            output.print_md("- ✓ Compression slab ({} mm)".format(creator.espesor_losa))
        else:
            output.print_md("- ✗ Compression slab failed")
        
        output.print_md("- ✓ Voids created: {}".format(creator.openings_creados))
        if creator.openings_fallidos > 0:
            output.print_md("- ⚠ Voids failed: {} (likely too close to edges)".format(creator.openings_fallidos))
        output.print_md("- 🏛 Columns detected: {}".format(len(creator.columnas)))
        output.print_md("")
        output.print_md("**Note**: View in 3D or section to see the waffle pattern!")
        
        forms.alert(
            "Real Waffle Slab Created!\n\n"
            "✓ Main floor: {}\n"
            "✓ Compression slab: {}\n"
            "✓ Voids: {}\n"
            "⚠ Failed voids: {}\n"
            "🏛 Solid zones: {}\n\n"
            "Check 3D/section views to see the waffle structure!".format(
                "Yes" if creator.forjado_principal else "No",
                "Yes" if creator.losa_compresion else "No",
                creator.openings_creados,
                creator.openings_fallidos,
                len(creator.columnas)
            ),
            title="Success"
        )
    else:
        forms.alert("Failed to create waffle slab. Check output window.", exitscript=True)

if __name__ == "__main__":
    main()
