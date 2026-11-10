"""
21_au_download.py  -  Australia test, step 2: download the Australian layers (all Geoscience Australia, CC BY 4.0)

  A02  Surface Geology of Australia 1:1M (2012), shapefiles - polygons with free-text `lithology` (classified with
       the SAME India classifier) and the fault / shear-zone lines                      eCat 74619
  A03  Major Crustal Boundaries of Australia 2D (2024)  -> crustal_zones                 eCat 149663
  A04  Neotectonic Features Database (KML)               -> neotectonic                  eCat 74056
  A05  Australian Geological Provinces 2018.01           -> greenstone / ophiolite / rift setting   eCat 116823
  A06  2019 National Gravity Grids, A4 complete Bouguer (ground + marine, 400 m, ~430 MB)   eCat 133023
  A07  GEODATA COAST 100K 2004                           -> land mask                    eCat 61395
  A08  NSW soil-gas H2/He surveys, Record 2024/56, Appendix F (secondary, descriptive)  eCat (Record 2024/56)
Already on disk and reused exactly as in the US test: D05 WGM2012 (unused here), D06 IHFC heat flow,
D08a CRUST1.0 sediment thickness (basement depth, primary), D09 Hasterok provinces.

Run:  python scripts/21_au_download.py            (everything; resumes interrupted downloads)
      python scripts/21_au_download.py --only A02 A06
A link that fails: open the eCat page printed next to it in a browser, download the same file by hand into
data_raw/<folder>/, and run the script again (it unzips whatever is there).
Then send me the console output (or metadata/au_downloads.md).
"""
import argparse
import time
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data_raw"
CF = "https://d28rz98at9flks.cloudfront.net"
ECAT = "https://ecat.ga.gov.au/geonetwork/srv/api/records/"
ITEMS = [  # id, folder, url, eCat record (for manual download)
    ("A02", "A02_ga_geology_1m", f"{CF}/74619/74619_1M_shapefiles.zip", "c8856c41-0d5b-2b1d-e044-00144fdd4fa6"),
    ("A03", "A03_ga_crustal_boundaries", f"{CF}/149663/149663_00_0.ZIP", "ce57a8df-4815-43f4-b66d-92b08d66ff18"),
    ("A04", "A04_ga_neotectonic", f"{CF}/74056/74056_00_0.kml", "bf933a18-58b3-41c9-e044-00144fdd4fa6"),
    ("A05", "A05_ga_provinces", f"{CF}/116823/116823_AGP_2018_shapefile.zip", "af11c9e2-12ac-43a2-a085-edf24cd51c94"),
    ("A06", "A06_ga_gravity", f"{CF}/133023/133023_02_1.zip", "(2019 Australian National Gravity Grids, eCat 133023)"),
    ("A07", "A07_ga_coast", f"{CF}/61395/61395_shp.zip", "a05f7892-eae3-7506-e044-00144fdd4fa6"),
    ("A08", "A08_ga_nsw_soilgas", f"{CF}/149687/149687_03_0.zip", "fe6588fe-85eb-4b2e-a3ac-627abddb7774"),
]
HEADERS = {"User-Agent": "h2-prospectivity-research/0.1 (validation study)"}


def fetch(s, url, dest, tries=5):
    part = dest.with_suffix(dest.suffix + ".part")
    for k in range(tries):
        have = part.stat().st_size if part.exists() else 0
        h = {"Range": f"bytes={have}-"} if have else {}
        try:
            with s.get(url, headers=h, stream=True, timeout=120) as r:
                if r.status_code == 416:            # already complete
                    break
                if r.status_code not in (200, 206):
                    print(f"      HTTP {r.status_code}")
                    if r.status_code in (403, 404):
                        return False
                    raise requests.RequestException(f"HTTP {r.status_code}")
                if r.status_code == 200 and have:   # server ignored Range: start again
                    part.unlink()
                    have = 0
                total = int(r.headers.get("Content-Length", 0)) + have
                done, t0 = have, time.time()
                with open(part, "ab") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
                        done += len(chunk)
                        if total and time.time() - t0 > 5:
                            print(f"      {done / 1e6:,.0f} / {total / 1e6:,.0f} MB", end="\r")
                            t0 = time.time()
            part.replace(dest)
            return True
        except requests.RequestException as e:
            print(f"      try {k + 1}/{tries}: {e}")
            time.sleep(5 * (k + 1))
    return dest.exists()      # a partial download stays as .part and resumes next run


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    s = requests.Session()
    s.headers.update(HEADERS)
    L = ["# Australian layer downloads", "", "| id | folder | file | status | size (MB) |", "| --- | --- | --- | --- | --- |"]
    for iid, folder, url, rec in ITEMS:
        if a.only and iid not in a.only:
            continue
        d = RAW / folder
        d.mkdir(parents=True, exist_ok=True)
        name = url.rsplit("/", 1)[1]
        dest = d / name
        print(f"{iid} {folder}")
        manual = [f for f in d.iterdir() if f.is_file() and not f.name.startswith(".") and not f.name.endswith(".part")]
        ok = dest.exists() or bool(manual) or fetch(s, url, dest)
        status = "ok" if ok else f"FAILED - download by hand from {ECAT + rec if '-' in rec else rec}"
        zips = list(d.glob("*.zip")) + list(d.glob("*.ZIP"))
        for z in zips:
            try:
                with zipfile.ZipFile(z) as zf:
                    bad = zf.testzip()
                    if bad:
                        status = f"CORRUPT zip ({bad}) - delete {z.name} and run again"
                        continue
                    marker = d / f".unzipped_{z.stem}"
                    if not marker.exists():
                        zf.extractall(d / z.stem)
                        marker.write_text("ok")
            except zipfile.BadZipFile:
                status = f"CORRUPT zip - delete {z.name} and run again"
        size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 1e6
        print(f"   {status}")
        L.append(f"| {iid} | {folder} | {name} | {status} | {size:,.0f} |")
    (ROOT / "metadata" / "au_downloads.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote metadata/au_downloads.md")


if __name__ == "__main__":
    main()
