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

    # Credentials come from env (loaded in wwtracked.py via dotenv)
    print(f'[scheduler] Running for {date_str}', flush=True)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f'[scheduler] wwtracked.py exited with code {result.returncode}', flush=True)


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
        today = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        run_for_date(today)


if __name__ == '__main__':
    main()
