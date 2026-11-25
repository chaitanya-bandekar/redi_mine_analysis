"""
04_ndvi_rings.py  -  Redi Iron Ore Mine recheck, step 4
========================================================
Did vegetation AROUND the mine change differently from vegetation further away?

Method
------
1. Distance rings measured outward from the `mine_complex` polygon edge
   (the polygon itself is excluded - inside it is step 3's job):
      0-250 m, 250-500 m, 500-1000 m, 1000-2000 m, 2000-3000 m (= control)
2. Only pixels with clear, valid NDVI in BOTH years are used (sea, creek,
   pit lakes and clouds drop out automatically).
3. For each ring: median NDVI per year, median change (dNDVI), and the share of
   pixels that lost or gained more than CHANGE_T (0.10 NDVI).
4. "Excess change" = ring change minus control-ring change. This removes the
   landscape-wide trend (rainfall timing, plantation growth, sensor) so what is
   left is the part that varies with distance from the mine.
5. Sensitivity check: the same numbers from the single best-matched scene pair
   (19 Feb 2012 vs 17 Feb 2023, two days apart in the season).

Outputs (data\\processed\\rings\\):
  rings.tif                 ring id (1-5), 0 = outside, 255 = mine polygon
  rings.geojson             ring outlines (add to ArcGIS Pro)
  dndvi_2012_2023.tif       NDVI change per pixel (composites)
  ring_stats.csv            the results table (both comparisons)
  ring_plot.png             change vs distance chart

RUN:  python "G:\\G I S\\Redi_Mine_2\\Redi_mining_PY\\04_ndvi_rings.py"
Needs: numpy, scipy, rasterio, matplotlib (all in uhi_py). Reads mine_complex
from Redi_mining_PY.gdb with arcpy (or pyogrio+shapely if arcpy is absent).
"""

import csv
import glob
import json
import os
import sys

import numpy as np
import rasterio
from rasterio import features
from rasterio.warp import transform_geom
from scipy import ndimage

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
PROC = os.path.join(ROOT, "data", "processed")
OUT = os.path.join(PROC, "rings")
GDB = os.path.join(ROOT, "Redi_mining_PY.gdb")
MINE_LAYER = "mine_complex"

RINGS = [(0, 250), (250, 500), (500, 1000), (1000, 2000), (2000, 3000)]   # last = control
CHANGE_T = 0.10
NODATA = -9999.0

COMPARISONS = {
    # name : (before file, after file)
    "composite_2012_vs_2023": ("ndvi_2012.tif", "ndvi_2023.tif"),
    "composite_2012_vs_2014": ("ndvi_2012.tif", "ndvi_2014.tif"),
    "scene_19Feb2012_vs_17Feb2023": ("ndvi_scenes/LE07_L2SP_147049_20120219_02_T1_ndvi.tif",
                                     "ndvi_scenes/LC09_L2SP_147049_20230217_02_T1_ndvi.tif"),
}


# ---------------------------------------------------------------- helpers
def _xy_only(c):
    if isinstance(c[0], (int, float)):
        return [c[0], c[1]]
    return [_xy_only(x) for x in c]


def read_mine_complex():
    try:
        import arcpy
        fc = os.path.join(GDB, MINE_LAYER)
        if not arcpy.Exists(fc):
            sys.exit(f"{fc} not found - digitize mine_complex first (step 3).")
        out = []
        with arcpy.da.SearchCursor(fc, ["SHAPE@"]) as cur:
            for (shp,) in cur:
                gi = shp.__geo_interface__
                out.append({"type": gi["type"], "coordinates": _xy_only(gi["coordinates"])})
        return out
    except ImportError:
        import pyogrio
        import shapely
        _, _, wkb, _ = pyogrio.raw.read(GDB, layer=MINE_LAYER)
        return [shapely.geometry.mapping(shapely.force_2d(g)) for g in shapely.from_wkb(wkb)]


def load(rel):
    with rasterio.open(os.path.join(PROC, rel)) as s:
        a = s.read(1).astype("float64")
        a[a == NODATA] = np.nan
        return a, s.profile


def write_tif(path, arr, prof, dtype, nodata):
    p = dict(prof, dtype=dtype, nodata=nodata, count=1, compress="deflate", driver="GTiff")
    with rasterio.open(path, "w", **p) as d:
        d.write(arr.astype(dtype), 1)


def ring_stats(before, after, ring_id):
    rows = []
    for k, (r0, r1) in enumerate(RINGS, start=1):
        m = (ring_id == k) & ~np.isnan(before) & ~np.isnan(after)
        if m.sum() == 0:
            continue
        d = after[m] - before[m]
        rows.append({
            "ring": f"{r0}-{r1} m" + (" (control)" if k == len(RINGS) else ""),
            "pixels": int(m.sum()), "area_ha": round(m.sum() * 0.09, 1),
            "ndvi_before_median": round(float(np.median(before[m])), 3),
            "ndvi_after_median": round(float(np.median(after[m])), 3),
            "dndvi_median": round(float(np.median(d)), 3),
            "dndvi_mean": round(float(np.mean(d)), 3),
            "pct_loss_gt_0.1": round(100 * float(np.mean(d < -CHANGE_T)), 1),
            "pct_gain_gt_0.1": round(100 * float(np.mean(d > CHANGE_T)), 1),
        })
    ctrl = rows[-1]["dndvi_median"]
    for r in rows:
        r["excess_dndvi_vs_control"] = round(r["dndvi_median"] - ctrl, 3)
    return rows


# ---------------------------------------------------------------- main
def main():
    os.makedirs(OUT, exist_ok=True)
    base, prof = load("ndvi_2012.tif")
    T = prof["transform"]
    shape = base.shape

    mine = features.rasterize([(g, 1) for g in read_mine_complex()], out_shape=shape,
                              transform=T, fill=0, dtype="uint8").astype(bool)
    dist = ndimage.distance_transform_edt(~mine) * abs(T.a)      # metres to polygon edge

    ring_id = np.zeros(shape, "uint8")
    for k, (r0, r1) in enumerate(RINGS, start=1):
        ring_id[(dist > r0) & (dist <= r1) & ~mine] = k
    ring_out = np.where(mine, 255, ring_id)
    write_tif(os.path.join(OUT, "rings.tif"), ring_out, prof, "uint8", 255)

    # ring outlines for ArcGIS Pro
    feats = []
    for geom, val in features.shapes(ring_id, mask=ring_id > 0, transform=T):
        k = int(val)
        feats.append({"type": "Feature", "geometry": transform_geom(prof["crs"], "EPSG:4326", geom),
                      "properties": {"ring_id": k, "ring": f"{RINGS[k-1][0]}-{RINGS[k-1][1]} m"}})
    with open(os.path.join(OUT, "rings.geojson"), "w") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f)

    all_rows = []
    for name, (b, a) in COMPARISONS.items():
        if not (os.path.exists(os.path.join(PROC, b)) and os.path.exists(os.path.join(PROC, a))):
            print(f"  skip {name}: input missing")
            continue
        before, _ = load(b)
        after, _ = load(a)
        rows = ring_stats(before, after, ring_id)
        for r in rows:
            r["comparison"] = name
        all_rows += rows
        if name == "composite_2012_vs_2023":
            write_tif(os.path.join(OUT, "dndvi_2012_2023.tif"),
                      np.where(np.isnan(after - before), NODATA, after - before), prof, "float32", NODATA)

        print(f"\n== {name}")
        print(f"  {'ring':22s} {'area ha':>8s} {'NDVI before':>11s} {'after':>6s} {'change':>7s} "
              f"{'excess vs ctrl':>14s} {'%lost>0.1':>9s} {'%gain>0.1':>9s}")
        for r in rows:
            print(f"  {r['ring']:22s} {r['area_ha']:8.0f} {r['ndvi_before_median']:11.3f} "
                  f"{r['ndvi_after_median']:6.3f} {r['dndvi_median']:+7.3f} {r['excess_dndvi_vs_control']:+14.3f} "
                  f"{r['pct_loss_gt_0.1']:9.1f} {r['pct_gain_gt_0.1']:9.1f}")

    cols = ["comparison", "ring", "pixels", "area_ha", "ndvi_before_median", "ndvi_after_median",
            "dndvi_median", "dndvi_mean", "excess_dndvi_vs_control", "pct_loss_gt_0.1", "pct_gain_gt_0.1"]
    with open(os.path.join(OUT, "ring_stats.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(all_rows)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        mids = [(r0 + r1) / 2 for r0, r1 in RINGS]
        fig, ax = plt.subplots(figsize=(7, 4))
        for name in COMPARISONS:
            ys = [r["dndvi_median"] for r in all_rows if r["comparison"] == name]
            if len(ys) == len(mids):
                ax.plot(mids, ys, marker="o", label=name.replace("_", " "))
        ax.axhline(0, color="grey", lw=0.8)
        ax.set_xlabel("distance from mine boundary (m, ring midpoint)")
        ax.set_ylabel("median NDVI change")
        ax.set_title("NDVI change vs distance from the Redi mine")
        ax.legend(fontsize=8)
        fig.savefig(os.path.join(OUT, "ring_plot.png"), dpi=130, bbox_inches="tight")
        print("\n  ring_plot.png written")
    except Exception as e:  # noqa
        print(f"  (no plot: {e})")
    print(f"\nDone. Outputs in {OUT}")


if __name__ == "__main__":
    main()
