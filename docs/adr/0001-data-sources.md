# ADR 0001: Data sources and how we collect them

- Status: Accepted
- Date: 2026-09-29

## Context

Planned power and water outages in Skopje are published by two utilities:

- **Elektrodistribucija DOOEL** (power, part of the EVN group), on elektrodistribucija.mk.
- **JP Vodovod i kanalizacija Skopje** (water), on vodovod-skopje.com.mk.

News portals and the Skopje Regional Crisis Management Centre repost the same notices as articles.
We need a reliable, polite way to collect the original data.

## Findings

### Elektrodistribucija (power)

- The page `/Grid/OutagesMap.aspx` renders an empty table. Its inline script loads all planned
  outages for the country from one JSON endpoint:
  `GET https://portal-api.elektrodistribucija.mk/DSO/Prekini/ZemiPrekini`.
- Each record has: `prekinID`, `kecId` (regional customer centre), `tipPrekin` (outage type),
  `nasMesto` (municipality/settlement), `adresa` (free text), `pocetok` / `kraj` (start/end as
  ISO timestamps in local time with no offset) and `napNivo` (voltage level).
- Skopje is covered by customer centres `kecId` 10, 38 and 39 (taken from the page's own filter).
- **`prekinID` is regenerated on every request.** Two requests 1.5 s apart returned the same
  73 records with zero matching ids. It cannot be used to deduplicate or track changes.
- The API sends `Access-Control-Allow-Origin: https://elektrodistribucija.mk`, so browsers on other
  sites cannot call it. This does not affect server-side requests.
- `robots.txt` returns 404 (no crawl rules). The site footer states a generic copyright notice.
- Snapshot on 2026-09-29: 73 outages nationally, 14 in Skopje.

### Vodovod Skopje (water)

- `robots.txt` does not exist (the server returns the homepage, a "soft 404").
- Interruptions are published as one long article (`/mk-MK/article/INFORMACIIIZAPREKINNAVODOSNABDUVANjEIDEFEKTI_1`),
  one free-text paragraph per notice, separated by `<hr>`. Formatting is inconsistent
  (bold tags inside dates, typos, "until the work is finished" instead of an end time).
- Most entries are same-day defects rather than work planned in advance.
- A map page embeds an ArcGIS Online web app (`gdi-sk.maps.arcgis.com`); its backing feature
  service has not been investigated yet.
- **The footer says copying or displaying the site's material requires written approval.**

## Decision

1. **Power:** consume the JSON endpoint directly with `httpx`. No HTML scraping, no headless
   browser.
2. **Identity:** identify a power outage by a SHA-256 hash of its content (customer centre, place,
   whitespace-normalised location text, start, end), not by `prekinID`.
3. **Water:** deferred to a later phase. When implemented we store only extracted facts
   (streets, times) plus a link to the source notice, never the notice text itself, and we will
   ask the utility for permission before making the site public.
4. **Politeness, for every source:**
   - poll no more often than every 30 minutes;
   - send a descriptive `User-Agent` with a contact URL;
   - use timeouts, and back off on errors instead of retrying immediately;
   - honour `robots.txt` if a source adds one later.
5. **Testing:** tests run against saved responses in `backend/tests/fixtures/`. Tests never call
   the live sources. New fixtures are captured with `uv run vidituka fetch-power --save <path>`.

## Consequences

- Power ingestion is simple and robust; the hard part moves to parsing the `adresa` free text
  into streets and house-number ranges.
- A content hash cannot tell "the utility edited this outage" from "one outage was cancelled and
  another announced". Matching edited records (same centre, place and day, similar text) is a
  separate problem for the ingestion phase.
- The endpoint is undocumented and can change without notice. Response validation
  (`RawOutage`) makes such a change fail loudly, and the scheduled job must alert us when it does.
