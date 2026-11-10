"""
28_serp_test.py  -  final desk test: serpentinisation hydrogen on NEW literature sites
(protocol: decisions_log 2026-11-03, "Final desk test").

Positives : metadata/serp_literature.csv rows with h2_basis = measured and coordinates, more than 25 km from ANY EPRI record,
            aggregated to res-5 scored cells.
Background: scored res-5 cells with an onshore IHFC site, no EPRI record and no literature site.
Scores    : V2 accumulation (primary), V2 generation, V1.2; baselines near ophiolite province, sediment thickness, heat flow.
Outcome A : V2 AUC >= 0.65, low > 0.5, V2 - ophiolite baseline >= +0.05 with 90% low > 0
Outcome B : V2 AUC >= 0.65, low > 0.5, not A
Outcome C : otherwise. Insufficient if < 15 positive cells or < 4 countries.
Writes metadata/serp_test.md and serp_test_roc.png.  Run:  python scripts/28_serp_test.py
"""
import importlib.util
import os
import sys
from pathlib import Path

os.environ["H2_REGION"] = "global"
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h2pros.grid import RES, sphere_nearest_km   # noqa: E402

spec = importlib.util.spec_from_file_location("v26", ROOT / "scripts" / "26_global_validate.py")
v26 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v26)
auc = v26.auc
N_BOOT, SEED, EXCL_KM, MIN_CELLS, MIN_COUNTRIES = 1000, 20261104, 25, 15, 4


def main():
    import h3
    out = ROOT / "metadata"
    lit = pd.read_csv(out / "serp_literature.csv")
    n0 = len(lit)
    lit["lat"], lit["lon"] = pd.to_numeric(lit["lat"], errors="coerce"), pd.to_numeric(lit["lon"], errors="coerce")
    lit = lit[(lit["h2_basis"].astype(str).str.strip().str.lower() == "measured") & lit.lat.notna() & lit.lon.notna()].copy()
    n1 = len(lit)
    e = v26.epri()
    lit["km_to_epri"] = sphere_nearest_km(lit.lon.values, lit.lat.values, e.lon.values, e.lat.values)
    new = lit[lit.km_to_epri > EXCL_KM].copy()
    new["h3"] = [h3.latlng_to_cell(a, b, RES) for a, b in zip(new.lat, new.lon)]
    t = v26.table()
    t = t[t["status"] == "scored"].copy()
    pos = set(new["h3"]) & set(t["h3"])
    hf = v26.ihfc_cells()
    t["pos"] = t["h3"].isin(pos)
    t["bg"] = t["h3"].isin(hf) & ~t["h3"].isin(set(e["h3"])) & ~t["h3"].isin(set(new["h3"]))
    d = t[t.pos | t.bg].reset_index(drop=True)
    countries = new[new.h3.isin(pos)]["country"].nunique()
    L = ["# Final desk test: serpentinisation hydrogen on new literature sites (protocol 2026-11-03)", "",
         f"Literature rows {n0}; measured with coordinates {n1}; more than {EXCL_KM} km from any EPRI record {len(new)} "
         f"-> {len(pos)} positive scored cells in {countries} countries ({len(set(new['h3']) - pos)} cells unscored).",
         f"Background: {int(d.bg.sum()):,} heat-flow cells.", ""]
    L += ["Sites used:", "", new[["site", "country", "ophiolite_or_massif", "sample_type", "h2_value", "h2_units", "coord_precision",
                                   "km_to_epri"]].round(1).to_markdown(index=False), ""]
    if len(pos) < MIN_CELLS or countries < MIN_COUNTRIES:
        L.insert(2, f"**Result: INSUFFICIENT SAMPLE** ({len(pos)} cells, {countries} countries; minimum {MIN_CELLS} and {MIN_COUNTRIES}). Descriptive only.\n")
    y = d["pos"].values.astype(bool)
    oph = -d["d_um_rock"].values
    sc = {"V2 accumulation (primary)": d["v2_acc"].values, "V2 generation": d["v2_gen"].values}
    if "v12_acc" in d:
        sc["V1.2 accumulation"] = d["v12_acc"].values
    base = {"baseline: near ophiolite province": oph, "baseline: sediment thickness": d["bd_depth_m"].values,
            "baseline: heat flow": d["hf_median_50km"].values}
    note = {}
    for k, v in list(base.items()):
        if k != "baseline: near ophiolite province" and auc(v.astype(float), y) < 0.5:
            base[k], note[k] = -v, "direction flipped (lower = more H2)"
    allsc = {**sc, **base}
    full = {k: auc(np.asarray(v, float), y) for k, v in allsc.items()}
    blocks = np.array([h3.cell_to_parent(c, 3) for c in d["h3"]])
    ub = np.unique(blocks)
    idx = {b: np.where(blocks == b)[0] for b in ub}
    rng = np.random.default_rng(SEED)
    bt = {k: [] for k in allsc}
    diff = []
    for _ in range(N_BOOT):
        pick = np.concatenate([idx[b] for b in rng.choice(ub, len(ub), replace=True)])
        vals = {k: auc(np.asarray(v, float)[pick], y[pick]) for k, v in allsc.items()}
        for k in allsc:
            bt[k].append(vals[k])
        diff.append(vals["V2 accumulation (primary)"] - vals["baseline: near ophiolite province"])
    res = pd.DataFrame([{"score": k, "AUC": round(full[k], 3), "90% low": round(np.nanpercentile(bt[k], 5), 3),
                         "90% high": round(np.nanpercentile(bt[k], 95), 3), "note": note.get(k, "")} for k in allsc])
    a, lo = full["V2 accumulation (primary)"], np.nanpercentile(bt["V2 accumulation (primary)"], 5)
    m, mlo, mhi = a - full["baseline: near ophiolite province"], np.nanpercentile(diff, 5), np.nanpercentile(diff, 95)
    if not L[2].startswith("**Result: INSUFFICIENT"):
        if a >= 0.65 and lo > 0.5 and m >= 0.05 and mlo > 0:
            v = "A - V2 adds value beyond 'near an ophiolite'"
        elif a >= 0.65 and lo > 0.5:
            v = "B - V2 only matches the simple rule"
        else:
            v = "C - the serpentinisation signal does not hold up on new sites"
        L.insert(2, f"**Result: Outcome {v}.** V2 AUC {a:.3f} (90% low {lo:.3f}); V2 minus ophiolite baseline {m:+.3f} (90%: {mlo:+.3f} to {mhi:+.3f}).\n")
    L += [f"{int(y.sum())} positive and {int((~y).sum()):,} background cells in {len(ub)} blocks.", "", res.to_markdown(index=False), "",
          "Percentile of each positive cell among background cells (V2 accumulation):", ""]
    bgv = np.sort(d.loc[~y, "v2_acc"].values)
    pp = d[y][["h3", "v2_acc", "v2_gen", "d_um_rock"]].copy()
    pp["v2_pct_vs_background"] = (np.searchsorted(bgv, pp.v2_acc.values) / len(bgv) * 100).round(0)
    pp = pp.merge(new.drop_duplicates("h3")[["h3", "site", "country"]], on="h3", how="left")
    L += [pp.sort_values("v2_pct_vs_background", ascending=False).round(3).to_markdown(index=False), ""]
    fig, ax = plt.subplots(figsize=(6, 6))
    for k in ("V2 accumulation (primary)", "V2 generation", "baseline: near ophiolite province"):
        s = np.asarray(allsc[k], float)
        ok = ~np.isnan(s)
        o = np.argsort(-s[ok])
        yy = y[ok][o]
        ax.plot(np.r_[0, np.cumsum(~yy) / max((~yy).sum(), 1)], np.r_[0, np.cumsum(yy) / max(yy.sum(), 1)], label=f"{k} ({full[k]:.2f})")
    ax.plot([0, 1], [0, 1], "k:", lw=0.8)
    ax.set_xlabel("share of background cells"); ax.set_ylabel("share of serpentinisation-site cells"); ax.legend(fontsize=7)
    ax.set_title("Final desk test: new serpentinisation sites")
    fig.savefig(out / "serp_test_roc.png", dpi=120, bbox_inches="tight")
    L.append("![roc](serp_test_roc.png)")
    (out / "serp_test.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:4]))
    print("wrote metadata/serp_test.md")


if __name__ == "__main__":
    main()
