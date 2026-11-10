"""
04_ngdr_download.py  -  Phase 1b: download India layers from NGDR in one go

Why this can work: the NGDR API guide shows layers are served by a GeoServer
map server (https://geodataindia.gov.in/guestuser/wmsurl128/). GeoServer usually
offers two services on the same address:
  WMS  - map PICTURES (what the portal shows)        -> not usable for analysis
  WFS  - the actual FEATURES with attributes, as GeoJSON -> what we need
If WFS is switched on, each layer can be downloaded for ALL of India in one go,
with no state-by-state exports.

Two steps:

  1) python scripts/04_ngdr_download.py probe
     Checks what the server offers and writes:
       metadata/ngdr_wfs_layers.csv   every downloadable layer (if WFS works)
       metadata/ngdr_wms_layers.csv   every map layer (pictures)
       configs/ngdr_layers.yaml       a DRAFT mapping of our 12 layers to server
                                      layer names - open it and check each line
  2) python scripts/04_ngdr_download.py count
     Asks the server how many features each CANDIDATE layer has and which
     columns it carries (one small request per layer, nothing downloaded).
     Writes metadata/ngdr_layer_counts.csv.
  3) python scripts/04_ngdr_download.py download            (all layers)
     python scripts/04_ngdr_download.py download --only D16
     Downloads every layer in configs/ngdr_layers.yaml that has a server name, to
       data_raw/<folder>/<LAYER>/All_India.geojson
       data_raw/<folder>/<LAYER>/All_India.manifest.json   (where/when/how many)

Credentials (only needed if the server refuses anonymous requests):
  set NGDR_USER=your_username
  set NGDR_PASS=your_password
Never write your password into a file in this project.

The script is polite to the server: one request at a time, a pause between
requests, and it never re-downloads a layer that is already complete.
"""

import argparse
import getpass
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "ngdr_layers.yaml"
META = ROOT / "metadata"

API = os.environ.get("NGDR_API", "https://geodataindia.gov.in/ngdrapi")
OWS = os.environ.get("NGDR_OWS", "https://geodataindia.gov.in/guestuser/wmsurl128/")
PAGE = 2000            # features per request (resumable: each page is saved as it arrives)
PAUSE = 1.0            # seconds between requests
HEADERS = {"User-Agent": "h2-prospectivity-research/0.1 (data download for geological study)"}

# Our selection (decisions_log 2026-11-01). keywords are used to guess the
# server's internal layer name; 'avoid' words exclude look-alike layers.
WANTED = [
    ("D15", "D15_gsi_geology2m",          "Geology_2M",                      ["geology", "2m"],  ["label", "commodity", "fault", "thrust"], "core"),
    ("D16", "D16_gsi_tectonic",           "TECTONIC_FRAMEWORK",              ["framework"],      [], "core"),
    ("D16", "D16_gsi_tectonic",           "SUTURE_ZONE_TECTONIC",            ["suture"],         [], "core"),
    ("D16", "D16_gsi_tectonic",           "SHEAR_ZONE_TECTONIC",             ["shear"],          [], "core"),
    ("D16", "D16_gsi_tectonic",           "FAULT_TECTONIC",                  ["fault", "tecton"], ["active"], "core"),
    ("D16", "D16_gsi_tectonic",           "BASEMENT_DEPTH_TECTONIC",         ["basement", "tecton"], [], "core"),
    ("D16", "D16_gsi_tectonic",           "THRUST_TECTONIC",                 ["thrust", "tecton"], [], "trial"),
    ("D16", "D16_gsi_tectonic",           "BOUGER_GRAVITY_ANOMALY_TECTONIC", ["boug", "tecton"], [], "trial"),
    ("D17", "D17_gsi_seismotectonic",     "ACTIVE_FAULT",                    ["active", "fault"], [], "core"),
    ("D18", "D18_gsi_mineral",            "DEPOSIT",                         ["deposit"],        [], "core"),
    ("D19", "D19_gsi_geothermal",         "GEOTHERMAL_SPRING_GEOTHERMAL",    ["geothermal"],     [], "core"),
    ("D20", "D20_gsi_ground_geophysics",  "GRAVITY",                         ["gravity"],        ["boug", "tecton", "seismo"], "trial"),
]


# ---------------------------------------------------------------- helpers

def session_with_auth(require=False):
    """A requests session; adds a Bearer token if credentials are available."""
    s = requests.Session()
    s.headers.update(HEADERS)
    user, pwd = os.environ.get("NGDR_USER"), os.environ.get("NGDR_PASS")
    if require and not (user and pwd):
        user = input("NGDR username: ").strip()
        pwd = getpass.getpass("NGDR password (not shown): ")
    if user and pwd:
        r = s.post(f"{API}/authenticate", json={"username": user, "password": pwd}, timeout=60)
        if r.ok and "token" in r.text:
            s.headers["Authorization"] = f"Bearer {r.json()['token']}"
            print("Authenticated with NGDR API.")
        else:
            print(f"Authentication failed (HTTP {r.status_code}); continuing without a token.")
    return s


def local(tag):
    return tag.rsplit("}", 1)[-1]


def capabilities(s, service, version):
    r = s.get(OWS, params={"service": service, "version": version, "request": "GetCapabilities"}, timeout=120)
    if not r.ok or b"<" not in r.content[:200]:
        return None, f"HTTP {r.status_code}"
    root = ET.fromstring(r.content)
    if local(root.tag) in ("ServiceExceptionReport", "ExceptionReport"):
        return None, ET.tostring(root, encoding="unicode")[:300]
    return root, "ok"


def wfs_layers(root):
    out = []
    for ft in root.iter():
        if local(ft.tag) != "FeatureType":
            continue
        rec = {"name": "", "title": "", "default_crs": ""}
        for ch in ft:
            t = local(ch.tag)
            if t == "Name":
                rec["name"] = (ch.text or "").strip()
            elif t == "Title":
                rec["title"] = (ch.text or "").strip()
            elif t in ("DefaultCRS", "DefaultSRS", "SRS"):
                rec["default_crs"] = (ch.text or "").strip()
        out.append(rec)
    return out


def wms_layers(root):
    out = []
    for lay in root.iter():
        if local(lay.tag) != "Layer":
            continue
        name = next((c.text for c in lay if local(c.tag) == "Name"), None)
        title = next((c.text for c in lay if local(c.tag) == "Title"), "")
        if name:
            out.append({"name": name.strip(), "title": (title or "").strip()})
    return out


def guess(names, keywords, avoid):
    """Server layer names containing every keyword and none of the avoid words."""
    hits = []
    for n in names:
        low = n.lower()
        if all(k in low for k in keywords) and not any(a in low for a in avoid):
            hits.append(n)
    return sorted(hits, key=len)


# ---------------------------------------------------------------- probe

def probe(args):
    import csv
    META.mkdir(exist_ok=True)
    s = session_with_auth(require=False)

    # what the documented API says about geology layers
    try:
        r = s.post(f"{API}/api/geologylayer", timeout=60)
        print(f"API /geologylayer: HTTP {r.status_code}: {r.text[:300]}")
    except requests.RequestException as err:
        print(f"API /geologylayer not reachable: {err}")

    wms_root, wms_msg = capabilities(s, "WMS", "1.1.1")
    wms = wms_layers(wms_root) if wms_root is not None else []
    print(f"WMS (pictures): {wms_msg}, {len(wms)} layers")

    wfs_root, wfs_msg = None, ""
    for v in ("2.0.0", "1.1.0", "1.0.0"):
        wfs_root, wfs_msg = capabilities(s, "WFS", v)
        if wfs_root is not None:
            break
    wfs = wfs_layers(wfs_root) if wfs_root is not None else []
    print(f"WFS (features): {wfs_msg}, {len(wfs)} layers")

    for fname, rows in (("ngdr_wms_layers.csv", wms), ("ngdr_wfs_layers.csv", wfs)):
        if rows:
            with open(META / fname, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
            print(f"  wrote metadata/{fname}")

    if not wfs:
        print("\nRESULT: the server does not offer WFS (downloadable features) to this account.\n"
              "Options: (a) set NGDR_USER / NGDR_PASS and run probe again;\n"
              "         (b) download from the portal state by state (README, Phase 1b).\n"
              "Send me the lines above.")
        return

    names = [w["name"] for w in wfs]
    lines = ["# NGDR layer mapping - DRAFT written by `probe`. Check every line.",
             "# wfs_name: the server's name for the layer (blank = skip).",
             "# Candidates found on the server are listed as comments under each entry.", "layers:"]
    for ds_id, folder, label, kw, avoid, status in WANTED:
        cands = guess(names, kw, avoid)
        lines += [f"  - id: {ds_id}", f"    folder: {folder}", f"    layer: {label}", f"    status: {status}",
                  f"    wfs_name: {cands[0] if len(cands) == 1 else ''}"]
        lines += [f"    # candidate: {c}" for c in cands[:6]] or ["    # candidate: none found - search metadata/ngdr_wfs_layers.csv"]
    CONFIG.parent.mkdir(exist_ok=True)
    if CONFIG.exists() and not args.overwrite:
        draft = CONFIG.with_suffix(".draft.yaml")
        draft.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n{CONFIG.name} already exists; new draft written to {draft.name}")
    else:
        CONFIG.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nRESULT: WFS works. Draft mapping written to configs/{CONFIG.name}.")
    print("Open it, fill or correct every wfs_name (blank ones had zero or several candidates), then run:\n"
          "  python scripts/04_ngdr_download.py download")


# ---------------------------------------------------------------- count

# Layers we may add, checked before downloading (decisions_log 2026-11-01)
CANDIDATES = [
    # 1:50k lithology: would replace age-only Geology 2M if the size is workable
    "cite:lithology_gcs_ngdr", "cite:lithology_gcs_ngdr1", "cite:lithology_gcs_ngdr1_new",
    "cite:lithology_gcs_ngdr_makevalid", "cite:lithology_25k_ngdr", "cite:karnataka_lithology_50k",
    # mineral maps: ultramafic / serpentinite indicators and uranium
    "cite:iron_ferro_chromite_mineral_map_ngdr", "cite:iron_ferro_chromite_nickel_mineral_map_ngdr",
    "cite:iron_ferro_chromite_pge_mineral_map_ngdr", "cite:iron_ferro_nickel_mineral_map_ngdr",
    "cite:ceramic_magnesite_mineral_map_ngdr", "cite:industri_asbestos_mineral_map_ngdr",
    "cite:others_talc_mineral_map_ngdr", "cite:radioactive_uranium_mineral_map_ngdr",
    "cite:pge_chromite_critical_min_ngdr", "cite:nickel_cobalt_critical_min_ngdr",
    # why the GRAVITY download failed
    "cite:gravity_gcs_ngdr",
]


def count(args):
    import csv
    s = session_with_auth(require=False)
    rows = []
    for name in (args.layers or CANDIDATES):
        params = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": name,
                  "outputFormat": "application/json", "srsName": "EPSG:4326", "count": 1}
        row = {"layer": name, "features": "", "geometry": "", "columns": "", "example": "", "error": ""}
        try:
            r = s.get(OWS, params=params, timeout=120)
            if r.ok and r.text.lstrip().startswith("{"):
                d = r.json()
                row["features"] = d.get("numberMatched") or d.get("totalFeatures") or ""
                if d.get("features"):
                    f = d["features"][0]
                    props = f.get("properties") or {}
                    row["geometry"] = (f.get("geometry") or {}).get("type", "")
                    row["columns"] = "; ".join(props)
                    row["example"] = "; ".join(f"{k}={v}" for k, v in props.items()
                                               if isinstance(v, str) and v.strip())[:300]
            else:
                row["error"] = f"HTTP {r.status_code}: {r.text[:150]}".replace("\n", " ")
        except Exception as err:
            row["error"] = str(err)[:150]
        rows.append(row)
        print(f"  {name:55s} {str(row['features'] or '-'):>9}  {row['geometry'] or row['error'][:40]}")
        time.sleep(PAUSE)
    out = META / "ngdr_layer_counts.csv"
    META.mkdir(exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    print(f"\nwrote {out.relative_to(ROOT)} - send it to me")


# ---------------------------------------------------------------- download

def read_config():
    import yaml
    if not CONFIG.exists():
        raise SystemExit("configs/ngdr_layers.yaml not found - run `probe` first")
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["layers"]


def _get(s, params, log, tries=4):
    """One request with retries (5 s, 20 s, 60 s back-off). Returns parsed JSON or raises."""
    last = None
    for i in range(tries):
        try:
            r = s.get(OWS, params=params, timeout=600)
            log.append({"url": r.url, "status": r.status_code, "at": datetime.now(timezone.utc).isoformat()})
            if r.ok and r.text.lstrip().startswith("{"):
                return r.json()
            last = f"HTTP {r.status_code}: {r.text[:200]}"
        except (requests.RequestException, ValueError) as err:
            last = str(err)[:200]
        if i < tries - 1:
            wait = (5, 20, 60)[min(i, 2)]
            print(f"\n      retry in {wait}s ({last[:80]})")
            time.sleep(wait)
    raise RuntimeError(last)


def fetch_pages(s, type_name, page_dir):
    """Page through a WFS layer, saving each page to page_dir as it arrives.
    Pages already on disk are skipped, so an interrupted download resumes.
    Returns (number reported by server, request log)."""
    page_dir.mkdir(parents=True, exist_ok=True)
    log, matched, start = [], None, 0
    state = page_dir / "_state.json"
    sort = {"sortBy": "gid"}     # stable order between pages; dropped if the server refuses it
    if state.exists():
        st = json.loads(state.read_text())
        matched = st.get("matched")
        sort = sort if st.get("sorted", True) else {}
    while True:
        page = page_dir / f"page_{start:09d}.json"
        if page.exists():
            n = json.loads(page.read_text(encoding="utf-8"))["n"]
        else:
            base = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": type_name,
                    "outputFormat": "application/json", "srsName": "EPSG:4326", "count": PAGE, "startIndex": start}
            if sort and start == 0:
                try:
                    data = _get(s, {**base, **sort}, log, tries=1)
                except RuntimeError:
                    sort = {}                      # server refuses sortBy: use its natural order
                    data = _get(s, base, log)
            else:
                data = _get(s, {**base, **sort}, log)
            feats = data.get("features", [])
            matched = data.get("numberMatched") or data.get("totalFeatures") or matched
            state.write_text(json.dumps({"matched": matched, "sorted": bool(sort)}))
            tmp = page.with_suffix(".part")
            tmp.write_text(json.dumps({"n": len(feats), "features": feats}), encoding="utf-8")
            tmp.replace(page)
            n = len(feats)
            time.sleep(PAUSE)
        done = start + n
        print(f"      {done:,}" + (f" / {matched:,}" if isinstance(matched, int) else ""), end="\r")
        if n < PAGE or (isinstance(matched, int) and done >= matched):
            break
        start += PAGE
    print()
    return matched, log


def join_pages(page_dir, out, name):
    """Stream the saved pages into one GeoJSON without holding it all in memory.
    Returns (feature count, first features for the axis check)."""
    total, sample = 0, []
    tmp = out.with_suffix(".part")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "FeatureCollection", "name": name,
                             "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}})[:-1])
        fh.write(', "features": [\n')
        for page in sorted(page_dir.glob("page_*.json")):
            for f in json.loads(page.read_text(encoding="utf-8"))["features"]:
                fh.write((",\n" if total else "") + json.dumps(f))
                total += 1
                if len(sample) < 50:
                    sample.append(f)
        fh.write("\n]}\n")
    tmp.replace(out)
    return total, sample


def axis_check(features):
    """Warn if coordinates look like (lat, lon) instead of (lon, lat) for India."""
    for f in features[:50]:
        geom = f.get("geometry") or {}
        nums = re.findall(r"-?\d+\.?\d*", json.dumps(geom.get("coordinates", []))[:200])
        if len(nums) >= 2:
            x, y = float(nums[0]), float(nums[1])
            return "swapped?" if (5 <= x <= 38.5 and 66 <= y <= 99) else "ok"
    return "unknown"


def download(args):
    s = session_with_auth(require=False)
    todo = [l for l in read_config() if (not args.only or l["id"] == args.only)]
    for lay in todo:
        name = (lay.get("wfs_name") or "").strip()
        if not name or lay.get("status") == "dropped":
            print(f"[{lay['id']}] {lay['layer']}: {'dropped' if name else 'no wfs_name'} in config - skipped")
            continue
        out_dir = ROOT / "data_raw" / lay["folder"] / lay["layer"]
        out = out_dir / "All_India.geojson"
        man = out_dir / "All_India.manifest.json"
        if out.exists() and man.exists():
            print(f"[{lay['id']}] {lay['layer']}: already downloaded - skipped")
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"[{lay['id']}] {lay['layer']}  <-  {name}")
        page_dir = out_dir / "_pages"
        try:
            matched, log = fetch_pages(s, name, page_dir)
        except Exception as err:
            print(f"\n    FAILED: {err}\n    Pages saved so far are kept; re-run the same command to resume.")
            continue
        n, sample = join_pages(page_dir, out, lay["layer"])
        complete = (not isinstance(matched, int)) or n == matched
        sorted_ok = json.loads((page_dir / "_state.json").read_text()).get("sorted")
        man.write_text(json.dumps({"source": OWS, "server_layer": name, "our_layer": lay["layer"],
                                   "dataset_id": lay["id"], "features": n, "server_reported": matched,
                                   "complete": complete, "axis_order": axis_check(sample),
                                   "paging_sorted_by_gid": sorted_ok,
                                   "downloaded_utc": datetime.now(timezone.utc).isoformat(),
                                   "requests_this_run": len(log)}, indent=2), encoding="utf-8")
        if complete:
            import shutil
            shutil.rmtree(page_dir, ignore_errors=True)
        feats = range(n)
        flag = "" if complete else f"  INCOMPLETE: server reported {matched}"
        print(f"    saved {len(feats):,} features -> {out.relative_to(ROOT)}{flag}")
        time.sleep(PAUSE)
    print("\nNext: python scripts/03_audit_datasets.py --only D15   (then D16 ... D21)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("step", choices=["probe", "count", "download"])
    p.add_argument("layers", nargs="*", help="count: server layer names (default: built-in candidates)")
    p.add_argument("--only", help="dataset ID, e.g. D16")
    p.add_argument("--overwrite", action="store_true", help="probe: overwrite configs/ngdr_layers.yaml")
    args = p.parse_args()
    try:
        {"probe": probe, "count": count, "download": download}[args.step](args)
    except requests.RequestException as err:
        sys.exit(f"Network error: {err}\nCheck your internet connection or try again later.")


if __name__ == "__main__":
    main()
