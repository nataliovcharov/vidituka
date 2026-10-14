# ADR 0005: Matching parsed names to the gazetteer

- Status: Accepted
- Date: 2026-10-14

## Context

The parser gives names (`ГРУЈИЦА ВОЈВОДА`, `С.ОБРШАНИ`) and the outage's place field
(`БУТЕЛ-СКОПЈЕ-БУТЕЛ`, `ПРИЛЕП`). To draw an outage or check a subscriber's address, each name has
to point at one row in `admin_areas`, `places` or `streets`. An exact name lookup in the outage's
municipality finds 75% of the labeled locations and 63% of Skopje streets (ADR 0004).

Looking at the misses:

- **Spelling:** `ГРУЈИЦА` vs `Груица`, `ЃЕМИЏИСКА` vs `Гемиџиска`, `СОТКА ЏИГИЏИК` vs `Сотка Џигидик`
- **Name forms:** ordinals (`3-ТА` / `Трета`), titles (`ГЕНЕРАЛ`, `Народен херој`), nicknames
  (`Ѓорѓи (Гоце) Делчев`, `Јордан Чопела-Кулак`), abbreviations (`МАК.КОСОВСКА`, `Ј. Османо`) and
  some OSM names in Latin (`Marshal Tito`)
- **The wrong municipality:** the feed's municipality is the power company's district.
  `ПРИЛЕП` lists villages that are in Krivogaštani, and `ЧАИР` lists streets just over the line in
  Gazi Baba.

## Options considered

- **Matching in SQL with `pg_trgm`:** fuzzy matching close to the data, but every location is a
  query and the rules (which tier, when to give up) end up split between SQL and Python. Harder
  to unit test.
- **A search engine (Elasticsearch, Typesense):** a new service to run and host, for 9,000 names.
  Rejected.
- **Names in memory, matched in Python with `rapidfuzz`:** the whole gazetteer is ~9,000 names,
  loaded once per run in well under a second. Pure functions, easy to test without a database.
  **Chosen.**

## Decision

1. `resolve_place` splits the place field into a municipality and a settlement. Municipality
   names that contain a dash are recognised by trying the longest known name first. Two names
   that the feed spells differently from OSM are aliases (`МАВРОВО-РОСТУШЕ`, `ДЕМИР ХИСАР`).
2. Both sides get the same canonical keys (`geocoding/names.py`): ordinals to digits, leading
   `СВ.`, `НАС.` and titles dropped, nicknames in brackets or after a dash as extra keys, and
   Latin transliterated to Cyrillic. Old and alternative names from OSM count too.
3. Search runs through tiers: the outage's municipality first, then the municipalities that share
   a border with it (computed with PostGIS when the index loads). A settlement also checks the
   neighbourhood list, and a neighbourhood checks streets, because some are named after a
   street.
4. In each tier: exact key, then abbreviation, then fuzzy (`rapidfuzz` ratio ≥ 88). The first
   method that finds anything decides. Fuzzy only compares names with the same number of words
   and the same numbers, so `МАКЕДОНСКА БРИГАДА` never becomes `Втора македонска бригада`.
   Villages across the border must match exactly, since another village with the same name is
   more likely than a typo.
5. If two different features tie, nothing is matched. A wrong place on the map is worse than a
   missing one.
6. Results say how they were found (`exact`, `abbreviation`, `fuzzy`, and whether it was across
   the border), so the UI can show less certain matches differently later.

## Evaluation

Each location in `power_v1.jsonl` now has a `match`: the OSM name and municipality it refers to,
or `null` when OSM doesn't have it. I made them by running an early version of the matcher, then
checked every case that wasn't an exact match in the outage's own municipality by hand. That
was 82 cases, looked up against the gazetteer and the outage text. The matcher gets the labeled
names, so parser mistakes don't count against it.

CI can't download the 28 MB extract, so tests use `tests/fixtures/osm/gazetteer_snapshot.json.gz`:
the gazetteer's names, ids and borders without geometry (90 KB). `vidituka save-gazetteer-snapshot`
regenerates it after a new extract is loaded.

| | precision | recall |
|---|---|---|
| exact name in own municipality (baseline) | 0.994 | 0.753 |
| matcher, all | 1.000 | 0.971 |
| matcher, streets | 1.000 | 0.965 |
| matcher, Skopje streets | 1.000 | 0.971 (baseline 0.629) |

239 of 269 labeled locations exist in OSM. The 7 still missed are mostly spellings that are too
far apart to risk (`ПИПЕРЕВО` vs `Пиперово`, `ПУСТАРЕКА` vs `Пуста Река`). The CI gate is
precision ≥ 0.99 and recall ≥ 0.95.

These numbers flatter the matcher: I built the rules looking at all 92 records, including the test
split. A fair check is a new batch of records labeled after this change, before tuning anything
on it.

## Consequences

- The next step can store, for each outage location, the matched rows and draw them.
- Locations OSM doesn't have (about 1 in 9) need a fallback: the settlement or municipality area,
  shown as approximate.
- Changing the OSM extract can change matches. Re-run `eval-matcher --db` after loading a new
  one, and regenerate the snapshot.
