"""
03_audit_datasets.py  -  Phase 1, part B: content audit

The inventory (01) proved the files open. This script looks INSIDE each
dataset and asks: is it fit for the job the model will give it?

For every dataset it writes, under metadata/audit/:
  <ID>_audit.md        findings in plain language
  <ID>_columns.csv     a profile of every attribute column (tables/vectors)
  <ID>_*.png           quick-look maps
and one summary: metadata/audit/AUDIT_SUMMARY.md with all issues ranked.

Issue levels
  BLOCKER  must be resolved before Phase 3 (preprocessing)
  PHASE3   a known transformation to apply during preprocessing
  NOTE     a limitation to record; no action needed now

Nothing in data_raw/ is ever modified.

Run from the project folder (venv active):
  python scripts/03_audit_datasets.py              -> all datasets
  python scripts/03_audit_datasets.py --only D01   -> one dataset
"""

import argparse
import json
import math
import re
import traceback
import zipfile
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")                       # draw to files, no window
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyogrio
import rasterio
from rasterio.enums import Resampling

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data_raw"
OUT = ROOT / "metadata" / "audit"

# GLiM level-1 classes (Hartmann & Moosdorf 2012)
GLIM_L1 = {
    "su": "unconsolidated sediments", "ss": "siliciclastic sedimentary",
    "sm": "mixed sedimentary", "sc": "carbonate sedimentary",
    "py": "pyroclastics", "ev": "evaporites", "mt": "metamorphics",
    "pa": "acid plutonic", "pi": "intermediate plutonic", "pb": "basic plutonic",
    "va": "acid volcanic", "vi": "intermediate volcanic", "vb": "basic volcanic",
    "ig": "ice and glaciers", "wb": "water bodies", "nd": "no data",
}


# =====================================================================
# Shared helpers
# =====================================================================

def is_junk(p: Path) -> bool:
    return ("__MACOSX" in p.parts or p.name.startswith("._")
            or p.name in {".DS_Store", "Thumbs.db", "desktop.ini"})


def find(folder: str, *patterns):
    """Files in a dataset folder matching any glob pattern (case-insensitive)."""
    base = RAW / folder
    if not base.exists():
        return []
    hits = []
    for p in base.rglob("*"):
        if is_junk(p):
            continue
        name = p.name.lower()
        if any(Path(name).match(pat.lower()) for pat in patterns):
            hits.append(p)
    return sorted(hits)


class Report:
    """Collects findings for one dataset and writes its markdown file."""

    def __init__(self, ds_id, title, role):
        self.ds_id, self.title, self.role = ds_id, title, role
        self.lines, self.issues = [], []

    def h(self, text):
        self.lines += ["", f"## {text}", ""]

    def p(self, text):
        self.lines.append(text)

    def table(self, df: pd.DataFrame, max_rows=40):
        if df is None or df.empty:
            self.p("_(none)_")
            return
        self.lines.append(df.head(max_rows).to_markdown(index=False))
        if len(df) > max_rows:
            self.p(f"_... {len(df) - max_rows} more rows in the CSV_")

    def img(self, fname, caption):
        self.lines.append(f"![{caption}]({fname})")

    def issue(self, level, text, action=""):
        self.issues.append({"dataset": self.ds_id, "level": level, "issue": text, "action": action})

    def write(self):
        head = [f"# {self.ds_id} - {self.title}", "",
                f"Audited {date.today().isoformat()}. Role in V1: {self.role}"]
        body = head + self.lines + ["", "## Issues", ""]
        if self.issues:
            body.append(pd.DataFrame(self.issues)[["level", "issue", "action"]].to_markdown(index=False))
        else:
            body.append("None found.")
        (OUT / f"{self.ds_id}_audit.md").write_text("\n".join(body) + "\n", encoding="utf-8")


def profile(df: pd.DataFrame) -> pd.DataFrame:
    """One row per column: type, completeness, distinct values, range, examples."""
    rows = []
    n = len(df)
    for col in df.columns:
        s = df[col]
        nonnull = s.notna() & (s.astype(str).str.strip() != "")
        num = pd.to_numeric(s, errors="coerce")
        numeric_share = num.notna().sum() / max(nonnull.sum(), 1)
        row = {
            "column": col,
            "filled_%": round(100 * nonnull.sum() / max(n, 1), 1),
            "distinct": int(s[nonnull].nunique()),
            "numeric_%": round(100 * numeric_share, 1),
            "min": num.min() if numeric_share > 0.8 else "",
            "max": num.max() if numeric_share > 0.8 else "",
            "examples": "; ".join(map(str, s[nonnull].astype(str).unique()[:4]))[:120],
        }
        rows.append(row)
    return pd.DataFrame(rows)


def value_counts(df, col, top=25):
    vc = df[col].fillna("(blank)").astype(str).value_counts().head(top)
    return vc.rename_axis(col).reset_index(name="count")


def find_col(df, *candidates, contains=None):
    """Find a column by exact name (case-insensitive) or by a substring."""
    lower = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    if contains:
        for c in df.columns:
            if all(k in c.lower() for k in contains):
                return c
    return None


def read_text_table(path: Path) -> pd.DataFrame:
    """Read a CSV/TSV whose delimiter, encoding and header line are unknown."""
    best = None
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            with open(path, encoding=enc) as fh:
                head = [next(fh, "") for _ in range(60)]
        except UnicodeDecodeError:
            continue
        for delim in (",", "\t", ";", "|"):
            counts = [ln.count(delim) for ln in head if ln.strip()]
            typical = max(set(counts), key=counts.count) if counts else 0
            starts = {0}
            if typical:
                starts.add(next(i for i, ln in enumerate(head) if ln.strip() and ln.count(delim) == typical))
            for start in sorted(starts):
                try:
                    df = pd.read_csv(path, sep=delim, encoding=enc, skiprows=start, dtype=str,
                                     on_bad_lines="skip", low_memory=False)
                except Exception:
                    continue
                if df.shape[1] > 1 and (best is None or df.shape[1] > best.shape[1]):
                    best = df
        if best is not None:
            return best
    raise ValueError(f"could not parse {path.name}")


# --- maps -------------------------------------------------------------

_COAST = None


def coastline():
    """Coastline from the Hasterok bundle, used as a map background if present."""
    global _COAST
    if _COAST is None:
        hits = find("D09_hasterok", "ne_10m_coastline.shp")
        if hits:
            try:
                _COAST = pyogrio.read_dataframe(hits[0])
            except Exception:
                _COAST = False
        else:
            _COAST = False
    return _COAST


def world_axes(title):
    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=110)
    c = coastline()
    if c is not False and c is not None:
        c.plot(ax=ax, color="#888888", linewidth=0.3)
    ax.set_xlim(-180, 180)
    ax.set_ylim(-90, 90)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    return fig, ax


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name)
    plt.close(fig)
    return name


# --- distances ------------------------------------------------------------

def haversine_matrix(lat, lon):
    """Great-circle distances in km between all pairs of points."""
    la, lo = np.radians(lat)[:, None], np.radians(lon)[:, None]
    dlat = la - la.T
    dlon = lo - lo.T
    a = np.sin(dlat / 2) ** 2 + np.cos(la) * np.cos(la.T) * np.sin(dlon / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def single_linkage_groups(dist, threshold_km):
    """Group points chained by gaps smaller than threshold (union-find)."""
    n = len(dist)
    parent = list(range(n))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    ii, jj = np.where(np.triu(dist <= threshold_km, k=1))
    for i, j in zip(ii, jj):
        parent[root(i)] = root(j)
    return np.array([root(i) for i in range(n)])


def decimals(text):
    """Number of decimal places written in a coordinate string."""
    m = re.match(r"^\s*-?\d+\.(\d+)\s*$", str(text))
    return len(m.group(1)) if m else 0


# --- rasters ----------------------------------------------------------------

def _xarray_grid(path: Path, max_cols: int):
    """Read a netCDF/GMT grid with xarray: the 2-D variable, its lon/lat
    coordinates, and a decimated copy of the values."""
    import xarray as xr
    ds = xr.open_dataset(path)
    var = max((v for v in ds.data_vars if ds[v].ndim == 2), key=lambda v: ds[v].size)
    da = ds[var]
    ydim, xdim = da.dims
    lon = ds[xdim].values.astype("float64")
    lat = ds[ydim].values.astype("float64")
    step = max(1, lon.size // max_cols)
    vals = da.isel({ydim: slice(None, None, step), xdim: slice(None, None, step)}).values.astype("float64")
    attrs = {k: da.attrs[k] for k in ("units", "long_name", "actual_range") if k in da.attrs}
    ds.close()
    return var, (xdim, ydim), lon, lat, vals, step, attrs


def audit_grid(r: Report, path: Path, png_name: str, units_hint: str, max_cols=1800):
    """Checks for a global grid. netCDF/GMT grids are read with xarray, which
    sees the coordinate variables directly; GeoTIFFs with rasterio."""
    is_nc = path.suffix.lower() in {".nc", ".grd"}
    lat_ascending = False
    if is_nc:
        try:
            var, dims, lon, lat, vals, step, attrs = _xarray_grid(path, max_cols)
        except Exception as err:
            r.p(f"_xarray could not read this file ({err}); falling back to rasterio._")
            is_nc = False
    if is_nc:
        lon_min, lon_max, lat_min, lat_max = lon.min(), lon.max(), lat.min(), lat.max()
        dx = float(np.median(np.abs(np.diff(lon))))
        lat_ascending = lat[0] < lat[-1]
        r.p(f"**Grid:** variable `{var}`, dimensions {dims}; {lon.size} x {lat.size} nodes, spacing {dx:.5f} deg; "
            f"longitude {lon_min:.3f} to {lon_max:.3f}; latitude {lat_min:.3f} to {lat_max:.3f} "
            f"({'south to north' if lat_ascending else 'north to south'}). Attributes: {attrs or 'none'}")
        # does GDAL (used later for preprocessing) see the georeferencing?
        with rasterio.open(path) as src:
            tgt = src.subdatasets[0] if src.subdatasets else path
        with rasterio.open(tgt) as src:
            identity = src.transform.is_identity
        if identity:
            r.issue("PHASE3", "GDAL/rasterio cannot read this file's georeferencing (it sees pixel numbers only)",
                    "In Phase 3, build the transform from the lon/lat coordinate variables shown above")
        span = lon.size * dx
        reg = "node-registered (values on grid lines incl. both edges)" if span > 360 + 0.5 * dx else "cell-registered"
        r.p(f"Registration: {reg}.")
    else:
        with rasterio.open(path) as src:
            step = max(1, src.width // max_cols)
            vals = src.read(1, out_shape=(src.height // step, src.width // step),
                            resampling=Resampling.nearest, masked=True).astype("float64").filled(np.nan)
            b = src.bounds
            lon_min, lon_max, lat_min, lat_max = b.left, b.right, b.bottom, b.top
            r.p(f"**Grid:** {src.width} x {src.height} cells, cell size {abs(src.res[0]):.5f} deg; "
                f"bounds {b.left:.3f}, {b.bottom:.3f}, {b.right:.3f}, {b.top:.3f}; "
                f"nodata {src.nodatavals[0]}; CRS {src.crs or 'none'}")

    data = np.ma.masked_invalid(vals)
    valid = data.compressed()
    r.p("")
    if valid.size == 0:
        r.issue("BLOCKER", "No valid values could be read", "Send me this report")
        return None
    pct = np.percentile(valid, [1, 50, 99])
    stats = pd.DataFrame([{
        "valid_%": round(100 * valid.size / data.size, 2),
        "min": round(valid.min(), 2), "p1": round(pct[0], 2), "median": round(pct[1], 2),
        "p99": round(pct[2], 2), "max": round(valid.max(), 2),
        "exact_zero_%": round(100 * (valid == 0).sum() / valid.size, 2),
    }])
    r.p(f"**Values** (sampled every {step} cells; expected units: {units_hint}):")
    r.table(stats)

    vals_u, counts = np.unique(valid, return_counts=True)
    top = vals_u[counts.argmax()]
    if counts.max() / valid.size > 0.05 and (abs(top) > 1e4 or top in (-9999, 99999)):
        r.issue("PHASE3", f"Value {top} fills {100 * counts.max() / valid.size:.1f}% of cells - likely an undeclared nodata value",
                "Treat it as nodata in preprocessing")
    if 100 * valid.size / data.size < 95:
        r.issue("NOTE", f"Only {100 * valid.size / data.size:.1f}% of cells hold values", "Check the quick-look for gaps")
    if lon_max > 180.5:
        r.issue("PHASE3", f"Longitudes run {lon_min:.2f} to {lon_max:.2f} (0-360 convention)",
                "Shift to -180..180 in preprocessing")
    if lon_min < -180.5 or lon_max > 360.5 or lat_min < -90.5 or lat_max > 90.5:
        r.issue("BLOCKER", f"Coordinates outside any lon/lat range ({lon_min:.1f}..{lon_max:.1f}, {lat_min:.1f}..{lat_max:.1f})",
                "Send me this report")

    # quick-look map, north up, -180..180
    show = data[::-1] if lat_ascending else data
    if lon_max > 180.5:
        half = show.shape[1] // 2
        show = np.ma.concatenate([show[:, half:], show[:, :half]], axis=1)
        extent = (lon_min - 180, lon_max - 180, lat_min, lat_max)
    else:
        extent = (lon_min, lon_max, lat_min, lat_max)
    fig, ax = world_axes(f"{r.ds_id}: {path.name}")
    lo, hi = np.percentile(valid, [2, 98])
    im = ax.imshow(show, extent=extent, vmin=lo, vmax=hi, cmap="RdBu_r", interpolation="nearest", zorder=0)
    fig.colorbar(im, ax=ax, shrink=0.7, label=units_hint)
    r.img(save(fig, png_name), "quick look")
    return stats


# =====================================================================
# Dataset audits
# =====================================================================

def audit_D01():
    r = Report("D01", "EPRI Natural Hydrogen Database", "validation and diagnostics only (never training labels as-is)")
    occ_files = find("D01_epri", "*occur*.csv") or find("D01_epri", "*.csv")[:1]
    if not occ_files:
        r.issue("BLOCKER", "No occurrence CSV found in data_raw/D01_epri", "Check the file name")
        return r
    occ = read_text_table(occ_files[0])
    # collapse line breaks and repeated spaces inside text cells ("Russian\nFederation")
    for c in occ.columns:
        occ[c] = occ[c].astype("string").str.replace(r"\s+", " ", regex=True).str.strip()
    r.h("Occurrences - columns")
    prof = profile(occ)
    prof.to_csv(OUT / "D01_occurrence_columns.csv", index=False)
    r.p(f"{len(occ)} records, {occ.shape[1]} columns (file: `{occ_files[0].name}`).")
    r.table(prof)

    for col in ("Category", "Subcategory", "Country"):
        c = find_col(occ, col)
        if c:
            r.h(f"Occurrences by {c}")
            r.table(value_counts(occ, c, top=45))
    cat, sub = find_col(occ, "Category"), find_col(occ, "Subcategory")
    if cat and sub:
        r.h("Category x Subcategory")
        r.p("Category says WHAT was found (free gas, dissolved gas, fluid inclusions). "
            "These are different evidence types and will validate different maps.")
        ct = pd.crosstab(occ[sub], occ[cat], margins=True, margins_name="total").reset_index()
        r.table(ct.sort_values("total", ascending=False), max_rows=25)

    # hydrogen content: how often is it a usable number?
    hcol = find_col(occ, "Hydrogen", "Content")
    if hcol:
        num = pd.to_numeric(occ[hcol].str.replace("%", "", regex=False).str.replace(",", ".", regex=False),
                            errors="coerce")
        r.h("Hydrogen concentration field")
        r.p(f"Field `{hcol}`: {num.notna().sum()} of {len(occ)} values are plain numbers "
            f"(median {num.median():.2f}, max {num.max():.2f}). The rest are text, ranges or blank.")
        if num.notna().sum() < 0.7 * len(occ):
            r.issue("PHASE3", f"Only {num.notna().sum()} of {len(occ)} hydrogen values are numeric",
                    "Standardize concentration and units by hand in Phase 2 occurrence QC")

    # coordinates
    lat_c, lon_c = find_col(occ, "Latitude", "lat"), find_col(occ, "Longitude", "long", "lon")
    if lat_c and lon_c:
        lat = pd.to_numeric(occ[lat_c], errors="coerce")
        lon = pd.to_numeric(occ[lon_c], errors="coerce")
        ok = lat.notna() & lon.notna()
        dec = np.minimum(occ.loc[ok, lat_c].map(decimals), occ.loc[ok, lon_c].map(decimals))
        prec = pd.cut(dec, [-1, 0, 1, 2, 3, 99],
                      labels=["0 dp (~100 km)", "1 dp (~10 km)", "2 dp (~1 km)", "3 dp (~100 m)", "4+ dp (<10 m)"])
        r.h("Coordinate precision (decimal places written)")
        r.p("Decimal places are a proxy for how precisely a site was located. "
            "Coarse coordinates can fall in the wrong grid cell or even the wrong geology.")
        r.table(prec.value_counts().sort_index().rename_axis("precision").reset_index(name="records"))
        coarse = int((dec <= 1).sum())
        dec_max = np.maximum(occ.loc[ok, lat_c].map(decimals), occ.loc[ok, lon_c].map(decimals))
        if dec_max.median() >= 8:
            r.p("**Caveat:** most coordinates carry 8+ decimal places. That is an artefact of conversion "
                "(e.g. 15.70330000019058), not survey precision. True location precision must be graded "
                "from each record's source in Phase 2.")
            r.issue("PHASE3", "Coordinate precision cannot be inferred from decimal places (float artefacts)",
                    "Grade location precision per record from its source in Phase 2")
        if coarse:
            r.issue("NOTE", f"{coarse} occurrences have coordinates with 1 decimal place or fewer (~10 km or worse)",
                    "Flag as low-precision in Phase 2; exclude from fine-scale checks")

        # duplicates and clusters
        la, lo = lat[ok].to_numpy(), lon[ok].to_numpy()
        dist = haversine_matrix(la, lo)
        exact = int(pd.DataFrame({"a": la, "b": lo}).duplicated().sum())
        near1 = int((np.triu(dist < 1.0, k=1)).sum())
        r.h("Independence: duplicates and spatial clusters")
        r.p(f"Exact duplicate coordinates: **{exact}**. Pairs closer than 1 km: **{near1}**.")
        rows = []
        for km in (1, 10, 25, 50, 100):
            g = single_linkage_groups(dist, km)
            sizes = pd.Series(g).value_counts()
            rows.append({"merge distance (km)": km, "groups": len(sizes),
                         "largest group": int(sizes.max()), "singletons": int((sizes == 1).sum())})
        r.p("If records closer than the merge distance belong to the same system, this is how many "
            "independent units remain. This is the real sample size for validation.")
        clusters = pd.DataFrame(rows)
        r.table(clusters)
        n25 = clusters.loc[clusters["merge distance (km)"] == 25, "groups"].iloc[0]
        r.issue("NOTE", f"{ok.sum()} records collapse to ~{n25} independent groups at 25 km",
                "Phase 2 groups records into hydrogen systems; validation counts systems, not records")

        country_c = find_col(occ, "Country")
        if country_c:
            top3 = occ[country_c].value_counts(normalize=True).head(3)
            share = 100 * top3.sum()
            r.issue("NOTE", f"Top 3 countries hold {share:.0f}% of records ({', '.join(top3.index)})",
                    "Reporting bias: validate per region, never pooled only")

        fig, ax = world_axes("D01 EPRI occurrences")
        ax.scatter(lo, la, s=8, c="crimson", zorder=3, label="occurrence")
        r.img(save(fig, "D01_occurrences.png"), "occurrence map")

    # projects
    proj_files = find("D01_epri", "*project*.csv")
    if proj_files:
        pj = read_text_table(proj_files[0])
        r.h("Current projects")
        r.p(f"{len(pj)} projects. These are exploration activity, not confirmed hydrogen.")
        profile(pj).to_csv(OUT / "D01_project_columns.csv", index=False)
        for col in ("Status", "Country", "Geological Environment"):
            c = find_col(pj, col)
            if c:
                r.table(value_counts(pj, c, top=15))
        plat, plon = find_col(pj, "Lat", "Latitude"), find_col(pj, "Long", "Longitude", "lon")
        if plat and plon and lat_c:
            pla = pd.to_numeric(pj[plat], errors="coerce").to_numpy()
            plo = pd.to_numeric(pj[plon], errors="coerce").to_numpy()
            ok2 = ~np.isnan(pla) & ~np.isnan(plo)
            d = haversine_matrix(np.r_[pla[ok2], la], np.r_[plo[ok2], lo])[: ok2.sum(), ok2.sum():]
            near = d.min(axis=1)
            r.p(f"Projects within 25 km of a listed occurrence: {(near <= 25).sum()} of {ok2.sum()}.")
    return r


def audit_D02():
    r = Report("D02", "GLiM global lithology", "generation (ultramafic, mafic, granitoid); reservoir/seal surface proxies")
    gdbs = [p for p in (RAW / "D02_glim").rglob("*.gdb") if p.is_dir()]
    if not gdbs:
        r.issue("BLOCKER", "No .gdb folder found", "Rename the geodatabase folder to end in .gdb")
        return r
    gdb = gdbs[0]
    layers = pyogrio.list_layers(gdb)
    layer = next((l for l, _ in layers if "glim" in l.lower()), layers[0][0])
    info = pyogrio.read_info(gdb, layer=layer)
    r.p(f"Layer `{layer}`: {info['features']:,} polygons. CRS: {info['crs']}")
    r.p(f"Fields: {', '.join(info['fields'])}")

    print("    reading GLiM attributes (no geometry) - about 1 minute ...")
    attrs = pyogrio.read_dataframe(gdb, layer=layer, read_geometry=False)
    prof = profile(attrs)
    prof.to_csv(OUT / "D02_columns.csv", index=False)
    r.h("Columns")
    r.table(prof)

    # find the lithology code column: short lowercase letter codes
    code = find_col(attrs, "Litho", "litho_code", "xx")
    if code is None:
        for c in attrs.columns:
            s = attrs[c].dropna().astype(str).head(2000)
            if len(s) and s.str.fullmatch(r"[a-z]{2,8}").mean() > 0.9:
                code = c
                break
    area = find_col(attrs, "Shape_Area", "AREA", "area_km2")
    if code is None:
        r.issue("BLOCKER", "Could not identify the lithology code column", "Send me D02_columns.csv")
        return r
    codes = attrs[code].astype(str).str.strip().str.lower()
    weight = pd.to_numeric(attrs[area], errors="coerce") / 1e6 if area else pd.Series(1.0, index=attrs.index)
    unit = "km2" if area else "polygons"
    r.p(f"Lithology code column: `{code}`. Area column: `{area or 'none (counting polygons)'}` "
        f"- areas are in the file's equal-area projection, so they are true areas.")

    l1 = codes.str[:2]
    t = (pd.DataFrame({"code": l1, "w": weight, "n": 1}).groupby("code")
         .agg(**{unit: ("w", "sum"), "polygons": ("n", "sum")}).reset_index())
    t["share_%"] = (100 * t[unit] / t[unit].sum()).round(2)
    t["class"] = t["code"].map(GLIM_L1).fillna("UNKNOWN CODE")
    t = t.sort_values(unit, ascending=False)
    r.h("Level-1 lithology classes by area")
    r.table(t[["code", "class", unit, "share_%", "polygons"]].round(0))
    unknown = t[t["class"] == "UNKNOWN CODE"]
    if len(unknown):
        r.issue("PHASE3", f"Unrecognized level-1 codes: {', '.join(unknown['code'])}",
                "Check against the GLiM legend before classifying")

    # GLiM full code = 3 x 2 letters: level 1 | level 2 | level 3 ("__" = not specified)
    if codes.str.len().max() >= 6:
        for lvl, sl in (("level 2", slice(2, 4)), ("level 3", slice(4, 6))):
            t2 = (pd.DataFrame({"code": codes.str[sl], "w": weight}).groupby("code")["w"]
                  .agg(["sum", "count"]).rename(columns={"sum": unit, "count": "polygons"}).reset_index())
            t2 = t2[t2["code"] != "__"].sort_values(unit, ascending=False)
            r.h(f"GLiM {lvl} attribute codes (all classes, by area)")
            r.table(t2.round(0), max_rows=30)
            t2.to_csv(OUT / f"D02_{lvl.replace(' ', '')}_codes.csv", index=False)

    # full codes inside the classes that matter for hydrogen generation
    r.h("Sub-classes inside hydrogen-relevant classes")
    r.p("GLiM has no explicit 'ultramafic' class at level 1. Ultramafics, ophiolites and iron formations, "
        "if tagged at all, sit in sub-codes of basic plutonics (pb), metamorphics (mt) or basic volcanics (vb). "
        "The table shows which sub-codes actually exist, so we can decide what to map.")
    full = (pd.DataFrame({"full_code": codes, "w": weight}).groupby("full_code")["w"].sum()
            .rename(unit).reset_index())
    rel = full[full["full_code"].str[:2].isin(["pb", "mt", "vb", "ev"])].sort_values(unit, ascending=False)
    rel.to_csv(OUT / "D02_relevant_subcodes.csv", index=False)
    r.table(rel.round(0), max_rows=50)
    full.sort_values(unit, ascending=False).to_csv(OUT / "D02_all_codes.csv", index=False)
    r.issue("NOTE", "Surface lithology only; Quaternary cover mapped inconsistently between source maps",
            "Record in the register; never treat as subsurface truth")
    r.issue("PHASE3", "Native CRS is World Eckert IV (ESRI:54012), not lon/lat",
            "Reproject once in Phase 3 and cache the result")

    # geometry health on a sample (full check is slow)
    print("    checking geometry validity on a sample ...")
    try:
        import shapely
        n = info["features"]
        parts = []
        for skip in (0, n // 2):
            parts.append(pyogrio.read_dataframe(gdb, layer=layer, columns=[], skip_features=skip, max_features=15000))
        geoms = pd.concat(parts).geometry
        bad = int((~shapely.is_valid(geoms.values)).sum())
        empty = int(geoms.isna().sum() + shapely.is_empty(geoms.values).sum())
        r.h("Geometry health (30,000-polygon sample)")
        r.p(f"Invalid geometries: {bad}; empty geometries: {empty}.")
        if bad:
            r.issue("PHASE3", f"~{100 * bad / len(geoms):.2f}% of sampled polygons are invalid",
                    "Repair with make_valid before overlay")
    except Exception as err:
        r.p(f"_Geometry check skipped: {err}_")
    return r


def audit_D03():
    r = Report("D03", "GEM Global Active Faults", "migration access; seal and preservation penalties")
    files = find("D03_gem_faults", "*.geojson", "*.gpkg", "*.shp")
    if not files:
        r.issue("BLOCKER", "No fault file found", "")
        return r
    gdf = pyogrio.read_dataframe(files[0])
    r.p(f"{len(gdf):,} features; CRS {gdf.crs}; geometry types: "
        f"{', '.join(gdf.geom_type.value_counts().index)}")
    prof = profile(gdf.drop(columns="geometry"))
    prof.to_csv(OUT / "D03_columns.csv", index=False)
    r.h("Attribute completeness")
    r.p("Missing attributes do not mean the property is absent - only that no one recorded it.")
    r.table(prof)

    from pyproj import Geod
    geod = Geod(ellps="WGS84")
    gdf["length_km"] = [geod.geometry_length(g) / 1000 if g is not None else 0 for g in gdf.geometry]
    r.p(f"Total mapped fault length: {gdf['length_km'].sum():,.0f} km; median trace {gdf['length_km'].median():.1f} km.")
    for col in ("slip_type", "catalog_name"):
        c = find_col(gdf, col)
        if c:
            t = gdf.groupby(gdf[c].fillna("(blank)"))["length_km"].agg(["count", "sum"]).round(0)
            t = t.sort_values("sum", ascending=False).reset_index().rename(columns={"sum": "length_km"})
            r.h(f"Faults by {c}")
            r.table(t, max_rows=25)
    empty = int(gdf.geometry.isna().sum() + gdf.geometry.is_empty.sum())
    if empty:
        r.issue("PHASE3", f"{empty} features have no geometry", "Drop them")
    if gdf.has_z.any():
        r.issue("PHASE3", "Geometries carry a Z value (EPSG:4979)", "Drop Z and use EPSG:4326")
    r.issue("NOTE", "Active faults only, with regional gaps (GEM lists Malay Archipelago, Madagascar, Canada)",
            "Distance-to-fault is 'unknown' outside covered regions, not 'far'")

    fig, ax = world_axes("D03 GEM active faults")
    gdf.plot(ax=ax, linewidth=0.4, color="darkorange")
    r.img(save(fig, "D03_faults.png"), "fault map")
    return r


def audit_D04():
    r = Report("D04", "WDMAM magnetic anomaly (retired)", "not used: replaced by D04b EMAG2v3 (licence CC BY-NC 4.0)")
    r.p("Retired on 2026-11-01 because its licence forbids commercial use. Kept only as a record.")
    r.issue("NOTE", "Retired: non-commercial licence; replaced by D04b EMAG2v3", "Do not use in any layer")
    return r


def audit_D04b():
    r = Report("D04b", "EMAG2v3 Earth Magnetic Anomaly Grid (NOAA)", "context only (not scored in V1)")
    files = find("D04b_emag2", "*.tif", "*.tiff", "*.nc", "*.grd")
    if not files:
        r.issue("BLOCKER", "No grid found in data_raw/D04b_emag2", "Download the Upward Continued GIS TIFF")
        return r
    for f in files:
        r.h(f.name)
        audit_grid(r, f, f"D04b_{f.stem[:30]}.png", "nT")
    r.issue("NOTE", "Magnetic anomalies are ambiguous over serpentinite; gaps filled by the MF7 satellite model are not measurements",
            "Context layer only in V1")
    return r


def audit_D05():
    r = Report("D05", "WGM2012 Bouguer gravity", "generation: positive residual gravity (dense body proxy)")
    files = find("D05_wgm2012", "*.grd", "*.nc", "*.tif")
    if not files:
        r.issue("BLOCKER", "No grid found", "")
        return r
    stats = audit_grid(r, files[0], "D05_gravity.png", "mGal")
    if stats is not None and stats["max"].iloc[0] < 50:
        r.issue("BLOCKER", "Values look too small for Bouguer anomaly in mGal", "Check units and the variable read")
    r.issue("PHASE3", "No CRS stored", "Assign EPSG:4326")
    r.issue("NOTE", "Derived from EGM2008 + terrain correction; effective resolution is coarser where ground gravity is sparse",
            "Use long-wavelength-removed residuals, not raw values")
    r.issue("NOTE", "BGI asked about commercial use of derived layers (email sent 2026-11-01); usable internally meanwhile",
            "Log BGI's reply in decisions_log.md; if refused, replace before any client delivery")
    return r


def read_ihfc(path: Path):
    """The GHFDB text file has a code row (P1..P13 = parent fields, C1..C49 = child
    fields) followed by several metadata rows (obligation, scheme, score type,
    unit, name) before the data. Returns (data rows, field dictionary)."""
    df = read_text_table(path)
    id_col = next((c for c in df.columns if df[c].astype(str).str.match(r"^R\d+-\d+$").mean() > 0.5), None)
    pid_col = next((c for c in df.columns if df[c].astype(str).str.match(r"^R\d+-P\d+$").mean() > 0.5), None)
    if id_col is None:
        return df, None, None, None
    is_data = df[id_col].astype(str).str.match(r"^R\d+-\d+$")
    meta = df[~is_data]
    data = df[is_data].copy()
    # name the unnamed trailing columns from the metadata row that labels the ID column
    label_row = meta[meta[id_col].astype(str).str.strip() == "ID"]
    if len(label_row):
        rename = {c: str(label_row.iloc[0][c]).strip() for c in df.columns
                  if str(c).startswith("Unnamed") and pd.notna(label_row.iloc[0][c])}
        data = data.rename(columns=rename)
        meta = meta.rename(columns=rename)
        id_col, pid_col = rename.get(id_col, id_col), rename.get(pid_col, pid_col)
    fields = pd.DataFrame({"code": meta.columns,
                           "metadata (obligation; scheme; score; unit/name)":
                               ["; ".join(str(v) for v in meta[c].dropna().astype(str) if v.strip())
                                for c in meta.columns]})
    return data, fields, id_col, pid_col


def audit_D06():
    r = Report("D06", "IHFC Global Heat Flow Database 2024", "high heat flow (deep source); temperature proxy")
    files = find("D06_ihfc", "*.txt")
    files = [f for f in files if "ghfdb" in f.name.lower()] or files
    if not files:
        r.issue("BLOCKER", "No heat-flow text file found", "")
        return r
    data, fields, id_col, pid_col = read_ihfc(files[0])
    if fields is None:
        r.issue("BLOCKER", "Could not find the record ID column (R24-000001 style)", "Send me D06_columns.csv")
        profile(data).to_csv(OUT / "D06_columns.csv", index=False)
        return r
    fields.to_csv(OUT / "D06_field_dictionary.csv", index=False)
    profile(data).to_csv(OUT / "D06_columns.csv", index=False)
    r.p(f"{len(data):,} measurement (child) records; {data[pid_col].nunique():,} sites (parents). "
        f"Field dictionary: `D06_field_dictionary.csv`.")
    r.h("Field dictionary (from the file's own metadata rows)")
    r.table(fields, max_rows=70)

    # parent fields by code, checked against their stated units and ranges
    def num(c):
        return pd.to_numeric(data[c], errors="coerce") if c in data else pd.Series(np.nan, index=data.index)
    unit_of = dict(zip(fields["code"], fields.iloc[:, 1].astype(str)))
    q, lat, lon = num("P1"), num("P4"), num("P5")
    checks = [("P1 heat flow", "mW" in unit_of.get("P1", "")), ("P4 latitude", lat.abs().max() <= 90),
              ("P5 longitude", lon.abs().max() <= 180)]
    r.h("Key parent fields")
    r.table(pd.DataFrame(checks, columns=["field", "matches unit / range"]))
    if not all(ok for _, ok in checks):
        r.issue("BLOCKER", "Parent field codes P1/P4/P5 do not match heat flow / lat / lon", "Send me D06_field_dictionary.csv")
        return r

    parents = data.assign(q=q, lat=lat, lon=lon).drop_duplicates(pid_col)
    r.p(f"One row per site (parent): {len(parents):,}.")
    r.h("Parent heat flow (mW/m2)")
    r.table(pd.DataFrame([parents["q"].describe(percentiles=[0.001, 0.01, 0.5, 0.99, 0.999]).round(1)]))
    neg = int((parents["q"] < 0).sum())
    high = int((parents["q"] > 250).sum())
    r.p(f"Negative values: {neg}. Above 250 mW/m2: {high} (continental background is ~40-120; values far above "
        "occur only at volcanic/hydrothermal sites or are errors).")
    if neg or high:
        r.issue("PHASE3", f"{neg} negative and {high} >250 mW/m2 site values",
                "Exclude negatives; keep >250 only if quality flags are good and setting is volcanic")

    if "P7" in parents:
        r.h("Environment (P7)")
        r.table(value_counts(parents, "P7"))
    qcol = next((c for c in parents.columns if "quality_score_parent" in str(c).lower()), None)
    if qcol:
        qs = parents[qcol].astype(str)
        r.h(f"Quality score ({qcol})")
        r.p("Format U.M.flags: U = uncertainty score (U1 best ... U5, Ux = not assessed), "
            "M = methodology score. These decide which sites we trust.")
        r.table(value_counts(pd.DataFrame({"U score": qs.str.split(".").str[0]}), "U score"))
        r.table(value_counts(pd.DataFrame({"M score": qs.str.split(".").str[1]}), "M score"))
        not_assessed = (qs.str.split(".").str[0] == "Ux").mean() * 100
        if not_assessed > 50:
            r.issue("NOTE", f"{not_assessed:.0f}% of sites have no uncertainty score (Ux)",
                    "Cannot filter on U score alone; combine with M score and environment")

    ok = parents.dropna(subset=["q", "lat", "lon"])
    cells = (np.floor(ok["lat"] / 5) * 1000 + np.floor(ok["lon"] / 5)).nunique()
    r.p(f"Sites occupy {cells} of ~2,592 global 5-degree cells.")
    r.issue("NOTE", "Point data, strongly clustered", "Do not interpolate into unsampled areas; publish a coverage mask")
    fig, ax = world_axes("D06 heat flow by site (mW/m2)")
    sc = ax.scatter(ok["lon"], ok["lat"], c=ok["q"].clip(0, 150), s=1.5, cmap="inferno", zorder=3)
    fig.colorbar(sc, ax=ax, shrink=0.7, label="mW/m2 (clipped 0-150)")
    r.img(save(fig, "D06_heatflow.png"), "heat-flow sites")
    return r


def _xyz_from_zip(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if not n.startswith("__MACOSX") and not n.endswith("/"))
        with z.open(name) as fh:
            return pd.read_csv(fh, sep=r"\s+", header=None, names=["lon", "lat", "value"])


def audit_D08a():
    r = Report("D08a", "CRUST1.0 sediment and crustal thickness", "reservoir/seal (sediment class); migration surface")
    for fname, label, unit in (("sedthk-m.xyz.zip", "sediment thickness", "m"),
                               ("sedthk.xyz.zip", "sediment thickness", "km"),
                               ("crsthk.xyz.zip", "crustal thickness", "km")):
        hits = find("D08a_crust1", fname)
        if not hits:
            continue
        df = _xyz_from_zip(hits[0])
        r.h(f"{label} ({hits[0].name}, {unit})")
        lon_step = np.median(np.diff(np.sort(df["lon"].unique())))
        r.p(f"{len(df):,} grid points (a full 1-degree grid is 64,800); lon {df.lon.min()} to {df.lon.max()}, "
            f"lat {df.lat.min()} to {df.lat.max()}, spacing {lon_step} deg.")
        r.table(pd.DataFrame([df["value"].describe(percentiles=[0.5, 0.9, 0.99]).round(2)]))
        if len(df) != 64800:
            r.issue("PHASE3", f"{fname}: {len(df)} points, not 64,800", "Check grid completeness")
        if "sed" in fname:
            zero = (df["value"] <= 0).mean() * 100
            r.p(f"Cells with zero sediment: {zero:.1f}%.")
            fig, ax = world_axes(f"D08a {label} ({unit})")
            s = ax.scatter(df.lon, df.lat, c=df["value"], s=2, marker="s", cmap="YlOrBr", zorder=0)
            fig.colorbar(s, ax=ax, shrink=0.7, label=unit)
            r.img(save(fig, "D08a_sediment.png"), "sediment thickness")
    r.issue("NOTE", "1-degree cells (~110 km); offshore and onshore mixed in coastal cells",
            "Use thin / moderate / thick classes only")
    r.issue("NOTE", "No licence stated; citation requested", "Cite; ask before redistributing values")
    return r


def audit_D09():
    r = Report("D09", "Hasterok et al. global provinces, plates, cratons", "generation (cratons, rifts, sutures, orogen age); preservation")
    from pyproj import Geod
    geod = Geod(ellps="WGS84")
    for name in ("global_gprv", "plates", "cratons", "boundaries"):
        hits = [h for h in find("D09_hasterok", f"{name}.shp")]
        if not hits:
            r.issue("BLOCKER", f"{name}.shp not found", "Check the unzipped plates&provinces folder")
            continue
        gdf = pyogrio.read_dataframe(hits[0])
        r.h(f"{name}.shp - {len(gdf):,} features, CRS {gdf.crs}")
        prof = profile(gdf.drop(columns="geometry"))
        prof.to_csv(OUT / f"D09_{name}_columns.csv", index=False)
        r.table(prof)
        import shapely
        bad = int((~shapely.is_valid(gdf.geometry.values)).sum())
        if bad:
            r.issue("PHASE3", f"{name}: {bad} invalid geometries", "Repair with make_valid")
        if gdf.geom_type.str.contains("Polygon").all():
            gdf["area_km2"] = [abs(geod.geometry_area_perimeter(g)[0]) / 1e6 for g in gdf.geometry]
            r.p(f"Total area {gdf['area_km2'].sum() / 1e6:,.1f} million km2 (Earth: 510).")
            # tabulate every low-cardinality text attribute by area: these are the classes we will use
            for c in gdf.columns:
                if c in ("geometry", "area_km2") or gdf[c].dtype.kind in "if":
                    continue
                k = gdf[c].nunique()
                if 2 <= k <= 40:
                    t = gdf.groupby(gdf[c].fillna("(blank)"))["area_km2"].agg(["count", "sum"])
                    t["share_%"] = (100 * t["sum"] / t["sum"].sum()).round(1)
                    r.p(f"**{c}** (by area):")
                    r.table(t.sort_values("sum", ascending=False).round(0).reset_index())
        if name == "global_gprv":
            fig, ax = world_axes("D09 geological provinces")
            col = next((c for c in gdf.columns if re.search(r"type", c, re.I) and gdf[c].nunique() <= 40), None)
            gdf.plot(ax=ax, column=col, categorical=True, legend=bool(col), linewidth=0.1,
                     edgecolor="white", legend_kwds={"fontsize": 6, "loc": "lower left"} if col else None)
            r.img(save(fig, "D09_provinces.png"), "province map")
    r.issue("NOTE", "Authors flag weaker fidelity in much of Africa, eastern CAOB, East Antarctica, eastern Australia",
            "Lower confidence there in the confidence map")
    r.issue("NOTE", "Bundle contains third-party layers (WDMAM copy, gravity, earthquakes, dating) under their own licences",
            "Use only plates&provinces layers in V1")
    return r


def audit_D11a():
    r = Report("D11a", "UTIG PLATES ophiolite database", "generation: ultramafic presence")
    files = find("D11a_ophiolites", "*.shp", "*.gpkg", "*.geojson", "*.kml", "*.gmt")
    tables = find("D11a_ophiolites", "*.csv", "*.xlsx", "*.txt")
    if not files and not tables:
        r.issue("NOTE", "Deferred: not downloaded (decision 2026-11-01)",
                "Ultramafic sources come from GLiM sub-codes, Hasterok provinces and positive gravity in V1")
        return r
    for f in files:
        try:
            gdf = pyogrio.read_dataframe(f)
        except Exception as err:
            r.p(f"`{f.name}`: could not read ({err})")
            continue
        r.h(f"{f.name} - {len(gdf):,} features, CRS {gdf.crs}, {', '.join(gdf.geom_type.value_counts().index)}")
        prof = profile(gdf.drop(columns="geometry"))
        prof.to_csv(OUT / f"D11a_{f.stem}_columns.csv", index=False)
        r.table(prof)
        fig, ax = world_axes(f"D11a {f.name}")
        gdf.plot(ax=ax, color="green", markersize=4, linewidth=0.6)
        r.img(save(fig, f"D11a_{f.stem}.png"), "ophiolites")
    for t in tables:
        try:
            df = read_text_table(t) if t.suffix.lower() != ".xlsx" else pd.read_excel(t)
            r.h(f"{t.name} - {len(df):,} rows")
            r.table(profile(df))
        except Exception:
            pass
    r.issue("NOTE", "Compiled for plate reconstructions; outlines are generalized",
            "Use as presence with a buffer, not exact boundaries")
    return r


def audit_D13():
    r = Report("D13", "ETOPO 2022 60 arc-second bedrock elevation", "land mask; basement elevation with D08a")
    files = find("D13_etopo", "*.tif", "*.nc")
    if not files:
        r.issue("BLOCKER", "No elevation grid found", "")
        return r
    stats = audit_grid(r, files[0], "D13_elevation.png", "m", max_cols=1440)
    with rasterio.open(files[0]) as src:
        arr = src.read(1, out_shape=(src.height // 15, src.width // 15), resampling=Resampling.nearest)
    land = 100 * (arr > 0).mean()
    r.p(f"Share of cells above sea level: {land:.1f}% (Earth: about 29%; includes ice-covered bedrock below sea level as ocean).")
    r.issue("NOTE", "Bedrock version: Antarctica and Greenland show rock surface under ice", "Fine for an onshore mask")
    return r


def audit_D14():
    r = Report("D14", "USGS natural gas compositional analyses (US wells)", "validation of the ranking (optional addition)")
    files = find("D14_usgs_gas", "*.csv") or find("D14_usgs_gas", "*.txt")
    if not files:
        r.issue("NOTE", "Not downloaded (optional)",
                "Download 'Natural Gas Dataset.csv' from https://doi.org/10.5066/P9TR93E3 into data_raw/D14_usgs_gas")
        return r
    df = read_text_table(files[0])
    prof = profile(df)
    prof.to_csv(OUT / "D14_columns.csv", index=False)
    r.p(f"{len(df):,} gas analyses, {df.shape[1]} columns.")
    r.h("Columns")
    r.table(prof, max_rows=60)
    h = next((c for c in df.columns if re.search(r"hydrogen|^h2$", c, re.I) and not re.search(r"sulf|sulph|h2s", c, re.I)), None)
    if not h:
        r.issue("BLOCKER", "No hydrogen column found", "Send me D14_columns.csv")
        return r
    raw = df[h].astype(str).str.strip()
    blank = df[h].isna() | raw.isin(["", "nan", "None", "<NA>"])
    val = pd.to_numeric(raw.str.replace("<", "", regex=False), errors="coerce")
    trace = raw.str.contains(r"tr|<", case=False, na=False)
    rows = [
        ("blank (not reported: unknown, NOT zero)", int(blank.sum())),
        ("reported as trace or below detection", int(trace.sum())),
        ("reported exactly 0", int((val == 0).sum())),
        ("> 0 to < 0.5 mol%", int(((val > 0) & (val < 0.5)).sum())),
        ("0.5 to < 5 mol%", int(((val >= 0.5) & (val < 5)).sum())),
        ("5 to < 10 mol%", int(((val >= 5) & (val < 10)).sum())),
        (">= 10 mol%", int((val >= 10).sum())),
    ]
    r.h(f"Hydrogen field `{h}`")
    r.table(pd.DataFrame(rows, columns=["category", "samples"]))
    r.issue("NOTE", "Blank can mean not measured, unknown or zero; some labs used H2 as carrier gas",
            "Only explicitly reported values count; blanks are never negatives")
    lat, lon = find_col(df, "Latitude", "lat", contains=["lat"]), find_col(df, "Longitude", "long", "lon", contains=["lon"])
    if lat and lon:
        la, lo = pd.to_numeric(df[lat], errors="coerce"), pd.to_numeric(df[lon], errors="coerce")
        fig, ax = world_axes("D14 USGS gas samples (red: H2 >= 0.5 mol%)")
        ax.scatter(lo, la, s=1, c="grey", zorder=2)
        hi = val >= 0.5
        ax.scatter(lo[hi], la[hi], s=6, c="red", zorder=3)
        ax.set_xlim(-170, -60)
        ax.set_ylim(15, 72)
        r.img(save(fig, "D14_gas.png"), "gas samples")
    return r


# =====================================================================
# India: GSI / NGDR layers downloaded state by state
# Expected layout:  data_raw/<Dxx folder>/<layer name>/<State>.geojson
# (files placed directly in the dataset folder are treated as one layer)
# =====================================================================

INDIA_STATES = [
    "Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
    "Chandigarh", "Chhattisgarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Goa",
    "Gujarat", "Haryana", "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka",
    "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Odisha", "Puducherry", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
    "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
]
INDIA_BOX = (66.0, 5.0, 99.0, 38.5)          # lon_min, lat_min, lon_max, lat_max


def _norm(text):
    return re.sub(r"[^a-z]", "", str(text).lower())


def state_of(stem):
    """Match a file name to a state/UT name (longest match wins)."""
    n = _norm(stem)
    hits = [s for s in INDIA_STATES if _norm(s) in n]
    if not hits:   # common short forms
        alias = {"andaman": "Andaman and Nicobar Islands", "an": "Andaman and Nicobar Islands",
                 "jk": "Jammu and Kashmir", "orissa": "Odisha", "dnhdd": "Dadra and Nagar Haveli and Daman and Diu",
                 "pondicherry": "Puducherry", "nctofdelhi": "Delhi", "up": "Uttar Pradesh", "mp": "Madhya Pradesh"}
        hits = [v for k, v in alias.items() if n == k or n.startswith(k)]
    return max(hits, key=len) if hits else None


def india_axes(title):
    fig, ax = plt.subplots(figsize=(8, 8.5), dpi=110)
    c = coastline()
    if c is not False and c is not None:
        c.plot(ax=ax, color="#888888", linewidth=0.4)
    ax.set_xlim(INDIA_BOX[0], INDIA_BOX[2])
    ax.set_ylim(INDIA_BOX[1], INDIA_BOX[3])
    ax.set_title(title, fontsize=10)
    return fig, ax


def audit_gsi_layer(r: Report, ds_id: str, layer: str, files):
    """Combine one layer's state files in memory (nothing is written to data_raw)
    and check completeness, consistency, location, duplicates and classes."""
    import geopandas as gpd
    import shapely
    rows, parts, unmatched = [], [], []
    for f in files:
        try:
            g = pyogrio.read_dataframe(f)
        except Exception as err:
            r.issue("BLOCKER", f"{layer}/{f.name}: could not read ({str(err)[:80]})", "Re-export this file")
            continue
        st = "All India" if _norm(f.stem) in ("allindia", "india") else state_of(f.stem)
        if st is None:
            unmatched.append(f.name)
        rows.append({"file": f.name, "state": st or "?", "features": len(g),
                     "crs": g.crs.to_string() if g.crs else "MISSING",
                     "geometry": ", ".join(g.geom_type.dropna().unique()), "columns": g.shape[1] - 1})
        g["_state"] = st or f.stem
        parts.append(g)
    if not parts:
        return
    per = pd.DataFrame(rows)
    r.h(f"Layer: {layer}")
    r.p(f"{len(files)} files, {per['features'].sum():,} features in total.")
    r.table(per.sort_values("state"), max_rows=40)

    # completeness: which states have no file at all
    have = set(per["state"])
    missing = [] if "All India" in have else [s for s in INDIA_STATES if s not in have]
    man = files[0].parent / "All_India.manifest.json"
    if man.exists():
        m = json.loads(man.read_text(encoding="utf-8"))
        r.p(f"Downloaded {m.get('downloaded_utc', '?')[:19]} from server layer `{m.get('server_layer')}`: "
            f"{m.get('features')} features, server reported {m.get('server_reported')}, axis order {m.get('axis_order')}.")
        if m.get("complete") is False:
            r.issue("BLOCKER", f"{layer}: download incomplete ({m.get('features')} of {m.get('server_reported')})",
                    "Delete the layer folder and re-run the download")
    if unmatched:
        r.issue("PHASE3", f"{layer}: {len(unmatched)} file names not matched to a state ({', '.join(unmatched[:4])})",
                "Rename files to the state name, e.g. Odisha.geojson")
    if missing and len(missing) < len(INDIA_STATES):
        r.p(f"No file for {len(missing)} states/UTs: {', '.join(missing)}.")
        r.issue("NOTE", f"{layer}: {len(missing)} of 36 states/UTs have no file",
                "Download them, or confirm the layer has no features there (an empty state is valid)")
    empty = per[per["features"] == 0]
    if len(empty):
        r.p(f"Files with zero features: {', '.join(empty['file'])}.")

    # consistency of coordinate system and columns across states
    crs_set = set(per["crs"])
    if len(crs_set) > 1:
        r.issue("PHASE3", f"{layer}: states use different CRS ({'; '.join(sorted(crs_set))[:120]})",
                "Reproject every state to EPSG:4326 before combining")
    if "MISSING" in crs_set:
        r.issue("BLOCKER", f"{layer}: some files have no CRS", "Re-export; check the export dialog for a CRS option")
    if crs_set - {"EPSG:4326", "MISSING"} and len(crs_set) == 1:
        r.issue("PHASE3", f"{layer}: CRS is {next(iter(crs_set))}", "Reproject to EPSG:4326 in Phase 3")
    colsets = [set(c for c in g.columns if c not in ("geometry", "_state")) for g in parts]
    allcols = set().union(*colsets)
    partial = sorted(c for c in allcols if sum(c in cs for cs in colsets) < len(colsets))
    if partial:
        r.issue("PHASE3", f"{layer}: {len(partial)} columns missing in some states ({', '.join(partial[:5])})",
                "Harmonise column names when combining")

    # combine in lon/lat
    fixed = [g.to_crs(4326) if g.crs and g.crs.to_epsg() != 4326 else g for g in parts]
    alls = gpd.GeoDataFrame(pd.concat(fixed, ignore_index=True), crs=4326)
    empty = int((alls.geometry.isna() | alls.geometry.is_empty).sum())
    alls = alls[alls.geometry.notna() & ~alls.geometry.is_empty]
    if empty:
        r.issue("PHASE3", f"{layer}: {empty} features have no geometry", "Dropped when combining (attributes only)")

    # location: a few features just beyond the box = map extends into neighbouring
    # countries (normal for GSI tectonic maps); many, or far away = CRS problem
    reps = alls.geometry.representative_point()
    lon, lat = reps.x, reps.y
    outside = ~lon.between(INDIA_BOX[0], INDIA_BOX[2]) | ~lat.between(INDIA_BOX[1], INDIA_BOX[3])
    if outside.any():
        dx = np.maximum(INDIA_BOX[0] - lon, 0) + np.maximum(lon - INDIA_BOX[2], 0)
        dy = np.maximum(INDIA_BOX[1] - lat, 0) + np.maximum(lat - INDIA_BOX[3], 0)
        far = float(np.hypot(dx, dy)[outside].max())
        n, share = int(outside.sum()), outside.mean()
        if share <= 0.05 and far <= 5:
            r.issue("NOTE", f"{layer}: {n} features lie just beyond India (up to {far:.1f} deg away)",
                    "Map extends into neighbouring countries; clipped to the India boundary in Phase 3")
        else:
            r.issue("BLOCKER", f"{layer}: {n} features ({share:.0%}) fall outside India's bounding box, up to {far:.0f} deg away",
                    "Usually a wrong or missing CRS: send me this report")

    # duplicates: identical geometry AND attributes (ignoring server ids) = true duplicate;
    # identical geometry only = several records at one place (e.g. two minerals at one locality)
    id_cols = {"id", "gid", "objectid", "fid", "slnanona", "_state"}
    attrs = [c for c in alls.columns if c != "geometry" and c.lower() not in id_cols]
    # hash geometries in chunks: large layers (360k polygons) would not fit in memory as WKB
    import hashlib
    geoms = alls.geometry.values
    hashes = []
    for i in range(0, len(geoms), 20000):
        hashes += [hashlib.blake2b(w, digest_size=12).digest() for w in shapely.to_wkb(geoms[i:i + 20000])]
    wkb = pd.Series(hashes, index=alls.index)
    key = pd.concat([wkb.rename("_wkb"), alls[attrs].astype(str)], axis=1)
    dup = int(key.duplicated().sum())
    coloc = int(wkb.duplicated().sum()) - dup
    single = len(files) == 1
    if dup:
        r.issue("PHASE3", f"{layer}: {dup} exact duplicate features" + ("" if single else " (same feature in two state files)"),
                "Drop exact duplicates when combining")
    if "gid" in alls.columns and alls["gid"].notna().all() and alls["gid"].duplicated().any():
        r.issue("BLOCKER", f"{layer}: {int(alls['gid'].duplicated().sum())} server ids (gid) repeated",
                "Paging returned some features twice: delete the layer folder and re-download")
    if coloc:
        r.issue("NOTE", f"{layer}: {coloc} features share a location with another record but differ in attributes",
                "Keep both; count the location once when scoring")
    bad = int((~shapely.is_valid(alls.geometry.values)).sum())
    if bad:
        r.issue("PHASE3", f"{layer}: {bad} invalid geometries", "Repair with make_valid")
    r.p(f"Combined: {len(alls):,} features with geometry; exact duplicates: {dup}; same place, different record: {coloc}; invalid geometries: {bad}.")

    # attributes and the classes we will build rules on
    data = alls.drop(columns=["geometry"])
    prof = profile(data.drop(columns=["_state"]))
    safe = re.sub(r"[^A-Za-z0-9]+", "_", layer)[:40]
    prof.to_csv(OUT / f"{ds_id}_{safe}_columns.csv", index=False)
    r.p(f"Column profile: `{ds_id}_{safe}_columns.csv`")
    r.table(prof, max_rows=40)

    from pyproj import Geod
    polys = alls.geom_type.str.contains("Polygon").all()
    if polys:
        geod = Geod(ellps="WGS84")
        alls["area_km2"] = [abs(geod.geometry_area_perimeter(g)[0]) / 1e6 for g in alls.geometry]
        r.p(f"Total area {alls['area_km2'].sum():,.0f} km2 (India incl. islands is about 3.29 million km2; "
            "state borders overlap slightly, so expect a little more).")
    key = re.compile(r"lith|rock|unit|group|form|strat|age|era|class|type|name|comm|mineral|domain|tecton|categ", re.I)
    shown = 0
    idlike = {"id", "gid", "__gid", "objectid", "fid"}
    cols = sorted(data.columns, key=lambda c: (not re.search(r"lith", c, re.I), not key.search(c)))
    for c in cols:
        if c == "_state" or c.lower() in idlike or data[c].dtype.kind in "if" or shown >= 8:
            continue
        k = data[c].nunique()
        if k == len(data) and k > 40:      # unique text per feature (names, ids): not a class
            continue
        if 2 <= k and (k <= 40 or (key.search(c) and (k <= 400 or re.search(r"lith", c, re.I)))):
            if polys:
                t = alls.groupby(alls[c].fillna("(blank)").astype(str))["area_km2"].agg(["count", "sum"])
                t = t.sort_values("sum", ascending=False).round(0).reset_index().rename(columns={"sum": "km2"})
            else:
                t = value_counts(alls, c, top=60)
            t.to_csv(OUT / f"{ds_id}_{safe}_classes_{re.sub(r'[^A-Za-z0-9]+', '_', c)[:30]}.csv", index=False)
            r.p(f"**Classes in `{c}`** ({k} distinct; full list in CSV):")
            r.table(t, max_rows=30)
            shown += 1

    # map
    fig, ax = india_axes(f"{ds_id} {layer}")
    col = next((c for c in data.columns if c != "_state" and data[c].dtype.kind not in "if"
                and 2 <= data[c].nunique() <= 20), None)
    big = len(alls) > 50000
    shown_geom = alls.set_geometry(alls.geometry.representative_point()) if big and polys else alls
    shown_geom.plot(ax=ax, column=col, categorical=bool(col), legend=bool(col), linewidth=0.3,
                    markersize=0.2 if big else 4,
                    legend_kwds={"fontsize": 6, "loc": "lower left"} if col else None)
    r.img(save(fig, f"{ds_id}_{safe}.png"), layer)


def ngdr_dropped():
    """Layer names marked status: dropped in configs/ngdr_layers.yaml."""
    cfg = ROOT / "configs" / "ngdr_layers.yaml"
    if not cfg.exists():
        return set()
    import yaml
    return {l["layer"] for l in yaml.safe_load(cfg.read_text(encoding="utf-8"))["layers"] if l.get("status") == "dropped"}


def audit_gsi(ds_id, folder, title, role, note=None):
    r = Report(ds_id, title, role)
    base = RAW / folder
    files = [p for p in base.rglob("*") if p.is_file() and not is_junk(p)
             and p.suffix.lower() in {".geojson", ".json", ".shp", ".gpkg", ".kml"}
             and not p.name.lower().endswith(".manifest.json")
             and "_pages" not in p.parts] if base.exists() else []
    if not files:
        r.issue("BLOCKER", f"No GeoJSON/shapefile found in data_raw/{folder}",
                "Export each chosen layer state by state into data_raw/<folder>/<layer>/<State>.geojson")
        return r
    by_layer = {}
    for f in sorted(files):
        layer = f.parent.name if f.parent != base else folder
        by_layer.setdefault(layer, []).append(f)
    dropped = ngdr_dropped()
    for layer in [l for l in by_layer if l in dropped]:
        r.issue("NOTE", f"{layer}: marked 'dropped' in configs/ngdr_layers.yaml - not audited", "Folder can be deleted")
        del by_layer[layer]
    r.p(f"{len(by_layer)} layer(s): {', '.join(by_layer)}.")
    for layer, fl in by_layer.items():
        print(f"    {layer}: {len(fl)} files")
        audit_gsi_layer(r, ds_id, layer, fl)
    terms = [p for p in base.rglob("*") if p.suffix.lower() in {".pdf", ".html", ".txt"} and "term" in p.name.lower()]
    if ds_id == "D15" and not terms:
        r.issue("BLOCKER", "NGDR terms of use not saved", "Save the terms page as PDF into data_raw/D15_gsi_geology2m/")
    if note:
        r.issue("NOTE", *note)
    return r


def audit_D15():
    return audit_gsi("D15", "D15_gsi_geology2m", "GSI Geology 1:2M (NGDR)",
                     "generation (rock types from Lithology_50K; Geology_2M fills unmapped sheets); reservoir/seal (sedimentary cover)")


def audit_D16():
    return audit_gsi("D16", "D16_gsi_tectonic", "GSI Tectonic map (NGDR)",
                     "generation (cratons, sutures, rifts); preservation; basin outlines")


def audit_D17():
    return audit_gsi("D17", "D17_gsi_seismotectonic", "GSI Seismotectonic atlas (NGDR)",
                     "context only: GSI active-fault study sites (national active faults come from FAULT_TECTONIC 'Neotectonic Fault')",
                     ("26 faults from individual GSI field studies, not a national inventory", "Context and validation only; not scored"))


def audit_D18():
    return audit_gsi("D18", "D18_gsi_mineral", "GSI Mineral occurrences (NGDR)",
                     "generation evidence: ultramafic indicators (chromite, Ni, PGE, magnesite, talc, asbestos); iron ore",
                     ("Occurrences reflect where GSI explored, not where minerals are absent", "Use as presence evidence only"))


def audit_D19():
    return audit_gsi("D19", "D19_gsi_geothermal", "GSI Geothermal / hot springs (NGDR)",
                     "evidence list (not a scoring layer)")


def audit_D20():
    return audit_gsi("D20", "D20_gsi_ground_geophysics", "GSI Ground geophysics (NGDR)",
                     "generation (dense mafic/ultramafic bodies): ground Bouguer anomaly; replaces WGM2012 over India where stations exist",
                     ("Station coverage is uneven", "Use WGM2012 only where no stations within ~10 km; flag those cells in the confidence map"))


def audit_D21():
    return audit_gsi("D21", "D21_gsi_boundary", "India state boundaries (NGDR)",
                     "India mask for clipping; state names for the shortlist")


AUDITS = {"D01": audit_D01, "D02": audit_D02, "D03": audit_D03, "D04": audit_D04, "D04b": audit_D04b, "D05": audit_D05,
          "D06": audit_D06, "D08a": audit_D08a, "D09": audit_D09, "D11a": audit_D11a, "D13": audit_D13,
          "D14": audit_D14, "D15": audit_D15, "D16": audit_D16, "D17": audit_D17, "D18": audit_D18,
          "D19": audit_D19, "D20": audit_D20, "D21": audit_D21}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="dataset ID, e.g. D01")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    all_issues, done = [], []
    for ds_id, fn in AUDITS.items():
        if args.only and ds_id != args.only:
            continue
        print(f"Auditing {ds_id} ...")
        try:
            rep = fn()
        except Exception as err:
            rep = Report(ds_id, "audit crashed", "")
            rep.p("```\n" + traceback.format_exc()[-1500:] + "\n```")
            rep.issue("BLOCKER", f"Audit script failed: {err}", "Send me this report")
        rep.write()
        all_issues += rep.issues
        done.append(ds_id)

    order = {"BLOCKER": 0, "PHASE3": 1, "NOTE": 2}
    iss = pd.DataFrame(all_issues)
    lines = [f"# Dataset audit summary - {date.today().isoformat()}", "",
             "Per-dataset reports: " + ", ".join(f"[{d}]({d}_audit.md)" for d in done), ""]
    if not iss.empty:
        iss["o"] = iss["level"].map(order)
        iss = iss.sort_values(["o", "dataset"]).drop(columns="o")
        counts = iss["level"].value_counts()
        lines.append(f"**{counts.get('BLOCKER', 0)} blockers, {counts.get('PHASE3', 0)} preprocessing items, "
                     f"{counts.get('NOTE', 0)} notes.**")
        lines += ["", iss.to_markdown(index=False)]
    if args.only and (OUT / "AUDIT_SUMMARY.md").exists():
        print(f"\nWrote metadata/audit/{args.only}_audit.md (summary not rebuilt for a single dataset)")
        return
    (OUT / "AUDIT_SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\nWrote metadata/audit/AUDIT_SUMMARY.md and one report per dataset.")


if __name__ == "__main__":
    main()
