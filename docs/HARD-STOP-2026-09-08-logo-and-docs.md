# HARD STOP — logo swap, publish.py additions, documentation cleanup

**Date:** 2026-09-08
**Branch:** main
**State:** working tree modified, NOTHING deployed, NOTHING committed.
**Scope honoured:** `public/grace-assistant.js`, `publish.py`, `HANDOFF.md`,
`PUBLISHING.md`. Untouched: `.github/`, `worker/`, `worker-clock/`, the Sheet.

---

## Summary of changes

```
HANDOFF.md                | 80 +++++++++++++++++++++++++++++++-------
PUBLISHING.md             | 28 ++++++++++++
public/grace-assistant.js | 44 +++++++++++++-------
publish.py                | 58 +++++++++++++++++++++++--
4 files changed, 187 insertions(+), 23 deletions(-)
```

Also deleted: `GRACE-WIDGET-BUILD-STATE-2026-08-27.md` (untracked for twelve
days, superseded by the tracked `SESSION-2026-08-27.md`; no history lost).

---

## PART A — Logo swap from T's artwork

### Source verification

`design/Grace_Logo.svg` was read rather than taken on trust. It matches the
brief exactly.

- md5 `1d92c992cb43e1751bde7ac0a655bf19`, 489 bytes
- `viewBox="0 0 144 144"`
- one filled circle `cx=72 cy=72 r=72`, class fill `#f15822` (lowercase in the
  file; same colour as the `#F15822` in the brief)
- five white dots `r=9.67` at (72.12,72) (100.88,72) (43.12,72) (72,100.88)
  (72,43.12)

The centre dot's `cx=72.12` is reproduced as drawn. It is not tidied to 72.

### Arithmetic

Glyph span, horizontal and vertical alike:

```
right edge  = 100.88 + 9.67 = 110.55
left edge   =  43.12 - 9.67 =  33.45
span        = 110.55 - 33.45 = 77.10 units of 144
ratio       = 77.10 / 144 = 0.535417 = 53.54%
```

The glyph is square. The old mark was not.

**Launcher.** In her file the badge circle *is* the viewBox — r=72 of a 144-unit
box — so setting the svg box to the badge diameter reproduces her proportion
exactly rather than approximating it:

```
svg = 60px (= the badge diameter, unchanged)
glyph = 60 x 77.10/144 = 32.13px
      = 32.13 / 60 = 53.54% of the badge   <- her ratio, to 2dp
```

Browser-measured after the change: `32.1px tall in a 60px circle, 53.54%`.

| | before | after |
|---|---|---|
| badge | 60px | 60px (unchanged) |
| svg box | 40px on a 44 viewBox | 60px on a 144 viewBox |
| rendered glyph | 29.09px | **32.13px** |
| % of badge | 48.5% | **53.5%** |
| badge fill | `#FF5500` | `#F15822` |

**Header.** There is no circle behind the header mark, so the 53.5%-of-circle
ratio is meaningless there and the box was sized for visual weight instead.

```
before: svg 22px on a 44 viewBox -> 16.00px tall x 14.00px wide (asymmetric plus)
after:  svg 28px on a 144 viewBox -> 28 x 77.10/144 = 14.99px square
```

28px was chosen because the new glyph is square while the old one was not: 15.0px
sits inside the old 14x16 envelope on both axes, rather than matching one
dimension and overshooting the other. Dot radius goes 2.00px -> 1.88px.

Browser-measured after the change: `svg 28x28, glyph 14.99 tall x 14.99 wide,
dot r 1.88px, fill rgb(241, 88, 34)`.

### Colour containment

`LOGO_ORANGE = '#F15822'` was added as a separate constant. `ORANGE = '#FF5500'`
is untouched. `grep -n LOGO_ORANGE` returns exactly three lines — the definition
and the two permitted uses:

```
59:  var LOGO_ORANGE = '#F15822';
206:    '  background: ' + LOGO_ORANGE + '; color: #FFFFFF;',      <- launcher badge
261:    '.mark svg { ... fill: ' + LOGO_ORANGE + '; ... }',        <- header dots
```

Buttons, focus rings, borders, carets and the ghost-chip washes all remain on
`ORANGE`.

### A note for T on the two oranges

Before this change the header mark and the primary action button were **the same
colour** (`rgb(255,85,0)` both). There was no adjacency to judge. There is now:
mark `#F15822`, button `#FF5500`. The second screenshot exists for exactly this
call and it is a real design decision, not a rendering artefact.

### B1 flag-off paired trace

Panel driven to exhaustion under both flag settings, before and after.

```
flag-off: steps 26 -> 26   flow mismatches 0
flag-on:  steps  8 ->  8   flow mismatches 0
```

Raw shadow-DOM comparison reports 26 and 8 differences. Every one of them is
inside an `<svg>` element: masking all svg markup makes both sides byte-identical
on both flag settings. That is the intended change and nothing else moved. The
sole computed-style delta across the whole sweep is `launcherBug.bg`.

---

## PART B — The service-times row (read-only; no Sheet writes)

### Finding: there is no service-times row on Planning your visit

The premise does not hold, and the Sheet is in better condition than the brief
assumed.

- 70 live rows; every ID conforms to the RTS scheme `^[A-Z]{3,6}-(F?\d{1,2})$`
- **zero** leading/trailing whitespace anywhere in ID, Slug, Page, Status or
  Follow-up IDs — the whitespace hypothesis is disproved, not merely unconfirmed
- Status values are exactly `{'DRAFT': 48, 'HOLD': 22}`
- CHANGE LOG holds five entries, all RTS, none later than 2026-08-28. No
  third-party addition is recorded anywhere.

The seven Plan Your Visit rows are `what-to-wear`, `parking`, `kids`,
`nursing-room`, `quieter-space`, `watch-online`, `pets-firearms`. None concerns
service times.

### The two rows that do exist, verbatim

| Field | Row 18 | Row 5 |
|---|---|---|
| ID | `'ORL-02'` | `'HOME-01'` |
| Slug | `'service-times'` | `'when-services'` |
| Page | `'Orlando'` | `'Homepage'` |
| Status | `'DRAFT'` | `'DRAFT'` |
| Question | `'What are service times here?'` | `'When are your services?'` |

Every value is `repr()`-printed above; none carries padding.

### Gate-by-gate

**1. Scope — FAILS, and at two levels.**
`Page` is `'Orlando'` / `'Homepage'`, neither of which is a pilot page, so both
rows are dropped at build. More importantly, correcting the Page cell alone would
not be enough: `PILOT_ROUTES = ['/plan-your-visit/', '/giving/']`, so `/orlando/`
and `/` cannot ship at all without a **publish.py** change. This is not fixable
from the Sheet if the intent is to ship it on its own page.

**2. Reachability — also FAILS, independently.**
Neither `service-times` nor `when-services` appears in any PLACEMENT starter list
or in any row's Follow-up IDs cell. Even with scope corrected, nothing would
link to it. Two gates fail, not one — fixing either alone still renders nothing.

**3. Timing — irrelevant, as expected.**
The Sheet was last modified 2026-08-30T14:08Z and four publishes have run since.
The debounce only ever defers a tick to the next one; it cannot permanently
withhold a row. Noted for completeness.

### What would fix it — NOT DONE

Set `ORL-02`'s Page to `Plan Your Visit`, **and** make the slug reachable.

On the starter cap: `/plan-your-visit/` starters are
`PYV-01, PYV-02, PYV-03, PYV-04, PYV-06` — five of a maximum five. Promoting
service-times to a starter therefore displaces an existing question, which is a
content decision for T and not ours to make.

**There is a cheaper route that avoids the displacement entirely.** All seven PYV
rows already carry populated Follow-up IDs cells:

```
PYV-01 what-to-wear    followups='parking, kids, pets-firearms'
PYV-02 parking         followups='what-to-wear, kids, pets-firearms'
PYV-03 kids            followups='nursing-room, quieter-space, parking'
...
```

Adding `service-times` to one or two of those cells makes it reachable without
touching the starter list at all. Still a content decision, but a smaller one.

Cosmetic note: the ID would read `ORL-02` on a Plan Your Visit page. Harmless —
`Slug` is the JSON key, `ID` is only used for starter references — but it will
look wrong to the next reader.

---

## PART C — publish.py, two additions

Neither alters any RESULT status value, any exit code, or the deploy path.

### 1. Out-of-scope rows are now reported

A correction to the brief's premise: the rows were not *entirely* silent — a
summary line already existed. But it went through `say()`, which `--quiet`
suppresses, and **CI always runs `--quiet`**. So the single largest reason a row
does not ship was invisible in exactly the place people go looking. It now uses
`print()`, states the reason, and breaks the count down per page:

```
  in scope: 14 questions   out of scope: 56 rows (Page is not a pilot page)
      6 row(s)  Page='Family Ministry'
      6 row(s)  Page='GraceKids'
      5 row(s)  Page='Care'
      ... 17 pages in total ...
      1 row(s)  Page='Contact'
```

56 excluded + 14 shipped = 70 rows. Fully accounted for.

**Near-miss detection.** The useful definition is narrower than it first appears.
`fold()` is already trim + casefold, so a page differing only by case or by outer
spaces *already ships*. Flagging those would be noise. What actually bites is
whitespace `fold()` cannot see — an internal double space, or a non-breaking
space pasted in from a document — which looks identical in the cell and silently
drops the row. The check squashes all whitespace including U+00A0 and re-tests;
if it would then match a pilot page, the row is one invisible character from
shipping and gets a `warn()`.

Verified against the real gate logic:

```
'Plan Your Visit'       -> ships (fold already matches)
'plan your visit'       -> ships (fold already matches)
'  Plan Your Visit  '   -> ships (fold already matches)
'Plan  Your  Visit'     -> NEAR-MISS -> warn
'Plan\xa0Your Visit'    -> NEAR-MISS -> warn
'Orlando' / 'Giving'    -> genuinely out of scope, silent
```

Zero near-misses in the Sheet today, so `warnings=` is unchanged.

### 2. `changed` — DECISION: made it a real count

The brief allowed either renaming the field or making it count. **Made it count.**

Reasoning: the field is already *named* like a count, and it appears in the ntfy
notification body. `changed=3` tells a reader something at 2am; a renamed
`content_changed=true` would only repeat what `status=deployed` already said. The
information was cheap to compute and the field was the only thing lying about it.

One unit = one question added, removed or edited; one route whose config differs;
or the meta block. `_editorNote` is excluded, exactly as it is from the
`unified()` gate that decides whether to deploy at all — so any publish reaching
this line counts at least 1, and `changed=0` is unreachable in practice.

Unit-tested against the live document with synthetic mutations:

```
identical documents                                changed=0
1 answer edited                                    changed=1
2 answers edited     (old code reported changed=1) changed=2
1 question added                                   changed=1
1 question removed                                 changed=1
1 route retitled                                   changed=1
meta changed                                       changed=1
_editorNote ONLY  (must be 0, matches deploy gate) changed=0
1 question + 1 route + meta                        changed=3
```

### Dry-run battery — identical to baseline

Run against the pre-change file and the post-change file, same machine, same
Sheet:

```
publish.py                                     exit=0  RESULT status=nochange questions=14 warnings=1
publish.py --quiet                             exit=0  RESULT status=nochange questions=14 warnings=1
publish.py --quiet --min-quiet-minutes 30      exit=0  RESULT status=nochange questions=14 warnings=1
publish.py --quiet --min-quiet-minutes 99999   exit=0  RESULT status=debounced idle_minutes=13306 threshold_minutes=99999
publish.py --help                              exit=0  (no RESULT line, as expected)
```

All RESULT lines and exit codes match the baseline exactly.

*(An earlier run of this battery appeared to show exit=2 regressions. That was my
harness, not the code: zsh does not word-split unquoted parameters, so the whole
flag string was passed as a single argv entry and argparse rejected it. Re-run
with arguments passed as real argv, as above.)*

---

## PART D — Documentation corrections

All eight applied, plus two found along the way.

| # | Correction | File |
|---|---|---|
| 1 | "three files" -> four files plus a `fonts/` directory | HANDOFF |
| 2 | "No font files shipped" -> the widget ships `QuincyCF-Medium.woff2`, with why | HANDOFF |
| 3 | Known gap rewritten as *narrowed*, not deleted: what the heartbeat covers, and the three things it does not (24h latency; it is a pull not a push; it heartbeats happily through a partial failure) | HANDOFF |
| 4 | "nine consecutive missed ticks" -> **seven**, with a note that sixteen hours cannot contain nine ticks at a two-hour cadence | HANDOFF |
| 5 | Sheet title -> `grace-assistant-corpus-2026-08-27`, with a warning that searching Drive for the short name fails | HANDOFF |
| 6 | The `@font-face` deviation documented: why it is in `document.head`, that shadow-root `@font-face` is ignored by Chromium and WebKit, and that it was proven with the `shadow-scoped-probe` family (1127.05px = monospace baseline vs 872.13px loaded). Ends "Do not 'fix' this by moving the rule back." | HANDOFF |
| 7 | Pre-deploy guard added as a REQUIRED step, with the 2026-09-08 incident as the reason, and the reverse hazard (uncommitted widget change reverted by the next content publish) | PUBLISHING |
| 8 | Model corrected to the alias `claude-haiku-4-5`, with the implication stated: the vendor can repoint it, so the model can change without a deploy. Framed as a deliberate trade, with the remedy if pinning is ever wanted | HANDOFF |

Two beyond the list:

- The widget's own source comment also read `No font files shipped.` — the same
  falsehood in a second place. Corrected in `public/grace-assistant.js`.
- HANDOFF now notes that Cloudflare Pages strips the extension, so `test.html` is
  live at `/test` as well as `/test.html`. Relevant to the teardown checklist item.

---

## PART E — Do the demo pages load Grace's own webfonts?

**Yes. All six families resolve. Reviewers have not been judging fallback type.**

Measured, not inferred: the deployed demo bundle was served and loaded in a real
browser, with each family explicitly loaded before measuring.

| family | width @48px | resolves |
|---|---|---|
| monospace baseline | 1184.84 | — |
| bogus control | 1184.84 | control sound |
| **interstate** | 932.31 | **yes** |
| greyclif-regular | 904.28 | yes |
| greycliff-demi | 920.22 | yes |
| greycliff-bold | 933.84 | yes |
| quincy-black | 986.31 | yes |
| greycliff-cf | 934.72 | yes |

What the demo HTML references, and how it resolves:

- **Greycliff x4 + Quincy Black** — `/wp-content/uploads/useanyfont/uaf.css`,
  five `.woff2` files mirrored locally, all HTTP 200.
- **Interstate x5 weights** — `/use.typekit.net/yzg5cqn.css`. The `wget` mirror
  rewrote the Typekit `src` URLs to **relative local paths**, and pulled down all
  15 binaries (5 weights x 3 formats) under `/use.typekit.net/af/`. The demo
  therefore does not depend on Adobe's CDN and is not affected by Typekit's
  domain-locking — which is what would otherwise have broken Interstate on a
  `pages.dev` host.
- Only `/p.typekit.net/p.css` 404s. That is Typekit's analytics beacon, declares
  no faces, and is harmless.

Verified locally rather than against the live host because `grace-demo.pages.dev`
is behind Cloudflare Access (one-time PIN to two named addresses) and headless
cannot reach it. The bundle measured is the bundle that was uploaded: demo files
are dated 2026-08-27 13:10 and the deployment is 2026-08-27 17:22, with no demo
redeploy since.

**Correction to my own first pass.** I initially reported Interstate and
quincy-black as *absent*. That was a measurement error, not a finding: I measured
spans without calling `document.fonts.load()` first, and a webfont is not fetched
until something needs it, so lazily-loaded faces read as fallback. The table above
is the corrected run, with the bogus-family control sitting exactly on the
monospace baseline to prove the method.

---

## Findings where the machine disagreed with the documentation

Reported as findings, per the brief's instruction that the machine outranks the docs.

1. **`HANDOFF.md` model id was wrong** — documented `claude-haiku-4-5-20251001`,
   actual `claude-haiku-4-5`. Corrected, and the consequence spelled out.
2. **`HANDOFF.md` file list was wrong** — three files, actually four plus a fonts
   directory. Corrected.
3. **"No font files shipped" was wrong in two places** — HANDOFF and the widget's
   own comment. Both corrected.
4. **`HANDOFF.md` incident-log tick count is arithmetically impossible** — nine
   ticks in sixteen hours at a two-hour cadence. PUBLISHING.md and the workflow
   comment both say seven. Corrected to seven.
5. **The Sheet's title is not what any document says.** Corrected.
6. **The "known gap" had been narrowed and never written down.** Corrected, with
   the residual gap stated rather than papered over.
7. **The brief's premise for Part B does not hold.** No service-times row exists
   on Planning your visit, and the Sheet has no whitespace defects at all.
8. **The brief's premise for Part C.1 is half right.** Out-of-scope rows were not
   silent in principle — there was a `say()` line — but they were silent in CI,
   which is the only place it mattered.

---

## Outstanding decision, outside the stated scope

`design/Grace_Logo.svg` is **untracked**. The brief calls it "in the repo", and
the widget's new source comment cites it by path as the source of truth for the
geometry — that citation dangles unless the file is committed. Committing it was
outside the stated file scope, so it has not been done. Recommend including it.

---

## Not yet done — awaiting approval

```
1. git fetch origin && git diff --quiet origin/main -- public/answers.json
2. npx wrangler pages deploy public --project-name grace-assistant --branch main
3. two cache-busted md5 checks on BOTH hostnames
4. commit and push IN THIS SESSION
```

Step 4 is not optional housekeeping: an uncommitted widget change is silently
reverted by the next content publish, which is now documented in PUBLISHING.md as
a consequence of the 2026-09-08 incident.

To be reported on completion: new md5, commit hash, rollback deployment id.
