#!/usr/bin/env bash
# Render every scene in the kit at once.
# Usage: ./scripts/render_all.sh [ql|qm|qh|qk]   (default: qm)

set -e
QUALITY="${1:-qm}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCENES_DIR="$ROOT/src/scenes"

cd "$SCENES_DIR"

echo "Rendering at -$QUALITY ..."
manim "-$QUALITY" carbon_schedule.py CarbonSchedule
manim "-$QUALITY" energy_attribution.py EnergyAttribution
manim "-$QUALITY" material_electricity_split.py MaterialElectricitySplit

echo "Done. Output under $ROOT/media/videos/"
