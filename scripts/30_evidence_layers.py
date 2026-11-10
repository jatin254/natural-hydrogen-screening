"""
30_evidence_layers.py  -  build the three evidence layers per H3 cell (NOT scored)

Rules: decisions_log 2026-11-09 (two entries). V2 and the pilot key are not touched.

  magnetic   GSI ground magnetic stations (D24, cite:magnetic_gcs_ngdr, anomaly in nT)
             regional = median of cell medians within 50 km (>= 5 cells with data)
             station residual = anomaly - regional; |residual| > 5,000 nT dropped as errors
             cell value = SECOND-largest |residual| (cells need >= 3 stations, so one bad station
             cannot set the value); flag = top 10% of covered cells
  radiometric GSI NGCM stream sediments (D25, cite:stream_sediments_gcs_ngdr; U, Th ppm; K2O %)
             cell value = median of samples (>= 3 samples); flag = U or Th in the top 10% of covered cells
             Cr, Ni, MgO medians kept as context columns (ultramafic catchments) - no flag, no test
  water      CGWB groundwater quality 2019-2023 (D23, from 29_evidence_data.py water)
             flag = >= 1 sample within 5 km of the cell with pH >= 10 and Ca > Mg (meq/L)
             descriptive tier: pH >= 9 (reported, not tested)
  No data -> flag is empty (NaN), not 0; such sites are left out of that layer's test.

Writes
  layers/india_h3r6.gpkg  table "evidence"   (open in QGIS)
  metadata/evidence_layers.md (+ evidence_layers.png)

Run:  python scripts/30_evidence_layers.py                 (all three; ~10-20 minutes)
      python scripts/30_evidence_layers.py --only water    (one layer; others left empty)
"""
import argparse
import re
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h2pros.grid import CRS_DIST, GPKG, RAW, RES, load_grid, write_layer   # noqa: E402

META = ROOT / "metadata"
TOP = 0.90                       # top 10%
R_REGIONAL = 50_000              # m
MIN_REG_CELLS = 5
MAG_MAX_RES = 5000               # nT
MIN_STATIONS = 3
MIN_SAMPLES = 3
WATER_KM = 5
T0 = time.time()


def stage(msg):
    print(f"[{(time.time() - T0) / 60:5.1f} min] {msg}", flush=True)


def num(s):
    """Numbers from messy text: '<0.1' -> 0.05 (half the detection limit); 'BDL', '<Null>', '' -> NaN."""
    if s.dtype.kind in "fi":
        return s.astype(float)
    t = s.astype(str).str.strip()
    lt = t.str.startswith("<")
    v = pd.to_numeric(t.str.lstrip("<").str.strip(), errors="coerce")
    return v.where(~lt, v / 2)


def cells_of(lon, lat):
    import h3
    return np.array([h3.latlng_to_cell(y, x, RES) for x, y in zip(lon, lat)])


def read_points(path, wanted):
    """wanted: {our name: regex for the server column}. Returns numeric frame with our names."""
    import pyogrio
    cols = list(pyogrio.read_info(path)["fields"])
    pick = {}
    for k, rx in wanted.items():
        hit = [c for c in cols if re.fullmatch(rx, c, re.I)]
        if not hit:
            raise SystemExit(f"{path.name}: no column matching {rx!r} (columns: {cols})")
        pick[k] = hit[0]
    d = pyogrio.read_dataframe(path, columns=list(pick.values()), read_geometry=False)
    d = d.rename(columns={v: k for k, v in pick.items()})
    for c in d.columns:
        d[c] = num(d[c])
    return d, pick


def q_flag(v, q=TOP):
    ok = ~np.isnan(v)
    thr = float(np.quantile(v[ok], q)) if ok.any() else np.nan
    f = np.where(ok, (v >= thr).astype(float), np.nan)
    return f, thr


# ---------------------------------------------------------------- magnetic

def magnetic(grid, pi, pj, L):
    path = RAW / "D24_gsi_magnetic" / "MAGNETIC" / "All_India.geojson"
    n = len(grid)
    empty = {"mag_n": np.zeros(n, int), "mag_res2": np.full(n, np.nan), "mag_flag": np.full(n, np.nan)}
    if not path.exists():
        L += ["## Magnetic", "", f"Not built: {path.relative_to(ROOT)} not found "
              "(python scripts/04_ngdr_download.py download --only D24).", ""]
        return empty
    stage("magnetic: reading stations ...")
    d, pick = read_points(path, {"lon": r"longitude.*", "lat": r"latitude.*", "obs": r"observed.*",
                                 "igrf": r"igrf.*", "anom": r"magnetic_a.*"})
    n0 = len(d)
    d = d.dropna()
    d = d[d.lon.between(66, 99) & d.lat.between(5, 38) & d.obs.between(30000, 60000) & d.igrf.between(30000, 60000)]
    incons = (d.obs - d.igrf - d.anom).abs() > 5
    d = d[~incons].drop_duplicates(["lon", "lat", "anom"])
    d["h3"] = cells_of(d.lon.values, d.lat.values)
    pos = pd.Series(np.arange(n), index=grid["h3"].values)
    d = d[d.h3.isin(pos.index)]
    d["i"] = pos[d.h3].values
    stage(f"    {n0:,} read, {len(d):,} valid (inconsistent obs-IGRF-anomaly: {int(incons.sum()):,})")
    cm = d.groupby("i")["anom"].median()
    v = np.full(n, np.nan)
    v[cm.index.values] = cm.values
    pr = pd.DataFrame({"i": pi, "v": v[pj]}).dropna()
    g = pr.groupby("i")["v"].agg(["median", "size"])
    reg = np.full(n, np.nan)
    ok = g["size"] >= MIN_REG_CELLS
    reg[g.index.values[ok]] = g["median"].values[ok]
    d["res"] = d["anom"] - reg[d["i"].values]
    d = d.dropna(subset=["res"])
    bad = d["res"].abs() > MAG_MAX_RES
    d = d[~bad].copy()
    d["ar"] = d["res"].abs()
    size = d.groupby("i").size()
    second = d.sort_values(["i", "ar"], ascending=[True, False]).groupby("i").nth(1).set_index("i")["ar"]
    second = second[size.reindex(second.index) >= MIN_STATIONS]
    res2 = np.full(n, np.nan)
    res2[second.index.values] = second.values
    flag, thr = q_flag(res2)
    cnt = np.zeros(n, int)
    cnt[size.index.values] = size.values
    cov = int((~np.isnan(res2)).sum())
    L += ["## Magnetic (GSI ground stations, D24)", "",
          f"- columns used: {pick}",
          f"- stations: {n0:,} read; {len(d):,} used (dropped: bad values/duplicates, {int(incons.sum()):,} inconsistent "
          f"observed - IGRF - anomaly, {int(bad.sum()):,} with |residual| > {MAG_MAX_RES:,} nT)",
          f"- cells covered (>= {MIN_STATIONS} stations): {cov:,} of {n:,} ({cov / n:.0%})",
          f"- |residual| (2nd largest per cell): median {np.nanmedian(res2):.0f} nT; flag threshold (top 10%) "
          f"**{thr:.0f} nT**; flagged cells {int(np.nansum(flag)):,}", ""]
    return {"mag_n": cnt, "mag_res2": np.round(res2, 1), "mag_flag": flag}


# ---------------------------------------------------------------- radiometric (NGCM)

def radiometric(grid, L):
    path = RAW / "D25_gsi_ngcm" / "STREAM_SEDIMENTS" / "All_India.geojson"
    n = len(grid)
    keys = ["rad_n", "u_ppm", "th_ppm", "k2o_pct", "cr_ppm", "ni_ppm", "mgo_pct", "rad_flag"]
    empty = {k: (np.zeros(n, int) if k == "rad_n" else np.full(n, np.nan)) for k in keys}
    if not path.exists():
        L += ["## Radiometric", "", f"Not built: {path.relative_to(ROOT)} not found "
              "(python scripts/04_ngdr_download.py download --only D25).", ""]
        return empty
    stage("radiometric: reading NGCM stream sediments ...")
    d, pick = read_points(path, {"lon": r"longitude", "lat": r"latitude", "u": r"u", "th": r"th", "k2o": r"k2o",
                                 "cr": r"cr", "ni": r"ni", "mgo": r"mgo"})
    n0 = len(d)
    d = d.dropna(subset=["lon", "lat"])
    d = d[d.lon.between(66, 99) & d.lat.between(5, 38)]
    for c, hi in (("u", 2000), ("th", 5000), ("k2o", 20), ("cr", 50000), ("ni", 20000), ("mgo", 60)):
        d.loc[(d[c] < 0) | (d[c] > hi), c] = np.nan
    d = d.drop_duplicates(["lon", "lat", "u", "th"])
    d["h3"] = cells_of(d.lon.values, d.lat.values)
    pos = pd.Series(np.arange(n), index=grid["h3"].values)
    d = d[d.h3.isin(pos.index)]
    d["i"] = pos[d.h3].values
    m = d.groupby("i")[["u", "th", "k2o", "cr", "ni", "mgo"]].median()
    cnt = d.dropna(subset=["u", "th"], how="all").groupby("i").size()
    out = {k: np.full(n, np.nan) for k in keys}
    out["rad_n"] = np.zeros(n, int)
    out["rad_n"][cnt.index.values] = cnt.values
    good = cnt.index.values[cnt.values >= MIN_SAMPLES]
    for col, k in (("u", "u_ppm"), ("th", "th_ppm"), ("k2o", "k2o_pct"), ("cr", "cr_ppm"), ("ni", "ni_ppm"), ("mgo", "mgo_pct")):
        out[k][good] = m.loc[good, col].values
    fu, tu = q_flag(out["u_ppm"])
    ft, tt = q_flag(out["th_ppm"])
    flag = np.where(np.isnan(fu) & np.isnan(ft), np.nan, np.nan_to_num(fu) + np.nan_to_num(ft) > 0)
    out["rad_flag"] = flag.astype(float)
    cov = int((~np.isnan(flag)).sum())
    L += ["## Radiometric (GSI NGCM stream sediments, D25)", "",
          f"- columns used: {pick}",
          f"- samples: {n0:,} read; {len(d):,} inside the grid",
          f"- cells covered (>= {MIN_SAMPLES} samples with U or Th): {cov:,} of {n:,} ({cov / n:.0%})",
          f"- medians over covered cells: U {np.nanmedian(out['u_ppm']):.1f} ppm, Th {np.nanmedian(out['th_ppm']):.1f} ppm, "
          f"K2O {np.nanmedian(out['k2o_pct']):.2f} % (unit check: typical crust U ~2-3 ppm, Th ~8-11 ppm)",
          f"- flag thresholds (top 10%): **U >= {tu:.1f} ppm or Th >= {tt:.1f} ppm**; flagged cells {int(np.nansum(flag)):,}",
          "- Cr, Ni, MgO medians stored as context only (no flag, no test).", ""]
    return out


# ---------------------------------------------------------------- water

CANON = {"ph": r"ph_mg_l\d*", "ca": r"ca_mgl\d*", "mg": r"mg_mg_l\d*", "co3": r"co3_mg_l\d*",
         "hco3": r"hco3_mg_l\d*", "ec": r"ec_mg_l\d*", "u_ppb": r"u_ppb_mg_l\d*", "year": r"year_",
         "state": r"state_", "district": r"district_name", "block": r"block_", "location": r"locat_?",
         "well_id": r"gems_id(_w)?"}


def water_samples():
    files = sorted((RAW / "D23_cgwb_gwq").glob("layer_*.csv"))
    parts = []
    for f in files:
        x = pd.read_csv(f, dtype=str)
        ren = {}
        for k, rx in CANON.items():
            hit = [c for c in x.columns if re.fullmatch(rx, c, re.I)]
            if hit:
                ren[hit[0]] = k
        y = x.rename(columns=ren)
        keep = ["lon", "lat"] + [k for k in CANON if k in y.columns]
        y = y[keep].copy()
        y["source_file"] = f.name
        parts.append(y)
    if not parts:
        return None
    d = pd.concat(parts, ignore_index=True)
    for c in ("lon", "lat", "ph", "ca", "mg", "co3", "hco3", "ec", "u_ppb", "year"):
        if c in d:
            d[c] = num(d[c])
    d.loc[~d["ph"].between(0, 14, inclusive="neither"), "ph"] = np.nan
    d = d[d.lon.between(66, 99) & d.lat.between(5, 38)]
    d["ca_meq"] = d["ca"] / 20.04
    d["mg_meq"] = d["mg"] / 12.15
    return d


def water(grid, L):
    import geopandas as gpd
    import shapely
    n = len(grid)
    keys = ["w_n", "w_ph_max", "w_ph9", "water_flag", "w_u_ppb_max"]
    out = {k: np.full(n, np.nan) for k in keys}
    out["w_n"] = np.zeros(n, int)
    d = water_samples()
    if d is None:
        L += ["## Groundwater", "", "Not built: no data_raw/D23_cgwb_gwq/layer_*.csv "
              "(python scripts/29_evidence_data.py water).", ""]
        return out, None
    stage(f"water: {len(d):,} samples; matching to cells within {WATER_KM} km ...")
    pts = gpd.GeoSeries(gpd.points_from_xy(d.lon, d.lat), crs=4326).to_crs(CRS_DIST).values
    polys = grid.to_crs(CRS_DIST).geometry.values
    tree = shapely.STRtree(polys)
    iw, ic = tree.query(pts, predicate="dwithin", distance=WATER_KM * 1000)
    s = d.iloc[iw].reset_index(drop=True)
    s["i"] = ic
    s["hit10"] = (s["ph"] >= 10) & (s["ca_meq"] > s["mg_meq"])
    s["hit9"] = s["ph"] >= 9
    has_ph = s[s["ph"].notna()]
    g = has_ph.groupby("i").agg(n=("ph", "size"), ph_max=("ph", "max"), h10=("hit10", "any"), h9=("hit9", "any"))
    out["w_n"][g.index.values] = g["n"].values
    out["w_ph_max"][g.index.values] = g["ph_max"].values
    out["water_flag"][g.index.values] = g["h10"].astype(float).values
    out["w_ph9"][g.index.values] = g["h9"].astype(float).values
    if "u_ppb" in s:
        gu = s.groupby("i")["u_ppb"].max()
        out["w_u_ppb_max"][gu.index.values] = gu.values
    cov = int((out["w_n"] > 0).sum())
    wells = d.dropna(subset=["ph"])
    hits = wells[wells["ph"] >= 10].copy()
    hits["ca_gt_mg"] = hits["ca_meq"] > hits["mg_meq"]
    try:
        import pyogrio
        lith = pyogrio.read_dataframe(GPKG, layer="lithology", columns=["h3", "f_UM"], read_geometry=False)
        um_cells = set(lith.loc[lith["f_UM"].fillna(0) > 0, "h3"])
        um_idx = np.where(grid["h3"].isin(um_cells).values)[0]
        near = set(iw[np.isin(ic, um_idx)])
        hits["near_ultramafic_cell"] = [k in near for k in hits.index.map(lambda j: d.index.get_loc(j))]
    except Exception as err:   # lithology table missing in a test grid
        hits["near_ultramafic_cell"] = np.nan
        print(f"    (ultramafic check skipped: {err})")
    show = [c for c in ("state", "district", "block", "location", "year", "ph", "ca", "mg", "ca_gt_mg", "co3", "hco3",
                        "ec", "near_ultramafic_cell", "lon", "lat") if c in hits]
    L += ["## Groundwater (CGWB 2019-2023 via Esri India, D23)", "",
          f"- samples: {len(d):,}; with pH: {len(wells):,}; files: {', '.join(sorted(d['source_file'].unique()))}",
          f"- cells with >= 1 sample within {WATER_KM} km: {cov:,} of {n:,} ({cov / n:.0%})",
          f"- samples with pH >= 9: {int((wells['ph'] >= 9).sum()):,}; pH >= 10: {len(hits):,}; "
          f"pH >= 10 and Ca > Mg: {int(hits['ca_gt_mg'].sum())}",
          f"- flagged cells (pH >= 10 and Ca > Mg within {WATER_KM} km): {int(np.nansum(out['water_flag'])):,}; "
          f"pH >= 9 tier: {int(np.nansum(out['w_ph9'])):,}",
          "- Caution: pH >= 10 with CO3 reported as 0 is chemically odd for carbonate waters and may be a typing error; "
          "the dataset gives no well type (tube-well cement can raise pH).", ""]
    if len(hits):
        L += ["### Samples with pH >= 10", "", hits[show].sort_values("ph", ascending=False).head(60).to_markdown(index=False), ""]
    return out, hits


# ---------------------------------------------------------------- pilot join + report

def pairs_within(pts, radius):
    import shapely
    tree = shapely.STRtree(pts)
    i, j = tree.query(pts, predicate="dwithin", distance=radius)
    return i.astype(np.int32), j.astype(np.int32)


def main():
    import geopandas as gpd
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", choices=["magnetic", "radiometric", "water"])
    args = ap.parse_args()
    todo = set(args.only or ["magnetic", "radiometric", "water"])
    grid = load_grid()
    n = len(grid)
    L = ["# Evidence layers (not scored)", "",
         f"Built {time.strftime('%Y-%m-%d %H:%M')} by scripts/30_evidence_layers.py. Rules: decisions_log 2026-11-09. "
         f"Grid: {n:,} cells (H3 res {RES}). No data = flag empty, not 0.", "",
         "Product of Geological Survey of India; reproduced by permission of Director General on behalf of Government of India "
         "(magnetic, radiometric). Groundwater: Central Ground Water Board data via Esri India (licence unconfirmed; internal use).", ""]
    res = {}
    if "magnetic" in todo:
        stage("neighbour lists (50 km) ...")
        pi, pj = pairs_within(grid.to_crs(CRS_DIST).geometry.centroid.values, R_REGIONAL)
        res.update(magnetic(grid, pi, pj, L))
        del pi, pj
    if "radiometric" in todo:
        res.update(radiometric(grid, L))
    hits = None
    if "water" in todo:
        w, hits = water(grid, L)
        res.update(w)
    ev = grid[["h3", "lon", "lat", "state", "geometry"]].copy()
    for k, v in res.items():
        ev[k] = v
    if GPKG.exists():
        import pyogrio
        if "evidence" in pyogrio.list_layers(GPKG)[:, 0]:
            old = pyogrio.read_dataframe(GPKG, layer="evidence", read_geometry=False)
            keep = [c for c in old.columns if c not in ev.columns]
            ev = ev.merge(old[["h3"] + keep], on="h3", how="left")   # keep layers not rebuilt this run
    ev = ev[[c for c in ev.columns if c != "geometry"] + ["geometry"]]
    write_layer(gpd.GeoDataFrame(ev, geometry="geometry", crs=grid.crs), "evidence")
    fig, axs = plt.subplots(1, 3, figsize=(16, 6))
    for ax, (col, t) in zip(axs, [("mag_res2", "Magnetic |residual| (nT)"), ("th_ppm", "Th in stream sediment (ppm)"),
                                  ("w_ph_max", "Max groundwater pH within 5 km")]):
        if col in ev and ev[col].notna().any():
            v = ev[col].values.astype(float)
            sc = ax.scatter(ev["lon"], ev["lat"], c=v, s=0.3, cmap="viridis",
                            vmin=np.nanpercentile(v, 2), vmax=np.nanpercentile(v, 98))
            fig.colorbar(sc, ax=ax, shrink=0.6)
        ax.set_title(t); ax.set_aspect("equal")
    fig.savefig(META / "evidence_layers.png", dpi=120, bbox_inches="tight"); plt.close(fig)
    L += ["![maps](evidence_layers.png)", ""]
    (META / "evidence_layers.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    stage("done - wrote metadata/evidence_layers.md; send it to me")


if __name__ == "__main__":
    main()
