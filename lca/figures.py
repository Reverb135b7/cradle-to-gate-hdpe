"""Figures for the LCA report and presentation (matplotlib, Agg)."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyArrowPatch, Rectangle

from pcf.model import PCFModel
from pcf.params import ModelParams

from .impact import ImpactResult
from .inventory import stage_frame

INK = "#20262b"
MUTED = "#6b7378"
RULE = "#c8ced4"
SCOPE1 = "#b5533c"
SCOPE2 = "#2f6f9f"
SCOPE3 = "#6f8f5a"
ACCENT = "#c9a227"
BASIS_COLORS = {
    "evidence": "#2f6f9f",
    "scenario": "#c9a227",
    "method": "#6f8f5a",
    "judgement": "#9a9a9a",
}


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
            "grid.color": "#e2e5e8",
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


# ------------------------------------------------------------- boundary diagram
def boundary_diagram(model: PCFModel, path: Path) -> Path:
    """Functional-unit and system-boundary diagram, with exclusions shown."""
    _style()
    p = model.params
    f = model.flows
    stages = {s.key: s for s in model.stages()}

    fig, ax = plt.subplots(figsize=(10.6, 5.0))
    ax.set_axis_off()
    ax.set_xlim(0, 105)
    ax.set_ylim(0, 48)

    # system boundary
    ax.add_patch(
        Rectangle((3, 6), 85, 37, fill=False, edgecolor=INK, lw=1.2, ls=(0, (6, 3)))
    )
    ax.text(3, 44.4, "SYSTEM BOUNDARY  ·  cradle-to-gate", fontsize=8, color=INK,
            fontweight="bold", va="bottom")

    boxes = [
        ("Natural gas\nextraction &\ntransport", 5, "#eef1f3"),
        ("Methanol\nsynthesis\n(SMR/ATR)", 26, "#e8edf1"),
        ("Methanol-to-\nolefins &\nseparation", 47, "#eef1f3"),
        ("HDPE poly-\nmerisation &\npelletising", 68, "#e8edf1"),
    ]
    y0, h, w = 20, 9, 14
    centers = []
    for label, x, colour in boxes:
        ax.add_patch(Rectangle((x, y0), w, h, facecolor=colour, edgecolor="#7f8b95", lw=0.8))
        ax.text(x + w / 2, y0 + h / 2, label, ha="center", va="center", fontsize=7.2,
                color=INK, linespacing=1.25)
        centers.append(x + w / 2)

    # chain flows
    chain = [
        (5 + w, 26, f"{f.natural_gas_t:,.3f} t NG"),
        (26 + w, 47, f"{f.methanol_t:,.3f} t MeOH"),
        (47 + w, 68, f"{f.ethylene_t:,.3f} t C2H4"),
    ]
    for x_start, x_end, label in chain:
        ax.add_patch(
            FancyArrowPatch((x_start + 0.3, y0 + h / 2), (x_end - 0.3, y0 + h / 2),
                            arrowstyle="-|>", mutation_scale=9, lw=1.0, color="#3d4348")
        )
        ax.text((x_start + x_end) / 2, y0 + h / 2 + 2.0, label, ha="center", va="bottom",
                fontsize=6.4, color="#3d4348",
                bbox=dict(facecolor="white", edgecolor="none", pad=0.6))

    # product across the gate
    ax.add_patch(
        FancyArrowPatch((68 + w + 0.3, y0 + h / 2), (91.5, y0 + h / 2),
                        arrowstyle="-|>", mutation_scale=9, lw=1.2, color=INK)
    )
    ax.text(90.4, 15.0, "1,000 kg HDPE\nresin at gate", ha="left", va="bottom",
            fontsize=6.8, color=INK, fontweight="bold", linespacing=1.25)
    ax.plot([88.4, 88.4], [12, 34], color=INK, lw=0.9, ls=":")
    ax.text(88.4, 10.6, "gate", ha="center", fontsize=6.8, color=INK)

    # electricity bus
    ax.plot([7, 80], [36.2, 36.2], color=SCOPE2, lw=1.3)
    ax.text(7, 37.5, f"Grid electricity  {f.methanol_t * p.methanol_kwh_per_t + f.ethylene_t * p.mto_kwh_per_t * p.mto_burden_share + f.hdpe_t * p.hdpe_kwh_per_t:,.0f} kWh  ·  0.475 kg CO2e/kWh",
            fontsize=6.6, color=SCOPE2, va="bottom")
    for x, kwh in zip(
        centers,
        [
            0.0,
            p.methanol_kwh_per_t * f.methanol_t,
            p.mto_kwh_per_t * f.ethylene_t * p.mto_burden_share,
            p.hdpe_kwh_per_t * f.hdpe_t,
        ],
    ):
        ax.plot([x, x], [36.2, y0 + h], color=SCOPE2, lw=0.7, ls=(0, (2, 2)))
        if kwh:
            ax.text(x + 1.2, 33.6, f"{kwh:,.0f}", fontsize=5.8, color=SCOPE2, rotation=0,
                    bbox=dict(facecolor="white", edgecolor="none", pad=0.4))

    # co-monomer input (kept left of the HDPE electricity drop)
    ax.add_patch(
        FancyArrowPatch((70.2, 34.4), (70.2, y0 + h + 0.2), arrowstyle="-|>", mutation_scale=8,
                        lw=0.8, color="#7a5aa0")
    )
    ax.text(69.8, 31.0, f"co-monomer {f.comonomer_t * 1000:,.0f} kg", fontsize=5.8,
            color="#7a5aa0", ha="right")

    # emissions by stage
    for x, key in zip(centers, ("ng_extraction", "methanol", "mto", "hdpe")):
        s = stages[key]
        ax.text(x, y0 - 2.2, f"{s.total:,.0f} kg CO2e", ha="center", fontsize=6.8,
                fontweight="bold", color=INK)
        parts = []
        if s.scope1:
            parts.append(f"S1 {s.scope1:,.0f}")
        if s.scope2:
            parts.append(f"S2 {s.scope2:,.0f}")
        if s.scope3:
            parts.append(f"S3 {s.scope3:,.0f}")
        ax.text(x, y0 - 5.6, "  ".join(parts), ha="center", fontsize=5.8, color=MUTED)
        ax.plot([x, x], [y0 - 0.2, y0 - 1.0], color="#9aa4ac", lw=0.7)

    ax.text(3, 3.4,
            "Functional unit: 1,000 kg pelletised HDPE resin at the gate  ·  all quantities per functional unit  ·  "
            "grid factor 0.475 kg CO2e/kWh",
            fontsize=6.4, color=MUTED)

    # exclusions panel
    ex = (
        "NOT INVENTORIED / EXCLUDED\n\n"
        "Packaging\n"
        "Outbound transport\n"
        "Use phase\n"
        "End-of-life & recycling\n"
        "Water supply & wastewater\n"
        "Catalysts & adsorbents\n"
        "Capital goods\n\n"
        "These are outside the declared\n"
        "cradle-to-gate boundary and are\n"
        "not part of the 6.07 t result."
    )
    ax.text(93, 40, ex, fontsize=5.9, color=MUTED, va="top", linespacing=1.5)

    return _save(fig, path)


# ------------------------------------------------------------------ contribution
def gwp_contribution(model: PCFModel, path: Path) -> Path:
    _style()
    frame = stage_frame(model.params)
    frame = frame[frame["stage_key"] != "total"]
    labels = ["NG extraction", "Methanol", "MTO", "HDPE"]
    y = np.arange(len(frame))

    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    left = np.zeros(len(frame))
    for key, colour, name in (
        ("scope1_kg", SCOPE1, "Scope 1 (direct)"),
        ("scope2_kg", SCOPE2, "Scope 2 (energy)"),
        ("scope3_kg", SCOPE3, "Scope 3.1 (upstream gas)"),
    ):
        ax.barh(y, frame[key].to_numpy(), left=left, color=colour, label=name, height=0.6)
        left += frame[key].to_numpy()

    for i, row in enumerate(frame.itertuples()):
        ax.text(row.total_kg_co2e + 45, i, f"{row.total_kg_co2e:,.0f} kg  ({row.share_pct:.1f} %)",
                va="center", fontsize=7.2, color=INK)

    ax.set_yticks(y, labels, fontsize=7.8)
    ax.invert_yaxis()
    ax.set_xlabel("kg CO2e per functional unit (1 t HDPE)")
    ax.set_xlim(0, left.max() * 1.42)
    ax.legend(loc="lower right", fontsize=7)
    ax.set_title("Climate-change contribution by life-cycle stage", loc="left", color=INK)
    return _save(fig, path)


def energy_contribution(result: ImpactResult, path: Path) -> Path:
    _style()
    labels = {
        "ng_extraction": "NG extraction",
        "methanol": "Methanol",
        "mto": "MTO",
        "hdpe": "HDPE",
    }
    keys = list(labels)
    values = np.array([result.energy_by_stage.get(k, 0.0) for k in keys]) / 1000.0
    total = values.sum() or 1.0

    fig, ax = plt.subplots(figsize=(7.2, 2.7))
    bars = ax.bar([labels[k] for k in keys], values, color=["#9aa4ac", "#4f6f86", "#4f6f86", "#4f6f86"],
                  width=0.55)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + total * 0.02,
                f"{value:,.1f} GJ\n{100 * value / total:.0f} %", ha="center", fontsize=7,
                color=INK)
    ax.set_ylabel("GJ primary energy per functional unit")
    ax.set_ylim(0, values.max() * 1.32)
    ax.set_title("Fossil primary-energy demand by stage (screening indicator, 9.0 MJ/kWh)", loc="left")
    return _save(fig, path)


# ------------------------------------------------------------------ uncertainty
def uncertainty_hist(
    evidence: pd.DataFrame, screening: pd.DataFrame, baseline: float, path: Path
) -> Path:
    _style()
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 2.9), sharey=True)
    for ax, frame, title, colour in (
        (axes[0], evidence, "Evidence-constrained reconciliation", "#2f6f9f"),
        (axes[1], screening, "Screening: evidence + judgement brackets", "#9a7b2f"),
    ):
        values = frame["total_t"].to_numpy()
        ax.hist(values, bins=45, color=colour, alpha=0.82, edgecolor="white", linewidth=0.3)
        for pct, ls in ((5, ":"), (50, "-"), (95, ":")):
            ax.axvline(np.percentile(values, pct), color=INK, lw=0.8, ls=ls)
        ax.axvline(baseline, color=SCOPE1, lw=1.0, ls="--")
        ax.set_title(title, loc="left", fontsize=8.2)
        ax.set_xlabel("t CO2e / t HDPE")
        ax.text(
            0.03, 0.87,
            f"P5 {np.percentile(values, 5):.3f}   P50 {np.percentile(values, 50):.3f}   "
            f"P95 {np.percentile(values, 95):.3f}",
            transform=ax.transAxes, fontsize=6.2, color=INK,
            bbox=dict(facecolor="white", edgecolor="none", pad=1.4, alpha=0.9),
        )
    axes[0].set_ylabel("draws")
    return _save(fig, path)


def sensitivity_tornado(frame: pd.DataFrame, central: float, path: Path) -> Path:
    _style()
    fig, ax = plt.subplots(figsize=(8.2, 3.9))
    ordered = frame.iloc[::-1].reset_index(drop=True)
    y = np.arange(len(ordered))
    for i, row in enumerate(ordered.itertuples()):
        colour = BASIS_COLORS.get(row.basis, "#9a9a9a")
        ax.barh(i, row.pcf_high_t - row.pcf_low_t, left=row.pcf_low_t, height=0.55,
                color=colour, alpha=0.9)
        ax.text(row.pcf_high_t + 0.008, i, f"{row.swing_t:.3f} t  ({row.swing_pct:.1f} %)",
                va="center", fontsize=6.8, color=INK)
    ax.axvline(central, color=INK, lw=0.8, ls="--")
    ax.set_yticks(y, ordered["label"], fontsize=7.2)
    ax.set_xlabel("t CO2e / t HDPE")
    ax.set_xlim(ordered["pcf_low_t"].min() - 0.03, ordered["pcf_high_t"].max() + 0.30)
    handles = [
        plt.Line2D([], [], color=c, lw=6, label=b.capitalize())
        for b, c in BASIS_COLORS.items()
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=6.6, ncols=2)
    ax.set_title("One-at-a-time sensitivity, coloured by range provenance", loc="left")
    return _save(fig, path)


def scenario_envelope(frame: pd.DataFrame, baseline: float, path: Path) -> Path:
    _style()
    kind_colors = {"Grid & technology": "#2f6f9f", "Allocation": "#6f8f5a", "Utility basis": "#9a7b2f"}
    fig, ax = plt.subplots(figsize=(8.2, 3.2))
    y = np.arange(len(frame))
    for i, row in enumerate(frame.itertuples()):
        colour = kind_colors.get(row.kind, "#9a9a9a")
        ax.plot([baseline, row.pcf_t], [i, i], color=colour, lw=1.0, alpha=0.55)
        ax.scatter(row.pcf_t, i, s=34, color=colour, zorder=3)
        ax.text(row.pcf_t + 0.06, i, f"{row.pcf_t:.2f}", va="center", fontsize=6.8, color=INK)
    ax.axvline(baseline, color=SCOPE1, lw=0.9, ls="--")
    ax.set_yticks(y, frame["label"], fontsize=7)
    ax.invert_yaxis()
    ax.set_xlabel("t CO2e / t HDPE")
    ax.set_xlim(0.6, 6.9)
    handles = [plt.Line2D([], [], marker="o", ls="", color=c, label=k) for k, c in kind_colors.items()]
    ax.legend(handles=handles, loc="upper left", fontsize=6.6)
    ax.set_title("Decision and method scenarios (not inventory uncertainty)", loc="left")
    return _save(fig, path)


def build_all(
    model: PCFModel,
    impact: ImpactResult,
    figure_dir: Path,
    evidence: pd.DataFrame,
    screening: pd.DataFrame,
    sensitivity: pd.DataFrame,
    scenarios: pd.DataFrame,
) -> Mapping[str, Path]:
    figure_dir = Path(figure_dir)
    return {
        "boundary": boundary_diagram(model, figure_dir / "boundary.png"),
        "gwp": gwp_contribution(model, figure_dir / "contribution_gwp.png"),
        "energy": energy_contribution(impact, figure_dir / "contribution_energy.png"),
        "uncertainty": uncertainty_hist(evidence, screening, model.total_t,
                                        figure_dir / "uncertainty.png"),
        "tornado": sensitivity_tornado(sensitivity, model.total_t, figure_dir / "sensitivity.png"),
        "scenarios": scenario_envelope(scenarios, model.total_t, figure_dir / "scenarios.png"),
    }
