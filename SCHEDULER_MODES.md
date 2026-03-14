# Scheduler Modes — Technical Documentation

## Overview

The notification engine supports two scheduler modes for executing scheduled rules. The mode is controlled via the `SCHEDULER_MODE` environment variable in `.env`.

```env
# Default — efficient, production-ready
SCHEDULER_MODE=next_run

# Old method — bulk schedule records (backward compatibility)
SCHEDULER_MODE=schedule_records
```

Both modes share the same public interface. The service layer does not know which mode is active — it calls the same dispatcher methods regardless.

---

## Mode 1: `next_run` (Default)

### Concept

Each rule stores a single `next_run_at` field. The dispatcher sleeps until the earliest `next_run_at`, executes all due rules, then advances each rule's `next_run_at` by its frequency. No bulk records are created.

### Data Model

```
rules table:
┌──────────┬─────────────────┬───────────┬─────────────────────┐
│ name     │ frequency       │ enabled   │ next_run_at         │
├──────────┼─────────────────┼───────────┼─────────────────────┤
│ CPU Alert│ Every 1 Minute  │ true      │ 2026-03-14 02:05 PM │
│ OEE Check│ Hourly          │ true      │ 2026-03-14 03:00 PM │
│ Weekly   │ Weekly          │ true      │ 2026-03-21 00:00 AM │
└──────────┴─────────────────┴───────────┴─────────────────────┘
```

### How the Dispatcher Loop Works

```
                    ┌──────────────────────────────┐
                    │          START                │
                    └──────────────┬───────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │  Query: earliest rule       │
                    │  WHERE enabled=true         │
                    │  AND next_run_at != ""      │
                    │  ORDER BY next_run_at       │
                    │  LIMIT 1                    │
                    └─────────────┬───────────────┘
                                  │
                         ┌────────▼────────┐
                         │  Rule found?    │
                         └───┬─────────┬───┘
                          NO │         │ YES
                    ┌────────▼──┐  ┌───▼──────────────┐
                    │ Sleep 60s │  │ Calculate wait    │
                    │ then loop │  │ = next_run_at-now │
                    └───────────┘  └───┬──────────────┘
                                      │
                              ┌───────▼───────┐
                              │ wait > 0?     │
                              └──┬─────────┬──┘
                              YES│         │ NO
                         ┌───────▼──┐      │
                         │Sleep wait│      │
                         └───────┬──┘      │
                                 │         │
                    ┌────────────▼─────────▼─────┐
                    │  Query: ALL due rules       │
                    │  WHERE enabled=true         │
                    │  AND next_run_at <= now      │
                    └────────────┬────────────────┘
                                 │
                    ┌────────────▼────────────────┐
                    │  How many due?               │
                    │                              │
                    │  <= 5 → run sequentially     │
                    │  >  5 → ThreadPoolExecutor(5)│
                    └────────────┬────────────────┘
                                 │
                    ┌────────────▼────────────────┐
                    │  For EACH due rule:          │
                    │  1. Check expiry             │
                    │  2. Run engine.detect()      │
                    │  3. If events → deliver()    │
                    │  4. Advance next_run_at      │
                    │  5. Log to execution_logs    │
                    └────────────┬────────────────┘
                                 │
                          (loop back to top)
```

### Rule Lifecycle

#### Create Rule (frequency = "Every 1 Minute")

```
1. User POST /api/v1/rules
2. Service creates rule in PocketBase
3. Service calls dispatcher.on_rule_created(rule)
4. Dispatcher calculates next_run_at = now + 1 minute
5. Dispatcher UPDATE rule SET next_run_at = "2026-03-14 02:01:00"
6. Dispatcher wakes up to check new schedule
```

DB operations: 1 CREATE (rule) + 1 UPDATE (next_run_at) = **2 total**

#### Execute Rule

```
1. Dispatcher wakes at 02:01:00
2. Query: rules WHERE next_run_at <= "02:01:00" AND enabled=true
3. Found "CPU Alert" → check expiry → not expired
4. Run detect() → 3 events found
5. Run deliver() → WebSocket + Email
6. UPDATE rule SET next_run_at = "02:02:00"
7. UPDATE rule SET last_run_at = now, last_status = "ok"
8. CREATE execution_log record
```

DB operations: 1 query + 3 UPDATEs + 1 CREATE = **5 total**

#### Pause Rule

```
1. User PATCH /api/v1/rules/{id}/toggle {enabled: false}
2. Service updates rule enabled=false
3. Service calls dispatcher.on_rule_disabled(rule)
4. Dispatcher UPDATE rule SET next_run_at = ""
```

DB operations: 1 UPDATE (enabled) + 1 UPDATE (next_run_at) = **2 total**

#### Resume Rule

```
1. User PATCH /api/v1/rules/{id}/toggle {enabled: true}
2. Service updates rule enabled=true
3. Service calls dispatcher.on_rule_enabled(rule)
4. Dispatcher calculates next_run_at = now + frequency
5. UPDATE rule SET next_run_at = "2026-03-14 02:15:00"
```

DB operations: 1 UPDATE (enabled) + 1 UPDATE (next_run_at) = **2 total**

#### Delete Rule

```
1. User DELETE /api/v1/rules/{id}
2. Service calls dispatcher.on_rule_deleted(rule) → nothing to clean
3. Service DELETE rule from PocketBase
```

DB operations: **1 DELETE**

#### Expiry Reached

```
1. Dispatcher picks up rule at scheduled time
2. Checks expiry_date → expired!
3. UPDATE rule SET enabled=false
4. UPDATE rule SET next_run_at = ""
5. Rule stops running — no more executions
```

DB operations: **2 UPDATEs**

#### Server Restart

```
1. App starts → dispatcher._init_next_run_for_all()
2. Query all enabled scheduled rules
3. For each rule:
   - Has next_run_at in the past? → Keep it (will execute immediately on next tick)
   - No next_run_at? → Calculate and set one
4. Missed runs execute immediately, then advance to next slot
```

No data loss. No stale records to clean up.

### Scaling: 1-Minute Frequency for 6 Months

```
Old method:  259,200 schedule records to create (~3.6 hours)
next_run:    1 field on the rule (instant)

Old method:  259,200 records to delete on rule deletion
next_run:    1 DELETE (instant)

Old method:  259,200 records to skip on pause
next_run:    1 UPDATE (instant)
```

---

## Mode 2: `schedule_records` (Old Method)

### Concept

When a rule is created, the system generates ALL schedule records from now until expiry (or 30 days for no-expiry rules). Each record is a row in the `schedules` collection with a specific `scheduled_at` time and a `status` field.

### Data Model

```
rules table:
┌──────────┬──────────┬─────────┐
│ name     │ frequency│ enabled │
├──────────┼──────────┼─────────┤
│ CPU Alert│ Hourly   │ true    │
└──────────┴──────────┴─────────┘

schedules table (24 records per day for Hourly):
┌──────────┬─────────────────────┬─────────┬──────────┐
│ rule_id  │ scheduled_at        │ status  │ events   │
├──────────┼─────────────────────┼─────────┼──────────┤
│ r001     │ 2026-03-14 01:00 PM │ done    │ 2        │
│ r001     │ 2026-03-14 02:00 PM │ done    │ 0        │
│ r001     │ 2026-03-14 03:00 PM │ running │ -        │
│ r001     │ 2026-03-14 04:00 PM │ pending │ -        │
│ r001     │ 2026-03-14 05:00 PM │ pending │ -        │
│ ...      │ ...                 │ pending │ -        │
└──────────┴─────────────────────┴─────────┴──────────┘

Schedule statuses: pending → running → done / failed / skipped
```

### How the Dispatcher Loop Works

```
                    ┌──────────────────────────────┐
                    │          START                │
                    │  1. Mark stale running→failed │
                    │  2. Generate all schedules    │
                    └──────────────┬───────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │  Query: next pending        │
                    │  FROM schedules             │
                    │  WHERE status="pending"     │
                    │  ORDER BY scheduled_at      │
                    │  LIMIT 1                    │
                    └─────────────┬───────────────┘
                                  │
                         ┌────────▼────────┐
                         │  Found?         │
                         └───┬─────────┬───┘
                          NO │         │ YES
                    ┌────────▼──┐  ┌───▼──────────────┐
                    │ Sleep 60s │  │ Sleep until       │
                    │ then loop │  │ scheduled_at      │
                    └───────────┘  └───┬──────────────┘
                                      │
                    ┌─────────────────▼──────────────┐
                    │  Query: ALL due schedules       │
                    │  WHERE status="pending"         │
                    │  AND scheduled_at <= now         │
                    └─────────────────┬───────────────┘
                                     │
                    ┌────────────────▼────────────────┐
                    │  For EACH due schedule:          │
                    │  1. Mark status = "running"      │
                    │  2. Fetch parent rule             │
                    │  3. Check expiry                  │
                    │  4. Run engine.detect()           │
                    │  5. If events → deliver()         │
                    │  6. Mark status = "done"/"failed" │
                    │  7. Log to execution_logs         │
                    └────────────────┬────────────────┘
                                     │
                    ┌────────────────▼────────────────┐
                    │  Top up schedules               │
                    │  (for no-expiry rules,           │
                    │   generate more if running low)  │
                    └────────────────┬────────────────┘
                                     │
                              (loop back to top)
```

### Rule Lifecycle

#### Create Rule (frequency = "Hourly", expiry = 30 days)

```
1. User POST /api/v1/rules
2. Service creates rule in PocketBase
3. Service calls dispatcher.on_rule_created(rule)
4. Schedule generator runs:
   - Calculates: 24 records/day × 30 days = 720 records
   - Creates 720 POST requests to PocketBase
   - Each: {rule_id, scheduled_at, status: "pending"}
5. Dispatcher wakes up to check new schedules
```

DB operations: 1 CREATE (rule) + **720 CREATEs** (schedules) = **721 total**

#### Create Rule (frequency = "Every 1 Minute", expiry = 6 months)

```
WARNING: This creates 259,200 schedule records!
- 60 min/hr × 24 hr/day × 180 days = 259,200
- At ~50ms per HTTP POST = ~3.6 hours
- API response blocks until all records are created
```

DB operations: 1 CREATE + **259,200 CREATEs** = **259,201 total**

#### Execute Rule

```
1. Dispatcher wakes at 02:00 PM
2. Query: schedules WHERE status="pending" AND scheduled_at <= now
3. Found schedule s001 → UPDATE status = "running"
4. Fetch parent rule → check expiry → not expired
5. Run detect() → 2 events found
6. deliver() → WebSocket + Email
7. UPDATE schedule SET status="done", events_count=2
8. CREATE execution_log record
```

DB operations: 1 query + 1 rule fetch + 2 UPDATEs + 1 CREATE = **5 total per execution**

#### Pause Rule

```
1. User PATCH /api/v1/rules/{id}/toggle {enabled: false}
2. Service updates rule enabled=false
3. Service calls dispatcher.on_rule_disabled(rule)
4. Query all pending schedules for this rule
5. UPDATE each to status="skipped"
```

DB operations: 1 UPDATE (rule) + **N UPDATEs** (schedules, could be thousands)

#### Resume Rule

```
1. User PATCH /api/v1/rules/{id}/toggle {enabled: true}
2. Service updates rule enabled=true
3. Service calls dispatcher.on_rule_enabled(rule)
4. Regenerate ALL schedule records from now to expiry
```

DB operations: 1 UPDATE (rule) + **N CREATEs** (schedules)

#### Delete Rule

```
1. User DELETE /api/v1/rules/{id}
2. Service calls dispatcher.on_rule_deleted(rule)
3. Query ALL schedules for this rule
4. DELETE each schedule record
5. DELETE rule
```

DB operations: **N DELETEs** (schedules) + 1 DELETE (rule)

#### Server Restart

```
1. App starts
2. Query all schedules WHERE status="running"
3. Mark each as "failed" (stale from crash)
4. Regenerate schedules for all enabled rules
5. Normal loop resumes
```

---

## Side-by-Side Comparison

### DB Operations per Action

| Action | `next_run` | `schedule_records` |
|--------|-----------|-------------------|
| Create rule (Hourly, 30 days) | **2** | **721** |
| Create rule (1 min, 6 months) | **2** | **259,201** |
| Execute 1 rule | **5** | **5** |
| Pause rule | **2** | **1 + N** (N = pending schedules) |
| Resume rule | **2** | **1 + N** (N = new schedules) |
| Delete rule | **1** | **1 + N** (N = all schedules) |
| Server restart | **0** (just re-check) | **N** (mark stale + regenerate) |

### Performance

| Metric | `next_run` | `schedule_records` |
|--------|-----------|-------------------|
| Rule creation time | Instant | Minutes to hours |
| API response time | Fast | Blocks during generation |
| Storage growth | None | Grows with every rule |
| Cleanup needed | No | Yes (old done/failed records) |
| Crash recovery | Automatic | Mark stale + regenerate |

### Features

| Feature | `next_run` | `schedule_records` |
|---------|-----------|-------------------|
| See next run time | Yes (`next_run_at` on rule) | Yes (next pending schedule) |
| See all future runs | No (calculated, not stored) | Yes (all in schedules table) |
| Execution history | Yes (`execution_logs` table) | Yes (`execution_logs` + schedule status) |
| Per-schedule status | No | Yes (pending/running/done/failed/skipped) |

---

## Concurrent Execution (Same for Both Modes)

When multiple rules are due at the same time:

```
10 rules due at 02:00 PM

Check: 10 > CONCURRENT_THRESHOLD (5)?  YES

→ ThreadPoolExecutor(max_workers=5)
→ 5 rules execute in parallel (batch 1)
→ 5 rules execute in parallel (batch 2)
→ All 10 complete
```

```python
CONCURRENT_THRESHOLD = 5

if len(due) <= CONCURRENT_THRESHOLD:
    for rule in due:
        execute(rule)         # sequential
else:
    with ThreadPoolExecutor(5) as pool:
        pool.map(execute, due)  # parallel
```

---

## Common Dispatcher Interface

Both dispatchers implement the same interface. The service layer calls these methods without knowing which mode is active:

```python
class Dispatcher:
    def start(self)                      # Start the dispatch loop
    def stop(self)                       # Stop the dispatch loop
    def wake(self)                       # Wake up to check new rules

    def on_rule_created(self, rule)      # New scheduled rule created
    def on_rule_enabled(self, rule)      # Rule re-enabled
    def on_rule_disabled(self, rule)     # Rule paused
    def on_rule_deleted(self, rule)      # Rule deleted
    def on_rule_updated(self, rule)      # Rule config changed
```

### Service Layer (mode-agnostic)

```python
# service.py — same code works for both modes
def create_rule(data):
    rule = repo.create_rule(data)
    if rule_is_scheduled(rule):
        _dispatcher.on_rule_created(rule)   # dispatcher handles the rest
    return rule

def toggle_rule(rule_id, enabled):
    rule = repo.update_rule(rule_id, {"enabled": enabled})
    if enabled:
        _dispatcher.on_rule_enabled(rule)
    else:
        _dispatcher.on_rule_disabled(rule)
    return rule
```

---

## Switching Modes

### From `schedule_records` to `next_run`

1. Stop the app
2. Change `.env`: `SCHEDULER_MODE=next_run`
3. Start the app
4. The `next_run` dispatcher initializes `next_run_at` for all enabled rules
5. Old schedule records in the `schedules` table are ignored (not deleted)
6. Optionally: clear the `schedules` table manually if you want to free space

### From `next_run` to `schedule_records`

1. Stop the app
2. Change `.env`: `SCHEDULER_MODE=schedule_records`
3. Start the app
4. The `schedule_records` dispatcher generates schedule records for all enabled rules
5. `next_run_at` field on rules is ignored

---

## File Structure

```
app/engine/
├── scheduler.py                       ← Factory: picks dispatcher by SCHEDULER_MODE
├── dispatcher_next_run.py             ← Default mode (next_run_at on rules)
├── dispatcher_schedule_records.py     ← Old mode (standalone, removable in future)
└── schedule_generator.py              ← Only used by schedule_records mode
```

### Removing the Old Method (Future)

When you no longer need `schedule_records` mode:

1. Delete `app/engine/dispatcher_schedule_records.py`
2. Delete `app/engine/schedule_generator.py`
3. Remove the `schedule_records` branch from `app/engine/scheduler.py`
4. Optionally: drop the `schedules` collection from PocketBase
5. Remove schedule-related functions from `pb_repositories.py`

The rest of the app continues to work unchanged.

---

## Expiry Handling (Same for Both Modes)

```
Rule: "CPU Alert", frequency: Every 1 Minute, expiry: 2026-06-14

Dispatcher picks up rule at each scheduled time:
  1. Check: is expiry_date < now?
  2. NO  → execute normally
  3. YES → disable rule, stop scheduling

After expiry:
  next_run mode:         UPDATE rule SET enabled=false, next_run_at=""
  schedule_records mode: UPDATE rule SET enabled=false (no new schedules generated)
```

No manual intervention needed. The rule auto-disables when expiry is reached.

---

## Recommendation

Use `next_run` (default) for all new deployments. It is:

- Faster (instant rule creation vs minutes/hours)
- Lighter (no storage growth)
- Simpler (no cleanup, no stale records)
- Crash-safe (automatic recovery)
- Scalable (1-minute frequency for 6 months = same cost as weekly)

Use `schedule_records` only if you specifically need to see all future scheduled times in a table view.
