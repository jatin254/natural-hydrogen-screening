"""
05_lithology_classes.py  -  Phase 2: rock-type classes for India

Applies configs/lithology_classes.yaml (the rulebook) to
  1) every rock name in the 1:50k lithology (from the D15 audit class list)
  2) the mineral occurrence points (D18), to find ultramafic-indicator points
and writes, for review (nothing in data_raw is changed):
  metadata/lithology_50k_classified.csv   one row per rock name: main class, all classes present
  metadata/um_indicator_points.csv        mineral points with ultramafic evidence
  metadata/lithology_review.md            area per class, every ultramafic name, what is left unclassified

Run:  python scripts/05_lithology_classes.py
Edit the rulebook and re-run as often as needed.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h2pros.lithology import classify, load_rules   # noqa: E402

META = ROOT / "metadata"
NAMES = META / "audit" / "D15_Lithology_50K_classes_lithologic.csv"
D18 = ROOT / "data_raw" / "D18_gsi_mineral"
HOT = {"UM", "UMA", "BIF", "MAF_I", "EVAP", "COAL"}


def md_table(df, n=None):
    df = df if n is None else df.head(n)
    return df.to_markdown(index=False) if len(df) else "_none_"


def classify_names(lines):
    if not NAMES.exists():
        lines.append(f"Rock-name list not found ({NAMES.relative_to(ROOT)}): run `python scripts/03_audit_datasets.py --only D15` first.")
        return
    d = pd.read_csv(NAMES)
    res = d["lithologic"].map(classify)
    d["main"] = res.map(lambda r: r["main"])
    d["present"] = res.map(lambda r: "|".join(r["present"]))
    d["unmatched_parts"] = res.map(lambda r: "|".join(r["unmatched"]))
    for c in sorted(HOT):
        d[f"has_{c}"] = res.map(lambda r, c=c: c in r["present"])
    d.to_csv(META / "lithology_50k_classified.csv", index=False)

    total = d["km2"].sum()
    by = d.groupby("main").agg(names=("lithologic", "size"), polygons=("count", "sum"), km2=("km2", "sum")).reset_index()
    by["share_%"] = (by["km2"] / total * 100).round(2)
    labels = {code: lab for code, lab in [(c["code"], c["label"]) for c in __import__("yaml").safe_load(
        (ROOT / "configs" / "lithology_classes.yaml").read_text(encoding="utf-8"))["classes"]]}
    by.insert(1, "class", by["main"].map(labels).fillna("unclassified"))
    lines += ["## 1:50k lithology: area by main class", "",
              f"{len(d):,} rock names, {d['count'].sum():,} polygons, {total:,.0f} km2.", "",
              md_table(by.sort_values("km2", ascending=False)), ""]

    hot = []
    for c in ["UM", "UMA", "BIF", "MAF_I", "EVAP", "COAL"]:
        m, a = d[d["main"] == c], d[d[f"has_{c}"]]
        hot.append({"class": c, "main_km2": round(m["km2"].sum()), "main_polygons": int(m["count"].sum()),
                    "present_anywhere_km2": round(a["km2"].sum()), "present_anywhere_polygons": int(a["count"].sum())})
    lines += ["## Hydrogen-relevant classes", "",
              "`main` = the polygon's first-listed rock; `present anywhere` also counts polygons where it is a minor rock.", "",
              md_table(pd.DataFrame(hot)), ""]

    um = d[d["has_UM"]].sort_values("km2", ascending=False)[["lithologic", "main", "present", "count", "km2"]]
    lines += ["## Every rock name with ultramafic content", "", "Check these: a wrong row here moves the map.", "",
              md_table(um), ""]
    unk = d[d["main"] == "UNK"].sort_values("km2", ascending=False)[["lithologic", "count", "km2"]]
    lines += ["## Unclassified names (largest first)", "", md_table(unk, 40), ""]


def mineral_points(lines):
    import pyogrio
    files = sorted(p for p in D18.rglob("All_India.geojson")) if D18.exists() else []
    if not files:
        lines.append("No D18 mineral files found.")
        return
    rows = []
    for f in files:
        g = pyogrio.read_dataframe(f)
        layer = f.parent.name
        host = next((c for c in ("host_rock", "hostrock") if c in g.columns), None)
        ctx = [c for c in ("geology", "formation", "morphometr", "morphogene", "remarks") if c in g.columns]
        comm = next((c for c in ("commodity", "mineral_or") if c in g.columns), None)
        for _, r in g.iterrows():
            if r.geometry is None or r.geometry.is_empty:
                continue
            h = classify(r[host]) if host else {"present": []}
            c = [classify(r[k]) for k in ctx]
            in_host = "UM" in h["present"]
            in_ctx = any("UM" in x["present"] for x in c)
            alt = "UMA" in h["present"] or any("UMA" in x["present"] for x in c)
            strength = "strong" if in_host else ("moderate" if (in_ctx or alt) else None)
            rows.append({"layer": layer, "gid": r.get("gid"), "commodity": r[comm] if comm else layer,
                         "locality": r.get("locality"), "state": r.get("state"),
                         "lon": round(r.geometry.x, 5), "lat": round(r.geometry.y, 5),
                         "host_rock": r[host] if host else None, "um_evidence": strength or "none",
                         "where": ", ".join(x for x, ok in [("host rock", in_host), ("geology/remarks", in_ctx),
                                                            ("alteration", alt)] if ok)})
    p = pd.DataFrame(rows)
    p["site"] = p["lon"].round(2).astype(str) + "," + p["lat"].round(2).astype(str)   # ~1 km
    um = p[p["um_evidence"] != "none"].copy()
    um.to_csv(META / "um_indicator_points.csv", index=False)
    summ = p.groupby("layer").agg(points=("gid", "size"),
                                  strong=("um_evidence", lambda s: (s == "strong").sum()),
                                  moderate=("um_evidence", lambda s: (s == "moderate").sum())).reset_index()
    lines += ["## Mineral points with ultramafic evidence (D18)", "",
              "strong = ultramafic host rock; moderate = ultramafic only in geology/remarks, or alteration minerals.", "",
              md_table(summ), "",
              f"Distinct sites (~1 km): {um['site'].nunique()} with evidence "
              f"({um.loc[um['um_evidence'] == 'strong', 'site'].nunique()} strong), out of {p['site'].nunique()} sites.", "",
              "Points without ultramafic evidence, by commodity (these do NOT count):", "",
              md_table(p[p["um_evidence"] == "none"].groupby("layer").size().rename("points").reset_index()), ""]


def main():
    load_rules()
    lines = ["# Lithology classes (rulebook v1)", "",
             "Rulebook: `configs/lithology_classes.yaml`. Classifier: `src/h2pros/lithology.py`.", ""]
    classify_names(lines)
    mineral_points(lines)
    out = META / "lithology_review.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}, metadata/lithology_50k_classified.csv, metadata/um_indicator_points.csv")


if __name__ == "__main__":
    main()
