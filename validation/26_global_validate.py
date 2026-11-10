"""
26_global_validate.py  -  global test, step 3: the pre-registered test (decisions_log 2026-11-03)

Positive cells : res-5 cells with >= 1 EPRI record, Category Free Gas or Dissolved gas, not volcanic/magmatic.
Background     : (primary) res-5 cells with >= 1 onshore IHFC heat-flow site and no EPRI record of any category;
                 (secondary) all scored cells without an EPRI record.
Metric         : AUC of V2 acc_mean; 90% interval from 1,000 bootstraps of res-3 blocks; baselines in their better
                 direction; outside-Russia AUC (country of the cell centre from Natural Earth admin-0, public domain).
Pass           : AUC >= 0.65, low > 0.5, >= best baseline + 0.05, outside-Russia AUC >= 0.60 with low > 0.5
                 (>= 30 positive cells outside Russia, else that criterion is 'insufficient' -> at most Partial).
Writes metadata/global_validation.md and global_validation_roc.png.
Run after:  python scripts/12_score.py --region global --rules configs/scoring_rules_v2.yaml   (and v1.2 without --rules)
            python scripts/26_global_validate.py
"""
import importlib.util
import os
import re
import sys
import zipfile
from pathlib import Path

os.environ["H2_REGION"] = "global"
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h2pros.grid import GPKG, RAW, RES   # noqa: E402

N_BOOT, SEED = 1000, 20261103
PASS_AUC, PASS_MARGIN, OUT_AUC, MIN_OUT = 0.65, 0.05, 0.60, 30
VOLCANIC = r"volcan|fumarol|crater|magmatic gas"
NE_URL = "https://naciscdn.org/naturalearth/50m/cultural/ne_50m_admin_0_countries.zip"
spec = importlib.util.spec_from_file_location("audit03", ROOT / "scripts" / "03_audit_datasets.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def auc(score, label):
    ok = ~np.isnan(score)
    s, y = score[ok], label[ok]
    n1, n0 = y.sum(), (~y).sum()
    if n1 == 0 or n0 == 0:
        return np.nan
    r = pd.Series(s).rank().values
    return (r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def epri():
    import h3
    f = audit.find("D01_epri", "*occur*.csv") or audit.find("D01_epri", "*.csv")[:1]
    o = audit.read_text_table(f[0])
    for c in o.columns:
        o[c] = o[c].astype("string").str.replace(r"\s+", " ", regex=True).str.strip()
    cat = o[audit.find_col(o, "Category")].fillna("").str.lower()
    txt = o[[c for c in o.columns if re.search(r"categ|comment|descr|name", c, re.I)]].fillna("").astype(str).agg(" ".join, axis=1).str.lower()
    lat = pd.to_numeric(o[audit.find_col(o, "Latitude", contains=["lat"])], errors="coerce")
    lon = pd.to_numeric(o[audit.find_col(o, "Longitude", contains=["lon"])], errors="coerce")
    d = pd.DataFrame({"lat": lat, "lon": lon, "cat": cat, "volcanic": txt.str.contains(VOLCANIC, regex=True),
                      "country": o[audit.find_col(o, "Country")]}).dropna(subset=["lat", "lon"])
    d["h3"] = [h3.latlng_to_cell(a, b, RES) for a, b in zip(d.lat, d.lon)]
    d["primary"] = d.cat.str.contains("free gas|dissolved gas", regex=True) & ~d.volcanic
    d["inclusion"] = d.cat.str.contains("inclusion")
    return d


def countries(lon, lat):
    import geopandas as gpd
    import pyogrio
    folder = RAW / "D22_naturalearth"
    z = sorted(folder.glob("ne_50m_admin_0_countries*.zip")) if folder.exists() else []
    if not z:
        import requests
        folder.mkdir(parents=True, exist_ok=True)
        print("downloading Natural Earth admin-0 (public domain, ~5 MB) ...")
        r = requests.get(NE_URL, timeout=120, headers={"User-Agent": "h2-prospectivity-research/0.1"})
        r.raise_for_status()
        (folder / "ne_50m_admin_0_countries.zip").write_bytes(r.content)
        z = [folder / "ne_50m_admin_0_countries.zip"]
    shp = next(n for n in zipfile.ZipFile(z[0]).namelist() if n.endswith(".shp"))
    ne = pyogrio.read_dataframe(f"/vsizip/{z[0]}/{shp}", columns=["ADMIN"])
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(lon, lat), crs=4326)
    j = gpd.sjoin(pts, ne[["ADMIN", "geometry"]], predicate="within", how="left")
    return j[~j.index.duplicated()]["ADMIN"].reindex(range(len(pts))).fillna("(none)").values


def ihfc_cells():
    import h3
    fh = [p for p in sorted((RAW / "D06_ihfc").rglob("*.txt")) if "ghfdb" in p.name.lower() and not p.name.startswith("._")]
    data, _, _, pid_col = audit.read_ihfc(fh[0])
    num = lambda c: pd.to_numeric(data[c], errors="coerce")   # noqa: E731
    p = pd.DataFrame({"pid": data[pid_col], "lat": num("P4"), "lon": num("P5"), "env": data["P7"].astype(str).str.lower()})
    p = p.drop_duplicates("pid").dropna(subset=["lat", "lon"])
    p = p[p.env.str.contains("onshore")]
    return set(h3.latlng_to_cell(a, b, RES) for a, b in zip(p.lat, p.lon))


def table():
    import pyogrio
    v2 = pyogrio.read_dataframe(GPKG, layer="scores_v2", columns=["h3", "lon", "lat", "status", "acc_mean", "gen_mean"], read_geometry=False)
    v2 = v2.rename(columns={"acc_mean": "v2_acc", "gen_mean": "v2_gen"})
    layers = list(pyogrio.list_layers(GPKG)[:, 0])
    if "scores" in layers:
        v1 = pyogrio.read_dataframe(GPKG, layer="scores", columns=["h3", "acc_mean"], read_geometry=False).rename(columns={"acc_mean": "v12_acc"})
        v2 = v2.merge(v1, on="h3", how="left")
    st = pyogrio.read_dataframe(GPKG, layer="structures", columns=["h3", "d_um_rock"], read_geometry=False)
    dh = pyogrio.read_dataframe(GPKG, layer="depth_heat", columns=["h3", "bd_depth_m", "hf_median_50km"], read_geometry=False)
    return v2.merge(st, on="h3", how="left").merge(dh, on="h3", how="left")


def evaluate(d, title):
    import h3
    y = d["pos"].values.astype(bool)
    cand = {"V2 accumulation (primary)": d["v2_acc"].values, "V2 generation": d["v2_gen"].values}
    if "v12_acc" in d:
        cand["V1.2 accumulation"] = d["v12_acc"].values
    base = {"baseline: near ophiolite province": -d["d_um_rock"].values, "baseline: sediment thickness": d["bd_depth_m"].values,
            "baseline: heat flow": d["hf_median_50km"].values}
    flip = {}
    for k, v in list(base.items()):
        a = auc(v.astype(float), y)
        flip[k] = bool(a < 0.5)
        if flip[k]:
            base[k] = -v
    allsc = {**cand, **base}
    full = {k: auc(np.asarray(v, float), y) for k, v in allsc.items()}
    best = max(base, key=lambda k: -1 if np.isnan(full[k]) else full[k])
    blocks = np.array([h3.cell_to_parent(c, 3) for c in d["h3"]])
    ub = np.unique(blocks)
    idx = {b: np.where(blocks == b)[0] for b in ub}
    rng = np.random.default_rng(SEED)
    boot = {k: [] for k in allsc}
    diff = []
    for _ in range(N_BOOT):
        pick = np.concatenate([idx[b] for b in rng.choice(ub, len(ub), replace=True)])
        yy = y[pick]
        vals = {k: auc(np.asarray(v, float)[pick], yy) for k, v in allsc.items()}
        for k in allsc:
            boot[k].append(vals[k])
        diff.append(vals["V2 accumulation (primary)"] - vals[best])
    rows = [{"score": k, "AUC": round(full[k], 3), "90% low": round(np.nanpercentile(boot[k], 5), 3),
             "90% high": round(np.nanpercentile(boot[k], 95), 3), "note": "direction flipped (lower = more H2)" if flip.get(k) else ""}
            for k in allsc]
    return pd.DataFrame(rows), full, boot, best, diff, int(y.sum()), int((~y).sum()), len(ub)


def main():
    out = ROOT / "metadata"
    t = table()
    t = t[t["status"] == "scored"].copy()
    e = epri()
    pos_cells = set(e.loc[e.primary, "h3"])
    any_cells = set(e["h3"])
    hf = ihfc_cells()
    t["pos"] = t["h3"].isin(pos_cells)
    t["bg_target"] = t["h3"].isin(hf) & ~t["h3"].isin(any_cells)
    t["bg_all"] = ~t["h3"].isin(any_cells)
    t["country"] = countries(t["lon"].values, t["lat"].values)
    lost = len(pos_cells - set(t["h3"]))
    L = ["# Global test of the method (pre-registered 2026-11-03)", "",
         f"EPRI records {len(e)}; primary records {int(e.primary.sum())} (Free Gas / Dissolved gas, not volcanic) -> {len(pos_cells)} positive cells "
         f"(res {RES}); {lost} of them are not scored cells (no mapped geology) and drop out.",
         f"Background (primary): {int(t.bg_target.sum()):,} scored cells with an onshore heat-flow site and no EPRI record.", ""]
    prim = t[t.pos | t.bg_target]
    res, full, boot, best, diff, n1, n0, nb = evaluate(prim, "primary")
    a = full["V2 accumulation (primary)"]
    lo = np.nanpercentile(boot["V2 accumulation (primary)"], 5)
    margin = a - full[best]
    L += ["## Primary: positive cells vs heat-flow cells", "", f"{n1} positive and {n0:,} background cells in {nb} blocks.", "",
          res.to_markdown(index=False), "",
          f"Best baseline: **{best}** ({full[best]:.3f}). V2 minus best baseline: {margin:+.3f} "
          f"(90%: {np.nanpercentile(diff, 5):+.3f} to {np.nanpercentile(diff, 95):+.3f}).", ""]
    top = prim["v2_acc"] >= t["v2_acc"].quantile(0.9)
    L += [f"Top-10% capture (global top 10% of scored cells): {top[prim.pos].mean():.0%} of positive cells, "
          f"{top[prim.bg_target].mean():.0%} of background cells.", ""]
    # outside Russia
    o = prim[prim.country != "Russia"]
    n_out = int(o.pos.sum())
    if n_out >= MIN_OUT:
        r2, f2, b2, *_ = evaluate(o, "outside Russia")
        ao, loo = f2["V2 accumulation (primary)"], np.nanpercentile(b2["V2 accumulation (primary)"], 5)
        out_ok = ao >= OUT_AUC and loo > 0.5
        L += ["## Outside the Russian Federation", "", f"{n_out} positive cells.", "", r2.to_markdown(index=False), ""]
        out_txt = f"outside-Russia AUC {ao:.3f} (low {loo:.3f})"
    else:
        out_ok = None
        L += ["## Outside the Russian Federation", "", f"Only {n_out} positive cells (< {MIN_OUT}): insufficient.", ""]
        out_txt = f"outside Russia insufficient ({n_out} positive cells)"
    core = a >= PASS_AUC and lo > 0.5
    if core and margin >= PASS_MARGIN and out_ok:
        verdict = "PASS"
    elif core:
        verdict = "PARTIAL"
    else:
        verdict = "FAIL"
    L.insert(4, f"**Result: {verdict}** - V2 AUC {a:.3f} (90% low {lo:.3f}); margin over best baseline {margin:+.3f}; {out_txt}.\n")
    # secondary
    sec = t[t.pos | t.bg_all]
    r3, *_ = evaluate(sec, "all-land background")
    L += ["## Secondary: all scored land as background", "", r3.to_markdown(index=False), ""]
    inc = set(e.loc[e.inclusion, "h3"]) - pos_cells
    ti = t[t.h3.isin(inc) | t.bg_target].copy()
    ti["pos"] = ti.h3.isin(inc)
    if ti.pos.sum() >= 10:
        r4, *_ = evaluate(ti, "inclusions")
        L += ["## Secondary: fluid-inclusion records as positives", "", f"{int(ti.pos.sum())} cells.", "", r4.to_markdown(index=False), ""]
    by = prim.groupby("country").agg(pos=("pos", "sum"), cells=("h3", "size")).sort_values("pos", ascending=False).head(12)
    L += ["## Positive cells by country (concentration)", "", by.reset_index().to_markdown(index=False), ""]
    # ROC
    fig, ax = plt.subplots(figsize=(6, 6))
    y = prim["pos"].values
    for col, lab in (("v2_acc", "V2 accumulation"), ("v2_gen", "V2 generation"), ("bd_depth_m", "sediment thickness")):
        s = prim[col].values.astype(float)
        if col == "bd_depth_m" and auc(s, y) < 0.5:
            s = -s
        ok = ~np.isnan(s)
        order = np.argsort(-s[ok])
        yy = y[ok][order]
        ax.plot(np.r_[0, np.cumsum(~yy) / max((~yy).sum(), 1)], np.r_[0, np.cumsum(yy) / max(yy.sum(), 1)], label=f"{lab} ({auc(s, y):.2f})")
    ax.plot([0, 1], [0, 1], "k:", lw=0.8)
    ax.set_xlabel("share of background cells"); ax.set_ylabel("share of occurrence cells"); ax.legend(fontsize=8)
    ax.set_title("Global test: occurrence vs heat-flow cells")
    fig.savefig(out / "global_validation_roc.png", dpi=120, bbox_inches="tight")
    L.append("![roc](global_validation_roc.png)")
    (out / "global_validation.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:6]))
    print("wrote metadata/global_validation.md")


if __name__ == "__main__":
    main()
