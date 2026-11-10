"""
15_us_layers.py  -  US validation, step 3: US grid and layers with the SAME columns as India

Builds layers/us_h3r6.gpkg with the tables the scoring engine reads (grid, lithology, structures,
gravity, depth_heat), mapping US data to the India columns as fixed in configs/us_lithology_terms.yaml
and the decisions log (US validation protocol, 2026-11-02). Rules are not touched.

  grid        H3 res 6 over the conterminous US (cells whose centre falls on an SGMC polygon)
  geology     SGMC lithology -> f_<class>, any_<flag>, km2_UM_*, main_class; SGMC faults -> fault distances;
              Quaternary faults -> d_neotectonic; Hasterok provinces -> tf_*; distance to ultramafic rock (baseline)
  gravity     WGM2012 Bouguer residual (cell minus 50 km mean) -> g_res
  depth       CRUST1.0 sediment thickness -> bd_depth_m; IHFC heat flow within 50 km (baseline)
Not available for the US (left missing = "no evidence" in the rules): mineral-deposit evidence, sutures,
greenstone setting. Writes metadata/us_layers_check.md.

Run:  python scripts/15_us_layers.py              (all steps; 30-90 minutes)
      python scripts/15_us_layers.py --step gravity (one step again)
"""
import argparse
import importlib.util
import os
import re
import sys
import time
from pathlib import Path

os.environ["H2_REGION"] = "us"
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h2pros.grid import CRS_AREA, GPKG, RAW, RES, area_matrix, load_grid, write_layer   # noqa: E402
from h2pros.lithology import classify   # noqa: E402

CFG = yaml.safe_load((ROOT / "configs" / "us_lithology_terms.yaml").read_text(encoding="utf-8"))
BOX = (-125.0, 24.0, -66.0, 50.0)
QUAT_AGE = re.compile(r"HOLOCENE|PLEISTOCENE|QUATERNARY", re.I)
FLAGS = ["UM", "UMA", "BIF", "MAF_I", "EVAP", "COAL", "MEL"]
CHECK = ROOT / "metadata" / "us_layers_check.md"
T0 = time.time()


def stage(msg):
    print(f"[{(time.time() - T0) / 60:5.1f} min] {msg}", flush=True)


def note(lines):
    old = CHECK.read_text(encoding="utf-8") if CHECK.exists() else "# US layers - check\n\n"
    CHECK.write_text(old + "\n".join(lines) + "\n\n", encoding="utf-8")


def find_one(folder, pattern):
    hits = sorted(p for p in (RAW / folder).rglob(pattern) if not p.name.startswith("._"))
    return hits[0] if hits else None


def sgmc_gdb():
    g = next((p for p in (RAW / "U02_sgmc").rglob("*.gdb") if p.is_dir()), None)
    if g is None:
        raise SystemExit("SGMC geodatabase not found in data_raw/U02_sgmc (unzip it there)")
    return g


def nearest_km(points, geoms):
    import shapely
    if len(geoms) == 0:
        return np.full(len(points), np.nan)
    _, d = shapely.STRtree(geoms).query_nearest(points, return_distance=True, all_matches=False)
    return d / 1000.0


# ------------------------------------------------------------------ grid
def step_grid():
    import geopandas as gpd
    import h3
    import pyogrio
    import shapely
    stage("grid: candidate H3 cells over the conterminous US box ...")
    box = shapely.box(*BOX)
    cells = sorted(h3.h3shape_to_cells(h3.geo_to_h3shape(box), RES))
    ll = np.array([h3.cell_to_latlng(c) for c in cells])
    pts = gpd.GeoSeries(gpd.points_from_xy(ll[:, 1], ll[:, 0]), crs=4326).to_crs(CRS_AREA)
    stage(f"    {len(cells):,} candidates; keeping cells whose centre is on SGMC ...")
    geo = pyogrio.read_dataframe(sgmc_gdb(), layer="SGMC_Geology", columns=["STATE"])
    geo = geo.to_crs(CRS_AREA)
    tree = shapely.STRtree(geo.geometry.values)
    ip, ig = tree.query(pts.values, predicate="within")
    first = pd.Series(ig, index=ip).groupby(level=0).first()
    keep = np.zeros(len(cells), bool)
    keep[first.index.values] = True
    out = gpd.GeoDataFrame({"h3": np.array(cells)[keep], "lon": ll[keep, 1].round(5), "lat": ll[keep, 0].round(5)},
                           geometry=[shapely.Polygon([(b, a) for a, b in h3.cell_to_boundary(c)]) for c in np.array(cells)[keep]], crs=4326)
    out["area_km2"] = out.to_crs(CRS_AREA).area.values / 1e6
    out["land_frac"] = 1.0
    out["state"] = geo["STATE"].values[first.values]
    out = out[["h3", "lon", "lat", "area_km2", "land_frac", "state", "geometry"]]
    write_layer(out, "grid")
    note([f"## Grid", f"{len(out):,} H3 res-6 cells (centre on SGMC), {out['area_km2'].sum():,.0f} km2."])


# ------------------------------------------------------------------ geology (lithology + structures)
def term_classes(term, cache={}):
    t = "" if term is None or (isinstance(term, float) and np.isnan(term)) else str(term).strip()
    if not t:
        return []
    if t not in cache:
        ov = {k.lower(): v for k, v in CFG["term_overrides"].items()}
        cache[t] = [ov[t.lower()]] if t.lower() in ov else [c for c in classify(t)["present"]]
    return cache[t]


def step_geology():
    import geopandas as gpd
    import pyogrio
    import shapely
    grid = load_grid()
    lit_cols = ["MAJOR1", "MAJOR2", "MAJOR3", "MINOR1", "MINOR2", "MINOR3", "MINOR4", "MINOR5", "INCIDENTAL", "INDETERMINATE"]
    stage("geology: reading SGMC polygons (large) ...")
    g = pyogrio.read_dataframe(sgmc_gdb(), layer="SGMC_Geology",
                               columns=["STATE", "UNIT_LINK", "UNIT_NAME", "AGE_MIN", "AGE_MAX", "GENERALIZED_LITH"] + lit_cols)
    g = g[g.geometry.notna() & ~g.geometry.is_empty].to_crs(CRS_AREA).reset_index(drop=True)
    bad = ~shapely.is_valid(g.geometry.values)
    if bad.any():
        g.loc[bad, "geometry"] = shapely.make_valid(g.geometry.values[bad])
    stage(f"    {len(g):,} polygons ({int(bad.sum())} repaired); classifying ...")

    codes = [c["code"] for c in yaml.safe_load((ROOT / "configs" / "lithology_classes.yaml").read_text(encoding="utf-8"))["classes"]] + ["MAF_D", "UNK"]
    ci = {c: i for i, c in enumerate(codes)}
    gen_map = CFG["generalized_lith"]
    main, present, unmatched = [], [], {}
    for _, r in g[lit_cols + ["GENERALIZED_LITH"]].iterrows():
        m = term_classes(r["MAJOR1"])
        mc = m[0] if m else gen_map.get(str(r["GENERALIZED_LITH"]).strip(), "UNK")
        if not m and str(r["MAJOR1"]).strip() not in ("", "None", "nan"):
            unmatched[str(r["MAJOR1"]).strip()] = unmatched.get(str(r["MAJOR1"]).strip(), 0) + 1
        ps = {mc}
        for c in lit_cols:
            ps.update(term_classes(r[c]))
        main.append(mc)
        present.append(ps)
    main = np.array(main, dtype=object)
    age_min = g["AGE_MIN"].fillna("").astype(str)
    young = age_min.str.contains(QUAT_AGE).values
    pre_q = (age_min.str.strip() != "").values & ~young
    main[(main == "QUAT") & pre_q] = "SH"
    main[(main == "EVAP") & young] = "QUAT"
    flood = (main == "MAF_V") & g["UNIT_NAME"].fillna("").str.upper().str.contains(CFG["flood_basalt_unit_name"]).values
    main[flood] = "MAF_D"
    mel = (g["GENERALIZED_LITH"].fillna("") == CFG["melange_generalized"]).values
    minor = np.column_stack([np.array([f in p for p in present]) | (main == f) for f in FLAGS[:-1]] + [mel])
    minor[young, FLAGS.index("EVAP")] = False
    code_idx = np.array([ci.get(m, ci["UNK"]) for m in main])

    stage("    overlaying on the grid (exact areas) ...")
    hx = grid.to_crs(CRS_AREA).geometry
    m, mm = area_matrix(hx, g.geometry, code_idx, len(codes), minor=minor)
    out = grid[["h3", "geometry"]].copy()
    mapped = m.sum(axis=1) - m[:, ci["NODATA"]]
    out["lith_cover"] = np.clip(mapped / grid["area_km2"].values, 0, 1).round(4)
    den = np.where(mapped > 0, mapped, np.nan)
    for c in codes:
        if c != "NODATA":
            out[f"f_{c}"] = np.nan_to_num(m[:, ci[c]] / den).round(5)
    for k, f in enumerate(FLAGS):
        out[f"any_{f}"] = np.nan_to_num(np.minimum(mm[:, k] / den, 1)).round(5)
    out["km2_UM_main"] = m[:, ci["UM"]].round(3)
    out["km2_UM_any"] = mm[:, FLAGS.index("UM")].round(3)
    fcols = [c for c in out.columns if c.startswith("f_")]
    out["main_class"] = np.where(mapped > 0, out[fcols].idxmax(axis=1).str[2:], "NODATA")
    out = out[[c for c in out.columns if c != "geometry"] + ["geometry"]]
    write_layer(gpd.GeoDataFrame(out, crs=grid.crs), "lithology")
    area_cls = pd.Series(m.sum(axis=0), index=codes).round(0)
    un = pd.Series(unmatched).sort_values(ascending=False)
    note(["## Lithology", f"Polygons {len(g):,}; QUAT->SH {int(((np.array(main) == 'SH') & pre_q).sum()):,}; "
          f"flood basalt {int(flood.sum()):,}; melange {int(mel.sum()):,}.",
          "Area by main class in the grid (km2):", "", area_cls[area_cls > 0].sort_values(ascending=False).to_frame("km2").to_markdown(), "",
          f"Cells with ultramafic rock: {(out['km2_UM_any'] > 0).sum():,} (as main rock {(out['km2_UM_main'] > 0).sum():,}).",
          f"MAJOR1 terms with no class (fallback to GENERALIZED_LITH), by polygons: {len(un)} terms", "",
          un.head(40).to_frame("polygons").to_markdown() if len(un) else "_none_"])

    # ---- structures
    stage("structures: SGMC faults, Quaternary faults, provinces ...")
    cent = grid.to_crs(CRS_AREA).geometry.centroid.values
    s = pyogrio.read_dataframe(sgmc_gdb(), layer="SGMC_Structure", columns=["DESCRIPTION"]).to_crs(CRS_AREA)
    desc = s["DESCRIPTION"].fillna("").astype(str)
    st = CFG["structures"]
    is_fault = desc.str.contains(st["fault"], case=False).values
    is_thrust = is_fault & desc.str.contains(st["thrust"], case=False).values
    is_shear = desc.str.contains(st["shear"], case=False).values
    basement_poly = np.isin(main, ["GNS", "GRAN", "UM", "MAF_I"]) | g["AGE_MAX"].fillna("").str.upper().str.contains(st["precambrian_age"]).values
    btree = shapely.STRtree(g.geometry.values[basement_poly])
    fl = s.geometry.values[is_fault]
    il, _ = btree.query(fl, predicate="intersects")
    bflag = np.zeros(len(fl), bool)
    bflag[np.unique(il)] = True
    q_path = find_one("U03_qfaults", "Qfaults_US_Database.shp")
    if q_path is None:
        z = find_one("U03_qfaults", "Qfaults_GIS.zip")
        import zipfile
        name = next(n for n in zipfile.ZipFile(z).namelist() if n.endswith("Qfaults_US_Database.shp"))
        q_path = f"/vsizip/{z}/{name}"
    q = pyogrio.read_dataframe(q_path, columns=["class", "slip_sense"]).to_crs(CRS_AREA)
    q = q[q["class"].fillna("").astype(str).str.upper() != CFG["qfaults"]["exclude_class"]]
    q_thrust = q["slip_sense"].fillna("").str.contains(CFG["qfaults"]["thrust_slip_sense"], case=False).values
    so = grid[["h3", "geometry"]].copy()
    so["d_fault_basement"] = nearest_km(cent, fl[bflag]).round(2)
    so["d_fault_any"] = nearest_km(cent, np.concatenate([fl, q.geometry.values])).round(2)
    so["d_neotectonic"] = nearest_km(cent, q.geometry.values).round(2)
    so["d_thrust"] = nearest_km(cent, np.concatenate([s.geometry.values[is_thrust], q.geometry.values[q_thrust]])).round(2)
    so["d_shear"] = nearest_km(cent, s.geometry.values[is_shear]).round(2)
    so["d_suture"] = np.nan
    um_poly = np.array(["UM" in p for p in present]) | (main == "UM")
    so["d_um_rock"] = nearest_km(cent, g.geometry.values[um_poly]).round(2)      # baseline only
    # provinces (Hasterok)
    pv_path = find_one("D09_hasterok", "global_gprv.shp")
    pv = pyogrio.read_dataframe(pv_path, columns=["prov_type"])
    pv["geometry"] = shapely.make_valid(pv.geometry.values)
    pv = pv.clip(shapely.box(*BOX)).to_crs(CRS_AREA)
    pv = pv[pv.geom_type.str.contains("Polygon")].reset_index(drop=True)
    lab = pv["prov_type"].fillna("unknown").astype(str).str.title()
    cats = sorted(lab.unique())
    pm = area_matrix(grid.to_crs(CRS_AREA).geometry, pv.geometry, lab.map({c: i for i, c in enumerate(cats)}).values, len(cats))
    cov = pm.sum(axis=1)
    so["tf_class"] = np.where(cov > 0, np.array(cats, dtype=object)[pm.argmax(axis=1)], None)
    pvc = CFG["provinces"]
    share = lambda rx: np.nan_to_num(pm[:, [i for i, c in enumerate(cats) if re.search(rx, c, re.I)]].sum(axis=1) / np.where(cov > 0, cov, np.nan))   # noqa: E731
    so["tf_ophiolite"] = np.clip(share(pvc["ophiolite"]) + out["any_MEL"].values, 0, 1).round(4)
    so["tf_greenstone"] = 0.0
    so["tf_rift"] = share(pvc["rift"]).round(4)
    so["tf_accretion"] = share(pvc["accretion"]).round(4)
    for c in ("n_um_strong", "n_um_moderate", "d_um_strong", "d_spring", "spring_tmax_25km"):
        so[c] = np.nan
    so = so[[c for c in so.columns if c != "geometry"] + ["geometry"]]
    write_layer(gpd.GeoDataFrame(so, crs=grid.crs), "structures")
    note(["## Structures", f"SGMC fault lines {int(is_fault.sum()):,} (touching basement: {int(bflag.sum()):,}); thrusts {int(is_thrust.sum()):,}; "
          f"shear zones {int(is_shear.sum()):,}; Quaternary faults used {len(q):,}.",
          f"Provinces in the US box: {', '.join(cats)}.",
          so.drop(columns=["geometry", "h3", "tf_class"]).describe().T[["count", "mean", "50%", "max"]].round(2).to_markdown()])


# ------------------------------------------------------------------ gravity
def step_gravity():
    import geopandas as gpd
    import shapely
    import xarray as xr
    grid = load_grid()
    stage("gravity: WGM2012 residual ...")
    f = next(p for p in sorted((RAW / "D05_wgm2012").rglob("*")) if p.suffix.lower() in (".grd", ".nc") and not p.name.startswith("._"))
    ds = xr.open_dataset(f)
    da = ds["z"] if "z" in ds else ds[list(ds.data_vars)[0]]
    xd = next(d for d in da.dims if d.lower() in ("x", "lon", "longitude"))
    yd = next(d for d in da.dims if d.lower() in ("y", "lat", "latitude"))
    da = da.sortby(yd).sel({xd: slice(BOX[0] - 2, BOX[2] + 2), yd: slice(BOX[1] - 2, BOX[3] + 2)}).load()
    v = da.interp({xd: xr.DataArray(grid["lon"].values, dims="p"), yd: xr.DataArray(grid["lat"].values, dims="p")}).values.astype(float)
    pts = grid.to_crs(CRS_AREA).geometry.centroid.values
    i, j = shapely.STRtree(pts).query(pts, predicate="dwithin", distance=50_000)
    i, j = i.astype(np.int32), j.astype(np.int32)
    ok = ~np.isnan(v)
    w = ok[j]
    s = np.bincount(i[w], weights=v[j][w], minlength=len(v))
    c = np.bincount(i[w], minlength=len(v))
    n_all = np.bincount(i, minlength=len(v))
    res = v - np.where(c > 0, s / np.maximum(c, 1), np.nan)
    res[(c / np.maximum(n_all, 1)) < 0.5] = np.nan
    out = grid[["h3", "geometry"]].copy()
    out["wgm_ba"] = np.round(v, 1)
    out["wgm_res"] = np.round(res, 2)
    out["g_res"] = out["wgm_res"]
    out["g_source"] = np.where(np.isnan(res), "none", "WGM2012")
    out = out[[c for c in out.columns if c != "geometry"] + ["geometry"]]
    write_layer(gpd.GeoDataFrame(out, crs=grid.crs), "gravity")
    note(["## Gravity", f"WGM2012 residual for {int((~np.isnan(res)).sum()):,} cells; residual p10/p50/p90: "
          f"{np.nanpercentile(res, 10):.1f} / {np.nanpercentile(res, 50):.1f} / {np.nanpercentile(res, 90):.1f} mGal."])


# ------------------------------------------------------------------ depth + heat
def step_depth():
    import geopandas as gpd
    import shapely
    import zipfile
    grid = load_grid()
    stage("depth: CRUST1.0 sediment thickness; heat flow ...")
    z = find_one("D08a_crust1", "sedthk-m.xyz.zip") or find_one("D08a_crust1", "sedthk.xyz.zip")
    with zipfile.ZipFile(z) as zz:
        name = next(n for n in zz.namelist() if not n.startswith("__MACOSX") and not n.endswith("/"))
        with zz.open(name) as fh:
            c1 = pd.read_csv(fh, sep=r"\s+", header=None, names=["lon", "lat", "v"])
    km = c1["v"].median() < 50 and "-m" not in z.name      # sedthk.xyz is in km, sedthk-m.xyz in m
    c1["m"] = c1["v"] * (1000 if km else 1)
    key = lambda lo, la: (np.floor(lo) + 0.5).round(1).astype(str) + "," + (np.floor(la) + 0.5).round(1).astype(str)   # noqa: E731
    look = pd.Series(c1["m"].values, index=key(c1["lon"], c1["lat"]))
    look = look[~look.index.duplicated()]
    out = grid[["h3", "geometry"]].copy()
    out["bd_depth_m"] = look.reindex(key(grid["lon"], grid["lat"]).values).values.round(0)
    out["bd_dist_km"] = 0.0
    out["bd_n_contours"] = np.nan
    spec = importlib.util.spec_from_file_location("audit03", ROOT / "scripts" / "03_audit_datasets.py")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    f = [p for p in sorted((RAW / "D06_ihfc").rglob("*.txt")) if "ghfdb" in p.name.lower() and not p.name.startswith("._")]
    data, fields, id_col, pid_col = audit.read_ihfc(f[0])
    num = lambda c: pd.to_numeric(data[c], errors="coerce")   # noqa: E731
    p = pd.DataFrame({"pid": data[pid_col], "q": num("P1"), "lat": num("P4"), "lon": num("P5"),
                      "env": data["P7"].astype(str).str.lower()}).drop_duplicates("pid").dropna(subset=["q", "lat", "lon"])
    p = p[p["env"].str.contains("onshore") & (p["q"] > 0) & (p["q"] <= 250) & p["lon"].between(BOX[0], BOX[2]) & p["lat"].between(BOX[1], BOX[3])]
    hp = gpd.GeoSeries(gpd.points_from_xy(p["lon"], p["lat"]), crs=4326).to_crs(CRS_AREA).values
    cent = grid.to_crs(CRS_AREA).geometry.centroid.values
    ic, ih = shapely.STRtree(hp).query(cent, predicate="dwithin", distance=50_000)
    hq = pd.DataFrame({"c": ic, "q": p["q"].values[ih]}).groupby("c")["q"]
    out["hf_median_50km"] = hq.median().reindex(range(len(out))).round(1).values
    out["hf_n_50km"] = hq.size().reindex(range(len(out))).fillna(0).astype(int).values
    out = out[[c for c in out.columns if c != "geometry"] + ["geometry"]]
    write_layer(gpd.GeoDataFrame(out, crs=grid.crs), "depth_heat")
    note(["## Depth and heat flow", f"CRUST1.0 file {z.name} ({'km -> m' if km else 'm'}); cells with thickness "
          f"{int(out['bd_depth_m'].notna().sum()):,}; median {np.nanmedian(out['bd_depth_m']):,.0f} m.",
          f"Heat-flow sites (US, onshore) {len(p):,}; cells with a site within 50 km {int(out['hf_median_50km'].notna().sum()):,}."])


STEPS = {"grid": step_grid, "geology": step_geology, "gravity": step_gravity, "depth": step_depth}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", choices=["all"] + list(STEPS), default="all")
    a = ap.parse_args()
    if a.step == "all" and CHECK.exists():
        CHECK.unlink()
    for name, fn in STEPS.items():
        if a.step in ("all", name):
            fn()
    stage(f"done - layers in {GPKG.relative_to(ROOT)}; check metadata/us_layers_check.md")
    print("Next: python scripts/12_score.py --region us   then   python scripts/16_us_validate.py")


if __name__ == "__main__":
    main()
