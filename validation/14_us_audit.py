"""
14_us_audit.py  -  US validation, step 2: audit the US layers and the validation sample

Checks, read-only:
  U02 SGMC        layers, polygon count, CRS, total area; lithology terms (LITH1-5, LOW_LITH,
                  LITH_RANK, GENERALIZED_LITH) with mapped area; every ultramafic-type term; fault lines
  U03 Qfaults     layers, counts, age / slip classes
  U04 PP 1900     rasters: CRS, resolution, extent, value range
  D14 USGS gas    the validation sample as the protocol defines it (conterminous US, H2 reported):
                  positives (>= 0.5 mol%), negatives (< 0.5), after declustering to grid cells and blocks
Writes metadata/audit/US_audit.md, US_lith_terms.csv, US_generalized_lith.csv, US_d14_sample.png.
Run after unzipping the downloads:  python scripts/14_us_audit.py
"""
import re
import sys
import zipfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyogrio

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data_raw"
OUT = ROOT / "metadata" / "audit"
UM_RX = re.compile(r"ultramafic|ultrabasic|serpentin|peridotit|dunite|harzburg|lherzol|pyroxenit|komatii|hornblendit|ophiolit|kimberl|talc|soapstone", re.I)
CONUS = (-125.0, 24.0, -66.0, 50.0)
L = []


def md(df, n=None):
    df = df if n is None else df.head(n)
    return df.to_markdown(index=False) if len(df) else "_none_"


def find(folder, exts):
    base = RAW / folder
    if not base.exists():
        return []
    hits = []
    for p in base.rglob("*"):
        if p.name.startswith("._") or "__MACOSX" in p.parts:
            continue
        if p.is_dir() and p.suffix.lower() == ".gdb" and ".gdb" in exts:
            hits.append(p)
        elif p.is_file() and p.suffix.lower() in exts and not any(q.suffix.lower() == ".gdb" for q in p.parents):
            hits.append(p)
    return sorted(hits)


def layers_of(src):
    try:
        return [(n, g) for n, g in pyogrio.list_layers(src)]
    except Exception as err:
        return [("(error)", str(err)[:80])]


def sgmc():
    L.append("## U02 - SGMC lithology (USGS State Geologic Map Compilation)\n")
    srcs = find("U02_sgmc", {".gdb", ".shp", ".csv"})
    if not srcs:
        L.append("**BLOCKER:** nothing found in data_raw/U02_sgmc (download and unzip first).\n")
        return
    gdb = next((s for s in srcs if s.suffix.lower() == ".gdb"), None)
    tables = {}
    if gdb:
        lay = layers_of(gdb)
        L.append(f"Geodatabase `{gdb.name}`: {len(lay)} layers.\n\n" + md(pd.DataFrame(lay, columns=["layer", "geometry"])) + "\n")
        names = {n.lower(): n for n, _ in lay}
        pick = lambda key: next((names[k] for k in names if key in k), None)   # noqa: E731
        geo, lith, struct = pick("geology"), pick("lithology"), pick("structure")
        tables["geo"] = (gdb, geo)
        tables["lith"] = (gdb, lith)
        tables["struct"] = (gdb, struct)
    else:
        shp = [s for s in srcs if s.suffix.lower() == ".shp"]
        csv = [s for s in srcs if s.suffix.lower() == ".csv"]
        L.append("No geodatabase; using shapefiles / CSV: " + ", ".join(s.name for s in shp + csv) + "\n")
        tables["geo"] = (next((s for s in shp if "geol" in s.name.lower()), None), None)
        tables["struct"] = (next((s for s in shp if "struct" in s.name.lower()), None), None)
        tables["lith"] = (next((s for s in csv if "lith" in s.name.lower()), None), None)

    src, lyr = tables["geo"]
    if src is None or (gdb and lyr is None):
        L.append("**BLOCKER:** geology polygon layer not found.\n")
        return
    info = pyogrio.read_info(src, layer=lyr)
    L.append(f"Geology polygons: {info['features']:,}; CRS {info['crs']}; fields: {', '.join(info['fields'][:30])}.\n")
    # shapefiles cut field names to 10 characters (GENERALIZED_LITH -> GENERALIZE): match on the first 10
    want = ("UNIT_LINK", "STATE", "GENERALIZED_LITH", "MAJOR1", "MAJOR2", "MAJOR3", "MINOR1", "MINOR2",
            "MINOR3", "MINOR4", "MINOR5", "INCIDENTAL", "INDETERMINATE", "MIN_AGE", "MAX_AGE")
    fields = {f.upper()[:10]: f for f in info["fields"]}
    keep = {fields[w[:10]]: w for w in want if w[:10] in fields}
    print("reading SGMC polygons (large) ...", flush=True)
    g = pyogrio.read_dataframe(src, layer=lyr, columns=list(keep)).rename(columns=keep)
    g = g[g.geometry.notna()]
    if g.crs is None:
        L.append("**BLOCKER:** no CRS on the geology layer.\n")
        return
    area = g.to_crs(5070).area.values / 1e6
    g["km2"] = area
    bad = int((~g.geometry.is_valid).sum())
    L.append(f"Total mapped area {area.sum():,.0f} km2 (conterminous US is about 8.08 million km2); invalid geometries: {bad:,}.\n")
    if "GENERALIZED_LITH" in g:
        gl = g.groupby(g["GENERALIZED_LITH"].fillna("(blank)"))["km2"].agg(["size", "sum"]).reset_index()
        gl.columns = ["GENERALIZED_LITH", "polygons", "km2"]
        gl = gl.sort_values("km2", ascending=False).round(0)
        gl.to_csv(OUT / "US_generalized_lith.csv", index=False)
        L.append("### GENERALIZED_LITH by area (full list in US_generalized_lith.csv)\n\n" + md(gl, 40) + "\n")

    # lithology terms: area of each unit counted once per term
    lsrc, llyr = tables["lith"]
    if lsrc is not None and "UNIT_LINK" in g:
        lt = pyogrio.read_dataframe(lsrc, layer=llyr, read_geometry=False) if lsrc.suffix.lower() != ".csv" else pd.read_csv(lsrc, low_memory=False)
        lt.columns = [c.upper() for c in lt.columns]
        L.append(f"Lithology table: {len(lt):,} rows; fields: {', '.join(lt.columns[:20])}.\n")
        if "LITH_RANK" in lt:
            L.append("LITH_RANK: " + ", ".join(f"{k} {v:,}" for k, v in lt["LITH_RANK"].value_counts().items()) + ".\n")
        unit_km2 = g.groupby("UNIT_LINK")["km2"].sum()
        cols = [c for c in ("LITH1", "LITH2", "LITH3", "LITH4", "LITH5", "LOW_LITH") if c in lt]
        rows = []
        for c in cols:
            for term, sub in lt.groupby(lt[c].fillna("").astype(str).str.strip()):
                if not term:
                    continue
                units = sub["UNIT_LINK"].unique()
                rows.append({"level": c, "term": term, "units": len(units),
                             "km2_units_with_term": round(float(unit_km2.reindex(units).fillna(0).sum()), 0),
                             "ranks": ", ".join(sorted(sub.get("LITH_RANK", pd.Series(dtype=str)).dropna().astype(str).unique()))})
        terms = pd.DataFrame(rows).sort_values(["level", "km2_units_with_term"], ascending=[True, False])
        terms.to_csv(OUT / "US_lith_terms.csv", index=False)
        low = terms[terms["level"] == "LOW_LITH"]
        L.append(f"Distinct lithology terms: {len(terms):,} (all levels); LOW_LITH terms: {len(low):,}. Full list: US_lith_terms.csv.\n")
        L.append("### Most extensive LOW_LITH terms\n\n" + md(low.sort_values("km2_units_with_term", ascending=False), 30) + "\n")
        um = terms[terms["term"].str.contains(UM_RX)]
        L.append("### Every ultramafic-type term (check these: they drive the source score)\n\n" + md(um.sort_values("km2_units_with_term", ascending=False)) + "\n")
    else:
        L.append("**BLOCKER:** lithology table (LITH1-5) not found or no UNIT_LINK to join on.\n")

    ssrc, slyr = tables["struct"]
    if ssrc is not None and (not gdb or slyr):
        s = pyogrio.read_dataframe(ssrc, layer=slyr, read_geometry=False)
        dcol = next((c for c in s.columns if c.upper()[:10] in ("DESCRIPTIO", "TYPE", "FEATURE")), None)
        L.append(f"### SGMC structure lines: {len(s):,}\n")
        if dcol:
            vc = s[dcol].fillna("(blank)").astype(str).str.strip().value_counts().rename_axis(dcol).reset_index(name="lines")
            vc.to_csv(OUT / "US_structure_types.csv", index=False)
            L.append(md(vc, 30) + "\n\nFault lines (DESCRIPTION contains 'fault'): "
                     f"{int(s[dcol].astype(str).str.contains('fault', case=False).sum()):,}.\n")
    else:
        L.append("SGMC structure layer not found.\n")


def qfaults():
    L.append("## U03 - USGS Quaternary Fault and Fold Database\n")
    srcs = find("U03_qfaults", {".shp", ".gdb", ".geojson", ".kml"})
    if not srcs:
        z = sorted((RAW / "U03_qfaults").glob("*.zip")) if (RAW / "U03_qfaults").exists() else []
        if z:
            with zipfile.ZipFile(z[0]) as zz:
                srcs = [f"/vsizip/{z[0]}/{n}" for n in zz.namelist() if n.lower().endswith(".shp")]
    if not srcs:
        L.append("**BLOCKER:** nothing found in data_raw/U03_qfaults.\n")
        return
    for s in srcs:
        for lyr, geom in layers_of(s):
            try:
                d = pyogrio.read_dataframe(s, layer=lyr, read_geometry=False)
            except Exception as err:
                L.append(f"- `{Path(str(s)).name}` / {lyr}: could not read ({str(err)[:60]})\n")
                continue
            L.append(f"- `{Path(str(s)).name}` / {lyr}: {len(d):,} features, {geom}; fields {', '.join(d.columns[:15])}\n")
            for c in d.columns:
                if re.search(r"age|slip|class|recency", c, re.I) and d[c].nunique() <= 30:
                    vc = d[c].fillna("(blank)").astype(str).value_counts().rename_axis(c).reset_index(name="features")
                    L.append(f"\n{md(vc)}\n")
    L.append("")


def pp1900():
    L.append("## U04 - USGS PP 1900 prospectivity data release (benchmark)\n")
    rs = find("U04_usgs_h2_prospectivity", {".tif", ".tiff", ".img", ".asc"})
    if not rs:
        L.append("No rasters found (optional benchmark; download if you have marked it).\n")
        return
    import rasterio
    rows = []
    for p in rs:
        try:
            with rasterio.open(p) as r:
                a = r.read(1, out_shape=(1, max(1, r.height // 20), max(1, r.width // 20)), masked=True)
                rows.append({"file": p.name, "crs": str(r.crs)[:30], "res": f"{r.res[0]:.4g}", "size": f"{r.width}x{r.height}",
                             "nodata": r.nodata, "min": float(a.min()) if a.count() else None, "max": float(a.max()) if a.count() else None})
        except Exception as err:
            rows.append({"file": p.name, "crs": f"error: {str(err)[:40]}"})
    L.append(md(pd.DataFrame(rows)) + "\n")


def d14():
    L.append("## D14 - validation sample (protocol 2026-11-02)\n")
    f = sorted((RAW / "D14_usgs_gas").rglob("*.csv"))
    if not f:
        L.append("**BLOCKER:** D14 CSV not found.\n")
        return
    d = pd.read_csv(f[0], low_memory=False)
    raw = d["H2"].astype(str).str.strip()
    blank = d["H2"].isna() | raw.isin(["", "nan", "None", "<NA>"])
    val = pd.to_numeric(raw.str.replace("<", "", regex=False), errors="coerce")
    trace = raw.str.contains(r"tr|<", case=False, na=False)
    lat, lon = pd.to_numeric(d["LAT"], errors="coerce"), pd.to_numeric(d["LONG"], errors="coerce")
    conus = lon.between(CONUS[0], CONUS[2]) & lat.between(CONUS[1], CONUS[3]) & ~d["STATE"].astype(str).str.upper().isin(["ALASKA", "HAWAII"])
    pos = ~blank & (val >= 0.5)
    neg = ~blank & ((val < 0.5) | (trace & val.isna()))
    s = pd.DataFrame({"lat": lat, "lon": lon, "state": d["STATE"], "pos": pos, "neg": neg})[conus & (pos | neg)]
    L.append(f"Samples with H2 reported, conterminous US: {len(s):,} (positive {int(s.pos.sum())}, negative {int(s.neg.sum())}); "
             f"excluded: blank {int(blank.sum()):,}, outside conterminous US or no coordinates {int(((pos | neg) & ~conus).sum())}.\n")
    try:
        import h3
        s["c6"] = [h3.latlng_to_cell(a, b, 6) for a, b in zip(s.lat, s.lon)]
        s["c3"] = [h3.cell_to_parent(c, 3) for c in s.c6]
        cells = s.groupby("c6").agg(pos=("pos", "max"), c3=("c3", "first"), state=("state", "first"))
        blocks = cells.groupby("c3")["pos"].agg(["size", "sum"])
        L.append(f"After declustering: {len(cells):,} cells ({int(cells.pos.sum())} positive, {int((~cells.pos).sum())} negative), "
                 f"in {len(blocks):,} spatial blocks ({int((blocks['sum'] > 0).sum())} blocks contain a positive cell).\n")
        bystate = cells.groupby("state")["pos"].agg(["size", "sum"]).rename(columns={"size": "cells", "sum": "positive_cells"})
        bystate = bystate.sort_values("positive_cells", ascending=False).reset_index()
        L.append("Positive cells by state (concentration check):\n\n" + md(bystate, 15) + "\n")
        top_share = bystate["positive_cells"].head(1).sum() / max(1, bystate["positive_cells"].sum())
        if top_share > 0.5:
            L.append(f"**NOTE:** {top_share:.0%} of positive cells are in one state: the test is dominated by one region.\n")
    except ImportError:
        L.append("h3 not installed: declustering skipped.\n")
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(s.lon[s.neg], s.lat[s.neg], s=2, c="grey", label="H2 < 0.5 mol%")
    ax.scatter(s.lon[s.pos], s.lat[s.pos], s=10, c="red", label="H2 >= 0.5 mol%")
    ax.set_xlim(CONUS[0], CONUS[2]); ax.set_ylim(CONUS[1], CONUS[3]); ax.legend(); ax.set_title("Validation sample (H2 reported)")
    fig.savefig(OUT / "US_d14_sample.png", dpi=120, bbox_inches="tight"); plt.close(fig)
    L.append("![sample](US_d14_sample.png)\n")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    L.extend(["# US validation data - audit", ""])
    for fn in (d14, qfaults, pp1900, sgmc):
        try:
            fn()
        except Exception as err:
            import traceback
            L.append(f"**ERROR in {fn.__name__}:** {err}\n\n```\n{traceback.format_exc()[-1500:]}\n```\n")
    (OUT / "US_audit.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote metadata/audit/US_audit.md")


if __name__ == "__main__":
    main()
