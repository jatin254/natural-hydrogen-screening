## Location check of uncertain GLiM codes (12 largest polygons each)
'fe' polygons within 300 km of a known iron-formation district: 5 of 12 -> iron-formation flag USED (rule: >= 3).

| code                 | litho   |     km2 |    lon |   lat | nearest_district                    |     km |
|:---------------------|:--------|--------:|-------:|------:|:------------------------------------|-------:|
| fe (iron formation?) | scshfe  | 15374.9 |   24   | -28.1 | Transvaal (Sishen-Thabazimbi)       |  119   |
| fe (iron formation?) | mtamfe  | 11218.6 |   33.9 |  65.8 | Kostomuksha                         |  205   |
| fe (iron formation?) | mt__fe  |  9819.9 |  -59.1 | -10.7 | Carajas                             | 1081.2 |
| fe (iron formation?) | vbpyfe  |  6608.2 |  -92.7 |  49.5 | Lake Superior (Mesabi-Marquette)    |  337.5 |
| fe (iron formation?) | mt__fe  |  6400.9 |  -60.7 | -10.8 | Carajas                             | 1245.6 |
| fe (iron formation?) | mtamfe  |  5513.9 |  -38.2 |  -7.5 | Carajas                             | 1364.6 |
| fe (iron formation?) | mtamfe  |  5145.7 |  -42.2 | -17   | Minas Gerais Quadrilatero Ferrifero |  378.7 |
| fe (iron formation?) | mtamfe  |  4250.1 |   30.1 |  67.5 | Kostomuksha                         |  325.8 |
| fe (iron formation?) | mtamfe  |  3631.3 |   31.4 |  67.5 | Kostomuksha                         |  328.1 |
| fe (iron formation?) | mtamfe  |  3618   |   31.1 |  66.6 | Kostomuksha                         |  220.7 |
| fe (iron formation?) | mtamfe  |  3564.7 |   30.6 |  66.9 | Kostomuksha                         |  260.2 |
| fe (iron formation?) | mt__fe  |  3544.7 |  116.4 | -22.1 | Hamersley                           |  171   |
| gr (greenstone)      | mtgr__  | 27226.3 |  -59.4 |   6.4 | Carajas                             | 1696.5 |
| gr (greenstone)      | mtgr__  |  7806.1 |  -57.2 |   2.8 | Carajas                             | 1224.3 |
| gr (greenstone)      | mtgr__  |  7189.7 |   35.3 |  67.3 | Kostomuksha                         |  367.4 |
| gr (greenstone)      | mtgr__  |  6337.4 |  -54.5 |   4.6 | Carajas                             | 1259.2 |
| gr (greenstone)      | mtgr__  |  5990.2 |   38.2 |  67.4 | Kostomuksha                         |  464.9 |
| gr (greenstone)      | mtgr__  |  4601.5 |   81.9 |  24.3 | Singhbhum-Odisha                    |  447.9 |
| gr (greenstone)      | mtgr__  |  3935.2 |   36.4 |  66.8 | Kostomuksha                         |  356.6 |
| gr (greenstone)      | mtgr__  |  3868.2 |   30.9 |  68.7 | Kostomuksha                         |  453.8 |
| gr (greenstone)      | mtgr__  |  3025.9 |   34   |  61.4 | Kostomuksha                         |  396.1 |
| gr (greenstone)      | mtgr__  |  2837.6 | -124.6 |  56.8 | Lake Superior (Mesabi-Marquette)    | 2578.9 |
| gr (greenstone)      | mtgr__  |  2633.1 |   97.9 |   3.8 | Singhbhum-Odisha                    | 2424.5 |
| gr (greenstone)      | mtgr__  |  2128.6 |  -61.3 |   7   | Carajas                             | 1876.2 |

## Raster
GLiM 1,235,259 polygons, 437 codes, raster 16654 x 8419 at 2000 m (153 tiles).

## Grid and lithology
588,472 land cells (res 5); scored-geology cells 539,303; iron-formation flag USED.
Area by class (km2):

|         |              km2 |
|:--------|-----------------:|
| f_QUAT  |      3.70098e+07 |
| f_SH    |      2.57311e+07 |
| f_SST   |      2.10446e+07 |
| f_GNS   |      1.69725e+07 |
| f_CARB  |      1.12465e+07 |
| f_GRAN  |      9.38379e+06 |
| f_MAF_V |      7.96091e+06 |
| f_VOLC  |      5.26132e+06 |
| f_MAF_I |      1.0941e+06  |
| f_EVAP  | 435248           |
| f_MSED  | 332936           |
| f_MAF_D | 148275           |

Cells with greenstone share > 0: 2,750; ophiolite share > 0: 4,739; flood basalt (MAF_D) > 0: 1,592.

## Structures
GEM: 16,195 faults -> 501,821 points (thrust/reverse 195,044; in hard-rock cells 66,155). Province boundary points shared by two continental provinces: 1,179,808.
|                  |   count |    mean |     50% |     max |
|:-----------------|--------:|--------:|--------:|--------:|
| d_fault_any      |  588472 |  706.76 |  465.4  | 3249.73 |
| d_neotectonic    |  588472 |  706.76 |  465.4  | 3249.73 |
| d_thrust         |  588472 | 1176.4  |  872.53 | 4144.46 |
| d_fault_basement |  588472 | 1064.23 |  690.72 | 5527.1  |
| d_shear          |       0 |  nan    |  nan    |  nan    |
| d_suture         |  588472 |   77.33 |   55.11 | 3767    |
| d_um_rock        |  588472 | 2529.17 | 2259.32 | 6760.53 |
| n_um_strong      |       0 |  nan    |  nan    |  nan    |
| n_um_moderate    |       0 |  nan    |  nan    |  nan    |
| d_um_strong      |       0 |  nan    |  nan    |  nan    |
| d_spring         |       0 |  nan    |  nan    |  nan    |
| spring_tmax_25km |       0 |  nan    |  nan    |  nan    |
| tf_ophiolite     |  588472 |    0.01 |    0    |    1    |
| tf_greenstone    |  588472 |    0    |    0    |    1    |
| tf_rift          |  588472 |    0.06 |    0    |    1    |
| tf_accretion     |  588472 |    0.07 |    0    |    1    |

## Gravity
WGM2012 residual for 588,472 cells; p10/p50/p90 -11.0 / 0.1 / 11.3 mGal.

## Depth and heat flow
CRUST1.0 sedthk-m.xyz.zip; cells with thickness 588,472; median 500 m.
Onshore heat-flow sites 39,362; cells with a site within 50 km 141,391.

