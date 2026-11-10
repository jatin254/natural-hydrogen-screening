# Raw data inventory - 2026-11-01

## D01_epri
- `data_raw/D01_epri/occurrence.csv` (0.3 MB) - table | count: 341 | notes: comma-delimited, utf-8, header on line 1; 1,189 physical lines (quoted text may span lines); coords: 0 missing, 0 out of range, 3 exact duplicates
- `data_raw/D01_epri/project.csv` (0.0 MB) - table | count: 23 | notes: comma-delimited, utf-8, header on line 1; 31 physical lines (quoted text may span lines); coords: 0 missing, 0 out of range, 1 exact duplicates

## D02_glim
- `data_raw/D02_glim/LiMW_GIS.gdb` (1257.8 MB) - vector | layer: GLiM_export | count: 1235259 | crs: PROJCS["World_Eckert_IV",GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0],UNIT["Degree",0.0174532925199433]],PROJECTION["Eckert_IV"],PARAMETER["central_meridian",0],PARAMETER["false_easting",0],PARAMETER["false_northing",0],UNIT["metre",1,AUTHORITY["EPSG","9001"]],AXIS["Easting",EAST],AXIS["Northing",NORTH],AUTHORITY["ESRI","54012"]]

## D03_gem_faults
- `data_raw/D03_gem_faults/gem_fault.geojson` (12.3 MB) - vector | layer: gem_fault | count: 16195 | crs: EPSG:4979

## D04_wdmam
- `data_raw/D04_wdmam/wdmam.nc` (56.5 MB) - raster | count: 7201 x 3601 cells, 1 band(s) | crs: MISSING - lon/lat with longitudes 0-360; assign EPSG:4326 and shift to -180..180 in Phase 3 | resolution: 0.05000 x 0.05000 deg | notes: node-registered (cells centred on +/-180, +/-90)

## D05_wgm2012
- `data_raw/D05_wgm2012/WGM2012.grd` (233.4 MB) - raster | count: 10801 x 5401 cells, 1 band(s) | crs: MISSING - values fit lon/lat; assign EPSG:4326 in Phase 3 | resolution: 0.03333 x 0.03333 deg | notes: node-registered (cells centred on +/-180, +/-90)

## D06_ihfc
- `data_raw/D06_ihfc/GHFDB-R2024_v.2026-03/GHFBD-R2024_v.2026.03_data_description.pdf.pdf` (2.5 MB) - other (checksum only)
- `data_raw/D06_ihfc/GHFDB-R2024_v.2026-03/IHFC_2024_GHFDB_v.2026.03.txt` (39.2 MB) - table | count: 91187 | notes: tab-delimited, latin-1, header on line 8; 91,200 physical lines (quoted text may span lines)
- `data_raw/D06_ihfc/GHFDB-R2024_v.2026-03/IHFC_2024_GHFDB_v.2026.03.xlsx` (14.6 MB) - table | layer: sheet: Metadata | count: 6
- `data_raw/D06_ihfc/GHFDB-R2024_v.2026-03/IHFC_2024_GHFDB_v.2026.03.xlsx` (14.6 MB) - table | layer: sheet: GHFDB R20024 v.2026.03 | count: 91187

## D08a_crust1
- `data_raw/D08a_crust1/crsthk.xyz.zip` (0.3 MB) - other (checksum only)
- `data_raw/D08a_crust1/crust1.0.tar.gz` (1.2 MB) - other (checksum only)
- `data_raw/D08a_crust1/crust1.bnds` (4.1 MB) - other (checksum only)
- `data_raw/D08a_crust1/crust1.rho` (3.6 MB) - other (checksum only)
- `data_raw/D08a_crust1/crust1.vp` (3.6 MB) - other (checksum only)
- `data_raw/D08a_crust1/crust1.vs` (3.6 MB) - other (checksum only)
- `data_raw/D08a_crust1/getCN1maps.f` (0.0 MB) - other (checksum only)
- `data_raw/D08a_crust1/getCN1point.f` (0.0 MB) - other (checksum only)
- `data_raw/D08a_crust1/getCN1xyz.f` (0.0 MB) - other (checksum only)
- `data_raw/D08a_crust1/readme` (0.0 MB) - other (checksum only)
- `data_raw/D08a_crust1/sedthk-m.xyz.zip` (0.2 MB) - other (checksum only)

## D09_hasterok
- `data_raw/D09_hasterok/global_tectonics.zip` (1172.4 MB) - other (checksum only)
- `data_raw/D09_hasterok/GPS/GPS_APM.shp` (0.6 MB) - vector | layer: GPS_APM | count: 22511 | crs: EPSG:4326
- `data_raw/D09_hasterok/GPS/GPS_ITRF08.shp` (0.6 MB) - vector | layer: GPS_ITRF08 | count: 22511 | crs: EPSG:4326
- `data_raw/D09_hasterok/GPS/GPS_NNR.shp` (0.6 MB) - vector | layer: GPS_NNR | count: 22511 | crs: EPSG:4326
- `data_raw/D09_hasterok/plates&provinces/boundaries.gmt` (0.4 MB) - other (checksum only)
- `data_raw/D09_hasterok/plates&provinces/boundaries.kml` (0.7 MB) - vector | layer: boundaries | count: 571 | crs: EPSG:4326
- `data_raw/D09_hasterok/plates&provinces/boundaries.shp` (0.2 MB) - vector | layer: boundaries | count: 571 | crs: EPSG:4326
- `data_raw/D09_hasterok/plates&provinces/cratons.shp` (0.2 MB) - vector | layer: cratons | count: 114 | crs: EPSG:4326
- `data_raw/D09_hasterok/plates&provinces/global_gprv.gmt` (4.5 MB) - other (checksum only)
- `data_raw/D09_hasterok/plates&provinces/global_gprv.kml` (8.0 MB) - vector | layer: global_gprv | count: 921 | crs: EPSG:4326
- `data_raw/D09_hasterok/plates&provinces/global_gprv.shp` (2.2 MB) - vector | layer: global_gprv | count: 921 | crs: EPSG:4326
- `data_raw/D09_hasterok/plates&provinces/oc_boundaries.gmt` (0.4 MB) - other (checksum only)
- `data_raw/D09_hasterok/plates&provinces/oc_boundaries.kml` (0.4 MB) - vector | layer: oc_boundaries | count: 93 | crs: EPSG:4326
- `data_raw/D09_hasterok/plates&provinces/oc_boundaries.shp` (0.2 MB) - vector | layer: oc_boundaries | count: 93 | crs: EPSG:4326
- `data_raw/D09_hasterok/plates&provinces/plates.gmt` (1.3 MB) - other (checksum only)
- `data_raw/D09_hasterok/plates&provinces/plates.kml` (1.5 MB) - vector | layer: plates | count: 280 | crs: EPSG:4326
- `data_raw/D09_hasterok/plates&provinces/plates.shp` (0.7 MB) - vector | layer: plates | count: 280 | crs: EPSG:4326
- `data_raw/D09_hasterok/point_data/global_eq_M3-5.5_1990-2020.shp` (10.9 MB) - vector | layer: global_eq_M3-5.5_1990-2020 | count: 247072 | crs: EPSG:4326
- `data_raw/D09_hasterok/point_data/global_eq_M5.5+_1970-2020.shp` (0.4 MB) - vector | layer: global_eq_M5.5+_1970-2020 | count: 10053 | crs: EPSG:4326
- `data_raw/D09_hasterok/point_data/GVP_Holocene+Pleistocene.shp` (0.1 MB) - vector | layer: GVP_Holocene+Pleistocene | count: 2672 | crs: EPSG:4326
- `data_raw/D09_hasterok/point_data/igneous_dates.shp` (12.7 MB) - vector | layer: igneous_dates | count: 455696 | crs: EPSG:4326
- `data_raw/D09_hasterok/point_data/metamorphic_dates.shp` (0.0 MB) - vector | layer: metamorphic_dates | count: 1708 | crs: EPSG:4326
- `data_raw/D09_hasterok/point_data/n.shpcedc_3.0_1980_2015.shp` (21.8 MB) - vector | layer: n.shpcedc_3.0_1980_2015 | count: 496116 | crs: EPSG:4326
- `data_raw/D09_hasterok/polygon_data/GSHHS_I_L1.shp` (1.8 MB) - vector | layer: GSHHS_I_L1 | count: 6042 | crs: EPSG:4326
- `data_raw/D09_hasterok/polygon_data/Johansson_etal_2018_EarthByte_LIPs_v2.shp` (2.0 MB) - vector | layer: Johansson_etal_2018_EarthByte_LIPs_v2 | count: 2526 | crs: EPSG:4326
- `data_raw/D09_hasterok/polygon_data/ne_10m_coastline.shp` (6.8 MB) - vector | layer: ne_10m_coastline | count: 4083 | crs: EPSG:4326
- `data_raw/D09_hasterok/polygon_data/ne_10m_wgs84_bounding_box.README.html` (0.0 MB) - other (checksum only)
- `data_raw/D09_hasterok/polygon_data/ne_10m_wgs84_bounding_box.shp` (0.0 MB) - vector | layer: ne_10m_wgs84_bounding_box | count: 1 | crs: EPSG:4326
- `data_raw/D09_hasterok/polygon_data/ne_10m_wgs84_bounding_box.VERSION.txt` (0.0 MB) - text document
- `data_raw/D09_hasterok/QGIS/global_tectonics.qgz` (0.1 MB) - other (checksum only)
- `data_raw/D09_hasterok/raster_data/3D218-08Sv_70km.tif` (3.0 MB) - raster | count: 180 x 90 cells, 46 band(s) | crs: EPSG:4326 | resolution: 2.00000 x 2.00000 deg | notes: cell-registered
- `data_raw/D09_hasterok/raster_data/ETOPO1.tif` (933.3 MB) - raster | count: 21601 x 10801 cells, 1 band(s) | crs: EPSG:4326 | resolution: 0.01667 x 0.01667 deg | notes: node-registered (cells centred on +/-180, +/-90)
- `data_raw/D09_hasterok/raster_data/GGM+2013.tif` (233.4 MB) - raster | count: 10801 x 5401 cells, 1 band(s) | crs: EPSG:4326 | resolution: 0.03333 x 0.03333 deg | notes: node-registered (cells centred on +/-180, +/-90)
- `data_raw/D09_hasterok/raster_data/Seafloor_age.2020.1.GTS2012.1min.tif` (933.4 MB) - raster | count: 21601 x 10801 cells, 1 band(s) | crs: EPSG:4326 | resolution: 0.01667 x 0.01667 deg | notes: node-registered (cells centred on +/-180, +/-90)
- `data_raw/D09_hasterok/raster_data/WDMAM_V2.tif` (103.7 MB) - raster | count: 7200 x 3601 cells, 1 band(s) | crs: EPSG:4326 | resolution: 0.05000 x 0.05000 deg | notes: cell-registered
- `data_raw/D09_hasterok/readme.txt` (0.0 MB) - text document
- plus 99 companion files (.dbf, .shx, .prj, styles ...) - fingerprinted, not listed

## D13_etopo
- `data_raw/D13_etopo/ETOPO_2022_v1_60s_N90W180_bed.tif` (478.4 MB) - raster | count: 21600 x 10800 cells, 1 band(s) | crs: EPSG:9518 (WGS84 + EGM2008 heights; horizontally = EPSG:4326) | resolution: 0.01667 x 0.01667 deg | notes: cell-registered

## D14_usgs_gas
- `data_raw/D14_usgs_gas/Natural Gas Dataset.csv` (4.1 MB) - table | count: 21254 | notes: comma-delimited, utf-8, header on line 1; 21,255 physical lines (quoted text may span lines); coords: 967 missing, 0 out of range, 3275 exact duplicates

## Warnings
- data_raw/D03_gem_faults/gem_fault.geojson: CRS is EPSG:4979 (WGS84 3D) - horizontally identical to EPSG:4326, fine
- data_raw/D04_wdmam/wdmam.nc: no CRS stored in the file (lon/lat with longitudes 0-360; assign EPSG:4326 and shift to -180..180 in Phase 3)
- data_raw/D05_wgm2012/WGM2012.grd: no CRS stored in the file (values fit lon/lat; assign EPSG:4326 in Phase 3)
- D08a_crust1: 7 system junk files ignored (__MACOSX, ._*, .DS_Store) - safe to delete
- D09_hasterok: 1 system junk files ignored (__MACOSX, ._*, .DS_Store) - safe to delete
- D11a_ophiolites: folder is empty
