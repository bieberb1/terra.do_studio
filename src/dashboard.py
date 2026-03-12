"""
Interactive dashboard for the ComStock combined energy dataset.

Reads:  data/processed/combined.csv
Writes: dashboard/index.html  (self-contained, no server required)
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
INPUT_CSV = os.path.join(ROOT_DIR, "data", "processed", "combined.csv")
DASHBOARD_DIR = os.path.join(ROOT_DIR, "dashboard")
OUTPUT_HTML = os.path.join(DASHBOARD_DIR, "index.html")

SITE_COL = "out.site_energy.total.energy_consumption.kwh_per_1000sqft"
ELEC_COL = "out.electricity.total.energy_consumption.kwh_per_1000sqft"
GAS_COL = "out.natural_gas.total.energy_consumption.kwh_per_1000sqft"
DISTRICT_COOL_COL = "out.district_cooling.total.energy_consumption.kwh_per_1000sqft"
DISTRICT_HEAT_COL = "out.district_heating.total.energy_consumption.kwh_per_1000sqft"
OTHER_FUEL_COL = "out.other_fuel.total.energy_consumption.kwh_per_1000sqft"
BTYPE_COL = "in.comstock_building_type"
COUNTY_COL = "in.county"

COUNTY_LABELS = {
    "G0600590": "Orange Co, CA",
    "G0801110": "San Juan Co, CO",
    "G2601610": "Washtenaw Co, MI",
}

STATE_COLORS = {
    "CA": "#1f77b4",
    "CO": "#ff7f0e",
    "MI": "#2ca02c",
}

FUEL_COLORS = {
    "Electricity": "#1f77b4",
    "Natural Gas": "#d62728",
    "District Heating": "#ff7f0e",
    "District Cooling": "#9467bd",
    "Other Fuel": "#8c564b",
}

MONTH_ABBR = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


# =============================================================================
# LOAD + PREP
# =============================================================================


def load_data() -> pd.DataFrame:
    print(f"Loading {INPUT_CSV} ...")
    df = pd.read_csv(INPUT_CSV, parse_dates=["timestamp"])
    print(f"  Shape: {df.shape}")
    null_counts = df.isnull().sum()
    print(f"  Null counts: {null_counts[null_counts > 0].to_dict() or 'none'}")
    df["county_label"] = df[COUNTY_COL].map(COUNTY_LABELS)
    df["month"] = df["timestamp"].dt.month
    df["hour"] = df["timestamp"].dt.hour
    df["date"] = df["timestamp"].dt.date.astype(str)
    df["month_name"] = df["month"].map(MONTH_ABBR)
    return df


# =============================================================================
# CHART 1 — Peak energy by building type (grouped bars, one bar per county)
# =============================================================================


def chart_peak_by_building(df: pd.DataFrame) -> go.Figure:
    peak = (
        df.groupby(["county_label", BTYPE_COL])[SITE_COL]
        .max()
        .reset_index()
        .rename(columns={SITE_COL: "peak_kwh"})
    )
    btypes = sorted(df[BTYPE_COL].unique())
    counties = list(COUNTY_LABELS.values())
    state_map = dict(zip(counties, ["CA", "CO", "MI"]))

    fig = go.Figure()
    for county in counties:
        sub = peak[peak["county_label"] == county].set_index(BTYPE_COL)
        state = state_map[county]
        fig.add_trace(go.Bar(
            name=county,
            x=btypes,
            y=[sub.loc[b, "peak_kwh"] if b in sub.index else 0 for b in btypes],
            marker_color=STATE_COLORS[state],
            hovertemplate=(
                "<b>%{x}</b><br>"
                f"County: {county}<br>"
                "Peak 15-min site energy: %{y:,.1f} kWh<extra></extra>"
            ),
        ))

    fig.update_layout(
        title="Peak 15-min Site Energy by Building Type and County",
        barmode="group",
        xaxis_title="Building Type",
        yaxis_title="Peak 15-min site energy (kWh)",
        legend_title="County",
        xaxis_tickangle=-35,
        yaxis_tickformat=",.0f",
        template="plotly_white",
        height=480,
    )
    return fig


# =============================================================================
# CHART 2 — Daily time series (aggregated across all building types per state)
# =============================================================================


def chart_daily_timeseries(df: pd.DataFrame) -> go.Figure:
    daily = (
        df.groupby(["state", "date"])[SITE_COL]
        .sum()
        .reset_index()
        .rename(columns={SITE_COL: "daily_kwh"})
    )
    daily["date_dt"] = pd.to_datetime(daily["date"])

    btypes = sorted(df[BTYPE_COL].unique())
    states = sorted(df["state"].unique())

    # Base figure: one line per state (all buildings summed)
    fig = go.Figure()
    for state in states:
        sub = daily[daily["state"] == state].sort_values("date_dt")
        fig.add_trace(go.Scatter(
            x=sub["date_dt"],
            y=sub["daily_kwh"],
            name=state,
            mode="lines",
            line={"color": STATE_COLORS[state], "width": 1.5},
            hovertemplate="<b>%{x|%b %d}</b><br>Daily site energy: %{y:,.0f} kWh<extra></extra>",
        ))

    # Hidden per-building traces for dropdown
    for btype in btypes:
        sub_b = (
            df[df[BTYPE_COL] == btype]
            .groupby(["state", "date"])[SITE_COL]
            .sum()
            .reset_index()
        )
        sub_b["date_dt"] = pd.to_datetime(sub_b["date"])
        for state in states:
            s = sub_b[sub_b["state"] == state].sort_values("date_dt")
            fig.add_trace(go.Scatter(
                x=s["date_dt"],
                y=s[SITE_COL],
                name=f"{state} — {btype}",
                mode="lines",
                line={"color": STATE_COLORS[state], "width": 1.5, "dash": "dot"},
                visible=False,
                hovertemplate=(
                    f"<b>%{{x|%b %d}}</b><br>{btype}<br>"
                    "Daily site energy: %{y:,.0f} kWh<extra></extra>"
                ),
            ))

    n_states = len(states)
    n_btypes = len(btypes)

    def visibility_for(selected_btype_idx: int | None) -> list:
        """Return visibility list: show base traces OR one building's traces."""
        vis = []
        for _ in range(n_states):
            vis.append(selected_btype_idx is None)
        for bi in range(n_btypes):
            for _ in range(n_states):
                vis.append(bi == selected_btype_idx)
        return vis

    buttons = [
        {"label": "All buildings", "method": "update",
         "args": [{"visible": visibility_for(None)},
                  {"title": "Daily Site Energy — All Buildings by State"}]}
    ]
    for bi, btype in enumerate(btypes):
        buttons.append({
            "label": btype,
            "method": "update",
            "args": [{"visible": visibility_for(bi)},
                     {"title": f"Daily Site Energy — {btype}"}],
        })

    fig.update_layout(
        title="Daily Site Energy — All Buildings by State",
        xaxis_title="Date",
        yaxis_title="Daily site energy (kWh)",
        yaxis_tickformat=",.0f",
        template="plotly_white",
        height=460,
        xaxis={"rangeslider": {"visible": True}, "type": "date"},
        updatemenus=[{
            "buttons": buttons,
            "direction": "down",
            "showactive": True,
            "x": 0.01, "xanchor": "left",
            "y": 1.18, "yanchor": "top",
            "bgcolor": "#f8f9fa",
            "bordercolor": "#dee2e6",
        }],
    )
    return fig


# =============================================================================
# CHART 3 — Mean hourly electricity profile (heatmap: building type × hour)
# =============================================================================


def chart_hourly_heatmap(df: pd.DataFrame) -> go.Figure:
    states = sorted(df["state"].unique())
    hours = list(range(24))

    fig = make_subplots(
        rows=1, cols=len(states),
        subplot_titles=[f"{s} — {COUNTY_LABELS[k]}" for s, k in zip(
            states, list(COUNTY_LABELS.keys())
        )],
        shared_yaxes=True,
        horizontal_spacing=0.04,
    )

    for col_idx, state in enumerate(states, start=1):
        sub = df[df["state"] == state]
        hourly = (
            sub.groupby([BTYPE_COL, "hour"])[ELEC_COL]
            .mean()
            .unstack("hour")
            .reindex(columns=hours, fill_value=0)
        )
        # Normalise each building type to 0-1 for visual comparability
        row_max = hourly.max(axis=1).replace(0, 1)
        hourly_norm = hourly.div(row_max, axis=0)

        heatmap_btypes = list(hourly.index)
        fig.add_trace(
            go.Heatmap(
                z=hourly_norm.values,
                x=[f"{h:02d}:00" for h in hours],
                y=heatmap_btypes,
                colorscale="YlOrRd",
                showscale=(col_idx == len(states)),
                colorbar={"title": "Normalised<br>mean elec.", "x": 1.02}
                if col_idx == len(states) else {},
                hovertemplate=(
                    "Hour: %{x}<br>Building: %{y}<br>"
                    "Normalised electricity: %{z:.2f}<extra></extra>"
                ),
            ),
            row=1, col=col_idx,
        )
        fig.update_xaxes(title_text="Hour", row=1, col=col_idx, tickangle=-45)

    fig.update_yaxes(title_text="Building Type", row=1, col=1)
    fig.update_layout(
        title="Mean Hourly Electricity Profile by Building Type and State<br>"
              "<sup>Colour scale normalised within each building type (1.0 = peak hour)</sup>",
        template="plotly_white",
        height=500,
    )
    return fig


# =============================================================================
# CHART 4 — Monthly total site energy (line chart per building type)
# =============================================================================


def chart_monthly_by_building(df: pd.DataFrame) -> go.Figure:
    states = sorted(df["state"].unique())
    btypes = sorted(df[BTYPE_COL].unique())

    monthly = (
        df.groupby(["state", BTYPE_COL, "month"])[SITE_COL]
        .sum()
        .reset_index()
    )
    monthly["month_abbr"] = monthly["month"].map(MONTH_ABBR)

    month_order = [MONTH_ABBR[m] for m in range(1, 13)]

    fig = go.Figure()

    # One visible trace per state (all btypes summed)
    all_monthly = df.groupby(["state", "month"])[SITE_COL].sum().reset_index()
    all_monthly["month_abbr"] = all_monthly["month"].map(MONTH_ABBR)

    for state in states:
        sub = all_monthly[all_monthly["state"] == state].set_index("month_abbr")
        fig.add_trace(go.Scatter(
            x=month_order,
            y=[sub.loc[m, SITE_COL] if m in sub.index else 0 for m in month_order],
            name=state,
            mode="lines+markers",
            line={"color": STATE_COLORS[state], "width": 2},
            marker={"size": 7},
            hovertemplate="<b>%{x}</b><br>%{y:,.0f} kWh<extra></extra>",
        ))

    # Per-building hidden traces
    for btype in btypes:
        for state in states:
            sub = monthly[(monthly[BTYPE_COL] == btype) & (monthly["state"] == state)]
            sub_idx = sub.set_index("month_abbr")
            fig.add_trace(go.Scatter(
                x=month_order,
                y=[sub_idx.loc[m, SITE_COL] if m in sub_idx.index else 0 for m in month_order],
                name=f"{state}",
                mode="lines+markers",
                line={"color": STATE_COLORS[state], "width": 2, "dash": "dot"},
                marker={"size": 7},
                visible=False,
                hovertemplate="<b>%{x}</b><br>%{y:,.0f} kWh<extra></extra>",
            ))

    n_states = len(states)
    n_btypes = len(btypes)

    def vis(bi):
        v = []
        for _ in range(n_states):
            v.append(bi is None)
        for b_idx in range(n_btypes):
            for _ in range(n_states):
                v.append(b_idx == bi)
        return v

    buttons = [{"label": "All buildings", "method": "update",
                "args": [{"visible": vis(None)},
                         {"title": "Monthly Total Site Energy — All Buildings"}]}]
    for bi, btype in enumerate(btypes):
        buttons.append({
            "label": btype, "method": "update",
            "args": [{"visible": vis(bi)},
                     {"title": f"Monthly Total Site Energy — {btype}"}],
        })

    fig.update_layout(
        title="Monthly Total Site Energy — All Buildings",
        xaxis_title="Month",
        yaxis_title="Total site energy (kWh)",
        yaxis_tickformat=",.0f",
        template="plotly_white",
        height=450,
        updatemenus=[{
            "buttons": buttons,
            "direction": "down",
            "showactive": True,
            "x": 0.01, "xanchor": "left",
            "y": 1.18, "yanchor": "top",
            "bgcolor": "#f8f9fa",
            "bordercolor": "#dee2e6",
        }],
    )
    return fig


# =============================================================================
# CHART 5 — Energy mix stacked bar (annual totals by county)
# =============================================================================


def chart_energy_mix(df: pd.DataFrame) -> go.Figure:
    fuel_map = {
        "Electricity": ELEC_COL,
        "Natural Gas": GAS_COL,
        "District Heating": DISTRICT_HEAT_COL,
        "District Cooling": DISTRICT_COOL_COL,
        "Other Fuel": OTHER_FUEL_COL,
    }

    counties = list(COUNTY_LABELS.values())
    fig = go.Figure()
    for fuel, col in fuel_map.items():
        vals = [
            df[df["county_label"] == c][col].sum() if col in df.columns else 0
            for c in counties
        ]
        fig.add_trace(go.Bar(
            name=fuel,
            x=counties,
            y=vals,
            marker_color=FUEL_COLORS[fuel],
            hovertemplate=(
                f"<b>{fuel}</b><br>"
                "County: %{x}<br>"
                "Annual total: %{y:,.0f} kWh<extra></extra>"
            ),
        ))

    fig.update_layout(
        title="Annual Energy Mix by County (2018)",
        barmode="stack",
        xaxis_title="County",
        yaxis_title="Annual energy consumption (kWh)",
        yaxis_tickformat=",.0f",
        legend_title="Fuel Type",
        template="plotly_white",
        height=450,
    )
    return fig


# =============================================================================
# CHART 6 — Top 20 peak 15-min intervals (scatter)
# =============================================================================


def chart_top_peaks(df: pd.DataFrame) -> go.Figure:
    top = df.nlargest(50, SITE_COL).copy()
    top["county_label"] = top[COUNTY_COL].map(COUNTY_LABELS)
    top["label"] = (
        top[BTYPE_COL] + " — " + top["county_label"]
        + "<br>" + top["timestamp"].dt.strftime("%b %d, %H:%M")
    )

    fig = go.Figure()
    for state in sorted(top["state"].unique()):
        sub = top[top["state"] == state]
        fig.add_trace(go.Scatter(
            x=sub["timestamp"],
            y=sub[SITE_COL],
            mode="markers",
            name=state,
            marker={
                "size": 10,
                "color": STATE_COLORS[state],
                "symbol": "circle",
                "opacity": 0.8,
            },
            hovertemplate=(
                "%{customdata}<br>"
                "Site energy: %{y:,.1f} kWh<extra></extra>"
            ),
            customdata=sub["label"],
        ))

    fig.update_layout(
        title="Top 50 Peak 15-min Site Energy Intervals",
        xaxis_title="Date",
        yaxis_title="Site energy (kWh per 15-min interval)",
        yaxis_tickformat=",.0f",
        template="plotly_white",
        height=450,
        legend_title="State",
    )
    return fig


# =============================================================================
# KPI SUMMARY DATA
# =============================================================================


def compute_kpis(df: pd.DataFrame) -> dict:
    peak_row = df.loc[df[SITE_COL].idxmax()]
    return {
        "total_rows": f"{len(df):,}",
        "date_range": f"{df['timestamp'].min().strftime('%b %d, %Y')} – {df['timestamp'].max().strftime('%b %d, %Y')}",
        "n_building_types": str(df[BTYPE_COL].nunique()),
        "n_counties": str(df[COUNTY_COL].nunique()),
        "peak_val": f"{peak_row[SITE_COL]:,.0f} kWh",
        "peak_where": f"{peak_row[BTYPE_COL]}, {COUNTY_LABELS.get(peak_row[COUNTY_COL], peak_row[COUNTY_COL])}",
        "peak_when": peak_row["timestamp"].strftime("%b %d, %H:%M"),
        "null_count": str(int(df.isnull().sum().sum())),
    }


# =============================================================================
# ASSEMBLE HTML
# =============================================================================


def fig_to_json(fig: go.Figure) -> str:
    return pio.to_json(fig, validate=False)


def build_html(
    kpis: dict,
    fig_jsons: dict,
    generated_date: str,
) -> str:

    kpi_cards = "".join(
        f"""<div class="kpi-card">
          <div class="kpi-value">{v}</div>
          <div class="kpi-label">{k}</div>
        </div>"""
        for k, v in [
            ("15-min records", kpis["total_rows"]),
            ("Date range", kpis["date_range"]),
            ("Building types", kpis["n_building_types"]),
            ("Counties", kpis["n_counties"]),
            ("Overall peak", kpis["peak_val"]),
            ("Peak location", kpis["peak_where"]),
            ("Peak time", kpis["peak_when"]),
            ("Null values", kpis["null_count"]),
        ]
    )

    tab_defs = [
        ("tab-peak", "Peak by Building", "peak"),
        ("tab-ts", "Daily Time Series", "ts"),
        ("tab-hourly", "Hourly Profile", "hourly"),
        ("tab-monthly", "Monthly Trends", "monthly"),
        ("tab-mix", "Energy Mix", "mix"),
        ("tab-top", "Top Peaks", "top"),
    ]

    tab_buttons = "".join(
        f'<button class="tab-btn{" active" if i == 0 else ""}" '
        f'onclick="showTab(\'{tid}\')" id="btn-{tid}">{label}</button>'
        for i, (tid, label, _) in enumerate(tab_defs)
    )

    tab_panels = "".join(
        f'<div id="{tid}" class="tab-panel{" active" if i == 0 else ""}">'
        f'<div id="plot-{key}"></div>'
        f'</div>'
        for i, (tid, _, key) in enumerate(tab_defs)
    )

    # Build JS to render each figure
    render_calls = "\n".join(
        f"  Plotly.newPlot('plot-{key}', JSON.parse(figData['{key}']).data, "
        f"JSON.parse(figData['{key}']).layout, {{responsive: true}});"
        for _, _, key in tab_defs
    )

    fig_data_js = "const figData = " + json.dumps({
        key: fig_jsons[key] for _, _, key in tab_defs
    }) + ";"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ComStock Energy Dashboard</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f0f2f5;
      color: #212529;
    }}
    header {{
      background: #1a1a2e;
      color: #fff;
      padding: 18px 32px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    header h1 {{ font-size: 1.4em; font-weight: 600; }}
    header .subtitle {{ font-size: 0.82em; color: #adb5bd; margin-top: 3px; }}
    header .gen-date {{ font-size: 0.78em; color: #6c757d; }}

    .kpi-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      padding: 20px 32px 0;
    }}
    .kpi-card {{
      background: #fff;
      border-radius: 8px;
      padding: 14px 20px;
      min-width: 160px;
      flex: 1;
      box-shadow: 0 1px 4px rgba(0,0,0,0.08);
      border-left: 4px solid #1f77b4;
    }}
    .kpi-value {{ font-size: 1.15em; font-weight: 700; color: #1a1a2e; }}
    .kpi-label {{ font-size: 0.78em; color: #6c757d; margin-top: 3px; }}

    .tab-bar {{
      display: flex;
      gap: 4px;
      padding: 18px 32px 0;
      flex-wrap: wrap;
    }}
    .tab-btn {{
      padding: 8px 18px;
      border: 1px solid #dee2e6;
      background: #fff;
      border-radius: 6px 6px 0 0;
      cursor: pointer;
      font-size: 0.88em;
      color: #495057;
      transition: background 0.15s;
    }}
    .tab-btn:hover {{ background: #e9ecef; }}
    .tab-btn.active {{
      background: #1a1a2e;
      color: #fff;
      border-color: #1a1a2e;
      font-weight: 600;
    }}

    .chart-area {{
      margin: 0 32px 32px;
      background: #fff;
      border-radius: 0 8px 8px 8px;
      padding: 20px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.08);
      min-height: 520px;
    }}
    .tab-panel {{ display: none; }}
    .tab-panel.active {{ display: block; }}

    footer {{
      text-align: center;
      padding: 16px;
      font-size: 0.78em;
      color: #adb5bd;
    }}
  </style>
</head>
<body>

<header>
  <div>
    <h1>ComStock Energy Dashboard</h1>
    <div class="subtitle">End-Use Load Profiles — U.S. Building Stock (2018)</div>
  </div>
  <div class="gen-date">Generated {generated_date}</div>
</header>

<div class="kpi-row">
  {kpi_cards}
</div>

<div class="tab-bar">
  {tab_buttons}
</div>

<div class="chart-area">
  {tab_panels}
</div>

<footer>
  Source: NREL End-Use Load Profiles for the U.S. Building Stock &nbsp;|&nbsp;
  Data: data/processed/combined.csv
</footer>

<script>
{fig_data_js}

function showTab(tabId) {{
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(tabId).classList.add('active');
  document.getElementById('btn-' + tabId).classList.add('active');
  // Trigger plotly resize for the newly visible chart
  const plotDivId = 'plot-' + tabId.replace('tab-', '');
  const plotDiv = document.getElementById(plotDivId);
  if (plotDiv && plotDiv.data) Plotly.relayout(plotDiv, {{}});
}}

// Render all figures on load
window.addEventListener('DOMContentLoaded', () => {{
{render_calls}
}});
</script>
</body>
</html>"""


# =============================================================================
# MAIN
# =============================================================================


def main() -> None:
    os.makedirs(DASHBOARD_DIR, exist_ok=True)
    df = load_data()
    kpis = compute_kpis(df)

    print("Building charts...")
    fig_jsons = {
        "peak": fig_to_json(chart_peak_by_building(df)),
        "ts": fig_to_json(chart_daily_timeseries(df)),
        "hourly": fig_to_json(chart_hourly_heatmap(df)),
        "monthly": fig_to_json(chart_monthly_by_building(df)),
        "mix": fig_to_json(chart_energy_mix(df)),
        "top": fig_to_json(chart_top_peaks(df)),
    }
    for key in fig_jsons:
        print(f"  Built: {key}")

    print("Writing HTML...")
    generated_date = pd.Timestamp.now().strftime("%Y-%m-%d")
    html = build_html(kpis, fig_jsons, generated_date)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved -> {OUTPUT_HTML}")
    print("Done. Open dashboard/index.html in a browser.")


if __name__ == "__main__":
    main()
