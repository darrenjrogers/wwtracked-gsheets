"""
Google Sheets export for wwtracked.
One tab per month (e.g. "2026-05"), one row per tracked food entry.
Rows are keyed by (date, entryId) so re-runs are idempotent.
"""

import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

HEADERS = [
    'Date', 'Meal', 'Food', 'Portion Size', 'Portion Name',
    'Calories', 'Fat', 'Sat Fat', 'Sodium', 'Carbs',
    'Fiber', 'Sugar', 'Added Sugar', 'Protein',
]


def _service(key_file):
    creds = service_account.Credentials.from_service_account_file(key_file, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds, cache_discovery=False)


def _tab_name(date_str):
    # date_str is YYYY-MM-DD
    return date_str[:7]


def _ensure_tab(svc, sheet_id, tab):
    meta = svc.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing = [s['properties']['title'] for s in meta['sheets']]
    if tab not in existing:
        body = {'requests': [{'addSheet': {'properties': {'title': tab}}}]}
        svc.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body=body).execute()
        # Write header row
        svc.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"'{tab}'!A1",
            valueInputOption='RAW',
            body={'values': [HEADERS]},
        ).execute()
    return tab


def _existing_keys(svc, sheet_id, tab):
    """Return set of (date, entry_id) tuples already in the sheet."""
    result = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{tab}'!A:B",
    ).execute()
    rows = result.get('values', [])
    # rows[0] is header; col A = Date, col B = Meal — entry_id not in sheet.
    # We use (date, food_name, meal) as a dedup key since entry_id isn't exported.
    # Re-read cols A, B, C (Date, Meal, Food).
    result = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{tab}'!A:C",
    ).execute()
    rows = result.get('values', [])
    keys = set()
    for row in rows[1:]:  # skip header
        if len(row) >= 3:
            keys.add((row[0], row[1], row[2]))
    return keys


def export_nutrition(nutrition_rows, key_file, sheet_id):
    """
    nutrition_rows: list of dicts as returned by getfoodentrynutrition().
    Appends only rows not already present, grouped by month tab.
    """
    if not nutrition_rows:
        return

    svc = _service(key_file)

    # Group by month tab
    by_tab = {}
    for row in nutrition_rows:
        if row is None:
            continue
        tab = _tab_name(row['trackedDate'])
        by_tab.setdefault(tab, []).append(row)

    for tab, rows in sorted(by_tab.items()):
        _ensure_tab(svc, sheet_id, tab)
        existing = _existing_keys(svc, sheet_id, tab)

        new_rows = []
        for r in rows:
            key = (r['trackedDate'], r['timeOfDay'], r['name'])
            if key in existing:
                continue
            new_rows.append([
                r['trackedDate'],
                r['timeOfDay'],
                r['name'],
                r.get('portionSize', ''),
                r.get('portionName', ''),
                r.get('calories', ''),
                r.get('fat', ''),
                r.get('saturatedFat', ''),
                r.get('sodium', ''),
                r.get('carbs', ''),
                r.get('fiber', ''),
                r.get('sugar', ''),
                r.get('addedSugar', ''),
                r.get('protein', ''),
            ])

        if new_rows:
            svc.spreadsheets().values().append(
                spreadsheetId=sheet_id,
                range=f"'{tab}'!A1",
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': new_rows},
            ).execute()
            print(f"Sheets: appended {len(new_rows)} rows to tab '{tab}'", flush=True)
        else:
            print(f"Sheets: no new rows for tab '{tab}'", flush=True)
