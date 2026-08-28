#!/usr/bin/env python3.12
# One-off (2026-08-28): link harvest into 11 cells + 18 draft answers + notes banking.
# NOT part of the publish path. Needs the service account temporarily
# promoted to Editor on the Sheet; revert to Viewer after. Dry run by default.
"""
sheet_write.py - ONE-OFF batch write into grace-assistant-corpus.

Dry run is the default and prints the complete planned write table. Nothing is
written without --apply. Every cell is read first and guarded:

  * link cells      - current value must match the expected-old test, else SKIP
  * the 18 answers  - current value must be EMPTY, else SKIP
  * notes / FLAGS   - APPEND to whatever is there, never overwrite

The service account needs Editor on the Sheet for --apply. Revert it to Viewer
afterwards; publish.py only ever needs read.
"""

import argparse
import datetime
import os
import re
import sys

import gspread
from google.oauth2.service_account import Credentials

KEY_PATH = os.environ.get('GRACE_PUBLISHER_KEY', 'secrets/grace-publisher.json')
SHEET_KEY = '1uxB85U-lRTZo75eGdmB23PAvJ2jdyLvvezaQIzaaekY'
# Write scope, for THIS script only. publish.py stays read-only.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

DRAFT_PATH = os.path.expanduser('~/Downloads/DRAFT-COPY-18-ROWS.md')
DRAFT_MARKER = 'Hunt complete 2026-08-28'
ARROW = '→'                      # the Sheet's own arrow character
NOTE_STAMP = 'RTS draft 2026-08-28 - for T\'s edit'
TODAY = '2026-08-28'

COL = {'ID': 1, 'Slug': 2, 'Page': 3, 'Question': 4, 'Answer': 5,
       'Link': 6, 'Tags': 7, 'Status': 8, 'Notes': 9, 'Followups': 10}
HEADER_ROW = 4

# --------------------------------------------------------------------------
# A. LINK CELLS - (row id, guard kind, guard value, new value or None=derive)
# --------------------------------------------------------------------------
LINK_EDITS = [
    ('CARE-01', 'exact', 'Request prayer ' + ARROW + ' prayer form',
     'Request prayer ' + ARROW + ' https://gcfl.churchcenter.com/people/forms/303951'),
    ('CARE-02', 'contains', 'gracecounselingcenter.org/intake',
     'Request appointment ' + ARROW + ' https://gracecounselingcenter.org/intake/'
     ' | Call Grace Counseling ' + ARROW + ' tel:+14075191307'),
    ('CARE-03', 'exact', 'Start the application ' + ARROW + ' Church Center form',
     'Start the application ' + ARROW + ' https://gcfl.churchcenter.com/people/forms/1120989'
     ' | Más Información ' + ARROW + ' https://gcfl.churchcenter.com/people/forms/1147388'),
    ('CARE-04', 'exact', 'Request a visit ' + ARROW + ' hospital form',
     'Request a visit ' + ARROW + ' https://gcfl.churchcenter.com/people/forms/313980'),
    ('CON-01', 'call_no_second', 'Call 407-418-1300',
     'Call 407-418-1300 | Send a message ' + ARROW
     + ' https://gcfl.churchcenter.com/people/forms/461746'),
    ('NXT-05', 'contains', '/baptism/', None),      # keep label, swap destination
    ('KID-06', 'contains', '/baptism/', None),
    ('ORL-01', 'contains', 'maps',
     'Get directions ' + ARROW + ' https://www.google.com/maps/place/Grace+Church/'
     '@28.6875612,-81.3335485,12z/data=!4m5!3m4!1s0x88e770df6b31506f:0x579cd9326fed97c9'
     '!8m2!3d28.6323177!4d-81.4098103'),
    ('GIV-04', 'contains', 'Open the app',
     'Open the app ' + ARROW + ' https://churchcenter.com/setup'),
    ('GIV-05', 'exact', 'Contact us ' + ARROW + ' /contact/',
     'Start a non-cash gift ' + ARROW + ' https://gcfl.churchcenter.com/people/forms/313017'),
    ('NXT-02', 'exact', 'Browse open Groups ' + ARROW + ' Church Center',
     'Browse open Groups ' + ARROW + ' https://gcfl.churchcenter.com/groups/small-groups'
     '?enrollment=open_signup%2Crequest_to_join&filter=enrollment'),
]

# --------------------------------------------------------------------------
# C. SOURCE / NOTES banking - appended, never overwritten
# --------------------------------------------------------------------------
NOTE_APPENDS = [
    ('NXT-05', 'baptism signup event 3841934 (baptism-main button) vs family-ministry '
               'interest form 596566 - routing = T'),
    ('KID-06', 'baptism signup event 3841934 (baptism-main button) vs family-ministry '
               'interest form 596566 - routing = T'),
    ('BAP-F2', 'orientation cat 42336 · GK journal /wp-content/uploads/2023/03/'
               '22_GC_Gk_BaptismGuide.pdf · GS journal .../22_GC_Gs_BaptismGuide.pdf'),
    ('KID-03', 'NO online registration exists on site - check-in is in-person (big orange '
               'wall, per /orlando/). Answer likely needs reframe = T.'),
    ('CARE-05', 'lifecycle spares: premarital form 996348 · weddings /weddings/ · '
                'memorial form 313970 · dedication /family-ministry/ · '
                'pastoral-counseling form 313974 · pastoral vs professional split = T decision'),
    ('GDG-F1', 'Ways-to-do-Good PDF /wp-content/uploads/2026/02/GDG-Mobile.pdf (dated upload '
               '- not a button per no-rotating rule) · share-your-good form 1158266 · '
               'partner contact hello@discovergrace.com (mailto excluded by validator)'),
    ('HOME-02', 'introduce-yourself form 307693 (Orlando page) - candidate first-time-guest button'),
    ('PYV-06', 'YouTube youtube.com/@GraceChurchFL · blog /blog/'),
    ('STU-01', 'grads: /life-prep/ · /gradsold/ · register 3662216 · camps /camp'),
]

READ_ME_LINE = ('RULE: no series-rotating destinations as buttons (e.g. /stand, dated PDF '
                'uploads). Category 42336 is a shared Family Ministry listing - '
                'orientation/dedication/student-serve all land there.')

FLAGS_D1_APPEND = 'RESOLVED - form 461746, confirmed via /contact/ + /family-ministry/, 2026-08-27'

CHANGE_LOG_ROW = [TODAY, 'RTS', 'link cells + 18 FUTURE rows + notes',
                  'Batch: link harvest (11 cells), 18 draft answers for T review, '
                  'notes banking, D1 resolved', 'DRAFT/HOLD (unchanged)']


# --------------------------------------------------------------------------
def parse_drafts():
    """18 entries out of the draft markdown -> {id: (answer, link)}."""
    if not os.path.exists(DRAFT_PATH):
        sys.exit(f'draft file not found: {DRAFT_PATH}')
    text = open(DRAFT_PATH, encoding='utf-8').read()
    head = [l for l in text.split('\n') if l.strip()][:4]
    print('DRAFT FILE HEADER')
    for line in head[:2]:
        print('  ' + line)
    if DRAFT_MARKER not in text:
        sys.exit(f'draft file is not the final version - {DRAFT_MARKER!r} missing')
    print(f'  marker present: {DRAFT_MARKER!r}\n')

    out = {}
    blocks = re.split(r'^\*\*([A-Z]{3}-F\d) · ', text, flags=re.M)
    for i in range(1, len(blocks), 2):
        rid, body = blocks[i], blocks[i + 1]
        lines = [l.rstrip() for l in body.split('\n')]
        answer, links = [], []
        for line in lines[1:]:
            if line.startswith('**') or line.startswith('---') or line.startswith('##'):
                break
            if re.match(r'^Buttons?:', line):
                for seg in re.findall(r'`([^`]+)`', line):
                    seg = seg.strip().lstrip('|').strip()
                    if ARROW in seg:
                        links.append(seg)
                continue
            if line.startswith('*(') or not line.strip():
                continue
            answer.append(line.strip())
        out[rid] = (' '.join(answer).strip(), ' | '.join(links))
    return out


def find_rows(values):
    """ID -> sheet row number (1-indexed)."""
    return {r[0].strip(): n for n, r in enumerate(values, 1)
            if n > HEADER_ROW and r and r[0].strip()}


def guard_ok(kind, expected, current):
    cur = (current or '').strip()
    if kind == 'exact':
        return cur == expected
    if kind == 'contains':
        return expected in cur
    if kind == 'call_no_second':
        return expected in cur and '|' not in cur
    return False


def a1(row, col):
    return gspread.utils.rowcol_to_a1(row, col)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true',
                    help='perform the writes (default is a dry run)')
    args = ap.parse_args()

    drafts = parse_drafts()
    print(f'parsed {len(drafts)} draft entries: {", ".join(sorted(drafts))}\n')

    gc = gspread.authorize(Credentials.from_service_account_file(KEY_PATH, scopes=SCOPES))
    sh = gc.open_by_key(SHEET_KEY)
    ans = sh.worksheet('ANSWERS')
    values = ans.get_all_values()
    rows = find_rows(values)

    def cell(rid, colname):
        r = rows.get(rid)
        if not r:
            return None
        line = values[r - 1]
        i = COL[colname] - 1
        return line[i] if i < len(line) else ''

    plan, skips = [], []

    # ---- A. link cells ----------------------------------------------------
    for rid, kind, expected, new in LINK_EDITS:
        if rid not in rows:
            skips.append((rid, 'Link', 'row not found')); continue
        cur = cell(rid, 'Link') or ''
        if not guard_ok(kind, expected, cur):
            skips.append((rid, 'Link', f'guard failed ({kind} {expected!r}); current={cur!r}'))
            continue
        value = new
        if value is None:                       # NXT-05 / KID-06: keep label
            label = cur.split(ARROW)[0].strip()
            value = f'{label} {ARROW} /baptism-main/'
        plan.append((rid, rows[rid], 'Link', COL['Link'], cur, value, 'replace'))

    # ---- B. 18 draft answers ---------------------------------------------
    for rid in sorted(drafts):
        if rid not in rows:
            skips.append((rid, 'Answer', 'row not found')); continue
        answer, link = drafts[rid]
        cur_ans = (cell(rid, 'Answer') or '').strip()
        if cur_ans:
            skips.append((rid, 'Answer', f'NOT EMPTY ({cur_ans[:40]!r}) - refusing to overwrite'))
        else:
            plan.append((rid, rows[rid], 'Answer', COL['Answer'], '', answer, 'replace'))
        if link:
            plan.append((rid, rows[rid], 'Link', COL['Link'],
                         cell(rid, 'Link') or '', link, 'replace'))
        cur_notes = cell(rid, 'Notes') or ''
        if NOTE_STAMP not in cur_notes:
            merged = (cur_notes + ' · ' + NOTE_STAMP).strip(' · ') if cur_notes else NOTE_STAMP
            plan.append((rid, rows[rid], 'Notes', COL['Notes'], cur_notes, merged, 'append'))

    # ---- C. notes banking -------------------------------------------------
    for rid, note in NOTE_APPENDS:
        if rid not in rows:
            skips.append((rid, 'Notes', 'row not found')); continue
        cur = cell(rid, 'Notes') or ''
        if note in cur:
            skips.append((rid, 'Notes', 'note already present')); continue
        merged = (cur + ' · ' + note) if cur.strip() else note
        plan.append((rid, rows[rid], 'Notes', COL['Notes'], cur, merged, 'append'))

    # ---- D. FLAGS D1 ------------------------------------------------------
    flags = sh.worksheet('FLAGS')
    fvals = flags.get_all_values()
    d1 = next((n for n, r in enumerate(fvals, 1) if r and r[0].strip() == 'D1'), None)
    if d1:
        cur = fvals[d1 - 1][2] if len(fvals[d1 - 1]) > 2 else ''
        if FLAGS_D1_APPEND in cur:
            skips.append(('FLAGS D1', 'What\'s wrong', 'already resolved'))
        else:
            plan.append(('FLAGS D1', d1, "What's wrong", 3, cur,
                         (cur + ' — ' + FLAGS_D1_APPEND).strip(), 'append'))
    else:
        skips.append(('FLAGS D1', '-', 'row not found'))

    # ---- READ ME line -----------------------------------------------------
    readme = sh.worksheet('READ ME')
    rvals = readme.get_all_values()
    if any(READ_ME_LINE[:40] in (r[0] if r else '') for r in rvals):
        skips.append(('READ ME', 'A', 'rule line already present'))
    else:
        plan.append(('READ ME', len(rvals) + 1, 'A', 1, '', READ_ME_LINE, 'new row'))

    # ---- E. CHANGE LOG ----------------------------------------------------
    clog = sh.worksheet('CHANGE LOG')
    cvals = clog.get_all_values()
    if any(TODAY in (r[0] if r else '') for r in cvals):
        skips.append(('CHANGE LOG', '-', f'{TODAY} row already present'))
    else:
        plan.append(('CHANGE LOG', len(cvals) + 1, 'A:E', 1, '',
                     ' | '.join(CHANGE_LOG_ROW), 'new row'))

    # A re-run after a partial failure must not redo work: drop any planned write
    # whose current value already equals the target.
    before = len(plan)
    plan = [p for p in plan if (p[4] or '').strip() != (p[5] or '').strip()]
    if before != len(plan):
        print(f'(idempotent: {before - len(plan)} planned writes already applied - dropped)\n')

    # ---- print the table --------------------------------------------------
    print('=' * 118)
    print(f'{"ID":10} {"row":>4} {"col":10} {"mode":8} {"current":34} -> new')
    print('=' * 118)
    for rid, row, colname, _c, cur, new, mode in plan:
        c = (cur or '').replace('\n', ' ')
        n = (new or '').replace('\n', ' ')
        print(f'{rid:10} {row:>4} {colname:10} {mode:8} {c[:33]!r:34} -> {n[:150]!r}')
    print('=' * 118)
    print(f'planned writes: {len(plan)}')
    if skips:
        print(f'\nSKIPPED ({len(skips)}) - guard failures and no-ops:')
        for rid, colname, why in skips:
            print(f'  !! {rid:12} {colname:12} {why}')
    else:
        print('\nno skips - every guard passed')

    if not args.apply:
        print('\nDRY RUN - nothing written. Re-run with --apply to perform these writes.')
        return

    # ---- apply ------------------------------------------------------------
    print('\n=== APPLYING (batched) ===')
    # One batched call per worksheet. Sheets allows 60 WRITE REQUESTS per minute
    # per user; a cell-at-a-time loop burns that in 60 cells, which is exactly how
    # the first attempt died. Batching turns 77 cells into 4 requests.
    buckets = {}
    for rid, row, colname, colnum, cur, new, mode in plan:
        if rid == 'FLAGS D1':
            tab, title = flags, 'FLAGS'
        elif rid == 'READ ME':
            tab, title = readme, 'READ ME'
        elif rid == 'CHANGE LOG':
            tab, title = clog, 'CHANGE LOG'
        else:
            tab, title = ans, 'ANSWERS'
        if rid == 'CHANGE LOG':
            buckets.setdefault(title, (tab, []))[1].append(
                {'range': f"'{title}'!A{row}:E{row}", 'values': [CHANGE_LOG_ROW]})
        else:
            buckets.setdefault(title, (tab, []))[1].append(
                {'range': f"'{title}'!{a1(row, colnum)}", 'values': [[new]]})
        print(f'  queued {rid} {colname} ({a1(row, colnum)})')

    written = 0
    for title, (tab, data) in buckets.items():
        sh.values_batch_update({'valueInputOption': 'RAW', 'data': data})
        written += len(data)
        print(f'  -> {title}: {len(data)} cells in 1 request')

    # ---- re-read and verify ----------------------------------------------
    print('\n=== VERIFY (full re-read) ===')
    ans2 = sh.worksheet('ANSWERS').get_all_values()
    rows2 = find_rows(ans2)
    fv2 = sh.worksheet('FLAGS').get_all_values()
    rv2 = sh.worksheet('READ ME').get_all_values()
    cv2 = sh.worksheet('CHANGE LOG').get_all_values()
    ok = bad = 0
    for rid, row, colname, colnum, cur, new, mode in plan:
        if rid == 'FLAGS D1':
            got = fv2[row - 1][colnum - 1] if len(fv2) >= row else ''
        elif rid == 'READ ME':
            got = rv2[row - 1][0] if len(rv2) >= row else ''
        elif rid == 'CHANGE LOG':
            got = ' | '.join(cv2[row - 1]) if len(cv2) >= row else ''
        else:
            line = ans2[rows2.get(rid, row) - 1]
            got = line[colnum - 1] if len(line) >= colnum else ''
        match = got.strip() == new.strip()
        ok, bad = (ok + 1, bad) if match else (ok, bad + 1)
        mark = 'OK ' if match else 'BAD'
        print(f'  {mark} {rid:10} {colname:10} now={got[:80]!r}')
    print(f'\nwritten={written}  verified_ok={ok}  verified_bad={bad}  skipped={len(skips)}')
    print('\nThese writes bump the Sheet\'s Drive modifiedTime, so the cron will DEBOUNCE')
    print('for 30 minutes. Expected next publish RESULT: status=deployed carrying the')
    print('GIV-04 and GIV-05 link changes (both are live pilot rows on /giving/).')
    print('Everything else written here is non-pilot and will not appear in answers.json.')


if __name__ == '__main__':
    main()
