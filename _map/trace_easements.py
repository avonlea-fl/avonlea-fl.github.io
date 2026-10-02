#!/usr/bin/env python3
"""Write data/easements.geojson: conservation and drainage easements.

Unlike the buildable areas, the plats draw easements as plain dashed outlines,
so they cannot be picked out of the scans automatically. This script rebuilds
them from what the plats and later records say:

* Conservation Easements A and C are 60-foot strips along the subdivision
  boundary, built from the county parcel lines.
* Conservation Easements B and D are bounded by numbered lines whose bearings
  and distances are in the plat's line table (LINES below).
* Drainage easements are built from the bearings and distances on the plat
  where it gives them, and otherwise read off the plat sheets by eye.
* The additional conservation easements granted in 2008 and 2024 come from
  the St. Johns River Water Management District's map data
  (data/sjrwmd-easements.geojson).

Conservation Easement E (lot 24) and its two access easements were released
in 2024 (OR Book 8491, Page 168) and are deliberately left out.

Coordinates are build_map.py's local metres, x east and y south. Positions
read off the plat sheets are good to a metre or two. Needs shapely.
"""
import datetime
import json
import math
import os

from shapely.geometry import LineString, Polygon, box, shape
from shapely.ops import transform, unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

LON0, LAT0 = -81.9837413, 29.0516860
K = math.cos(math.radians(LAT0))
FT = 0.3048 * 0.997                  # plat feet to local metres


def to_m(x, y, z=None):
    return ((x - LON0) * 111320 * K, -(y - LAT0) * 110574)


def to_ll(x, y, z=None):
    return (round(LON0 + x / (111320 * K), 7), round(LAT0 - y / 110574, 7))


def azimuth(b):
    """'N26 11 15E' to degrees clockwise from north."""
    d, m, s = (float(v) for v in b[1:-1].split())
    a = d + m / 60 + s / 3600
    return {"NE": a, "SE": 180 - a, "SW": 180 + a, "NW": 360 - a}[b[0] + b[-1]]


def traverse(start, legs, rot=0.0):
    """Points reached from `start` by (bearing, feet) legs. A bearing with a
    leading '-' is walked backwards. `rot` turns plat north to map north."""
    pts = [start]
    for b, ft in legs:
        a = math.radians(azimuth(b.lstrip("-")) + (180 if b.startswith("-") else 0) + rot)
        pts.append((pts[-1][0] + ft * FT * math.sin(a), pts[-1][1] - ft * FT * math.cos(a)))
    return pts


with open(os.path.join(DATA, "parcels.geojson")) as fh:
    PARCELS = {f["properties"]["PARCEL"]: transform(to_m, shape(f["geometry"])) for f in json.load(fh)["features"]}
ROAD = PARCELS["39393-000-00"]
# Everything inside the subdivision boundary, with the lot 22 gap filled.
AVONLEA = unary_union([g for k, g in PARCELS.items() if k != "39393+001-00"]).buffer(1.5).buffer(-1.5)
AVONLEA = Polygon(max(getattr(AVONLEA, "geoms", [AVONLEA]), key=lambda g: g.area).exterior)
minx, miny, maxx, maxy = AVONLEA.bounds

# Line table, Plat Book 10, Page 201 (the Phase 2 plat repeats it).
LINES = {
    11: (50.24, "N26 11 15E"), 12: (50, "N05 54 55E"), 13: (50, "N06 21 19W"), 14: (50, "N25 39 19W"),
    15: (50, "N43 44 51W"), 16: (50, "N62 28 20W"), 17: (50, "N75 02 44W"), 18: (50, "N82 48 56W"),
    19: (50, "S86 45 53W"), 20: (50, "S75 49 01W"), 21: (50, "S56 14 24W"), 22: (50, "S39 54 32W"),
    23: (50, "S23 03 03W"), 24: (50, "S02 05 16W"), 25: (50, "S18 34 20E"), 26: (50, "S36 53 46E"),
    27: (50, "S51 00 23E"), 28: (50, "S59 26 05E"), 29: (50, "S71 21 00E"), 30: (50, "S82 13 55E"),
    31: (50, "N82 33 29E"), 32: (50, "N62 01 09E"), 33: (50, "N52 22 46E"), 34: (19.84, "N37 17 10E"),
    50: (132.89, "N17 31 47E"), 51: (191.50, "S21 10 40W"), 52: (164.56, "S28 20 40W"),
    53: (118.09, "S38 15 06W"), 54: (77.93, "S52 55 10W"), 55: (79.99, "S67 00 42W"),
    56: (72.01, "S82 18 03W"), 57: (51.00, "N82 50 26W"), 58: (82.19, "S24 12 29E"),
    59: (109.30, "S07 13 11E"), 60: (107.03, "S10 19 48W"), 61: (103.84, "S28 13 07W"),
    62: (97.50, "S46 38 19W"), 63: (87.29, "S66 17 24W"), 64: (80.23, "S89 46 35W"),
    65: (84.01, "N66 13 50W"), 66: (88.29, "N45 20 49W"), 67: (95.49, "N24 17 29W"),
    68: (90.56, "N00 12 38W"), 69: (111.93, "N22 37 54E"), 70: (102.20, "N38 58 10E"),
    71: (110.08, "N53 48 11E"), 72: (85.24, "N74 36 32E"), 73: (207.51, "N60 52 50W"),
    74: (95.46, "N44 09 17W"), 75: (143.10, "N26 06 34W"), 76: (58.79, "N52 42 21W"),
    77: (80.47, "N85 37 34W"), 78: (149.97, "S84 52 52W"), 79: (29.04, "S38 23 45W"),
    80: (64.50, "S21 35 23W"), 81: (79.46, "S35 53 47W"), 82: (56.61, "S44 51 56W"),
    83: (80.06, "S16 16 41W"), 84: (50.52, "S14 08 23W"), 85: (72.05, "S25 58 37W"),
    86: (78.78, "S41 14 03W"), 87: (101.32, "S52 43 30W"), 88: (71.58, "S61 22 07W"),
}


def line_chain(start, numbers, rot=0.0):
    return traverse(start, [(("-" if n < 0 else "") + LINES[abs(n)][1], LINES[abs(n)][0]) for n in numbers], rot)


features = []


def add(kind, name, source, geom):
    geom = geom.buffer(0).intersection(AVONLEA).difference(ROAD).buffer(0)
    for g in getattr(geom, "geoms", [geom]):
        if g.geom_type == "Polygon" and g.area > 15:
            features.append({
                "type": "Feature",
                "properties": {"KIND": kind, "NAME": name, "SOURCE": source, "ACRES": round(g.area / 4046.86, 2)},
                "geometry": json.loads(json.dumps(transform(to_ll, g.simplify(0.3)).__geo_interface__)),
            })


P1, P2 = "Plat Book 10, Page 195", "Plat Book 11, Page 1"
W60 = 60 * 0.3048

# ------------------------------------------------------ conservation easements
# A: 60 ft along the west boundary from the lot 25/26 line south to the
# highway, following the boundary's jog east at lot 29.
lot26 = PARCELS["39393-000-26"]
west_x, a_top = lot26.bounds[0], lot26.bounds[1]
lot29 = PARCELS["39393-000-29"]
jog_y = max(y for x, y in lot29.exterior.coords if x < west_x + 1)       # where the boundary turns east
jog_x = min(x for x, y in PARCELS["39393-000-30"].exterior.coords)       # west line south of the jog
add("conservation", "Conservation Easement A", P1, Polygon([
    (west_x - 5, a_top), (west_x + W60, a_top), (west_x + W60, jog_y - W60), (jog_x + W60, jog_y - W60),
    (jog_x + W60, maxy + 5), (west_x - 5, maxy + 5)]))

# B: the lakeshore, between the lake and lines L50 to L88. The position and
# rotation of the chain were fitted to the georeferenced plat sheets.
b_line = line_chain((180.35, -512.42), [-50] + list(range(51, 89)))
shore_side = Polygon(b_line + [(minx - 30, b_line[-1][1] + 3), (minx - 30, miny - 60), (b_line[0][0], miny - 60)]).buffer(0)
add("conservation", "Conservation Easement B", f"{P1}; {P2}", shore_side)

# C: 60 ft along the north boundary east of the lake and down the east
# boundary to part-way along lot 19.
north_y, east_x = PARCELS["39393-000-20"].bounds[1], PARCELS["39393-000-20"].bounds[2]
c_shape = unary_union([box(b_line[0][0], north_y - 5, east_x + 5, north_y + W60),
                       box(east_x - W60, north_y - 5, east_x + 5, -321.0)])
add("conservation", "Conservation Easement C", P1, c_shape.difference(shore_side))

# D: closed figure L11 to L34 on lots 23 and 24.
add("conservation", "Conservation Easement D", P1, Polygon(line_chain((-121.5, -15.0), range(11, 35), rot=0.2)))

# Additional easements from the water district's records.
with open(os.path.join(DATA, "sjrwmd-easements.geojson")) as fh:
    for f in json.load(fh)["features"]:
        p = f["properties"]
        if p["STATUS"] == "Active":
            recorded = datetime.datetime.fromtimestamp(p["DT_RECD"] / 1000, datetime.timezone.utc).date()
            add("conservation", "Additional conservation easement",
                f'OR Book {p["ORB"]}, Page {p["PAGE"]} (recorded {recorded})', transform(to_m, shape(f["geometry"])))

# ---------------------------------------------------------- drainage easements
# Lot 9, from the plat's bearings: round the north and east sides, then back
# along the edge it shares with the lot's buildable area.
lot9 = (205.6, 181.0)
upper = traverse(lot9, [
    ("N13 41 35W", 19.46), ("N13 50 10E", 80.98), ("N60 02 03E", 67.69), ("S88 37 57E", 85.83),
    ("S53 56 06E", 68.22), ("S22 39 08E", 68.25), ("S21 11 21W", 35.67), ("S34 59 00W", 74.66)])
lower = traverse(lot9, [("S41 01 53E", 47.97), ("S30 20 39E", 29.23), ("S67 21 59E", 46.64), ("S78 21 07E", 50.40)])
add("drainage", "Drainage easement", P1, Polygon(upper + lower[:0:-1]))

# Lots 16 and 17, against the east boundary, from the plat's bearings, with
# the 20 ft strip that reaches it from the road along the lot 16/17 line.
body = traverse((east_x, -138.3), [
    ("N34 24 53W", 29.27), ("S72 39 00W", 155.35), ("S62 31 19W", 158.34), ("S18 22 17W", 35.05),
    ("S06 49 17E", 48.87 + 100.82), ("S21 58 50E", 48.67), ("S50 07 01E", 112.75),
    ("S66 10 07E", 61.84), ("S88 17 46E", 45.06), ("N57 17 24E", 55.83), ("N40 47 00E", 41.04),
    ("N33 45 45E", 23.91)])
add("drainage", "Drainage easement", P1, Polygon(body + [(east_x + 5, body[-1][1]), (east_x + 5, -138.3)]))
shared = PARCELS["39393-000-16"].exterior.intersection(PARCELS["39393-000-17"].buffer(0.5))
add("drainage", "Drainage easement", P1, shared.buffer(10 * 0.3048, cap_style=2).intersection(box(295, -130, 377, -70)))

# The rest are read off the plat sheets by eye.
BY_EYE = [
    (P1, [(-8.2, 28.6), (7.3, 31.4), (11.1, 33.6), (41.9, 57.7), (40.3, 78.1), (13.6, 79.0), (-34.1, 93.4),
          (-46, 92), (-40, 78), (-30, 58), (-22, 40), (-16, 28)]),                         # lot 13
    (P2, [(-8, -55), (13.6, -76.5), (15.8, -77.6), (18, -76.5), (47, -47.5), (35, -38), (18, -33), (5, -42)]),  # lot 35
    (P1, [(-108, -135), (-118, -137), (-127, -124), (-124, -114), (-112, -108), (-97, -101), (-88, -92),
          (-83, -82), (-79, -72), (-72, -71), (-64, -78), (-61, -88), (-55, -82), (-100, -127)]),   # lots 23 and 24
    (P2, [(-100, -146), (-104, -155), (-102, -166), (-98, -174), (-93, -176), (-88, -172), (-78, -158),
          (-74, -153), (-66, -152), (-60, -150), (-57, -145), (-60, -136), (-66, -127), (-72, -120), (-66, -112)]),  # lot 36
    (P1, [(-262, 385), (-262.5, 388), (-265.5, 392), (-270.3, 438), (-268, 442.5), (-262.5, 444),
          (-261.5, 446), (-261.8, 453), (-250.5, 482), (-259.8, 519.8), (-253.9, 521.3), (-244.2, 482),
          (-255.2, 446.5), (-255, 441), (-251, 437.5), (-248.2, 434), (-245.8, 392), (-245.7, 385)]),   # lots 29 and 30
    (P1, [(45.5, 270), (39, 277), (36.5, 283), (38.5, 290), (46, 297), (54, 300), (72, 300.3), (80, 298),
          (87, 292), (89.5, 284), (87, 277), (81, 271)]),                                   # lots 6 and 7
]
for source, pts in BY_EYE:
    add("drainage", "Drainage easement", source, Polygon(pts).buffer(0))

# One merged outline of all the conservation easements, so the map can draw
# a single edge where neighbouring easements touch or overlap.
merged = unary_union([shape(f["geometry"]).buffer(1e-6) for f in features if f["properties"]["KIND"] == "conservation"])
features.append({"type": "Feature", "properties": {"KIND": "conservation-outline", "NAME": "", "SOURCE": "", "ACRES": 0},
                 "geometry": json.loads(json.dumps(merged.simplify(2e-6).__geo_interface__))})

with open(os.path.join(DATA, "easements.geojson"), "w") as fh:
    json.dump({"type": "FeatureCollection", "features": features}, fh)
for kind in ("conservation", "drainage"):
    fs = [f for f in features if f["properties"]["KIND"] == kind]
    print(f"{kind}: {len(fs)} areas, {sum(f['properties']['ACRES'] for f in fs):.1f} acres")
    for f in fs:
        print(f"  {f['properties']['ACRES']:5.2f} ac  {f['properties']['NAME']}  ({f['properties']['SOURCE']})")
