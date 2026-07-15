#!/usr/bin/env bash
# Render every scene in the kit at once.
# Usage: ./scripts/render_all.sh [ql|qm|qh|qk]   (default: qm)

set -e
QUALITY="${1:-qm}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Run from the package root (not src/scenes/) so manim picks up manim.cfg,
# which it only looks for in the current working directory, not parent dirs.
cd "$ROOT"

echo "Rendering at -$QUALITY ..."
manim "-$QUALITY" src/scenes/carbon_schedule.py CarbonSchedule
manim "-$QUALITY" src/scenes/energy_attribution.py EnergyAttribution
manim "-$QUALITY" src/scenes/material_electricity_split.py MaterialElectricitySplit

echo "Done. Output under $ROOT/media/videos/"
