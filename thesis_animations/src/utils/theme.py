"""
Shared color palette and text sizing so every scene in the kit looks like
it belongs to the same deck. Change values here, not in individual scenes.
"""

from manim import *

# core palette
PRIMARY = BLUE          # curves, primary data series
GOOD = GREEN            # low-carbon / favorable outcomes
BAD = RED               # high-carbon / unfavorable outcomes
THRESHOLD = YELLOW      # decision boundaries, thresholds
NEUTRAL = GREY_B        # axes, scaffolding, inactive elements
ACCENT = "#8B5CF6"      # secondary highlight (purple), use sparingly

# font sizes, keep animations legible at 720p and up
TITLE_SIZE = 40
SUBTITLE_SIZE = 24
LABEL_SIZE = 22
ANNOTATION_SIZE = 18
CALLOUT_SIZE = 26


def make_title(text, subtitle=None):
    """Standard title card. Returns (title, subtitle_or_None) as VMobjects."""
    title = Text(text, font_size=TITLE_SIZE, weight=BOLD)
    if subtitle is None:
        return title, None
    sub = Text(subtitle, font_size=SUBTITLE_SIZE)
    sub.next_to(title, DOWN, buff=0.25)
    return title, sub
