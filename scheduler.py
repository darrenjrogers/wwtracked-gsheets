#!/usr/bin/env python3
"""
Scheduler entrypoint for Docker.
On start: runs wwtracked for yesterday.
Then sleeps until midnight +/- 30 minutes and repeats daily.
"""

import datetime
import os
import random
import subprocess
import sys
import time


def run_for_date(date_str):
    cmd = [sys.executable, 'wwtracked.py',
           '-s', date_str, '-e', date_str,
           '--nutrition', '--gsheets']
    print(f'[scheduler] Running for {date_str}', flush=True)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f'[scheduler] wwtracked.py exited with code {result.returncode}', flush=True)


def run_update_summary():
    cmd = [sys.executable, 'wwtracked.py', '--update-summary']
    print('[scheduler] Updating Summary tab', flush=True)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f'[scheduler] --update-summary exited with code {result.returncode}', flush=True)


def run_update_daily_macros():
    cmd = [sys.executable, 'wwtracked.py', '--update-daily-macros']
    print('[scheduler] Updating Daily Macros tab', flush=True)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f'[scheduler] --update-daily-macros exited with code {result.returncode}', flush=True)


def seconds_until_next_midnight():
    now = datetime.datetime.now()
    tomorrow = (now + datetime.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    offset = random.randint(-1800, 1800)  # ±30 minutes
    delta = (tomorrow - now).total_seconds() + offset
    return max(delta, 60)


def main():
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    run_for_date(yesterday)

    while True:
        wait = seconds_until_next_midnight()
        wake = datetime.datetime.now() + datetime.timedelta(seconds=wait)
        print(f'[scheduler] Next run at {wake.strftime("%Y-%m-%d %H:%M:%S")}', flush=True)
        time.sleep(wait)
        yesterday = (datetime.date.today() - datetime.timedelta(days=1))
        run_for_date(yesterday.isoformat())
        run_update_daily_macros()
        # Sunday = weekday 6 — update summary after capturing the last day of the week
        if yesterday.weekday() == 6:
            run_update_summary()


if __name__ == '__main__':
    main()
