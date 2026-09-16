/**
 * grace-assistant-router
 *
 * Given the question a guest just tapped, picks the best 2-3 follow-up questions
 * to show next from a list of IDs the page already approved.
 *
 * Contract, in both directions:
 *   POST { page, tappedId, history, candidateIds }  ->  200 { ids: [...] }
 *
 * Two rules this Worker never breaks:
 *   1. It can only ever return IDs that arrived in candidateIds. The model is
 *      constrained to that set by schema AND the output is filtered against it
 *      again here, so a hallucinated ID cannot reach the widget.
 *   2. It never returns a non-200. Every failure path - bad JSON, missing key,
 *      API down, timeout, refusal, garbage response - returns { ids: [] }, and
 *      the widget falls back to its own static follow-ups without the guest
 *      ever seeing a hiccup.
 *
 * The API key is read from env.ANTHROPIC_API_KEY (a Worker secret). It is never
 * hardcoded, never logged, and never echoed in a response.
 *
 * TWO ENDPOINTS, split on pathname:
 *   POST /        ranking, as above. Unchanged.
 *   POST /event   usage telemetry -> one row in D1 (env.USAGE_DB). Added
 *                 2026-09-15. Same origin allowlist, same always-200 contract.
 *
 * The ranking endpoint is the bare path because that is what the widget has
 * always posted to; adding a path for it would have been a breaking change for
 * a file that is already deployed.
 */

const ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages';
const ANTHROPIC_VERSION = '2023-06-01';

// Override per-environment with a `MODEL` var in wrangler.toml if needed.
const DEFAULT_MODEL = 'claude-haiku-4-5';

const API_TIMEOUT_MS = 5000; // fall back to static follow-ups rather than stall
const MAX_TOKENS = 256;      // the reply is a short list of IDs
const MAX_IDS = 3;
const MIN_IDS = 2;
const MAX_CANDIDATES = 40;   // bound the prompt regardless of what is posted
const MAX_HISTORY = 10;

const ALLOWED_ORIGINS = [
  'https://discovergrace.com',
  'https://www.discovergrace.com',
  'https://grace-assistant.pages.dev',
  'https://assistant.discovergrace.ai',
  'https://grace-demo.pages.dev',
  /* The usage dashboard, added 2026-09-16. Two entries because a Pages project
     always answers on its own pages.dev name as well as its custom domain, and
     the dashboard will be reached on the pages.dev one until the DNS record for
     widget.discovergrace.ai exists. Same pattern as grace-assistant above.
     These are the ONLY additions - /stats reads nothing a guest can see, but it
     is still gated by the same one list as everything else. */
  'https://widget.discovergrace.ai',
  'https://grace-widget-dashboard.pages.dev'
];

/**
 * CORS headers for one request. The caller's Origin is echoed back only when it
 * is on the allowlist; anything else gets no Access-Control-Allow-Origin at all,
 * so the browser refuses the response. Vary: Origin keeps a cache from serving
 * one site's ACAO to another.
 */
function corsHeaders(request) {
  const headers = {
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
    'Vary': 'Origin'
  };

  let origin = null;
  try {
    origin = request && request.headers ? request.headers.get('Origin') : null;
  } catch (err) {
    origin = null;
  }

  if (origin && ALLOWED_ORIGINS.indexOf(origin) !== -1) {
    headers['Access-Control-Allow-Origin'] = origin;
  }

  return headers;
}

const SYSTEM_PROMPT = [
  'You order follow-up questions for a church website help widget.',
  '',
  'A guest just tapped a question and read its answer. You are given the IDs of the',
  'follow-up questions that page has approved. Choose the 2-3 that a real person is',
  'most likely to want next, and put the most likely first.',
  '',
  'Rules:',
  '- Only ever return IDs from the candidate list you are given. Never invent one.',
  '- Never return the ID the guest just tapped, and never return one already in history.',
  '- Return 2 or 3 IDs. Prefer 3 when the candidates are genuinely useful, 2 when they are not.',
  '- Think about what practically comes next for someone planning a visit: after service',
  '  times they often want directions or parking; after kids they often want check-in or',
  '  nursing details; after giving they often want to reach a person.'
].join('\n');

function jsonResponse(body, request) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: {
      ...corsHeaders(request),
      'Content-Type': 'application/json',
      'Cache-Control': 'no-store'
    }
  });
}

function empty(request) {
  return jsonResponse({ ids: [] }, request);
}

function stringsOnly(value, limit) {
  if (!Array.isArray(value)) return [];
  const out = [];
  for (const item of value) {
    if (typeof item === 'string' && item.length > 0 && item.length <= 120) {
      out.push(item);
      if (out.length >= limit) break;
    }
  }
  return out;
}

/* ------------------------------------------------------------------ */
/* Usage telemetry                                                     */
/* ------------------------------------------------------------------ */

/* This endpoint is PUBLIC and UNAUTHENTICATED by necessity - a guest's browser
   cannot hold a credential. Every field is therefore treated as hostile, and
   every bound below exists to stop a crafted POST doing something the schema
   did not intend. Anything that fails a check is dropped silently: logged,
   answered 200, not written. A caller learns nothing about why. */

/* ===================================================================== */
/* THE PAYLOAD CONTRACT — POST /event                                    */
/* ===================================================================== */
/*
 * Part 2 (the widget) is written against THIS. Get it wrong and nothing
 * complains: the endpoint answers 200, drops or marks the row, and the first
 * symptom is a dashboard that is empty or quietly wrong, weeks later.
 *
 * EVERYTHING BELOW MARKED (probed) WAS GENERATED BY RUNNING toEventRow, not
 * written by hand. Regenerate it after any change to the validator rather than
 * editing it - the block's whole value is that it was measured. The generator
 * lives with the session notes; it feeds inputs in and records what comes out.
 *
 * Minimal accepted bodies:
 *   open   {"kind":"open",  "route":"/giving/"}
 *   tap    {"kind":"tap",   "route":"/giving/", "question_id":"how-to-give",
 *           "position":1}
 *   close  {"kind":"close", "route":"/giving/"}
 *
 * Reading the table: FORBIDDEN means the WHOLE EVENT IS DROPPED if the field is
 * present - not that the field is ignored. Sending question_id on an open loses
 * the open. "ignored" means accepted and silently discarded (a close may carry
 * position; it is never stored).
 *
 * FIELD BY KIND  (probed)
 *   field        | open      | tap       | close
 *   -------------|-----------|-----------|----------
 *   kind         | REQUIRED  | REQUIRED  | REQUIRED
 *   route        | REQUIRED  | REQUIRED  | REQUIRED 
 *   question_id  | FORBIDDEN | REQUIRED  | optional 
 *   position     | FORBIDDEN | REQUIRED  | ignored  
 *   depth        | FORBIDDEN | FORBIDDEN | optional 
 *   outcome      | FORBIDDEN | FORBIDDEN | optional 
 *
 * BOUNDS  (probed)
 *   kind         exactly 'open' | 'tap' | 'close'. Case-sensitive.
 *   route        string, 1..120 chars, MUST START WITH '/'.  "giving" is dropped.
 *   question_id  string, 1..64 chars.
 *   position     integer 1..100. Floats and numeric strings are rejected.
 *   depth        integer 0..100.
 *   outcome      exactly 'none' | 'read' | 'person' | 'exhausted'.
 *   body         2048 bytes max, refused before parsing (Content-Length).
 *
 * UNUSABLE VALUES ARE MARKED, NOT DROPPED AND NOT CLAMPED  (probed)
 *   A close whose depth or outcome is present but unusable is still written,
 *   with the offending field set to -1 / 'invalid'. Absent stays NULL.
 *
 *   sent                        -> stored
 *     depth=3                     -> depth=3
 *     depth=0                     -> depth=0
 *     depth=100                   -> depth=100
 *     depth=101                   -> depth=-1
 *     depth=-1                    -> depth=-1
 *     depth=1.5                   -> depth=-1
 *     depth="3"                   -> depth=-1
 *     depth=null                  -> depth=null
 *     depth=(absent)              -> depth=null
 *     outcome="read"              -> outcome="read"
 *     outcome="exploded"          -> outcome="invalid"
 *     outcome=""                  -> outcome="invalid"
 *     outcome=123                 -> outcome="invalid"
 *     outcome=null                -> outcome=null
 *     outcome=(absent)            -> outcome=null
 *
 *   position is DIFFERENT and stays different: a tap REQUIRES it, so an
 *   unusable position has no row to mark and the tap is dropped.
 *     tap position=1             -> position=1
 *     tap position=100           -> position=100
 *     tap position=101           -> EVENT DROPPED
 *     tap position=0             -> EVENT DROPPED
 *     tap position=1.5           -> EVENT DROPPED
 *
 * SERVER-GENERATED - SEND THESE AND THEY ARE IGNORED  (probed)
 *   sent ts=1999-01-01T00:00:00.000Z day=1999-01-01 id=999
 *   stored ts=2026-09-15... day=2026-09-15   id absent (SQLite AUTOINCREMENT)
 *   row keys: ["ts","day","kind","route","question_id","position","depth","outcome"]
 *   A caller-supplied ts is refused on purpose: it would let anyone backdate
 *   rows into a closed reporting period.
 *
 * NEVER PERSISTED, whatever is sent
 *   Unknown fields are dropped on the floor: a POST carrying {"ip":"1.2.3.4",
 *   "evil":"x"} writes a row with neither. No IP, no headers, no user agent, no
 *   identifier of any kind. The schema is the entire contract; see the header of
 *   worker/schema.sql for why that is a commitment and not an oversight.
 *
 * RESPONSE
 *   Always 200 {"ok":true}. It does NOT indicate whether a row was written, by
 *   design - a guest must never notice telemetry failing, and a hostile caller
 *   must not learn which field was rejected. To check it worked, count rows in
 *   D1. A 200 is not a receipt.
 *
 * ORIGIN
 *   Same allowlist as the ranking endpoint, same function, one list. NO Origin
 *   header is refused, so a bare curl writes nothing - manual testing needs
 *   -H "Origin: https://discovergrace.com".
 */

const EVENT_KINDS = ['open', 'tap', 'close'];
const EVENT_OUTCOMES = ['none', 'read', 'person', 'exhausted'];

const MAX_ROUTE_LEN = 120;
const MAX_QUESTION_ID_LEN = 64;
/* A visit with more than 100 taps is not a person. Out-of-range values are
   DROPPED rather than clamped - clamping would silently invent data, and a
   position of 100 that was really 10^9 is worse than no row at all. */
const MAX_POSITION = 100;
const MAX_DEPTH = 100;

/* Markers for "the caller sent something, and it was unusable".
 *
 * The alternative to these is silence, and silence is the expensive option. A
 * close whose depth failed its bounds used to be written with depth NULL -
 * indistinguishable from a close that legitimately reported no depth. The visit
 * vanished from "where do people stop" and nothing anywhere counted it. Dropping
 * the whole row instead is no better: a row that was never written cannot be
 * counted either.
 *
 * So: never invent data (no clamping - a depth of 100 that was really 10^9 is a
 * lie), never discard the row, and make the failure COUNTABLE. -1 and 'invalid'
 * are not values a guest can produce; they can only come from a caller sending
 * something the contract forbids.
 *
 * FOR WHOEVER BUILDS THE DASHBOARD: these are their own bucket. Never average
 * over depth without excluding -1, and never fold 'invalid' into 'none'. A
 * rising count of either means THE WIDGET IS BROKEN - it is a bug report, not a
 * fact about guests. */
const DEPTH_INVALID = -1;
const OUTCOME_INVALID = 'invalid';
/* A well-formed event is a couple of hundred bytes. Refuse to even parse
   anything larger rather than burning CPU on a hostile body. */
const MAX_EVENT_BODY_BYTES = 2048;

function shortString(value, limit) {
  return (typeof value === 'string' && value.length > 0 && value.length <= limit)
    ? value
    : null;
}

/* A whole number in [min, max], or null. Rejects floats, NaN, Infinity,
   numeric strings and anything else - only a real integer in range passes. */
function boundedInt(value, min, max) {
  if (typeof value !== 'number' || !Number.isInteger(value)) return null;
  if (value < min || value > max) return null;
  return value;
}

/**
 * Whatever was posted -> a row this schema will accept, or null.
 *
 * ts and day are generated HERE, never taken from the caller. A client-supplied
 * timestamp is hostile input: it would let anyone backdate rows into a closed
 * reporting period, and it is not information the caller is better placed to
 * know than we are.
 */
function toEventRow(body) {
  if (!body || typeof body !== 'object') return null;

  const kind = shortString(body.kind, 16);
  if (!kind || EVENT_KINDS.indexOf(kind) === -1) return null;

  /* Routes in this system are always normalised paths. Requiring the leading
     slash is stricter than "must be a string" on purpose - it costs a real
     caller nothing and rejects a whole class of junk. */
  const route = shortString(body.route, MAX_ROUTE_LEN);
  if (!route || route.charAt(0) !== '/') return null;

  const questionId = shortString(body.question_id, MAX_QUESTION_ID_LEN);
  const position = boundedInt(body.position, 1, MAX_POSITION);

  /* Present-but-unusable has to be distinguishable from absent, and a parsed
     value cannot tell you which it was - both arrive as null. So presence is
     tested on the raw body before parsing. undefined and an explicit null both
     count as absent. */
  const depthSent = body.depth !== undefined && body.depth !== null;
  const outcomeSent = body.outcome !== undefined && body.outcome !== null;

  const depthValue = boundedInt(body.depth, 0, MAX_DEPTH);
  const outcomeRaw = shortString(body.outcome, 16);
  const outcomeValue = (outcomeRaw !== null && EVENT_OUTCOMES.indexOf(outcomeRaw) !== -1)
    ? outcomeRaw
    : null;

  const depth = depthSent ? (depthValue === null ? DEPTH_INVALID : depthValue) : null;
  const outcome = outcomeSent ? (outcomeValue === null ? OUTCOME_INVALID : outcomeValue) : null;

  /* Per-kind requirements. A tap without a question is not a tap - recording it
     would put a row in the table that no query can make sense of. */
  if (kind === 'tap' && (!questionId || position === null)) return null;
  /* Forbidden fields are tested on PRESENCE, not on the parsed value: sending
     depth on a tap is a caller with a bug whether or not the value was valid. */
  if (kind !== 'close' && (depthSent || outcomeSent)) return null;
  if (kind === 'open' && (questionId !== null || position !== null)) return null;

  const now = new Date();
  const ts = now.toISOString();

  return {
    ts,
    day: ts.slice(0, 10),          // YYYY-MM-DD, UTC, same instant as ts
    kind,
    route,
    question_id: questionId,
    position: kind === 'tap' ? position : null,
    depth: kind === 'close' ? depth : null,
    outcome: kind === 'close' ? outcome : null
  };
}

/**
 * One validated event -> one row. Never throws: a telemetry failure must not be
 * something a guest can notice, so every problem is logged and swallowed.
 *
 * Nothing beyond the schema is persisted. No IP, no headers, no user agent, no
 * identifier of any kind - see the header of worker/schema.sql for why that is a
 * commitment rather than an oversight.
 */
async function writeEvent(db, row) {
  try {
    await db
      .prepare(
        'INSERT INTO events (ts, day, kind, route, question_id, position, depth, outcome) ' +
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
      )
      .bind(row.ts, row.day, row.kind, row.route,
            row.question_id, row.position, row.depth, row.outcome)
      .run();
    return true;
  } catch (err) {
    console.log('usage write failed:', err && err.name ? err.name : 'error');
    return false;
  }
}

/* ------------------------------------------------------------------ */
/* Nightly rollup: events -> daily_stats                               */
/* ------------------------------------------------------------------ */

/* DAYS THAT ARE OURS, NOT GUESTS'.
 *
 * 2026-09-16 is 21 rows from four scripted walks run by RTS while turning
 * counting on for the demo - a person handoff, an exhausted walk, a 'none'
 * close and a panel-X close. Rolling them up would make the first numbers the
 * dashboard ever shows a record of us clicking.
 *
 * ADD ANY FUTURE TEST DAY HERE. This array is the one place the rollup knows
 * about test data; a date buried in a WHERE clause would be invisible to the
 * next person and would silently stop being complete the moment someone tested
 * again. It is also recorded in HANDOFF.md - keep the two in step. */
const EXCLUDED_DAYS = ['2026-09-16'];

/* Every metric this job writes. daily_stats.metric is one of these, and the
 * dashboard should know no others.
 *
 *   opens / closes        per route
 *   taps / first_taps /   per route per question. first_taps is position=1,
 *   later_taps            later_taps is position>=2 - the pair is what answers
 *                         "how many people asked more than one question"
 *                         without any identifier linking rows together.
 *   outcomes              per route per outcome value, including '' for a close
 *                         that reported none. NOT the same as outcome 'none',
 *                         which means the guest tapped nothing.
 *   invalid_depth /       per route. THESE ARE BUG REPORTS, NOT BEHAVIOUR. See
 *   invalid_outcome       the marker note in schema.sql. A rising count means
 *                         the widget is sending values the contract forbids.
 *                         'invalid' also appears under outcomes, deliberately:
 *                         that view stays honest about what is in the table,
 *                         and this one is the alarm. */

/* The day's statements, in order. Parameterised on day - never interpolated.
 *
 * DELETE-then-INSERT rather than upsert alone, which is a deliberate departure
 * from the note in schema.sql and is strictly stronger. Upsert makes a re-run
 * idempotent only for rows that still exist: if a question stops appearing for
 * that day (events corrected, a bad row removed), its stale daily_stats row
 * survives the re-run with its old value and nothing ever clears it. Clearing
 * the day first makes the rollup a true projection of events-as-they-are-now.
 * Both statements run in one db.batch(), which D1 executes atomically, so there
 * is no window where the day is deleted but not yet rebuilt.
 *
 * Every SELECT is filtered to a single day, which idx_events_day_kind serves,
 * and every one also filters on kind, which is that index's second column.
 * Nothing here scans the table. */
function rollupStatements(day) {
  const ins = 'INSERT INTO daily_stats (day, route, question_id, metric, outcome, value) ';
  return [
    ['DELETE FROM daily_stats WHERE day = ?', [day]],

    [ins + "SELECT day, route, '', 'opens', '', COUNT(*) FROM events " +
      "WHERE day = ? AND kind = 'open' GROUP BY day, route", [day]],

    [ins + "SELECT day, route, '', 'closes', '', COUNT(*) FROM events " +
      "WHERE day = ? AND kind = 'close' GROUP BY day, route", [day]],

    /* question_id is NOT NULL on a tap by contract, but the guard costs nothing
       and a NULL here would violate daily_stats' NOT NULL and fail the batch. */
    [ins + "SELECT day, route, question_id, 'taps', '', COUNT(*) FROM events " +
      "WHERE day = ? AND kind = 'tap' AND question_id IS NOT NULL " +
      "GROUP BY day, route, question_id", [day]],

    [ins + "SELECT day, route, question_id, 'first_taps', '', COUNT(*) FROM events " +
      "WHERE day = ? AND kind = 'tap' AND question_id IS NOT NULL AND position = 1 " +
      "GROUP BY day, route, question_id", [day]],

    [ins + "SELECT day, route, question_id, 'later_taps', '', COUNT(*) FROM events " +
      "WHERE day = ? AND kind = 'tap' AND question_id IS NOT NULL AND position >= 2 " +
      "GROUP BY day, route, question_id", [day]],

    /* COALESCE, not a filter: a close that reported no outcome is still a close
       and belongs in this breakdown as '' - the schema's "'' means absent". */
    [ins + "SELECT day, route, '', 'outcomes', COALESCE(outcome, ''), COUNT(*) FROM events " +
      "WHERE day = ? AND kind = 'close' GROUP BY day, route, COALESCE(outcome, '')", [day]],

    [ins + "SELECT day, route, '', 'invalid_depth', '', COUNT(*) FROM events " +
      "WHERE day = ? AND kind = 'close' AND depth = -1 GROUP BY day, route", [day]],

    [ins + "SELECT day, route, '', 'invalid_outcome', '', COUNT(*) FROM events " +
      "WHERE day = ? AND kind = 'close' AND outcome = 'invalid' GROUP BY day, route", [day]]
  ];
}

/* YYYY-MM-DD for the UTC day N days before the given instant. */
function utcDay(date, back) {
  const d = new Date(date.getTime() - (back || 0) * 86400000);
  return d.toISOString().slice(0, 10);
}

/**
 * Roll one day. Returns a short result object for the log; never throws, because
 * an unhandled throw in a scheduled handler is a silent red mark nobody is
 * watching, and the next night's run would fix it anyway.
 */
async function rollupDay(db, day) {
  if (EXCLUDED_DAYS.indexOf(day) !== -1) {
    return { day: day, status: 'skipped-test-day' };
  }
  if (!db) return { day: day, status: 'no-binding' };
  try {
    const statements = rollupStatements(day).map(function (pair) {
      const stmt = db.prepare(pair[0]);
      return stmt.bind.apply(stmt, pair[1]);
    });
    const results = await db.batch(statements);
    let read = 0, written = 0;
    for (const r of results) {
      if (r && r.meta) {
        read += r.meta.rows_read || 0;
        written += r.meta.rows_written || 0;
      }
    }
    return { day: day, status: 'ok', rows_read: read, rows_written: written };
  } catch (err) {
    return { day: day, status: 'failed', error: err && err.name ? err.name : 'error' };
  }
}

/**
 * Server-side budget lock. Separate concern from CORS: the CORS headers decide
 * what a browser is allowed to READ, this decides whether we SPEND an API call
 * at all. A blocked caller never reaches the Anthropic request.
 *
 * A MISSING Origin is rejected as well. A real guest's browser always sends
 * Origin on a cross-origin POST, so no Origin means the caller is not a guest.
 * That tradeoff is deliberate and it also blocks bare curl and server-side
 * callers - our own manual tests now need -H "Origin: https://discovergrace.com"
 * (or any other allowlisted origin) to get past this.
 */
function originAllowed(request) {
  let origin = null;
  try {
    origin = request && request.headers ? request.headers.get('Origin') : null;
  } catch (err) {
    return false;
  }
  return !!origin && ALLOWED_ORIGINS.indexOf(origin) !== -1;
}

/**
 * Ask the model to rank the candidates. Throws on any problem; the caller turns
 * that into an empty list.
 */
async function chooseFollowUps(payload, apiKey, model) {
  const { page, tappedId, history, candidateIds } = payload;

  const request = {
    model,
    max_tokens: MAX_TOKENS,
    system: SYSTEM_PROMPT,
    messages: [
      {
        role: 'user',
        content: JSON.stringify({
          page,
          just_tapped: tappedId,
          already_seen: history,
          candidates: candidateIds
        })
      }
    ],
    // enum pins the model to the approved IDs at decode time. The filter after
    // this call is the second line of defence, not the only one.
    output_config: {
      format: {
        type: 'json_schema',
        schema: {
          type: 'object',
          properties: {
            ids: {
              type: 'array',
              description: 'Between 2 and 3 candidate IDs, best first.',
              items: { type: 'string', enum: candidateIds }
            }
          },
          required: ['ids'],
          additionalProperties: false
        }
      }
    }
  };

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), API_TIMEOUT_MS);

  let response;
  try {
    response = await fetch(ANTHROPIC_API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': ANTHROPIC_VERSION
      },
      body: JSON.stringify(request),
      signal: controller.signal
    });
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) throw new Error('anthropic ' + response.status);

  const result = await response.json();

  // A safety refusal is HTTP 200 but the body will not match the schema.
  if (result.stop_reason === 'refusal') throw new Error('refusal');

  const block = Array.isArray(result.content)
    ? result.content.find((b) => b && b.type === 'text' && typeof b.text === 'string')
    : null;
  if (!block) throw new Error('no text block');

  const parsed = JSON.parse(block.text);
  return Array.isArray(parsed.ids) ? parsed.ids : [];
}

/**
 * Reduce whatever the model returned to IDs we know are safe to show:
 * strings, in the approved set, not the tapped one, no duplicates, max 3.
 */
function filterToApproved(ids, candidateIds, tappedId) {
  const approved = new Set(candidateIds);
  const seen = new Set();
  const out = [];

  for (const id of Array.isArray(ids) ? ids : []) {
    if (typeof id !== 'string') continue;
    if (!approved.has(id)) continue;
    if (id === tappedId) continue;
    if (seen.has(id)) continue;
    seen.add(id);
    out.push(id);
    if (out.length >= MAX_IDS) break;
  }

  // One usable suggestion reads like a dead end - let the widget's static
  // follow-ups handle it instead.
  return out.length >= MIN_IDS ? out : [];
}

/**
 * POST /event - record one usage event.
 *
 * ALWAYS 200 { ok: true }, whatever happened. The response deliberately does not
 * say whether a row was written: a guest must never be able to notice telemetry
 * failing, and a hostile caller must not learn which of its fields was rejected.
 * Row counts in D1 are the way to check this worked, not the response body.
 */
async function handleEvent(request, env) {
  const ok = () => jsonResponse({ ok: true }, request);

  // Same lock as the ranking endpoint, same function - not a second copy of the
  // list. No Origin at all is refused here exactly as it is there.
  if (!originAllowed(request)) {
    console.log('usage guard: origin-not-allowed');
    return ok();
  }

  const declared = Number(request.headers.get('Content-Length'));
  if (Number.isFinite(declared) && declared > MAX_EVENT_BODY_BYTES) {
    console.log('usage guard: body-too-large');
    return ok();
  }

  const body = await request.json().catch(() => null);
  const row = toEventRow(body);
  if (!row) {
    console.log('usage guard: malformed-dropped');
    return ok();
  }

  if (!env || !env.USAGE_DB) {
    console.log('usage guard: no-binding');
    return ok();
  }

  await writeEvent(env.USAGE_DB, row);
  return ok();
}

/* ------------------------------------------------------------------ */
/* GET /stats - the dashboard's reader                                  */
/* ------------------------------------------------------------------ */

/* Never more than this in one request. 400 days is a year plus slack for a
   year-on-year comparison; past that a single crafted request starts walking
   the whole table, which is the exact cost daily_stats exists to avoid. */
const STATS_MAX_DAYS = 400;
const STATS_DEFAULT_DAYS = 30;

function isDay(v) {
  return typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v) &&
         !isNaN(Date.parse(v + 'T00:00:00Z'));
}

function daysBetween(from, to) {
  return Math.round(
    (Date.parse(to + 'T00:00:00Z') - Date.parse(from + 'T00:00:00Z')) / 86400000
  ) + 1;
}

function statsError(request, status, message) {
  return new Response(JSON.stringify({ error: message }), {
    status: status,
    headers: {
      ...corsHeaders(request),
      'Content-Type': 'application/json',
      'Cache-Control': 'no-store'
    }
  });
}

/**
 * GET /stats?from=YYYY-MM-DD&to=YYYY-MM-DD
 *
 * READS daily_stats ONLY. Never events - see the comment on the events table in
 * worker/schema.sql: an aggregate over raw events reads every row it scans, and
 * a dashboard refreshing against a full table would burn the daily read budget
 * and stop D1 answering queries at all. This endpoint is the reason that table
 * exists; it must not be the thing that defeats it.
 *
 * UNLIKE /event, THIS ONE REPORTS FAILURE. A telemetry write that vanishes costs
 * a row nobody misses; a dashboard that spins forever because the fetch failed
 * silently costs someone an afternoon. 400 for a bad request, 500 for a read
 * that failed, both as JSON with an `error` string and both carrying CORS
 * headers so the browser can actually read them.
 */
async function handleStats(request, env) {
  if (request.method !== 'GET') {
    return statsError(request, 405, 'GET only');
  }
  if (!originAllowed(request)) {
    /* Deliberately terse and deliberately a real status: a browser on an
       unlisted origin could not read the body anyway, and saying more would
       only help someone probing. */
    return statsError(request, 403, 'origin not allowed');
  }

  let url;
  try {
    url = new URL(request.url);
  } catch (err) {
    return statsError(request, 400, 'bad url');
  }

  const today = new Date().toISOString().slice(0, 10);
  const to = url.searchParams.get('to') || today;
  const from = url.searchParams.get('from') ||
    utcDay(new Date(Date.parse(to + 'T00:00:00Z')), STATS_DEFAULT_DAYS - 1);

  if (!isDay(from) || !isDay(to)) {
    return statsError(request, 400, 'from and to must be YYYY-MM-DD');
  }
  if (from > to) {
    return statsError(request, 400, 'from must not be after to');
  }
  const span = daysBetween(from, to);
  if (span > STATS_MAX_DAYS) {
    return statsError(request, 400,
      'range is ' + span + ' days; the maximum is ' + STATS_MAX_DAYS);
  }
  if (!env || !env.USAGE_DB) {
    return statsError(request, 500, 'no database binding');
  }

  let rows;
  try {
    const result = await env.USAGE_DB
      .prepare(
        'SELECT day, route, question_id, metric, outcome, value FROM daily_stats ' +
        'WHERE day >= ? AND day <= ? ' +
        'ORDER BY day, route, metric, question_id, outcome'
      )
      .bind(from, to)
      .all();
    rows = result.results || [];
  } catch (err) {
    console.log('stats read failed:', err && err.name ? err.name : 'error');
    return statsError(request, 500, 'could not read usage data');
  }

  /* SHAPE: flat rows plus a thin envelope.
     Flat because it is exactly what the table holds - no reshaping to argue
     with, and a chart can group by whatever axis it wants in one pass. Nesting
     would bake one chart's idea of the hierarchy into the transport.

     `alarms` is a summary, NOT a fold: invalid_depth and invalid_outcome are
     still present in rows as their own metrics, untouched. The summary exists
     so a dashboard cannot quietly omit them - they are a bug report about the
     widget, and the one thing worse than not charting them is not noticing
     them. Zero here means no marker rows in range, which is the healthy case. */
  let invalidDepth = 0, invalidOutcome = 0;
  for (const r of rows) {
    if (r.metric === 'invalid_depth') invalidDepth += r.value;
    if (r.metric === 'invalid_outcome') invalidOutcome += r.value;
  }

  return new Response(JSON.stringify({
    from: from,
    to: to,
    days: span,
    row_count: rows.length,
    alarms: { invalid_depth: invalidDepth, invalid_outcome: invalidOutcome },
    rows: rows
  }), {
    status: 200,
    headers: {
      ...corsHeaders(request),
      'Content-Type': 'application/json',
      'Cache-Control': 'no-store'
    }
  });
}

export default {
  async fetch(request, env) {
    try {
      if (request.method === 'OPTIONS') {
        return new Response(null, { status: 204, headers: corsHeaders(request) });
      }

      // Split on pathname first. /stats is a GET, so it has to be routed before
      // the POST-only gate below; everything else is unchanged.
      let pathname = '/';
      try {
        pathname = new URL(request.url).pathname;
      } catch (err) {
        pathname = '/';
      }
      if (pathname === '/stats' || pathname === '/stats/') {
        return await handleStats(request, env);
      }

      // Anything that is not a POST still gets the fallback contract, not an error.
      if (request.method !== 'POST') {
        return empty(request);
      }

      // Everything that is not /event falls through to the ranking endpoint
      // below, so the bare path the widget has always posted to behaves exactly
      // as it did before these endpoints existed.
      if (pathname === '/event' || pathname === '/event/') {
        return await handleEvent(request, env);
      }

      // Budget lock. Nothing past this point can reach the Anthropic API unless
      // the caller is an allowlisted origin. Still a 200 with the fallback shape,
      // so a legitimate browser that somehow fails the check degrades quietly.
      if (!originAllowed(request)) {
        console.log('router guard: origin-not-allowed');
        return empty(request);
      }

      const body = await request.json().catch(() => null);
      if (!body || typeof body !== 'object') {
        return empty(request);
      }

      const candidateIds = stringsOnly(body.candidateIds, MAX_CANDIDATES);
      const tappedId = typeof body.tappedId === 'string' ? body.tappedId : '';
      const page = typeof body.page === 'string' ? body.page : '';
      const history = stringsOnly(body.history, MAX_HISTORY);

      // Nothing to choose between - no reason to spend a call.
      if (candidateIds.length < MIN_IDS) {
        return empty(request);
      }

      const apiKey = env && env.ANTHROPIC_API_KEY;
      if (!apiKey) {
        return empty(request);
      }

      const model = (env && env.MODEL) || DEFAULT_MODEL;


      const raw = await chooseFollowUps(
        { page, tappedId, history, candidateIds },
        apiKey,
        model
      );

      return jsonResponse({ ids: filterToApproved(raw, candidateIds, tappedId) }, request);
    } catch (err) {
      // Deliberately swallowed. The widget degrades to its static follow-ups,
      // and nothing about the key or the request is written to the log.
      // handleEvent already swallows its own failures, so reaching here from
      // /event means something truly unexpected - still a 200, still silent.
      console.log('router fallback:', err && err.name ? err.name : 'error');
      return empty(request);
    }
  },

  /**
   * Nightly rollup. Cron is in wrangler.toml.
   *
   * Rolls YESTERDAY, not today: the job runs at 03:25 UTC so the previous UTC
   * day is closed and cannot gain more rows. Rolling today would write a
   * partial day that looks complete.
   *
   * MANUAL RE-RUN, for a night that failed or a day that gained late rows.
   * There is no HTTP path for this on purpose - the rollup is pure SQL, so
   * exposing an endpoint would add public, unauthenticated attack surface to do
   * something wrangler already does with the operator's own credentials:
   *
   *   npx wrangler d1 execute grace-widget-usage --remote --command \
   *     "DELETE FROM daily_stats WHERE day = '2026-09-20';"
   *   # ...then the eight INSERTs from rollupStatements() with the day substituted.
   *
   * Simpler in practice: temporarily change the cron, or wait a night - the job
   * is idempotent, so re-rolling a day is always safe.
   */
  async scheduled(event, env, ctx) {
    const now = new Date(event && event.scheduledTime ? event.scheduledTime : Date.now());
    const day = utcDay(now, 1);
    const result = await rollupDay(env && env.USAGE_DB, day);
    console.log('rollup ' + JSON.stringify(result));
  }
};
