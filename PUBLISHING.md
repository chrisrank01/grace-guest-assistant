# Publishing the Grace Guest Assistant

The widget's entire content — every question a guest can tap and every answer
they see — comes from one Google Sheet. `publish.py` is the only thing that
writes `public/answers.json`. Do not hand-edit that file; edit the Sheet and
republish.

## How content flows

Publishing is **automated**. Nobody runs a command to ship.

1. **T edits the Sheet.**
   - `ANSWERS` tab: question text, answer text, status, links, follow-up slugs.
   - `PLACEMENT` tab: which pages show the assistant, and which questions start
     the panel on each one.
2. **A Cloudflare cron we operate dispatches publishes every two hours**
   (`worker-clock/`, Worker `grace-publish-clock`, cron `17 */2 * * *`). It POSTs
   a `workflow_dispatch` to `.github/workflows/auto-publish.yml`. Each run reads
   the Sheet, validates, and deploys only if something actually changed.
   **GitHub's own `schedule:` block is kept as a redundant backup, not the primary
   clock** — it missed 7 consecutive ticks over 16 hours on 2026-08-28 with a
   valid cron, an active workflow, and the file on the default branch. Treat
   GitHub's scheduler as best-effort; the Cloudflare cron is the reliable one.
   If both fire, the workflow's `concurrency: auto-publish` group queues them.
3. **The regenerated `public/answers.json` is committed back** to `main` by the
   workflow, so the repo always matches what is live.

There is no approval step and no human gate. **The gates are mechanical:**

| Gate | What it stops |
|---|---|
| `Status` column | `HOLD` rows never ship. This is the approval mechanism. |
| Validator | Broken references, orphans, bad links → exit 2, nothing written, run fails |
| Quiescence debounce | A Sheet edited in the last 30 minutes is skipped entirely |

### The debounce

`publish.py --min-quiet-minutes 30` reads the Sheet's Drive `modifiedTime`. If it
was touched inside that window the run prints `RESULT status=debounced` and exits
0 without publishing — so a half-typed answer cannot go live mid-edit. The next
scheduled run picks it up.

If the debounce check itself fails (Drive API disabled, scope revoked), the run
**fails loudly** with `RESULT status=quiescence_check_failed` and exit 3 rather
than guessing. It never publishes on an unverified quiet period.

Requires two things beyond the Sheets setup: the **Drive API enabled** on the GCP
project, and the `drive.metadata.readonly` scope in `publish.py`'s `SCOPES`.

### Running it by hand

GitHub → **Actions** → **auto-publish** → **Run workflow**. Two inputs:

| Input | Effect |
|---|---|
| `force_publish` | Skips the 30-minute debounce (`--min-quiet-minutes 0`). **Dispatch only** — `inputs` is empty on a schedule event, so the clock can never skip the debounce. |
| `simulate` | `none` (default), `failure`, or `deploy_ping`. Exercises the notification paths without reading the Sheet or deploying. |

Without `force_publish`, the debounce still applies — a manual run right after an
edit will correctly skip.

You can also poke the clock Worker directly:
`curl https://grace-publish-clock.relax-tech.workers.dev` dispatches a run
immediately and returns `{"ok":true,"status":204}`.

### Notifications

Push alerts go to an [ntfy.sh](https://ntfy.sh) topic held in the `NTFY_TOPIC`
secret (GitHub repo secret, and a Worker secret on the clock).

| Tier | Fires when | Priority |
|---|---|---|
| **Publish FAILED** | any workflow step fails — validator exit 2, deploy error, push failure | high |
| **Published** | a run reports `RESULT status=deployed` | default |
| **Clock dispatch FAILED** | the Cloudflare Worker cannot reach GitHub (non-2xx or fetch throw) | high |

Bodies carry a status code and timestamp only — never a token, never a response
body, because those can echo request context into a log.

**What is deliberately NOT alerted:** `status=nochange` and `status=debounced`.
Both are healthy outcomes and would train you to ignore the channel.

**The gap worth knowing:** a clock that never fires produces no failed run and so
no alert. That is exactly the 2026-08-28 failure mode. The clock Worker closes it
for GitHub's scheduler, but nothing yet watches the Worker itself — a
"no successful publish in N hours" check is the missing piece.

### When something breaks

A failed run emails whoever owns the repo, per GitHub's notification settings.
Failures are loud by design: validation failure, quiescence-check failure, and
deploy failure all exit non-zero. A run that finds nothing to do exits 0 quietly
with `RESULT status=nochange`.

### Running it locally

Still possible and still useful for reviewing a diff before the scheduler gets
there:

```
.venv/bin/python publish.py             # dry run, full diff, nothing shipped
.venv/bin/python publish.py --deploy    # ship it now
```

Add `--quiet` for machine-readable output (a single `RESULT ...` line plus
warnings), which is what the workflow uses.

### REQUIRED before ANY hand deploy

Run this first, every time, whether you are shipping content or a widget change:

```
git fetch origin && git diff --quiet origin/main -- public/answers.json \
  && echo "GUARD PASS" || echo "GUARD FAIL - do not deploy"
```

**Why.** `wrangler pages deploy public` uploads the *whole directory*, not a diff.
Anything stale sitting in `public/` rides along and overwrites what is live, even
if you never touched it.

This is not hypothetical. On **2026-09-08** a hand deploy of a widget change also
shipped a week-old `public/answers.json`, silently reverting two of T's published
copy edits — "make arrival simple" back to "make arrival easy", and "GraceKids!"
back to "GraceKids". They were live for roughly twenty minutes. Nothing detected
it: the deploy verified its own md5 and passed, because the file it shipped was
exactly the file it meant to ship. It surfaced only because the follow-up
`git push` was rejected as non-fast-forward.

The same hazard runs the other way. While a hand-authored widget change sits
uncommitted, the next content publish checks out `main` and deploys *its* copy of
`public/`, silently reverting the widget. `publish.py` only deploys when
`answers.json` actually changed, so the revert waits for the next Sheet edit
rather than the next tick — which makes it less likely to be noticed, not more.
**Commit and push a hand deploy in the same session that made it.**

## What the validator refuses

Any of these fails the run with **exit 2 and nothing written** — the deploy does
not happen:

- **Broken references** — a starter or follow-up slug that is not a shipped question.
- **Self-reference** — a question listing itself as its own follow-up.
- **Orphaned questions** — BFS from each page's starters must reach exactly the
  set of questions the `Page` columns assign to that page. Checked in both
  directions: a question no starter can reach fails, and so does a follow-up
  that leaks into another page's question. Since 2026-09-13 "the `Page` columns"
  means `Page` plus `Also on` / `Also on 2`, and the BFS walks the per-page
  follow-up lists — so it judges the graph that actually ships. The rule is
  unchanged; the sets simply overlap now.
- **Malformed links** — an `href` outside the whitelist (`/path`, `http(s)://`,
  `tel:`).
- **`watch-online` as a follow-up** — it is starter-only by policy.
- **Empty answers** — a shipped row with no answer text.
- **Duplicate slugs**, and **duplicate IDs**.
- **A shippable row with an empty Slug** — cleared to ship but unaddressable by
  any starter or follow-up.
- **A destination cell that yields zero usable links** — someone wrote a
  destination and it produced nothing. Previously a warning, which let a button
  vanish silently from a shipped answer.
- **An `Also on` value naming a page PLACEMENT does not define** — see below.

Input is normalised before any of it is judged: `Status`, `Page` and `Slug` are
trimmed and compared case-insensitively, and a plain ASCII `->` is accepted
anywhere the Sheet's `→` is expected.

## Putting one question on several pages

`Also on` and `Also on 2` on the ANSWERS tab ship a question to more than one
page. A question appears on its `Page` plus whatever those name. **Blank means it
appears only on its `Page`.**

### RULE: `Also on` alone is half an edit

Naming a second page makes a question **expected** on that page. It does not make
it **reachable** there — and a question nobody can navigate to is an orphan, which
has always stopped the publish. You will get:

```
VALIDATION FAILED - nothing written

  - /giving/: questions on this page unreachable from its starters: ['what-to-wear']
```

**The complete edit is two things:**

1. Name the page in `Also on` (or `Also on 2`), **and**
2. Make the question reachable on that page — either add it to that page's
   `Starter question IDs` on PLACEMENT, or add its slug to the `Follow-up IDs` of
   a question already on that page.

Do one without the other and the publish stops. That is not a new rule; it is the
existing orphan check meeting the new column. Nothing is written and nothing is
deployed, so the fix is to finish the edit and wait for the next tick.

### A shared question can show a SHORTER follow-up list on one page

This is correct, and it surprises people.

A question on two pages may list follow-ups that only exist on one of them.
Follow-ups resolve **per page**: `publish.py` filters each question's follow-up
list to the questions that belong to the page being rendered, and emits the
shortened list under that route. A follow-up belonging to the other page is
dropped rather than shipped to a page where tapping it would go nowhere.

So `what-to-wear` on `/plan-your-visit/` can offer three follow-up chips, and the
same `what-to-wear` on `/giving/` offer none. Same question, same answer, fewer
chips. **That is the feature working.** If the shorter page should offer more, give
those follow-ups an `Also on` for that page too — remembering the rule above.

The BFS reachability check walks these same per-page lists, so the validator
judges the graph that actually ships rather than an unfiltered one.

### What stops the publish, and what only warns

| `Also on` names… | Result |
|---|---|
| a page with a PLACEMENT row carrying one concrete URL path | ships |
| a page with **no** PLACEMENT row | **exit 2, nothing written** |
| a PLACEMENT row whose path is a pattern (`*`, `/watch/*`, `/a/, /b/*`) or the `——— HIDE below ———` separator | **exit 2** — those rows name rules, not pages |
| a page whose PLACEMENT row is `HIDE` | **warns and ships** — pre-staging for a page that is not live yet is legitimate |

The fatal message names the offending row and the bad value:

```
FATAL PYV-01 (what-to-wear): Also on is 'Sermons', which has no PLACEMENT row
      naming one concrete page. Add the PLACEMENT row, or clear the cell.
```

The dropdown protects the editor at typing time. This check is the backstop for
what a dropdown cannot catch: **a PLACEMENT row deleted afterwards, or cells
pasted in** — paste bypasses Sheets validation entirely.

## Per-page wording, from the Sheet

PLACEMENT's `Panel title`, `Launcher label`, `Intro` and `End of questions`
columns drive the per-page strings that used to live only in code.

**A blank cell falls back to the hardcoded value**, so the site is byte-identical
until someone types something. `Panel title` / `Launcher label` / `Intro` fall
back to `ROUTE_META_FALLBACK` in `publish.py`; `End of questions` — the line a
guest sees once they have tapped everything on a page — falls back to
`END_OF_QUESTIONS_FALLBACK`, which is byte-identical to `EXHAUSTION_NOTE` in the
widget.

`End of questions` is written into `answers.json` **only when the cell says
something different from that default.** Retyping the default by hand is treated
as blank. That is deliberate: emitting the fallback would rewrite every route for
no change a guest could see.

The column names are matched lowercased and are not free choices — spell one
differently and it is silently never read.

## Known behaviors, not bugs

- **Prose destinations drop the link, with a warning.** A `Primary Action →
  Destination` cell that names a place in words ("Open the app", "Church Center
  giving") rather than a URL ships *no* link rather than a broken one. Put a real
  URL in the cell and the link appears on the next publish, no code change.
- **`_editorNote` regenerates every run** and carries the date, but it is
  **excluded from the changed-vs-unchanged comparison on both sides**, so a date
  rollover alone can never produce `deployed` or `would_change`. It is still
  written to the artifact, so a real deploy always ships a fresh one. This is
  because of the 2026-08-29 00:18 UTC incident: the first tick after UTC midnight
  deployed with `_editorNote` as its entire content diff, producing a no-op
  deploy, a junk auto-publish commit, and a "Grace published" push every night.
- **Live verification runs twice, cache-busted.** Cloudflare's edge can serve a
  stale copy for a beat after a deploy, and a single probe has returned a false
  negative more than once. Two checks is the rule, by hand as well as in the script.
- **DRAFT rows ship during the pilot.** `SHIP_STATUSES` allows `DRAFT` and
  `APPROVED`; `HOLD` is never shipped. Every run warns with the DRAFT count.

## Pilot exit procedure — now MANDATORY

With publishing automated, `SHIP_STATUSES` is the only thing standing between a
DRAFT row and the live site. Every pilot row is currently DRAFT, so **the flip to
`{'APPROVED'}` is required at pilot exit, not optional** — until it happens, any
new DRAFT row T adds ships automatically within two hours.

Do these together, as one event, in this order:

1. T's approval pass sets the pilot rows to `APPROVED` in the Sheet.
2. Only then, flip `SHIP_STATUSES` in `publish.py` to `{'APPROVED'}`.
3. Publish.

Flipping the constant first ships **zero** questions: with no APPROVED rows the
routes have no starters, validation fails, and nothing is written. That is the
correct, safe behavior — but it is alarming if you were not expecting it.

## Credentials

- Key: `secrets/grace-publisher.json`, mode `600`, gitignored, **never committed**.
  Override the path with the `GRACE_PUBLISHER_KEY` environment variable.
- Service account: `grace-publisher@flowing-sign-487115-t3.iam.gserviceaccount.com`,
  granted **Viewer on this one Sheet** and nothing else. `publish.py` requests a
  read-only scope and never writes to the Sheet.
- `SHEET_KEY` in `publish.py` is the spreadsheet id, not a credential. Access is
  allowlisted to the service account, so the id alone grants nobody anything.

### Credentials in CI

The workflow uses two repository secrets (Settings → Secrets and variables →
Actions):

| Secret | What it is |
|---|---|
| `GCP_SA_KEY` | Full JSON of the service-account key. Written to `$RUNNER_TEMP` at mode 600, exported as `GRACE_PUBLISHER_KEY`, deleted in an `always()` step. Never echoed. |
| `CLOUDFLARE_API_TOKEN` | Scoped to **Cloudflare Pages: Edit** on this account only — not a global key. |

Neither is ever printed. `publish.py` logs the key *path*, never its contents,
and the debounce error handler reports only an exception type name so Google's
error payloads cannot echo request context into a public log.

Corpus content **does** appear in logs (warnings name slugs and link labels).
That is fine: the same text ships to a public website minutes later.

## The one-off Sheet-writing tools

`tools/` holds the scripts used to write into the Sheet during the 2026-08-28
content session. They are **not** part of the publish path and are kept for
reference and reuse.

Every one of them needs the service account temporarily promoted to **Editor** on
the Sheet, and reverted to **Viewer** afterwards. `publish.py` only ever needs
read. Each script defaults to a dry run and requires `--apply` to write.

## Adding a page later

1. Add a `PLACEMENT` row: the page name, its URL path, `SHOW`, and 3–5 starter
   question IDs.
2. **Add the page name to the dropdown in all THREE columns** — `ANSWERS!C Page`,
   `ANSWERS!K Also on`, `ANSWERS!L Also on 2`. They are three independent
   `ONE_OF_LIST` rules holding literal values, not one shared list, so a name
   added to one and not the others is typeable in one column and rejected in the
   next. `Page` also carries `(any page)`; the other two must not.
3. Add that page's rows to `ANSWERS` (slug, question, answer, status, follow-ups).
4. Add the URL path to `PILOT_ROUTES` in `publish.py`.
5. Add a `ROUTE_META_FALLBACK` entry for that path (`title`, `launcherLabel`,
   `intro`), or fill the PLACEMENT route-meta columns instead. (Those PLACEMENT
   columns exist as of 2026-09-13 and `publish.py` reads them; a value there wins
   over this fallback.) Without either, those three fields come out `null` and
   the page loses its page-specific voice — the panel still works, but:

   | field | with `null` |
   |---|---|
   | `title` | **no heading at all** in the panel body — `seed()` renders `.route-heading` only `if (route.title)` |
   | `intro` | **no opening message** — `meta` carries no `intro`, so nothing renders |
   | `launcherLabel` | the pill says **"Ask Grace"**, the `GLOBAL_META` default, instead of something like "Planning a visit? Tap here" |

   The panel header is unaffected either way: it is a fixed brand lockup reading
   **"Grace" / "Guest Assistant"** from `GLOBAL_META`, never the route.
6. Publish.

No widget change and no WordPress change. The site-wide snippet reads
`window.location.pathname` and finds the route itself; pages not listed in
`answers.json` render nothing at all.
