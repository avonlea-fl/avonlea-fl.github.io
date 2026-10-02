# Property map source

`build_map.py` draws the property map on the [Map page](../map.md). Lot lines, roads and the lake come from Marion County GIS data, buildable areas and easements from the recorded plats, and later easement changes from the water management district. Jekyll ignores this directory because its name starts with an underscore, so nothing here is published. The published files are:

* `assets/img/property-map.webp`, shown on the page (1600 px wide, about 200 KB)
* `assets/img/property-map.png`, the full-size image the page links to
* `docs/avonlea-property-map.pdf`, the printable copy

Rebuild them when the county's parcels change (for example, when two lots are combined), when a plat or easement changes, or to change the map's design.

| Script | Writes | Run it when |
| --- | --- | --- |
| `build_map.py` | `map.html`, which is rendered to the published files | Any data or design change. Always run last. |
| `extract_buildable.py` | `data/buildable.geojson` | A plat is added or replatted |
| `trace_easements.py` | `data/easements.geojson` | An easement is added or released, or the parcel lines are refreshed |

The data files the last two write are kept in the repository, so `build_map.py` runs on its own.

## Rebuilding

`build_map.py` needs only Python 3. Rendering needs Google Chrome, and ImageMagick makes the PNG and WebP. The window size in the screenshot command must match `W, H` in `build_map.py`.

```bash
cd _map
python3 build_map.py     # writes map.html

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
"$CHROME" --headless=new --hide-scrollbars --force-device-scale-factor=1 \
  --window-size=2400,3476 --screenshot="$PWD/map.png" "file://$PWD/map.html"
"$CHROME" --headless=new --no-pdf-header-footer \
  --print-to-pdf="$PWD/../docs/avonlea-property-map.pdf" "file://$PWD/map.html"
magick map.png -strip -define png:compression-level=9 ../assets/img/property-map.png
magick map.png -resize 1600x -quality 82 -define webp:method=6 ../assets/img/property-map.webp
rm map.html map.png
```

Labels are set in Baskerville, which ships with macOS. On another system the map falls back to Hoefler Text or Georgia.

## Data

Everything in `data/` listed in this table is an unmodified download from the county's public GIS service, in longitude/latitude, with only the listed fields requested. Do not request `outFields=*` for the parcel layers: the full records include owner names and mailing addresses, which do not belong in this repository.

| File | County layer | Fields |
| --- | --- | --- |
| `parcels.geojson` | `General/Parcels/MapServer/0`, `PARCEL LIKE '39393%'` | `PARCEL`, `ACRES` |
| `context.geojson` | `General/Parcels/MapServer/0`, surrounding parcels | `PARCEL` |
| `water.geojson` | `General/Water/MapServer/3`, Smith Lake | `GNIS_NAME` |
| `streets.geojson` | `General/Streets/MapServer/0` | `STREET`, `SUB_NAME`, `SEGMENT_ID` |

The other three files are not county downloads. `buildable.geojson` and `easements.geojson` are written by the scripts above, and `sjrwmd-easements.geojson` is an unmodified download from the water management district. See Buildable areas and Easements below.

To refresh them:

```bash
BASE=https://gis.marionfl.org/public/rest/services/General
BOX='geometry=-81.9920,29.0430,-81.9750,29.0600&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects'
OUT='returnGeometry=true&outSR=4326&f=geojson'

curl -G "$BASE/Parcels/MapServer/0/query" --data-urlencode "where=PARCEL LIKE '39393%'" \
  -d "outFields=PARCEL,ACRES&$OUT" -o data/parcels.geojson
curl "$BASE/Parcels/MapServer/0/query?$BOX&outFields=PARCEL&$OUT" -o data/context.geojson
curl -G "$BASE/Water/MapServer/3/query" --data-urlencode "where=GNIS_NAME = 'Smith Lake'" \
  -d "outFields=GNIS_NAME&$OUT" -o data/water.geojson
curl "$BASE/Streets/MapServer/0/query?$BOX&outFields=STREET,SUB_NAME,SEGMENT_ID&$OUT" -o data/streets.geojson
```

## Buildable areas

`data/buildable.geojson` holds the buildable area of each lot, traced from the recorded plat by `extract_buildable.py`. The plat shades each lot's buildable area with a dot pattern. The script lines each plat sheet up with the county's parcel lines and outlines the dotted regions. `build_map.py` draws them if the file exists.

To run it again, or to add another plat:

1. Get the plat PDF. The three current plats are in `docs/plats/`. For a new one, open it in the [Marion County Clerk's Official Records search](https://nvweb.marioncountyclerk.org/BrowserView/) and save it as a PDF. The viewer has a reCAPTCHA, so this step is manual.
2. Split the PDF into one image per sheet. `pdfimages` is part of poppler.
3. Run the script on the detail sheets only (the ones drawn at 1 inch = 60 feet), not the cover or index sheets.

```bash
pdfimages -png ../docs/plats/2007-06-20_Avonlea-Phase-1_PB10-195.pdf sheet   # sheet-000.png ... sheet-008.png
uv venv .venv && uv pip install --python .venv/bin/python numpy opencv-python-headless shapely
.venv/bin/python extract_buildable.py "Plat Book 10, Page 195" sheet-00[2-8].png

pdfimages -png ../docs/plats/2007-06-20_Avonlea-Phase-2_PB11-1.pdf p2       # p2-000.png ... p2-004.png
.venv/bin/python extract_buildable.py "Plat Book 11, Page 1" p2-00[2-4].png
```

Each run replaces the lots it finds and keeps the rest, so a second plat adds to the file. Every run then applies `REPLATS`, and running the script with no arguments applies only those. The sheet images and `.venv` are not kept in this repository.

What is in the file now:

* **Phase 1, lots 1 to 30:** from Plat Book 10, Page 195, sheets 3 to 9. The outlines are within about a metre of the plat. Where the plat gives simple dimensions the traced areas agree with them: lot 5 is 250 ft by 180 ft (1.03 acres) on the plat and 1.03 acres traced, and lot 18 is 355 ft by 200 ft (1.63 acres) and 1.64 traced.
* **Phase 2, lots 31 to 38:** from Plat Book 11, Page 1, sheets 3 to 5.
* **Lot 19:** from the replat, Plat Book 15, Page 16 (recorded 2022). That sheet has no dot pattern; it gives the buildable area by bearings and distances, which are entered by hand in `REPLATS` in `extract_buildable.py` and positioned from the lot's north-east corner. The figure closes and comes to 1.14 acres, the area the replat states. It differs from the original plat's outline by up to about two metres.

## Easements

`data/easements.geojson` holds the conservation and drainage easements, written by `trace_easements.py`. The plats draw easements as plain dashed outlines, so they cannot be picked out of the scans the way the buildable areas are. The script rebuilds them from the records instead, and every number in it is from a plat or was read off a plat sheet:

* **Conservation Easements A and C:** 60-foot strips along the west, north and east boundary, built from the county parcel lines.
* **Conservation Easements B and D:** bounded by the numbered lines L11 to L34 and L50 to L88, whose bearings and distances are in the line table on Plat Book 10, Page 201.
* **Additional conservation easements:** from the St. Johns River Water Management District's map data, saved in `data/sjrwmd-easements.geojson`. Ten were recorded in 2008 (OR Book 5094, Page 456) and one in 2024 (OR Book 8469, Page 1461).
* **Conservation Easement E** on lot 24 is left out on purpose. It was released in 2024 (OR Book 8491, Page 168).
* **Drainage easements:** the ones on lots 9, 16 and 17 are built from the plat's bearings. The others (lots 6 and 7, 13, 23 and 24, 29 and 30, 35, 36) were read off the plat sheets by eye and are good to a metre or two.

```bash
.venv/bin/python trace_easements.py          # needs shapely; uses the .venv from Buildable areas
```

To refresh the water district's data:

```bash
curl -G "https://permitting.sjrwmd.com/arcgis02/rest/services/srvc/easement/MapServer/2/query" \
  -d "geometry=-81.9880,29.0455,-81.9785,29.0570&geometryType=esriGeometryEnvelope&inSR=4326" \
  -d "outFields=ORB,PAGE,EXHIBIT,DEED_ACRES,STATUS,DT_RECD,PRMT_NO&outSR=4326&f=geojson" \
  -o data/sjrwmd-easements.geojson
```

Only easements the district marks Active are drawn, so a released easement drops off the map after a refresh.

Not drawn: the 10-foot utility easements along the roads, the conservation access easements on the plats, the dock access areas from the 2008 agreement, the landscape buffer tracts along the highway, and the flood zone. The plats use a 1983 flood map that has since been replaced.

## Things the county data does not say

These are handled in `build_map.py` and are worth re-checking after a data refresh.

* **Lot 22.** The parcel (39393-000-22, 2.53 acres) is in the county's parcel centroid layer, but its polygon is missing from the parcel layer. The script rebuilds it from the parcels around it and checks that the result is 2.53 acres. If the county restores the polygon, the script uses it instead.
* **Combined lots.** Parcel 39393-000-17 is lots 17 and 18, and parcel 39393-000-33 is lots 32 and 33. There are no parcels numbered 18 or 32. Each buildable area carries its own plat lot number, and the parcel's acreage is labelled "combined". `COMBINED` is used only if the buildable areas are missing.
* **Lake edge.** Water is drawn from the county's waterbody layer only. The state-owned lake parcel (39392-000-00) shares its boundary with the lakefront lots but reaches further inland than the water, notably west of lots 22 to 24, so it is drawn as shore.
* **Retention area.** Parcel 39393+001-00, south of lots 4 and 5, has an Avonlea-style number but is a county-maintained retention area serving Lake Weir Heights. It is drawn as part of the surroundings, not as part of Avonlea.
* **Front gate.** The marker is placed a short way up the entrance road from the highway. It is not surveyed.
* **Street-name labels.** `ROAD_LABELS` places each name by the county's street segment ID, which may change if the county re-segments its streets.

The plat references printed on the map come from the county's subdivision layer (`General/Parcels/MapServer/1`).

## Logo

The plaque is modelled on the entrance signs: gold script on charcoal. "Avonlea" is set in Great Vibes, the closest freely licensed match to the sign's lettering. The font is in `fonts/` under the SIL Open Font License (`fonts/OFL.txt`).
