#!/usr/bin/env python3
"""
Create PocketBase collections for the Notification Engine.
Collections: rules, schedules, execution_logs

Usage:
    python create_collections.py
"""

import requests
import sys

PB_URL = "https://pb.dev.industryapps.net/OCCDUBAI"
ADMIN_EMAIL = "abhi-s@industryapps.net"
ADMIN_PASSWORD = "Linux@1994"


def authenticate():
    resp = requests.post(
        f"{PB_URL}/api/admins/auth-with-password",
        json={"identity": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=10,
    )
    resp.raise_for_status()
    token = resp.json()["token"]
    print(f"Authenticated as admin")
    return token


def create_collection(token, schema):
    name = schema["name"]
    resp = requests.post(
        f"{PB_URL}/api/collections",
        headers={"Authorization": token},
        json=schema,
        timeout=10,
    )
    if resp.status_code == 200:
        print(f"  [OK] Collection '{name}' created")
        return True
    elif resp.status_code == 400:
        body = resp.json()
        msg = str(body)
        if "already exists" in msg or "name" in body.get("data", {}):
            print(f"  [SKIP] Collection '{name}' already exists")
            return True
        else:
            print(f"  [FAIL] Collection '{name}': {body}")
            return False
    else:
        print(f"  [FAIL] Collection '{name}': {resp.status_code} {resp.text}")
        return False


COLLECTIONS = [
    {
        "name": "rules",
        "type": "base",
        "schema": [
            {
                "name": "name",
                "type": "text",
                "required": True,
                "options": {"min": 1, "max": 200},
            },
            {
                "name": "engine",
                "type": "text",
                "required": True,
                "options": {"min": 1, "max": 100},
            },
            {
                "name": "frequency",
                "type": "text",
                "required": False,
                "options": {"min": None, "max": 50},
            },
            {
                "name": "channel",
                "type": "text",
                "required": False,
                "options": {"min": None, "max": 20},
            },
            {
                "name": "targets",
                "type": "json",
                "required": False,
                "options": {"maxSize": 2000000},
            },
            {
                "name": "params",
                "type": "json",
                "required": False,
                "options": {"maxSize": 2000000},
            },
            {
                "name": "description",
                "type": "text",
                "required": False,
                "options": {"min": None, "max": 1000},
            },
            {
                "name": "expiry_date",
                "type": "date",
                "required": False,
            },
            {
                "name": "enabled",
                "type": "bool",
                "required": False,
            },
            {
                "name": "state",
                "type": "json",
                "required": False,
                "options": {"maxSize": 2000000},
            },
            {
                "name": "last_run_at",
                "type": "date",
                "required": False,
            },
            {
                "name": "last_status",
                "type": "text",
                "required": False,
                "options": {"min": None, "max": 20},
            },
        ],
    },
    {
        "name": "schedules",
        "type": "base",
        "schema": [
            {
                "name": "rule_id",
                "type": "relation",
                "required": True,
                "options": {
                    "collectionId": "",  # filled dynamically
                    "cascadeDelete": True,
                    "maxSelect": 1,
                },
            },
            {
                "name": "rule_name",
                "type": "text",
                "required": False,
                "options": {"min": None, "max": 200},
            },
            {
                "name": "scheduled_at",
                "type": "date",
                "required": True,
            },
            {
                "name": "status",
                "type": "text",
                "required": False,
                "options": {"min": None, "max": 20},
            },
            {
                "name": "executed_at",
                "type": "date",
                "required": False,
            },
            {
                "name": "events_count",
                "type": "number",
                "required": False,
            },
            {
                "name": "error",
                "type": "text",
                "required": False,
                "options": {"min": None, "max": 2000},
            },
        ],
    },
    {
        "name": "execution_logs",
        "type": "base",
        "schema": [
            {
                "name": "rule_name",
                "type": "text",
                "required": False,
                "options": {"min": None, "max": 200},
            },
            {
                "name": "started_at",
                "type": "date",
                "required": False,
            },
            {
                "name": "finished_at",
                "type": "date",
                "required": False,
            },
            {
                "name": "status",
                "type": "text",
                "required": False,
                "options": {"min": None, "max": 20},
            },
            {
                "name": "events_count",
                "type": "number",
                "required": False,
            },
            {
                "name": "error",
                "type": "text",
                "required": False,
                "options": {"min": None, "max": 2000},
            },
        ],
    },
]


def get_collection_id(token, name):
    resp = requests.get(
        f"{PB_URL}/api/collections/{name}",
        headers={"Authorization": token},
        timeout=10,
    )
    if resp.status_code == 200:
        return resp.json()["id"]
    return None


def main():
    print(f"PocketBase URL: {PB_URL}\n")

    token = authenticate()

    # Create rules first (schedules depends on it)
    print("\nCreating collections...")
    rules_schema = COLLECTIONS[0]
    create_collection(token, rules_schema)

    # Get rules collection ID for the relation field
    rules_id = get_collection_id(token, "rules")
    if not rules_id:
        print("  [ERROR] Could not get 'rules' collection ID")
        sys.exit(1)
    print(f"  Rules collection ID: {rules_id}")

    # Set the relation target for schedules.rule_id
    schedules_schema = COLLECTIONS[1]
    for field in schedules_schema["schema"]:
        if field["name"] == "rule_id":
            field["options"]["collectionId"] = rules_id
    create_collection(token, schedules_schema)

    # Create execution_logs
    create_collection(token, COLLECTIONS[2])

    print("\nDone! Collections ready.")
    print("You can now start the app: uvicorn main:app --reload --port 8000")


if __name__ == "__main__":
    main()
