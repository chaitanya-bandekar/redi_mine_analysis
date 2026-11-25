"""
05_dem_terrain.py  -  Redi Iron Ore Mine recheck, step 5
=========================================================
Terrain context and DEM-based excavation / dump detection.

DEMs (both are surface models - they include tree canopy):
  * NASADEM  - reprocessed SRTM, flown Feb 2000. Mining at Redi was paused
               1992-2010, so this is the "before restart" surface.
  * Copernicus GLO-30 - TanDEM-X, acquired 2011-2015, i.e. a few years
               into the restart.
Neither can see the current pit floor (IBM reports -74 m RL in 2023-24);
water surfaces are flattened in Copernicus. So the DEMs describe the terrain
the mine was cut into and the first ~3-5 years of excavation - NOT pit depth.

Steps
-----
1. Reproject both DEMs onto the Landsat 30 m UTM 43N grid (bilinear).
2. Slope in degrees, computed in metres (no z-factor problem).
3. Terrain stats for the mine polygon, 2012 / 2023 disturbed areas, newly
   disturbed and recovered land (step 3) and the 0-1 km ring (step 4).
4. DEM difference (Copernicus - NASADEM). Noise is estimated OUTSIDE the
   mine (5th-95th percentile); only changes beyond +/-CHANGE_M are reported
   as excavation (lowered) or dumping (raised).
5. West-east profile through the deepest DEM point, with IBM-reported
   working levels drawn for reference (labelled as reported, not measured).

Outputs (data\\processed\\terrain\\):
  dem_nasadem_2000_utm.tif, dem_copernicus_2013_utm.tif
  slope_nasadem_2000.tif, dem_diff_cop_minus_nasa.tif
  terrain_stats.csv, dem_change_patches.csv
  profile.png, dem_diff_map.png

RUN:  python "G:\\G I S\\Redi_Mine_2\\Redi_mining_PY\\05_dem_terrain.py"
"""

import csv
import os
import sys

import numpy as np
import rasterio
from rasterio import features
from rasterio.warp import reproject, Resampling
from scipy import ndimage

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
PROC = os.path.join(DATA, "processed")
OUT = os.path.join(PROC, "terrain")
GDB = os.path.join(ROOT, "Redi_mining_PY.gdb")
MINE_LAYER = "mine_complex"
NODATA = -9999.0
CHANGE_M = 10.0          # report only DEM changes larger than this (m)
MIN_PATCH_HA = 1.0

# IBM inspection report, 21 Nov 2024 (Redi Block I, 2023-24): working levels
# +30 m to -74 m, pit extent E 358095-358732 / N 1740560-1741283 (UTM 43N).
IBM_TOP, IBM_BOTTOM = 30.0, -74.0
IBM_E = (358095.0, 358732.0)


def _xy_only(c):
    if isinstance(c[0], (int, float)):
        return [c[0], c[1]]
    return [_xy_only(x) for x in c]


def read_mine_complex():
    try:
        import arcpy
        out = []
        with arcpy.da.SearchCursor(os.path.join(GDB, MINE_LAYER), ["SHAPE@"]) as cur:
            for (shp,) in cur:
                gi = shp.__geo_interface__
                out.append({"type": gi["type"], "coordinates": _xy_only(gi["coordinates"])})
        return out
    except ImportError:
        import pyogrio
        import shapely
        _, _, wkb, _ = pyogrio.raw.read(GDB, layer=MINE_LAYER)
        return [shapely.geometry.mapping(shapely.force_2d(g)) for g in shapely.from_wkb(wkb)]


def to_grid(path, ref):
    with rasterio.open(path) as s:
        dst = np.full(ref.shape, np.nan, "float32")
        reproject(rasterio.band(s, 1), dst, src_nodata=s.nodata,
                  dst_transform=ref.transform, dst_crs=ref.crs,
                  resampling=Resampling.bilinear, dst_nodata=np.nan)
    dst[(dst < -100) | (dst > 3000)] = np.nan
    return dst


def slope_deg(dem, cell):
    gy, gx = np.gradient(dem, cell)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def write_tif(path, arr, prof):
    p = dict(prof, dtype="float32", nodata=NODATA, count=1, compress="deflate", driver="GTiff")
    with rasterio.open(path, "w", **p) as d:
        d.write(np.where(np.isnan(arr), NODATA, arr).astype("float32"), 1)


def read_mask(rel, values):
    path = os.path.join(PROC, rel)
    if not os.path.exists(path):
        return None
    with rasterio.open(path) as s:
        a = s.read(1)
    return np.isin(a, values)


def main():
    os.makedirs(OUT, exist_ok=True)
    ref = rasterio.open(os.path.join(PROC, "ndvi_2012.tif"))
    prof, T, cell = ref.profile, ref.transform, abs(ref.transform.a)

    nasa = to_grid(os.path.join(DATA, "clip", "dem", "NASADEM_HGT_n15e073_NASADEM.tif"), ref)
    cop = to_grid(os.path.join(DATA, "clip", "dem", "Copernicus_GLO30_N15_E073.tif"), ref)
    slope = slope_deg(nasa, cell)
    diff = cop - nasa
    for name, arr in (("dem_nasadem_2000_utm", nasa), ("dem_copernicus_2013_utm", cop),
                      ("slope_nasadem_2000", slope), ("dem_diff_cop_minus_nasa", diff)):
        write_tif(os.path.join(OUT, name + ".tif"), arr, prof)

    mine = features.rasterize([(g, 1) for g in read_mine_complex()], out_shape=ref.shape,
                              transform=T, fill=0, dtype="uint8").astype(bool)

    # ---- terrain stats per zone
    zones = {"mine_complex": mine,
             "disturbed_2012": read_mask("footprint/disturbed_2012.tif", [1, 2]),
             "disturbed_2023": read_mask("footprint/disturbed_2023.tif", [1, 2]),
             "newly_disturbed_2012_2023": read_mask("footprint/change_2012_2023.tif", [2]),
             "recovered_2012_2023": read_mask("footprint/change_2012_2023.tif", [3]),
             "ring_0_1000m": read_mask("rings/rings.tif", [1, 2, 3])}
    stats = []
    print(f"{'zone':28s} {'ha':>6s} {'elev2000 mean':>13s} {'min':>6s} {'max':>6s} "
          f"{'slope mean':>10s} {'%>15deg':>8s} {'DEM change median':>17s}")
    for z, m in zones.items():
        if m is None:
            continue
        ok = m & ~np.isnan(nasa)
        row = {"zone": z, "area_ha": round(ok.sum() * 0.09, 1),
               "elev2000_mean_m": round(float(np.nanmean(nasa[ok])), 1),
               "elev2000_min_m": round(float(np.nanmin(nasa[ok])), 1),
               "elev2000_max_m": round(float(np.nanmax(nasa[ok])), 1),
               "slope2000_mean_deg": round(float(np.nanmean(slope[ok])), 1),
               "pct_slope_gt_15deg": round(100 * float(np.mean(slope[ok] > 15)), 1),
               "dem_change_median_m": round(float(np.nanmedian(diff[ok])), 1)}
        stats.append(row)
        print(f"{z:28s} {row['area_ha']:6.0f} {row['elev2000_mean_m']:13.1f} {row['elev2000_min_m']:6.1f} "
              f"{row['elev2000_max_m']:6.1f} {row['slope2000_mean_deg']:10.1f} {row['pct_slope_gt_15deg']:8.1f} "
              f"{row['dem_change_median_m']:17.1f}")
    with open(os.path.join(OUT, "terrain_stats.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(stats[0]))
        w.writeheader()
        w.writerows(stats)

    # ---- DEM change: noise outside the mine, then excavation / dump patches
    outside = ~mine & ~np.isnan(diff) & ~np.isnan(nasa) & (nasa > 2)
    p5, p50, p95 = np.percentile(diff[outside], [5, 50, 95])
    print(f"\nDEM difference outside the mine (noise): median {p50:+.1f} m, 5-95% {p5:+.1f} to {p95:+.1f} m"
          f"  -> reporting only changes beyond +/-{CHANGE_M:.0f} m")
    patches = []
    for label, m in (("lowered (excavation)", mine & (diff < -CHANGE_M)),
                     ("raised (dumps)", mine & (diff > CHANGE_M))):
        lab, n = ndimage.label(m, structure=np.ones((3, 3)))
        for i in range(1, n + 1):
            pm = lab == i
            ha = pm.sum() * 0.09
            if ha < MIN_PATCH_HA:
                continue
            rr, cc = np.where(pm)
            xs, ys = rasterio.transform.xy(T, rr, cc)
            patches.append({"type": label, "area_ha": round(ha, 1),
                            "centre_E": round(float(np.mean(xs))), "centre_N": round(float(np.mean(ys))),
                            "mean_change_m": round(float(np.mean(diff[pm])), 1),
                            "max_abs_change_m": round(float(np.max(np.abs(diff[pm]))), 1),
                            "volume_Mm3_indicative": round(float(np.sum(diff[pm])) * cell * cell / 1e6, 2)})
    patches.sort(key=lambda p: -p["area_ha"])
    print(f"\n{'type':22s} {'ha':>6s} {'centre E':>9s} {'centre N':>10s} {'mean dz':>8s} {'max |dz|':>8s} {'vol Mm3':>8s}")
    for p in patches:
        print(f"{p['type']:22s} {p['area_ha']:6.1f} {p['centre_E']:9d} {p['centre_N']:10d} "
              f"{p['mean_change_m']:+8.1f} {p['max_abs_change_m']:8.1f} {p['volume_Mm3_indicative']:+8.2f}")
    if patches:
        with open(os.path.join(OUT, "dem_change_patches.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(patches[0]))
            w.writeheader()
            w.writerows(patches)

    # ---- figures
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        # profile through the lowest Copernicus point inside the mine
        c_in = np.where(mine, cop, np.nan)
        r_low, c_low = np.unravel_index(np.nanargmin(c_in), c_in.shape)
        _, y_line = rasterio.transform.xy(T, r_low, c_low)
        x0, x1 = 356600, 360200
        xs = np.arange(x0, x1, cell)
        cols = [rasterio.transform.rowcol(T, x, y_line)[1] for x in xs]
        fig, ax = plt.subplots(figsize=(9, 4.5))
        ax.plot(xs, nasa[r_low, cols], label="NASADEM (Feb 2000, before restart)", color="#1b7837")
        ax.plot(xs, cop[r_low, cols], label="Copernicus (2011-15)", color="#762a83")
        ax.axhline(0, color="#2166ac", lw=1, ls="--", label="mean sea level")
        ax.fill_between(IBM_E, IBM_BOTTOM, IBM_TOP, color="#b2182b", alpha=0.12,
                        label=f"IBM-reported working levels 2023-24 (+{IBM_TOP:.0f} to {IBM_BOTTOM:.0f} m)")
        ax.hlines(IBM_BOTTOM, *IBM_E, color="#b2182b", lw=2)
        ax.text(np.mean(IBM_E), IBM_BOTTOM - 6, f"reported pit floor {IBM_BOTTOM:.0f} m", ha="center",
                color="#b2182b", fontsize=8)
        inside = mine[r_low, cols]
        if inside.any():
            ax.axvspan(xs[inside][0], xs[inside][-1], color="grey", alpha=0.08, label="mine_complex")
        ax.set_xlabel("Easting, UTM 43N (m)")
        ax.set_ylabel("elevation (m, ~MSL)")
        ax.set_ylim(IBM_BOTTOM - 15, max(np.nanmax(nasa[r_low, cols]), np.nanmax(cop[r_low, cols])) + 15)
        ax.set_title(f"West-east profile at N {y_line:.0f} through the deepest DEM point in the mine")
        ax.legend(fontsize=7, loc="lower left")
        fig.savefig(os.path.join(OUT, "profile.png"), dpi=130, bbox_inches="tight")

        # difference map, cropped to the mine
        rr, cc = np.where(mine)
        pad = 20
        r0, r1 = max(rr.min() - pad, 0), rr.max() + pad
        c0, c1 = max(cc.min() - pad, 0), cc.max() + pad
        fig, ax = plt.subplots(figsize=(7, 6))
        im = ax.imshow(diff[r0:r1, c0:c1], cmap="RdBu", vmin=-30, vmax=30)
        ax.contour(mine[r0:r1, c0:c1], levels=[0.5], colors="k", linewidths=0.8)
        ax.set_title("Copernicus (2011-15) minus NASADEM (2000)\nblue = raised (dumps), red = lowered (excavation)")
        ax.axis("off")
        fig.colorbar(im, ax=ax, shrink=0.7, label="elevation change (m)")
        fig.savefig(os.path.join(OUT, "dem_diff_map.png"), dpi=130, bbox_inches="tight")
        print("\n  profile.png, dem_diff_map.png written")
    except Exception as e:  # noqa
        print(f"  (no figures: {e})")
    print(f"\nDone. Outputs in {OUT}")


if __name__ == "__main__":
    main()
