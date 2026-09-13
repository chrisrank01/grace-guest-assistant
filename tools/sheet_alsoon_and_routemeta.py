#!/usr/bin/env python3.12
# One-off (2026-09-13): multi-page question columns on ANSWERS, route-meta
# columns on PLACEMENT, and one PLACEMENT page-name correction.
# NOT part of the publish path. Needs the service account temporarily promoted
# to Editor on the Sheet; revert to Viewer after. Dry run by default.
"""One-off: add the columns that let a question ship to more than one page, and
the columns that let per-page strings come from the Sheet instead of from
hardcoded fallbacks in publish.py.

Three changes, one Editor window:

  1. ANSWERS K 'Also on' and L 'Also on 2' - strict dropdowns, blank on every
     existing row. Blank means "appears only on its Page", which is exactly
     today's behaviour for all 70 rows.
  2. PLACEMENT F-I 'Panel title' / 'Launcher label' / 'Intro' /
     'End of questions' - blank everywhere. Populating them is T's work.
     The first three names are not arbitrary: publish.py ALREADY greps for
     them, case-insensitively (read_placement), so naming them anything else
     silently leaves them unread.
  3. PLACEMENT A10 'Start Here / Next' -> 'Start Here'. The ANSWERS Page
     dropdown offers 'Start Here' and five rows already use it, but PLACEMENT
     called that page 'Start Here / Next', so the name resolved to no
     PLACEMENT row. Harmless today because /next/ is not a pilot route;
     a publish-stopper the moment the Phase 3b validator lands.

The allowed page list is read from the sheet's OWN Page dropdown at runtime,
minus '(any page)' - not from a list typed here. '(any page)' is the
talk-person marker, not a page: 'Also on: (any page)' would either mean nothing
or mean all eighteen, and talk-person already ships everywhere by a different
mechanism.
"""
import argparse
import json
import os
import sys

import gspread
from google.oauth2.service_account import Credentials

KEY_PATH = os.environ.get('GRACE_PUBLISHER_KEY', 'secrets/grace-publisher.json')
SHEET_KEY = '1uxB85U-lRTZo75eGdmB23PAvJ2jdyLvvezaQIzaaekY'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

HEADER_ROW = 4
FIRST_DATA_ROW = 5
# Matches the extent of the dropdowns already on ANSWERS C and H, so a row
# added later inherits the new rules exactly as it inherits the old ones.
LAST_ROW = 300

NOT_A_PAGE = '(any page)'

# ANSWERS J 'Follow-up IDs (slugs)' is the one header in teal rather than the
# navy every other header uses - it is the column that points at other rows.
# K and L point at other rows too, so they take the same colour. Everything
# else about the format is copied from the existing headers verbatim.
TEAL = {'red': 0.011764706, 'green': 0.6784314, 'blue': 0.6901961}
NAVY = {'red': 0.16078432, 'green': 0.18039216, 'blue': 0.21960784}
BORDER = {'style': 'SOLID', 'width': 1, 'color': {}}


def header_format(bg):
    return {
        'backgroundColor': bg,
        'backgroundColorStyle': {'rgbColor': bg},
        'borders': {k: dict(BORDER) for k in ('top', 'bottom', 'left', 'right')},
        'textFormat': {'bold': True, 'fontSize': 11,
                       'foregroundColor': {'red': 1, 'green': 1, 'blue': 1},
                       'foregroundColorStyle': {'rgbColor': {'red': 1, 'green': 1, 'blue': 1}}},
        'verticalAlignment': 'TOP',
        'wrapStrategy': 'WRAP',
    }


ANSWERS_NEW = [
    ('K', 'Also on',
     'Optional. A second page this question also appears on. Blank = it appears '
     'only on its Page. Must be a page with a PLACEMENT row.'),
    ('L', 'Also on 2',
     'Optional. A third page this question also appears on. Blank = no third '
     'page. Must be a page with a PLACEMENT row.'),
]

PLACEMENT_NEW = [
    ('F', 'Panel title',
     'Optional. Heading inside the panel on this page. Blank = publish.py uses '
     'its built-in fallback for this route.'),
    ('G', 'Launcher label',
     'Optional. Text on the launcher pill on this page. Blank = built-in fallback.'),
    ('H', 'Intro',
     'Optional. First message in the panel on this page. Blank = built-in fallback.'),
    ('I', 'End of questions',
     'Optional. The line shown when a guest has tapped every question on this '
     'page. Blank = built-in fallback.'),
]

RENAME = {'tab': 'PLACEMENT', 'row': 10, 'col': 'A',
          'was': 'Start Here / Next', 'now': 'Start Here'}

CHANGE_LOG_ROW = [
    '2026-09-13', 'RTS',
    "ANSWERS K/L headers+validation; PLACEMENT F-I headers; PLACEMENT A10",
    "Added 'Also on' / 'Also on 2' (strict dropdown, 18 page names, blank on all "
    "70 rows) so one question can ship to more than one page. Added route-meta "
    "columns 'Panel title' / 'Launcher label' / 'Intro' / 'End of questions' "
    "(blank) so per-page strings come from the Sheet instead of hardcoded "
    "fallbacks. Renamed PLACEMENT row 10 Page 'Start Here / Next' -> 'Start "
    "Here' to match the ANSWERS Page dropdown and the 5 rows already using it.",
    'unchanged',
]


def colnum(letter):
    return ord(letter) - 65


def fail(msg):
    print(f'\n  REFUSING: {msg}')
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true',
                    help='actually write (default is a dry run)')
    args = ap.parse_args()

    gc = gspread.authorize(Credentials.from_service_account_file(KEY_PATH, scopes=SCOPES))
    sh = gc.open_by_key(SHEET_KEY)
    answers = sh.worksheet('ANSWERS')
    placement = sh.worksheet('PLACEMENT')
    changelog = sh.worksheet('CHANGE LOG')

    a_vals = answers.get_all_values()
    p_vals = placement.get_all_values()
    c_vals = changelog.get_all_values()

    a_hdr = a_vals[HEADER_ROW - 1]
    p_hdr = p_vals[HEADER_ROW - 1]

    # ---- GUARDS. Every one of these would make the write wrong, not just odd.
    if a_hdr[:10] != ['ID', 'Slug', 'Page', 'Tap Question (guest sees)',
                      'Answer Text (pre-approved)', 'Primary Action → Destination',
                      'Topic Tags', 'Status', 'Source / Notes', 'Follow-up IDs (slugs)']:
        fail(f'ANSWERS header row is not what this script was written against: {a_hdr[:10]}')
    if p_hdr[:5] != ['Page', 'URL path', 'Show / Hide',
                     'Starter question IDs (3–5)', 'Why']:
        fail(f'PLACEMENT header row is not what this script was written against: {p_hdr[:5]}')
    for letter, name, _ in ANSWERS_NEW:
        i = colnum(letter)
        occupied = [r for r in a_vals if len(r) > i and r[i].strip()]
        if occupied:
            fail(f'ANSWERS column {letter} is not empty ({len(occupied)} cells) - '
                 'this script only ever creates new columns')
    for letter, name, _ in PLACEMENT_NEW:
        i = colnum(letter)
        occupied = [r for r in p_vals if len(r) > i and r[i].strip()]
        if occupied:
            fail(f'PLACEMENT column {letter} is not empty ({len(occupied)} cells)')

    # ---- the page list, read from the sheet's own dropdown --------------
    meta = sh.fetch_sheet_metadata({
        'ranges': [f'ANSWERS!C{FIRST_DATA_ROW}:C{FIRST_DATA_ROW}'],
        'includeGridData': True,
        'fields': 'sheets(data(rowData(values(dataValidation))))',
    })
    try:
        rule = meta['sheets'][0]['data'][0]['rowData'][0]['values'][0]['dataValidation']
        page_values = [v['userEnteredValue'] for v in rule['condition']['values']]
    except (KeyError, IndexError):
        fail('could not read the existing Page dropdown from ANSWERS!C5')
    if rule['condition']['type'] != 'ONE_OF_LIST':
        fail(f"existing Page rule is {rule['condition']['type']}, not ONE_OF_LIST")

    allowed = [v for v in page_values if v != NOT_A_PAGE]

    # ---- the rename target ---------------------------------------------
    r = RENAME['row']
    current = p_vals[r - 1][colnum(RENAME['col'])].strip() if len(p_vals) >= r else ''
    if current != RENAME['was']:
        fail(f"{RENAME['tab']}!{RENAME['col']}{r} is {current!r}, expected {RENAME['was']!r}")

    users = sum(1 for row in a_vals[FIRST_DATA_ROW - 1:]
                if len(row) > 2 and row[2].strip() == RENAME['now'])

    cl_row = len(c_vals) + 1

    # ---- PLANNED CHANGES ------------------------------------------------
    print('=' * 78)
    print('PLANNED CHANGES'.center(78))
    print('=' * 78)
    print(f"\nWorkbook : {sh.title}")
    print(f"Page list: read from ANSWERS!C5 dropdown at runtime - "
          f"{len(page_values)} values, minus {NOT_A_PAGE!r} = {len(allowed)}")
    print(f"           {allowed}")

    print('\n--- 1. ANSWERS: two new columns -------------------------------------')
    print(f'{"cell":<12} {"header":<16} {"validation":<46}')
    for letter, name, msg in ANSWERS_NEW:
        rng = f'{letter}{FIRST_DATA_ROW}:{letter}{LAST_ROW}'
        print(f'{letter}{HEADER_ROW:<11} {name:<16} ONE_OF_LIST strict showCustomUi  {rng}')
        print(f'{"":<12} {"":<16} {len(allowed)} values, inputMessage set')
    print(f'  header fill: TEAL, matching J "Follow-up IDs (slugs)" - the other')
    print(f'               column that points at rows rather than holding content')
    print(f'  data cells : written BLANK on all {len(a_vals) - HEADER_ROW} existing rows')
    print(f'               (blank = "appears only on its Page" = today\'s behaviour)')

    print('\n--- 2. PLACEMENT: four route-meta columns ---------------------------')
    for letter, name, msg in PLACEMENT_NEW:
        read_by = 'publish.py reads this ALREADY' if name.lower() in (
            'panel title', 'launcher label', 'intro') else 'needs the Phase 3a reader'
        print(f'{letter}{HEADER_ROW:<11} {name:<18} blank everywhere   ({read_by})')
    print('  header fill: NAVY, matching every other PLACEMENT header')
    print('  no validation - these are free text')

    print('\n--- 3. PLACEMENT: one page-name correction --------------------------')
    print(f"  {RENAME['tab']}!{RENAME['col']}{r}")
    print(f"      was : {RENAME['was']!r}")
    print(f"      now : {RENAME['now']!r}")
    print(f"      why : the ANSWERS Page dropdown offers {RENAME['now']!r} and "
          f"{users} rows already use it;")
    print(f"            PLACEMENT was the only place carrying the longer name.")

    print('\n--- 4. CHANGE LOG: one appended row ---------------------------------')
    print(f'  row {cl_row}: {CHANGE_LOG_ROW[0]} | {CHANGE_LOG_ROW[1]} | '
          f'{CHANGE_LOG_ROW[2][:44]}…')

    print('\n--- NOT changed ------------------------------------------------------')
    print('  - no existing cell value anywhere except PLACEMENT!A10')
    print('  - ANSWERS C and H dropdowns: untouched')
    print('  - PLACEMENT B and C dropdowns: untouched')
    print('  - the Slug column protection: untouched')
    print(f'  - all {len(a_vals) - HEADER_ROW} ANSWERS rows keep their Page, Status, '
          'answers and follow-ups')

    n_req = (len(ANSWERS_NEW) * 2) + len(PLACEMENT_NEW) + 2   # +rename +changelog
    print('\n' + '=' * 78)
    print(f'{n_req} write requests in ONE batchUpdate '
          f'(API limit is 60 writes/min; this counts as 1)')
    print('=' * 78)

    if not args.apply:
        print('\nDRY RUN - nothing written. Re-run with --apply.')
        return

    # ---- APPLY ----------------------------------------------------------
    requests = []

    # headers + validation, ANSWERS
    for letter, name, msg in ANSWERS_NEW:
        i = colnum(letter)
        requests.append({'updateCells': {
            'range': {'sheetId': answers.id, 'startRowIndex': HEADER_ROW - 1,
                      'endRowIndex': HEADER_ROW, 'startColumnIndex': i, 'endColumnIndex': i + 1},
            'rows': [{'values': [{'userEnteredValue': {'stringValue': name},
                                  'userEnteredFormat': header_format(TEAL)}]}],
            'fields': 'userEnteredValue,userEnteredFormat',
        }})
        requests.append({'setDataValidation': {
            'range': {'sheetId': answers.id, 'startRowIndex': FIRST_DATA_ROW - 1,
                      'endRowIndex': LAST_ROW, 'startColumnIndex': i, 'endColumnIndex': i + 1},
            'rule': {'condition': {'type': 'ONE_OF_LIST',
                                   'values': [{'userEnteredValue': v} for v in allowed]},
                     'strict': True, 'showCustomUi': True, 'inputMessage': msg},
        }})

    # headers, PLACEMENT
    for letter, name, _ in PLACEMENT_NEW:
        i = colnum(letter)
        requests.append({'updateCells': {
            'range': {'sheetId': placement.id, 'startRowIndex': HEADER_ROW - 1,
                      'endRowIndex': HEADER_ROW, 'startColumnIndex': i, 'endColumnIndex': i + 1},
            'rows': [{'values': [{'userEnteredValue': {'stringValue': name},
                                  'userEnteredFormat': header_format(NAVY)}]}],
            'fields': 'userEnteredValue,userEnteredFormat',
        }})

    # the rename
    ri = colnum(RENAME['col'])
    requests.append({'updateCells': {
        'range': {'sheetId': placement.id, 'startRowIndex': r - 1, 'endRowIndex': r,
                  'startColumnIndex': ri, 'endColumnIndex': ri + 1},
        'rows': [{'values': [{'userEnteredValue': {'stringValue': RENAME['now']}}]}],
        'fields': 'userEnteredValue',
    }})

    # change log
    requests.append({'updateCells': {
        'range': {'sheetId': changelog.id, 'startRowIndex': cl_row - 1, 'endRowIndex': cl_row,
                  'startColumnIndex': 0, 'endColumnIndex': len(CHANGE_LOG_ROW)},
        'rows': [{'values': [{'userEnteredValue': {'stringValue': v}} for v in CHANGE_LOG_ROW]}],
        'fields': 'userEnteredValue',
    }})

    print(f'\nAPPLYING {len(requests)} requests in one batchUpdate...')
    sh.batch_update({'requests': requests})
    print('  done.')


if __name__ == '__main__':
    main()
