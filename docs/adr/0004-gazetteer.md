# ADR 0004: Gazetteer from an OpenStreetMap extract

- Status: Accepted
- Date: 2026-10-14

## Context

The parser turns outage text into names (`ЈАЈЦЕ`, `С.ЛЕСКОВИЦА`). To draw outages on a map and to
check whether a subscriber's address is affected, each name has to become a real place with a
geometry. The parser also misses villages listed without `С.` and abbreviations like `ВС БАТО`;
a list of real names would fix most of those.

## Options considered

- **Nominatim (public geocoding API)**: one HTTP request per name. Its usage policy forbids bulk
  and systematic geocoding, it gives one point rather than a whole street, and results change
  under us. Rejected.
- **Commercial geocoders**: cost money and their terms usually forbid storing results. Rejected.
- **OpenStreetMap extract loaded into our own PostGIS**: free, ODbL licensed (attribution needed),
  full street geometries, works offline, reproducible from one file. **Chosen.**

## Decision

1. Source: the North Macedonia extract from Geofabrik (`macedonia-latest.osm.pbf`, ~30 MB), kept in
   git-ignored `data/` and refreshed by downloading it again.
2. `vidituka load-osm <file>` reads it with `osmium` and `shapely` and fills:
   - `admin_areas`: country-level boundaries 6 (City of Skopje), 7 (80 municipalities),
     8 (settlements) and 9 (urban areas), as polygons, with each settlement linked to its municipality
   - `places`: `place=*` nodes (villages, suburbs, neighbourhoods), as points
   - `streets`: named `highway=*` ways that are addresses (no footways or tracks). Pieces with the
     same name in the same settlement are merged into one line.
   - `gazetteer_loads`: which file was loaded and the date of its data
3. Everything is clipped to the boundary tagged `ISO3166-1=MK`; the extract also contains strips of
   neighbouring countries.
4. Alternative names (`name:mk`, `old_name`, `alt_name`, `official_name`, `short_name`) are kept,
   because notices sometimes use a street's old name.
5. A load replaces all reference data inside one transaction; a failed load leaves the previous
   data untouched.
6. Spatial columns use geoalchemy2, SRID 4326, with GiST indexes. The Alembic environment ignores
   tables owned by PostGIS extensions (see the fix for the tiger geocoder tables in CI).
7. Tests use a hand-made map (`tests/fixtures/osm/tiny.osm`, built by `make_tiny.py`); CI never
   downloads the real extract.

## Results (extract of 2026-10-13)

1,847 areas (80 municipalities, 1,749 settlements), 2,176 places, 5,317 streets; load takes ~25 s.

How many labeled locations from `power_v1` exist in the gazetteer with an exact name key:

| | found |
|---|---|
| settlements, neighbourhoods, municipalities | 146 / 170 (86%) |
| streets | 76 / 100 (76%) |
| streets in Skopje | 30 / 46 (65%) |

Many misses are spelling differences (`СВЕТИ КИРИЛ И МЕТОДИЈ` vs `Кирил и Методиј`,
`ПУСТАРЕКА` vs `Пуста Река`, `ПЕТРЕ` vs `ПЕТАР`). Some streets are missing from OSM altogether,
mostly small streets in Gazi Baba and Butel.

## Consequences

- Matching parsed names to the gazetteer (fuzzy matching, abbreviations, ordinals) is the next step,
  measured against these coverage numbers.
- Streets missing from OSM cannot be drawn as lines; the fallback is the neighbourhood or settlement
  area. Contributing missing streets back to OSM is possible but out of scope.
- The map must show "© OpenStreetMap contributors".
