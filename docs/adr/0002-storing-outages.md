# ADR 0002: Storing outages and detecting withdrawals

- Status: Accepted
- Date: 2026-09-29

## Context

The power feed returns the full list of current and upcoming planned outages on every request.
Record ids change on every request (ADR 0001), so we track outages by content hash. We need to
know which outages are new, which are still announced, and which were withdrawn.

Observed on 2026-09-29: the feed keeps an outage listed for the rest of the day after it ends.
So "no longer in the feed" does not mean "cancelled".

## Decision

- **PostgreSQL + PostGIS**, accessed with SQLAlchemy 2.0 and psycopg 3. Schema changes go through
  Alembic migrations only. CI runs `alembic check` so a model change without a migration fails.
- **`fetch_runs` table**: one row per poll, committed before fetching, then marked `ok` or
  `failed` with counts and the error. This is the audit trail and the basis for alerting when
  the feed breaks.
- **`outages` table**: unique on `(source, content_hash)`. Each poll upserts every record and
  bumps `last_seen_at`. `first_seen_at` never changes. Times are stored as `timestamptz`.
- **Withdrawal rule**: after a successful poll, an outage that is not in the response and has
  **not started yet** gets `withdrawn_at` set. Outages that already started or ended are left
  alone. If it reappears later, `withdrawn_at` is cleared.
- **Empty response guard**: if the feed returns zero records, nothing is withdrawn. An empty list
  is more likely an upstream problem than no planned outages anywhere in the country.
- **Ingestion is a one-shot command** (`vidituka ingest-power`) that exits non-zero on failure.
  Scheduling (cron, a systemd timer or a hosted scheduler) is chosen at deploy time and stays
  outside the code.

## Consequences

- If the utility edits the time of an outage, we see a withdrawal plus a new outage. Linking
  the two is left for later, when alerts need to say "rescheduled" instead of "cancelled".
- Two polls running at once are safe (the upsert is idempotent) but wasteful; the scheduler
  should not overlap runs.
- Database tests run against a real PostGIS (Docker locally, a service container in CI), each
  inside a transaction that is rolled back.
