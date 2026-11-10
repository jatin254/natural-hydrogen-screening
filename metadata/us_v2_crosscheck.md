# Rules v2 candidates: cross-half check

Sanity check: v1.2 expected-score AUC on all cells = 0.515 (full Monte Carlo result was 0.517; these should be close).

Candidates come from the diagnosis of ALL US wells, so the held-out half is not fully independent. A success here justifies an independent test; it is not proof.

## Result

| fitted on   | tested on   | chosen                                      |   chosen AUC (test half) |   v1.2 AUC (test half) |   thin-sediment baseline (test half) | success   |
|:------------|:------------|:--------------------------------------------|-------------------------:|-----------------------:|-------------------------------------:|:----------|
| west        | east        | cover:thin-seal:drop-preservation:no_faults |                    0.625 |                  0.565 |                                0.628 | no        |
| east        | west        | cover:thin-seal:drop-preservation:drop      |                    0.566 |                  0.469 |                                0.633 | no        |

Success needs, in BOTH directions, test-half AUC >= 0.6 and >= 0.03 above the thin-sediment baseline.

## All candidates (expected scores)

| candidate                                   |   AUC west |   AUC east |
|:--------------------------------------------|-----------:|-----------:|
| cover:thin-seal:drop-preservation:drop      |      0.566 |      0.644 |
| cover:keep-seal:drop-preservation:drop      |      0.556 |      0.632 |
| cover:thin-seal:drop-preservation:no_faults |      0.567 |      0.625 |
| cover:thin-seal:drop-preservation:keep      |      0.564 |      0.625 |
| cover:keep-seal:drop-preservation:no_faults |      0.556 |      0.612 |
| cover:keep-seal:drop-preservation:keep      |      0.553 |      0.612 |
| cover:thin-seal:keep-preservation:drop      |      0.493 |      0.601 |
| cover:keep-seal:keep-preservation:drop      |      0.474 |      0.586 |
| cover:thin-seal:keep-preservation:no_faults |      0.494 |      0.582 |
| cover:thin-seal:keep-preservation:keep      |      0.489 |      0.582 |
| cover:keep-seal:keep-preservation:keep      |      0.469 |      0.565 |
| cover:keep-seal:keep-preservation:no_faults |      0.475 |      0.565 |

## Dilution check: median gas composition (mol%) and depth (ft), all analysed samples

If H2-rich samples carry far less methane (C1) and more N2/He, part of the 'thin sediment' signal is dilution: thick basins make so much methane that hydrogen's share stays small.

|       |   H2-poor (< 0.5%) |   H2-rich (>= 0.5%) |   samples with a value |
|:------|-------------------:|--------------------:|-----------------------:|
| C1    |              84.57 |               73.1  |                   3930 |
| C2    |               4.6  |                2.6  |                   3843 |
| N2    |               2.9  |                7.25 |                   3909 |
| HE    |               0.1  |                0.14 |                   3649 |
| CO2   |               0.4  |                0.6  |                   3424 |
| DEPTH |            4992    |             3869    |                   3629 |

