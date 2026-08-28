#!/usr/bin/env python3.12
# One-off (2026-08-28): normalised PLACEMENT Show/Hide to SHOW|HIDE + strict dropdown.
# NOT part of the publish path. Needs the service account temporarily
# promoted to Editor on the Sheet; revert to Viewer after. Dry run by default.
"""RIDER - normalize PLACEMENT Show/Hide to SHOW|HIDE, then strict-validate.

The condition that used to live inside the value moves to the Why column, so no
information is lost. Guards: each target must still hold its expected compound.
"""
import argparse, collections, os, sys
import gspread
from google.oauth2.service_account import Credentials

KEY_PATH  = os.environ.get('GRACE_PUBLISHER_KEY', 'secrets/grace-publisher.json')
SHEET_KEY = '1uxB85U-lRTZo75eGdmB23PAvJ2jdyLvvezaQIzaaekY'
SCOPES    = ['https://www.googleapis.com/auth/spreadsheets']
FIRST, LAST = 5, 300

COMPOUND_NOTE = '(turn on once F-rows APPROVED — Status gate enforces)'
OPTIONAL_NOTE = '(OPTIONAL — T to decide; flip to SHOW when she says go)'
CHANGE_LOG_ROW = ['2026-08-28', 'RTS', 'PLACEMENT Show/Hide (7 rows)',
                  'RTS — normalized Show/Hide values, added dropdown validation',
                  'unchanged']

ap = argparse.ArgumentParser(); ap.add_argument('--apply', action='store_true')
args = ap.parse_args()

gc = gspread.authorize(Credentials.from_service_account_file(KEY_PATH, scopes=SCOPES))
sh = gc.open_by_key(SHEET_KEY)
ws = sh.worksheet('PLACEMENT')
vals = ws.get_all_values()
h = vals[3]
iP, iU, iS, iW = h.index('Page'), h.index('URL path'), h.index('Show / Hide'), h.index('Why')

plan, skips = [], []
for n, r in enumerate(vals, 1):
    if n <= 4 or not r or not r[0].strip():
        continue
    cur = (r[iS] if iS < len(r) else '').strip()
    if cur in ('SHOW', 'HIDE', ''):
        continue
    why = (r[iW] if iW < len(r) else '').strip()
    if cur.upper().startswith('SHOW'):
        new_val, note = 'SHOW', COMPOUND_NOTE
    elif cur.upper() == 'OPTIONAL':
        new_val, note = 'HIDE', OPTIONAL_NOTE
    else:
        skips.append((r[iP].strip(), cur, 'unrecognised value - not normalising')); continue
    new_why = (why + ' ' + note).strip() if note not in why else why
    plan.append({'row': n, 'page': r[iP].strip(), 'path': (r[iU] if iU < len(r) else '').strip(),
                 'old': cur, 'new': new_val, 'why_old': why, 'why_new': new_why})

print('=' * 116)
print(f'{"row":>4}  {"page":18} {"path":22} {"old":28} -> new')
print('=' * 116)
for p in plan:
    print(f'{p["row"]:>4}  {p["page"]:18} {p["path"]:22} {p["old"]:28} -> {p["new"]}')
    print(f'{"":46} Why: {p["why_new"][:96]}')
print('=' * 116)
print(f'rows to normalize: {len(plan)}')
if skips:
    print('SKIPPED:'); [print(f'  !! {a} {b!r} {c}') for a, b, c in skips]

# publish impact check - does any normalised row become publishable?
sys.path.insert(0, '.')
PILOT = ['/plan-your-visit/', '/giving/']
now_show = [p for p in plan if p['new'] == 'SHOW']
in_pilot = [p for p in now_show if p['path'] in PILOT]
print(f'\nPUBLISH IMPACT: {len(now_show)} rows become literal SHOW; '
      f'{len(in_pilot)} of them are in PILOT_ROUTES {PILOT}')
print('  -> ' + ('NONE reach production (all outside PILOT_ROUTES)' if not in_pilot
                 else f'WARNING: {[p["page"] for p in in_pilot]} would now publish'))

if not args.apply:
    print('\nDRY RUN - nothing written. Re-run with --apply.')
    sys.exit(0)

# guard re-check immediately before writing
live = ws.get_all_values()
for p in plan:
    got = (live[p['row'] - 1][iS] if iS < len(live[p['row'] - 1]) else '').strip()
    if got != p['old']:
        sys.exit(f'ABORT: row {p["row"]} changed under us (expected {p["old"]!r}, found {got!r})')

data = []
for p in plan:
    data.append({'range': f"'PLACEMENT'!{gspread.utils.rowcol_to_a1(p['row'], iS+1)}",
                 'values': [[p['new']]]})
    data.append({'range': f"'PLACEMENT'!{gspread.utils.rowcol_to_a1(p['row'], iW+1)}",
                 'values': [[p['why_new']]]})
sh.values_batch_update({'valueInputOption': 'RAW', 'data': data})
print(f'\nnormalized {len(plan)} rows ({len(data)} cells in 1 request)')

sh.batch_update({'requests': [{'setDataValidation': {
    'range': {'sheetId': ws.id, 'startRowIndex': FIRST-1, 'endRowIndex': LAST,
              'startColumnIndex': iS, 'endColumnIndex': iS+1},
    'rule': {'condition': {'type': 'ONE_OF_LIST',
                           'values': [{'userEnteredValue': v} for v in ('SHOW', 'HIDE')]},
             'strict': True, 'showCustomUi': True,
             'inputMessage': 'SHOW or HIDE only. Conditions belong in the Why column.'}}}]})
print('validation applied: [SHOW, HIDE] strict')

clog = sh.worksheet('CHANGE LOG')
nrow = len(clog.get_all_values()) + 1
clog.update(f'A{nrow}:E{nrow}', [CHANGE_LOG_ROW], value_input_option='RAW')
print(f'CHANGE LOG row {nrow} added')

# ---- verify -------------------------------------------------------------
print('\n=== VERIFY ===')
v2 = ws.get_all_values()
c = collections.Counter()
for n, r in enumerate(v2, 1):
    if n > 4 and r and r[0].strip():
        c[(r[iS] if iS < len(r) else '').strip()] += 1
print('  distinct Show/Hide now:', dict(c))
for p in plan:
    r = v2[p['row'] - 1]
    print(f"  row {p['row']:>2} {p['page']:18} = {(r[iS] if iS<len(r) else ''):5} "
          f"| Why: {(r[iW] if iW<len(r) else '')[:78]}")
dv = gc.http_client.request('get',
    f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_KEY}'
    f'?ranges=PLACEMENT!{chr(65+iS)}{FIRST}:{chr(65+iS)}{FIRST}'
    '&fields=sheets(data(rowData(values(dataValidation))))').json()
d = dv['sheets'][0]['data'][0]['rowData'][0]['values'][0]['dataValidation']
print(f"\n  RULE: {d['condition']['type']} strict={d.get('strict')} customUi={d.get('showCustomUi')}")
print(f"  allowed: {[x['userEnteredValue'] for x in d['condition']['values']]}")
outside = [v for v in c if v and v not in ('SHOW', 'HIDE')]
print(f"  OUT-OF-LIST cells: {outside or 'none'}")
