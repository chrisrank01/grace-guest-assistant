#!/usr/bin/env python3.12
# One-off (2026-08-28): PLACEMENT URL-path corrections + two new SHOW rows.
# NOT part of the publish path. Needs the service account temporarily
# promoted to Editor on the Sheet; revert to Viewer after. Dry run by default.
"""Amendment F - PLACEMENT tab: two URL-path corrections + two new SHOW rows.

Order matters. The URL path column now carries a STRICT ONE_OF_LIST rule whose
allowed set was frozen from the pre-amendment values, so the four new paths are
rejected until the rule is widened. This script widens the rule first, then writes.
"""
import argparse, os, sys, json
import gspread
from google.oauth2.service_account import Credentials

KEY_PATH  = os.environ.get('GRACE_PUBLISHER_KEY', 'secrets/grace-publisher.json')
SHEET_KEY = '1uxB85U-lRTZo75eGdmB23PAvJ2jdyLvvezaQIzaaekY'
SCOPES    = ['https://www.googleapis.com/auth/spreadsheets']
FIRST, LAST = 5, 300

# (page name guard, column, expected-old, new value)
EDITS = [
    ('About Grace', 'URL path', '/our-church/',  '/the-grace-mission/'),
    ('Baptism',     'URL path', '/baptism/',     '/baptism-main/'),
]
NEW_ROWS = [
    ['Classes', '/semester-sessions/', 'SHOW (when CLS-F written)',
     'CLS-F1, CLS-F2, NXT-04', 'Turn on once FUTURE rows are APPROVED.'],
    ['Grace Does Good', '/grace-does-good/', 'SHOW (when GDG-F written)',
     'GDG-F1, GDG-F2, NXT-03', 'Turn on once FUTURE rows are APPROVED.'],
]
DIVIDER_MARK = 'HIDE below'

ap = argparse.ArgumentParser(); ap.add_argument('--apply', action='store_true')
args = ap.parse_args()

gc = gspread.authorize(Credentials.from_service_account_file(KEY_PATH, scopes=SCOPES))
sh = gc.open_by_key(SHEET_KEY)
ws = sh.worksheet('PLACEMENT')
vals = ws.get_all_values()
hdr = vals[3]
ci = {name: i for i, name in enumerate(hdr)}

rows = {r[0].strip(): n for n, r in enumerate(vals, 1) if n > 4 and r and r[0].strip()}
divider = next((n for n, r in enumerate(vals, 1) if r and DIVIDER_MARK in (r[0] or '')), None)
if not divider:
    sys.exit('divider row not found - refusing to guess an insert point')

plan, skips = [], []
for page, colname, old, new in EDITS:
    r = rows.get(page)
    if not r:
        skips.append((page, colname, 'row not found')); continue
    cur = vals[r - 1][ci[colname]] if ci[colname] < len(vals[r - 1]) else ''
    if cur.strip() != old:
        skips.append((page, colname, f'guard failed: expected {old!r}, found {cur.strip()!r}'))
        continue
    plan.append((page, r, colname, cur.strip(), new))

# new paths that the frozen validation list would reject
new_paths = [n for _p, _r, _c, _o, n in plan] + [r[1] for r in NEW_ROWS]

print('=' * 104)
print(f'{"row":>4}  {"page":18} {"col":10} {"current":22} -> new')
print('=' * 104)
for page, r, colname, cur, new in plan:
    print(f'{r:>4}  {page:18} {colname:10} {cur!r:22} -> {new!r}')
print()
print(f'INSERT 2 rows at row {divider} (above the "{DIVIDER_MARK}" divider, pushing it down):')
for nr in NEW_ROWS:
    print(f'      {" | ".join(nr)}')
print('=' * 104)
print(f'validation list must gain: {new_paths}')
if skips:
    print(f'\nSKIPPED ({len(skips)}):')
    for a, b, c in skips:
        print(f'  !! {a:18} {b:10} {c}')
else:
    print('\nno skips - every guard passed')

if not args.apply:
    print('\nDRY RUN - nothing written. Re-run with --apply.')
    sys.exit(0)

# ---- 1. widen the URL path validation BEFORE writing new paths ----------
url_i = ci['URL path']
existing = sorted({(r[url_i].strip() if url_i < len(r) else '')
                   for r in vals[FIRST - 1:] if r and r[0].strip()} - {''})
allowed = sorted(set(existing) | set(new_paths))
sh.batch_update({'requests': [{'setDataValidation': {
    'range': {'sheetId': ws.id, 'startRowIndex': FIRST - 1, 'endRowIndex': LAST,
              'startColumnIndex': url_i, 'endColumnIndex': url_i + 1},
    'rule': {'condition': {'type': 'ONE_OF_LIST',
                           'values': [{'userEnteredValue': v} for v in allowed]},
             'strict': True, 'showCustomUi': True,
             'inputMessage': 'Existing paths only. Adding a new page? Extend this list first.'}}}]})
print(f'\nvalidation widened to {len(allowed)} values (was {len(existing)})')

# ---- 2. the two corrections --------------------------------------------
for page, r, colname, cur, new in plan:
    ws.update_acell(gspread.utils.rowcol_to_a1(r, ci[colname] + 1), new)
    print(f'  wrote {page} {colname} -> {new}')

# ---- 3. insert the two new rows above the divider ----------------------
ws.insert_rows(NEW_ROWS, row=divider)
print(f'  inserted 2 rows at {divider}')

# ---- verify -------------------------------------------------------------
print('\n=== VERIFY (re-read) ===')
v2 = ws.get_all_values()
for n, r in enumerate(v2, 1):
    if n < 4:
        continue
    if r and (r[0].strip() in ('About Grace', 'Baptism', 'Classes', 'Grace Does Good')
              or DIVIDER_MARK in (r[0] or '')):
        print(f'  {n:>2}: {" | ".join(c[:34] for c in r[:5])}')
dv = gc.http_client.request('get',
    f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_KEY}'
    f'?ranges=PLACEMENT!{chr(65+url_i)}{FIRST}:{chr(65+url_i)}{FIRST}'
    '&fields=sheets(data(rowData(values(dataValidation))))').json()
try:
    d = dv['sheets'][0]['data'][0]['rowData'][0]['values'][0]['dataValidation']
    got = [x['userEnteredValue'] for x in d['condition']['values']]
    print(f'\nURL path rule: strict={d.get("strict")} n={len(got)}')
    for p in new_paths:
        print(f'   {p!r} in list: {p in got}')
except (KeyError, IndexError):
    print('\ncould not read validation back')
