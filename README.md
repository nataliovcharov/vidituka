# Vidituka

Planned power and water outages in Skopje, in one place, with an alert the day before.

"Види тука" means "look here" in Macedonian.

## Why

Outages are announced as long blocks of text on the utilities' sites and then reposted by news
portals. The street lists are hard to scan, and most people find out when the power or water is
already off. Vidituka collects the announcements, turns them into structured data (streets, house
numbers, start and end), puts them on a map and notifies people subscribed to their address.

## Status

Early development.

- [x] Power outages client (Elektrodistribucija JSON feed)
- [x] Ingestion into PostgreSQL + PostGIS, with withdrawal detection
- [ ] Scheduled runs
- [x] Parser for streets, villages and house numbers (F1 0.956 on a labeled set)
- [x] Gazetteer: municipalities, settlements and streets from OpenStreetMap, in PostGIS
- [ ] Matching parsed names to the gazetteer
- [ ] A point or line on the map for each outage location
- [ ] Map and list UI
- [ ] Subscriptions and alerts (email, web push)
- [ ] Water outages (Vodovod Skopje)

## Stack

Python 3.12, FastAPI, httpx, Pydantic, SQLAlchemy, Alembic, PostgreSQL + PostGIS, uv, ruff,
mypy, pytest, GitHub Actions. Frontend (planned): React + MapLibre.

## Running locally

Requires [uv](https://docs.astral.sh/uv/) and Docker.

```sh
cp .env.example .env
docker compose up -d --wait

mkdir -p data
curl -L -o data/macedonia-latest.osm.pbf https://download.geofabrik.de/europe/macedonia-latest.osm.pbf

cd backend
uv sync
uv run alembic upgrade head
uv run vidituka load-osm ../data/macedonia-latest.osm.pbf
uv run vidituka ingest-power
uv run uvicorn vidituka.api.main:app --reload
```

`vidituka fetch-power` fetches and prints the feed without touching the database.

`load-osm` reads the OpenStreetMap extract (about 30 MB, takes ~30 s) into the `admin_areas`,
`places` and `streets` tables, replacing what was there. Re-download and re-run it to refresh.
`data/` is git-ignored.

Postgres is published on port 5433 (set `POSTGRES_PORT` in `.env` to change it), so it can run
next to other local Postgres servers.

Checks (same as CI):

```sh
cd backend
uv run ruff check . && uv run ruff format --check .
uv run mypy src tests migrations
uv run pytest
```

Scoring the address parser against the labeled set:

```sh
uv run vidituka eval-parser
uv run vidituka eval-parser --skopje --errors
```

Tests use saved responses and a small hand-made map in `backend/tests/fixtures/` and never call
the live sources or need the real OSM extract. Database
tests run against the `vidituka_test` database from Docker Compose and are skipped if
`VIDITUKA_TEST_DATABASE_URL` is not set.

## Data sources

- [Elektrodistribucija](https://elektrodistribucija.mk/Grid/OutagesMap.aspx), planned power outages
- [Vodovod i kanalizacija Skopje](https://www.vodovod-skopje.com.mk/mk-MK/article/INFORMACIIIZAPREKINNAVODOSNABDUVANjEIDEFEKTI_1), water interruptions (planned)
- [OpenStreetMap](https://www.openstreetmap.org/copyright) via [Geofabrik](https://download.geofabrik.de/europe/macedonia.html), municipalities, settlements and streets. Map data © OpenStreetMap contributors, available under the [ODbL](https://opendatacommons.org/licenses/odbl/).

Sources are polled at most every 30 minutes with an identifying User-Agent. Only extracted facts
are stored, with a link back to the original notice. Decisions are recorded in [docs/adr](docs/adr).

This is an independent project and is not affiliated with either utility or with OpenStreetMap.
