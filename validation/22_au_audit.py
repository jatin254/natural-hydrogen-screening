"""
22_au_audit.py  -  Australia test, step 3: audit the Australian layers and the label sample (read-only)

  A02 geology 1:1M   polygon / line layers, fields, CRS, area; the `lithology` text run through the SAME India
                     classifier (configs/lithology_classes.yaml): area by class, unmatched terms, every ultramafic term;
                     age field values; fault-line types
  A03-A05            fields, counts, categorical values; provinces mentioning greenstone / ophiolite / rift / craton
  A06 gravity        grids found: CRS, cell size, extent, value range (units)
  A07 coast          land area (Australia ~7.69 million km2)
  A08 NSW soil gas   files, sheets, columns
  A01 GA gas         label counts as the protocol defines them (onshore, positive >= 0.5 mol%), after declustering.
                     Counts only - no score is joined.
Writes metadata/audit/AU_audit.md, AU_lith_classes.csv, AU_lith_unmatched.csv, AU_um_terms.csv, AU_sample.png.
Run:  python scripts/22_au_audit.py
"""
import re
import sys
import traceback
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyogrio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h2pros.lithology import classify   # noqa: E402

RAW = ROOT / "data_raw"
OUT = ROOT / "metadata" / "audit"
UM_RX = re.compile(r"ultramafic|ultrabasic|serpentin|peridotit|dunite|harzburg|lherzol|pyroxenit|komatii|hornblendit|ophiolit|kimberl|talc|soapstone|picrit", re.I)
AREA_CRS = "EPSG:3577"     # GDA94 / Australian Albers (equal-area)
AU_BOX = (112.0, -44.5, 154.5, -9.0)
L = []


def md(df, n=None):
    df = df if n is None else df.head(n)
    return df.to_markdown(index=False) if len(df) else "_none_"


def vector_sources(folder):
    base = RAW / folder
    if not base.exists():
        return []
    out = []
    for p in sorted(base.rglob("*")):
        if p.name.startswith("._") or "__MACOSX" in p.parts:
            continue
        if p.is_dir() and p.suffix.lower() == ".gdb":
            out.append(p)
        elif p.is_file() and p.suffix.lower() in (".shp", ".kml", ".geojson", ".gpkg", ".tab") \
                and not any(q.suffix.lower() == ".gdb" for q in p.parents):
            out.append(p)
    return out


def describe(src):
    rows = []
    for lyr, geom in pyogrio.list_layers(src):
        try:
            i = pyogrio.read_info(src, layer=lyr)
            rows.append({"source": src.name, "layer": lyr, "geometry": geom, "features": i["features"],
                         "crs": (i["crs"] or "NONE")[:20], "fields": ", ".join(i["fields"][:25])})
        except Exception as e:      # noqa: BLE001
            rows.append({"source": src.name, "layer": lyr, "geometry": geom, "features": None, "crs": f"error {str(e)[:40]}", "fields": ""})
    return rows


def categorical(df, maxu=40, skip=()):
    out = []
    for c in df.columns:
        if c == "geometry" or c in skip:
            continue
        nu = df[c].nunique(dropna=False)
        if 1 < nu <= maxu:
            vc = df[c].astype("object").fillna("(blank)").astype(str).value_counts().rename_axis(c).reset_index(name="features")
            out.append(f"`{c}`:\n\n{md(vc)}\n")
    return out


def a02_geology():
    L.append("## A02 - Surface Geology of Australia 1:1M\n")
    srcs = vector_sources("A02_ga_geology_1m")
    if not srcs:
        L.append("**BLOCKER:** nothing in data_raw/A02_ga_geology_1m.\n")
        return
    rows = sum((describe(s) for s in srcs), [])
    L.append(md(pd.DataFrame(rows)) + "\n")
    polys = [r for r in rows if r["geometry"] and "Polygon" in r["geometry"] and "lithology" in r["fields"].lower()]
    lines = [r for r in rows if r["geometry"] and "LineString" in r["geometry"]]
    if not polys:
        L.append("**BLOCKER:** no polygon layer with a `lithology` field.\n")
        return
    p = max(polys, key=lambda r: r["features"] or 0)
    src = next(s for s in srcs if s.name == p["source"])
    print(f"reading geology polygons {src.name}/{p['layer']} ...", flush=True)
    g = pyogrio.read_dataframe(src, layer=p["layer"])
    g.columns = [c if c == "geometry" else c.lower() for c in g.columns]
    g = g[g.geometry.notna()]
    g["km2"] = g.to_crs(AREA_CRS).area.values / 1e6
    L.append(f"Polygons used: `{src.name}` / `{p['layer']}`: {len(g):,}; CRS {g.crs}; total area {g.km2.sum():,.0f} km2; "
             f"invalid geometries {int((~g.geometry.is_valid).sum()):,}.\n")
    # classify each distinct lithology text once
    names = g["lithology"].fillna("").astype(str)
    uniq = names.unique()
    res = {n: classify(n) for n in uniq}
    g["main"] = names.map(lambda n: res[n]["main"] or "UNCLASSIFIED")
    cls = g.groupby("main")["km2"].agg(["size", "sum"]).reset_index()
    cls.columns = ["main_class", "polygons", "km2"]
    cls["share"] = (cls.km2 / cls.km2.sum()).round(3)
    cls["km2"] = cls.km2.round(0)
    cls = cls.sort_values("km2", ascending=False)
    cls.to_csv(OUT / "AU_lith_classes.csv", index=False)
    L.append("### Area by main rock class (India classifier, unchanged)\n\n" + md(cls) + "\n")
    um = pd.DataFrame([{"lithology": n, "km2": g.loc[names == n, "km2"].sum(), "main": res[n]["main"],
                        "present": ",".join(res[n]["present"])} for n in uniq if UM_RX.search(n)])
    if len(um):
        um = um.sort_values("km2", ascending=False).round(1)
        um.to_csv(OUT / "AU_um_terms.csv", index=False)
    L.append(f"### Ultramafic-type texts ({len(um)}; all in AU_um_terms.csv) - check main/present\n\n" + md(um, 40) + "\n")
    un = pd.DataFrame([{"lithology": n, "unmatched": "; ".join(res[n]["unmatched"]), "km2": g.loc[names == n, "km2"].sum()}
                       for n in uniq if res[n]["unmatched"] or not res[n]["main"]])
    if len(un):
        un = un.sort_values("km2", ascending=False).round(0)
        un.to_csv(OUT / "AU_lith_unmatched.csv", index=False)
        L.append(f"### Texts with unmatched parts: {len(un):,} (area {un.km2.sum():,.0f} km2); largest 40 (all in AU_lith_unmatched.csv)\n\n"
                 + md(un, 40) + "\n")
    for c in ("geolhist", "typename", "oldage_uri", "yngage_uri", "replith_uri"):
        if c in g:
            vc = g.groupby(g[c].fillna("(blank)").astype(str))["km2"].agg(["size", "sum"]).sort_values("sum", ascending=False).round(0)
            L.append(f"`{c}` (top 25 by area, {g[c].nunique():,} values):\n\n" + vc.head(25).reset_index().to_markdown(index=False) + "\n")
    for r in lines:
        s = next(x for x in srcs if x.name == r["source"])
        d = pyogrio.read_dataframe(s, layer=r["layer"], read_geometry=False)
        d.columns = [c.lower() for c in d.columns]
        L.append(f"### Lines `{s.name}` / `{r['layer']}`: {len(d):,}\n")
        L.extend(categorical(d, skip=("fltname", "name", "descr", "comments")))


def simple(folder, title, pattern=None):
    L.append(f"## {title}\n")
    srcs = vector_sources(folder)
    if not srcs:
        L.append(f"**MISSING:** nothing in data_raw/{folder}.\n")
        return
    rows = sum((describe(s) for s in srcs), [])
    L.append(md(pd.DataFrame(rows)) + "\n")
    for s in srcs[:3]:
        for lyr, _ in pyogrio.list_layers(s):
            d = pyogrio.read_dataframe(s, layer=lyr, read_geometry=False)
            L.extend(categorical(d, maxu=25))
            if pattern:
                txt = d.astype(str).agg(" | ".join, axis=1)
                hit = d[txt.str.contains(pattern, case=False, regex=True)]
                name = next((c for c in d.columns if c.lower() in ("name", "provname", "prov_name", "province")), d.columns[0])
                L.append(f"Features matching `{pattern}`: {len(hit)}\n\n" + md(hit[[name]].drop_duplicates(), 60) + "\n")


def a06_gravity():
    L.append("## A06 - National gravity grid\n")
    base = RAW / "A06_ga_gravity"
    grids = [p for p in base.rglob("*") if p.is_file() and p.suffix.lower() in (".ers", ".tif", ".tiff", ".nc", ".grd", ".img")] if base.exists() else []
    if not grids:
        L.append("**MISSING:** no grid in data_raw/A06_ga_gravity.\n")
        return
    import rasterio
    rows = []
    for p in grids:
        try:
            with rasterio.open(p) as r:
                a = r.read(1, out_shape=(max(1, r.height // 20), max(1, r.width // 20)), masked=True)
                rows.append({"file": str(p.relative_to(base))[:70], "crs": str(r.crs)[:25], "cell": f"{r.res[0]:.5g}",
                             "size": f"{r.width}x{r.height}", "nodata": r.nodata,
                             "p1": float(np.percentile(a.compressed(), 1)) if a.count() else None,
                             "p99": float(np.percentile(a.compressed(), 99)) if a.count() else None})
        except Exception as e:      # noqa: BLE001
            rows.append({"file": p.name, "crs": f"error {str(e)[:50]}"})
    L.append(md(pd.DataFrame(rows)) + "\n\nValues in um/s2 (GA convention) are 10x mGal: a 1-99% range of roughly -1,000 to +1,000 means um/s2.\n")


def a07_coast():
    L.append("## A07 - Coastline / land mask\n")
    srcs = vector_sources("A07_ga_coast")
    if not srcs:
        L.append("**MISSING:** nothing in data_raw/A07_ga_coast.\n")
        return
    rows = sum((describe(s) for s in srcs), [])
    L.append(md(pd.DataFrame(rows)) + "\n")
    for r in rows:
        if r["geometry"] and "Polygon" in r["geometry"]:
            s = next(x for x in srcs if x.name == r["source"])
            g = pyogrio.read_dataframe(s, layer=r["layer"])
            if g.crs is None:
                g = g.set_crs(4283)
            km2 = g.to_crs(AREA_CRS).area / 1e6
            L.append(f"`{s.name}`: {len(g):,} polygons, {km2.sum():,.0f} km2.\n")
            L.extend(categorical(g, maxu=15))


def a08_soilgas():
    L.append("## A08 - NSW soil-gas surveys (secondary, descriptive)\n")
    base = RAW / "A08_ga_nsw_soilgas"
    files = [p for p in base.rglob("*") if p.is_file() and not p.name.startswith(".")] if base.exists() else []
    if not files:
        L.append("**MISSING:** nothing in data_raw/A08_ga_nsw_soilgas.\n")
        return
    L.append("Files: " + ", ".join(sorted({str(p.relative_to(base))[:60] for p in files})[:40]) + "\n")
    for p in files:
        if p.suffix.lower() in (".xlsx", ".xls"):
            try:
                xl = pd.ExcelFile(p)
                for sh in xl.sheet_names[:6]:
                    d = pd.read_excel(p, sheet_name=sh, nrows=200)
                    L.append(f"- `{p.name}` / {sh}: columns {', '.join(map(str, d.columns[:25]))}\n")
            except Exception as e:      # noqa: BLE001
                L.append(f"- `{p.name}`: could not read ({str(e)[:60]})\n")
        elif p.suffix.lower() == ".shp":
            i = pyogrio.read_info(p)
            L.append(f"- `{p.name}`: {i['features']} features; fields {', '.join(i['fields'][:20])}\n")


def pick(cols, *rx):
    for r in rx:
        m = [c for c in cols if re.search(r, c, re.I)]
        if m:
            return m[0]
    return None


def a01_labels():
    L.append("## A01 - GA gas analyses: label sample (protocol 2026-11-02; counts only)\n")
    f = RAW / "A01_ga_orgchem" / "Hydrogen.csv"
    if not f.exists():
        L.append("**MISSING:** data_raw/A01_ga_orgchem/Hydrogen.csv (run scripts/20_au_gas_download.py).\n")
        return
    d = pd.read_csv(f, low_memory=False)
    # columns confirmed from metadata/au_gas_overview.md (GA ORGCHEM gas table, 290 columns)
    lon, lat, val, flag = "COLLAR_LONG_GDA94", "COLLAR_LAT_GDA94", "H2_MOLE_PERCENT", "ONSHORE_OFFSHORE"
    L.append(f"Rows: {len(d):,} gas analyses from {d['BOREHOLE_NAME'].nunique():,} boreholes. Value column `{val}` (mol%).\n")
    raw = d[val].astype(str).str.strip()
    v = pd.to_numeric(raw.str.replace("<", "", regex=False), errors="coerce")
    blank = d[val].isna() | raw.isin(["", "nan", "None"])
    trace = raw.str.contains(r"tr|<|nd|bdl", case=False, na=False)
    x, y = pd.to_numeric(d[lon], errors="coerce"), pd.to_numeric(d[lat], errors="coerce")
    pos = ~blank & (v >= 0.5)
    neg = ~blank & ((v < 0.5) | (trace & v.isna()))
    zero = ~blank & (v == 0)
    bins = [-1e9, 0, 0.001, 0.01, 0.1, 0.5, 1, 5, 10, 1e9]
    lab = ["0 (exact)", "0-0.001", "0.001-0.01", "0.01-0.1", "0.1-0.5", "0.5-1", "1-5", "5-10", ">10"]
    tab = pd.crosstab(pd.cut(v, bins, labels=lab), d[flag].fillna("(blank)")).reindex(lab)
    L.append("H2 (mol%) by GA's onshore/offshore flag:\n\n" + tab.to_markdown() + f"\n\nBlank / non-numeric: {int(blank.sum()):,}.\n")
    for c in ("CONTAMINATION", "CONTAMINATION_INTERPRETED", "SAMPLE_TYPE", "BOREHOLE_TYPE", "PROJECT", "GAS_DESC"):
        if c in d:
            vc = d.loc[~blank, c].fillna("(blank)").astype(str).value_counts().head(12)
            L.append(f"`{c}` (rows with H2 reported):\n\n" + vc.rename("rows").to_frame().to_markdown() + "\n")
    s = pd.DataFrame({"lon": x, "lat": y, "pos": pos, "neg": neg, "zero": zero, "v": v,
                      "onshore": d[flag].astype(str).str.lower().eq("onshore"),
                      "prov": d.get("GEOLOGICAL_PROVINCE", pd.Series("", index=d.index)).astype(str).str.split(";").str[0],
                      "well": d["BOREHOLE_NAME"], "c1": pd.to_numeric(d.get("C1_MOLE_PERCENT"), errors="coerce"),
                      "n2": pd.to_numeric(d.get("N2_MOLE_PERCENT"), errors="coerce")})
    s = s[(s.pos | s.neg) & s.lon.notna() & s.lat.notna()].copy()
    land = None
    for src in vector_sources("A07_ga_coast"):
        for lyr, geom in pyogrio.list_layers(src):
            if geom and "Polygon" in geom and land is None:
                land = pyogrio.read_dataframe(src, layer=lyr)
    if land is not None:
        import geopandas as gpd
        if land.crs is None:
            land = land.set_crs(4283)
        pts = gpd.GeoDataFrame(s, geometry=gpd.points_from_xy(s.lon, s.lat), crs=4283).to_crs(land.crs)
        inside = s.index.isin(gpd.sjoin(pts, land[["geometry"]], predicate="within", how="inner").index)
        L.append(f"Cross-check with the A07 land mask: GA 'onshore' {int(s.onshore.sum()):,}, inside land polygons "
                 f"{int(inside.sum()):,}, disagreeing {int((s.onshore != inside).sum()):,}.\n")
    L.append(f"Samples with H2 reported and coordinates: {len(s):,} (positive {int(s.pos.sum())}, negative {int(s.neg.sum())}, "
             f"of which exact zero {int(s.zero.sum()):,}); onshore {int(s.onshore.sum()):,} (positive {int((s.pos & s.onshore).sum())}).\n")
    on = s[s.onshore]
    if len(on):
        dil = on.groupby(on.pos.map({True: "H2 >= 0.5", False: "H2 < 0.5"}))[["c1", "n2"]].median().round(1)
        L.append("Dilution check (onshore medians, mol%):\n\n" + dil.to_markdown() + "\n")
        top = on[on.pos].sort_values("v", ascending=False)[["well", "prov", "v", "c1", "n2"]].head(25)
        L.append("Onshore positive samples (top 25 by H2):\n\n" + md(top.round(2)) + "\n")
    import h3
    o = s[s.onshore].copy()
    o["c6"] = [h3.latlng_to_cell(a, b, 6) for a, b in zip(o.lat, o.lon)]
    o["c3"] = [h3.cell_to_parent(c, 3) for c in o.c6]
    cells = o.groupby("c6").agg(pos=("pos", "max"), c3=("c3", "first"), prov=("prov", "first"),
                                nz=("zero", "min"))
    blocks = cells.groupby("c3")["pos"].agg(["size", "sum"])
    npos, nneg = int(cells.pos.sum()), int((~cells.pos).sum())
    verdict = "meets" if npos >= 20 and nneg >= 100 else "DOES NOT meet"
    L.append(f"**After declustering (onshore):** {len(cells):,} cells - {npos} positive, {nneg} negative - in {len(blocks):,} blocks "
             f"({int((blocks['sum'] > 0).sum())} blocks with a positive). The minimum sample (20 positive, 100 negative cells) {verdict}.\n")
    s1 = o.groupby("c6")["v"].max()
    nz = cells[~(cells.nz & ~cells.pos)]
    L.append(f"Without cells whose only H2 values are exact zeros: {int(nz.pos.sum())} positive, {int((~nz.pos).sum())} negative cells.\n")
    bp = cells.groupby("prov")["pos"].agg(["size", "sum"]).rename(columns={"size": "cells", "sum": "positive_cells"})
    bp = bp.sort_values(["positive_cells", "cells"], ascending=False).reset_index()
    L.append("Onshore cells by geological province (concentration check):\n\n" + md(bp, 15) + "\n")
    L.append(f"Sensitivity labels (>= 1 mol% / <= 0.1 mol%): {int((s1 >= 1).sum())} positive, {int((s1 <= 0.1).sum())} negative cells.\n")
    fig, ax = plt.subplots(figsize=(8, 7))
    ax.scatter(s.lon[s.neg], s.lat[s.neg], s=3, c="grey", label="H2 < 0.5 mol%")
    ax.scatter(s.lon[s.pos], s.lat[s.pos], s=14, c="red", label="H2 >= 0.5 mol%")
    if land is not None:
        land.to_crs(4326).boundary.plot(ax=ax, lw=0.4, color="k")
    ax.set_xlim(AU_BOX[0], AU_BOX[2]); ax.set_ylim(AU_BOX[1], AU_BOX[3]); ax.legend(); ax.set_title("GA gas analyses with H2 reported")
    fig.savefig(OUT / "AU_sample.png", dpi=120, bbox_inches="tight"); plt.close(fig)
    L.append("![sample](AU_sample.png)\n")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    L.extend(["# Australia test - data audit", ""])
    steps = [a01_labels, a02_geology,
             lambda: simple("A03_ga_crustal_boundaries", "A03 - Major Crustal Boundaries"),
             lambda: simple("A04_ga_neotectonic", "A04 - Neotectonic features"),
             lambda: simple("A05_ga_provinces", "A05 - Geological provinces", r"greenstone|ophiolit|rift|craton|komatii"),
             a06_gravity, a07_coast, a08_soilgas]
    for fn in steps:
        try:
            fn()
        except Exception as err:      # noqa: BLE001
            L.append(f"**ERROR:** {err}\n\n```\n{traceback.format_exc()[-1500:]}\n```\n")
        (OUT / "AU_audit.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote metadata/audit/AU_audit.md")


if __name__ == "__main__":
    main()
