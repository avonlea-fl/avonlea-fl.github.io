#!/usr/bin/env python3
"""Build the Avonlea property map (map.html) from Marion County GIS data.

Inputs, all in data/ as GeoJSON in longitude/latitude (EPSG:4326):
  parcels.geojson  Avonlea parcels (PARCEL LIKE '39393%') with PARCEL, ACRES
  context.geojson  surrounding parcels, outlines only (PARCEL)
  water.geojson    county Waterbodies layer (GNIS_NAME)
  streets.geojson  county Streets layer (STREET, SUB_NAME)
  buildable.geojson  each lot's buildable area, traced from the recorded plat
                     by extract_buildable.py (optional)
  easements.geojson  conservation and drainage easements, from
                     trace_easements.py (optional)

Render map.html with headless Chrome; see README.md.
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

# ---------------------------------------------------------------- projection
LON0, LAT0 = -81.9837413, 29.0516860
K = math.cos(math.radians(LAT0))


def to_m(p):
    """Longitude/latitude to local metres, x east and y south."""
    return ((p[0] - LON0) * 111320 * K, -(p[1] - LAT0) * 110574)


# Page layout, in pixels. The frame shows XMIN..XMAX, YMIN..YMAX metres.
W, H = 2400, 3476
FX, FY, FW = 110, 250, 2180
XMIN, XMAX, YMIN, YMAX = -450.0, 570.0, -700.0, 690.0
S = FW / (XMAX - XMIN)
FH = (YMAX - YMIN) * S


def px(m):
    return (FX + (m[0] - XMIN) * S, FY + (m[1] - YMIN) * S)


def load(name):
    with open(os.path.join(DATA, name)) as f:
        return json.load(f)["features"]


def rings(feature):
    g = feature["geometry"]
    c = g["coordinates"]
    polys = [c] if g["type"] == "Polygon" else c
    return [[to_m(p) for p in r] for poly in polys for r in poly]


def lines(feature):
    g = feature["geometry"]
    c = g["coordinates"]
    return [[to_m(p) for p in l] for l in ([c] if g["type"] == "LineString" else c)]


def path_d(ring_list, close=True):
    d = []
    for r in ring_list:
        d.append("M" + " L".join("%.1f,%.1f" % px(p) for p in r) + ("Z" if close else ""))
    return " ".join(d)


# ------------------------------------------------------------------ geometry
def seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def inside(p, ring):
    x, y = p
    n = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            n = not n
    return n


def label_point(ring, half_w=0.0, step=3.0):
    """Point inside the ring farthest from its edges (pole of inaccessibility).

    half_w widens the test horizontally so wide labels favour wide spots.
    """
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    mid = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    best, best_d = None, (-1, 0)
    y = min(ys)
    while y <= max(ys):
        x = min(xs)
        while x <= max(xs):
            if inside((x, y), ring):
                d = min(
                    min(seg_dist(q, a, b) for a, b in zip(ring, ring[1:]))
                    for q in ((x - half_w, y), (x, y), (x + half_w, y))
                    if inside(q, ring) or q == (x, y)
                )
                # Among equally roomy spots, prefer the one nearest the middle.
                d = (round(d / 4), -math.dist((x, y), mid))
                if all(inside(q, ring) for q in ((x - half_w, y), (x + half_w, y))) and d > best_d:
                    best, best_d = (x, y), d
            x += step
        y += step
    if best is None and half_w:
        return label_point(ring, 0.0, step)
    return best


def free_spot(ring, holes, target, half_w, clear, step=3.0):
    """Spot for a label on the part of a lot outside its buildable areas.

    Returns the point nearest `target` that has `clear` metres of room around
    a label 2 * half_w wide; failing that, the roomiest point there is.
    """
    edges = [e for r in [ring] + holes for e in zip(r, r[1:])]
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    near, roomy = (None, 1e9), (None, -1)
    y = min(ys)
    while y <= max(ys):
        x = min(xs)
        while x <= max(xs):
            pts = ((x - half_w, y), (x, y), (x + half_w, y))
            if all(inside(q, ring) and not any(inside(q, h) for h in holes) for q in pts):
                d = min(seg_dist(q, a, b) for q in pts for a, b in edges)
                if d > roomy[1]:
                    roomy = ((x, y), d)
                if d >= clear and math.dist((x, y), target) < near[1]:
                    near = ((x, y), math.dist((x, y), target))
            x += step
        y += step
    return near[0] or roomy[0]


def touches_lot(ring, lot):
    """True if the ring has any part inside the lot (sampled every few metres)."""
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        n = max(1, int(math.dist((x1, y1), (x2, y2)) / 4))
        if any(inside((x1 + (x2 - x1) * (i + .5) / n, y1 + (y2 - y1) * (i + .5) / n), lot) for i in range(n)):
            return True
    return False


def area_acres(ring):
    a = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:])) / 2
    return abs(a) / 4046.86


# --------------------------------------------------------------------- data
PREFIX = "39393-000-"
parcels = {f["properties"]["PARCEL"]: f for f in load("parcels.geojson")}
ring_of = {k: rings(f)[0] for k, f in parcels.items()}
acres = {k: f["properties"]["ACRES"] for k, f in parcels.items()}

ROAD = PREFIX + "00"
COMMON = {
    "39393-005-00": "lake",      # lake access: boat ramp, pier, parking
    "39393-004-00": "common",
    "39393-002-00": "entry",     # landscaped frontage either side of the gate
    "39393-003-00": "entry",
}
# 39393+001-00 carries an Avonlea-style number but is a county-maintained
# retention area serving Lake Weir Heights, so it is drawn as context.
RETENTION = "39393+001-00"

# Lot 22 (39393-000-22, 2.53 ac) is in the county's parcel centroid layer but
# its polygon is missing from the parcel layer. It is the land enclosed by the
# common area to the north, the road to the east, lot 23 to the south and the
# subdivision's west line, so rebuild it from those neighbours.
if PREFIX + "22" not in ring_of:
    road, ca, l23 = ring_of[ROAD], ring_of["39393-004-00"], ring_of[PREFIX + "23"]

    def on_road(p):
        d, i = min((math.dist(p, q), i) for i, q in enumerate(road))
        return i if d < 0.5 else None

    ca_road = [(p, on_road(p)) for p in ca if on_road(p) is not None]
    l23_road = [(p, on_road(p)) for p in l23 if on_road(p) is not None]
    i0 = max(ca_road, key=lambda t: t[0][1])[1]      # southernmost common-area point on the road
    i1 = min(l23_road, key=lambda t: t[0][1])[1]     # northernmost lot 23 point on the road
    west = min(p[0] for p in ca)
    sw_ca = max((p for p in ca if p[0] < west + 1), key=lambda p: p[1])
    nw_23 = min((p for p in l23 if p[0] < west + 1), key=lambda p: p[1])
    step = 1 if i1 > i0 else -1
    lot22 = [sw_ca] + road[i0:i1 + step:step] + [nw_23, sw_ca]
    ring_of[PREFIX + "22"] = lot22
    acres[PREFIX + "22"] = 2.53
    assert abs(area_acres(lot22) - 2.53) < 0.15, area_acres(lot22)

# County parcels that combine two platted lots.
COMBINED = {"17": "17 & 18", "33": "32 & 33"}
# Pixel offsets for lot labels that would otherwise collide with another label.
LABEL_NUDGE = {"1": (121, 48)}      # acreage clear of the front gate label

lots = sorted(k for k in ring_of if k.startswith(PREFIX) and k != ROAD)

# Tints: greedy colouring so neighbouring lots differ slightly.
TINTS = ["#cfe0b3", "#c3d7a4", "#d8e6be", "#bcd29c"]


def touches(a, b):
    n = 0
    for p in ring_of[a]:
        if any(seg_dist(p, q1, q2) < 0.5 for q1, q2 in zip(ring_of[b], ring_of[b][1:])):
            n += 1
            if n >= 2:
                return True
    return False


tint = {}
for a in lots:
    used = {tint[b] for b in tint if touches(a, b) or touches(b, a)}
    tint[a] = next(i for i in range(len(TINTS)) if i not in used) if len(used) < len(TINTS) else 0

# ---------------------------------------------------------------------- svg
o = []
add = o.append

add(f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 {W} {H}">
<defs>
  <clipPath id="frame"><rect x="{FX}" y="{FY}" width="{FW}" height="{FH:.0f}"/></clipPath>
  <linearGradient id="lake" x1="0" y1="0" x2="0.6" y2="1">
    <stop offset="0" stop-color="#8fbfd6"/><stop offset="1" stop-color="#b9dbe6"/>
  </linearGradient>
  <pattern id="conserve" width="11" height="11" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
    <rect width="11" height="11" fill="#9fc48a" fill-opacity=".55"/>
    <line x1="0" y1="0" x2="0" y2="11" stroke="#2f6b3f" stroke-width="2.4"/>
  </pattern>
  <pattern id="waves" width="84" height="40" patternUnits="userSpaceOnUse" patternTransform="rotate(-8)">
    <path d="M4,12 q10,-7 20,0 t20,0" fill="none" stroke="#fff" stroke-opacity=".45" stroke-width="2" stroke-linecap="round"/>
    <path d="M46,32 q8,-6 16,0 t16,0" fill="none" stroke="#fff" stroke-opacity=".3" stroke-width="2" stroke-linecap="round"/>
  </pattern>
  <linearGradient id="gold" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#f6e2a0"/><stop offset=".45" stop-color="#dcb556"/><stop offset="1" stop-color="#b08630"/>
  </linearGradient>
  <linearGradient id="plaque" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#33363a"/><stop offset="1" stop-color="#202225"/>
  </linearGradient>
  <filter id="lift" x="-10%" y="-10%" width="120%" height="120%">
    <feGaussianBlur in="SourceAlpha" stdDeviation="9"/><feOffset dy="5"/>
    <feComponentTransfer><feFuncA type="linear" slope=".32"/></feComponentTransfer>
    <feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
</defs>
<rect width="{W}" height="{H}" fill="#f9f5ea"/>
<rect x="34" y="34" width="{W-68}" height="{H-68}" fill="none" stroke="#b8975a" stroke-width="5"/>
<rect x="48" y="48" width="{W-96}" height="{H-96}" fill="none" stroke="#b8975a" stroke-width="1.5"/>
''')

# Title
add(f'''<g font-family="Baskerville, 'Hoefler Text', Georgia, serif" fill="#23402f" text-anchor="middle">
  <text x="{W/2}" y="172" font-size="78" letter-spacing="26">PROPERTY MAP</text>
  <line x1="{FX}" y1="146" x2="{W/2-470}" y2="146" stroke="#b8975a" stroke-width="2.5"/>
  <line x1="{W/2+470}" y1="146" x2="{FX+FW}" y2="146" stroke="#b8975a" stroke-width="2.5"/>
</g>''')

add('<g clip-path="url(#frame)">')
add(f'<rect x="{FX}" y="{FY}" width="{FW}" height="{FH:.0f}" fill="#eeebdc"/>')

# Surrounding parcels, faint
ctx = [f for f in load("context.geojson") if not f["properties"]["PARCEL"].startswith("39393-")]
LAKE_PARCEL = "39392-000-00"
d = " ".join(path_d(rings(f)) for f in ctx if f["properties"]["PARCEL"] not in (LAKE_PARCEL, RETENTION))
add(f'<path d="{d}" fill="none" stroke="#d9d3bd" stroke-width="1.2"/>')

# Surrounding streets
streets = load("streets.geojson")
hwy = [l for f in streets if f["properties"]["STREET"] == "E HWY 25" for l in lines(f)]
other = [l for f in streets if f["properties"]["STREET"] != "E HWY 25"
         and f["properties"].get("SUB_NAME") != "AVONLEA" for l in lines(f)]
add(f'<path d="{path_d(other, False)}" fill="none" stroke="#f8f5ec" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>')

# Lake: the county's waterbody outline only. The state-owned lake parcel
# reaches further inland (west of lots 22 to 24) than the water does, so it
# is drawn as shore, not water.
water = [f for f in load("water.geojson") if f["properties"].get("GNIS_NAME") == "Smith Lake"]
lakep = [r for f in ctx if f["properties"]["PARCEL"] == LAKE_PARCEL for r in rings(f)]
add(f'<path d="{path_d(lakep)}" fill="#dfe6cf" stroke="#d9d3bd" stroke-width="1.2"/>')
water_d = " ".join(path_d(rings(f)) for f in water)
for fill in ("url(#lake)", "url(#waves)"):
    add(f'<path d="{water_d}" fill="{fill}" fill-rule="evenodd"/>')
add(f'<path d="{water_d}" fill="none" stroke="#6da0bb" stroke-width="1.5"/>')

# County retention area south of lots 4 and 5
add(f'<path d="{path_d([rings(f)[0] for f in load("context.geojson") if f["properties"]["PARCEL"] == RETENTION])}" fill="#e2e4d2" stroke="#cfc9b2" stroke-width="1.2"/>')

# Highway
add(f'<path d="{path_d(hwy, False)}" fill="none" stroke="#c9c1a8" stroke-width="30" stroke-linejoin="round"/>')
add(f'<path d="{path_d(hwy, False)}" fill="none" stroke="#fbf8ef" stroke-width="25" stroke-linejoin="round"/>')

# Avonlea: a dark outline under everything gives the community one outer edge
allrings = [ring_of[k] for k in lots] + [ring_of[ROAD]] + [ring_of[k] for k in COMMON]
add(f'<path d="{path_d(allrings)}" fill="#2f5233" stroke="#2f5233" stroke-width="9" stroke-linejoin="round" filter="url(#lift)"/>')
for k in lots:
    add(f'<path d="{path_d([ring_of[k]])}" fill="{TINTS[tint[k]]}" stroke="#5f8250" stroke-width="2" stroke-linejoin="round"/>')
for k, kind in COMMON.items():
    add(f'<path d="{path_d([ring_of[k]])}" fill="#8fb878" stroke="#5f8250" stroke-width="2" stroke-linejoin="round"/>')

# Buildable areas from the recorded plat: the part of each lot that may be
# developed under the county's hamlet rules.
BUILD_FILL, BUILD_LINE = "#f8f1cf", "#8c7a3a"
DRAIN_FILL, DRAIN_LINE = "#cfe4ee", "#2f6f93"
CONS_LINE = "#2f6b3f"

# Easements: conservation easements hatched, drainage easements outlined.
easements = load("easements.geojson") if os.path.exists(os.path.join(DATA, "easements.geojson")) else []
for f in easements:
    if f["properties"]["KIND"] == "conservation":
        add(f'<path d="{path_d(rings(f))}" fill="url(#conserve)" fill-rule="evenodd"/>')
for f in easements:
    if f["properties"]["KIND"] == "conservation-outline":
        add(f'<path d="{path_d(rings(f))}" fill="none" stroke="{CONS_LINE}" stroke-width="1.2" stroke-linejoin="round"/>')
for f in easements:
    if f["properties"]["KIND"] == "drainage":
        add(f'<path d="{path_d(rings(f))}" fill="{DRAIN_FILL}" fill-opacity=".8" fill-rule="evenodd" stroke="{DRAIN_LINE}" stroke-width="2" stroke-dasharray="3 5" stroke-linecap="round" stroke-linejoin="round"/>')
buildable = load("buildable.geojson") if os.path.exists(os.path.join(DATA, "buildable.geojson")) else []
for f in buildable:
    add(f'<path d="{path_d(rings(f))}" fill="{BUILD_FILL}" fill-opacity=".82" stroke="{BUILD_LINE}" stroke-width="1.8" stroke-dasharray="10 6" stroke-linejoin="round"/>')
built_lots = sorted(int(f["properties"]["LOT"]) for f in buildable)

add(f'<path d="{path_d([ring_of[ROAD]])}" fill="#f6f0e1" stroke="#a89c7c" stroke-width="2" stroke-linejoin="round"/>')

# ------------------------------------------------------------------- labels
SERIF = "Baskerville, 'Hoefler Text', Georgia, serif"

# Street names, set along the county centrelines
av = {}
for f in streets:
    if f["properties"].get("SUB_NAME") == "AVONLEA":
        av[f["properties"]["SEGMENT_ID"]] = (f["properties"]["STREET"], lines(f)[0])


def along(line, f0, f1):
    """Sub-line between fractions f0..f1 of the line's length, left to right."""
    seg = [math.dist(a, b) for a, b in zip(line, line[1:])]
    total = sum(seg)
    out, acc = [], 0.0
    for (a, b), L in zip(zip(line, line[1:]), seg):
        for t in (f0, f1):
            if acc <= t * total <= acc + L and L:
                u = (t * total - acc) / L
                out.append((t, (a[0] + u * (b[0] - a[0]), a[1] + u * (b[1] - a[1]))))
        if f0 * total < acc + L < f1 * total:
            out.append(((acc + L) / total, b))
        acc += L
    pts = [p for _, p in sorted(out)]
    return pts if pts[0][0] <= pts[-1][0] else pts[::-1]


def pretty(street):
    words = {"RD": "Rd", "LN": "Ln", "COURT": "Court", "AVENUE": "Avenue", "SE": "SE"}
    return " ".join(words.get(w, w.lower() if w[0].isdigit() else w.title()) for w in street.split())


ROAD_LABELS = [(39095, 0.18, 0.72), (39091, 0.52, 0.86), (39091, 0.06, 0.36), (39093, 0.25, 0.8), (39090, 0.2, 0.75)]
for n, (seg_id, f0, f1) in enumerate(ROAD_LABELS):
    name, line = av[seg_id]
    add(f'<path id="rd{n}" d="{path_d([along(line, f0, f1)], False)}" fill="none"/>')
    add(f'<text font-family="{SERIF}" font-size="23" letter-spacing="3" fill="#7d7154" dominant-baseline="central">'
        f'<textPath href="#rd{n}" startOffset="50%" text-anchor="middle">{pretty(name).upper()}</textPath></text>')

h = sorted((l for l in hwy if -360 < l[0][0] < -100), key=lambda l: l[0][0])[0]
add(f'<path id="hwy" d="{path_d([h], False)}" fill="none"/>')
add(f'<text font-family="{SERIF}" font-size="23" letter-spacing="3" fill="#7d7154" dominant-baseline="central">'
    f'<textPath href="#hwy" startOffset="42%" text-anchor="middle">E HWY 25 (CR 25)</textPath></text>')

# Lot numbers and acreage. Where the plat gives a buildable area, the lot
# number goes inside it and the acreage goes outside it, on the rest of the
# lot, so the acreage is not mistaken for the size of the buildable area.
add(f'<g font-family="{SERIF}" text-anchor="middle" fill="#1f3a26" stroke="#eef4dd" stroke-opacity=".55" stroke-width="5" paint-order="stroke" stroke-linejoin="round">')
for k in lots:
    num = k[len(PREFIX):].lstrip("0")
    patches = [f for f in buildable if inside(label_point(rings(f)[0], 0, 6.0), ring_of[k])]
    if not patches:
        text = COMBINED.get(num, num)
        x, y = px(label_point(ring_of[k], 15 * len(text) / S + 6))
        x, y = x + LABEL_NUDGE.get(num, (0, 0))[0], y + LABEL_NUDGE.get(num, (0, 0))[1]
        add(f'<text x="{x:.0f}" y="{y+6:.0f}" font-size="50" font-weight="600">{text.replace("&", "&amp;")}</text>')
        add(f'<text x="{x:.0f}" y="{y+38:.0f}" font-size="25" font-style="italic" fill="#3d5a41" stroke-width="4">{acres[k]:.2f} ac</text>')
        continue
    centres = []
    for f in patches:
        ring = rings(f)[0]
        lot_no = f["properties"]["LOT"]
        c = label_point(ring, 15 * len(lot_no) / S + 4) or label_point(ring)
        centres.append(c)
        x, y = px(c)
        add(f'<text x="{x:.0f}" y="{y+17:.0f}" font-size="50" font-weight="600">{lot_no}</text>')
    text = f"{acres[k]:.2f} ac" + (" combined" if len(patches) > 1 else "")
    half = 5.6 * len(text) / S + 2
    holes = [rings(f)[0] for f in patches]
    # Keep the acreage off the easements too, where the lot has room.
    avoid = holes + [r for f in easements if f["properties"]["KIND"] != "conservation-outline"
                     for r in rings(f) if touches_lot(r, ring_of[k])]
    if len(patches) > 1:        # between the two buildable areas
        target = (sum(c[0] for c in centres) / len(centres), sum(c[1] for c in centres) / len(centres))
    else:                       # just below the buildable area
        target = (centres[0][0], max(p[1] for p in holes[0]) + 11)
    x, y = px(free_spot(ring_of[k], avoid, target, half, 10.5) or free_spot(ring_of[k], holes, target, half, 10.5))
    x, y = x + LABEL_NUDGE.get(num, (0, 0))[0], y + LABEL_NUDGE.get(num, (0, 0))[1]
    add(f'<text x="{x:.0f}" y="{y+8:.0f}" font-size="25" font-style="italic" fill="#3d5a41" stroke-width="4">{text}</text>')
add('</g>')

# Lake and common areas
add(f'''<g font-family="{SERIF}" text-anchor="middle">
  <text x="{px((-215, -565))[0]:.0f}" y="{px((-215, -565))[1]:.0f}" font-size="92" font-style="italic" letter-spacing="10" fill="#3b6f8c" fill-opacity=".85">Smith Lake</text>
</g>''')

lake_ca = ring_of["39393-005-00"]
top = min(lake_ca, key=lambda p: p[1])
cx, cy = px(label_point(lake_ca))
tx, ty = px((top[0] + 60, top[1] - 62))
add(f'''<g font-family="{SERIF}" fill="#1f3a26">
  <path d="M{cx+10:.0f},{cy-34:.0f} L{tx-70:.0f},{ty+34:.0f}" stroke="#1f3a26" stroke-width="1.6" fill="none"/>
  <circle cx="{cx+10:.0f}" cy="{cy-34:.0f}" r="5"/>
  <g text-anchor="middle" stroke="#b9dbe6" stroke-opacity=".7" stroke-width="5" paint-order="stroke">
    <text x="{tx:.0f}" y="{ty-8:.0f}" font-size="30" letter-spacing="4" font-weight="600">LAKE ACCESS</text>
    <text x="{tx:.0f}" y="{ty+22:.0f}" font-size="24" font-style="italic">boat ramp, pier &amp; parking</text>
  </g>
</g>''')
for k, kind in COMMON.items():
    if kind in ("lake", "common"):
        x, y = px(label_point(ring_of[k], 40))
        add(f'<text x="{x:.0f}" y="{y-4:.0f}" font-family="{SERIF}" font-size="21" letter-spacing="2.5" text-anchor="middle" fill="#1f3a26">COMMON</text>')
        add(f'<text x="{x:.0f}" y="{y+19:.0f}" font-family="{SERIF}" font-size="21" letter-spacing="2.5" text-anchor="middle" fill="#1f3a26">AREA</text>')

# Front gate, on the entrance road just inside the highway
entry = av[39095][1][::-1]            # runs from the highway north
gate = along(entry, 0.0, 0.17)[-1] if entry[0][1] > entry[-1][1] else along(entry, 0.83, 1.0)[0]
gx, gy = px(gate)
add(f'''<g font-family="{SERIF}">
  <rect x="{gx-9:.0f}" y="{gy-9:.0f}" width="18" height="18" transform="rotate(45 {gx:.0f} {gy:.0f})" fill="#b8975a" stroke="#6b5526" stroke-width="2"/>
  <path d="M{gx+13:.0f},{gy+13:.0f} L{gx+62:.0f},{gy+88:.0f} L{gx+84:.0f},{gy+88:.0f}" stroke="#1f3a26" stroke-width="1.6" fill="none"/>
  <text x="{gx+92:.0f}" y="{gy+96:.0f}" font-size="25" letter-spacing="2.5" fill="#1f3a26" stroke="#d6e5bd" stroke-opacity=".7" stroke-width="5" paint-order="stroke">FRONT GATE</text>
</g>''')

add('</g>')  # end clip
add(f'<rect x="{FX}" y="{FY}" width="{FW}" height="{FH:.0f}" fill="none" stroke="#b8975a" stroke-width="3"/>')

# ------------------------------------------------------------------ compass
nx, ny = px((505, -615))
add(f'''<g transform="translate({nx:.0f} {ny:.0f})" font-family="{SERIF}">
  <circle r="58" fill="#f9f5ea" fill-opacity=".85" stroke="#b8975a" stroke-width="2"/>
  <path d="M0,-46 L13,10 L0,2 L-13,10 Z" fill="#23402f"/>
  <path d="M0,46 L13,10 L0,2 L-13,10 Z" fill="none" stroke="#23402f" stroke-width="1.5"/>
  <text y="-64" text-anchor="middle" font-size="34" font-weight="600" fill="#23402f">N</text>
</g>''')

# ---------------------------------------------------------------- scale bar
FT = 0.3048
bx, by = px((-425, 652))
unit = 250 * FT * S
BOX_W = 446                          # scale bar and legend boxes
add(f'<g transform="translate({bx:.0f} {by:.0f})" font-family="{SERIF}" font-size="23" fill="#23402f">')
add(f'<rect x="-22" y="-44" width="{BOX_W}" height="78" fill="#f9f5ea" fill-opacity=".85" stroke="#b8975a" stroke-width="1.5"/>')
add(f'<rect x="0" y="0" width="{unit:.1f}" height="10" fill="#23402f" stroke="#23402f" stroke-width="1.5"/>')
add(f'<rect x="{unit:.1f}" y="0" width="{unit:.1f}" height="10" fill="#f9f5ea" stroke="#23402f" stroke-width="1.5"/>')
for i, t in enumerate(("0", "250", "500 ft")):
    add(f'<text x="{i*unit:.1f}" y="-12" text-anchor="{"start" if i == 0 else "middle"}">{t}</text>')
add('</g>')

# ------------------------------------------------------------------- legend
# In the lake, top left, clear of the highway along the bottom of the map.
rows = []
if buildable:
    rows.append((f'fill="{BUILD_FILL}" stroke="{BUILD_LINE}" stroke-width="1.8" stroke-dasharray="10 6"', "Buildable area"))
if easements:
    rows.append((f'fill="url(#conserve)" stroke="{CONS_LINE}" stroke-width="1.2"', "Conservation easement"))
    rows.append((f'fill="{DRAIN_FILL}" stroke="{DRAIN_LINE}" stroke-width="2" stroke-dasharray="3 5" stroke-linecap="round"', "Drainage easement"))
if rows:
    lx, ly = px((-428, -668))
    add(f'<g transform="translate({lx:.0f} {ly:.0f})" font-family="{SERIF}" font-size="24" fill="#23402f">')
    add(f'<rect x="-22" y="-30" width="350" height="{44 * len(rows) + 16}" fill="#f9f5ea" fill-opacity=".9" stroke="#b8975a" stroke-width="1.5"/>')
    for i, (style, label) in enumerate(rows):
        add(f'<rect x="0" y="{44 * i - 16}" width="54" height="32" {style}/>')
        add(f'<text x="70" y="{44 * i + 8}">{label}</text>')
    add('</g>')

# --------------------------------------------------------------------- logo
# Set over the neighbouring land south-east of the community.
p0, p1 = px((118, 445)), px((490, 610))
pw, ph = p1[0] - p0[0], p1[1] - p0[1]
mx = p0[0] + pw / 2
add(f'''<g filter="url(#lift)">
  <rect x="{p0[0]:.0f}" y="{p0[1]:.0f}" width="{pw:.0f}" height="{ph:.0f}" fill="url(#plaque)"/>
  <rect x="{p0[0]+5:.0f}" y="{p0[1]+5:.0f}" width="{pw-10:.0f}" height="{ph-10:.0f}" fill="none" stroke="url(#gold)" stroke-width="5"/>
  <rect x="{p0[0]+16:.0f}" y="{p0[1]+16:.0f}" width="{pw-32:.0f}" height="{ph-32:.0f}" fill="none" stroke="#b08630" stroke-width="1.5"/>
</g>
<g fill="url(#gold)" text-anchor="middle">
  <text x="{mx-22:.0f}" y="{p0[1]+ph*0.56:.0f}" font-family="'Great Vibes', 'Snell Roundhand', cursive" font-size="{ph*0.62:.0f}">Avonlea</text>
  <text x="{mx-22:.0f}" y="{p0[1]+ph*0.83:.0f}" font-family="{SERIF}" font-size="{ph*0.105:.0f}" letter-spacing="{ph*0.03:.1f}">AT SMITH LAKE</text>
  <g transform="translate({mx+pw*0.245:.0f} {p0[1]+ph*0.60:.0f}) scale({ph/350:.3f})">
    <path d="M-52,-6 C-28,14 6,20 38,6" fill="none" stroke="url(#gold)" stroke-width="4" stroke-linecap="round"/>
    <path d="M30,8 C52,-20 104,-26 150,-6 C112,2 86,22 44,22 C38,18 33,13 30,8 Z"/>
    <path d="M52,24 C70,40 62,58 40,54 C52,48 54,36 46,26 Z"/>
    <path d="M40,10 C74,-4 108,-8 142,-6" fill="none" stroke="#7a5a17" stroke-width="2.5" stroke-linecap="round"/>
  </g>
</g>''')

# ------------------------------------------------------------------- footer
fy = FY + FH + 52
missing = [n for n in range(1, 39) if n not in built_lots]
build_note = "Buildable areas and easements are from the recorded plats, the lot 19 replat, and later recorded easement changes."
if buildable and missing:
    build_note = "Buildable areas are traced from the recorded plat of Avonlea Phase 1."
    build_note += f" Lots {missing[0]}–{missing[-1]} are in Phase 2 and are not yet shown."
if not buildable:
    build_note = "The recorded plats show the buildable area of each lot."
add(f'''<g font-family="{SERIF}" font-size="26" fill="#4a4636" text-anchor="middle">
  <text x="{W/2}" y="{fy:.0f}">Lot lines and acreages (whole lot) are from Marion County Property Appraiser parcel records, October 2026.</text>
  <text x="{W/2}" y="{fy+36:.0f}">Lots 17 &amp; 18 and lots 32 &amp; 33 are each held as a single parcel. For general reference only; not a survey.</text>
  <text x="{W/2}" y="{fy+72:.0f}">{build_note}</text>
  <text x="{W/2}" y="{fy+108:.0f}" font-style="italic">Recorded plats: Plat Book 10, Page 195 · Plat Book 11, Page 1 · Plat Book 15, Page 16</text>
</g>
</svg>''')

svg = "\n".join(o)
html = f'''<!doctype html>
<html><head><meta charset="utf-8"><title>Avonlea at Smith Lake property map</title>
<style>
@font-face {{ font-family: "Great Vibes"; src: url("fonts/GreatVibes-Regular.ttf"); }}
@page {{ size: 8.5in {8.5*H/W:.3f}in; margin: 0; }}
html, body {{ margin: 0; background: #f9f5ea; }}
svg {{ display: block; width: 100%; height: auto; }}
</style></head><body>
{svg}
</body></html>
'''
with open(os.path.join(HERE, "map.html"), "w") as f:
    f.write(html)
print(f"wrote map.html ({W}x{H}); lot 22 rebuilt at {area_acres(ring_of[PREFIX + '22']):.2f} ac; {len(lots)} lots")
