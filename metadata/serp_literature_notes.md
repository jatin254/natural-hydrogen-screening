# Serpentinisation-setting H2 occurrences: notes

Compiled 2026-11-03 as a validation set for the prospectivity map. The data file is `serp_literature.csv` (30 rows). Every value and coordinate in it was read on a page that was actually opened with WebFetch. Search snippets were not used as sources.

## Result

| | Count |
| --- | --- |
| Rows | 30 |
| Qualifying rows (H2 measured, onshore ophiolite/ultramafic, located to ~10 km) | 19 |
| Rows kept for the record with blank lat/lon (cannot be located to ~10 km) | 11 |

Qualifying rows by country: Oman 4, Turkey 4, New Caledonia 3, Philippines 3, Italy 2, Kosovo 1, Spain 1, Canada 1.

Coordinate quality of the 19 qualifying rows:
- **source-printed (12):** Oman ×4 (Leong 2023), Kizildag ×3, Vuçe, Voltri ×2, Manleluag, Tablelands.
- **named-locality (4):** Chimaera, Bain des Japonais, Kaoris, Fuente Amargosa/Tolox.
- **approximate ~10 km (3):** Montagne des Sources, Poon Bato, Nagsasa. Consider dropping these from a strict hit/miss test or using a 10 km buffer.

## Method

1. Searched for each starting point in the brief plus general queries (hyperalkaline spring H2, ophiolite gas seep H2, recent discoveries 2023-2026).
2. Opened open-access full texts, accepted manuscripts, theses, SI files and abstracts. ScienceDirect, Wiley/AGU, doi.org, PMC (captcha), HAL (Anubis bot wall), earth-prints.org (empty JS pages) and several repositories could not be opened, so many primary papers were unreachable (list below).
3. Inclusion test as specified:
   - free gas H2 ≥ 1 vol%, or dissolved H2 above detection;
   - onshore ophiolite/ultramafic host;
   - natural seep, vent or spring (no wells, mines, fluid inclusions or submarine vents).
4. One row per site. Springs <1 km apart were merged, keeping the max value; per-sample values are in `notes`.
5. Units are copied as printed. Kizildag values were extracted as "mmol mol-1" but must be µmol/mol, since 605,000 mmol/mol is impossible; the Greek mu was lost in extraction.

## Coordinate caveats

- **Kizildag (D'Alessandro 2018):** coordinates are printed Long, Lat. Kurtbagi is the midpoint of the printed vent range.
- **Tablelands:** the coordinates are NAD27 (per Rietze 2015 thesis), roughly 100 m off WGS84. That does not matter at 10 km.
- **New Caledonia, Prony:**
  - Kaoris: point 24 of the Province Sud trail guide, UTM 58S, converted with pyproj. It matches the newcaledonia.travel pin to ~30 m.
  - Bain des Japonais: the viewpoint overlooking the pool, which lies a few hundred m to the SE.
- **Chimaera:** from the Kültür Envanteri map link, not a scientific paper. Etiope et al. 2011 EPSL (paywalled) probably prints coordinates.
- **Nagsasa (Philippines):** the coordinates are a harzburgite sample site at Nagsasa Cove (Grozeva 2020). That paper says its Zambales samples are ~5 km from the seeps. The seep GPS points are in Vacquand et al. 2018 (paywalled).
- **Poon Bato:** barangay centroid (PhilAtlas).
- **Montagne des Sources:** the peak inside the reserve (PeakVisor).
- **Fuente Amargosa:** Tolox village coordinates (Wikipedia); the spa adjoins the village.

## H2-value caveats

- **Nagsasa 58.5%:** taken from a GeoExPro news report of Aquino et al. 2025 (IJHE), because the paper was not reachable.
- **Chimaera ~10%:** from the Etiope AAPG 2014 abstract. The 7.5–11% range is Hosgormez 2008 as quoted on Wikipedia; the primary was not opened.
- **Manleluag / Poon Bato:** Cardace 2015 Table 3 extracted garbled. Check against the PDF.
- **Kizildag Tahtakopru / Gulderen:** the bold "free gas" flags were not legible, so some values may be dissolved-gas compositions. They qualify either way.
- **Lembi / Pourina (New Caledonia):** values are upper bounds ("≤20%", "≤10%") from an EGU abstract.

## Sources opened (used)

- Leong et al. 2023, GCA 347 (ORA accepted manuscript): Oman, Table 1 coordinates and Table 2 gas.
- D'Alessandro et al. 2018, Mar. Petrol. Geol. 89 (author PDF): Kizildag, Turkey.
- Etiope et al. 2014, AAPG/Search and Discovery abstract: Chimaera. Kültür Envanteri: Chimaera coordinates. Wikipedia "Yanartaş": Hosgormez 2008 range.
- Lévy et al. 2023, Front. Earth Sci.: Kosovo and Albania.
- New Caledonia:
  - Monnin et al. 2014 Biogeosciences (preprint and Archimer PDF);
  - Monnin et al. 2021 JGR-B (Archimer text and SI, Table S2);
  - Quéméneur et al. 2023 Front. Microbiol.;
  - Izerumugaba et al. EGU25-12600;
  - Province Sud Prony trail guide;
  - newcaledonia.travel;
  - PeakVisor.
- Philippines:
  - Cardace et al. 2015 Front. Microbiol. (Table 3 dissolved H2);
  - Woycheese et al. 2015 Front. Microbiol. (Manleluag coordinates);
  - Grozeva et al. 2020 Phil Trans A (NSF PAR);
  - GeoExPro;
  - DOST-STII;
  - Goldschmidt 2024/2025 abstracts (Aquino);
  - PhilAtlas.
- Italy: Boulart et al. 2013 Ofioliti (free gas and dissolved, Oman and Voltri; coordinate tables did not extract) and Brazelton et al. 2017 PeerJ (Voltri coordinates and dissolved H2).
- Spain: Ojeda et al. 2023 Chem. Geol. (RIUMA PDF) and Wikipedia "Tolox".
- Canada: Szponar 2012 MSc thesis (Memorial U.) and Rietze 2015 MSc thesis (Memorial U.).
- Costa Rica: Crespo-Medina et al. 2017 Front. Microbiol. and Sánchez-Murillo et al. 2014 G3 (ACG repository PDF).
- Miller et al. 2016 GCA (LDEO PDF): Oman wells, and the Neal & Stanger 1983 citation.

## Sites rejected and why

| Site | Reason |
| --- | --- |
| Al Bana, Oman (Leong 2023) | H2 below detection (air-contaminated) |
| Al Hilayw, Oman | no gas sampled |
| NSHQ04/NSHQ14 wells, Oman (Miller 2016) | wells |
| Kisecik and Tahtakopru B, Kizildag | H2 <10 µmol/mol (not detected) |
| Gökdere, Kizildag/Erzin | max 43 µmol/mol. Free vs dissolved not legible: if free gas it fails the 1% threshold. Latitude 37.0063 is printed, near Erzin. Borderline, excluded. |
| Erzin hyperalkaline spring (Yasin & Yüce 2023, Turk. J. Earth Sci.) | abstract lists H2 among dissolved gases but no value; PDF failed to load |
| Ujë-i-Bardhë spring, Albania (Lévy 2023) | free gas 369 ppm, below 1% |
| Leskovik, Albania (17 ppm) and Poklek, Kosovo (3 ppm) | below threshold and not shown to be ophiolite-hosted |
| Bulqizë chromite mine, Albania | mine |
| Fanama and Nemwegi, New Caledonia (EGU25) | ≤300 ppm |
| Bigbiga well, Philippines | well, 0 µM |
| Philippines Palawan: San Isidro (0 µM), Mainit Falls (not reported) | no H2 detected or reported |
| Ronda, Spain: Baños del Duque, Baños del Puerto, Fuente Romana, Lucildi | H2 below detection in 2021. Vega Escondida (0.01 mg/L) is mine-tunnel water. |
| Othrys, Greece | Etiope et al. 2013 call H2 "trivial"; Daskalopoulou/Li Vigni (IJG 2021) report <2–2500 µmol/mol across 17 sites without attribution. Full text robots-blocked, so not attributable. |
| Cedars, California (Morrill 2013 GCA) | abstract says "gases rich in N2, H2 and CH4 were exsolving from the springs", but no numeric value could be opened (Caltech SI behind an over-long S3 URL; Rietze thesis tables did not extract). Probable qualifier: Barnes Spring Complex N38°37'17.8" W123°07'53.5"; Grotto Pool N38°37'16.3" W123°08'01.1" (NAD27, Rietze 2015). Add if the value is verified. |
| Hakuba Happo, Japan (Suda) | dissolved H2 201–664 µmol/L, but the samples are from drilled wells Happo #1 and #3 |
| Bosnia and Herzegovina (Etiope et al. 2017 Appl. Geochem.) | paywalled. The GeoERA summary shows the main sites (Lješljani SB-1, Kokori IBK-1, Poljice EBM-1) are wells. Lévy 2023 Fig. 9 reports 8–48% H2 in Bosnia, unattributed. |
| Southeast Serbia, 32–85% H2 (Lévy 2023 Fig. 9 citing older literature) | sites, setting and coordinates not given; Randazzo 2021 G3 Serbian bubbling gases carry no H2 in the dataset description |
| Cabeço de Vide, Portugal | waters come from spa boreholes; H2 data not opened |
| Romania, Tișovița–Iuți (29% H2) | borehole gas |
| China, Hegenshan and Lajishan (Oil & Gas Geology 2026) | soil gas only; no spring values |
| Brazil, Cedrolina | rock or chromitite gas extraction, not a seep |
| Norway (Leka, Bymarka) | no measured H2 found (EAGE 2025 abstract is a desk study) |
| Prony submarine vents | seafloor (excluded by rule) |

## Not found or not checked (completeness gaps)

- **Vacquand et al. 2018 GCA** (Oman, Philippines, Turkey, New Caledonia seep coordinates). Paywalled; HAL blocked. This is the most important missing source: it likely adds several Oman seeps and the Los Fuegos Eternos / Nagsasa / Mangatarem seep coordinates.
- **Abrajano et al. 1988/1990:** paywalled.
- **Neal & Stanger 1983; Sano et al. 1993 (Oman H2-N2 seeps):** paywalled.
- **Deville & Prinzhofer 2016 Chem. Geol. (New Caledonia seeps):** not found open.
- **Etiope et al. 2011 EPSL (Chimaera/Tekirova); Etiope et al. 2016 Ronda; Etiope 2017 Bosnia; Etiope & Whiticar 2019 compilation:** earth-prints pages render empty.
- **Zgonnik 2020 Earth-Sci. Rev. supplementary tables:** ScienceDirect not reachable. This is the obvious cross-check for completeness.
- **Etiope & Sherwood Lollar 2013 Rev. Geophys. table:** not reached.
- **Canovas et al. 2017 JGR-B (Oman spring dissolved H2 with coordinates):** Wiley not reachable. The Leong et al. 2021 EarthChem dataset has spring chemistry but no H2.
- **Sánchez-Murillo 2014 auxiliary Table S1 (Costa Rica coordinates):** not reached.
- **Not searched in depth:** UAE springs (Etiope et al. 2015 is groundwater/wells), Cyprus Troodos, Iran/Pakistan, Cuba, Mexico, Papua New Guinea, Canada BC/Yukon, Oregon/Klamath, New Zealand, Russia Urals springs. Brief searches found no measured seep or spring H2 for any of them.
