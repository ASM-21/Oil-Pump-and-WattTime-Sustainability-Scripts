# Future Work

## Cleanup and handoff work

- Rename or archive scripts with version suffixes after `docs/FIGURE_INDEX.md` identifies the canonical outputs.
- Add small anonymized example datasets for WattTime-like data, CNC traces, additive traces, and OpenNX reports.
- Add one command that runs all lightweight checks without private data.
- Convert repeated WattTime credential helpers into a shared utility module.
- Move OpenNX hardcoded Windows paths to environment variables or a small config file.

## Research extensions

- Compare carbon-aware scheduling value across more regions, seasons, and operational constraints.
- Connect measured machine energy directly to WattTime scheduling scenarios for specific parts/programs.
- ~~Validate OpenNX feature-energy estimates against measured CNC program energy.~~ First pass done: see
  [`OpenNX Feature Library Draft/library_validation_findings.md`](../OpenNX%20Feature%20Library%20Draft/library_validation_findings.md).
  The placeholder library undershoots measured cavity-milling energy by ~12x and has no category at all for
  roughly a third of the part's real operations (wall/profile finishing passes). Follow-up: replace placeholder
  rows with real (dimension, energy, uuid) triples once feature dimensions are pulled from the NX part files.
- Use OpenLCA results to compare timing-based electricity benefits against broader life-cycle impacts.
- Explore operator-facing dashboards or decision aids beyond static figures.

## Portfolio/publication polish

- Add a project diagram to the root README.
- Add screenshots or sanitized example outputs for OpenLCA GUI and OpenNX reports.
- Add a concise methodology page for each final thesis/paper figure.
- Add a short limitations section explaining data licensing, external tools, and uncertainty.
