#!/usr/bin/env python3
"""
Create PocketBase collections for the Notification Engine.
Collections: rules, execution_logs

Usage:
    python create_collections.py
"""

import requests
import sys

PB_URL = "http://127.0.0.1:8090"
ADMIN_EMAIL = "abhi-s@industryapps.net"
ADMIN_PASSWORD = "Linux@1994"


def authenticate():
    resp = requests.post(
        f"{PB_URL}/api/collections/_superusers/auth-with-password",
        json={
            "identity": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
        },
        timeout=10,
    )
    resp.raise_for_status()
    token = resp.json()["token"]
    print("Authenticated as admin")
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
    if resp.status_code == 400:
        body = resp.json()
        if _already_exists(body):
            print(f"  [SKIP] Collection '{name}' already exists")
            return True
        print(f"  [FAIL] Collection '{name}': {body}")
        return False
    print(f"  [FAIL] Collection '{name}': {resp.status_code}")
    return False


def _already_exists(body: dict) -> bool:
    msg = str(body)
    return "already exists" in msg or "name" in body.get("data", {})


RULES_SCHEMA = {
    "name": "rules",
    "type": "base",
    "fields": [
        {"name": "name", "type": "text", "required": True, "presentable": True, "unique": False,
         "options": {"min": 1, "max": 200, "pattern": ""}},
        {"name": "engine", "type": "text", "required": True, "presentable": True, "unique": False,
         "options": {"min": 1, "max": 100, "pattern": ""}},
        {"name": "frequency", "type": "text", "required": False, "presentable": True, "unique": False,
         "options": {"min": 0, "max": 50, "pattern": ""}},
        {"name": "channel", "type": "text", "required": False, "presentable": True, "unique": False,
         "options": {"min": 0, "max": 20, "pattern": ""}},
        {"name": "targets", "type": "json", "required": False, "presentable": True, "unique": False,
         "options": {"maxSize": 2000000}},
        {"name": "params", "type": "json", "required": False, "presentable": False, "unique": False,
         "options": {"maxSize": 2000000}},
        {"name": "description", "type": "text", "required": False, "presentable": True, "unique": False,
         "options": {"min": 0, "max": 1000, "pattern": ""}},
        {"name": "expiry_date", "type": "date", "required": False, "presentable": True, "unique": False,
         "options": {}},
        {"name": "enabled", "type": "bool", "required": False, "presentable": True, "unique": False,
         "options": {}},
        {"name": "state", "type": "json", "required": False, "presentable": False, "unique": False,
         "options": {"maxSize": 2000000}},
        {"name": "last_run_at", "type": "date", "required": False, "presentable": True, "unique": False,
         "options": {}},
        {"name": "last_status", "type": "text", "required": False, "presentable": True, "unique": False,
         "options": {"min": 0, "max": 20, "pattern": ""}},
        {"name": "next_run_at", "type": "date", "required": False, "presentable": True, "unique": False,
         "options": {}},
    ],
}

EXECUTION_LOGS_SCHEMA = {
    "name": "execution_logs",
    "type": "base",
    "fields": [
        {"name": "rule_name", "type": "text", "required": False, "presentable": True, "unique": False,
         "options": {"min": 0, "max": 200, "pattern": ""}},
        {"name": "started_at", "type": "date", "required": False, "presentable": True, "unique": False,
         "options": {}},
        {"name": "finished_at", "type": "date", "required": False, "presentable": True, "unique": False,
         "options": {}},
        {"name": "status", "type": "text", "required": False, "presentable": True, "unique": False,
         "options": {"min": 0, "max": 20, "pattern": ""}},
        {"name": "events_count", "type": "number", "required": False, "presentable": True, "unique": False,
         "options": {}},
        {"name": "error", "type": "text", "required": False, "presentable": False, "unique": False,
         "options": {"min": 0, "max": 2000, "pattern": ""}},
    ],
}


def main():
    print(f"PocketBase URL: {PB_URL}\n")
    token = authenticate()

    print("\nCreating collections...")
    create_collection(token, RULES_SCHEMA)
    create_collection(token, EXECUTION_LOGS_SCHEMA)

    print("\nDone! Collections ready.")
    print("Start the app: uvicorn main:app --reload --port 8000")


if __name__ == "__main__":
    main()
