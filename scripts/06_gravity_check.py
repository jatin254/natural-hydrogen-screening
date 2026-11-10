"""
06_gravity_check.py  -  Phase 2: are the GSI ground gravity stations usable?

Reads data_raw/D20_gsi_ground_geophysics/GRAVITY/All_India.geojson (attributes only)
and the India mask (D21), then checks:
  - bad values: theoretical gravity 0, observed gravity outside 977,000-984,000 mGal,
    Bouguer anomaly outside -400..+400 mGal
  - does bouguer_an agree with a simple Bouguer recomputation from observed, theoretical
    and elevation (density 2.67 g/cm3)? A large disagreement means mixed corrections.
  - coverage: share of India (0.1 deg cells, ~11 km) with at least one station
Writes metadata/audit/D20_gravity_check.md and D20_gravity_coverage.png. Nothing is changed.

Run:  python scripts/06_gravity_check.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyogrio

ROOT = Path(__file__).resolve().parents[1]
GRAV = ROOT / "data_raw" / "D20_gsi_ground_geophysics" / "GRAVITY" / "All_India.geojson"
MASK = ROOT / "data_raw" / "D21_gsi_boundary" / "STATE_BOUNDARY" / "All_India.geojson"
OUT = ROOT / "metadata" / "audit"
CELL = 0.1
BOX = (66.0, 6.0, 98.0, 38.0)


def find(cols, *starts):
    for s in starts:
        for c in cols:
            if c.lower().startswith(s):
                return c
    raise SystemExit(f"column starting with {starts} not found in {list(cols)}")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("reading stations (attributes only) ...")
    info = pyogrio.read_info(GRAV)
    cols = list(info["fields"])
    lon_c, lat_c = find(cols, "longitude"), find(cols, "latitude")
    obs_c, th_c = find(cols, "observed"), find(cols, "theoretic")
    el_c, ba_c = find(cols, "elevation"), find(cols, "bouguer")
    d = pyogrio.read_dataframe(GRAV, columns=[lon_c, lat_c, obs_c, th_c, el_c, ba_c], read_geometry=False)
    d = d.rename(columns={lon_c: "lon", lat_c: "lat", obs_c: "obs", th_c: "theo", el_c: "elev", ba_c: "ba"})
    for c in d.columns:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    n = len(d)
    L = ["# D20 - ground gravity: values and coverage", "", f"{n:,} stations read from `{GRAV.relative_to(ROOT)}`.", ""]

    # 1. bad values
    bad = {
        "missing value in any column": d.isna().any(axis=1),
        "theoretical gravity = 0": d["theo"] == 0,
        "observed gravity outside 977,000-984,000 mGal": ~d["obs"].between(977000, 984000),
        "Bouguer anomaly outside -400..+400 mGal": ~d["ba"].between(-400, 400),
        "elevation below -100 m or above 6,000 m": ~d["elev"].between(-100, 6000),
    }
    rows = [{"check": k, "stations": int(v.sum()), "share_%": round(v.mean() * 100, 3)} for k, v in bad.items()]
    anybad = np.logical_or.reduce(list(bad.values()))
    rows.append({"check": "ANY of the above (dropped in Phase 3)", "stations": int(anybad.sum()), "share_%": round(anybad.mean() * 100, 3)})
    L += ["## Bad values", "", pd.DataFrame(rows).to_markdown(index=False), ""]
    g = d[~anybad].copy()

    # 2. consistency: simple Bouguer = obs - theo + 0.3086 h - 0.1119 h  (2.67 g/cm3)
    g["ba_calc"] = g["obs"] - g["theo"] + (0.3086 - 0.04193 * 2.67) * g["elev"]
    g["diff"] = g["ba"] - g["ba_calc"]
    q = g["diff"].abs().quantile([0.5, 0.9, 0.99]).round(1)
    far = (g["diff"].abs() > 10).mean() * 100
    L += ["## Does `bouguer_an` match a simple recomputation?", "",
          f"Difference (stored - recomputed, mGal): median |diff| {q[0.5]}, 90th percentile {q[0.9]}, 99th {q[0.99]}; "
          f"{far:.1f}% of stations differ by more than 10 mGal.", "",
          "Small differences are expected (terrain correction, rounding to 1 mGal). If many stations differ by >10 mGal, "
          "surveys used different corrections and the anomaly will be recomputed in Phase 3 from observed and theoretical gravity.", ""]

    # 2b. GSI policy (2019, s.7.4): values are rounded to 1 mGal, or to 20 mGal in MoD-restricted zones
    r20 = (g["ba"] % 20 == 0)
    nx0, ny0 = int((BOX[2] - BOX[0]) / 0.5), int((BOX[3] - BOX[1]) / 0.5)
    cx = ((g["lon"] - BOX[0]) / 0.5).astype(int).clip(0, nx0 - 1)
    cy = ((BOX[3] - g["lat"]) / 0.5).astype(int).clip(0, ny0 - 1)
    grp = r20.groupby([cy, cx]).agg(["mean", "size"])
    coarse = grp[(grp["mean"] > 0.9) & (grp["size"] >= 10)]   # by chance only ~5% of values are multiples of 20
    in_coarse = g.set_index([cy, cx]).index.isin(coarse.index)
    g["restricted_20mgal"] = in_coarse
    L += ["## 20 mGal rounding (restricted zones)", "",
          "GSI's data policy rounds Bouguer values to 1 mGal, but to 20 mGal in zones restricted by the Ministry of Defence. "
          "A 0.5 deg cell with at least 10 stations, over 90% of them multiples of 20, is treated as restricted.", "",
          f"Restricted-looking cells: {len(coarse):,}; stations in them: {int(in_coarse.sum()):,} "
          f"({in_coarse.mean() * 100:.1f}%). These are too coarse for local anomalies and get low weight in Phase 3.", ""]

    # 3. coverage on 0.1 deg cells inside India
    nx, ny = int((BOX[2] - BOX[0]) / CELL), int((BOX[3] - BOX[1]) / CELL)
    ix = ((g["lon"] - BOX[0]) / CELL).astype(int).clip(0, nx - 1)
    iy = ((BOX[3] - g["lat"]) / CELL).astype(int).clip(0, ny - 1)
    cnt = np.zeros((ny, nx), dtype=np.int32)
    np.add.at(cnt, (iy.values, ix.values), 1)
    india = None
    if MASK.exists():
        import rasterio.features
        from rasterio.transform import from_origin
        m = pyogrio.read_dataframe(MASK)
        india = rasterio.features.rasterize(((geom, 1) for geom in m.geometry if geom is not None),
                                            out_shape=(ny, nx), transform=from_origin(BOX[0], BOX[3], CELL, CELL),
                                            all_touched=False, dtype="uint8").astype(bool)
        inside = cnt[india]
        cov = (inside > 0).mean() * 100
        out_india = int(cnt[~india].sum())
        L += ["## Coverage", "",
              f"India cells (0.1 deg, ~11 km): {india.sum():,}. With at least one station: **{cov:.1f}%**. "
              f"Median stations per covered cell: {int(np.median(inside[inside > 0])) if (inside > 0).any() else 0}.",
              f"Stations outside the India mask: {out_india:,}.", ""]
        if "state" not in m.columns and "stname" in m.columns:
            m["state"] = m["stname"]
        per = []
        for _, s in m.iterrows():
            one = rasterio.features.rasterize([(s.geometry, 1)], out_shape=(ny, nx),
                                              transform=from_origin(BOX[0], BOX[3], CELL, CELL), dtype="uint8").astype(bool)
            if one.sum():
                per.append({"state": s.get("state"), "cells": int(one.sum()), "covered_%": round((cnt[one] > 0).mean() * 100, 1)})
        L += ["### Coverage by state/UT", "", pd.DataFrame(per).sort_values("covered_%").to_markdown(index=False), ""]
    else:
        L += ["India mask (D21) not found: coverage not computed.", ""]

    # map
    fig, ax = plt.subplots(figsize=(8, 8))
    show = np.where(cnt > 0, 1.0, np.nan)
    if india is not None:
        ax.imshow(np.where(india, 0.0, np.nan), extent=(BOX[0], BOX[2], BOX[1], BOX[3]), cmap="Greys", vmin=-1, vmax=1)
    ax.imshow(show, extent=(BOX[0], BOX[2], BOX[1], BOX[3]), cmap="viridis", vmin=0, vmax=1.5)
    ax.set_title("Cells (0.1 deg) with at least one gravity station; grey = India without stations", fontsize=9)
    fig.savefig(OUT / "D20_gravity_coverage.png", dpi=130, bbox_inches="tight")
    L += ["![coverage](D20_gravity_coverage.png)", ""]

    out = OUT / "D20_gravity_check.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
