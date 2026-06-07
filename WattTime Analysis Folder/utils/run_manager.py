"""
Run Manager - Create and Manage Analysis Runs

Handles:
- Creating new run directories
- Loading/saving run configurations
- Accessing run paths
- Validating run requirements against library
"""

import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Literal
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import RUNS_DIR, SIGNALS, REGIONS, REGION_GROUPS, expand_region_group

# Valid data types
DataType = Literal["historical", "forecast"]


def create_run(
    name: str,
    signal: str,
    regions: List[str] | str,
    data_types: List[DataType] | DataType = "historical",
    description: str = "",
    date_range: Optional[tuple] = None
) -> Path:
    """
    Create a new run directory with config.
    
    Args:
        name: Short name for the run (e.g., 'moer_temporal')
        signal: Signal type (e.g., 'co2_moer')
        regions: List of regions or region group name
        data_types: 'historical', 'forecast', or list of both
        description: Optional description
        date_range: Optional (start, end) tuple
    
    Returns:
        Path to the run directory
    """
    # Expand region group if needed
    region_list = expand_region_group(regions)
    
    # Normalize data_types to list
    if isinstance(data_types, str):
        data_type_list = [data_types]
    else:
        data_type_list = list(data_types)
    
    # Validate signal
    if signal not in SIGNALS:
        print(f"  Warning: Signal '{signal}' not in SIGNALS config. Proceeding anyway.")
    
    # Validate regions
    unknown_regions = [r for r in region_list if r not in REGIONS]
    if unknown_regions:
        print(f"  Warning: Regions {unknown_regions} not in REGIONS config. Proceeding anyway.")
    
    # Create timestamped directory name
    timestamp = datetime.now().strftime("%Y-%m-%d")
    run_dir_name = f"{timestamp}_{name}"
    run_dir = RUNS_DIR / run_dir_name
    
    # Handle duplicate names
    counter = 1
    while run_dir.exists():
        run_dir_name = f"{timestamp}_{name}_{counter}"
        run_dir = RUNS_DIR / run_dir_name
        counter += 1
    
    # Create directory structure
    run_dir.mkdir(parents=True)
    (run_dir / "processed").mkdir()
    (run_dir / "outputs").mkdir()
    (run_dir / "figures").mkdir()
    
    # Create run config
    config = {
        "name": name,
        "created": datetime.now().isoformat(),
        "signal": signal,
        "regions": region_list,
        "region_group": regions if isinstance(regions, str) and regions in REGION_GROUPS else None,
        "data_types": data_type_list,
        "date_range": {
            "start": date_range[0].isoformat() if date_range else None,
            "end": date_range[1].isoformat() if date_range else None,
        },
        "description": description,
        "scripts_run": [],
        "signal_metadata": SIGNALS.get(signal, {}),
        "region_metadata": {r: REGIONS.get(r, {}) for r in region_list},
    }
    
    save_run_config(run_dir, config)
    
    print(f"Created run: {run_dir}")
    print(f"  Signal: {signal}")
    print(f"  Regions: {', '.join(region_list)}")
    print(f"  Data types: {', '.join(data_type_list)}")
    
    return run_dir


def save_run_config(run_dir: Path, config: dict) -> None:
    """Save run configuration."""
    config_path = run_dir / "run_config.json"
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2, default=str)


def load_run_config(run_dir: Path) -> dict:
    """Load run configuration."""
    config_path = run_dir / "run_config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"No run config found at {config_path}")
    
    with open(config_path, 'r') as f:
        return json.load(f)


def validate_run_config(run_dir: Path) -> tuple[bool, List[str]]:
    """
    Validate that a run config has all required fields.
    
    Returns:
        (is_valid, list_of_errors)
    """
    errors = []
    
    try:
        config = load_run_config(run_dir)
    except FileNotFoundError as e:
        return False, [str(e)]
    
    required_fields = ["signal", "regions", "data_types"]
    
    for field in required_fields:
        if field not in config:
            errors.append(f"Missing required field: {field}")
        elif not config[field]:
            errors.append(f"Empty required field: {field}")
    
    # Validate signal
    if "signal" in config and config["signal"] not in SIGNALS:
        errors.append(f"Unknown signal: {config['signal']}. Valid: {list(SIGNALS.keys())}")
    
    # Validate data_types
    valid_types = ["historical", "forecast"]
    if "data_types" in config:
        for dt in config["data_types"]:
            if dt not in valid_types:
                errors.append(f"Invalid data_type: {dt}. Valid: {valid_types}")
    
    return len(errors) == 0, errors


def validate_run_against_library(run_dir: Path) -> tuple[bool, List[str]]:
    """
    Validate that library has required data for this run.
    
    Returns:
        (is_valid, list_of_missing_data)
    """
    from utils.library_manager import validate_library_requirements
    
    config = load_run_config(run_dir)
    
    signal = config["signal"]
    regions = config["regions"]
    data_types = config["data_types"]
    
    # Parse date range if specified
    date_range = config.get("date_range", {})
    start = datetime.fromisoformat(date_range["start"]) if date_range.get("start") else None
    end = datetime.fromisoformat(date_range["end"]) if date_range.get("end") else None
    
    all_missing = []
    
    for data_type in data_types:
        is_valid, missing = validate_library_requirements(
            signal, regions, data_type, start, end
        )
        all_missing.extend(missing)
    
    return len(all_missing) == 0, all_missing


def get_run_paths(run_dir: Path) -> dict:
    """Get standard paths for a run."""
    return {
        "root": run_dir,
        "processed": run_dir / "processed",
        "outputs": run_dir / "outputs",
        "figures": run_dir / "figures",
        "config": run_dir / "run_config.json",
    }


def mark_script_run(run_dir: Path, script_name: str) -> None:
    """Record that a script was run."""
    config = load_run_config(run_dir)
    
    entry = {
        "script": script_name,
        "timestamp": datetime.now().isoformat(),
    }
    
    config["scripts_run"].append(entry)
    save_run_config(run_dir, config)


def list_runs() -> List[Path]:
    """List all run directories, newest first."""
    if not RUNS_DIR.exists():
        return []
    
    runs = [d for d in RUNS_DIR.iterdir() if d.is_dir() and (d / "run_config.json").exists()]
    return sorted(runs, reverse=True)


def print_runs_summary() -> None:
    """Print summary of all runs."""
    runs = list_runs()
    
    print("=" * 70)
    print("ANALYSIS RUNS")
    print("=" * 70)
    
    if not runs:
        print("\n  No runs found. Create one with:")
        print("    python utils/run_manager.py create <name> -s <signal> -r <regions>")
        return
    
    for run_dir in runs:
        try:
            config = load_run_config(run_dir)
            print(f"\n{run_dir.name}:")
            print(f"  Signal: {config.get('signal', '?')}")
            print(f"  Data types: {', '.join(config.get('data_types', ['?']))}")
            print(f"  Regions: {', '.join(config.get('regions', []))}")
            print(f"  Created: {config.get('created', '?')[:16]}")
            if config.get("description"):
                print(f"  Description: {config['description']}")
            scripts = [s["script"] for s in config.get("scripts_run", [])]
            if scripts:
                print(f"  Scripts run: {', '.join(scripts)}")
        except Exception as e:
            print(f"\n{run_dir.name}: Error reading config - {e}")
    
    print("\n" + "=" * 70)


def get_latest_run(signal: Optional[str] = None) -> Optional[Path]:
    """Get the most recent run, optionally filtered by signal."""
    runs = list_runs()
    
    for run_dir in runs:
        try:
            config = load_run_config(run_dir)
            if signal is None or config.get("signal") == signal:
                return run_dir
        except:
            continue
    
    return None


def find_run_by_name(name_pattern: str) -> Optional[Path]:
    """Find a run by partial name match."""
    runs = list_runs()
    
    for run_dir in runs:
        if name_pattern in run_dir.name:
            return run_dir
    
    return None


# CLI interface
def main():
    parser = argparse.ArgumentParser(description="Manage analysis runs")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List all runs")
    
    # Create command
    create_parser = subparsers.add_parser("create", help="Create new run")
    create_parser.add_argument("name", help="Run name (e.g., 'moer_temporal')")
    create_parser.add_argument("--signal", "-s", required=True, help="Signal type")
    create_parser.add_argument("--regions", "-r", required=True, help="Regions or group name")
    create_parser.add_argument("--data-types", "-t", nargs="+", default=["historical"],
                               choices=["historical", "forecast"],
                               help="Data types needed (default: historical)")
    create_parser.add_argument("--description", "-d", default="", help="Description")
    
    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate a run")
    validate_parser.add_argument("run_name", help="Run name or pattern to match")
    
    args = parser.parse_args()
    
    if args.command == "list":
        print_runs_summary()
    
    elif args.command == "create":
        # Parse regions (could be comma-separated or group name)
        if args.regions in REGION_GROUPS:
            regions = args.regions
        else:
            regions = [r.strip() for r in args.regions.split(",")]
        
        create_run(
            name=args.name,
            signal=args.signal,
            regions=regions,
            data_types=args.data_types,
            description=args.description
        )
    
    elif args.command == "validate":
        run_dir = find_run_by_name(args.run_name)
        if not run_dir:
            print(f"No run found matching: {args.run_name}")
            return
        
        print(f"Validating: {run_dir.name}")
        
        # Validate config
        is_valid, errors = validate_run_config(run_dir)
        if not is_valid:
            print("\nConfig errors:")
            for e in errors:
                print(f"  - {e}")
            return
        print("  Config: OK")
        
        # Validate against library
        is_valid, missing = validate_run_against_library(run_dir)
        if not is_valid:
            print("\nMissing library data:")
            for m in missing:
                print(f"  - {m}")
            print("\nRun data collection first.")
        else:
            print("  Library data: OK")
            print("\nRun is ready to execute.")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
