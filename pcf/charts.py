"""Figure generation for the PCF report.

Every figure is written as a PNG at 200 dpi and sized for the A4 portrait text
column of the generated report.  All functions return the path they wrote.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyArrowPatch, Rectangle

from .model import PCFModel
from .params import KG_PER_TONNE

SCOPE_COLORS = {
    "scope1": "#b5533c",
    "scope2": "#2f6f9f",
    "scope3": "#6f8f5a",
}
SCOPE_LABELS = {
    "scope1": "Scope 1 (direct)",
    "scope2": "Scope 2 (grid electricity)",
    "scope3": "Scope 3 (upstream NG)",
}
TOTAL_COLOR = "#33383d"
ACCENT = "#c9a227"
GRID_COLOR = "#d5d8dc"


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 200,
            "savefig.dpi": 200,
            "font.family": "DejaVu Sans",
            "font.size": 8.5,
            "axes.titlesize": 10,
            "axes.labelsize": 8.5,
            "axes.edgecolor": "#aab0b6",
            "axes.linewidth": 0.7,
            "axes.grid": True,
            "grid.color": GRID_COLOR,
            "grid.linewidth": 0.6,
            "legend.frameon": False,
            "xtick.color": "#3d4348",
            "ytick.color": "#3d4348",
        }
    )


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


# --------------------------------------------------------------- flowsheet
def process_flow_diagram(model: PCFModel, path: Path) -> Path:
    """Cradle-to-gate process flow diagram with stage emissions."""
    _style()
    p = model.params
    f = model.flows
    stages = {s.key: s for s in model.stages()}

    fig, ax = plt.subplots(figsize=(7.1, 3.9))
    ax.set_axis_off()
    ax.set_xlim(0, 10.4)
    ax.set_ylim(0, 4.2)

    boxes = [
        (0.10, "Natural gas\nextraction &\ntransport", "ng_extraction"),
        (2.60, "Methanol\nsynthesis\n(SMR/ATR)", "methanol"),
        (5.10, "Methanol-to-\nolefins &\nseparation", "mto"),
        (7.60, "HDPE\npolymerisation\n& finishing", "hdpe"),
    ]
    width, height, y0 = 1.75, 1.35, 2.05

    for x, label, key in boxes:
        ax.add_patch(
            Rectangle(
                (x, y0),
                width,
                height,
                facecolor="#f4f6f8",
                edgecolor="#4a5259",
                linewidth=1.0,
                zorder=2,
            )
        )
        ax.text(
            x + width / 2,
            y0 + height / 2,
            label,
            ha="center",
            va="center",
            zorder=3,
            fontsize=8.5,
            color="#20262b",
        )
        stage = stages[key]
        ax.text(
            x + width / 2,
            y0 - 0.28,
            f"Scope 1 {stage.scope1:,.0f}",
            ha="center",
            va="top",
            fontsize=7.4,
            color=SCOPE_COLORS["scope1"],
        )
        ax.text(
            x + width / 2,
            y0 - 0.55,
            f"Scope 2 {stage.scope2:,.0f}",
            ha="center",
            va="top",
            fontsize=7.4,
            color=SCOPE_COLORS["scope2"],
        )
        ax.text(
            x + width / 2,
            y0 - 0.82,
            f"Scope 3 {stage.scope3:,.0f}",
            ha="center",
            va="top",
            fontsize=7.4,
            color=SCOPE_COLORS["scope3"],
        )
        ax.text(
            x + width / 2,
            y0 + height + 0.12,
            f"cumulative {stage.cumulative:,.0f} kg CO2e",
            ha="center",
            va="bottom",
            fontsize=7.0,
            color="#6b7378",
        )

    streams = [
        (0.10 + width, 2.60, f"{f.natural_gas_t:.3f} t\nNG"),
        (2.60 + width, 5.10, f"{f.methanol_t:.3f} t\nCH3OH"),
        (5.10 + width, 7.60, f"{f.ethylene_t:.3f} t\nC2H4"),
    ]
    ymid = y0 + height / 2
    for x_start, x_end, label in streams:
        ax.add_patch(
            FancyArrowPatch(
                (x_start, ymid),
                (x_end, ymid),
                arrowstyle="-|>",
                mutation_scale=11,
                linewidth=1.1,
                color="#20262b",
                zorder=1,
            )
        )
        ax.text(
            (x_start + x_end) / 2,
            ymid + 0.30,
            label,
            ha="center",
            va="bottom",
            fontsize=6.9,
            color="#20262b",
            linespacing=1.15,
        )

    ax.add_patch(
        FancyArrowPatch(
            (7.60 + width,
            ymid),
            (10.30, ymid),
            arrowstyle="-|>",
            mutation_scale=11,
            linewidth=1.1,
            color="#20262b",
        )
    )
    ax.text(
        10.28,
        ymid + 0.30,
        f"{f.hdpe_t:.3f} t\nHDPE resin",
        ha="right",
        va="bottom",
        fontsize=6.9,
        linespacing=1.15,
    )

    ax.text(
        0.10,
        3.92,
        f"Cradle-to-gate PCF  |  functional unit: {f.hdpe_t:.1f} t HDPE resin  |  "
        f"total {model.total_kg:,.0f} kg CO2e ({model.total_t:.2f} t CO2e/t HDPE)",
        fontsize=8.6,
        color="#20262b",
    )
    ax.text(
        0.10,
        0.28,
        f"Stage emissions in kg CO2e per functional unit; "
        f"grid factor {p.ef_grid:.3f} kg CO2e/kWh; "
        f"upstream NG factor {p.ef_ng_upstream:.3f} kg CO2e/kg.",
        fontsize=7.2,
        color="#6b7378",
    )
    return _save(fig, Path(path))


# ----------------------------------------------------------------- waterfall
def waterfall(model: PCFModel, path: Path) -> Path:
    """Cumulative build-up of the footprint, stage by stage, split by scope."""
    _style()
    stages = list(model.stages())
    fig, ax = plt.subplots(figsize=(7.1, 3.6))

    cumulative = 0.0
    for i, stage in enumerate(stages):
        bottom = cumulative
        for key, value in (
            ("scope3", stage.scope3),
            ("scope2", stage.scope2),
            ("scope1", stage.scope1),
        ):
            if value <= 0:
                continue
            ax.bar(
                i,
                value,
                bottom=bottom,
                width=0.62,
                color=SCOPE_COLORS[key],
                edgecolor="white",
                linewidth=0.6,
                zorder=3,
            )
            bottom += value
        cumulative += stage.total
        ax.text(
            i,
            cumulative + 40,
            f"+{stage.total:,.0f}",
            ha="center",
            va="bottom",
            fontsize=8,
            color="#20262b",
        )
        if i < len(stages) - 1:
            ax.plot(
                [i + 0.31, i + 1 - 0.31],
                [cumulative, cumulative],
                color="#8b9298",
                linestyle=(0, (3, 2)),
                linewidth=0.9,
                zorder=2,
            )

    ax.bar(
        len(stages),
        cumulative,
        width=0.62,
        color=TOTAL_COLOR,
        zorder=3,
    )
    ax.text(
        len(stages),
        cumulative + 40,
        f"{cumulative:,.0f} kg CO2e\n{cumulative / KG_PER_TONNE:.2f} t CO2e/t HDPE",
        ha="center",
        va="bottom",
        fontsize=8.4,
        color="#20262b",
    )

    short = {
        "ng_extraction": "Natural gas\nextraction",
        "methanol": "Methanol\nsynthesis",
        "mto": "MTO &\nseparation",
        "hdpe": "HDPE\npolymerisation",
    }
    labels = [short[s.key] for s in stages] + ["Total"]
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=7.6, linespacing=1.25)
    ax.set_ylabel("kg CO2e per functional unit")
    ax.set_ylim(0, cumulative * 1.22)
    ax.set_title("Footprint build-up by life-cycle stage")
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=SCOPE_COLORS[k]) for k in SCOPE_COLORS
    ]
    ax.legend(
        handles,
        [SCOPE_LABELS[k] for k in SCOPE_COLORS],
        loc="upper left",
        fontsize=7.2,
    )
    ax.grid(axis="x", visible=False)
    return _save(fig, Path(path))


# -------------------------------------------------------------- hotspot bars
def hotspot_bars(model: PCFModel, path: Path) -> Path:
    """Stacked stage contributions with share-of-total annotations."""
    _style()
    frame = model.hotspot_frame()
    fig, ax = plt.subplots(figsize=(7.1, 2.9))

    y = np.arange(len(frame))[::-1]
    left = np.zeros(len(frame))
    for key, column in (
        ("scope1", "scope1_kg"),
        ("scope2", "scope2_kg"),
        ("scope3", "scope3_kg"),
    ):
        values = frame[column].to_numpy()
        ax.barh(
            y,
            values,
            left=left,
            height=0.58,
            color=SCOPE_COLORS[key],
            edgecolor="white",
            linewidth=0.6,
            label=SCOPE_LABELS[key],
        )
        left = left + values

    for yi, (total, share) in zip(y, zip(frame["total_kg"], frame["share_pct"])):
        ax.text(
            total + 60,
            yi,
            f"{total:,.0f} kg  ({share:.1f}%)",
            va="center",
            fontsize=7.8,
            color="#20262b",
        )

    ax.set_yticks(y)
    ax.set_yticklabels(frame["stage"], fontsize=7.8)
    ax.set_xlabel("kg CO2e per functional unit")
    ax.set_xlim(0, max(frame["total_kg"]) * 1.42)
    ax.set_title("Hotspot breakdown by stage and scope")
    ax.legend(loc="lower right", fontsize=7.2)
    ax.grid(axis="y", visible=False)
    return _save(fig, Path(path))


# ----------------------------------------------------------------- scenarios
def scenario_chart(
    sweep: pd.DataFrame,
    scenarios: pd.DataFrame,
    path: Path,
) -> Path:
    """Grid-decarbonisation curve (left) and scenario comparison (right)."""
    _style()
    fig, (ax_left, ax_right) = plt.subplots(
        1, 2, figsize=(7.1, 3.3), gridspec_kw={"width_ratios": [1.25, 1.0]}
    )

    ax_left.plot(
        sweep["ef_grid"],
        sweep["pcf_t"],
        color=TOTAL_COLOR,
        linewidth=1.6,
        label="Total footprint",
    )
    ax_left.fill_between(
        sweep["ef_grid"],
        sweep["scope1_kg"] / KG_PER_TONNE + sweep["scope3_kg"] / KG_PER_TONNE,
        sweep["pcf_t"],
        color=SCOPE_COLORS["scope2"],
        alpha=0.18,
        label="Grid-linked portion",
    )

    marks = {
        "baseline": 0.475,
        "mid_transition": 0.200,
        "renewable_grid": 0.0,
        "green_h2_syngas": 0.0,
    }
    for key, ef in marks.items():
        row = sweep.iloc[(sweep["ef_grid"] - ef).abs().argmin()]
        ax_left.plot([row["ef_grid"]], [row["pcf_t"]], "o", color=ACCENT, markersize=4.5)
    for _, row in scenarios.iterrows():
        if pd.isna(row.get("spec_reference_t")) or row["scenario"] not in marks:
            continue
        ax_left.plot(
            [marks[row["scenario"]]],
            [row["spec_reference_t"]],
            "x",
            color="#b5533c",
            markersize=5.5,
            markeredgewidth=1.3,
        )
    ax_left.annotate(
        "spec 6.07",
        (0.475, 6.07),
        textcoords="offset points",
        xytext=(2, -13),
        fontsize=6.8,
        color="#b5533c",
    )
    ax_left.annotate(
        "spec 4.61",
        (0.200, 4.61),
        textcoords="offset points",
        xytext=(-34, 9),
        fontsize=6.8,
        color="#b5533c",
    )
    ax_left.annotate(
        "spec 1.82",
        (0.0, 1.82),
        textcoords="offset points",
        xytext=(7, -3),
        fontsize=6.8,
        color="#b5533c",
        annotation_clip=False,
    )
    ax_left.set_xlabel("Grid emission factor (kg CO2e/kWh)")
    ax_left.set_ylabel("t CO2e per t HDPE")
    ax_left.set_title("Grid decarbonisation response")
    ax_left.legend(loc="upper left", fontsize=7.0)
    ax_left.set_xlim(-0.01, 0.6)

    plot = scenarios.copy()
    colors = ["#b5533c" if s == "baseline" else "#2f6f9f" for s in plot["scenario"]]
    ypos = np.arange(len(plot))[::-1]
    ax_right.barh(ypos, plot["pcf_t"], height=0.6, color=colors)
    for yi, row in zip(ypos, plot.itertuples()):
        ax_right.text(
            row.pcf_t + 0.08,
            yi - 0.16,
            f"{row.pcf_t:.2f}",
            va="center",
            fontsize=7.4,
            color="#20262b",
        )
        if not pd.isna(row.spec_reference_t):
            ax_right.plot(
                [row.spec_reference_t],
                [yi],
                "x",
                color="#b5533c",
                markersize=6,
                markeredgewidth=1.4,
            )
    ax_right.set_yticks(ypos)
    ax_right.set_yticklabels(
        [s.replace("_", " ") for s in plot["scenario"]], fontsize=7.4
    )
    ax_right.set_xlabel("t CO2e/t HDPE")
    ax_right.set_xlim(0, max(plot["pcf_t"]) * 1.25)
    ax_right.set_title("Scenario comparison (x = spec value)")
    ax_right.grid(axis="y", visible=False)
    fig.tight_layout()
    return _save(fig, Path(path))


# ------------------------------------------------------------------- tornado
def tornado_chart(tornado_frame: pd.DataFrame, path: Path, central: float) -> Path:
    """One-at-a-time +/-10 % parameter perturbation ranking."""
    _style()
    frame = tornado_frame.iloc[::-1]
    fig, ax = plt.subplots(figsize=(7.1, 3.4))
    y = np.arange(len(frame))

    low = frame["pcf_low_t"].to_numpy()
    high = frame["pcf_high_t"].to_numpy()
    ax.barh(y, low - central, left=central, height=0.6, color="#7fa8c9")
    ax.barh(y, high - central, left=central, height=0.6, color="#b5533c", alpha=0.85)
    ax.axvline(central, color=TOTAL_COLOR, linewidth=1.1)

    for yi, row in zip(y, frame.itertuples()):
        ax.text(
            min(row.pcf_low_t, row.pcf_high_t) - 0.04,
            yi,
            f"{min(row.pcf_low_t, row.pcf_high_t):.2f}",
            va="center",
            ha="right",
            fontsize=7.0,
            color="#3d4348",
        )
        ax.text(
            max(row.pcf_low_t, row.pcf_high_t) + 0.04,
            yi,
            f"{max(row.pcf_low_t, row.pcf_high_t):.2f}",
            va="center",
            ha="left",
            fontsize=7.0,
            color="#3d4348",
        )

    ax.set_yticks(y)
    ax.set_yticklabels(frame["label"], fontsize=7.6)
    ax.set_xlabel("t CO2e/t HDPE")
    lo = min(frame["pcf_low_t"].min(), central) - 0.5
    hi = max(frame["pcf_high_t"].max(), central) + 0.5
    ax.set_xlim(lo, hi)
    ax.set_title("Parameter sensitivity, one-at-a-time +/-10 %")
    ax.grid(axis="y", visible=False)
    return _save(fig, Path(path))


def build_all(
    model: PCFModel,
    outdir: Path,
    sweep: pd.DataFrame,
    scenarios: pd.DataFrame,
    tornado_frame: pd.DataFrame,
) -> dict[str, Path]:
    """Generate the full figure set and return a name -> path mapping."""
    outdir = Path(outdir)
    return {
        "process_flow": process_flow_diagram(model, outdir / "process_flow.png"),
        "waterfall": waterfall(model, outdir / "waterfall.png"),
        "hotspot": hotspot_bars(model, outdir / "hotspot_bars.png"),
        "scenarios": scenario_chart(sweep, scenarios, outdir / "scenarios.png"),
        "tornado": tornado_chart(tornado_frame, outdir / "tornado.png", model.total_t),
    }
