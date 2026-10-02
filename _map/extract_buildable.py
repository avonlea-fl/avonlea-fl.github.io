#!/usr/bin/env python3
"""Trace each lot's buildable area from scans of the recorded plat.

The plat shades the buildable area of every lot with a dot pattern. This
script lines each plat sheet up with the county's parcel lines, finds the
dotted regions, and writes them to data/buildable.geojson for build_map.py.

Usage (see README.md for how to get the sheet images):

    python3 extract_buildable.py "Plat Book 10, Page 195" sheet-3.png sheet-4.png ...

Pass only the detail sheets drawn at 1 inch = 60 feet and scanned at 400 dpi.
Run it once per plat; lots already in data/buildable.geojson from another plat
are kept. Needs numpy, opencv-python-headless and shapely.

Replats that give the buildable area by bearings and distances instead of a
dot pattern are entered by hand in REPLATS and applied at the end of every
run. With no arguments the script only applies them.
"""
import json
import math
import os
import sys

import cv2
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "buildable.geojson")

# Same local projection as build_map.py: metres, x east and y south.
LON0, LAT0 = -81.9837413, 29.0516860
K = math.cos(math.radians(LAT0))


def to_m(p):
    return ((p[0] - LON0) * 111320 * K, -(p[1] - LAT0) * 110574)


def to_ll(m):
    return [round(LON0 + m[0] / (111320 * K), 7), round(LAT0 - m[1] / 110574, 7)]


M_PER_PX = 60 * 0.3048 / 400         # 1 inch = 60 ft, scanned at 400 dpi
DS = 8                               # downscale used to match sheet to parcels
G = M_PER_PX * DS                    # metres per matching pixel
X0, Y0, X1, Y1 = -520.0, -760.0, 640.0, 760.0   # extent of the parcel raster

with open(os.path.join(HERE, "data", "parcels.geojson")) as fh:
    PARCELS = {f["properties"]["PARCEL"]: [to_m(p) for p in f["geometry"]["coordinates"][0]]
               for f in json.load(fh)["features"]}


# Buildable areas redrawn by a later replat, entered from its dimensions.
# "tie" runs from the named corner of the county parcel to the first point of
# the traverse; "basis" is the plat bearing of the lot's north boundary, used
# to turn plat bearings into map directions. Bearings are (N/S, deg, min, sec,
# E/W) and distances are in feet.
REPLATS = {
    "19": {
        "source": "Plat Book 15, Page 16",
        "parcel": "39393-000-19",
        "corner": "NE",
        "basis": ("S", 89, 39, 20, "E"),
        "tie": (("S", 71, 19, 8, "W"), 153.38),
        "traverse": [
            (("S", 0, 20, 40, "W"), 196.47),
            (("N", 89, 39, 20, "W"), 258.28),
            (("N", 0, 20, 40, "E"), 117.39),
            (("N", 56, 25, 56, "W"), 10.00),
            (("N", 33, 34, 4, "E"), 87.99),
            (("S", 89, 39, 20, "E"), 218.44),
        ],
    },
}
# build_map.py's metres run about 0.2% short of ground distance.
LOCAL_PER_FT = 0.3048 * 0.998


def azimuth(b):
    """Quadrant bearing to degrees clockwise from north."""
    ns, d, m, sec, ew = b
    a = d + m / 60 + sec / 3600
    return {"NE": a, "SE": 180 - a, "SW": 180 + a, "NW": 360 - a}[ns + ew]


def replat_feature(lot, r):
    ring = PARCELS[r["parcel"]][:-1]
    # North-east corner of the county parcel, and the bearing of its north
    # boundary there, give the position and rotation of the plat's figure.
    i = max(range(len(ring)), key=lambda j: ring[j][0] - ring[j][1])
    ne = ring[i]
    west = min((ring[i - 1], ring[(i + 1) % len(ring)]), key=lambda p: abs(p[1] - ne[1]))
    county_az = math.degrees(math.atan2(ne[0] - west[0], -(ne[1] - west[1])))
    turn = county_az - azimuth(r["basis"])

    def step(p, leg):
        a = math.radians(azimuth(leg[0]) + turn)
        return (p[0] + leg[1] * LOCAL_PER_FT * math.sin(a), p[1] - leg[1] * LOCAL_PER_FT * math.cos(a))

    pts = [step(ne, r["tie"])]
    feet = [(0.0, 0.0)]
    for leg in r["traverse"]:
        pts.append(step(pts[-1], leg))
        a = math.radians(azimuth(leg[0]))
        feet.append((feet[-1][0] + leg[1] * math.sin(a), feet[-1][1] + leg[1] * math.cos(a)))
    gap = math.hypot(*feet[-1])
    assert gap < 0.1, f"lot {lot} replat traverse does not close ({gap:.2f} ft)"
    sqft = abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(feet, feet[1:]))) / 2
    pts[-1] = pts[0]
    return {
        "type": "Feature",
        "properties": {"LOT": lot, "ACRES": round(sqft / 43560, 2), "SOURCE": r["source"]},
        "geometry": {"type": "Polygon", "coordinates": [[to_ll(p) for p in pts]]},
    }


def parcel_raster():
    img = np.zeros((int((Y1 - Y0) / G), int((X1 - X0) / G)), np.uint8)
    for ring in PARCELS.values():
        pts = np.array([[(x - X0) / G, (y - Y0) / G] for x, y in ring], np.int32)
        cv2.polylines(img, [pts], True, 255, 1, cv2.LINE_AA)
    return cv2.GaussianBlur(img, (0, 0), 2.0)


def register(lab, stats, shape):
    """Affine transform from sheet pixels to local metres.

    The sheet's long solid lines (lot lines, rights-of-way) are matched
    against the county parcel lines: first by position, then with a small
    search over scale and rotation to absorb scanning and projection error.
    """
    H, W = shape
    w, h = stats[:, cv2.CC_STAT_WIDTH], stats[:, cv2.CC_STAT_HEIGHT]
    keep = np.zeros(len(stats), np.uint8)
    keep[1:][np.maximum(w, h)[1:] > 500] = 255
    small = cv2.resize(keep[lab], (W // DS, H // DS), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), 2.0)
    sh, sw = small.shape
    # Blank the sheet border and title block so only the drawing is matched.
    small[:, : int(0.08 * sw)] = 0
    small[: int(0.12 * sh), :] = 0
    small[int(0.96 * sh):, :] = 0
    small[:, int(0.965 * sw):] = 0

    pad = 400
    big = cv2.copyMakeBorder(parcel_raster(), pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0).astype(np.float32)
    _, _, _, loc = cv2.minMaxLoc(cv2.matchTemplate(big, small.astype(np.float32), cv2.TM_CCORR_NORMED))

    m = 24
    region = big[loc[1] - m: loc[1] + sh + m, loc[0] - m: loc[0] + sw + m]
    best = (-1,)
    for scale in np.arange(0.990, 1.0101, 0.001):
        for rot in np.arange(-0.5, 0.501, 0.1):
            M = cv2.getRotationMatrix2D((sw / 2, sh / 2), rot, scale)
            t = cv2.warpAffine(small, M, (sw, sh)).astype(np.float32)
            _, v, _, l = cv2.minMaxLoc(cv2.matchTemplate(region, t, cv2.TM_CCORR_NORMED))
            if v > best[0]:
                best = (v, M, l[0] - m, l[1] - m, scale, rot)
    score, M, dx, dy, scale, rot = best
    A = np.array([[M[0, 0] / DS, M[0, 1] / DS, M[0, 2] + loc[0] - pad + dx],
                  [M[1, 0] / DS, M[1, 1] / DS, M[1, 2] + loc[1] - pad + dy]]) * G
    A[0, 2] += X0
    A[1, 2] += Y0
    print(f"  matched to parcel lines: score {score:.2f}, scale {scale:.3f}, rotation {rot:+.1f} deg")
    return A


def stipple_regions(stats, cent, shape):
    """Outlines, in sheet pixels, of the areas filled with the dot pattern."""
    H, W = shape
    area, w, h = stats[:, cv2.CC_STAT_AREA], stats[:, cv2.CC_STAT_WIDTH], stats[:, cv2.CC_STAT_HEIGHT]
    cand = (area >= 4) & (area <= 60) & (w <= 10) & (h <= 10)
    med = float(np.median(area[cand]))       # the pattern's dots dominate the small marks
    dots = np.where(cand & (area >= 0.62 * med) & (area <= 1.6 * med) & (w >= 3) & (h >= 3))[0]

    q = 4
    pts = np.zeros((H // q + 1, W // q + 1), np.uint8)
    pts[(cent[dots, 1] / q).astype(int), (cent[dots, 0] / q).astype(int)] = 1
    # A dot counts only with others around it, which rejects full stops and
    # degree signs in the lettering.
    dens = cv2.boxFilter(pts.astype(np.float32), -1, (15, 15), normalize=False)
    mask = np.where((pts > 0) & (dens >= 5), 255, 0).astype(np.uint8)

    def k(shape_, n):
        return cv2.getStructuringElement(shape_, (n, n))

    mask = cv2.dilate(mask, k(cv2.MORPH_ELLIPSE, 13))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k(cv2.MORPH_ELLIPSE, 61))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k(cv2.MORPH_RECT, 29))
    mask = cv2.erode(mask, k(cv2.MORPH_ELLIPSE, 7))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in contours:
        if cv2.contourArea(c) * (q * M_PER_PX) ** 2 < 800:    # legend swatch or noise
            continue
        out.append([(x * q, y * q) for x, y in cv2.approxPolyDP(c, 6.0, True)[:, 0, :]])
    return out


def sheet_polygons(path):
    print(path)
    src = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    ink = (src < 128).astype(np.uint8)
    _, lab, stats, cent = cv2.connectedComponentsWithStats(ink, connectivity=8)
    A = register(lab, stats, ink.shape)
    polys = []
    for region in stipple_regions(stats, cent, ink.shape):
        g = Polygon([(A[0, 0] * x + A[0, 1] * y + A[0, 2], A[1, 0] * x + A[1, 1] * y + A[1, 2]) for x, y in region]).buffer(0)
        if g.area > 0:
            polys.append(g)
    print(f"  {len(polys)} buildable areas")
    return polys


def main():
    source, sheets = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else (None, [])
    polys = [g for path in sheets for g in sheet_polygons(path)]
    # Areas cut by a sheet's match line appear on two sheets; join them.
    merged = unary_union(polys)
    geoms = [g for g in getattr(merged, "geoms", [merged]) if not g.is_empty]

    lots = {k[-2:]: Polygon(r) for k, r in PARCELS.items() if k.startswith("39393-000-") and not k.endswith("-00")}
    found = []
    for g in geoms:
        # The dots stop about a metre short of the dashed outline.
        g = Polygon(g.exterior).simplify(1.2).buffer(1.0, join_style=2, mitre_limit=3)
        # Lettering on the plat interrupts the dots and leaves shallow notches.
        # Nearly convex areas take their convex hull; the rest are simplified.
        hull = g.convex_hull
        g = hull.simplify(1.5) if hull.area / g.area < 1.035 else g.simplify(1.8)
        c = g.representative_point()
        # Lot 22 has no county polygon (see README), so an area outside every
        # county lot is lot 22.
        lot = next((n for n, poly in lots.items() if poly.contains(c)), "22")
        found.append([lot, g])
    # County parcel 17 holds lots 17 (south) and 18 (north); 33 holds 32 and 33.
    for parcel, north in (("17", "18"), ("33", "32")):
        pair = sorted((f for f in found if f[0] == parcel), key=lambda f: f[1].centroid.y)
        if len(pair) == 2:
            pair[0][0] = north

    features = []
    if os.path.exists(OUT):
        with open(OUT) as fh:
            new = {str(int(lot)) for lot, _ in found}
            features = [f for f in json.load(fh)["features"] if f["properties"]["LOT"] not in new]
    for lot, g in found:
        features.append({
            "type": "Feature",
            "properties": {"LOT": str(int(lot)), "ACRES": round(g.area / 4046.86, 2), "SOURCE": source},
            "geometry": {"type": "Polygon", "coordinates": [[to_ll(p) for p in g.exterior.coords]]},
        })
    features = [f for f in features if f["properties"]["LOT"] not in REPLATS]
    features += [replat_feature(lot, r) for lot, r in REPLATS.items()]
    features.sort(key=lambda f: int(f["properties"]["LOT"]))
    with open(OUT, "w") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh)
    for f in features:
        print(f'  lot {f["properties"]["LOT"]:>2}: {f["properties"]["ACRES"]:.2f} ac  ({f["properties"]["SOURCE"]})')
    print(f"wrote {OUT}: {len(features)} areas")


if __name__ == "__main__":
    main()
