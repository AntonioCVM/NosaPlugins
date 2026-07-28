# -*- coding: utf-8 -*-
__title__ = "Align Element\nto Column"
__doc__ = """Aligns beams, ground beams, or pilecaps to column centers.

FEATURES v3.1:
✓ Beam end alignment to columns
✓ Ground beam alignment to columns
✓ Pilecap centering to columns (NEW)
✓ Option to align both beam ends
✓ Configurable max distance threshold
✓ Preview before alignment
✓ Progress reporting
"""
__author__  = "A. Viñas"
__version__ = "3.1"

from Autodesk.Revit import DB
from pyrevit import revit, forms, script
import sys
import json
import os

# Import NOSA utils library
extension_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
lib_path = os.path.join(extension_root, "lib")
if lib_path not in sys.path:
    sys.path.append(lib_path)
from nosa_utils import ui_helpers, geometry
from nosa_utils.revit_helpers import get_id_value

from Autodesk.Revit.DB import (
    BuiltInCategory, FamilyInstance, LocationCurve, Line, LocationPoint, XYZ,
    ElementTransformUtils
)

doc = revit.doc
output = script.get_output()

# =============================================================================
# CONFIGURATION
# =============================================================================

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')

DEFAULT_CONFIG = {
    'max_distance_mm': 1000,
    'align_both_ends': False,
    'include_pilecaps': True,
    'include_ground_beams': True
}

def load_config():
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                saved = json.load(f)
                result = DEFAULT_CONFIG.copy()
                result.update(saved)
                return result
    except Exception:
        pass
    return DEFAULT_CONFIG.copy()

def save_config(config):
    try:
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception:
        pass

MAX_CHANGE_WARNING_THRESHOLD = 0.3
MIN_BEAM_LENGTH_FT = 0.328

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def mm_to_ft(mm):
    return mm / 304.8

def ft_to_mm(ft):
    return ft * 304.8

def get_beam_endpoints(beam):
    """Get start and end points of a beam."""
    location = beam.Location
    if isinstance(location, LocationCurve):
        curve = location.Curve
        return curve.GetEndPoint(0), curve.GetEndPoint(1)
    return None, None

def get_element_center(element):
    """Get center point of any element (shared helper — also covers a
    bounding-box fallback for elements with neither LocationPoint nor
    LocationCurve, which the previous local copy here didn't handle)."""
    return geometry.get_element_center(element)

def get_column_center(column):
    """Get the center point of a column."""
    return get_element_center(column)

def calculate_distance_2d(point1, point2):
    """Calculate 2D distance between two points (ignoring Z)."""
    return geometry.calculate_distance_2d(point1, point2)

def calculate_distance_3d(point1, point2):
    """Calculate 3D distance between two points."""
    return geometry.calculate_distance_3d(point1, point2)

def find_closest_column(point, columns):
    """Find the closest column to a point."""
    closest_column = None
    min_distance = float('inf')
    
    for column in columns:
        column_centre = get_column_center(column)
        if column_centre:
            dist = calculate_distance_2d(point, column_centre)
            if dist < min_distance:
                min_distance = dist
                closest_column = column
    
    return closest_column, min_distance

def find_closest_column_for_beam(beam, columns, align_both=False):
    """Find closest column(s) for beam end(s)."""
    endpoints = get_beam_endpoints(beam)
    if not endpoints or not endpoints[0] or not endpoints[1]:
        return []
    
    results = []
    
    if align_both:
        # Find closest column for each end
        for end_index, endpoint in enumerate(endpoints):
            column, distance = find_closest_column(endpoint, columns)
            if column:
                results.append({
                    'end_index': end_index,
                    'endpoint': endpoint,
                    'column': column,
                    'distance': distance
                })
    else:
        # Find single closest column-endpoint pair
        min_distance = float('inf')
        best_result = None
        
        for column in columns:
            column_centre = get_column_center(column)
            if column_centre:
                for end_index, endpoint in enumerate(endpoints):
                    dist = calculate_distance_2d(endpoint, column_centre)
                    if dist < min_distance:
                        min_distance = dist
                        best_result = {
                            'end_index': end_index,
                            'endpoint': endpoint,
                            'column': column,
                            'distance': dist
                        }
        
        if best_result:
            results.append(best_result)
    
    return results

def move_beam_end_keep_level(beam, end_index, new_point):
    """Move beam end to new position while maintaining original Z level.
    
    For straight beams: Modifies the curve directly.
    For curved beams: Translates the entire beam to align the endpoint.
    """
    location = beam.Location
    if not isinstance(location, LocationCurve):
        return False, "Beam does not have location curve", {}
    
    curve = location.Curve
    old_end_point = curve.GetEndPoint(end_index)
    
    # Maintain original Z level
    new_point_with_level = XYZ(new_point.X, new_point.Y, old_end_point.Z)
    
    # Check if it's a straight beam (Line)
    is_straight = isinstance(curve, Line)
    
    if is_straight:
        # For straight beams: modify the curve directly
        other_index = 1 - end_index
        other_point = curve.GetEndPoint(other_index)
        
        # Calculate lengths
        original_length = curve.Length
        new_length = calculate_distance_3d(new_point_with_level, other_point)
        
        # Safety check
        short_curve_tolerance = doc.Application.ShortCurveTolerance
        if new_length <= short_curve_tolerance or new_length < MIN_BEAM_LENGTH_FT:
            return False, "Beam would be too short", {}
        
        # Warning for large changes
        length_change_ratio = abs(new_length - original_length) / original_length
        warning = None
        if length_change_ratio > MAX_CHANGE_WARNING_THRESHOLD:
            warning = "Large change: {:.1f}%".format(length_change_ratio * 100)
        
        # Create new curve
        if end_index == 0:
            new_curve = Line.CreateBound(new_point_with_level, other_point)
        else:
            new_curve = Line.CreateBound(other_point, new_point_with_level)
        
        location.Curve = new_curve
        
        return True, warning, {
            "original_length_mm": ft_to_mm(original_length),
            "new_length_mm": ft_to_mm(new_length),
            "change_percent": length_change_ratio * 100
        }
    else:
        # For curved beams (Arc): translate the entire beam
        # Calculate translation vector
        translation = XYZ(
            new_point_with_level.X - old_end_point.X,
            new_point_with_level.Y - old_end_point.Y,
            0  # Keep same Z
        )
        
        move_distance = translation.GetLength()
        
        # Move the beam
        ElementTransformUtils.MoveElement(doc, beam.Id, translation)
        
        return True, "Curved beam translated", {
            "move_distance_mm": ft_to_mm(move_distance),
            "is_curved": True
        }

def move_pilecap_to_column(pilecap, column):
    """Move pilecap center to column center."""
    pilecap_center = get_element_center(pilecap)
    column_center = get_column_center(column)
    
    if not pilecap_center or not column_center:
        return False, "Could not get element centers", {}
    
    # Calculate 2D movement (keep original Z)
    move_vector = XYZ(
        column_center.X - pilecap_center.X,
        column_center.Y - pilecap_center.Y,
        0  # Keep original Z level
    )
    
    distance = calculate_distance_2d(pilecap_center, column_center)
    
    # Move the pilecap
    ElementTransformUtils.MoveElement(doc, pilecap.Id, move_vector)
    
    return True, None, {
        "distance_mm": ft_to_mm(distance)
    }

def get_element_name(element):
    """Get a friendly name for an element."""
    try:
        family_name = element.Symbol.Family.Name if hasattr(element, 'Symbol') else "Unknown"
        type_name = element.Name if hasattr(element, 'Name') else ""
        return "{} : {}".format(family_name, type_name)
    except Exception:
        return "Element {}".format(element.Id)

def is_pilecap(element):
    """Check if element is a pilecap (structural foundation)."""
    try:
        cat_id = get_id_value(element.Category.Id)
        return cat_id == int(BuiltInCategory.OST_StructuralFoundation)
    except Exception:
        return False

def is_ground_beam(element):
    """Ground beams are structural foundations that behave like beams (LocationCurve)."""
    try:
        if get_id_value(element.Category.Id) != int(BuiltInCategory.OST_StructuralFoundation):
            return False
        return isinstance(element.Location, LocationCurve)
    except Exception:
        return False

# =============================================================================
# MAIN FUNCTION
# =============================================================================

def main():
    output.print_md("## 🔧 Align Element to Column")
    output.print_md("")
    
    config = load_config()
    
    # ==========================================================================
    # GET SELECTION
    # ==========================================================================
    
    selection = revit.get_selection()
    
    selected_beams = [
        el for el in selection 
        if isinstance(el, FamilyInstance) and 
        get_id_value(el.Category.Id) == int(BuiltInCategory.OST_StructuralFraming)
    ]
    
    selected_columns = [
        el for el in selection 
        if isinstance(el, FamilyInstance) and 
        get_id_value(el.Category.Id) == int(BuiltInCategory.OST_StructuralColumns)
    ]
    
    selected_foundations = [
        el for el in selection 
        if isinstance(el, FamilyInstance) and 
        get_id_value(el.Category.Id) == int(BuiltInCategory.OST_StructuralFoundation)
    ]

    selected_ground_beams = [el for el in selected_foundations if is_ground_beam(el)]
    selected_pilecaps = [el for el in selected_foundations if not is_ground_beam(el)]
    selected_beams_all = selected_beams + selected_ground_beams
    
    # ==========================================================================
    # VALIDATION
    # ==========================================================================
    
    has_elements = selected_beams_all or selected_pilecaps
    
    if not has_elements and not selected_columns:
        forms.alert(
            "No elements selected.\n\n"
            "Please select:\n"
            "- Beams AND/OR Pilecaps\n"
            "- AND at least one Column",
            title="Selection Required",
            exitscript=True
        )
        return
    
    if not has_elements:
        forms.alert(
            "No beams or pilecaps selected.\n\n"
            "Selected columns: {}\n"
            "Please also select beams/ground beams or pilecaps.".format(len(selected_columns)),
            title="Elements Required",
            exitscript=True
        )
        return
    
    if not selected_columns:
        forms.alert(
            "No columns selected.\n\n"
            "Selected beams: {}\n"
            "Selected ground beams: {}\n"
            "Selected pilecaps: {}\n"
            "Please also select at least one column.".format(
                len(selected_beams), len(selected_ground_beams), len(selected_pilecaps)
            ),
            title="Columns Required",
            exitscript=True
        )
        return
    
    output.print_md("**Selection:**")
    output.print_md("- 🔵 Beams: {}".format(len(selected_beams)))
    output.print_md("- 🟣 Ground Beams: {}".format(len(selected_ground_beams)))
    output.print_md("- 🟠 Pilecaps: {}".format(len(selected_pilecaps)))
    output.print_md("- 🟢 Columns: {}".format(len(selected_columns)))
    output.print_md("")
    
    # ==========================================================================
    # OPTIONS
    # ==========================================================================
    
    max_distance_mm = config.get('max_distance_mm', 1000)
    max_distance_ft = mm_to_ft(max_distance_mm)
    
    # Ask for both-ends alignment if beams selected
    align_both_ends = False
    if selected_beams_all:
        align_both_ends = ui_helpers.confirm_action(
            "Align BOTH ends of beams/ground beams to columns?\n\n"
            "Yes = Align both ends (each to closest column)\n"
            "No = Align only the closest end",
            title="Beam End Options"
        )
        config['align_both_ends'] = align_both_ends
        save_config(config)
    
    # ==========================================================================
    # COLLECT ALIGNMENTS
    # ==========================================================================
    
    output.print_md("### Preview of Alignments")
    output.print_md("")
    
    beam_alignments = []
    pilecap_alignments = []
    skipped = []
    
    # Process beams
    for beam in selected_beams_all:
        alignment_results = find_closest_column_for_beam(beam, selected_columns, align_both_ends)
        
        for result in alignment_results:
            if result['distance'] > max_distance_ft:
                skipped.append((beam, "Too far ({:.0f}mm > {}mm)".format(
                    ft_to_mm(result['distance']), max_distance_mm
                )))
                continue
            
            # Check if already aligned
            column_center = get_column_center(result['column'])
            if column_center:
                endpoint = result['endpoint']
                if abs(endpoint.X - column_center.X) < 0.001 and \
                   abs(endpoint.Y - column_center.Y) < 0.001:
                    skipped.append((beam, "Already aligned"))
                    continue
            
            beam_alignments.append({
                'beam': beam,
                'column': result['column'],
                'end_index': result['end_index'],
                'distance_mm': ft_to_mm(result['distance'])
            })
            
            beam_label = "Ground Beam" if is_ground_beam(beam) else "Beam"
            output.print_md("- **{} {}** end {} → **Column {}** ({:.0f}mm)".format(
                beam_label, beam.Id, result['end_index'], result['column'].Id, 
                ft_to_mm(result['distance'])
            ))
    
    # Process pilecaps
    for pilecap in selected_pilecaps:
        pilecap_center = get_element_center(pilecap)
        if not pilecap_center:
            skipped.append((pilecap, "Could not get center"))
            continue
        
        closest_column, distance = find_closest_column(pilecap_center, selected_columns)
        
        if not closest_column:
            skipped.append((pilecap, "No column found"))
            continue
        
        if distance > max_distance_ft:
            skipped.append((pilecap, "Too far ({:.0f}mm > {}mm)".format(
                ft_to_mm(distance), max_distance_mm
            )))
            continue
        
        # Check if already aligned
        column_center = get_column_center(closest_column)
        if column_center:
            if abs(pilecap_center.X - column_center.X) < 0.001 and \
               abs(pilecap_center.Y - column_center.Y) < 0.001:
                skipped.append((pilecap, "Already aligned"))
                continue
        
        pilecap_alignments.append({
            'pilecap': pilecap,
            'column': closest_column,
            'distance_mm': ft_to_mm(distance)
        })
        
        output.print_md("- **Pilecap {}** → **Column {}** ({:.0f}mm)".format(
            pilecap.Id, closest_column.Id, ft_to_mm(distance)
        ))
    
    if skipped:
        output.print_md("")
        output.print_md("**Skipped:**")
        for elem, reason in skipped:
            output.print_md("- {} {}: {}".format(
                "Pilecap" if is_pilecap(elem) else ("Ground Beam" if is_ground_beam(elem) else "Beam"),
                elem.Id, reason
            ))
    
    output.print_md("")
    
    total_alignments = len(beam_alignments) + len(pilecap_alignments)
    
    if total_alignments == 0:
        forms.alert(
            "No elements to align.\n\n"
            "All elements are either already aligned or too far from columns.",
            title="Nothing to Do"
        )
        return
    
    # ==========================================================================
    # CONFIRMATION
    # ==========================================================================
    
    if total_alignments > 1:
        if not ui_helpers.confirm_action(
            "Align {} elements?\n\n"
            "- Beam/Ground beam ends: {}\n"
            "- Pilecaps: {}".format(
                total_alignments, len(beam_alignments), len(pilecap_alignments)
            ),
            title="Confirm Alignment"
        ):
            forms.alert("Operation cancelled.", exitscript=True)
            return
    
    # ==========================================================================
    # EXECUTE ALIGNMENTS
    # ==========================================================================
    
    output.print_md("### Processing...")
    output.print_md("")
    
    beam_aligned = 0
    ground_beam_aligned = 0
    pilecap_aligned = 0
    failed = 0
    warnings = []
    
    with revit.Transaction("Align Elements to Columns"):
        # Align beams
        for alignment in beam_alignments:
            beam = alignment['beam']
            column = alignment['column']
            end_index = alignment['end_index']
            column_centre = get_column_center(column)
            
            if not column_centre:
                failed += 1
                continue
            
            success, warning, info = move_beam_end_keep_level(beam, end_index, column_centre)
            
            if success:
                if is_ground_beam(beam):
                    ground_beam_aligned += 1
                else:
                    beam_aligned += 1
                if warning:
                    warnings.append("Beam {}: {}".format(beam.Id, warning))
                label = "Ground Beam" if is_ground_beam(beam) else "Beam"
                output.print_md("✓ {} {} aligned".format(label, beam.Id))
            else:
                failed += 1
                output.print_md("✗ Beam {} failed: {}".format(beam.Id, warning))
        
        # Align pilecaps
        for alignment in pilecap_alignments:
            pilecap = alignment['pilecap']
            column = alignment['column']
            
            success, warning, info = move_pilecap_to_column(pilecap, column)
            
            if success:
                pilecap_aligned += 1
                output.print_md("✓ Pilecap {} aligned ({:.0f}mm)".format(
                    pilecap.Id, info.get('distance_mm', 0)
                ))
            else:
                failed += 1
                output.print_md("✗ Pilecap {} failed: {}".format(pilecap.Id, warning))
    
    # ==========================================================================
    # RESULTS
    # ==========================================================================
    
    output.print_md("")
    output.print_md("---")
    output.print_md("## ✅ Alignment Complete")
    output.print_md("")
    
    ui_helpers.display_results("Results", {
        "Beams Aligned": beam_aligned,
        "Ground Beams Aligned": ground_beam_aligned,
        "Pilecaps Aligned": pilecap_aligned,
        "Failed": failed,
        "Skipped": len(skipped)
    })
    
    if warnings:
        output.print_md("")
        output.print_md("### Warnings")
        for warning in warnings:
            output.print_md("- {}".format(warning))
    
    forms.alert(
        "Alignment Complete!\n\n"
        "✓ Beams: {}\n"
        "✓ Ground beams: {}\n"
        "✓ Pilecaps: {}\n"
        "✗ Failed: {}\n"
        "⊘ Skipped: {}".format(beam_aligned, ground_beam_aligned, pilecap_aligned, failed, len(skipped)),
        title="Alignment Complete"
    )



if __name__ == "__main__":
    main()

# -- usage tracking --
try:
    import nosa_utils.usage as _ut
    _ut.record('centerbeamtocolumn')
except Exception:
    pass
