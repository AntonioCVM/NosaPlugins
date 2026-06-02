# -*- coding: utf-8 -*-
import sys, os
from pyrevit import DB, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.revit_helpers import get_id_value as _get_id_value

class TagLogic:
    def __init__(self, doc):
        self.doc = doc

    def get_id_value(self, element_id):
        return _get_id_value(element_id)

    def safe_get_builtincategory(self, name):
        return getattr(DB.BuiltInCategory, name, None)

    def get_categories(self):
        """Return list of (DisplayName, BuiltInCategory, BuiltInNameString, Discipline)."""
        # (Name, BuiltInCategoryName, Discipline)
        cats_data = [
            # Architecture
            ("Areas", "OST_Areas", "Architecture"),
            ("Casework", "OST_Casework", "Architecture"),
            ("Ceilings", "OST_Ceilings", "Architecture"),
            ("Doors", "OST_Doors", "Architecture"),
            ("Furniture", "OST_Furniture", "Architecture"),
            ("Generic Models", "OST_GenericModel", "Architecture"),
            ("Parking", "OST_Parking", "Architecture"),
            ("Planting", "OST_Planting", "Architecture"),
            ("Railings", "OST_StairsRailing", "Architecture"),
            ("Rooms", "OST_Rooms", "Architecture"),
            ("Roofs", "OST_Roofs", "Architecture"),
            ("Specialty Equipment", "OST_SpecialtyEquipment", "Architecture"),
            ("Stairs", "OST_Stairs", "Architecture"),
            ("Walls", "OST_Walls", "Architecture"),
            ("Windows", "OST_Windows", "Architecture"),
            
            # Structure
            ("Floors", "OST_Floors", "Structure"),
            ("Rebar", "OST_Rebar", "Structure"),
            ("Structural Columns", "OST_StructuralColumns", "Structure"),
            ("Structural Connections", "OST_StructConnections", "Structure"),
            ("Structural Foundations", "OST_StructuralFoundation", "Structure"),
            ("Structural Framing", "OST_StructuralFraming", "Structure"),
            ("Structural Stiffeners", "OST_StructuralStiffener", "Structure"),
            
            # MEP
            ("Cable Trays", "OST_CableTray", "MEP"),
            ("Conduits", "OST_Conduit", "MEP"),
            ("Ducts", "OST_DuctCurves", "MEP"),
            ("Duct Fittings", "OST_DuctFitting", "MEP"),
            ("Duct Accessories", "OST_DuctAccessory", "MEP"),
            ("Electrical Equipment", "OST_ElectricalEquipment", "MEP"),
            ("Electrical Fixtures", "OST_ElectricalFixtures", "MEP"),
            ("Lighting Devices", "OST_LightingDevices", "MEP"),
            ("Lighting Fixtures", "OST_LightingFixtures", "MEP"),
            ("Mechanical Equipment", "OST_MechanicalEquipment", "MEP"),
            ("Pipes", "OST_PipeCurves", "MEP"),
            ("Pipe Fittings", "OST_PipeFitting", "MEP"),
            ("Pipe Accessories", "OST_PipeAccessory", "MEP"),
            ("Plumbing Fixtures", "OST_PlumbingFixtures", "MEP"),
            ("Sprinklers", "OST_Sprinklers", "MEP"),
            ("Air Terminals", "OST_DuctTerminal", "MEP"),
        ]
        
        result = []
        for name, bic_name, discipline in cats_data:
            bic = self.safe_get_builtincategory(bic_name)
            if bic:
                result.append({
                    "name": name,
                    "bic": bic,
                    "bic_name": bic_name,
                    "discipline": discipline
                })
        return sorted(result, key=lambda x: (x['discipline'], x['name']))

    def diagnose_tags_in_project(self):
        """Diagnose what tag families are available in the project."""
        # DIAGNOSIS DISABLED FOR PRODUCTION PERFORMANCE
        pass

    def get_tag_family_symbols(self, category_bic_name):
        """Get all FamilySymbols for tags of the given category + Multi-Category Tags."""
        
        CAT_MAP = {
            "OST_Areas": "OST_AreaTags",
            "OST_Casework": "OST_CaseworkTags",
            "OST_Ceilings": "OST_CeilingTags",
            "OST_Doors": "OST_DoorTags",
            "OST_Furniture": "OST_FurnitureTags",
            "OST_GenericModel": "OST_GenericModelTags",
            "OST_Parking": "OST_ParkingTags",
            "OST_Planting": "OST_PlantingTags",
            "OST_StairsRailing": "OST_StairsRailingTags",
            "OST_Rooms": "OST_RoomTags",
            "OST_Roofs": "OST_RoofTags",
            "OST_SpecialtyEquipment": "OST_SpecialtyEquipmentTags",
            "OST_Stairs": "OST_StairsTags",
            "OST_Walls": "OST_WallTags",
            "OST_Windows": "OST_WindowTags",
            "OST_Floors": "OST_FloorTags",
            "OST_Rebar": "OST_RebarTags",
            "OST_StructuralColumns": "OST_StructuralColumnTags",
            "OST_StructConnections": "OST_StructConnectionTags",
            "OST_StructuralFoundation": "OST_StructuralFoundationTags",
            "OST_StructuralFraming": "OST_StructuralFramingTags",
            "OST_StructuralStiffener": "OST_StructuralStiffenerTags",
            "OST_CableTray": "OST_CableTrayTags",
            "OST_Conduit": "OST_ConduitTags",
            "OST_DuctCurves": "OST_DuctTags",
            "OST_DuctFitting": "OST_DuctFittingTags",
            "OST_DuctAccessory": "OST_DuctAccessoryTags",
            "OST_ElectricalEquipment": "OST_ElectricalEquipmentTags",
            "OST_ElectricalFixtures": "OST_ElectricalFixtureTags",
            "OST_LightingDevices": "OST_LightingDeviceTags",
            "OST_LightingFixtures": "OST_LightingFixtureTags",
            "OST_MechanicalEquipment": "OST_MechanicalEquipmentTags",
            "OST_PipeCurves": "OST_PipeTags",
            "OST_PipeFitting": "OST_PipeFittingTags",
            "OST_PipeAccessory": "OST_PipeAccessoryTags",
            "OST_PlumbingFixtures": "OST_PlumbingFixturesTags",
            "OST_Sprinklers": "OST_SprinklerTags",
            "OST_DuctTerminal": "OST_DuctTerminalTags",
            "OST_MEPSpaces": "OST_SpaceTags"
        }
        
        results = []
        
        # Helper for Robust Name Getting - VERSION MEJORADA
        def get_robust_name(s):
            """Safely extract name from symbol with multiple fallbacks."""
            fam_name = "Unknown Family"
            sym_name = "Unknown Type"
            
            # Try getting Symbol Name (multiple approaches)
            try:
                sym_name = s.Name
            except Exception:
                try:
                    p = s.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
                    if p and p.AsString():
                        sym_name = p.AsString()
                except Exception:
                    try:
                        sym_name = s.LookupParameter("Type Name").AsString()
                    except Exception:
                        try:
                            # Last resort: use ID
                            sym_name = "Type_{}".format(s.Id)
                        except Exception:
                            pass
            
            # Try getting Family Name (multiple approaches)
            try:
                if hasattr(s, "Family") and s.Family:
                    fam_name = s.Family.Name
            except Exception:
                try:
                    p = s.get_Parameter(DB.BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM)
                    if p and p.AsString():
                        fam_name = p.AsString()
                except Exception:
                    try:
                        fam_name = s.LookupParameter("Family").AsString()
                    except Exception:
                        try:
                            p = s.get_Parameter(DB.BuiltInParameter.ALL_MODEL_FAMILY_NAME)
                            if p and p.AsString():
                                fam_name = p.AsString()
                        except Exception:
                            pass
            
            return "{} : {}".format(fam_name, sym_name)

        # MÉTODO 1: Búsqueda por mapeo directo
        tag_bic_name = CAT_MAP.get(str(category_bic_name))
        if tag_bic_name:
            tag_bic = self.safe_get_builtincategory(tag_bic_name)
            if tag_bic:
                try:
                    symbols = list(DB.FilteredElementCollector(self.doc)\
                        .OfCategory(tag_bic)\
                        .OfClass(DB.FamilySymbol)\
                        .WhereElementIsElementType()\
                        .ToElements())
                    
                    for s in symbols:
                        try:
                            tag_name = get_robust_name(s)
                            tag_id = self.get_id_value(s.Id)
                            
                            results.append({
                                "name": tag_name,
                                "symbol": s,
                                "id": tag_id
                            })
                            
                        except Exception:
                            # Continue to next symbol instead of failing completely
                            continue
                            
                except Exception:
                    pass
        
        # MÉTODO 3: Multi-Category Tags
        multi_bic = self.safe_get_builtincategory("OST_MultiCategoryTags")
        if multi_bic:
            try:
                multi_symbols = list(DB.FilteredElementCollector(self.doc)\
                    .OfCategory(multi_bic)\
                    .OfClass(DB.FamilySymbol)\
                    .ToElements())
                
                for s in multi_symbols:
                    try:
                        tag_name = "[Multi] " + get_robust_name(s)
                        tag_id = self.get_id_value(s.Id)
                        
                        tag_info = {
                            "name": tag_name,
                            "symbol": s,
                            "id": tag_id
                        }
                        
                        # De-duplicate
                        if not any(r['id'] == tag_info['id'] for r in results):
                            results.append(tag_info)
                            
                    except Exception:
                        continue
                        
            except Exception:
                pass
        
        # Deduplicate results by ID
        unique_results = []
        seen_ids = set()
        for r in results:
            if r['id'] not in seen_ids:
                unique_results.append(r)
                seen_ids.add(r['id'])

        return sorted(unique_results, key=lambda x: x['name'])

    def get_taggable_views(self):
        """Get views where tags can be placed."""
        allowed = [
            DB.ViewType.FloorPlan,
            DB.ViewType.EngineeringPlan,
            DB.ViewType.CeilingPlan,
            DB.ViewType.Section,
            DB.ViewType.Elevation
        ]
        
        views = []
        col = DB.FilteredElementCollector(self.doc).OfClass(DB.View)
        for v in col:
            if not v.IsTemplate and v.ViewType in allowed:
                views.append({
                    "name": "{} [{}]".format(v.Name, v.ViewType),
                    "element": v,
                    "id": self.get_id_value(v.Id)
                })
        return sorted(views, key=lambda x: x['name'])

    def get_elements_in_view(self, view, bic):
        """Get elements of category in view."""
        return list(DB.FilteredElementCollector(self.doc, view.Id)\
            .OfCategory(bic)\
            .WhereElementIsNotElementType()\
            .ToElements())

    def get_existing_tagged_ids(self, view):
        """Get IDs of elements already tagged in view."""
        tags = DB.FilteredElementCollector(self.doc, view.Id)\
            .OfClass(DB.IndependentTag)\
            .ToElements()
        
        tagged = set()
        for t in tags:
            try:
                if hasattr(t, "GetTaggedLocalElementIds"):
                    eids = t.GetTaggedLocalElementIds()
                    for eid in eids:
                         tagged.add(self.get_id_value(eid))
                else:
                    eid = t.GetTaggedLocalElementId()
                    if eid != DB.ElementId.InvalidElementId:
                        tagged.add(self.get_id_value(eid))
            except Exception:
                pass
        return tagged

    def get_element_center(self, element):
        """Estimate center point for tag placement."""
        try:
            bbox = element.get_BoundingBox(None)
            if bbox:
                return DB.XYZ(
                    (bbox.Min.X + bbox.Max.X) / 2,
                    (bbox.Min.Y + bbox.Max.Y) / 2,
                    (bbox.Min.Z + bbox.Max.Z) / 2
                )
        except Exception:
            pass
        
        # Fallback: LocationPoint or Curve
        if hasattr(element, "Location"):
            loc = element.Location
            if isinstance(loc, DB.LocationPoint):
                return loc.Point
            elif isinstance(loc, DB.LocationCurve):
                p1 = loc.Curve.GetEndPoint(0)
                p2 = loc.Curve.GetEndPoint(1)
                return DB.XYZ((p1.X+p2.X)/2, (p1.Y+p2.Y)/2, (p1.Z+p2.Z)/2)
                
        return None
