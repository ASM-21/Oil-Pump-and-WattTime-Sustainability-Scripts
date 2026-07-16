# Background WattTime Scripts

This folder contains early helper scripts for working with the WattTime API, including token testing, region discovery, location tests, and exported region availability.

## Current status

**Legacy / setup reference.** These scripts are useful for understanding how WattTime access and region discovery were first tested, but the newer workflow in `WattTime Analysis Folder/` should be treated as the main analysis area.

## Key files

| File | Role |
| --- | --- |
| `wattTime_token.py` | Token/authentication helper. |
| `wattTime_tester.py` | Early API connectivity test. |
| `wattTime_listregions.py` | Exports available WattTime regions and signal availability. |
| `wattTime_somelocationstest.py` | Tests selected locations/regions. |
| `wattTime_extras.py` | Miscellaneous helper experiments. |
| `watttime_regions.csv` | Exported region/signal availability reference. |

## Recommended docs to add next

- ~~Replace hardcoded credentials with environment-variable instructions.~~ **Checked:** all five scripts already read `WATTTIME_USERNAME`/`WATTTIME_PASSWORD` via `os.getenv(...)` with a clear error if unset; no hardcoded credentials found in this pass. `wattTime_token.py` writes a fetched token to `WattTime_token.txt`, which matches the repo `.gitignore`'s `*Token*.txt` pattern and is not tracked.
- Add a short explanation of WattTime signal types used by the research.
- Document when to use these helpers versus the newer data-collection pipeline.
- Add an example `.env.example` file after removing real credentials (repo root already has one; confirm it covers these two variables).

## Safety notes before sharing

- Rotate any WattTime credentials that have ever been committed to older history (not present in the current files, but check git log if this folder is ever made public).
- Do not publish token files or license-restricted access details.
- Treat generated region CSVs as reference artifacts and confirm redistribution rights before public release.

