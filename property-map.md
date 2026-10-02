---
layout: single
title: Property Map Sources
permalink: /property-map/
description: "County parcel records, verified lot numbers, acreage, and recorded plat references for Avonlea at Smith Lake."
---

[Open the full-size property map]({{ '/assets/maps/avonlea-current-parcels.svg' | relative_url }}){: .btn .btn--primary }
[Back to the Realtors page]({{ '/realtors/#property-map' | relative_url }}){: .btn }

The map shows current Marion County tax parcel boundaries and county-reported acreage as retrieved on **October 2, 2026**. All displayed lot numbers were checked against the legal-description section of the county's 2026 property record cards. Acreages come from the county's records, not measurements of the illustration.

### Combined parcels

The county records identify **lots 17 and 18** as one parcel and **lots 32 and 33** as one parcel. Each pair appears as a single shape on the map. The current record for parcel 39393-000-23 identifies **lot 23 only**, so the map does not infer a combination with lot 22.

There are 35 numbered parcel records in this map. This count does not establish the number of legally buildable lots. Hatched areas represent association-owned parcels; other unnumbered land is not assigned a residential lot number.

### Recorded plats

| Recorded plat | Plat book / starting page |
| --- | --- |
| [Avonlea Phase 1](https://nvweb.marioncountyclerk.org/BrowserView/viewer.aspx?docID=4234893) | 10 / 195 |
| Avonlea Phase 2 | 11 / 1 |
| Avonlea Phase 1 Replat of Lot 19 | 15 / 16 |

These references are listed in the county subdivision index. To locate a plat in the [Marion County Clerk's Official Records search](https://nvweb.marioncountyclerk.org/BrowserView/), select **Book/Page**, choose **PLAT**, and enter its book and page. Phase 1 was recorded June 20, 2007.

The illustration does not show development envelopes, conservation easements, setbacks, or individual improvements. Consult the recorded plats and governing documents for these details. County GIS boundaries are an informational reference, not a survey.

### County parcel records

Select a parcel number to open its 2026 Property Appraiser record. Labels below use the lot numbers in those records.

| Lot(s) | County parcel record | County acres |
| --- | --- | ---: |
{% for parcel in site.data.avonlea_parcels %}| {{ parcel.label }} | [{{ parcel.parcel }}]({{ parcel.recordUrl }}) | {{ parcel.acresDisplay }} |
{% endfor %}

### Map data

Parcel boundaries and acreage: [Marion County parcel layer](https://gis.marionfl.org/public/rest/services/General/Parcels/MapServer/0). Plat references: [county subdivision layer](https://gis.marionfl.org/public/rest/services/General/Parcels/MapServer/1). Road centerlines: [county street layer](https://gis.marionfl.org/public/rest/services/General/Streets/MapServer/0). Water outlines: [county waterbody layer](https://gis.marionfl.org/public/rest/services/General/Water/MapServer/3).

For the latest county map, use the [Marion County Property Appraiser map viewer](https://experience.arcgis.com/experience/fdebe26ee2fb40758e399cc5447c5809).
