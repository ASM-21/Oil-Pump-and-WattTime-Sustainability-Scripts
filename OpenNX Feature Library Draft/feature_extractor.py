"""
feature_extractor.py - NX Manufacturing Feature Extraction

Extracts manufacturing-relevant features from NX part files using NXOpen API.
All dimensions converted to mm. Returns empty list for purchased parts.

Target NX Version: 2027 (Build 3302)
Version: 4.2 - NX2027 API fixes:
    - Through-hole depth: expressions → body geometry fallback
    - Pattern/mirror parent: feature tree scanning + instance counting
    - Extrude boolean: string comparison (NXOpen.GeometricUtilities missing in 2027)
    - JournalIdentifier as authoritative hole-type source
    - ApexRangeChamfer support
    - Cosmetic thread sub-feature filtering
"""

import NXOpen
import re
import math
from collections import defaultdict


# ============================================================================
# FEATURE TYPE ROUTING TABLE
# ============================================================================

# NX JournalIdentifier / type-name prefixes → internal handler
_HOLE_JOURNAL_PREFIXES = {
    "SIMPLE HOLE":              "simple",
    "COUNTERBORED HOLE":        "counterbore",
    "COUNTERSUNK HOLE":         "countersink",
    "THREADED HOLE":            "threaded",
    "TAPERED THREAD":           "threaded",
    "COUNTERBORE THREADED":     "counterbore_threaded",
    "COUNTERSINK THREADED":     "countersink_threaded",
}

_SKIP_FEATURE_TYPES = {
    "DatumPlane", "DatumAxis", "DatumCsys", "Sketch", "ReferenceSet",
    "CoordinateSystem", "SketchFeature", "ReferenceFeature",
    "CosmeticThread", "SymbolicThread",          # handled inside hole
    "Curve", "Point", "Offset", "AssociativeOffset",
}

_POCKET_TYPES   = {"Pocket", "RectangularPocket", "GeneralPocket", "CircularPocket"}
_SLOT_TYPES     = {"Slot", "RectangularSlot", "BallEndSlot", "TSlot", "DoveTailSlot"}
_GROOVE_TYPES   = {"Groove", "RectangularGroove", "BallEndGroove"}
_CHAMFER_TYPES  = {"Chamfer", "ApexRangeChamfer"}
_FILLET_TYPES   = {"EdgeBlend", "Fillet"}
_PATTERN_RECT   = {"PatternFeature", "RectangularPattern", "LinearPattern"}
_PATTERN_CIRC   = {"CircularPattern"}
_MIRROR_TYPES   = {"MirrorFeature", "MirrorBody"}
_EXTRUDE_TYPES  = {"Extrude"}
_THREAD_EXT     = {"Thread", "SymbolicThread"}
_FACE_TYPES     = {"Face", "FaceFeature", "Facing"}


class FeatureExtractor:
    """Extract manufacturing features from an NX part."""

    def __init__(self, part, listing_window=None, debug=False):
        self.part   = part
        self.lw     = listing_window
        self.debug  = debug
        self._units = self._detect_units()

    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------

    def extract_all(self):
        """Return list of feature dicts. Empty list = purchased/no features."""
        results = []
        seen_ids = set()

        try:
            features = self.part.Features
        except Exception as e:
            self._log(f"Cannot access features: {e}")
            return results

        for feature in features:
            try:
                feat_dict = self._dispatch(feature)
            except Exception as e:
                self._log(f"Error dispatching feature: {e}")
                feat_dict = None

            if feat_dict is None:
                continue

            # Deduplicate by NX internal tag
            try:
                feat_id = feature.Tag
            except Exception:
                feat_id = id(feature)

            if feat_id in seen_ids:
                continue
            seen_ids.add(feat_id)

            results.append(feat_dict)

        return results

    # -------------------------------------------------------------------------
    # DISPATCH
    # -------------------------------------------------------------------------

    def _dispatch(self, feature):
        """Route feature to correct extractor based on type/JournalIdentifier."""
        try:
            journal_id = feature.JournalIdentifier          # e.g. "SIMPLE HOLE(5)"
        except Exception:
            journal_id = ""

        try:
            feat_type = type(feature).__name__              # class name in NXOpen
        except Exception:
            feat_type = ""

        # Build name
        try:
            feat_name = feature.Name or journal_id
        except Exception:
            feat_name = journal_id

        # Skip non-manufacturing features
        if feat_type in _SKIP_FEATURE_TYPES:
            return None
        for skip in _SKIP_FEATURE_TYPES:
            if skip.lower() in feat_type.lower() or skip.lower() in journal_id.lower():
                return None

        # Base info attached to every result
        base = {
            "name":             feat_name,
            "journal_id":       journal_id,
            "feature_type":     feat_type,
            "extraction_status": "ok",
        }

        # ---- Hole (all subtypes via JournalIdentifier) ----
        journal_upper = journal_id.upper()
        for prefix, hole_subtype in _HOLE_JOURNAL_PREFIXES.items():
            if journal_upper.startswith(prefix):
                return self._extract_hole(feature, base, hole_subtype)

        if feat_type == "HolePackage":
            return self._extract_hole(feature, base, None)

        # ---- Other feature types ----
        if feat_type in _POCKET_TYPES or "POCKET" in journal_upper:
            return self._extract_pocket(feature, base)

        if feat_type in _SLOT_TYPES or "SLOT" in journal_upper:
            return self._extract_slot(feature, base)

        if feat_type in _GROOVE_TYPES or "GROOVE" in journal_upper:
            return self._extract_groove(feature, base)

        if feat_type in _CHAMFER_TYPES or "CHAMFER" in journal_upper:
            return self._extract_chamfer(feature, base)

        if feat_type in _FILLET_TYPES or "BLEND" in journal_upper or "FILLET" in journal_upper:
            return self._extract_fillet(feature, base)

        if feat_type in _PATTERN_RECT or "RECTANGULAR PATTERN" in journal_upper:
            return self._extract_pattern_rectangular(feature, base)

        if feat_type in _PATTERN_CIRC or "CIRCULAR PATTERN" in journal_upper:
            return self._extract_pattern_circular(feature, base)

        if feat_type in _MIRROR_TYPES or "MIRROR" in journal_upper:
            return self._extract_mirror(feature, base)

        if feat_type in _EXTRUDE_TYPES or "EXTRUDE" in journal_upper:
            return self._extract_extrude(feature, base)

        if feat_type in _THREAD_EXT or "THREAD" in journal_upper:
            return self._extract_thread_external(feature, base)

        if feat_type in _FACE_TYPES or "FACING" in journal_upper:
            return self._extract_face(feature, base)

        # Unknown — skip silently
        self._log(f"Unhandled feature type: {feat_type} | {journal_id}")
        return None

    # =========================================================================
    # HOLE EXTRACTION
    # =========================================================================

    def _extract_hole(self, feature, base, hint_subtype):
        """Extract hole parameters.  hint_subtype from JournalIdentifier."""
        base["category"] = "hole_unknown"

        # ---- Determine hole subtype (JournalIdentifier is authoritative) ----
        subtype = hint_subtype or self._detect_hole_subtype_from_journal(feature)
        base["hole_subtype"] = subtype

        # ---- Extract numeric parameters ----
        params = {}
        # Method 1: HolePackageBuilder
        params = self._hole_params_via_builder(feature, params)
        # Method 2: Expression pattern learning
        params = self._hole_params_via_expressions(feature, params, subtype)
        # Method 3: Face geometry measurement
        if params.get("diameter") is None:
            params["diameter"] = self._measure_hole_diameter_from_faces(feature)

        # ---- Resolve through-hole depth ----
        is_through = params.get("is_through", False)
        depth = self._convert_mm(params.get("depth"))
        if is_through and (depth is None or depth <= 0):
            depth = self._estimate_part_thickness()
            params["depth_source"] = "part_thickness_estimate"

        diameter = self._convert_mm(params.get("diameter"))
        if diameter is None:
            base["extraction_status"] = "warning"
            base["extraction_error"]  = "diameter not extracted"

        # ---- Decompose compound features ----
        if subtype == "simple":
            base.update({
                "category":    "hole_simple",
                "diameter_mm": diameter,
                "depth_mm":    depth,
                "is_through":  is_through,
            })
            return base

        if subtype == "counterbore":
            cb_dia   = self._convert_mm(params.get("counterbore_diameter"))
            cb_depth = self._convert_mm(params.get("counterbore_depth"))
            base.update({
                "category":              "hole_compound",
                "decomposed_operations": [
                    {"category": "hole_simple",          "diameter_mm": diameter, "depth_mm": depth},
                    {"category": "counterbore_operation","cb_diameter_mm": cb_dia, "cb_depth_mm": cb_depth},
                ],
            })
            return base

        if subtype == "countersink":
            cs_dia  = self._convert_mm(params.get("countersink_diameter"))
            cs_angle = params.get("countersink_angle", 90.0)
            base.update({
                "category":              "hole_compound",
                "decomposed_operations": [
                    {"category": "hole_simple",             "diameter_mm": diameter, "depth_mm": depth},
                    {"category": "countersink_operation",   "cs_diameter_mm": cs_dia, "cs_angle_deg": cs_angle},
                ],
            })
            return base

        if subtype in ("threaded", "tapered_thread"):
            thread_size  = params.get("thread_size")
            thread_depth = self._convert_mm(params.get("thread_depth")) or depth
            base.update({
                "category":              "hole_compound",
                "decomposed_operations": [
                    {"category": "hole_simple",    "diameter_mm": diameter, "depth_mm": depth},
                    {"category": "tap_operation",  "thread_size": thread_size, "thread_depth_mm": thread_depth},
                ],
            })
            return base

        if subtype == "counterbore_threaded":
            cb_dia   = self._convert_mm(params.get("counterbore_diameter"))
            cb_depth = self._convert_mm(params.get("counterbore_depth"))
            thread_size  = params.get("thread_size")
            thread_depth = self._convert_mm(params.get("thread_depth")) or depth
            base.update({
                "category":              "hole_compound",
                "decomposed_operations": [
                    {"category": "hole_simple",          "diameter_mm": diameter, "depth_mm": depth},
                    {"category": "counterbore_operation","cb_diameter_mm": cb_dia, "cb_depth_mm": cb_depth},
                    {"category": "tap_operation",        "thread_size": thread_size, "thread_depth_mm": thread_depth},
                ],
            })
            return base

        # Fallback: treat as simple
        base.update({
            "category":    "hole_simple",
            "diameter_mm": diameter,
            "depth_mm":    depth,
            "is_through":  is_through,
        })
        return base

    def _detect_hole_subtype_from_journal(self, feature):
        """Parse JournalIdentifier for hole subtype."""
        try:
            ji = feature.JournalIdentifier.upper()
        except Exception:
            return "simple"
        for prefix, subtype in _HOLE_JOURNAL_PREFIXES.items():
            if ji.startswith(prefix):
                return subtype
        return "simple"

    def _hole_params_via_builder(self, feature, params):
        """Try HolePackageBuilder with NX2027-compatible property names."""
        builder = None
        try:
            builder = self.part.Features.CreateHolePackageBuilder(feature)

            # Diameter — try several property names across NX versions
            for prop in ("DrillSizeHoleDiameter", "GeneralHoleDiameter",
                         "HoleDiameter", "Diameter"):
                val = self._builder_value(builder, prop)
                if val is not None:
                    params["diameter"] = val
                    break

            # Depth
            for prop in ("DrillSizeHoleDepth", "GeneralHoleDepth",
                         "HoleDepth", "Depth"):
                val = self._builder_value(builder, prop)
                if val is not None:
                    params["depth"] = val
                    break

            # Through-hole flag
            for prop in ("GeneralHoleDepthLimitOption", "HoleDepthLimitOption",
                         "DepthLimitOption"):
                try:
                    limit = getattr(builder, prop, None)
                    if limit is not None:
                        params["is_through"] = "throughbody" in str(limit).lower()
                        break
                except Exception:
                    pass

            # Counterbore
            for prop in ("CounterboreDiameter", "CBDiameter"):
                val = self._builder_value(builder, prop)
                if val is not None and val > 0:
                    params["counterbore_diameter"] = val
                    break
            for prop in ("CounterboreDepth", "CBDepth"):
                val = self._builder_value(builder, prop)
                if val is not None and val > 0:
                    params["counterbore_depth"] = val
                    break

            # Countersink
            for prop in ("CountersinkDiameter", "CSDiameter"):
                val = self._builder_value(builder, prop)
                if val is not None and val > 0:
                    params["countersink_diameter"] = val
                    break
            for prop in ("CountersinkAngle", "CSAngle"):
                try:
                    ang = getattr(builder, prop, None)
                    if ang is not None:
                        params["countersink_angle"] = float(str(ang))
                except Exception:
                    pass

            # Thread
            for prop in ("ThreadSize", "TapDrillDiameter"):
                try:
                    val = getattr(builder, prop, None)
                    if val is not None:
                        params["thread_size"] = str(val)
                        break
                except Exception:
                    pass
            for prop in ("ThreadDepth", "TapDepth"):
                val = self._builder_value(builder, prop)
                if val is not None and val > 0:
                    params["thread_depth"] = val
                    break

        except Exception as e:
            self._log(f"  Builder failed: {e}")
        finally:
            if builder:
                try:
                    builder.Destroy()
                except Exception:
                    pass
        return params

    def _builder_value(self, builder, prop_name):
        """Safely retrieve numeric value from a builder property."""
        try:
            prop = getattr(builder, prop_name, None)
            if prop is None:
                return None
            # Expression object
            if hasattr(prop, "Value"):
                return float(prop.Value)
            # Direct numeric
            return float(prop)
        except Exception:
            return None

    def _hole_params_via_expressions(self, feature, params, subtype):
        """
        Learn dimension positions from NX expression patterns.
        NX creates expressions in consistent per-hole-type order:
          Simple:      [diameter, depth]
          Counterbore: [diameter, depth, cb_diameter, cb_depth]
          Countersink: [diameter, depth, cs_diameter, cs_angle]
          Threaded:    [diameter, depth, thread_pitch, thread_depth]
        """
        try:
            exprs = feature.GetExpressions()
        except Exception:
            return params

        # Filter: only positive numeric expressions, sort by name (p0, p1, ...)
        numeric = []
        for expr in exprs:
            try:
                val = float(expr.Value)
                if val > 0:
                    numeric.append((expr.Name, val))
            except Exception:
                pass

        # Sort by trailing integer in name (p0 < p1 < p12)
        def _sort_key(item):
            m = re.search(r"(\d+)$", item[0])
            return int(m.group(1)) if m else 9999

        numeric.sort(key=_sort_key)

        if len(numeric) < 2:
            return params

        # Position-based mapping
        if params.get("diameter") is None and len(numeric) >= 1:
            params.setdefault("diameter", numeric[0][1])
        if params.get("depth") is None and len(numeric) >= 2:
            params.setdefault("depth", numeric[1][1])

        if subtype == "counterbore" and len(numeric) >= 4:
            params.setdefault("counterbore_diameter", numeric[2][1])
            params.setdefault("counterbore_depth",    numeric[3][1])

        if subtype == "countersink" and len(numeric) >= 3:
            params.setdefault("countersink_diameter", numeric[2][1])
            if len(numeric) >= 4:
                params.setdefault("countersink_angle", numeric[3][1])

        if subtype in ("threaded",) and len(numeric) >= 4:
            params.setdefault("thread_depth", numeric[3][1])

        return params

    def _measure_hole_diameter_from_faces(self, feature):
        """Fallback: measure cylindrical face radius from feature faces."""
        try:
            bodies = feature.GetBodies()
            for body in bodies:
                for face in body.GetFaces():
                    try:
                        face_type = face.SurfaceType
                        if "CYLINDER" in str(face_type).upper():
                            data = face.GetCylinder()
                            # data = (point, axis, radius, height)
                            return data[2] * 2.0   # radius → diameter
                    except Exception:
                        pass
        except Exception:
            pass
        return None

    def _estimate_part_thickness(self):
        """Estimate part thickness as minimum bounding box dimension."""
        try:
            bbox = self.part.Bodies.First.GetBoundingBox()
            dims = [abs(bbox[1][i] - bbox[0][i]) for i in range(3)]
            return min(d for d in dims if d > 0)
        except Exception:
            return None

    # =========================================================================
    # POCKET EXTRACTION
    # =========================================================================

    def _extract_pocket(self, feature, base):
        """Extract pocket (area, depth)."""
        base["category"] = "pocket_rectangular"
        depth = None
        area  = None
        builder = None

        try:
            builder = self.part.Features.CreatePocketBuilder(feature)
            depth = self._builder_value(builder, "Depth")
            # Corner radius — used to infer circular pocket
            cr = self._builder_value(builder, "CornerRadius") or 0
            fr = self._builder_value(builder, "FloorRadius")  or 0
            base["corner_radius_mm"] = self._convert_mm(cr)
            base["floor_radius_mm"]  = self._convert_mm(fr)
        except Exception:
            pass
        finally:
            if builder:
                try: builder.Destroy()
                except: pass

        # Area from faces if builder failed
        if area is None:
            area = self._area_from_bottom_face(feature)

        # Depth from expressions if builder failed
        if depth is None:
            depth = self._depth_from_expressions(feature)

        base["area_mm2"] = self._convert_area_mm2(area)
        base["depth_mm"] = self._convert_mm(depth)

        # Classify pocket type
        if area is not None and depth is not None:
            aspect = math.sqrt(area) / max(depth, 0.001)
            if aspect > 5:
                base["category"] = "pocket_shallow"
        return base

    # =========================================================================
    # SLOT / GROOVE
    # =========================================================================

    def _extract_slot(self, feature, base):
        base["category"] = "slot"
        params = self._generic_from_expressions(feature, 4)
        # Typical expression order: width, depth, length, corner_radius
        base["width_mm"]  = self._convert_mm(params.get(0))
        base["depth_mm"]  = self._convert_mm(params.get(1))
        base["length_mm"] = self._convert_mm(params.get(2))
        if all(v is not None for v in [base["width_mm"], base["depth_mm"], base["length_mm"]]):
            base["volume_mm3"] = base["width_mm"] * base["depth_mm"] * base["length_mm"]
        return base

    def _extract_groove(self, feature, base):
        base["category"] = "groove"
        params = self._generic_from_expressions(feature, 3)
        base["width_mm"]  = self._convert_mm(params.get(0))
        base["depth_mm"]  = self._convert_mm(params.get(1))
        base["length_mm"] = self._convert_mm(params.get(2))
        if all(v is not None for v in [base["width_mm"], base["depth_mm"], base["length_mm"]]):
            base["volume_mm3"] = base["width_mm"] * base["depth_mm"] * base["length_mm"]
        return base

    # =========================================================================
    # CHAMFER
    # =========================================================================

    def _extract_chamfer(self, feature, base):
        base["category"] = "chamfer"
        offset = None
        builder = None

        try:
            builder = self.part.Features.CreateChamferBuilder(feature)
            for prop in ("Offset", "Distance", "OffsetDistance"):
                val = self._builder_value(builder, prop)
                if val is not None and val > 0:
                    offset = val
                    break
        except Exception:
            pass
        finally:
            if builder:
                try: builder.Destroy()
                except: pass

        # Expression fallback
        if offset is None:
            params = self._generic_from_expressions(feature, 1)
            offset = params.get(0)

        base["offset_mm"]     = self._convert_mm(offset)
        base["edge_count"]    = self._count_feature_edges(feature)
        return base

    # =========================================================================
    # FILLET
    # =========================================================================

    def _extract_fillet(self, feature, base):
        base["category"] = "fillet"
        radius = None
        builder = None

        try:
            builder = self.part.Features.CreateEdgeBlendBuilder(feature)
            for prop in ("DefaultRadius", "Radius", "BlendRadius"):
                val = self._builder_value(builder, prop)
                if val is not None and val > 0:
                    radius = val
                    break
        except Exception:
            pass
        finally:
            if builder:
                try: builder.Destroy()
                except: pass

        if radius is None:
            params = self._generic_from_expressions(feature, 1)
            radius = params.get(0)

        base["radius_mm"]        = self._convert_mm(radius)
        base["edge_chain_count"] = self._count_feature_edges(feature)
        return base

    # =========================================================================
    # PATTERN RECTANGULAR
    # =========================================================================

    def _extract_pattern_rectangular(self, feature, base):
        base["category"]    = "pattern_rectangular"
        base["is_multiplier"] = True

        count  = None
        parent = None
        builder = None
        try:
            builder = self.part.Features.CreateLinearPatternBuilder(feature)
            try:
                count_x = int(self._builder_value(builder, "NumberAlongXp") or 1)
            except: count_x = 1
            try:
                count_y = int(self._builder_value(builder, "NumberAlongYp") or 1)
            except: count_y = 1
            count = count_x * count_y
        except Exception:
            pass
        finally:
            if builder:
                try: builder.Destroy()
                except: pass

        # Instance counting fallback
        if count is None:
            count = self._count_pattern_instances(feature) or 1

        parent = self._find_pattern_parent(feature)
        base["instance_count"]  = count
        base["parent_name"]     = parent
        base["parent_journal_id"] = parent
        return base

    # =========================================================================
    # PATTERN CIRCULAR
    # =========================================================================

    def _extract_pattern_circular(self, feature, base):
        base["category"]    = "pattern_circular"
        base["is_multiplier"] = True

        count  = None
        parent = None
        builder = None
        try:
            builder = self.part.Features.CreateCircularPatternBuilder(feature)
            count = int(self._builder_value(builder, "TotalNumber") or 1)
        except Exception:
            pass
        finally:
            if builder:
                try: builder.Destroy()
                except: pass

        if count is None:
            count = self._count_pattern_instances(feature) or 1

        parent = self._find_pattern_parent(feature)
        base["instance_count"]    = count
        base["parent_name"]       = parent
        base["parent_journal_id"] = parent
        return base

    # =========================================================================
    # MIRROR
    # =========================================================================

    def _extract_mirror(self, feature, base):
        base["category"]    = "mirror"
        base["is_multiplier"] = True
        base["instance_count"] = 2      # original + mirror = ×2

        parent = None
        # Multiple API attempts for NX2027
        for method_name in ("GetInputFeatures", "SourceFeatures", "SourceFeature",
                            "FeatureReferences"):
            try:
                result = getattr(feature, method_name)()
                if isinstance(result, (list, tuple)) and len(result) > 0:
                    try:
                        parent = result[0].JournalIdentifier
                    except Exception:
                        parent = result[0].Name
                    break
            except Exception:
                pass

        # Feature tree scan fallback: find last non-multiplier feature before this one
        if parent is None:
            parent = self._find_parent_by_tree_position(feature)

        base["parent_name"]       = parent
        base["parent_journal_id"] = parent
        return base

    # =========================================================================
    # EXTRUDE CUT → POCKET
    # =========================================================================

    def _extract_extrude(self, feature, base):
        """Map extrude-subtract to pocket category."""
        if not self._is_extrude_subtract(feature):
            return None     # additive extrude, skip

        base["category"] = "pocket_rectangular"
        depth = None
        area  = None

        # Depth from expressions
        depth = self._depth_from_expressions(feature)

        # Area from bottom face
        area = self._area_from_bottom_face(feature)

        base["depth_mm"] = self._convert_mm(depth)
        base["area_mm2"] = self._convert_area_mm2(area)
        base["note"]     = "Extrude-subtract mapped to pocket"
        return base

    def _is_extrude_subtract(self, feature):
        """NX2027-safe boolean type check (GeometricUtilities enum absent)."""
        try:
            builder = self.part.Features.CreateExtrudeBuilder(feature)
            try:
                bool_type = builder.BooleanOperation.Type
                result = "subtract" in str(bool_type).lower()
            finally:
                try: builder.Destroy()
                except: pass
            return result
        except Exception:
            pass

        # Fallback: check if feature has target bodies (subtract always does)
        try:
            targets = feature.GetTargetBodies()
            return len(targets) > 0
        except Exception:
            return False

    # =========================================================================
    # EXTERNAL THREAD
    # =========================================================================

    def _extract_thread_external(self, feature, base):
        base["category"] = "thread_external"
        length  = None
        thread_size = None

        try:
            builder = self.part.Features.CreateThreadBuilder(feature)
            length = self._builder_value(builder, "Length") or self._builder_value(builder, "ThreadLength")
            for prop in ("ThreadSize", "Size", "Designation"):
                try:
                    ts = getattr(builder, prop, None)
                    if ts is not None:
                        thread_size = str(ts)
                        break
                except Exception:
                    pass
            try: builder.Destroy()
            except: pass
        except Exception:
            pass

        base["length_mm"]   = self._convert_mm(length)
        base["thread_size"] = thread_size
        return base

    # =========================================================================
    # FACE / FACING
    # =========================================================================

    def _extract_face(self, feature, base):
        base["category"] = "face"
        area  = self._area_from_bottom_face(feature)
        depth = self._depth_from_expressions(feature)
        base["area_mm2"] = self._convert_area_mm2(area)
        base["depth_mm"] = self._convert_mm(depth)
        return base

    # =========================================================================
    # HELPERS — geometry measurement
    # =========================================================================

    def _area_from_bottom_face(self, feature):
        """Area of the largest planar (bottom) face associated with feature."""
        max_area = 0.0
        try:
            bodies = feature.GetBodies()
            for body in bodies:
                for face in body.GetFaces():
                    try:
                        props = face.GetArea()
                        if props > max_area:
                            max_area = props
                    except Exception:
                        pass
        except Exception:
            pass
        return max_area if max_area > 0 else None

    def _count_feature_edges(self, feature):
        """Count edges associated with feature."""
        count = 0
        try:
            for body in feature.GetBodies():
                for edge in body.GetEdges():
                    count += 1
        except Exception:
            pass
        return max(count, 1)

    def _depth_from_expressions(self, feature):
        """Extract largest named-depth expression value."""
        try:
            exprs = feature.GetExpressions()
            for expr in exprs:
                try:
                    name_l = expr.Name.lower()
                    if "depth" in name_l or "dist" in name_l:
                        v = float(expr.Value)
                        if v > 0:
                            return v
                except Exception:
                    pass
            # Fall back to ordered position
            params = self._generic_from_expressions(feature, 2)
            return params.get(1)
        except Exception:
            return None

    def _generic_from_expressions(self, feature, count):
        """Return first `count` positive numeric expressions as {0: val, 1: val, ...}."""
        result = {}
        try:
            exprs = feature.GetExpressions()
            numeric = []
            for expr in exprs:
                try:
                    val = float(expr.Value)
                    if val > 0:
                        numeric.append((expr.Name, val))
                except Exception:
                    pass

            def _key(item):
                m = re.search(r"(\d+)$", item[0])
                return int(m.group(1)) if m else 9999

            numeric.sort(key=_key)
            for i, (_, val) in enumerate(numeric[:count]):
                result[i] = val
        except Exception:
            pass
        return result

    def _count_pattern_instances(self, feature):
        """Count InstanceFeature children to determine pattern count."""
        try:
            count = 0
            for f in self.part.Features:
                if "Instance" in type(f).__name__:
                    count += 1
            return count if count > 0 else None
        except Exception:
            return None

    def _find_pattern_parent(self, pattern_feature):
        """Scan feature tree backwards from pattern to find manufacturing parent."""
        try:
            # Try API first
            for method_name in ("GetInputFeatures", "ParentFeature", "SourceFeatures"):
                try:
                    result = getattr(pattern_feature, method_name)()
                    if isinstance(result, (list, tuple)) and len(result) > 0:
                        return result[0].JournalIdentifier or result[0].Name
                    if result is not None:
                        return result.JournalIdentifier or result.Name
                except Exception:
                    pass

            # Feature tree: find nearest non-skip feature before this one
            return self._find_parent_by_tree_position(pattern_feature)
        except Exception:
            return None

    def _find_parent_by_tree_position(self, pattern_feature):
        """Return JournalIdentifier of last manufacturing feature before pattern_feature."""
        try:
            pattern_tag = pattern_feature.Tag
            last_parent = None
            for f in self.part.Features:
                if f.Tag == pattern_tag:
                    break
                jid = f.JournalIdentifier
                jid_upper = jid.upper()
                # Skip non-manufacturing features
                skip = False
                for s in _SKIP_FEATURE_TYPES:
                    if s.lower() in jid.lower():
                        skip = True
                        break
                if not skip and jid:
                    last_parent = jid
            return last_parent
        except Exception:
            return None

    # =========================================================================
    # UNIT CONVERSION
    # =========================================================================

    def _detect_units(self):
        """Detect part units. Returns 25.4 for inches, 1.0 for mm."""
        try:
            unit_name = self.part.UnitCollection.GetBase("Length").Name.lower()
            if "inch" in unit_name or unit_name == "in":
                return 25.4
        except Exception:
            pass
        return 1.0

    def _convert_mm(self, value):
        if value is None:
            return None
        return float(value) * self._units

    def _convert_area_mm2(self, value):
        if value is None:
            return None
        return float(value) * (self._units ** 2)

    # =========================================================================
    # LOGGING
    # =========================================================================

    def _log(self, msg):
        if self.debug and self.lw:
            try:
                self.lw.WriteLine(f"[FX] {msg}")
            except Exception:
                pass


if __name__ == "__main__":
    print("FeatureExtractor module v4.2")
    print("NX2027 fixes: through-hole depth, pattern/mirror parent, extrude boolean, JournalIdentifier")
