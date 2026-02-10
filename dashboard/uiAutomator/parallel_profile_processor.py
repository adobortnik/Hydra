#!/usr/bin/env python3
"""
Parallel Profile Processor
Processes profile automation tasks with intelligent device grouping:
- Same device: sequential (one after another)
- Different devices: parallel (can run simultaneously)
"""

import sys
import os
from pathlib import Path
from collections import defaultdict
import threading
import time

sys.path.insert(0, str(Path(__file__).parent))

from automated_profile_manager import AutomatedProfileManager
from profile_automation_db import get_pending_tasks, init_database
from instagram_automation import disconnect_device


class ParallelProfileProcessor:
    """
    Processes profile automation tasks intelligently:
    - Groups tasks by device
    - Processes tasks on same device sequentially (one at a time)
    - Can process multiple devices in parallel (optional)
    """

    def __init__(self):
        self.managers = {}  # device_serial -> AutomatedProfileManager
        self.device_locks = {}  # device_serial -> threading.Lock
        self.results = {
            'successful': 0,
            'failed': 0,
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
            device_serial: Device serial number
            tasks: List of tasks for this device
        """
        print(f"\n{'='*70}")
        print(f"PROCESSING DEVICE: {device_serial}")
        print(f"Tasks to process: {len(tasks)}")
        print(f"{'='*70}\n")

        # Create manager instance for this device
        manager = AutomatedProfileManager()

        successful = 0
        failed = 0

        for i, task in enumerate(tasks, 1):
            print(f"\n{'#'*70}")
            print(f"# Device {device_serial} - Task {i}/{len(tasks)}")
            print(f"# Task ID: {task['id']}")
            print(f"{'#'*70}\n")

            try:
                if manager.process_single_task(task):
                    successful += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"❌ Exception processing task {task['id']}: {e}")
                failed += 1

            # Wait between tasks on same device
            if i < len(tasks):
                print(f"\n⏳ Waiting 5 seconds before next task on {device_serial}...")
                time.sleep(5)

        # Update global results
        with self.results_lock:
            self.results['successful'] += successful
            self.results['failed'] += failed
            self.results['total'] += len(tasks)

        # Cleanup: Disconnect device to release UIAutomator for Onimator
        if hasattr(manager, 'device') and manager.device:
            print(f"\n🔌 Disconnecting device {device_serial} to release UIAutomator...")
            disconnect_device(manager.device, device_serial)
            # CRITICAL: Clear the manager's reference to allow garbage collection
            manager.device = None

        print(f"\n{'='*70}")
        print(f"DEVICE {device_serial} COMPLETE")
        print(f"{'='*70}")
        print(f"✅ Successful: {successful}")
        print(f"❌ Failed: {failed}")
        print(f"📊 Total: {len(tasks)}")
        print(f"{'='*70}\n")

    def run_sequential(self, tasks):
        """
        Process all tasks sequentially (one device at a time)
        Best for: Single-threaded, safe, predictable
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
        print(f"\n🚀 Starting {len(threads)} device threads...")

        if max_parallel_devices:
            # Start threads in batches
            for i in range(0, len(threads), max_parallel_devices):
                batch = threads[i:i+max_parallel_devices]
                print(f"\n📦 Starting batch of {len(batch)} devices...")

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
        print("🎉 BATCH PROCESSING COMPLETE")
        print(f"{'='*70}")
        print(f"✅ Successful: {self.results['successful']}")
        print(f"❌ Failed: {self.results['failed']}")
        print(f"📊 Total: {self.results['total']}")

        if self.results['total'] > 0:
            success_rate = (self.results['successful'] / self.results['total']) * 100
            print(f"📈 Success Rate: {success_rate:.1f}%")

        print(f"{'='*70}\n")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Profile Automation Processor')
    parser.add_argument(
        '--mode',
        choices=['sequential', 'parallel'],
        default='sequential',
        help='Processing mode: sequential (safer) or parallel (faster)'
    )
    parser.add_argument(
        '--max-devices',
        type=int,
        default=None,
        help='Maximum devices to process in parallel (parallel mode only)'
    )

    args = parser.parse_args()

    # Initialize database
    init_database()

    # Get pending tasks
    pending_tasks = get_pending_tasks()

    if not pending_tasks:
        print("\n✅ No pending tasks found.")
        return

    print(f"\n📋 Found {len(pending_tasks)} pending task(s)")

    # Create processor
    processor = ParallelProfileProcessor()

    # Run based on mode
    if args.mode == 'sequential':
        processor.run_sequential(pending_tasks)
    else:
        processor.run_parallel(pending_tasks, max_parallel_devices=args.max_devices)


if __name__ == "__main__":
    main()
