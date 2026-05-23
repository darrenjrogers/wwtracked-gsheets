# wwtracked-gsheets

Export Weight Watchers tracked food and nutrition data to Markdown reports and Google Sheets — runs unattended on a daily schedule via Docker.

This is a fork of [joswr1ght/wwtracked](https://github.com/joswr1ght/wwtracked) with these additions:

- `.env` support for unattended/scheduled runs (no interactive password prompt)
- Google Sheets export: one tab per month, cumulative rows, idempotent re-runs
- Daily scheduler with randomised midnight run time (±30 min)
- Docker Compose packaging for OrbStack or any Docker host

---

## Quick start (local, no Docker)

```bash
git clone https://github.com/darrenjrogers/wwtracked-gsheets.git
cd wwtracked-gsheets
uv venv && uv pip install -r requirements.txt

cp .env.example .env
# edit .env with your credentials
```

Run for a date range:

```bash
source .venv/bin/activate
python wwtracked.py -s 2026-05-01 -e 2026-05-23 -n --gsheets
```

---

## Credentials

### Weight Watchers

Add to `.env`:

```
WW_EMAIL=you@example.com
WW_PASSWORD=yourpassword
```

You can also pass credentials on the command line with `-E` / `-J` as before.
The `WW_PASSWORD` env var is only used when `-E` is set (or `WW_EMAIL` is in `.env`) — it is never used with JWT auth.

### Google Sheets — service account setup

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project and enable the **Google Sheets API**.
2. Create a **Service Account**, give it no special roles.
3. Under the service account, create a JSON key and download it as `service-account-key.json` in the project root.
4. Create a Google Sheet. Note the **Sheet ID** from the URL:
   `https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit`
5. Share the sheet with the service account's email address (Editor access).
6. Add to `.env`:

```
GOOGLE_SHEET_ID=your_sheet_id_here
```

The script creates one tab per month (e.g. `2026-05`) and appends rows for each food entry. Re-running for the same date range is safe — duplicate rows are skipped.

---

## Docker Compose (OrbStack / Docker Desktop)

### Setup

1. Complete the credential steps above so you have `.env` and `service-account-key.json` in the project root.
2. Build and start:

```bash
docker compose up -d --build
```

The container runs `scheduler.py` which:
- On startup: fetches yesterday's data and exports to Sheets.
- Daily: wakes at midnight ±30 minutes and repeats.

Logs:

```bash
docker compose logs -f
```

Reports are written to `./reports/` on the host via the bind mount.

### Stopping

```bash
docker compose down
```

---

## Running on a second Mac with OrbStack

1. Copy the project directory to the second Mac (or `git clone` the repo there).
2. Place `.env` and `service-account-key.json` in the project root (these are gitignored).
3. Install [OrbStack](https://orbstack.dev/) if not already installed.
4. `docker compose up -d --build`

---

## Backfilling historical data

Use `--backfill` to pull historical data in one shot. The end date is always yesterday.

```bash
# Year to date
python wwtracked.py --backfill ytd -n --gsheets

# Last 3, 6, or 12 months
python wwtracked.py --backfill 3months -n --gsheets
python wwtracked.py --backfill 6months -n --gsheets
python wwtracked.py --backfill 12months -n --gsheets

# Since a specific date
python wwtracked.py --backfill 2026-01-01 -n --gsheets
```

The Google Sheets export is idempotent — rows already in the sheet are skipped, so you can re-run a backfill safely without creating duplicates.

---

## Command-line reference

```
usage: wwtracked.py [-h] [-E EMAIL | -J JWT] [-s START] [-e END] [-n] [-l TLD] [-o FILE] [--gsheets] [--backfill PERIOD]

options:
  -E, --email         WW login email (or set WW_EMAIL in .env)
  -J, --jwt           WW JWT token (or set WW_JWT in .env)
  -s, --start         Start date YYYY-MM-DD (not needed with --backfill)
  -e, --end           End date YYYY-MM-DD (default: yesterday with --backfill)
  -n, --nutrition     Also produce a CSV report of nutritional data
  -l, --tld           WW site TLD (default: com)
  -o, --output        Write Markdown report to FILE (- for stdout)
  --gsheets           Export nutrition data to Google Sheets (requires -n)
  --backfill PERIOD   Backfill history: ytd, 3months, 6months, 12months, or YYYY-MM-DD start date
```

---

## Authentication notes

The WW JWT expires ~2 hours after browser login, making it unsuitable for unattended scheduled runs. Use `WW_EMAIL` + `WW_PASSWORD` in `.env` for automated use — the script authenticates fresh on each run.

For manual one-off runs you can still pass a JWT with `-J`. See [AUTHJWT.md](AUTHJWT.md) for how to extract the JWT from your browser.

---

## Files

| File | Purpose |
|---|---|
| `wwtracked.py` | Main script — fetch WW data, write Markdown + CSV reports |
| `gsheets.py` | Google Sheets export module |
| `scheduler.py` | Docker entrypoint — daily scheduler |
| `Dockerfile` | Container image |
| `docker-compose.yml` | Compose service definition |
| `.env.example` | Template for your `.env` |
| `service-account-key.json` | Google service account key (gitignored, you provide this) |
| `reports/` | Output directory for Markdown and CSV reports (bind-mounted in Docker) |
