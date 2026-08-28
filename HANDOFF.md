# Grace Guest Assistant — Handoff

**Built by:** RTS (Relax Technical Services) — Chris Rank, chris@relax-tech.com
**For:** Grace Church Orlando — discovergrace.com
**Status at handoff:** built, deployed, publishing automated. Not yet embedded on
the live WordPress site — see **GO-LIVE**.
**Last updated:** 2026-08-28

This document contains **no secret values**. It names credentials and says where
they live; it never reproduces one.

---

## 1. SYSTEM MAP

### Widget assets (what a guest's browser loads)

| Surface | URL | Purpose |
|---|---|---|
| Branded host | `https://assistant.discovergrace.ai` | Primary. CNAME `assistant` → `grace-assistant.pages.dev`, proxied, in the `discovergrace.ai` zone |
| Pages project | `https://grace-assistant.pages.dev` | Same files, byte-identical. Cloudflare Pages project `grace-assistant` |

Serves three files plus `_headers`:

- `grace-assistant.js` — the whole widget. Vanilla JS, no dependencies, no build
  step. Renders inside a shadow root with `:host { all: initial }`, so the host
  page's CSS cannot reach in and the widget cannot leak out.
- `answers.json` — all guest-visible content. **Generated. Never hand-edit.**
- `test.html` — a local mock harness. **Remove from the production origin at
  handoff** (see checklist).
- `_headers` — `X-Robots-Tag: noindex` on everything.

**Default-hide contract:** `answers.json` has no `default` route key, so the
widget renders *nothing at all* on any page not explicitly listed. Adding a page
is a content change, not a code change.

### Ranking Worker

`https://grace-assistant-router.relax-tech.workers.dev` (source: `worker/`)

Takes `POST {page, tappedId, history, candidateIds}` and returns `{"ids":[…]}` —
at most 3, always HTTP 200. Model `claude-haiku-4-5-20251001`, ~$0.0003/call.

**It is an enhancement, never a dependency.** If it is slow, broken, or deleted,
the widget shows its static follow-up chips and the guest notices nothing. This is
proven live, and is the single most important property of the design.

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

### Source of truth — the Sheet

**grace-assistant-corpus**, Drive fileId `1uxB85U-lRTZo75eGdmB23PAvJ2jdyLvvezaQIzaaekY`

Five tabs: `READ ME`, `ANSWERS`, `PLACEMENT`, `FLAGS`, `CHANGE LOG`.

**ANSWERS** — headers on **row 4**, data from **row 5**. Ten columns:
`A ID` · `B Slug` · `C Page` · `D Tap Question (guest sees)` ·
`E Answer Text (pre-approved)` · `F Primary Action → Destination` (arrow is U+2192,
plain `->` also accepted) · `G Topic Tags` · `H Status` · `I Source / Notes` ·
`J Follow-up IDs (slugs)`

**PLACEMENT** — headers row 4: `Page` · `URL path` · `Show / Hide` ·
`Starter question IDs (3–5)` · `Why`

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

**Known gap:** a clock that never fires produces no failed run and therefore no
alert. The Worker closes that hole for GitHub's scheduler; nothing yet watches the
Worker itself. A "no successful publish in N hours" check is the missing piece.

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
2. Add the PLACEMENT row: page name, URL path, `SHOW`, 3–5 starter IDs, why.
3. Add that page's rows to ANSWERS.
4. Add the path to `PILOT_ROUTES` in `publish.py`.
5. Add a `ROUTE_META_FALLBACK` entry for the path (`title`, `launcherLabel`,
   `intro`) — without one those render `null` and the panel falls back to generic
   strings.
6. Publish.

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
fired **zero** times — nine consecutive missed ticks. Every possible
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
