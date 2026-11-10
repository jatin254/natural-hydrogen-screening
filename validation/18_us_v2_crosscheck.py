"""
18_us_v2_crosscheck.py  -  rules v2 candidates, cross-half test (decisions_log 2026-11-02)

The candidates (configs/rules_v2_candidates.yaml) were suggested by the diagnosis of ALL US wells, so
the held-out half is not fully independent: a pass here is encouraging, not proof. Values are not tuned;
only whole mechanism switches are compared.

Method: expected scores (mean of each rule's low/mode/high; independent factors, so means combine
exactly for noisy-OR and products; charge uses the same 50 km lateral rule on expected generation).
For each split (fit = west -> test = east, and the reverse): pick the candidate with the best AUC on the
fit half; report its AUC on the test half next to v1.2 and the thin-sediment baseline there.
Success (both directions): test-half AUC >= 0.60 AND beats the thin-sediment baseline by >= 0.03.
Also: a dilution check - are H2-rich samples simply poor in methane?
Writes metadata/us_v2_crosscheck.md.
"""
import copy
import importlib.util
import itertools
import os
import sys
from pathlib import Path

os.environ["H2_REGION"] = "us"
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h2pros.grid import RAW   # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), ROOT / "scripts" / name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


eng = load("12_score.py")
val = load("16_us_validate.py")
SUCCESS_AUC, SUCCESS_MARGIN = 0.60, 0.03


def apply(cfg, patch):
    c = copy.deepcopy(cfg)
    if "replace_factor" in patch:
        comp, fac = patch["replace_factor"]
        c["components"][comp]["factors"][fac] = {"rules": patch["rules"], "default": patch["default"]}
    if "drop_component" in patch:
        c["components"].pop(patch["drop_component"], None)
    if "drop_factor" in patch:
        comp, fac = patch["drop_factor"]
        c["components"][comp]["factors"].pop(fac, None)
        if not c["components"][comp]["factors"]:
            c["components"].pop(comp)
    return c


def expected(cfg, df, keep, lat):
    pidx, n_par, pi, pj, w = lat
    comp = {}
    for name, cc in cfg["components"].items():
        how = cc.get("combine", "noisy_or")
        acc = np.ones(keep.sum())
        for fac, f in cc["factors"].items():
            idx = eng.rule_index(df, f["rules"])[keep]
            lo, mo, hi = eng.tri_params(f["rules"], f["default"])
            mean = (lo + mo + hi) / 3
            acc *= (1 - mean[idx]) if how == "noisy_or" else mean[idx]
        comp[name] = 1 - acc if how == "noisy_or" else acc
    g = comp["generation"]
    gp = np.zeros(n_par)
    np.maximum.at(gp, pidx[keep], g)
    lt = np.zeros(n_par)
    np.maximum.at(lt, pi, gp[pj] * w)
    charge = np.maximum(g, lt[pidx[keep]])
    accm = charge.copy()
    for name in comp:
        if name != "generation":
            accm *= comp[name]
    return accm


def main():
    base_cfg = yaml.safe_load((ROOT / "configs" / "scoring_rules.yaml").read_text(encoding="utf-8"))
    cand = yaml.safe_load((ROOT / "configs" / "rules_v2_candidates.yaml").read_text(encoding="utf-8"))["switches"]
    grid, df = eng.load_inputs()
    for name, expr in base_cfg.get("derived", {}).items():
        ns = {c: df[c] for c in df.columns}
        ns.update({"minimum": np.fmin, "maximum": np.fmax})
        df[name] = eval(expr, {"__builtins__": {}}, ns)
    keep = ~np.asarray(df.eval(base_cfg["settings"]["exclude_if"], engine="python").fillna(True), dtype=bool)
    lat = eng.lateral_setup(grid, base_cfg["settings"]["lateral_migration_km"], int(base_cfg["settings"].get("lateral_block_res", 5)))
    names = list(cand)
    combos = list(itertools.product(*[list(cand[n]) for n in names]))
    print(f"scoring {len(combos)} candidate rule sets ...", flush=True)
    h3k = df["h3"].values[keep]
    scores = {}
    for combo in combos:
        cfg = base_cfg
        for n, opt in zip(names, combo):
            cfg = apply(cfg, cand[n][opt])
        scores["-".join(f"{n}:{o}" for n, o in zip(names, combo))] = pd.Series(expected(cfg, df, keep, lat), index=h3k)
    cells = val.sample()
    dep = df.set_index("h3")["bd_depth_m"]
    cells = cells[cells["h3"].isin(h3k)].copy()
    lon = df.set_index("h3")["lon"]
    cells["west"] = lon.reindex(cells["h3"]).values < -100
    y = cells["pos"].values.astype(bool)
    rows = []
    for k, s in scores.items():
        v = s.reindex(cells["h3"]).values
        rows.append({"candidate": k, "AUC west": val.auc(v[cells.west.values], y[cells.west.values]),
                     "AUC east": val.auc(v[~cells.west.values], y[~cells.west.values])})
    r = pd.DataFrame(rows).round(3)
    base = "cover:keep-seal:keep-preservation:keep"
    thin = -dep.reindex(cells["h3"]).values
    b_w, b_e = val.auc(thin[cells.west.values], y[cells.west.values]), val.auc(thin[~cells.west.values], y[~cells.west.values])
    out = []
    for fit, test, bt in (("AUC west", "AUC east", b_e), ("AUC east", "AUC west", b_w)):
        best = r.sort_values(fit, ascending=False).iloc[0]
        v12 = r[r["candidate"] == base].iloc[0]
        ok = best[test] >= SUCCESS_AUC and best[test] - bt >= SUCCESS_MARGIN
        out.append({"fitted on": fit.split()[1], "tested on": test.split()[1], "chosen": best["candidate"],
                    "chosen AUC (test half)": best[test], "v1.2 AUC (test half)": v12[test],
                    "thin-sediment baseline (test half)": round(bt, 3), "success": "yes" if ok else "no"})
    res = pd.DataFrame(out)
    # dilution check on the raw samples
    f = sorted((RAW / "D14_usgs_gas").rglob("*.csv"))[0]
    d = pd.read_csv(f, low_memory=False)
    h2 = pd.to_numeric(d["H2"].astype(str).str.replace("<", "", regex=False), errors="coerce")
    d = d[h2.notna()].assign(grp=np.where(h2[h2.notna()] >= 0.5, "H2-rich (>= 0.5%)", "H2-poor (< 0.5%)"))
    cols = [c for c in ("C1", "C2", "N2", "HE", "CO2", "DEPTH") if c in d]
    for c in cols:   # some columns hold text such as "tr" or "<0.01": count those as missing
        d[c] = pd.to_numeric(d[c].astype(str).str.replace("<", "", regex=False).str.strip(), errors="coerce")
    dil = d.groupby("grp")[cols].median().T.round(2)
    dil["samples with a value"] = d[cols].notna().sum().values
    v_all = scores[base].reindex(cells["h3"]).values
    L = ["# Rules v2 candidates: cross-half check", "",
         f"Sanity check: v1.2 expected-score AUC on all cells = {val.auc(v_all, y):.3f} (full Monte Carlo result was 0.517; "
         "these should be close).", "",
         "Candidates come from the diagnosis of ALL US wells, so the held-out half is not fully independent. "
         "A success here justifies an independent test; it is not proof.", "",
         "## Result", "", res.to_markdown(index=False), "",
         f"Success needs, in BOTH directions, test-half AUC >= {SUCCESS_AUC} and >= {SUCCESS_MARGIN} above the thin-sediment baseline.", "",
         "## All candidates (expected scores)", "", r.sort_values("AUC east", ascending=False).to_markdown(index=False), "",
         "## Dilution check: median gas composition (mol%) and depth (ft), all analysed samples", "",
         "If H2-rich samples carry far less methane (C1) and more N2/He, part of the 'thin sediment' signal is dilution: "
         "thick basins make so much methane that hydrogen's share stays small.", "", dil.to_markdown(), ""]
    (ROOT / "metadata" / "us_v2_crosscheck.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(res.to_string(index=False))
    print("wrote metadata/us_v2_crosscheck.md")


if __name__ == "__main__":
    main()
