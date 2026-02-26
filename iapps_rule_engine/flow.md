# iApps Rule Engine — Project Flow

---

## What Is This Project?

This is a **Python Script Scheduler / Rule Engine**.

It lets you:
- Register Python scripts (rules/tasks) with a cron schedule and JSON parameters
- Automatically run those scripts at the scheduled time
- Track every run's success/failure in a SQLite database
- Also manually run scripts interactively whenever you want

Think of it as a **mini cron job manager** where your "rules" are Python scripts.

---

## Project Structure

```
iapps_rule_engine/
│
├── task_scheduler.py       ← MAIN ENTRY POINT (scheduler management)
├── script_runner.py        ← SECONDARY ENTRY POINT (manual/interactive runner)
│
├── scheduler.db            ← SQLite database (auto-created on first run)
│
├── scripts/                ← Your actual task/rule scripts go here
│   ├── sample_task.py      ← Example script (Rule 1)
│   ├── sample_task_2.py    ← Example script (Rule 2)
│   └── backup.py           ← Example script (backup task)
│
└── SCHEDULER_README.md     ← Original documentation
```

---

## Entry Points

| File | Purpose | How to start |
|------|---------|--------------|
| `task_scheduler.py` | Schedule & manage tasks via cron | `python task_scheduler.py run` |
| `script_runner.py` | Manually run scripts interactively | `python script_runner.py -i` |

---

## How the Project Works — Step by Step Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER                                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
          ┌────────────────▼────────────────┐
          │        task_scheduler.py         │
          │        (Entry Point)             │
          └────────────────┬────────────────┘
                           │
          ┌────────────────▼────────────────┐
          │        TaskDatabase              │
          │  - Creates scheduler.db          │
          │  - Tables: scheduled_tasks       │
          │            task_logs             │
          └────────────────┬────────────────┘
                           │
          ┌────────────────▼────────────────┐
          │        TaskScheduler             │
          │  - Reads enabled tasks from DB   │
          │  - Registers cron triggers       │
          │  - Runs APScheduler in background│
          └────────────────┬────────────────┘
                           │  (at scheduled time)
          ┌────────────────▼────────────────┐
          │        _run_task()               │
          │  - Reads script path from DB     │
          │  - Sets TASK_ID + TASK_PARAMS    │
          │    as environment variables      │
          │  - Runs script via subprocess    │
          │  - Logs result to task_logs      │
          └────────────────┬────────────────┘
                           │
          ┌────────────────▼────────────────┐
          │   scripts/your_script.py         │
          │  - Reads TASK_ID from env        │
          │  - Reads TASK_PARAMS (JSON) env  │
          │  - Does the actual work          │
          └─────────────────────────────────┘
```

---

## How Data Flows

```
CLI command
    │
    ▼
task_scheduler.py  ──► TaskDatabase ──► scheduler.db (SQLite)
                              │
                              │  (stores)
                              ▼
                     scheduled_tasks table
                     ┌────────────────────────────────┐
                     │ id | script_path | schedule     │
                     │    | parameters  | enabled      │
                     │    | last_run    | last_status  │
                     └────────────────────────────────┘
                              │
                              │  (on trigger)
                              ▼
                     _run_task() executes script
                              │
                              ▼
                     task_logs table
                     ┌────────────────────────────────┐
                     │ task_id | run_time | status     │
                     │ exit_code | output | error      │
                     └────────────────────────────────┘
```

---

## How to Install & Run

### Step 1 — Install dependency

```bash
pip install apscheduler
```

### Step 2 — Go to the project folder

```bash
cd /home/nived-c/Downloads/iapps_rule_engine/iapps_rule_engine
```

### Step 3 — Add a task (register a script)

```bash
# Register sample_task.py to run every minute (for testing)
python task_scheduler.py -f ./scripts add sample_task.py "* * * * *" \
  --params '{"name": "Alice", "count": 3, "message": "Hello"}' \
  --desc "Test task"
```

### Step 4 — Check registered tasks

```bash
python task_scheduler.py list
```

### Step 5 — Start the scheduler (keep it running)

```bash
python task_scheduler.py -f ./scripts run
```

The scheduler runs in a loop. It will execute scripts automatically at their scheduled times.
Press `Ctrl+C` to stop.

### Step 6 — View execution logs

```bash
# View last 10 logs for task with ID 1
python task_scheduler.py logs 1
```

---

## Manual / Interactive Mode (script_runner.py)

If you just want to run scripts manually without scheduling:

```bash
# Interactive menu — pick and run scripts from ./scripts folder
python script_runner.py ./scripts -i

# Run all scripts at once
python script_runner.py ./scripts -a

# List available scripts
python script_runner.py ./scripts -l

# Run a specific script by name
python script_runner.py ./scripts -r sample_task.py
```

---

## All CLI Commands (task_scheduler.py)

| Command | Description |
|---------|-------------|
| `python task_scheduler.py list` | List all registered tasks |
| `python task_scheduler.py -f ./scripts add <script> "<cron>"` | Register a new task |
| `python task_scheduler.py -f ./scripts run` | Start the scheduler (blocking) |
| `python task_scheduler.py logs <task_id>` | View logs for a task |
| `python task_scheduler.py enable <task_id>` | Enable a task |
| `python task_scheduler.py disable <task_id>` | Disable a task |
| `python task_scheduler.py delete <task_id>` | Delete a task |

Optional flags for all commands:
- `-f ./scripts` — folder where your scripts live (default: `.`)
- `-d scheduler.db` — path to database (default: `scheduler.db`)

---

## Cron Schedule Quick Reference

| Schedule | Meaning |
|----------|---------|
| `* * * * *` | Every minute |
| `*/5 * * * *` | Every 5 minutes |
| `0 9 * * *` | Every day at 9:00 AM |
| `0 2 * * *` | Every day at 2:00 AM |
| `0 */4 * * *` | Every 4 hours |
| `30 2 * * 0` | Every Sunday at 2:30 AM |
| `0 0 1 * *` | First day of every month at midnight |

Format: `minute hour day-of-month month day-of-week`

---

## How to Write Your Own Script (Rule)

Create a `.py` file inside the `scripts/` folder. Parameters are passed as environment variables:

```python
import os
import json

task_id = os.environ.get('TASK_ID')
params = json.loads(os.environ.get('TASK_PARAMS', '{}'))

# Use your params
name = params.get('name', 'default')
print(f"Running task {task_id} for {name}")
```

Then register it:
```bash
python task_scheduler.py -f ./scripts add my_rule.py "0 9 * * *" \
  --params '{"name": "test"}' \
  --desc "My custom rule"
```

---

## Key Classes & Files

| Class / File | Responsibility |
|---|---|
| `TaskDatabase` (task_scheduler.py) | All SQLite read/write operations |
| `TaskScheduler` (task_scheduler.py) | APScheduler setup, cron triggers, task execution |
| `ScriptRunner` (script_runner.py) | Manual script discovery and execution |
| `scripts/` folder | The actual rule/task scripts that do real work |
| `scheduler.db` | SQLite database — auto-created, stores tasks & logs |

---

## Complete Example Workflow

```bash
# 1. Install
pip install apscheduler

# 2. Add two tasks
python task_scheduler.py -f ./scripts add sample_task.py "* * * * *" \
  --params '{"name": "Alice", "count": 2, "message": "Hi"}' --desc "Rule 1"

python task_scheduler.py -f ./scripts add sample_task_2.py "*/2 * * * *" \
  --params '{"name": "Bob", "count": 1, "message": "Hey"}' --desc "Rule 2"

# 3. Verify
python task_scheduler.py list

# 4. Run scheduler
python task_scheduler.py -f ./scripts run

# 5. In another terminal, check logs
python task_scheduler.py logs 1
python task_scheduler.py logs 2
```
