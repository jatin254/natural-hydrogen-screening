"""
08_layer_lithology.py  -  Phase 3, step 2: rock types per grid cell

For every grid cell: the share of each rock class from the GSI 1:50k lithology,
using the rulebook configs/lithology_classes.yaml and three Phase 3 corrections
(decisions_log 2026-11-01):
  - "QUAT" (sand/silt/clay names) with a pre-Quaternary age becomes SH (older clays, mélange sediments)
  - evaporite in Quaternary deposits (surface salt / gypsum crusts) is not counted as evaporite
  - basalt of the Deccan Trap supergroup is kept apart as MAF_D (flood basalt), not scored like greenstone mafics
  - ultramafic intrusions recorded only in the `intrusive` column add to the ultramafic flag
Areas are exact (polygon x hexagon intersection), so small ultramafic bodies (~0.5 km2) are not lost.

Writes layers/india_h3r6.gpkg, table "lithology":
  lith_cover            share of the cell's land with mapped lithology (NODATA excluded)
  f_<CLASS>             share of mapped area where <CLASS> is the main rock (sums to 1)
  any_UM, any_UMA, any_BIF, any_MAF_I, any_EVAP, any_COAL
                        share of mapped area where that rock is present at all (main or minor)
  km2_UM_main, km2_UM_any   absolute ultramafic area in the cell
  main_class            the class with the largest share
and metadata/lithology_grid_check.md (totals vs the polygon totals, as a self-check).
Run:  python scripts/08_layer_lithology.py     (timings are printed for each stage; needs ~8-16 GB RAM)
"""
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h2pros.grid import CRS_AREA, area_matrix, load_grid, raw, read_clean, write_layer   # noqa: E402
from h2pros.lithology import classify   # noqa: E402

QUAT_AGE = re.compile(r"HOLOCENE|PLEISTOCENE|QUATERNARY|MEGHALAYAN|NORTHGRIPPIAN|GREENLANDIAN|RECENT", re.I)
FLAGS = ["UM", "UMA", "BIF", "MAF_I", "EVAP", "COAL"]


def classes_from_yaml():
    import yaml
    cfg = yaml.safe_load((ROOT / "configs" / "lithology_classes.yaml").read_text(encoding="utf-8"))
    codes = [c["code"] for c in cfg["classes"]]
    return codes + ["MAF_D", "UNK"]


T0 = time.time()


def stage(msg):
    print(f"[{(time.time() - T0) / 60:5.1f} min] {msg}", flush=True)


def main():
    import geopandas as gpd
    grid = load_grid()
    codes = classes_from_yaml()
    ci = {c: i for i, c in enumerate(codes)}

    stage("reading Lithology_50K (large) ...")
    lit = read_clean(raw("D15_gsi_geology2m", "Lithology_50K"),
                     columns=["lithologic", "age", "supergroup", "intrusive"], label="Lithology_50K")
    lit = lit[lit.geom_type.str.contains("Polygon")].copy()

    stage("classifying rock names ...")
    names = lit["lithologic"].fillna("").astype(str)
    cache = {n: classify(n) for n in names.unique()}
    main = names.map(lambda n: cache[n]["main"]).values.astype(object)
    present = names.map(lambda n: set(cache[n]["present"]))
    age = lit["age"].fillna("").astype(str)
    sg = lit["supergroup"].fillna("").astype(str).str.upper()
    old_quat = (main == "QUAT") & (age.str.strip() != "").values & ~age.str.contains(QUAT_AGE).values
    main[old_quat] = "SH"
    deccan = (main == "MAF_V") & sg.str.contains("DECCAN").values
    main[deccan] = "MAF_D"
    it = lit["intrusive"].fillna("").astype(str)
    it_um = {t: ("UM" in classify(t)["present"]) if t.strip() else False for t in it.unique()}
    intr = it.map(it_um).values.astype(bool)
    print(f"    QUAT -> SH (pre-Quaternary age): {old_quat.sum():,} polygons; Deccan basalt: {deccan.sum():,}; "
          f"ultramafic in `intrusive` only: {(intr & ~present.map(lambda p: 'UM' in p).values).sum():,}")
    # evaporite in Quaternary deposits = surface salt / gypsum crusts (Rann, playas, salt marsh), not a buried seal
    young = (age.str.strip() != "").values & age.str.contains(QUAT_AGE).values
    young_evap = young & (main == "EVAP")
    main[young_evap] = "QUAT"
    code_idx = np.array([ci.get(m, ci["UNK"]) for m in main])
    minor = np.column_stack([present.map(lambda p, f=f: f in p).values | (main == f) for f in FLAGS])
    minor[:, FLAGS.index("UM")] |= intr
    ev = FLAGS.index("EVAP")
    print(f"    evaporite in Quaternary deposits (not counted as seal): {int((minor[:, ev] & young).sum()):,} polygons")
    minor[young, ev] = False

    stage("overlaying on the grid (exact areas) ...")
    hx = grid.to_crs(CRS_AREA).geometry
    stage("projecting polygons to equal-area ...")
    pa = lit.to_crs(CRS_AREA).geometry
    stage("cutting large polygons into pieces, then overlaying ...")
    m, mm = area_matrix(hx, pa, code_idx, len(codes), minor=minor)

    out = grid[["h3", "geometry"]].copy()
    land = (grid["area_km2"] * grid["land_frac"]).values
    mapped = m.sum(axis=1) - m[:, ci["NODATA"]]
    out["lith_cover"] = np.clip(mapped / np.maximum(land, 1e-9), 0, 1).round(4)
    denom = np.where(mapped > 0, mapped, np.nan)
    for c in codes:
        if c == "NODATA":
            continue
        out[f"f_{c}"] = np.nan_to_num(m[:, ci[c]] / denom).round(5)
    for k, f in enumerate(FLAGS):
        out[f"any_{f}"] = np.nan_to_num(np.minimum(mm[:, k] / denom, 1)).round(5)
    out["km2_UM_main"] = m[:, ci["UM"]].round(3)
    out["km2_UM_any"] = mm[:, FLAGS.index("UM")].round(3)
    fcols = [c for c in out.columns if c.startswith("f_")]
    out["main_class"] = np.where(mapped > 0, out[fcols].idxmax(axis=1).str[2:], "NODATA")
    out = out[[c for c in out.columns if c != "geometry"] + ["geometry"]]
    stage("writing results ...")
    write_layer(gpd.GeoDataFrame(out, crs=grid.crs), "lithology")

    # self-check: grid totals vs polygon totals
    poly_km2 = pd.Series(lit.to_crs(CRS_AREA).area.values / 1e6).groupby(main).sum()
    grid_km2 = pd.Series(m.sum(axis=0), index=codes)
    chk = pd.DataFrame({"polygons_km2": poly_km2, "in_grid_km2": grid_km2}).fillna(0).round(0)
    chk["captured_%"] = (chk["in_grid_km2"] / chk["polygons_km2"].replace(0, np.nan) * 100).round(1)
    lines = ["# Lithology on the grid - self-check", "",
             "Area of each main class in the polygons vs inside grid cells. Close to 100% means nothing was lost; "
             "a little under 100% is rock just offshore or outside the India mask.", "",
             chk.sort_values("polygons_km2", ascending=False).to_markdown(), "",
             f"Cells: {len(out):,}. Cells with any ultramafic rock: {(out['km2_UM_any'] > 0).sum():,}; "
             f"with ultramafic as a main rock: {(out['km2_UM_main'] > 0).sum():,}.",
             f"Cells with no mapped lithology (lith_cover = 0): {(out['lith_cover'] == 0).sum():,}.", ""]
    top = out.sort_values("km2_UM_any", ascending=False).head(15).merge(grid[["h3", "lon", "lat", "state"]], on="h3")
    lines += ["Cells with the most ultramafic rock:", "",
              top[["h3", "state", "lon", "lat", "km2_UM_main", "km2_UM_any"]].to_markdown(index=False), ""]
    (ROOT / "metadata" / "lithology_grid_check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    stage("done - wrote metadata/lithology_grid_check.md")


if __name__ == "__main__":
    main()
