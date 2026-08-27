"""Auth smoke test: can we reach the corpus Sheet with the service-account key?"""
import json, os, sys
import gspread
from google.oauth2.service_account import Credentials

KEY_PATH  = os.environ.get('GRACE_PUBLISHER_KEY', 'secrets/grace-publisher.json')
SHEET_KEY = '1uxB85U-lRTZo75eGdmB23PAvJ2jdyLvvezaQIzaaekY'
SCOPES    = ['https://www.googleapis.com/auth/spreadsheets.readonly']

if not os.path.exists(KEY_PATH):
    sys.exit(f'FileNotFoundError: no key at {KEY_PATH} -- key not in place yet')
print('client_email:', json.load(open(KEY_PATH)).get('client_email', '(missing)'))
gc = gspread.authorize(Credentials.from_service_account_file(KEY_PATH, scopes=SCOPES))
sh = gc.open_by_key(SHEET_KEY)
print('spreadsheet:', sh.title)
print('worksheets :', [ws.title for ws in sh.worksheets()])
print('ANSWERS rows:', len(sh.worksheet('ANSWERS').get_all_values()))
