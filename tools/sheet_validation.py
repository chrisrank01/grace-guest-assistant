#!/usr/bin/env python3.12
# One-off (2026-08-28): strict dropdown on the ANSWERS Status column.
# NOT part of the publish path. Needs the service account temporarily
# promoted to Editor on the Sheet; revert to Viewer after. Dry run by default.
"""One-off: put a strict dropdown on the ANSWERS Status column.

The allowed list is derived from what is actually in the sheet plus APPROVED -
not from anyone's memory of what the statuses are.
"""
import argparse, collections, os, sys, json
import gspread
from google.oauth2.service_account import Credentials

KEY_PATH  = os.environ.get('GRACE_PUBLISHER_KEY', 'secrets/grace-publisher.json')
SHEET_KEY = '1uxB85U-lRTZo75eGdmB23PAvJ2jdyLvvezaQIzaaekY'
SCOPES    = ['https://www.googleapis.com/auth/spreadsheets']
FIRST_DATA_ROW = 5
LAST_ROW       = 300          # generous buffer so future rows inherit the rule

ap = argparse.ArgumentParser()
ap.add_argument('--apply', action='store_true')
args = ap.parse_args()

gc = gspread.authorize(Credentials.from_service_account_file(KEY_PATH, scopes=SCOPES))
sh = gc.open_by_key(SHEET_KEY)
ws = sh.worksheet('ANSWERS')
vals = ws.get_all_values()
col  = vals[3].index('Status')          # 0-based

found = collections.Counter()
for r in vals[FIRST_DATA_ROW - 1:]:
    if r and r[0].strip():
        found[(r[col].strip() if col < len(r) else '')] += 1

allowed = list(dict.fromkeys([v for v in found if v] + ['APPROVED']))
order = {'HOLD': 0, 'DRAFT': 1, 'APPROVED': 2}
allowed.sort(key=lambda v: order.get(v, 99))

print('values found in sheet :', dict(found))
print('validation list       :', allowed)
print(f'range                 : {chr(65+col)}{FIRST_DATA_ROW}:{chr(65+col)}{LAST_ROW}'
      f'  (grid is {ws.row_count} rows, no resize needed)')

outside = [(n, r[0], r[col] if col < len(r) else '')
           for n, r in enumerate(vals[FIRST_DATA_ROW - 1:], start=FIRST_DATA_ROW)
           if r and r[0].strip() and (r[col].strip() if col < len(r) else '') not in allowed]
print('existing cells OUTSIDE the list:', outside or 'none')

if not args.apply:
    print('\nDRY RUN - no validation applied. Re-run with --apply.')
    sys.exit(0)

body = {'requests': [{
    'setDataValidation': {
        'range': {'sheetId': ws.id,
                  'startRowIndex': FIRST_DATA_ROW - 1, 'endRowIndex': LAST_ROW,
                  'startColumnIndex': col, 'endColumnIndex': col + 1},
        'rule': {
            'condition': {'type': 'ONE_OF_LIST',
                          'values': [{'userEnteredValue': v} for v in allowed]},
            'strict': True,
            'showCustomUi': True,
            'inputMessage': 'Pick a status. HOLD never ships; DRAFT ships during the '
                            'pilot; APPROVED is the post-pilot gate.',
        }}}]}
sh.batch_update(body)
print('\nvalidation applied.')

# ---- read the rule back out of sheet metadata ----------------------------
meta = sh.fetch_sheet_metadata({'includeGridData': False,
                                'fields': 'sheets(properties(sheetId,title),'
                                          'conditionalFormats,basicFilter)'})
full = gc.http_client.request(
    'get',
    f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_KEY}'
    f'?ranges=ANSWERS!{chr(65+col)}{FIRST_DATA_ROW}:{chr(65+col)}{FIRST_DATA_ROW}'
    '&fields=sheets(data(rowData(values(dataValidation))))').json()
try:
    dv = full['sheets'][0]['data'][0]['rowData'][0]['values'][0]['dataValidation']
    print('\nVALIDATION READ BACK FROM SHEET METADATA:')
    print(json.dumps(dv, indent=2))
except (KeyError, IndexError):
    print('\ncould not read validation back - inspect manually')
