# thesis_animations

Manim scenes for visualizing the carbon-aware scheduling and energy
attribution work (Purdue IN-MaC thesis / MSEC 2026 paper / JMSE
extension). Presentation/communication layer only, it renders figures and
video from data and numbers computed elsewhere in this repo; it performs no
analysis itself.

## Setup

System deps (once per machine):
```
# Debian/Ubuntu
sudo apt install ffmpeg libpango1.0-dev libcairo2-dev pkg-config

# macOS
brew install ffmpeg pango cairo pkg-config
```

Python deps:
```
pip install -r requirements.txt
```

LaTeX is intentionally not required, all scenes use `Text` instead of
`MathTex`. If you want real typeset equations (e.g. the attribution
integral from Ch. 2), install a LaTeX distribution (texlive-full or
MiKTeX) and swap the relevant `Text(...)` calls for `MathTex(...)`.

## Structure

```
thesis_animations/
├── data/                        # real MOER CSVs go here, per archetype
├── src/
│   ├── scenes/
│   │   ├── carbon_schedule.py           # Ch. 3: threshold vs fixed scheduling
│   │   ├── energy_attribution.py        # Ch. 2: UUID-tagged power trace
│   │   └── material_electricity_split.py # materials vs. mfg. electricity
│   └── utils/
│       ├── theme.py             # shared colors/fonts, edit once, applies everywhere
│       └── data_loader.py       # MOER CSV loader with synthetic fallback
├── scripts/
│   └── render_all.sh            # render every scene in one pass
└── manim.cfg                    # output goes to ./media, keeps repo root clean
```

## Rendering

Single scene, from the `thesis_animations/` root (not `src/scenes/` — manim
only looks for `manim.cfg` in the current working directory, so running from
the package root is what makes output land in `./media` instead of
`src/scenes/media`):
```
manim -qm src/scenes/carbon_schedule.py CarbonSchedule      # medium quality, fast iteration
manim -qh src/scenes/carbon_schedule.py CarbonSchedule      # high quality, for a talk/paper
```

All scenes at once:
```
./scripts/render_all.sh qm
```

## Using real data

`carbon_schedule.py` reads `data/{archetype}.csv` (see `data/README.md`
for the schema). Until you drop real WattTime exports in, it renders
against a labeled synthetic placeholder so nothing breaks. To render
all six archetypes, change `ARCHETYPE` at the top of the file and
re-render, or extend `render_all.sh` with a loop.

`energy_attribution.py` and `material_electricity_split.py` currently
use illustrative placeholder numbers (`OPERATIONS` and `MATERIALS_PCT`
respectively) rather than a real logged run, since that means editing
one constant/table at the top of each file to swap in a real MTConnect
or IAMMETER-derived dataset when you have one ready.

This repo already has real WattTime MOER exports elsewhere (see
`WattTime Analysis Folder/` and `Background watttime scripts/`) and real
machine energy logs (`Machine Specific Scripts/`, `Al6061Body/`,
`Al6061Lid/`). When you are ready to make a scene reflect real numbers,
pull the representative-day series or attributed-energy table from those
folders into `data/` or the scene's constants rather than re-deriving it
here, this kit intentionally does no data processing of its own.

## Extending

- New scene: add a file to `src/scenes/`, `import theme` and
  `data_loader` from `utils` the same way the existing scenes do, so
  colors and fonts stay consistent.
- Consistent look: change `PRIMARY`, `GOOD`, `BAD`, etc. in
  `src/utils/theme.py` rather than hardcoding colors in each scene.
- New chapter/finding as it's computed: add a scene file plus, if it
  needs a data file, a loader in `src/utils/` following `data_loader.py`'s
  pattern (real CSV/table if present, labeled synthetic fallback
  otherwise) so the kit keeps rendering even before the number is final.
