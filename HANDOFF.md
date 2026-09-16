# Grace Guest Assistant — Handoff

**Built by:** RTS (Relax Technical Services) — Chris Rank, chris@relax-tech.com
**For:** Grace Church Orlando — discovergrace.com
**Status at handoff:** built, deployed, publishing automated. Not yet embedded on
the live WordPress site — see **GO-LIVE**.
**Last updated:** 2026-09-13

This document contains **no secret values**. It names credentials and says where
they live; it never reproduces one.

---

## 1. SYSTEM MAP

### Widget assets (what a guest's browser loads)

| Surface | URL | Purpose |
|---|---|---|
| Branded host | `https://assistant.discovergrace.ai` | Primary. CNAME `assistant` → `grace-assistant.pages.dev`, proxied, in the `discovergrace.ai` zone |
| Pages project | `https://grace-assistant.pages.dev` | Same files, byte-identical. Cloudflare Pages project `grace-assistant` |

Serves four files plus `_headers` and a `fonts/` directory:

- `grace-assistant.js` — the whole widget. Vanilla JS, no dependencies, no build
  step. Renders inside a shadow root with `:host { all: initial }`, so the host
  page's CSS cannot reach in and the widget cannot leak out.

  **A tapped question does not come back.** This shipped behind
  `?ga-hide-tapped=1` on 2026-09-07 and **became the default on 2026-09-13**;
  the flag and the comparison harness that ran the widget with it off are both
  retired, so there is no longer an "off" to compare against. When a guest has
  tapped everything on a page, the panel says so and hands off to a person —
  wording from PLACEMENT's `End of questions`, falling back to the widget's own
  `EXHAUSTION_NOTE`. `talk-person` is exempt and never counts toward exhaustion.
  State is two closure variables: **no localStorage, no sessionStorage, no
  cookies.** A reload is the reset. `Start over` clears it; `Back` does not,
  because Back is navigation, not a reset.

  **The end-of-questions line replaces the CHIP LIST, never the card.** The
  guest keeps the answer they just asked for, and `Talk to a person` stays
  pinned, so a human is one tap away. This is the fix for a bug live between the
  2026-09-13 and 2026-09-14 deploys: exhaustion called `select('talk-person')`,
  whose first act is `feed.textContent = ''`, so tapping the last question on a
  page rendered its answer and then wiped it milliseconds later — the guest
  asked a question and got a phone number. **Contact details are now one tap
  away rather than automatic.** That is the trade: the old behaviour bought that
  convenience by throwing away the answer.

  **Why four review passes missed it:** every exhaustion test asserted the
  handoff *happened* — note renders, person card renders, chips empty, no echo
  bubble — and not one asserted the guest still had the answer. The feature test
  passed while the guest experience was broken. **Write the next battery against
  what the guest sees, not against what the code did.**
- `answers.json` — all guest-visible content. **Generated. Never hand-edit.**
- `test.html` — a local mock harness. **Remove from the production origin at
  handoff** (see checklist). Note Pages strips the extension, so it is live at
  `/test` as well as `/test.html`.
- `fonts/QuincyCF-Medium.woff2` — 36,692 bytes. **The widget does ship one font.**
  Every other family is pinned to a face Grace already registers document-wide,
  but Quincy Medium is not among them (discovergrace.com serves Quincy *Black*
  only), so naming it without shipping it would have fallen back silently.
  Added 2026-09-07, converted from Grace's licensed `QuincyCF-Medium.otf`.
- `_headers` — `X-Robots-Tag: noindex` on everything, plus
  `Access-Control-Allow-Origin: *` on `/fonts/*`.

**Why the font needs a CORS header.** The widget is embedded cross-origin by
design, and browsers fetch fonts in CORS mode whatever the markup says. Without
that header the file is blocked and the heading falls back to quincy-black with
no console error. Cloudflare Pages happens to send `Access-Control-Allow-Origin: *`
on static assets by default, so this worked before the rule existed — the rule is
there so the requirement is stated rather than inherited from a platform default
that could change.

**The `@font-face` lives in `document.head`, NOT in the shadow root.** This looks
like a violation of the widget's own encapsulation rule and is deliberate:
Chromium and WebKit **ignore `@font-face` declared inside a shadow root**. The
family still resolves, the file is simply never fetched, and the text renders in
the fallback with no error of any kind. This was not assumed — it was proven on
2026-09-07 with a named probe: the identical face was injected into the shadow
root under the family `shadow-scoped-probe` and measured at exactly the monospace
baseline (1127.05px), while the same file declared in `document.head` measured
872.13px. One `<style>` element carrying one rule is the entire exception;
everything visual stays inside the shadow root. **Do not "fix" this by moving the
rule back.**

**Default-hide contract:** `answers.json` has no `default` route key, so the
widget renders *nothing at all* on any page not explicitly listed. Adding a page
is a content change, not a code change.

### Ranking Worker

`https://grace-assistant-router.relax-tech.workers.dev` (source: `worker/`)

Takes `POST {page, tappedId, history, candidateIds}` and returns `{"ids":[…]}` —
at most 3, always HTTP 200. Model `claude-haiku-4-5`, ~$0.0003/call.

**That is the alias, not a dated snapshot.** `DEFAULT_MODEL` in
`worker/src/index.js` is `'claude-haiku-4-5'`, and no `MODEL` variable is bound on
the Worker, so the alias is what runs. The implication is worth stating plainly:
Anthropic can repoint the alias, so the model backing this Worker can change
without anyone deploying anything. That is an accepted trade — the Worker is a
ranking enhancement whose every failure path already degrades to the widget's
static follow-ups — but if a pinned model is ever wanted, bind `MODEL` to a dated
id rather than editing the default.

**It is an enhancement, never a dependency.** If it is slow, broken, or deleted,
the widget shows its static follow-up chips and the guest notices nothing. This is
proven live, and is the single most important property of the design.

**It now has a second endpoint and a database.** Added 2026-09-15:

| Path | Purpose |
|---|---|
| `POST /` | ranking, as above. Unchanged — the widget has always posted to the bare path, so it stays there. |
| `POST /event` | usage telemetry. One validated event → one row in D1. |

Binding `env.USAGE_DB` → D1 database **`grace-widget-usage`**
(`f0d62985-5c9f-4811-8843-2d8fce7b3e07`, region ENAM). Schema is
version-controlled at `worker/schema.sql` and the database can be rebuilt from
it:

```
npx wrangler d1 execute grace-widget-usage --remote --file worker/schema.sql
```

Every statement is `IF NOT EXISTS`, so re-running it against the live database is
a no-op rather than a data-loss event.

`/event` follows the same two rules as the ranking endpoint: **same origin
allowlist** (one list, one function — no Origin header is refused, so a bare
`curl` writes nothing), and **always HTTP 200**. It never reports whether a row
was written; row counts in D1 are how you check. Malformed events are dropped
silently. Nothing beyond the schema is persisted — no IP, no headers, no
identifier of any kind, and `ts`/`day` are generated server-side rather than
trusted from the caller.

**COUNTING IS ON FOR THE DEMO as of 2026-09-16.** Both demo pages carry
`data-events="https://grace-assistant-router.relax-tech.workers.dev/event"`
alongside their existing attributes. **The live site does not** — no embed on
discovergrace.com carries the attribute, so nothing there is counted. The two
switches are independent by design.

**TELLING TEST FROM REAL: use `source`, never the date.**

Every event records which embed sent it — `demo` or `live`, `''` if the sender
declared none, `'invalid'` if it sent something unknown. The demo embed carries
`data-source="demo"`; the live embed will carry `data-source="live"` when it is
switched on. So:

```sql
WHERE source = 'live'     -- real guest behaviour, whenever it happened
```

**The 21 scripted rows are gone** (deleted 2026-09-16) and `EXCLUDED_DAYS` is now
empty. It stays as a mechanism for striking out a whole day — a bad backfill, a
load test — but it is no longer how demo and live are separated.

**Why this changed.** Identifying test data by date failed twice inside 24 hours:
once when scripted walks and real demo clicks landed on the same UTC day, and
once when "today" turned out to *be* the excluded day. A date cannot say which
embed sent a row, so it was only ever a proxy, and a proxy that breaks whenever
two kinds of traffic share a calendar day. That was the stated trigger condition
for making it structural, and it was met.

**The 44 rows that predate the column were backfilled to `demo`** on 2026-09-16.
That is not a guess: `data-events` has only ever existed on the two demo pages.
The cost, recorded honestly — a row that *declared* `demo` and one that was
*assigned* it are now indistinguishable.

**CLOSES ARE NOT VISITS — do not compute a per-visit average from them.**
One pageview can produce several `close` rows. The widget's counters are scoped
to the pageview and deliberately do not reset when the panel is closed and
reopened, because `position` means "the Nth thing tapped in this pageview". A
guest who taps twice, closes the panel, reopens it and closes again produces two
closes, the second repeating the cumulative `depth=2` with no new taps. Seen in
real traffic (2026-09-16, rows 77–78). So `SUM(depth)` over closes double-counts
and `AVG(depth)` is meaningless; `closes` and `outcomes` stay honest as "moments
a guest stopped". There is no identifier linking rows, by design, so this cannot
be corrected after the fact. **The fix, not implemented:** have the widget send
depth *since the last close* rather than cumulative, making closes additive —
a behaviour change to a shipped contract, so it needs its own pass and a way to
tell the two eras apart.

**THE ROUTER IS NOW A FETCH *AND* SCHEDULED WORKER.** As of 2026-09-16 it
carries `[triggers] crons = ["25 3 * * *"]` and a `scheduled()` handler that
rolls the **previous** UTC day's `events` into `daily_stats`. One Worker owns
both deliberately: two Workers would be two deploys, two log surfaces and one
more thing to explain at handoff.

03:25 UTC is after the day being rolled has closed, and clear of the
content-publish cron at :17 past every second hour.

**The rollup is idempotent and safe to re-run** — it DELETEs the day and rebuilds
it inside one atomic `db.batch()`, so a re-run is a no-op and a day whose events
were corrected loses its stale figures. Proven by running one day four times for
an identical fingerprint, and by deleting an event and confirming no stale row
survived.

**Re-running a day by hand.** There is deliberately **no HTTP endpoint** for it:
the rollup is pure SQL, and an endpoint would add public unauthenticated attack
surface to do what `wrangler` already does with the operator's own credentials.
The statements are `rollupStatements(day)` in `worker/src/index.js`. In practice
the job is idempotent and runs nightly, so the usual answer to a failed night is
to wait for the next one.

**Test days are skipped by name.** `EXCLUDED_DAYS` in `worker/src/index.js`
currently holds `2026-09-16`. **Any future RTS test day goes there**, and in the
note above about test rows — the two must stay in step, or the dashboard starts
reporting us. Verified: an excluded day issues zero SQL statements, not merely
zero writes.

**UNPROVEN UNTIL 2026-09-17 03:25 UTC — worth one glance.** The exclusion gate
was proven by calling `rollupDay()` directly with the excluded day, but the cron
rolls *yesterday*, so the scheduled path does not actually meet `2026-09-16`
until its first run on the 17th. Check the Worker's logs after that run and
confirm it logged `status=skipped-test-day` rather than assuming it did:

```
npx wrangler tail grace-assistant-router
```

A line reading `rollup {"day":"2026-09-16","status":"ok",...}` with rows written
would mean the exclusion did not fire, and `daily_stats` would then be holding
RTS clicks. Clear it with `DELETE FROM daily_stats WHERE day = '2026-09-16';`
and find out why before anything reads the table.

**Two records of one fact, kept in step by hand.** `EXCLUDED_DAYS` and the
test-row note above both record which days are ours. Nothing enforces that they
agree. That is tolerable while testing is occasional; **if RTS testing becomes
routine, that is the trigger to add a `source` column to `events`** and stop
identifying test data by date at all. Doing it now would mean a column that
exists only to describe rows we made — doing it then would mean a column that
earns its place. The decision point is frequency, not preference.

**Since 2026-08-27 the visible re-render is disabled** — chips reordering ~2s after
a tap caused misclicks. The POST still happens as telemetry (`console.debug`,
Chrome Verbose only). Re-enabling means designing a render-once flow first.

**Origin allowlist** — one list in `worker/src/index.js` feeds both the CORS
headers (what a browser may *read*) and the budget gate (whether we *spend*):

```
https://discovergrace.com
https://www.discovergrace.com
https://grace-assistant.pages.dev
https://assistant.discovergrace.ai
https://grace-demo.pages.dev
```

An allowed origin gets a real answer in ~0.8–1.1s. A blocked origin, **or a request
with no Origin header at all**, gets `{"ids":[]}` in ~80ms with no API call. The
~10× timing gap is the proof the gate fires before the spend.

Consequence: **a bare `curl` always returns `{"ids":[]}`**. Manual testing needs
`-H "Origin: https://discovergrace.com"`.

### Demo site

`https://grace-demo.pages.dev/plan-your-visit/` and `/giving/`

Near-exact static clones of Grace's real pages with the widget injected, for
showing the work without touching production. Built by `wget` mirror: 748KB CSS
across 27 files, 21 fonts, 62 images. All WordPress scripts stripped (so the FAQ
accordion is inert — accepted), heroes converted from `data-bg-image` to static
CSS, and an injected spam link removed.

Protected by **Cloudflare Access** — Zero Trust app "grace-demo - Cloudflare
Pages" covering `*.grace-demo.pages.dev` and the apex, policy "Grace Demo
Viewers", one-time PIN to two named emails. Also `noindex, nofollow`.

The demo loads the widget from `grace-assistant.pages.dev`, so content publishes
reach it automatically with no demo redeploy. **Teardown candidate after the
pilot decision.**

### Usage dashboard

`https://widget.discovergrace.ai` — Pages project **`grace-widget-dashboard`**,
direct upload from `dashboard/`. Also answers on
`grace-widget-dashboard.pages.dev`.

One file, `dashboard/index.html`, ~217KB. No build step and no dependencies: four
woff2 faces (Quincy CF, Greycliff Regular and DemiBold, Interstate Bold) are
embedded as base64 and Grace's wordmark is inlined SVG, **so the page does not
depend on discovergrace.com for type or logo**. Do not "optimise" either into a
link; the dashboard has to render when the church site does not.

**Three tabs:** the verdict (what to change), every question (per page, per
question), over time (how conversations ended).

**What it reads — two fetches, no others:**

| Source | For |
|---|---|
| `GET /stats` on the router Worker | all the numbers — `daily_stats` only, **never `events`** |
| `answers.json` on `assistant.discovergrace.ai` | the opening list (`starters`) and question wording |

Each page's full question set is a breadth-first walk from its starters along
`followups` — the same rule `publish.py` validates, so the dashboard and the
publisher agree on what "on this page" means. `talk-person` is removed after the
walk and appears only as the "asked for a person" figure, never in a ranking.

**The three actions, and their thresholds.** Set as constants at the top of the
script block in `dashboard/index.html`, and **stated on the page in plain
language** so a reader never has to ask what "few taps" means:

| Constant | Value | Meaning |
|---|---|---|
| `DEMAND_SHARE` | `0.05` | A question is wanted if it draws **one tap in twenty** on its page. A share, not a count, so a busy page and a quiet one are held to the same standard. |
| `VERDICT_MIN_TAPS` | `40` | No page is judged below this. Under 40 a single tap moves a question across the line and the verdict is noise. |
| `CHART_MIN` | `40` | The daily line is not drawn below this many conversations. |

The classification is deliberately asymmetric and this is the part most easily
got wrong: **on the opening list with few taps is a Rewrite** — everyone was
offered it and ignored it. **Off the list with few taps is No verdict yet** — it
was never really offered. The same zero means opposite things.

Swap instructions are **generated**, never hardcoded: the real page name, the
real slugs, and the outgoing candidate chosen as the least-tapped question on the
opening list. A full list (5 of 5) produces a swap naming both questions; a list
with room says the question can be added outright.

**`SOURCE` — one constant, at the top of the script block.** Currently `'demo'`,
sent as `?source=demo`, so the dashboard shows the demo embed's traffic only.
**Change it to `'live'` at go-live**, when the live embed starts sending. It is
the single line that decides whose numbers are on screen; nothing else needs
touching.

**Four states, all real rather than drawn:**

1. **Almost no data** — under `VERDICT_MIN_TAPS` a page gets no verdict and the
   panel says so with the actual figures. Under `CHART_MIN` the daily line is not
   drawn. This is what the page shows today.
2. **A page with no taps** — a dashed resting card. Nothing yet, not failing.
3. **A fault** — driven by the `alarms` block from `/stats` (`invalid_depth`,
   `invalid_outcome`). **If both are zero the panel does not render at all.**
   These are bug reports about the widget, never facts about guests.
4. **`/stats` unreachable** — a banner and an explicit "this is a loading
   failure, not an empty week". It never shows an empty page that could be
   mistaken for a reading of zero.

**The banner reports the span of days that hold data, not the query window.** The
page asks `/stats` for 90 days; only some of those days have rows. Saying "29
conversations from 19 June to 16 September" was true of the query and false about
the assistant — a reader would take it to mean barely used, when all 29 happened
in one day. It now says "29 conversations, all on 16 Sep 2026". **If you add a
range picker, keep that distinction.**

**Access, and the preview-URL hole.** The app protects
`widget.discovergrace.ai` and `grace-widget-dashboard.pages.dev`; both return a
302 to the Cloudflare Access login, which is how you check the protection is on.

**Cloudflare Pages also mints a per-deployment preview URL —
`<8-hex>.grace-widget-dashboard.pages.dev` — and those are NOT covered by an
Access app that lists only the two hostnames.** They return 200 to anyone who
knows the id, and every deploy mints another. Adding
`*.grace-widget-dashboard.pages.dev` as a hostname on the app closes it, which is
how the `grace-demo` app has always been configured. Worth knowing in both
directions: it is also why a preview URL is the only way to verify deployed
*content* by md5, since the front door returns a redirect rather than the page.

**The approved design** is `grace-dashboard-APPROVED.html`, md5
`21cc87ca1377b42689014315e271fdd7`, deliberately **not** in the working tree —
two copies of a design is how they drift. It is in git history:

```
git log --all --diff-filter=A -- dashboard/grace-dashboard-APPROVED.html
git show <that commit>:dashboard/grace-dashboard-APPROVED.html > approved.html
```

`index.html` was verified against it: all four font blobs byte-identical, the
wordmark identical, the approved CSS present verbatim.

### Source of truth — the Sheet

**grace-assistant-corpus-2026-08-27** (that is the file's actual title — searching
Drive for "grace-assistant-corpus" alone will not find it), Drive fileId
`1uxB85U-lRTZo75eGdmB23PAvJ2jdyLvvezaQIzaaekY`

Five tabs: `READ ME`, `ANSWERS`, `PLACEMENT`, `FLAGS`, `CHANGE LOG`.

**ANSWERS** — headers on **row 4**, data from **row 5**. Twelve columns:
`A ID` · `B Slug` · `C Page` · `D Tap Question (guest sees)` ·
`E Answer Text (pre-approved)` · `F Primary Action → Destination` (arrow is U+2192,
plain `->` also accepted) · `G Topic Tags` · `H Status` · `I Source / Notes` ·
`J Follow-up IDs (slugs)` · `K Also on` · `L Also on 2`

**`Also on` / `Also on 2` (added 2026-09-13) put one question on more than one
page.** A question ships to its `Page` plus whatever those two name. **Blank means
"appears only on its Page"** — which is what every row said before the columns
existed, and is why adding them changed nothing. Both are strict dropdowns
carrying the same 18 page names, deliberately *without* `(any page)`: that value
is the talk-person marker, not a page.

**PLACEMENT** — headers row 4: `Page` · `URL path` · `Show / Hide` ·
`Starter question IDs (3–5)` · `Why` · `Panel title` · `Launcher label` ·
`Intro` · `End of questions`

**The last four (added 2026-09-13) are the route-meta columns**, and they are why
per-page wording no longer lives in code. **A blank cell falls back to the
hardcoded value in `publish.py`**, so the site is byte-identical until someone
types something. `Panel title` / `Launcher label` / `Intro` fall back to
`ROUTE_META_FALLBACK`; `End of questions` falls back to
`END_OF_QUESTIONS_FALLBACK`, which must stay byte-identical to `EXHAUSTION_NOTE`
in the widget. The names are not free choices — `read_placement` matches them
lowercased, so a different spelling leaves the column silently unread.

Data-validation dropdowns are in place: `Status` = `HOLD|DRAFT|APPROVED`,
`Page` = the 19 live page names, `Show / Hide` = `SHOW|HIDE`, `URL path` = the
live path list. All strict — a typo is rejected at entry. The `Slug` column
carries a **warning-only** protection ("Slugs are permanent identifiers"), which
warns without blocking.

**A new page path must be added to the URL-path dropdown before the row can be
typed.** That is deliberate, and it also means the list needs extending whenever
a page is added.

### The publish pipeline

```
T edits the Sheet
   ↓
Cloudflare cron (worker-clock) every 2h at :17 UTC
   ↓  POST workflow_dispatch
GitHub Actions auto-publish.yml
   ↓  publish.py --deploy --min-quiet-minutes 30 --quiet
validate → build/answers.json → public/answers.json → Cloudflare Pages
   ↓
commit "auto-publish: <UTC>" back to main   (git history = the audit trail)
   ↓
ntfy push
```

- **`publish.py`** (repo root) reads the Sheet, validates, deploys, verifies live.
- **`.github/workflows/auto-publish.yml`** runs it.
- **`worker-clock/`** → Worker `grace-publish-clock`, cron `17 */2 * * *`. **This is
  the clock.** It POSTs a `workflow_dispatch` and alerts if it cannot.
- **GitHub's own `schedule:` block is a redundant backup and is NOT reliable** —
  see INCIDENT LOG. Do not depend on it.

### Notifications (ntfy.sh)

| Tier | Fires when | Priority |
|---|---|---|
| **Grace publish FAILED** | any workflow step fails | high |
| **Grace published** | a run reports `RESULT status=deployed` | default |
| **Grace clock: dispatch FAILED** | the Worker cannot reach GitHub | high |

Deliberately **not** alerted: `status=nochange` and `status=debounced`. Both are
healthy, and alerting on them trains you to ignore the channel.

**Known gap, narrowed 2026-08-30.** A clock that never fires produces no failed
run and therefore no alert. The Worker closes that hole for GitHub's scheduler,
and a **daily heartbeat** now covers the Worker itself: on the primary dispatch at
hour 12 UTC the workflow sends the `RESULT` line to ntfy at `Priority: min`, which
lists silently and never buzzes. It is not a message to read — it is one whose
*absence* is the signal.

What it covers: the whole chain being dead for a day. If the Worker stops
dispatching, the workflow stops running, or the ntfy topic breaks, the daily line
stops appearing.

What it does **not** cover, and why the gap is narrowed rather than closed:

- **Latency.** Detection takes up to 24 hours. A clock that dies at 13:00 UTC goes
  unnoticed until the following midday.
- **It is a pull, not a push.** Nothing alerts on the absence; a person has to
  notice a quiet line missing from a quiet channel. That is a weak signal by
  design, but it is a weak signal.
- **Partial failure.** It fires on a successful run of any kind, so a pipeline
  that runs and reports `nochange` every time because the Sheet read silently
  returns nothing would still heartbeat happily.

A genuine "no successful publish in N hours" watchdog — something that alerts on
the absence rather than reporting on the presence — is still the missing piece.

---

## 2. CREDENTIAL LEDGER

**Names and locations only. No values appear in this repo or this document.**

| # | Credential | Lives in | Grants | Rotate at handoff |
|---|---|---|---|---|
| 1 | Anthropic API key | Cloudflare Worker secret `ANTHROPIC_API_KEY` on `grace-assistant-router` | Calls to the Claude API, billed to the key's owner | **YES — priority.** Currently Chris's personal key. Was also briefly exposed to a terminal scrollback and a Vim swap file during debugging |
| 2 | `CLOUDFLARE_API_TOKEN` | GitHub repo secret | Cloudflare **Pages: Edit** on this account only — not a global key | YES |
| 3 | `GCP_SA_KEY` | GitHub repo secret | Full JSON of the publisher service account | YES |
| 4 | Service-account key file | `secrets/grace-publisher.json`, mode 600, gitignored | Same as #3, for local runs | YES |
| 5 | `GH_DISPATCH_TOKEN` | `worker-clock` Worker secret | GitHub Actions read+write on this repo, to fire `workflow_dispatch` | YES |
| 6 | `NTFY_TOPIC` | GitHub repo secret **and** `worker-clock` Worker secret | The ntfy topic string. Anyone holding it can read and post notifications | YES — treat as a secret, not an identifier |

**Service account:** `grace-publisher@flowing-sign-487115-t3.iam.gserviceaccount.com`
GCP project `flowing-sign-487115-t3` (number `450055151257`), with the Sheets API
and Drive API enabled. Scopes requested: `spreadsheets.readonly` +
`drive.metadata.readonly`.

**Its standing access is Viewer on the one Sheet, and nothing else.** Write access
is granted temporarily and revoked immediately — see the Editor-window runbook.

**Cloudflare Access policy** — "Grace Demo Viewers" on the `grace-demo` app allows
two named email addresses via one-time PIN. Those addresses are in the Zero Trust
dashboard, not here. Update them there when people change.

**Cloudflare account:** `542c6caf232f86b4a1e6e69cb49e5326`, currently under
chris@relax-tech.com.

**Figma reference file:** *Grace · Guest Assistant — Production Reference 2026-08-28*,
file key `KlNVjhoZAQkpJIBZv2jJh0` —
`https://www.figma.com/design/KlNVjhoZAQkpJIBZv2jJh0/Grace-·-Guest-Assistant-—-Production-Reference-2026-08-28`
16 production-state frames plus a design-token card. This is T's markup surface;
the widget CSS remains production truth. **Confirm sharing settings and transfer
ownership at handoff.**

---

## 3. RUNBOOKS

### Routine publish

1. T edits the Sheet. Status column is the approval gate: `HOLD` never ships.
2. Within two hours the Cloudflare cron dispatches a run.
3. If the Sheet was edited in the last 30 minutes the run **debounces** and exits
   cleanly — a half-typed answer cannot go live mid-edit. The next tick picks it up.
4. A `status=deployed` run sends a quiet push and commits the regenerated
   `answers.json` to `main`.

Nothing else is required. No one runs a command.

### Manual publish

**Actions → auto-publish → Run workflow.** Two inputs:

| Input | Effect |
|---|---|
| `force_publish` | Skips the 30-minute debounce. **Dispatch-only by construction** — `inputs` is empty on a schedule event, so the clock can never skip it |
| `simulate` | `none` / `failure` / `deploy_ping`. Exercises the notification paths without reading the Sheet or deploying |

Or poke the clock directly:
`curl https://grace-publish-clock.relax-tech.workers.dev` → `{"ok":true,"status":204}`
and a run appears within seconds.

### Failure response

1. High-priority push arrives.
2. Open the run: **Actions → auto-publish → the red run**.
3. **Read the `RESULT status=` line, not the badge.** A green tick can mean
   `debounced`, which is a healthy no-op. Rough tell: ~20s runs declined,
   ~40–50s deployed.
4. Exit codes: **2** = validation refused, nothing written, nothing deployed.
   **3** = quiescence check failed (Drive API or scope problem), nothing published.
5. Fix the Sheet cell the message names, then wait for the next tick or dispatch.

### The Editor window (any bulk Sheet write)

The service account is Viewer by default and must be returned to Viewer.

1. Sheet → **Share** → the service account → **Viewer → Editor**.
2. Run the tool from `tools/`. Every one defaults to a dry run; read the planned
   table before passing `--apply`.
3. Verify the writes by re-reading the Sheet.
4. Sheet → **Share** → **Editor → Viewer**.
5. **Prove it.** Attempt a no-op write through the service account and confirm it
   fails:
   ```
   APIError: [403]: The caller does not have permission
   ```
   A silent success means the window is still open.

**The Sheets API allows 60 write requests per minute per user.** A cell-at-a-time
loop hits that at exactly 60 cells — batch writes per worksheet instead.

### Pilot exit — MANDATORY, one event

`SHIP_STATUSES` in `publish.py` currently allows `{'DRAFT', 'APPROVED'}`, and every
shipped row is `DRAFT`. **With publishing automated, that constant is the only thing
between a new DRAFT row and the live site.**

Do these together, in this order:

1. T's approval pass sets rows to `APPROVED` in the Sheet.
2. **Then** flip `SHIP_STATUSES` to `{'APPROVED'}`.
3. Publish.

Flipping first ships zero questions: the routes have no starters, validation fails
loudly, nothing is written. Correct behaviour, alarming if unexpected.

### Adding a page

1. Extend the `URL path` validation list on PLACEMENT (strict dropdown will
   otherwise reject the new path).
2. **Add the page name to the dropdown in all THREE columns** — `ANSWERS!C Page`,
   `ANSWERS!K Also on`, and `ANSWERS!L Also on 2`. They are three separate
   `ONE_OF_LIST` rules holding literal values, not one list three cells point at,
   so a name added to one and not the others is typeable in one column and
   rejected in the next. (`Page` also carries `(any page)`; the other two must
   not.) PLACEMENT's own `Page` column is free text and is *not* one of the three.
3. Add the PLACEMENT row: page name, URL path, `SHOW`, 3–5 starter IDs, why.
4. Add that page's rows to ANSWERS.
5. Add the path to `PILOT_ROUTES` in `publish.py`.
6. Add a `ROUTE_META_FALLBACK` entry for the path (`title`, `launcherLabel`,
   `intro`) — without one those render `null` and the panel falls back to generic
   strings. Or fill the PLACEMENT route-meta columns instead, which is the point
   of them existing.
7. Publish.

**No WordPress change and no widget change.** The site-wide snippet reads
`window.location.pathname` and finds the route itself.

---

## 4. GO-LIVE

Paste this into **WPCode → HTML snippet → Site Wide Footer**:

```html
<script src="https://assistant.discovergrace.ai/grace-assistant.js"
  data-answers="https://assistant.discovergrace.ai/answers.json"
  data-router="https://grace-assistant-router.relax-tech.workers.dev" defer></script>
```

**Before pasting**, confirm the hostname WordPress actually serves from is in the
Worker's origin allowlist. If the site answers on a hostname not in that list, the
widget still works — chips just stay in their static order, silently.

**After pasting, verify:**

1. Visit `/plan-your-visit/` — the launcher appears bottom-right (white pill +
   orange bug).
2. Visit a page that is *not* in `answers.json` — **nothing should render at all**.
   That is the default-hide contract working.
3. Open the panel, tap a question — the answer appears instantly, with no wait.
4. Check on a phone. The phone is the final verdict on any visual change; desktop
   parity means nothing until the device agrees.
5. In devtools Network, confirm a POST to the Worker returns 200 with ranked ids.
   If it returns `{"ids":[]}` fast, the hostname is not allowlisted.

---

## 5. HANDOFF / TEARDOWN CHECKLIST

- [ ] **Rotate all six credentials** under Grace's ownership (ledger §2). The
      Anthropic key first — it is currently a personal key and was briefly exposed
      during debugging.
- [ ] **Remove `test.html`** from the production origin (`public/test.html`). It is
      a mock harness with a visible TEST PAGE banner.
- [ ] **Demo site:** tear down the `grace-demo` Pages project and its Access app,
      or agree who keeps paying attention to it.
- [ ] **Figma:** transfer ownership of `KlNVjhoZAQkpJIBZv2jJh0` and review sharing.
- [ ] **Repo:** decide transfer to a Grace-owned GitHub account, or fork. It is
      **public** today — check that is still intended. Note the repo contains no
      secrets, only names.
- [ ] **Cloudflare:** the account is currently Chris's. Decide whether the Pages
      projects, Workers, and the `discovergrace.ai` zone move.
- [ ] Confirm the ntfy topic is subscribed on whichever phone should receive alerts
      after handoff.
- [ ] Consider a "no successful publish in N hours" watchdog (see §1 known gap).

---

## 6. INCIDENT LOG

**The scheduler that never fired (2026-08-27 → 28).** The auto-publish workflow was
pushed with a `schedule: '17 */2 * * *'` trigger. Over the following 16 hours it
fired **zero** times — **seven** consecutive missed ticks. (This document said
"nine" until 2026-09-08. At a two-hour cadence sixteen hours cannot contain nine
ticks; seven is the figure in PUBLISHING.md and in the workflow's own header
comment, and it is the correct one.) Every possible
misconfiguration was checked and ruled out from the machine: workflow `state=active`,
file present on the default branch, Actions enabled with `allowed_actions: all`,
public non-fork repo, valid cron. Nothing was wrong; GitHub's hosted scheduler is
best-effort and had simply dropped every tick. The fix was to stop depending on it:
a Cloudflare Worker (`worker-clock`) now owns the cadence and POSTs a
`workflow_dispatch` on its own cron, with a high-priority alert if it cannot reach
GitHub. GitHub's schedule block stays as redundant backup. **Lesson: a scheduler
you do not operate is not a guarantee, and a clock that never fires raises no
alarm — silence is not success.**

**The push race (run #2, 2026-08-28 01:22Z).** A run deployed successfully, made its
`auto-publish` commit, and then failed to push: `! [rejected] main -> main (fetch
first)`. Cause was a human push landing mid-run. The run showed red although the
deploy had already succeeded and the content was live — severity far lower than the
badge implied. Fixed by adding `git pull --rebase` and one retry to the commit step.
**Lesson: a failed run is not necessarily a failed publish. Read which step failed.**

**The swap-file near-miss.** A pre-commit dry run caught `worker/.dev.vars.swp` about
to be staged — a Vim swap file of the file holding the Anthropic API key, headed for
a public repo. `.gitignore` had `.dev.vars` (exact match), which does not cover
`.dev.vars.swp`. Patterns were widened to `.dev.vars*`, `*.swp`, `*.swo`, `*~`,
`.wrangler/`. The practice that caught it: **canary-test the ignore rule before the
real secret exists near the repo** — `touch secrets/canary.json`,
`git check-ignore -v`, confirm, delete. Every commit since has run a credential
pattern sweep over the staged diff before committing.

**Green check ≠ deployed.** `RESULT status=debounced` exits 0 and shows a green tick,
because declining to publish a half-finished edit is a success. Early in the session
this was misread as "it published" more than once. Every run now prints a single
machine-readable `RESULT status=…` line, and the runbooks say to read it rather than
the badge. The same discipline applies to Cloudflare's edge, which served stale
content three times and twice produced a false "deploy failed" reading — **verify
deploys twice, cache-busted.**
