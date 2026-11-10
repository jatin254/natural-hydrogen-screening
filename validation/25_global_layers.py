"""
25_global_layers.py  -  global test, step 2: global H3 res-5 grid and layers with the SAME columns as India

Mapping fixed in configs/global_mapping.yaml (decisions_log 2026-11-03) before any occurrence is joined.
No EPRI record is read here.

Steps (run all, or one with --step):
  raster      GLiM -> 2 km raster in its own Eckert IV projection (Litho code id), Hasterok provinces -> same raster;
              cached in layers/cache/ (slow once: 10-30 min); also the location check for GLiM 'fe' and 'gr' codes
  geology     all H3 res-5 cells; land test on 7 points per cell, then 49 sample points per land cell ->
              grid, lithology (class fractions + flags), provinces (tf_* and tf_class)
  structures  GEM active faults, Hasterok province boundaries -> great-circle distances; merges tf_* -> structures
  gravity     WGM2012 Bouguer at cell centres; 50 km residual
  depth       CRUST1.0 sediment thickness -> bd_depth_m; IHFC heat-flow median within 50 km (baseline)
Writes layers/global_h3r5.gpkg and metadata/global_layers_check.md.
Run:  python scripts/25_global_layers.py                (all steps; expect 1-3 hours the first time)
      python scripts/25_global_layers.py --step gravity
Then: python scripts/12_score.py --region global --rules configs/scoring_rules_v2.yaml   (and without --rules for v1.2)
"""
import argparse
import importlib.util
import os
import re
import sys
import time
from pathlib import Path

os.environ["H2_REGION"] = "global"
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h2pros.grid import (GPKG, LAYERS, RAW, RES, densify_lines, load_grid, sphere_nearest_km,   # noqa: E402
                         sphere_pairs, write_layer)

CFG = yaml.safe_load((ROOT / "configs" / "global_mapping.yaml").read_text(encoding="utf-8"))
CLASSES = [c["code"] for c in yaml.safe_load((ROOT / "configs" / "lithology_classes.yaml").read_text(encoding="utf-8"))["classes"]] + ["MAF_D"]
FLAGS = ["UM", "UMA", "BIF", "MAF_I", "EVAP", "COAL"]
CACHE = LAYERS / "cache"
CHECK = ROOT / "metadata" / "global_layers_check.md"
ECK = "ESRI:54012"
T0 = time.time()
COOL = 0          # seconds to pause after each tile / chunk (--cool), to keep a laptop from overheating


def stage(msg):
    print(f"[{time.time() - T0:7.0f}s] {msg}", flush=True)


def note(lines):
    with open(CHECK, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n\n")


def find_one(folder, pattern):
    hits = [p for p in sorted((RAW / folder).rglob(pattern)) if not p.name.startswith("._")]
    return hits[0] if hits else None


def glim_gdb():
    g = [p for p in (RAW / "D02_glim").rglob("*.gdb") if p.is_dir()]
    if not g:
        sys.exit("GLiM geodatabase not found in data_raw/D02_glim")
    return g[0]


def class_of(litho):
    """Full GLiM code -> (India class, greenstone, evaporite, iron formation)."""
    lv = {1: litho[0:2], 2: litho[2:4], 3: litho[4:6]}
    cls = CFG["glim_level1"].get(lv[1], "NODATA")
    for o in CFG["overrides"]:
        if lv[o["level"]] == o["code"] and cls == o["from"]:
            cls = o["to"]
    fl = CFG["flags"]
    gs = lv[fl["greenstone"]["level"]] == fl["greenstone"]["code"]
    ev = lv[fl["evaporite"]["level"]] == fl["evaporite"]["code"] or lv[1] == "ev"
    fe = lv[fl["iron_formation"]["level"]] == fl["iron_formation"]["code"]
    return cls, gs, ev, fe


# ------------------------------------------------------------------ raster
def step_raster():
    """GLiM -> 2 km raster, tile by tile: each tile reads only the polygons inside it (low memory), and finished tiles
    are kept in layers/cache/glim_tiles/, so an interrupted run resumes where it stopped."""
    import pyogrio
    import rasterio
    from rasterio import features
    from rasterio.transform import from_origin
    import shapely
    CACHE.mkdir(parents=True, exist_ok=True)
    res = float(CFG["grid"]["raster_m"])
    gdb = glim_gdb()
    layer = next((l for l, _ in pyogrio.list_layers(gdb) if "glim" in l.lower()), pyogrio.list_layers(gdb)[0][0])
    info = pyogrio.read_info(gdb, layer=layer)
    stage("raster: reading GLiM attributes (no geometry) ...")
    at = pyogrio.read_dataframe(gdb, layer=layer, columns=["Litho", "Shape_Area"], read_geometry=False)
    lit = at["Litho"].astype(str).str.strip().str.lower()
    codes = sorted(lit.unique())
    cid = {c: i + 1 for i, c in enumerate(codes)}               # 0 = no polygon (ocean)
    tab = pd.DataFrame([{"id": cid[c], "litho": c, **dict(zip(["cls", "greenstone", "evaporite", "iron_fm"], class_of(c)))} for c in codes])
    tab.to_csv(CACHE / "glim_codes.csv", index=False)
    chk_done = CHECK.exists() and "Location check" in CHECK.read_text(encoding="utf-8")
    if not chk_done:
        # location check for the uncertain codes (decides whether 'fe' is used - rule in configs/global_mapping.yaml)
        dist = CFG["iron_formation_districts"]
        rows = []
        for key, like in (("fe (iron formation?)", "____fe"), ("gr (greenstone)", "__gr%")):
            sub = pyogrio.read_dataframe(gdb, layer=layer, columns=["Litho", "Shape_Area"], where=f"Litho LIKE '{like}'")
            sub = sub.nlargest(12, "Shape_Area")
            if sub.crs is None:
                sub = sub.set_crs(ECK)
            cp = sub.geometry.representative_point().to_crs(4326)
            top = pd.DataFrame({"code": key, "litho": sub["Litho"].str.lower().values, "km2": sub["Shape_Area"].values / 1e6,
                                "lon": cp.x.values, "lat": cp.y.values})
            dk = np.column_stack([sphere_nearest_km(top.lon, top.lat, [v[0]], [v[1]]) for v in dist.values()])
            top["nearest_district"] = np.array(list(dist))[dk.argmin(axis=1)]
            top["km"] = dk.min(axis=1)
            rows.append(top)
        chk = pd.concat(rows).round(1)
        fe_hits = int((chk[chk.code.str.startswith("fe")]["km"] <= 300).sum())
        flag = ROOT / "metadata" / "global_fe_ok.txt"
        if fe_hits >= 3:
            flag.write_text(f"{fe_hits} of the 12 largest 'fe' polygons within 300 km of an iron-formation district\n")
        elif flag.exists():
            flag.unlink()
        note(["## Location check of uncertain GLiM codes (12 largest polygons each)",
              f"'fe' polygons within 300 km of a known iron-formation district: {fe_hits} of 12 -> iron-formation flag "
              f"{'USED' if fe_hits >= 3 else 'DROPPED'} (rule: >= 3).", "", chk.to_markdown(index=False)])
    xmin, ymin, xmax, ymax = info["total_bounds"]
    w, h = int(np.ceil((xmax - xmin) / res)), int(np.ceil((ymax - ymin) / res))
    tr = from_origin(xmin, ymax, res, res)
    TILE = 1024
    tdir = CACHE / "glim_tiles"
    tdir.mkdir(exist_ok=True)
    tiles = [(r0, c0) for r0 in range(0, h, TILE) for c0 in range(0, w, TILE)]
    todo = [t for t in tiles if not (tdir / f"t_{t[0]:05d}_{t[1]:05d}.npy").exists()]
    stage(f"raster: {len(at):,} polygons, {len(codes)} codes; {w} x {h} px at {res:.0f} m in {len(tiles)} tiles "
          f"({len(tiles) - len(todo)} already done)")
    t_start = time.time()
    for k, (r0, c0) in enumerate(todo, 1):
        th, tw = min(TILE, h - r0), min(TILE, w - c0)
        x0, y1 = tr * (c0, r0)
        x1, y0 = tr * (c0 + tw, r0 + th)
        sub = pyogrio.read_dataframe(gdb, layer=layer, columns=["Litho"], bbox=(x0, y0, x1, y1))
        arr = np.zeros((th, tw), dtype="uint16")
        if len(sub):
            geo = sub.geometry.values
            bad = ~shapely.is_valid(geo)
            if bad.any():
                geo[bad] = shapely.make_valid(geo[bad])
            ids = sub["Litho"].astype(str).str.strip().str.lower().map(cid).fillna(0).astype(int).values
            arr = features.rasterize(zip(geo, ids), out_shape=(th, tw), transform=from_origin(x0, y1, res, res), fill=0, dtype="uint16")
        np.save(tdir / f"t_{r0:05d}_{c0:05d}.npy", arr)
        el = time.time() - t_start
        print(f"      tile {k}/{len(todo)} ({len(sub):,} polygons); about {el / k * (len(todo) - k) / 60:.0f} min left", flush=True)
        if COOL:
            time.sleep(COOL)
    full = np.zeros((h, w), dtype="uint16")
    for r0, c0 in tiles:
        t = np.load(tdir / f"t_{r0:05d}_{c0:05d}.npy")
        full[r0:r0 + t.shape[0], c0:c0 + t.shape[1]] = t
    with rasterio.open(CACHE / "glim_2km.tif", "w", driver="GTiff", width=w, height=h, count=1, dtype="uint16",
                       crs=ECK, transform=tr, compress="deflate", tiled=True) as dst:
        dst.write(full, 1)
    del full
    stage("    Hasterok provinces -> same raster ...")
    pv = pyogrio.read_dataframe(find_one("D09_hasterok", "global_gprv.shp"), columns=["prov_name", "prov_type", "lastorogen", "continent"])
    pv["geometry"] = shapely.make_valid(pv.geometry.values)
    pv = pv.reset_index(drop=True)
    pv[["prov_name", "prov_type", "lastorogen", "continent"]].assign(id=np.arange(1, len(pv) + 1)).to_csv(CACHE / "provinces.csv", index=False)
    pv = pv.to_crs(ECK)
    parr = features.rasterize(zip(pv.geometry.values, np.arange(1, len(pv) + 1)), out_shape=(h, w), transform=tr, fill=0, dtype="uint16")
    with rasterio.open(CACHE / "provinces_2km.tif", "w", driver="GTiff", width=w, height=h, count=1, dtype="uint16",
                       crs=ECK, transform=tr, compress="deflate", tiled=True) as dst:
        dst.write(parr, 1)
    note([f"## Raster", f"GLiM {len(at):,} polygons, {len(codes)} codes, raster {w} x {h} at {res:.0f} m ({len(tiles)} tiles)."])
    stage("raster done")


# ------------------------------------------------------------------ geology (grid + lithology + provinces)
def sample(cells, child_res, tf, arrs, transform):
    """Raster values at the centres of each cell's children. Returns (owner index, values per raster)."""
    import h3
    from pyproj import Transformer
    lon, lat, own = [], [], []
    for k, c in enumerate(cells):
        ch = h3.cell_to_children(c, child_res)
        ll = [h3.cell_to_latlng(x) for x in ch]
        lat.extend(a for a, _ in ll); lon.extend(b for _, b in ll); own.extend([k] * len(ll))
    x, y = tf.transform(np.asarray(lon), np.asarray(lat))
    inv = ~transform
    col, row = inv * (x, y)
    col, row = np.floor(col).astype(np.int64), np.floor(row).astype(np.int64)
    out = []
    for a in arrs:
        ok = (row >= 0) & (row < a.shape[0]) & (col >= 0) & (col < a.shape[1]) & np.isfinite(x)
        v = np.zeros(len(row), dtype=a.dtype)
        v[ok] = a[row[ok], col[ok]]
        out.append(v)
    return np.asarray(own), out


def step_geology():
    import geopandas as gpd
    import h3
    import rasterio
    import shapely
    from pyproj import Transformer
    if not (CACHE / "glim_2km.tif").exists():
        step_raster()
    with rasterio.open(CACHE / "glim_2km.tif") as r:
        garr, gtr = r.read(1), r.transform
    with rasterio.open(CACHE / "provinces_2km.tif") as r:
        parr = r.read(1)
    tab = pd.read_csv(CACHE / "glim_codes.csv")
    pv = pd.read_csv(CACHE / "provinces.csv")
    use_fe = (ROOT / "metadata" / "global_fe_ok.txt").exists()     # created by hand after the location check
    ci = {c: i for i, c in enumerate(CLASSES)}
    n_id = int(tab["id"].max()) + 1
    cls_of = np.full(n_id, ci["NODATA"], dtype=np.int16)
    cls_of[tab["id"].values] = [ci[c] for c in tab["cls"]]
    gs_of = np.zeros(n_id, bool); gs_of[tab["id"].values] = tab["greenstone"].values
    ev_of = np.zeros(n_id, bool); ev_of[tab["id"].values] = tab["evaporite"].values
    fe_of = np.zeros(n_id, bool); fe_of[tab["id"].values] = tab["iron_fm"].values & use_fe
    hc = CFG["hasterok"]
    ptype = np.r_[[""], pv["prov_type"].fillna("").astype(str).values]
    is_oph = np.isin(ptype, hc["ophiolite"]); is_rift = np.isin(ptype, hc["rift"])
    is_acc = np.isin(ptype, hc["accretion"]); is_flood = np.isin(ptype, hc["flood_basalt"])
    tfcls = np.r_[[None], (pv["prov_type"].fillna("").astype(str) + " " + pv["lastorogen"].fillna("").astype(str)).str.strip().str.title().values]
    cont = np.r_[["unknown"], pv["continent"].fillna("unknown").astype(str).values]

    tf = Transformer.from_crs(4326, ECK, always_xy=True)
    stage("geology: land test on all res-5 cells (7 points each) ...")
    allc = [c for r0 in h3.get_res0_cells() for c in h3.cell_to_children(r0, RES)]
    lf = CACHE / "land_cells.npy"
    if lf.exists():
        land = np.load(lf, allow_pickle=True)
    else:
        land = []
        for s in range(0, len(allc), 200_000):
            chunk = allc[s:s + 200_000]
            own, (gv,) = sample(chunk, RES + 1, tf, [garr], gtr)
            hit = np.bincount(own[gv > 0], minlength=len(chunk)) > 0
            land.extend(np.asarray(chunk)[hit])
            print(f"      {min(s + 200_000, len(allc)):,} / {len(allc):,} cells", end="\r", flush=True)
            if COOL:
                time.sleep(COOL)
        print()
        land = np.asarray(sorted(land))
        np.save(lf, land, allow_pickle=True)
    stage(f"    {len(land):,} cells touch GLiM; sampling 49 points per cell ...")
    nC = len(CLASSES)
    rows = []
    cdir = CACHE / "geo_chunks"
    cdir.mkdir(exist_ok=True)
    for s in range(0, len(land), 50_000):
        cf = cdir / f"c_{s:07d}.pkl"
        if cf.exists():
            rows.append(pd.read_pickle(cf))
            continue
        chunk = land[s:s + 50_000]
        own, (gv, pvv) = sample(chunk, CFG["grid"]["sample_res"], tf, [garr, parr], gtr)
        k = len(chunk)
        cl = cls_of[gv]
        cl = np.where((cl == ci["MAF_V"]) & is_flood[pvv], ci["MAF_D"], cl)
        npts = np.bincount(own, minlength=k)
        on = np.bincount(own[gv > 0], minlength=k)
        cnt = np.bincount(own * nC + cl, minlength=k * nC).reshape(k, nC)
        mapped = cnt.sum(axis=1) - cnt[:, ci["NODATA"]]
        den = np.where(mapped > 0, mapped, np.nan)
        d = {"h3": chunk, "land_frac": on / npts, "lith_cover": np.nan_to_num(mapped / np.maximum(on, 1))}
        for c in CLASSES:
            if c != "NODATA":
                d[f"f_{c}"] = np.nan_to_num(cnt[:, ci[c]] / den)
        share = lambda m: np.nan_to_num(np.bincount(own[m], minlength=k) / den)   # noqa: E731
        d["any_UM"] = 0.0; d["any_UMA"] = 0.0
        d["any_BIF"] = share(fe_of[gv])
        d["any_MAF_I"] = d["f_MAF_I"]
        d["any_EVAP"] = share(ev_of[gv] | (cl == ci["EVAP"]))
        d["any_COAL"] = 0.0
        d["tf_greenstone"] = share(gs_of[gv])
        d["tf_ophiolite"] = np.bincount(own[is_oph[pvv]], minlength=k) / npts
        d["tf_rift"] = np.bincount(own[is_rift[pvv]], minlength=k) / npts
        d["tf_accretion"] = np.bincount(own[is_acc[pvv]], minlength=k) / npts
        pm = pd.DataFrame({"o": own, "p": pvv})
        pm = pm[pm.p > 0].groupby(["o", "p"]).size().reset_index(name="n").sort_values("n").drop_duplicates("o", keep="last")
        maj = np.zeros(k, dtype=np.int64); maj[pm["o"].values] = pm["p"].values
        d["tf_class"] = tfcls[maj]
        d["state"] = cont[maj]
        rows.append(pd.DataFrame(d))
        rows[-1].to_pickle(cf)
        print(f"      {min(s + 50_000, len(land)):,} / {len(land):,} land cells", end="\r", flush=True)
        if COOL:
            time.sleep(COOL)
    print()
    df = pd.concat(rows, ignore_index=True)
    df = df[df["land_frac"] > 0].reset_index(drop=True)
    fcols = [f"f_{c}" for c in CLASSES if c != "NODATA"]
    df["main_class"] = np.where(df["lith_cover"] > 0, df[fcols].idxmax(axis=1).str[2:], "NODATA")
    df["km2_UM_main"] = 0.0
    df["km2_UM_any"] = 0.0
    ll = np.array([h3.cell_to_latlng(c) for c in df["h3"]])
    df["lon"], df["lat"] = ll[:, 1].round(5), ll[:, 0].round(5)
    df["area_km2"] = [h3.cell_area(c, unit="km^2") for c in df["h3"]]

    def poly(c):
        b = np.array([(lo, la) for la, lo in h3.cell_to_boundary(c)])
        if b[:, 0].max() - b[:, 0].min() > 180:          # cell across the antimeridian: keep it on one side
            b[:, 0] = np.where(b[:, 0] < 0, b[:, 0] + 360, b[:, 0])
        return shapely.Polygon(b)
    geom = [poly(c) for c in df["h3"]]
    grid = gpd.GeoDataFrame(df[["h3", "lon", "lat", "area_km2", "land_frac", "state"]], geometry=geom, crs=4326)
    write_layer(grid, "grid")
    lith = gpd.GeoDataFrame(df[["h3", "lith_cover"] + fcols + [f"any_{f}" for f in FLAGS] + ["km2_UM_main", "km2_UM_any", "main_class"]],
                            geometry=geom, crs=4326)
    write_layer(lith, "lithology")
    prov = gpd.GeoDataFrame(df[["h3", "tf_class", "tf_ophiolite", "tf_greenstone", "tf_rift", "tf_accretion"]], geometry=geom, crs=4326)
    write_layer(prov, "provinces")
    area = (df[fcols].mul(df["area_km2"] * df["lith_cover"], axis=0)).sum().sort_values(ascending=False)
    note(["## Grid and lithology", f"{len(df):,} land cells (res {RES}); scored-geology cells {int((df.lith_cover > 0).sum()):,}; "
          f"iron-formation flag {'USED' if use_fe else 'NOT used (no metadata/global_fe_ok.txt)'}.",
          "Area by class (km2):", "", (area[area > 0] / 1).round(0).to_frame("km2").to_markdown(), "",
          f"Cells with greenstone share > 0: {int((df.tf_greenstone > 0).sum()):,}; ophiolite share > 0: {int((df.tf_ophiolite > 0).sum()):,}; "
          f"flood basalt (MAF_D) > 0: {int((df.f_MAF_D > 0).sum()):,}."])


# ------------------------------------------------------------------ structures
def step_structures():
    import geopandas as gpd
    import h3
    import pyogrio
    import shapely
    grid = load_grid()
    lith = pyogrio.read_dataframe(GPKG, layer="lithology", read_geometry=False)
    prov = pyogrio.read_dataframe(GPKG, layer="provinces", read_geometry=False)
    hard = lith.set_index("h3")[[f"f_{c}" for c in ("GNS", "GRAN", "MAF_I", "MAF_V", "UM", "MSED")]].sum(axis=1)
    lon, lat = grid["lon"].values, grid["lat"].values
    stage("structures: GEM faults ...")
    fpath = find_one("D03_gem_faults", "*.geojson") or find_one("D03_gem_faults", "*.gpkg") or find_one("D03_gem_faults", "*.shp")
    f = pyogrio.read_dataframe(fpath, columns=["slip_type"])
    f["geometry"] = shapely.force_2d(f.geometry.values)
    flo, fla, fo = densify_lines(f.geometry.values, 2.0)
    slip = f["slip_type"].fillna("").astype(str).values[fo]
    thrust = pd.Series(slip).str.contains("Reverse|Thrust", case=False).values
    fcell = np.array([h3.latlng_to_cell(a, b, RES) for a, b in zip(fla, flo)])
    fhard = hard.reindex(fcell).fillna(0).values >= 0.5
    so = grid[["h3", "geometry"]].copy()
    so["d_fault_any"] = sphere_nearest_km(lon, lat, flo, fla).round(2)
    so["d_neotectonic"] = so["d_fault_any"]
    so["d_thrust"] = sphere_nearest_km(lon, lat, flo[thrust], fla[thrust]).round(2)
    so["d_fault_basement"] = sphere_nearest_km(lon, lat, flo[fhard], fla[fhard]).round(2)
    so["d_shear"] = np.nan
    stage("structures: province boundaries between continental provinces ...")
    pv = pyogrio.read_dataframe(find_one("D09_hasterok", "global_gprv.shp"), columns=["prov_type", "crust_type"])
    pv["geometry"] = shapely.make_valid(pv.geometry.values)
    cont = pv[pv["crust_type"].fillna("") != "oceanic"].reset_index(drop=True)
    blo, bla, bo = densify_lines(cont.geometry.boundary.values, 2.0)
    tree = shapely.STRtree(cont.geometry.values)
    ip, ig = tree.query(shapely.points(blo, bla), predicate="dwithin", distance=0.01)
    shared = np.zeros(len(blo), bool)
    shared[ip[ig != bo[ip]]] = True
    so["d_suture"] = sphere_nearest_km(lon, lat, blo[shared], bla[shared]).round(2)
    oph = pv[pv["prov_type"].isin(CFG["hasterok"]["ophiolite"])]
    olo, ola, _ = densify_lines(oph.geometry.boundary.values, 2.0)
    d_oph = sphere_nearest_km(lon, lat, olo, ola)
    inside = prov.set_index("h3")["tf_ophiolite"].reindex(grid["h3"]).fillna(0).values > 0
    so["d_um_rock"] = np.where(inside, 0.0, d_oph).round(2)          # baseline only: distance to ophiolite provinces
    for c in ("n_um_strong", "n_um_moderate", "d_um_strong", "d_spring", "spring_tmax_25km"):
        so[c] = np.nan
    so = so.merge(prov, on="h3", how="left")
    so = so[[c for c in so.columns if c != "geometry"] + ["geometry"]]
    write_layer(gpd.GeoDataFrame(so, crs=grid.crs), "structures")
    note(["## Structures", f"GEM: {len(f):,} faults -> {len(flo):,} points (thrust/reverse {int(thrust.sum()):,}; in hard-rock cells {int(fhard.sum()):,}). "
          f"Province boundary points shared by two continental provinces: {int(shared.sum()):,}.",
          so.drop(columns=["geometry", "h3", "tf_class"]).describe().T[["count", "mean", "50%", "max"]].round(2).to_markdown()])


# ------------------------------------------------------------------ gravity
def step_gravity():
    import geopandas as gpd
    import xarray as xr
    grid = load_grid()
    stage("gravity: WGM2012 residual ...")
    f = next(p for p in sorted((RAW / "D05_wgm2012").rglob("*")) if p.suffix.lower() in (".grd", ".nc") and not p.name.startswith("._"))
    ds = xr.open_dataset(f)
    da = ds["z"] if "z" in ds else ds[list(ds.data_vars)[0]]
    xd = next(d for d in da.dims if d.lower() in ("x", "lon", "longitude"))
    yd = next(d for d in da.dims if d.lower() in ("y", "lat", "latitude"))
    da = da.sortby(yd)
    v = da.interp({xd: xr.DataArray(grid["lon"].values, dims="p"), yd: xr.DataArray(grid["lat"].values, dims="p")}).values.astype(float)
    i, j, _ = sphere_pairs(grid["lon"].values, grid["lat"].values, 50)
    ok = ~np.isnan(v)
    w = ok[j]
    s = np.bincount(i[w], weights=v[j][w], minlength=len(v))
    c = np.bincount(i[w], minlength=len(v))
    n_all = np.bincount(i, minlength=len(v))
    res = v - np.where(c > 0, s / np.maximum(c, 1), np.nan)
    res[(c / np.maximum(n_all, 1)) < 0.5] = np.nan
    out = grid[["h3", "geometry"]].copy()
    out["wgm_ba"] = np.round(v, 1)
    out["g_res"] = np.round(res, 2)
    out["g_source"] = np.where(np.isnan(res), "none", "WGM2012")
    out = out[[c for c in out.columns if c != "geometry"] + ["geometry"]]
    write_layer(gpd.GeoDataFrame(out, crs=grid.crs), "gravity")
    note(["## Gravity", f"WGM2012 residual for {int((~np.isnan(res)).sum()):,} cells; p10/p50/p90 "
          f"{np.nanpercentile(res, 10):.1f} / {np.nanpercentile(res, 50):.1f} / {np.nanpercentile(res, 90):.1f} mGal."])


# ------------------------------------------------------------------ depth + heat
def step_depth():
    import geopandas as gpd
    import zipfile
    from scipy.spatial import cKDTree
    from h2pros.grid import km_to_chord, unit_xyz
    grid = load_grid()
    stage("depth: CRUST1.0 sediment thickness; heat flow ...")
    z = find_one("D08a_crust1", "sedthk-m.xyz.zip") or find_one("D08a_crust1", "sedthk.xyz.zip")
    with zipfile.ZipFile(z) as zz:
        name = next(n for n in zz.namelist() if not n.startswith("__MACOSX") and not n.endswith("/"))
        with zz.open(name) as fh:
            c1 = pd.read_csv(fh, sep=r"\s+", header=None, names=["lon", "lat", "v"])
    km = c1["v"].median() < 50 and "-m" not in z.name
    c1["m"] = c1["v"] * (1000 if km else 1)
    key = lambda lo, la: (np.floor(lo) + 0.5).round(1).astype(str) + "," + (np.floor(la) + 0.5).round(1).astype(str)   # noqa: E731
    look = pd.Series(c1["m"].values, index=key(c1["lon"], c1["lat"]))
    look = look[~look.index.duplicated()]
    out = grid[["h3", "geometry"]].copy()
    lon = np.where(grid["lon"].values >= 180, grid["lon"].values - 360, grid["lon"].values)
    out["bd_depth_m"] = look.reindex(key(pd.Series(lon), grid["lat"]).values).values.round(0)
    out["bd_dist_km"] = 0.0
    out["bd_n_contours"] = np.nan
    spec = importlib.util.spec_from_file_location("audit03", ROOT / "scripts" / "03_audit_datasets.py")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    fh = [p for p in sorted((RAW / "D06_ihfc").rglob("*.txt")) if "ghfdb" in p.name.lower() and not p.name.startswith("._")]
    data, fields, id_col, pid_col = audit.read_ihfc(fh[0])
    num = lambda c: pd.to_numeric(data[c], errors="coerce")   # noqa: E731
    p = pd.DataFrame({"pid": data[pid_col], "q": num("P1"), "lat": num("P4"), "lon": num("P5"),
                      "env": data["P7"].astype(str).str.lower()}).drop_duplicates("pid").dropna(subset=["q", "lat", "lon"])
    p = p[p["env"].str.contains("onshore") & (p["q"] > 0) & (p["q"] <= 250)].reset_index(drop=True)
    t = cKDTree(unit_xyz(p["lon"], p["lat"]))
    nb = t.query_ball_point(unit_xyz(grid["lon"], grid["lat"]), float(km_to_chord(50)))
    q = p["q"].values
    out["hf_median_50km"] = np.round([np.median(q[x]) if len(x) else np.nan for x in nb], 1)
    out["hf_n_50km"] = [len(x) for x in nb]
    out = out[[c for c in out.columns if c != "geometry"] + ["geometry"]]
    write_layer(gpd.GeoDataFrame(out, crs=grid.crs), "depth_heat")
    note(["## Depth and heat flow", f"CRUST1.0 {z.name}; cells with thickness {int(out['bd_depth_m'].notna().sum()):,}; "
          f"median {np.nanmedian(out['bd_depth_m']):,.0f} m.", f"Onshore heat-flow sites {len(p):,}; cells with a site within 50 km "
          f"{int(out['hf_median_50km'].notna().sum()):,}."])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", choices=["raster", "geology", "structures", "gravity", "depth"])
    ap.add_argument("--cool", type=float, default=0, help="pause (seconds) after each tile or chunk, e.g. 20")
    a = ap.parse_args()
    global COOL
    COOL = a.cool
    steps = [a.step] if a.step else ["geology", "structures", "gravity", "depth"]
    for s in steps:
        globals()[f"step_{s}"]()
    stage(f"done - layers in {GPKG.relative_to(ROOT)}; check {CHECK.relative_to(ROOT)}")
    print("Next: python scripts/12_score.py --region global --rules configs/scoring_rules_v2.yaml ; python scripts/12_score.py --region global")


if __name__ == "__main__":
    main()
