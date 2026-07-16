"""
Supporting scene: materials vs. manufacturing-electricity share of embodied
carbon, animated as a counting bar buildup. Numbers below reflect the oil
pump case study finding (materials 97.9%, manufacturing electricity 2.1%),
update MATERIALS_PCT if you re-run this for a different part.

Render:
  manim -qm material_electricity_split.py MaterialElectricitySplit
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from manim import *
from utils import theme

MATERIALS_PCT = 97.9
ELECTRICITY_PCT = 100 - MATERIALS_PCT


class MaterialElectricitySplit(Scene):
    def construct(self):
        title, subtitle = theme.make_title(
            "Where the Carbon Actually Comes From",
            "embodied carbon, materials vs. manufacturing electricity",
        )
        self.play(Write(title))
        self.play(FadeIn(subtitle, shift=UP * 0.2))
        self.wait(0.5)
        self.play(FadeOut(title), FadeOut(subtitle))

        chart_width = 8.0
        bar_height = 0.9

        materials_bar = Rectangle(
            width=0.01, height=bar_height, color=theme.PRIMARY, fill_color=theme.PRIMARY, fill_opacity=0.85
        )
        electricity_bar = Rectangle(
            width=0.01, height=bar_height, color=theme.ACCENT, fill_color=theme.ACCENT, fill_opacity=0.85
        )

        materials_bar.align_on_border(LEFT, buff=1.5).shift(UP * 1)
        electricity_bar.align_on_border(LEFT, buff=1.5).shift(DOWN * 0.5)

        materials_label = Text("materials", font_size=theme.LABEL_SIZE)
        materials_label.next_to(materials_bar, LEFT, buff=0.3)
        electricity_label = Text("mfg. electricity", font_size=theme.LABEL_SIZE)
        electricity_label.next_to(electricity_bar, LEFT, buff=0.3)

        self.play(FadeIn(materials_label), FadeIn(electricity_label))

        materials_target = Rectangle(
            width=chart_width * (MATERIALS_PCT / 100),
            height=bar_height,
            color=theme.PRIMARY,
            fill_color=theme.PRIMARY,
            fill_opacity=0.85,
        )
        materials_target.align_to(materials_bar, LEFT).align_to(materials_bar, UP)

        electricity_target = Rectangle(
            width=max(chart_width * (ELECTRICITY_PCT / 100), 0.15),
            height=bar_height,
            color=theme.ACCENT,
            fill_color=theme.ACCENT,
            fill_opacity=0.85,
        )
        electricity_target.align_to(electricity_bar, LEFT).align_to(electricity_bar, UP)

        pct_tracker_m = ValueTracker(0)
        pct_tracker_e = ValueTracker(0)

        materials_pct_label = always_redraw(
            lambda: Text(f"{pct_tracker_m.get_value():.1f}%", font_size=22, weight=BOLD)
            .next_to(materials_target, RIGHT, buff=0.25)
        )
        electricity_pct_label = always_redraw(
            lambda: Text(f"{pct_tracker_e.get_value():.1f}%", font_size=22, weight=BOLD)
            .next_to(electricity_target, RIGHT, buff=0.25)
        )

        self.add(materials_pct_label, electricity_pct_label)

        self.play(
            Transform(materials_bar, materials_target),
            pct_tracker_m.animate.set_value(MATERIALS_PCT),
            run_time=2.2,
        )
        self.play(
            Transform(electricity_bar, electricity_target),
            pct_tracker_e.animate.set_value(ELECTRICITY_PCT),
            run_time=1.4,
        )
        self.wait(0.5)

        takeaway = Text(
            "process-level carbon accounting misses the bigger lever",
            font_size=theme.ANNOTATION_SIZE,
            color=theme.NEUTRAL,
        ).to_edge(DOWN, buff=0.6)
        self.play(FadeIn(takeaway, shift=UP * 0.15))
        self.wait(2)
