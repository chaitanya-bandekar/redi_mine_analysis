"""
02_preprocess_ndvi.py  -  Redi Iron Ore Mine recheck, step 2
=============================================================
Turns the clipped Landsat Collection 2 Level-2 bands from step 1 into clean NDVI.

For every scene:
  1. Scale DN -> surface reflectance:  refl = DN * 0.0000275 - 0.2
     (Collection 2 Level-2 values; skipping this biases NDVI badly because the
      -0.2 offset does NOT cancel in the NDVI ratio)
  2. Mask: fill / Landsat-7 SLC-off stripes, cloud, dilated cloud, cirrus,
     cloud shadow, snow (QA_PIXEL bits 0-5), water (bit 7), and any reflectance
     outside 0-1.
  3. Landsat 7 only: convert ETM+ red/NIR to OLI-equivalent reflectance
     (Roy et al. 2016, RSE 185:57-70, OLS ETM+->OLI coefficients) so 2012 and
     2023 come from comparable sensors.  Set HARMONIZE = False to switch off.
  4. NDVI = (NIR - Red) / (NIR + Red)

Then per epoch it builds a median composite:
  * 2012 : median of 02-Jan, 18-Jan, 19-Feb; remaining gaps filled from 06-Mar
           (06-Mar is ~20% cloud and later in the dry season, so it is gap-fill only)
  * 2014 : median of 14-Dec-2013, 31-Jan-2014   (Landsat 8 cross-check)
  * 2023 : median of 08-Jan, 17-Feb

Outputs (data\\processed\\):
  ndvi_scenes\\<scene>_ndvi.tif   per-scene NDVI  (NoData = -9999)
  ndvi_2012.tif, ndvi_2014.tif, ndvi_2023.tif      composites
  nobs_2012.tif ...                                 clear observations per pixel
  water_2023.tif                                    water mask (1 = water)
  qc_scenes.csv                                     per-scene quality numbers
  quicklook_ndvi.png                                3-panel preview

RUN (Python Command Prompt):
  python "G:\\G I S\\Redi_Mine_2\\Redi_mining_PY\\02_preprocess_ndvi.py"
Uses rasterio if installed, otherwise arcpy. numpy is required (ships with ArcGIS Pro).
"""

import csv
import glob
import os
import sys

import numpy as np

# ---------------------------------------------------------------- settings
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
CLIP = os.path.join(ROOT, "data", "clip", "landsat")
OUT = os.path.join(ROOT, "data", "processed")
NODATA = -9999.0
SCALE, OFFSET = 2.75e-05, -0.2
HARMONIZE = True
# Roy et al. 2016 OLS ETM+ -> OLI (surface reflectance): OLI = a + b * ETM
ROY_RED = (0.0061, 0.9047)
ROY_NIR = (0.0412, 0.8462)

EPOCHS = {
    # name : (primary scene dates, gap-fill-only dates)
    "2012": (["20120102", "20120118", "20120219"], ["20120306"]),
    "2014": (["20131214", "20140131"], []),
    "2023": (["20230108", "20230217"], []),
}

# QA_PIXEL bits (Collection 2)
B_FILL, B_DILATED, B_CIRRUS, B_CLOUD, B_SHADOW, B_SNOW, B_WATER = 0, 1, 2, 3, 4, 5, 7


# ---------------------------------------------------------------- raster I/O
try:
    import rasterio
    BACKEND = "rasterio"
except ImportError:
    import arcpy
    BACKEND = "arcpy"


def read(path):
    """Return (array, georef) where georef is whatever write() needs."""
    if BACKEND == "rasterio":
        with rasterio.open(path) as src:
            return src.read(1), src.profile
    r = arcpy.Raster(path)
    arr = arcpy.RasterToNumPyArray(r, nodata_to_value=0)
    ref = {"x": r.extent.XMin, "y": r.extent.YMin, "cw": r.meanCellWidth,
           "ch": r.meanCellHeight, "sr": r.spatialReference}
    return arr, ref


def write(path, arr, ref, dtype="float32", nodata=NODATA):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    arr = arr.astype(dtype)
    if BACKEND == "rasterio":
        prof = dict(ref, dtype=dtype, count=1, nodata=nodata, compress="deflate", driver="GTiff")
        with rasterio.open(path, "w", **prof) as dst:
            dst.write(arr, 1)
        return
    if os.path.exists(path):
        arcpy.management.Delete(path)
    ras = arcpy.NumPyArrayToRaster(arr, arcpy.Point(ref["x"], ref["y"]), ref["cw"], ref["ch"], nodata)
    ras.save(path)
    arcpy.management.DefineProjection(path, ref["sr"])


# ---------------------------------------------------------------- core
def bit(q, b):
    return ((q >> b) & 1).astype(bool)


def scene_ndvi(folder):
    sid = os.path.basename(folder)
    red_dn, ref = read(os.path.join(folder, f"{sid}_red.tif"))
    nir_dn, _ = read(os.path.join(folder, f"{sid}_nir08.tif"))
    qa, _ = read(os.path.join(folder, f"{sid}_qa_pixel.tif"))
    red_dn = red_dn.astype("float64")
    nir_dn = nir_dn.astype("float64")
    qa = qa.astype("uint16")

    fill = (red_dn == 0) | (nir_dn == 0) | bit(qa, B_FILL)
    cloud = bit(qa, B_DILATED) | bit(qa, B_CIRRUS) | bit(qa, B_CLOUD) | bit(qa, B_SHADOW) | bit(qa, B_SNOW)
    water = bit(qa, B_WATER) & ~fill

    red = red_dn * SCALE + OFFSET
    nir = nir_dn * SCALE + OFFSET
    is_l7 = sid.startswith("LE07")
    if is_l7 and HARMONIZE:
        red = ROY_RED[0] + ROY_RED[1] * red
        nir = ROY_NIR[0] + ROY_NIR[1] * nir
    bad_refl = (red < 0) | (red > 1) | (nir < 0) | (nir > 1)

    good = ~fill & ~cloud & ~water & ~bad_refl
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = (nir - red) / (nir + red)
        ndvi_raw = (nir_dn - red_dn) / (nir_dn + red_dn)     # the WRONG way, kept only for the QC table
    ndvi = np.where(good, ndvi, np.nan)

    qc = {
        "scene_id": sid, "date": sid[17:25], "sensor": "ETM+" if is_l7 else "OLI",
        "fill_stripes_pct": round(100 * fill.mean(), 1),
        "cloud_shadow_pct": round(100 * (cloud & ~fill).mean(), 1),
        "water_pct": round(100 * water.mean(), 1),
        "usable_land_pct": round(100 * good.mean(), 1),
        "median_ndvi_correct": round(float(np.nanmedian(ndvi)), 3),
        "median_ndvi_no_scale_factor": round(float(np.nanmedian(np.where(good, ndvi_raw, np.nan))), 3),
        "harmonized_to_OLI": bool(is_l7 and HARMONIZE),
    }
    return ndvi, water, ref, qc


def main():
    print(f"I/O backend: {BACKEND}   root: {ROOT}")
    folders = sorted(glob.glob(os.path.join(CLIP, "*", "*")))
    if not folders:
        sys.exit(f"No clipped scenes found under {CLIP} - run step 1 first.")

    scenes, qcs, ref, water_by_date = {}, [], None, {}
    for f in folders:
        ndvi, water, ref, qc = scene_ndvi(f)
        scenes[qc["date"]] = ndvi
        water_by_date[qc["date"]] = water
        qcs.append(qc)
        write(os.path.join(OUT, "ndvi_scenes", f"{qc['scene_id']}_ndvi.tif"),
              np.where(np.isnan(ndvi), NODATA, ndvi), ref)
        print(f"  {qc['date']} {qc['sensor']:5s} usable {qc['usable_land_pct']:5.1f}%  "
              f"NDVI {qc['median_ndvi_correct']:.3f} (no-scale would be {qc['median_ndvi_no_scale_factor']:.3f})")

    with open(os.path.join(OUT, "qc_scenes.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(qcs[0]))
        w.writeheader()
        w.writerows(qcs)

    composites = {}
    for name, (primary, fillers) in EPOCHS.items():
        missing = [d for d in primary + fillers if d not in scenes]
        if missing:
            print(f"  !! {name}: missing scenes {missing} - skipped")
            continue
        stack = np.stack([scenes[d] for d in primary])
        nobs = np.sum(~np.isnan(stack), axis=0)
        with np.errstate(all="ignore"):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                comp = np.nanmedian(stack, axis=0)
        for d in fillers:
            gap = np.isnan(comp) & ~np.isnan(scenes[d])
            comp[gap] = scenes[d][gap]
            nobs = nobs + gap
        composites[name] = comp
        write(os.path.join(OUT, f"ndvi_{name}.tif"), np.where(np.isnan(comp), NODATA, comp), ref)
        write(os.path.join(OUT, f"nobs_{name}.tif"), nobs, ref, dtype="int16", nodata=-1)
        print(f"  composite {name}: median NDVI {np.nanmedian(comp):.3f}, "
              f"no clear data on {100*np.isnan(comp).mean():.1f}% of pixels (sea/water mostly)")

    # water mask from the clear 2023 scenes (sea, creeks, pit lakes)
    w23 = water_by_date.get("20230108", 0) | water_by_date.get("20230217", 0)
    write(os.path.join(OUT, "water_2023.tif"), np.asarray(w23).astype("uint8"), ref, dtype="uint8", nodata=255)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, len(composites), figsize=(5 * len(composites), 5))
        for ax, (name, comp) in zip(np.atleast_1d(axes), composites.items()):
            im = ax.imshow(comp, vmin=0, vmax=0.9, cmap="RdYlGn")
            ax.set_title(f"NDVI {name} (dry season)")
            ax.axis("off")
        fig.colorbar(im, ax=axes, shrink=0.7, label="NDVI")
        fig.savefig(os.path.join(OUT, "quicklook_ndvi.png"), dpi=130, bbox_inches="tight")
        print("  quicklook_ndvi.png written")
    except Exception as e:  # noqa
        print(f"  (no quicklook: {e})")

    print(f"\nDone. Outputs in {OUT}")


if __name__ == "__main__":
    main()
