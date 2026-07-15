# data/

Drop one CSV per grid archetype here, named to match the `ARCHETYPE`
constant in `src/scenes/carbon_schedule.py` (lowercase, e.g. `ercot.csv`).

## Schema

```
hour,moer
0,48
1,45
...
23,52
```

- `hour`: 0-24, doesn't need to be every integer hour, `data_loader.py`
  interpolates.
- `moer`: your marginal operating emissions rate value, any consistent
  unit. If you're pulling from WattTime, export the daily (or averaged)
  MOER series for the representative day you used in the thesis.

`caiso.csv` is included as a real example of the schema (values are
illustrative, not WattTime data). If a requested archetype has no CSV,
`data_loader.py` falls back to a synthetic placeholder curve so scenes
still render.
