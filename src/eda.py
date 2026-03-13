"""
Exploratory data analysis of combined ComStock energy data.

Reads:  data/processed/combined.csv
Writes: reports/eda_stats.csv
        reports/eda_report.html
"""

import json
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

INPUT_CSV = os.path.join(PROCESSED_DIR, "combined.csv")
STATS_CSV = os.path.join(REPORTS_DIR, "eda_stats.csv")
REPORT_HTML = os.path.join(REPORTS_DIR, "eda_report.html")

SITE_COL = "out.site_energy.total.energy_consumption.kwh_per_1000sqft"
ELEC_COL = "out.electricity.total.energy_consumption.kwh_per_1000sqft"
GAS_COL = "out.natural_gas.total.energy_consumption.kwh_per_1000sqft"
BTYPE_COL = "in.comstock_building_type"
COUNTY_COL = "in.county"

COUNTY_LABELS = {
    "G0600590": "Orange Co, CA",
    "G0800310": "Denver Co, CO",
    "G2601610": "Washtenaw Co, MI",
}

UPGRADE_COL = "upgrade"
UPGRADE_LABELS = {0: "Baseline", 36: "Package 3"}
UPGRADE_DASH = {0: "solid", 36: "dash"}
UPGRADE_OPACITY = {0: 0.85, 36: 0.55}

STATE_COLORS = {
    "CA": "#1f77b4",
    "CO": "#ff7f0e",
    "MI": "#2ca02c",
}

FUEL_COLS = {
    "Electricity": ELEC_COL,
    "Natural Gas": GAS_COL,
    "District Heating": "out.district_heating.total.energy_consumption.kwh_per_1000sqft",
    "District Cooling": "out.district_cooling.total.energy_consumption.kwh_per_1000sqft",
    "Other Fuel": "out.other_fuel.total.energy_consumption.kwh_per_1000sqft",
}

FUEL_COLORS = ["#1f77b4", "#d62728", "#ff7f0e", "#9467bd", "#8c564b"]

MONTH_ABBR = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

# =============================================================================
# LOAD
# =============================================================================


def load_data() -> pd.DataFrame:
    print(f"Loading {INPUT_CSV} ...")
    df = pd.read_csv(INPUT_CSV, parse_dates=["timestamp"])
    print(f"  Shape: {df.shape}")
    null_counts = df.isnull().sum()
    print(f"  Null counts: {null_counts[null_counts > 0].to_dict() or 'none'}")

    df["county_label"] = df[COUNTY_COL].map(COUNTY_LABELS)
    df["upgrade_label"] = df[UPGRADE_COL].map(UPGRADE_LABELS)
    df["month"] = df["timestamp"].dt.month
    df["hour"] = df["timestamp"].dt.hour
    df["season"] = df["month"].map(
        lambda m: "Winter" if m in (12, 1, 2)
        else "Spring" if m in (3, 4, 5)
        else "Summer" if m in (6, 7, 8)
        else "Fall"
    )
    return df


# =============================================================================
# SUMMARY STATISTICS
# =============================================================================


def compute_stats(df: pd.DataFrame) -> pd.DataFrame:
    stats = (
        df.groupby(["state", UPGRADE_COL, COUNTY_COL, BTYPE_COL])[SITE_COL]
        .agg(mean_kwh_per_1000sqft="mean", peak_kwh_per_1000sqft="max",
             total_kwh_per_1000sqft="sum", p95_kwh_per_1000sqft=lambda x: x.quantile(0.95))
        .reset_index()
    )
    stats["county_label"] = stats[COUNTY_COL].map(COUNTY_LABELS)
    stats["upgrade_label"] = stats[UPGRADE_COL].map(UPGRADE_LABELS)
    stats.to_csv(STATS_CSV, index=False)
    print(f"Saved stats -> {STATS_CSV}")
    return stats


# =============================================================================
# FIGURES (plotly)
# =============================================================================


def fig_peak_by_building(df: pd.DataFrame) -> go.Figure:
    """Grouped bar: peak 15-min site energy per building type by county × upgrade."""
    peak = (
        df.groupby(["county_label", "upgrade_label", BTYPE_COL])[SITE_COL]
        .max()
        .reset_index()
    )
    btypes = sorted(df[BTYPE_COL].unique())
    counties = list(COUNTY_LABELS.values())
    state_map = dict(zip(counties, ["CA", "CO", "MI"]))
    upgrade_labels = [UPGRADE_LABELS[u] for u in sorted(UPGRADE_LABELS)]

    fig = go.Figure()
    for county in counties:
        state = state_map[county]
        for ulabel in upgrade_labels:
            sub = peak[
                (peak["county_label"] == county) & (peak["upgrade_label"] == ulabel)
            ].set_index(BTYPE_COL)
            fig.add_trace(go.Bar(
                name=f"{county} — {ulabel}",
                x=btypes,
                y=[sub.loc[b, SITE_COL] if b in sub.index else 0 for b in btypes],
                marker_color=STATE_COLORS[state],
                opacity=UPGRADE_OPACITY[next(k for k, v in UPGRADE_LABELS.items() if v == ulabel)],
                hovertemplate=f"<b>%{{x}}</b><br>{county} ({ulabel})<br>Peak: %{{y:.2f}} kWh/1000 sqft<extra></extra>",
            ))

    fig.update_layout(
        title="Peak 15-min Site Energy Intensity by Building Type, County, and Scenario",
        barmode="group",
        xaxis_title="Building Type",
        yaxis_title="Peak 15-min site energy (kWh/1000 sqft)",
        xaxis_tickangle=-35,
        template="plotly_white",
        legend_title="County / Scenario",
        height=480,
    )
    return fig


def fig_monthly_site(df: pd.DataFrame) -> go.Figure:
    """Line chart: monthly total site energy intensity by state × upgrade."""
    monthly = (
        df.groupby(["state", UPGRADE_COL, "month"])[SITE_COL]
        .sum()
        .reset_index()
    )
    monthly["month_abbr"] = monthly["month"].map(MONTH_ABBR)
    month_order = [MONTH_ABBR[m] for m in range(1, 13)]

    fig = go.Figure()
    for state in sorted(df["state"].unique()):
        for upgrade_id in sorted(df[UPGRADE_COL].unique()):
            ulabel = UPGRADE_LABELS[upgrade_id]
            sub = monthly[
                (monthly["state"] == state) & (monthly[UPGRADE_COL] == upgrade_id)
            ].set_index("month_abbr")
            fig.add_trace(go.Scatter(
                name=f"{state} — {ulabel}",
                x=month_order,
                y=[sub.loc[m, SITE_COL] if m in sub.index else 0 for m in month_order],
                mode="lines+markers",
                line={"color": STATE_COLORS[state], "width": 2,
                      "dash": UPGRADE_DASH[upgrade_id]},
                marker={"size": 5},
                opacity=UPGRADE_OPACITY[upgrade_id],
                hovertemplate=f"<b>%{{x}}</b> — {state} ({ulabel})<br>Total: %{{y:.2f}} kWh/1000 sqft<extra></extra>",
            ))

    fig.update_layout(
        title="Monthly Total Site Energy Intensity by State and Scenario (2018)",
        xaxis_title="Month",
        yaxis_title="Total site energy (kWh/1000 sqft)",
        template="plotly_white",
        legend_title="State / Scenario",
        height=430,
    )
    return fig


def fig_hourly_electricity(df: pd.DataFrame) -> go.Figure:
    """Line chart: mean hourly electricity intensity by state × upgrade."""
    hourly = df.groupby(["state", UPGRADE_COL, "hour"])[ELEC_COL].mean().reset_index()

    fig = go.Figure()
    for state in sorted(df["state"].unique()):
        for upgrade_id in sorted(df[UPGRADE_COL].unique()):
            ulabel = UPGRADE_LABELS[upgrade_id]
            sub = hourly[(hourly["state"] == state) & (hourly[UPGRADE_COL] == upgrade_id)]
            fig.add_trace(go.Scatter(
                x=sub["hour"],
                y=sub[ELEC_COL],
                name=f"{state} — {ulabel}",
                mode="lines+markers",
                line={"color": STATE_COLORS[state], "width": 2,
                      "dash": UPGRADE_DASH[upgrade_id]},
                marker={"size": 5},
                opacity=UPGRADE_OPACITY[upgrade_id],
                hovertemplate=f"Hour %{{x}}:00 ({ulabel})<br>Mean electricity: %{{y:.2f}} kWh/1000 sqft<extra></extra>",
            ))

    fig.update_layout(
        title="Mean Hourly Electricity Intensity Profile by State and Scenario",
        xaxis_title="Hour of day",
        yaxis_title="Mean electricity (kWh/1000 sqft per 15-min interval)",
        xaxis={"tickmode": "linear", "dtick": 2},
        template="plotly_white",
        legend_title="State / Scenario",
        height=420,
    )
    return fig


def fig_energy_mix(df: pd.DataFrame) -> go.Figure:
    """Stacked bar: annual energy mix by county × upgrade."""
    counties = list(COUNTY_LABELS.values())
    upgrade_labels = [UPGRADE_LABELS[u] for u in sorted(UPGRADE_LABELS)]
    x_labels = [f"{c}<br>{ul}" for c in counties for ul in upgrade_labels]

    fig = go.Figure()
    for (fuel, col), color in zip(FUEL_COLS.items(), FUEL_COLORS):
        if col not in df.columns:
            continue
        vals = []
        for c in counties:
            for ulabel in upgrade_labels:
                uid = next(k for k, v in UPGRADE_LABELS.items() if v == ulabel)
                vals.append(
                    df[(df["county_label"] == c) & (df[UPGRADE_COL] == uid)][col].sum()
                )
        fig.add_trace(go.Bar(
            name=fuel,
            x=x_labels,
            y=vals,
            marker_color=color,
            hovertemplate=f"<b>{fuel}</b><br>%{{x}}<br>Annual: %{{y:.2f}} kWh/1000 sqft<extra></extra>",
        ))

    fig.update_layout(
        title="Annual Energy Intensity Mix by County and Scenario (2018)",
        barmode="stack",
        xaxis_title="County / Scenario",
        yaxis_title="Annual energy intensity (kWh/1000 sqft)",
        template="plotly_white",
        legend_title="Fuel Type",
        height=450,
    )
    return fig


def fig_seasonal_heatmap(df: pd.DataFrame) -> go.Figure:
    """Heatmap subplots: peak site energy intensity by building type x season.

    Layout: 2 rows (Baseline, Package 3) × 3 columns (one per county).
    """
    seasons = ["Winter", "Spring", "Summer", "Fall"]
    counties = list(COUNTY_LABELS.values())
    upgrade_labels = [UPGRADE_LABELS[u] for u in sorted(UPGRADE_LABELS)]

    subplot_titles = [
        f"{county}<br>{ulabel}"
        for ulabel in upgrade_labels
        for county in counties
    ]

    fig = make_subplots(
        rows=len(upgrade_labels), cols=len(counties),
        subplot_titles=subplot_titles,
        horizontal_spacing=0.06,
        vertical_spacing=0.12,
    )

    n_cols = len(counties)
    for row_idx, ulabel in enumerate(upgrade_labels, start=1):
        uid = next(k for k, v in UPGRADE_LABELS.items() if v == ulabel)
        for col_idx, county in enumerate(counties, start=1):
            sub = df[(df["county_label"] == county) & (df[UPGRADE_COL] == uid)]
            if sub.empty:
                continue
            peak = sub.groupby([BTYPE_COL, "season"])[SITE_COL].max().unstack("season")
            peak = peak.reindex(columns=seasons).dropna(how="all")

            row_max = peak.max(axis=1).replace(0, 1)
            peak_norm = peak.div(row_max, axis=0)
            show_cb = (col_idx == n_cols) and (row_idx == 1)

            fig.add_trace(
                go.Heatmap(
                    z=peak_norm.values,
                    x=seasons,
                    y=list(peak_norm.index),
                    colorscale="YlOrRd",
                    showscale=show_cb,
                    colorbar={"title": "Normalised<br>peak", "x": 1.02} if show_cb else {},
                    hovertemplate=(
                        "Season: %{x}<br>Building: %{y}<br>"
                        "Normalised peak: %{z:.2f}<extra></extra>"
                    ),
                ),
                row=row_idx, col=col_idx,
            )

    fig.update_layout(
        title="Peak Site Energy Intensity: Building Type × Season × Scenario<br>"
              "<sup>Colour normalised within each building type (1.0 = highest season)</sup>",
        template="plotly_white",
        height=800,
    )
    return fig


def fig_top10_peaks(df: pd.DataFrame) -> go.Figure:
    """Bar chart: top 10 peak 15-min site energy intensity intervals."""
    top10 = df.nlargest(10, SITE_COL)[
        ["timestamp", "state", COUNTY_COL, UPGRADE_COL, BTYPE_COL, SITE_COL]
    ].reset_index(drop=True)
    top10["county_label"] = top10[COUNTY_COL].map(COUNTY_LABELS)
    top10["upgrade_label"] = top10[UPGRADE_COL].map(UPGRADE_LABELS)
    top10["label"] = (
        top10[BTYPE_COL] + "<br>"
        + top10["county_label"] + " (" + top10["upgrade_label"] + ")<br>"
        + top10["timestamp"].dt.strftime("%b %d, %H:%M")
    )
    colors = [STATE_COLORS.get(s, "gray") for s in top10["state"]]

    fig = go.Figure(go.Bar(
        x=top10[SITE_COL][::-1],
        y=top10["label"][::-1],
        orientation="h",
        marker_color=colors[::-1],
        hovertemplate="Site energy: %{x:.2f} kWh/1000 sqft<extra></extra>",
    ))
    fig.update_layout(
        title="Top 10 Peak 15-min Site Energy Intensity Intervals",
        xaxis_title="Site energy (kWh/1000 sqft per 15-min interval)",
        template="plotly_white",
        height=420,
        yaxis={"tickfont": {"size": 10}},
    )
    return fig


# =============================================================================
# HTML REPORT
# =============================================================================


def df_to_html_table(df: pd.DataFrame, float_fmt: str = ".2f") -> str:
    """Render a DataFrame as a styled HTML table."""
    header = "".join(
        f'<th style="padding:6px 12px;text-align:right;background:#343a40;color:#fff">{c}</th>'
        for c in df.columns
    )
    rows = ""
    for i, row in df.iterrows():
        bg = "#f8f9fa" if i % 2 == 0 else "#ffffff"
        cells = ""
        for v in row:
            if isinstance(v, float):
                cells += f'<td style="padding:6px 12px;text-align:right">{v:{float_fmt}}</td>'
            else:
                cells += f'<td style="padding:6px 12px;text-align:right">{v}</td>'
        rows += f'<tr style="background:{bg}">{cells}</tr>'

    return (
        '<div style="overflow-x:auto">'
        '<table style="width:100%;border-collapse:collapse;font-size:0.88em">'
        f"<thead><tr>{header}</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table></div>"
    )


def fig_to_div(fig: go.Figure, div_id: str) -> str:
    fig_json = pio.to_json(fig, validate=False)
    return (
        f'<div id="{div_id}"></div>'
        f'<script>'
        f'(function(){{'
        f'var d=JSON.parse({json.dumps(fig_json)});'
        f'Plotly.newPlot("{div_id}",d.data,d.layout,{{responsive:true}});'
        f'}})();'
        f'</script>'
    )


def build_html(df: pd.DataFrame, stats: pd.DataFrame, generated_date: str) -> str:
    # --- Computed values for narrative ---
    n_rows = len(df)
    states = sorted(df["state"].unique())
    upgrades = sorted(df[UPGRADE_COL].unique())
    btype_list = sorted(df[BTYPE_COL].unique())
    btype_per_state = df[df[UPGRADE_COL] == 0].groupby("state")[BTYPE_COL].nunique().to_dict()
    ts_min = df["timestamp"].min().strftime("%Y-%m-%d")
    ts_max = df["timestamp"].max().strftime("%Y-%m-%d")
    n_groups = df.groupby(["state", UPGRADE_COL, COUNTY_COL, BTYPE_COL]).ngroups

    state_stats = df.groupby(["state", UPGRADE_COL])[SITE_COL].agg(["mean", "max", "sum"]).round(2)

    peak_row = df.loc[df[SITE_COL].idxmax()]

    hourly_peak = (
        df[df[UPGRADE_COL] == 0].groupby(["state", "hour"])[ELEC_COL]
        .mean()
        .reset_index()
        .sort_values(ELEC_COL, ascending=False)
        .groupby("state")
        .first()
        .reset_index()
    )

    elec_share = (
        df[df[UPGRADE_COL] == 0]
        .groupby("county_label")[[ELEC_COL, GAS_COL, SITE_COL]]
        .sum()
    )
    elec_share["elec_pct"] = (elec_share[ELEC_COL] / elec_share[SITE_COL] * 100).round(1)
    elec_share["gas_pct"] = (elec_share[GAS_COL] / elec_share[SITE_COL] * 100).round(1)

    null_total = int(df.isnull().sum().sum())

    # --- Summary stats table ---
    state_stats_display = state_stats.copy().reset_index()
    state_stats_display[UPGRADE_COL] = state_stats_display[UPGRADE_COL].map(UPGRADE_LABELS)
    state_stats_display.columns = ["State", "Scenario", "Mean (kWh/1000 sqft)",
                                   "Peak (kWh/1000 sqft)", "Sum (kWh/1000 sqft)"]

    # --- Building rankings per county × upgrade ---
    rankings_html = ""
    for county_code, county_name in COUNTY_LABELS.items():
        for upgrade_id in sorted(upgrades):
            ulabel = UPGRADE_LABELS[upgrade_id]
            sub = stats[
                (stats[COUNTY_COL] == county_code) & (stats[UPGRADE_COL] == upgrade_id)
            ].sort_values("peak_kwh_per_1000sqft", ascending=False)
            if sub.empty:
                continue
            rows = ""
            for i, (_, r) in enumerate(sub.iterrows(), 1):
                bg = "#f8f9fa" if i % 2 == 0 else "#ffffff"
                rows += (
                    f'<tr style="background:{bg}">'
                    f'<td style="padding:5px 10px">{i}</td>'
                    f'<td style="padding:5px 10px">{r[BTYPE_COL]}</td>'
                    f'<td style="padding:5px 10px;text-align:right">{r["mean_kwh_per_1000sqft"]:.2f}</td>'
                    f'<td style="padding:5px 10px;text-align:right">{r["peak_kwh_per_1000sqft"]:.2f}</td>'
                    f'<td style="padding:5px 10px;text-align:right">{r["p95_kwh_per_1000sqft"]:.2f}</td>'
                    f'</tr>'
                )
            rankings_html += f"""
            <h3>{county_name} — {ulabel}</h3>
            <table style="width:100%;border-collapse:collapse;font-size:0.88em;margin-bottom:16px">
              <thead><tr style="background:#343a40;color:#fff">
                <th style="padding:6px 10px">#</th>
                <th style="padding:6px 10px">Building Type</th>
                <th style="padding:6px 10px;text-align:right">Mean (kWh/1000 sqft)</th>
                <th style="padding:6px 10px;text-align:right">Peak (kWh/1000 sqft)</th>
                <th style="padding:6px 10px;text-align:right">P95 (kWh/1000 sqft)</th>
              </tr></thead>
              <tbody>{rows}</tbody>
            </table>"""

    # --- Energy mix table ---
    mix_rows = ""
    for county in list(COUNTY_LABELS.values()):
        if county in elec_share.index:
            r = elec_share.loc[county]
            mix_rows += (
                f'<tr><td style="padding:6px 10px">{county}</td>'
                f'<td style="padding:6px 10px;text-align:right">{r["elec_pct"]:.1f}%</td>'
                f'<td style="padding:6px 10px;text-align:right">{r["gas_pct"]:.1f}%</td></tr>'
            )
    mix_table = f"""
    <table style="border-collapse:collapse;font-size:0.9em">
      <thead><tr style="background:#343a40;color:#fff">
        <th style="padding:6px 12px">County</th>
        <th style="padding:6px 12px;text-align:right">Electricity %</th>
        <th style="padding:6px 12px;text-align:right">Natural Gas %</th>
      </tr></thead>
      <tbody>{mix_rows}</tbody>
    </table>"""

    # --- Figures ---
    print("  Building figures...")
    figures = {
        "fig-peak": fig_to_div(fig_peak_by_building(df), "fig-peak"),
        "fig-monthly": fig_to_div(fig_monthly_site(df), "fig-monthly"),
        "fig-hourly": fig_to_div(fig_hourly_electricity(df), "fig-hourly"),
        "fig-mix": fig_to_div(fig_energy_mix(df), "fig-mix"),
        "fig-seasonal": fig_to_div(fig_seasonal_heatmap(df), "fig-seasonal"),
        "fig-top10": fig_to_div(fig_top10_peaks(df), "fig-top10"),
    }
    for k in figures:
        print(f"    Built: {k}")

    btype_list_html = "".join(f"<li>{b}</li>" for b in btype_list)
    state_coverage_html = "".join(
        f"<li>{s}: {btype_per_state[s]} building types</li>" for s in states
    )
    hourly_peak_html = "".join(
        f"<li>{r['state']}: peak at {int(r['hour']):02d}:00 "
        f"(mean {r[ELEC_COL]:.2f} kWh/1000 sqft per 15-min interval)</li>"
        for _, r in hourly_peak.iterrows()
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>EDA Report — ComStock Energy Data</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           max-width: 1100px; margin: 40px auto; padding: 0 20px;
           color: #212529; line-height: 1.6; background: #fff; }}
    h1 {{ border-bottom: 3px solid #1a1a2e; padding-bottom: 10px; color: #1a1a2e; }}
    h2 {{ color: #343a40; margin-top: 40px; border-bottom: 1px solid #dee2e6;
          padding-bottom: 6px; }}
    h3 {{ color: #495057; margin-top: 24px; }}
    .meta {{ background:#f8f9fa; padding:12px 18px; border-radius:6px;
             font-size:0.9em; margin-bottom:24px; }}
    .meta span {{ margin-right:20px; }}
    .kv {{ display:grid; grid-template-columns:200px 1fr; gap:4px 16px;
           font-size:0.9em; }}
    .kv dt {{ color:#6c757d; }}
    .kv dd {{ margin:0; font-weight:600; }}
    .note {{ background:#e7f3fe; border-left:4px solid #2196F3;
             padding:10px 16px; border-radius:0 4px 4px 0; margin:16px 0;
             font-size:0.9em; }}
    .fig-wrap {{ margin:24px 0; }}
    ul {{ padding-left:20px; }}
    code {{ background:#f8f9fa; padding:1px 5px; border-radius:3px;
            font-family:monospace; font-size:0.88em; }}
    footer {{ margin-top:48px; padding-top:16px; border-top:1px solid #dee2e6;
              font-size:0.8em; color:#6c757d; }}
  </style>
</head>
<body>

<h1>EDA Report: ComStock Energy Data (2018)</h1>
<div class="meta">
  <span><strong>Source:</strong> data/processed/combined.csv</span>
  <span><strong>Stats:</strong> reports/eda_stats.csv</span>
  <span><strong>Generated:</strong> {generated_date}</span>
</div>

<h2>1. Dataset Overview</h2>
<dl class="kv">
  <dt>Total rows</dt>          <dd>{n_rows:,}</dd>
  <dt>County × building × upgrade groups</dt> <dd>{n_groups}</dd>
  <dt>Timestamp range</dt>     <dd>{ts_min} to {ts_max}</dd>
  <dt>Interval</dt>            <dd>15-minute</dd>
  <dt>States</dt>              <dd>{", ".join(states)}</dd>
  <dt>Scenarios</dt>           <dd>{", ".join(UPGRADE_LABELS.get(u, str(u)) for u in upgrades)}</dd>
  <dt>Energy unit</dt>         <dd>kWh per 1000 square feet per 15-min interval</dd>
  <dt>Null values</dt>         <dd>{null_total}</dd>
</dl>
<div class="note">
  Two scenarios are included: <strong>Baseline (upgrade 0)</strong> — existing 2018 building stock,
  and <strong>Package 3 (upgrade 36)</strong> — an efficiency measure package applied to the same
  building stock. Charts show both scenarios; solid lines / full-opacity bars = Baseline,
  dashed lines / lower-opacity bars = Package 3.
</div>

<h3>Building types ({len(btype_list)})</h3>
<ul>{btype_list_html}</ul>

<h3>Coverage by state (Baseline)</h3>
<ul>{state_coverage_html}</ul>

<h2>2. Site Energy Intensity — Summary by State and Scenario</h2>
<p>All values in kWh/1000 sqft per 15-min interval. After normalising by
<code>floor_area_represented</code>, values are comparable across counties.</p>
{df_to_html_table(state_stats_display)}

<h2>3. Peak 15-Minute Interval (across all scenarios)</h2>
<dl class="kv">
  <dt>Peak value</dt>      <dd>{peak_row[SITE_COL]:.2f} kWh/1000 sqft</dd>
  <dt>Timestamp</dt>       <dd>{peak_row["timestamp"]}</dd>
  <dt>State</dt>           <dd>{peak_row["state"]}</dd>
  <dt>County</dt>          <dd>{COUNTY_LABELS.get(peak_row[COUNTY_COL], peak_row[COUNTY_COL])}</dd>
  <dt>Building type</dt>   <dd>{peak_row[BTYPE_COL]}</dd>
  <dt>Scenario</dt>        <dd>{UPGRADE_LABELS.get(peak_row[UPGRADE_COL], str(peak_row[UPGRADE_COL]))}</dd>
</dl>

<h2>4. Peak Energy Intensity by Building Type, County, and Scenario</h2>
<div class="fig-wrap">{figures["fig-peak"]}</div>

<h2>5. Monthly Total Site Energy Intensity by Scenario</h2>
<div class="fig-wrap">{figures["fig-monthly"]}</div>

<h2>6. Mean Hourly Electricity Intensity Profile by Scenario</h2>
<div class="fig-wrap">{figures["fig-hourly"]}</div>
<h3>Peak electricity hour by state (Baseline)</h3>
<ul>{hourly_peak_html}</ul>

<h2>7. Annual Energy Mix by County and Scenario</h2>
<div class="fig-wrap">{figures["fig-mix"]}</div>
<h3>Electricity and natural gas share of site energy (Baseline)</h3>
{mix_table}

<h2>8. Seasonal Peak Energy Intensity by Scenario</h2>
<div class="fig-wrap">{figures["fig-seasonal"]}</div>

<h2>9. Top 10 Peak 15-min Intervals</h2>
<div class="fig-wrap">{figures["fig-top10"]}</div>

<h2>10. Building Type Rankings by County and Scenario</h2>
<p>Ranked by peak 15-min site energy intensity (kWh/1000 sqft).</p>
{rankings_html}

<footer>
  Source: NREL End-Use Load Profiles for the U.S. Building Stock &nbsp;|&nbsp;
  Energy values normalised by <code>floor_area_represented</code> (kWh/1000 sqft per 15-min interval)
</footer>

</body>
</html>"""


# =============================================================================
# MAIN
# =============================================================================


def main() -> None:
    os.makedirs(REPORTS_DIR, exist_ok=True)

    df = load_data()
    stats = compute_stats(df)

    generated_date = pd.Timestamp.now().strftime("%Y-%m-%d")
    print("Building HTML report...")
    html = build_html(df, stats, generated_date)

    with open(REPORT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved -> {REPORT_HTML}")
    print("Done.")


if __name__ == "__main__":
    main()
