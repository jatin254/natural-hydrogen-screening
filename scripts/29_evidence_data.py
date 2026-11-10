"""
29_evidence_data.py  -  find and download the data for the three evidence layers
(magnetics, radiometrics, groundwater chemistry). NOT scored: decisions_log 2026-11-09.

Two steps:

  1) python scripts/29_evidence_data.py probe
     Nothing large is downloaded. It checks two places and writes metadata/evidence_probe.md:
       a) NGDR (GSI): searches metadata/ngdr_wfs_layers.csv (written earlier by 04 probe) for
          magnetic, geochemistry and radiometric layers, and asks the server for each one's
          feature count and columns (one small request per layer).
       b) CGWB groundwater quality 2019-2023, as republished on Esri India's Living Atlas:
          lists its layers, columns and record counts, and how many records have pH >= 9 and >= 10.
     Send me evidence_probe.md. I then pick the layers and write the build step.

  2) python scripts/29_evidence_data.py water            (all groundwater layers)
     python scripts/29_evidence_data.py water --layers 0 2
     Downloads the groundwater points, resumable, to
       data_raw/D23_cgwb_gwq/layer_<id>.csv  (+ manifest)
     The NGDR layers are downloaded later with 04_ngdr_download.py, once their names are known.

NGDR credentials, as before, only from environment variables NGDR_USER / NGDR_PASS.
Licences: GSI data is single-user (Data Policy 2019) - never pass raw files on.
The Esri India service states no licence; treat it as internal use only until CGWB confirms.
"""

import argparse
import csv
import importlib.util
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "metadata"
OUT_MD = META / "evidence_probe.md"
GWQ_DIR = ROOT / "data_raw" / "D23_cgwb_gwq"
ESRI = "https://livingatlas.esri.in/server1/rest/services/Water/Ground_Water_Quality_2019_2023/FeatureServer"
HEADERS = {"User-Agent": "h2-prospectivity-research/0.1 (data download for geological study)"}
PAUSE = 1.0

# words that mark a candidate NGDR layer (name or title)
KEYWORDS = r"magnet|tmi|ngpm|aero|geophys|spectr|radiom|gamma|geochem|ngcm|stream|sediment|soil|uranium|thorium|potass"
SKIP = r"mineral_map|critical_min|deposit|lithology|geology|gravity|boug"   # already handled or not wanted


def ngdr_module():
    """Reuse the session/login code from 04_ngdr_download.py."""
    spec = importlib.util.spec_from_file_location("ngdr04", ROOT / "scripts" / "04_ngdr_download.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def esri_get(s, url, params, tries=3):
    last = None
    for i in range(tries):
        try:
            r = s.get(url, params={**params, "f": "json"}, timeout=180)
            if r.ok:
                d = r.json()
                if "error" not in d:
                    return d
                last = json.dumps(d["error"])[:200]
            else:
                last = f"HTTP {r.status_code}"
        except (requests.RequestException, ValueError) as err:
            last = str(err)[:200]
        time.sleep((5, 20, 60)[min(i, 2)])
    raise RuntimeError(last)


def esri_layers(s):
    d = esri_get(s, f"{ESRI}/layers", {})
    return d.get("layers", []) + d.get("tables", [])


# ---------------------------------------------------------------- probe

def probe_ngdr(lines):
    lines += ["## A. NGDR (GSI) candidate layers", ""]
    src = META / "ngdr_wfs_layers.csv"
    if not src.exists():
        lines += ["metadata/ngdr_wfs_layers.csv not found - run `python scripts/04_ngdr_download.py probe` first.", ""]
        return
    with open(src, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    cands = [r for r in rows
             if re.search(KEYWORDS, f"{r['name']} {r.get('title', '')}", re.I)
             and not re.search(SKIP, r["name"], re.I)]
    lines += [f"{len(rows)} layers on the server; {len(cands)} match magnetic / geochemistry / radiometric words.", ""]
    if not cands:
        lines += ["None found. Magnetics, NGCM geochemistry and radiometrics are not on the WFS for this account:",
                  "request them through the NGDR portal (Map Service Gateway) instead.", ""]
        return
    ngdr = ngdr_module()
    s = ngdr.session_with_auth(require=False)
    out = []
    lines += ["| layer | title | features | geometry | columns | example |", "|---|---|---|---|---|---|"]
    for r in cands[:60]:
        name = r["name"]
        rec = {"layer": name, "title": r.get("title", ""), "features": "", "geometry": "", "columns": "",
               "example": "", "error": ""}
        params = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": name,
                  "outputFormat": "application/json", "srsName": "EPSG:4326", "count": 1}
        try:
            resp = s.get(ngdr.OWS, params=params, timeout=120)
            if resp.ok and resp.text.lstrip().startswith("{"):
                d = resp.json()
                rec["features"] = d.get("numberMatched") or d.get("totalFeatures") or ""
                if d.get("features"):
                    f = d["features"][0]
                    props = f.get("properties") or {}
                    rec["geometry"] = (f.get("geometry") or {}).get("type", "")
                    rec["columns"] = "; ".join(props)
                    rec["example"] = "; ".join(f"{k}={v}" for k, v in props.items() if v not in (None, ""))[:300]
            else:
                rec["error"] = f"HTTP {resp.status_code}: {resp.text[:120]}".replace("\n", " ")
        except requests.RequestException as err:
            rec["error"] = str(err)[:120]
        out.append(rec)
        print(f"  {name:55s} {str(rec['features'] or '-'):>9}  {rec['geometry'] or rec['error'][:40]}")
        cell = lambda v: str(v).replace("|", "/")[:300]
        lines.append(f"| {name} | {cell(rec['title'])} | {rec['features'] or rec['error'][:60]} | {rec['geometry']} "
                     f"| {cell(rec['columns'])} | {cell(rec['example'])} |")
        time.sleep(PAUSE)
    with open(META / "evidence_probe_ngdr.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    lines.append("")


def ph_field(fields):
    for f in fields:
        if re.fullmatch(r"p_?h(_value|_mg_l)?\d*", f["name"], re.I) or (f.get("alias") or "").strip().lower() == "ph":
            return f
    return None


def probe_water(lines):
    lines += ["## B. CGWB groundwater quality 2019-2023 (Esri India Living Atlas)", "", f"Service: {ESRI}", ""]
    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        layers = esri_layers(s)
    except RuntimeError as err:
        lines += [f"Service not reachable: {err}", ""]
        return
    for lay in layers:
        lid = lay["id"]
        info = esri_get(s, f"{ESRI}/{lid}", {})
        fields = info.get("fields", [])
        cnt = esri_get(s, f"{ESRI}/{lid}/query", {"where": "1=1", "returnCountOnly": "true"}).get("count")
        ph = ph_field(fields)
        ph_counts = {}
        if ph:
            for thr in (9, 10):
                where = f"{ph['name']} >= {thr}" if ph["type"] != "esriFieldTypeString" else \
                        f"CAST({ph['name']} AS FLOAT) >= {thr}"
                try:
                    ph_counts[thr] = esri_get(s, f"{ESRI}/{lid}/query",
                                              {"where": where, "returnCountOnly": "true"}, tries=1).get("count")
                except RuntimeError as err:
                    ph_counts[thr] = f"query refused ({err[:60]})"
        sample = esri_get(s, f"{ESRI}/{lid}/query", {"where": "1=1", "outFields": "*", "resultRecordCount": 1,
                                                    "returnGeometry": "true", "outSR": 4326}).get("features", [])
        ex = sample[0] if sample else {}
        print(f"  layer {lid}: {lay.get('name')}  records={cnt}  pH>=10: {ph_counts.get(10, '-')}")
        lines += [f"### Layer {lid}: {lay.get('name')}",
                  f"- geometry: {info.get('geometryType', 'table')}; records: {cnt}; max per request: {info.get('maxRecordCount')}",
                  f"- pH column: {ph['name'] if ph else 'not found'}; records with pH >= 9: {ph_counts.get(9, '-')}; "
                  f"pH >= 10: {ph_counts.get(10, '-')}",
                  f"- copyright text: {info.get('copyrightText') or '(none)'}",
                  f"- description: {(info.get('description') or '(none)')[:300]}",
                  "- columns: " + "; ".join(f"{f['name']} ({f.get('alias', '')}, {f['type'].replace('esriFieldType', '')})"
                                             for f in fields),
                  f"- example record: {json.dumps(ex.get('attributes', {}))[:600]}",
                  f"- example geometry: {json.dumps(ex.get('geometry', {}))[:120]}", ""]
        time.sleep(PAUSE)


def probe(args):
    META.mkdir(exist_ok=True)
    lines = ["# Evidence-layer data probe", "",
             f"Run {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by scripts/29_evidence_data.py probe.", ""]
    print("NGDR (GSI) layers ...")
    probe_ngdr(lines)
    print("CGWB groundwater quality (Esri India) ...")
    probe_water(lines)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT_MD.relative_to(ROOT)} - send it to me.")


# ---------------------------------------------------------------- water download

def water(args):
    s = requests.Session()
    s.headers.update(HEADERS)
    layers = esri_layers(s)
    todo = [l for l in layers if not args.layers or l["id"] in args.layers]
    GWQ_DIR.mkdir(parents=True, exist_ok=True)
    for lay in todo:
        lid = lay["id"]
        out = GWQ_DIR / f"layer_{lid}.csv"
        man = GWQ_DIR / f"layer_{lid}.manifest.json"
        if out.exists() and man.exists():
            print(f"layer {lid}: already downloaded - skipped")
            continue
        info = esri_get(s, f"{ESRI}/{lid}", {})
        oid = info.get("objectIdField") or next((f["name"] for f in info.get("fields", [])
                                                 if f["type"] == "esriFieldTypeOID"), None)
        page_n = min(int(info.get("maxRecordCount") or 1000), 2000)
        total = esri_get(s, f"{ESRI}/{lid}/query", {"where": "1=1", "returnCountOnly": "true"}).get("count")
        page_dir = GWQ_DIR / f"_pages_{lid}"
        page_dir.mkdir(exist_ok=True)
        print(f"layer {lid}: {lay.get('name')}  ({total} records)")
        start = 0
        while True:
            page = page_dir / f"page_{start:08d}.json"
            if page.exists():
                n = len(json.loads(page.read_text(encoding="utf-8")))
            else:
                p = {"where": "1=1", "outFields": "*", "returnGeometry": "true", "outSR": 4326,
                     "resultOffset": start, "resultRecordCount": page_n}
                if oid:
                    p["orderByFields"] = oid
                feats = esri_get(s, f"{ESRI}/{lid}/query", p).get("features", [])
                tmp = page.with_suffix(".part")
                tmp.write_text(json.dumps(feats), encoding="utf-8")
                tmp.replace(page)
                n = len(feats)
                time.sleep(PAUSE)
            print(f"   {start + n:,} / {total:,}", end="\r")
            if n == 0 or (isinstance(total, int) and start + n >= total):
                break
            start += n
        print()
        rows, cols = [], ["lon", "lat"]
        for page in sorted(page_dir.glob("page_*.json")):
            for f in json.loads(page.read_text(encoding="utf-8")):
                g = f.get("geometry") or {}
                rec = {"lon": g.get("x"), "lat": g.get("y"), **(f.get("attributes") or {})}
                for k in rec:
                    if k not in cols:
                        cols.append(k)
                rows.append(rec)
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        complete = not isinstance(total, int) or len(rows) == total
        man.write_text(json.dumps({"source": f"{ESRI}/{lid}", "layer_name": lay.get("name"), "records": len(rows),
                                   "server_reported": total, "complete": complete,
                                   "downloaded_utc": datetime.now(timezone.utc).isoformat(),
                                   "licence": "none stated by the service; internal use only until CGWB confirms"},
                                  indent=2), encoding="utf-8")
        if complete:
            import shutil
            shutil.rmtree(page_dir, ignore_errors=True)
        print(f"   saved {len(rows):,} rows -> {out.relative_to(ROOT)}" + ("" if complete else "  INCOMPLETE - re-run to resume"))
    print("\nNext: send me metadata/evidence_probe.md (if not yet sent); I write the build step.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("step", choices=["probe", "water"])
    p.add_argument("--layers", nargs="*", type=int, help="water: Esri layer ids (default: all)")
    args = p.parse_args()
    try:
        {"probe": probe, "water": water}[args.step](args)
    except (requests.RequestException, RuntimeError) as err:
        sys.exit(f"Network error: {err}\nCheck your internet connection or try again later.")


if __name__ == "__main__":
    main()
