"""
main.py - CAD-Phase Machining Energy Estimator
Orchestrates feature extraction, energy lookup, and report generation.

Run in NX via: File > Execute > NX Open > select this file
Version: 4.2 - NX2027 compatible

Usage:
    Open part/assembly in NX, then execute this script.
"""

import NXOpen
import os
import sys
import json
import traceback
from datetime import datetime
from collections import defaultdict

# ============================================================================
# CONFIGURATION - Edit these before running
# ============================================================================

# Path to material library Excel file
MATERIAL_LIBRARY = r"C:\cad_energy_tool\aluminum.xlsx"

# Output directory for reports
OUTPUT_DIRECTORY = r"C:\temp\cad_energy_output"

# Debug mode: verbose logging to listing window
DEBUG_MODE = False

# Report formats to export
EXPORT_JSON  = True
EXPORT_EXCEL = True

# ============================================================================
# IMPORTS - after config so path errors surface clearly
# ============================================================================

# Add script directory to path so sibling modules are found
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

try:
    from feature_extractor import FeatureExtractor
    from energy_lookup import EnergyLookup, FeatureLibraryLoader
    from report_generator import ReportGenerator
except ImportError as e:
    # Surface import errors clearly in NX listing window
    _sess = NXOpen.Session.GetSession()
    _lw   = _sess.ListingWindow
    _lw.Open()
    _lw.WriteLine(f"IMPORT ERROR: {e}")
    _lw.WriteLine(f"Ensure feature_extractor.py, energy_lookup.py, report_generator.py")
    _lw.WriteLine(f"are in the same directory as main.py: {_script_dir}")
    raise


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Entry point called by NX when script is executed."""
    session = NXOpen.Session.GetSession()
    lw = session.ListingWindow
    lw.Open()

    try:
        _run(session, lw)
    except Exception as e:
        lw.WriteLine("")
        lw.WriteLine("=" * 70)
        lw.WriteLine("FATAL ERROR")
        lw.WriteLine("=" * 70)
        lw.WriteLine(str(e))
        lw.WriteLine("")
        lw.WriteLine(traceback.format_exc())


def _run(session, lw):
    """Core workflow."""

    _header(lw)

    # ------------------------------------------------------------------
    # Load work part
    # ------------------------------------------------------------------
    work_part = session.Parts.Work
    if work_part is None:
        lw.WriteLine("ERROR: No part is open. Open a .prt file and run again.")
        return

    # ------------------------------------------------------------------
    # Load material library
    # ------------------------------------------------------------------
    lw.WriteLine(f"Loading library: {MATERIAL_LIBRARY}")
    if not os.path.isfile(MATERIAL_LIBRARY):
        lw.WriteLine(f"ERROR: Library file not found: {MATERIAL_LIBRARY}")
        lw.WriteLine("Update MATERIAL_LIBRARY path at top of main.py")
        return

    library_loader = FeatureLibraryLoader(MATERIAL_LIBRARY)
    lookup = EnergyLookup(library_loader)
    lw.WriteLine(f"Library loaded. Sheets: {list(library_loader.sheets.keys())}")
    lw.WriteLine("")

    # ------------------------------------------------------------------
    # Process part or assembly
    # ------------------------------------------------------------------
    if _is_assembly(work_part):
        lw.WriteLine(f"Detected assembly: {work_part.Name}")
        result = _process_assembly(work_part, lookup, lw)
    else:
        lw.WriteLine(f"Detected single part: {work_part.Name}")
        result = _process_single_part(work_part, lookup, lw)

    # ------------------------------------------------------------------
    # Generate report
    # ------------------------------------------------------------------
    os.makedirs(OUTPUT_DIRECTORY, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    part_stem = _safe_name(work_part.Name)

    reporter = ReportGenerator(lw, debug=DEBUG_MODE)
    reporter.print_report(result)

    if EXPORT_JSON:
        json_path = os.path.join(OUTPUT_DIRECTORY, f"{part_stem}_{timestamp}.json")
        _export_json(result, json_path)
        lw.WriteLine(f"JSON report: {json_path}")

    if EXPORT_EXCEL:
        xlsx_path = os.path.join(OUTPUT_DIRECTORY, f"{part_stem}_{timestamp}.xlsx")
        reporter.export_excel(result, xlsx_path)
        lw.WriteLine(f"Excel report: {xlsx_path}")

    lw.WriteLine("")
    lw.WriteLine("Done.")


# ============================================================================
# ASSEMBLY / PART PROCESSING
# ============================================================================

def _is_assembly(part):
    """Return True if part has components (is an assembly)."""
    try:
        comps = part.ComponentAssembly.RootComponent.GetChildren()
        return len(comps) > 0
    except Exception:
        return False


def _process_assembly(assembly_part, lookup, lw):
    """Recursively process all components; skip purchased parts."""
    results = []
    purchased_count = 0
    total_energy = 0.0

    try:
        root = assembly_part.ComponentAssembly.RootComponent
        components = root.GetChildren()
    except Exception as e:
        lw.WriteLine(f"  WARNING: Could not get assembly components: {e}")
        components = []

    seen_parts = set()
    for comp in components:
        try:
            comp_part = comp.Prototype.OwningPart
        except Exception:
            continue

        if comp_part is None:
            continue

        part_name = comp_part.Name
        is_dup = part_name in seen_parts
        seen_parts.add(part_name)

        if _is_assembly(comp_part):
            lw.WriteLine(f"  Sub-assembly: {part_name}")
            sub_result = _process_assembly(comp_part, lookup, lw)
            sub_result["is_duplicate"] = is_dup
            results.append(sub_result)
            total_energy += sub_result["total_energy_wh"]
        else:
            part_result = _process_single_part(comp_part, lookup, lw)
            part_result["is_duplicate"] = is_dup
            results.append(part_result)
            if part_result.get("is_purchased"):
                purchased_count += 1
            else:
                total_energy += part_result["total_energy_wh"]

    return {
        "type": "assembly",
        "name": assembly_part.Name,
        "components": results,
        "total_energy_wh": total_energy,
        "purchased_parts_skipped": purchased_count,
        "timestamp": datetime.now().isoformat(),
    }


def _process_single_part(part, lookup, lw):
    """Extract features from one part and estimate energy."""
    part_name = part.Name or "UnnamedPart"
    lw.WriteLine(f"  Processing: {part_name}")

    # ------------------------------------------------------------------
    # Feature extraction
    # ------------------------------------------------------------------
    extractor = FeatureExtractor(part, lw, debug=DEBUG_MODE)
    features = extractor.extract_all()

    if not features:
        lw.WriteLine(f"    No manufacturing features found — treating as purchased part.")
        return {
            "type": "part",
            "name": part_name,
            "is_purchased": True,
            "features": [],
            "total_energy_wh": 0.0,
        }

    lw.WriteLine(f"    Extracted {len(features)} feature(s).")

    # ------------------------------------------------------------------
    # Build name→feature map for pattern/mirror parent resolution
    # ------------------------------------------------------------------
    feature_by_name = {}
    for f in features:
        for key in (f.get("name"), f.get("journal_id")):
            if key:
                feature_by_name[key] = f
        # Also index by bare base name (strip "(N)" suffix)
        journal = f.get("journal_id", "")
        base = journal.rsplit("(", 1)[0].strip() if "(" in journal else journal
        if base:
            feature_by_name.setdefault(base, f)

    # ------------------------------------------------------------------
    # Energy lookup
    # ------------------------------------------------------------------
    total_energy = 0.0
    for f in features:
        if f.get("is_multiplier"):
            # Pattern/mirror: multiply parent energy
            parent_name = f.get("parent_name") or f.get("parent_journal_id")
            parent = _find_parent(parent_name, features, feature_by_name)
            if parent and parent.get("energy_wh", 0) > 0:
                multiplier = f.get("instance_count", 1)
                extra = parent["energy_wh"] * (multiplier - 1)
                f["energy_wh"] = extra
                f["energy_result"] = {
                    "estimation_basis": f"Pattern/mirror × {multiplier-1} additional instances of {parent_name}",
                    "energy_wh": extra,
                }
                total_energy += extra
                lw.WriteLine(f"    {f.get('journal_id','pattern')}: ×{multiplier} of {parent_name} = {extra:.4f} Wh")
            else:
                f["energy_wh"] = 0.0
                f["energy_result"] = {"estimation_basis": "Parent feature not found or no energy", "energy_wh": 0.0}
                _warn(lw, f"    WARNING: Pattern/mirror parent '{parent_name}' not found")
            continue

        energy_result = lookup.estimate(f)
        f["energy_result"] = energy_result
        f["energy_wh"] = energy_result.get("energy_wh", 0.0)
        total_energy += f["energy_wh"]

        if DEBUG_MODE:
            lw.WriteLine(f"    {f.get('journal_id','?')}: {f['energy_wh']:.4f} Wh "
                         f"[{energy_result.get('estimation_basis','?')}]")

    lw.WriteLine(f"    Total energy: {total_energy:.4f} Wh")

    return {
        "type": "part",
        "name": part_name,
        "is_purchased": False,
        "features": features,
        "total_energy_wh": total_energy,
        "timestamp": datetime.now().isoformat(),
    }


def _find_parent(parent_name, features, feature_by_name):
    """Locate parent feature by name or journal_id."""
    if parent_name is None:
        return None

    # Direct lookup
    if parent_name in feature_by_name:
        return feature_by_name[parent_name]

    # Fuzzy: base name match
    base = parent_name.rsplit("(", 1)[0].strip() if "(" in parent_name else parent_name
    if base in feature_by_name:
        return feature_by_name[base]

    # Scan all features
    for f in features:
        if f.get("name") == parent_name or f.get("journal_id") == parent_name:
            return f

    return None


# ============================================================================
# HELPERS
# ============================================================================

def _header(lw):
    lw.WriteLine("=" * 70)
    lw.WriteLine("  CAD-PHASE MACHINING ENERGY ESTIMATOR  v4.2")
    lw.WriteLine(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lw.WriteLine("  NX 2027 compatible | Empirical lookup | Trapezoidal interp")
    lw.WriteLine("=" * 70)
    lw.WriteLine("")


def _warn(lw, msg):
    lw.WriteLine(msg)


def _safe_name(name):
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in (name or "part"))


def _export_json(result, path):
    """Write result dict to JSON, skipping non-serialisable objects."""
    def _default(o):
        return str(o)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=_default)


# ============================================================================
# NX ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    main()
