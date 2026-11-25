# Redi iron ore mine - results
_Generated 2026-11-25 by 06_summary.py from the outputs of steps 2-5._

## 1. Data quality (step 2)
NDVI from Landsat Collection 2 Level-2 surface reflectance (scale 0.0000275, offset -0.2), cloud/shadow/water masked with QA_PIXEL. Landsat 7 values harmonized to OLI (Roy et al. 2016). The last column shows what NDVI would be without the scale factor, for comparison.

| date | sensor | SLC-off gaps % | cloud/shadow % | usable land % | median NDVI | NDVI if unscaled |
|---|---|---|---|---|---|---|
| 20120102 | ETM+ | 24.3 | 0.0 | 41.8 | 0.58 | 0.229 |
| 20120118 | ETM+ | 23.6 | 0.0 | 41.9 | 0.582 | 0.226 |
| 20120219 | ETM+ | 24.0 | 0.0 | 41.1 | 0.516 | 0.197 |
| 20120306 | ETM+ | 23.2 | 19.8 | 23.5 | 0.412 | 0.164 |
| 20131214 | OLI | 0.0 | 0.0 | 55.2 | 0.637 | 0.264 |
| 20140131 | OLI | 0.0 | 0.0 | 55.1 | 0.58 | 0.232 |
| 20230108 | OLI | 0.0 | 0.0 | 55.9 | 0.624 | 0.249 |
| 20230217 | OLI | 0.0 | 0.0 | 55.2 | 0.588 | 0.231 |

## 2. Disturbed area inside the mine boundary (step 3)
Analysis area: hand-digitized `mine_complex` polygon minus coast/creek = 405.5 ha. Disturbed = NDVI below threshold, plus pit lakes. Bare = disturbed minus pit-lake water.

| NDVI threshold | year | disturbed ha | bare ha | pit-lake ha |
|---|---|---|---|---|
| 0.15 | 2012 | 23.4 | 3.9 | 19.5 |
| 0.15 | 2014 | 65.5 | 42.8 | 22.7 |
| 0.15 | 2023 | 22.6 | 22.6 | 0.0 |
| 0.2 | 2012 | 68.9 | 49.4 | 19.5 |
| 0.2 | 2014 | 92.7 | 70.0 | 22.7 |
| 0.2 | 2023 | 43.6 | 43.6 | 0.0 |
| 0.25 | 2012 | 113.0 | 93.5 | 19.5 |
| 0.25 | 2014 | 114.2 | 91.1 | 23.1 |
| 0.25 | 2023 | 62.1 | 61.6 | 0.5 |
| 0.3 | 2012 | 141.8 | 122.0 | 19.8 |
| 0.3 | 2014 | 132.7 | 109.6 | 23.1 |
| 0.3 | 2023 | 72.5 | 72.0 | 0.5 |

### Change classes

| NDVI threshold | period | newly disturbed ha | recovered ha | stayed disturbed ha | net ha | net ha/yr |
|---|---|---|---|---|---|---|
| 0.15 | 2012-2023 | 22.0 | 22.9 | 0.5 | -0.8 | -0.07 |
| 0.15 | 2012-2014 | 45.2 | 3.1 | 20.3 | 42.1 | 21.05 |
| 0.15 | 2014-2023 | 5.0 | 47.9 | 17.6 | -42.9 | -4.77 |
| 0.2 | 2012-2023 | 15.5 | 40.9 | 28.1 | -25.4 | -2.31 |
| 0.2 | 2012-2014 | 34.2 | 10.4 | 58.5 | 23.8 | 11.9 |
| 0.2 | 2014-2023 | 6.5 | 55.6 | 37.1 | -49.1 | -5.46 |
| 0.25 | 2012-2023 | 10.1 | 61.0 | 52.0 | -50.9 | -4.63 |
| 0.25 | 2012-2014 | 16.6 | 15.4 | 97.6 | 1.2 | 0.6 |
| 0.25 | 2014-2023 | 6.6 | 58.7 | 55.5 | -52.1 | -5.79 |
| 0.3 | 2012-2023 | 12.2 | 81.4 | 60.3 | -69.2 | -6.29 |
| 0.3 | 2012-2014 | 11.9 | 21.0 | 120.8 | -9.1 | -4.55 |
| 0.3 | 2014-2023 | 9.3 | 69.4 | 63.3 | -60.1 | -6.68 |

### Notes

- Total disturbed area (bare + pit lakes) is smaller in 2023 than 2012 at thresholds: 0.15, 0.2, 0.25, 0.3 (of 0.15, 0.2, 0.25, 0.3).
- Bare ground alone is LARGER in 2023 than 2012 at thresholds: 0.15 - i.e. the most intensely bare surface (the active pit) grew even where the wider disturbed zone shrank.
- 'Recovered' only means NDVI rose above the threshold. In the imagery much of it looks like planting around old pits rather than natural forest.

## 3. Vegetation around the mine (step 4)
Median NDVI change in distance rings outside the mine boundary; 'excess' = change minus the 2-3 km control ring.

| comparison | ring | ha | dNDVI | excess vs control | % lost >0.1 | % gained >0.1 |
|---|---|---|---|---|---|---|
| composite_2012_vs_2023 | 0-250 m | 233.7 | 0.011 | -0.024 | 4.5 | 8.5 |
| composite_2012_vs_2023 | 250-500 m | 232.8 | 0.018 | -0.017 | 4.7 | 8.9 |
| composite_2012_vs_2023 | 500-1000 m | 440.5 | 0.019 | -0.016 | 6.6 | 10.9 |
| composite_2012_vs_2023 | 1000-2000 m | 836.1 | 0.026 | -0.009 | 5.0 | 11.7 |
| composite_2012_vs_2023 | 2000-3000 m (control) | 1221.2 | 0.035 | 0.0 | 1.9 | 11.8 |
| composite_2012_vs_2014 | 0-250 m | 233.7 | 0.032 | -0.003 | 0.7 | 7.6 |
| composite_2012_vs_2014 | 250-500 m | 232.3 | 0.028 | -0.007 | 1.2 | 2.0 |
| composite_2012_vs_2014 | 500-1000 m | 434.4 | 0.019 | -0.016 | 5.3 | 3.9 |
| composite_2012_vs_2014 | 1000-2000 m | 821.4 | 0.023 | -0.012 | 5.3 | 4.7 |
| composite_2012_vs_2014 | 2000-3000 m (control) | 1221.8 | 0.035 | 0.0 | 1.3 | 5.2 |
| scene_19Feb2012_vs_17Feb2023 | 0-250 m | 184.2 | 0.071 | 0.006 | 1.5 | 30.7 |
| scene_19Feb2012_vs_17Feb2023 | 250-500 m | 173.3 | 0.068 | 0.003 | 2.9 | 26.1 |
| scene_19Feb2012_vs_17Feb2023 | 500-1000 m | 317.8 | 0.063 | -0.002 | 4.4 | 28.3 |
| scene_19Feb2012_vs_17Feb2023 | 1000-2000 m | 597.5 | 0.059 | -0.006 | 3.6 | 25.9 |
| scene_19Feb2012_vs_17Feb2023 | 2000-3000 m (control) | 910.6 | 0.065 | 0.0 | 1.9 | 23.9 |

## 4. Terrain and DEM change (step 5)
NASADEM = Feb 2000 (mining paused 1992-2010); Copernicus GLO-30 = 2011-15. Both are surface models (include canopy). Changes under 10 m are treated as noise.

| zone | ha | mean elev 2000 m | max m | mean slope deg | % slope >15deg | median DEM change m |
|---|---|---|---|---|---|---|
| mine_complex | 405.5 | 33.4 | 82.7 | 6.4 | 5.0 | 1.7 |
| disturbed_2012 | 68.9 | 37.3 | 82.7 | 7.8 | 11.1 | -2.8 |
| disturbed_2023 | 43.6 | 33.8 | 80.7 | 8.2 | 14.3 | -6.1 |
| newly_disturbed_2012_2023 | 15.5 | 28.4 | 64.7 | 7.6 | 12.8 | -5.2 |
| recovered_2012_2023 | 40.9 | 37.6 | 82.7 | 7.2 | 8.4 | -0.7 |
| ring_0_1000m | 1192.0 | 13.6 | 71.8 | 3.7 | 0.9 | 0.8 |

| type | ha | mean change m | max change m | volume Mm3 (indicative) |
|---|---|---|---|---|
| lowered (excavation) | 27.5 | -20.2 | 39.3 | -5.57 |
| raised (dumps) | 13.0 | 19.1 | 40.7 | 2.49 |
| lowered (excavation) | 5.8 | -21.0 | 32.7 | -1.23 |
| raised (dumps) | 1.4 | 12.0 | 15.6 | 0.17 |
| lowered (excavation) | 1.1 | -16.6 | 23.5 | -0.18 |

Reported (not measured): IBM inspection report, 21 Nov 2024 - Redi Block I working levels +30 m to -74 m (2023-24); approved ultimate pit -90 m RL (pre-feasibility report).
