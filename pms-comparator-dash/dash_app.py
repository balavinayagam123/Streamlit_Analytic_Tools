import base64
import io
import itertools
import json

import dash
from dash import dcc, html, dash_table, Input, Output, State, ctx, no_update
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ─────────────────────────────────────────────────────────────────────────────
# APP INIT — Bootstrap theme for proper grid + components
# ─────────────────────────────────────────────────────────────────────────────

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.FLATLY],
    title="Sister Vessel PMS Comparison",
    suppress_callback_exceptions=True,
)
server = app.server   # expose for gunicorn / Render deployment

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

VESSEL_COLORS = ["#0066cc", "#ff7700", "#27a060", "#9b59b6"]
MAX_VESSELS   = 4
NAV_BRAND_COLOR = "#0a2540"

# ─────────────────────────────────────────────────────────────────────────────
# ANALYSIS HELPERS  (identical logic to Streamlit version)
# ─────────────────────────────────────────────────────────────────────────────

def load_csv(bytes_data):
    df = pd.read_csv(io.BytesIO(bytes_data), header=0, dtype=str)
    cols = df.columns.tolist()
    cols[1] = "Critical"
    df.columns = cols
    if "Unnamed: 2" in df.columns:
        df = df.drop(columns=["Unnamed: 2"])
    for col in ["Job Code","Machinery Location","Sub Component Location",
                "Frequency","Job Action","Title","Function","Department","Vessel"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    return df


def get_vessel_name(df):
    if "Vessel" in df.columns:
        names = [n for n in df["Vessel"].dropna().unique() if n not in ("","nan")]
        if names:
            return names[0]
    return "Vessel"


def make_key(df):
    KEY = ["Job Code","Machinery Location","Sub Component Location","Title"]
    return df[KEY].fillna("").apply(lambda r: "|||".join(r.values), axis=1)


def compare_pair(df_x, df_y, nx, ny):
    df_x = df_x.copy(); df_x["_key"] = make_key(df_x)
    df_y = df_y.copy(); df_y["_key"] = make_key(df_y)
    sx, sy = set(df_x["_key"]), set(df_y["_key"])
    cols = ["Job Code","Critical","Machinery Location","Sub Component Location",
            "Frequency","Job Action","Title","Function","Department"]
    mj = df_x[df_x["_key"].isin(sx-sy)][[c for c in cols if c in df_x.columns]].copy()
    mi = df_y[df_y["_key"].isin(sy-sx)][[c for c in cols if c in df_y.columns]].copy()
    common = sx & sy
    merged = pd.merge(
        df_x[df_x["_key"].isin(common)][["_key","Job Code","Critical","Machinery Location",
                                          "Sub Component Location","Frequency","Job Action",
                                          "Title","Function","Department"]],
        df_y[df_y["_key"].isin(common)][["_key","Frequency"]],
        on="_key", suffixes=(f" ({nx})",f" ({ny})")
    )
    fa, fb = f"Frequency ({nx})", f"Frequency ({ny})"
    fm = merged[merged[fa]!=merged[fb]][[
        "Job Code","Critical","Machinery Location","Sub Component Location",
        fa,fb,"Job Action","Title","Function","Department"
    ]].copy()
    return mj, mi, fm


def freq_sort_key(f):
    try:
        num, unit = str(f).strip().split(" ",1)
        num = float(num); unit = unit.lower()
        if "day"   in unit: return num
        if "month" in unit: return num*30
        if "hour"  in unit: return num/24
        if "year"  in unit: return num*365
    except Exception:
        pass
    return 99999


def to_excel_bytes(dfs: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet, df in dfs.items():
            df.to_excel(writer, sheet_name=sheet[:31], index=False)
    return buf.getvalue()


def make_datatable(df, table_id, freq_cols=None):
    """Build a Dash DataTable with critical-row + freq-cell colouring."""
    freq_cols = freq_cols or []
    style_data_conditional = [
        {
            "if": {"filter_query": '{Critical} = "C"'},
            "backgroundColor": "#ffe0e0",
            "color": "#900",
        }
    ]
    for fc in freq_cols:
        style_data_conditional.append({
            "if": {"column_id": fc},
            "backgroundColor": "#fff3cd",
            "color": "#7a5900",
            "fontWeight": "bold",
        })
        style_data_conditional.append({
            "if": {"filter_query": '{Critical} = "C"', "column_id": fc},
            "backgroundColor": "#ff9900",
            "color": "#000",
            "fontWeight": "bold",
        })

    cols = [{"name": c, "id": c} for c in df.columns]
    return dash_table.DataTable(
        id=table_id,
        columns=cols,
        data=df.to_dict("records"),
        style_data_conditional=style_data_conditional,
        style_header={
            "backgroundColor": NAV_BRAND_COLOR,
            "color": "white",
            "fontWeight": "bold",
            "fontSize": "12px",
        },
        style_cell={
            "fontSize": "12px",
            "padding": "6px 10px",
            "textAlign": "left",
            "whiteSpace": "normal",
            "height": "auto",
            "maxWidth": "220px",
            "overflow": "hidden",
            "textOverflow": "ellipsis",
        },
        style_table={"overflowX": "auto"},
        page_size=20,
        sort_action="native",
        filter_action="native",
        tooltip_data=[
            {col: {"value": str(row[col]), "type": "markdown"}
             for col in df.columns}
            for row in df.to_dict("records")
        ],
        tooltip_duration=None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# LAYOUT
# ─────────────────────────────────────────────────────────────────────────────

navbar = dbc.Navbar(
    dbc.Container([
        html.Span("🚢", style={"fontSize":"1.6rem","marginRight":"10px"}),
        dbc.NavbarBrand("Sister Vessel PMS Comparison",
                        style={"fontWeight":"700","fontSize":"1.2rem","color":"white"}),
        dbc.Nav(
            dbc.NavItem(html.Small(
                "Upload 2–4 JiBe PMS exports to identify missing jobs & frequency mismatches",
                style={"color":"rgba(255,255,255,0.7)","marginLeft":"20px"}
            )),
            navbar=True,
        ),
    ], fluid=True),
    color=NAV_BRAND_COLOR,
    dark=True,
    sticky="top",
    style={"marginBottom":"0"},
)

upload_panel = dbc.Card([
    dbc.CardHeader(html.B("📂 Upload PMS Exports"), style={"backgroundColor":NAV_BRAND_COLOR,"color":"white"}),
    dbc.CardBody([
        html.P("Upload 2–4 JiBe CSV exports. Vessel names are auto-detected from the file.",
               className="text-muted small"),
        *[
            html.Div([
                html.Label(f"Vessel {i+1}", className="fw-bold small"),
                dcc.Upload(
                    id=f"upload-{i}",
                    children=html.Div([
                        html.Span("📎 ", style={"fontSize":"1.2rem"}),
                        html.Span("Drag & drop or "),
                        html.A("browse", style={"color":VESSEL_COLORS[i],"fontWeight":"bold"}),
                    ]),
                    style={
                        "width":"100%","padding":"12px","borderRadius":"8px",
                        "border":f"2px dashed {VESSEL_COLORS[i]}",
                        "textAlign":"center","cursor":"pointer",
                        "backgroundColor":"#f8f9fa","marginBottom":"4px",
                        "fontSize":"13px",
                    },
                    accept=".csv",
                ),
                html.Div(id=f"upload-name-{i}", className="text-muted small mb-2"),
            ])
            for i in range(MAX_VESSELS)
        ],
        html.Hr(),
        dbc.Button("🔍 Run Comparison", id="run-btn", color="primary",
                   className="w-100 fw-bold", size="lg"),
        html.Div(id="upload-error", className="mt-2"),
    ])
], style={"position":"sticky","top":"60px","borderRadius":"12px","boxShadow":"0 2px 12px rgba(0,0,0,0.1)"})

app.layout = html.Div([
    navbar,
    dbc.Container([
        dbc.Row([
            # Left sidebar
            dbc.Col(upload_panel, width=3, className="mt-3"),

            # Main content
            dbc.Col([
                html.Div(id="main-content", className="mt-3"),
            ], width=9),
        ]),
    ], fluid=True, className="px-4"),

    # Hidden stores
    dcc.Store(id="store-vessels"),     # JSON list of vessel data + names
    dcc.Store(id="store-pairs"),       # JSON pair results
    dcc.Store(id="store-pivot"),       # machinery pivot
])


# ─────────────────────────────────────────────────────────────────────────────
# CALLBACK: track upload filenames
# ─────────────────────────────────────────────────────────────────────────────

for i in range(MAX_VESSELS):
    @app.callback(
        Output(f"upload-name-{i}", "children"),
        Input(f"upload-{i}", "filename"),
        prevent_initial_call=True,
    )
    def show_filename(name, _i=i):
        if name:
            return html.Span(f"✅ {name}", style={"color": VESSEL_COLORS[_i]})
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# CALLBACK: Run comparison → populate stores
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(
    Output("store-vessels", "data"),
    Output("store-pairs",   "data"),
    Output("store-pivot",   "data"),
    Output("upload-error",  "children"),
    Input("run-btn", "n_clicks"),
    [State(f"upload-{i}", "contents") for i in range(MAX_VESSELS)],
    [State(f"upload-{i}", "filename") for i in range(MAX_VESSELS)],
    prevent_initial_call=True,
)
def run_comparison(n_clicks, *args):
    contents_list = list(args[:MAX_VESSELS])
    active = [(c, f) for c, f in zip(contents_list, args[MAX_VESSELS:]) if c is not None]

    if len(active) < 2:
        return no_update, no_update, no_update, dbc.Alert(
            "Please upload at least 2 vessel CSV files.", color="warning", dismissable=True
        )

    # Decode and parse
    vessels_df, vessel_names = [], []
    for content, fname in active:
        _, b64 = content.split(",", 1)
        raw = base64.b64decode(b64)
        df  = load_csv(raw)
        vessels_df.append(df)
        vessel_names.append(get_vessel_name(df))

    # Store vessel data as JSON
    vessel_store = [
        {"name": vessel_names[i], "data": vessels_df[i].to_json(orient="split")}
        for i in range(len(vessels_df))
    ]

    # Pairwise comparison
    pairs = list(itertools.combinations(range(len(vessels_df)), 2))
    pair_store = {}
    for i, j in pairs:
        mj, mi, fm = compare_pair(vessels_df[i], vessels_df[j], vessel_names[i], vessel_names[j])
        pair_store[f"{i}_{j}"] = {
            "miss_j": mj.to_json(orient="split"),
            "miss_i": mi.to_json(orient="split"),
            "freq_mm": fm.to_json(orient="split"),
        }

    # Machinery pivot
    mach_frames = []
    for df, name in zip(vessels_df, vessel_names):
        if "Machinery Location" not in df.columns:
            continue
        counts = df.groupby("Machinery Location").size().reset_index(name=name)
        mach_frames.append(counts.set_index("Machinery Location"))

    pivot_json = None
    if mach_frames:
        pivot = mach_frames[0]
        for frame in mach_frames[1:]:
            pivot = pivot.join(frame, how="outer")
        pivot = pivot.reset_index().sort_values("Machinery Location").reset_index(drop=True)
        for name in vessel_names:
            if name in pivot.columns:
                pivot[name] = pd.to_numeric(pivot[name], errors="coerce")
        pivot["Total (All Vessels)"] = pivot[vessel_names].sum(axis=1, skipna=True).astype(int)
        pivot_json = pivot.to_json(orient="split")

    return vessel_store, pair_store, pivot_json, ""


# ─────────────────────────────────────────────────────────────────────────────
# CALLBACK: Render main content from stores
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(
    Output("main-content", "children"),
    Input("store-vessels", "data"),
    Input("store-pairs",   "data"),
    Input("store-pivot",   "data"),
    prevent_initial_call=True,
)
def render_content(vessel_store, pair_store, pivot_json):
    if not vessel_store or not pair_store:
        return dbc.Alert("Upload files and click Run Comparison.", color="info")

    # Reconstruct DataFrames
    vessels_df   = [pd.read_json(v["data"], orient="split") for v in vessel_store]
    vessel_names = [v["name"] for v in vessel_store]
    n_vessels    = len(vessels_df)
    color_map    = {vessel_names[i]: VESSEL_COLORS[i] for i in range(n_vessels)}
    pairs        = list(itertools.combinations(range(n_vessels), 2))

    pair_results = {}
    for i, j in pairs:
        pr = pair_store[f"{i}_{j}"]
        pair_results[(i,j)] = (
            pd.read_json(pr["miss_j"], orient="split"),
            pd.read_json(pr["miss_i"], orient="split"),
            pd.read_json(pr["freq_mm"], orient="split"),
        )

    pivot = pd.read_json(pivot_json, orient="split") if pivot_json else pd.DataFrame()

    # ── Fleet summary cards ───────────────────────────────────────────────────
    summary_cards = dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardBody([
                html.Div(vessel_names[i], className="fw-bold",
                         style={"color": VESSEL_COLORS[i], "fontSize":"15px"}),
                html.H3(len(vessels_df[i]), className="mb-0"),
                html.Small("Total Jobs", className="text-muted"),
                html.Hr(className="my-1"),
                html.H4(int((vessels_df[i]["Critical"]=="C").sum())
                        if "Critical" in vessels_df[i].columns else 0,
                        style={"color":"#d9534f"}, className="mb-0"),
                html.Small("Critical Jobs", className="text-muted"),
            ])
        ], style={"borderTop": f"4px solid {VESSEL_COLORS[i]}",
                  "borderRadius":"10px","textAlign":"center",
                  "boxShadow":"0 2px 8px rgba(0,0,0,0.08)"}),
        width=12//n_vessels) for i in range(n_vessels)
    ], className="mb-3")

    # ── Pair selector ─────────────────────────────────────────────────────────
    pair_labels   = [f"{vessel_names[i]}  ↔  {vessel_names[j]}" for i,j in pairs]
    pair_selector = dbc.Row([
        dbc.Col([
            html.H5("🔍 Pairwise Comparison", className="fw-bold"),
            dbc.Select(
                id="pair-select",
                options=[{"label": l, "value": l} for l in pair_labels],
                value=pair_labels[0],
                style={"maxWidth":"450px","marginBottom":"16px"},
            ),
        ])
    ])

    # Pre-render first pair for initial load
    si, sj = pairs[0]
    mj, mi, fm = pair_results[(si, sj)]
    fa = f"Frequency ({vessel_names[si]})"
    fb = f"Frequency ({vessel_names[sj]})"

    def pair_metrics(mj, mi, fm, ni, nj):
        crit_mj = int((mj["Critical"]=="C").sum()) if "Critical" in mj.columns else 0
        crit_mi = int((mi["Critical"]=="C").sum()) if "Critical" in mi.columns else 0
        def kpi(label, val, danger=True):
            color = "#d9534f" if danger and val > 0 else "#27a060"
            return dbc.Col(dbc.Card(dbc.CardBody([
                html.Div(label, className="text-muted small"),
                html.H3(val, style={"color":color}, className="mb-0"),
            ]), style={"borderRadius":"8px","textAlign":"center",
                       "boxShadow":"0 1px 6px rgba(0,0,0,0.07)"}))
        return dbc.Row([
            kpi(f"Missing in {nj}", len(mj)),
            kpi(f"Missing in {ni}", len(mi)),
            kpi("Freq Mismatches", len(fm)),
            kpi(f"Critical ∅ in {nj}", crit_mj),
            kpi(f"Critical ∅ in {ni}", crit_mi),
        ], className="mb-3 g-2")

    pair_kpis = pair_metrics(mj, mi, fm, vessel_names[si], vessel_names[sj])

    pair_tabs = dbc.Tabs([
        dbc.Tab(
            html.Div([
                html.P([html.Span("🔴 Red rows = Critical jobs", className="text-danger small")],
                       className="mt-2 mb-1"),
                make_datatable(mj.reset_index(drop=True), "tbl-miss-j"),
            ], className="p-2"),
            label=f"❌ Missing in {vessel_names[sj]} ({len(mj)})",
            tab_id="t1",
        ),
        dbc.Tab(
            html.Div([
                html.P([html.Span("🔴 Red rows = Critical jobs", className="text-danger small")],
                       className="mt-2 mb-1"),
                make_datatable(mi.reset_index(drop=True), "tbl-miss-i"),
            ], className="p-2"),
            label=f"❌ Missing in {vessel_names[si]} ({len(mi)})",
            tab_id="t2",
        ),
        dbc.Tab(
            html.Div([
                html.P("🟡 Amber = frequency columns  |  🔴 Red = Critical",
                       className="text-muted small mt-2 mb-1"),
                make_datatable(fm.reset_index(drop=True), "tbl-freq", freq_cols=[fa, fb]),
            ], className="p-2"),
            label=f"⚠️ Freq Mismatches ({len(fm)})",
            tab_id="t3",
        ),
    ], id="pair-tabs", active_tab="t1",
       style={"borderBottom":"2px solid #dee2e6"})

    # ── Fleet analytics ───────────────────────────────────────────────────────

    # Gap matrix
    matrix_data = []
    for i in range(n_vessels):
        row = {}
        for j in range(n_vessels):
            if i == j:
                row[vessel_names[j]] = "—"
            elif i < j:
                mj2, mi2, _ = pair_results[(i,j)]
                row[vessel_names[j]] = f"{len(mj2)} / {len(mi2)}"
            else:
                mj2, mi2, _ = pair_results[(j,i)]
                row[vessel_names[j]] = f"{len(mi2)} / {len(mj2)}"
        row["Vessel"] = vessel_names[i]
        matrix_data.append(row)
    matrix_df = pd.DataFrame(matrix_data).set_index("Vessel").reset_index()

    mismatch_rows = []
    for i,j in pairs:
        _,_,fm2 = pair_results[(i,j)]
        mismatch_rows.append({
            "Vessel Pair": f"{vessel_names[i]}  ↔  {vessel_names[j]}",
            "Freq Mismatches": len(fm2),
            "Critical Mismatches": int((fm2["Critical"]=="C").sum()) if "Critical" in fm2.columns else 0,
        })

    gap_matrix_tab = html.Div([
        html.H6("Pairwise Gap Matrix", className="fw-bold mt-3"),
        html.P("Format: Missing in column vessel / Missing in row vessel",
               className="text-muted small"),
        make_datatable(matrix_df, "tbl-matrix"),
        html.H6("Frequency Mismatch Summary", className="fw-bold mt-4"),
        make_datatable(pd.DataFrame(mismatch_rows), "tbl-mm-summary"),
    ])

    # Department gap charts
    dept_charts = []
    for i,j in pairs:
        mj2, mi2, _ = pair_results[(i,j)]
        ni, nj = vessel_names[i], vessel_names[j]
        sides = []
        for df_miss, missing_from in [(mj2, nj), (mi2, ni)]:
            if df_miss.empty or "Department" not in df_miss.columns:
                sides.append(dbc.Col(dbc.Alert(f"No missing jobs in {missing_from}.", color="success"), width=6))
                continue
            grp = df_miss.groupby("Department").agg(
                Critical=("Critical", lambda x: (x=="C").sum()),
                Total=("Job Code","count")
            ).reset_index()
            grp["Non-Critical"] = grp["Total"] - grp["Critical"]
            fig = go.Figure()
            fig.add_bar(x=grp["Department"], y=grp["Critical"],   name="Critical",     marker_color="#d9534f")
            fig.add_bar(x=grp["Department"], y=grp["Non-Critical"],name="Non-Critical", marker_color="#5bc0de")
            fig.update_layout(barmode="stack", height=260,
                              margin=dict(t=30,b=20,l=30,r=10),
                              legend=dict(orientation="h",y=1.1),
                              title=f"Missing in {missing_from}")
            sides.append(dbc.Col([dcc.Graph(figure=fig, config={"displayModeBar":False})], width=6))
        dept_charts.append(dbc.Card([
            dbc.CardHeader(html.B(f"{ni}  ↔  {nj}"),
                           style={"backgroundColor":"#f0f4f8"}),
            dbc.CardBody(dbc.Row(sides)),
        ], className="mb-3", style={"borderRadius":"10px"}))

    dept_tab = html.Div(dept_charts)

    # Frequency distribution
    dist_frames = []
    for df, name in zip(vessels_df, vessel_names):
        if "Frequency" not in df.columns:
            continue
        counts = df["Frequency"].value_counts().reset_index()
        counts.columns = ["Frequency","Count"]
        counts["Vessel"] = name
        dist_frames.append(counts)

    freq_tab = html.Div()
    if dist_frames:
        dist_all   = pd.concat(dist_frames, ignore_index=True)
        freq_order = (dist_all.assign(_s=dist_all["Frequency"].apply(freq_sort_key))
                      .drop_duplicates("Frequency").sort_values("_s")["Frequency"].tolist())
        fig_dist = px.bar(dist_all, x="Frequency", y="Count", color="Vessel",
                          barmode="group",
                          category_orders={"Frequency": freq_order},
                          color_discrete_map=color_map,
                          labels={"Count":"Number of Jobs","Frequency":"Maintenance Interval"},
                          height=420)
        fig_dist.update_layout(legend=dict(orientation="h",y=1.02),
                               xaxis_tickangle=-45, margin=dict(t=40,b=100))

        all_freqs  = [set(df["Frequency"].dropna().unique()) for df in vessels_df]
        common_all = set.intersection(*all_freqs)
        uniq_cols  = []
        for i2, (name2, freqs2) in enumerate(zip(vessel_names, all_freqs)):
            unique_to = freqs2 - common_all
            if unique_to and i2 < len(dist_frames):
                udf = dist_frames[i2][dist_frames[i2]["Frequency"].isin(unique_to)][["Frequency","Count"]]
                uniq_cols.append(dbc.Col([
                    html.B(name2, style={"color": VESSEL_COLORS[i2]}),
                    make_datatable(udf.reset_index(drop=True), f"tbl-uniq-{i2}"),
                ], width=12//n_vessels))

        freq_tab = html.Div([
            dcc.Graph(figure=fig_dist, config={"displayModeBar": False}),
            html.H6("Intervals unique to each vessel", className="fw-bold mt-3"),
            dbc.Row(uniq_cols) if uniq_cols else dbc.Alert("All vessels share the same intervals.", color="success"),
        ])

    # Machinery pivot tab
    pivot_tab = html.Div()
    if not pivot.empty:
        vessel_cols = [c for c in vessel_names if c in pivot.columns]
        missing_counts = {n: int(pivot[n].isna().sum()) for n in vessel_cols}

        kpi_cards = dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Total Unique Machineries", className="text-muted small"),
                html.H3(len(pivot), className="mb-0"),
            ]), style={"borderRadius":"8px","textAlign":"center"}), width=2),
            *[
                dbc.Col(dbc.Card(dbc.CardBody([
                    html.Div(f"Not in {n}", className="text-muted small"),
                    html.H3(missing_counts[n],
                            style={"color":"#d9534f" if missing_counts[n]>0 else "#27a060"},
                            className="mb-0"),
                ]), style={"borderRadius":"8px","textAlign":"center",
                           "borderTop":f"3px solid {VESSEL_COLORS[idx]}"}),
                width=2)
                for idx, n in enumerate(vessel_cols)
            ]
        ], className="mb-3 g-2")

        # Style pivot table cells
        style_pivot = [
            {"if": {"column_id": n, "filter_query": f"{{{n}}} is blank"},
             "backgroundColor": "#ffe0e0", "color": "#900"}
            for n in vessel_cols
        ] + [
            {"if": {"column_id": "Total (All Vessels)"},
             "fontWeight": "bold", "backgroundColor": "#f0f4f8"}
        ]

        pivot_display = pivot.copy()
        for n in vessel_cols:
            pivot_display[n] = pivot_display[n].apply(
                lambda v: "" if pd.isna(v) else str(int(v))
            )

        pivot_tbl = dash_table.DataTable(
            id="tbl-pivot",
            columns=[{"name": c, "id": c} for c in pivot_display.columns],
            data=pivot_display.to_dict("records"),
            style_data_conditional=style_pivot,
            style_header={
                "backgroundColor": NAV_BRAND_COLOR, "color": "white",
                "fontWeight": "bold", "fontSize": "12px",
            },
            style_cell={
                "fontSize": "12px", "padding": "6px 10px",
                "textAlign": "left", "maxWidth": "200px",
                "overflow": "hidden", "textOverflow": "ellipsis",
            },
            style_table={"overflowX": "auto"},
            page_size=25,
            sort_action="native",
            filter_action="native",
            tooltip_header={"Machinery Location": "Filter using the row below ↓"},
        )

        pivot_tab = html.Div([kpi_cards, pivot_tbl])

    # ── Fleet analytics tabs ──────────────────────────────────────────────────
    fleet_tabs = dbc.Card([
        dbc.CardHeader(html.H5("📊 Fleet-Wide Analytics", className="mb-0 fw-bold"),
                       style={"backgroundColor":"#f8f9fa"}),
        dbc.CardBody(
            dbc.Tabs([
                dbc.Tab(gap_matrix_tab, label="📋 Gap Matrix",           tab_id="f1"),
                dbc.Tab(dept_tab,       label="📊 Department Gap",        tab_id="f2"),
                dbc.Tab(freq_tab,       label="📈 Frequency Distribution", tab_id="f3"),
                dbc.Tab(pivot_tab,      label="🔩 Machinery Job Count",    tab_id="f4"),
            ], active_tab="f1", style={"borderBottom":"2px solid #dee2e6"})
        )
    ], className="mt-4", style={"borderRadius":"12px","boxShadow":"0 2px 12px rgba(0,0,0,0.08)"})

    # ── Download button ───────────────────────────────────────────────────────
    download_section = dbc.Row(
        dbc.Col(
            html.Div([
                dbc.Button("📥 Download Full Report (.xlsx)", id="download-btn",
                           color="success", className="fw-bold", size="lg"),
                dcc.Download(id="download-xlsx"),
            ], className="d-flex justify-content-end mt-3"),
        )
    )

    return html.Div([
        summary_cards,
        dbc.Card([
            dbc.CardBody([pair_selector, pair_kpis, pair_tabs])
        ], style={"borderRadius":"12px","boxShadow":"0 2px 12px rgba(0,0,0,0.08)"}),
        fleet_tabs,
        download_section,
    ])


# ─────────────────────────────────────────────────────────────────────────────
# CALLBACK: Download
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(
    Output("download-xlsx", "data"),
    Input("download-btn", "n_clicks"),
    State("store-vessels", "data"),
    State("store-pairs",   "data"),
    State("store-pivot",   "data"),
    prevent_initial_call=True,
)
def download_report(n_clicks, vessel_store, pair_store, pivot_json):
    if not vessel_store or not pair_store:
        return no_update

    vessel_names = [v["name"] for v in vessel_store]
    n = len(vessel_names)
    pairs = list(itertools.combinations(range(n), 2))

    sheets = {}
    for i, j in pairs:
        pr  = pair_store[f"{i}_{j}"]
        ni, nj = vessel_names[i], vessel_names[j]
        sheets[f"Missing in {nj}"[:31]]         = pd.read_json(pr["miss_j"], orient="split")
        sheets[f"Missing in {ni}"[:31]]         = pd.read_json(pr["miss_i"], orient="split")
        sheets[f"FreqMM {ni[:8]}-{nj[:8]}"[:31]] = pd.read_json(pr["freq_mm"], orient="split")

    if pivot_json:
        sheets["Machinery Job Count"] = pd.read_json(pivot_json, orient="split")

    raw  = to_excel_bytes(sheets)
    b64  = base64.b64encode(raw).decode()
    pair_str = "_".join(vessel_names)
    return {"base64": True, "content": b64,
            "filename": f"PMS_Comparison_{pair_str[:50]}.xlsx",
            "type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=False)
