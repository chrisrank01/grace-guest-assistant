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
  'https://grace-demo.pages.dev'
];

/**
 * CORS headers for one request. The caller's Origin is echoed back only when it
 * is on the allowlist; anything else gets no Access-Control-Allow-Origin at all,
 * so the browser refuses the response. Vary: Origin keeps a cache from serving
 * one site's ACAO to another.
 */
function corsHeaders(request) {
  const headers = {
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
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

const EVENT_KINDS = ['open', 'tap', 'close'];
const EVENT_OUTCOMES = ['none', 'read', 'person', 'exhausted'];

const MAX_ROUTE_LEN = 120;
const MAX_QUESTION_ID_LEN = 64;
/* A visit with more than 100 taps is not a person. Out-of-range values are
   DROPPED rather than clamped - clamping would silently invent data, and a
   position of 100 that was really 10^9 is worse than no row at all. */
const MAX_POSITION = 100;
const MAX_DEPTH = 100;
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
  const depth = boundedInt(body.depth, 0, MAX_DEPTH);
  const outcome = shortString(body.outcome, 16);

  /* Per-kind requirements. A tap without a question is not a tap - recording it
     would put a row in the table that no query can make sense of. */
  if (kind === 'tap' && (!questionId || position === null)) return null;
  if (outcome !== null && EVENT_OUTCOMES.indexOf(outcome) === -1) return null;
  if (kind !== 'close' && (depth !== null || outcome !== null)) return null;
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

export default {
  async fetch(request, env) {
    try {
      if (request.method === 'OPTIONS') {
        return new Response(null, { status: 204, headers: corsHeaders(request) });
      }

      // Anything that is not a POST still gets the fallback contract, not an error.
      if (request.method !== 'POST') {
        return empty(request);
      }

      // Split on pathname. Everything that is not /event falls through to the
      // ranking endpoint below, so the bare path the widget has always posted to
      // behaves exactly as it did before this endpoint existed.
      let pathname = '/';
      try {
        pathname = new URL(request.url).pathname;
      } catch (err) {
        pathname = '/';
      }
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
  }
};
