"""
06_summary.py  -  Redi Iron Ore Mine recheck, step 6
=====================================================
Collects the results of steps 2-5 into:
  outputs\\results_summary.md     all key numbers in one place (paste into a report)
  outputs\\summary_figure.png     4-panel figure for the README / portfolio
  data\\vector\\mine_complex.geojson  the digitized mine boundary (GitHub previews it as a map)

RUN:  python "G:\\G I S\\Redi_Mine_2\\Redi_mining_PY\\06_summary.py"
"""

import csv
import json
import os
import sys
from datetime import date

import numpy as np

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
PROC = os.path.join(ROOT, "data", "processed")
OUTD = os.path.join(ROOT, "outputs")
GDB = os.path.join(ROOT, "Redi_mining_PY.gdb")
MAIN_T = 0.2


def rcsv(rel):
    with open(os.path.join(PROC, rel), newline="") as f:
        return list(csv.DictReader(f))


def md_table(rows, cols, headers=None):
    headers = headers or cols
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(out)


def export_mine_geojson():
    """Write mine_complex as WGS84 GeoJSON (GitHub renders it as a map)."""
    from rasterio.warp import transform_geom
    try:
        import arcpy
        geoms = []
        with arcpy.da.SearchCursor(os.path.join(GDB, "mine_complex"), ["SHAPE@"]) as cur:
            for (shp,) in cur:
                gi = shp.__geo_interface__
                strip = lambda c: [c[0], c[1]] if isinstance(c[0], (int, float)) else [strip(x) for x in c]  # noqa
                geoms.append({"type": gi["type"], "coordinates": strip(gi["coordinates"])})
    except ImportError:
        import pyogrio
        import shapely
        _, _, wkb, _ = pyogrio.raw.read(GDB, layer="mine_complex")
        geoms = [shapely.geometry.mapping(shapely.force_2d(g)) for g in shapely.from_wkb(wkb)]
    feats = [{"type": "Feature", "properties": {"name": "mine_complex",
                                                "note": "hand-digitized mining area (pit, dumps, old workings)"},
              "geometry": transform_geom("EPSG:32643", "EPSG:4326", g)} for g in geoms]
    os.makedirs(os.path.join(ROOT, "data", "vector"), exist_ok=True)
    with open(os.path.join(ROOT, "data", "vector", "mine_complex.geojson"), "w") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f)


def main():
    os.makedirs(OUTD, exist_ok=True)
    qc = rcsv("qc_scenes.csv")
    foot = rcsv("footprint/footprint_areas.csv")
    chg = rcsv("footprint/change_areas.csv")
    rings = rcsv("rings/ring_stats.csv")
    terr = rcsv("terrain/terrain_stats.csv")
    dem = rcsv("terrain/dem_change_patches.csv") if os.path.exists(
        os.path.join(PROC, "terrain", "dem_change_patches.csv")) else []

    for r in foot:
        r["bare_ha"] = round(float(r["disturbed_ha"]) - float(r["of_which_pit_lake_ha"]), 1)
    zone_ha = foot[0]["zone_ha"]

    # ---------------- results_summary.md
    L = ["# Redi iron ore mine - results",
         f"_Generated {date.today().isoformat()} by 06_summary.py from the outputs of steps 2-5._", ""]

    L += ["## 1. Data quality (step 2)",
          "NDVI from Landsat Collection 2 Level-2 surface reflectance (scale 0.0000275, offset -0.2), "
          "cloud/shadow/water masked with QA_PIXEL. Landsat 7 values harmonized to OLI (Roy et al. 2016). "
          "The last column shows what NDVI would be without the scale factor, for comparison.", "",
          md_table(qc, ["date", "sensor", "fill_stripes_pct", "cloud_shadow_pct", "usable_land_pct",
                        "median_ndvi_correct", "median_ndvi_no_scale_factor"],
                   ["date", "sensor", "SLC-off gaps %", "cloud/shadow %", "usable land %",
                    "median NDVI", "NDVI if unscaled"]), ""]

    L += [f"## 2. Disturbed area inside the mine boundary (step 3)",
          f"Analysis area: hand-digitized `mine_complex` polygon minus coast/creek = {zone_ha} ha. "
          "Disturbed = NDVI below threshold, plus pit lakes. Bare = disturbed minus pit-lake water.", "",
          md_table(foot, ["threshold", "year", "disturbed_ha", "bare_ha", "of_which_pit_lake_ha"],
                   ["NDVI threshold", "year", "disturbed ha", "bare ha", "pit-lake ha"]), "",
          "### Change classes", "",
          md_table(chg, ["threshold", "period", "newly_disturbed_ha", "recovered_ha", "stable_disturbed_ha",
                         "net_change_ha", "net_change_ha_per_yr"],
                   ["NDVI threshold", "period", "newly disturbed ha", "recovered ha", "stayed disturbed ha",
                    "net ha", "net ha/yr"]), ""]

    # robustness statements generated from the numbers
    def fval(t, y, k):
        return next(float(r[k]) for r in foot if float(r["threshold"]) == t and r["year"] == y)
    ths = sorted({float(r["threshold"]) for r in foot})
    smaller = [t for t in ths if fval(t, "2023", "disturbed_ha") < fval(t, "2012", "disturbed_ha")]
    bare_up = [t for t in ths if fval(t, "2023", "bare_ha") > fval(t, "2012", "bare_ha")]
    L += ["### Notes", "",
          f"- Total disturbed area (bare + pit lakes) is smaller in 2023 than 2012 at thresholds: "
          f"{', '.join(str(t) for t in smaller) or 'none'} (of {', '.join(str(t) for t in ths)}).",
          f"- Bare ground alone is LARGER in 2023 than 2012 at thresholds: {', '.join(str(t) for t in bare_up) or 'none'} "
          "- i.e. the most intensely bare surface (the active pit) grew even where the wider disturbed zone shrank.",
          "- 'Recovered' only means NDVI rose above the threshold. In the imagery much of it looks like planting "
          "around old pits rather than natural forest.", ""]

    L += ["## 3. Vegetation around the mine (step 4)",
          "Median NDVI change in distance rings outside the mine boundary; 'excess' = change minus the 2-3 km control ring.", "",
          md_table(rings, ["comparison", "ring", "area_ha", "dndvi_median", "excess_dndvi_vs_control",
                           "pct_loss_gt_0.1", "pct_gain_gt_0.1"],
                   ["comparison", "ring", "ha", "dNDVI", "excess vs control", "% lost >0.1", "% gained >0.1"]), ""]

    L += ["## 4. Terrain and DEM change (step 5)",
          "NASADEM = Feb 2000 (mining paused 1992-2010); Copernicus GLO-30 = 2011-15. Both are surface models "
          "(include canopy). Changes under 10 m are treated as noise.", "",
          md_table(terr, ["zone", "area_ha", "elev2000_mean_m", "elev2000_max_m", "slope2000_mean_deg",
                          "pct_slope_gt_15deg", "dem_change_median_m"],
                   ["zone", "ha", "mean elev 2000 m", "max m", "mean slope deg", "% slope >15deg", "median DEM change m"]), ""]
    if dem:
        L += [md_table(dem, ["type", "area_ha", "mean_change_m", "max_abs_change_m", "volume_Mm3_indicative"],
                       ["type", "ha", "mean change m", "max change m", "volume Mm3 (indicative)"]), ""]
    L += ["Reported (not measured): IBM inspection report, 21 Nov 2024 - Redi Block I working levels +30 m to -74 m "
          "(2023-24); approved ultimate pit -90 m RL (pre-feasibility report).", ""]

    with open(os.path.join(OUTD, "results_summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("  outputs\\results_summary.md written")

    # ---------------- summary figure
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    import matplotlib.patches as mp
    import rasterio

    fig, axes = plt.subplots(2, 2, figsize=(13, 10))
    # (a) change map
    with rasterio.open(os.path.join(PROC, "footprint", "change_2012_2023.tif")) as s:
        c = s.read(1).astype(float)
    c[c == 255] = np.nan
    rr, cc = np.where(~np.isnan(c))
    c = c[rr.min():rr.max() + 1, cc.min():cc.max() + 1]
    cols = ["#d9ead3", "#d7191c", "#1a9641", "#7f6000"]
    ax = axes[0, 0]
    ax.imshow(c, cmap=ListedColormap(cols), vmin=1, vmax=4, interpolation="nearest")
    ax.set_title(f"(a) Disturbance change 2012 -> 2023 (NDVI < {MAIN_T})")
    ax.axis("off")
    ax.legend(handles=[mp.Patch(color=k, label=l) for k, l in
                       zip(cols, ["stable vegetation", "newly disturbed", "recovered", "stayed disturbed"])],
              fontsize=8, loc="lower left")
    # (b) area by year and threshold
    ax = axes[0, 1]
    years = ["2012", "2014", "2023"]
    for t in ths:
        ax.plot(years, [fval(t, y, "disturbed_ha") for y in years], marker="o", label=f"disturbed, NDVI<{t}")
    ax.plot(years, [fval(MAIN_T, y, "bare_ha") for y in years], marker="s", ls="--", color="k",
            label=f"bare only, NDVI<{MAIN_T}")
    ax.set_ylabel("hectares inside mine boundary")
    ax.set_title("(b) Disturbed area by year (threshold sensitivity)")
    ax.legend(fontsize=7)
    # (c) rings
    ax = axes[1, 0]
    for comp in dict.fromkeys(r["comparison"] for r in rings):
        rs = [r for r in rings if r["comparison"] == comp]
        ax.plot(range(len(rs)), [float(r["excess_dndvi_vs_control"]) for r in rs], marker="o",
                label=comp.replace("_", " "))
    ax.set_xticks(range(len(rs)))
    ax.set_xticklabels([r["ring"].replace(" (control)", "\n(control)") for r in rs], fontsize=8)
    ax.axhline(0, color="grey", lw=0.8)
    ax.set_ylim(-0.1, 0.1)          # same scale as a meaningful NDVI change, so noise is not exaggerated
    ax.axhspan(-0.05, 0.05, color="grey", alpha=0.08, label="|change| < 0.05 (within noise)")
    ax.set_ylabel("NDVI change minus control ring")
    ax.set_title("(c) Vegetation change vs distance from mine boundary")
    ax.legend(fontsize=7)
    # (d) profile from step 5
    ax = axes[1, 1]
    prof_png = os.path.join(PROC, "terrain", "profile.png")
    if os.path.exists(prof_png):
        ax.imshow(plt.imread(prof_png))
    ax.axis("off")
    ax.set_title("(d) Terrain profile: 2000 vs 2011-15 DEM, IBM-reported pit floor")
    fig.suptitle("Redi iron ore mine, Vengurla (Sindhudurg) - Landsat & DEM analysis 2000-2023", fontsize=13)
    fig.tight_layout()
    fig.savefig(os.path.join(OUTD, "summary_figure.png"), dpi=130, bbox_inches="tight")
    print("  outputs\\summary_figure.png written")

    try:
        export_mine_geojson()
        print("  data\\vector\\mine_complex.geojson written")
    except Exception as e:  # noqa
        print(f"  (mine_complex.geojson not written: {e})")
    print("\nDone.")


if __name__ == "__main__":
    main()
