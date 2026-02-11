#!/usr/bin/env python3
"""
Parallel Login Processor

Processes login automation tasks with intelligent device grouping:
- Same device: sequential (one after another)
- Different devices: parallel (can run simultaneously)

Example scenario:
- Device A (10.1.10.36_5555): 7 tasks
- Device B (10.1.10.183_5555): 8 tasks

Sequential mode: Process all 7 tasks on Device A, then all 8 on Device B (~170 seconds)
Parallel mode: Process Device A and Device B simultaneously (~70 seconds)

Usage:
    # Parallel mode (default, faster)
    python parallel_login_processor.py --mode parallel

    # Sequential mode (safer, current behavior)
    python parallel_login_processor.py --mode sequential

    # Filter by device
    python parallel_login_processor.py --device 10.1.10.36_5555

    # Limit max parallel devices
    python parallel_login_processor.py --mode parallel --max-devices 3

Author: Claude Code
Created: 2025-11-26
"""

import sys
import os
from pathlib import Path
from collections import defaultdict
import threading
import time

sys.path.insert(0, str(Path(__file__).parent))

from automated_login_manager import AutomatedLoginManager
from login_automation_db import get_pending_login_tasks, init_database, get_task_by_id


class ParallelLoginProcessor:
    """
    Processes login automation tasks intelligently:
    - Groups tasks by device
    - Processes tasks on same device sequentially (one at a time)
    - Can process multiple devices in parallel (optional)
    """

    def __init__(self):
        self.managers = {}  # device_serial -> AutomatedLoginManager
        self.results = {
            'successful': 0,
            'failed': 0,
            'needs_manual': 0,
            'total': 0
        }
        self.results_lock = threading.Lock()

    def group_tasks_by_device(self, tasks):
        """
        Group tasks by device serial number

        Returns:
            dict: {device_serial: [task1, task2, ...]}
        """
        grouped = defaultdict(list)
        for task in tasks:
            device_serial = task['device_serial']
            grouped[device_serial].append(task)

        return dict(grouped)

    def process_device_tasks(self, device_serial, tasks):
        """
        Process all tasks for a single device sequentially

        Args:
            device_serial: Device serial number (e.g., "10.1.10.36_5555")
            tasks: List of tasks for this device
        """
        print(f"\n{'='*70}")
        print(f"PROCESSING DEVICE: {device_serial}")
        print(f"Tasks to process: {len(tasks)}")
        print(f"{'='*70}\n")

        # Create manager instance for this device
        manager = AutomatedLoginManager()

        successful = 0
        failed = 0
        needs_manual = 0

        for i, task in enumerate(tasks, 1):
            print(f"\n{'#'*70}")
            print(f"# Device {device_serial} - Task {i}/{len(tasks)}")
            print(f"# Task ID: {task['id']} | Username: {task['username']}")
            print(f"{'#'*70}\n")

            try:
                success = manager.process_single_task(task)

                if success:
                    successful += 1
                else:
                    # Check final status to categorize failure
                    final_task = get_task_by_id(task['id'])
                    if final_task and final_task['status'] == 'needs_manual':
                        needs_manual += 1
                    else:
                        failed += 1

            except Exception as e:
                print(f"[X] Exception processing task {task['id']}: {e}")
                failed += 1

            # Wait between tasks on same device
            if i < len(tasks):
                wait_time = 10
                print(f"\n[...] Waiting {wait_time} seconds before next task on {device_serial}...")
                time.sleep(wait_time)

        # Update global results (thread-safe)
        with self.results_lock:
            self.results['successful'] += successful
            self.results['failed'] += failed
            self.results['needs_manual'] += needs_manual
            self.results['total'] += len(tasks)

        print(f"\n{'='*70}")
        print(f"DEVICE {device_serial} COMPLETE")
        print(f"{'='*70}")
        print(f"[OK] Successful: {successful}")
        print(f"[X] Failed: {failed}")
        print(f"[!]  Needs Manual: {needs_manual}")
        print(f" Total: {len(tasks)}")
        print(f"{'='*70}\n")

    def run_sequential(self, tasks):
        """
        Process all tasks sequentially (one device at a time)
        Best for: Single-threaded, safe, predictable

        This is the current behavior of automated_login_manager.py
        """
        print("\n" + "="*70)
        print("SEQUENTIAL PROCESSING MODE")
        print("="*70)

        grouped_tasks = self.group_tasks_by_device(tasks)

        print(f"\nDevices to process: {len(grouped_tasks)}")
        for device_serial, device_tasks in grouped_tasks.items():
            print(f"  - {device_serial}: {len(device_tasks)} tasks")

        for device_serial, device_tasks in grouped_tasks.items():
            self.process_device_tasks(device_serial, device_tasks)

        self._print_summary()

    def run_parallel(self, tasks, max_parallel_devices=None):
        """
        Process multiple devices in parallel
        Best for: Fast processing when you have many devices

        Args:
            tasks: List of tasks
            max_parallel_devices: Maximum devices to process simultaneously (None = unlimited)

        Example:
            Device A: 7 tasks (~70 seconds)
            Device B: 8 tasks (~80 seconds)

            Sequential: 70 + 80 = 150 seconds total
            Parallel: max(70, 80) = 80 seconds total
        """
        print("\n" + "="*70)
        print("PARALLEL PROCESSING MODE")
        print("="*70)

        grouped_tasks = self.group_tasks_by_device(tasks)

        print(f"\nDevices to process: {len(grouped_tasks)}")
        for device_serial, device_tasks in grouped_tasks.items():
            print(f"  - {device_serial}: {len(device_tasks)} tasks")

        if max_parallel_devices:
            print(f"\nMax parallel devices: {max_parallel_devices}")

        # Create threads for each device
        threads = []
        for device_serial, device_tasks in grouped_tasks.items():
            thread = threading.Thread(
                target=self.process_device_tasks,
                args=(device_serial, device_tasks),
                name=f"Device-{device_serial}"
            )
            threads.append(thread)

        # Start threads
        print(f"\n[>] Starting {len(threads)} device thread(s)...")

        if max_parallel_devices:
            # Start threads in batches
            for i in range(0, len(threads), max_parallel_devices):
                batch = threads[i:i+max_parallel_devices]
                print(f"\n[>] Starting batch of {len(batch)} device(s)...")

                for thread in batch:
                    thread.start()

                # Wait for this batch to complete
                for thread in batch:
                    thread.join()
        else:
            # Start all threads at once
            for thread in threads:
                thread.start()

            # Wait for all to complete
            for thread in threads:
                thread.join()

        self._print_summary()

    def _print_summary(self):
        """Print final summary"""
        print(f"\n\n{'='*70}")
        print("[OK] BATCH PROCESSING COMPLETE")
        print(f"{'='*70}")
        print(f"[OK] Successful: {self.results['successful']}")
        print(f"[X] Failed: {self.results['failed']}")
        print(f"[!]  Needs Manual: {self.results['needs_manual']}")
        print(f" Total: {self.results['total']}")

        if self.results['total'] > 0:
            success_rate = (self.results['successful'] / self.results['total']) * 100
            print(f" Success Rate: {success_rate:.1f}%")

        print(f"{'='*70}\n")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Login Automation Processor with Parallel Processing',
        epilog='''
Examples:
  # Process all pending tasks in parallel (fastest)
  python parallel_login_processor.py --mode parallel

  # Process all pending tasks sequentially (current behavior)
  python parallel_login_processor.py --mode sequential

  # Process only tasks for specific device
  python parallel_login_processor.py --device 10.1.10.36_5555

  # Limit parallel devices to 3 at a time
  python parallel_login_processor.py --mode parallel --max-devices 3
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--mode',
        choices=['sequential', 'parallel'],
        default='parallel',
        help='Processing mode: sequential (safer) or parallel (faster, default)'
    )
    parser.add_argument(
        '--max-devices',
        type=int,
        default=None,
        help='Maximum devices to process in parallel (parallel mode only)'
    )
    parser.add_argument(
        '--device',
        type=str,
        default=None,
        help='Filter tasks by device serial (e.g., 10.1.10.36_5555)'
    )
    parser.add_argument(
        '--max-tasks',
        type=int,
        default=None,
        help='Maximum number of tasks to process'
    )

    args = parser.parse_args()

    # Initialize database
    print("Initializing database...")
    init_database()

    # Get pending tasks
    pending_tasks = get_pending_login_tasks(
        device_serial=args.device,
        limit=args.max_tasks
    )

    if not pending_tasks:
        print("\n[OK] No pending tasks found.")
        return

    print(f"\n Found {len(pending_tasks)} pending task(s)")

    # Show task breakdown by device
    tasks_by_device = defaultdict(list)
    for task in pending_tasks:
        tasks_by_device[task['device_serial']].append(task)

    print(f"\nTasks by device:")
    for device_serial, device_tasks in tasks_by_device.items():
        print(f"  - {device_serial}: {len(device_tasks)} tasks")

    # Create processor
    processor = ParallelLoginProcessor()

    # Run based on mode
    start_time = time.time()

    if args.mode == 'sequential':
        processor.run_sequential(pending_tasks)
    else:
        processor.run_parallel(pending_tasks, max_parallel_devices=args.max_devices)

    end_time = time.time()
    duration = int(end_time - start_time)

    print(f"\n[T]  Total execution time: {duration} seconds ({duration // 60}m {duration % 60}s)")


if __name__ == "__main__":
    main()
