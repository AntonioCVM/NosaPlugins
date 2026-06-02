# -*- coding: utf-8 -*-
from pyrevit import DB, revit
import math

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
        try:
            return element.Name
        except Exception:
            return str(element.Id)

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
            pass
            
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
        
        # Vector for projecting candidates along the wall
        if geo['is_arc']:
            axis = (geo['end_pt'] - geo['start_pt']).Normalize()
        else:
            axis = geo['tangent']
            
        ref_pt = geo['start_pt']

        for solid in solids:
            for face in solid.Faces:
                # We want vertical faces
                normal = face.ComputeNormal(DB.UV(0.5,0.5))
                if abs(normal.Z) > 0.1: continue
                
                # We want faces acting as "Ends". 
                # For straight wall: Normal is parallel to Tangent.
                # For arc wall: Normal is parallel to Chord (approx).
                
                # Check alignment with axis
                dot = normal.DotProduct(axis)
                if abs(dot) < 0.7: continue # Ignore side faces
                
                # It's an end face.
                # Project centroid to sort
                if face.Reference:
                    centroid = face.Evaluate(DB.UV(0.5,0.5))
                    proj = (centroid - ref_pt).DotProduct(axis)
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

    def create_linear_dimension(self, wall, view, dim_type, offset_mm):
        """Create standard linear dimension for straight wall."""
        geo = self.get_wall_curve_data(wall)
        if geo['is_arc']: return None # Wrong method
        
        refs = self.get_wall_references(wall, view)
        if not refs: return None
        
        ref_array = DB.ReferenceArray()
        ref_array.Append(refs[0])
        ref_array.Append(refs[1])
        
        offset = self.mm_to_internal(offset_mm)
        pt1 = geo['start_pt'] + geo['perp'] * offset
        pt2 = geo['end_pt'] + geo['perp'] * offset
        line = DB.Line.CreateBound(pt1, pt2)
        
        try:
            return self.doc.Create.NewDimension(view, line, ref_array, dim_type)
        except Exception:
            return None

    def create_arc_dimensions(self, wall, view, dim_type, offset_mm):
        """Create Radius and Arc Length dimensions for curved wall."""
        geo = self.get_wall_curve_data(wall)
        if not geo['is_arc']: return []
        
        created = []
        offset = self.mm_to_internal(offset_mm)
        
        curve_ref = None
        
        # 0. Try to get Curve Reference directly from LocationCurve (sometimes works)
        # Usually LocationCurve doesn't have a reference unless we get it from an Instance Geometry
        
        # 1. Try finding a Curved Face (Cylindrical)
        # This is the most reliable way for Radial Dimensions on Walls
        if not curve_ref:
            opts = DB.Options()
            opts.ComputeReferences = True
            opts.View = view
            opts.IncludeNonVisibleObjects = True
            
            geom = wall.get_Geometry(opts)
            if geom:
                for obj in geom:
                    if isinstance(obj, DB.Solid):
                        for f in obj.Faces:
                            # Check if cylindrical
                            if isinstance(f, DB.CylindricalFace):
                                if f.Reference:
                                    curve_ref = f.Reference
                                    break
                        if curve_ref: break
        
        # 2. RADIUS DIMENSION
        if curve_ref:
            try:
                # Origin for the dimension text/leader
                mid_vec = (geo['mid_pt'] - geo['center']).Normalize()
                origin = geo['mid_pt'] + mid_vec * offset
                
                dim_rad = self.doc.Create.NewRadialDimension(view, curve_ref, origin)
                if dim_type: dim_rad.DimensionType = dim_type
                created.append(dim_rad)
            except Exception as e:
                pass
                # print("Radius dim failed: " + str(e))

        # 3. ARC LENGTH DIMENSION
        # Needs Arc Ref (to the curve being measured) + 2 Perpendicular Refs (Limits)
        # Using the same curve_ref (Wall Face) works for the "Arc" input of NewDimension usually?
        # Actually NewDimension for Arc Length expects the *Dimension Line* arc geometry as input.
        
        try:
            refs = self.get_wall_references(wall, view) # Get vertical end faces
            if refs and len(refs) >= 2:
                ref_array = DB.ReferenceArray()
                ref_array.Append(refs[0]) # Start Face
                ref_array.Append(refs[1]) # End Face
                
                # If we have a curve reference (face), add it too?
                # Some API docs suggest adding the arc reference to the array for Arc Length?
                # or is it implied by the dimension type?
                
                # Let's try to find an Arc Length dimension type if the current one is Linear
                # But we can't switch types easily. Assuming user selected a proper type or Linear works.
                
                # Geometry: Arc concentric to wall
                new_radius = geo['radius'] + offset
                v_start = (geo['start_pt'] - geo['center']).Normalize()
                v_end = (geo['end_pt'] - geo['center']).Normalize()
                
                # Angles calculation handling periodicity
                # Simplification: Create bound arc through 3 points? or by center/radius
                # DB.Arc.Create(plane, radius, startParam, endParam)
                
                # Let's use simple 3-point construction if possible or Plane-based
                # We assume wall is on XY plane (ViewPlan)
                
                angle_start = math.atan2(v_start.Y, v_start.X)
                angle_end = math.atan2(v_end.Y, v_end.X)
                
                # DB.Arc.Create(center, radius, startAngle, endAngle, xAxis, yAxis)
                dim_arc_geom = DB.Arc.Create(geo['center'], new_radius, angle_start, angle_end, DB.XYZ.BasisX, DB.XYZ.BasisY)

                dim_arc_len = self.doc.Create.NewDimension(view, dim_arc_geom, ref_array, dim_type)
                
                # Check if it was created as Linear or ArcLength?
                # If created, it's good.
                created.append(dim_arc_len)

        except Exception as e:
            # print("Arc Length dim failed: " + str(e))
            pass
            
        return created
