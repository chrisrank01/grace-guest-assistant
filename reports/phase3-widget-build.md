# Phase 3 — Guest Assistant Widget Build

**Date:** 2026-08-27
**Branch:** `main`
**Scope:** Build a tap-only guest assistant widget for the church website and serve it
locally.

---

## Files created

All three live in `public/`, plus this report.

| File | Size | Purpose |
| --- | --- | --- |
| `public/grace-assistant.js` | ~465 lines | The widget. Vanilla JS, no deps, no build. |
| `public/answers.json` | 16 questions | Every question a guest can tap and its answer. |
| `public/test.html` | 1 page | Mock visit page for testing, with a route switcher. |
| `reports/phase3-widget-build.md` | — | This file. |

---

### `public/grace-assistant.js`

Drops onto any page with a single tag:

```html
<script src="/grace-assistant.js" data-answers="/answers.json" defer></script>
```

**Attributes**

- `data-answers` — URL of the answers file (default `answers.json`)
- `data-route` — force a route instead of reading `location.pathname`
- `?ga-route=/some-path/` — query-string override, for testing; wins over `data-route`

**What it does**

- Renders entirely inside a **shadow root**, so the church's existing CSS cannot reach
  into the widget and the widget cannot leak styles onto the page.
- Resolves the current route by normalizing the path (lowercase, leading and trailing
  slash), then matching **exact route → longest matching prefix → `default`**.
- Renders an intro bubble plus that route's starter questions. Tapping a chip appends the
  question as a guest bubble and the answer as a church bubble, then swaps the chip list
  to that question's follow-ups.
- If a question has no follow-ups, it falls back to the starter list minus the question
  just asked, so the widget never dead-ends.
- Follow-up views always include a dashed "Back to the main questions" chip. The footer
  has a persistent "Start over".

**Structure of the panel:** header (cross mark, title, subtitle, close) → scrolling
transcript → chip list (scrolls independently, capped at 46% height) → footer hint and
restart.

---

### `public/answers.json`

Single source of truth for content. Shape:

```json
{
  "meta":      { "title": "...", "subtitle": "...", "homeLabel": "...", "_editorNote": "..." },
  "routes":    { "/plan-your-visit/": { "intro": "...", "starters": ["id", "..."] },
                 "default":           { "intro": "...", "starters": ["id", "..."] } },
  "questions": { "id": { "label": "...", "answer": ["para", "para"],
                         "links": [{ "label": "...", "href": "..." }],
                         "followups": ["id", "..."] } }
}
```

**Routes**

- `/plan-your-visit/` — starts with **service times, what to wear, parking** (the three
  requested)
- `default` — service times, what happens when I arrive, where are you, talk to someone

**The 16 questions**

- service times
- what to wear
- parking
- what happens when I arrive
- what's a service like
- how long is it
- kids
- students
- running late
- will I be singled out
- will I be asked for money
- what do you believe
- accessibility
- coffee
- where are you located
- can I talk to a person

Every starter and follow-up reference was validated against the question set — **no broken
references**.

---

### `public/test.html`

A mock Plan Your Visit page in the same palette: nav, hero, service cards, and a black
test bar at the top with links that switch the simulated route between
`/plan-your-visit/`, `/`, and an unmatched path (to confirm the `default` fallback). Loads
the widget with `data-route="/plan-your-visit/"` so the visit-page starters appear even
though the file is served at `/test.html`.

---

## Design decisions

**Palette, exactly as specified**

| Token | Value | Applied to |
| --- | --- | --- |
| Navy | `#292E38` | All text, guest bubble background |
| Orange | `#FF5400` | Launcher, header mark, chip carets, hover borders, links |
| Cream | `#FAFAF7` | Panel background, header, footer, guest bubble text |
| White | `#FFFFFF` | Answer bubbles, chips |
| Radius | `4px` | Panel, bubbles, chips, buttons — all but the circular launcher |

**Launcher mark.** 60px orange circle holding 5 white dots arranged as a **Latin cross** —
vertical dots at y=8/20/32, horizontal at x=12/32 sharing the y=20 center dot. Placing the
crossbar high rather than centered is what makes it read as a cross instead of a plus
sign. The same mark appears small and orange in the panel header. Opening the panel swaps
the launcher glyph to an X.

**Tap-only, enforced structurally.** The widget contains no text-entry element of any kind
— no input, no textarea, no `contenteditable`. The only interactive elements are the
launcher, close button, "Start over", and question chips.

**Answers can't inject markup.** Answer paragraphs are set with `textContent`, never
`innerHTML`. Hyperlinks come only from the structured `links` array, and external hosts
get `target="_blank" rel="noopener noreferrer"`. This means a non-technical editor can
update `answers.json` without any way to introduce script into the page.

**Fails silent, not broken.** If `answers.json` is missing or malformed, the widget logs to
the console and renders nothing. A content error should never put a visibly broken
launcher on the live site. Likewise, a route with no starters renders nothing at all.

**Accessibility.** `role="dialog"` on the panel, `role="log"` plus `aria-live="polite"` on
the transcript, `aria-expanded` on the launcher, Escape to close, focus moves to the first
chip after each answer and returns to the launcher on close, visible `:focus-visible`
rings throughout, and `prefers-reduced-motion` disables transitions.

**Responsive.** Fixed bottom-right card at 372px wide; under 480px it becomes a full-width
bottom sheet at 74vh.

---

## Did it run?

**Yes.** `npx serve public` is running.

**Local URL: http://localhost:59480/test.html**

Verified over HTTP:

| Path | Status | Content-Type |
| --- | --- | --- |
| `/test.html` | 200 | `text/html; charset=utf-8` |
| `/grace-assistant.js` | 200 | `application/javascript; charset=utf-8` |
| `/answers.json` | 200 | `application/json; charset=utf-8` |

---

## Things to flag for review

### 1. Content specifics are placeholders — this is the blocking item

The prose is written to be kept; the facts in it are invented and must be replaced before
this goes anywhere near production:

- Service times (Sun 9:00 and 11:00 a.m., 75 minutes, doors 30 min early)
- Address `1200 Church Street`, lot entrance on Oak Avenue, orange doors
- Kids age bands (nursery–2, ages 3–5th grade) and student night (Wed 6:30–8:00)
- Guest services hours (Mon–Thu, 9:00–4:00)
- Phone `(555) 010-0199` and email `hello@example.church` — deliberately fake so a wrong
  real number cannot ship by accident
- Overflow lot one block east with a shuttle
- The `/what-we-believe/` link target, which may not exist

A `meta._editorNote` field at the top of `answers.json` says the same thing to whoever
opens the file next.

### 2. Port 3000 was already occupied

`serve` fell back to **59480** on its own. A pre-existing `node` process (PID 77582,
started outside this session) holds port 3000 and appears to be serving this same
directory — requests to `http://localhost:3000/answers.json` return the file written in
this session. Worth identifying and killing it before anyone assumes 3000 is the live
instance, since both ports currently serve the same content and it would be easy to test
the wrong one.

### 3. Not done, because it wasn't in scope

- No automated tests. Verification was HTTP status and content-type checks plus JSON
  reference validation; the interaction flow has not been exercised in a browser by me.
- No analytics or "was this helpful" capture. Worth considering later — which questions
  get tapped is the most useful signal this widget can produce.
- No persistence. Closing and reopening the panel keeps the transcript, but a page reload
  resets it. That seemed right for a guest widget; flagging it in case it isn't.
- Not tested against the real site's CSS. Shadow DOM should make that a non-issue, but
  "should" is doing work in that sentence until it's on a staging page.
- The `default` route's starters were my judgment call, not specified. Easy to change in
  `answers.json` without touching the JS.
