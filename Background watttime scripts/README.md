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

- Replace hardcoded credentials with environment-variable instructions.
- Add a short explanation of WattTime signal types used by the research.
- Document when to use these helpers versus the newer data-collection pipeline.
- Add an example `.env.example` file after removing real credentials.

## Safety notes before sharing

- Rotate any WattTime credentials that have ever been committed.
- Do not publish token files or license-restricted access details.
- Treat generated region CSVs as reference artifacts and confirm redistribution rights before public release.

