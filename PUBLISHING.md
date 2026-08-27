# Publishing the Grace Guest Assistant

The widget's entire content — every question a guest can tap and every answer
they see — comes from one Google Sheet. `publish.py` is the only thing that
writes `public/answers.json`. Do not hand-edit that file; edit the Sheet and
republish.

## How content flows

1. **T edits the Sheet.**
   - `ANSWERS` tab: question text, answer text, status, links, follow-up slugs.
   - `PLACEMENT` tab: which pages show the assistant, and which questions start
     the panel on each one.
2. **RTS runs the dry run.**
   ```
   .venv/bin/python publish.py
   ```
   Writes `build/answers.json` and prints two diffs against what is live — a
   unified text diff and a field-level semantic diff (per question: label,
   answer, links, followups). `public/` is not touched.
3. **RTS reviews the diff, then ships.**
   ```
   .venv/bin/python publish.py --deploy
   ```
   Validates, copies to `public/answers.json`, deploys to Cloudflare Pages, then
   verifies the live file twice.

Nothing reaches a guest without step 3. A Sheet edit on its own changes nothing.

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

## Pilot exit procedure

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
