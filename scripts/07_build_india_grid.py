"""
07_build_india_grid.py  -  Phase 3, step 1: the India grid

Builds the H3 resolution-6 grid (hexagons of ~36 km2) over India, using the GSI state
boundaries (D21) as the India mask. Coastal and island cells are kept if any land falls in them.

Writes layers/india_h3r6.gpkg, table "grid":
  h3        cell id
  lon, lat  cell centre
  area_km2  cell area
  land_frac share of the cell inside India (coastal / border cells < 1)
  state     state/UT with the largest share of the cell
Run:  python scripts/07_build_india_grid.py      (a few minutes)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h2pros.grid import CRS_AREA, RES, raw, read_clean, write_layer   # noqa: E402


def main():
    import geopandas as gpd
    import h3
    import shapely
    print("India mask (D21) ...")
    st = read_clean(raw("D21_gsi_boundary", "STATE_BOUNDARY"), label="STATE_BOUNDARY")
    name = "stname" if "stname" in st.columns else next(c for c in st.columns if "name" in c.lower())
    st = st[[name, "geometry"]].rename(columns={name: "state"})
    india = shapely.union_all(st.geometry.values)

    print(f"H3 cells at resolution {RES} ...")
    # simplify + buffer ~5 km only to FIND candidate cells (catches small islands and the coast)
    search = india.simplify(0.005).buffer(0.05)
    cells = set()
    for part in getattr(search, "geoms", [search]):
        cells |= set(h3.h3shape_to_cells(h3.geo_to_h3shape(part), RES))
    cells = sorted(cells)
    hexes = gpd.GeoDataFrame({"h3": cells},
                             geometry=[shapely.Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in cells],
                             crs=4326)
    print(f"    {len(hexes):,} candidate cells")

    print("land share and state per cell ...")
    hx_a = hexes.to_crs(CRS_AREA)
    st_a = st.to_crs(CRS_AREA)
    tree = shapely.STRtree(st_a.geometry.values)
    ih, ist = tree.query(hx_a.geometry.values, predicate="intersects")
    inter = shapely.area(shapely.intersection(hx_a.geometry.values[ih], st_a.geometry.values[ist])) / 1e6
    pairs = pd.DataFrame({"hex": ih, "state": st["state"].values[ist], "km2": inter})
    pairs = pairs[pairs["km2"] > 0]
    land = pairs.groupby("hex")["km2"].sum()
    top = pairs.sort_values("km2").groupby("hex").tail(1).set_index("hex")["state"]
    hexes["area_km2"] = shapely.area(hx_a.geometry.values) / 1e6
    hexes["land_frac"] = (land.reindex(range(len(hexes))).fillna(0).values / hexes["area_km2"]).clip(0, 1)
    hexes["state"] = top.reindex(range(len(hexes))).values
    hexes = hexes[hexes["land_frac"] > 0].reset_index(drop=True)
    ll = [h3.cell_to_latlng(c) for c in hexes["h3"]]
    hexes.insert(1, "lon", [round(x[1], 5) for x in ll])
    hexes.insert(2, "lat", [round(x[0], 5) for x in ll])
    hexes = hexes[["h3", "lon", "lat", "area_km2", "land_frac", "state", "geometry"]]

    land_km2 = (hexes["area_km2"] * hexes["land_frac"]).sum()
    print(f"    {len(hexes):,} cells; land inside cells {land_km2:,.0f} km2 "
          f"(mask area {shapely.area(shapely.union_all(st_a.geometry.values)) / 1e6:,.0f} km2)")
    print(f"    cells per state: min {hexes.groupby('state').size().min()}, "
          f"states/UTs with cells: {hexes['state'].nunique()} of {st['state'].nunique()}")
    write_layer(hexes, "grid")


if __name__ == "__main__":
    main()
