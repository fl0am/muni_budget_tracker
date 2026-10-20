"""Builds data/governments.csv from free U.S. Census Bureau files.

Sources (all public, no API key):
  - Census of Governments / Annual Survey of State & Local Government Finances,
    Individual Unit Files (Fin_PID_<year>.txt = directory incl. FISCAL YEAR ENDING,
    <year>FinEstDAT_*.txt = finance items incl. Parks & Rec spending)
    https://www.census.gov/programs-surveys/gov-finances/data/datasets.html
  - Census Gazetteer files (lat/lon for places, counties, county subdivisions,
    school districts) https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html

Usage:
    python build_data.py            # downloads into ./raw and writes data/governments.csv
Re-run once a year when Census posts a new finance year.
"""
from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).parent
RAW = ROOT / "raw"
OUT = ROOT / "data" / "governments.csv"

FIN_YEARS = {  # year -> zip url. 2022 is a full Census of Governments (every unit); 2024 is a sample used to refresh.
    2022: "https://www2.census.gov/programs-surveys/gov-finances/tables/2022/2022_Individual_Unit_File.zip",
    2024: "https://www2.census.gov/programs-surveys/gov-finances/tables/2024/2024_Individual_Unit_Files.zip",
}
GAZ = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_{}_national.zip"
GAZ_FILES = ["place", "counties", "cousubs", "unsd", "scsd"]

TYPE_NAMES = {"1": "County", "2": "City/Town", "3": "Township", "4": "Park District", "5": "School District"}
PARK_FUNC = "61"  # Census special-district function code for Parks & Recreation
PARKS_ITEMS = {"E61", "F61", "G61"}  # Parks & Rec: current operation, construction, other capital outlay

# Keep in the file (the app filters further).
#   Cities/counties/townships: population >= MIN_POP, OR parks & rec spending >= MIN_PARKS (small towns that spend big)
#   Park districts (IL, ND, CA, OH, WA, CO, OR...): parks & rec spending >= MIN_PARKS
#   School districts: enrollment >= MIN_ENROLL
MIN_POP = 0  # keep every city, town, township and county (small towns included); the app filters by size
MIN_PARKS = 250_000
MIN_ENROLL = 1_000

STATE_ABBR = dict(zip(
    "01 02 04 05 06 08 09 10 11 12 13 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 44 45 46 47 48 49 50 51 53 54 55 56".split(),
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split(),
))


def fetch(url: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    marker = dest / ".done"
    if not marker.exists():
        print(f"Downloading {url}")
        r = requests.get(url, timeout=300, headers={"User-Agent": "TMR muni-budget-tracker"})
        r.raise_for_status()
        zipfile.ZipFile(io.BytesIO(r.content)).extractall(dest)
        marker.touch()
    return dest


def find(folder: Path, pattern: str) -> Path:
    hits = sorted(folder.rglob(pattern))
    if not hits:
        sys.exit(f"Could not find {pattern} in {folder}")
    return hits[0]


def read_pid(path: Path) -> pd.DataFrame:
    colspecs = [(0, 12), (12, 76), (76, 111), (111, 116), (116, 125), (125, 127),
                (127, 134), (134, 136), (136, 138), (138, 140), (140, 144), (144, 146)]
    names = ["id", "name", "county", "fips_place", "population", "pop_year", "enrollment",
             "enroll_year", "func_code", "school_level", "fy_end", "survey_year"]
    df = pd.read_fwf(path, colspecs=colspecs, names=names, dtype=str, encoding="latin-1")
    for c in ["population", "enrollment"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    return df


def read_parks(path: Path) -> pd.Series:
    """Parks & Rec spending per government, in dollars."""
    dat = pd.read_fwf(path, colspecs=[(0, 12), (12, 15), (15, 27)], names=["id", "item", "amt"], dtype=str)
    dat = dat[dat["item"].isin(PARKS_ITEMS)]
    dat["amt"] = pd.to_numeric(dat["amt"], errors="coerce").fillna(0) * 1000
    return dat.groupby("id")["amt"].sum()


def fy_start(fy_end: str) -> tuple[int | None, str]:
    """'0630' -> (7, 'Jun 30'). Fiscal year starts the day after it ends."""
    if not isinstance(fy_end, str) or not re.fullmatch(r"\d{4}", fy_end):
        return None, ""
    m, d = int(fy_end[:2]), int(fy_end[2:])
    try:
        end = date(2023, m, d)
    except ValueError:
        return None, ""
    return (end + timedelta(days=1)).month, end.strftime("%b %-d")


def norm(s: str) -> str:
    s = str(s).upper()
    s = re.sub(r"\b(CITY|TOWN|VILLAGE|BOROUGH|TOWNSHIP|TWP|CDP|SCHOOLS?|SCH|DISTRICT|DIST|PUBLIC|PUB|UNIFIED|UNIF|"
               r"CONSOLIDATED|CONS|INDEPENDENT|IND|INDEP|COUNTY|CO|CNTY|COMMUNITY|COMM|CMNTY|UNIT|AREA|REGIONAL|REG|"
               r"HIGH|UNION|CENTRAL|CENT|OF|THE|ISD|USD|CSD|SD|NO|CHARTER|R|C|U|K12)\b", " ", s)
    s = re.sub(r"\d+", " ", s)
    return re.sub(r"[^A-Z0-9]", "", s)


def main() -> None:
    # --- Census finance directory (fiscal year ending) ---
    frames, parks = [], []
    for year, url in FIN_YEARS.items():
        folder = fetch(url, RAW / f"fin{year}")
        pid = read_pid(find(folder, "Fin_PID_*.txt"))
        pid["data_year"] = year
        frames.append(pid)
        parks.append(read_parks(find(folder, f"{year}FinEstDAT*.txt")).rename(f"parks_{year}"))
    # Newest year wins when a government appears in both files
    pid = pd.concat(frames).sort_values("data_year").drop_duplicates("id", keep="last")
    full = frames[0].set_index("id")  # 2022 census has population for every unit
    pid = pid.set_index("id")
    pid["population"] = pid["population"].where(pid["population"] > 0, full["population"].reindex(pid.index).fillna(0)).astype(int)
    pid["enrollment"] = pid["enrollment"].where(pid["enrollment"] > 0, full["enrollment"].reindex(pid.index).fillna(0)).astype(int)
    pid = pid.reset_index()

    pid["type_code"] = pid["id"].str[2]
    pid = pid[pid["type_code"].isin(TYPE_NAMES)]
    pid["type"] = pid["type_code"].map(TYPE_NAMES)
    pid["state_fips"] = pid["id"].str[:2]
    pid["state"] = pid["state_fips"].map(STATE_ABBR)
    pid["county_fips"] = pid["state_fips"] + pid["id"].str[3:6]
    # School level codes: 02 secondary, 03 elem-secondary (unified), 04 community college.
    # Dropped: 01 elementary-only, 05 vocational/special ed, 06 non-operating, 07 service agencies.
    pid = pid[(pid["type_code"] != "5") | pid["school_level"].isin(["02", "03", "04"])]
    pid.loc[(pid["type_code"] == "5") & (pid["school_level"] == "04"), "type"] = "Community College"
    # Parks & Rec spending: newest year available
    p = pd.concat(parks, axis=1)
    p["parks_spend"] = p["parks_2024"].fillna(p["parks_2022"]) if "parks_2024" in p else p["parks_2022"]
    pid = pid.merge(p[["parks_spend"]], left_on="id", right_index=True, how="left")
    pid["parks_spend"] = pid["parks_spend"].fillna(0).round(-3).astype(int)

    # Special districts: keep only park & recreation districts
    is_sd = pid["type_code"] == "4"
    parkish = (pid["func_code"] == PARK_FUNC) | pid["name"].str.contains(r"\bPARKS?\b|RECREATION", case=False, na=False)
    pid = pid[~is_sd | parkish]

    t = pid["type_code"]
    keep = ((t == "5") & (pid["enrollment"] >= MIN_ENROLL)) | \
           (t.isin(["1", "2", "3"]) & ((pid["population"] >= MIN_POP) | (pid["parks_spend"] >= MIN_PARKS))) | \
           ((t == "4") & (pid["parks_spend"] >= MIN_PARKS))
    pid = pid[keep].copy()

    starts = pid["fy_end"].map(fy_start)
    pid["fy_start_month"] = starts.map(lambda t: t[0])
    pid["fy_end_label"] = starts.map(lambda t: t[1])
    pid = pid[pid["fy_start_month"].notna()]
    pid["fy_start_month"] = pid["fy_start_month"].astype(int)

    # --- Coordinates from Gazetteer ---
    gaz = {}
    for g in GAZ_FILES:
        folder = fetch(GAZ.format(g), RAW / f"gaz_{g}")
        df = pd.read_csv(find(folder, "*.txt"), sep="\t", dtype=str)
        df.columns = [c.strip() for c in df.columns]
        df["lat"] = pd.to_numeric(df["INTPTLAT"], errors="coerce")
        df["lon"] = pd.to_numeric(df["INTPTLONG"].str.strip(), errors="coerce")
        gaz[g] = df
    place = gaz["place"].set_index("GEOID")[["lat", "lon"]]
    # Park districts: match "NAPERVILLE PARK DISTRICT" to the place "Naperville city"
    pl = gaz["place"].copy()
    pl["key"] = pl["USPS"] + "|" + pl["NAME"].map(norm)
    place_by_name = pl.drop_duplicates("key").set_index("key")[["lat", "lon"]]
    county = gaz["counties"].set_index("GEOID")[["lat", "lon"]]
    cousub = gaz["cousubs"]
    schools = pd.concat([gaz["unsd"], gaz["scsd"]])
    schools["key"] = schools["USPS"] + "|" + schools["NAME"].map(norm)
    schools = schools.drop_duplicates("key").set_index("key")[["lat", "lon"]]
    # Townships: match by state+county+name
    cousub["key"] = cousub["GEOID"].str[:5] + "|" + cousub["NAME"].map(norm)
    cousub = cousub.drop_duplicates("key").set_index("key")[["lat", "lon"]]

    lat, lon, how = [], [], []
    for r in pid.itertuples():
        hit = None
        if r.type_code == "2" and isinstance(r.fips_place, str):
            hit = place.loc[r.state_fips + r.fips_place] if (r.state_fips + r.fips_place) in place.index else None
        elif r.type_code == "1":
            hit = county.loc[r.county_fips] if r.county_fips in county.index else None
        elif r.type_code == "3":
            k = r.county_fips + "|" + norm(r.name)
            hit = cousub.loc[k] if k in cousub.index else None
        elif r.type_code == "4":
            k = f"{r.state}|{norm(re.sub(r'(?i)METROPOLITAN|METRO|PARKS?|RECREATION|AND|&|PLEASURE|DRIVEWAY|COMMISSION|AUTHORITY|SPECIAL|FOUNDATION', ' ', r.name))}"
            hit = place_by_name.loc[k] if k in place_by_name.index else None
        elif r.type_code == "5":
            k = f"{r.state}|{norm(r.name)}"
            hit = schools.loc[k] if k in schools.index else None
        if hit is not None:
            lat.append(hit["lat"]); lon.append(hit["lon"]); how.append("exact")
        elif r.county_fips in county.index:
            c = county.loc[r.county_fips]
            lat.append(c["lat"]); lon.append(c["lon"]); how.append("county center")
        else:
            lat.append(None); lon.append(None); how.append("none")
    pid["lat"], pid["lon"], pid["location"] = lat, lon, how

    out = pid[["id", "name", "type", "state", "county", "population", "enrollment", "fy_end_label",
               "fy_start_month", "parks_spend", "lat", "lon", "location", "data_year"]].copy()
    out["name"] = out["name"].str.strip().str.title()
    out["county"] = out["county"].fillna("").str.strip()
    out = out.sort_values(["state", "type", "population"], ascending=[True, True, False])
    OUT.parent.mkdir(exist_ok=True)
    out.to_csv(OUT, index=False)

    # Refresh reminder for the app: Census posts finance data ~2 years after the data year,
    # usually in July/August (2024 data came out summer 2026).
    latest = max(FIN_YEARS)
    meta = {"finance_years": sorted(FIN_YEARS), "latest_finance_year": latest,
            "built_on": date.today().isoformat(), "refresh_check_on": f"{latest + 3}-08-01"}
    (OUT.parent / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"Wrote {len(out):,} governments to {OUT}")
    print(out["type"].value_counts().to_string())
    print("Location match:", out["location"].value_counts().to_dict())


if __name__ == "__main__":
    main()
