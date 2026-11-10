"""
27_global_learn.py  -  V3: weights learned from global occurrences, tested by holding out whole regions
(protocol: decisions_log 2026-11-03, "V3 (learned weights) protocol").

Needs: layers/global_h3r5.gpkg with grid, lithology, structures, gravity, depth_heat, scores_v2 (scripts 25 and 12),
EPRI occurrences (D01), IHFC (D06), Natural Earth countries (D22, downloaded by script 26).
Needs scikit-learn:  pip install scikit-learn
Writes metadata/global_v3.md, global_v3_roc.png, and (only on Pass / Partial) metadata/global_v3_india.csv + map.
Run:  python scripts/27_global_learn.py
"""
import importlib.util
import os
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

spec = importlib.util.spec_from_file_location("v26", ROOT / "scripts" / "26_global_validate.py")
v26 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v26)
auc, epri, ihfc_cells = v26.auc, v26.epri, v26.ihfc_cells

N_BOOT, SEED = 1000, 20261103
FOLDS = ["Russia", "Europe", "Asia", "North America", "Rest"]
CLASSES = ["GNS", "GRAN", "MAF_I", "MAF_V", "MAF_D", "VOLC", "SST", "SH", "CARB", "EVAP", "MSED", "QUAT"]
DIST = ["d_fault_any", "d_thrust", "d_fault_basement", "d_suture", "d_um_rock"]
OTHER = ["any_BIF", "any_EVAP", "tf_ophiolite", "tf_greenstone", "tf_rift", "tf_accretion"]


def regions(lon, lat):
    import geopandas as gpd
    import pyogrio
    z = sorted((RAW / "D22_naturalearth").glob("ne_50m_admin_0_countries*.zip"))
    if not z:
        sys.exit("Natural Earth not found: run scripts/26_global_validate.py first (it downloads it)")
    shp = next(n for n in zipfile.ZipFile(z[0]).namelist() if n.endswith(".shp"))
    ne = pyogrio.read_dataframe(f"/vsizip/{z[0]}/{shp}")
    cols = {c.upper(): c for c in ne.columns}
    ne = ne[[cols["ADMIN"], cols.get("CONTINENT", cols["ADMIN"]), "geometry"]]
    ne.columns = ["admin", "continent", "geometry"]
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(lon, lat), crs=4326)
    j = gpd.sjoin(pts, ne, predicate="within", how="left")
    j = j[~j.index.duplicated()].reindex(range(len(pts)))
    admin = j["admin"].fillna("(none)").values
    cont = j["continent"].fillna("(none)").values
    reg = np.where(admin == "Russia", "Russia",
          np.where(np.isin(cont, ["Europe", "Asia", "North America"]), cont, "Rest"))
    return admin, reg


def load():
    import pyogrio
    t = pyogrio.read_dataframe(GPKG, layer="grid", columns=["h3", "lon", "lat"], read_geometry=False)
    for layer, cols in (("lithology", ["h3"] + [f"f_{c}" for c in CLASSES] + ["any_BIF", "any_EVAP"]),
                        ("structures", ["h3"] + DIST + ["tf_ophiolite", "tf_greenstone", "tf_rift", "tf_accretion"]),
                        ("gravity", ["h3", "g_res"]), ("depth_heat", ["h3", "bd_depth_m", "hf_median_50km"]),
                        ("scores_v2", ["h3", "status", "acc_mean", "gen_mean"])):
        t = t.merge(pyogrio.read_dataframe(GPKG, layer=layer, columns=cols, read_geometry=False), on="h3", how="left")
    return t[t["status"] == "scored"].reset_index(drop=True)


def features(t):
    X = pd.DataFrame(index=t.index)
    for c in CLASSES:
        X[f"f_{c}"] = t[f"f_{c}"].fillna(0)
    for c in OTHER:
        X[c] = t[c].fillna(0)
    for c in DIST:
        X[f"log_{c}"] = np.log1p(t[c].fillna(t[c].max()))
    g = t["g_res"]
    X["g_res"] = g.fillna(g.median())
    X["g_res_missing"] = g.isna().astype(float)
    X["log_sed_m"] = np.log1p(t["bd_depth_m"].fillna(t["bd_depth_m"].median()).clip(lower=0))
    return X


def models():
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return {"V3 logistic (primary)": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=1.0, class_weight="balanced", max_iter=5000)),
            "V3 boosted trees": lambda: HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200,
                                                                       l2_regularization=1.0, class_weight="balanced", random_state=SEED)}


def out_of_fold(X, y, reg, make):
    oof = np.full(len(y), np.nan)
    for f in FOLDS:
        te = reg == f
        tr = ~te
        if te.sum() == 0 or y[tr].sum() == 0:
            continue
        m = make().fit(X[tr], y[tr])
        p = m.predict_proba(X[te])[:, 1]
        oof[te] = pd.Series(p).rank(pct=True).values      # within-region rank: folds comparable when pooled
    return oof


def boot(d, scores, y, blocks, key, best):
    ub = np.unique(blocks)
    idx = {b: np.where(blocks == b)[0] for b in ub}
    rng = np.random.default_rng(SEED)
    out = {k: [] for k in scores}
    dv2, dbase = [], []
    for _ in range(N_BOOT):
        pick = np.concatenate([idx[b] for b in rng.choice(ub, len(ub), replace=True)])
        vals = {k: auc(v[pick], y[pick]) for k, v in scores.items()}
        for k in scores:
            out[k].append(vals[k])
        dv2.append(vals[key] - vals["V2 accumulation"])
        dbase.append(vals[key] - vals[best])
    return out, np.array(dv2), np.array(dbase)


def evaluate(t, X, label):
    import h3
    y = t["pos"].values.astype(bool)
    reg = t["region"].values
    oof = {name: out_of_fold(X.values, y, reg, mk) for name, mk in models().items()}
    # V2 and baselines ranked within region the same way, so all are compared on equal footing
    rk = lambda v: pd.Series(v).groupby(reg).rank(pct=True).values   # noqa: E731
    base = {"baseline: near ophiolite province": -t["d_um_rock"].values, "baseline: sediment thickness": t["bd_depth_m"].values,
            "baseline: heat flow": t["hf_median_50km"].values}
    for k, v in list(base.items()):
        if auc(v.astype(float), y) < 0.5:
            base[k] = -v
    scores = {**oof, "V2 accumulation": rk(t["acc_mean"].values), **{k: rk(v.astype(float)) for k, v in base.items()}}
    full = {k: auc(np.asarray(v, float), y) for k, v in scores.items()}
    best = max(base, key=lambda k: -1 if np.isnan(full[k]) else full[k])
    blocks = np.array([h3.cell_to_parent(c, 3) for c in t["h3"]])
    key = "V3 logistic (primary)"
    bt, dv2, dbase = boot(t, {k: np.asarray(v, float) for k, v in scores.items()}, y, blocks, key, best)
    rows = [{"score": k, "AUC": round(full[k], 3), "90% low": round(np.nanpercentile(bt[k], 5), 3),
             "90% high": round(np.nanpercentile(bt[k], 95), 3)} for k in scores]
    per = []
    for f in FOLDS:
        m = reg == f
        if m.sum() and y[m].sum():
            per.append({"held-out region": f, "positive cells": int(y[m].sum()), "background": int((~y[m]).sum()),
                        **{k.split(" (")[0]: round(auc(np.asarray(scores[k], float)[m], y[m]), 3) for k in (key, "V3 boosted trees", "V2 accumulation", best)}})
    return pd.DataFrame(rows), pd.DataFrame(per), full, bt, dv2, dbase, best, scores, oof


def main():
    out = ROOT / "metadata"
    t = load()
    e = epri()
    pos = set(e.loc[e.primary, "h3"])
    hf = ihfc_cells()
    t["pos"] = t["h3"].isin(pos)
    t["bg"] = t["h3"].isin(hf) & ~t["h3"].isin(set(e["h3"]))
    t = t[t.pos | t.bg].reset_index(drop=True)
    t["admin"], t["region"] = regions(t["lon"].values, t["lat"].values)
    X = features(t)
    key = "V3 logistic (primary)"
    res, per, full, bt, dv2, dbase, best, scores, oof = evaluate(t, X, "all")
    a, lo = full[key], np.nanpercentile(bt[key], 5)
    eligible = per[per["positive cells"] >= 10]
    n_ok = int((eligible["V3 logistic"] > 0.5).sum()) if len(eligible) else 0
    m_v2, m_b = a - full["V2 accumulation"], a - full[best]
    core = a >= 0.65 and lo > 0.5
    verdict = "PASS" if core and m_b >= 0.05 and m_v2 >= 0.05 and n_ok >= 3 else ("PARTIAL" if core else "FAIL")
    L = ["# V3: learned weights, tested on held-out regions (protocol 2026-11-03)", "",
         f"**Result: {verdict}** - pooled out-of-fold AUC {a:.3f} (90% low {lo:.3f}); vs V2 {m_v2:+.3f} "
         f"(90%: {np.percentile(dv2, 5):+.3f} to {np.percentile(dv2, 95):+.3f}); vs best baseline ({best}) {m_b:+.3f} "
         f"({np.percentile(dbase, 5):+.3f} to {np.percentile(dbase, 95):+.3f}); held-out regions with AUC > 0.5: {n_ok} of {len(eligible)} eligible.", "",
         f"Cells: {int(t.pos.sum())} positive, {int(t.bg.sum()):,} background. Scores are ranked within each region before pooling.", "",
         "## Pooled out-of-fold", "", res.to_markdown(index=False), "",
         "## Each region predicted by a model trained on the others", "", per.to_markdown(index=False), ""]
    # sensitivity: without Russia
    tn = t[t.region != "Russia"].reset_index(drop=True)
    r2, p2, f2, b2, *_ = evaluate(tn, features(tn), "no Russia")
    L += ["## Sensitivity: Russia removed entirely", "", r2.to_markdown(index=False), "", p2.to_markdown(index=False), ""]
    # weights learned on all cells (for reading only)
    from sklearn.inspection import permutation_importance
    mk = models()[key]().fit(X.values, t.pos.values)
    coef = pd.Series(mk[-1].coef_[0], index=X.columns).sort_values(key=np.abs, ascending=False)
    L += ["## Learned weights (logistic, all cells; standardised inputs - positive = more occurrences)", "",
          coef.round(3).rename("weight").to_frame().to_markdown(), ""]
    # exploratory: which settings the inputs recognise
    ee = e[e.primary].copy()
    occ = v26.audit.read_text_table((v26.audit.find("D01_epri", "*occur*.csv") or v26.audit.find("D01_epri", "*.csv")[:1])[0])
    sub_col = v26.audit.find_col(occ, "Subcategory")
    if sub_col:
        ee["sub"] = occ.loc[ee.index, sub_col].astype(str).str.strip().values
        pct = pd.Series(oof[key], index=t["h3"])
        pct = pct[~pct.index.duplicated()]
        ee["v3_pct"] = pct.reindex(ee["h3"]).values * 100
        v2p = pd.Series(scores["V2 accumulation"], index=t["h3"])
        v2p = v2p[~v2p.index.duplicated()]
        ee["v2_pct"] = v2p.reindex(ee["h3"]).values * 100
        tab = ee.groupby("sub").agg(records=("h3", "size"), cells=("h3", "nunique"),
                                    v3_median_pct=("v3_pct", "median"), v2_median_pct=("v2_pct", "median")).round(0)
        L += ["## Exploratory: median percentile (within region) of occurrence cells, by EPRI Subcategory", "",
              "50 = no better than a background cell. Not a test.", "", tab.sort_values("cells", ascending=False).reset_index().to_markdown(index=False), ""]
    # ROC
    fig, ax = plt.subplots(figsize=(6, 6))
    y = t["pos"].values
    for k in (key, "V3 boosted trees", "V2 accumulation", best):
        s = np.asarray(scores[k], float)
        ok = ~np.isnan(s)
        o = np.argsort(-s[ok])
        yy = y[ok][o]
        ax.plot(np.r_[0, np.cumsum(~yy) / max((~yy).sum(), 1)], np.r_[0, np.cumsum(yy) / max(yy.sum(), 1)], label=f"{k} ({full[k]:.2f})")
    ax.plot([0, 1], [0, 1], "k:", lw=0.8)
    ax.set_xlabel("share of background cells"); ax.set_ylabel("share of occurrence cells"); ax.legend(fontsize=7)
    ax.set_title("V3 out-of-fold (regions held out)")
    fig.savefig(out / "global_v3_roc.png", dpi=120, bbox_inches="tight")
    L.append("![roc](global_v3_roc.png)")
    if verdict in ("PASS", "PARTIAL"):
        import pyogrio
        allc = load()
        allc["admin"], _ = regions(allc["lon"].values, allc["lat"].values)
        ind = allc[allc.admin == "India"].reset_index(drop=True)
        p = mk.predict_proba(features(ind).values)[:, 1]
        ind["v3_pct_india"] = (pd.Series(p).rank(pct=True) * 100).round(1)
        ind[["h3", "lon", "lat", "v3_pct_india", "acc_mean"]].to_csv(out / "global_v3_india.csv", index=False)
        fig, ax = plt.subplots(figsize=(7, 8))
        sc = ax.scatter(ind.lon, ind.lat, c=ind.v3_pct_india, s=4, cmap="viridis")
        ax.set_aspect("equal"); fig.colorbar(sc, ax=ax, shrink=0.6)
        ax.set_title(f"V3 India (global layers), percentile - test result {verdict}")
        fig.savefig(out / "global_v3_india.png", dpi=120, bbox_inches="tight")
        L += ["", f"India map from global layers written (global_v3_india.csv / .png), {len(ind):,} cells - result {verdict}."]
    else:
        L += ["", "No V3 map is produced (protocol: only on Pass or Partial)."]
    (out / "global_v3.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:3]))
    print("wrote metadata/global_v3.md")


if __name__ == "__main__":
    main()
