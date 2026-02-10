#!/usr/bin/env python3
"""
Tag-Based Profile Automation System - Fixed Version
Reads tags from existing settings.db files (no separate database)
"""

import sqlite3
import os
import sys
import json
from pathlib import Path
from collections import defaultdict

# Add parent directory to path to import from dashboard
sys.path.insert(0, str(Path(__file__).parent.parent / "the-livehouse-dashboard"))

from profile_automation_db import (
    add_profile_update_task, get_pending_tasks,
    get_profile_pictures, add_profile_picture, PROFILE_AUTOMATION_DB
)

# Database paths
BASE_DIR = Path(__file__).parent.parent.parent
PHONE_FARM_DB = BASE_DIR / "db" / "phone_farm.db"

class TagBasedAutomation:
    """
    Manages tag-based profile automation
    Reads tags from phone_farm.db account_settings (settings_json -> tags field)
    """

    def __init__(self):
        pass

    def get_all_accounts_with_tags(self):
        """
        Get all accounts with their tags from phone_farm.db

        Returns:
            list: List of dicts with device_serial, username, tags, enable_tags
        """
        accounts_with_tags = []

        try:
            conn = sqlite3.connect(str(PHONE_FARM_DB))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT a.id, a.device_serial, a.username, s.settings_json
                FROM accounts a
                LEFT JOIN account_settings s ON a.id = s.account_id
                WHERE s.settings_json IS NOT NULL
            """)

            for row in cursor.fetchall():
                try:
                    settings = json.loads(row['settings_json'])
                    tags = settings.get('tags', '')
                    enable_tags = settings.get('enable_tags', False)

                    accounts_with_tags.append({
                        'device_serial': row['device_serial'],
                        'username': row['username'],
                        'tags': tags,
                        'enable_tags': enable_tags,
                        'settings': settings
                    })
                except (json.JSONDecodeError, Exception) as e:
                    print(f"Error parsing settings for account {row['id']}: {e}")
                    continue

            conn.close()
        except Exception as e:
            print(f"Error reading from phone_farm.db: {e}")

        return accounts_with_tags

    def get_tags(self):
        """
        Get all unique tags from all accounts

        Returns:
            list: List of dicts with tag name and account count
        """
        all_accounts = self.get_all_accounts_with_tags()

        # Count accounts per tag
        tag_counts = defaultdict(int)

        for account in all_accounts:
            tags_str = account.get('tags', '')
            if tags_str and account.get('enable_tags', False):
                # Tags can be comma-separated
                tags_list = [t.strip() for t in tags_str.split(',') if t.strip()]
                for tag in tags_list:
                    tag_counts[tag] += 1

        # Convert to list format
        tags = [
            {
                'name': tag_name,
                'account_count': count,
                'id': hash(tag_name)  # Fake ID for compatibility
            }
            for tag_name, count in sorted(tag_counts.items())
        ]

        return tags

    def get_accounts_by_tag(self, tag_name):
        """
        Get all accounts with a specific tag

        Args:
            tag_name: Tag to search for

        Returns:
            list: List of accounts with this tag
        """
        all_accounts = self.get_all_accounts_with_tags()

        matching_accounts = []

        for account in all_accounts:
            tags_str = account.get('tags', '')
            if not tags_str or not account.get('enable_tags', False):
                continue

            # Tags can be comma-separated
            tags_list = [t.strip() for t in tags_str.split(',') if t.strip()]

            if tag_name in tags_list:
                matching_accounts.append({
                    'device_serial': account['device_serial'],
                    'username': account['username'],
                    'tags': account['tags']
                })

        return matching_accounts

    def tag_account(self, device_serial, username, tag_name):
        """
        Add a tag to an account's settings.db

        Args:
            device_serial: Device ID (folder name like 192.168.101.107_5555)
            username: Account username
            tag_name: Tag to add

        Returns:
            bool: True if tagged successfully
        """
        settings_db_path = BASE_DIR / device_serial / username / "settings.db"

        if not settings_db_path.exists():
            print(f"Settings not found: {settings_db_path}")
            return False

        try:
            conn = sqlite3.connect(settings_db_path)
            cursor = conn.cursor()

            # Read current settings
            cursor.execute('SELECT settings FROM accountsettings WHERE id = 1')
            row = cursor.fetchone()

            if not row or not row[0]:
                conn.close()
                return False

            settings = json.loads(row[0])

            # Get current tags
            current_tags = settings.get('tags', '')
            current_tags_list = [t.strip() for t in current_tags.split(',') if t.strip()]

            # Add new tag if not already present
            if tag_name not in current_tags_list:
                current_tags_list.append(tag_name)
                settings['tags'] = ','.join(current_tags_list)
                settings['enable_tags'] = True

                # Update settings
                cursor.execute(
                    'UPDATE accountsettings SET settings = ? WHERE id = 1',
                    (json.dumps(settings),)
                )
                conn.commit()
                conn.close()
                return True
            else:
                conn.close()
                return False  # Already has this tag

        except Exception as e:
            print(f"Error tagging account {device_serial}/{username}: {e}")
            return False

    def untag_account(self, device_serial, username, tag_name):
        """
        Remove a tag from an account's settings.db

        Args:
            device_serial: Device ID
            username: Account username
            tag_name: Tag to remove
        """
        settings_db_path = BASE_DIR / device_serial / username / "settings.db"

        if not settings_db_path.exists():
            return False

        try:
            conn = sqlite3.connect(settings_db_path)
            cursor = conn.cursor()

            cursor.execute('SELECT settings FROM accountsettings WHERE id = 1')
            row = cursor.fetchone()

            if not row or not row[0]:
                conn.close()
                return False

            settings = json.loads(row[0])

            # Get current tags
            current_tags = settings.get('tags', '')
            current_tags_list = [t.strip() for t in current_tags.split(',') if t.strip()]

            # Remove tag
            if tag_name in current_tags_list:
                current_tags_list.remove(tag_name)
                settings['tags'] = ','.join(current_tags_list)

                # Update settings
                cursor.execute(
                    'UPDATE accountsettings SET settings = ? WHERE id = 1',
                    (json.dumps(settings),)
                )
                conn.commit()

            conn.close()
            return True

        except Exception as e:
            print(f"Error untagging account {device_serial}/{username}: {e}")
            return False

    def bulk_tag_accounts(self, tag_name, device_serials=None, usernames=None):
        """
        Bulk tag multiple accounts

        Args:
            tag_name: Tag to apply
            device_serials: List of device serials (tags all accounts on these devices)
            usernames: List of specific usernames to tag (optional)

        Returns:
            int: Number of accounts tagged
        """
        tagged_count = 0

        if device_serials:
            for device_serial in device_serials:
                device_dir = BASE_DIR / device_serial

                if not device_dir.exists():
                    print(f"Device directory not found: {device_dir}")
                    continue

                # Iterate through all account folders
                for account_dir in device_dir.iterdir():
                    if not account_dir.is_dir():
                        continue

                    username = account_dir.name

                    # If specific usernames provided, filter
                    if usernames and username not in usernames:
                        continue

                    if self.tag_account(device_serial, username, tag_name):
                        tagged_count += 1
                        print(f"Tagged: {device_serial}/{username}")

        return tagged_count

    def create_campaign(self, tag_name, campaign_name, mother_account=None,
                       name_shortcuts=None, mother_bio=None, use_ai=False,
                       ai_config=None, strategies=None):
        """
        Create an automation campaign for a tag
        Uses the existing profile_automation.db for campaign tracking

        Args:
            name_shortcuts: List of name variations (e.g., ['chantall', 'chantie', 'chan'])
            mother_bio: The bio to use as base
        """
        # We still use the campaign tracking from profile_automation_db
        from profile_automation_db import PROFILE_AUTOMATION_DB

        if strategies is None:
            strategies = {}
        if ai_config is None:
            ai_config = {}
        if name_shortcuts is None:
            name_shortcuts = []

        conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
        cursor = conn.cursor()

        # Ensure tag_campaigns table exists with name_shortcuts column
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tag_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tag_name TEXT NOT NULL,
                name TEXT NOT NULL,
                mother_account TEXT,
                name_shortcuts TEXT,
                mother_bio TEXT,
                use_ai BOOLEAN DEFAULT 0,
                ai_endpoint TEXT,
                ai_api_key TEXT,
                profile_picture_strategy TEXT DEFAULT 'rotate',
                bio_strategy TEXT DEFAULT 'template',
                username_strategy TEXT DEFAULT 'manual',
                status TEXT DEFAULT 'draft',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                executed_at TIMESTAMP
            )
        ''')

        # Store name_shortcuts as JSON
        shortcuts_json = json.dumps(name_shortcuts) if name_shortcuts else None

        cursor.execute('''
            INSERT INTO tag_campaigns (
                tag_name, name, mother_account, name_shortcuts, mother_bio,
                use_ai, ai_endpoint, ai_api_key,
                profile_picture_strategy, bio_strategy, username_strategy, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready')
        ''', (
            tag_name, campaign_name, mother_account, shortcuts_json, mother_bio,
            int(use_ai),
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
        """
        from profile_automation_db import PROFILE_AUTOMATION_DB

        conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get campaign details
        cursor.execute('SELECT * FROM tag_campaigns WHERE id = ?', (campaign_id,))
        campaign = dict(cursor.fetchone())
        conn.close()

        # Get accounts with this tag from settings.db files
        accounts = self.get_accounts_by_tag(campaign['tag_name'])

        if not accounts:
            return {
                'success': False,
                'message': f"No accounts found with tag '{campaign['tag_name']}'",
                'tasks_created': 0,
                'tasks': []
            }

        return self._execute_for_accounts(campaign_id, campaign, accounts)

    def execute_campaign_for_accounts(self, campaign_id, selected_accounts):
        """
        Execute a campaign for specific selected accounts only

        Args:
            campaign_id: Campaign ID
            selected_accounts: List of dicts with device_serial and username
        """
        from profile_automation_db import PROFILE_AUTOMATION_DB

        conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get campaign details
        cursor.execute('SELECT * FROM tag_campaigns WHERE id = ?', (campaign_id,))
        campaign = dict(cursor.fetchone())
        conn.close()

        # Convert selected_accounts to same format as get_accounts_by_tag
        accounts = [
            {
                'device_serial': acc['device_serial'],
                'username': acc['username'],
                'tags': campaign['tag_name']
            }
            for acc in selected_accounts
        ]

        return self._execute_for_accounts(campaign_id, campaign, accounts)

    def _execute_for_accounts(self, campaign_id, campaign, accounts):
        """Internal method to execute campaign for given accounts"""
        from profile_automation_db import PROFILE_AUTOMATION_DB, auto_import_profile_pictures

        # Auto-import any new profile pictures from upload folder
        print("\n" + "="*70)
        print("AUTO-IMPORTING PROFILE PICTURES")
        print("="*70)
        import_result = auto_import_profile_pictures()
        if import_result['imported'] > 0:
            print(f"✓ Imported {import_result['imported']} new profile picture(s)")

        # Generate profile data based on strategies
        profile_data = self._generate_profile_data(campaign, accounts)

        # Create tasks
        created_tasks = []

        for i, account in enumerate(accounts):
            device_serial = account['device_serial']
            username = account['username']

            # Get data for this account
            account_data = profile_data[i] if i < len(profile_data) else {}

            # Get Instagram package from account's settings.db
            instagram_package = self._get_instagram_package(device_serial, username)

            task_id = add_profile_update_task(
                device_serial=device_serial,
                instagram_package=instagram_package,
                username=username,
                new_username=account_data.get('new_username'),
                new_bio=account_data.get('new_bio'),
                profile_picture_id=account_data.get('profile_picture_id'),
                ai_api_key=campaign.get('ai_api_key'),
                ai_provider='openai',
                mother_account=campaign.get('mother_account')
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

    def _generate_profile_data(self, campaign, accounts):
        """Generate profile data based on campaign strategies"""
        profile_data = []

        pictures = get_profile_pictures()

        from profile_automation_db import get_bio_templates
        bio_templates = get_bio_templates()

        # Parse name shortcuts if available
        name_shortcuts = []
        if campaign.get('name_shortcuts'):
            try:
                name_shortcuts = json.loads(campaign['name_shortcuts'])
            except:
                name_shortcuts = []

        for i, account in enumerate(accounts):
            data = {}

            # Profile picture strategy
            if campaign['profile_picture_strategy'] == 'gallery_auto':
                # Use special marker to indicate automatic gallery selection
                # The profile manager will pick first/last photo from phone gallery
                data['profile_picture_id'] = 'AUTO_GALLERY'
            elif campaign['profile_picture_strategy'] == 'rotate' and pictures:
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
                ai_bio = self._generate_ai_bio(campaign, account)
                # Fallback to mother_bio if AI fails or returns None
                data['new_bio'] = ai_bio if ai_bio else campaign.get('mother_bio')
            elif campaign.get('mother_bio'):
                # Use mother bio as-is or with slight variations
                data['new_bio'] = campaign['mother_bio']

            # Username strategy
            if campaign['username_strategy'] == 'creative' and name_shortcuts:
                data['new_username'] = self._generate_creative_username(name_shortcuts, i)
            elif campaign['username_strategy'] == 'variation' and campaign['mother_account']:
                data['new_username'] = self._generate_username_variation(
                    campaign['mother_account'], i
                )
            elif campaign['username_strategy'] == 'ai' and campaign['use_ai']:
                data['new_username'] = self._generate_ai_username(campaign, account)

            profile_data.append(data)

        return profile_data

    def _generate_creative_username(self, name_shortcuts, index):
        """
        Generate creative username using shortcuts and extensions

        Args:
            name_shortcuts: List like ['chantall', 'chantie', 'chan']
            index: Account index for variation

        Returns:
            str: Creative username like 'chantie.private', 'chan.fit', etc.
        """
        import random

        # Creative extensions that work well for Instagram
        extensions = [
            'private', 'real', 'official', 'vip', 'exclusive',
            'fun', 'fit', 'play', 'life', 'style',
            'daily', 'vibes', 'mood', 'energy', 'aura',
            'club', 'squad', 'crew', 'fam', 'tribe',
            'glam', 'chic', 'luxe', 'elite', 'prime',
            'hq', 'hub', 'zone', 'world', 'universe',
            'moments', 'stories', 'tales', 'diary', 'notes',
            'insider', 'secret', 'mystique', 'enigma',
            'goddess', 'queen', 'star', 'icon', 'legend'
        ]

        # Select shortcut (rotate through them)
        shortcut = name_shortcuts[index % len(name_shortcuts)]

        # Select extension (use different pattern for variety)
        ext_index = (index // len(name_shortcuts)) % len(extensions)
        extension = extensions[ext_index]

        # Different patterns
        patterns = [
            f"{shortcut}.{extension}",      # chantie.private
            f"{shortcut}_{extension}",      # chantie_private
            f"{extension}.{shortcut}",      # private.chantie
            f"{shortcut}{extension}",       # chantieprivate
        ]

        # Choose pattern based on index
        pattern = patterns[index % len(patterns)]

        return pattern

    def _generate_username_variation(self, base_username, index):
        """Generate username variation"""
        variations = [
            f"{base_username}{index + 1}",
            f"{base_username}.{index + 1}",
            f"{base_username}_{index + 1}",
        ]
        return variations[index % len(variations)]

    def _generate_ai_bio(self, campaign, account):
        """Generate bio using AI"""
        try:
            from ai_profile_generator import AIProfileGenerator

            api_key = campaign.get('ai_api_key')
            if not api_key:
                return None

            generator = AIProfileGenerator(
                api_key=api_key,
                provider='openai'
            )

            mother_bio = campaign.get('mother_bio', '')
            if not mother_bio:
                return None

            # Generate bio variation
            result = generator.generate_bio(
                mother_bio=mother_bio,
                context=f"Account {account['username']} on device {account['device_serial']}"
            )

            return result if result else None

        except Exception as e:
            print(f"AI bio generation failed: {e}")
            return None

    def _generate_ai_username(self, campaign, account):
        """Generate username using AI"""
        try:
            from ai_profile_generator import AIProfileGenerator

            api_key = campaign.get('ai_api_key')
            if not api_key:
                return None

            generator = AIProfileGenerator(
                api_key=api_key,
                provider='openai'
            )

            mother_username = campaign.get('mother_account', '')
            if not mother_username:
                return None

            # Generate username variation
            result = generator.generate_username(
                mother_username=mother_username,
                existing_usernames=[]  # Could track these to avoid duplicates
            )

            return result if result else None

        except Exception as e:
            print(f"AI username generation failed: {e}")
            return None

    def _get_instagram_package(self, device_serial, username):
        """
        Get Instagram package name from account's settings.db

        Args:
            device_serial: Device serial number
            username: Account username

        Returns:
            str: Instagram package name (e.g., 'com.instagram.androide')
        """
        settings_db_path = BASE_DIR / device_serial / username / "settings.db"

        if not settings_db_path.exists():
            print(f"Warning: Settings not found for {device_serial}/{username}, using default package")
            return 'com.instagram.android'

        try:
            conn = sqlite3.connect(settings_db_path)
            cursor = conn.cursor()

            # Read current settings
            cursor.execute('SELECT settings FROM accountsettings WHERE id = 1')
            row = cursor.fetchone()

            if row and row[0]:
                settings = json.loads(row[0])

                # Try app_cloner field first (format: "com.instagram.androie/com.instagram.mainactivity.mainactivity")
                app_cloner = settings.get('app_cloner', '')
                if app_cloner and '/' in app_cloner:
                    # Extract just the package name (before the slash)
                    package = app_cloner.split('/')[0]
                    conn.close()
                    return package

                # Fallback to instagram_package field
                package = settings.get('instagram_package', 'com.instagram.android')
                conn.close()
                return package
            else:
                conn.close()
                return 'com.instagram.android'

        except Exception as e:
            print(f"Error reading package for {device_serial}/{username}: {e}")
            return 'com.instagram.android'


if __name__ == "__main__":
    automation = TagBasedAutomation()

    print("="*70)
    print("TESTING TAG-BASED AUTOMATION (Reading from settings.db)")
    print("="*70)

    print("\n1. Getting all accounts with tags...")
    all_accounts = automation.get_all_accounts_with_tags()
    print(f"Found {len(all_accounts)} total accounts")

    for acc in all_accounts[:5]:
        print(f"  - {acc['username']} on {acc['device_serial']}: tags='{acc['tags']}'")

    print("\n2. Getting all unique tags...")
    tags = automation.get_tags()
    print(f"Found {len(tags)} unique tags:")
    for tag in tags:
        print(f"  - {tag['name']}: {tag['account_count']} accounts")

    if tags:
        first_tag = tags[0]['name']
        print(f"\n3. Getting accounts with tag '{first_tag}'...")
        tagged_accounts = automation.get_accounts_by_tag(first_tag)
        print(f"Found {len(tagged_accounts)} accounts with tag '{first_tag}':")
        for acc in tagged_accounts:
            print(f"  - {acc['username']} on {acc['device_serial']}")
