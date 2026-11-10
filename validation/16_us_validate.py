"""
16_us_validate.py  -  US validation, step 4: the pre-registered test (decisions_log 2026-11-02)

Does the scoring logic (rules v1.2, unchanged) rank hydrogen-rich gas wells above hydrogen-poor ones?
  sample     USGS gas analyses with H2 reported, conterminous US; positive >= 0.5 mol%, negative < 0.5
  unit       H3 res-6 cell (positive if any sample is positive); each cell counts once
  metric     AUC (chance a positive cell outscores a negative one; 0.5 = coin flip)
  interval   90% from 1,000 bootstrap resamples of spatial blocks (H3 res 3)
  baselines  distance to ultramafic rock, sediment thickness, heat flow (each in its better direction,
             which favours the baselines), random = 0.5; benchmark (not a criterion): USGS PP 1900 maps
  PASS       AUC(acc_mean) >= 0.65 AND lower bound > 0.5 AND AUC - best baseline >= 0.05
Writes metadata/us_validation.md and us_validation_roc.png.
Run after `python scripts/12_score.py --region us`:  python scripts/16_us_validate.py
"""
import os
import sys
from pathlib import Path

os.environ["H2_REGION"] = "us"
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h2pros.grid import GPKG, RAW   # noqa: E402

BOX = (-125.0, 24.0, -66.0, 50.0)
N_BOOT, SEED = 1000, 20261102
PASS_AUC, PASS_MARGIN = 0.65, 0.05


def auc(score, label):
    """Mann-Whitney AUC with ties; NaN scores dropped."""
    ok = ~np.isnan(score)
    s, y = score[ok], label[ok]
    n1, n0 = y.sum(), (~y).sum()
    if n1 == 0 or n0 == 0:
        return np.nan
    r = pd.Series(s).rank().values
    return (r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def sample(pos_min=0.5, neg_max=0.5):
    f = sorted((RAW / "D14_usgs_gas").rglob("*.csv"))[0]
    d = pd.read_csv(f, low_memory=False)
    raw = d["H2"].astype(str).str.strip()
    blank = d["H2"].isna() | raw.isin(["", "nan", "None", "<NA>"])
    val = pd.to_numeric(raw.str.replace("<", "", regex=False), errors="coerce")
    trace = raw.str.contains(r"tr|<", case=False, na=False)
    lat, lon = pd.to_numeric(d["LAT"], errors="coerce"), pd.to_numeric(d["LONG"], errors="coerce")
    conus = lon.between(BOX[0], BOX[2]) & lat.between(BOX[1], BOX[3]) & ~d["STATE"].astype(str).str.upper().isin(["ALASKA", "HAWAII"])
    pos = ~blank & (val >= pos_min)
    neg = ~blank & ((val < neg_max) | (trace & val.isna()))
    s = pd.DataFrame({"lat": lat, "lon": lon, "pos": pos})[conus & (pos | neg)]
    import h3
    s["h3"] = [h3.latlng_to_cell(a, b, 6) for a, b in zip(s.lat, s.lon)]
    c = s.groupby("h3")["pos"].max().reset_index()
    c["block"] = [h3.cell_to_parent(h, 3) for h in c["h3"]]
    return c


def scores_table():
    import pyogrio
    sc = pyogrio.read_dataframe(GPKG, layer="scores", read_geometry=False)
    st = pyogrio.read_dataframe(GPKG, layer="structures", columns=["h3", "d_um_rock"], read_geometry=False)
    dh = pyogrio.read_dataframe(GPKG, layer="depth_heat", columns=["h3", "bd_depth_m", "hf_median_50km"], read_geometry=False)
    t = sc.merge(st, on="h3", how="left").merge(dh, on="h3", how="left")
    # benchmark: USGS PP 1900 grids sampled at cell centres (EPSG:5070)
    for col, name in (("pp1900_total", "cos.asc"), ("pp1900_source", "cos_sc.asc")):
        hit = sorted((RAW / "U04_usgs_h2_prospectivity").rglob(name)) if (RAW / "U04_usgs_h2_prospectivity").exists() else []
        if hit:
            import rasterio
            from pyproj import Transformer
            with rasterio.open(hit[0]) as r:
                x, y = Transformer.from_crs(4326, r.crs or 5070, always_xy=True).transform(t["lon"].values, t["lat"].values)
                v = np.array([a[0] for a in r.sample(zip(x, y))], dtype=float)
                v[v == r.nodata] = np.nan
            t[col] = v
    return t


def evaluate(cells, t, label="primary"):
    d = cells.merge(t, on="h3", how="inner")
    d = d[d["status"] == "scored"]
    y = d["pos"].values.astype(bool)
    cand = {"model: accumulation (acc_mean)": d["acc_mean"].values, "model: generation (gen_mean)": d["gen_mean"].values}
    base = {"baseline: near ultramafic rock": -d["d_um_rock"].values, "baseline: sediment thickness": d["bd_depth_m"].values,
            "baseline: heat flow": d["hf_median_50km"].values}
    bench = {k: d[c].values for k, c in (("benchmark: USGS PP 1900 total", "pp1900_total"), ("benchmark: USGS PP 1900 source", "pp1900_source")) if c in d}
    flip = {}
    for k, v in base.items():   # baselines get their better direction (favours them)
        a = auc(v.astype(float), y)
        flip[k] = bool(a < 0.5)
        if flip[k]:
            base[k] = -v
    allsc = {**cand, **base, **bench}
    full = {k: auc(np.asarray(v, float), y) for k, v in allsc.items()}
    best_base = max(base, key=lambda k: full[k])
    rng = np.random.default_rng(SEED)
    blocks = d["block"].values
    ub = np.unique(blocks)
    idx_by = {b: np.where(blocks == b)[0] for b in ub}
    boot = {k: [] for k in allsc}
    diff = []
    for _ in range(N_BOOT):
        pick = np.concatenate([idx_by[b] for b in rng.choice(ub, len(ub), replace=True)])
        yy = y[pick]
        vals = {k: auc(np.asarray(v, float)[pick], yy) for k, v in allsc.items()}
        for k in allsc:
            boot[k].append(vals[k])
        diff.append(vals["model: accumulation (acc_mean)"] - vals[best_base])
    rows = [{"score": k, "AUC": round(full[k], 3), "90% low": round(np.nanpercentile(boot[k], 5), 3),
             "90% high": round(np.nanpercentile(boot[k], 95), 3),
             "note": "direction flipped (lower = more H2)" if flip.get(k) else ""} for k in allsc]
    res = pd.DataFrame(rows)
    a = full["model: accumulation (acc_mean)"]
    lo = np.nanpercentile(boot["model: accumulation (acc_mean)"], 5)
    margin = a - full[best_base]
    passed = (a >= PASS_AUC) and (lo > 0.5) and (margin >= PASS_MARGIN)
    top = d["acc_mean"] >= d["acc_mean"].quantile(0.9)
    capture = (top & d["pos"]).sum() / max(1, d["pos"].sum())
    info = {"cells": len(d), "pos": int(y.sum()), "neg": int((~y).sum()), "blocks": len(ub), "auc": a, "lo": lo,
            "best_base": best_base, "margin": margin, "margin_lo": np.nanpercentile(diff, 5), "passed": passed, "capture": capture}
    return res, info, d


def main():
    t = scores_table()
    cells = sample()
    res, info, d = evaluate(cells, t)
    L = ["# US validation result (protocol 2026-11-02, rules v1.2 unchanged)", "",
         f"Cells: {info['cells']:,} ({info['pos']} positive, {info['neg']} negative) in {info['blocks']} spatial blocks.", "",
         f"## Verdict: **{'PASS' if info['passed'] else 'FAIL'}**", "",
         "| criterion | required | result |", "|:--|:--|:--|",
         f"| AUC of accumulation | >= {PASS_AUC} | {info['auc']:.3f} |",
         f"| lower 90% bound | > 0.5 | {info['lo']:.3f} |",
         f"| margin over best baseline ({info['best_base'].split(': ')[1]}) | >= {PASS_MARGIN} | {info['margin']:+.3f} (90% low {info['margin_lo']:+.3f}) |", "",
         f"Share of positive cells in the top 10% of well cells by accumulation: {info['capture']:.0%} (random: 10%).", "",
         "## All scores", "", res.to_markdown(index=False), ""]
    # sensitivity (reported, not used to pass)
    sens = []
    for lab, kw in (("positive >= 1 mol%", {"pos_min": 1.0}), ("negative <= 0.1 mol%", {"neg_max": 0.1001})):
        c2 = sample(**kw)
        r2, i2, _ = evaluate(c2, t, lab)
        sens.append({"variant": lab, "cells": i2["cells"], "positive": i2["pos"], "AUC accumulation": round(i2["auc"], 3),
                     "best baseline AUC": round(i2["auc"] - i2["margin"], 3), "verdict": "pass" if i2["passed"] else "fail"})
    west = d["lon"] < -100
    halves = [{"half": h, "cells": int(m.sum()), "positive": int(d["pos"][m].sum()),
               "AUC accumulation": round(auc(d["acc_mean"].values[m], d["pos"].values[m].astype(bool)), 3)} for h, m in (("west of 100 W", west), ("east of 100 W", ~west))]
    L += ["## Sensitivity (reported only)", "", pd.DataFrame(sens).to_markdown(index=False), "",
          "## West vs east", "", pd.DataFrame(halves).to_markdown(index=False), "",
          "![roc](us_validation_roc.png)", ""]
    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    y = d["pos"].values.astype(bool)
    for col, lab in (("acc_mean", "model: accumulation"), ("gen_mean", "model: generation")):
        s = d[col].values
        o = np.argsort(-s)
        tp = np.cumsum(y[o]) / y.sum()
        fp = np.cumsum(~y[o]) / (~y).sum()
        ax.plot(fp, tp, label=f"{lab} (AUC {auc(s, y):.2f})")
    ax.plot([0, 1], [0, 1], "k--", lw=0.8, label="random")
    ax.set_xlabel("share of H2-poor cells above threshold"); ax.set_ylabel("share of H2-rich cells above threshold")
    ax.legend(fontsize=8); fig.savefig(ROOT / "metadata" / "us_validation_roc.png", dpi=120, bbox_inches="tight")
    (ROOT / "metadata" / "us_validation.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"VERDICT: {'PASS' if info['passed'] else 'FAIL'}  (AUC {info['auc']:.3f}, margin {info['margin']:+.3f})")
    print("wrote metadata/us_validation.md")


if __name__ == "__main__":
    main()
