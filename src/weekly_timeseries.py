"""
15-minute energy intensity: first week of each quarter.
Interactive standalone HTML dashboard (Datawrapper-inspired).

Reads:  data/processed/combined.csv
Writes: dashboard/weekly_timeseries.html
"""

import datetime
import json
import os

import pandas as pd

# =============================================================================
# PATHS
# =============================================================================

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.normpath(os.path.join(SRC_DIR, ".."))
INPUT_CSV = os.path.join(ROOT_DIR, "data", "processed", "combined.csv")
DASHBOARD_DIR = os.path.join(ROOT_DIR, "dashboard")
OUTPUT_HTML = os.path.join(DASHBOARD_DIR, "weekly_timeseries.html")

# =============================================================================
# CONSTANTS
# =============================================================================

SITE_COL = "out.site_energy.total.energy_consumption.kwh_per_1000sqft"
BTYPE_COL = "in.comstock_building_type"
UPGRADE_COL = "upgrade"

COUNTIES = {
    "CA": {"label": "Orange Co, CA",      "color": "#1d81a2"},
    "CO": {"label": "Denver Co, CO",       "color": "#c0392b"},
    "MI": {"label": "Washtenaw Co, MI",    "color": "#27ae60"},
}

# Datawrapper-style neutral gray for Package 3 overlay
UPGRADE_STYLE = {
    0:  {"dash": "solid",  "opacity": 0.90, "width": 1.8, "label": "Baseline"},
    36: {"dash": "dot",    "opacity": 0.70, "width": 1.5, "label": "Package 3"},
}

# First week of each quarter — strict-start filter (>start, <=end) gives 672 rows
QUARTERS = [
    ("Q1", "2018-01-01", "2018-01-08", "Jan 1–7"),
    ("Q2", "2018-04-01", "2018-04-08", "Apr 1–7"),
    ("Q3", "2018-07-01", "2018-07-08", "Jul 1–7"),
    ("Q4", "2018-10-01", "2018-10-08", "Oct 1–7"),
]

INTERVALS_PER_DAY = 96          # 15-min intervals in 24 h
INTERVALS_PER_WEEK = 7 * INTERVALS_PER_DAY  # 672

DEFAULT_BTYPE = "LargeOffice"

# =============================================================================
# DATA LOADING
# =============================================================================


def load_and_filter() -> pd.DataFrame:
    print(f"Loading {INPUT_CSV} ...")
    df = pd.read_csv(INPUT_CSV, parse_dates=["timestamp"],
                     usecols=["state", BTYPE_COL, UPGRADE_COL, "timestamp", SITE_COL])
    print(f"  Shape: {df.shape}")

    masks = [
        (df["timestamp"] > start) & (df["timestamp"] <= end)
        for _, start, end, _ in QUARTERS
    ]
    combined = masks[0]
    for m in masks[1:]:
        combined = combined | m
    df = df[combined].copy()
    print(f"  After quarter filter: {df.shape}")
    return df


# =============================================================================
# PAYLOAD BUILDER
# =============================================================================


def build_payload(df: pd.DataFrame) -> tuple[list, dict, list]:
    """
    Returns:
      ts_list  – 2688 ISO timestamp strings (canonical order)
      data     – {btype: {state: {"0": [values], "36": [values]}}}
      btypes   – sorted list of building type names
    """
    # Canonical timestamps from a guaranteed-present group
    ref = (
        df[(df["state"] == "CA") & (df[BTYPE_COL] == "FullServiceRestaurant")
           & (df[UPGRADE_COL] == 0)]
        .sort_values("timestamp")["timestamp"]
    )
    ts_list = ref.dt.strftime("%Y-%m-%d %H:%M").tolist()
    n = len(ts_list)

    btypes = sorted(df[BTYPE_COL].unique())

    data: dict = {}
    for btype in btypes:
        data[btype] = {}
        for state in COUNTIES:
            data[btype][state] = {}
            for uid in [0, 36]:
                sub = (
                    df[(df["state"] == state) & (df[BTYPE_COL] == btype)
                       & (df[UPGRADE_COL] == uid)]
                    .sort_values("timestamp")
                )
                if sub.empty or len(sub) != n:
                    data[btype][state][str(uid)] = None
                else:
                    data[btype][state][str(uid)] = [
                        round(v, 3) if pd.notna(v) else None
                        for v in sub[SITE_COL].tolist()
                    ]
    return ts_list, data, btypes


# =============================================================================
# TICK CONFIG
# =============================================================================


def make_tick_config() -> tuple[list, list]:
    """One tick per day (96 intervals apart). Quarter-start ticks are bold."""
    tickvals, ticktext = [], []
    for q_idx, (qid, start_str, _, _label) in enumerate(QUARTERS):
        start_date = datetime.date.fromisoformat(start_str)
        for day in range(7):
            x = q_idx * INTERVALS_PER_WEEK + day * INTERVALS_PER_DAY
            d = start_date + datetime.timedelta(days=day)
            date_label = f"{d.strftime('%b')} {d.day}"
            if day == 0:
                text = f"<b>{qid}</b><br>{date_label}"
            else:
                text = date_label
            tickvals.append(x)
            ticktext.append(text)
    return tickvals, ticktext


# =============================================================================
# HTML GENERATION
# =============================================================================


def build_html(ts_list: list, data: dict, btypes: list) -> str:
    tickvals, ticktext = make_tick_config()
    n_intervals = len(ts_list)

    # Quarter separator x-positions (between weeks)
    separators = [
        INTERVALS_PER_WEEK,
        2 * INTERVALS_PER_WEEK,
        3 * INTERVALS_PER_WEEK,
    ]
    # Quarter label midpoints
    q_mids = [q_idx * INTERVALS_PER_WEEK + INTERVALS_PER_WEEK // 2
              for q_idx in range(4)]
    q_labels = [f"{qid} · {label}" for qid, _, _, label in QUARTERS]

    # Dropdown options (default selected)
    btype_opts = "\n".join(
        f'<option value="{b}"{" selected" if b == DEFAULT_BTYPE else ""}>{b}</option>'
        for b in btypes
    )

    # Serialize for JS
    def js(obj: object) -> str:
        return json.dumps(obj, separators=(",", ":"))

    county_js = js({s: {"label": v["label"], "color": v["color"]}
                    for s, v in COUNTIES.items()})
    upgrade_style_js = js({str(k): v for k, v in UPGRADE_STYLE.items()})

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>15-Min Energy Intensity — First Week of Each Quarter</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: "Roboto", "Helvetica Neue", Arial, sans-serif;
      background: #f9f9f9; color: #333; font-size: 14px; line-height: 1.5;
    }}
    .dw-wrap {{
      max-width: 980px; margin: 0 auto; padding: 24px 16px 48px;
    }}

    /* ── Header ────────────────────────────────────────────────────── */
    .dw-title {{
      font-size: 20px; font-weight: 700; color: #1a1a1a;
      margin-bottom: 4px; line-height: 1.3;
    }}
    .dw-subtitle {{
      font-size: 13px; color: #666; margin-bottom: 14px; max-width: 800px;
    }}

    /* ── Controls ──────────────────────────────────────────────────── */
    .dw-controls {{
      display: flex; flex-wrap: wrap; align-items: flex-start;
      gap: 0; background: #fff;
      border: 1px solid #ddd; border-radius: 3px;
      padding: 10px 14px; margin-bottom: 10px;
    }}
    .ctrl-grp {{
      display: flex; flex-direction: column; gap: 5px;
      padding: 0 14px 0 0; margin-right: 14px;
      border-right: 1px solid #eee;
    }}
    .ctrl-grp:last-of-type {{ border-right: none; }}
    .ctrl-lbl {{
      font-size: 10px; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.06em; color: #999;
    }}
    select#btype-sel {{
      border: 1px solid #ccc; border-radius: 3px; padding: 5px 8px;
      font-size: 13px; background: #fff; color: #333; cursor: pointer;
      min-width: 190px;
    }}
    select#btype-sel:focus {{ outline: none; border-color: #1d81a2; }}
    .cb-list {{
      display: flex; flex-direction: column; gap: 3px;
    }}
    .cb-list label {{
      display: flex; align-items: center; gap: 6px;
      font-size: 13px; color: #333; cursor: pointer; user-select: none;
    }}
    .cb-list input[type=checkbox] {{ cursor: pointer; accent-color: #1d81a2; }}
    .swatch {{ display: inline-block; width: 18px; height: 3px; border-radius: 1px; }}
    .swatch.dashed {{
      background: repeating-linear-gradient(
        90deg, currentColor 0, currentColor 4px, transparent 4px, transparent 7px
      );
      height: 2px;
    }}

    /* ── Download ──────────────────────────────────────────────────── */
    .dl-grp {{
      display: flex; flex-direction: column; gap: 5px;
      margin-left: auto; align-self: center;
      padding-left: 14px;
    }}
    .dl-btn {{
      background: #fff; border: 1px solid #1d81a2; color: #1d81a2;
      border-radius: 3px; padding: 5px 14px; font-size: 12px; font-weight: 600;
      cursor: pointer; white-space: nowrap; transition: background .15s, color .15s;
    }}
    .dl-btn:hover {{ background: #1d81a2; color: #fff; }}

    /* ── Chart ─────────────────────────────────────────────────────── */
    #chart-box {{
      background: #fff; border: 1px solid #ddd; border-radius: 3px;
      padding: 4px 0 0; margin-bottom: 8px;
    }}
    #chart {{ width: 100%; }}

    /* ── Footer ─────────────────────────────────────────────────────── */
    .dw-footer {{
      font-size: 11px; color: #999; line-height: 1.6;
      border-top: 1px solid #e8e8e8; padding-top: 8px;
    }}
    .dw-footer a {{ color: #1d81a2; text-decoration: none; }}
    .dw-footer a:hover {{ text-decoration: underline; }}
    code {{ font-size: 10px; background: #f3f3f3; padding: 1px 3px; border-radius: 2px; }}
  </style>
</head>
<body>
<div class="dw-wrap">

  <!-- ── Header ──────────────────────────────────────────────────────── -->
  <h1 class="dw-title">15-Minute Site Energy Intensity: First Week of Each Quarter</h1>
  <p class="dw-subtitle">
    Modeled commercial building energy use (kWh per 1,000 sq&thinsp;ft per 15-min interval) for
    three U.S. counties. Each panel shows one county. Solid lines = Baseline (existing stock);
    dotted lines = Package&nbsp;3 efficiency measures. Select a building type and toggle
    counties or scenarios below.
  </p>

  <!-- ── Controls ────────────────────────────────────────────────────── -->
  <div class="dw-controls">
    <div class="ctrl-grp">
      <span class="ctrl-lbl">Building Type</span>
      <select id="btype-sel">{btype_opts}</select>
    </div>

    <div class="ctrl-grp">
      <span class="ctrl-lbl">Counties</span>
      <div class="cb-list">
        <label>
          <input type="checkbox" id="cb-CA" checked>
          <span class="swatch" style="background:#1d81a2"></span>
          Orange Co, CA
        </label>
        <label>
          <input type="checkbox" id="cb-CO" checked>
          <span class="swatch" style="background:#c0392b"></span>
          Denver Co, CO
        </label>
        <label>
          <input type="checkbox" id="cb-MI" checked>
          <span class="swatch" style="background:#27ae60"></span>
          Washtenaw Co, MI
        </label>
      </div>
    </div>

    <div class="ctrl-grp">
      <span class="ctrl-lbl">Scenario</span>
      <div class="cb-list">
        <label>
          <input type="checkbox" id="cb-base" checked>
          <span class="swatch" style="background:#555"></span>
          Baseline (solid)
        </label>
        <label>
          <input type="checkbox" id="cb-pkg3" checked>
          <span class="swatch dashed" style="color:#555"></span>
          Package&nbsp;3 (dotted)
        </label>
      </div>
    </div>

    <div class="dl-grp">
      <button class="dl-btn" onclick="dlCSV()">&#8595; Download CSV</button>
      <button class="dl-btn" onclick="dlPNG()">&#8595; Download PNG</button>
    </div>
  </div>

  <!-- ── Chart ───────────────────────────────────────────────────────── -->
  <div id="chart-box">
    <div id="chart"></div>
  </div>

  <!-- ── Footer / citation ───────────────────────────────────────────── -->
  <p class="dw-footer">
    <strong>Source:</strong> NREL End-Use Load Profiles for the U.S. Building Stock
    (<a href="https://www.nrel.gov/buildings/end-use-load-profiles.html" target="_blank">ComStock</a>,
    2018 AMY weather year). Values represent 15-min aggregate site energy intensity
    (kWh&thinsp;/&thinsp;1,000&thinsp;sq&thinsp;ft) normalised by
    <code>floor_area_represented</code> across all ComStock model buildings of the
    selected type within each county. Upgrade 36 = Package&nbsp;3 efficiency measure bundle.
    First week of each quarter: Jan&nbsp;1–7, Apr&nbsp;1–7, Jul&nbsp;1–7, Oct&nbsp;1–7.
    <br>
    <strong>Note:</strong> Washtenaw Co, MI does not include a Hospital building type in this
    dataset. Values are modeled outputs, not measured.
  </p>

</div><!-- /dw-wrap -->

<script>
// ── Embedded data ─────────────────────────────────────────────────────────
const DATA         = {js(data)};
const TIMESTAMPS   = {js(ts_list)};
const COUNTY_INFO  = {county_js};
const UPG_STYLE    = {upgrade_style_js};
const N            = {n_intervals};
const TICKVALS     = {js(tickvals)};
const TICKTEXT     = {js(ticktext)};
const SEPARATORS   = {js(separators)};
const Q_MIDS       = {js(q_mids)};
const Q_LABELS     = {js(q_labels)};
const XARR         = Array.from({{length: N}}, (_, i) => i);

// ── Domain computation ────────────────────────────────────────────────────
function computeDomains(nRows) {{
  if (nRows === 1) return [[0, 1]];
  const gap = 0.06, rowH = (1 - gap * (nRows - 1)) / nRows;
  return Array.from({{length: nRows}}, (_, i) => [
    Math.max(0, 1 - (i + 1) * rowH - i * gap),
    1 - i * (rowH + gap),
  ]);
}}

// ── Build Plotly layout ───────────────────────────────────────────────────
function buildLayout(states) {{
  const n = states.length;
  const domains = computeDomains(n);
  const rowHeight = n === 1 ? 340 : n === 2 ? 280 : 240;
  const totalH = rowHeight * n + 110;

  const layout = {{
    height: totalH,
    margin: {{l: 62, r: 20, t: 36, b: 90}},
    paper_bgcolor: "#fff",
    plot_bgcolor: "#fff",
    showlegend: true,
    legend: {{
      orientation: "h", x: 0, y: -90 / totalH,
      xanchor: "left", yanchor: "top",
      font: {{size: 11, color: "#555", family: '"Roboto","Helvetica Neue",Arial,sans-serif'}},
      bgcolor: "rgba(0,0,0,0)",
    }},
    font: {{family: '"Roboto","Helvetica Neue",Arial,sans-serif', size: 11, color: "#555"}},
    xaxis: {{
      tickvals: TICKVALS, ticktext: TICKTEXT,
      tickfont: {{size: 10, color: "#666"}},
      tickangle: -40,
      gridcolor: "#f0f0f0", gridwidth: 1,
      linecolor: "#ccc", showline: true,
      zeroline: false, domain: [0, 1],
      anchor: "free", position: 0,
    }},
    shapes: [],
    annotations: [],
  }};

  // Quarter separator vertical lines
  SEPARATORS.forEach(x => {{
    layout.shapes.push({{
      type: "line", xref: "x", yref: "paper",
      x0: x, x1: x, y0: 0, y1: 1,
      line: {{color: "#ccc", width: 1, dash: "dot"}},
    }});
  }});

  // Quarter header annotations (above top subplot)
  Q_MIDS.forEach((x, i) => {{
    layout.annotations.push({{
      xref: "x", yref: "paper",
      x: x, y: 1.025,
      text: `<b style="font-size:11px">${{Q_LABELS[i]}}</b>`,
      showarrow: false, xanchor: "center",
      font: {{size: 10, color: "#888"}},
    }});
  }});

  // Per-row yaxis + county label
  states.forEach((state, i) => {{
    const info = COUNTY_INFO[state];
    const axKey = i === 0 ? "yaxis" : `yaxis${{i + 1}}`;
    layout[axKey] = {{
      title: {{text: "kWh / 1,000 sq ft", font: {{size: 10, color: "#888"}}, standoff: 6}},
      domain: domains[i],
      gridcolor: "#f0f0f0", gridwidth: 1,
      linecolor: "#ccc", showline: true,
      zeroline: true, zerolinecolor: "#e0e0e0",
      tickfont: {{size: 10, color: "#666"}},
      rangemode: "tozero",
    }};
    // County label inside plot (top-left of each subplot)
    layout.annotations.push({{
      xref: "paper", yref: "paper",
      x: 0.01, y: domains[i][1] - 0.005,
      text: `<b>${{info.label}}</b>`,
      showarrow: false, xanchor: "left", yanchor: "top",
      bgcolor: "rgba(255,255,255,0.85)", borderpad: 3,
      font: {{size: 12, color: info.color}},
    }});
  }});

  return layout;
}}

// ── Build traces ──────────────────────────────────────────────────────────
function buildTraces(btype, states, showBase, showPkg3) {{
  const traces = [];
  states.forEach((state, rowIdx) => {{
    const info  = COUNTY_INFO[state];
    const yAxis = rowIdx === 0 ? "y" : `y${{rowIdx + 1}}`;
    const grp   = DATA[btype] && DATA[btype][state];
    if (!grp) return;

    [[0, showBase], [36, showPkg3]].forEach(([uid, show]) => {{
      if (!show) return;
      const vals = grp[String(uid)];
      if (!vals || !vals.length) return;
      const sty = UPG_STYLE[String(uid)];
      traces.push({{
        x: XARR, y: vals,
        name: `${{info.label}} — ${{sty.label}}`,
        type: "scatter", mode: "lines",
        line: {{color: info.color, width: sty.width, dash: sty.dash}},
        opacity: sty.opacity,
        xaxis: "x", yaxis: yAxis,
        hovertemplate:
          "%{{customdata}}<br>%{{y:.3f}} kWh/1,000 sq ft" +
          `<extra>${{info.label}} · ${{sty.label}}</extra>`,
        customdata: TIMESTAMPS,
      }});
    }});
  }});
  return traces;
}}

// ── Main render ───────────────────────────────────────────────────────────
function render() {{
  const btype    = document.getElementById("btype-sel").value;
  const showBase = document.getElementById("cb-base").checked;
  const showPkg3 = document.getElementById("cb-pkg3").checked;
  const states   = ["CA","CO","MI"].filter(s =>
    document.getElementById(`cb-${{s}}`).checked
  );
  if (states.length === 0) {{
    Plotly.react("chart", [], {{height: 120, margin: {{l:60,r:20,t:30,b:30}}}});
    return;
  }}
  const traces = buildTraces(btype, states, showBase, showPkg3);
  const layout = buildLayout(states);
  Plotly.react("chart", traces, layout, {{
    responsive: true,
    displayModeBar: true,
    modeBarButtonsToRemove: ["select2d","lasso2d","autoScale2d"],
    displaylogo: false,
    toImageButtonOptions: {{format:"png", width:1400, scale:2}},
  }});
}}

// ── Download CSV ──────────────────────────────────────────────────────────
function dlCSV() {{
  const btype    = document.getElementById("btype-sel").value;
  const showBase = document.getElementById("cb-base").checked;
  const showPkg3 = document.getElementById("cb-pkg3").checked;
  const states   = ["CA","CO","MI"].filter(s =>
    document.getElementById(`cb-${{s}}`).checked
  );
  const scenarios = [];
  if (showBase) scenarios.push([0,  "Baseline"]);
  if (showPkg3) scenarios.push([36, "Package 3"]);

  const rows = ["timestamp,county,state,building_type,scenario,site_energy_kwh_per_1000sqft"];
  states.forEach(state => {{
    const info = COUNTY_INFO[state];
    scenarios.forEach(([uid, ulabel]) => {{
      const vals = DATA[btype]?.[state]?.[String(uid)];
      if (!vals) return;
      vals.forEach((v, i) => {{
        rows.push([
          TIMESTAMPS[i],
          `"${{info.label}}"`,
          state, btype, ulabel,
          v === null ? "" : v,
        ].join(","));
      }});
    }});
  }});

  const blob = new Blob([rows.join("\\n")], {{type:"text/csv;charset=utf-8;"}});
  const a = Object.assign(document.createElement("a"), {{
    href: URL.createObjectURL(blob),
    download: `comstock_${{btype}}_quarterly_weeks.csv`,
  }});
  a.click(); URL.revokeObjectURL(a.href);
}}

// ── Download PNG ──────────────────────────────────────────────────────────
function dlPNG() {{
  const btype  = document.getElementById("btype-sel").value;
  const states = ["CA","CO","MI"].filter(s =>
    document.getElementById(`cb-${{s}}`).checked
  );
  Plotly.downloadImage("chart", {{
    format: "png", scale: 2,
    width: 1300,
    height: document.getElementById("chart").offsetHeight,
    filename: `comstock_${{btype}}_quarterly_weeks`,
  }});
}}

// ── Wire events ───────────────────────────────────────────────────────────
["btype-sel","cb-CA","cb-CO","cb-MI","cb-base","cb-pkg3"].forEach(id =>
  document.getElementById(id).addEventListener("change", render)
);
render();
</script>
</body>
</html>"""


# =============================================================================
# MAIN
# =============================================================================


def main() -> None:
    os.makedirs(DASHBOARD_DIR, exist_ok=True)

    df = load_and_filter()
    ts_list, data, btypes = build_payload(df)
    print(f"Building payload: {len(btypes)} building types, {len(ts_list)} timestamps")

    html = build_html(ts_list, data, btypes)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    size_kb = os.path.getsize(OUTPUT_HTML) / 1024
    print(f"Saved -> {OUTPUT_HTML}  ({size_kb:.0f} KB)")
    print("Done. Open dashboard/weekly_timeseries.html in a browser.")


if __name__ == "__main__":
    main()
