"""
ch3_run_all.py — Run all Chapter 3 figure/table scripts.

Usage:
    python ch3_run_all.py                 # run all sections
    python ch3_run_all.py --section 2     # run only Section 3.4 (traffic light)
    python ch3_run_all.py --section 1 3   # run Sections 3.3 and 3.5
    python ch3_run_all.py --recompute     # ignore cached results
    python ch3_run_all.py --clean         # delete cache + outputs before running
"""

import argparse
import shutil
import time
from pathlib import Path

from ch3_common import OUTPUT_DIR, CACHE_DIR, FIGURES_DIR, TABLES_DIR, NUMBERS_FILE


def clean_outputs():
    """Remove all cached and generated outputs."""
    for d in [CACHE_DIR, FIGURES_DIR, TABLES_DIR]:
        if d.exists():
            shutil.rmtree(d)
            print(f"  🗑  Removed {d}")
    if NUMBERS_FILE.exists():
        NUMBERS_FILE.unlink()
        print(f"  🗑  Removed {NUMBERS_FILE.name}")
    print()


def run_section(section: int, recompute: bool):
    """Run one section script."""
    t0 = time.time()
    
    if section == 1:
        from ch3_s1_grid_characterization import main as s1_main
        s1_main(recompute=recompute)
    elif section == 2:
        from ch3_s2_traffic_light import main as s2_main
        s2_main(recompute=recompute)
    elif section == 3:
        from ch3_s3_constraints import main as s3_main
        s3_main(recompute=recompute)
    elif section == 4:
        from ch3_s4_discussion import main as s4_main
        s4_main(recompute=recompute)
    elif section == 5:
        from ch3_appendix_c import main as app_main
        app_main(recompute=recompute)
    else:
        print(f"  ⚠️  Unknown section: {section}")
        return
    
    elapsed = time.time() - t0
    print(f"\n⏱  Section 3.{section + 2} completed in {elapsed:.1f}s")


def main():
    parser = argparse.ArgumentParser(
        description="Run Chapter 3 figure and table generation."
    )
    parser.add_argument(
        "--section", "-s", type=int, nargs="+", default=None,
        help="Section(s) to run: 1=3.3, 2=3.4, 3=3.5, 4=3.6, 5=AppC. Default: all."
    )
    parser.add_argument(
        "--recompute", action="store_true",
        help="Ignore cached simulation results."
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Delete all cached/generated outputs before running."
    )
    args = parser.parse_args()
    
    if args.clean:
        clean_outputs()
    
    sections = args.section or [1, 2, 3, 4, 5]
    
    print("=" * 60)
    print("CHAPTER 3 — FIGURE & TABLE GENERATION")
    sec_names = {1: "3.3", 2: "3.4", 3: "3.5", 4: "3.6", 5: "App C"}
    print(f"Sections to run: {[sec_names.get(s, f'?{s}') for s in sections]}")
    print(f"Recompute: {args.recompute}")
    print("=" * 60)
    print()
    
    t_total = time.time()
    
    for s in sections:
        run_section(s, args.recompute)
        print()
    
    elapsed = time.time() - t_total
    print("=" * 60)
    print(f"ALL DONE — {elapsed:.1f}s total")
    print(f"  Figures: {FIGURES_DIR}")
    print(f"  Tables:  {TABLES_DIR}")
    print(f"  Numbers: {NUMBERS_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
