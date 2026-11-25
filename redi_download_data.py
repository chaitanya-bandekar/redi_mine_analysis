"""
Redi Iron Ore Mine - data download script (Step 1 of the recheck)
==================================================================
Downloads everything needed to recheck the "Mining Expansion & Environmental
Impact" project. All sources are free and need NO account:

  * Landsat Collection 2 Level-2 (surface reflectance) - Microsoft Planetary Computer
      - 2012 baseline : Landsat 7 ETM+ (SLC-off, striped) dry season Dec 2011 - Mar 2012
      - 2014 fallback : Landsat 8 OLI dry season Dec 2013 - Mar 2014 (first clean dry season)
      - 2023 recent   : Landsat 8/9 OLI dry season Dec 2022 - Mar 2023
    Bands: red, nir08, qa_pixel (+ the MTL metadata for scale factors / dates)
  * NASADEM (reprocessed SRTM, Feb 2000)  - Planetary Computer
  * Copernicus GLO-30 DEM (2011-2015)     - AWS Open Data

HOW TO RUN (Windows, ArcGIS Pro installed):
  1. Put this file in your project folder, e.g. C:\\...\\Redi_Recheck\\
  2. Open "Python Command Prompt" from the ArcGIS start-menu folder
  3. cd to that folder and run:   python redi_download_data.py
  It only uses the Python standard library, so any Python 3.8+ works too.
  If arcpy is available it also clips every raster to the study area
  (originals are kept in data\\raw\\, clips go to data\\clip\\).

Re-running is safe: files that already exist are skipped.
"""

import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------- settings
# Study area: ~5.5 km around the Block-I working pit (IBM 2024 report coords,
# pit centre ~15.743 N, 73.679 E). Includes the coastline to the west.
BBOX_WGS84 = [73.62, 15.69, 73.74, 15.80]            # minLon, minLat, maxLon, maxLat
CLIP_UTM43N = "352000 1735000 365100 1747400"        # same box in EPSG:32643 (for arcpy)

MAX_CLOUD = 30          # % scene cloud cover allowed
EPOCHS = {
    # name           : (date range,                           platforms,                      scenes to keep)
    "2012_L7":  ("2011-12-01/2012-03-31", ["landsat-7"],               4),  # several -> fill SLC-off gaps
    "2014_L8":  ("2013-12-01/2014-03-31", ["landsat-8"],               2),
    "2023_L89": ("2022-12-01/2023-03-31", ["landsat-8", "landsat-9"],  2),
}
BANDS = ["red", "nir08", "qa_pixel"]

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
SAS = "https://planetarycomputer.microsoft.com/api/sas/v1/token/{}"
COP_DEM = ("https://copernicus-dem-30m.s3.amazonaws.com/"
           "Copernicus_DSM_COG_10_N15_00_E073_00_DEM/"
           "Copernicus_DSM_COG_10_N15_00_E073_00_DEM.tif")

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "data", "raw")
CLIP = os.path.join(ROOT, "data", "clip")
UA = {"User-Agent": "redi-recheck/1.0"}


# ---------------------------------------------------------------- helpers
def http_json(url, body=None, tries=4):
    data = json.dumps(body).encode() if body is not None else None
    hdr = dict(UA, **({"Content-Type": "application/json"} if data else {}))
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=hdr)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # noqa
            if i == tries - 1:
                raise
            print(f"   retry ({e})")
            time.sleep(3 * (i + 1))


_tokens = {}
def sign(href, collection):
    if collection not in _tokens:
        _tokens[collection] = http_json(SAS.format(collection))["token"]
    return href + ("&" if "?" in href else "?") + _tokens[collection]


def download(url, dest, tries=4):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print(f"   [skip] {os.path.basename(dest)}")
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
                total = int(r.headers.get("Content-Length", 0))
                got = 0
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if total:
                        sys.stdout.write(f"\r   {os.path.basename(dest)}  {got/1e6:6.1f}/{total/1e6:.1f} MB")
                        sys.stdout.flush()
            os.replace(tmp, dest)
            print()
            return dest
        except Exception as e:  # noqa
            print(f"\n   retry {i+1} ({e})")
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"failed: {url}")


def stac_search(collection, datetime=None, extra=None, limit=100):
    body = {"collections": [collection], "bbox": BBOX_WGS84, "limit": limit}
    if datetime:
        body["datetime"] = datetime
    if extra:
        body.update(extra)
    return http_json(STAC + "/search", body).get("features", [])


# ---------------------------------------------------------------- Landsat
def get_landsat(manifest):
    for epoch, (dt, platforms, keep) in EPOCHS.items():
        print(f"\n== Landsat {epoch}  ({dt})")
        items = stac_search("landsat-c2-l2", dt,
                            {"query": {"eo:cloud_cover": {"lt": MAX_CLOUD},
                                       "platform": {"in": platforms}}})
        # prefer the clearest scenes; tie-break by date
        items.sort(key=lambda it: (it["properties"].get("eo:cloud_cover", 100),
                                   it["properties"]["datetime"]))
        print(f"   {len(items)} candidate scenes <{MAX_CLOUD}% cloud; keeping {min(keep, len(items))}")
        if not items:
            print("   !! none found - widen the date range or MAX_CLOUD")
        for it in items[:keep]:
            p = it["properties"]
            sid = it["id"]
            print(f" - {sid}  {p['datetime'][:10]}  cloud {p.get('eo:cloud_cover')}%  {p['platform']}")
            folder = os.path.join(RAW, "landsat", epoch, sid)
            for b in BANDS:
                href = it["assets"][b]["href"]
                download(sign(href, "landsat-c2-l2"), os.path.join(folder, f"{sid}_{b}.tif"))
            for meta_key in ("mtl.txt", "mtl.json"):
                if meta_key in it["assets"]:
                    download(sign(it["assets"][meta_key]["href"], "landsat-c2-l2"),
                             os.path.join(folder, f"{sid}_MTL.{meta_key.split('.')[-1]}"))
                    break
            with open(os.path.join(folder, f"{sid}_stac.json"), "w") as f:
                json.dump(it, f, indent=1)
            manifest.append({
                "epoch": epoch, "scene_id": sid, "date": p["datetime"][:10],
                "platform": p["platform"], "cloud_cover": p.get("eo:cloud_cover"),
                "sun_elevation": p.get("view:sun_elevation"),
                "wrs_path_row": f"{p.get('landsat:wrs_path')}/{p.get('landsat:wrs_row')}",
                "folder": os.path.relpath(folder, ROOT),
            })


# ---------------------------------------------------------------- DEMs
def get_dems(manifest):
    print("\n== DEMs")
    items = stac_search("nasadem")
    if items:
        it = items[0]
        dest = os.path.join(RAW, "dem", f"{it['id']}_NASADEM.tif")
        download(sign(it["assets"]["elevation"]["href"], "nasadem"), dest)
        manifest.append({"epoch": "DEM", "scene_id": it["id"], "date": "2000-02",
                         "platform": "NASADEM (SRTM)", "folder": os.path.relpath(os.path.dirname(dest), ROOT)})
    else:
        print("   !! NASADEM not found")
    dest = os.path.join(RAW, "dem", "Copernicus_GLO30_N15_E073.tif")
    download(COP_DEM, dest)
    manifest.append({"epoch": "DEM", "scene_id": "Copernicus_GLO30_N15_E073", "date": "2011-2015",
                     "platform": "Copernicus GLO-30", "folder": os.path.relpath(os.path.dirname(dest), ROOT)})


# ---------------------------------------------------------------- optional clip
def clip_with_arcpy():
    try:
        import arcpy
    except ImportError:
        print("\n(arcpy not found - skipping clip; full rasters are in data\\raw)")
        return
    print("\n== Clipping to study area with arcpy")
    arcpy.env.overwriteOutput = False
    utm = arcpy.SpatialReference(32643)
    for dirpath, _, files in os.walk(RAW):
        for fn in files:
            if not fn.endswith(".tif"):
                continue
            src = os.path.join(dirpath, fn)
            out = os.path.join(CLIP, os.path.relpath(src, RAW))
            if os.path.exists(out):
                continue
            os.makedirs(os.path.dirname(out), exist_ok=True)
            sr = arcpy.Describe(src).spatialReference
            try:
                if sr.factoryCode == 32643:
                    arcpy.management.Clip(src, CLIP_UTM43N, out, "#", "#", "NONE", "NO_MAINTAIN_EXTENT")
                else:   # DEMs come in WGS84 -> clip in their own CRS
                    rect = " ".join(str(v) for v in BBOX_WGS84)
                    arcpy.management.Clip(src, rect, out, "#", "#", "NONE", "NO_MAINTAIN_EXTENT")
                print(f"   clipped {fn}")
            except Exception as e:  # noqa
                print(f"   !! clip failed for {fn}: {e}")


# ---------------------------------------------------------------- main
def main():
    os.makedirs(RAW, exist_ok=True)
    manifest = []
    get_landsat(manifest)
    get_dems(manifest)
    keys = sorted({k for row in manifest for k in row})
    with open(os.path.join(ROOT, "data", "download_manifest.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(manifest)
    clip_with_arcpy()
    print("\nDone. See data\\download_manifest.csv for what was downloaded.")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        print(f"\nHTTP error {e.code} on {e.url}\n{e.read()[:300]}")
        sys.exit(1)
