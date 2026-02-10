#!/usr/bin/env python3
"""
Device Bot - Autonomous bot that manages one device

Usage:
    python device_bot.py --device 10.1.10.183_5555
"""

import argparse
import time
from datetime import datetime, timedelta
from pathlib import Path

from onimator_reader import OnimatorReader
from bot_db import (
    init_bot_database, update_bot_status, get_bot_status,
    create_account_session, complete_account_session,
    log_action, get_last_session_time
)

# Import device connection from instagram_automation
from instagram_automation import connect_device, open_instagram


class DeviceBot:
    """Autonomous bot that manages one device"""

    def __init__(self, device_serial):
        """
        Initialize device bot

        Args:
            device_serial: Device serial (e.g., "10.1.10.183_5555")
        """
        self.device_serial = device_serial
        self.device = None
        self.onimator_reader = OnimatorReader(device_serial)
        self.current_account = None
        self.current_session = None

        # Initialize database
        init_bot_database(device_serial)

    def run(self):
        """Main bot loop"""
        print(f"\n{'='*70}")
        print(f"STARTING DEVICE BOT")
        print(f"Device: {self.device_serial}")
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}\n")

        # Mark bot as running
        import os
        update_bot_status(self.device_serial, 'running', pid=os.getpid())

        # Connect to device once
        print("Connecting to device...")
        try:
            self.connect_to_device()
            print(f"✓ Connected to device: {self.device_serial}")
        except Exception as e:
            print(f"✗ Failed to connect to device: {e}")
            update_bot_status(self.device_serial, 'stopped')
            return

        # Main bot loop
        while self.is_running():
            try:
                current_time = datetime.now()
                print(f"\n[{current_time.strftime('%H:%M:%S')}] Checking for scheduled accounts...")

                # Get accounts that should run this hour
                scheduled_accounts = self.onimator_reader.get_accounts_for_current_hour()

                if not scheduled_accounts:
                    print(f"No accounts scheduled for hour {current_time.hour}")
                else:
                    print(f"Found {len(scheduled_accounts)} scheduled account(s):")
                    for acc in scheduled_accounts:
                        print(f"  - {acc['account']} (time window: {acc['starttime']}-{acc['endtime']})")

                    # Run each account sequentially
                    for account in scheduled_accounts:
                        if self.should_run_account(account):
                            try:
                                self.run_account_session(account)
                            except Exception as e:
                                print(f"✗ Error running account {account['account']}: {e}")

                            # Wait between accounts
                            time.sleep(10)
                        else:
                            print(f"Skipping {account['account']} (recently run or other condition)")

                # Wait before next check (check every minute)
                print(f"\nWaiting 60 seconds before next check...")
                time.sleep(60)

            except KeyboardInterrupt:
                print("\n\nReceived keyboard interrupt, stopping bot...")
                break

            except Exception as e:
                print(f"\n✗ Bot error: {e}")
                time.sleep(60)

        # Mark bot as stopped
        update_bot_status(self.device_serial, 'stopped')

        print(f"\n{'='*70}")
        print(f"DEVICE BOT STOPPED")
        print(f"Device: {self.device_serial}")
        print(f"Stopped at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}\n")

    def run_account_session(self, account):
        """
        Run one account's automation session

        Args:
            account: Account dict from accounts.db
        """
        username = account['account']

        print(f"\n{'#'*70}")
        print(f"STARTING SESSION: {username}")
        print(f"Time: {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'#'*70}\n")

        # Create session record
        session_id = create_account_session(
            device_serial=self.device_serial,
            username=username
        )

        self.current_account = account
        self.current_session = session_id

        try:
            # Load account settings
            print(f"Loading settings for {username}...")
            settings = self.onimator_reader.get_account_settings(username)
            print(f"✓ Loaded {len(settings)} settings")

            # Get Instagram package
            instagram_package = self.onimator_reader.get_instagram_package(username)
            print(f"Instagram package: {instagram_package}")

            # Open Instagram for this account
            print(f"\nOpening Instagram...")
            if not open_instagram(self.device, instagram_package):
                raise Exception("Failed to open Instagram")
            print(f"✓ Instagram opened")

            time.sleep(3)

            # Get enabled actions from accounts.db
            enabled_actions = self.get_enabled_actions(account)

            if not enabled_actions:
                print("⚠ No actions enabled for this account")
            else:
                print(f"\nEnabled actions: {', '.join(enabled_actions)}")

                # Execute each enabled action
                actions_performed = {}
                for action_name in enabled_actions:
                    print(f"\n--- Executing: {action_name} ---")
                    result = self.execute_action(action_name, account, settings)
                    actions_performed[action_name] = result.get('actions_performed', 0)
                    print(f"✓ {action_name} completed: {result['actions_performed']} actions")

                    # Wait between actions
                    time.sleep(5)

                # Mark session complete
                complete_account_session(
                    self.device_serial,
                    session_id,
                    status='completed',
                    actions=actions_performed
                )

                print(f"\n✓ Session completed successfully")
                print(f"Actions performed: {actions_performed}")

        except Exception as e:
            print(f"\n✗ Session error for {username}: {e}")
            complete_account_session(
                self.device_serial,
                session_id,
                status='error',
                error=str(e)
            )

        finally:
            self.current_account = None
            self.current_session = None

            print(f"\n{'#'*70}")
            print(f"SESSION ENDED: {username}")
            print(f"{'#'*70}\n")

    def get_enabled_actions(self, account):
        """
        Return list of enabled actions from accounts.db

        Args:
            account: Account dict

        Returns:
            List[str]: List of enabled action names
        """
        actions = []

        # Check each action flag
        if account.get('follow') == 'True':
            actions.append('follow')

        if account.get('unfollow') == 'True':
            actions.append('unfollow')

        # Add more actions as they're implemented
        # if account.get('like') == 'True':
        #     actions.append('like')
        # if account.get('comment') == 'True':
        #     actions.append('comment')

        return actions

    def execute_action(self, action_name, account, settings):
        """
        Execute one action (follow, unfollow, like, etc.)

        Args:
            action_name: Action name ('follow', 'unfollow', etc.)
            account: Account dict from accounts.db
            settings: Account settings from settings.db

        Returns:
            dict: {'success': bool, 'actions_performed': int, 'errors': list}
        """
        # Placeholder for now - will be replaced with actual action modules
        print(f"Executing {action_name} for {account['account']}...")

        # For now, just log a placeholder action
        if self.current_session:
            log_action(
                session_id=self.current_session,
                device_serial=self.device_serial,
                username=account['account'],
                action_type=action_name,
                target="placeholder_target",
                success=True,
                error=None
            )

        # Simulate action taking some time
        time.sleep(2)

        return {
            'success': True,
            'actions_performed': 1,
            'errors': []
        }

        # TODO: Implement actual action execution
        # from actions import follow_action, unfollow_action
        #
        # action_map = {
        #     'follow': follow_action.FollowAction,
        #     'unfollow': unfollow_action.UnfollowAction,
        # }
        #
        # if action_name not in action_map:
        #     return {'success': False, 'actions_performed': 0, 'errors': [f'Unknown action: {action_name}']}
        #
        # ActionClass = action_map[action_name]
        # action = ActionClass(device=self.device, account=account, settings=settings)
        # return action.execute(self.current_session)

    def connect_to_device(self):
        """Connect to device using proven UIAutomator pattern"""
        self.device = connect_device(device_serial=self.device_serial)

        if not self.device:
            raise Exception("Failed to connect to device")

    def should_run_account(self, account):
        """
        Check if account should run (not already running, not recently run, etc.)

        Args:
            account: Account dict

        Returns:
            bool: True if should run, False otherwise
        """
        username = account['account']

        # Check if we recently ran this account (avoid running twice in same hour)
        last_run = get_last_session_time(self.device_serial, username)

        if last_run:
            time_since_run = datetime.now() - last_run
            # Don't run again if we ran within the last hour
            if time_since_run < timedelta(hours=1):
                print(f"  Account {username} ran {int(time_since_run.total_seconds() / 60)} minutes ago, skipping")
                return False

        return True

    def is_running(self):
        """
        Check if bot should continue running

        Returns:
            bool: True if should continue, False to stop
        """
        # Check bot status in database
        status = get_bot_status(self.device_serial)
        return status.get('status') == 'running'


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Device Bot - Autonomous bot for one device',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Start bot for device
  python device_bot.py --device 10.1.10.183_5555

  # The bot will:
  - Read accounts from {device}/accounts.db
  - Run accounts during their scheduled time windows
  - Execute enabled actions (follow, unfollow, etc.)
  - Log all activity to bot database
        '''
    )

    parser.add_argument(
        '--device',
        required=True,
        help='Device serial (e.g., 10.1.10.183_5555)'
    )

    args = parser.parse_args()

    # Create and run bot
    try:
        bot = DeviceBot(args.device)
        bot.run()
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"\nBot failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
