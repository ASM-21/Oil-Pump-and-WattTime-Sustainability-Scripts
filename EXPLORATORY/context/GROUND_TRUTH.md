# Ground truth: facts, numbers to verify, and hard rules

## Hard rules (do not violate)
1. **No new experimental data.** Use only what is already in this repo. If something needed is missing, log it to `_data_gaps.md` and park the project; never fabricate a stand-in. The only sanctioned synthetic step is superposition of *real measured* signals in a disaggregation exploration, labeled synthetic everywhere it appears.
2. **Prohibited claim:** never compute or state a specific numeric deviation multiplier against the ecoinvent aluminum-milling dataset (e.g. "N times higher than ecoinvent"). The owner's thesis position is that database aggregation *masks* operation-level variation; it does not claim a specific multiplier. Allowed framing: measured within-product and between-operation spread in specific energy, on its own terms. A "48x" figure appeared in old drafts and is explicitly wrong; do not reintroduce it.
3. **Additive only.** Write only inside `EXPLORATORY/` and `EXPLORATORY/shared/adapters.py`. Read the rest of the repo freely. The existing paper pipeline must still run untouched.
4. **Verify, don't trust, quoted numbers.** Every number in these context docs is an *expectation to check against the data*, not an input. Disagreements are findings to report, not to suppress or silently adopt.
5. **No em dashes** in any prose written for the owner or their advisors (FINDINGS, summaries). House style preference.

## Numbers to verify against the data (expectations, not inputs)
| Quantity | Quoted value | Note |
|---|---|---|
| Fleet average operating power (CNC) | ~1,376 W | regression slope; recompute from data |
| Homing / non-productive share of CNC energy | ~11.7% | within-program repositioning |
| Lid energy as fraction of body energy | 67.7% | the mass-vs-energy decoupling seed |
| Operations passing Shapiro-Wilk normality | 40 of 45 | reconcile the 45 vs 49 count |
| Distinct tracked operations | 45 vs 49 | sources disagree; settle from data, encode once in adapter |
| Replicate runs per program | 16 to 27 | confirm actual counts |
| MTConnect downtime data exclusion | ~20% | confirm which runs excluded; match the paper's inclusion set |

## Machine specifications (for the estimation-ladder / utilization-factor work)
- **CNC:** Hurco VMX30Ui machining center. Spindle rated 18 hp ≈ **13.4 kW** at 12,000 rpm (confirmed from Hurco product literature). For the utilization factor u = mean/rated, decide explicitly between spindle rating and **total connected load** (the latter is larger and only readable from the machine's electrical plate, which the owner may or may not be able to photograph). Parameterize rated power so either can be used; report which.
- **FDM:** Ultimaker 2+ Extended, rated ~**221 W**, measured draw ~200 W. Gives u ≈ 0.9, the contrast point against the CNC's u ≈ 0.10.

## Three inputs a reviewer could actually challenge (get these right)
1. The rated-power basis (spindle vs connected load) behind any utilization or estimation-error figure.
2. The measured average power (recompute from data, do not quote the slide).
3. The body/lid mass basis: stock vs finished mass are inconsistent in old drafts (72% vs 84% lighter). Pick one basis, use it everywhere, state it.

## Data expected in this repo (confirm during discovery)
Raw 1 Hz power streams (CNC IAMMETER, AM); UUID/MTConnect event logs; processed per-operation/per-run energy tables; program-structure and BOM tables; WattTime MOER parquet (from the thesis scheduling work, may or may not be co-located); OpenLCA/olca integration code; the `manufacturing_lca_toolkit` and `manufacturing_energy` packages (feature_library, carbon_passport, training_table pipeline).
