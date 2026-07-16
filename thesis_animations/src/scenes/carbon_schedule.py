"""
Chapter 3: carbon-aware scheduling.

Shows a fixed time-of-day rule firing regardless of grid conditions next
to a threshold heuristic that waits for a low-carbon window, against a
grid MOER curve for the chosen archetype.

Render:
  manim -qm carbon_schedule.py CarbonSchedule
  manim -qh carbon_schedule.py CarbonSchedule   (final quality)

Change ARCHETYPE below and re-render to produce the same scene for each
of your six grid archetypes. Drop real data into data/{archetype}.csv
(see src/utils/data_loader.py) to replace the synthetic placeholder.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from manim import *
import numpy as np
from utils.data_loader import load_moer
from utils import theme

ARCHETYPE = "caiso"          # change per render: e.g. "ercot", "pjm", "miso"
FIXED_HOUR = 9                # fixed time-of-day rule fires here
THRESHOLD_Y = 40              # MOER threshold for the adaptive rule


class CarbonSchedule(Scene):
    def construct(self):
        hours, moer, is_synthetic = load_moer(ARCHETYPE)
        moer_fn = lambda h: np.interp(h, hours, moer)

        # ---------- title ----------
        title, subtitle = theme.make_title(
            "Carbon-Aware Scheduling",
            f"Threshold vs. fixed rule — {ARCHETYPE.upper()} archetype",
        )
        self.play(Write(title))
        self.play(FadeIn(subtitle, shift=UP * 0.2))
        self.wait(0.4)
        self.play(FadeOut(title), FadeOut(subtitle))

        if is_synthetic:
            note = Text(
                "sample data — replace with WattTime export",
                font_size=16,
                color=theme.NEUTRAL,
            ).to_corner(DR, buff=0.2)
            self.add(note)

        # ---------- axes ----------
        axes = Axes(
            x_range=[0, 24, 4],
            y_range=[0, 100, 20],
            x_length=10,
            y_length=5,
            axis_config={"include_tip": False, "color": theme.NEUTRAL},
        ).to_edge(DOWN, buff=0.9)

        x_label = Text("hour of day", font_size=theme.LABEL_SIZE).next_to(
            axes.x_axis, DOWN, buff=0.3
        )
        y_label = Text("grid MOER", font_size=theme.LABEL_SIZE).rotate(90 * DEGREES)
        y_label.next_to(axes.y_axis, LEFT, buff=0.3)

        self.play(Create(axes), Write(x_label), Write(y_label))

        # ---------- MOER curve ----------
        curve = axes.plot(moer_fn, x_range=[0, 23.9, 0.1], color=theme.PRIMARY)
        curve_label = Text(
            "carbon intensity", font_size=20, color=theme.PRIMARY
        ).next_to(axes.c2p(19.5, moer_fn(19.5)), UP, buff=0.2)

        self.play(Create(curve, run_time=2.5))
        self.play(FadeIn(curve_label, shift=UP * 0.2))
        self.wait(0.3)

        # ---------- threshold line ----------
        threshold_line = DashedLine(
            axes.c2p(0, THRESHOLD_Y), axes.c2p(24, THRESHOLD_Y), color=theme.THRESHOLD
        )
        threshold_label = Text(
            "threshold", font_size=20, color=theme.THRESHOLD
        ).next_to(axes.c2p(1.5, THRESHOLD_Y), UP, buff=0.15)

        self.play(Create(threshold_line), FadeIn(threshold_label))
        self.wait(0.5)

        # ---------- fixed time-of-day rule ----------
        fixed_y = moer_fn(FIXED_HOUR)
        fixed_dot = Dot(axes.c2p(FIXED_HOUR, fixed_y), color=theme.BAD, radius=0.09)
        fixed_line = DashedLine(
            axes.c2p(FIXED_HOUR, 0), axes.c2p(FIXED_HOUR, fixed_y), color=theme.BAD
        )
        fixed_label = Text(
            f"fixed {FIXED_HOUR} AM rule", font_size=20, color=theme.BAD
        ).next_to(fixed_dot, UP, buff=0.35)

        self.play(Create(fixed_line), FadeIn(fixed_dot), Write(fixed_label))
        bad_note = Text(
            "fires into a high-carbon window", font_size=theme.ANNOTATION_SIZE, color=theme.BAD
        ).next_to(fixed_label, UP, buff=0.15)
        self.play(FadeIn(bad_note, shift=UP * 0.15))
        self.wait(0.8)
        self.play(FadeOut(bad_note))

        # ---------- threshold-triggered rule ----------
        scan_dot = Dot(axes.c2p(0, moer_fn(0)), color=theme.NEUTRAL, radius=0.07)
        self.play(FadeIn(scan_dot))

        trigger_hour = next(
            (h for h in np.arange(0, 24, 0.2) if moer_fn(h) <= THRESHOLD_Y and h > FIXED_HOUR),
            18.0,
        )

        path = axes.plot(moer_fn, x_range=[0, trigger_hour, 0.1])
        self.play(MoveAlongPath(scan_dot, path), run_time=2.0, rate_func=linear)

        trigger_y = moer_fn(trigger_hour)
        trigger_line = DashedLine(
            axes.c2p(trigger_hour, 0), axes.c2p(trigger_hour, trigger_y), color=theme.GOOD
        )
        trigger_dot = Dot(axes.c2p(trigger_hour, trigger_y), color=theme.GOOD, radius=0.09)
        trigger_label = Text(
            "threshold-triggered", font_size=20, color=theme.GOOD
        ).next_to(trigger_dot, DOWN, buff=0.35)

        self.play(
            Transform(scan_dot, trigger_dot),
            Create(trigger_line),
            Write(trigger_label),
        )
        good_note = Text(
            "waits for the low-carbon dip", font_size=theme.ANNOTATION_SIZE, color=theme.GOOD
        ).next_to(trigger_label, DOWN, buff=0.15)
        self.play(FadeIn(good_note, shift=DOWN * 0.15))
        self.wait(0.8)

        # ---------- summary ----------
        # Guard against archetypes/thresholds where the triggered point isn't
        # actually lower (e.g. no low-carbon window found before the fallback
        # hour) so the callout never claims a nonsensical negative reduction.
        if fixed_y > 0 and trigger_y < fixed_y:
            reduction_pct = round((fixed_y - trigger_y) / fixed_y * 100)
            summary_text = f"~{reduction_pct}% lower carbon intensity at execution"
        else:
            summary_text = "waits for a lower-carbon window than the fixed rule"
        summary = Text(
            summary_text,
            font_size=theme.CALLOUT_SIZE,
            weight=BOLD,
            color=theme.GOOD,
        ).to_edge(UP, buff=0.5)
        self.play(Write(summary))
        self.wait(2)
