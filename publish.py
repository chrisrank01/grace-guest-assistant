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
    'title': 'GraceGuide',
    'launcherLabel': 'Have a question? Tap here',
    'startersLabel': 'Common questions',
    'followupsLabel': 'People also ask',
    'footerHint': 'Tap a question to see the answer.',
    'restartLabel': 'Start over',
    'homeLabel': 'Back to the main questions',
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

HEADER_ROW = 4          # 1-indexed; data starts at row 5
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
OUT_BUILD = 'build/answers.json'
OUT_PUBLIC = 'public/answers.json'
PAGES_PROJECT = 'grace-assistant'
LIVE_URL = 'https://grace-assistant.pages.dev/grace-assistant.js'
LIVE_JSON = 'https://grace-assistant.pages.dev/answers.json'

WARNINGS = []


def warn(msg):
    WARNINGS.append(msg)
    print(f'  WARN  {msg}')


def die(problems):
    print('\nVALIDATION FAILED - nothing written\n')
    for p in problems:
        print(f'  - {p}')
    sys.exit(2)


# ---------------------------------------------------------------------------
# READ
# ---------------------------------------------------------------------------

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


def read_placement(sh):
    """SHOW rows whose URL path is in PILOT_ROUTES -> route config."""
    header, rows = tabulate(sh.worksheet('PLACEMENT').get_all_values())
    lower = {h.strip().lower(): h for h in header if h.strip()}
    # optional, absent today - present-tense support so the Sheet can drive these later
    col_title = lower.get('panel title')
    col_launch = lower.get('launcher label')
    col_intro = lower.get('intro')

    routes = {}
    for row in rows:
        path = row.get('URL path', '').strip()
        show = row.get('Show / Hide', '').strip().upper()
        if show != 'SHOW' or path not in PILOT_ROUTES:
            continue
        fallback = ROUTE_META_FALLBACK.get(path, {})
        routes[path] = {
            'page': row.get(COL_PAGE, '').strip(),
            'starter_ids': [s.strip() for s in row.get('Starter question IDs (3–5)', '').split(',') if s.strip()],
            'title': (row.get(col_title) or '').strip() or fallback.get('title'),
            'launcherLabel': (row.get(col_launch) or '').strip() or fallback.get('launcherLabel'),
            'intro': (row.get(col_intro) or '').strip() or fallback.get('intro'),
        }
    if col_title or col_launch or col_intro:
        print('  PLACEMENT supplies route meta columns; Sheet values win over fallback')
    else:
        print('  PLACEMENT has no route-meta columns; using ROUTE_META_FALLBACK')
    return routes


# ---------------------------------------------------------------------------
# TRANSFORM
# ---------------------------------------------------------------------------

def parse_link(raw, slug):
    """'Label -> /path' -> {label, href}, or None (with a warning) if the
    destination is prose rather than somewhere a browser can go."""
    raw = (raw or '').strip()
    if not raw:
        return None
    if slug == TALK_PERSON_SLUG:                      # 'Call 407-418-1300'
        digits = re.sub(r'\D', '', raw)
        if len(digits) == 10:
            return {'label': raw, 'href': f'tel:+1{digits}'}
        warn(f'{slug}: phone link not parseable from {raw!r} - link dropped')
        return None
    if '→' not in raw:
        warn(f'{slug}: link {raw!r} has no destination - link dropped')
        return None
    label, dest = (p.strip() for p in raw.split('→', 1))
    if dest.startswith('/') or re.match(r'^https?://', dest) or dest.startswith('tel:'):
        return {'label': label, 'href': dest}
    warn(f'{slug}: destination {dest!r} is not a path/URL/tel - link dropped')
    return None


def build(sh):
    routes_cfg = read_placement(sh)
    if not routes_cfg:
        die(['PLACEMENT has no SHOW rows matching PILOT_ROUTES'])

    # Page -> route path, derived from PLACEMENT rather than hardcoded names
    page_to_route = {cfg['page']: path for path, cfg in routes_cfg.items()}
    print(f'  pilot pages from PLACEMENT: {page_to_route}')

    _, rows = tabulate(sh.worksheet('ANSWERS').get_all_values())

    questions, by_id, drafts, skipped = {}, {}, 0, 0
    page_slugs = {}
    for row in rows:
        rid, slug = row.get(COL_ID, ''), row.get(COL_SLUG, '')
        page, status = row.get(COL_PAGE, ''), row.get(COL_STATUS, '').upper()
        question, answer = row.get(COL_Q, ''), row.get(COL_A, '')

        in_scope = page in page_to_route or slug == TALK_PERSON_SLUG
        if not in_scope:
            skipped += 1
            continue
        if status not in SHIP_STATUSES:
            warn(f'{rid} ({slug}): status {status or "(blank)"} - not shipped')
            continue
        if not (slug and question and answer):
            warn(f'{rid}: missing slug/question/answer - not shipped')
            continue
        if slug in questions:
            die([f'duplicate slug {slug!r} (second occurrence at {rid})'])

        if status == 'DRAFT':
            drafts += 1
        entry = {'label': question, 'answer': [p.strip() for p in answer.split('\n\n') if p.strip()]}
        link = parse_link(row.get(COL_LINK, ''), slug)
        if link:
            entry['links'] = [link]
        entry['_followups_raw'] = [s.strip() for s in row.get(COL_FOLLOWUPS, '').split(',') if s.strip()]
        questions[slug] = entry
        by_id[rid] = slug
        # Expected membership comes from the Page column, independent of the
        # follow-up graph - that is what lets the BFS check below actually fail.
        if page in page_to_route:
            page_slugs.setdefault(page_to_route[page], set()).add(slug)

    print(f'  in scope: {len(questions)} questions   out of scope: {skipped} rows')
    if drafts:
        warn(f'{drafts} DRAFT row(s) shipped - SHIP_STATUSES currently allows DRAFT')

    # followups: sheet order, then talk-person appended everywhere but itself
    for slug, entry in questions.items():
        fus = [f for f in entry.pop('_followups_raw')]
        if slug != TALK_PERSON_SLUG:
            if TALK_PERSON_SLUG not in fus:
                fus.append(TALK_PERSON_SLUG)
        else:
            fus = []
        entry['followups'] = fus

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
        seen, queue = set(r['starters']), list(r['starters'])
        while queue:
            for f in qs.get(queue.pop(0), {}).get('followups', []):
                if f not in seen:
                    seen.add(f)
                    queue.append(f)
        reached = seen - {TALK_PERSON_SLUG}      # ships on every page by design
        unreached = expected - reached
        unexpected = reached - expected
        print(f'  BFS {path}: expected {len(expected)} from Page column, '
              f'reached {len(reached)} -> {sorted(reached)}')
        if unreached:
            problems.append(f'{path}: questions on this page unreachable from its '
                            f'starters: {sorted(unreached)}')
        if unexpected:
            problems.append(f'{path}: reaches questions belonging to another page: '
                            f'{sorted(unexpected)}')

    if problems:
        die(problems)
    print('  validation: PASS')


# ---------------------------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------------------------

def dump(doc, path):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write('\n')


def unified(old_path, new_path):
    old = open(old_path, encoding='utf-8').read().splitlines(keepends=True) if os.path.exists(old_path) else []
    new = open(new_path, encoding='utf-8').read().splitlines(keepends=True)
    return list(difflib.unified_diff(old, new, fromfile=old_path, tofile=new_path, n=2))


def semantic(old_path, new_doc):
    if not os.path.exists(old_path):
        print('  (no current public/answers.json to compare)')
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
    print(f'  copied {OUT_BUILD} -> {OUT_PUBLIC}')
    subprocess.run(['npx', 'wrangler', 'pages', 'deploy', 'public',
                    '--project-name', PAGES_PROJECT, '--branch', 'main'], check=True)
    local = hashlib.md5(open(OUT_PUBLIC, 'rb').read()).hexdigest()
    print(f'  local md5 {local}')
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
        print(f'  live md5 check {attempt}: {live}  match={live == local}')
        print(f"     'GraceGuide' present: {'GraceGuide' in text}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--deploy', action='store_true',
                    help='copy to public/ and ship (default is dry run)')
    args = ap.parse_args()

    print('reading Sheet...')
    doc, page_slugs = build(open_sheet())
    print('validating...')
    validate(doc, page_slugs)
    dump(doc, OUT_BUILD)
    print(f'wrote {OUT_BUILD}')

    print('\n=== UNIFIED DIFF vs public/answers.json ===')
    diff = unified(OUT_PUBLIC, OUT_BUILD)
    print(''.join(diff) if diff else '  (identical)')

    print('=== SEMANTIC DIFF (per question) ===')
    semantic(OUT_PUBLIC, doc)

    print(f'\nwarnings: {len(WARNINGS)}')
    if args.deploy:
        print('\n=== DEPLOYING ===')
        deploy()
    else:
        print('\ndry run - public/ untouched, nothing deployed. Use --deploy to ship.')


if __name__ == '__main__':
    main()
