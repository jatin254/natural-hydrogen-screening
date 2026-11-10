"""
11_layer_depth_heat.py  -  Phase 3, step 5: basement depth and heat flow per cell

Basement depth (GSI tectonic map, D16 BASEMENT_DEPTH_TECTONIC): contour lines in metres.
  Lines are turned into points every 2 km; each cell gets an inverse-distance-weighted depth
  from contour points within 40 km. Further than 40 km from any contour = no estimate (NaN):
  the map only contours sedimentary basins.
Heat flow (IHFC 2024, D06): onshore sites only; values <= 0 or > 250 mW/m2 dropped.
  No interpolation into unsampled areas (audit decision): each cell gets the median of sites
  within 50 km, the count, and the distance to the nearest site.

Writes layers/india_h3r6.gpkg table "depth_heat" and metadata/depth_heat_check.md.
Run:  python scripts/11_layer_depth_heat.py     (a few minutes)
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h2pros.grid import CRS_DIST, RAW, load_grid, raw, read_clean, write_layer   # noqa: E402

STEP, R_DEPTH, R_HF = 2000, 40_000, 50_000


def basement_depth(cent):
    import shapely
    b = read_clean(raw("D16_gsi_tectonic", "BASEMENT_DEPTH_TECTONIC"))
    b["depth"] = pd.to_numeric(b["depth"], errors="coerce")
    b = b.dropna(subset=["depth"])
    # some contours (Assam shelf) are entered in km: a basement contour of 1-20 "m" is not real
    km = (b["depth"] > 0) & (b["depth"] <= 20)
    b.loc[km, "depth"] *= 1000
    print(f"    {int(km.sum())} contours with values 1-20 treated as km and converted to m")
    lines = shapely.segmentize(b.to_crs(CRS_DIST).geometry.values, STEP)
    xy, idx = shapely.get_coordinates(lines, return_index=True)
    pts = shapely.points(xy)
    val = b["depth"].values[idx]
    tree = shapely.STRtree(pts)
    ic, ip = tree.query(cent, predicate="dwithin", distance=R_DEPTH)
    d = np.maximum(shapely.distance(cent[ic], pts[ip]), 100.0)
    w = 1.0 / d ** 2
    num = np.bincount(ic, weights=w * val[ip], minlength=len(cent))
    den = np.bincount(ic, weights=w, minlength=len(cent))
    depth = np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)
    _, dist = tree.query_nearest(cent, return_distance=True, all_matches=False)
    nval = pd.DataFrame({"c": ic, "v": val[ip]}).groupby("c")["v"].nunique().reindex(range(len(cent))).fillna(0).astype(int).values
    print(f"    basement depth: {len(b)} contours -> {len(pts):,} points; cells with an estimate: {int((den > 0).sum()):,}")
    return depth, dist / 1000.0, nval


def load_ihfc():
    spec = importlib.util.spec_from_file_location("audit03", ROOT / "scripts" / "03_audit_datasets.py")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    files = sorted((RAW / "D06_ihfc").rglob("*.txt"))
    files = [f for f in files if "ghfdb" in f.name.lower() and not f.name.startswith("._")] or files
    data, fields, id_col, pid_col = audit.read_ihfc(files[0])
    num = lambda c: pd.to_numeric(data[c], errors="coerce")   # noqa: E731
    p = pd.DataFrame({"pid": data[pid_col], "q": num("P1"), "lat": num("P4"), "lon": num("P5"),
                      "env": data["P7"].astype(str).str.lower()}).drop_duplicates("pid")
    n0 = len(p)
    p = p.dropna(subset=["q", "lat", "lon"])
    p = p[p["env"].str.contains("onshore") & (p["q"] > 0) & (p["q"] <= 250)]
    p = p[p["lon"].between(60, 100) & p["lat"].between(0, 40)]
    print(f"    heat flow: {n0:,} sites worldwide; {len(p):,} onshore, valid, in the India region")
    return p


def main():
    import geopandas as gpd
    import shapely
    grid = load_grid()
    out = grid[["h3", "geometry"]].copy()
    cent = grid.to_crs(CRS_DIST).geometry.centroid.values

    print("basement depth ...")
    depth, dist, nval = basement_depth(cent)
    out["bd_depth_m"] = np.round(depth, 0)
    out["bd_dist_km"] = np.round(dist, 2)
    out["bd_n_contours"] = nval

    print("heat flow ...")
    hf = load_ihfc()
    hg = gpd.GeoDataFrame(hf, geometry=gpd.points_from_xy(hf["lon"], hf["lat"]), crs=4326).to_crs(CRS_DIST)
    hp = hg.geometry.values
    tree = shapely.STRtree(hp)
    ic, ih = tree.query(cent, predicate="dwithin", distance=R_HF)
    g = pd.DataFrame({"c": ic, "q": hf["q"].values[ih]}).groupby("c")["q"]
    out["hf_median_50km"] = g.median().reindex(range(len(out))).round(1).values
    out["hf_n_50km"] = g.size().reindex(range(len(out))).fillna(0).astype(int).values
    _, d = tree.query_nearest(cent, return_distance=True, all_matches=False)
    out["d_hf_site_km"] = np.round(d / 1000.0, 2)

    out = out[[c for c in out.columns if c != "geometry"] + ["geometry"]]
    write_layer(gpd.GeoDataFrame(out, crs=grid.crs), "depth_heat")

    z = out.drop(columns="geometry").merge(grid[["h3", "state"]], on="h3")
    by = z.groupby("state").agg(cells=("h3", "size"),
                                depth_cells=("bd_depth_m", lambda s: int(s.notna().sum())),
                                depth_max_m=("bd_depth_m", "max"),
                                hf_cells=("hf_median_50km", lambda s: int(s.notna().sum())),
                                hf_median=("hf_median_50km", "median")).reset_index()
    L = ["# Basement depth and heat flow on the grid", "",
         f"Cells with a basement-depth estimate: {int(out['bd_depth_m'].notna().sum()):,} of {len(out):,} "
         f"(within {R_DEPTH // 1000} km of a contour). Depth range {np.nanmin(depth):,.0f}-{np.nanmax(depth):,.0f} m.",
         f"Heat-flow sites used: {len(hf):,}. Cells with a site within {R_HF // 1000} km: "
         f"{int(out['hf_median_50km'].notna().sum()):,}; median of those cells {np.nanmedian(out['hf_median_50km']):.0f} mW/m2.", "",
         by.sort_values("cells", ascending=False).round(1).to_markdown(index=False), ""]
    (ROOT / "metadata" / "depth_heat_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("    wrote metadata/depth_heat_check.md")


if __name__ == "__main__":
    main()
