# -*- coding: utf-8 -*-
from Autodesk.Revit import DB
from pyrevit import revit
from nosa_utils.revit_helpers import element_name
from nosa_utils.telemetry import log_swallowed
_LOG = u'annotationhub'

class DimensionLogic:
    def __init__(self, doc):
        self.doc = doc

    def get_valid_walls_in_view(self, view):
        """Get all walls in view that are valid for dimensioning."""
        collector = DB.FilteredElementCollector(self.doc, view.Id)\
            .OfCategory(DB.BuiltInCategory.OST_Walls)\
            .WhereElementIsNotElementType()
        
        return list(collector.ToElements())

    def get_name(self, element):
        return element_name(element) or str(element.Id)

    def get_dimension_types(self):
        """Get all Linear and Radial dimension types."""
        linear_types = []
        
        for dt in DB.FilteredElementCollector(self.doc).OfClass(DB.DimensionType).ToElements():
            try:
                # We need a linear style for length/arc length
                if dt.StyleType == DB.DimensionStyleType.Linear:
                    linear_types.append(dt)
            except Exception:
                continue
                
        return sorted(linear_types, key=lambda x: self.get_name(x))

    def mm_to_internal(self, mm):
        return DB.UnitUtils.ConvertToInternalUnits(mm, DB.UnitTypeId.Millimeters)

    # =========================================================================
    # GEOMETRY HELPERS
    # =========================================================================

    def get_wall_curve_data(self, wall):
        """Get basic curve data."""
        curve = wall.Location.Curve
        is_arc = isinstance(curve, DB.Arc)
        
        if is_arc:
            deriv = curve.ComputeDerivatives(0.5, True)
            tangent = deriv.BasisX.Normalize()
            mid_pt = curve.Evaluate(0.5, True)
            center = curve.Center
            radius = curve.Radius
        else:
            tangent = curve.Direction.Normalize()
            mid_pt = curve.Evaluate(0.5, True)
            center = None
            radius = 0.0
            
        perp_dir = tangent.CrossProduct(DB.XYZ.BasisZ).Normalize()
        
        return {
            'curve': curve,
            'is_arc': is_arc,
            'tangent': tangent,
            'perp': perp_dir,
            'mid_pt': mid_pt,
            'start_pt': curve.GetEndPoint(0),
            'end_pt': curve.GetEndPoint(1),
            'center': center,
            'radius': radius
        }

    def get_solids_with_views_options(self, element, view):
        """Get solids using query options that return valid references."""
        opts = DB.Options()
        opts.ComputeReferences = True
        opts.IncludeNonVisibleObjects = True
        opts.View = view
        
        geom = element.get_Geometry(opts)
        if not geom: return []
        
        solids = []
        for obj in geom:
            if isinstance(obj, DB.Solid) and obj.Faces.Size > 0:
                solids.append(obj)
            elif isinstance(obj, DB.GeometryInstance):
                inst_geom = obj.GetInstanceGeometry()
                for inst_obj in inst_geom:
                    if isinstance(inst_obj, DB.Solid) and inst_obj.Faces.Size > 0:
                        solids.append(inst_obj)
        return solids

    def get_wall_references(self, wall, view):
        """Get references for start and end of wall, prioritizing Exterior faces."""
        try:
            # Method 1: HostObjectUtils (Most reliable for "Exterior" faces)
            # This returns the side faces (long faces), not end faces.
            # But for Arc Length, we need references *at the ends*.
            pass
        except Exception:
            log_swallowed(_LOG, u'DimensionLogic.get_wall_references')
            
        # For standard Length/Arc Length, we actually need references perpendicular to the wall direction at the ends.
        # Finding those is tricky with HostObjectUtils (which gives side faces).
        # We stick to Geometry analysis but refine it to pick the "outermost" text.
        
        solids = self.get_solids_with_views_options(wall, view)
        if not solids: return None

        geo = self.get_wall_curve_data(wall)

        # Determine "Outside" vector if possible, or just Start/End
        # For a single wall, Start/End is clear.
        # For joined walls, we want the "free" ends or the intersection points?
        # User image shows dimensions processing the *entire* length of the wall chain segments?
        # No, image shows individual wall dimensions but placed clearly.

        # Let's verify we are getting the END faces.

        candidates = []

        # Vector for projecting candidates along the wall (used for sorting
        # start-vs-end only — NOT for the alignment test below).
        if geo['is_arc']:
            axis = (geo['end_pt'] - geo['start_pt']).Normalize()
            # An arc wall's end-cap face normal follows the arc's LOCAL
            # tangent at that specific end, not the overall chord — using
            # one fixed chord axis for both ends under-detects end faces on
            # walls with a large sweep angle (the two tangents diverge
            # further from the chord as the sweep grows).
            start_tangent = geo['curve'].ComputeDerivatives(0.0, True).BasisX.Normalize()
            end_tangent   = geo['curve'].ComputeDerivatives(1.0, True).BasisX.Normalize()
        else:
            axis = geo['tangent']
            start_tangent = end_tangent = axis

        ref_pt = geo['start_pt']
        wall_span = (geo['end_pt'] - geo['start_pt']).DotProduct(axis)

        for solid in solids:
            for face in solid.Faces:
                # We want vertical faces
                normal = face.ComputeNormal(DB.UV(0.5,0.5))
                if abs(normal.Z) > 0.1: continue

                if not face.Reference:
                    continue

                centroid = face.Evaluate(DB.UV(0.5,0.5))
                proj = (centroid - ref_pt).DotProduct(axis)

                # Check alignment against the LOCAL tangent for whichever
                # end this candidate is closer to.
                local_axis = start_tangent if proj < wall_span * 0.5 else end_tangent
                dot = normal.DotProduct(local_axis)
                if abs(dot) < 0.7: continue # Ignore side faces

                candidates.append((proj, face.Reference))

        if len(candidates) < 2: return None
        
        candidates.sort(key=lambda x: x[0])
        
        # Return the two extremes (furthest apart)
        # This handles joined walls where multiple faces might exist at one end? 
        # Usually valid end faces are unique per end.
        return candidates[0][1], candidates[-1][1]

    # =========================================================================
    # CREATE DIMENSIONS
    # =========================================================================

    def find_crossing_grids(self, wall, view):
        """
        Grids whose direction is roughly perpendicular to the wall's own
        direction (i.e. grids that cross the wall along its length, the
        usual structural set-out reference) and whose line crosses near the
        wall's span. Returns [(position_ft, Reference), ...] sorted by
        position along the wall's tangent, position=0 at the wall start.
        Only straight (Line) grids are considered — arc grids are rare and
        the perpendicular test below doesn't apply to them cleanly.
        """
        geo = self.get_wall_curve_data(wall)
        tangent = geo['tangent'] if not geo['is_arc'] else (geo['end_pt'] - geo['start_pt']).Normalize()
        start_pt = geo['start_pt']
        wall_len = geo['start_pt'].DistanceTo(geo['end_pt'])

        results = []
        try:
            grids = DB.FilteredElementCollector(self.doc, view.Id).OfClass(DB.Grid).ToElements()
        except Exception:
            return results

        for g in grids:
            try:
                gcurve = g.Curve
                if not isinstance(gcurve, DB.Line):
                    continue
                g0 = gcurve.GetEndPoint(0)
                g1 = gcurve.GetEndPoint(1)
                gdir = (g1 - g0).Normalize()

                # Must cross the wall, not run alongside it.
                if abs(gdir.DotProduct(tangent)) > 0.2:
                    continue

                # 2D line-line intersection (wall axis vs grid axis), plan only.
                denom = tangent.X * gdir.Y - tangent.Y * gdir.X
                if abs(denom) < 1e-9:
                    continue
                dx = g0.X - start_pt.X
                dy = g0.Y - start_pt.Y
                t = (dx * gdir.Y - dy * gdir.X) / denom

                # Keep grids crossing near the wall's own span, with some
                # allowance either side for set-out grids just past the ends.
                if t < -wall_len * 0.5 or t > wall_len * 1.5:
                    continue

                results.append((t, DB.Reference(g)))
            except Exception:
                continue

        results.sort(key=lambda x: x[0])
        return results

    def create_linear_dimension(self, wall, view, dim_type, offset_mm, include_grids=False):
        """Create standard linear dimension for straight wall. When
        include_grids is True, any grid crossing the wall's length gets
        inserted into the dimension chain alongside the wall's own end
        faces (and the dimension line is extended to cover them) — default
        stays False so existing wall-to-wall behaviour is unaffected unless
        explicitly opted into."""
        geo = self.get_wall_curve_data(wall)
        if geo['is_arc']: return None # Wrong method

        refs = self.get_wall_references(wall, view)
        if not refs: return None

        offset = self.mm_to_internal(offset_mm)
        wall_len = geo['start_pt'].DistanceTo(geo['end_pt'])

        if not include_grids:
            ref_array = DB.ReferenceArray()
            ref_array.Append(refs[0])
            ref_array.Append(refs[1])
            pt1 = geo['start_pt'] + geo['perp'] * offset
            pt2 = geo['end_pt'] + geo['perp'] * offset
            line = DB.Line.CreateBound(pt1, pt2)
            try:
                return self.doc.Create.NewDimension(view, line, ref_array, dim_type)
            except Exception:
                return None

        grid_hits = self.find_crossing_grids(wall, view)
        ref_array = DB.ReferenceArray()
        min_t, max_t = 0.0, wall_len
        for t, r in grid_hits:
            if t < 0:
                ref_array.Append(r)
                min_t = min(min_t, t)
        ref_array.Append(refs[0])
        for t, r in grid_hits:
            if 0 <= t <= wall_len:
                ref_array.Append(r)
        ref_array.Append(refs[1])
        for t, r in grid_hits:
            if t > wall_len:
                ref_array.Append(r)
                max_t = max(max_t, t)

        pt1 = geo['start_pt'] + geo['tangent'] * min_t + geo['perp'] * offset
        pt2 = geo['start_pt'] + geo['tangent'] * max_t + geo['perp'] * offset
        line = DB.Line.CreateBound(pt1, pt2)

        try:
            return self.doc.Create.NewDimension(view, line, ref_array, dim_type)
        except Exception:
            # Fall back to the plain wall-to-wall dimension rather than
            # producing nothing if the grid-extended chain is rejected.
            try:
                ref_array2 = DB.ReferenceArray()
                ref_array2.Append(refs[0])
                ref_array2.Append(refs[1])
                pt1b = geo['start_pt'] + geo['perp'] * offset
                pt2b = geo['end_pt'] + geo['perp'] * offset
                return self.doc.Create.NewDimension(
                    view, DB.Line.CreateBound(pt1b, pt2b), ref_array2, dim_type)
            except Exception:
                return None

    def create_arc_dimensions(self, wall, view, dim_type, offset_mm, log_fn=None):
        """
        Curved-wall radius/angle/arc-length annotation — PARKED, intentionally
        a no-op.

        Four substantially different approaches were tried across this many
        rounds, live-tested against the user's real project each time:
          1. NewRadialDimension + Arc/ReferenceArray on the wall's own
             CylindricalFace reference — NewRadialDimension confirmed absent
             from this Revit API build (checked via hasattr, never found).
          2. NewDimension(view, Arc, Reference) on the wall's own
             CylindricalFace — raised an overload-mismatch error.
          3. NewDimension(view, Arc, ReferenceArray) on the wall's own
             CylindricalFace — no error, but produced nothing visible.
          4. Auxiliary DetailCurves created by this tool itself (2 radius
             lines + 1 offset arc) referenced by NewAngularDimension and
             NewDimension — the auxiliary lines/text were created
             successfully, but both dimension calls still failed, leaving
             only stray annotation lines with no actual dimension: reported
             back as "erroneous, confusing" by the user.

        Per explicit instruction: if it can't be made to work, create
        nothing rather than leave misleading partial artifacts. This method
        now does exactly that for curved walls — no DetailCurves, no
        TextNote, no dimension attempt — logging why once per wall so the
        result dialog stays informative instead of silently skipping.
        """
        def _log(msg):
            if log_fn:
                try:
                    log_fn(msg)
                except Exception:
                    log_swallowed(_LOG, u'DimensionLogic._log')

        geo = self.get_wall_curve_data(wall)
        if not geo['is_arc']: return []

        _log(u'Wall {}: curved-wall dimensioning (radius/angle/arc-length) is '
             u'parked — not supported on this Revit API build after 4 '
             u'different approaches tried across separate live tests; '
             u'creating nothing rather than a partial/confusing result.'.format(wall.Id))
        return []
