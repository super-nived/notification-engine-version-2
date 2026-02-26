#!/usr/bin/env python3
"""
Sample task script that accepts parameters from the task scheduler
Reads parameters from environment variables: TASK_ID and TASK_PARAMS
"""

import os
import json
import sys
from datetime import datetime
import time


def main():
    """Main task execution function"""
    
    # Read task information from environment variables
    task_id = os.environ.get('TASK_ID', 'Unknown')
    task_params_json = os.environ.get('TASK_PARAMS', '{}')
    
    print(f"[{datetime.now().isoformat()}] Sample task started")
    print(f"Task ID: {task_id}")
    
    # Parse JSON parameters
    try:
        params = json.loads(task_params_json)
        print(f"Parameters: {params}")
    except json.JSONDecodeError as e:
        print(f"Error parsing parameters: {e}", file=sys.stderr)
        return 1
    
    # Example: Extract some parameters
    name = params.get('name', 'World')
    count = params.get('count', 1)
    message = params.get('message', 'Hello')
    
    print(f"\nExecuting task with parameters:")
    print(f"  Name: {name}")
    print(f"  Count: {count}")
    print(f"  Message: {message}")
    
    # Do some work
    print(f"\nProcessing:")
    for i in range(count):
        print(f"  [{i+1}] {message}, {name}!")
    
    print(f"\n[{datetime.now().isoformat()}] Sample task completed successfully")

    print ("Sleepig..")
    time.sleep(15)
    print("Woke up")
    return 0


if __name__ == "__main__":
    sys.exit(main())
