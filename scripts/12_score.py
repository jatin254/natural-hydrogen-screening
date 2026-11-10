"""
12_score.py  -  Phase 4: play-fairway scores and ranking for India

Applies configs/scoring_rules.yaml to every grid cell, with Monte Carlo uncertainty.
Outputs (layers/india_h3r6.gpkg table "scores", one row per cell):
  gen_mean            generation fairway: chance a hydrogen source is present (mean over runs)
  charge_mean         generation incl. supply from sources up to 250 km away (linear decay)
  mig_mean, res_mean, seal_mean, pres_mean   component chances
  acc_mean, acc_p10, acc_p90                 accumulation fairway (all five components)
  p_top_gen, p_top_acc   share of runs in which the cell is in the top 10% of India (THE ranking)
  rank_acc            1 = best
  evidence_share      share of optional evidence available (gravity, basin depth, mapped geology)
  rule_<factor>       which rule fired (for explaining any cell)
Also: metadata/scores_summary.md (top cells, regional shortlist, rule usage) and maps PNG.
Run:  python scripts/12_score.py      (5-20 minutes for 1,000 runs)
"""
import os
import sys
import time
from pathlib import Path

if "--region" in sys.argv:          # must be set before h2pros.grid is imported
    os.environ["H2_REGION"] = sys.argv[sys.argv.index("--region") + 1]

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h2pros.grid import CRS_DIST, GPKG, REGION, RES, load_grid, sphere_pairs, write_layer   # noqa: E402

RULES = ROOT / (sys.argv[sys.argv.index("--rules") + 1] if "--rules" in sys.argv else "configs/scoring_rules.yaml")
VERSION = yaml.safe_load(RULES.read_text(encoding="utf-8")).get("settings", {}).get("version", "v1")
SHORT = {"generation": "gen", "migration": "mig", "reservoir": "res", "seal": "seal", "preservation": "pres"}
OUT = ROOT / "metadata"
PFX = ("" if REGION == "india" else f"{REGION}_") + ("" if VERSION == "v1" else f"{VERSION}_")   # us_..., v2_...
LAYER = "scores" if VERSION == "v1" else f"scores_{VERSION}"
T0 = time.time()


def stage(msg):
    print(f"[{(time.time() - T0) / 60:5.1f} min] {msg}", flush=True)


def load_inputs():
    import pyogrio
    grid = load_grid()
    df = grid.drop(columns="geometry").copy()
    for t in ("lithology", "structures", "gravity", "depth_heat"):
        try:
            x = pyogrio.read_dataframe(GPKG, layer=t, read_geometry=False)
        except Exception:
            raise SystemExit(f"table '{t}' missing in {GPKG.name}: run scripts 08-11 first")
        df = df.merge(x, on="h3", how="left", suffixes=("", f"_{t}"))
    return grid, df


def rule_index(df, rules):
    """Index of the first matching rule per cell; len(rules) = default."""
    idx = np.full(len(df), len(rules), dtype=np.int16)
    for k in range(len(rules) - 1, -1, -1):
        cond = df.eval(rules[k]["when"], engine="python")
        idx[np.asarray(cond.fillna(False), dtype=bool)] = k
    return idx


def tri_params(rules, default):
    p = np.array([r["cos"] for r in rules] + [default], dtype=float)
    lo, mo, hi = p[:, 0], p[:, 1], p[:, 2]
    hi = np.maximum(hi, lo + 1e-6)
    return lo, np.clip(mo, lo, hi), hi


def lateral_setup(grid, km, res):
    """Parent blocks (H3 `res`) and block pairs within `km`, with linear-decay weights."""
    import h3
    import shapely
    import geopandas as gpd
    parent = np.array([h3.cell_to_parent(h, res) for h in grid["h3"]])
    up, pidx = np.unique(parent, return_inverse=True)
    ll = np.array([h3.cell_to_latlng(p) for p in up])
    if CRS_DIST is None:                        # global grid: great-circle distances
        i, j, d = sphere_pairs(ll[:, 1], ll[:, 0], km)
    else:
        pts = gpd.GeoSeries(gpd.points_from_xy(ll[:, 1], ll[:, 0]), crs=4326).to_crs(CRS_DIST).values
        tree = shapely.STRtree(pts)
        i, j = tree.query(pts, predicate="dwithin", distance=km * 1000)
        d = shapely.distance(pts[i], pts[j]) / 1000.0
    d = np.where(i == j, 0.7 * h3.average_hexagon_edge_length(res, unit="km"), d)   # typical distance inside a block
    w = np.clip(1 - d / km, 0, 1).astype(np.float32)
    return pidx, len(up), i, j, w


def main():
    import geopandas as gpd
    cfg = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    st = cfg["settings"]
    grid, df = load_inputs()
    for name, expr in cfg.get("derived", {}).items():
        # arithmetic on columns, plus minimum / maximum that ignore missing values
        ns = {c: df[c] for c in df.columns}
        ns.update({"minimum": np.fmin, "maximum": np.fmax})
        df[name] = eval(expr, {"__builtins__": {}}, ns)
    excluded = np.asarray(df.eval(st["exclude_if"], engine="python").fillna(True), dtype=bool)
    keep = ~excluded
    n = int(keep.sum())
    stage(f"{len(df):,} cells; scored {n:,}; excluded (no mapped geology) {int(excluded.sum()):,}")

    # rule assignment
    plan, usage = {}, []
    for comp, c in cfg["components"].items():
        for fac, f in c["factors"].items():
            idx = rule_index(df, f["rules"])
            plan[(comp, fac)] = (idx[keep], *tri_params(f["rules"], f["default"]))
            df[f"rule_{fac}"] = np.where(idx < len(f["rules"]), idx + 1, 0)   # 0 = default
            counts = np.bincount(idx[keep], minlength=len(f["rules"]) + 1)
            for k, r in enumerate(f["rules"] + [{"when": "(default)", "cos": f["default"], "why": ""}]):
                usage.append({"component": comp, "factor": fac, "rule": k + 1 if k < len(f["rules"]) else "default",
                              "when": r["when"].replace("|", "\\|"), "cos (low/mode/high)": "/".join(f"{v:.2f}" for v in r["cos"]),
                              "cells": int(counts[k])})

    # lateral blocks are one H3 level above the grid (India: res-6 cells, res-5 blocks). On the res-5 global grid that
    # is res 4, so a block again holds ~7 cells and the pair list stays small (decisions_log 2026-11-03).
    block_res = min(int(st.get("lateral_block_res", 5)), RES - 1)
    pidx_all, n_par, pi, pj, w = lateral_setup(grid, st["lateral_migration_km"], block_res)
    pidx = pidx_all[keep]
    rng = np.random.default_rng(st["seed"])
    runs, B = int(st["runs"]), (20 if n > 300_000 else 50)
    cool = float(sys.argv[sys.argv.index("--cool") + 1]) if "--cool" in sys.argv else 0.0
    tops = st.get("top_shares", [st.get("top_share", 0.10)])
    top = tops[0]
    others = [c for c in cfg["components"] if c != "generation"]
    keys = ["gen", "charge"] + [SHORT.get(c, c) for c in others] + ["acc"]
    sums = {k: np.zeros(n) for k in keys}
    top_gen, top_acc = np.zeros((len(tops), n)), np.zeros((len(tops), n))
    keep_every = max(1, int(np.ceil(runs * n / 1e8)))   # memory cap for the p10/p90 store (global grid)
    acc_all = np.empty((int(np.ceil(runs / keep_every)), n), dtype=np.float32)
    stage(f"Monte Carlo: {runs} runs ...")
    for b0 in range(0, runs, B):
        nb = min(B, runs - b0)
        comp_val = {}
        for comp, c in cfg["components"].items():
            how = c.get("combine", "noisy_or")
            acc_c = np.ones((nb, n), dtype=np.float32)
            for fac in c["factors"]:
                idx, lo, mo, hi = plan[(comp, fac)]
                draws = rng.triangular(lo, mo, hi, size=(nb, len(lo))).astype(np.float32)
                acc_c *= (1 - draws[:, idx]) if how == "noisy_or" else draws[:, idx]
            comp_val[comp] = 1 - acc_c if how == "noisy_or" else acc_c   # noisy-OR or product
        g = comp_val["generation"]
        # lateral charge: best (parent max x decay) among parents within range
        gp = np.zeros((n_par, nb), dtype=np.float32)
        np.maximum.at(gp, pidx, g.T)
        lat = np.zeros((n_par, nb), dtype=np.float32)
        np.maximum.at(lat, pi, gp[pj] * w[:, None])
        charge = np.maximum(g, lat[pidx].T)
        acc = charge.copy()
        for c in others:
            acc = acc * comp_val[c]
        sel = [k for k in range(nb) if (b0 + k) % keep_every == 0]
        acc_all[[(b0 + k) // keep_every for k in sel]] = acc[sel]
        for k, v in [("gen", g), ("charge", charge)] + [(SHORT.get(c, c), comp_val[c]) for c in others] + [("acc", acc)]:
            sums[k] += v.sum(axis=0)
        for t, q in enumerate(tops):
            top_gen[t] += (g >= np.quantile(g, 1 - q, axis=1, keepdims=True)).sum(axis=0)
            top_acc[t] += (acc >= np.quantile(acc, 1 - q, axis=1, keepdims=True)).sum(axis=0)
        print(f"      {b0 + nb} / {runs} runs", end="\r", flush=True)
        if cool:
            time.sleep(cool)
    print()

    stage("summarising ...")
    out = grid[["h3", "lon", "lat", "state", "geometry"]].copy()
    def put(col, vals, nd=4):
        full = np.full(len(out), np.nan)
        full[keep] = vals
        out[col] = np.round(full, nd)
    for k in sums:
        put(f"{k}_mean", sums[k] / runs)
    put("acc_p10", np.quantile(acc_all, 0.10, axis=0))
    put("acc_p90", np.quantile(acc_all, 0.90, axis=0))
    put("p_top_gen", top_gen[0] / runs, 3)
    put("p_top_acc", top_acc[0] / runs, 3)
    if len(tops) > 1:
        put("p_top1_gen", top_gen[1] / runs, 3)
        put("p_top1_acc", top_acc[1] / runs, 3)
    key = out.get("p_top1_acc", 0).fillna(-1) * 100 if len(tops) > 1 else 0
    r = key + out["p_top_acc"].fillna(-1) * 10 + out["acc_mean"].fillna(-1)
    out["rank_acc"] = r.rank(ascending=False, method="min").astype(int)
    out.loc[excluded, "rank_acc"] = -1
    ev = np.column_stack([df["g_res"].notna(), df["bd_depth_m"].notna() | (df["f_hardrock"] >= 0.5), df["lith_cover"] >= 0.8])
    out["evidence_share"] = np.round(ev.mean(axis=1), 2)
    out["status"] = np.where(excluded, "no data", "scored")
    for c in [c for c in df.columns if c.startswith("rule_")]:
        out[c] = df[c].values
    ctx = df[["tf_class", "main_class"]]
    out["tf_class"] = ctx["tf_class"].values
    out["main_class"] = ctx["main_class"].values
    out = out[[c for c in out.columns if c != "geometry"] + ["geometry"]]
    write_layer(gpd.GeoDataFrame(out, crs=grid.crs), LAYER)

    # ---- summary
    s = out[out["status"] == "scored"]
    cols = ["rank_acc", "h3", "state", "lon", "lat"] + (["p_top1_acc"] if len(tops) > 1 else []) + ["p_top_acc", "acc_mean", "gen_mean", "charge_mean"] \
        + [f"{SHORT.get(c, c)}_mean" for c in others] + ["main_class", "tf_class"]
    topc = s.sort_values("rank_acc").head(30)[cols]
    hot = s[s["p_top_acc"] >= 0.5]
    reg = (hot.groupby(["state", "tf_class"], dropna=False)
              .agg(cells=("h3", "size"), mean_p_top=("p_top_acc", "mean"), max_p_top=("p_top_acc", "max"),
                   acc_mean=("acc_mean", "mean"), lon=("lon", "mean"), lat=("lat", "mean"))
              .reset_index())
    import h3
    reg["area_km2"] = (reg["cells"] * h3.average_hexagon_area(RES, unit="km^2")).round(0)
    reg = reg.sort_values(["cells", "mean_p_top"], ascending=False).round(3)
    genhot = s[s["p_top_gen"] >= 0.5].groupby("state").size().sort_values(ascending=False).rename("cells").reset_index()
    q = s[["gen_mean", "charge_mean", "acc_mean"]].quantile([0.1, 0.5, 0.9, 0.99]).round(3)
    q.index = ["p10", "median", "p90", "p99"]
    L = [f"# Phase 4 scores - {REGION}, rules {VERSION} ({RULES.name})", "",
         f"Rules: `configs/{RULES.name}`. Runs: {runs}. Cells scored: {n:,}; no data: {int(excluded.sum()):,}.",
         f"Ranking = share of runs in which a cell is in the top {top:.0%} of the {REGION} grid for accumulation "
         "(source + pathway + reservoir + seal + preservation).", "",
         "## Spread of the main scores across scored cells", "",
         "If charge is high almost everywhere, the source no longer separates cells (the v1 problem).", "",
         q.to_markdown(), "",
         "## Regional shortlist (cells in the top 10% in at least half the runs)", "",
         reg.head(25).to_markdown(index=False) if len(reg) else "_none_", "",
         "## Generation fairway: cells in the top 10% for source in >= half the runs, by state", "",
         genhot.head(15).to_markdown(index=False) if len(genhot) else "_none_", "",
         "## Top 30 cells", "", topc.to_markdown(index=False), "",
         "## How often each rule fired (scored cells)", "", pd.DataFrame(usage).to_markdown(index=False), "",
         f"![maps]({PFX}scores_maps.png)", ""]
    (OUT / f"{PFX}scores_summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    fig, axs = plt.subplots(1, 3, figsize=(18, 7))
    for ax, col, t in zip(axs, ["gen_mean", "acc_mean", "p_top_acc"],
                          ["Generation (mean chance)", "Accumulation (mean chance)", "P(top 10%) - ranking"]):
        sc = ax.scatter(out["lon"], out["lat"], c=out[col], s=0.3, cmap="viridis")
        ax.scatter(out.loc[excluded, "lon"], out.loc[excluded, "lat"], c="lightgrey", s=0.3)
        ax.set_title(t); ax.set_aspect("equal"); fig.colorbar(sc, ax=ax, shrink=0.6)
    fig.savefig(OUT / f"{PFX}scores_maps.png", dpi=120, bbox_inches="tight"); plt.close(fig)
    stage(f"done - wrote metadata/{PFX}scores_summary.md and {PFX}scores_maps.png")


if __name__ == "__main__":
    main()
