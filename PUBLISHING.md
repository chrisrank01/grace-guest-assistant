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
2. **A GitHub Action publishes on a schedule** — every two hours at :17 UTC
   (`.github/workflows/auto-publish.yml`). Each run reads the Sheet, validates,
   and deploys only if something actually changed.
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

GitHub → **Actions** → **auto-publish** → **Run workflow**. Same gates apply,
including the debounce — a manual run right after an edit will still skip.

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

## What the validator refuses

Any of these fails the run with **exit 2 and nothing written** — the deploy does
not happen:

- **Broken references** — a starter or follow-up slug that is not a shipped question.
- **Self-reference** — a question listing itself as its own follow-up.
- **Orphaned questions** — BFS from each page's starters must reach exactly the
  set of questions the `Page` column assigns to that page. Checked in both
  directions: a question no starter can reach fails, and so does a follow-up
  that leaks into another page's question.
- **Malformed links** — an `href` outside the whitelist (`/path`, `http(s)://`,
  `tel:`).
- **`watch-online` as a follow-up** — it is starter-only by policy.
- **Empty answers** — a shipped row with no answer text.
- **Duplicate slugs.**

## Known behaviors, not bugs

- **Prose destinations drop the link, with a warning.** A `Primary Action →
  Destination` cell that names a place in words ("Open the app", "Church Center
  giving") rather than a URL ships *no* link rather than a broken one. Put a real
  URL in the cell and the link appears on the next publish, no code change.
- **`_editorNote` regenerates every run** and carries the date, so it shows in
  the diff whenever the date has changed since the last publish.
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

## Adding a page later

1. Add a `PLACEMENT` row: the page name, its URL path, `SHOW`, and 3–5 starter
   question IDs.
2. Add that page's rows to `ANSWERS` (slug, question, answer, status, follow-ups).
3. Add the URL path to `PILOT_ROUTES` in `publish.py`.
4. Add a `ROUTE_META_FALLBACK` entry for that path (`title`, `launcherLabel`,
   `intro`). Without one those three fields come out `null` and the widget falls
   back to its built-in strings — the panel still works, but it will say
   "GraceGuide" rather than anything page-specific. (If the `PLACEMENT` tab ever
   grows `Panel title` / `Launcher label` / `Intro` columns, `publish.py` picks
   them up automatically and they win over this fallback.)
5. Publish.

No widget change and no WordPress change. The site-wide snippet reads
`window.location.pathname` and finds the route itself; pages not listed in
`answers.json` render nothing at all.
