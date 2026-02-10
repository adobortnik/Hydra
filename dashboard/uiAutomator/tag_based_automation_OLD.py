#!/usr/bin/env python3
"""
Tag-Based Profile Automation System
Integrates with dashboard account database to automate profile changes by tags
"""

import sqlite3
import os
import sys
from pathlib import Path
import json
import requests

# Add parent directory to path to import from dashboard
sys.path.insert(0, str(Path(__file__).parent.parent / "the-livehouse-dashboard"))

from profile_automation_db import (
    init_database, add_profile_update_task, get_pending_tasks,
    get_profile_pictures, add_profile_picture, PROFILE_AUTOMATION_DB
)

# Database paths
BASE_DIR = Path(__file__).parent.parent
DEVICES_DB = BASE_DIR / "devices.db"
ACCOUNT_INVENTORY_DB = BASE_DIR / "the-livehouse-dashboard" / "data" / "account_inventory" / "account_inventory.db"

class TagBasedAutomation:
    """
    Manages tag-based profile automation
    Links dashboard account database with profile automation system
    """

    def __init__(self):
        init_database()
        self._init_tags_system()

    def _init_tags_system(self):
        """Initialize tags and account mapping tables"""
        conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
        cursor = conn.cursor()

        # Table for tags
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # Table for account-tag mapping
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS account_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_serial TEXT NOT NULL,
            username TEXT NOT NULL,
            tag_id INTEGER NOT NULL,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tag_id) REFERENCES tags(id),
            UNIQUE(device_serial, username, tag_id)
        )
        ''')

        # Table for tag automation campaigns
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS tag_campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            mother_account TEXT,
            use_ai BOOLEAN DEFAULT 0,
            ai_endpoint TEXT,
            ai_api_key TEXT,
            profile_picture_strategy TEXT DEFAULT 'rotate',
            bio_strategy TEXT DEFAULT 'template',
            username_strategy TEXT DEFAULT 'manual',
            status TEXT DEFAULT 'draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            executed_at TIMESTAMP,
            FOREIGN KEY (tag_id) REFERENCES tags(id)
        )
        ''')

        # Indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_account_tags_tag ON account_tags(tag_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_account_tags_device ON account_tags(device_serial)')

        conn.commit()
        conn.close()

    def create_tag(self, name, description=None):
        """Create a new tag"""
        conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
        cursor = conn.cursor()

        try:
            cursor.execute('INSERT INTO tags (name, description) VALUES (?, ?)',
                         (name, description))
            tag_id = cursor.lastrowid
            conn.commit()
            return tag_id
        except sqlite3.IntegrityError:
            print(f"Tag '{name}' already exists")
            cursor.execute('SELECT id FROM tags WHERE name = ?', (name,))
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def get_tags(self):
        """Get all tags"""
        conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT t.*, COUNT(at.id) as account_count
            FROM tags t
            LEFT JOIN account_tags at ON t.id = at.tag_id
            GROUP BY t.id
            ORDER BY t.name
        ''')

        tags = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return tags

    def tag_account(self, device_serial, username, tag_name):
        """Tag an account"""
        # Get or create tag
        tag_id = self.create_tag(tag_name)

        conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO account_tags (device_serial, username, tag_id)
                VALUES (?, ?, ?)
            ''', (device_serial, username, tag_id))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Already tagged
        finally:
            conn.close()

    def untag_account(self, device_serial, username, tag_name):
        """Remove tag from account"""
        conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
        cursor = conn.cursor()

        cursor.execute('''
            DELETE FROM account_tags
            WHERE device_serial = ? AND username = ? AND tag_id = (
                SELECT id FROM tags WHERE name = ?
            )
        ''', (device_serial, username, tag_name))

        conn.commit()
        conn.close()

    def get_accounts_by_tag(self, tag_name):
        """Get all accounts with a specific tag"""
        conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT at.device_serial, at.username, at.assigned_at
            FROM account_tags at
            JOIN tags t ON at.tag_id = t.id
            WHERE t.name = ?
            ORDER BY at.assigned_at DESC
        ''', (tag_name,))

        accounts = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return accounts

    def get_device_accounts(self):
        """
        Get all accounts from device folders
        Scans device directories to find all accounts
        """
        accounts = []

        # Scan device directories
        for device_dir in BASE_DIR.glob("192.168.*_*"):
            if not device_dir.is_dir():
                continue

            device_serial = device_dir.name

            # Check for accounts.db
            accounts_db = device_dir / "accounts.db"
            if not accounts_db.exists():
                continue

            try:
                conn = sqlite3.connect(accounts_db)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute('SELECT account FROM accounts')
                for row in cursor.fetchall():
                    accounts.append({
                        'device_serial': device_serial,
                        'username': row['account']
                    })

                conn.close()
            except Exception as e:
                print(f"Error reading {accounts_db}: {e}")

        return accounts

    def bulk_tag_accounts(self, tag_name, device_serials=None, usernames=None):
        """
        Bulk tag multiple accounts

        Args:
            tag_name: Tag to apply
            device_serials: List of device serials (tags all accounts on these devices)
            usernames: List of specific usernames to tag
        """
        tagged_count = 0

        if device_serials:
            for device_serial in device_serials:
                # Get all accounts on this device
                accounts_db = BASE_DIR / device_serial / "accounts.db"
                if not accounts_db.exists():
                    continue

                conn = sqlite3.connect(accounts_db)
                cursor = conn.cursor()
                cursor.execute('SELECT account FROM accounts')

                for row in cursor.fetchall():
                    username = row[0]
                    if self.tag_account(device_serial, username, tag_name):
                        tagged_count += 1

                conn.close()

        if usernames:
            # Find these usernames across all devices
            all_accounts = self.get_device_accounts()
            for account in all_accounts:
                if account['username'] in usernames:
                    if self.tag_account(account['device_serial'], account['username'], tag_name):
                        tagged_count += 1

        return tagged_count

    def create_campaign(self, tag_name, campaign_name, mother_account=None,
                       use_ai=False, ai_config=None, strategies=None):
        """
        Create an automation campaign for a tag

        Args:
            tag_name: Tag to target
            campaign_name: Name of campaign
            mother_account: Mother account to base variations on
            use_ai: Whether to use AI for generation
            ai_config: Dict with 'endpoint' and 'api_key'
            strategies: Dict with 'profile_picture', 'bio', 'username' strategies
        """
        # Get tag ID
        conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
        cursor = conn.cursor()

        cursor.execute('SELECT id FROM tags WHERE name = ?', (tag_name,))
        tag_row = cursor.fetchone()

        if not tag_row:
            conn.close()
            raise ValueError(f"Tag '{tag_name}' not found")

        tag_id = tag_row[0]

        if strategies is None:
            strategies = {}

        if ai_config is None:
            ai_config = {}

        cursor.execute('''
            INSERT INTO tag_campaigns (
                tag_id, name, mother_account, use_ai, ai_endpoint, ai_api_key,
                profile_picture_strategy, bio_strategy, username_strategy, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready')
        ''', (
            tag_id, campaign_name, mother_account, int(use_ai),
            ai_config.get('endpoint'), ai_config.get('api_key'),
            strategies.get('profile_picture', 'rotate'),
            strategies.get('bio', 'template'),
            strategies.get('username', 'manual')
        ))

        campaign_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return campaign_id

    def execute_campaign(self, campaign_id):
        """
        Execute a campaign - create profile update tasks for all tagged accounts

        Returns:
            dict: Execution results with created task IDs
        """
        conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get campaign details
        cursor.execute('''
            SELECT c.*, t.name as tag_name
            FROM tag_campaigns c
            JOIN tags t ON c.tag_id = t.id
            WHERE c.id = ?
        ''', (campaign_id,))

        campaign = dict(cursor.fetchone())
        conn.close()

        # Get accounts with this tag
        accounts = self.get_accounts_by_tag(campaign['tag_name'])

        if not accounts:
            return {'success': False, 'message': 'No accounts found with this tag', 'tasks': []}

        # Get Instagram package for each device
        device_packages = self._get_device_packages(accounts)

        # Generate profile data based on strategies
        profile_data = self._generate_profile_data(campaign, accounts)

        # Create tasks
        created_tasks = []

        for i, account in enumerate(accounts):
            device_serial = account['device_serial']
            username = account['username']

            # Get data for this account
            account_data = profile_data[i] if i < len(profile_data) else {}

            task_id = add_profile_update_task(
                device_serial=device_serial,
                instagram_package=device_packages.get(device_serial, 'com.instagram.android'),
                username=username,
                new_username=account_data.get('new_username'),
                new_bio=account_data.get('new_bio'),
                profile_picture_id=account_data.get('profile_picture_id')
            )

            created_tasks.append({
                'task_id': task_id,
                'device_serial': device_serial,
                'username': username
            })

        # Update campaign status
        conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE tag_campaigns
            SET status = 'executed', executed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (campaign_id,))
        conn.commit()
        conn.close()

        return {
            'success': True,
            'campaign_id': campaign_id,
            'tag': campaign['tag_name'],
            'tasks_created': len(created_tasks),
            'tasks': created_tasks
        }

    def _get_device_packages(self, accounts):
        """Get Instagram package for each device from accounts.db"""
        device_packages = {}

        for account in accounts:
            device_serial = account['device_serial']

            if device_serial in device_packages:
                continue

            # Try to get from accounts.db - check for appid or default
            # For now, default to com.instagram.android
            # You can enhance this to read from your device settings
            device_packages[device_serial] = 'com.instagram.android'

        return device_packages

    def _generate_profile_data(self, campaign, accounts):
        """
        Generate profile data (username, bio, picture) for accounts
        Based on campaign strategies
        """
        profile_data = []

        # Get available profile pictures
        pictures = get_profile_pictures()

        # Get bio templates (if using templates)
        from profile_automation_db import get_bio_templates
        bio_templates = get_bio_templates()

        for i, account in enumerate(accounts):
            data = {}

            # Profile picture strategy
            if campaign['profile_picture_strategy'] == 'rotate' and pictures:
                pic_idx = i % len(pictures)
                data['profile_picture_id'] = pictures[pic_idx]['id']
            elif campaign['profile_picture_strategy'] == 'random' and pictures:
                import random
                data['profile_picture_id'] = random.choice(pictures)['id']

            # Bio strategy
            if campaign['bio_strategy'] == 'template' and bio_templates:
                bio_idx = i % len(bio_templates)
                data['new_bio'] = bio_templates[bio_idx]['bio_text']
            elif campaign['bio_strategy'] == 'ai' and campaign['use_ai']:
                # AI generation - will be handled by AI integration module
                data['new_bio'] = self._generate_ai_bio(campaign, account)

            # Username strategy
            if campaign['username_strategy'] == 'variation' and campaign['mother_account']:
                data['new_username'] = self._generate_username_variation(
                    campaign['mother_account'], i
                )
            elif campaign['username_strategy'] == 'ai' and campaign['use_ai']:
                data['new_username'] = self._generate_ai_username(campaign, account)

            profile_data.append(data)

        return profile_data

    def _generate_username_variation(self, base_username, index):
        """Generate username variation"""
        variations = [
            f"{base_username}{index + 1}",
            f"{base_username}.{index + 1}",
            f"{base_username}_{index + 1}",
            f"{base_username}.official",
            f"{base_username}.real"
        ]

        # Cycle through variation patterns
        return variations[index % len(variations)]

    def _generate_ai_bio(self, campaign, account):
        """Generate bio using AI (placeholder for AI integration)"""
        # This will be implemented in the AI integration module
        return None

    def _generate_ai_username(self, campaign, account):
        """Generate username using AI (placeholder for AI integration)"""
        # This will be implemented in the AI integration module
        return None


def example_usage():
    """Example usage of tag-based automation"""

    automation = TagBasedAutomation()

    print("="*70)
    print("TAG-BASED PROFILE AUTOMATION - EXAMPLE")
    print("="*70)

    # Example 1: Create tags
    print("\n--- Creating Tags ---")
    chantall_tag = automation.create_tag("chantall", "Chantall campaign accounts")
    anna_tag = automation.create_tag("anna", "Anna campaign accounts")
    print(f"Created tags: chantall (ID: {chantall_tag}), anna (ID: {anna_tag})")

    # Example 2: Tag accounts
    print("\n--- Tagging Accounts ---")
    automation.tag_account("192.168.101.107_5555", "anna.borli", "chantall")
    automation.tag_account("192.168.101.107_5555", "anna.borsn", "chantall")
    print("Tagged 2 accounts with 'chantall'")

    # Example 3: Get accounts by tag
    print("\n--- Accounts with 'chantall' tag ---")
    chantall_accounts = automation.get_accounts_by_tag("chantall")
    for acc in chantall_accounts:
        print(f"  - {acc['username']} on {acc['device_serial']}")

    # Example 4: Create campaign
    print("\n--- Creating Campaign ---")
    campaign_id = automation.create_campaign(
        tag_name="chantall",
        campaign_name="Chantall Profile Update Q1",
        mother_account="chantall.main",
        use_ai=False,
        strategies={
            'profile_picture': 'rotate',
            'bio': 'template',
            'username': 'variation'
        }
    )
    print(f"Created campaign ID: {campaign_id}")

    # Example 5: Execute campaign (creates tasks)
    print("\n--- Executing Campaign ---")
    result = automation.execute_campaign(campaign_id)
    print(f"Success: {result['success']}")
    print(f"Tasks created: {result['tasks_created']}")
    for task in result['tasks']:
        print(f"  Task {task['task_id']}: {task['username']} on {task['device_serial']}")

    print("\n" + "="*70)
    print("Now run: python automated_profile_manager.py")
    print("="*70)


if __name__ == "__main__":
    example_usage()
