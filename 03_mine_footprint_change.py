"""
03_mine_footprint_change.py  -  Redi Iron Ore Mine recheck, step 3
===================================================================
Maps the mine-disturbed area for 2012 / 2014 / 2023 from the step-2 NDVI
composites and measures how it changed.

Method
------
1. Analysis area: the hand-digitized `mine_complex` polygon in the project
   geodatabase (pit, dumps, old workings; farmland north of the creek left out).
   If it is missing, falls back to a circle of SEARCH_RADIUS_M around the pit
   (centre of the IBM 2024 pit extent, UTM 43N 358437 E, 1740921 N).
2. Natural water (sea, Shiroda/Terekhol creek) = no-data areas that touch the
   image edge or are larger than BIG_WATER_HA. Everything within
   COAST_BUFFER_M of it is excluded so beach sand is not counted as mine.
3. Pit lakes = smaller no-data (water) patches inside the zone that are NOT
   natural water. They count as disturbed (a flooded pit is still a pit).
4. Disturbed = NDVI < threshold  OR  pit lake.  Patches smaller than
   MIN_PATCH_HA are dropped (single fields, roads, noise).
5. Change classes between two years:
      1 stable vegetation   2 newly disturbed   3 recovered   4 stable disturbed
6. Repeated at NDVI 0.15 / 0.20 / 0.25 / 0.30 so the result does not hang on
   one threshold. Main maps use MAIN_THRESHOLD.

All areas are pixel counts x 900 m2 (30 m Landsat pixels, UTM 43N), so they
are true ground areas - no Web Mercator distortion.

Outputs (data\\processed\\footprint\\):
  disturbed_<year>.tif            1 = bare/disturbed, 2 = pit lake, 0 = not, 255 = excluded
  change_2012_2023.tif (+2012_2014, 2014_2023)   classes 1-4 above
  disturbed_<year>.geojson        patches as polygons with area_ha (add to ArcGIS Pro)
  analysis_area.geojson           the area actually analysed
  footprint_areas.csv             areas per year x threshold
  change_areas.csv                change-class areas per period x threshold
  quicklook_change.png            preview

RUN:  python "G:\\G I S\\Redi_Mine_2\\Redi_mining_PY\\03_mine_footprint_change.py"
Needs: numpy, scipy, rasterio (all present in your uhi_py environment).
"""

import csv
import json
import os
import sys

import numpy as np
import rasterio
from rasterio import features
from rasterio.warp import transform_geom
from scipy import ndimage

# ---------------------------------------------------------------- settings
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
PROC = os.path.join(ROOT, "data", "processed")
OUT = os.path.join(PROC, "footprint")

GDB = os.path.join(ROOT, "Redi_mining_PY.gdb")
MINE_LAYER = "mine_complex"
PIT_CENTRE = (358437.0, 1740921.0)   # UTM 43N, centre of IBM 2024 working-pit extent
SEARCH_RADIUS_M = 2500
COAST_BUFFER_M = 150
BIG_WATER_HA = 50
MIN_PATCH_HA = 1.0
THRESHOLDS = [0.15, 0.20, 0.25, 0.30]
MAIN_THRESHOLD = 0.20
YEARS = ["2012", "2014", "2023"]
PERIODS = [("2012", "2023"), ("2012", "2014"), ("2014", "2023")]
PIX_HA = 0.09                         # 30 m x 30 m = 900 m2 = 0.09 ha
CLASS_NAMES = {1: "stable_vegetation", 2: "newly_disturbed", 3: "recovered", 4: "stable_disturbed"}


# ---------------------------------------------------------------- helpers
def load(year):
    with rasterio.open(os.path.join(PROC, f"ndvi_{year}.tif")) as s:
        a = s.read(1).astype("float64")
        a[a == s.nodata] = np.nan
        return a, s.profile


def natural_water(nan_mask):
    """No-data patches touching the edge or bigger than BIG_WATER_HA."""
    lab, n = ndimage.label(nan_mask)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    sizes = ndimage.sum(nan_mask, lab, index=np.arange(1, n + 1)) * PIX_HA
    big = {i + 1 for i, s in enumerate(sizes) if s >= BIG_WATER_HA}
    keep = np.array(sorted(edge | big), dtype=int)
    return np.isin(lab, keep) if keep.size else np.zeros_like(nan_mask)


def drop_small(mask, min_ha):
    lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if n == 0:
        return mask
    sizes = ndimage.sum(mask, lab, index=np.arange(1, n + 1)) * PIX_HA
    ok = np.concatenate([[False], sizes >= min_ha])
    return ok[lab]


def write_tif(path, arr, prof, dtype, nodata):
    p = dict(prof, dtype=dtype, nodata=nodata, count=1, compress="deflate", driver="GTiff")
    with rasterio.open(path, "w", **p) as d:
        d.write(arr.astype(dtype), 1)


def write_geojson(path, mask, prof, props_fn=None):
    feats = []
    for i, (geom, val) in enumerate(features.shapes(mask.astype("uint8"), mask=mask, transform=prof["transform"])):
        g = transform_geom(prof["crs"], "EPSG:4326", geom)
        # area from the UTM geometry (true metres)
        ring = np.array(geom["coordinates"][0])
        area = 0.5 * abs(np.dot(ring[:, 0], np.roll(ring[:, 1], 1)) - np.dot(ring[:, 1], np.roll(ring[:, 0], 1)))
        for hole in geom["coordinates"][1:]:
            h = np.array(hole)
            area -= 0.5 * abs(np.dot(h[:, 0], np.roll(h[:, 1], 1)) - np.dot(h[:, 1], np.roll(h[:, 0], 1)))
        props = {"patch_id": i + 1, "area_ha": round(area / 1e4, 2)}
        if props_fn:
            props.update(props_fn(geom))
        feats.append({"type": "Feature", "geometry": g, "properties": props})
    with open(path, "w") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f)
    return feats


def _xy_only(c):
    """Strip Z values from nested GeoJSON coordinate lists."""
    if isinstance(c[0], (int, float)):
        return [c[0], c[1]]
    return [_xy_only(x) for x in c]


def read_mine_complex():
    """Return list of GeoJSON-like geometries (UTM 43N) or None."""
    if not os.path.exists(GDB):
        return None
    try:                                   # 1) arcpy (always present with ArcGIS Pro)
        import arcpy
        fc = os.path.join(GDB, MINE_LAYER)
        if not arcpy.Exists(fc):
            return None
        sr = arcpy.Describe(fc).spatialReference
        if sr.factoryCode != 32643:
            sys.exit(f"{MINE_LAYER} must be in WGS 1984 UTM Zone 43N (found {sr.name})")
        geoms = []
        with arcpy.da.SearchCursor(fc, ["SHAPE@"]) as cur:
            for (shp,) in cur:
                gi = shp.__geo_interface__
                geoms.append({"type": gi["type"], "coordinates": _xy_only(gi["coordinates"])})
        return geoms
    except ImportError:
        pass
    try:                                   # 2) pyogrio + shapely
        import pyogrio
        import shapely
        meta, _, wkb, _ = pyogrio.raw.read(GDB, layer=MINE_LAYER)
        if meta["crs"] != "EPSG:32643":
            sys.exit(f"{MINE_LAYER} must be in EPSG:32643 (found {meta['crs']})")
        return [shapely.geometry.mapping(shapely.force_2d(g)) for g in shapely.from_wkb(wkb)]
    except Exception as e:  # noqa
        print(f"  (could not read {MINE_LAYER}: {e})")
        return None


# ---------------------------------------------------------------- main
def main():
    os.makedirs(OUT, exist_ok=True)
    ndvi, prof = {}, None
    for y in YEARS:
        ndvi[y], prof = load(y)
    T = prof["transform"]
    rows, cols = ndvi[YEARS[0]].shape
    xs = T.c + (np.arange(cols) + 0.5) * T.a
    ys = T.f + (np.arange(rows) + 0.5) * T.e
    X, Y = np.meshgrid(xs, ys)
    mine_geoms = read_mine_complex()
    if mine_geoms:
        zone = features.rasterize([(g, 1) for g in mine_geoms], out_shape=(rows, cols),
                                  transform=T, fill=0, dtype="uint8").astype(bool)
        print(f"Analysis area: {MINE_LAYER} polygon ({zone.sum()*PIX_HA:.0f} ha before coast mask)")
    else:
        zone = np.hypot(X - PIT_CENTRE[0], Y - PIT_CENTRE[1]) <= SEARCH_RADIUS_M
        print(f"Analysis area: {SEARCH_RADIUS_M} m circle (no {MINE_LAYER} polygon found)")

    # natural water = union over years (sea/creek don't move); coast buffer around it
    nat = np.zeros_like(zone)
    for y in YEARS:
        nat |= natural_water(np.isnan(ndvi[y]))
    dist_to_nat = ndimage.distance_transform_edt(~nat) * abs(T.a)
    coast_excl = nat | (dist_to_nat <= COAST_BUFFER_M)
    analysis = zone & ~coast_excl

    # zone polygon for reference
    write_geojson(os.path.join(OUT, "analysis_area.geojson"), analysis, prof)

    foot_rows, change_rows, disturbed_main = [], [], {}
    for thr in THRESHOLDS:
        dist = {}
        for y in YEARS:
            a = ndvi[y]
            pit_lake = np.isnan(a) & analysis
            bare = (a < thr) & analysis
            d = drop_small(bare | pit_lake, MIN_PATCH_HA)
            dist[y] = (d, pit_lake & d)
            foot_rows.append({
                "threshold": thr, "year": y,
                "disturbed_ha": round(d.sum() * PIX_HA, 1),
                "of_which_pit_lake_ha": round((pit_lake & d).sum() * PIX_HA, 1),
                "zone_ha": round(analysis.sum() * PIX_HA, 1),
            })
        for a_y, b_y in PERIODS:
            A, B = dist[a_y][0], dist[b_y][0]
            cls = np.zeros(A.shape, "uint8")
            cls[analysis & ~A & ~B] = 1
            cls[analysis & ~A & B] = 2
            cls[analysis & A & ~B] = 3
            cls[analysis & A & B] = 4
            row = {"threshold": thr, "period": f"{a_y}-{b_y}"}
            for k, nm in CLASS_NAMES.items():
                row[f"{nm}_ha"] = round((cls == k).sum() * PIX_HA, 1)
            row["net_change_ha"] = round((B.sum() - A.sum()) * PIX_HA, 1)
            yrs = int(b_y) - int(a_y)
            row["net_change_ha_per_yr"] = round(row["net_change_ha"] / yrs, 2)
            change_rows.append(row)
            if thr == MAIN_THRESHOLD:
                out = np.where(analysis, cls, 255)
                write_tif(os.path.join(OUT, f"change_{a_y}_{b_y}.tif"), out, prof, "uint8", 255)
        if thr == MAIN_THRESHOLD:
            disturbed_main = dist

    for y, (d, lake) in disturbed_main.items():
        arr = np.where(analysis, d.astype("uint8") + lake.astype("uint8"), 255)  # 0 / 1 bare / 2 pit lake
        write_tif(os.path.join(OUT, f"disturbed_{y}.tif"), arr, prof, "uint8", 255)
        feats = write_geojson(os.path.join(OUT, f"disturbed_{y}.geojson"), d, prof)
        print(f"  {y}: {len(feats)} disturbed patches written (NDVI < {MAIN_THRESHOLD})")

    for name, rows_ in (("footprint_areas.csv", foot_rows), ("change_areas.csv", change_rows)):
        with open(os.path.join(OUT, name), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows_[0]))
            w.writeheader()
            w.writerows(rows_)

    # console summary
    print(f"\nAnalysis area (minus coast/creek): {analysis.sum()*PIX_HA:.0f} ha")
    print("\nDisturbed area (ha)      " + "  ".join(f"NDVI<{t:.2f}" for t in THRESHOLDS))
    for y in YEARS:
        vals = [r["disturbed_ha"] for r in foot_rows if r["year"] == y]
        print(f"  {y}                   " + "  ".join(f"{v:9.1f}" for v in vals))
    print(f"\nChange 2012 -> 2023 at NDVI < {MAIN_THRESHOLD}:")
    r = next(r for r in change_rows if r["threshold"] == MAIN_THRESHOLD and r["period"] == "2012-2023")
    for k, nm in CLASS_NAMES.items():
        print(f"  {nm:20s} {r[nm + '_ha']:8.1f} ha")
    print(f"  net change           {r['net_change_ha']:8.1f} ha  ({r['net_change_ha_per_yr']:+.2f} ha/yr)")

    # quicklook
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import ListedColormap
        with rasterio.open(os.path.join(OUT, "change_2012_2023.tif")) as s:
            c = s.read(1).astype(float)
        c[c == 255] = np.nan
        r0, r1 = np.where(zone.any(1))[0][[0, -1]]
        c0, c1 = np.where(zone.any(0))[0][[0, -1]]
        cmap = ListedColormap(["#d9ead3", "#d7191c", "#1a9641", "#7f6000"])
        fig, ax = plt.subplots(figsize=(7, 7))
        ax.imshow(c[r0:r1 + 1, c0:c1 + 1], cmap=cmap, vmin=1, vmax=4, interpolation="nearest")
        ax.set_title(f"Mine disturbance change 2012 -> 2023 (NDVI < {MAIN_THRESHOLD})")
        ax.axis("off")
        import matplotlib.patches as mp
        ax.legend(handles=[mp.Patch(color=col, label=lab) for col, lab in
                           zip(cmap.colors, ["stable vegetation", "newly disturbed", "recovered", "stable disturbed"])],
                  loc="lower left", fontsize=8)
        fig.savefig(os.path.join(OUT, "quicklook_change.png"), dpi=130, bbox_inches="tight")
        print("\n  quicklook_change.png written")
    except Exception as e:  # noqa
        print(f"  (no quicklook: {e})")
    print(f"\nDone. Outputs in {OUT}")


if __name__ == "__main__":
    main()
