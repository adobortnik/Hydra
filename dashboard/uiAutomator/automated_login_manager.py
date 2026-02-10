"""
automated_login_manager.py

Batch Processor for Instagram Login Automation
Reads tasks from database and executes them sequentially per device.

Follows the same patterns as automated_profile_manager.py:
- Task queue processing
- Device connection management
- Retry logic for transient failures
- Comprehensive logging

Author: Claude Code
Created: 2025-11-21
"""

import sys
import time
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))

from login_automation_db import (
    get_pending_login_tasks,
    update_task_status,
    increment_retry_count,
    log_login_attempt,
    get_task_by_id,
    update_2fa_token_usage
)
from login_automation import LoginAutomation


class AutomatedLoginManager:
    """
    Batch processor for automated Instagram logins

    Usage:
        manager = AutomatedLoginManager()
        manager.run_batch_processor()  # Process all pending tasks
    """

    def __init__(self):
        """Initialize the login manager"""
        self.current_device = None
        self.current_task = None
        self.login_automation = None

    def login_account(self, device_serial, instagram_package, username, password, two_fa_token=None):
        """
        Direct login method — wraps process_single_task with a synthetic task dict.
        Called by login_automation_v2_routes.py.
        
        Returns:
            dict with 'success' (bool) and 'message' (str)
        """
        task = {
            'id': 0,  # synthetic
            'device_serial': device_serial,
            'instagram_package': instagram_package,
            'username': username,
            'password': password,
            'two_fa_token': two_fa_token,
            'retry_count': 0,
            'max_retries': 3,
        }
        try:
            success = self.process_single_task(task)
            return {
                'success': bool(success),
                'message': 'Login completed' if success else 'Login failed',
            }
        except Exception as e:
            return {
                'success': False,
                'message': str(e),
            }

    def process_single_task(self, task):
        """
        Process a single login task

        Args:
            task: Task dict from database

        Returns:
            bool: True if successful
        """
        task_id = task['id']
        device_serial = task['device_serial']
        instagram_package = task['instagram_package']
        username = task['username']
        password = task['password']
        two_fa_token = task.get('two_fa_token')

        print("\n" + "="*70)
        print(f"PROCESSING LOGIN TASK #{task_id}")
        print("="*70)
        print(f"Device: {device_serial}")
        print(f"Package: {instagram_package}")
        print(f"Username: {username}")
        print(f"2FA: {'Yes' if two_fa_token else 'No'}")
        print(f"Retry Count: {task['retry_count']} / {task['max_retries']}")
        print("="*70)

        self.current_task = task

        # Update status to processing
        update_task_status(task_id, 'processing')

        try:
            # Connect to device if not already connected or different device
            if not self.current_device or self.current_device != device_serial:
                print(f"\nConnecting to device: {device_serial}")
                self.login_automation = LoginAutomation(device_serial)

                if not self.login_automation.connect_device():
                    error_msg = "Failed to connect to device"
                    print(f"\n✗ {error_msg}")
                    update_task_status(task_id, 'failed', error_msg)
                    log_login_attempt(
                        device_serial, instagram_package, username,
                        'failed', False, error_msg
                    )
                    return False

                self.current_device = device_serial
            else:
                print(f"\n✓ Already connected to device: {device_serial}")

            # Perform login
            result = self.login_automation.login_account(
                username=username,
                password=password,
                instagram_package=instagram_package,
                two_fa_token=two_fa_token
            )

            # Handle result
            if result['success']:
                print(f"\n✓ Task #{task_id} completed successfully!")

                # Update 2FA token usage if used
                if result['two_fa_used'] and two_fa_token:
                    update_2fa_token_usage(two_fa_token)

                # Update task status
                update_task_status(task_id, 'completed')

                # Log to history
                log_login_attempt(
                    device_serial, instagram_package, username,
                    result['login_type'], True,
                    two_fa_used=result['two_fa_used'],
                    challenge_encountered=result['challenge_encountered']
                )

                return True

            else:
                error_msg = result.get('error', 'Unknown error')
                print(f"\n✗ Task #{task_id} failed: {error_msg}")

                # Check if it's a challenge screen (needs manual intervention)
                if result['challenge_encountered']:
                    print("⚠ Challenge screen - marking as needs_manual")
                    update_task_status(task_id, 'needs_manual', error_msg)
                    log_login_attempt(
                        device_serial, instagram_package, username,
                        'challenge', False, error_msg,
                        challenge_encountered=True
                    )
                    return False

                # Check if we should retry
                retry_count = increment_retry_count(task_id)
                max_retries = task['max_retries']

                if retry_count < max_retries:
                    # Transient error, will retry
                    print(f"⚠ Will retry (attempt {retry_count + 1}/{max_retries})")
                    update_task_status(task_id, 'pending', error_msg)
                    log_login_attempt(
                        device_serial, instagram_package, username,
                        result['login_type'], False, error_msg,
                        two_fa_used=result['two_fa_used']
                    )
                    return False
                else:
                    # Max retries reached
                    print(f"✗ Max retries reached ({max_retries}), marking as failed")
                    update_task_status(task_id, 'failed', error_msg)
                    log_login_attempt(
                        device_serial, instagram_package, username,
                        result['login_type'], False, error_msg,
                        two_fa_used=result['two_fa_used']
                    )
                    return False

        except Exception as e:
            error_msg = f"Exception during login: {str(e)}"
            print(f"\n✗ {error_msg}")

            # Increment retry count
            retry_count = increment_retry_count(task_id)
            max_retries = task['max_retries']

            if retry_count < max_retries:
                print(f"⚠ Will retry (attempt {retry_count + 1}/{max_retries})")
                update_task_status(task_id, 'pending', error_msg)
            else:
                print(f"✗ Max retries reached, marking as failed")
                update_task_status(task_id, 'failed', error_msg)

            log_login_attempt(
                device_serial, instagram_package, username,
                'exception', False, error_msg
            )

            return False

    def run_batch_processor(self, device_serial=None, max_tasks=None):
        """
        Process all pending login tasks

        Args:
            device_serial: Optional device filter (process only this device)
            max_tasks: Optional limit on number of tasks to process

        Returns:
            dict: Statistics about processed tasks
        """
        print("\n" + "="*70)
        print("AUTOMATED LOGIN MANAGER - BATCH PROCESSOR")
        print("="*70)
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if device_serial:
            print(f"Device Filter: {device_serial}")
        if max_tasks:
            print(f"Max Tasks: {max_tasks}")
        print("="*70)

        stats = {
            'total_tasks': 0,
            'successful': 0,
            'failed': 0,
            'needs_manual': 0,
            'start_time': time.time()
        }

        try:
            # Get pending tasks
            tasks = get_pending_login_tasks(device_serial=device_serial, limit=max_tasks)

            if not tasks:
                print("\n✓ No pending login tasks found")
                return stats

            stats['total_tasks'] = len(tasks)
            print(f"\n✓ Found {len(tasks)} pending login task(s)")

            # Group tasks by device (process one device at a time)
            tasks_by_device = {}
            for task in tasks:
                dev = task['device_serial']
                if dev not in tasks_by_device:
                    tasks_by_device[dev] = []
                tasks_by_device[dev].append(task)

            print(f"\n✓ Tasks grouped across {len(tasks_by_device)} device(s)")

            # Process each device's tasks
            for dev_serial, dev_tasks in tasks_by_device.items():
                print("\n" + "="*70)
                print(f"PROCESSING DEVICE: {dev_serial}")
                print(f"Tasks: {len(dev_tasks)}")
                print("="*70)

                for i, task in enumerate(dev_tasks, 1):
                    print(f"\n>>> Task {i}/{len(dev_tasks)} for device {dev_serial}")

                    success = self.process_single_task(task)

                    if success:
                        stats['successful'] += 1
                    else:
                        # Check final status to categorize failure
                        final_task = get_task_by_id(task['id'])
                        if final_task and final_task['status'] == 'needs_manual':
                            stats['needs_manual'] += 1
                        else:
                            stats['failed'] += 1

                    # Brief delay between tasks on same device
                    if i < len(dev_tasks):
                        print("\n⏳ Waiting 10 seconds before next task...")
                        time.sleep(10)

                # Disconnect from device after all its tasks
                self.current_device = None
                self.login_automation = None
                print(f"\n✓ Finished processing device: {dev_serial}")

            # Calculate final stats
            stats['end_time'] = time.time()
            stats['duration'] = int(stats['end_time'] - stats['start_time'])

            print("\n" + "="*70)
            print("BATCH PROCESSING COMPLETE")
            print("="*70)
            print(f"Total Tasks: {stats['total_tasks']}")
            print(f"Successful: {stats['successful']}")
            print(f"Failed: {stats['failed']}")
            print(f"Needs Manual: {stats['needs_manual']}")
            print(f"Duration: {stats['duration']} seconds")
            print("="*70)

            return stats

        except KeyboardInterrupt:
            print("\n\n⚠ Interrupted by user (Ctrl+C)")
            stats['interrupted'] = True
            return stats

        except Exception as e:
            print(f"\n✗ Batch processor error: {e}")
            stats['error'] = str(e)
            return stats

    def process_task_by_id(self, task_id):
        """
        Process a specific task by ID

        Args:
            task_id: Task ID to process

        Returns:
            bool: True if successful
        """
        print("\n" + "="*70)
        print(f"PROCESSING SINGLE TASK #{task_id}")
        print("="*70)

        task = get_task_by_id(task_id)

        if not task:
            print(f"✗ Task #{task_id} not found")
            return False

        if task['status'] not in ['pending', 'failed']:
            print(f"⚠ Task #{task_id} status is '{task['status']}' (expected 'pending' or 'failed')")
            print("Processing anyway...")

        return self.process_single_task(task)


def main():
    """Main function for CLI usage"""
    import argparse

    parser = argparse.ArgumentParser(description='Instagram Login Automation - Batch Processor')
    parser.add_argument('--device', '-d', help='Process only tasks for this device serial')
    parser.add_argument('--task-id', '-t', type=int, help='Process a specific task by ID')
    parser.add_argument('--max-tasks', '-m', type=int, help='Maximum number of tasks to process')

    args = parser.parse_args()

    manager = AutomatedLoginManager()

    if args.task_id:
        # Process single task
        success = manager.process_task_by_id(args.task_id)
        sys.exit(0 if success else 1)
    else:
        # Process batch
        stats = manager.run_batch_processor(
            device_serial=args.device,
            max_tasks=args.max_tasks
        )
        sys.exit(0 if stats['failed'] == 0 else 1)


if __name__ == '__main__':
    main()
