# Figure and Table Index

This is the traceability table for thesis/report/portfolio outputs. Fill it in as figures are finalized so every claim can be regenerated or audited.

| Output | Script | Inputs | Output path | Final? | Notes |
| --- | --- | --- | --- | --- | --- |
| Chapter 3 summary numbers | `WattTime Analysis Folder/ch3_run_all.py` | Processed WattTime run data | `WattTime Analysis Folder/ch3_outputs/ch3_numbers.md` | Candidate | Verify exact run folder/date before publication. |
| Extended Chapter 3 summary numbers | `WattTime Analysis Folder/ch3_run_all_extended.py` | Processed WattTime run data | `WattTime Analysis Folder/ch3_outputs/ch3_numbers_extended.md` | Candidate | Verify exact run folder/date before publication. |
| Green-window length figure | `WattTime Analysis Folder/CH3_FIG_greenwindowLength.py` | Chapter 3 processed outputs | TBD | Candidate | Add output filename and figure caption. |
| Optimal-hour heatmap | `WattTime Analysis Folder/CH3_FIG_optimalHourHeatmap.py` | Chapter 3 processed outputs | TBD | Candidate | Add output filename and figure caption. |
| CNC program energy plots | `Machine Specific Scripts/CNC/map9EntireProgramsV2.py` and variants | Machine energy traces | TBD | Exploratory | Decide canonical plotting script. |
| Additive energy boxplots | `Machine Specific Scripts/Additive/` scripts | 3D printer energy traces | TBD | Exploratory | Add sample input schema. |

## How to use this file

- Add one row per thesis figure, appendix figure, report table, or portfolio graphic.
- Mark `Final?` as `Final`, `Candidate`, `Exploratory`, or `Deprecated`.
- Record exact input data versions and output paths once canonical runs are finalized.
