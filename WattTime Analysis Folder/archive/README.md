# Archive

Retired scripts, kept for history rather than deleted. Each was superseded
by a canonical version per `../CODE_GUIDE.md` section 4 ("Versioned /
Duplicate Scripts — Consolidation Guide"), which explains what each version
added and why it's safe to treat as historical:

| File | Superseded by |
|---|---|
| `03_temporal_patterns_v1.py`, `v2.py`, `v3.py` | `../03_temporal_patterns.py` (was v4; contains every prior version's additions) |
| `06_heuristics_v1.py`, `v2.py` | `../06_heuristics.py` (was v3) |
| `01_data_collection v2.py` | `../01_data_collection.py` (was v1; v2 was the same script with different CONFIG values for one specific data pull) |
| `03.1_temporal_patterns_kansas debug.py` | Diagnostic only, not production code; see CODE_GUIDE.md Group B |
| `400_all_aoer_regions_exploretest.py` | One-off API access verification, not part of any pipeline |
| `Ch3_defesneercotandspp_code that suckis and output directorywrong.py` | Abandoned debug script; kept in case any logic is worth salvaging later |

Nothing here is imported by any active script (verified: only comments/print
statements referenced these filenames, and those were updated to point at
the canonical files). Safe to consult for history, not meant to be run.
