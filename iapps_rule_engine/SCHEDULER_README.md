# Task Scheduler for Python Scripts

A comprehensive scheduler system for running Python scripts with configurable parameters stored in SQLite database.

## Features

- **SQLite Database**: Stores tasks with cron schedules and JSON parameters
- **Background Scheduler**: Uses APScheduler for reliable task execution
- **Parameter Management**: Pass JSON parameters to scripts via environment variables
- **Execution Logging**: Tracks all executions with status, exit codes, and output
- **CLI Management**: Add, delete, enable/disable tasks from command line
- **Flexible Scheduling**: Uses standard cron syntax for scheduling

## Installation

```bash
pip install apscheduler
```

## Database Schema

### scheduled_tasks table
- `id`: Task ID (primary key)
- `script_name`: Name of the script
- `script_path`: Path to the script file
- `schedule`: Cron schedule string (e.g., "0 9 * * *")
- `parameters`: JSON object with script parameters
- `enabled`: Boolean flag to enable/disable task
- `created_at`: Task creation timestamp
- `last_run`: Last execution timestamp
- `last_status`: Status of last execution (SUCCESS, FAILED, ERROR, TIMEOUT)
- `description`: Task description

### task_logs table
- `id`: Log entry ID
- `task_id`: Reference to scheduled_tasks
- `run_time`: When the task ran
- `status`: Execution status
- `exit_code`: Process exit code
- `output`: stdout from the script
- `error`: stderr or error message

## Usage

### Add a Task

```bash
# Basic task (daily at 9 AM)
python task_scheduler.py -f ./scripts add my_script.py "0 9 * * *"

# With parameters
python task_scheduler.py -f ./scripts add backup.py "0 2 * * *" \
  --params '{"path": "/data", "format": "zip"}' \
  --desc "Daily database backup"

# Every 30 minutes
python task_scheduler.py add process.py "*/30 * * * *"
```

### List Tasks

```bash
python task_scheduler.py list
```

Output:
```
Scheduled Tasks:
ID    Script               Schedule             Enabled    Last Run
1     my_script.py         0 9 * * *            Yes        2026-01-21 09:00:00
2     backup.py            0 2 * * *            Yes        Never
```

### View Task Logs

```bash
# View last 10 logs for task 1
python task_scheduler.py logs 1

# View last 20 logs
python task_scheduler.py logs 1 --limit 20
```

### Enable/Disable Tasks

```bash
python task_scheduler.py enable 1
python task_scheduler.py disable 2
```

### Delete a Task

```bash
python task_scheduler.py delete 1
```

### Run the Scheduler

```bash
python task_scheduler.py -f ./scripts run
```

This starts the scheduler that continuously monitors and executes tasks.

## Cron Schedule Examples

```
0 9 * * *        - Every day at 9:00 AM
0 */4 * * *      - Every 4 hours
30 2 * * 0       - Every Sunday at 2:30 AM
0 0 1 * *        - First day of every month at midnight
*/15 * * * *     - Every 15 minutes
0 9-17 * * 1-5   - Every hour from 9 AM to 5 PM on weekdays
```

## Accessing Parameters in Your Script

Parameters are passed as environment variables:

```python
import os
import json

# Get parameters from environment
task_id = os.environ.get('TASK_ID')
params = json.loads(os.environ.get('TASK_PARAMS', '{}'))

backup_path = params.get('path', '/default/path')
format_type = params.get('format', 'tar')

print(f"Running task {task_id} with backup path: {backup_path}")
```

## Example Workflow

```bash
# Initialize and add tasks
python task_scheduler.py -d ~/scheduler.db add backup.py "0 2 * * *" \
  --params '{"dest": "/backups"}' \
  --desc "Nightly backup"

python task_scheduler.py -d ~/scheduler.db add cleanup.py "0 3 * * 0" \
  --params '{"days": 30}' \
  --desc "Weekly cleanup"

# List all tasks
python task_scheduler.py -d ~/scheduler.db list

# Run the scheduler
python task_scheduler.py -d ~/scheduler.db -f ./scripts run

# In another terminal, view logs
python task_scheduler.py -d ~/scheduler.db logs 1 --limit 5
```

## Integration with Script Runner

Use alongside `script_runner.py` for flexible script management:

```bash
# Run scripts manually
python script_runner.py -i

# Or schedule them
python task_scheduler.py add my_script.py "0 9 * * *"
```

## Error Handling

- **Timeout**: Tasks exceeding 5 minutes (300 seconds) are automatically terminated
- **Invalid Parameters**: JSON parsing errors are logged and task continues
- **Missing Scripts**: Logged as errors; scheduler continues with other tasks
- **Cron Syntax**: Invalid cron schedules prevent task scheduling

All errors are logged in the database for auditing and debugging.

## Database Maintenance

View the raw database:
```bash
sqlite3 scheduler.db "SELECT * FROM scheduled_tasks;"
sqlite3 scheduler.db "SELECT * FROM task_logs ORDER BY run_time DESC LIMIT 10;"
```

Clean up old logs:
```sql
DELETE FROM task_logs WHERE run_time < datetime('now', '-30 days');
```
