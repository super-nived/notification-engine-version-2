#!/usr/bin/env python3
"""
Task Scheduler for Python Scripts
Manages scheduled execution of Python scripts with JSON parameters
"""

import sqlite3
import json
import sys
import os
from pathlib import Path
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import subprocess


class TaskDatabase:
    """Manages SQLite database for scheduled tasks"""
    
    def __init__(self, db_path="scheduler.db"):
        self.db_path = Path(db_path)
        self.init_db()
    
    def init_db(self):
        """Initialize database schema"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    script_name TEXT NOT NULL,
                    script_path TEXT NOT NULL,
                    schedule TEXT NOT NULL,
                    parameters TEXT,
                    enabled BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_run TIMESTAMP,
                    last_status TEXT,
                    description TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS task_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    run_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT NOT NULL,
                    exit_code INTEGER,
                    output TEXT,
                    error TEXT,
                    FOREIGN KEY (task_id) REFERENCES scheduled_tasks (id)
                )
            ''')
            conn.commit()
    
    def add_task(self, script_name, script_path, schedule, parameters=None, description=""):
        """Add a new scheduled task"""
        params_json = json.dumps(parameters) if parameters else None
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO scheduled_tasks 
                (script_name, script_path, schedule, parameters, description)
                VALUES (?, ?, ?, ?, ?)
            ''', (script_name, script_path, schedule, params_json, description))
            conn.commit()
            return cursor.lastrowid
    
    def get_all_tasks(self):
        """Get all tasks"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM scheduled_tasks ORDER BY id')
            return cursor.fetchall()
    
    def get_enabled_tasks(self):
        """Get only enabled tasks"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM scheduled_tasks WHERE enabled = 1')
            return cursor.fetchall()
    
    def get_task(self, task_id):
        """Get a specific task"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM scheduled_tasks WHERE id = ?', (task_id,))
            return cursor.fetchone()
    
    def update_task(self, task_id, **kwargs):
        """Update task details"""
        allowed_fields = {'schedule', 'parameters', 'enabled', 'description'}
        fields = {k: v for k, v in kwargs.items() if k in allowed_fields}
        
        if 'parameters' in fields and fields['parameters']:
            fields['parameters'] = json.dumps(fields['parameters'])
        
        if not fields:
            return
        
        set_clause = ', '.join(f"{k} = ?" for k in fields.keys())
        values = list(fields.values()) + [task_id]
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f'UPDATE scheduled_tasks SET {set_clause} WHERE id = ?', values)
            conn.commit()
    
    def delete_task(self, task_id):
        """Delete a task"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('DELETE FROM scheduled_tasks WHERE id = ?', (task_id,))
            conn.execute('DELETE FROM task_logs WHERE task_id = ?', (task_id,))
            conn.commit()
    
    def log_execution(self, task_id, status, exit_code=None, output="", error=""):
        """Log task execution"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO task_logs (task_id, status, exit_code, output, error)
                VALUES (?, ?, ?, ?, ?)
            ''', (task_id, status, exit_code, output, error))
            
            # Update last_run and last_status
            cursor.execute('''
                UPDATE scheduled_tasks 
                SET last_run = CURRENT_TIMESTAMP, last_status = ?
                WHERE id = ?
            ''', (status, task_id))
            conn.commit()
    
    def get_task_logs(self, task_id, limit=10):
        """Get execution logs for a task"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM task_logs 
                WHERE task_id = ? 
                ORDER BY run_time DESC 
                LIMIT ?
            ''', (task_id, limit))
            return cursor.fetchall()


class TaskScheduler:
    """Manages scheduled task execution"""
    
    def __init__(self, db_path="scheduler.db", script_folder="."):
        self.db = TaskDatabase(db_path)
        self.script_folder = Path(script_folder)
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
    
    def schedule_task(self, task_id):
        """Schedule a single task"""
        task = self.db.get_task(task_id)
        if not task:
            print(f"Task {task_id} not found")
            return
        
        if not task['enabled']:
            print(f"Task {task_id} is disabled")
            return
        
        # Parse schedule string (cron format)
        try:
            trigger = CronTrigger.from_crontab(task['schedule'])
        except Exception as e:
            print(f"Invalid cron schedule for task {task_id}: {e}")
            return
        
        # Add job to scheduler
        job_id = f"task_{task_id}"
        self.scheduler.add_job(
            self._run_task,
            trigger=trigger,
            args=[task_id],
            id=job_id,
            replace_existing=True,
            name=task['script_name']
        )
        print(f"Scheduled task {task_id}: {task['script_name']} ({task['schedule']})")
    
    def schedule_all(self):
        """Schedule all enabled tasks"""
        tasks = self.db.get_enabled_tasks()
        for task in tasks:
            self.schedule_task(task['id'])
        print(f"Scheduled {len(tasks)} tasks")
    
    def _run_task(self, task_id):
        """Execute a task"""
        task = self.db.get_task(task_id)
        script_path = self.script_folder / task['script_path']
        
        print(f"[{datetime.now()}] Running task {task_id}: {task['script_name']}")
        
        # Prepare parameters
        params = {}
        if task['parameters']:
            try:
                params = json.loads(task['parameters'])
            except json.JSONDecodeError:
                print(f"Invalid JSON parameters for task {task_id}")
        
        try:
            # Run the script with parameters passed as environment variables
            env = {
                'TASK_ID': str(task_id),
                'TASK_PARAMS': json.dumps(params)
            }
            
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=300,
                env={**os.environ, **env}
            )
            
            # Print stdout to scheduler console
            if result.stdout:
                print(result.stdout, end='')
            
            status = "SUCCESS" if result.returncode == 0 else "FAILED"
            self.db.log_execution(
                task_id,
                status,
                result.returncode,
                result.stdout,
                result.stderr
            )
            
            if result.returncode != 0:
                print(f"Task {task_id} failed with exit code {result.returncode}")
                if result.stderr:
                    print(f"Error: {result.stderr}")
        
        except subprocess.TimeoutExpired:
            self.db.log_execution(task_id, "TIMEOUT", -1, "", "Script execution timeout")
            print(f"Task {task_id} timed out")
        except Exception as e:
            self.db.log_execution(task_id, "ERROR", -1, "", str(e))
            print(f"Error running task {task_id}: {e}")
    
    def list_jobs(self):
        """List all scheduled jobs"""
        jobs = self.scheduler.get_jobs()
        if not jobs:
            print("No scheduled jobs")
            return
        
        print(f"\nScheduled Jobs ({len(jobs)}):")
        print("-" * 70)
        for job in jobs:
            print(f"ID: {job.id}")
            print(f"  Name: {job.name}")
            print(f"  Trigger: {job.trigger}")
            print(f"  Next run: {job.next_run_time}")
            print()
    
    def pause_scheduler(self):
        """Pause the scheduler"""
        self.scheduler.pause()
        print("Scheduler paused")
    
    def resume_scheduler(self):
        """Resume the scheduler"""
        self.scheduler.resume()
        print("Scheduler resumed")
    
    def stop_scheduler(self):
        """Stop the scheduler"""
        self.scheduler.shutdown()
        print("Scheduler stopped")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Schedule and run Python scripts with JSON parameters"
    )
    parser.add_argument(
        "-f", "--folder",
        default=".",
        help="Folder containing scripts"
    )
    parser.add_argument(
        "-d", "--db",
        default="scheduler.db",
        help="Path to SQLite database"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Add task command
    add_parser = subparsers.add_parser("add", help="Add a new scheduled task")
    add_parser.add_argument("script", help="Script name/path")
    add_parser.add_argument("schedule", help="Cron schedule (e.g., '0 9 * * *' for daily at 9 AM)")
    add_parser.add_argument("--params", help="JSON parameters for the script")
    add_parser.add_argument("--desc", help="Task description")
    
    # List tasks command
    subparsers.add_parser("list", help="List all tasks")
    
    # Delete task command
    delete_parser = subparsers.add_parser("delete", help="Delete a task")
    delete_parser.add_argument("task_id", type=int, help="Task ID to delete")
    
    # Enable/disable task command
    enable_parser = subparsers.add_parser("enable", help="Enable a task")
    enable_parser.add_argument("task_id", type=int, help="Task ID to enable")
    
    disable_parser = subparsers.add_parser("disable", help="Disable a task")
    disable_parser.add_argument("task_id", type=int, help="Task ID to disable")
    
    # Show logs command
    logs_parser = subparsers.add_parser("logs", help="Show task execution logs")
    logs_parser.add_argument("task_id", type=int, help="Task ID")
    logs_parser.add_argument("--limit", type=int, default=10, help="Number of logs to show")
    
    # Run scheduler command
    subparsers.add_parser("run", help="Run the scheduler (blocking)")
    
    args = parser.parse_args()
    
    db = TaskDatabase(args.db)
    scheduler = TaskScheduler(args.db, args.folder)
    
    if args.command == "add":
        params = None
        if args.params:
            try:
                params = json.loads(args.params)
            except json.JSONDecodeError:
                print("Invalid JSON parameters")
                return
        
        task_id = db.add_task(
            Path(args.script).stem,
            args.script,
            args.schedule,
            params,
            args.desc or ""
        )
        print(f"Task added with ID: {task_id}")
    
    elif args.command == "list":
        tasks = db.get_all_tasks()
        if not tasks:
            print("No tasks found")
            return
        
        print("\nScheduled Tasks:")
        print("-" * 100)
        print(f"{'ID':<5} {'Script':<20} {'Schedule':<20} {'Enabled':<10} {'Last Run':<20}")
        print("-" * 100)
        for task in tasks:
            enabled = "Yes" if task['enabled'] else "No"
            last_run = task['last_run'] or "Never"
            print(f"{task['id']:<5} {task['script_name']:<20} {task['schedule']:<20} {enabled:<10} {last_run:<20}")
        print("-" * 100)
    
    elif args.command == "delete":
        db.delete_task(args.task_id)
        print(f"Task {args.task_id} deleted")
    
    elif args.command == "enable":
        db.update_task(args.task_id, enabled=1)
        print(f"Task {args.task_id} enabled")
    
    elif args.command == "disable":
        db.update_task(args.task_id, enabled=0)
        print(f"Task {args.task_id} disabled")
    
    elif args.command == "logs":
        logs = db.get_task_logs(args.task_id, args.limit)
        if not logs:
            print(f"No logs found for task {args.task_id}")
            return
        
        print(f"\nLogs for Task {args.task_id} (latest {len(logs)}):")
        print("-" * 100)
        for log in logs:
            print(f"[{log['run_time']}] {log['status']} (exit code: {log['exit_code']})")
            if log['error']:
                print(f"  Error: {log['error'][:100]}")
        print("-" * 100)
    
    elif args.command == "run":
        print("Starting scheduler...")
        scheduler.schedule_all()
        scheduler.list_jobs()
        print("\nScheduler is running. Press Ctrl+C to stop.")
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping scheduler...")
            scheduler.stop_scheduler()
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
