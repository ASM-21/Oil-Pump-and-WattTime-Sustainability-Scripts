# Verifying the "best-guess" olca-ipc response shapes

`tools/lcia.py` and `tools/inventory.py` both carry `NOTE:`/`§14`-style
comments admitting that three response shapes were never confirmed against
a live OpenLCA IPC connection: `get_impact_contributions`'s contribution
entries, `get_grouped_impact_results`'s group entries, and `get_total_flows`'s
`EnviFlowValue` entries. No OpenLCA desktop is available in this environment
either, so a live probe wasn't possible here -- but the shapes are public API,
documented outside any specific user's database, so they were checked against
that instead.

## What was checked, and how

`WebFetch` is blocked in this sandbox for every host tried (the pdoc site,
`raw.githubusercontent.com`, `pypi.org` all returned 403), so this used
`WebSearch` snippets only, which surfaced partial but usable information from
`olca-ipc`'s published API docs.

**`get_impact_contributions` (tools/lcia.py) -- confirmed wrong, fixed.**
Search results twice independently described `ContributionItem`'s fields as:
`item: Optional[schema.Ref]`, `amount: Optional[float]`, `share`, `rest`,
`unit`. There is no `tech_flow` field. The code was reading
`entry.tech_flow.provider.{name,id}`, which does not exist on this class --
it would have silently returned `process="unknown"`, `process_id=None` for
every contribution row, while `amount` (a real top-level field) came through
fine. That matters because the module's own defensive guard
(`_all_amounts_none`) only checks `amount`, so it would never have fired for
this specific bug -- the exact silent-failure mode the guard was written to
catch, missed because the guard checked the one field that happened to still
work. Fixed to read `.item` directly, kept `tech_flow.provider` as a
fallback, and added `_all_none(out, "process_id")` to the guard so an
identity-field-only failure is caught even if a future shape change again
leaves `amount` intact.

**`get_grouped_impact_results` and `get_total_flows` -- still unverified.**
Search did not surface the field names for the grouped-result class or for
`EnviFlowValue`. These remain exactly as risky as the README already said.
Do not assume they are fine because the contribution-shape bug got fixed --
they were not checked.

## What this doesn't prove

This is documentation-based verification, not a live-data test. `olca-ipc`
versions could differ from what's publicly documented, and the fallback path
is there specifically because of that uncertainty. The integration test
`test_get_impact_contributions_oil_pump` (`tests/test_tools.py`) is still the
real canary -- run it against a live OpenLCA IPC connection before trusting
this fix in production, and if it fails, `print(repr(contribs[0]))` as the
existing error message already suggests.
