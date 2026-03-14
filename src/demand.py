"""
Demand-side metrics for battery sizing analysis.

Converts 15-min energy intensity (kWh/1000 sqft) to aggregate power (kW) for
each county × building-type × upgrade group and computes:
  - Peak demand (kW and kW/1000 sqft)
  - Mean demand (kW)
  - Load factor (mean kW / peak kW)
  - Timestamp of the peak interval

Also produces two Plotly charts:
  - Load factor bar chart by building type × upgrade (sorted, spikiest first)
  - Load duration curves by building type (baseline vs Package 3)

Reads:  data/processed/combined.csv
Writes: reports/demand_summary.csv
        reports/figures/fig_load_factor.html
        reports/figures/fig_load_duration.html
"""

import os

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

# =============================================================================
# PATHS
# =============================================================================

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.normpath(os.path.join(SRC_DIR, ".."))
PROCESSED_DIR = os.path.join(ROOT_DIR, "data", "processed")
REPORTS_DIR = os.path.join(ROOT_DIR, "reports")
FIGURES_DIR = os.path.join(REPORTS_DIR, "figures")

INPUT_CSV = os.path.join(PROCESSED_DIR, "combined.csv")
SUMMARY_CSV = os.path.join(REPORTS_DIR, "demand_summary.csv")
FIG_LOAD_FACTOR = os.path.join(FIGURES_DIR, "fig_load_factor.html")
FIG_LOAD_DURATION = os.path.join(FIGURES_DIR, "fig_load_duration.html")

# =============================================================================
# CONSTANTS
# =============================================================================

SITE_COL = "out.site_energy.total.energy_consumption.kwh_per_1000sqft"
BTYPE_COL = "in.comstock_building_type"
COUNTY_COL = "in.county"
UPGRADE_COL = "upgrade"
FLOOR_AREA_COL = "floor_area_represented"

COUNTY_LABELS = {
    "G0600590": "Orange Co, CA",
    "G0800310": "Denver Co, CO",
    "G2601610": "Washtenaw Co, MI",
}
UPGRADE_LABELS = {0: "Baseline", 36: "Package 3"}
UPGRADE_DASH = {0: "solid", 36: "dash"}
UPGRADE_OPACITY = {0: 0.85, 36: 0.55}

STATE_COLORS = {
    "CA": "#1f77b4",
    "CO": "#ff7f0e",
    "MI": "#2ca02c",
}

# 15-minute interval: kWh ÷ 0.25 h = kW average power
INTERVAL_HOURS = 0.25


# =============================================================================
# LOAD
# =============================================================================


def load_data() -> pd.DataFrame:
    print(f"Loading {INPUT_CSV} ...")
    df = pd.read_csv(INPUT_CSV, parse_dates=["timestamp"])
    print(f"  Shape: {df.shape}")
    null_counts = df.isnull().sum()
    print(f"  Null counts: {null_counts[null_counts > 0].to_dict() or 'none'}")

    missing = [c for c in [SITE_COL, FLOOR_AREA_COL, BTYPE_COL, COUNTY_COL, UPGRADE_COL]
               if c not in df.columns]
    if missing:
        raise ValueError(f"Required columns missing from combined.csv: {missing}")

    zero_fa = (df[FLOOR_AREA_COL] == 0).sum()
    if zero_fa:
        raise ValueError(f"{zero_fa} rows have floor_area_represented == 0; cannot compute kW.")

    # Aggregate kW for the entire building-type pool in each county:
    #   kWh/1000sqft × (sqft / 1000) / interval_hours = kW
    df["kw"] = df[SITE_COL] * (df[FLOOR_AREA_COL] / 1000.0) / INTERVAL_HOURS
    df["county_label"] = df[COUNTY_COL].map(COUNTY_LABELS)
    df["upgrade_label"] = df[UPGRADE_COL].map(UPGRADE_LABELS)
    return df


# =============================================================================
# DEMAND SUMMARY
# =============================================================================


def compute_demand_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per county × building-type × upgrade: peak kW, mean kW, load factor."""
    groups = ["state", UPGRADE_COL, COUNTY_COL, BTYPE_COL]

    agg = df.groupby(groups).agg(
        peak_kw=("kw", "max"),
        mean_kw=("kw", "mean"),
        floor_area_sqft=(FLOOR_AREA_COL, "first"),
    ).reset_index()

    # Identify timestamp of peak interval
    idx_peak = df.groupby(groups)["kw"].idxmax()
    agg["peak_timestamp"] = df.loc[idx_peak, "timestamp"].values

    agg["load_factor"] = agg["mean_kw"] / agg["peak_kw"]
    agg["peak_kw_per_1000sqft"] = agg["peak_kw"] / (agg["floor_area_sqft"] / 1000.0)
    agg["mean_kw_per_1000sqft"] = agg["mean_kw"] / (agg["floor_area_sqft"] / 1000.0)
    agg["county_label"] = agg[COUNTY_COL].map(COUNTY_LABELS)
    agg["upgrade_label"] = agg[UPGRADE_COL].map(UPGRADE_LABELS)

    col_order = [
        "state", UPGRADE_COL, "upgrade_label", COUNTY_COL, "county_label", BTYPE_COL,
        "peak_kw", "mean_kw", "load_factor",
        "peak_kw_per_1000sqft", "mean_kw_per_1000sqft",
        "floor_area_sqft", "peak_timestamp",
    ]
    agg = agg[col_order].sort_values(["state", UPGRADE_COL, BTYPE_COL])

    agg.to_csv(SUMMARY_CSV, index=False)
    print(f"Saved demand summary -> {SUMMARY_CSV}  ({len(agg)} rows)")

    # Quick sanity print
    print("\n  Load factors by building type (Baseline, all counties averaged):")
    lf_base = (
        agg[agg[UPGRADE_COL] == 0]
        .groupby(BTYPE_COL)["load_factor"]
        .mean()
        .sort_values()
    )
    for btype, lf in lf_base.items():
        print(f"    {btype:<30s}  {lf:.3f}")

    return agg


# =============================================================================
# FIGURE: LOAD FACTOR BAR CHART
# =============================================================================


def fig_load_factor_chart(summary: pd.DataFrame) -> go.Figure:
    """Horizontal bar: mean load factor by building type × upgrade (all counties)."""
    lf = (
        summary.groupby([BTYPE_COL, UPGRADE_COL, "upgrade_label"])["load_factor"]
        .mean()
        .reset_index()
    )

    # Sort building types by baseline load factor ascending (spikiest at top when flipped)
    order = (
        lf[lf[UPGRADE_COL] == 0]
        .sort_values("load_factor", ascending=False)[BTYPE_COL]
        .tolist()
    )

    fig = go.Figure()
    for upgrade_id in sorted(lf[UPGRADE_COL].unique()):
        ulabel = UPGRADE_LABELS[upgrade_id]
        sub = lf[lf[UPGRADE_COL] == upgrade_id].set_index(BTYPE_COL)
        fig.add_trace(go.Bar(
            name=ulabel,
            y=order,
            x=[sub.loc[b, "load_factor"] if b in sub.index else None for b in order],
            orientation="h",
            opacity=UPGRADE_OPACITY[upgrade_id],
            marker_color="#1f77b4" if upgrade_id == 0 else "#ff7f0e",
            hovertemplate="<b>%{y}</b><br>Load factor: %{x:.3f}<extra>"
                          + ulabel + "</extra>",
        ))

    fig.add_vline(
        x=0.5, line_dash="dot", line_color="gray",
        annotation_text="LF = 0.5", annotation_position="top right",
    )

    fig.update_layout(
        title="Mean Load Factor by Building Type and Scenario<br>"
              "<sup>Load factor = mean kW ÷ peak kW  |  Lower = spikier profile = better battery opportunity</sup>",
        xaxis_title="Load factor (0 – 1)",
        xaxis={"range": [0, 1]},
        barmode="group",
        template="plotly_white",
        legend_title="Scenario",
        height=520,
    )
    return fig


# =============================================================================
# FIGURE: LOAD DURATION CURVES
# =============================================================================


def fig_load_duration_curves(df: pd.DataFrame, summary: pd.DataFrame) -> go.Figure:
    """
    Load duration curves for each building type × state (baseline vs Package 3).

    X-axis: % of 8,760 hours the demand exceeds the threshold.
    Y-axis: demand as % of peak.

    Shows one subplot per building type, baseline (solid) vs Package 3 (dashed).
    """
    btypes = sorted(df[BTYPE_COL].unique())
    n = len(btypes)
    n_cols = 3
    n_rows = (n + n_cols - 1) // n_cols

    subplot_titles = btypes + [""] * (n_rows * n_cols - n)
    fig = make_subplots(
        rows=n_rows, cols=n_cols,
        subplot_titles=subplot_titles,
        horizontal_spacing=0.08,
        vertical_spacing=0.10,
    )

    # Use county-averaged peak for normalisation per btype × upgrade
    norm_peak = summary.groupby([BTYPE_COL, UPGRADE_COL])["peak_kw"].max()

    for idx, btype in enumerate(btypes):
        row = idx // n_cols + 1
        col = idx % n_cols + 1

        for state in sorted(df["state"].unique()):
            for upgrade_id in sorted(df[UPGRADE_COL].unique()):
                sub = df[
                    (df[BTYPE_COL] == btype)
                    & (df["state"] == state)
                    & (df[UPGRADE_COL] == upgrade_id)
                ]["kw"].dropna().sort_values(ascending=False)

                if sub.empty:
                    continue

                peak = norm_peak.get((btype, upgrade_id), sub.max())
                if peak == 0:
                    continue

                pct_demand = (sub.values / peak * 100)
                pct_time = (pd.Series(range(1, len(pct_demand) + 1)) / len(pct_demand) * 100).values
                ulabel = UPGRADE_LABELS[upgrade_id]

                fig.add_trace(
                    go.Scatter(
                        x=pct_time,
                        y=pct_demand,
                        name=f"{state} — {ulabel}",
                        showlegend=(idx == 0),
                        mode="lines",
                        line={
                            "color": STATE_COLORS[state],
                            "width": 1.5,
                            "dash": UPGRADE_DASH[upgrade_id],
                        },
                        opacity=UPGRADE_OPACITY[upgrade_id],
                        hovertemplate=(
                            f"{state} ({ulabel})<br>"
                            "Time ≥ threshold: %{x:.1f}%<br>"
                            "Demand: %{y:.1f}% of peak<extra></extra>"
                        ),
                    ),
                    row=row, col=col,
                )

    fig.update_xaxes(title_text="% of year ≥ demand level", range=[0, 100])
    fig.update_yaxes(title_text="% of peak demand", range=[0, 105])
    fig.update_layout(
        title="Load Duration Curves by Building Type and Scenario<br>"
              "<sup>Steep drop = spiky profile; flat curve = steady load</sup>",
        template="plotly_white",
        legend_title="State / Scenario",
        height=220 * n_rows,
    )
    return fig


# =============================================================================
# MAIN
# =============================================================================


def main() -> None:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs(FIGURES_DIR, exist_ok=True)

    df = load_data()
    summary = compute_demand_summary(df)

    print("\nBuilding load factor chart...")
    fig_lf = fig_load_factor_chart(summary)
    pio.write_html(fig_lf, FIG_LOAD_FACTOR, include_plotlyjs="cdn", full_html=True)
    print(f"  Saved -> {FIG_LOAD_FACTOR}")

    print("Building load duration curves...")
    fig_ld = fig_load_duration_curves(df, summary)
    pio.write_html(fig_ld, FIG_LOAD_DURATION, include_plotlyjs="cdn", full_html=True)
    print(f"  Saved -> {FIG_LOAD_DURATION}")

    print("Done.")


if __name__ == "__main__":
    main()
