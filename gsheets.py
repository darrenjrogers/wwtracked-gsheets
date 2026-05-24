"""
Google Sheets export for wwtracked.
One tab per month (e.g. "2026-05"), one row per tracked food entry.
Rows are keyed by (date, meal, food name) so re-runs are idempotent.

Summary tab: weekly averages of daily macro totals, excluding days where
fewer than 2 of morning/midday/evening had any tracked items.
"""

import datetime
import os
from collections import defaultdict
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

HEADERS = [
    'Date', 'Meal', 'Food', 'Portion Size', 'Portion Name',
    'Calories', 'Fat', 'Sat Fat', 'Sodium', 'Carbs',
    'Fiber', 'Sugar', 'Added Sugar', 'Protein',
]

SUMMARY_HEADERS = [
    'Week Starting (Mon)', 'Week Ending (Sun)', 'Days Included',
    'Avg Calories', 'Avg Protein (g)', 'Avg Fat (g)', 'Avg Sat Fat (g)',
    'Avg Carbs (g)', 'Avg Fiber (g)', 'Avg Sugar (g)', 'Avg Added Sugar (g)',
    'Avg Sodium (mg)',
]

DAILY_HEADERS = [
    'Date', 'Items Tracked',
    'Calories', 'Protein (g)', 'Fat (g)', 'Sat Fat (g)',
    'Carbs (g)', 'Fiber (g)', 'Sugar (g)', 'Added Sugar (g)', 'Sodium (mg)',
]

MACROS = ['calories', 'protein', 'fat', 'saturatedFat', 'carbs', 'fiber', 'sugar', 'addedSugar', 'sodium']

# Column indices in HEADERS for each macro (0-based, after skipping the 5 label cols)
HEADER_COL = {
    'calories':     HEADERS.index('Calories'),
    'fat':          HEADERS.index('Fat'),
    'saturatedFat': HEADERS.index('Sat Fat'),
    'sodium':       HEADERS.index('Sodium'),
    'carbs':        HEADERS.index('Carbs'),
    'fiber':        HEADERS.index('Fiber'),
    'sugar':        HEADERS.index('Sugar'),
    'addedSugar':   HEADERS.index('Added Sugar'),
    'protein':      HEADERS.index('Protein'),
}


def _service(key_file):
    creds = service_account.Credentials.from_service_account_file(key_file, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds, cache_discovery=False)


def _tab_name(date_str):
    return date_str[:7]


def _sheet_meta(svc, sheet_id):
    return svc.spreadsheets().get(spreadsheetId=sheet_id).execute()


def _existing_tabs(meta):
    return {s['properties']['title']: s['properties']['sheetId'] for s in meta['sheets']}


def _ensure_tab(svc, sheet_id, tab, meta=None):
    if meta is None:
        meta = _sheet_meta(svc, sheet_id)
    existing = _existing_tabs(meta)
    if tab not in existing:
        body = {'requests': [{'addSheet': {'properties': {'title': tab}}}]}
        svc.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body=body).execute()
        svc.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"'{tab}'!A1",
            valueInputOption='RAW',
            body={'values': [HEADERS]},
        ).execute()


def _existing_keys(svc, sheet_id, tab):
    result = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{tab}'!A:C",
    ).execute()
    rows = result.get('values', [])
    keys = set()
    for row in rows[1:]:
        if len(row) >= 3:
            keys.add((row[0], row[1], row[2]))
    return keys


def export_nutrition(nutrition_rows, key_file, sheet_id):
    """
    Appends only rows not already present, grouped by month tab.
    """
    if not nutrition_rows:
        return

    svc = _service(key_file)

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


def _read_all_data(svc, sheet_id):
    """Read all monthly tabs and return list of row dicts."""
    meta = _sheet_meta(svc, sheet_id)
    tabs = [t for t in _existing_tabs(meta) if len(t) == 7 and t[4] == '-']  # YYYY-MM shape
    rows = []
    for tab in sorted(tabs):
        result = svc.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"'{tab}'!A:N",
        ).execute()
        tab_rows = result.get('values', [])
        for r in tab_rows[1:]:  # skip header
            if len(r) < len(HEADERS):
                r += [''] * (len(HEADERS) - len(r))
            rows.append(r)
    return rows


def _safe_float(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def update_summary(key_file, sheet_id):
    """
    Reads all monthly tabs, computes weekly averages of daily macro totals,
    and overwrites the Summary tab. Days with fewer than 2 of
    morning/midday/evening having any tracked items are excluded.
    """
    svc = _service(key_file)
    rows = _read_all_data(svc, sheet_id)

    # Aggregate per day: meals present + macro totals
    # day_meals[date] = set of meal names that have at least one item
    # day_macros[date][macro] = total
    day_meals = defaultdict(set)
    day_macros = defaultdict(lambda: defaultdict(float))

    for r in rows:
        date = r[HEADERS.index('Date')]
        meal = r[HEADERS.index('Meal')]
        if not date:
            continue
        day_meals[date].add(meal)
        for macro, col in HEADER_COL.items():
            day_macros[date][macro] += _safe_float(r[col])

    TRACKED_MEALS = {'morning', 'midday', 'evening'}

    # Filter: keep only days where ≥2 of the 3 main meal periods have data
    qualified_days = {
        date for date, meals in day_meals.items()
        if len(meals & TRACKED_MEALS) >= 2
    }

    # Group qualified days by ISO week (Monday–Sunday)
    # week key = date of that Monday
    week_days = defaultdict(list)
    for date_str in qualified_days:
        d = datetime.date.fromisoformat(date_str)
        monday = d - datetime.timedelta(days=d.weekday())
        week_days[monday].append(date_str)

    # Build summary rows, one per complete week (exclude current/partial week)
    today = datetime.date.today()
    this_monday = today - datetime.timedelta(days=today.weekday())

    summary_rows = []
    for monday in sorted(week_days):
        if monday >= this_monday:
            continue  # skip current partial week
        sunday = monday + datetime.timedelta(days=6)
        days = week_days[monday]
        n = len(days)
        avgs = {}
        for macro in MACROS:
            total = sum(day_macros[d][macro] for d in days)
            avgs[macro] = round(total / n, 1) if n else ''
        summary_rows.append([
            monday.isoformat(),
            sunday.isoformat(),
            n,
            avgs['calories'],
            avgs['protein'],
            avgs['fat'],
            avgs['saturatedFat'],
            avgs['carbs'],
            avgs['fiber'],
            avgs['sugar'],
            avgs['addedSugar'],
            avgs['sodium'],
        ])

    # Overwrite Summary tab entirely
    meta = _sheet_meta(svc, sheet_id)
    existing = _existing_tabs(meta)
    if 'Summary' not in existing:
        body = {'requests': [{'addSheet': {'properties': {'title': 'Summary'}}}]}
        svc.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body=body).execute()
    else:
        # Clear existing content
        svc.spreadsheets().values().clear(
            spreadsheetId=sheet_id,
            range="'Summary'",
        ).execute()

    all_rows = [SUMMARY_HEADERS] + summary_rows
    svc.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="'Summary'!A1",
        valueInputOption='RAW',
        body={'values': all_rows},
    ).execute()

    print(f"Sheets: Summary tab updated — {len(summary_rows)} weeks written", flush=True)


def update_daily_macros(key_file, sheet_id):
    """
    Reads all monthly tabs, computes per-day item counts and macro totals,
    and overwrites the 'Daily Macros' tab. All days with any tracked data
    are included, sorted ascending by date.
    """
    svc = _service(key_file)
    rows = _read_all_data(svc, sheet_id)

    day_item_count = defaultdict(int)
    day_macros = defaultdict(lambda: defaultdict(float))

    for r in rows:
        date = r[HEADERS.index('Date')]
        if not date:
            continue
        day_item_count[date] += 1
        for macro, col in HEADER_COL.items():
            day_macros[date][macro] += _safe_float(r[col])

    daily_rows = []
    for date_str in sorted(day_item_count):
        m = day_macros[date_str]
        daily_rows.append([
            date_str,
            day_item_count[date_str],
            round(m['calories'], 1),
            round(m['protein'], 1),
            round(m['fat'], 1),
            round(m['saturatedFat'], 1),
            round(m['carbs'], 1),
            round(m['fiber'], 1),
            round(m['sugar'], 1),
            round(m['addedSugar'], 1),
            round(m['sodium'], 1),
        ])

    meta = _sheet_meta(svc, sheet_id)
    existing = _existing_tabs(meta)
    if 'Daily Macros' not in existing:
        body = {'requests': [{'addSheet': {'properties': {'title': 'Daily Macros'}}}]}
        svc.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body=body).execute()
    else:
        svc.spreadsheets().values().clear(
            spreadsheetId=sheet_id,
            range="'Daily Macros'",
        ).execute()

    all_rows = [DAILY_HEADERS] + daily_rows
    svc.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="'Daily Macros'!A1",
        valueInputOption='RAW',
        body={'values': all_rows},
    ).execute()

    print(f"Sheets: Daily Macros tab updated — {len(daily_rows)} days written", flush=True)
