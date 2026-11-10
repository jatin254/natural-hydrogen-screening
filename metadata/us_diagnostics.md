# US diagnosis after the FAIL (not a test; nothing tuned)

Cells 2,586 (157 H2-rich). AUC 0.5 = no signal; below 0.5 = the input works in reverse. 'Consistent both halves' = same direction and at least 0.03 from 0.5 in the west AND the east.

## Model components

| score       |   AUC all |   90% low |   90% high |   AUC west |   AUC east | direction        | consistent both halves   |   missing % |
|:------------|----------:|----------:|-----------:|-----------:|-----------:|:-----------------|:-------------------------|------------:|
| gen_mean    |     0.545 |     0.508 |      0.581 |      0.51  |      0.58  | higher = more H2 |                          |           0 |
| charge_mean |     0.598 |     0.551 |      0.649 |      0.549 |      0.638 | higher = more H2 | yes                      |           0 |
| mig_mean    |     0.544 |     0.51  |      0.58  |      0.504 |      0.583 | higher = more H2 |                          |           0 |
| res_mean    |     0.546 |     0.503 |      0.587 |      0.554 |      0.531 | higher = more H2 | yes                      |           0 |
| seal_mean   |     0.45  |     0.41  |      0.496 |      0.437 |      0.473 | lower = more H2  |                          |           0 |
| pres_mean   |     0.455 |     0.422 |      0.487 |      0.472 |      0.433 | lower = more H2  |                          |           0 |
| acc_mean    |     0.517 |     0.476 |      0.559 |      0.471 |      0.565 | higher = more H2 |                          |           0 |

## Raw inputs, strongest first

| group      | score            |   AUC all |   90% low |   90% high |   AUC west |   AUC east | direction        | consistent both halves   |   missing % |
|:-----------|:-----------------|----------:|----------:|-----------:|-----------:|-----------:|:-----------------|:-------------------------|------------:|
| depth_heat | bd_depth_m       |     0.36  |     0.319 |      0.409 |      0.367 |      0.372 | lower = more H2  | yes                      |         0   |
| structures | d_shear          |     0.41  |     0.359 |      0.465 |      0.404 |      0.435 | lower = more H2  | yes                      |         0   |
| structures | d_thrust         |     0.418 |     0.373 |      0.469 |      0.465 |      0.383 | lower = more H2  | yes                      |         0   |
| structures | d_fault_basement |     0.429 |     0.382 |      0.478 |      0.45  |      0.423 | lower = more H2  | yes                      |         0   |
| structures | d_fault_any      |     0.435 |     0.395 |      0.482 |      0.464 |      0.41  | lower = more H2  | yes                      |         0   |
| lithology  | f_QUAT           |     0.462 |     0.424 |      0.502 |      0.446 |      0.461 | lower = more H2  | yes                      |         0   |
| gravity    | wgm_ba           |     0.463 |     0.41  |      0.52  |      0.444 |      0.544 | lower = more H2  |                          |         0   |
| structures | tf_accretion     |     0.534 |     0.505 |      0.567 |      0.504 |      0.573 | higher = more H2 |                          |         0   |
| depth_heat | hf_median_50km   |     0.532 |     0.479 |      0.588 |      0.582 |      0.449 | higher = more H2 |                          |        18.1 |
| lithology  | f_SST            |     0.53  |     0.488 |      0.571 |      0.556 |      0.504 | higher = more H2 |                          |         0   |
| gravity    | g_res            |     0.528 |     0.477 |      0.578 |      0.495 |      0.57  | higher = more H2 |                          |         0   |
| lithology  | any_EVAP         |     0.479 |     0.448 |      0.511 |      0.498 |      0.462 | lower = more H2  |                          |         0   |
| lithology  | f_SH             |     0.48  |     0.436 |      0.521 |      0.444 |      0.538 | lower = more H2  |                          |         0   |
| lithology  | f_CARB           |     0.519 |     0.494 |      0.543 |      0.509 |      0.529 | higher = more H2 |                          |         0   |
| structures | d_neotectonic    |     0.485 |     0.431 |      0.543 |      0.429 |      0.592 | lower = more H2  |                          |         0   |
| structures | tf_rift          |     0.51  |     0.498 |      0.524 |      0.511 |      0.51  | higher = more H2 |                          |         0   |
| structures | d_um_rock        |     0.491 |     0.427 |      0.55  |      0.528 |      0.394 | lower = more H2  |                          |         0   |
| lithology  | f_MAF_V          |     0.507 |     0.499 |      0.518 |      0.513 |      0.5   | higher = more H2 |                          |         0   |
| lithology  | f_GRAN           |     0.505 |     0.499 |      0.512 |      0.509 |      0.5   | higher = more H2 |                          |         0   |
| lithology  | f_MSED           |     0.503 |     0.5   |      0.509 |      0.506 |      0.5   | higher = more H2 |                          |         0   |
| lithology  | f_VOLC           |     0.498 |     0.496 |      0.499 |      0.495 |      0.5   | lower = more H2  |                          |         0   |
| lithology  | lith_cover       |     0.502 |     0.484 |      0.52  |      0.51  |      0.486 | higher = more H2 |                          |         0   |
| lithology  | any_BIF          |     0.5   |     0.5   |      0.5   |      0.5   |      0.5   | higher = more H2 |                          |         0   |
| lithology  | f_GNS            |     0.5   |     0.5   |      0.5   |      0.5   |      0.5   | higher = more H2 |                          |         0   |
| lithology  | km2_UM_any       |     0.5   |     0.5   |      0.5   |      0.5   |      0.5   | higher = more H2 |                          |         0   |
| lithology  | km2_UM_main      |     0.5   |     0.5   |      0.5   |      0.5   |      0.5   | higher = more H2 |                          |         0   |
| lithology  | f_MAF_I          |     0.5   |     0.5   |      0.5   |      0.5   |      0.5   | higher = more H2 |                          |         0   |

## Medians of the inputs, H2-poor vs H2-rich cells

|                  |   median, H2-poor cells |   median, H2-rich cells |
|:-----------------|------------------------:|------------------------:|
| km2_UM_any       |                    0    |                    0    |
| km2_UM_main      |                    0    |                    0    |
| any_BIF          |                    0    |                    0    |
| any_EVAP         |                    0    |                    0    |
| f_GNS            |                    0    |                    0    |
| f_GRAN           |                    0    |                    0    |
| f_SST            |                    0.02 |                    0.04 |
| f_CARB           |                    0    |                    0    |
| f_SH             |                    0.31 |                    0.2  |
| f_QUAT           |                    0    |                    0    |
| f_MAF_V          |                    0    |                    0    |
| f_MAF_I          |                    0    |                    0    |
| f_VOLC           |                    0    |                    0    |
| f_MSED           |                    0    |                    0    |
| lith_cover       |                    1    |                    1    |
| d_fault_basement |                  176.36 |                  140.84 |
| d_fault_any      |                   51.73 |                   37.32 |
| d_neotectonic    |                  233.55 |                  230.08 |
| d_thrust         |                  241.3  |                  193.03 |
| d_shear          |                  448.84 |                  309.14 |
| d_um_rock        |                  312.6  |                  311.62 |
| tf_rift          |                    0    |                    0    |
| tf_accretion     |                    0    |                    0    |
| g_res            |                   -0.2  |                    1.21 |
| wgm_ba           |                   57.7  |                   44.4  |
| bd_depth_m       |                 3300    |                 2500    |
| hf_median_50km   |                   53    |                   53    |

