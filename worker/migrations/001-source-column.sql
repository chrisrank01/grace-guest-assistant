-- 001 — add `source` to events and daily_stats.        Applied 2026-09-16.
--
-- WHY: test data was identified by DATE, and that broke twice inside 24 hours.
-- Once when the scripted walks and the demo clicks landed on the same UTC day,
-- and once when "today" turned out to BE the excluded day. A date cannot say
-- which embed sent a row, so it can only ever be a proxy for that, and the proxy
-- fails the moment two kinds of traffic share a calendar day. `source` records
-- the thing we actually wanted to know.
--
-- This file exists because schema.sql is a from-scratch definition built from
-- CREATE TABLE IF NOT EXISTS, which by design does nothing to a table that
-- already exists. A live database needs the change spelled out separately.
-- schema.sql has been updated to match, so a rebuild from scratch and a migrated
-- database end up identical.

-- events: a plain ADD COLUMN. '' follows the ''-for-absent convention the rest
-- of the schema uses, and means "the sender declared no source".
ALTER TABLE events ADD COLUMN source TEXT NOT NULL DEFAULT '';

-- BACKFILL, and the basis for it. The 44 rows present at migration time are set
-- to 'demo' rather than left ''. That is not a guess: data-events has only ever
-- existed on the two demo pages, no other embed has ever carried it, and the
-- deploy history shows the attribute added to those two files and nowhere else.
-- The attribution is therefore a fact about where those rows could have come
-- from, not an inference about where they probably did.
-- The cost is recorded honestly: after this, a row that declared 'demo' and a
-- row that was assigned it are indistinguishable. That is acceptable for 44
-- rows of known provenance and would not be for a larger or less certain set.
UPDATE events SET source = 'demo' WHERE source = '';

-- daily_stats: source joins the PRIMARY KEY, so the table has to be rebuilt -
-- SQLite cannot ALTER a primary key. Safe here because the table is EMPTY; if it
-- ever holds rows, copy them across before the DROP instead of assuming.
DROP TABLE IF EXISTS daily_stats;

CREATE TABLE daily_stats (
  day         TEXT    NOT NULL,
  source      TEXT    NOT NULL DEFAULT '',
  route       TEXT    NOT NULL,
  question_id TEXT    NOT NULL DEFAULT '',
  metric      TEXT    NOT NULL,
  outcome     TEXT    NOT NULL DEFAULT '',
  value       INTEGER NOT NULL,
  PRIMARY KEY (day, source, route, question_id, metric, outcome)
);

CREATE INDEX IF NOT EXISTS idx_daily_route_day ON daily_stats (route, day);
CREATE INDEX IF NOT EXISTS idx_events_source_day ON events (source, day);
