"""
17_us_diagnose.py  -  US validation, step 5: DIAGNOSIS after the FAIL (not a test, nothing is tuned)

Which parts of the model, and which raw inputs, carry signal for hydrogen-rich vs hydrogen-poor wells?
Each score's AUC is shown for all cells and separately for the west and east halves (100 W).
A candidate idea for rules v2 is only worth testing if it points the same way in BOTH halves; it must
then be fitted on one half and judged on the other (decisions_log 2026-11-02, "If it fails").
Writes metadata/us_diagnostics.md.
Run:  python scripts/17_us_diagnose.py
"""
import importlib.util
import os
import sys
from pathlib import Path

os.environ["H2_REGION"] = "us"
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h2pros.grid import GPKG   # noqa: E402

spec = importlib.util.spec_from_file_location("v", ROOT / "scripts" / "16_us_validate.py")
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

COMPONENTS = ["gen_mean", "charge_mean", "mig_mean", "res_mean", "seal_mean", "pres_mean", "acc_mean"]
INPUTS = {
    "lithology": ["km2_UM_any", "km2_UM_main", "any_BIF", "any_EVAP", "f_GNS", "f_GRAN", "f_SST", "f_CARB", "f_SH", "f_QUAT",
                  "f_MAF_V", "f_MAF_I", "f_VOLC", "f_MSED", "lith_cover"],
    "structures": ["d_fault_basement", "d_fault_any", "d_neotectonic", "d_thrust", "d_shear", "d_um_rock", "tf_rift", "tf_accretion"],
    "gravity": ["g_res", "wgm_ba"],
    "depth_heat": ["bd_depth_m", "hf_median_50km"],
}


def block_ci(s, y, blocks, n=500, seed=1):
    rng = np.random.default_rng(seed)
    ub = np.unique(blocks)
    idx = {b: np.where(blocks == b)[0] for b in ub}
    out = []
    for _ in range(n):
        pick = np.concatenate([idx[b] for b in rng.choice(ub, len(ub), replace=True)])
        out.append(v.auc(s[pick], y[pick]))
    return np.nanpercentile(out, 5), np.nanpercentile(out, 95)


def main():
    import pyogrio
    t = pyogrio.read_dataframe(GPKG, layer="scores", read_geometry=False)
    for layer, cols in INPUTS.items():
        x = pyogrio.read_dataframe(GPKG, layer=layer, columns=["h3"] + cols, read_geometry=False)
        t = t.merge(x, on="h3", how="left", suffixes=("", f"_{layer}"))
    cells = v.sample()
    d = cells.merge(t, on="h3", how="inner")
    d = d[d["status"] == "scored"].reset_index(drop=True)
    y = d["pos"].values.astype(bool)
    west = (d["lon"] < -100).values
    rows = []
    for group, cols in [("component", COMPONENTS)] + [(k, c) for k, c in INPUTS.items()]:
        for c in cols:
            s = pd.to_numeric(d[c], errors="coerce").values.astype(float)
            a = v.auc(s, y)
            lo, hi = block_ci(s, y, d["block"].values)
            aw, ae = v.auc(s[west], y[west]), v.auc(s[~west], y[~west])
            same = (aw - 0.5) * (ae - 0.5) > 0 and min(abs(aw - 0.5), abs(ae - 0.5)) >= 0.03
            rows.append({"group": group, "score": c, "AUC all": round(a, 3), "90% low": round(lo, 3), "90% high": round(hi, 3),
                         "AUC west": round(aw, 3), "AUC east": round(ae, 3),
                         "direction": "higher = more H2" if a >= 0.5 else "lower = more H2",
                         "consistent both halves": "yes" if same else "", "missing %": round(np.isnan(s).mean() * 100, 1)})
    r = pd.DataFrame(rows)
    r["strength"] = (r["AUC all"] - 0.5).abs()
    # positives vs negatives: medians of key inputs
    med = d.groupby("pos")[[c for cols in INPUTS.values() for c in cols]].median().T.round(2)
    med.columns = ["median, H2-poor cells", "median, H2-rich cells"]
    L = ["# US diagnosis after the FAIL (not a test; nothing tuned)", "",
         f"Cells {len(d):,} ({int(y.sum())} H2-rich). AUC 0.5 = no signal; below 0.5 = the input works in reverse. "
         "'Consistent both halves' = same direction and at least 0.03 from 0.5 in the west AND the east.", "",
         "## Model components", "", r[r["group"] == "component"].drop(columns=["group", "strength"]).to_markdown(index=False), "",
         "## Raw inputs, strongest first", "", r[r["group"] != "component"].sort_values("strength", ascending=False).drop(columns="strength").to_markdown(index=False), "",
         "## Medians of the inputs, H2-poor vs H2-rich cells", "", med.to_markdown(), ""]
    (ROOT / "metadata" / "us_diagnostics.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote metadata/us_diagnostics.md")


if __name__ == "__main__":
    main()
