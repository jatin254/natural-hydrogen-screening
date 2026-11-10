"""
19_check_sites.py  -  where do the published Indian gas sites fall on the maps?

Reads metadata/india_gas_literature.csv (rows with coordinates), finds each site's grid cell and reports
its V1.2 and V2 scores plus the cell's national percentile (100 = best cell in India).
A handful of sites from one region is an ANECDOTE, not a validation: use it to choose sampling sites.
Writes metadata/india_sites_check.md.
Run after scripts 12 (v1.2) and 12 --rules configs/scoring_rules_v2.yaml (v2).
"""
import sys
from pathlib import Path

import h3
import numpy as np
import pandas as pd
import pyogrio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h2pros.grid import GPKG, RES   # noqa: E402


def main():
    lit = pd.read_csv(ROOT / "metadata" / "india_gas_literature.csv")
    lit = lit.dropna(subset=["lat", "lon"]).copy()
    lit["h3"] = [h3.latlng_to_cell(a, b, RES) for a, b in zip(lit["lat"], lit["lon"])]
    out = lit[["site", "state", "h2", "he", "n2", "coord_precision", "h3"]].copy()
    layers = list(pyogrio.list_layers(GPKG)[:, 0])
    for layer, tag in (("scores", "v1.2"), ("scores_v2", "v2")):
        if layer not in layers:
            print(f"table {layer} not found - run script 12 for {tag} first")
            continue
        s = pyogrio.read_dataframe(GPKG, layer=layer, columns=["h3", "gen_mean", "acc_mean", "p_top_acc", "status"], read_geometry=False)
        s = s[s["status"] == "scored"]
        for col in ("gen_mean", "acc_mean"):
            s[f"{col}_pct"] = s[col].rank(pct=True) * 100
        m = s.set_index("h3")
        out[f"{tag} source pct"] = m["gen_mean_pct"].reindex(out["h3"]).round(0).values
        out[f"{tag} score pct"] = m["acc_mean_pct"].reindex(out["h3"]).round(0).values
        out[f"{tag} P(top 10%)"] = m["p_top_acc"].reindex(out["h3"]).values
    out = out.drop(columns="h3")
    L = ["# Published Indian gas sites on the maps", "",
         "Percentile = share of India's scored cells with a lower score (100 = best). Rows are from "
         "`india_gas_literature.csv` with coordinates; check `coord_precision` before reading much into a row.", "",
         "**This is an anecdote, not a test:** few sites, mostly one region, values of uneven quality. Use it to pick "
         "sampling sites and to spot obvious misses.", "",
         out.to_markdown(index=False), ""]
    (ROOT / "metadata" / "india_sites_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote metadata/india_sites_check.md")


if __name__ == "__main__":
    main()
