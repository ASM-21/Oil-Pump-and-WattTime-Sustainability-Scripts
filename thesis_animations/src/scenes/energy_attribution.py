"""
Chapter 2: UUID-based operation-level energy attribution.

Shows a machining/print job as a sequence of operations, each tagged with
a UUID, synced against a power draw trace, then rolled up into per-
operation attributed energy. This is illustrative structure, not real
IAMMETER data, swap POWER_TRACE and OPERATIONS for a real logged run if
you want it to reflect an actual part.

Render:
  manim -qm energy_attribution.py EnergyAttribution
  manim -qh energy_attribution.py EnergyAttribution
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from manim import *
import numpy as np
from utils import theme

# (label, start_time_s, end_time_s, average_power_w) — replace with a real
# MTConnect/IAMMETER-derived operation table for an actual part.
OPERATIONS = [
    ("Face mill", 0, 12, 850),
    ("Rough pocket", 12, 34, 1400),
    ("Finish pass", 34, 48, 620),
    ("Drill x4", 48, 58, 950),
]


def power_trace(t):
    """Piecewise power draw with noise, standing in for a real 1 Hz log."""
    for label, start, end, avg_power in OPERATIONS:
        if start <= t < end:
            ramp = min((t - start) / 1.5, 1.0, (end - t) / 1.5) if end - t < 1.5 or t - start < 1.5 else 1.0
            return avg_power * max(ramp, 0.15) + 25 * np.sin(t * 3)
    return 60  # idle draw between/after operations


class EnergyAttribution(Scene):
    def construct(self):
        title, subtitle = theme.make_title(
            "Operation-Level Energy Attribution", "UUID-tagged power trace"
        )
        self.play(Write(title))
        self.play(FadeIn(subtitle, shift=UP * 0.2))
        self.wait(0.4)
        self.play(FadeOut(title), FadeOut(subtitle))

        total_time = OPERATIONS[-1][2]

        axes = Axes(
            x_range=[0, total_time, 10],
            y_range=[0, 1600, 400],
            x_length=10.5,
            y_length=4,
            axis_config={"include_tip": False, "color": theme.NEUTRAL},
        ).to_edge(UP, buff=1.2)

        x_label = Text("time (s)", font_size=theme.LABEL_SIZE).next_to(axes.x_axis, DOWN, buff=0.3)
        y_label = Text("power (W)", font_size=theme.LABEL_SIZE).rotate(90 * DEGREES)
        y_label.next_to(axes.y_axis, LEFT, buff=0.3)

        self.play(Create(axes), Write(x_label), Write(y_label))

        # power curve, drawn segment by segment so each op highlights in turn
        colors = [theme.PRIMARY, theme.ACCENT, theme.GOOD, theme.THRESHOLD]
        op_curves = []
        op_labels = []
        attributed_energy = []

        for i, (label, start, end, avg_power) in enumerate(OPERATIONS):
            seg = axes.plot(
                power_trace, x_range=[start, end - 0.05, 0.2], color=colors[i % len(colors)]
            )
            op_curves.append(seg)

            uuid_tag = f"op-{i+1:02d}-{'abcd1234'[i]}f2e"
            tag_text = Text(uuid_tag, font_size=16, color=colors[i % len(colors)])
            tag_text.next_to(axes.c2p((start + end) / 2, avg_power), UP, buff=0.15)
            op_labels.append(tag_text)

            energy_j = avg_power * (end - start)  # simplified rectangular estimate
            attributed_energy.append((label, energy_j))

        for seg, tag in zip(op_curves, op_labels):
            self.play(Create(seg, run_time=0.9), FadeIn(tag, shift=UP * 0.1))

        self.wait(0.5)

        # roll up into an attribution table below the plot
        rollup_title = Text(
            "attributed energy by operation", font_size=theme.SUBTITLE_SIZE
        ).next_to(axes, DOWN, buff=0.6)
        self.play(Write(rollup_title))

        rows = VGroup()
        for i, (label, energy_j) in enumerate(attributed_energy):
            row = Text(
                f"{label:<14} {energy_j/1000:.1f} kJ",
                font_size=20,
                color=colors[i % len(colors)],
                font="monospace",
            )
            rows.add(row)
        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.15)
        rows.next_to(rollup_title, DOWN, buff=0.3)

        for row in rows:
            self.play(FadeIn(row, shift=LEFT * 0.15), run_time=0.4)

        total_kj = sum(e for _, e in attributed_energy) / 1000
        total_row = Text(
            f"{'total':<14} {total_kj:.1f} kJ",
            font_size=22,
            weight=BOLD,
            font="monospace",
        )
        total_row.next_to(rows, DOWN, buff=0.25)
        underline = Line(
            total_row.get_left() + UP * 0.15, total_row.get_right() + UP * 0.15, color=theme.NEUTRAL
        )
        self.play(Create(underline), Write(total_row))
        self.wait(2)
