#!/usr/bin/env python3.12
# One-off (2026-08-28): dropdowns on ANSWERS.Page and PLACEMENT.URL path, warning fence on Slug.
# NOT part of the publish path. Needs the service account temporarily
# promoted to Editor on the Sheet; revert to Viewer after. Dry run by default.
"""Add-on validation: ANSWERS.Page, PLACEMENT.URL path, ANSWERS.Slug warning fence.

PLACEMENT 'Show / Hide' is deliberately NOT touched here - see the report.
"""
import argparse, collections, json, os, sys
import gspread
from google.oauth2.service_account import Credentials

KEY_PATH  = os.environ.get('GRACE_PUBLISHER_KEY', 'secrets/grace-publisher.json')
SHEET_KEY = '1uxB85U-lRTZo75eGdmB23PAvJ2jdyLvvezaQIzaaekY'
SCOPES    = ['https://www.googleapis.com/auth/spreadsheets']
FIRST, LAST = 5, 300

ap = argparse.ArgumentParser(); ap.add_argument('--apply', action='store_true')
args = ap.parse_args()

gc = gspread.authorize(Credentials.from_service_account_file(KEY_PATH, scopes=SCOPES))
sh = gc.open_by_key(SHEET_KEY)

def col_values(ws_vals, hdr, name):
    i = hdr.index(name)
    c = collections.Counter()
    for r in ws_vals[FIRST - 1:]:
        if r and r[0].strip():
            c[(r[i].strip() if i < len(r) else '')] += 1
    return i, c

ans = sh.worksheet('ANSWERS');  av = ans.get_all_values(); ah = av[3]
pla = sh.worksheet('PLACEMENT'); pv = pla.get_all_values(); ph = pv[3]

page_i,  page_c  = col_values(av, ah, 'Page')
url_i,   url_c   = col_values(pv, ph, 'URL path')
slug_i           = ah.index('Slug')

page_list = sorted([v for v in page_c if v])
url_list  = sorted([v for v in url_c if v])

def dv_request(sheet_id, col, values, msg):
    return {'setDataValidation': {
        'range': {'sheetId': sheet_id, 'startRowIndex': FIRST - 1, 'endRowIndex': LAST,
                  'startColumnIndex': col, 'endColumnIndex': col + 1},
        'rule': {'condition': {'type': 'ONE_OF_LIST',
                               'values': [{'userEnteredValue': v} for v in values]},
                 'strict': True, 'showCustomUi': True, 'inputMessage': msg}}}

plan = [
    ('ANSWERS.Page',        ans.id, page_i, page_list,
     'Must match a Page name used on the PLACEMENT tab.'),
    ('PLACEMENT.URL path',  pla.id, url_i,  url_list,
     'Existing paths only. Adding a new page? Extend this list first (see READ ME).'),
]

print('=' * 100)
for label, _sid, col, values, _msg in plan:
    print(f'{label}  (col {chr(65+col)})  {len(values)} allowed values')
    for v in values:
        print(f'    {v!r}')
    print()
print('ANSWERS.Slug  (col %s)  warning-only protected range, rows %d-%d'
      % (chr(65 + slug_i), FIRST, LAST))
print('=' * 100)

# out-of-list report
for label, counter, values in (('ANSWERS.Page', page_c, page_list),
                               ('PLACEMENT.URL path', url_c, url_list)):
    outside = [v for v in counter if v and v not in values]
    blanks  = counter.get('', 0)
    print(f'{label}: out-of-list={outside or "none"}  blank cells={blanks}')

if not args.apply:
    print('\nDRY RUN - nothing applied. Re-run with --apply.')
    sys.exit(0)

reqs = [dv_request(sid, col, vals, msg) for _l, sid, col, vals, msg in plan]
reqs.append({'addProtectedRange': {'protectedRange': {
    'range': {'sheetId': ans.id, 'startRowIndex': FIRST - 1, 'endRowIndex': LAST,
              'startColumnIndex': slug_i, 'endColumnIndex': slug_i + 1},
    'description': 'Slugs are permanent identifiers - editing after ship breaks '
                   'references. Sure?',
    'warningOnly': True}}})
sh.batch_update({'requests': reqs})
print('\napplied.')

# ---- verify each rule back from metadata --------------------------------
def read_dv(tab, colletter):
    r = gc.http_client.request('get',
        f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_KEY}'
        f'?ranges={tab}!{colletter}{FIRST}:{colletter}{FIRST}'
        '&fields=sheets(data(rowData(values(dataValidation))))').json()
    try:
        return r['sheets'][0]['data'][0]['rowData'][0]['values'][0]['dataValidation']
    except (KeyError, IndexError):
        return None

print('\n=== VERIFY ===')
for tab, colletter, label in (('ANSWERS', chr(65 + page_i), 'ANSWERS.Page'),
                              ('PLACEMENT', chr(65 + url_i), 'PLACEMENT.URL path')):
    dv = read_dv(tab, colletter)
    if dv:
        vals = [v['userEnteredValue'] for v in dv['condition']['values']]
        print(f'{label}: type={dv["condition"]["type"]} strict={dv.get("strict")} '
              f'customUi={dv.get("showCustomUi")} n={len(vals)}')
        print(f'   values: {vals}')
    else:
        print(f'{label}: NO RULE READ BACK')

meta = gc.http_client.request('get',
    f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_KEY}'
    '?fields=sheets(properties(sheetId,title),protectedRanges)').json()
print('\nprotected ranges:')
for s in meta['sheets']:
    for pr in s.get('protectedRanges', []):
        rng = pr['range']
        print(f'   {s["properties"]["title"]}  cols {rng.get("startColumnIndex")}-'
              f'{rng.get("endColumnIndex")}  rows {rng.get("startRowIndex")}-'
              f'{rng.get("endRowIndex")}  warningOnly={pr.get("warningOnly")}')
        print(f'      description: {pr.get("description")!r}')
