# US layers - check

## Grid
225,052 H3 res-6 cells (centre on SGMC), 8,375,277 km2.

## Lithology
Polygons 313,732; QUAT->SH 60,788; flood basalt 327; melange 169.
Area by main class in the grid (km2):

|        |              km2 |
|:-------|-----------------:|
| SH     |      2.3759e+06  |
| SST    |      1.79187e+06 |
| QUAT   |      1.13908e+06 |
| CARB   | 869302           |
| NODATA | 618836           |
| GRAN   | 418836           |
| MAF_V  | 383251           |
| MSED   | 276806           |
| VOLC   | 236654           |
| GNS    | 199407           |
| MAF_I  |  20983           |
| MAF_D  |  16039           |
| UM     |   8939           |
| EVAP   |   5931           |
| BIF    |   1344           |

Cells with ultramafic rock: 5,073 (as main rock 1,899).
MAJOR1 terms with no class (fallback to GENERALIZED_LITH), by polygons: 30 terms

|                            |   polygons |
|:---------------------------|-----------:|
| Sedimentary                |       2763 |
| Mixed-clastic              |        965 |
| Metasiltstone              |        689 |
| Latite                     |        381 |
| Granofels                  |        316 |
| Novaculite                 |        231 |
| Felsic-hypabyssal          |        213 |
| Banded-iron-formation      |        201 |
| Metaandesite               |        132 |
| Metadacite                 |        103 |
| Metamorphic                |         85 |
| Hypabyssal-felsic-alkaline |         79 |
| Metaclastic                |         76 |
| Metadiabase                |         66 |
| Hypabyssal                 |         66 |
| Quartz-latite              |         61 |
| Metadiorite                |         57 |
| Cataclasite                |         51 |
| Basanite                   |         48 |
| Metaigneous                |         41 |
| Metaanorthosite            |         37 |
| Metatrondhjemite           |         35 |
| Metatonalite               |         28 |
| Metaintrusive              |         22 |
| Quartz-monzodiorite        |         19 |
| Monzodiorite               |         18 |
| Hypabyssal-latite          |         12 |
| Alaskite                   |          7 |
| Phyllonite                 |          6 |
| Coquina                    |          2 |

## Structures
SGMC fault lines 291,152 (touching basement: 82,787); thrusts 30,224; shear zones 1,240; Quaternary faults used 108,135.
Provinces in the US box: Accretionary Complex, Basin, Craton, Magmatic Province, Narrow Rift, Oceanic Back-Arc Basin, Oceanic Crust, Ophiolite Complex, Orogenic Belt, Passive Margin, Shield, Volcanic Arc, Wide Rift.
|                  |   count |   mean |    50% |     max |
|:-----------------|--------:|-------:|-------:|--------:|
| d_fault_basement |  225052 | 135.17 |  76.35 |  967.06 |
| d_fault_any      |  225052 |  56.65 |  15.38 |  904.48 |
| d_neotectonic    |  225052 | 677.45 | 430.61 | 2896.17 |
| d_thrust         |  225052 | 157.01 | 109.53 |  973.28 |
| d_shear          |  225052 | 577.56 | 558.5  | 1441.87 |
| d_suture         |       0 | nan    | nan    |  nan    |
| d_um_rock        |  225052 | 209.62 | 169.05 |  968    |
| tf_ophiolite     |  225052 |   0    |   0    |    1    |
| tf_greenstone    |  225052 |   0    |   0    |    0    |
| tf_rift          |  225052 |   0.16 |   0    |    1    |
| tf_accretion     |  225052 |   0.09 |   0    |    1    |
| n_um_strong      |       0 | nan    | nan    |  nan    |
| n_um_moderate    |       0 | nan    | nan    |  nan    |
| d_um_strong      |       0 | nan    | nan    |  nan    |
| d_spring         |       0 | nan    | nan    |  nan    |
| spring_tmax_25km |       0 | nan    | nan    |  nan    |

## Gravity
WGM2012 residual for 225,052 cells; residual p10/p50/p90: -11.9 / -0.1 / 12.2 mGal.

## Depth and heat flow
CRUST1.0 file sedthk-m.xyz.zip (m); cells with thickness 225,052; median 1,100 m.
Heat-flow sites (US, onshore) 18,557; cells with a site within 50 km 157,178.

