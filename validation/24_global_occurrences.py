"""
24_global_occurrences.py  -  global test, step 1: what the EPRI occurrence list can support (labels only)

Read-only. Looks ONLY at the occurrence records and at where geoscience sampling exists (IHFC heat-flow sites as a
proxy for "where people looked"). No model input (geology, faults, gravity ...) and no score is joined, so the test
protocol can still be fixed without having seen how any map does.

Reports
  - every column of the occurrence table (non-blank, distinct, top values) - so the setting fields can be mapped by hand
  - setting of each record (well / mine / spring-seep / soil gas or depression / fluid inclusion / other) from its text,
    and whether the text mentions an ultramafic / ophiolite / serpentinite context
  - hydrogen values: numeric, ranges, '<', trace, blank (units as written)
  - independence: records -> 25 km groups -> H3 res-5 cells, by continent and setting
  - background proxy: IHFC onshore heat-flow sites by continent
Writes metadata/audit/global_occurrences.md, global_occurrences.png, metadata/global_occurrences_clean.csv
Run:  python scripts/24_global_occurrences.py
"""
import importlib.util
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data_raw"
OUT = ROOT / "metadata" / "audit"
spec = importlib.util.spec_from_file_location("audit03", ROOT / "scripts" / "03_audit_datasets.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

SETTINGS = [  # first match wins (order matters)
    ("fluid inclusion", r"inclusion"),
    ("well / borehole", r"\bwells?\b|borehole|drill|\bbore\b|gas field|reservoir|production|mud ?log"),
    ("mine / tunnel", r"\bmines?\b|mining|tunnel|gallery|quarry|underground|shaft"),
    ("spring / seep", r"spring|seep|vent|bubbl|fumarol|emanation|mud volcano|geyser|flame|fire|burning|eternal"),
    ("soil gas / depression", r"soil|depression|fairy|circle|\bscd|sub-?circular|pockmark|surface gas"),
]
UM_RX = r"ophiolit|serpentin|ultramafic|ultrabasic|peridotit|dunite|harzburg|komatii"
CONTINENT = {
    "Africa": "Mali|Morocco|Algeria|Tunisia|Egypt|Libya|Namibia|South Africa|Botswana|Zimbabwe|Zambia|Tanzania|Kenya|Ethiopia|Djibouti|Congo|Gabon|Cameroon|Nigeria|Ghana|Senegal|Mauritania|Niger|Chad|Sudan|Uganda|Rwanda|Burundi|Mozambique|Madagascar|Angola|Malawi|Eritrea|Somalia|Burkina|Ivory|Côte|Guinea|Sierra|Liberia|Togo|Benin",
    "Europe": "France|Spain|Portugal|Italy|Germany|Poland|Czech|Slovakia|Austria|Switzerland|Belgium|Netherlands|Luxembourg|Denmark|Norway|Sweden|Finland|Iceland|United Kingdom|UK|England|Scotland|Ireland|Albania|Greece|Bulgaria|Romania|Hungary|Serbia|Croatia|Bosnia|Slovenia|Montenegro|Macedonia|Ukraine|Belarus|Lithuania|Latvia|Estonia|Moldova|Cyprus|Malta",
    "Asia": "Russia|China|India|Japan|Korea|Mongolia|Kazakhstan|Uzbekistan|Turkmenistan|Kyrgyz|Tajik|Afghanistan|Pakistan|Nepal|Bhutan|Bangladesh|Myanmar|Thailand|Laos|Vietnam|Cambodia|Malaysia|Indonesia|Philippines|Taiwan|Turkey|Türkiye|Iran|Iraq|Syria|Jordan|Israel|Lebanon|Saudi|Yemen|Oman|Emirates|UAE|Qatar|Bahrain|Kuwait|Georgia|Armenia|Azerbaijan|Sri Lanka|Brunei|Timor",
    "North America": "United States|USA|U\\.S\\.|Canada|Mexico|Greenland|Cuba|Guatemala|Honduras|Nicaragua|Costa Rica|Panama|Salvador|Belize|Dominican|Haiti|Jamaica|Puerto Rico",
    "South America": "Brazil|Argentina|Chile|Peru|Bolivia|Colombia|Venezuela|Ecuador|Uruguay|Paraguay|Guyana|Suriname",
    "Oceania": "Australia|New Zealand|Papua|New Caledonia|Fiji|Solomon|Vanuatu",
}


def continent(country):
    for k, rx in CONTINENT.items():
        if re.search(rx, str(country), re.I):
            return k
    return "unmapped"


def parse_h2(x):
    """(value, kind). kind: number / range (max kept) / less-than / trace / text / blank."""
    s = str(x).strip()
    if s in ("", "nan", "None", "<NA>"):
        return np.nan, "blank"
    t = s.replace("%", "").replace(",", ".").strip()
    if re.search(r"tr", t, re.I):
        return np.nan, "trace"
    m = re.match(r"^<\s*([\d.]+)$", t)
    if m:
        return float(m.group(1)), "less-than"
    m = re.match(r"^~?\s*([\d.]+)$", t)
    if m:
        return float(m.group(1)), "number"
    nums = [float(v) for v in re.findall(r"\d+(?:\.\d+)?", t)]
    if nums and re.search(r"\d\s*(-|–|to)\s*\d", t):
        return max(nums), "range"
    return (max(nums), "text") if nums else (np.nan, "text")


def md(df, n=None):
    df = df if n is None else df.head(n)
    return df.to_markdown(index=False) if len(df) else "_none_"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    L = ["# Global occurrences (EPRI) - what a global test can support", "",
         "Labels only: no geology, fault, gravity or score has been joined to these records.", ""]
    files = audit.find("D01_epri", "*occur*.csv") or audit.find("D01_epri", "*.csv")[:1]
    if not files:
        sys.exit("No occurrence CSV in data_raw/D01_epri")
    occ = audit.read_text_table(files[0])
    for c in occ.columns:
        occ[c] = occ[c].astype("string").str.replace(r"\s+", " ", regex=True).str.strip()
    L += [f"File `{files[0].name}`: {len(occ):,} records, {occ.shape[1]} columns.", "", "## Columns", ""]
    prof = []
    for c in occ.columns:
        vc = occ[c].dropna().value_counts()
        prof.append({"column": c, "non_blank": int(occ[c].notna().sum()), "distinct": int(occ[c].nunique()),
                     "top values": " | ".join(f"{str(k)[:30]} ({v})" for k, v in vc.head(4).items())})
    L += [md(pd.DataFrame(prof)), ""]

    lat_c = audit.find_col(occ, "Latitude", "lat", contains=["lat"])
    lon_c = audit.find_col(occ, "Longitude", "long", "lon", contains=["lon"])
    h2_c = audit.find_col(occ, "Hydrogen", "H2", contains=["hydrogen"])
    country_c = audit.find_col(occ, "Country")
    text_cols = [c for c in occ.columns if re.search(r"categ|type|setting|environ|geolog|host|rock|descr|name|site|comment|note|source|origin", c, re.I)
                 and c not in (lat_c, lon_c, h2_c)]
    L += [f"Columns used: lat `{lat_c}`, lon `{lon_c}`, H2 `{h2_c}`, country `{country_c}`; setting text from "
          + ", ".join(f"`{c}`" for c in text_cols) + ".", ""]
    d = pd.DataFrame({"rec": range(len(occ)),
                      "lat": pd.to_numeric(occ[lat_c], errors="coerce") if lat_c else np.nan,
                      "lon": pd.to_numeric(occ[lon_c], errors="coerce") if lon_c else np.nan,
                      "country": occ[country_c] if country_c else ""})
    txt = occ[text_cols].fillna("").astype(str).agg(" | ".join, axis=1).str.lower() if text_cols else pd.Series("", index=occ.index)
    d["setting"] = "other / unclear"
    for name, rx in reversed(SETTINGS):        # reversed so the FIRST pattern wins
        d.loc[txt.str.contains(rx, regex=True).values, "setting"] = name
    d["um_context"] = txt.str.contains(UM_RX, regex=True).values
    d["continent"] = d["country"].map(continent)
    if h2_c:
        parsed = occ[h2_c].map(parse_h2)
        d["h2"] = [p[0] for p in parsed]
        d["h2_kind"] = [p[1] for p in parsed]
        d["h2_raw"] = occ[h2_c]
    else:
        d["h2"], d["h2_kind"], d["h2_raw"] = np.nan, "no column", ""
    ok = d.lat.between(-90, 90) & d.lon.between(-180, 180) & d.lat.notna() & d.lon.notna()
    L += [f"Records with usable coordinates: {int(ok.sum()):,} of {len(d):,}.", ""]

    # hydrogen values
    L += ["## Hydrogen values (as written; units are not standardised in the source)", "",
          md(d["h2_kind"].value_counts().rename_axis("form").reset_index(name="records")), ""]
    v = d.loc[d.h2.notna(), "h2"]
    if len(v):
        bins = [-1, 0.1, 1, 10, 50, 1e9]
        lab = ["< 0.1", "0.1-1", "1-10", "10-50", ">= 50"]
        L += ["Numeric values (largest of a range):", "",
              md(pd.cut(v, bins, labels=lab).value_counts().reindex(lab).rename_axis("value").reset_index(name="records")), ""]
    odd = d[d.h2_kind.isin(["text", "range", "less-than"])]["h2_raw"].dropna().astype(str).value_counts().head(20)
    if len(odd):
        L += ["Non-plain values (top 20):", "", md(odd.rename_axis("as written").reset_index(name="records")), ""]

    # independence
    g = d[ok].copy()
    dist = audit.haversine_matrix(g.lat.to_numpy(), g.lon.to_numpy())
    g["group25"] = audit.single_linkage_groups(dist, 25)
    import h3
    g["h3_5"] = [h3.latlng_to_cell(a, b, 5) for a, b in zip(g.lat, g.lon)]
    g["h3_3"] = [h3.cell_to_parent(c, 3) for c in g.h3_5]
    summ = g.groupby("continent").agg(records=("rec", "size"), groups_25km=("group25", "nunique"),
                                      cells_res5=("h3_5", "nunique"), blocks_res3=("h3_3", "nunique"))
    summ["um_context_groups"] = g[g.um_context].groupby("continent")["group25"].nunique().reindex(summ.index).fillna(0).astype(int)
    summ = summ.sort_values("groups_25km", ascending=False).reset_index()
    tot = pd.DataFrame([{"continent": "TOTAL", "records": len(g), "groups_25km": g.group25.nunique(), "cells_res5": g.h3_5.nunique(),
                         "blocks_res3": g.h3_3.nunique(), "um_context_groups": g[g.um_context].group25.nunique()}])
    L += ["## Independence: records -> 25 km groups -> grid cells", "",
          "A test counts groups or cells, not records: records within 25 km usually describe one system.", "",
          md(pd.concat([summ, tot], ignore_index=True)), ""]
    st = g.groupby("setting").agg(records=("rec", "size"), groups_25km=("group25", "nunique"),
                                  with_numeric_h2=("h2", lambda s: int(s.notna().sum())),
                                  h2_ge_10=("h2", lambda s: int((s >= 10).sum())))
    L += ["## Setting of each record (from its text) - check a sample by hand", "",
          md(st.sort_values("groups_25km", ascending=False).reset_index()), "",
          f"Records whose text mentions an ultramafic / ophiolite / serpentinite context: {int(g.um_context.sum())} "
          f"({g[g.um_context].group25.nunique()} groups).", ""]
    ct = pd.crosstab(g.setting, g.continent)
    L += ["Setting x continent (records):", "", ct.reset_index().to_markdown(index=False), ""]
    if (g.continent == "unmapped").any():
        L += ["Unmapped countries: " + ", ".join(sorted(g.loc[g.continent == "unmapped", "country"].astype(str).unique())[:30]), ""]
    ex = g.groupby("setting").head(3)[["setting", "country"]].copy()
    ex["text"] = txt.loc[ex.index].str.slice(0, 120).values
    L += ["Three example texts per setting (to check the classification):", "", md(ex), ""]

    # background proxy: where geoscience sampling exists
    try:
        f = [p for p in sorted((RAW / "D06_ihfc").rglob("*.txt")) if "ghfdb" in p.name.lower() and not p.name.startswith("._")]
        data, fields, id_col, pid_col = audit.read_ihfc(f[0])
        num = lambda c: pd.to_numeric(data[c], errors="coerce")   # noqa: E731
        hp = pd.DataFrame({"pid": data[pid_col], "lat": num("P4"), "lon": num("P5"),
                           "env": data["P7"].astype(str).str.lower()}).drop_duplicates("pid").dropna(subset=["lat", "lon"])
        hp = hp[hp.env.str.contains("onshore")]
        hp["h3_3"] = [h3.cell_to_parent(h3.latlng_to_cell(a, b, 5), 3) for a, b in zip(hp.lat, hp.lon)]
        blocks_hf = set(hp.h3_3)
        L += ["## Background proxy: onshore heat-flow sites (IHFC)", "",
              f"{len(hp):,} onshore sites in {len(blocks_hf):,} res-3 blocks. Occurrence blocks that also hold a heat-flow site: "
              f"{len(set(g.h3_3) & blocks_hf)} of {g.h3_3.nunique()}. A 'target-group' background drawn near heat-flow sites "
              "mimics where geoscientists worked, which partly cancels the search bias of the occurrence list.", ""]
    except Exception as e:      # noqa: BLE001
        L += ["## Background proxy", "", f"IHFC not read ({str(e)[:80]}).", ""]

    proj = audit.find("D01_epri", "*project*.csv")
    if proj:
        pj = audit.read_text_table(proj[0])
        L += [f"EPRI projects file: {len(pj)} exploration projects (licences / activity, not confirmed hydrogen).", ""]

    out = g[["rec", "lat", "lon", "country", "continent", "setting", "um_context", "h2", "h2_kind", "group25", "h3_5", "h3_3"]]
    out.to_csv(ROOT / "metadata" / "global_occurrences_clean.csv", index=False)
    fig, ax = plt.subplots(figsize=(13, 6.5))
    for name, grp in g.groupby("setting"):
        ax.scatter(grp.lon, grp.lat, s=10, label=f"{name} ({grp.group25.nunique()} groups)")
    ax.set_xlim(-180, 180); ax.set_ylim(-60, 80); ax.grid(lw=0.3); ax.legend(fontsize=7, loc="lower left")
    ax.set_title("EPRI natural hydrogen occurrences by setting")
    fig.savefig(OUT / "global_occurrences.png", dpi=120, bbox_inches="tight")
    L.append("![occurrences](global_occurrences.png)")
    (OUT / "global_occurrences.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote metadata/audit/global_occurrences.md and metadata/global_occurrences_clean.csv")


if __name__ == "__main__":
    main()
