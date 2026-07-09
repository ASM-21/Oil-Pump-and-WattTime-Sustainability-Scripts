# signature_mining

Mines the raw 1 Hz power waveforms that the energy totals throw away, to test
the retrofit claim: how much operation-level attribution survives when the
CAM/UUID channel is removed?

Three analyses, all machine-agnostic (built on `shared/segmentation.py` and
`shared/signatures.py`):

1. **Boundary recovery** - binary-segmentation changepoints from power alone,
   scored against UUID transition boundaries (precision/recall/F1).
2. **Machine-state decomposition** - off / idle / positioning / cutting
   shares of time and of energy, per program file.
3. **Operation fingerprinting** - nearest-centroid over nine waveform
   features, leave-one-run-out; plus cross-part transfer (train on body,
   classify lid at category level), the honest generalization test.

## Run

    python EXPLORATORY/signature_mining/run.py

Always produces the fixture-verified result set (tag `fixture`, known truth,
full real pipeline). If `CNC_DATA_DIR` points at the real Al6061 folder the
same analyses also run there (tag `measured`).

## Outputs

- `outputs/boundary_recovery_<tag>.csv`, `state_shares_<tag>.csv`,
  `signature_features_<tag>.csv`
- `outputs/boundary_overlay_<tag>.(png|pdf)` - trace with true vs detected
  boundaries; the paper's retrofit exhibit
- `outputs/state_shares_<tag>.(png|pdf)`
- `FINDINGS.md` - regenerated each run

## How to extend

- Sweep detector penalty/min_seg_len for an ROC-style recall/precision curve.
- Add a rejection threshold on centroid distance to get an open-set
  classifier (flag unseen operations instead of misassigning them).
- Apply the state decomposition to the FDM stream once AM_DATA_DIR loading
  is wired in `shared/adapters.py`.
