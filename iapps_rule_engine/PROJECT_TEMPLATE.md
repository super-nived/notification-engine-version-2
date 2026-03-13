# Notification Rule Engine — Project Blueprint

## What This App Is

A **scalable rule-based notification engine** that:
- Connects to multiple data sources (PocketBase, SQL Server, MongoDB, etc.)
- Runs detection rules on a schedule
- Each rule detects a specific condition (new downtime, machine stopped, job conflict, etc.)
- When condition is met → triggers one or more notifications (email, webhook, log, desktop, etc.)
- Managed via a FastAPI REST API

---

## Core Concepts

```
DATA SOURCE          DETECTOR (Rule)         NOTIFIER
─────────────        ───────────────         ────────────────
PocketBase    ──►    NewDowntimeRule   ──►   EmailNotifier
SQL Server    ──►    MachineStopRule   ──►   WebhookNotifier
MongoDB       ──►    JobConflictRule   ──►   LogNotifier
                                      ──►   DesktopNotifier
```

One rule can trigger **multiple notifiers**.
One notifier can be used by **many rules**.
Data sources are **pluggable** — swap or add without touching rules.

---

## Recommended Project Structure

```
notification_engine/
│
├── main.py                         ← FastAPI app entry point
├── scheduler.py                    ← APScheduler setup, loads & runs rules
├── config.yaml                     ← Central config: rules, schedules, notifiers
│
├── core/
│   ├── __init__.py
│   ├── base_rule.py                ← Abstract base class for all rules
│   ├── base_notifier.py            ← Abstract base class for all notifiers
│   └── base_datasource.py          ← Abstract base class for all data sources
│
├── datasources/
│   ├── __init__.py
│   ├── pocketbase.py               ← PocketBase connector
│   ├── sqlserver.py                ← SQL Server connector
│   └── mongodb.py                  ← MongoDB connector
│
├── rules/
│   ├── __init__.py
│   ├── new_downtime_rule.py        ← Detects new downtime entries
│   ├── machine_stop_rule.py        ← Detects machines that stopped
│   └── job_conflict_rule.py        ← Detects job schedule conflicts
│
├── notifiers/
│   ├── __init__.py
│   ├── email_notifier.py           ← Send email
│   ├── webhook_notifier.py         ← POST to Slack / Teams / custom URL
│   ├── log_notifier.py             ← Write to log file
│   └── desktop_notifier.py         ← OS desktop popup
│
├── api/
│   ├── __init__.py
│   ├── routes/
│   │   ├── rules.py                ← CRUD for rules via REST
│   │   ├── logs.py                 ← View execution logs
│   │   └── health.py               ← Health check endpoint
│   └── models.py                   ← Pydantic request/response models
│
├── db/
│   ├── __init__.py
│   ├── engine.py                   ← SQLite setup (internal app DB)
│   └── models.py                   ← SQLAlchemy models (rules, logs)
│
├── state/                          ← Runtime state files (last seen timestamps)
│   └── .gitkeep
│
├── logs/                           ← Alert log output files
│   └── .gitkeep
│
├── tests/
│   ├── test_rules.py
│   ├── test_notifiers.py
│   └── test_datasources.py
│
├── .env                            ← Secrets (DB credentials, API keys)
├── .env.example                    ← Template for .env (commit this, not .env)
├── .gitignore
├── requirements.txt
└── README.md
```

---

## How It All Connects

```
┌─────────────────────────────────────────────────────┐
│                    FastAPI (main.py)                 │
│   POST /rules     GET /rules     DELETE /rules/{id}  │
│   GET /logs       GET /health                        │
└──────────────────────┬──────────────────────────────┘
                       │ manages
┌──────────────────────▼──────────────────────────────┐
│                  Scheduler (scheduler.py)             │
│   APScheduler — loads enabled rules from DB          │
│   Runs each rule at its configured cron schedule     │
└──────────────────────┬──────────────────────────────┘
                       │ runs
┌──────────────────────▼──────────────────────────────┐
│                   Rule (rules/*.py)                  │
│   1. Get data source connection                      │
│   2. Fetch records / detect condition                │
│   3. If triggered → send to notifier(s)              │
│   4. Save result to internal DB (logs)               │
└──────┬───────────────────────────┬──────────────────┘
       │                           │
┌──────▼──────┐           ┌────────▼────────┐
│  DataSource │           │    Notifiers    │
│  (read DB)  │           │  email/webhook/ │
│  PocketBase │           │  log/desktop    │
│  SQL Server │           └─────────────────┘
│  MongoDB    │
└─────────────┘
```

---

## Key Design Patterns

### 1. Base Rule (every rule follows this contract)

```python
# core/base_rule.py
from abc import ABC, abstractmethod

class BaseRule(ABC):
    name: str           # unique rule name
    description: str    # what this rule detects
    notifiers: list     # list of notifier instances

    @abstractmethod
    def detect(self) -> list[dict]:
        """Fetch data and return list of triggered events. Empty = nothing new."""
        pass

    def run(self):
        events = self.detect()
        for event in events:
            for notifier in self.notifiers:
                notifier.send(event)
```

### 2. Base Notifier

```python
# core/base_notifier.py
from abc import ABC, abstractmethod

class BaseNotifier(ABC):
    @abstractmethod
    def send(self, event: dict):
        """Send notification for this event."""
        pass
```

### 3. Base DataSource

```python
# core/base_datasource.py
from abc import ABC, abstractmethod

class BaseDataSource(ABC):
    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def fetch(self, query: dict) -> list[dict]:
        pass
```

---

## config.yaml Structure

```yaml
rules:
  - name: new_downtime_alert
    class: rules.new_downtime_rule.NewDowntimeRule
    schedule: "* * * * *"        # every minute
    enabled: true
    datasource:
      type: pocketbase
      url: https://pb.dev.industryapps.net/ASWN
      collection: ASWNDUBAI_shift_downtime
    notifiers:
      - type: log
        path: ./logs/downtime.log
      - type: email
        to: engineer@company.com
        subject: "New Downtime Detected"
      - type: webhook
        url: https://hooks.slack.com/your-slack-url

  - name: machine_stop_alert
    class: rules.machine_stop_rule.MachineStopRule
    schedule: "*/2 * * * *"
    enabled: true
    datasource:
      type: sqlserver
      connection_string: "mssql+pyodbc://..."
      query: "SELECT * FROM machines WHERE status='stopped'"
    notifiers:
      - type: log
        path: ./logs/machine_stop.log
      - type: webhook
        url: https://hooks.slack.com/your-slack-url
```

---

## FastAPI Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Check if app is running |
| `GET` | `/rules` | List all rules |
| `POST` | `/rules` | Add a new rule |
| `PATCH` | `/rules/{id}/enable` | Enable a rule |
| `PATCH` | `/rules/{id}/disable` | Disable a rule |
| `DELETE` | `/rules/{id}` | Delete a rule |
| `GET` | `/logs` | View all execution logs |
| `GET` | `/logs/{rule_name}` | View logs for a specific rule |

---

## .env.example

```env
# PocketBase
PB_URL=https://pb.dev.industryapps.net/ASWN
PB_ADMIN_EMAIL=your-email@company.com
PB_ADMIN_PASSWORD=your-password

# SQL Server
SQLSERVER_CONNECTION_STRING=mssql+pyodbc://user:pass@host/db

# MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_DB=your_db

# Email (SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=your-app-password

# App
APP_PORT=8000
APP_ENV=development
```

---

## requirements.txt

```
fastapi
uvicorn
apscheduler
sqlalchemy
pydantic
pydantic-settings
python-dotenv
requests
pyyaml

# Data sources (install what you need)
pyodbc              # SQL Server
pymongo             # MongoDB
```

---

## How to Run

```bash
# 1. Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# edit .env with your credentials

# 3. Start the app (FastAPI + Scheduler together)
uvicorn main:app --reload --port 8000
```

The scheduler starts automatically when FastAPI starts.
Visit `http://localhost:8000/docs` for the interactive API.

---

## How to Add a New Rule (in future)

1. Create `rules/your_rule.py` extending `BaseRule`
2. Implement the `detect()` method — connect to your data source, return events
3. Add entry in `config.yaml` with schedule + notifiers
4. That's it — scheduler picks it up automatically

---

## Internal Database (SQLite — app's own DB)

Stores:
- `rules` table — registered rules, schedules, enabled/disabled
- `execution_logs` table — every run result (success/fail/triggered/nothing)
- `state` table — last seen timestamps per rule (replaces flat .txt files)

---

## Summary: What Makes This Scalable

| Problem | Solution |
|---------|----------|
| New data source | Add a file in `datasources/`, implement `BaseDataSource` |
| New notification type | Add a file in `notifiers/`, implement `BaseNotifier` |
| New detection rule | Add a file in `rules/`, implement `BaseRule` |
| Manage via UI/API | FastAPI REST endpoints |
| Multiple notifiers per rule | `notifiers` list in config.yaml |
| Secrets management | `.env` file via `pydantic-settings` |
| Track what was already alerted | State stored in internal SQLite DB |
