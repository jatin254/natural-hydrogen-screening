"""Shared helpers for Phase 3: the India H3 grid and polygon/line/point overlays.

CRS choices (decisions_log 2026-11-01, Phase 3):
  EPSG:4326  storage (lon/lat)
  EPSG:6933  areas (equal-area)
  EPSG:7755  distances (WGS 84 / India NSF LCC; distance error ~1-2% across India)
"""
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

import os

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data_raw"
LAYERS = ROOT / "layers"
RES = 6
# Region: India by default; the US validation sets H2_REGION=us (scripts 15-17 and `12_score.py --region us`)
REGION = os.environ.get("H2_REGION", "india").lower()
if REGION == "us":
    GPKG = LAYERS / "us_h3r6.gpkg"
    CRS_AREA = CRS_DIST = "EPSG:5070"      # NAD83 / Conus Albers (equal-area; distance error < ~1.5%)
elif REGION == "global":
    RES = 5
    GPKG = LAYERS / "global_h3r5.gpkg"
    CRS_AREA, CRS_DIST = "EPSG:6933", None   # no projection keeps distances worldwide: use sphere_pairs()
else:
    GPKG = LAYERS / "india_h3r6.gpkg"      # one file, one table per theme (open in QGIS)
    CRS_AREA, CRS_DIST = "EPSG:6933", "EPSG:7755"


def raw(folder, layer):
    return RAW / folder / layer / "All_India.geojson"


def read_clean(path, columns=None, label=None):
    """Read a downloaded layer: drop empty geometries and exact duplicates, repair invalid ones."""
    import geopandas as gpd
    import pyogrio
    import shapely
    g = pyogrio.read_dataframe(path, columns=columns)
    if g.crs is None:
        g = g.set_crs(4326)
    n0 = len(g)
    g = g[g.geometry.notna() & ~g.geometry.is_empty].copy()
    attrs = [c for c in g.columns if c != "geometry" and c.lower() not in {"id", "gid", "objectid", "__gid", "fid"}]
    h = []
    geoms = g.geometry.values
    for i in range(0, len(geoms), 20000):
        h += [hashlib.blake2b(w, digest_size=12).digest() for w in shapely.to_wkb(geoms[i:i + 20000])]
    key = pd.concat([pd.Series(h, index=g.index, name="_h"), g[attrs].astype(str)], axis=1)
    g = g[~key.duplicated()].copy()
    bad = ~shapely.is_valid(g.geometry.values)
    if bad.any():
        fixed = shapely.make_valid(g.geometry.values[bad])
        # keep only the polygon / line parts that match the layer's geometry family
        g.loc[bad, "geometry"] = [_keep_family(x, g.geometry.values[~bad][0] if (~bad).any() else x) for x in fixed]
    g = gpd.GeoDataFrame(g, geometry="geometry", crs=g.crs).to_crs(4326)
    print(f"    {label or Path(path).parent.name}: {n0:,} read, {len(g):,} kept, {int(bad.sum())} repaired")
    return g


def _keep_family(geom, like):
    import shapely
    fam = "Polygon" if "Polygon" in like.geom_type else ("LineString" if "Line" in like.geom_type else "Point")
    if fam in geom.geom_type:
        return geom
    parts = [p for p in getattr(geom, "geoms", [geom]) if fam in p.geom_type]
    return shapely.union_all(parts) if parts else geom


def load_grid():
    import pyogrio
    if not GPKG.exists():
        raise SystemExit("Grid not found: run python scripts/07_build_india_grid.py first")
    return pyogrio.read_dataframe(GPKG, layer="grid")


def subdivide(geoms, max_vertices=256):
    """Cut polygons into pieces of at most ~max_vertices vertices (like PostGIS ST_Subdivide).
    Areas are unchanged. Returns (pieces, index of the original polygon for each piece).
    Big detailed polygons otherwise make every polygon x hexagon intersection slow."""
    import shapely
    geoms = np.asarray(geoms, dtype=object)
    owner = np.arange(len(geoms))
    done_g, done_o = [], []
    while len(geoms):
        n = shapely.get_num_coordinates(geoms)
        small = n <= max_vertices
        done_g.append(geoms[small]); done_o.append(owner[small])
        geoms, owner = geoms[~small], owner[~small]
        if not len(geoms):
            break
        b = shapely.bounds(geoms)
        wide = (b[:, 2] - b[:, 0]) >= (b[:, 3] - b[:, 1])
        mx = np.where(wide, (b[:, 0] + b[:, 2]) / 2, b[:, 2])
        my = np.where(wide, b[:, 3], (b[:, 1] + b[:, 3]) / 2)
        hx0, hy0 = np.where(wide, mx, b[:, 0]), np.where(wide, b[:, 1], my)
        lo = np.array([shapely.clip_by_rect(g, b[k, 0], b[k, 1], mx[k], my[k]) for k, g in enumerate(geoms)], dtype=object)
        hi = np.array([shapely.clip_by_rect(g, hx0[k], hy0[k], b[k, 2], b[k, 3]) for k, g in enumerate(geoms)], dtype=object)
        geoms = np.concatenate([lo, hi]); owner = np.concatenate([owner, owner])
        keep = ~shapely.is_empty(geoms) & (shapely.area(geoms) > 0)
        geoms, owner = geoms[keep], owner[keep]
    pieces, own = np.concatenate(done_g), np.concatenate(done_o)
    # reprojection and cutting can leave a few slightly self-crossing pieces: repair them
    bad = ~shapely.is_valid(pieces)
    if bad.any():
        pieces[bad] = [polygons_only(g) for g in shapely.make_valid(pieces[bad])]
        print(f"      repaired {int(bad.sum()):,} invalid pieces", flush=True)
    keep = ~shapely.is_empty(pieces)
    return pieces[keep], own[keep]


def polygons_only(g):
    """Polygon parts of a geometry (make_valid can return lines/points alongside polygons)."""
    import shapely
    if g is None or g.is_empty:
        return shapely.Polygon()
    if g.geom_type in ("Polygon", "MultiPolygon"):
        return g
    parts = [p for p in shapely.get_parts(g) if p.geom_type in ("Polygon", "MultiPolygon")]
    return shapely.union_all(parts) if parts else shapely.Polygon()


def _safe_intersection_area(a, b):
    """Intersection areas; if GEOS fails on a bad pair, repair and retry one pair at a time,
    finally with snap-rounding on a 1 cm grid (robust; area change negligible)."""
    import shapely
    try:
        return shapely.area(shapely.intersection(a, b))
    except shapely.errors.GEOSException:
        pass
    out = np.empty(len(a))
    for k in range(len(a)):
        try:
            out[k] = shapely.area(shapely.intersection(a[k], b[k]))
        except shapely.errors.GEOSException:
            try:
                out[k] = shapely.area(shapely.intersection(polygons_only(shapely.make_valid(a[k])), b[k], grid_size=0.01))
            except shapely.errors.GEOSException:
                out[k] = 0.0
                print(f"\n      WARNING: could not intersect one piece (area {shapely.area(a[k]) / 1e6:.3f} km2); counted as 0", flush=True)
    return out


def area_matrix(hexes_area, polys_area, codes, n_codes, chunk=50000, minor=None, max_vertices=256):
    """Area (km2) of each polygon class inside each hexagon.

    hexes_area, polys_area: GeoSeries in an equal-area CRS (same CRS).
    codes: int array (one class index per polygon). minor: optional bool matrix
    (polygons x flags) - area is also added to each flagged column.
    Returns (n_hex x n_codes) matrix and, if minor given, (n_hex x n_flags) matrix.
    """
    import time
    import shapely
    hx = hexes_area.values
    tree = shapely.STRtree(hx)
    out = np.zeros((len(hx), n_codes))
    out_m = np.zeros((len(hx), minor.shape[1])) if minor is not None else None
    t0 = time.time()
    pv, owner = subdivide(polys_area.values, max_vertices)
    print(f"      {len(polys_area):,} polygons cut into {len(pv):,} pieces ({time.time() - t0:.0f} s)")
    codes = np.asarray(codes)[owner]
    if minor is not None:
        minor = np.asarray(minor)[owner]
    t0 = time.time()
    for i in range(0, len(pv), chunk):
        part = pv[i:i + chunk]
        ip, ih = tree.query(part, predicate="intersects")
        a, b = part[ip], hx[ih]
        area = np.empty(len(ip))
        within = shapely.within(a, b)            # piece fully inside one hexagon
        covers = ~within & shapely.within(b, a)  # hexagon fully inside a piece
        rest = ~within & ~covers
        area[within] = shapely.area(a[within])
        area[covers] = shapely.area(b[covers])
        if rest.any():
            area[rest] = _safe_intersection_area(a[rest], b[rest])
        area /= 1e6
        np.add.at(out, (ih, codes[i + ip]), area)
        if minor is not None:
            m = minor[i + ip]
            for k in range(m.shape[1]):
                sel = m[:, k]
                np.add.at(out_m[:, k], ih[sel], area[sel])
        done = min(i + chunk, len(pv))
        el = time.time() - t0
        print(f"      {done:,} / {len(pv):,} pieces, {el / 60:.1f} min, about {el / done * (len(pv) - done) / 60:.0f} min left",
              end="\r", flush=True)
    print()
    return (out, out_m) if minor is not None else out


def write_layer(gdf, layer):
    import pyogrio
    LAYERS.mkdir(exist_ok=True)
    pyogrio.write_dataframe(gdf, GPKG, layer=layer, driver="GPKG")
    print(f"    wrote {GPKG.relative_to(ROOT)} : {layer} ({len(gdf):,} cells, {gdf.shape[1] - 1} columns)")


# ------------------------------------------------------------------ great-circle helpers (global region)
R_EARTH_KM = 6371.0088


def unit_xyz(lon, lat):
    """Lon/lat (degrees) -> unit vectors on the sphere."""
    lo, la = np.radians(np.asarray(lon, float)), np.radians(np.asarray(lat, float))
    return np.column_stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])


def chord_to_km(c):
    return 2 * R_EARTH_KM * np.arcsin(np.clip(np.asarray(c) / 2, 0, 1))


def km_to_chord(km):
    return 2 * np.sin(np.asarray(km) / (2 * R_EARTH_KM))


def sphere_pairs(lon, lat, km):
    """All pairs (i, j) of points within `km` great-circle distance, with distances in km (includes i == j)."""
    from scipy.spatial import cKDTree
    xyz = unit_xyz(lon, lat)
    t = cKDTree(xyz)
    pairs = t.query_pairs(float(km_to_chord(km)), output_type="ndarray")
    n = len(xyz)
    i = np.concatenate([pairs[:, 0], pairs[:, 1], np.arange(n)])
    j = np.concatenate([pairs[:, 1], pairs[:, 0], np.arange(n)])
    d = chord_to_km(np.linalg.norm(xyz[i] - xyz[j], axis=1))
    return i.astype(np.int64), j.astype(np.int64), d


def sphere_nearest_km(lon, lat, src_lon, src_lat, max_km=None):
    """Great-circle distance (km) from each point to the nearest source point (NaN if none / beyond max_km)."""
    from scipy.spatial import cKDTree
    if len(src_lon) == 0:
        return np.full(len(lon), np.nan)
    t = cKDTree(unit_xyz(src_lon, src_lat))
    c, _ = t.query(unit_xyz(lon, lat), distance_upper_bound=float(km_to_chord(max_km)) if max_km else np.inf)
    out = chord_to_km(np.where(np.isinf(c), np.nan, c))
    return out


def densify_lines(geoms, step_km=2.0):
    """Points every ~step_km along lon/lat line geometries (returns lon, lat, index of the source line)."""
    import shapely
    lon, lat, owner = [], [], []
    for k, g in enumerate(geoms):
        if g is None or g.is_empty:
            continue
        parts = getattr(g, "geoms", [g])
        for p in parts:
            xy = np.asarray(p.coords)[:, :2]
            if len(xy) < 2:
                continue
            dxy = np.diff(xy, axis=0)
            seg = np.hypot(dxy[:, 0] * np.cos(np.radians(xy[:-1, 1])), dxy[:, 1]) * 111.2
            for a, b, s in zip(xy[:-1], xy[1:], seg):
                n = max(1, int(np.ceil(s / step_km)))
                t = np.linspace(0, 1, n, endpoint=False)
                lon.append(a[0] + (b[0] - a[0]) * t)
                lat.append(a[1] + (b[1] - a[1]) * t)
                owner.append(np.full(n, k))
            lon.append(xy[-1:, 0]); lat.append(xy[-1:, 1]); owner.append(np.array([k]))
    if not lon:
        return np.array([]), np.array([]), np.array([], int)
    return np.concatenate(lon), np.concatenate(lat), np.concatenate(owner)
