#!/usr/bin/env python3
"""
API Integration Example for Admin Dashboard
This script demonstrates how to integrate the profile automation system
with your admin dashboard for one-click automation
"""

import sqlite3
import json
from pathlib import Path
import random

from profile_automation_db import (
    init_database, add_profile_update_task,
    get_profile_pictures, add_profile_picture,
    get_bio_templates, PROFILE_PICTURES_DIR
)

class ProfileAutomationAPI:
    """
    API wrapper for profile automation
    Can be integrated into your Flask admin dashboard
    """

    def __init__(self):
        init_database()

    def create_bulk_update_tasks(self, devices_data):
        """
        Create profile update tasks for multiple devices

        Args:
            devices_data: List of device configurations
                [
                    {
                        'device_serial': '192.168.101.107_5555',
                        'instagram_package': 'com.instagram.android',
                        'username': 'current_username',
                        'new_username': 'new_username',
                        'new_bio': 'New bio text',
                        'profile_picture_id': 1  # or None
                    },
                    ...
                ]

        Returns:
            dict: Result with created task IDs
        """
        results = {
            'success': [],
            'failed': []
        }

        for device_data in devices_data:
            try:
                task_id = add_profile_update_task(
                    device_serial=device_data['device_serial'],
                    instagram_package=device_data['instagram_package'],
                    username=device_data.get('username'),
                    new_username=device_data.get('new_username'),
                    new_bio=device_data.get('new_bio'),
                    profile_picture_id=device_data.get('profile_picture_id')
                )

                results['success'].append({
                    'device_serial': device_data['device_serial'],
                    'task_id': task_id
                })

            except Exception as e:
                results['failed'].append({
                    'device_serial': device_data['device_serial'],
                    'error': str(e)
                })

        return results

    def auto_assign_profile_pictures(self, devices, gender=None, unused_only=True):
        """
        Automatically assign profile pictures to devices

        Args:
            devices: List of device serials
            gender: Filter pictures by gender (None = all)
            unused_only: Only use pictures that haven't been used

        Returns:
            dict: Device serial -> profile_picture_id mapping
        """
        # Get available profile pictures
        pictures = get_profile_pictures(gender=gender, unused_only=unused_only)

        if not pictures:
            print("Warning: No profile pictures available!")
            return {}

        # Create mapping
        assignments = {}

        for i, device_serial in enumerate(devices):
            # Rotate through available pictures
            pic_idx = i % len(pictures)
            assignments[device_serial] = pictures[pic_idx]['id']

        return assignments

    def auto_assign_bios(self, devices, category=None):
        """
        Automatically assign bios to devices

        Args:
            devices: List of device serials
            category: Filter bios by category (None = all)

        Returns:
            dict: Device serial -> bio_text mapping
        """
        # Get available bio templates
        bios = get_bio_templates(category=category)

        if not bios:
            print("Warning: No bio templates available!")
            return {}

        # Create mapping
        assignments = {}

        for i, device_serial in enumerate(devices):
            # Rotate through available bios
            bio_idx = i % len(bios)
            assignments[device_serial] = bios[bio_idx]['bio_text']

        return assignments

    def create_random_profile_updates(self, device_serials, instagram_packages=None):
        """
        Create profile update tasks with random assignments

        Args:
            device_serials: List of device serials
            instagram_packages: Dict mapping device_serial -> instagram_package
                               If None, uses 'com.instagram.android' for all

        Returns:
            dict: Result summary
        """
        if not instagram_packages:
            instagram_packages = {d: 'com.instagram.android' for d in device_serials}

        # Get random picture and bio assignments
        picture_assignments = self.auto_assign_profile_pictures(device_serials)
        bio_assignments = self.auto_assign_bios(device_serials)

        # Create tasks
        tasks_data = []

        for device_serial in device_serials:
            task_data = {
                'device_serial': device_serial,
                'instagram_package': instagram_packages.get(device_serial, 'com.instagram.android'),
                'profile_picture_id': picture_assignments.get(device_serial),
                'new_bio': bio_assignments.get(device_serial)
            }
            tasks_data.append(task_data)

        # Create tasks in database
        return self.create_bulk_update_tasks(tasks_data)

    def generate_username_variations(self, base_username, count=10):
        """
        Generate username variations

        Args:
            base_username: Base username to create variations from
            count: Number of variations to generate

        Returns:
            list: List of username variations
        """
        variations = []

        # Method 1: Add numbers
        for i in range(1, count + 1):
            variations.append(f"{base_username}{i}")

        # Method 2: Add underscores and numbers
        for i in range(1, 6):
            variations.append(f"{base_username}_{i}")

        # Method 3: Add letters
        suffixes = ['a', 'b', 'c', 'd', 'e', 'official', 'real', 'ig']
        for suffix in suffixes[:count]:
            variations.append(f"{base_username}.{suffix}")

        return variations[:count]


# Example Flask route integration
"""
Add this to your simple_app.py or create a new routes file:

from api_integration_example import ProfileAutomationAPI

# Initialize API
profile_api = ProfileAutomationAPI()

@app.route('/api/profile_automation/bulk_update', methods=['POST'])
def bulk_profile_update():
    '''
    Endpoint for bulk profile updates

    POST body example:
    {
        "devices": [
            {
                "device_serial": "192.168.101.107_5555",
                "instagram_package": "com.instagram.android",
                "new_username": "newuser123",
                "new_bio": "My new bio",
                "profile_picture_id": 1
            }
        ]
    }
    '''
    try:
        data = request.get_json()
        devices_data = data.get('devices', [])

        results = profile_api.create_bulk_update_tasks(devices_data)

        return jsonify({
            'status': 'success',
            'results': results
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/profile_automation/auto_update', methods=['POST'])
def auto_profile_update():
    '''
    Endpoint for automatic profile updates with random assignments

    POST body example:
    {
        "device_serials": ["192.168.101.107_5555", "192.168.101.108_5555"],
        "instagram_packages": {
            "192.168.101.107_5555": "com.instagram.android",
            "192.168.101.108_5555": "com.instagram.androide"
        }
    }
    '''
    try:
        data = request.get_json()
        device_serials = data.get('device_serials', [])
        instagram_packages = data.get('instagram_packages')

        results = profile_api.create_random_profile_updates(
            device_serials,
            instagram_packages
        )

        return jsonify({
            'status': 'success',
            'results': results
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/profile_automation/profile_pictures', methods=['GET'])
def get_profile_pictures_api():
    '''Get all profile pictures'''
    try:
        pictures = get_profile_pictures()

        return jsonify({
            'status': 'success',
            'pictures': pictures
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/profile_automation/bio_templates', methods=['GET'])
def get_bio_templates_api():
    '''Get all bio templates'''
    try:
        templates = get_bio_templates()

        return jsonify({
            'status': 'success',
            'templates': templates
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
"""


def example_usage():
    """Example usage of the API"""

    api = ProfileAutomationAPI()

    print("="*70)
    print("PROFILE AUTOMATION API - EXAMPLE USAGE")
    print("="*70)

    # Example 1: Create bulk update tasks with specific data
    print("\n--- Example 1: Bulk Update with Specific Data ---\n")

    devices_data = [
        {
            'device_serial': '192.168.101.107_5555',
            'instagram_package': 'com.instagram.android',
            'username': 'olduser1',
            'new_username': 'newuser1',
            'new_bio': 'New bio for user 1',
            'profile_picture_id': 1
        },
        {
            'device_serial': '192.168.101.108_5555',
            'instagram_package': 'com.instagram.androide',
            'username': 'olduser2',
            'new_username': 'newuser2',
            'new_bio': 'New bio for user 2',
            'profile_picture_id': 2
        }
    ]

    results = api.create_bulk_update_tasks(devices_data)
    print(f"Success: {len(results['success'])} tasks created")
    print(f"Failed: {len(results['failed'])} tasks")

    if results['success']:
        print("\nCreated tasks:")
        for item in results['success']:
            print(f"  Device: {item['device_serial']}, Task ID: {item['task_id']}")

    # Example 2: Auto-assign with random selection
    print("\n--- Example 2: Auto-Assign Random Profiles ---\n")

    device_serials = [
        '192.168.101.115_5555',
        '192.168.101.116_5555',
        '192.168.101.155_5555'
    ]

    instagram_packages = {
        '192.168.101.115_5555': 'com.instagram.android',
        '192.168.101.116_5555': 'com.instagram.androide',
        '192.168.101.155_5555': 'com.instagram.androidf'
    }

    results = api.create_random_profile_updates(device_serials, instagram_packages)
    print(f"Auto-assigned profiles to {len(device_serials)} devices")
    print(f"Success: {len(results['success'])}")
    print(f"Failed: {len(results['failed'])}")

    # Example 3: Generate username variations
    print("\n--- Example 3: Generate Username Variations ---\n")

    base_username = "anna.smith"
    variations = api.generate_username_variations(base_username, count=5)

    print(f"Base username: {base_username}")
    print("Variations:")
    for var in variations:
        print(f"  - {var}")

    print("\n" + "="*70)
    print("Run 'python automated_profile_manager.py' to process these tasks")
    print("="*70)


if __name__ == "__main__":
    example_usage()
