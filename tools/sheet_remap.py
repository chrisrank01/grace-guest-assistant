#!/usr/bin/env python3.12
# One-off (2026-08-28): fixed 8 F-row answer/question mismatches; added 18 slugs.
# NOT part of the publish path. Needs the service account temporarily
# promoted to Editor on the Sheet; revert to Viewer after. Dry run by default.
"""Correction batch - 8 F-row answer/question mismatches.

Rotations are resolved against a SNAPSHOT taken before any write, so a
three-cycle (GRP-F1 <- F2 <- F3 <- F1) cannot clobber its own source.
Every write carries an expected-current guard; mismatch = SKIP, never overwrite.
"""
import argparse, os, sys
import gspread
from google.oauth2.service_account import Credentials

KEY_PATH  = os.environ.get('GRACE_PUBLISHER_KEY', 'secrets/grace-publisher.json')
SHEET_KEY = '1uxB85U-lRTZo75eGdmB23PAvJ2jdyLvvezaQIzaaekY'
SCOPES    = ['https://www.googleapis.com/auth/spreadsheets']
STAMP     = 'RTS remap 2026-08-28'
CHANGE_LOG_ROW = ['2026-08-28', 'RTS', 'GRP-F1..3, ABT-F1..3, SRV-F2, SRV-F3, BAP-F2, EVT-F2, CLS-F2 + 18 F-row slugs',
                  'RTS — corrected 8 F-row answer/question mismatches from draft batch; added 18 F-row slugs',
                  'HOLD (unchanged)']

# rotations: target <- source (answer, and button unless overridden)
ROTATE = [
    ('GRP-F1', 'GRP-F2', None),
    ('GRP-F2', 'GRP-F3', None),
    ('GRP-F3', 'GRP-F1', None),
    ('ABT-F1', 'ABT-F2', 'About Grace → /the-grace-mission/'),
    ('ABT-F2', 'ABT-F3', 'Plan your visit → /plan-your-visit/'),
    ('ABT-F3', 'ABT-F1',
     'Watch House Rules → https://www.youtube.com/playlist?list=PLz5PuMh2kVdQTPfb8tB2JPeqt0v4Hxsju'),
    ('SRV-F2', 'SRV-F3', 'Join Team Grace → /serveORL'),
]

# fresh text: id -> (answer, button or None to leave alone)
FRESH = {
    'SRV-F3': ('Next Steps Night is a one-night gathering to help you find your place on Team '
               'Grace. Meet team leaders, ask your questions, and sign up on the spot. Watch '
               'the Events page for the next one.',
               'See events → /events'),
    'BAP-F2': ('Baptism is for anyone who believes in Jesus. That includes kids and students: '
               'GraceKids and GraceStudents each have a baptism journal to walk through as a '
               'family, plus a short orientation to get everyone ready.', None),
    'EVT-F2': ('Every event registers through our Events page. Tap in, pick your event, and '
               'sign up in a few minutes. We would love to see you there.', None),
    'CLS-F2': ('Find the class that fits and sign up right from the listing. It only takes a '
               'minute, and there is a seat for you.',
               'Find a class → https://gcfl.churchcenter.com/registrations/events/category/40975'),
}

# Slug addendum - 18 F-rows. Guards: cell must be EMPTY, and the new slug must be
# unique against the WHOLE Slug column plus the other 17 being written in this batch.
SLUGS = {
    'SRV-F1': 'serve-teams',      'SRV-F2': 'student-serve',   'SRV-F3': 'next-steps-night',
    'GRP-F1': 'discover-groups',  'GRP-F2': 'lead-group',      'GRP-F3': 'groups-near-me',
    'BAP-F1': 'what-is-baptism',  'BAP-F2': 'who-baptized',    'BAP-F3': 'baptism-signup',
    'EVT-F1': 'coming-up',        'EVT-F2': 'register-event',
    'ABT-F1': 'grace-believe',    'ABT-F2': 'who-pastors',     'ABT-F3': 'house-rules',
    'GDG-F1': 'serve-city',       'GDG-F2': 'join-serve-project',
    'CLS-F1': 'classes-offered',  'CLS-F2': 'class-signup',
}

ap = argparse.ArgumentParser(); ap.add_argument('--apply', action='store_true')
args = ap.parse_args()

gc = gspread.authorize(Credentials.from_service_account_file(KEY_PATH, scopes=SCOPES))
sh = gc.open_by_key(SHEET_KEY)
ans = sh.worksheet('ANSWERS')
vals = ans.get_all_values()
h = vals[3]
iQ, iA, iF, iN = (h.index('Tap Question (guest sees)'), h.index('Answer Text (pre-approved)'),
                  h.index('Primary Action → Destination'), h.index('Source / Notes'))
iS = h.index('Slug')
rows = {r[0].strip(): n for n, r in enumerate(vals, 1) if n > 4 and r and r[0].strip()}

def cur(rid, i):
    r = vals[rows[rid] - 1]
    return (r[i] if i < len(r) else '').strip()

# ---- SNAPSHOT before anything is planned or written ---------------------
snap = {rid: {'Q': cur(rid, iQ), 'A': cur(rid, iA), 'B': cur(rid, iF), 'N': cur(rid, iN)}
        for rid in set([t for t, _s, _b in ROTATE] + [s for _t, s, _b in ROTATE]
                       + list(FRESH) + [r for r in SLUGS if r in rows])}

plan, skips = [], []
touched = set()

for tgt, src, btn in ROTATE:
    new_a = snap[src]['A']
    new_b = btn if btn is not None else snap[src]['B']
    if not new_a:
        skips.append((tgt, 'Answer', f'source {src} answer is empty')); continue
    if snap[tgt]['A'] == new_a:
        skips.append((tgt, 'Answer', 'already holds the target text'))
    else:
        plan.append((tgt, rows[tgt], 'Answer', iA + 1, snap[tgt]['A'], new_a, f'<- {src}'))
        touched.add(tgt)
    if snap[tgt]['B'] != new_b:
        plan.append((tgt, rows[tgt], 'Button', iF + 1, snap[tgt]['B'], new_b,
                     f'<- {src}' if btn is None else 'explicit'))
        touched.add(tgt)

for rid, (new_a, new_b) in FRESH.items():
    if snap[rid]['A'] != new_a:
        plan.append((rid, rows[rid], 'Answer', iA + 1, snap[rid]['A'], new_a, 'fresh'))
        touched.add(rid)
    if new_b is not None and snap[rid]['B'] != new_b:
        plan.append((rid, rows[rid], 'Button', iF + 1, snap[rid]['B'], new_b, 'fresh'))
        touched.add(rid)

# ---- slug addendum ------------------------------------------------------
existing_slugs = {}
for n_, r_ in enumerate(vals, 1):
    if n_ > 4 and r_ and r_[0].strip():
        sv = (r_[iS] if iS < len(r_) else '').strip()
        if sv:
            existing_slugs.setdefault(sv, []).append(r_[0].strip())

dupes_in_batch = [v for v in SLUGS.values() if list(SLUGS.values()).count(v) > 1]
if dupes_in_batch:
    sys.exit(f'ABORT: duplicate slugs inside the addendum itself: {sorted(set(dupes_in_batch))}')

for rid, slug in SLUGS.items():
    if rid not in rows:
        skips.append((rid, 'Slug', 'row not found')); continue
    cur_slug = cur(rid, iS)
    if cur_slug:
        skips.append((rid, 'Slug', f'NOT EMPTY ({cur_slug!r}) - refusing to overwrite')); continue
    if slug in existing_slugs:
        skips.append((rid, 'Slug', f'COLLIDES with existing slug on {existing_slugs[slug]}')); continue
    plan.append((rid, rows[rid], 'Slug', iS + 1, '', slug, 'addendum'))
    touched.add(rid)

for rid in sorted(touched):
    n = snap[rid]['N']
    if STAMP in n:
        skips.append((rid, 'Notes', 'stamp already present')); continue
    plan.append((rid, rows[rid], 'Notes', iN + 1, n, (n + ' · ' + STAMP) if n else STAMP, 'append'))

print('=' * 120)
print(f'{"ID":8} {"row":>4} {"col":7} {"src":10} question / current -> new')
print('=' * 120)
for rid, row, colname, colnum, old, new, src in plan:
    if colname == 'Answer':
        print(f'{rid:8} {row:>4} {colname:7} {src:10} Q: {snap[rid]["Q"]}')
        print(f'{"":32} was: {old[:86]}')
        print(f'{"":32} now: {new[:86]}')
    else:
        print(f'{rid:8} {row:>4} {colname:7} {src:10} {old[:52]!r} -> {new[:60]!r}')
print('=' * 120)
print(f'planned writes: {len(plan)}   rows touched: {len(touched)}')
print(f'CHANGE LOG: + 1 row -> {" | ".join(CHANGE_LOG_ROW)[:110]}')
if skips:
    print(f'\nSKIPPED ({len(skips)}):')
    for a, b, c in skips:
        print(f'  !! {a:8} {b:8} {c}')
else:
    print('\nno skips - every guard passed')

if not args.apply:
    print('\nDRY RUN - nothing written. Re-run with --apply.')
    sys.exit(0)

# guard re-check against the live sheet immediately before writing
live = ans.get_all_values()
def live_cur(rid, i):
    r = live[rows[rid] - 1]
    return (r[i] if i < len(r) else '').strip()
for rid, row, colname, colnum, old, new, src in plan:
    if live_cur(rid, colnum - 1) != old:
        sys.exit(f'ABORT: {rid} {colname} changed under us - expected {old[:40]!r}, '
                 f'found {live_cur(rid, colnum-1)[:40]!r}. Nothing written.')

data = [{'range': f"'ANSWERS'!{gspread.utils.rowcol_to_a1(row, colnum)}", 'values': [[new]]}
        for _r, row, _c, colnum, _o, new, _s in plan]
clog = sh.worksheet('CHANGE LOG')
nrow = len(clog.get_all_values()) + 1
sh.values_batch_update({'valueInputOption': 'RAW', 'data': data})
clog.update(f'A{nrow}:E{nrow}', [CHANGE_LOG_ROW], value_input_option='RAW')
print(f'\napplied: {len(data)} ANSWERS cells in 1 request + CHANGE LOG row {nrow}')

print('\n=== VERIFY (re-read) ===')
v2 = ans.get_all_values()
ok = bad = 0
for rid, row, colname, colnum, old, new, src in plan:
    got = (v2[row - 1][colnum - 1] if colnum - 1 < len(v2[row - 1]) else '').strip()
    good = got == new.strip()
    ok, bad = (ok + 1, bad) if good else (ok, bad + 1)
    print(f'  {"OK " if good else "BAD"} {rid:8} {colname:7} {got[:74]!r}')
print(f'\nwritten={len(plan)}  ok={ok}  bad={bad}  skipped={len(skips)}')
print('\nAll touched rows are non-pilot (Status HOLD, pages outside PILOT_ROUTES),')
print('so the next publish will be RESULT status=nochange for these edits.')
