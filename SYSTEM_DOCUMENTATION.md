# iApps Notification Engine — System Documentation

## Table of Contents

1. [What This System Does](#1-what-this-system-does)
2. [Architecture Overview](#2-architecture-overview)
3. [Two Execution Modes](#3-two-execution-modes)
4. [Rule Lifecycle — Every Possible Case](#4-rule-lifecycle--every-possible-case)
5. [Engine Types](#5-engine-types)
6. [Frequency Modes Explained](#6-frequency-modes-explained)
7. [How Schedule Records Work](#7-how-schedule-records-work)
8. [How Notifications Are Delivered](#8-how-notifications-are-delivered)
9. [Concurrency — Multiple Rules at the Same Time](#9-concurrency--multiple-rules-at-the-same-time)
10. [Server Startup Flow](#10-server-startup-flow)
11. [Edge Cases and How They Are Handled](#11-edge-cases-and-how-they-are-handled)
12. [PocketBase Collections](#12-pocketbase-collections)
13. [API Endpoints](#13-api-endpoints)
14. [File Structure](#14-file-structure)
15. [Data Flow Diagrams](#15-data-flow-diagrams)

---

## 1. What This System Does

A **rule-based notification engine** that monitors PocketBase collections and sends alerts when conditions are met.

**In simple terms:**
- User creates a rule: "Alert me when OEE drops below 65"
- System watches the data source (PocketBase collection)
- When the condition matches, it sends a notification via In-App (WebSocket), Email, or Both

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        NOTIFICATION ENGINE                               │
│                                                                          │
│  ┌──────────────────────────────┐   ┌──────────────────────────────┐    │
│  │    DISPATCHER (Scheduled)     │   │   SSE LISTENER (Real-Time)   │    │
│  │                               │   │                              │    │
│  │  For: Every 1 Min / Hourly /  │   │  For: "As It Occurs" only    │    │
│  │       Daily / Weekly          │   │                              │    │
│  │                               │   │  PocketBase pushes event     │    │
│  │  1. Creates schedule records  │   │  instantly when new record   │    │
│  │  2. Sleeps until next time    │   │  is inserted                 │    │
│  │  3. Wakes up, runs rule       │   │                              │    │
│  │  4. Sends notification        │   │  Zero delay, zero polling    │    │
│  │                               │   │                              │    │
│  │  If > 5 rules due at once:    │   │  One SSE connection per      │    │
│  │  auto-scales to 5 threads     │   │  collection (shared)         │    │
│  └──────────────────────────────┘   └──────────────────────────────┘    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                     NOTIFICATION DELIVERY                         │   │
│  │                                                                    │   │
│  │  channel = "In-App"  → WebSocket broadcast to all connected UIs   │   │
│  │  channel = "Email"   → Spawns worker thread → SMTP to targets     │   │
│  │  channel = "Both"    → WebSocket + Email (parallel)               │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Two Execution Modes

### Mode A: Scheduled (Every 1 Minute / Hourly / Daily / Weekly)

**How it decides:** If `rule.frequency` is anything other than "As It Occurs", it goes to the Dispatcher.

```
User creates rule with frequency = "Hourly"
  │
  ├─→ System creates schedule records in PocketBase:
  │     2026-03-12 19:00 | pending
  │     2026-03-12 20:00 | pending
  │     2026-03-12 21:00 | pending
  │     ... (all the way to expiry date)
  │
  ├─→ Dispatcher thread sleeps until 19:00
  │
  ├─→ At 19:00, Dispatcher wakes up:
  │     1. Marks schedule as "running"
  │     2. Fetches data from PocketBase collection
  │     3. Checks conditions (threshold, new records, etc.)
  │     4. If match → sends notification
  │     5. Marks schedule as "done"
  │     6. Logs execution in execution_logs
  │
  └─→ Sleeps until 20:00, repeats
```

### Mode B: "As It Occurs" (Real-Time via PocketBase SSE)

**How it decides:** If `rule.frequency == "As It Occurs"`, it goes to the SSE Listener.

```
User creates rule with frequency = "As It Occurs"
  │
  ├─→ NO schedule records created
  │
  ├─→ SSE Listener subscribes to PocketBase collection
  │     (e.g., shift_downtime/*)
  │
  ├─→ When someone inserts a new record in PocketBase:
  │     PocketBase pushes SSE event instantly
  │       │
  │       ├─→ SSE Listener receives event
  │       ├─→ Evaluates rule conditions against the new record
  │       ├─→ If match → sends notification
  │       └─→ Logs execution
  │
  └─→ Zero delay, zero polling, zero schedule records
```

**Note:** SSE requires PocketBase to support `/api/realtime`. If your PocketBase version doesn't support it, use scheduled frequencies instead.

---

## 4. Rule Lifecycle — Every Possible Case

### Case 1: Create a Scheduled Rule

```
POST /api/v1/rules
{
  "name": "CPU Alert",
  "engine": "Threshold Breach",
  "frequency": "Hourly",
  "channel": "Both",
  "targets": ["ops-team", "alice@corp.io"],
  "params": {"condition_field": "oee", "condition_op": "lt", "condition_value": "65"},
  "expiry_date": "2026-03-17"
}
```

**What happens internally:**

```
1. service.create_rule() called
2. Validates engine "Threshold Breach" exists in ENGINE_REGISTRY
3. Creates rule record in PocketBase `rules` collection
4. frequency = "Hourly" → rule_is_scheduled() returns True
5. schedule_generator.generate_schedules() called:
   - Calculates: now to expiry (March 17)
   - Creates 1 schedule record per hour
   - Each record: { rule_id, rule_name, scheduled_at, status: "pending" }
6. dispatcher.wake() called → Dispatcher rechecks for new schedules
7. Returns rule to API response
```

### Case 2: Create an "As It Occurs" Rule

```
POST /api/v1/rules
{
  "name": "New Downtime Alert",
  "engine": "New Downtime Entry",
  "frequency": "As It Occurs",
  "channel": "In-App"
}
```

**What happens internally:**

```
1. service.create_rule() called
2. Validates engine exists
3. Creates rule record in PocketBase
4. frequency = "As It Occurs" → rule_is_as_it_occurs() returns True
5. sse_listener.add_rule(rule) called:
   - Looks up collection from ENGINE_REGISTRY → "shift_downtime"
   - Adds rule to subscriptions for that collection
   - If no listener thread exists for "shift_downtime", starts one
   - SSE thread connects to PocketBase /api/realtime
   - Subscribes to "shift_downtime/*"
6. NO schedule records created
7. Returns rule to API response
```

### Case 3: Pause a Scheduled Rule

```
PATCH /api/v1/rules/{id}/toggle
{ "enabled": false }
```

**What happens:**

```
1. Updates rule in PocketBase: enabled = false
2. frequency is scheduled → skip_pending_schedules_for_rule() called
3. All schedule records with status "pending" → changed to "skipped"
4. Dispatcher ignores skipped schedules
5. Rule stays in DB but does nothing
```

### Case 4: Resume a Scheduled Rule

```
PATCH /api/v1/rules/{id}/toggle
{ "enabled": true }
```

**What happens:**

```
1. Updates rule: enabled = true
2. generate_schedules() called → creates NEW schedule records
   (from now until expiry, skipping any already-existing times)
3. dispatcher.wake() → Dispatcher picks up new schedules
```

### Case 5: Pause an "As It Occurs" Rule

```
1. Updates rule: enabled = false
2. sse_listener.remove_rule(rule) called
3. Rule removed from subscriptions
4. If no other rules listen to that collection → listener thread stops
```

### Case 6: Resume an "As It Occurs" Rule

```
1. Updates rule: enabled = true
2. sse_listener.add_rule(rule) called
3. If listener thread not running for that collection → starts new one
```

### Case 7: Delete a Rule

```
DELETE /api/v1/rules/{id}
```

**What happens:**

```
If scheduled:
  1. Delete ALL schedule records for this rule
  2. Delete rule record

If "As It Occurs":
  1. Remove from SSE listener subscriptions
  2. Stop listener thread if no other rules on same collection
  3. Delete rule record
```

### Case 8: Update a Rule (Change Frequency)

```
PATCH /api/v1/rules/{id}
{ "frequency": "Daily" }  // was "Hourly"
```

**What happens:**

```
1. OLD rule state saved
2. Rule updated in PocketBase
3. Clean up OLD routing:
   - If old was "As It Occurs" → remove from SSE listener
   - If old was scheduled → delete all old schedule records
4. Set up NEW routing:
   - If new is "As It Occurs" → add to SSE listener
   - If new is scheduled → generate new schedule records + wake dispatcher
```

### Case 9: Rule Expires

```
Rule has expiry_date = "2026-03-17T00:00:00Z"
Current time is past March 17.
```

**For scheduled rules:**
```
Dispatcher picks up a due schedule:
  1. Fetches rule, checks expiry
  2. rule_expired() returns True
  3. Marks schedule as "done" with 0 events
  4. Calls disable_rule() → enabled = false
  5. No more schedules will be generated
```

**For "As It Occurs" rules:**
```
SSE event comes in for the collection:
  1. Before evaluating, checks expiry
  2. _rule_expired() returns True
  3. Calls disable_rule() → enabled = false
  4. Skips this rule, logs it
```

---

## 5. Engine Types

Each engine knows its data source, conditions, and what the user can edit:

### Threshold Breach

```
Collection:    production_metrics
Condition:     field <operator> value
User controls: field name, operator (lt/gt/eq/lte/gte), threshold value
Example:       oee < 65
```

**How detection works (scheduled):**
1. Fetch all records from `production_metrics`
2. For each record: check if `record[field] <op> threshold`
3. Return matching records as events

**How evaluation works (SSE):**
1. New record pushed via SSE
2. Check if `record[field] <op> threshold`
3. If match → return event

### New Job Entry

```
Collection:    job_details
Condition:     Field matches specific value
User controls: jobStatus value (e.g., "Released"), customerApproved value (e.g., "YES")
```

**How detection works:**
1. Fetch records created after `state.last_seen` timestamp
2. For each record: check if `jobStatus == "Released"` AND `customerApproved == "YES"`
3. Update `last_seen` to latest record timestamp
4. Return matching records as events

### New Downtime Entry

```
Collection:    shift_downtime
Condition:     Any new record (no filtering)
User controls: None — fully automatic
```

**How detection works:**
1. Fetch records created after `state.last_seen`
2. Every new record is an event (no conditions to check)
3. Update `last_seen`

---

## 6. Frequency Modes Explained

| Frequency | Interval | How It Works | Schedule Records? |
|-----------|----------|--------------|-------------------|
| **As It Occurs** | Instant | PocketBase SSE pushes event when record is created | No |
| **Every 1 Minute** | 1 min | Dispatcher runs rule every minute | Yes — 1 per minute |
| **Hourly** | 60 min | Dispatcher runs rule every hour | Yes — 1 per hour |
| **Daily** | 24 hours | Dispatcher runs rule once per day | Yes — 1 per day |
| **Weekly** | 7 days | Dispatcher runs rule once per week | Yes — 1 per week |

### Schedule Record Counts (example: created March 12, expiry March 17)

| Frequency | Records Created |
|-----------|----------------|
| Every 1 Minute | ~6,120 |
| Hourly | ~102 |
| Daily | ~4 |
| Weekly | ~0 (next slot is past expiry) |

### Rules Without Expiry

If no expiry date is set, the system generates **30 days** of schedule records ahead. The Dispatcher tops up more records as needed.

---

## 7. How Schedule Records Work

### Lifecycle of a Single Schedule Record

```
Created:   { scheduled_at: "2026-03-12 19:00", status: "pending" }
    │
    ├─→ Dispatcher wakes at 19:00
    │
    ├─→ Status: "running"
    │
    ├─→ Rule engine runs, finds 2 matching events
    │
    ├─→ Notifications sent
    │
    └─→ Status: "done", events_count: 2, executed_at: "2026-03-12 19:00:03"
```

### Schedule Status Values

| Status | Meaning |
|--------|---------|
| **pending** | Waiting to be executed |
| **running** | Currently being executed |
| **done** | Successfully completed |
| **failed** | Execution threw an error |
| **skipped** | Rule was paused, schedule was skipped |

### What Happens on Server Restart

```
Server crashes with 3 schedules in "running" status
  │
  └─→ On startup: mark_stale_running_as_failed()
       All "running" → "failed" with error: "Stale: was running when server restarted"
```

---

## 8. How Notifications Are Delivered

### Channel: In-App (WebSocket)

```
Rule triggers → deliver() called
  │
  └─→ websocket_manager.broadcast(event)
       │
       └─→ Sends JSON to every connected browser:
           {
             "rule_name": "CPU Alert",
             "engine": "Threshold Breach",
             "message": "[Threshold Breach] Rule 'CPU Alert' triggered on record abc123",
             "record": { ... full record data ... },
             "timestamp": "2026-03-12T19:00:03Z"
           }
           │
           └─→ Browser shows toast notification in the UI
```

### Channel: Email

```
Rule triggers → deliver() called
  │
  └─→ Spawns a new background thread (non-blocking)
       │
       └─→ For each email target (targets containing @):
           │
           └─→ Connects to SMTP (smtp.office365.com:587 + TLS)
               Sends email:
                 Subject: [Notification] CPU Alert — 2 event(s)
                 Body:
                   Rule: CPU Alert
                   Engine: Threshold Breach
                   Events: 2

                   --- Event 1 ---
                   [Threshold Breach] Rule 'CPU Alert' triggered on record abc123

                   --- Event 2 ---
                   [Threshold Breach] Rule 'CPU Alert' triggered on record def456
```

### Channel: Both

Runs In-App AND Email in parallel. WebSocket is instant (same thread), Email runs in a background thread.

---

## 9. Concurrency — Multiple Rules at the Same Time

### Scheduled Rules: Auto-Scaling

```
Dispatcher checks for due schedules:

If 1-5 schedules due → runs them one-by-one (sequential)
If 6+ schedules due  → runs them in ThreadPoolExecutor(max_workers=5)
                        (5 rules execute in parallel)
```

**Example:** 10 rules all scheduled at 19:00

```
19:00:00 — Dispatcher wakes up, finds 10 due schedules
19:00:00 — ThreadPool starts: rules 1-5 run in parallel
19:00:02 — Rule 1 finishes, rule 6 starts
19:00:03 — Rule 3 finishes, rule 7 starts
...       — continues until all 10 done
```

### SSE Rules: Single Connection, Multiple Rules

```
3 rules all listen to "shift_downtime" collection:
  - Rule A: "New Downtime Alert" (channel: In-App)
  - Rule B: "Downtime Email" (channel: Email)
  - Rule C: "Downtime Urgent" (channel: Both)

Only 1 SSE connection to PocketBase for "shift_downtime"

New record inserted → SSE event received
  → Rule A evaluated → match → WebSocket broadcast
  → Rule B evaluated → match → Email sent
  → Rule C evaluated → match → WebSocket + Email
```

### Email: Non-Blocking

Email delivery always runs in a **separate daemon thread**. It never blocks the Dispatcher or SSE Listener. If SMTP is slow or fails, the main system continues unaffected.

---

## 10. Server Startup Flow

```
uvicorn main:app --port 8000
  │
  ├─→ 1. FastAPI app created
  │
  ├─→ 2. lifespan() starts:
  │     │
  │     ├─→ 3. Configure logging
  │     │
  │     ├─→ 4. authenticate() → PocketBase admin login
  │     │
  │     ├─→ 5. Wire components:
  │     │       set_websocket_manager(ws_manager)
  │     │       set_dispatcher(dispatcher)
  │     │       set_sse_listener(sse_listener)
  │     │
  │     ├─→ 6. Load enabled rules from PocketBase
  │     │       Filter "As It Occurs" rules → load into SSE Listener
  │     │
  │     ├─→ 7. sse_listener.start()
  │     │       Start SSE threads for each subscribed collection
  │     │
  │     ├─→ 8. dispatcher.start()
  │     │       Mark stale "running" schedules as "failed"
  │     │       Generate schedules for all enabled scheduled rules
  │     │       Start dispatcher loop thread
  │     │
  │     └─→ 9. "Notification engine started"
  │
  ├─→ 10. FastAPI serves requests:
  │       GET  /              → UI (index.html)
  │       GET  /api/v1/rules  → List rules
  │       POST /api/v1/rules  → Create rule
  │       WS   /ws/notifications → Real-time events
  │       ...
  │
  └─→ On shutdown:
        dispatcher.stop()
        sse_listener.stop()
        "Notification engine stopped"
```

---

## 11. Edge Cases and How They Are Handled

| Case | What Happens |
|------|--------------|
| **Server crashes mid-execution** | On restart, stale "running" schedules → marked "failed" |
| **Rule created with no params** | Default params applied from ENGINE_REGISTRY |
| **Rule created with no expiry** | Schedules generated for 30 days ahead |
| **Expiry date is in the past** | No schedules generated (end < now), rule does nothing |
| **SSE connection drops** | Auto-reconnects with exponential backoff (1s, 2s, 4s, ... up to 60s) |
| **PocketBase doesn't support SSE** | SSE listener retries indefinitely, scheduled rules still work fine |
| **Multiple rules on same collection** | Single SSE connection shared, all rules fire on each event |
| **10+ rules due at same second** | ThreadPoolExecutor(5) runs them in parallel batches |
| **Email SMTP is down** | Email runs in background thread, logs error, doesn't block anything |
| **SMTP not configured** | Logs warning "SMTP not configured, skipping email", no crash |
| **Rule frequency changed** | Old schedules deleted, new schedules generated |
| **Rule engine changed** | Old routing cleaned up (SSE/schedules), new routing set up |
| **Duplicate schedule times** | generate_schedules() checks existing times, skips duplicates |
| **WebSocket client disconnects** | Removed from active list on next broadcast attempt |
| **No WebSocket clients connected** | Events logged but not lost — email still sends |
| **Rule with no targets and channel=Email** | No emails sent (filter for @ finds nothing) |

---

## 12. PocketBase Collections

### `rules`

| Field | Type | Description |
|-------|------|-------------|
| id | auto | PocketBase record ID |
| name | text | Display name (e.g., "CPU Alert") |
| engine | text | "Threshold Breach" / "New Job Entry" / "New Downtime Entry" |
| frequency | text | "As It Occurs" / "Every 1 Minute" / "Hourly" / "Daily" / "Weekly" |
| channel | text | "In-App" / "Email" / "Both" |
| targets | json | `["ops-team", "alice@corp.io"]` |
| params | json | `{"condition_field": "oee", "condition_op": "lt", "condition_value": "65"}` |
| description | text | What this rule monitors |
| expiry_date | date | When to stop (null = 30 days default) |
| enabled | bool | Active or paused |
| state | json | Runtime state (e.g., `{"last_seen": "2026-03-12T18:00:00Z"}`) |
| last_run_at | date | Last execution timestamp |
| last_status | text | "ok" / "error" |
| created | auto | Creation timestamp |

### `schedules`

| Field | Type | Description |
|-------|------|-------------|
| id | auto | PocketBase record ID |
| rule_id | relation | Link to parent rule |
| rule_name | text | Denormalized for display |
| scheduled_at | date | When to execute |
| status | text | pending / running / done / failed / skipped |
| executed_at | date | When it actually ran |
| events_count | number | Alerts fired |
| error | text | Error message if failed |

### `execution_logs`

| Field | Type | Description |
|-------|------|-------------|
| id | auto | PocketBase record ID |
| rule_name | text | Which rule ran |
| started_at | date | Execution start |
| finished_at | date | Execution end |
| status | text | "ok" / "error" |
| events_count | number | Alerts fired |
| error | text | Error message |

---

## 13. API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Serve the UI (index.html) |
| GET | `/health` | Health check |
| GET | `/api/v1/rules` | List all rules |
| POST | `/api/v1/rules` | Create a new rule |
| GET | `/api/v1/rules/engines` | Get ENGINE_REGISTRY (available engines + params) |
| GET | `/api/v1/rules/logs` | Get execution logs |
| GET | `/api/v1/rules/{id}` | Get a single rule |
| PATCH | `/api/v1/rules/{id}` | Update a rule |
| PATCH | `/api/v1/rules/{id}/toggle` | Enable/disable a rule |
| DELETE | `/api/v1/rules/{id}` | Delete a rule |
| GET | `/api/v1/rules/{id}/schedules` | Get schedule records for a rule |
| WS | `/ws/notifications` | WebSocket for real-time in-app notifications |

---

## 14. File Structure

```
iapps_rule_engine/
├── main.py                              ← FastAPI entry point + WebSocket endpoint
├── index.html                           ← UI (served at /)
├── requirements.txt                     ← Dependencies
├── .env.example                         ← Environment config template
├── create_collections.py                ← Standalone script to create PB collections
│
├── app/
│   ├── core/
│   │   ├── settings.py                  ← Pydantic settings (PB URL, SMTP, etc.)
│   │   └── events.py                    ← Lifespan: startup/shutdown orchestration
│   │
│   ├── db/
│   │   ├── pb_client.py                 ← ALL PocketBase HTTP calls go through here
│   │   └── pb_repositories.py           ← Domain CRUD (rules, schedules, logs)
│   │
│   ├── engine/
│   │   ├── registry.py                  ← ENGINE_REGISTRY + routing helpers
│   │   ├── rule_engine.py               ← detect() for scheduled, evaluate() for SSE
│   │   ├── scheduler.py                 ← Dispatcher class (scheduled rule execution)
│   │   ├── sse_listener.py              ← SSEListener class (real-time PB events)
│   │   ├── schedule_generator.py        ← Creates schedule records
│   │   └── delivery.py                  ← deliver() → WebSocket + Email
│   │
│   ├── features/rules/
│   │   ├── schema.py                    ← Pydantic models (RuleCreate, RuleUpdate, etc.)
│   │   ├── service.py                   ← Business logic (create, toggle, delete, etc.)
│   │   └── router.py                    ← REST API endpoints
│   │
│   ├── notifiers/
│   │   ├── websocket_manager.py         ← WebSocket connection manager
│   │   └── email_notifier.py            ← SMTP email sender
│   │
│   ├── utils/
│   │   └── response.py                  ← Standard success()/error() response format
│   │
│   └── api/
│       └── v1.py                        ← API version router
```

---

## 15. Data Flow Diagrams

### Flow A: Scheduled Rule Execution

```
[Schedule Record: pending, scheduled_at=19:00]
            │
            ▼
[Dispatcher Loop] ─── sleeps until 19:00 ───
            │
            ▼
  Mark schedule "running"
            │
            ▼
  Fetch rule from PocketBase
            │
            ▼
  Check expiry ─── expired? ──→ disable rule, mark done, stop
            │
           no
            ▼
  rule_engine.detect(rule)
            │
            ├─→ Threshold: fetch records, compare field <op> value
            ├─→ New Record: fetch records after last_seen, match params
            │
            ▼
  events[] returned
            │
    ┌───────┴────────────────────────────┐
    │ events empty                       │ events found
    │                                    │
    ▼                                    ▼
  Mark schedule "done"              deliver(rule, events)
  events_count = 0                       │
                                   ┌─────┴──────┐
                                   │             │
                                   ▼             ▼
                             [WebSocket]    [Email Thread]
                             broadcast      SMTP → targets
                                   │             │
                                   ▼             ▼
                             Mark schedule "done"
                             events_count = N
                                   │
                                   ▼
                             Log in execution_logs
```

### Flow B: "As It Occurs" (SSE) Execution

```
[PocketBase: new record inserted in shift_downtime]
            │
            ▼
  PocketBase SSE event pushed
            │
            ▼
[SSE Listener Thread for "shift_downtime"]
            │
            ▼
  For each rule subscribed to this collection:
            │
            ├─→ Check enabled? ─── no → skip
            ├─→ Check expired? ─── yes → disable rule, skip
            │
            ▼
  rule_engine.evaluate(rule, record)
            │
            ├─→ New Record: check param conditions against record fields
            ├─→ Threshold: check field <op> value against record
            │
            ▼
  events[] returned
            │
    ┌───────┴────────────────────────────┐
    │ empty (no match)                   │ match found
    │                                    │
    ▼                                    ▼
  Do nothing                        deliver(rule, events)
                                         │
                                   ┌─────┴──────┐
                                   │             │
                                   ▼             ▼
                             [WebSocket]    [Email Thread]
                                   │
                                   ▼
                             Log in execution_logs
```

### Flow C: Rule Creation Decision Tree

```
POST /api/v1/rules { name, engine, frequency, channel, targets, params, expiry_date }
            │
            ▼
  Validate engine exists in ENGINE_REGISTRY
            │
            ▼
  Apply default params if none provided
            │
            ▼
  Create rule record in PocketBase
            │
            ▼
  ┌─── frequency == "As It Occurs"? ───┐
  │                                     │
 YES                                   NO
  │                                     │
  ▼                                     ▼
SSE Listener                    Schedule Generator
  │                                     │
  ▼                                     ▼
add_rule(rule)                  generate_schedules(rule)
  │                                     │
  ▼                                     ▼
Subscribe to                    Create records from
collection SSE                  now → expiry (or 30 days)
  │                                     │
  ▼                                     ▼
Wait for events                 dispatcher.wake()
```

---

## Running the System

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your PocketBase URL and credentials

# 3. Create PocketBase collections (one-time)
python create_collections.py

# 4. Start the server
uvicorn main:app --reload --port 8000

# 5. Open the UI
# http://localhost:8000
```
