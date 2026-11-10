"""
13_us_download.py  -  US validation, step 1: download the US layers

Datasets (decisions_log 2026-11-02, US validation protocol):
  U02  USGS State Geologic Map Compilation (SGMC) v1.1      ScienceBase, doi:10.5066/F7WH2N65  (CC0)
  U03  USGS Quaternary Fault and Fold Database (GIS zip)     direct link, 16 MB
  U04  USGS PP 1900 hydrogen prospectivity data release      ScienceBase, doi:10.5066/P13WCG5U  (CC0, benchmark)
Already on disk: D14 USGS gas, D05 WGM2012, D08a CRUST1.0, D06 IHFC, D09 Hasterok.

Two steps, like the NGDR download:
  1) python scripts/13_us_download.py list
       Lists every file in the two ScienceBase releases (and their child items) and writes
       configs/us_downloads.yaml with get: false on each file. Send me that file, or set get: true
       on the files to fetch (I will tell you which).
  2) python scripts/13_us_download.py download
       Downloads U03 and every file marked get: true, resuming interrupted downloads.
Files land in data_raw/U02_sgmc, U03_qfaults, U04_usgs_h2_prospectivity.
"""
import argparse
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs" / "us_downloads.yaml"
HEADERS = {"User-Agent": "h2-prospectivity-research/0.1 (validation study)"}
SB = "https://www.sciencebase.gov/catalog"
RELEASES = [  # id, folder, DOI, ScienceBase item id if known (fallback when the DOI does not resolve)
    ("U02", "U02_sgmc", "10.5066/F7WH2N65", "5888bf4fe4b05ccb964bab9d"),
    ("U04", "U04_usgs_h2_prospectivity", "10.5066/P13WCG5U", "671be1c2d34efed56210dded"),
]
QFAULTS = ("U03", "U03_qfaults", "https://earthquake.usgs.gov/static/lfs/nshm/qfaults/Qfaults_GIS.zip")


def item_id(s, doi, fallback):
    try:
        r = s.get(f"https://doi.org/{doi}", timeout=60, allow_redirects=True)
        m = re.search(r"/item/([0-9a-f]{24})", r.url)
        if m:
            return m.group(1)
    except requests.RequestException:
        pass
    return fallback


def files_of(s, iid, depth=0, title=""):
    """Files of a ScienceBase item and its children (3 levels): attached files, facet files,
    and download links (webLinks / distributionLinks). The raw JSON is saved for checking."""
    r = s.get(f"{SB}/item/{iid}", params={"format": "json"}, timeout=60)
    r.raise_for_status()
    j = r.json()
    (ROOT / "metadata" / "sciencebase").mkdir(parents=True, exist_ok=True)
    (ROOT / "metadata" / "sciencebase" / f"{iid}.json").write_text(r.text, encoding="utf-8")
    t = j.get("title", "")[:80]
    out = []
    for f in j.get("files", []) + [x for fc in j.get("facets", []) for x in fc.get("files", [])]:
        url = f.get("downloadUri") or f.get("url")
        if url:
            out.append({"item": iid, "item_title": t, "name": f.get("name"), "mb": round((f.get("size") or 0) / 1e6, 1), "url": url})
    for w in j.get("webLinks", []) + j.get("distributionLinks", []):
        url = w.get("uri") or w.get("url")
        typ = (w.get("type") or "").lower() + " " + (w.get("title") or "").lower() + " " + (w.get("name") or "").lower()
        if url and (re.search(r"\.(zip|7z|gz|tif|tiff|gdb|csv)(\?|$)", url, re.I) or "download" in typ or "zip" in typ):
            out.append({"item": iid, "item_title": t, "name": w.get("title") or w.get("name") or Path(url).name,
                        "mb": round((w.get("length") or 0) / 1e6, 1), "url": url})
    print(f"    {'  ' * depth}item {iid}: {len(out)} files  [{t}]", flush=True)
    if depth < 3:   # children are listed even when hasChildren is missing
        k = s.get(f"{SB}/items", params={"parentId": iid, "format": "json", "max": 200, "fields": "title"}, timeout=60)
        if k.ok:
            for ch in k.json().get("items", []):
                out += files_of(s, ch["id"], depth + 1, t)
                time.sleep(0.5)
    return out


def do_list(args):
    s = requests.Session()
    s.headers.update(HEADERS)
    lines = ["# US validation downloads. Set get: true on the files to fetch, then run `download`.",
             "# U03 (Quaternary faults) is always downloaded; it is a single direct link.", "files:"]
    for ds, folder, doi, fb in RELEASES:
        iid = item_id(s, doi, fb)
        print(f"{ds}: ScienceBase item {iid} (doi:{doi})")
        try:
            fl = files_of(s, iid)
        except Exception as err:
            print(f"    could not list: {err}  (item {iid}; try opening https://www.sciencebase.gov/catalog/item/{iid} in a browser)")
            continue
        if not fl:
            print("    no files found: send me metadata/sciencebase/*.json and this screen output")
        for f in fl:
            print(f"    {f['mb']:>9,.1f} MB  {f['name']}   [{f['item_title']}]")
            lines += [f"  - id: {ds}", f"    folder: {folder}", f"    name: \"{f['name']}\"", f"    mb: {f['mb']}",
                      f"    item: \"{f['item_title'].replace(chr(34), '')}\"", f"    url: \"{f['url']}\"", "    get: false"]
    CFG.parent.mkdir(exist_ok=True)
    CFG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {CFG.relative_to(ROOT)} - send it to me, or mark files get: true and run `download`")


def fetch(s, url, out):
    if out.exists():
        print(f"    already there: {out.relative_to(ROOT)}")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_suffix(out.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    for attempt in range(4):
        try:
            h = {"Range": f"bytes={have}-"} if have else {}
            with s.get(url, stream=True, timeout=120, headers=h) as r:
                if r.status_code == 416:
                    break
                r.raise_for_status()
                mode = "ab" if have and r.status_code == 206 else "wb"
                total = int(r.headers.get("Content-Length", 0)) + (have if mode == "ab" else 0)
                done = have if mode == "ab" else 0
                with open(part, mode) as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
                        done += len(chunk)
                        if total:
                            print(f"      {done / 1e6:,.0f} / {total / 1e6:,.0f} MB", end="\r", flush=True)
            break
        except requests.RequestException as err:
            have = part.stat().st_size if part.exists() else 0
            print(f"\n      interrupted ({str(err)[:60]}); retrying from {have / 1e6:,.0f} MB")
            time.sleep(5 * (attempt + 1))
    else:
        print(f"\n    FAILED: {out.name} - run the same command again to resume")
        return
    part.replace(out)
    print(f"\n    saved {out.relative_to(ROOT)}")


def do_download(args):
    import yaml
    s = requests.Session()
    s.headers.update(HEADERS)
    ds, folder, url = QFAULTS
    print(f"{ds}: Quaternary faults")
    fetch(s, url, ROOT / "data_raw" / folder / Path(url).name)
    if not CFG.exists():
        print("configs/us_downloads.yaml not found - run `list` first for SGMC and the USGS hydrogen release")
        return
    todo = [f for f in (yaml.safe_load(CFG.read_text(encoding="utf-8")).get("files") or []) if f.get("get")]
    if not todo:
        print("No files marked get: true in configs/us_downloads.yaml")
    for f in todo:
        print(f"{f['id']}: {f['name']} ({f['mb']} MB)")
        name = re.sub(r'[<>:"/\\|?*]', "_", str(f["name"]))
        fetch(s, f["url"], ROOT / "data_raw" / f["folder"] / name)
    print("\nNext: unzip the archives in place (keep the zips), then python scripts/14_us_audit.py")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("step", choices=["list", "download"])
    a = p.parse_args()
    try:
        do_list(a) if a.step == "list" else do_download(a)
    except requests.RequestException as err:
        sys.exit(f"Network error: {err}")


if __name__ == "__main__":
    main()
