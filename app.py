"""TMR Municipal Budget Tracker — who to call this month, based on each
government's fiscal-year budget cycle (all 50 states + DC)."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

from cycle import DEFAULT_WINDOWS, MONTHS, PHASES, phase_for, window_text

DATA = Path(__file__).parent / "data" / "governments.csv"
META = Path(__file__).parent / "data" / "meta.json"
TMR_GREEN = "#083400"

st.set_page_config(page_title="TMR Budget Tracker", page_icon="📞", layout="wide")
# TMR brand theme. Built into the app so it works even if the hidden .streamlit/ folder
# doesn't make it into the GitHub repo.
TMR_GREEN_LIGHT = "#eef4ec"
st.markdown(f"""<style>
/* Header bar */
.tmr-bar {{ background: {TMR_GREEN}; color: #fff; padding: 18px 24px; border-radius: 10px; margin-bottom: 18px; }}
.tmr-bar h1 {{ color: #fff !important; margin: 0; padding: 0; font-size: 1.9rem; }}
.tmr-bar p {{ color: #d7e5d2; margin: 4px 0 0; font-size: 0.95rem; }}
h2, h3 {{ color: {TMR_GREEN}; }}
/* Sidebar */
section[data-testid="stSidebar"] {{ background: {TMR_GREEN_LIGHT}; border-right: 3px solid {TMR_GREEN}; }}
section[data-testid="stSidebar"] h2 {{ color: {TMR_GREEN}; }}
/* Metric cards */
div[data-testid="stMetric"] {{ background: #fff; border: 1px solid #dde3da; border-left: 5px solid {TMR_GREEN};
    border-radius: 8px; padding: 10px 14px; }}
div[data-testid="stMetricValue"] {{ color: {TMR_GREEN}; }}
/* Buttons */
.stButton > button, .stDownloadButton > button {{ background: {TMR_GREEN}; color: #fff; border: 1px solid {TMR_GREEN}; }}
.stButton > button:hover, .stDownloadButton > button:hover {{ background: #1d5a12; color: #fff; border-color: #1d5a12; }}
/* Multiselect chips */
span[data-baseweb="tag"] {{ background-color: {TMR_GREEN} !important; color: #fff !important; }}
/* Tabs */
button[data-baseweb="tab"][aria-selected="true"] p {{ color: {TMR_GREEN}; font-weight: 700; }}
div[data-baseweb="tab-highlight"] {{ background-color: {TMR_GREEN}; }}
/* Inputs: focus ring */
div[data-baseweb="input"]:focus-within, div[data-baseweb="select"] > div:focus-within {{ border-color: {TMR_GREEN} !important; }}
</style>""", unsafe_allow_html=True)

STATE_NAMES = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", "CALIFORNIA": "CA", "COLORADO": "CO",
    "CONNECTICUT": "CT", "DELAWARE": "DE", "DISTRICT OF COLUMBIA": "DC", "FLORIDA": "FL", "GEORGIA": "GA",
    "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS",
    "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA",
    "MICHIGAN": "MI", "MINNESOTA": "MN", "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT",
    "NEBRASKA": "NE", "NEVADA": "NV", "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM",
    "NEW YORK": "NY", "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK",
    "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY",
}


@st.cache_data
def load() -> pd.DataFrame:
    df = pd.read_csv(DATA)
    df["size"] = df["population"].where(df["population"] > 0, df["enrollment"])
    df.loc[df["type"] == "Park District", "size"] = pd.NA  # park districts don't report population
    # Ranking score: people served, or for park districts ~1 "resident" per $100 of parks spending
    df["rank_score"] = df["size"].fillna(df["parks_spend"] / 100)
    # Census parks & rec spending only applies to cities/counties/townships
    df["parks_spend"] = df["parks_spend"].astype(float)
    df.loc[df["type"].isin(["School District", "Community College"]), "parks_spend"] = float("nan")
    df["parks_m"] = (df["parks_spend"] / 1e6).round(1)
    return df


def key(name: str) -> str:
    s = str(name).upper()
    s = re.sub(r"\b(CITY|TOWN|VILLAGE|BOROUGH|TOWNSHIP|TWP|OF|THE|PARKS?|AND|RECREATION|REC|DEPARTMENT|DEPT|"
               r"GOVERNMENT|GOV|COUNTY|CO|SCHOOLS?|SCH|DISTRICT|DIST|PUBLIC|ISD|USD|INC|LLC)\b", " ", s)
    return re.sub(r"[^A-Z0-9]", "", s)


def hubspot_keys(file) -> set[str]:
    hs = pd.read_csv(file, dtype=str).fillna("")
    cols = {c.lower(): c for c in hs.columns}
    name_col = next((cols[c] for c in ["company name", "name", "company"] if c in cols), None)
    state_col = next((cols[c] for c in ["state/region", "state", "region"] if c in cols), None)
    if not name_col:
        st.sidebar.error("Couldn't find a 'Company name' column in that export.")
        return set()
    states = hs[state_col].str.strip().str.upper().map(lambda s: STATE_NAMES.get(s, s)) if state_col else ""
    return set(states + "|" + hs[name_col].map(key))


df = load()
today = date.today()
try:
    meta = json.loads(META.read_text())
except (OSError, ValueError):
    meta = {}

# ---------------- Sidebar ----------------
with st.sidebar:
    st.header("Filters")
    month = st.selectbox("Month", MONTHS, index=today.month - 1,
                         help="Defaults to this month. Change it to plan ahead.")
    m = MONTHS.index(month) + 1
    states = st.multiselect("States", sorted(df["state"].dropna().unique()), default=["GA"],
                            placeholder="All states")
    types = st.multiselect("Government type", sorted(df["type"].unique()),
                           default=["City/Town", "County", "Park District", "School District"])
    min_pop = st.number_input("Min population (cities, counties, townships)", 0, 5_000_000, 0, step=2_500,
                              help="0 = every town, however small. Try 10,000 to focus on larger places.")
    or_parks = st.number_input("…or parks & rec spending of at least ($/yr)", 250_000, 1_000_000_000, 500_000,
                               step=250_000,
                               help="Also includes smaller towns and park districts that spend at least this much "
                                    "on parks & rec, even below the population minimum. From Census finance data.")
    min_enroll = st.number_input("Min enrollment (schools)", 0, 500_000, 2_000, step=500)
    search = st.text_input("Search name")

    with st.expander("HubSpot overlay"):
        hs_file = st.file_uploader("HubSpot companies export (CSV)", type="csv")
        hs_keys = hubspot_keys(hs_file) if hs_file else set()
        if hs_file:
            st.caption(f"{len(hs_keys):,} companies loaded")

    with st.expander("Adjust call windows"):
        st.caption("Months after the fiscal year starts (0 = first month).")
        windows = {}
        for k, (a, b) in DEFAULT_WINDOWS.items():
            windows[k] = st.slider(PHASES[k].label, 0, 11, (a, b), key=f"w_{k}")

# ---------------- Filter + score ----------------
f = df.copy()
if states:
    f = f[f["state"].isin(states)]
f = f[f["type"].isin(types)]
is_school = f["type"].isin(["School District", "Community College"])
big_parks = f["parks_spend"].fillna(0) >= or_parks
f = f[(is_school & (f["enrollment"] >= min_enroll))
      | ((f["type"] == "Park District") & big_parks)
      | (~is_school & (f["type"] != "Park District") & ((f["population"] >= min_pop) | big_parks))]
if search:
    f = f[f["name"].str.contains(search, case=False, na=False)]

ph = f["fy_start_month"].map(lambda s: phase_for(int(s), m, windows))
f["phase"] = ph.map(lambda p: p.label)
f["phase_key"] = ph.map(lambda p: p.key)
f["priority"] = ph.map(lambda p: p.priority)
f["what_to_do"] = ph.map(lambda p: p.action)
f["fy_starts"] = f["fy_start_month"].map(lambda s: MONTHS[int(s) - 1])
f["best_window"] = f["fy_start_month"].map(lambda s: window_text(int(s), windows))
f["in_hubspot"] = (f["state"] + "|" + f["name"].map(key)).isin(hs_keys) if hs_keys else False
f = f.sort_values(["priority", "rank_score"], ascending=[True, False])

# ---------------- Header ----------------
# Data refresh reminder: Census usually posts a new finance year each summer
refresh_on = meta.get("refresh_check_on")
if refresh_on and today >= date.fromisoformat(refresh_on):
    st.warning(f"🔄 **Time to refresh the data.** This app uses Census data through {meta.get('latest_finance_year')}, "
               "and a newer year is likely out. Check census.gov for the new Individual Unit File, add it to "
               "`FIN_YEARS` in `build_data.py`, run `python build_data.py`, and push the new `data/` folder to GitHub.")

st.markdown(
    f"""<div class="tmr-bar"><h1>Municipal Budget Tracker</h1>
    <p>Who to call in <b>{month}</b>, based on when each government builds its budget ·
    {'All states' if not states else ', '.join(states)} · {len(f):,} governments</p></div>""",
    unsafe_allow_html=True)

c = f["phase_key"].value_counts()
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("🟢 Call now", f"{c.get('call_now', 0):,}")
k2.metric("🟢 Last call", f"{c.get('last_call', 0):,}")
k3.metric("🟡 Year-end spend", f"{c.get('year_end', 0):,}")
k4.metric("🔵 New fiscal year", f"{c.get('new_fy', 0):,}")
k5.metric("🔴 Budget locked", f"{c.get('locked', 0):,}")

show_cols = {
    "phase": "Status", "name": "Government", "type": "Type", "state": "State", "county": "County",
    "size": "Population / enrollment", "fy_starts": "FY starts", "best_window": "Best call window",
    "parks_m": "Parks & rec ($M/yr)", "what_to_do": "What to do",
}
if hs_keys:
    show_cols["in_hubspot"] = "In HubSpot"

tab_list, tab_map, tab_cal, tab_lookup, tab_about = st.tabs(
    ["📞 Call list", "🗺️ Map", "📆 Year view", "🔎 Look up one", "ℹ️ How it works"])

with tab_list:
    phase_pick = st.multiselect("Show", [p.label for p in PHASES.values()],
                                default=[PHASES["call_now"].label, PHASES["last_call"].label])
    view = f[f["phase"].isin(phase_pick)] if phase_pick else f
    st.dataframe(
        view[list(show_cols)].rename(columns=show_cols),
        hide_index=True, width="stretch", height=560,
        column_config={
            "Population / enrollment": st.column_config.NumberColumn(format="localized"),
            "Parks & rec ($M/yr)": st.column_config.NumberColumn(format="$%.1fM"),
        },
    )
    st.download_button("⬇ Download this list (CSV)", view[list(show_cols)].rename(columns=show_cols)
                       .to_csv(index=False).encode(), f"budget_calls_{month.lower()}.csv", "text/csv")

with tab_map:
    mp = f.dropna(subset=["lat", "lon"]).copy()
    mp["color"] = mp["phase_key"].map(lambda k: list(PHASES[k].color) + [200])
    mp["radius"] = (mp["rank_score"].clip(lower=5_000) ** 0.5) * 25
    mp["size_txt"] = [f"{int(v):,} people/students" if pd.notna(v) else f"${p:,.0f}/yr parks spend"
                      for v, p in zip(mp["size"], mp["parks_spend"])]
    if mp.empty:
        st.info("Nothing to map with these filters.")
    else:
        st.pydeck_chart(pdk.Deck(
            map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
            initial_view_state=pdk.ViewState(latitude=mp["lat"].mean(), longitude=mp["lon"].mean(),
                                             zoom=6 if states and len(states) <= 2 else 3.6),
            layers=[pdk.Layer("ScatterplotLayer", mp, get_position="[lon, lat]", get_fill_color="color",
                              get_radius="radius", radius_min_pixels=3, radius_max_pixels=30, pickable=True)],
            tooltip={"text": "{name} ({state})\n{phase}\nFY starts {fy_starts} · best window {best_window}\nSize: {size_txt}"},
        ))
        st.caption("🟢 Call now · 🟢 Last call (lighter) · 🟡 Year-end · 🔵 New FY · 🔴 Locked. "
                   "Some school districts are pinned at their county's center.")

with tab_cal:
    st.subheader("How many governments open their 'call now' window each month")
    rows = []
    for mm in range(1, 13):
        counts = f["fy_start_month"].map(lambda s: phase_for(int(s), mm, windows).key).value_counts()
        rows.append({"Month": MONTHS[mm - 1][:3], "Call now": counts.get("call_now", 0),
                     "Last call": counts.get("last_call", 0)})
    cal = pd.DataFrame(rows).set_index("Month")
    st.bar_chart(cal, color=[TMR_GREEN, "#4c8c2b"], stack=True)
    st.subheader("Fiscal year start dates in this selection")
    fy = f.groupby("fy_starts").size().reindex(MONTHS).dropna().astype(int).rename("Governments")
    st.dataframe(fy.to_frame().assign(**{"Best call window": [window_text(MONTHS.index(x) + 1, windows) for x in fy.index]}),
                 width="stretch")

with tab_lookup:
    pick = st.selectbox("Government", f["name"] + " — " + f["state"] + " (" + f["type"] + ")", index=None,
                        placeholder="Type a name…")
    if pick:
        r = f.iloc[(f["name"] + " — " + f["state"] + " (" + f["type"] + ")").tolist().index(pick)]
        s0 = int(r["fy_start_month"])
        a, b = st.columns(3)[:2]
        a.metric("Fiscal year starts", MONTHS[s0 - 1], f"FY ends {r['fy_end_label']}", delta_color="off")
        b.metric("Best call window", window_text(s0, windows))
        timeline = pd.DataFrame([{
            "Month": MONTHS[(s0 - 1 + i) % 12],
            "Status": phase_for(s0, ((s0 - 1 + i) % 12) + 1, windows).label,
            "What to do": phase_for(s0, ((s0 - 1 + i) % 12) + 1, windows).action,
        } for i in range(12)])
        st.dataframe(timeline, hide_index=True, width="stretch")
        if pd.notna(r["parks_spend"]) and r["parks_spend"]:
            st.caption(f"Parks & rec spending (Census): ${r['parks_spend']:,.0f}/yr")

with tab_about:
    st.markdown(f"""
**Where the data comes from.** Every fiscal year end date comes from the U.S. Census Bureau's
*Census of Governments* (2022, which covers every local government) and the *Annual Survey of State & Local
Government Finances* (2024, used where newer). Population, school enrollment and parks & rec spending
come from the same files. Map locations come from Census Gazetteer files.

**How the call windows work.** Cities don't buy on our timeline. They buy what's in the budget.
Each government's year is split into phases counted from its fiscal year start:

| Months after FY start | Status | Why |
|---|---|---|
| 0–2 | 🔵 New fiscal year | Money just released. Follow up only where they budgeted for us. |
| 3–6 | 🟢 Call now | Departments are drafting next year's requests. Get the robot in. |
| 7–8 | 🟢 Last call | Budget under review. Still possible to get added. |
| 9 | 🔴 Budget locked | Council is adopting the budget. Don't cold call. |
| 10–11 | 🟡 Year-end spend | Use-it-or-lose-it money. Pitch Pay As You Spray or small purchases. |

Example: Atlanta's fiscal year starts July 1, so **call now** runs Oct–Jan, last call is Feb–Mar,
the budget is locked in April, and May–June is year-end spending.
You can change these ranges under **Adjust call windows** in the sidebar.

**Caveats.** Fiscal year dates are self-reported to Census and rarely change, but always confirm on the call.
Park districts (separate governments that run parks, common in IL, ND, CA, OH, WA, CO and OR) are included,
along with any smaller town that spends at least the parks & rec amount set in the sidebar. Park districts don't report
population, so they're ranked by parks spending.
""")

if meta:
    st.caption(f"Data: U.S. Census Bureau finance data ({', '.join(map(str, meta.get('finance_years', [])))}) · "
               f"built {meta.get('built_on')} · next refresh check {meta.get('refresh_check_on')}")
