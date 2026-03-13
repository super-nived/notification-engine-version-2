#!/usr/bin/env python3
"""
PocketBase Downtime Alert Script
Polls ASWNDUBAI_shift_downtime table and logs new entries to alert log.
Params (via TASK_PARAMS env):
  - pb_url        : PocketBase base URL
  - admin_email   : Admin email
  - admin_password: Admin password
  - collection    : Collection name
  - alert_log     : Path to alert log file
  - state_file    : Path to file storing last seen timestamp
"""

import os
import json
import sys
import requests
from datetime import datetime, timezone
from pathlib import Path


# ── helpers ────────────────────────────────────────────────────────────────────

def get_admin_token(pb_url, email, password):
    resp = requests.post(
        f"{pb_url}/api/admins/auth-with-password",
        json={"identity": email, "password": password},
        timeout=10
    )
    resp.raise_for_status()
    return resp.json()["token"]


def fetch_new_records(pb_url, token, collection, since_timestamp):
    """
    Fetch records created strictly after since_timestamp.
    since_timestamp format: "2026-01-23 05:52:22.173Z"
    """
    filter_str = f'created > "{since_timestamp}"'
    resp = requests.get(
        f"{pb_url}/api/collections/{collection}/records",
        headers={"Authorization": token},
        params={
            "sort": "created",
            "perPage": 100,
            "filter": filter_str
        },
        timeout=10
    )
    resp.raise_for_status()
    return resp.json().get("items", [])


def read_last_seen(state_file):
    """Read last seen timestamp from state file. Returns None if not exists."""
    path = Path(state_file)
    if path.exists():
        ts = path.read_text().strip()
        if ts:
            return ts
    return None


def write_last_seen(state_file, timestamp):
    Path(state_file).write_text(timestamp)


def write_alert(alert_log, record):
    """Append a new alert line to the log file."""
    path = Path(alert_log)
    machines = ", ".join(record.get("machines", [])) or "N/A"
    line = (
        f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}] "
        f"NEW DOWNTIME ENTRY | "
        f"id={record['id']} | "
        f"machines={machines} | "
        f"reason_code={record.get('reason_code', 'N/A')} | "
        f"start_date={record.get('start_date', 'N/A')} | "
        f"end_date={record.get('end_date', 'N/A')} | "
        f"created={record['created']}\n"
    )
    with open(path, "a") as f:
        f.write(line)
    print(line.strip())


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    # Read params from environment (injected by task_scheduler.py)
    raw_params = os.environ.get("TASK_PARAMS", "{}")
    try:
        params = json.loads(raw_params)
    except json.JSONDecodeError:
        print("ERROR: Invalid TASK_PARAMS JSON", file=sys.stderr)
        return 1

    pb_url         = params.get("pb_url",         "https://pb.dev.industryapps.net/ASWN")
    admin_email    = params.get("admin_email",    "abhi-s@industryapps.net")
    admin_password = params.get("admin_password", "Linux@1994")
    collection     = params.get("collection",     "ASWNDUBAI_shift_downtime")
    alert_log      = params.get("alert_log",      "./downtime_alerts.log")
    state_file     = params.get("state_file",     "./downtime_last_seen.txt")

    print(f"[{datetime.now()}] Checking {collection} for new entries...")

    # Step 1: Authenticate
    try:
        token = get_admin_token(pb_url, admin_email, admin_password)
    except Exception as e:
        print(f"ERROR: Auth failed — {e}", file=sys.stderr)
        return 1

    # Step 2: Read last seen timestamp
    last_seen = read_last_seen(state_file)

    if last_seen is None:
        # First run — bootstrap: get the latest record's timestamp and save it
        # so next run onwards we only alert on truly new entries
        resp = requests.get(
            f"{pb_url}/api/collections/{collection}/records",
            headers={"Authorization": token},
            params={"sort": "-created", "perPage": 1},
            timeout=10
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if items:
            last_seen = items[0]["created"]
            write_last_seen(state_file, last_seen)
            print(f"First run — baseline set to: {last_seen}")
        else:
            # Table is empty, set a very old timestamp
            last_seen = "2000-01-01 00:00:00.000Z"
            write_last_seen(state_file, last_seen)
            print("First run — table is empty, waiting for first entry.")
        return 0

    # Step 3: Fetch records newer than last seen
    try:
        new_records = fetch_new_records(pb_url, token, collection, last_seen)
        print("lenght of the recoreds",len(new_records))
    except Exception as e:
        print(f"ERROR: Failed to fetch records — {e}", file=sys.stderr)
        return 1

    if not new_records:
        print(f"No new entries since {last_seen}")
        return 0

    # Step 4: Alert for each new record
    print(f"Found {len(new_records)} new entry/entries!")
    latest_ts = last_seen
    for record in new_records:
        write_alert(alert_log, record)
        # Track the latest created timestamp
        if record["created"] > latest_ts:
            latest_ts = record["created"]

    # Step 5: Update state file to latest seen timestamp
    write_last_seen(state_file, latest_ts)
    print(f"State updated to: {latest_ts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
