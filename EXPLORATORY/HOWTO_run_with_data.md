# How to run the analysis once you have your CNC data

**Deadline context:** journal submission June 30, 2026.
This is the step-by-step you follow when you sit down with your Al6061 CSV files.

---

## Before you start: what you need

| Item | Where it lives | Needed for |
|---|---|---|
| Al6061_body*.csv and Al6061_lid*.csv | Your local machine | All CNC analysis |
| Verified stock + finished masses (body, lid) | Lab records / measurement logs | L2 estimation, C1 specific energy |
| Photo of Hurco VMX30Ui electrical plate (optional) | IN-MaC machine room | Cleaner utilization factor |

You do NOT need the MOER data or AM CSV files to run the main analyses.

---

## Step 0: point the code at your CSV folder

The adapter asks you interactively the first time. You can also set it in advance:

```bash
# Mac / Linux
export CNC_DATA_DIR=/path/to/your/Al6061_csv_folder

# Windows (Command Prompt)
set CNC_DATA_DIR=C:\path\to\your\Al6061_csv_folder
```

Once you enter the path once (when prompted), it saves to `EXPLORATORY/.data_paths.txt`
and will not ask again on the same machine.

---

## Step 1: run the adapter gate test

```bash
python EXPLORATORY/shared/test_adapters.py
```

**What to check:**

- `[GATE] load_operation_energy ... shape=(N, 11) OK` -- if this fails, CNC_DATA_DIR is wrong or the CSV files are not named Al6061_*.csv
- Operation count printed: expect 45 or 49 distinct operations (the script notes which)
- Run counts per program: expect 16 to 27 runs per program
- `GATE PASSED` at the end

If the gate fails, do not proceed. Fix the path or CSV naming first.

---

## Step 2: run estimation_ladder

```bash
python EXPLORATORY/estimation_ladder/run.py
```

**What to check in the output:**

| Number | Where it appears | Expected | What it means |
|---|---|---|---|
| CNC fleet avg power | printed + FINDINGS.md | ~1,376 W | regression slope from data |
| u_CNC | printed + FINDINGS.md | ~0.10 | 1,376 / 13,400 rated |
| L0 error (body, lid) | FINDINGS.md table | large positive (+900% range) | rated power wildly overestimates |
| L1 error | FINDINGS.md table | near 0% | characterized power works well |
| SW near-normal ops | printed + FINDINGS.md | 40 of 45 | per-operation distribution shape |

**Before citing these numbers, update in `estimation_ladder/run.py`:**

- `CNC_RATED_POWER_W`: if you have the electrical plate photo, use total connected load; otherwise leave at 13,400 W and state the basis explicitly in the paper
- `MASS_REMOVED_G`: once you confirm stock and finished masses, update and set `MASS_DATA_VERIFIED = True`

**Outputs generated:**

- `estimation_ladder/outputs/program_run_errors.csv` -- L0-L4 error per run
- `estimation_ladder/outputs/operation_cv_replication.csv` -- CV and n requirement per operation
- `estimation_ladder/outputs/normality_shapiro_wilk.csv` -- SW test per operation
- `estimation_ladder/outputs/uncertainty_intervals.csv` -- 95% CI per program
- `estimation_ladder/outputs/summary_by_part.csv` -- one row per part, used by build_summary.py
- `estimation_ladder/FINDINGS.md` -- narrative with all numbers and caveats

---

## Step 3: run allocation

```bash
python EXPLORATORY/allocation/run.py
```

**What to check:**

| Number | Expected | What it means |
|---|---|---|
| Lid / body energy ratio | ~0.677 | 67.7% quoted in paper; DISAGREE here is a finding |
| Homing share | ~11.7% | non-productive repositioning energy |
| Time-based allocation error | depends | how badly time allocation misassigns vs measured |
| Body SEC (kWh/kg) | ~0.36 | specific energy at mass-removed basis |
| Lid SEC (kWh/kg) | ~0.78 | higher per-kg because it is lighter but still machined |

A DISAGREE on lid/body ratio is a genuine finding, not a bug. Report it.

**Outputs generated:**

- `allocation/outputs/allocation_rule_errors.csv`
- `allocation/outputs/part_mean_energy.csv`
- `allocation/outputs/specific_energy_per_part.csv` -- C1 specific energy
- `allocation/outputs/mix_sweep.csv`
- `allocation/FINDINGS.md`

---

## Step 4: run wear_runorder (optional -- needs extra packages)

```bash
pip install scipy statsmodels   # if not already installed
python EXPLORATORY/wear_runorder/run.py
```

This tests whether energy drifts systematically with run order (wear, warm-up, operator effects).
Expected: most operations show no trend; the paper's i.i.d. assumption holds for most but a few
high-variability operations (spotting, tapping) may show weak trends.

If the run-order test finds nothing significant, that is a clean result: the data supports the
paper's implicit assumption that runs are exchangeable. Report it as verification, not absence of result.

---

## Step 5: run B1 break-even (no data needed -- run anytime)

```bash
python EXPLORATORY/explorations/B1_breakeven.py
```

This is self-contained. It only needs the total CNC energy per part, which comes from the
context doc estimates until you update them from Step 2's output.

After running Step 2, update `B1_breakeven.py` at the top:

```python
# Update these from estimation_ladder/outputs/summary_by_part.csv
TOTAL_ENERGY_WH = {
    "body": <L4_mean_wh from body row>,
    "lid":  <L4_mean_wh from lid row>,
}
ENERGY_VERIFIED = True   # flip this flag
```

Then re-run. The break-even contour figure goes straight into the Discussion section.

---

## Step 6: run build_summary

```bash
python EXPLORATORY/build_summary.py
```

Reads all the output CSVs from Steps 2 and 3 and writes `EXPLORATORY/_summary.md` with the
computed-vs-quoted numbers table. Run this last to get the full picture in one place.

---

## Step 7: if a cross-check disagrees

Every analysis logs disagreements in its FINDINGS.md under "Verification."
`build_summary.py` collects them all into `_summary.md`.

A DISAGREE is not a bug. It means the computed number differs from the paper's quoted number
by more than the tolerance. Your options:

1. The data is right and the paper number was an error or a different basis -- report the
   corrected number and note the discrepancy.
2. The basis differs (e.g., spindle vs total connected load for rated power) -- clarify the basis and use both.
3. The data or inputs have an error -- investigate before citing.

Never silently adopt a quoted number if the data says otherwise.

---

## What order to do things on a single working session

If you have three hours and your CSV files:

1. Set CNC_DATA_DIR (30 seconds)
2. Gate test -- if it passes, proceed (5 minutes)
3. Run estimation_ladder, read FINDINGS.md (20 minutes)
4. Update MASS_REMOVED_G if you have lab records, re-run (10 minutes)
5. Run allocation, read FINDINGS.md (15 minutes)
6. Run B1_breakeven with updated energy values (5 minutes)
7. Run build_summary (1 minute)
8. Open _summary.md and check all [verify] rows are filled in

Everything else (wear_runorder, style polish, figure labels) can wait for a second session.
