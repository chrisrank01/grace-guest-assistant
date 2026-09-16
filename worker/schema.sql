-- grace-widget-usage — schema for the Grace Guest Assistant usage database.
--
-- Version-controlled so the database can be rebuilt from the repo:
--     npx wrangler d1 execute grace-widget-usage --remote --file worker/schema.sql
-- Every statement is IF NOT EXISTS, so re-running it against a live database is a
-- no-op rather than a data loss event.
--
-- ---------------------------------------------------------------------------
-- THERE IS NO IDENTIFIER IN THIS SCHEMA, AND THAT IS THE POINT
-- ---------------------------------------------------------------------------
-- No session id, no cookie, no IP, no fingerprint, nothing that links one row to
-- another. A written brief has gone to Grace stating this, so it is a commitment
-- and not a preference. DO NOT ADD ONE - not a hashed one, not a truncated one,
-- not "just for debugging".
--
-- The three metrics Grace asked for are all reachable without it, because each
-- tap carries its own POSITION in the visit:
--   which questions get tapped -> COUNT(*) GROUP BY question_id WHERE kind='tap'
--   how many ask more than one -> COUNT(position>=2) over COUNT(position=1)
--   where people stop          -> close rows, GROUP BY outcome and depth
--
-- What this design CANNOT do, stated so nobody is surprised later: individual
-- journeys are unrecoverable. "How many people went what-to-wear -> parking ->
-- kids, in that order" has no answer here and never will. Aggregate shape yes,
-- sequences no. That is the price of the commitment and it was paid knowingly.
--
-- ---------------------------------------------------------------------------
-- STORAGE: 500 MB IS THE CEILING, AND IT IS THE PER-DATABASE ONE
-- ---------------------------------------------------------------------------
-- D1 free tier: 500 MB per database (the 5 GB figure on the pricing page is the
-- account-wide total, not this). Measured on real-shaped rows with both indexes
-- below: 139.5 bytes per event row. So:
--
--     500 MB  ~=  3.76 million events  ~=  750,000 visits at 5 rows each
--       50 visits/day -> 41 years      200 visits/day -> 10 years
--     1000 visits/day ->  2.1 years
--
-- Writes are not the constraint either: 100,000 rows/day free tier is ~20,000
-- visits/day. READS are the constraint - 5 million rows/day, and an aggregate
-- over raw events reads every row it scans. That is why daily_stats exists; see
-- the note on it below.
--
-- The one-year retention sweep keeps events bounded regardless:
--     DELETE FROM events WHERE day < date('now','-1 year');
-- which idx_events_day_kind serves.

-- ---------------------------------------------------------------------------
-- events — one row per thing a guest did. Append-only, kept one year.
-- ---------------------------------------------------------------------------
-- *** THE DASHBOARD MUST NEVER QUERY THIS TABLE. READ daily_stats INSTEAD. ***
--
-- Not a style preference - an arithmetic one. D1's free tier allows 5 million
-- ROWS READ per day, and an aggregate over raw events reads every row it scans.
-- At 3.7 million rows (this table full) ten dashboard refreshes is 37 million
-- reads, seven times the daily cap, and when it is exceeded D1 stops answering
-- queries at all. daily_stats holds a few hundred rows a month and is what any
-- reporting query should touch.
--
-- Legitimate reasons to read events: the nightly rollup (one day at a time),
-- auditing a specific question, and re-deriving daily_stats if it is ever wrong.
-- All three are bounded and occasional. A dashboard is neither.
CREATE TABLE IF NOT EXISTS events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          TEXT    NOT NULL,   -- ISO8601 UTC, exact moment
  day         TEXT    NOT NULL,   -- YYYY-MM-DD UTC. STORED, not derived: every
                                  -- rollup and retention query filters on it, and
                                  -- date(ts) in a WHERE clause cannot use an index.
  kind        TEXT    NOT NULL,   -- 'open' | 'tap' | 'close'
  route       TEXT    NOT NULL,   -- e.g. /plan-your-visit/
  question_id TEXT,               -- tap: which question. close: the last one seen.
  position    INTEGER,            -- tap: 1,2,3... within this visit (1..100)
  depth       INTEGER,            -- close: how many questions this visit (0..100)
                                  -- -1 = THE CALLER SENT AN UNUSABLE VALUE. See
                                  -- the note below. NULL = none was reported.
  outcome     TEXT,               -- close: 'none'|'read'|'person'|'exhausted'
                                  -- 'invalid' = unusable value sent, as above.
                                  -- NULL = none was reported.
  source      TEXT    NOT NULL DEFAULT ''
                                  -- which embed sent it: 'demo' | 'live'.
                                  -- '' = the sender declared none.
                                  -- 'invalid' = an unknown value was sent.
                                  -- REPLACES identifying test data by date; see
                                  -- worker/migrations/001-source-column.sql.
);

-- ---------------------------------------------------------------------------
-- depth = -1 AND outcome = 'invalid' ARE BUG REPORTS, NOT DATA
-- ---------------------------------------------------------------------------
-- When a close arrives with a depth or outcome that is present but fails its
-- bounds, the row is written with the field set to these markers rather than
-- being clamped, nulled, or dropped. Each of the alternatives loses something:
--
--   clamping  invents data - a depth of 100 that was really 10^9 is a lie that
--             averages into every report thereafter
--   NULL      is indistinguishable from "no depth was reported", so the failure
--             becomes invisible and the visit silently leaves the metric
--   dropping  loses the whole close, and a row that was never written cannot be
--             counted either - equally invisible, and costlier
--
-- The markers keep the failure COUNTABLE. Neither value can be produced by a
-- guest; both can only come from a caller sending something the contract
-- forbids.
--
-- RULES FOR THE DASHBOARD:
--   * depth = -1 is its own bucket. NEVER average or sum depth without
--     excluding it:  WHERE depth >= 0
--   * outcome = 'invalid' is its own bucket. Never fold it into 'none'.
--   * A RISING COUNT OF EITHER MEANS THE WIDGET IS BROKEN. It is not a fact
--     about guests and must not be reported as one. Worth a standing check:
--       SELECT day, COUNT(*) FROM events
--        WHERE kind='close' AND (depth = -1 OR outcome = 'invalid')
--        GROUP BY day;
--
-- position has no equivalent marker and should not gain one: a tap REQUIRES
-- position, so an unusable one leaves no row to mark and the tap is dropped.

-- Serves the nightly rollup (one day at a time, split by kind), every
-- kind-filtered aggregate, and the one-year retention DELETE. day is the leading
-- column because every one of those filters on it first.
CREATE INDEX IF NOT EXISTS idx_events_day_kind
  ON events (day, kind);

-- Serves "how has this one question done over time" - the audit and
-- re-derivation path. Without it that question is a full table scan, which is
-- precisely the read-ceiling problem daily_stats exists to avoid.
CREATE INDEX IF NOT EXISTS idx_events_question_day
  ON events (question_id, day);

-- Serves "show me only the live embed, over time" - the split that source
-- exists for. The nightly rollup groups by source, so it reads through
-- idx_events_day_kind and this one is for ad-hoc queries.
CREATE INDEX IF NOT EXISTS idx_events_source_day
  ON events (source, day);

-- ---------------------------------------------------------------------------
-- daily_stats — precomputed. THE DASHBOARD READS THIS AND NEVER events.
-- ---------------------------------------------------------------------------
-- A few hundred rows a month instead of millions. This is also the one-year
-- rollup mechanism arriving early: when events are swept at a year old, the
-- numbers already live here.
--
-- WHY question_id AND outcome ARE NOT NULL DEFAULT '':
-- In SQLite a PRIMARY KEY does NOT imply NOT NULL (except for INTEGER PRIMARY
-- KEY), and NULL never compares equal to NULL. A PK containing nullable columns
-- therefore does not prevent duplicates. Verified, not assumed - with those two
-- columns nullable, inserting the identical ('2026-09-15','/giving/',NULL,
-- 'opens',NULL,5) three times yields THREE rows and SUM(value)=15.
--
-- That would make the rollup silently triple-count on any re-run, which is fatal
-- for a job whose whole value is being re-runnable. With '' meaning "not
-- applicable", the PK holds and the rollup can use
--     INSERT ... ON CONFLICT DO UPDATE SET value = excluded.value
-- so running it twice is a no-op. Write '' for absent, never NULL.
CREATE TABLE IF NOT EXISTS daily_stats (
  day         TEXT    NOT NULL,
  source      TEXT    NOT NULL DEFAULT '',   -- 'demo' | 'live' | '' | 'invalid'
  route       TEXT    NOT NULL,
  question_id TEXT    NOT NULL DEFAULT '',   -- '' = metric is not per-question
  metric      TEXT    NOT NULL,              -- see the full list below
                                             -- 'opens'|'closes'|'taps'|'first_taps'
                                             -- |'later_taps'|'outcomes'
                                             -- |'invalid_depth'|'invalid_outcome'
  outcome     TEXT    NOT NULL DEFAULT '',   -- '' = metric is not per-outcome
  value       INTEGER NOT NULL,
  PRIMARY KEY (day, source, route, question_id, metric, outcome)
);

-- THE METRICS, and what each row means. Written by the nightly rollup in
-- worker/src/index.js; the dashboard should know no others.
-- Every metric is ALSO per source, which is the first column of the key after
-- day: demo traffic and live traffic never mix in one row.
--   opens / closes    per route. question_id='' outcome=''
--   taps              per route per question. question_id=<slug> outcome=''
--   first_taps        as taps, but position=1 only
--   later_taps        as taps, but position>=2 only
--                     first_taps + later_taps = taps, per question. That pair is
--                     what answers "how many people asked more than one
--                     question" with no identifier linking any two rows.
--   outcomes          per route per outcome. question_id='' outcome=<value>.
--                     outcome='' here means a close that reported none, which is
--                     NOT the same as outcome='none' (guest tapped nothing).
--   invalid_depth     per route. BUG REPORTS, NOT BEHAVIOUR - see the marker
--   invalid_outcome   note above. 'invalid' also appears under outcomes on
--                     purpose: that view stays honest about what is in the
--                     table, these two are the alarm.
--
-- *** CLOSES ARE NOT VISITS. DO NOT COMPUTE A PER-VISIT AVERAGE FROM THEM. ***
-- One pageview can produce several closes. The widget's counters are scoped to
-- the PAGEVIEW and deliberately do not reset when the panel is closed and
-- reopened, because `position` is defined as "the Nth thing tapped in this
-- pageview". So a guest who taps twice, closes the panel, reopens it and closes
-- again produces TWO close rows, the second reporting the same cumulative
-- depth=2 with no new taps between them. Seen in real traffic on 2026-09-16,
-- rows 77-78: an open with no tap, then a close carrying depth=2 and a
-- question_id from two minutes earlier.
--
-- Consequences: SUM(depth) over closes double-counts, and AVG(depth) is
-- meaningless. `closes` and `outcomes` remain honest as "moments a guest
-- stopped", which is what they are named for. There is no identifier linking
-- rows, BY DESIGN, so you cannot tell which closes belong to one pageview and
-- cannot correct for it after the fact.
--
-- THE FIX, NOT IMPLEMENTED: the widget could send depth SINCE THE LAST CLOSE
-- rather than cumulative, which would make closes additive. That is a behaviour
-- change to a shipped contract - old and new rows would mean different things
-- with nothing in the row to say which - so it needs its own pass, a cutover
-- date, and probably a source value to tell the eras apart.
--
-- A metric with a count of zero produces NO ROW rather than a row of 0. Absence
-- is zero. That matters most for the two invalid_* metrics: a row appearing at
-- all is the signal.
--
-- The rollup DELETEs the day before inserting it, inside one atomic db.batch().
-- That is stronger than upsert alone, which cannot remove a row whose underlying
-- events have gone - re-rolling a corrected day would leave the stale figure
-- behind forever. Verified: deleting an event and re-rolling leaves 0 stale rows.
--
-- The PK's leading column is day, so a date range across all routes is already
-- covered. This serves the other axis - one route over time, which is how the
-- dashboard is most likely to be sliced.
CREATE INDEX IF NOT EXISTS idx_daily_route_day
  ON daily_stats (route, day);

-- ---------------------------------------------------------------------------
-- content_changes — what T changed, so usage can be read against content edits.
-- ---------------------------------------------------------------------------
-- A tap count that moves the day after a question is reworded is a different
-- story from one that moves on its own. Populated from publish.py's RESULT line
-- (changed=N); nothing writes to it yet.
CREATE TABLE IF NOT EXISTS content_changes (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  ts      TEXT    NOT NULL,
  day     TEXT    NOT NULL,
  changed INTEGER NOT NULL,       -- how many units changed in that publish
  detail  TEXT                    -- short human description
);

CREATE INDEX IF NOT EXISTS idx_content_changes_day
  ON content_changes (day);
