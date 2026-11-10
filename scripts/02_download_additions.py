"""
02_download_additions.py  -  Phase 1, step 4

Downloads the V1 additions whose links were verified on 31 Oct 2026.
Already-complete files are skipped; interrupted downloads resume.

  D09  Hasterok global tectonics (Zenodo, CC BY 4.0)      ~1.2 GB
  D08a CRUST1.0 sediment + crustal thickness (UCSD)        a few MB
  D13  ETOPO 2022 60 arc-second bedrock elevation (NOAA)   ~456 MB

D11a (ophiolite database) is a manual download - see README.

Run from the project folder:
  python scripts/02_download_additions.py            -> all
  python scripts/02_download_additions.py --only D08a
"""

import argparse
import hashlib
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]

DOWNLOADS = [
    {
        "id": "D09",
        "folder": "data_raw/D09_hasterok",
        "file": "global_tectonics.zip",
        "url": "https://zenodo.org/records/6586972/files/global_tectonics.zip?download=1",
        "md5": "3903adaa4d9ae80429049b2027c4b6c6",   # published on the Zenodo page
    },
    {
        "id": "D08a",
        "folder": "data_raw/D08a_crust1",
        "file": "sedthk-m.xyz.zip",
        "url": "https://igppweb.ucsd.edu/~gabi/crust1/sedthk-m.xyz.zip",
        "md5": None,
    },
    {
        "id": "D08a",
        "folder": "data_raw/D08a_crust1",
        "file": "crsthk.xyz.zip",
        "url": "https://igppweb.ucsd.edu/~gabi/crust1/crsthk.xyz.zip",
        "md5": None,
    },
    {
        "id": "D13",
        "folder": "data_raw/D13_etopo",
        "file": "ETOPO_2022_v1_60s_N90W180_bed.tif",
        "url": "https://www.ngdc.noaa.gov/mgg/global/relief/ETOPO2022/data/60s/60s_bed_elev_gtif/ETOPO_2022_v1_60s_N90W180_bed.tif",
        "md5": None,
    },
]


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(item):
    dest_dir = ROOT / item["folder"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / item["file"]
    part = dest.with_suffix(dest.suffix + ".part")

    if dest.exists():
        print(f"[{item['id']}] {item['file']} already present - skipping")
        return

    done = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={done}-"} if done else {}
    print(f"[{item['id']}] downloading {item['file']}" + (f" (resuming at {done/1e6:.0f} MB)" if done else ""))

    with requests.get(item["url"], headers=headers, stream=True, timeout=60) as r:
        if r.status_code == 200 and done:      # server ignored resume
            done = 0
        elif r.status_code not in (200, 206):
            raise SystemExit(f"HTTP {r.status_code} for {item['url']}")
        total = done + int(r.headers.get("Content-Length", 0))
        with open(part, "ab" if done else "wb") as fh:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                fh.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r    {done/1e6:,.0f} / {total/1e6:,.0f} MB", end="")
    print()

    if item["md5"]:
        got = md5_of(part)
        if got != item["md5"]:
            raise SystemExit(f"Checksum mismatch for {item['file']} - delete {part.name} and retry")
        print("    checksum OK")
    part.rename(dest)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="dataset ID, e.g. D09")
    args = parser.parse_args()
    for item in DOWNLOADS:
        if args.only and item["id"] != args.only:
            continue
        download(item)
    print("\nDone. Unzip nothing yet - re-run scripts/01_inventory_raw.py first.")


if __name__ == "__main__":
    main()
