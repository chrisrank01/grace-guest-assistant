#!/usr/bin/env python3.12
"""
publish.py - build public/answers.json from the corpus Google Sheet.

Default run is a DRY RUN: writes build/answers.json and prints both a unified
diff and a field-level semantic diff against public/answers.json. Nothing that
guests can see changes until you pass --deploy.

    .venv/bin/python publish.py             # dry run
    .venv/bin/python publish.py --deploy    # write public/ and ship it
"""

import argparse
import datetime
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

# The corpus workbook. Read-only scope; publish.py never writes to the Sheet.
SHEET_KEY = '1uxB85U-lRTZo75eGdmB23PAvJ2jdyLvvezaQIzaaekY'

# Service-account key. Lives in secrets/ which is gitignored; env var wins so a
# CI runner can point somewhere else without editing this file.
KEY_PATH = os.environ.get('GRACE_PUBLISHER_KEY', 'secrets/grace-publisher.json')

# Pilot scope. A page ships only if PLACEMENT marks it SHOW *and* its URL path
# is listed here. Adding a page to the pilot = adding its path to this list.
PILOT_ROUTES = ['/plan-your-visit/', '/giving/']

# HOLD rows are never shipped - they are blocked on a content conflict (FLAGS
# tab). DRAFT ships during the pilot per operator direction; tighten this to
# {'APPROVED'} at pilot exit and the same script enforces it.
SHIP_STATUSES = {'DRAFT', 'APPROVED'}

# Widget chrome that is not page-specific. Mirrors what is deployed today.
GLOBAL_META = {
    'title': 'Grace',
    'subtitle': 'Guest Assistant',
    'launcherLabel': 'Ask Grace',
    'startersLabel': 'Common questions',
    'followupsLabel': 'WOULD YOU ALSO LIKE TO KNOW',
    'footerHint': 'Tap a question — no typing needed',
    'restartLabel': 'Start over',
    'homeLabel': '← Back',
}

# Per-route overrides. The PLACEMENT tab has no columns for these today, so
# these hardcoded strings are the source of truth. If PLACEMENT later grows
# 'Panel title' / 'Launcher label' / 'Intro' columns, those win automatically
# (see read_placement) and these become the fallback only.
ROUTE_META_FALLBACK = {
    '/plan-your-visit/': {
        'title': 'Planning your visit',
        'launcherLabel': 'Planning a visit? Tap here',
        'intro': "Glad you're planning a visit. Tap a question and we'll help you get ready.",
    },
    '/giving/': {
        'title': 'Giving at Grace',
        'launcherLabel': 'Questions about giving? Tap here',
        'intro': "Thanks for your generosity. Here's how giving works at Grace.",
    },
}

# The one '(any page)' row that ships in the pilot. Appended as a follow-up to
# every other question so a guest always has a route to a human.
TALK_PERSON_SLUG = 'talk-person'

# Column headers, matched by name not position. The arrow is U+2192.
COL_ID, COL_SLUG, COL_PAGE = 'ID', 'Slug', 'Page'
COL_Q = 'Tap Question (guest sees)'
COL_A = 'Answer Text (pre-approved)'
COL_LINK = 'Primary Action → Destination'
COL_STATUS = 'Status'
COL_FOLLOWUPS = 'Follow-up IDs (slugs)'
# Added 2026-09-13. A question ships to its Page plus any page named here.
# Blank means "appears only on its Page", which is what all 70 rows say today.
COL_ALSO_1 = 'Also on'
COL_ALSO_2 = 'Also on 2'

# The end-of-questions handoff line, per route, from PLACEMENT.
COL_END = 'end of questions'     # matched lowercased, like the other route-meta

# What the widget says when a guest has tapped everything on a page. This MUST
# stay byte-identical to EXHAUSTION_NOTE in public/grace-assistant.js: it is the
# string the widget falls back to when a route carries no endOfQuestions key,
# and the two drifting apart would mean the Sheet silently stopped being able to
# reproduce the default.
#
# A route whose cell is blank resolves to exactly this string, and publish.py
# then omits the key rather than writing it. That is deliberate: emitting it
# would change every route in answers.json on the first run after this change,
# for no behaviour change at all, and the whole point is that the site stays
# byte-identical until someone types something.
END_OF_QUESTIONS_FALLBACK = (
    'That covers everything I can answer here. Want to talk with a real person?'
)

HEADER_ROW = 4          # 1-indexed; data starts at row 5
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    # Needed only for the quiescence debounce (Drive file modifiedTime).
    # Requires the Drive API to be enabled on the GCP project as well.
    'https://www.googleapis.com/auth/drive.metadata.readonly',
]
OUT_BUILD = 'build/answers.json'
OUT_PUBLIC = 'public/answers.json'
PAGES_PROJECT = 'grace-assistant'
LIVE_URL = 'https://grace-assistant.pages.dev/grace-assistant.js'
LIVE_JSON = 'https://grace-assistant.pages.dev/answers.json'

WARNINGS = []
FATAL = []
QUIET = False


def say(msg):
    """Chatter - suppressed under --quiet."""
    if not QUIET:
        print(msg)


def result(**fields):
    """One machine-readable summary line, always printed. Never contains
    credential material - only counts, statuses and content-derived values."""
    print('RESULT ' + ' '.join(f'{k}={v}' for k, v in fields.items()))


def warn(msg):
    WARNINGS.append(msg)
    print(f'  WARN  {msg}')


def fatal(msg):
    """A condition that must stop the publish. Collected so one run reports
    every problem rather than dying on the first."""
    FATAL.append(msg)
    print(f'  FATAL {msg}')


def norm(value):
    """Trim. Sheet cells routinely carry stray leading/trailing space."""
    return (value or '').strip()


def fold(value):
    """Trim + casefold, for comparisons that must not care about case."""
    return norm(value).casefold()


def die(problems):
    print('\nVALIDATION FAILED - nothing written\n')
    for p in problems:
        print(f'  - {p}')
    sys.exit(2)


# ---------------------------------------------------------------------------
# READ
# ---------------------------------------------------------------------------

def sheet_modified_minutes_ago():
    """Minutes since the corpus Sheet was last edited, via the Drive API.

    Raises on any failure - an unattended publisher that cannot establish
    quiescence must fail loudly rather than guess and ship a half-finished edit.
    """
    import urllib.request
    from google.oauth2.service_account import Credentials
    import google.auth.transport.requests as gtr

    creds = Credentials.from_service_account_file(KEY_PATH, scopes=SCOPES)
    creds.refresh(gtr.Request())
    url = (f'https://www.googleapis.com/drive/v3/files/{SHEET_KEY}'
           '?fields=modifiedTime&supportsAllDrives=true')
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + creds.token})
    body = json.load(urllib.request.urlopen(req, timeout=30))
    stamp = body['modifiedTime'].replace('Z', '+00:00')
    edited = datetime.datetime.fromisoformat(stamp)
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now - edited).total_seconds() / 60.0


def open_sheet():
    import gspread
    from google.oauth2.service_account import Credentials
    if not os.path.exists(KEY_PATH):
        sys.exit(f'no service-account key at {KEY_PATH} (set GRACE_PUBLISHER_KEY)')
    gc = gspread.authorize(Credentials.from_service_account_file(KEY_PATH, scopes=SCOPES))
    return gc.open_by_key(SHEET_KEY)


def tabulate(values, header_row=HEADER_ROW):
    """Rows below the header, as dicts keyed by header name."""
    header = values[header_row - 1]
    out = []
    for raw in values[header_row:]:
        row = {h: (raw[i].strip() if i < len(raw) else '') for i, h in enumerate(header)}
        if any(row.values()):
            out.append(row)
    return header, out


def is_concrete_path(path):
    """Is this URL path one real page, or a pattern standing for many?

    PLACEMENT's HIDE block carries catch-all rows - '*', '/watch/*',
    '/sermons/, /sermon/*', 'gracecounselingcenter.org/*' - and one separator
    row with no path at all. Those name rules, not pages. A page name is only
    addressable by an 'Also on' cell if it corresponds to exactly one real
    path, so the valid-page list is built from this test rather than from
    'every row that has something in column A' - which would happily accept
    'Also on: ——— HIDE below ———'.
    """
    path = (path or '').strip()
    return bool(path) and path.startswith('/') and ',' not in path and '*' not in path


def read_placement(sh):
    """PLACEMENT -> (pilot route config, page inventory).

    The route config is the SHOW rows whose URL path is in PILOT_ROUTES, as
    before. The inventory is EVERY row naming one concrete page, pilot or not,
    and is what 'Also on' values are validated against - a question may legally
    name a page that is not in the pilot, it just will not ship there yet.
    """
    header, rows = tabulate(sh.worksheet('PLACEMENT').get_all_values())
    lower = {h.strip().lower(): h for h in header if h.strip()}
    # optional, absent today - present-tense support so the Sheet can drive these later
    col_title = lower.get('panel title')
    col_launch = lower.get('launcher label')
    col_intro = lower.get('intro')
    col_end = lower.get(COL_END)

    routes = {}
    inventory = {}          # folded page name -> {'page', 'path', 'show'}
    for row in rows:
        page = row.get(COL_PAGE, '').strip()
        path = row.get('URL path', '').strip()
        show = row.get('Show / Hide', '').strip().upper() == 'SHOW'
        if page and is_concrete_path(path):
            # GATE: two PLACEMENT rows claiming one page name makes 'Also on'
            # ambiguous - which path did the author mean?
            if fold(page) in inventory:
                fatal(f'PLACEMENT names the page {page!r} twice '
                      f'({inventory[fold(page)]["path"]} and {path})')
            inventory[fold(page)] = {'page': page, 'path': path, 'show': show}
        if not show or path not in PILOT_ROUTES:
            continue
        fallback = ROUTE_META_FALLBACK.get(path, {})
        routes[path] = {
            'page': page,
            'starter_ids': [s.strip() for s in row.get('Starter question IDs (3–5)', '').split(',') if s.strip()],
            'title': (row.get(col_title) or '').strip() or fallback.get('title'),
            'launcherLabel': (row.get(col_launch) or '').strip() or fallback.get('launcherLabel'),
            'intro': (row.get(col_intro) or '').strip() or fallback.get('intro'),
            'endOfQuestions': ((row.get(col_end) or '').strip()
                               or fallback.get('endOfQuestions')
                               or END_OF_QUESTIONS_FALLBACK),
        }
    if col_title or col_launch or col_intro or col_end:
        say('  PLACEMENT supplies route meta columns; Sheet values win over fallback')
    else:
        say('  PLACEMENT has no route-meta columns; using ROUTE_META_FALLBACK')
    say(f'  page inventory: {len(inventory)} page(s) with one concrete path '
        f'({sum(1 for v in inventory.values() if v["show"])} SHOW)')
    return routes, inventory


# ---------------------------------------------------------------------------
# TRANSFORM
# ---------------------------------------------------------------------------

def parse_one_link(seg, slug):
    """One 'Label -> destination' segment -> {label, href}, or None (with a
    warning) if the destination is prose rather than somewhere a browser can go.

    Accepts the Sheet's own arrow (U+2192) or a plain ASCII '->', because a
    hand-typed cell will not always carry the fancy one."""
    seg = norm(seg).replace('->', '→')
    if not seg:
        return None
    if '→' not in seg:
        # A bare 'Call NNN-NNN-NNNN' is the one destination-less form we accept.
        digits = re.sub(r'\D', '', seg)
        if seg.lower().startswith('call') and len(digits) == 10:
            return {'label': seg, 'href': f'tel:+1{digits}'}
        warn(f'{slug}: link {seg!r} has no destination - link dropped')
        return None
    label, dest = (p.strip() for p in seg.split('→', 1))
    if dest.startswith('/') or re.match(r'^https?://', dest) or dest.startswith('tel:'):
        return {'label': label, 'href': dest}
    warn(f'{slug}: destination {dest!r} is not a path/URL/tel - link dropped')
    return None


def parse_links(raw, slug):
    """A Primary Action cell -> list of links. Multiple actions are separated by
    ' | '; the first is the primary and renders as the orange button. A cell with
    no separator behaves exactly as a single-link cell always has."""
    raw = norm(raw)
    if not raw:
        return []
    segments = [seg for seg in raw.split(' | ')] if ' | ' in raw else [raw]
    return [link for link in (parse_one_link(seg, slug) for seg in segments) if link]


def build(sh):
    routes_cfg, inventory = read_placement(sh)
    if not routes_cfg:
        die(['PLACEMENT has no SHOW rows matching PILOT_ROUTES'])

    # Page -> route path, derived from PLACEMENT rather than hardcoded names
    page_to_route = {fold(cfg['page']): path for path, cfg in routes_cfg.items()}
    say(f'  pilot pages from PLACEMENT: {page_to_route}')

    _, rows = tabulate(sh.worksheet('ANSWERS').get_all_values())

    questions, by_id, drafts, skipped = {}, {}, 0, 0
    out_of_scope = {}   # page value -> how many rows it dropped
    page_slugs = {}
    seen_ids = set()
    shippable = {fold(x) for x in SHIP_STATUSES}
    for row in rows:
        rid, slug = norm(row.get(COL_ID)), norm(row.get(COL_SLUG))
        page, status = norm(row.get(COL_PAGE)), norm(row.get(COL_STATUS))
        question, answer = norm(row.get(COL_Q)), norm(row.get(COL_A))

        # GATE: 'Also on' naming a page PLACEMENT does not define. The dropdown
        # protects the editor at typing time; this is the backstop for what a
        # dropdown cannot catch - a PLACEMENT row deleted afterwards, or cells
        # pasted in, which bypass Sheets validation entirely. Checked before the
        # scope filter so a bad value is caught even on a row that will not ship.
        also = []
        for col in (COL_ALSO_1, COL_ALSO_2):
            value = norm(row.get(col))
            if not value:
                continue
            entry = inventory.get(fold(value))
            if entry is None:
                fatal(f'{rid or "(no ID)"} ({slug or "(no slug)"}): {col} is '
                      f'{value!r}, which has no PLACEMENT row naming one concrete '
                      f'page. Add the PLACEMENT row, or clear the cell.')
                continue
            # Tier two: the page exists but is switched off. Pre-staging content
            # for a page that is not live yet is legitimate authoring, so this
            # warns and ships rather than stopping the publish.
            if not entry['show']:
                warn(f'{rid} ({slug}): {col} is {value!r}, whose PLACEMENT row is '
                     f'HIDE - the question will not appear there until it is SHOW')
            also.append(entry['page'])

        # GATE: an ID may appear once. Duplicates make starter lists ambiguous.
        if rid:
            if rid in seen_ids:
                fatal(f'duplicate ID {rid!r}')
            seen_ids.add(rid)

        # Every page this row claims: its Page, plus Also on / Also on 2.
        # A row is in scope if ANY of them is a pilot page.
        claimed = [page] + [p for p in also if fold(p) != fold(page)]
        in_scope = any(fold(p) in page_to_route for p in claimed) or slug == TALK_PERSON_SLUG
        if not in_scope:
            skipped += 1
            out_of_scope[page or '(blank)'] = out_of_scope.get(page or '(blank)', 0) + 1
            continue
        if fold(status) not in shippable:
            warn(f'{rid} ({slug}): status {status or "(blank)"} - not shipped')
            continue
        # GATE: cleared to ship but unaddressable. Dropping it silently hides
        # content somebody believes is live.
        if not slug:
            fatal(f'{rid}: status {status} is shippable but Slug is empty')
            continue
        if not (question and answer):
            warn(f'{rid}: missing question/answer - not shipped')
            continue
        if slug in questions:
            fatal(f'duplicate slug {slug!r} (second occurrence at {rid})')
            continue

        if status == 'DRAFT':
            drafts += 1
        entry = {'label': question, 'answer': [p.strip() for p in answer.split('\n\n') if p.strip()]}
        raw_link = norm(row.get(COL_LINK))
        links = parse_links(raw_link, slug)
        # GATE: a destination was written and produced nothing. Previously a
        # warning, which let a button vanish silently from a shipped answer.
        if raw_link and not links:
            fatal(f'{rid} ({slug}): destination cell {raw_link[:60]!r} yielded zero '
                  'usable links - fix the cell or clear it')
        if links:
            entry['links'] = links
        entry['_followups_raw'] = [s.strip() for s in row.get(COL_FOLLOWUPS, '').split(',') if s.strip()]
        questions[slug] = entry
        by_id[rid] = slug
        # Expected membership comes from the Page columns, independent of the
        # follow-up graph - that is what lets the BFS check below actually fail.
        # A multi-page question is expected on every pilot page it claims, which
        # is what keeps the reachability rule honest rather than loosened: each
        # page must still reach exactly its own set, the sets simply overlap now.
        for claim in claimed:
            if fold(claim) in page_to_route:
                page_slugs.setdefault(page_to_route[fold(claim)], set()).add(slug)

    if FATAL:
        die(FATAL)
    # Out-of-scope rows used to vanish without a line anyone could see: the old
    # summary went through say(), which --quiet suppresses, and CI always runs
    # --quiet. So the single largest reason a row does not ship was invisible in
    # exactly the place people go looking. print() instead of say(), because a
    # count of what was dropped is not chatter.
    print(f'  in scope: {len(questions)} questions   '
          f'out of scope: {skipped} rows (Page is not a pilot page)')
    for pg, n in sorted(out_of_scope.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f'    {n:3} row(s)  Page={pg!r}')

    # NEAR-MISS. fold() is trim + casefold, so case and outer spaces already
    # match. What still bites is whitespace fold() cannot see - a double space,
    # a non-breaking space pasted in from elsewhere - which looks identical in
    # the cell and silently drops the row. Squash all of that and re-test; if it
    # would then match a pilot page, the row is one invisible character away
    # from shipping and that is worth a warning, not a log line.
    def _squash(v):
        return re.sub(r'\s+', ' ', v.replace('\u00a0', ' ')).strip().casefold()
    pilot_squashed = {_squash(cfg['page']): cfg['page'] for cfg in routes_cfg.values()}
    for pg in out_of_scope:
        hit = pilot_squashed.get(_squash(pg))
        if hit is not None:
            warn(f'Page {pg!r} is one whitespace difference from the pilot page '
                 f'{hit!r} - {out_of_scope[pg]} row(s) dropped. Retype the cell.')
    if drafts:
        warn(f'{drafts} DRAFT row(s) shipped - SHIP_STATUSES currently allows DRAFT')

    # followups are pure Sheet content now. talk-person is a pinned action in the
    # widget, not a chip, so it is never appended here; if a Sheet cell still
    # lists it we drop it, and the widget filters it too during the transition.
    for slug, entry in questions.items():
        fus = [f for f in entry.pop('_followups_raw') if f != TALK_PERSON_SLUG]
        entry['followups'] = [] if slug == TALK_PERSON_SLUG else fus

    routes = {}
    for path, cfg in routes_cfg.items():
        starters = []
        for sid in cfg['starter_ids']:
            slug = by_id.get(sid)
            if not slug:
                warn(f'{path}: starter {sid} not among shipped questions - dropped')
                continue
            starters.append(slug)
        routes[path] = {
            'intro': cfg['intro'],
            'title': cfg['title'],
            'launcherLabel': cfg['launcherLabel'],
            'starters': starters,
        }

        # 3c: follow-ups resolve PER PAGE. A shared question can list follow-ups
        # that only exist on one of its pages; those must not render on the
        # other. Resolved here rather than in the widget - the widget already
        # receives everything else per route and stays a renderer, and doing it
        # here leaves the result visible in answers.json, so a shortened list
        # shows up in a diff and in the git history instead of being an
        # invisible runtime decision.
        #
        # Emitted ONLY for questions whose list actually differs on this page.
        # With no multi-page questions nothing differs, the key is absent, and
        # the artifact is byte-identical to before this feature existed.
        mine = page_slugs.get(path, set())
        per_page = {}
        for slug in sorted(mine):
            full = questions[slug]['followups']
            here = [f for f in full if f in mine]
            if here != full:
                per_page[slug] = here
        if per_page:
            routes[path]['followups'] = per_page
            say(f'  {path}: {len(per_page)} question(s) with a page-specific '
                f'follow-up list')

        # The handoff line. A blank cell resolved to END_OF_QUESTIONS_FALLBACK
        # up in read_placement, and that is exactly what the widget says on its
        # own - so writing it would change every route for no behaviour change.
        # Emitted only when the Sheet actually says something different.
        if cfg['endOfQuestions'] != END_OF_QUESTIONS_FALLBACK:
            routes[path]['endOfQuestions'] = cfg['endOfQuestions']

    today = datetime.date.today().isoformat()
    doc = {
        '_editorNote': (
            f'Generated by publish.py from grace-assistant-corpus Sheet {today}. '
            f'Pilot routes {", ".join(PILOT_ROUTES)}; statuses shipped: '
            f'{"/".join(sorted(SHIP_STATUSES))} (HOLD always excluded). '
            f'{TALK_PERSON_SLUG} appended to every question at generation. '
            'Per-route title/launcherLabel/intro overrides. Do not hand-edit: '
            'edit the Sheet and re-run publish.py.'
        ),
        'meta': dict(GLOBAL_META),
        'routes': routes,
        'questions': questions,
    }
    return doc, page_slugs


# ---------------------------------------------------------------------------
# VALIDATE
# ---------------------------------------------------------------------------

def validate(doc, page_slugs):
    problems = []
    qs, routes = doc['questions'], doc['routes']

    for slug, q in qs.items():
        if not q.get('answer') or not any(p.strip() for p in q['answer']):
            problems.append(f'{slug}: empty answer')
        for f in q.get('followups', []):
            if f not in qs:
                problems.append(f'{slug}: followup {f!r} does not resolve')
            if f == slug:
                problems.append(f'{slug}: lists itself as a followup')
        for link in q.get('links', []):
            href = link.get('href', '')
            if not (href.startswith('/') or re.match(r'^https?://', href) or href.startswith('tel:')):
                problems.append(f'{slug}: link href {href!r} outside whitelist (/ http tel:)')

    for path, r in routes.items():
        if not r['starters']:
            problems.append(f'{path}: no starters resolved')
        for s in r['starters']:
            if s not in qs:
                problems.append(f'{path}: starter {s!r} does not resolve')

    # policy: watch-online is starter-only, never a followup
    offenders = [s for s, q in qs.items() if 'watch-online' in q.get('followups', [])]
    if offenders:
        problems.append(f'watch-online appears as a followup on: {offenders}')

    # BFS reachability per route. `expected` is derived from the ANSWERS Page
    # column, NOT from the follow-up graph, so a question that no starter can
    # reach fails here instead of quietly defining itself as reachable.
    for path, r in routes.items():
        expected = set(page_slugs.get(path, set()))
        # Walk the SAME follow-up lists the widget will be given on this page,
        # not the unfiltered ones - otherwise the validator blesses a graph that
        # is not the one that ships. The rule itself is unchanged: every question
        # the Page columns assign to this page must still be reachable from this
        # page's starters, and nothing else may be.
        per_page = r.get('followups', {})
        seen, queue = set(r['starters']), list(r['starters'])
        while queue:
            current = queue.pop(0)
            for f in per_page.get(current, qs.get(current, {}).get('followups', [])):
                if f not in seen:
                    seen.add(f)
                    queue.append(f)
        reached = seen - {TALK_PERSON_SLUG}      # ships on every page by design
        unreached = expected - reached
        unexpected = reached - expected
        say(f'  BFS {path}: expected {len(expected)} from Page column, '
            f'reached {len(reached)} -> {sorted(reached)}')
        if unreached:
            problems.append(f'{path}: questions on this page unreachable from its '
                            f'starters: {sorted(unreached)}')
        if unexpected:
            problems.append(f'{path}: reaches questions belonging to another page: '
                            f'{sorted(unexpected)}')

    if problems:
        die(problems)
    say('  validation: PASS')


# ---------------------------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------------------------

def dump(doc, path):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write('\n')


def _without_editor_note(lines, label):
    """Drop the _editorNote line from a JSON dump for comparison purposes.

    _editorNote carries today's date, so it differs on the first run after every
    UTC midnight even when no content changed. Including it in the changed-vs-
    unchanged decision produced a nightly no-op deploy, a junk auto-publish
    commit, and a "Grace published" push - see PUBLISHING.md, 2026-08-29 00:18Z.
    It is metadata about the build, not content a guest can see, so it is
    excluded from the comparison on BOTH sides. It is still written to the
    artifact, so a real deploy always ships a fresh one.

    This filter is LINE-BASED and therefore coupled to dump() writing the
    artifact with indent=2, which puts _editorNote on exactly one line. If the
    dump were ever changed to compact JSON the whole document would be one line
    containing "_editorNote", the filter would drop everything, every run would
    compare empty-to-empty and report nochange, and deploys would stop silently.
    The two invariants below turn that into a loud failure instead: an
    unhandled raise fails the run, which reaches the existing high-priority
    failure notification. There is deliberately NO fallback to an unfiltered
    compare - a wrong-but-quiet answer is what we are defending against.
    """
    kept = [l for l in lines if '"_editorNote"' not in l]
    dropped = len(lines) - len(kept)
    if dropped > 1:
        raise RuntimeError(
            f'_editorNote filter dropped {dropped} lines from {label} (expected at '
            'most 1). The filter is line-based and assumes dump() uses indent=2 so '
            '_editorNote occupies one line. Did the artifact formatting change?')
    if lines and not kept:
        raise RuntimeError(
            f'_editorNote filter emptied {label} ({len(lines)} line(s) in, 0 out). '
            'The artifact is probably compact JSON on a single line; the filter is '
            'line-based and assumes dump() uses indent=2. Refusing to compare '
            'empty-to-empty, which would report nochange forever and stop deploys.')
    return kept


def count_changes(old_path, new_doc):
    """How many distinct things this publish alters, for the RESULT line.

    `changed` used to be hardcoded to 1 - a flag wearing a count's name, so a
    publish that rewrote six answers and a publish that fixed one typo both
    reported changed=1. The field is in the ntfy body, so that number is what a
    reader sees at 2am; it should mean something.

    One unit = one question added, removed or edited, one route whose config
    differs, or the meta block. _editorNote is excluded, exactly as it is from
    the unified() gate that decides whether to deploy at all - so any publish
    that gets this far counts at least 1, and changed=0 is unreachable.
    """
    if not os.path.exists(old_path):
        return len(new_doc.get('questions', {})) + len(new_doc.get('routes', {})) + 1
    old = json.load(open(old_path, encoding='utf-8'))
    oq, nq = old.get('questions', {}), new_doc.get('questions', {})
    n = sum(1 for slug in set(oq) | set(nq) if oq.get(slug) != nq.get(slug))
    orte, nrte = old.get('routes', {}), new_doc.get('routes', {})
    n += sum(1 for path in set(orte) | set(nrte) if orte.get(path) != nrte.get(path))
    if old.get('meta') != new_doc.get('meta'):
        n += 1
    return n


def unified(old_path, new_path, ignore_editor_note=True):
    old = open(old_path, encoding='utf-8').read().splitlines(keepends=True) if os.path.exists(old_path) else []
    new = open(new_path, encoding='utf-8').read().splitlines(keepends=True)
    if ignore_editor_note:
        old = _without_editor_note(old, old_path)
        new = _without_editor_note(new, new_path)
    return list(difflib.unified_diff(old, new, fromfile=old_path, tofile=new_path, n=2))


def semantic(old_path, new_doc):
    if not os.path.exists(old_path):
        say('  (no current public/answers.json to compare)')
        return
    old = json.load(open(old_path, encoding='utf-8'))
    oq, nq = old.get('questions', {}), new_doc['questions']
    for slug in sorted(set(oq) | set(nq)):
        if slug not in oq:
            print(f'  + {slug}: NEW question'); continue
        if slug not in nq:
            print(f'  - {slug}: REMOVED'); continue
        for field in ('label', 'answer', 'links', 'followups'):
            a, b = oq[slug].get(field), nq[slug].get(field)
            if a != b:
                print(f'  ~ {slug}.{field}')
                print(f'      was: {json.dumps(a, ensure_ascii=False)}')
                print(f'      now: {json.dumps(b, ensure_ascii=False)}')
    for path in sorted(set(old.get('routes', {})) | set(new_doc['routes'])):
        a, b = old.get('routes', {}).get(path), new_doc['routes'].get(path)
        if a != b:
            for k in sorted(set(a or {}) | set(b or {})):
                if (a or {}).get(k) != (b or {}).get(k):
                    print(f'  ~ route {path}.{k}')
                    print(f'      was: {json.dumps((a or {}).get(k), ensure_ascii=False)}')
                    print(f'      now: {json.dumps((b or {}).get(k), ensure_ascii=False)}')
    if old.get('meta') != new_doc['meta']:
        print(f'  ~ meta changed')
    if old.get('_editorNote') != new_doc['_editorNote']:
        print('  ~ _editorNote regenerated (expected every run - carries the date)')


def deploy():
    import shutil
    shutil.copyfile(OUT_BUILD, OUT_PUBLIC)
    say(f'  copied {OUT_BUILD} -> {OUT_PUBLIC}')
    subprocess.run(['npx', 'wrangler', 'pages', 'deploy', 'public',
                    '--project-name', PAGES_PROJECT, '--branch', 'main'], check=True)
    local = hashlib.md5(open(OUT_PUBLIC, 'rb').read()).hexdigest()
    say(f'  local md5 {local}')
    # Cloudflare 403s urllib's default User-Agent, so shell out to curl - which
    # is also what we verify by hand. Two checks: the edge can serve a stale copy
    # for a beat after a deploy, and one probe has given a false negative before.
    for attempt in (1, 2):
        time.sleep(3)
        url = f'{LIVE_JSON}?cb={int(time.time())}{attempt}'
        body = subprocess.run(['curl', '-s', '--max-time', '30', url],
                              capture_output=True).stdout
        live = hashlib.md5(body).hexdigest()
        text = body.decode('utf-8', 'replace')
        say(f'  live md5 check {attempt}: {live}  match={live == local}')
        say(f"     panel title present: {'Grace' in text}")


def main():
    global QUIET
    ap = argparse.ArgumentParser()
    ap.add_argument('--deploy', action='store_true',
                    help='copy to public/ and ship (default is dry run)')
    ap.add_argument('--min-quiet-minutes', type=int, default=0, metavar='N',
                    help='skip the run if the Sheet was edited less than N minutes '
                         'ago, so a half-finished edit never ships')
    ap.add_argument('--quiet', action='store_true',
                    help='machine-readable summary lines only')
    args = ap.parse_args()
    QUIET = args.quiet

    if args.min_quiet_minutes > 0:
        try:
            idle = sheet_modified_minutes_ago()
        except Exception as exc:
            # Never print the exception body verbatim - Google error payloads can
            # echo request context. Type name only.
            print(f'ERROR could not read Sheet modifiedTime ({type(exc).__name__}) - '
                  'Drive API enabled? drive.metadata.readonly scope granted?')
            result(status='quiescence_check_failed')
            sys.exit(3)
        if idle < args.min_quiet_minutes:
            say(f'Sheet edited {idle:.0f}m ago - debounce, skipping')
            result(status='debounced', idle_minutes=round(idle),
                   threshold_minutes=args.min_quiet_minutes)
            sys.exit(0)
        say(f'Sheet last edited {idle:.0f}m ago - past the {args.min_quiet_minutes}m '
            'debounce, proceeding')

    say('reading Sheet...')
    doc, page_slugs = build(open_sheet())
    say('validating...')
    validate(doc, page_slugs)
    dump(doc, OUT_BUILD)
    say(f'wrote {OUT_BUILD}')

    diff = unified(OUT_PUBLIC, OUT_BUILD)
    say('\n=== UNIFIED DIFF vs public/answers.json ===')
    say(''.join(diff) if diff else '  (identical)')
    say('=== SEMANTIC DIFF (per question) ===')
    if not QUIET:
        semantic(OUT_PUBLIC, doc)
    say(f'\nwarnings: {len(WARNINGS)}')

    if not diff:
        result(status='nochange', questions=len(doc['questions']),
               warnings=len(WARNINGS))
        if not args.deploy:
            say('\ndry run - public/ untouched, nothing deployed.')
        return

    changed = count_changes(OUT_PUBLIC, doc)

    if args.deploy:
        say('\n=== DEPLOYING ===')
        deploy()
        result(status='deployed', questions=len(doc['questions']),
               warnings=len(WARNINGS), changed=changed)
    else:
        result(status='would_change', questions=len(doc['questions']),
               warnings=len(WARNINGS), changed=changed)
        say('\ndry run - public/ untouched, nothing deployed. Use --deploy to ship.')


if __name__ == '__main__':
    main()
