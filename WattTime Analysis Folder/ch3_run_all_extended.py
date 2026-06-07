"""
ch3_run_all_extended.py — Run all Chapter 3 extended analysis scripts.

Separate from the core ch3_run_all.py. Uses the same ch3_common infrastructure
but outputs to a dedicated numbers file (ch3_numbers_extended.md) to avoid
overwriting core chapter numbers.

Usage:
    python ch3_run_all_extended.py                 # run all 10 extended scripts
    python ch3_run_all_extended.py --script 1 3    # run specific scripts
    python ch3_run_all_extended.py --recompute     # ignore cached results
    python ch3_run_all_extended.py --clean-cache   # clear extended caches only
    python ch3_run_all_extended.py --list          # show available scripts

Scripts:
     1  Signal Predictability       — Why do heuristics work?
     2  Three-Tier Signals          — Does signal choice matter?
     3  Threshold Optimization      — Is P25/P75 optimal?
     4  Heuristic Shelf Life        — How fast do rules go stale?
     5  Health Co-benefits          — Carbon vs health tradeoff?
     6  Decarbonization Trajectory  — Is this becoming more valuable?
     7  Economic Value              — What's it worth in dollars?
     8  Production Queue            — What about real batch sizes?
     9  Intra-ISO Portability       — One rule for multiple plants?
    10  Shift Flexibility           — How much does extending hours help?
"""

import argparse
import time
import ch3_common

# ── Override numbers file so we don't clobber core chapter numbers ──────────
_EXT_NUMBERS = ch3_common.OUTPUT_DIR / "ch3_numbers_extended.md"
ch3_common.NUMBERS_FILE = _EXT_NUMBERS


SCRIPTS = {
    1:  "Signal Predictability",
    2:  "Three-Tier Signals",
    3:  "Threshold Optimization",
    4:  "Heuristic Shelf Life",
    5:  "Health Co-benefits",
    6:  "Decarbonization Trajectory",
    7:  "Economic Value",
    8:  "Production Queue",
    9:  "Intra-ISO Portability",
    10: "Shift Flexibility",
}


def run_script(num: int, recompute: bool):
    t0 = time.time()
    name = SCRIPTS[num]
    print(f"\n{'='*60}")
    print(f"[{num}/10] {name}")
    print(f"{'='*60}")

    try:
        if num == 1:
            from ch3_extended_signal_predictability import main as fn
        elif num == 2:
            from ch3_extended_three_tier_signals import main as fn
        elif num == 3:
            from ch3_extended_threshold_optimization import main as fn
        elif num == 4:
            from ch3_extended_heuristic_shelf_life import main as fn
        elif num == 5:
            from ch3_extended_health_cobenefits import main as fn
        elif num == 6:
            from ch3_extended_decarbonization_trajectory import main as fn
        elif num == 7:
            from ch3_extended_economic_value import main as fn
        elif num == 8:
            from ch3_extended_production_queue import main as fn
        elif num == 9:
            from ch3_extended_intra_iso_portability import main as fn
        elif num == 10:
            from ch3_extended_shift_flexibility import main as fn
        else:
            print(f"  ⚠️  Unknown script: {num}")
            return

        fn(recompute=recompute)

    except Exception as e:
        print(f"\n  ❌ Script {num} ({name}) failed: {e}")
        import traceback
        traceback.print_exc()

    elapsed = time.time() - t0
    print(f"\n⏱  {name} completed in {elapsed:.1f}s")


def main():
    parser = argparse.ArgumentParser(
        description="Run Chapter 3 extended analysis scripts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(f"  {k:>2d}  {v}" for k, v in SCRIPTS.items()),
    )
    parser.add_argument(
        "--script", "-s", type=int, nargs="+", default=None,
        help="Script(s) to run (1-10). Default: all.",
    )
    parser.add_argument(
        "--recompute", action="store_true",
        help="Ignore cached simulation results.",
    )
    parser.add_argument(
        "--clean-cache", action="store_true",
        help="Clear extended caches (ext_* files) before running.",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List available scripts and exit.",
    )
    args = parser.parse_args()

    if args.list:
        print("Available extended analysis scripts:")
        for k, v in SCRIPTS.items():
            print(f"  {k:>2d}  {v}")
        return

    if args.clean_cache:
        import glob
        cache_dir = ch3_common.CACHE_DIR
        if cache_dir.exists():
            for f in cache_dir.glob("ext_*"):
                f.unlink()
                print(f"  🗑  {f.name}")
        print()

    scripts_to_run = args.script or list(SCRIPTS.keys())

    # Validate
    invalid = [s for s in scripts_to_run if s not in SCRIPTS]
    if invalid:
        print(f"⚠️  Unknown scripts: {invalid}. Valid: 1-10")
        return

    print("=" * 60)
    print("CHAPTER 3 — EXTENDED ANALYSIS")
    print("=" * 60)
    print(f"Scripts: {[SCRIPTS[s] for s in scripts_to_run]}")
    print(f"Recompute: {args.recompute}")
    print(f"Numbers file: {_EXT_NUMBERS}")
    print("=" * 60)

    t_total = time.time()

    for s in scripts_to_run:
        run_script(s, args.recompute)
        print()

    elapsed = time.time() - t_total
    print("=" * 60)
    print(f"ALL DONE — {elapsed:.1f}s total")
    print(f"  Figures: {ch3_common.FIGURES_DIR}")
    print(f"  Tables:  {ch3_common.TABLES_DIR}")
    print(f"  Numbers: {_EXT_NUMBERS}")
    print("=" * 60)


if __name__ == "__main__":
    main()
