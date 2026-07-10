"""
Verification helpers shared by all EXPLORATORY projects.

Two jobs:

1. cross_check / dual-path verification. Every project must compute its headline
   number two independent ways and confirm they agree, so a confident-but-wrong
   result cannot look finished. cross_check records both values and the verdict
   to a log the project writes into its FINDINGS.

2. Smoke tests. Each project defines a smoke_test() of cheap invariants
   (energies positive, percentages in [0, 100], row counts match the expected
   operation count, no NaNs in key columns). require() raises if an invariant
   fails. A project must pass its smoke test before it writes FINDINGS.md.

These helpers are deliberately small and dependency-free beyond the stdlib.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import math


class SmokeTestFailure(AssertionError):
    """Raised when a project invariant does not hold."""


def df_to_md(df) -> str:
    """
    Render a pandas DataFrame as markdown for FINDINGS files.

    DataFrame.to_markdown requires the optional `tabulate` package, which is
    not in requirements.txt; fall back to a fenced to_string block so FINDINGS
    generation never fails on a missing pretty-printer.
    """
    try:
        return df.to_markdown(index=False)
    except ImportError:
        return "```\n" + df.to_string(index=False) + "\n```"


def require(condition: bool, message: str) -> None:
    """Assert an invariant. Use inside each project's smoke_test()."""
    if not condition:
        raise SmokeTestFailure(message)


@dataclass
class CheckLog:
    """Accumulates cross-check results for one project, then renders to markdown."""
    rows: list[dict] = field(default_factory=list)

    def cross_check(
        self,
        label: str,
        value_a: float,
        value_b: float,
        rel_tol: float = 0.02,
        note: str = "",
    ) -> bool:
        """
        Compare two independently computed values for the same quantity.

        rel_tol is the allowed relative difference (default 2 percent). Returns
        True on agreement. Always records the row; never silently passes.
        """
        if value_a == 0 and value_b == 0:
            agree = True
            rel = 0.0
        else:
            denom = max(abs(value_a), abs(value_b))
            rel = abs(value_a - value_b) / denom if denom else math.inf
            agree = rel <= rel_tol
        self.rows.append({
            "label": label,
            "path_a": value_a,
            "path_b": value_b,
            "rel_diff_pct": round(rel * 100, 3),
            "tol_pct": round(rel_tol * 100, 3),
            "verdict": "AGREE" if agree else "DISAGREE",
            "note": note,
        })
        return agree

    def check_against_expected(
        self,
        label: str,
        computed: float,
        expected: float,
        rel_tol: float = 0.05,
        note: str = "",
    ) -> bool:
        """
        Compare a computed value against a number quoted in the paper/brief.

        These quoted numbers are expectations, not ground truth. A DISAGREE here
        is a finding to surface, not an error to suppress. Default tolerance is
        looser (5 percent) than dual-path because rounding in the source is
        unknown.
        """
        return self.cross_check(
            f"[vs quoted] {label}", computed, expected, rel_tol,
            note or "quoted value is an expectation to verify, not an input",
        )

    def to_markdown(self) -> str:
        """Render the log as a markdown table for FINDINGS.md."""
        if not self.rows:
            return "_No cross-checks recorded._\n"
        header = (
            "| quantity | path A | path B | rel diff % | tol % | verdict | note |\n"
            "|---|---|---|---|---|---|---|\n"
        )
        body = "".join(
            f"| {r['label']} | {r['path_a']:.4g} | {r['path_b']:.4g} | "
            f"{r['rel_diff_pct']} | {r['tol_pct']} | {r['verdict']} | {r['note']} |\n"
            for r in self.rows
        )
        return header + body

    def any_disagreements(self) -> bool:
        return any(r["verdict"] == "DISAGREE" for r in self.rows)
