"""
Shared plotting style for all EXPLORATORY projects.

One import gives every figure the same look, sized and styled for an ASME
journal manuscript: no reliance on color to carry meaning, readable at
single-column width, vector-friendly. Import and call once at the top of any
plotting script:

    from EXPLORATORY.shared.style import apply_style, COLORS, save_fig
    apply_style()

Then build figures normally and finish with save_fig(fig, "outputs/myfig").
save_fig writes both a .png (for quick viewing) and a .pdf (for the paper).
"""

from __future__ import annotations
import matplotlib as mpl
import matplotlib.pyplot as plt

# Colorblind-safe qualitative palette (Okabe-Ito). Use these in order.
# Figures must remain interpretable in grayscale, so also vary marker/linestyle,
# never color alone, when a distinction matters for the paper.
COLORS = [
    "#000000",  # black
    "#E69F00",  # orange
    "#56B4E9",  # sky blue
    "#009E73",  # bluish green
    "#CC79A7",  # reddish purple
    "#0072B2",  # blue
    "#D55E00",  # vermillion
    "#F0E442",  # yellow
]

MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]
LINESTYLES = ["-", "--", "-.", ":"]


def apply_style() -> None:
    """Set global rcParams. Call once per script before plotting."""
    mpl.rcParams.update({
        "figure.figsize": (3.5, 2.6),      # single-column default, inches
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "font.size": 8,
        "axes.titlesize": 9,
        "axes.labelsize": 8,
        "legend.fontsize": 7,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "font.family": "serif",            # matches ASME body text
        "mathtext.fontset": "dejavuserif",
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.linewidth": 0.5,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "lines.linewidth": 1.2,
        "lines.markersize": 4,
        "axes.prop_cycle": mpl.cycler(color=COLORS),
    })


def save_fig(fig, path_stem: str) -> None:
    """Save a figure as both .png and .pdf. path_stem has no extension."""
    for ext in ("png", "pdf"):
        fig.savefig(f"{path_stem}.{ext}")
    plt.close(fig)
