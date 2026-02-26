#!/usr/bin/env python3
"""
Dynamic Python Rule Runner
Reads and executes Python files from a folder dynamically
"""

import os
import sys
import subprocess
from pathlib import Path


class ScriptRunner:
    def __init__(self, folder_path):
        self.folder_path = Path(folder_path)
        if not self.folder_path.exists():
            raise FileNotFoundError(f"Folder not found: {folder_path}")
        if not self.folder_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {folder_path}")
    
    def get_python_files(self):
        """Get all Python files from the folder"""
        py_files = sorted(self.folder_path.glob("*.py"))
        return py_files
    
    def list_scripts(self):
        """List all available Python scripts"""
        scripts = self.get_python_files()
        if not scripts:
            print(f"No Python files found in {self.folder_path}")
            return None
        
        print(f"\nAvailable scripts in {self.folder_path}:")
        print("-" * 50)
        for idx, script in enumerate(scripts, 1):
            print(f"{idx}. {script.name}")
        print("-" * 50)
        return scripts
    
    def run_script(self, script_path):
        """Run a single Python script"""
        script_path = Path(script_path)
        if not script_path.exists():
            print(f"Error: Script not found: {script_path}")
            return False
        
        if not script_path.suffix == ".py":
            print(f"Error: Not a Python file: {script_path}")
            return False
        
        print(f"\n{'='*50}")
        print(f"Running: {script_path.name}")
        print(f"{'='*50}\n")
        
        try:
            result = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=self.folder_path
            )
            print(f"\n{'='*50}")
            print(f"Exit code: {result.returncode}")
            print(f"{'='*50}\n")
            return result.returncode == 0
        except Exception as e:
            print(f"Error running script: {e}")
            return False
    
    def run_all_scripts(self):
        """Run all Python scripts in the folder"""
        scripts = self.get_python_files()
        if not scripts:
            print("No Python files to run")
            return
        
        print(f"Running {len(scripts)} script(s)...\n")
        results = {}
        
        for script in scripts:
            success = self.run_script(script)
            results[script.name] = success
        
        # Summary
        print(f"\n{'='*50}")
        print("SUMMARY")
        print(f"{'='*50}")
        passed = sum(1 for v in results.values() if v)
        failed = len(results) - passed
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        for script, success in results.items():
            status = "✓ PASS" if success else "✗ FAIL"
            print(f"  {status}: {script}")
        print(f"{'='*50}\n")


def interactive_mode(runner):
    """Interactive menu to select and run scripts"""
    while True:
        scripts = runner.list_scripts()
        if not scripts:
            break
        
        print("\nOptions:")
        print(f"0. Exit")
        print(f"R. Run all scripts")
        choice = input("\nEnter script number or option: ").strip()
        
        if choice.lower() == 'r':
            runner.run_all_scripts()
        elif choice == '0':
            print("Exiting...")
            break
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(scripts):
                    runner.run_script(scripts[idx])
                else:
                    print("Invalid selection")
            except ValueError:
                print("Invalid input")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Dynamically read and run Python files from a folder"
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default=".",
        help="Folder path containing Python files (default: current directory)"
    )
    parser.add_argument(
        "-l", "--list",
        action="store_true",
        help="List all Python files in the folder"
    )
    parser.add_argument(
        "-r", "--run",
        type=str,
        help="Run a specific script by name or number"
    )
    parser.add_argument(
        "-a", "--all",
        action="store_true",
        help="Run all scripts in the folder"
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Interactive mode to select and run scripts"
    )
    
    args = parser.parse_args()
    
    try:
        runner = ScriptRunner(args.folder)
        
        if args.list:
            runner.list_scripts()
        elif args.run:
            # Try to run by number or name
            scripts = runner.get_python_files()
            try:
                idx = int(args.run) - 1
                if 0 <= idx < len(scripts):
                    runner.run_script(scripts[idx])
                else:
                    print(f"Invalid script number: {args.run}")
            except ValueError:
                # Try to run by name
                script_path = runner.folder_path / args.run
                if not script_path.exists():
                    script_path = runner.folder_path / f"{args.run}.py"
                runner.run_script(script_path)
        elif args.all:
            runner.run_all_scripts()
        elif args.interactive:
            interactive_mode(runner)
        else:
            # Default: interactive mode
            interactive_mode(runner)
    
    except (FileNotFoundError, NotADirectoryError) as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
