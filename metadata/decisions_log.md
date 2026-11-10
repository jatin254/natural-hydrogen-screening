# Decisions log (public extract)

Protocols and results, written as the work went; tests were fixed here before their data was used. Items about fieldwork and data partners are omitted.

One entry per decision that changes data, method or scores. Never edit old entries; add a new one.

## 2026-10-31 — Phase 1 source selections

- **Method:** V1 is a chance-of-sufficiency play-fairway model (USGS PP 1900 approach), five components; Frequency Ratio is a diagnostic only.
- **Grid:** H3 resolution 5, onshore only.
- **DEM:** ETOPO 2022 60 arc-second bedrock (456 MB) instead of GEBCO; resolution is far finer than the grid needs and the file is ~10x smaller. GEBCO (public domain) is the fallback.
- **Tectonic provinces:** Hasterok et al. Zenodo release (CC BY 4.0), not the GPL-3.0 GitHub copy.
- **Magnetics:** WDMAM v2 is CC BY-NC 4.0 (non-commercial). Magnetics are context-only in V1. OPEN: keep WDMAM for internal research or switch to EMAG2v3 (NOAA).
- **Gravity:** WGM2012 licence not confirmed. OPEN: confirm with BGI before any commercial product uses the gravity-derived source layer.
- **Faults:** GEM is CC BY-SA 4.0. OPEN: decide how fault-derived layers will be licensed if distributed.
- **Occurrences:** EPRI terms of use unknown. OPEN: record the terms before any EPRI-derived output is shared.

## 2026-11-01 — Scope and additions

- **Scope:** the product ranks areas by geological potential; it does not predict presence. The play-fairway model stays the core of V1.
- **Ranking outputs:** per-cell probability of being in the top 10% across Monte Carlo runs; a ranked shortlist of regions grouped by province; capture curve against known hydrogen systems and simple baselines.
- **D14 added:** USGS natural gas compositional analyses (CC0), used only to validate the ranking in the US. Blank hydrogen values are never treated as zero.
- **Hasterok bundle:** only plates&provinces layers are used; bundled third-party layers keep their own licences.
- **GLiM:** native CRS is ESRI:54012 (World Eckert IV); reproject once in Phase 3. Folder renamed to LiMW_GIS.gdb so GDAL can open it (contents unchanged).

## 2026-11-01 — D11a ophiolite database deferred

- Could not be downloaded from the UT Austin repository. Not required for V1.
- Ultramafic/serpentinization sources in V1 come from: GLiM ultramafic or mafic sub-codes (pending the D02 audit), Hasterok province and suture context, and positive residual gravity (as in USGS PP 1900, layer SP4).
- Revisit only if the GLiM audit shows ultramafic rocks cannot be identified. Fallback candidate: EarthChem PetDB ophiolite samples (CC BY-SA 4.0, share-alike).

## 2026-11-01 — Magnetics switched; BGI contacted; India is the target

- **Magnetics:** WDMAM (CC BY-NC 4.0) retired. Replaced by NOAA EMAG2v3 (D04b, data_raw/D04b_emag2). Context only in V1.
- **Gravity:** WGM2012 kept for internal development. BGI emailed (bgi@cnes.fr) about commercial use of derived, non-redistributed layers. BGI states its products are "mostly dedicated to support scientific and academic activities". If BGI refuses, replace the gravity layer before any client delivery.
- **Target:** the product is an India prospectivity ranking (onshore + Andaman & Nicobar). Global data and known systems elsewhere are used to calibrate and validate the method, not as the deliverable.
- **Hasterok provinces:** prov_type includes "ophiolite complex" (17 polygons), rifts, cratons, shields and accretionary complexes; lastorogen includes "failed rift"; cratons.shp carries a "reworked" flag. These partly fill GLiM's missing ultramafic class.

## 2026-11-01 — NGDR layer selection (India)

Core (all states): Geology_2M; TECTONIC_FRAMEWORK; SUTURE_ZONE_TECTONIC; SHEAR_ZONE_TECTONIC; FAULT_TECTONIC; BASEMENT_DEPTH_TECTONIC; ACTIVE_FAULT (Seismotectonic); DEPOSIT (Mineral); GEOTHERMAL_SPRING_GEOTHERMAL.
Rule: each structure or gravity layer is taken from ONE service only, to avoid double counting. Tectonic map is the source for structures and basement depth; Seismotectonic only for active faults; Geothermal (not Seismotectonic HOT_SPRING) for springs.
Skipped: base-map layers (rivers, towns, sea, water bodies); offshore (bathymetry, ridges, trenches); duplicates (Fault_2M, Thrust_2M, Commodity_2M, Seismotectonic BASEMENT_DEPTH, BOUGER_ANOMALY, STRUCTURE, HOT_SPRING); deferred to V2 (LINEAMENT, FOLD, VOLCANO, EARTHQUAKE, CMT/FPS, MOHO, MAGNETIC).

## 2026-11-01 — After the NGDR audits (D15-D20)

- **Geology_2M:** keep `geology_2m_gcs_ngdr_20_5` (3.26M km², matches India). Drop the look-alike `geology_2m_gcs_ngdr` (3.45M km² incl. ~0.2M km² blank/"Unmapped").
- **Geology_2M has no lithology column** (age, group, supergroup, index only). Rock types come from a Phase 2 rulebook over ~500 `index_` units. NGDR also serves 1:50k lithology (`lithology_gcs_ngdr*`); size checked with `count` before deciding.
- **Ultramafic sources for India:** TECTONIC_FRAMEWORK "Ophiolite / Melange" (143 polygons, ~4,800 km²: Andaman, Naga-Manipur, Indus suture) and "Greenstone and allied Supracrustal Belts" (~78,000 km²). These fill the gap left by GLiM.
- **Faults:** FAULT_TECTONIC + THRUST_TECTONIC form one structure layer (no overlap: FAULT has no thrust class). Classes give weights later: involving basement > cover; neotectonic = active (preservation risk / open pathway).
- **Active faults:** ACTIVE_FAULT (26 study sites) is context only; national active faults = FAULT_TECTONIC "Neotectonic Fault" (228 + 72 mixed).
- **Gravity:** WGM2012 stays the gridded source; D16 Bouguer contours (-550 to +150 mGal) check it over India and are the fallback if BGI refuses. D20 GRAVITY dropped (download failed; not needed).
- **India mask:** NGDR `india_state_boundary_ngdr_print` (D21). The tectonic maps extend into neighbouring countries (framework 4.36M km²) and are clipped to it.
- **Hot springs (D19):** evidence list only, as planned.
- **Audit fixes:** features just beyond India are a NOTE, not a CRS blocker; duplicates now mean same geometry AND attributes; co-located different records (e.g. two minerals at one locality) are kept.

## 2026-11-01 — Layer counts: 1:50k lithology and ground gravity added

- **Lithology:** GSI 1:50,000 seamless lithology (`lithology_gcs_ngdr_makevalid`, 360,702 polygons, `lithologic` rock-type column) becomes the rock-type source for India. Polygons average ~9 km², smaller than an H3 res-6 cell (~36 km²), so small ultramafic bodies survive as a fraction of the cell. Geology_2M becomes context: it fills sheets marked UNMAPPED.
- **Gravity:** D20 reinstated. `gravity_gcs_ngdr` holds 756,405 ground stations with observed gravity and Bouguer anomaly. It replaces WGM2012 over India where stations exist; WGM2012 only fills gaps, flagged in the confidence map. This also reduces dependence on the BGI licence answer.
- **Minerals:** seven thematic maps added (chromite, Cr-Ni, Cr-PGE, Ni, magnesite, asbestos, talc; ~128 points), merged with DEPOSIT into one ultramafic-indicator point layer in Phase 3. Host rock, not commodity, decides whether a point counts. Uranium (6 points) not used.
- **India mask:** D21 audited: 36 states/UTs, 3.27M km², 1 invalid polygon (make_valid in Phase 3).
- **Download:** pages are saved as they arrive and resume after a failure; requests are sorted by gid when the server allows it.

## 2026-11-01 — Audits of Lithology_50K, ground gravity and mineral maps; lithology rulebook v1

- **Lithology_50K accepted** as the India rock-type source: 360,702 polygons, 3,287,142 km² (matches India), complete download. Phase 3 fixes: drop 80 empty geometries and 350 exact duplicates; make_valid 37 polygons. ~148,000 km² is NODATA (unmapped sheets, water, snow, neighbouring countries); Geology_2M fills unmapped sheets.
- **Rulebook v1** (`configs/lithology_classes.yaml`, `src/h2pros/lithology.py`): 2,201 rock names → 16 classes, 99.999% of area classified. Each name is split into its listed rocks; the first-listed rock is the main class (GSI lists the dominant rock first) and every other class is kept as a minor flag.
- **Ultramafic rocks in India at 1:50k:** ~2,760 km² as main rock, ~6,250 km² including minor occurrences (ophiolite mélange, greenstone belts). Consistent with the tectonic map's ophiolite/mélange class (~4,800 km²). Ultramafic alteration (talc, tremolite-actinolite schist) ~540 km²; BIF ~4,040 km²; mafic intrusive ~8,900 km².
- **Known limits of v1:** "QUAT" (sand/silt/clay names) includes some pre-Quaternary clays and the Andaman "undifferentiated sediments" mélange; Phase 3 reassigns QUAT polygons with a pre-Quaternary `age` to SH. Basalt (MAF_V) is dominated by Deccan flood basalt (~430,000 km²); Phase 3 flags it separately using `supergroup` = DECCAN TRAP so it is not scored like greenstone-belt mafics. The `intrusive` column also records ultramafic intrusions and will be read in Phase 3.
- **Mineral points:** a point counts as ultramafic evidence only from its host rock (strong) or geology/remarks/alteration (moderate), never from the commodity alone (most magnesite in Uttarakhand/Rajasthan is dolomite-hosted; some asbestos and nickel points are in schist, basalt or laterite).
- **Ground gravity:** 756,405 stations, all complete. No stations north of 30.5°N (Himalaya, Ladakh). Some bad values seen (observed gravity -60, theoretical 0). `06_gravity_check.py` measures bad values, Bouguer consistency and coverage before we decide how to grid it.

## 2026-11-01 — NGDR / GSI licence terms (GSI Data Sharing and Accessibility Policy, 2019)

Saved as data_raw/D15_gsi_geology2m/NGDR_terms_Data_Dissemination_policy_2019.pdf. Applies to D15-D21. Not legal advice.
- **Allowed:** free use; "Value Added Services and/or derivative works with due acknowledgement to GSI" (Annex III). The prospectivity ranking is a derivative work.
- **Required on every product:** the notation "Product of Geological Survey of India; reproduced by permission of Director General on behalf of Government of India", in a conspicuous position, plus the source URL on the GSI portal.
- **Not allowed:** resell, transmit or convey the downloaded data to a third party, in full or in part (Annex IV). Clients receive scores and maps derived from it, never the GSI layers themselves.
- **Registration:** licence is single-user, non-transferable and for a named theme/project; downloads are for registered users who accept the online undertaking. ACTION: register on the GSI portal, naming this project.
- **Records:** keep a record of all downloaded datasets (manifests + checksums cover this).
- **Liability:** user indemnifies GSI; GSI disclaims liability for commercial use.
- **Gravity (s.7.4):** stations at ~1 per 2.5 km²; values rounded to 1 mGal, or 20 mGal in MoD-restricted zones; restricted-zone elevations come from open-source DEMs. 06_gravity_check.py now flags 20 mGal zones.

## 2026-11-01 — Review results: lithology v1.1, mineral evidence, gravity coverage

- **Ultramafic list reviewed and accepted** as classified (main vs minor). Rulebook v1.1 fixes 20 rare names (e.g. HERTZBURGITE typo, alkaline-complex rocks); unclassified area now 12 km².
- **Mineral evidence:** 132 distinct sites (~1 km) carry ultramafic evidence, 82 of them strong (ultramafic host rock). Talc and magnesite hosted in carbonate rocks no longer count as alteration evidence (they form from dolomite, not serpentinite).
- **Ground gravity coverage:** 56.8% of India's 0.1° cells have stations (median 44 per covered cell). No stations at all in Andaman & Nicobar, Manipur, Mizoram, Tripura, J&K, Ladakh, Himachal; under 1% in Nagaland and Arunachal; 18% in Maharashtra. The gaps include the ophiolite belts (Andaman, Naga-Manipur) that matter most. No 20 mGal (restricted) blocks found: restricted areas appear to be withheld, not coarsened.
- **Gravity values:** drop 7,780 stations (1.0%) with observed gravity outside 977,000-984,000 mGal. Use GSI's stored `bouguer_an` (its own corrections) rather than recomputing; 5.7% differ from a simple recomputation by >10 mGal and are handled by a spatial outlier filter on the gridded field (Phase 3).
- **Gravity source rule (decided in Phase 3 by a test, not by preference):** compute the residual (high-pass) Bouguer anomaly from GSI stations and from WGM2012 over the covered area. If WGM2012 reproduces the GSI residual well (correlation >= 0.7), use WGM2012 nationally for one consistent layer and GSI as validation. If not, use GSI where covered and treat gravity as "no evidence" (prior value, wider uncertainty, lower confidence) elsewhere — no stitching of two sources inside one score.
- **Phase 1-2 data audit complete for India.** Open: GSI portal registration; BGI reply.

## 2026-11-01 — Phase 3 started: India grid and first layers

- **Registered** on the GSI portal (licence condition). BGI: no reply yet.
- **Grid:** H3 resolution 6 (~36 km² cells) over the D21 India mask; coastal/island cells kept with `land_frac` < 1; each cell takes the state with the largest share. Stored in `layers/india_h3r6.gpkg` (one table per theme, opens directly in QGIS).
- **CRS:** EPSG:6933 for areas (equal-area); EPSG:7755 (WGS 84 / India NSF LCC) for distances.
- **Lithology layer:** exact polygon x hexagon areas (no sampling), so small ultramafic bodies (~0.5 km²) are kept. Per cell: share of each main class (sums to 1 over mapped area), `any_<flag>` shares for minor rocks, absolute ultramafic km². Corrections applied: pre-Quaternary "QUAT" -> SH; Deccan Trap basalt -> MAF_D; ultramafic intrusions in `intrusive` added to the ultramafic flag.
- **Structures layer:** distances (km) to basement faults (codes Fib/Fibc), any fault, neotectonic faults and thrusts, thrusts, shear zones, sutures; tectonic-framework unit and shares of ophiolite, greenstone, rift and accretionary settings; ultramafic evidence sites per cell and distance to the nearest strong one; distance to thermal springs and hottest spring within 25 km. Raw measurements only; turning them into chances is Phase 4.
- **Not yet on the grid:** gravity (needs the WGM2012 vs GSI test), basement depth (contours need gridding), heat flow (IHFC), hydrogen occurrences.

## 2026-11-02 — Grid, lithology and structures layers built

- **Grid:** 90,866 H3 res-6 cells. Script 08 needed two fixes on real data: big polygons are cut into <=256-vertex pieces before the overlay (hours -> minutes), and pieces left invalid by reprojection/cutting are repaired, with a snap-rounding fallback.
- **Lithology on grid:** every class captured at ~100% of its polygon area (QUAT 99.8%: coast). NODATA only 34% inside the grid: most NODATA polygons are outside the India mask (neighbouring countries, sea). Deccan basalt separated (MAF_D 481,000 km²; other mafic volcanics 35,400 km²); 27,000 km² of pre-Quaternary "QUAT" moved to SH.
- **Ultramafic cells:** 3,156 cells contain ultramafic rock (1,719 as main rock). Highest: Manipur (Naga-Manipur ophiolite), Ladakh (Indus suture ophiolites), Meghalaya (Sung Valley complex) - geologically expected.
- **No-lithology cells:** 3,371 cells have no mapped rock. Probably mostly the parts of the official India map that GSI has not mapped (PoK, Aksai Chin); script 10 prints them by state to confirm. These cells will be shown as "no data", never ranked.
- **Structures:** sutures and thrusts exist only in the Himalaya and north-east, so they act as regional context, not national layers. Basement faults are within ~81 km (median) of a cell.
- **Next:** gravity layer and the GSI vs WGM2012 test (script 10).

## 2026-11-02 — Gravity test result: GSI where it exists

- **Result:** GSI stations used 692,887 of 756,405; 49,675 cells have >= 3 stations; 54 isolated jumps removed. Correlation GSI vs WGM2012: full Bouguer r = 0.89, residual r = 0.67 (48,271 cells) - below the 0.7 bar set in advance.
- **By state:** WGM2012 agrees well in Gujarat, Andhra Pradesh, Rajasthan, West Bengal (r 0.75-0.82) but poorly in the eastern shield - Chhattisgarh 0.20, Odisha 0.35, Jharkhand 0.50, Bihar 0.47 - which holds key ultramafic and BIF targets (Sukinda, Singhbhum).
- **Maps:** WGM2012 residual shows strong artificial highs along both coasts (land-sea step in the model) and noise in the Himalaya; using it nationally would add false "dense body" signal along every coast.
- **Decision (rule applied as pre-registered):** gravity evidence = GSI residual where it exists (48,271 cells, 53%); elsewhere no gravity evidence (scored neutral, wider uncertainty, lower confidence). Both residuals stay in the `gravity` table.
- **Gap-fill option for Phase 4, not adopted now:** WGM2012 residual as a low-weight fallback in GSI gaps (Andaman, north-east, Himalaya), away from coasts - only if BGI permits commercial use and only if it does not create edge effects.
- **No-lithology cells confirmed:** Ladakh 2,797 and J&K 199 (areas GSI has not mapped inside the official boundary), Gujarat 205 (Rann of Kachchh), small islands (Lakshadweep 28, A&N 27). Shown as no data; never ranked.
- **Next:** script 11 - basement depth (gridded from GSI contours, 40 km limit) and heat flow (IHFC onshore sites, no interpolation beyond 50 km).

## 2026-11-02 — Depth/heat layer; Phase 4 scoring rules v1

- **Basement depth:** 20,084 cells (22%) within 40 km of a GSI contour: Indo-Gangetic plain, Rajasthan, Cambay (Gujarat), Bengal, Assam. Proterozoic basins (Vindhyan, Cuddapah, Chhattisgarh) are not contoured; their sediments still count through the lithology. Fix: contours valued 1-20 (Assam shelf, Arunachal, Nagaland) are in km and are converted to m.
- **Heat flow:** 620 IHFC onshore sites; 18,446 cells (20%) have a site within 50 km; median 49 mW/m² (cool shield). None in the north-east, Himalaya or Andaman. Not used in scoring V1 (too sparse); kept as context.
- **Scoring (Phase 4), rules v1 in `configs/scoring_rules.yaml`,** set before seeing any result:
  - generation = noisy-OR of serpentinisation, iron oxidation, radiolysis, dense body (gravity); mineral evidence and ophiolite/greenstone setting feed serpentinisation (max, not added, as they describe the same source).
  - charge = max(local generation, generation within 250 km x linear decay), computed on H3 res-4 blocks (~45 km).
  - migration = noisy-OR of basement faults, crustal zones (shear/suture/thrust), other faults.
  - reservoir = noisy-OR of sandstone/carbonate, basin depth 0.5-6 km, fractured hard rock near faults.
  - seal = noisy-OR of evaporite, shale, low-permeability cover (Deccan basalt, thick alluvial basin, slate/schist).
  - preservation = tectonic stability (neotectonic faults within 5/15 km lower it).
  - accumulation = charge x migration x reservoir x seal x preservation.
  - 1,000 Monte Carlo runs; one triangular draw per rule per run, shared by all cells using that rule.
  - Ranking = share of runs a cell is in India's top 10%. Cells with no mapped geology are excluded.
- Two outputs: the **generation fairway** (where hydrogen can form) and the **accumulation fairway** (where it can also gather and stay).

## 2026-11-02 — First ranking (rules v1) reviewed; rules v1.1

- **v1 result:** 87,495 cells scored. The ranking was led by Deccan basalt (MP, Maharashtra), Vindhyan/Cuddapah shelf cover and Ladakh. Top cells had low local generation (0.14) but charge 0.84.
- **Diagnosis (structural, not a matter of taste):**
  1. 250 km lateral migration on ~45 km blocks saturated charge: with ~300 ultramafic cells spread over India, nearly every cell was within reach of a strong source, so source quality stopped separating cells and the ranking became a "basin quality" map. PP 1900's 250 km is a maximum for its study area, not a requirement.
  2. Deccan basalt counted twice: as seal (flood-basalt cover) and as fractured-rock reservoir in the same cell.
  3. Preservation had a single factor (mapped neotectonic faults), so active orogens with few mapped neotectonic faults (Ladakh) scored as stable.
- **v1.1 changes:** lateral migration 50 km on ~250 km² blocks; Deccan basalt removed from the fractured-reservoir rock set (stays as seal cover); preservation = product of tectonic stability and a new orogenic-activity factor (Himalayan orogen, Indo-Burman and Andaman active margins 0.40/0.60/0.80; elsewhere 0.85/0.95/1.00); ranking adds P(top 1%) to separate the many cells tied at P(top 10%) = 1; summary now prints the spread of generation, charge and accumulation.
- **Guard against tuning to expectations:** these are the only post-result changes; each fixes a stated flaw. Further changes wait for the validation step (Phase 5: capture curve against independent evidence and simple baselines), not for how the map looks.
- **Open:** the active-margin penalty also lowers Andaman, the one Indian locality with a reported hydrogen find; the generation fairway still shows it. Revisit in validation.

## 2026-11-02 — Rules v1.1 result; v1.2 evaporite fix

- **v1.1 result:** charge no longer saturated (median 0.29, p90 0.57, p99 0.76). Shortlist led by the Dharwar greenstone belts (Karnataka), Cuddapah/Kurnool cover (Andhra Pradesh), Aravalli-Delhi fold belt (Rajasthan), Vindhyan cover (MP), Kachchh (Gujarat), Gondwana grabens (Damodar, Satpura, Pranhita-Godavari), Naga-Manipur and Ladakh. Generation fairway unchanged (Karnataka, Jharkhand, Odisha, Tamil Nadu lead).
- **Bug found:** the evaporite seal fired in gneiss cells (Tamil Nadu, Ladakh). Cause: Quaternary surface salt/gypsum crusts (salt marsh, Rann clays, "gypsite beds") were flagged as evaporite, and any trace in a cell triggered the rule.
- **v1.2 fix:** script 08 no longer counts evaporite in Quaternary-age polygons; the seal rule needs pre-Quaternary evaporite on >= 5% of the cell. Data-classification fix, not a weighting change. Requires re-running 08 and 12.
- **Not changed (by design):** Sukinda/Odisha and Andaman rank high for generation but not accumulation (weak reservoir/seal on the craton; active-margin penalty and no gravity in Andaman). This is the model's stated logic; validation decides whether it is right.

## 2026-11-02 — US validation: protocol fixed BEFORE any US data is processed

Purpose: test whether the scoring LOGIC (rules v1.2) ranks hydrogen-rich wells above hydrogen-poor wells, using US data. It is a test of the rules, not a US product.

- **Frozen rules:** `configs/scoring_rules.yaml` sha256 10a0ca87595c205f..., `configs/lithology_classes.yaml` sha256 c2808bbff9f9d37f... No rule is changed because of US results before this test is reported.
- **US layers mapped to the same columns** as India (rock classes, fault distances, gravity residual, basin depth). The mapping is fixed from the layers' own documentation before any well label is joined.
  - Lithology: USGS SGMC v1.1 (doi:10.5066/F7WH2N65, CC0): documented LITH1-LITH5 / LOW_LITH / LITH_RANK fields, ultramafic and serpentinite mapped. Chosen over GLiM (no ultramafic class, would test the data rather than the rules). The 2026 GeMS re-release (doi:10.5066/P1A3DQZK) corrects 8 states; can be swapped in later as a sensitivity check.
  - Faults: SGMC_Structure (faults) for "any fault"; USGS Quaternary Fault and Fold Database for "neotectonic". No US equivalent of GSI's "fault involving basement" exists: basement_faults uses SGMC faults that cut Precambrian units or crystalline rocks (rule fixed in the US layer script, documented there).
  - Gravity: WGM2012 residual (internal use; US ground gravity is dense in EGM2008). Basin depth: CRUST1.0 sediment thickness (1 deg, coarse). Tectonic setting: Hasterok provinces (ophiolite, rift, accretionary) in place of the GSI tectonic framework.
- **Sample:** USGS natural gas analyses (D14), conterminous US only. Positive = H2 reported >= 0.5 mol% (195 samples incl. Alaska). Negative = H2 reported (value or trace) < 0.5 mol% (3,794 incl. Alaska). Conterminous-US counts are reported by the US audit. Blank H2 = unknown, excluded (17,296), never negative.
- **Declustering:** labels aggregated to H3 res-6 cells (~36 km2): a cell is positive if any sample is positive, else negative. Each cell counts once.
- **Primary metric:** AUC of accumulation (acc_mean) separating positive from negative cells. Also reported: AUC of generation (gen_mean); share of positive cells in the top 10% of well cells.
- **Uncertainty:** 90% interval from 1,000 bootstrap resamples of spatial blocks (H3 res 3, ~12,000 km2).
- **Baselines** (same cells, same bootstrap): distance to ultramafic rock (SGMC); CRUST1.0 sediment thickness; heat flow (IHFC median within 50 km); random (0.5). External benchmark, not a pass criterion: USGS PP 1900 integrated prospectivity map (doi:10.5066/P13WCG5U).
- **Pass:** acc_mean AUC >= 0.65 AND lower 90% bound > 0.5 AND AUC exceeds the best baseline by >= 0.05.
- **Sensitivity (reported, not used to pass):** positive >= 1 mol%; negative <= 0.1 mol%; SGMC 2026 release.
- **Known confounders:** H2 in well gas can be a drilling artefact (bit or steel reactions); labs that used H2 as carrier gas report blanks (excluded); samples cluster by basin and by the BLM helium programme. A pass is evidence for the rules, not proof.
- **If it fails:** report it as is. Any later rule change is fitted on the western US (west of 100 deg W) and judged only on the eastern US (and the reverse), never on the same wells.

## 2026-11-02 — ScienceBase refuses scripted access (HTTP 403)

- `13_us_download.py list` got 403 Forbidden from ScienceBase for both releases (SGMC, PP 1900 data release). The site blocks non-browser requests; we do not try to get around that.
- SGMC and the PP 1900 rasters are downloaded by hand in a browser into data_raw/U02_sgmc and data_raw/U04_usgs_h2_prospectivity; record file names and the download date in metadata/dataset_register.csv. The Quaternary fault zip (USGS earthquake server) still downloads by script.

## 2026-11-02 — US audit result; US layer mapping fixed (before any well label is joined)

- **Audit:** validation sample = 3,830 analyses (191 positive, 3,639 negative) -> 2,591 cells (157 positive, 2,434 negative) in 237 blocks (94 with a positive). Positives spread over many states (Texas 30, Oklahoma 16, New Mexico 15, Colorado 11, Kansas 11, ...): no single state dominates. SGMC v1.1: 313,732 polygons, 18,418 lithology rows; ultramafic/serpentinite mapped (52 serpentinite units, GENERALIZED_LITH serpentinite 2,936 km2, melange 11,308 km2, iron formation 1,513 km2). Quaternary faults: 112,809 lines. PP 1900 grids: 5 km, EPSG:5070.
- **Mapping file:** `configs/us_lithology_terms.yaml` (sha256 54ca9bd30c35b738...): SGMC MAJOR1 -> main class (India patterns + 15 SGMC-term overrides, GENERALIZED_LITH fallback); other ranked lithologies -> minor flags; same Quaternary, evaporite and flood-basalt corrections as India (Columbia River Basalt -> MAF_D); melange -> tf_ophiolite.
- **Structures:** SGMC faults touching crystalline or Precambrian polygons = basement faults (SGMC maps surface faults only, so this input is weaker than GSI's); Quaternary faults (class B excluded) = neotectonic; Hasterok province types (title case) = tectonic setting. No US input for mineral-deposit evidence, sutures or greenstone setting: left missing = no evidence (conservative for the model).
- **Gravity:** WGM2012 residual (50 km), as in the protocol. **Basin depth:** CRUST1.0 sediment thickness (1 degree).
- **Baselines** are scored in whichever direction suits them better (e.g. if thinner sediment goes with more H2, it is flipped). This favours the baselines, making the test harder for the model.
- **Pipeline checked on mock data end to end** (layers -> scores -> verdict); AUC code checked against known separations.

## 2026-11-02 — US validation RESULT: FAIL (rules v1.2)

- **Sample:** 2,586 cells (157 H2-rich, 2,429 H2-poor) in 235 blocks. US layers: 225,052 cells; SGMC classified (30 rare MAJOR1 terms fell back to GENERALIZED_LITH); 82,787 basement-touching faults; WGM2012 residual everywhere; 18,557 US heat-flow sites.
- **Result:** accumulation AUC 0.517 (90%: 0.478-0.555); generation 0.545 (0.509-0.585). Best baseline: sediment thickness, inverted (thinner sediment = more H2), AUC 0.640 (0.594-0.684). Near-ultramafic 0.509; heat flow 0.532. USGS PP 1900 benchmark: total 0.508, source 0.556. Top-10% capture 13% (random 10%). Sensitivity variants also fail (0.523, 0.527). West 0.471, east 0.565.
- **Verdict:** FAIL on all three criteria. Reported as is.
- **Reading:** (1) neither our rules nor the USGS map separate H2-rich from H2-poor gas wells - the target is hard (wells only sample petroleum basins; H2 in well gas can be a drilling artefact). (2) The only clear signal, thin sediment, runs against our reservoir/seal logic, which rewards deep basins; generation alone does slightly better than the full accumulation model. (3) The India ranking is therefore unvalidated, and its accumulation logic is not supported by the US evidence; the generation fairway has weak support at best.
- **Next (per protocol):** diagnosis by component and input, by half (script 17). Any rules-v2 idea must point the same way in west and east, then be fitted on one half and judged on the other. The India report must state this result.

## 2026-11-02 — US diagnosis; v2 cross-half protocol (fixed before running it)

- **Diagnosis (all US cells, script 17):** ultramafic inputs carry no information in this sample (H2-rich and H2-poor wells alike are ~310 km from ultramafic rock), so the US test cannot judge the serpentinisation source. Consistent in BOTH halves: thinner sediment (AUC 0.36 = 0.64 reversed), closer shear zones (0.41), thrusts (0.42), basement faults (0.43), any fault (0.435); charge 0.60 (0.55 W / 0.64 E); reservoir 0.546. Reversed: seal 0.45, preservation 0.455.
- **Candidate switches** (`configs/rules_v2_candidates.yaml`, sha256 155417aab2854641...): cover = keep | thin (reservoir rewards thin cover instead of 0.5-6 km basins); seal = keep | drop; preservation = keep | no_faults | drop. 12 combinations, values not tuned.
- **Selection and test:** expected scores (mean COS). Fit on one half (best AUC), judge on the other, both ways. Success: test-half AUC >= 0.60 AND >= 0.03 above the thin-sediment baseline on that half, in both directions.
- **Honest limit:** the switches were suggested by diagnostics that saw all wells, so the held-out half is not independent of the idea, only of the choice among switches. A success justifies an independent test (new data); it does not validate v2.
- **Dilution check:** compare methane, N2, He, CO2 and depth between H2-rich and H2-poor samples. Thick basins generate much methane, which lowers hydrogen's share even if hydrogen is present; if so, part of the thin-sediment signal is dilution, not geology.

## 2026-11-02 — v2 cross-half RESULT: no success; what the US evidence supports

- **Sanity:** expected-score v1.2 AUC 0.515 vs Monte Carlo 0.517 - the shortcut is faithful.
- **Result:** fit west -> east: chose thin cover + no seal + no fault penalty: 0.625 on the east vs thin-sediment baseline 0.628. Fit east -> west: chose thin cover + no seal + no preservation: 0.566 on the west vs baseline 0.633. Fails both ways: v2 improves on v1.2 (east 0.565 -> 0.625, west 0.469 -> 0.566) but adds nothing over sediment thickness alone.
- **Robust in both halves:** dropping the seal component raises AUC by ~0.08-0.09 in every combination. Thin cover helps modestly. Preservation changes matter little.
- **Dilution check:** H2-rich samples carry less methane (median 73% vs 85%), more N2 (7.3% vs 2.9%) and come from shallower depth (3,869 vs 4,992 ft). Part of the thin-sediment signal is gas-system composition and depth (less hydrocarbon to dilute hydrogen), not hydrogen geology alone.
- **Conclusion:** on the largest public test, neither our rules (v1.2 or v2) nor the USGS PP 1900 map beats a one-variable baseline. Hydrogen share in petroleum-basin gas is a weak, confounded target and it does not sample ultramafic sources at all. No rule change is adopted from this test except one recorded lesson: petroleum-style seal scoring is not supported for hydrogen.
- **Status of India V1.2:** not validated; accumulation ranking not supported; generation fairway untested. Not to be presented as predictive.

## 2026-11-02 — Direction: from modelling to evidence; India V2 screening map

- **V2 rules** (`configs/scoring_rules_v2.yaml`, sha256 b17ee5723b0fd96f...): generation and migration unchanged; seal and preservation removed; reservoir replaced by "cover" (thin cover over basement highest; exposed hard rock counts as thin cover). Score = charge x migration x cover. Output table `scores_v2`; v1.2 stays in `scores`.
- **Status:** V2 is a screening tool for where to sample, built from lessons of the US test; it is NOT validated and must not be presented as predicting hydrogen. Its US performance is not reported as evidence because its changes were chosen using the same US wells.


## 2026-11-02 - Published Indian gas data compiled (step 2)
- `metadata/india_gas_literature.csv` (59 rows) + `india_gas_literature_notes.md`. Positive H2 at 6 sites only; 5 from one table
  (WGC 2015, Chaudhuri/Sinha/Chandrasekharam, Table 4: Bakreswar-Tantloi belt springs, N2-rich, He 1-2%), no method or year given.
  Plus a 1934 Assam oil-well report (0.1%). GSI Andaman H2 (2025) reported but unquantified. No Indian soil-gas H2 surveys found.
- Values checked against the source PDF. Known caveats: H2 used as GC carrier gas in some labs, air contamination, mixed units ("52 ppm").
- Use: candidate field-sampling sites and a sanity check (`scripts/19_check_sites.py`), NOT a validation set (too few, one region).

## 2026-11-02 - V2 screening run and site check
- V2 (configs/scoring_rules_v2.yaml) run by user: 87,495 cells. Shortlist = exposed crystalline basement near faults:
  Dharwar/Cuddapah margin (~100,500 km2), Southern Granulite Terrain (~49,500; Salem, Mettupalayam UM), Chotanagpur-Singhbhum (~27,000),
  Aravalli-Delhi (~21,700), central India (~19,800), Ladakh + Arunachal (~11,300). Basins favoured by V1.2 seal/reservoir drop out.
- Report updated (rev 26): V2 screening map + Published gas sites sections; Next steps items 1-2 marked done.

## 2026-11-02 - Australia test: protocol fixed BEFORE any Australian data is downloaded

Purpose: an independent test of the V2 screening logic (and V1.2 for reference) in a region whose geology is closer to
peninsular India (Archean-Proterozoic cratons, greenstone belts) than the US. V2 was shaped by US wells; Australia has
not been used for anything, so this is the first test V2 can genuinely fail.

- **Frozen rules:** `configs/scoring_rules_v2.yaml` (b17ee5723b0fd96f), `configs/scoring_rules.yaml`
  (10a0ca87595c205f), `configs/lithology_classes.yaml` (c2808bbff9f9d37f). No rule is changed because of Australian results before this test is reported.
- **Layers:** Australian national layers mapped to the India column names; the mapping is written down from the layers' own
  documentation after the audit and BEFORE any gas label is joined to the grid (separate log entry).
- **Labels:** GA ORGCHEM gas analyses (WFS layer orgchem:Hydrogen, CC BY 4.0), onshore samples with coordinates on the
  Australian land mask. Positive = H2 >= 0.5 mol%. Negative = H2 reported (value or trace) < 0.5 mol%. Blank or
  non-numeric = unknown, excluded, never negative. Samples flagged by GA or the source as air-contaminated or as
  drilling artefacts are excluded if such a flag exists (decided from the field list, before scores are joined).
- **Declustering:** labels aggregated to H3 res-6 cells: positive if any sample is positive. Each cell counts once.
- **Minimum sample:** at least 20 positive cells and 100 negative cells onshore. Fewer = "insufficient sample": results
  are reported descriptively, no pass/fail.
- **Primary metric:** AUC of V2 accumulation (v2 acc_mean), positive vs negative cells. Also reported: V2 generation,
  V1.2 accumulation, top-10% capture.
- **Uncertainty:** 90% interval from 1,000 bootstrap resamples of spatial blocks (H3 res 3).
- **Baselines** (same cells, same bootstrap, each scored in its better direction): basement depth / sediment
  thickness (best US baseline); distance to ultramafic rock; heat flow (IHFC, 50 km median); random.
- **Pass:** V2 AUC >= 0.65 AND lower 90% bound > 0.5 AND AUC exceeds the best baseline by >= 0.05.
  **Partial:** AUC >= 0.65 and lower bound > 0.5 but not 0.05 above the best baseline = better than chance, but no
  evidence the geology adds anything to the baseline.
- **Sensitivity (reported, not used to pass):** positive >= 1 mol% / negative <= 0.1 mol%; methane share of positive
  vs negative samples (dilution check); results with and without basement-hosted (non-sedimentary-basin) samples.
- **Secondary, descriptive only:** GA soil-gas H2 (NSW surveys, Record 2024/56): too few, too clustered for an AUC;
  reported as scores at survey sites with the survey's own high/low classes.
- **If it fails:** report it as is, in the India report. No rule tuning on Australian samples; any future change is fitted
  on one half of Australia and judged on the other, as in the US.

## 2026-11-02 - Australia labels: first look (no scores joined) and one clarification
- GA WFS works: every orgchem gas layer returns the same table (3,799 analyses, 1,095 boreholes, 290 columns); `Hydrogen.csv`
  is used. Columns: H2 = `H2_MOLE_PERCENT`; location = `COLLAR_LONG_GDA94` / `COLLAR_LAT_GDA94`; GA's own `ONSHORE_OFFSHORE`
  flag defines onshore (1,561 rows onshore, of which ~1,200 in the Cooper-Eromanga basins). The A07 land mask is a cross-check only.
- **Clarification fixed before scoring:** many old analyses report H2 as exactly 0, which can mean "not detected" or "not analysed".
  Primary analysis follows the protocol (a reported 0 is a negative). Added sensitivity: drop cells whose only H2 values are exact zeros.
- Concentration risk: onshore samples are dominated by one basin system (Cooper-Eromanga). The audit reports positive cells by province.

## 2026-11-02 - Australia test RESULT: insufficient sample (no pass/fail, per protocol)
- GA's public gas table reports H2 for only 340 of 3,799 analyses (3,459 blank). Onshore (GA flag): 188 samples, 40 with H2 >= 0.5 mol%.
- After declustering: 71 onshore cells (23 positive, 48 negative) in 26 blocks; 36 of the cells (16 positive) are in the Cooper Basin.
  Below the pre-registered minimum (100 negative cells) -> "insufficient sample". Without zero-only cells: 23 vs 34. Sensitivity labels: 14 vs 30.
- Not pursued further: with 71 cells in 26 blocks the AUC interval would be too wide (roughly +/-0.12 or more) to tell chance from a useful
  model, and every sample is from a petroleum well in a sedimentary basin - the same blind spot as the US test. No Australian layers built.
- **Lesson:** public well-gas databases sample sedimentary basins, while V2 ranks exposed crystalline basement. No well-based desk test
  can validate V2 in any country; surface measurements (soil gas, springs) at V2-ranked and control sites are the remaining route.

## 2026-11-03 - Global occurrence audit (labels only) and global test protocol, fixed BEFORE any global layer or score is built

**Audit (script 24):** EPRI occurrences: 341 records, 40 countries, 273 groups at 25 km, 241 res-3 blocks. Russian Federation 180 records
(53%; largely Soviet-era literature); Asia 175 groups, Europe 46, North America 32, Africa 8, Oceania 7, South America 5.
Category: Free Gas 171, Hydrogen in inclusions 95, Dissolved gas 69, Other 6. Hydrogen is numeric in 335 records and >= 10% in 332:
the list holds hydrogen-RICH occurrences only (presence-only, no negatives). 32 groups mention an ultramafic / ophiolite context.
Onshore IHFC heat-flow sites: 41,283 in 3,864 res-3 blocks; 153 of 241 occurrence blocks also hold one.

**Protocol (global test of the method):**
- **Question:** do the rules (V2 primary, V1.2 reported), applied to GLOBAL layers, rank cells with known hydrogen-rich occurrences above
  places where geoscientists measured but no occurrence is listed? Presence-only and search-biased; a pass is evidence, not proof.
- **Grid:** H3 res 5, onshore land with lithology. Layers: GLiM, Hasterok provinces, GEM faults, WGM2012 residual, CRUST1.0, IHFC; mapped to
  the India columns. The mapping is fixed from the layers' own legends in a separate entry BEFORE labels are joined.
- **Positive cells:** res-5 cells holding >= 1 EPRI record with Category Free Gas or Dissolved gas, excluding magmatic/volcanic gases
  (Subcategory or text: volcan*, fumarol*, crater) - the model does not target magmatic hydrogen.
  Fluid inclusions and "Other" are excluded from the primary test (rock-hosted traces, not gas systems) and reported separately.
- **Background (primary, target-group):** res-5 land cells with >= 1 onshore IHFC heat-flow site and no EPRI record of any category.
  Secondary background: all land cells without an EPRI record.
- **Metric:** AUC of V2 acc_mean, positive vs background cells; 90% interval from 1,000 bootstraps of res-3 blocks. Also: V2 generation,
  V1.2 accumulation, top-10% capture.
- **Baselines** (same cells and bootstrap, better direction each): CRUST1.0 sediment thickness; distance to an ultramafic proxy
  (Hasterok ophiolite complexes, or GLiM basic plutonic if that is what the mapping fixes); IHFC heat flow (50 km median); random.
- **Concentration check:** AUC outside the Russian Federation, with its own interval.
- **Minimum sample:** >= 30 positive cells outside the Russian Federation; otherwise the outside-Russia criterion is "insufficient" and
  the result can be at most Partial.
- **Pass:** V2 AUC >= 0.65 AND lower bound > 0.5 AND >= best baseline + 0.05 AND outside-Russia AUC >= 0.60 with lower bound > 0.5.
  **Partial:** AUC >= 0.65 and lower bound > 0.5 without the rest.
- **Known confounders:** search bias (Soviet well and mine literature dominates); GLiM has no ultramafic class, so the global source score is
  weaker than India's; EPRI coordinate precision unknown; EPRI terms of use unknown -> internal use only.
- **If it fails:** report it as is; no rule tuning on these labels.

## 2026-11-03 - Global layer mapping fixed (configs/global_mapping.yaml), before any occurrence is joined
- Grid: H3 res 5 (~252 km2), cells touching GLiM; rock-class fractions from 49 points per cell on a 2 km GLiM raster (Eckert IV).
- GLiM level 1 -> India classes: su QUAT; ss SST (fine-grained 'sh' -> SH); sm SH; sc CARB; ev EVAP; mt GNS ('am' amphibolite and 'gr'
  greenstone -> MAF_V; level-3 'sr' -> MSED); pa, pi GRAN; pb MAF_I; va, vi, py VOLC; vb MAF_V (MAF_D inside Hasterok 'magmatic province');
  ig, wb, nd NODATA. Flags: greenstone = level-2 'gr' -> tf_greenstone; evaporite = level-3 'ev' or level-1 'ev';
  iron formation = level-3 'fe' only if >= 3 of the 12 largest 'fe' polygons lie within 300 km of a listed iron-formation district
  (automatic check, reported). No ultramafic class exists in GLiM: UM inputs = 0 everywhere.
- Provinces (Hasterok): tf_ophiolite / tf_rift / tf_accretion = share of the cell; tf_class = prov_type + lastorogen (title case).
- Faults (GEM, all active): d_fault_any = d_neotectonic = all; d_thrust = Reverse/Thrust slip types; d_fault_basement = fault points in cells
  with f_hardrock >= 0.5; d_shear none; d_suture = boundaries shared by two non-oceanic Hasterok provinces. Baseline d_um_rock = distance to
  Hasterok ophiolite complexes. Distances are great-circle (densified lines, KD-tree on unit vectors).
- Gravity WGM2012 50 km residual; depth CRUST1.0; heat flow IHFC 50 km median (baseline). Countries for the outside-Russia check:
  Natural Earth admin-0 50m (public domain, D22).
- Engine (12_score.py): global region uses great-circle pairs for lateral charge; p10/p90 stored for a subset of runs when memory would
  exceed ~0.8 GB; rules unchanged.

## 2026-11-03 - Global layers built (user's run); one technical engine change before scoring
- Layers: 588,472 land cells (res 5, ~148 M km2), 539,303 with mapped geology (rest ice / water). GLiM 1,235,259 polygons, 437 codes,
  2 km raster in 153 tiles. Iron-formation flag USED (5 of 12 largest 'fe' polygons within 300 km of a district). Class areas match the
  GLiM audit (e.g. GRAN 9.38 M km2 vs pa + pi 9.17 M). Greenstone cells 2,750; ophiolite cells 4,739; heat-flow sites 39,362.
- Known weaknesses (accepted, not changed): flood basalt (MAF_D) only 148,000 km2 - Hasterok 'magmatic province' misses most continental
  traps; province boundaries are dense (median distance 55 km), so the crustal-zones migration rule fires far more often than in India;
  GEM active faults are sparse in stable continents (median distance 465 km).
- Engine change (technical, no rule changed): lateral-charge blocks = one H3 level above the grid (India res 6 -> blocks res 5; global
  res 5 -> blocks res 4), so a block again holds ~7 cells and the run fits laptop memory; batch 20 runs for grids > 300,000 cells;
  optional --cool pause. India results are unaffected (min(5, 6-1) = 5).

## 2026-11-03 - Global test RESULT: FAIL (pre-registered rules)
- Sample: 191 positive cells (211 EPRI free/dissolved-gas records, volcanic excluded), 1 unscored; 18,849 heat-flow background cells; 3,882 blocks.
- Primary: V2 AUC 0.555 (90%: 0.522-0.592); V2 generation 0.551; V1.2 0.579. Best baseline: LOW heat flow 0.630; near ophiolite 0.617;
  thin sediment 0.521. V2 - best baseline -0.075 (-0.132 to -0.024). Top-10% capture 12% vs 10%. -> FAIL (AUC < 0.65, below baseline).
- Outside Russia (92 positive cells): V2 0.648 (0.597-0.698), above every baseline there (best: heat flow 0.585). The outside-Russia criterion
  (>= 0.60, low > 0.5) is met, but the overall test is not; this is a subgroup and is reported, not promoted.
- Secondary (all land as background): V2 0.504, V1.2 0.649, thick sediment 0.632 - search bias (wells drilled in basins) dominates.
  Fluid inclusions: low heat flow 0.804, V2 generation 0.654 (Russian shield samples).
- Reading: 98 of 191 positive cells are Russian, mostly Soviet-era well and borehole records in sedimentary platforms - the same well-in-basin
  blind spot as the US and Australian tests; V2 ranks those low. The V2 generation curve rises steeply at the top (ophiolite / mafic cells hold
  a disproportionate share of occurrences) and then flattens: about a quarter of positive cells sit at the lowest source scores.

## 2026-11-03 - V3 (learned weights) protocol, fixed BEFORE any model is fitted
Purpose: let the global occurrence data set the weights of the existing inputs, and test whether such weights TRANSFER to a continent
the model has not seen. Known limit: this protocol is written after seeing the global V2 test, so its design is informed by that result;
the hold-out design protects against fitting the labels, not against design choices.
- **Cells, labels, background:** exactly as the global test (res-5 cells; positive = EPRI Free Gas / Dissolved gas, not volcanic;
  background = scored cells with an onshore IHFC site and no EPRI record).
- **Inputs (global layers only, no score):** rock-class shares f_* (GNS, GRAN, MAF_I, MAF_V, MAF_D, VOLC, SST, SH, CARB, EVAP, MSED, QUAT),
  any_BIF, any_EVAP, tf_ophiolite, tf_greenstone, tf_rift, tf_accretion, log distances to any / thrust / basement fault, to province
  boundary and to ophiolite province, gravity residual (+ missing flag), log sediment thickness. Heat flow is EXCLUDED (the background is
  defined by heat-flow sites, so it would leak).
- **Models, fixed settings, no tuning:** primary = L2 logistic regression on standardised inputs (C = 1, balanced class weights);
  secondary = gradient-boosted trees (depth 3, rate 0.05, 200 iterations, L2 1.0, balanced).
- **Hold-out by region (5 folds):** Russia; Europe without Russia; Asia without Russia; North America; Rest (Africa, South America, Oceania).
  Each fold is predicted by a model trained on the other four. Scores pooled across folds (out-of-fold).
- **Metric:** pooled out-of-fold AUC; 90% interval from 1,000 bootstraps of res-3 blocks; per-region AUC for regions with >= 10 positive cells.
  Compared on the same cells with V2 accumulation and the baselines (better direction each).
- **Pass:** pooled AUC >= 0.65 AND lower bound > 0.5 AND >= best baseline + 0.05 AND >= V2 + 0.05 AND AUC > 0.5 in at least 3 of the
  held-out regions with >= 10 positives. **Partial:** pooled AUC >= 0.65 with lower bound > 0.5, without the rest.
- **Sensitivity (reported):** the same with Russia removed entirely; the secondary model.
- **Only on Pass or Partial:** fit on all cells and map India from the GLOBAL layers (same inputs as training), as percentiles within India,
  labelled with the test result. On Fail no V3 map is produced.
- **Exploratory (not a test):** out-of-fold score percentile by EPRI Subcategory (which hydrogen settings the inputs recognise).

## 2026-11-03 - V3 (learned weights) RESULT: FAIL; desk validation closed
- Pooled out-of-fold AUC 0.589 (90%: 0.548-0.629); boosted trees 0.583; V2 0.571; low heat flow 0.573. V3 - V2 +0.018 (-0.029 to +0.065);
  V3 - best baseline +0.015 (-0.040 to +0.067). Held-out regions > 0.5: 4 of 5 (Europe 0.483). Russia removed: V3 0.618, V2 0.607.
  -> FAIL (AUC < 0.65, no margin). No V3 map produced.
- Reading: learning weights from the data adds nothing measurable over the expert V2 weights; both find a weak, real signal (~0.57-0.59).
- Learned weights (all cells, for reading only): farther from ACTIVE faults = more occurrences (+0.94; stable continental interiors);
  inside ophiolite provinces = more (+0.66); closer to basement faults and thrusts = more; large negative weights on evaporite (-1.98) and
  flood basalt (-1.70) rest on few cells and are treated as unstable.
- Exploratory (out-of-fold, by EPRI Subcategory, median percentile; 50 = background): Serpentinization 99 (V2 77), Orebodies 85 (V2 74),
  Igneous 88, Aquifers 65 (V2 51), Precambrian 48 (V2 66), Water from hydrocarbon fields 35 (V2 30). The inputs recognise
  serpentinisation-type hydrogen well, even in unseen regions; basin and aquifer hydrogen, which dominate every public dataset, poorly.
- **Decision:** desk validation is closed after four tests (US, Australia, global V2, global V3); none passes. No further desk tests on
  public occurrence data. V2 stays a screening map; its best-supported use is serpentinisation / ophiolite-type targets.

## 2026-11-03 - Final desk test: serpentinisation hydrogen on NEW literature sites (protocol fixed before compiling the sites)
- **Hypothesis:** V2 ranks serpentinisation-type hydrogen sites that it has never been scored against above heat-flow background, and
  does better than the simple rule "near an ophiolite province".
- **Positives:** sites from the published literature with hydrogen MEASURED in gas from seeps, gas vents or hyperalkaline springs in
  ophiolites or ultramafic massifs (free gas H2 >= 1 vol%, or dissolved H2 reported above detection); coordinates printed in the source
  or a named locality located to within ~10 km. Compiled into metadata/serp_literature.csv BEFORE any score is looked up.
  Any site within 25 km of ANY EPRI record is dropped (only new sites count). Aggregated to res-5 cells.
- **Background:** as the global test (scored res-5 cells with an onshore IHFC site, no EPRI record), minus literature cells.
- **Scores:** primary = V2 accumulation (global layers, already computed); also V2 generation and V1.2.
  Baselines: near ophiolite province (Hasterok), sediment thickness, heat flow (better direction each).
- **Minimum sample:** >= 15 new positive cells spread over >= 4 countries. Fewer = "insufficient": descriptive only.
- After this test: no further desk tests on public occurrence data, whatever the outcome.

## 2026-11-03 - Final desk test RESULT: INSUFFICIENT SAMPLE (descriptive only); desk validation closed
- 30 literature rows; 19 measured with coordinates; only 7 more than 25 km from any EPRI record -> 7 cells in 6 countries (minimum 15).
  EPRI already holds most published serpentinisation sites (Oman, Zambales north, Chimaera); the literature cannot supply enough new ones.
- Descriptive: V2 accumulation AUC 0.822 (90% 0.679-0.912), V2 generation 0.878, V1.2 0.621, near-ophiolite-province 0.359.
  Six of seven new sites rank at or above the 77th percentile of background for V2 (Voltri x2, Ronda, Poon Bato, Vuce, Montagne des Sources);
  Tablelands at the 49th. Hasterok's province map misses these small massifs; V2 picks them up through rock type and gravity.
- Reading: consistent with the V3 exploratory result (serpentinisation sites rank high on unseen data), but too small to count as a test.
  No outcome A/B/C is declared.

## 2026-11-09 - Evidence-layer data found (probe); build rules final before any download
- Probe (metadata/evidence_probe.md): NGDR WFS has `cite:magnetic_gcs_ngdr` (716,352 ground magnetic stations; observed, IGRF,
  anomaly in nT) and `cite:stream_sediments_gcs_ngdr` (510,641 NGCM samples; U, Th ppm, K2O %, plus Cr, Ni, MgO). Both GSI Data Policy
  2019. Marine magnetic layers not used (offshore). Esri India groundwater: 5 yearly layers 2019-2023, 59,955 records, pH column
  `ph_mg_l` (2021: `ph_mg_l1`); several years store numbers as text ("BDL", "<0.1").
- Final build rules (scripts/30_evidence_layers.py), fixed before the data is downloaded:
  - magnetic regional = median of CELL medians within 50 km (>= 5 cells with data), not of single stations (station pairs at 50 km
    are ~2 billion; cell medians give the same regional field). Stations with observed - IGRF - anomaly off by > 5 nT dropped.
    Cell value = SECOND-largest |residual| with >= 3 stations, so one bad station cannot set a flag (replaces "max").
  - radiometric: cells need >= 3 samples; "<x" values = x/2; Cr, Ni, MgO medians stored as context, no flag, no test.
  - water: "within 5 km of the cell" = within 5 km of the cell's boundary; "<x" = x/2; text such as BDL = missing.

## 2026-11-09 - Evidence layers BUILT (metadata/evidence_layers.md); test plan amended before any field result
- Coverage of India's 90,866 cells: magnetic 49% (threshold 566 nT), radiometric 62% (U >= 6.3 ppm or Th >= 39 ppm),
  groundwater 62%. Groundwater: 58,380 samples with pH; 310 at pH >= 9; 11 at pH >= 10 (7 of them Tumkur district, 2022);
  6 also Ca > Mg; 40 flagged cells.
## 2026-11-09 - Clean working copy
- Move completed: raw data and remaining files moved into `h2-india`; old folder `h2-prospectivity` emptied of unique files and cleared for deletion.
- Move completed: raw data and remaining files moved into `h2-india`; old folder `h2-prospectivity` emptied of unique files and cleared for deletion.
