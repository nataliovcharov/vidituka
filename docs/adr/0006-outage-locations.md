# ADR 0006: Storing where each outage is

- Status: Accepted
- Date: 2026-10-14

## Context

The parser (ADR 0003) and the matcher (ADR 0005) turn an outage's text into gazetteer features.
The map and the alerts need that result stored, with a geometry, for every outage.

## Decision

1. A table `outage_locations`: one row per location the parser finds in an outage, in text order.
   It keeps what the text said (name, kind, partial, house numbers, a village named in the text)
   and what it matched (OSM name, method, whether it was found in a neighbouring municipality).
2. **The geometry is copied into the row, not linked.** `load-osm` replaces every gazetteer row
   with new ids, so a foreign key would break on each reload. A copy also keeps past outages
   drawable after the map data changes. The cost is some duplicated geometry, which is small.
3. A feature that is several rows (a street through two villages) is stored as their union. A
   village is stored as its boundary when OSM has one, otherwise as its point.
4. A name that isn't in OSM still gets a row, with the village or municipality around it as the
   geometry and `approximate = true`, so the map can show it as "somewhere here" instead of
   dropping it. Only when the municipality itself is unknown is the geometry empty.
5. `outages.locator_version` and `outages.located_at` record when and by which rules an outage
   was located. `vidituka locate` redoes outages located by an older `LOCATOR_VERSION` or before
   the latest gazetteer load. `ingest-power` locates new outages right after storing them;
   a failure there doesn't undo the fetch, and `locate` can be run again.
6. Locations are replaced, not updated, when an outage is located again.

## Results

On the 81 outages of `2026-10-01_full.json`: 235 locations, 206 matched, 29 approximate, none
without a place. Locating them all takes about 2.5 s, most of it loading the gazetteer.

## Consequences

- Changing the parser or matcher means raising `LOCATOR_VERSION` in `locate.py`, so stored
  outages are redone on the next run.
- The API can now return outages as GeoJSON straight from this table.
