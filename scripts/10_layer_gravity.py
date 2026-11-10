"""
10_layer_gravity.py  -  Phase 3, step 4: gravity per cell, and the GSI vs WGM2012 test

Dense ultramafic / mafic bodies show as local gravity highs. We use the RESIDUAL Bouguer
anomaly: each cell's value minus the average within 50 km, which removes the broad
crustal trend and keeps features roughly 6-50 km across.

Sources
  GSI ground stations (D20): bad values dropped, stations far from their cell's median dropped,
                             cells need >= 3 stations; isolated cell jumps (> 30 mGal from neighbours) dropped
  WGM2012 Bouguer grid (D05): sampled at cell centres
Test (decisions_log 2026-11-01): correlation of the two residuals where both exist.
  r >= 0.7  -> WGM2012 used for all of India (one consistent layer), GSI kept as validation
  r <  0.7  -> GSI used where it exists; elsewhere gravity = no evidence (NaN)
Writes layers/india_h3r6.gpkg table "gravity" and metadata/gravity_test.md (+ two PNGs).
Run:  python scripts/10_layer_gravity.py     (5-15 minutes)
"""
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
from h2pros.grid import CRS_DIST, RAW, RES, load_grid, write_layer   # noqa: E402

R_REGIONAL = 50_000      # m, regional average radius
R_LOCAL = 15_000         # m, neighbour check for jumps
MIN_STATIONS = 3
R_THRESHOLD = 0.7
OUT = ROOT / "metadata"
T0 = time.time()


def stage(msg):
    print(f"[{(time.time() - T0) / 60:5.1f} min] {msg}", flush=True)


def pairs_within(pts, radius):
    import shapely
    tree = shapely.STRtree(pts)
    i, j = tree.query(pts, predicate="dwithin", distance=radius)
    return i.astype(np.int32), j.astype(np.int32)


def residual(v, pi, pj, n_all, min_share=0.5):
    """v minus the mean of valid values within the regional radius; NaN where under min_share of
    the neighbourhood has data (edges of coverage would bias the regional mean)."""
    ok = ~np.isnan(v)
    w = ok[pj]
    s = np.bincount(pi[w], weights=v[pj][w], minlength=len(v))
    c = np.bincount(pi[w], minlength=len(v))
    reg = np.where(c > 0, s / np.maximum(c, 1), np.nan)
    r = v - reg
    r[(c / np.maximum(n_all, 1)) < min_share] = np.nan
    return r


def gsi_cells(grid):
    import h3
    import pyogrio
    path = RAW / "D20_gsi_ground_geophysics" / "GRAVITY" / "All_India.geojson"
    cols = list(pyogrio.read_info(path)["fields"])
    pick = lambda s: next(c for c in cols if c.lower().startswith(s))   # noqa: E731
    c = {"lon": pick("longitude"), "lat": pick("latitude"), "obs": pick("observed"), "theo": pick("theoretic"), "ba": pick("bouguer")}
    d = pyogrio.read_dataframe(path, columns=list(c.values()), read_geometry=False).rename(columns={v: k for k, v in c.items()})
    d = d.apply(pd.to_numeric, errors="coerce").dropna()
    n0 = len(d)
    d = d[d["obs"].between(977000, 984000) & (d["theo"] > 0) & d["ba"].between(-400, 400)]
    d = d.drop_duplicates(["lon", "lat", "ba"])
    stage(f"GSI stations: {n0:,} read, {len(d):,} after bad values and duplicates; assigning to cells ...")
    d["h3"] = [h3.latlng_to_cell(y, x, RES) for x, y in zip(d["lon"].values, d["lat"].values)]
    d = d[d["h3"].isin(set(grid["h3"]))]
    med = d.groupby("h3")["ba"].transform("median")
    mad = (d["ba"] - med).abs().groupby(d["h3"]).transform("median") * 1.4826
    keep = (d["ba"] - med).abs() <= np.maximum(5.0, 4 * mad)
    stage(f"    dropped {(~keep).sum():,} stations far from their cell median")
    d = d[keep]
    g = d.groupby("h3")["ba"].agg(["median", "size"])
    g = g[g["size"] >= MIN_STATIONS]
    return g["median"], g["size"], {"read": n0, "used": int(keep.sum())}


def wgm_at(lon, lat):
    import xarray as xr
    files = sorted(p for p in (RAW / "D05_wgm2012").rglob("*") if p.suffix.lower() in (".grd", ".nc") and not p.name.startswith("._"))
    if not files:
        print("    WGM2012 grid (.grd/.nc) not found in data_raw/D05_wgm2012 - test skipped")
        return None
    ds = xr.open_dataset(files[0])
    var = "z" if "z" in ds else list(ds.data_vars)[0]
    da = ds[var]
    xd = next(d for d in da.dims if d.lower() in ("x", "lon", "longitude"))
    yd = next(d for d in da.dims if d.lower() in ("y", "lat", "latitude"))
    da = da.sortby(yd).sel({xd: slice(65, 100), yd: slice(4, 40)}).load()
    v = da.interp({xd: xr.DataArray(lon, dims="p"), yd: xr.DataArray(lat, dims="p")}, method="linear")
    stage(f"    WGM2012 sampled from {files[0].name}")
    return v.values.astype(float)


def main():
    import geopandas as gpd
    grid = load_grid()
    n = len(grid)
    pts = grid.to_crs(CRS_DIST).geometry.centroid.values
    stage("neighbour lists ...")
    pi, pj = pairs_within(pts, R_REGIONAL)
    n_all = np.bincount(pi, minlength=n)
    li, lj = pairs_within(pts, R_LOCAL)
    li, lj = li[li != lj], lj[li != lj]

    stage("GSI ground gravity ...")
    med, cnt, info = gsi_cells(grid)
    gsi = grid["h3"].map(med).values.astype(float)
    gsi_n = grid["h3"].map(cnt).fillna(0).astype(int).values
    # isolated jumps: cell vs median of its valid neighbours within 15 km
    ok = ~np.isnan(gsi)
    pr = pd.DataFrame({"i": li, "v": gsi[lj]}).dropna()
    nb_med = pr.groupby("i")["v"].median()
    nb_cnt = pr.groupby("i")["v"].size()
    nbm = nb_med.reindex(range(n)).values
    jump = ok & (nb_cnt.reindex(range(n)).fillna(0).values >= 3) & (np.abs(gsi - nbm) > 30)
    gsi[jump] = np.nan
    stage(f"    cells with GSI gravity: {int((~np.isnan(gsi)).sum()):,} of {n:,}; isolated jumps removed: {int(jump.sum())}")
    gsi_res = residual(gsi, pi, pj, n_all)

    stage("WGM2012 ...")
    wgm = wgm_at(grid["lon"].values, grid["lat"].values)
    wgm_res = residual(wgm, pi, pj, n_all) if wgm is not None else np.full(n, np.nan)

    both = ~np.isnan(gsi_res) & ~np.isnan(wgm_res)
    both_ba = ~np.isnan(gsi) & ~np.isnan(wgm if wgm is not None else np.full(n, np.nan))
    r_res = float(np.corrcoef(gsi_res[both], wgm_res[both])[0, 1]) if both.sum() > 100 else np.nan
    r_ba = float(np.corrcoef(gsi[both_ba], wgm[both_ba])[0, 1]) if both_ba.sum() > 100 else np.nan
    use_wgm = bool(r_res >= R_THRESHOLD)
    if use_wgm:
        g_res, src = wgm_res, np.where(np.isnan(wgm_res), "none", "WGM2012")
    else:
        g_res, src = gsi_res, np.where(np.isnan(gsi_res), "none", "GSI")

    out = grid[["h3", "geometry"]].copy()
    out["gsi_n"] = gsi_n
    out["gsi_ba"] = np.round(gsi, 1)
    out["gsi_res"] = np.round(gsi_res, 2)
    out["wgm_ba"] = np.round(wgm, 1) if wgm is not None else np.nan
    out["wgm_res"] = np.round(wgm_res, 2)
    out["g_res"] = np.round(g_res, 2)
    out["g_source"] = src
    out = out[[c for c in out.columns if c != "geometry"] + ["geometry"]]
    write_layer(gpd.GeoDataFrame(out, crs=grid.crs), "gravity")

    # report
    by_state = pd.DataFrame({"state": grid["state"], "both": both, "g": gsi_res, "w": wgm_res})
    rs = []
    for st, x in by_state[by_state["both"]].groupby("state"):
        if len(x) >= 50:
            rs.append({"state": st, "cells": len(x), "r_residual": round(float(np.corrcoef(x["g"], x["w"])[0, 1]), 2)})
    L = ["# Gravity: GSI ground stations vs WGM2012", "",
         f"GSI stations read {info['read']:,}, used {info['used']:,}. Cells with GSI gravity (>= {MIN_STATIONS} stations): "
         f"{int((~np.isnan(gsi)).sum()):,} of {n:,}; isolated jumps removed: {int(jump.sum())}.",
         f"Residual = cell minus mean within {R_REGIONAL // 1000} km (needs >= 50% of the neighbourhood with data).", "",
         "| comparison | cells | correlation r |", "|:--|--:|--:|",
         f"| Bouguer anomaly (full) | {int(both_ba.sum()):,} | {r_ba:.2f} |",
         f"| Residual anomaly (what we score) | {int(both.sum()):,} | {r_res:.2f} |", "",
         f"**Decision rule (r >= {R_THRESHOLD}): {'WGM2012 for all of India, GSI as validation' if use_wgm else 'GSI where it exists; no gravity evidence elsewhere'}.**",
         f"Cells with gravity evidence: {int((src != 'none').sum()):,} of {n:,}.", "",
         "Residual correlation by state (states with >= 50 shared cells):", "",
         pd.DataFrame(rs).sort_values("r_residual").to_markdown(index=False) if rs else "_none_", "",
         "![scatter](gravity_test_scatter.png)", "", "![maps](gravity_test_maps.png)", ""]
    if both.sum():
        fig, ax = plt.subplots(figsize=(5, 5))
        ax.scatter(gsi_res[both], wgm_res[both], s=1, alpha=0.2)
        lim = np.nanpercentile(np.abs(np.r_[gsi_res[both], wgm_res[both]]), 99)
        ax.plot([-lim, lim], [-lim, lim], "k--", lw=0.8)
        ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim)
        ax.set_xlabel("GSI residual (mGal)"); ax.set_ylabel("WGM2012 residual (mGal)"); ax.set_title(f"r = {r_res:.2f}")
        fig.savefig(OUT / "gravity_test_scatter.png", dpi=120, bbox_inches="tight"); plt.close(fig)
    fig, axs = plt.subplots(1, 2, figsize=(12, 6))
    for ax, v, t in zip(axs, [gsi_res, wgm_res], ["GSI residual", "WGM2012 residual"]):
        sc = ax.scatter(grid["lon"], grid["lat"], c=v, s=0.3, cmap="RdBu_r", vmin=-20, vmax=20)
        ax.set_title(t); ax.set_aspect("equal")
    fig.colorbar(sc, ax=axs, shrink=0.6, label="mGal")
    fig.savefig(OUT / "gravity_test_maps.png", dpi=120, bbox_inches="tight"); plt.close(fig)
    # side check for the lithology layer: where are the cells with no mapped rock?
    try:
        import pyogrio
        from h2pros.grid import GPKG
        lc = pyogrio.read_dataframe(GPKG, layer="lithology", columns=["h3", "lith_cover"], read_geometry=False)
        z = grid[["h3", "state"]].merge(lc, on="h3")
        z = z[z["lith_cover"] == 0].groupby("state").size().sort_values(ascending=False).rename("cells").reset_index()
        L += ["## Side check: cells with no mapped lithology, by state", "", z.head(12).to_markdown(index=False), ""]
    except Exception as err:
        L += [f"(lithology side check skipped: {err})", ""]
    (OUT / "gravity_test.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    stage("done - wrote metadata/gravity_test.md")


if __name__ == "__main__":
    main()
