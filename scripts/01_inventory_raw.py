"""
01_inventory_raw.py  -  Phase 1, step 3

Reads (never changes) everything under data_raw/ and writes:
  metadata/raw_inventory.csv       one row per file or layer, with facts
  metadata/checksums.sha256        a fingerprint of every raw file
  metadata/raw_inventory_report.md a readable summary with warnings

Why checksums: a SHA-256 fingerprint changes if even one byte of a
file changes. Re-run this script later and compare: if a fingerprint
differs, a raw file was modified, which must never happen.

Run from the project folder:
  python scripts/01_inventory_raw.py
"""

import csv
import hashlib
from datetime import date
from pathlib import Path

import pandas as pd
import pyogrio
import rasterio

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data_raw"
META = ROOT / "metadata"

VECTOR_EXT = {".geojson", ".json", ".shp", ".gpkg", ".kml"}
RASTER_EXT = {".tif", ".tiff", ".nc", ".grd", ".asc"}
TABLE_EXT = {".csv", ".txt", ".tsv", ".xlsx", ".xls"}

# Shapefile/QGIS companion files: fingerprinted, but not listed one by one.
SIDECAR_EXT = {".dbf", ".shx", ".prj", ".cpg", ".qmd", ".sbn", ".sbx", ".qix", ".qml"}

# Operating-system junk (macOS zips, Windows thumbnails): skipped entirely.
def is_junk(p: Path) -> bool:
    return ("__MACOSX" in p.parts or p.name.startswith("._")
            or p.name in {".DS_Store", "Thumbs.db", "desktop.ini"}
            or p.name.endswith(".aux.xml"))

# Approximate counts you already audited. A big difference is a warning.
EXPECTED = {
    ("D01_epri", "occurrence"): 341,
    ("D01_epri", "project"): 23,
    ("D02_glim", "glim"): 1_235_259,
    ("D03_gem_faults", "gem"): 16_195,
    ("D06_ihfc", "ihfc"): 91_182,
}


# ---------- helpers -------------------------------------------------------

def sha256_of(path: Path) -> str:
    """Fingerprint a file, or every file inside a folder (e.g. a .gdb)."""
    h = hashlib.sha256()
    files = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
    for f in files:
        h.update(f.relative_to(path.parent).as_posix().encode())
        with open(f, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
    return h.hexdigest()


def size_mb(path: Path) -> float:
    if path.is_dir():
        return round(sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) / 1e6, 1)
    return round(path.stat().st_size / 1e6, 1)


def inspect_vector(path: Path):
    rows = []
    for layer, geom_type in pyogrio.list_layers(path):
        info = pyogrio.read_info(path, layer=layer)
        rows.append({
            "kind": "vector",
            "layer": layer,
            "geometry": geom_type,
            "count": info["features"],
            "crs": info["crs"] or "MISSING",
            "bounds": ", ".join(f"{b:.2f}" for b in info["total_bounds"]) if info.get("total_bounds") is not None else "",
            "columns": "; ".join(info["fields"]),
        })
    return rows


def inspect_raster(path: Path):
    rows = []
    with rasterio.open(path) as src:
        targets = src.subdatasets or [str(path)]
    for target in targets:
        with rasterio.open(target) as r:
            b = r.bounds
            lat_ok = -91 <= b.bottom and b.top <= 91
            lon_180 = -181 <= b.left and b.right <= 181
            lon_360 = -1 <= b.left and b.right <= 361
            if r.crs:
                crs = r.crs.to_string()
                if crs == "EPSG:9518":
                    crs += " (WGS84 + EGM2008 heights; horizontally = EPSG:4326)"
            elif lat_ok and lon_180:
                crs = "MISSING - values fit lon/lat; assign EPSG:4326 in Phase 3"
            elif lat_ok and lon_360:
                crs = "MISSING - lon/lat with longitudes 0-360; assign EPSG:4326 and shift to -180..180 in Phase 3"
            else:
                crs = "MISSING - bounds are not lon/lat, investigate"
            # A global grid that is one cell wider than 360/res stores values
            # ON the grid lines (node registration), not in cell centres.
            span = r.width * abs(r.res[0])
            reg = "node-registered (cells centred on +/-180, +/-90)" if span > 360 + 0.5 * abs(r.res[0]) else "cell-registered"
            rows.append({
                "kind": "raster",
                "layer": target.split(":")[-1] if target != str(path) else "",
                "count": f"{r.width} x {r.height} cells, {r.count} band(s)",
                "crs": crs,
                "resolution": f"{abs(r.res[0]):.5f} x {abs(r.res[1]):.5f} deg",
                "bounds": ", ".join(f"{v:.3f}" for v in b),
                "nodata": r.nodata,
                "dtype": r.dtypes[0],
                "notes": reg,
            })
    return rows


def _find_header_row(lines, delim):
    """First line whose delimiter count matches the most common count.
    Finds the real header when a file has title lines above it."""
    counts = [ln.count(delim) for ln in lines if ln.strip()]
    if not counts:
        return None
    typical = max(set(counts), key=counts.count)
    if typical == 0:
        return None
    return next(i for i, ln in enumerate(lines) if ln.strip() and ln.count(delim) == typical)


def read_text_table(path: Path):
    """Try common delimiters, encodings and header positions; keep the
    parse with the most columns. Returns (dataframe, how it was read)."""
    best, how = None, ""
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            with open(path, encoding=enc) as fh:
                head = [next(fh, "") for _ in range(60)]
        except UnicodeDecodeError:
            continue
        for delim, label in ((",", "comma"), ("\t", "tab"), (";", "semicolon"), ("|", "pipe")):
            starts = {0}
            detected = _find_header_row(head, delim)
            if detected is not None:
                starts.add(detected)
            for start in sorted(starts):
                for quoting in (csv.QUOTE_MINIMAL, csv.QUOTE_NONE):
                    try:
                        df = pd.read_csv(path, sep=delim, encoding=enc, skiprows=start,
                                         quoting=quoting, on_bad_lines="skip", low_memory=False)
                    except Exception:
                        continue
                    if df.shape[1] > 1 and (best is None or df.shape[1] > best.shape[1]):
                        best = df
                        how = f"{label}-delimited, {enc}, header on line {start + 1}"
                        if quoting == csv.QUOTE_NONE:
                            how += ", quotes ignored"
                    break
        if best is not None:
            break
    if best is None:
        raise ValueError("not a table")
    with open(path, "rb") as fh:
        n_lines = sum(1 for _ in fh)
    return best, f"{how}; {n_lines:,} physical lines (quoted text may span lines)"


def inspect_table(path: Path):
    if path.suffix.lower() in {".xlsx", ".xls"}:
        rows = []
        for sheet, df in pd.read_excel(path, sheet_name=None).items():
            rows.append({
                "kind": "table",
                "layer": f"sheet: {sheet}",
                "count": len(df),
                "columns": "; ".join(map(str, df.columns))[:500],
                "notes": coordinate_check(df),
            })
        return rows
    try:
        df, how = read_text_table(path)
    except ValueError:
        if path.suffix.lower() == ".txt":
            return [{"kind": "text document"}]
        raise
    notes = "; ".join(x for x in (how, coordinate_check(df)) if x)
    return [{
        "kind": "table",
        "count": len(df),
        "columns": "; ".join(map(str, df.columns))[:500],
        "notes": notes,
    }]


def coordinate_check(df: pd.DataFrame) -> str:
    """Quick look at lat/lon columns: missing or out-of-range values."""
    cols = {c.lower(): c for c in df.columns}
    lat = next((cols[k] for k in ("latitude", "lat") if k in cols), None)
    lon = next((cols[k] for k in ("longitude", "long", "lon") if k in cols), None)
    if not (lat and lon):
        return ""
    la = pd.to_numeric(df[lat], errors="coerce")
    lo = pd.to_numeric(df[lon], errors="coerce")
    missing = int((la.isna() | lo.isna()).sum())
    bad = int(((la.abs() > 90) | (lo.abs() > 180)).sum())
    dup = int(df.duplicated(subset=[lat, lon]).sum())
    return f"coords: {missing} missing, {bad} out of range, {dup} exact duplicates"


def looks_like_gdb(folder: Path) -> bool:
    """An Esri file geodatabase folder, even if its name lost '.gdb'."""
    return (folder / "gdb").is_file() and any(folder.glob("*.gdbtable"))


def items_in(folder: Path):
    """Files, plus geodatabase folders treated as one item."""
    gdbs = [p for p in folder.rglob("*") if not is_junk(p) and p.is_dir() and (p.suffix.lower() == ".gdb" or looks_like_gdb(p))]
    for p in sorted(folder.rglob("*")):
        if is_junk(p):
            continue
        if any(g in p.parents for g in gdbs):
            continue  # files inside a geodatabase are covered by the folder
        if p in gdbs or p.is_file():
            yield p


def expected_warning(dataset: str, name: str, count) -> str:
    for (ds, key), exp in EXPECTED.items():
        if ds == dataset and key in name.lower() and isinstance(count, int):
            if abs(count - exp) > 0.02 * exp:
                return f"expected about {exp:,}, found {count:,}"
    return ""


# ---------- main ------------------------------------------------------------

def main():
    if not RAW.is_dir():
        raise SystemExit("data_raw/ not found. Run setup_project.py first.")
    META.mkdir(exist_ok=True)

    records, checksums, warnings = [], [], []

    for ds_folder in sorted(p for p in RAW.iterdir() if p.is_dir()):
        junk = [p for p in ds_folder.rglob("*") if is_junk(p) and p.is_file()]
        if junk:
            warnings.append(f"{ds_folder.name}: {len(junk)} system junk files ignored "
                            f"(__MACOSX, ._*, .DS_Store) - safe to delete")
        items = list(items_in(ds_folder))
        if not items:
            warnings.append(f"{ds_folder.name}: folder is empty")
            continue
        for item in items:
            rel = item.relative_to(ROOT).as_posix()
            print(f"Inspecting {rel} ...")
            base = {"dataset": ds_folder.name, "path": rel, "size_mb": size_mb(item)}
            ext = item.suffix.lower()
            try:
                if item.is_dir() and ext != ".gdb":
                    details = [{"kind": "geodatabase (not opened)",
                                "notes": "folder name must end in .gdb for GDAL to open it"}]
                    warnings.append(f"{rel}: this is a file geodatabase whose name lost '.gdb'. "
                                    f"Rename the folder to '{item.name}.gdb' (contents unchanged) and re-run")
                elif ext == ".gdb" or ext in VECTOR_EXT:
                    details = inspect_vector(item)
                elif ext in RASTER_EXT:
                    details = inspect_raster(item)
                elif ext in TABLE_EXT:
                    details = inspect_table(item)
                elif ext in SIDECAR_EXT:
                    details = [{"kind": "sidecar"}]
                else:
                    details = [{"kind": "other (checksum only)"}]
            except Exception as err:  # keep going; report the problem
                details = [{"kind": "ERROR", "notes": str(err)[:200]}]
                warnings.append(f"{rel}: could not read ({err})")

            # compare the largest layer/sheet with the count you audited
            counts = [d["count"] for d in details if isinstance(d.get("count"), int)]
            if counts:
                biggest = max(details, key=lambda d: d["count"] if isinstance(d.get("count"), int) else -1)
                name_and_layer = f"{item.name} {biggest.get('layer', '')}"
                w = expected_warning(ds_folder.name, name_and_layer, biggest["count"])
                if w:
                    warnings.append(f"{rel}: {w}")
            for d in details:
                row = {**base, **d}
                if str(d.get("crs", "")).startswith("MISSING"):
                    warnings.append(f"{rel}: no CRS stored in the file ({d['crs'].split(' - ')[-1]})")
                if str(d.get("crs", "")) == "EPSG:4979":
                    warnings.append(f"{rel}: CRS is EPSG:4979 (WGS84 3D) - horizontally identical to EPSG:4326, fine")
                records.append(row)

            checksums.append(f"{sha256_of(item)}  {rel}")

    # write outputs
    pd.DataFrame(records).to_csv(META / "raw_inventory.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    (META / "checksums.sha256").write_text("\n".join(checksums) + "\n", encoding="utf-8")

    lines = [f"# Raw data inventory - {date.today().isoformat()}", ""]
    df = pd.DataFrame(records)
    for ds, grp in df.groupby("dataset"):
        lines.append(f"## {ds}")
        n_side = int((grp["kind"] == "sidecar").sum())
        for _, r in grp[grp["kind"] != "sidecar"].iterrows():
            facts = [f"{r['kind']}"]
            for col in ("layer", "count", "crs", "resolution", "notes"):
                if col in r and pd.notna(r[col]) and str(r[col]):
                    facts.append(f"{col}: {r[col]}")
            lines.append(f"- `{r['path']}` ({r['size_mb']} MB) - " + " | ".join(map(str, facts)))
        if n_side:
            lines.append(f"- plus {n_side} companion files (.dbf, .shx, .prj, styles ...) - fingerprinted, not listed")
        lines.append("")
    lines.append("## Warnings")
    lines += [f"- {w}" for w in warnings] or ["- none"]
    (META / "raw_inventory_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nWrote metadata/raw_inventory.csv, checksums.sha256, raw_inventory_report.md")
    print(f"{len(warnings)} warning(s). Open raw_inventory_report.md to review.")


if __name__ == "__main__":
    main()
