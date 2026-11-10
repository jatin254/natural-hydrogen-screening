"""
09_layer_structures.py  -  Phase 3, step 3: structures, tectonic setting and point evidence per cell

Distances are from each cell centre, in km (EPSG:7755, India LCC). Nothing is scored yet:
these are the raw measurements the play-fairway rules will turn into chances in Phase 4.

Writes layers/india_h3r6.gpkg, table "structures":
  d_fault_basement   faults involving basement (GSI codes Fib, Fibc)          - deep pathways
  d_fault_any        any fault or lineament in FAULT_TECTONIC
  d_neotectonic      neotectonic faults (codes with NF), incl. neotectonic thrusts - active / open, or leaking
  d_thrust           thrusts (THRUST_TECTONIC)
  d_shear            crustal shear zones (SHEAR_ZONE_TECTONIC)
  d_suture           sutures (SUTURE_ZONE_TECTONIC)
  tf_class           tectonic-framework unit covering most of the cell
  tf_ophiolite, tf_greenstone, tf_rift, tf_accretion   share of the cell in those settings
  n_um_strong, n_um_moderate, d_um_strong   ultramafic mineral-evidence sites (from 05_lithology_classes.py)
  d_spring, spring_tmax_25km               thermal springs: distance, hottest spring within 25 km (deg C)
Run:  python scripts/09_layer_structures.py     (a few minutes)
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h2pros.grid import CRS_AREA, CRS_DIST, area_matrix, load_grid, raw, read_clean, write_layer   # noqa: E402

TF_GROUPS = {   # tectonic_f text -> group (GSI tectonic map legend)
    "tf_ophiolite": r"OPHIOLITE|MELANGE",
    "tf_greenstone": r"GREENSTONE|SUPRACRUSTAL",
    "tf_rift": r"RIFT|GRABEN",
    "tf_accretion": r"ACCRETIONARY|ACCRETED ARC",
}


def nearest_km(points, lines):
    """Distance (km) from each point to the nearest geometry; NaN if there are none."""
    import shapely
    if len(lines) == 0:
        return np.full(len(points), np.nan)
    tree = shapely.STRtree(lines)
    _, d = tree.query_nearest(points, return_distance=True, all_matches=False)
    return d / 1000.0


def main():
    import geopandas as gpd
    import shapely
    grid = load_grid()
    out = grid[["h3", "geometry"]].copy()
    cent = grid.to_crs(CRS_DIST).geometry.centroid.values

    print("structures ...")
    f = read_clean(raw("D16_gsi_tectonic", "FAULT_TECTONIC"))
    code = f["code"].fillna("").astype(str)
    fd = f.to_crs(CRS_DIST).geometry.values
    basement = code.str.contains(r"Fib", regex=True).values          # Fib, Fibc (+ mixed codes)
    neo_f = code.str.contains(r"\bNF\b|^NF", regex=True).values
    t = read_clean(raw("D16_gsi_tectonic", "THRUST_TECTONIC"))
    td = t.to_crs(CRS_DIST).geometry.values
    neo_t = t["code"].fillna("").astype(str).str.contains("NF").values
    out["d_fault_basement"] = nearest_km(cent, fd[basement]).round(2)
    out["d_fault_any"] = nearest_km(cent, fd).round(2)
    out["d_neotectonic"] = nearest_km(cent, np.concatenate([fd[neo_f], td[neo_t]])).round(2)
    out["d_thrust"] = nearest_km(cent, td).round(2)
    for col, layer in [("d_shear", "SHEAR_ZONE_TECTONIC"), ("d_suture", "SUTURE_ZONE_TECTONIC")]:
        out[col] = nearest_km(cent, read_clean(raw("D16_gsi_tectonic", layer)).to_crs(CRS_DIST).geometry.values).round(2)

    print("tectonic framework ...")
    tf = read_clean(raw("D16_gsi_tectonic", "TECTONIC_FRAMEWORK"))
    tf = tf[tf.geom_type.str.contains("Polygon")].reset_index(drop=True)
    label = tf["tectonic_f"].fillna("(blank)").astype(str)
    cats = sorted(label.unique())
    m = area_matrix(grid.to_crs(CRS_AREA).geometry, tf.to_crs(CRS_AREA).geometry,
                    label.map({c: i for i, c in enumerate(cats)}).values, len(cats))
    cover = m.sum(axis=1)
    out["tf_class"] = np.where(cover > 0, np.array(cats, dtype=object)[m.argmax(axis=1)], None)
    for col, rx in TF_GROUPS.items():
        sel = [i for i, c in enumerate(cats) if re.search(rx, c, re.I)]
        out[col] = np.nan_to_num(m[:, sel].sum(axis=1) / np.where(cover > 0, cover, np.nan)).round(4)
        print(f"    {col}: {', '.join(cats[i] for i in sel) or 'none matched'}")

    print("point evidence ...")
    um_csv = ROOT / "metadata" / "um_indicator_points.csv"
    if um_csv.exists():
        um = pd.read_csv(um_csv).drop_duplicates("site")   # one per ~1 km site
        ug = gpd.GeoDataFrame(um, geometry=gpd.points_from_xy(um["lon"], um["lat"]), crs=4326)
        j = gpd.sjoin(ug, grid[["h3", "geometry"]], predicate="within")
        cnt = j.groupby(["h3", "um_evidence"]).size().unstack(fill_value=0)
        for s in ("strong", "moderate"):
            out[f"n_um_{s}"] = out["h3"].map(cnt[s] if s in cnt else {}).fillna(0).astype(int)
        strong = ug[ug["um_evidence"] == "strong"].to_crs(CRS_DIST).geometry.values
        out["d_um_strong"] = nearest_km(cent, strong).round(2)
    else:
        print("    metadata/um_indicator_points.csv missing - run 05_lithology_classes.py first")
    sp = read_clean(raw("D19_gsi_geothermal", "GEOTHERMAL_SPRING_GEOTHERMAL"))
    sp["t"] = pd.to_numeric(sp.get("temparatur"), errors="coerce")
    sp = sp[sp.get("spring_typ", pd.Series("Thermal", index=sp.index)).astype(str).str.lower() != "cold"]
    spd = sp.to_crs(CRS_DIST)
    out["d_spring"] = nearest_km(cent, spd.geometry.values).round(2)
    tree = shapely.STRtree(spd.geometry.values)
    ic, isp = tree.query(cent, predicate="dwithin", distance=25000)
    tmax = pd.Series(spd["t"].values[isp]).groupby(ic).max()
    out["spring_tmax_25km"] = tmax.reindex(range(len(out))).values

    out = out[[c for c in out.columns if c != "geometry"] + ["geometry"]]
    write_layer(gpd.GeoDataFrame(out, crs=grid.crs), "structures")
    desc = out.drop(columns=["geometry", "h3", "tf_class"]).describe().T[["count", "mean", "50%", "max"]].round(2)
    (ROOT / "metadata" / "structures_grid_check.md").write_text(
        "# Structures on the grid - summary\n\n" + desc.to_markdown() + "\n\nMost common tectonic units:\n\n"
        + out["tf_class"].value_counts().head(15).to_markdown() + "\n", encoding="utf-8")
    print("    wrote metadata/structures_grid_check.md")


if __name__ == "__main__":
    main()
