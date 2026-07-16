# OpenNX feature-energy library vs. measured operations

First comparison of aluminum_expanded.xlsx (100% placeholder
data per build_aluminum_library.py: every row has
`source="placeholder"` and an empty `uuid` column) against the
real, UUID-labeled per-operation energy already committed in
`ML Explore/operation_csvs/`. This has never been checked before:
the library's `uuid`/`source` columns exist specifically to hold
this kind of measurement but have never been filled in.

**Category assignment is a judgment call made in this script**
(operation name -> library feature type), not a documented CAM
crosswalk. No per-operation geometry (hole diameter, pocket area,
depth) is available from the measured data, so this is a
category-level range check -- does the placeholder table sit in
the right order of magnitude for that class of operation -- not a
dimension-matched point comparison.

Matched 45 distinct operations (1113 runs
total) to measured data; 0 had no category
assignment; 0 operation UUIDs in the CSVs
were not in the uuid_to_operation table.

## featureId channel: confirmed dead

Every row in every operation CSV has `featureId` = `NONE` or
`UNAVAILABLE` -- never a real feature identifier. The channel that
would let a feature-energy library be built directly from the CNC
controller's own feature labels is not populated in this dataset.
Operation identity (`processKindId`) plus a hand-built name map
(`EnergyForFeatureLib.py`) is the only route to feature category
today. Worth stating plainly rather than continuing to describe
featureId as merely "unused."

## Category comparison

| Category | Measured ops (n) | Measured mean energy_wh (range across ops) | Placeholder library range (n rows) | Verdict |
|---|---|---|---|---|
| chamfer | 2 | 7.971-22.949 Wh | 0.005-0.550 Wh (13) | measured ABOVE placeholder range (14.5x high) |
| counterbore_operation | 3 | 0.272-7.107 Wh | 0.025-0.560 Wh (20) | measured falls within placeholder range |
| face | 6 | 4.450-57.733 Wh | 0.050-2.950 Wh (10) | measured ABOVE placeholder range (1.5x high) |
| hole_simple | 16 | 0.222-15.373 Wh | 0.010-1.500 Wh (46) | measured falls within placeholder range |
| pocket_rectangular | 4 | 41.536-141.633 Wh | 0.045-3.450 Wh (24) | measured ABOVE placeholder range (12.0x high) |
| tap_operation | 3 | 1.389-20.643 Wh | 0.015-1.780 Wh (35) | measured falls within placeholder range |

**Read on `pocket_rectangular` (the largest gap, 12x):** the
library's largest tabulated row is a 100x100 mm pocket, 30 mm
deep (300,000 mm^3 removed, 3.45 Wh). The body's own BOM shows
~1437 g (~532,000 mm^3 at Al6061 density) removed in total across
*all* operations combined, and cavity milling is the dominant
roughing step. A single cavity-mill pass plausibly removes a
volume near the library's largest entry, so this is less "the
placeholder number is wrong" and more "the placeholder table's
dimensional range stops well short of where this part's real
roughing operations sit" -- every pocket_rectangular estimate for
this part is extrapolated far past the table's calibrated range.

**Basis caveat on `chamfer`:** the library stores energy *per
edge* (`per_edge: True`, multiplied by `edge_count` at lookup
time), while the measured value here is the whole operation's
energy with an unknown edge count. The 14.5x gap therefore
conflates two things -- multiple edges per operation, and a
possibly-too-low per-edge placeholder -- and should not be read
as a clean per-edge error until edge_count is pulled from the NX
part file.

**Register resolution caveat:** the `forward kWh` register
advances in ~0.33 Wh steps (0.000333 kWh ticks, confirmed on the
raw data). For the shortest operations (SPOTTING_*, some
DRILLING_* -- means under ~1 Wh), a single tick is a large
fraction of the whole reading, which is why their per-run min-max
columns in `library_validation_results.csv` swing between 0 and a
few Wh. `hole_simple` and `counterbore_operation` "falls within
placeholder range" verdicts are the least trustworthy of the six
for this reason -- the bigger categories (face, pocket_rectangular,
chamfer, most of tap_operation) are tens of Wh, far above this
noise floor, so their above-range verdicts are not quantization
artifacts.

## Archetype cross-check

Corroboration for the category assignments above (not an input to
them): does each OpenNX category group operations the owner's own,
independently-defined `OPERATION_ARCHETYPES`
(`EnergyForFeatureLib_otherValsV2.py`) also considers mechanistically
alike? A category spanning >1 archetype is mixing process types
(e.g. roughing and finishing) under one energy lookup, which is a
second, independent reason a single point estimate per category
can be too coarse, on top of the missing-dimension problem above.

- `chamfer`: DEBURR_CHAMFER
- `counterbore_operation`: DRILLING, FINISH_MILL, SPOT_DRILL -- MIXED ARCHETYPES
- `face`: FACING
- `hole_simple`: DRILLING, FINISH_MILL, HOLE_MILL, SPOT_DRILL -- MIXED ARCHETYPES
- `pocket_rectangular`: ROUGH_MILL
- `tap_operation`: TAPPING

## Anomaly worth a second look: finishing costs more than roughing

For both hole-type features with a finishing pass in the data,
`FINISH_*` measures several times higher than the `DRILLING_*`/
`SPOTTING_*` steps on the same hole, which is the opposite of what
"finishing" suggests (a light final pass). Flagging rather than
explaining -- possible causes include the finish step actually
being a slow-feed boring/reaming pass rather than a light skim, or
a labeling mismatch; worth checking against the CAM program before
using either number:

- FINISH_CBORE=7.107 Wh, SPOTTING_CBORE=0.272 Wh, DRILLING_CBORE=1.062 Wh
- FINISH_POCKET_HOLE=12.827 Wh, SPOTTING_POCKET_HOLE=0.222 Wh, DRILLING_POCKET_HOLE=1.296 Wh

## Operations with no library category

These measured operations (wall/profile finishing passes, plus
engraving) have no matching category in `FEATURE_CONFIG`
(`energy_lookup.py`). This is a coverage gap in the library, not
just an accuracy question -- roughly a third of the real named
operations on this part cannot be looked up at all today:

- ENGRAVING (measured mean 6.708 Wh, n=32 runs)
- FINISH_INNER_PROFILE (measured mean 3.262 Wh, n=28 runs)
- FINISH_OUTER_PROFILE (measured mean 6.202 Wh, n=28 runs)
- FINISH_OUTER_WALL (measured mean 14.512 Wh, n=28 runs)
- LID_FINISH_OUTER_PROFILE (measured mean 6.097 Wh, n=24 runs)
- LID_FINISH_SURFACES (measured mean 8.431 Wh, n=24 runs)
- LID_FINISH_UPPER_WALL (measured mean 12.194 Wh, n=24 runs)
- PLANAR_DEBURRING (measured mean 12.962 Wh, n=88 runs)
- PLANAR_PROFILING_AGAIN (measured mean 23.739 Wh, n=23 runs)
- PLANAR_PROFILING_AGAIN_COPY (measured mean 13.778 Wh, n=18 runs)
- WALL_FLOOR_PROFILING (measured mean 29.274 Wh, n=28 runs)

## Next step this points to

The library schema already has `uuid` and `source` columns
waiting for exactly this data (see build_aluminum_library.py
docstring: "replace placeholder values with your IN-MaC
measurements"). The natural follow-up is not more validation but
substitution: for categories where measured operations exist,
replace the placeholder rows with real (dimension, energy, uuid)
triples once feature dimensions (hole diameter/depth, pocket area)
are pulled from the NX part files via feature_extractor.py. That
also directly answers EXPANSION_DIRECTIONS D2 / FUTURE_WORK.md's
"validate OpenNX feature-energy estimates against measured CNC
program energy" item, which has been open with no data behind it
until this run.

