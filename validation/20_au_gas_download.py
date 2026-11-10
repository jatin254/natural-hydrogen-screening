"""
20_au_gas_download.py  -  Australia test, step 1: download Geoscience Australia gas analyses (labels)

Source: GA Petroleum Source Rock and Fluids Atlas WFS (ORGCHEM database, CC BY 4.0)
  https://services.ga.gov.au/gis/petroleum-source-rocks/wfs
Layers fetched: Hydrogen (the label), and Methane, Nitrogen, Helium, CarbonDioxide, Gas (for the
dilution check and to see which samples were analysed at all).

What it does
  1) GetCapabilities -> confirms the layer names (saved to metadata/au_wfs_capabilities.xml)
  2) For each layer, pages through GetFeature (WFS 2.0 count/startIndex; falls back to WFS 1.1
     maxFeatures) and saves each page in data_raw/A01_ga_orgchem/<layer>/_pages, so an interrupted run
     resumes. Tries CSV output first, then GeoJSON.
  3) Joins the pages to data_raw/A01_ga_orgchem/<layer>.csv and writes metadata/au_gas_overview.md:
     columns, row counts, and for Hydrogen the value distribution. NO model scores are touched.

Run:  python scripts/20_au_gas_download.py            (all layers)
      python scripts/20_au_gas_download.py --layers Hydrogen
Send me metadata/au_gas_overview.md (and the error text if a layer fails).
"""
import argparse
import io
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_raw" / "A01_ga_orgchem"
WFS = "https://services.ga.gov.au/gis/petroleum-source-rocks/wfs"
NS = "orgchem"
LAYERS = ["Hydrogen", "Methane", "Nitrogen", "Helium", "CarbonDioxide", "Gas"]
PAGE = 5000
HEADERS = {"User-Agent": "h2-prospectivity-research/0.1 (validation study)"}


def get(s, params, tries=4):
    for k in range(tries):
        try:
            r = s.get(WFS, params=params, timeout=180)
            if r.status_code == 200:
                return r
            msg = f"HTTP {r.status_code}: {r.text[:400]}"
        except requests.RequestException as e:
            msg = str(e)
        print(f"      try {k + 1}/{tries} failed - {msg}")
        time.sleep(5 * (k + 1))
    return None


def is_exception(text):
    return "ExceptionReport" in text[:2000] or "ServiceException" in text[:2000]


def parse(text, kind):
    """A page of WFS output (csv or GeoJSON text) as a table; point coordinates go to _lon/_lat."""
    if kind == "csv":
        return pd.read_csv(io.StringIO(text), low_memory=False)
    j = json.loads(text)
    rows = []
    for f in j.get("features", []):
        p = dict(f.get("properties") or {})
        g = f.get("geometry") or {}
        if g.get("type") == "Point":
            p["_lon"], p["_lat"] = g["coordinates"][:2]
        rows.append(p)
    return pd.DataFrame(rows)


def fetch_layer(s, name):
    tn = f"{NS}:{name}"
    d = OUT / name / "_pages"
    d.mkdir(parents=True, exist_ok=True)
    print(f"  {tn}")
    # find a working request shape on the first page
    shapes = [
        ("2.0.0", "csv"), ("2.0.0", "application/json"),
        ("1.1.0", "csv"), ("1.1.0", "application/json"),
    ]
    shape = None
    for ver, fmt in shapes:
        p = {"service": "WFS", "version": ver, "request": "GetFeature", "outputFormat": fmt, "srsName": "EPSG:4326"}
        if ver == "2.0.0":
            p.update(typeNames=tn, count=5)
        else:
            p.update(typeName=tn, maxFeatures=5)
        r = get(s, p, tries=2)
        if r is not None and not is_exception(r.text):
            try:
                parse(r.text, "csv" if fmt == "csv" else "json")
                shape = (ver, fmt)
                break
            except Exception as e:      # noqa: BLE001
                print(f"      {ver}/{fmt}: could not parse ({e})")
        elif r is not None:
            print(f"      {ver}/{fmt}: service exception: {r.text[:300]}")
    if shape is None:
        print(f"    FAILED: no request shape worked for {tn}")
        return None
    ver, fmt = shape
    kind = "csv" if fmt == "csv" else "json"
    print(f"    using WFS {ver}, {fmt}")
    hits = None
    r = get(s, {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": tn, "resultType": "hits"}, tries=2)
    if r is not None:
        m = re.search(r'numberMatched="(\d+)"', r.text) or re.search(r'numberOfFeatures="(\d+)"', r.text)
        hits = int(m.group(1)) if m else None
    print(f"    server reports {hits if hits is not None else 'unknown'} features")
    if ver == "1.1.0":                 # no paging in 1.1: one big request
        f = d / f"all.{kind}"
        if not f.exists():
            r = get(s, {"service": "WFS", "version": ver, "request": "GetFeature", "typeName": tn,
                        "outputFormat": fmt, "srsName": "EPSG:4326"})
            if r is None:
                return None
            f.write_text(r.text, encoding="utf-8")
        files = [f]
    else:
        files, start = [], 0
        while True:
            f = d / f"page_{start:07d}.{kind}"
            if not f.exists():
                r = get(s, {"service": "WFS", "version": ver, "request": "GetFeature", "typeNames": tn,
                            "outputFormat": fmt, "srsName": "EPSG:4326", "count": PAGE, "startIndex": start,
                            })
                if r is None or is_exception(r.text):
                    print(f"    FAILED at startIndex {start}: {'' if r is None else r.text[:300]}")
                    return None
                f.write_text(r.text, encoding="utf-8")
            n = len(parse(f.read_text(encoding="utf-8"), kind))
            files.append(f)
            print(f"    page at {start:,}: {n:,} rows")
            if n < PAGE:
                break
            start += PAGE
    frames = []
    for f in files:
        frames.append(parse(f.read_text(encoding="utf-8"), kind))
    df = pd.concat(frames, ignore_index=True)
    n0 = len(df)
    if hits is not None and n0 != hits:
        print(f"    WARNING: fetched {n0:,} rows but the server reports {hits:,} - paging may be unstable; tell me")
    df.attrs["hits"] = hits
    df = df.drop_duplicates()
    out = OUT / f"{name}.csv"
    df.to_csv(out, index=False)
    print(f"    {name}: {n0:,} rows, {len(df):,} after exact-duplicate removal -> {out.relative_to(ROOT)}")
    return df


def value_column(df, name):
    """Guess the concentration column for a layer (reported in the overview so we can fix it by hand)."""
    cands = [c for c in df.columns if re.search(name, c, re.I) or re.search(r"(conc|value|mol|pct|percent|ppm)", c, re.I)]
    num = [c for c in cands if pd.to_numeric(df[c], errors="coerce").notna().mean() > 0.5]
    return num[0] if num else None


def overview(results):
    L = ["# Geoscience Australia gas analyses - download overview", "",
         f"Source: `{WFS}` (ORGCHEM, CC BY 4.0). Labels only; no model scores were looked at.", ""]
    for name, df in results.items():
        L += [f"## {name}", ""]
        if df is None:
            L += ["**Download failed** - see console output.", ""]
            continue
        L += [f"Rows: {len(df):,} (server reports {df.attrs.get('hits')}). Columns ({len(df.columns)}):", "", "`" + "`, `".join(map(str, df.columns)) + "`", ""]
        L += ["First 3 rows:", "", df.head(3).astype(str).apply(lambda s: s.str.slice(0, 40)).to_markdown(index=False), ""]
        col = value_column(df, name)
        L += [f"Guessed value column: `{col}`", ""]
        if col and name == "Hydrogen":
            v = pd.to_numeric(df[col], errors="coerce")
            unit_cols = [c for c in df.columns if re.search(r"unit", c, re.I)]
            if unit_cols:
                L += ["Units: " + ", ".join(f"`{c}`: {df[c].astype(str).value_counts().head(5).to_dict()}" for c in unit_cols), ""]
            bins = [-1e9, 0, 0.001, 0.01, 0.1, 0.5, 1, 5, 10, 1e9]
            lab = ["<=0", "0-0.001", "0.001-0.01", "0.01-0.1", "0.1-0.5", "0.5-1", "1-5", "5-10", ">10"]
            vc = pd.cut(v, bins, labels=lab).value_counts().reindex(lab)
            L += ["Hydrogen value distribution (unit as reported - check above):", "",
                  vc.rename("samples").to_frame().to_markdown(), "",
                  f"Non-numeric or blank: {int(v.isna().sum()):,}", ""]
            for k in ("WELL", "BOREHOLE", "ENO", "LOCATION", "SAMPLE"):
                cs = [c for c in df.columns if k in c.upper()]
                if cs:
                    L += [f"Distinct `{cs[0]}`: {df[cs[0]].nunique():,}", ""]
                    break
            for k in ("BASIN", "PROVINCE", "STATE", "ONSHORE", "OFFSHORE"):
                cs = [c for c in df.columns if k in c.upper()]
                for c in cs[:2]:
                    L += [f"`{c}` (top 12):", "", df[c].astype(str).value_counts().head(12).rename("rows").to_frame().to_markdown(), ""]
    p = ROOT / "metadata" / "au_gas_overview.md"
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {p.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layers", nargs="*", default=LAYERS)
    a = ap.parse_args()
    s = requests.Session()
    s.headers.update(HEADERS)
    print("GetCapabilities ...")
    r = get(s, {"service": "WFS", "request": "GetCapabilities"})
    if r is None:
        sys.exit("cannot reach the GA WFS - check your internet connection or try later")
    (ROOT / "metadata").mkdir(exist_ok=True)
    (ROOT / "metadata" / "au_wfs_capabilities.xml").write_text(r.text, encoding="utf-8")
    names = set(re.findall(r"<(?:wfs:)?Name>([^<]+)</(?:wfs:)?Name>", r.text))
    missing = [x for x in a.layers if f"{NS}:{x}" not in names]
    if missing:
        print(f"  not in capabilities (will still try): {missing}")
    results = {x: fetch_layer(s, x) for x in a.layers}
    overview(results)


if __name__ == "__main__":
    main()
