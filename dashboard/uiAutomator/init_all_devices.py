#!/usr/bin/env python3
"""
Initialize uiautomator2 on all connected devices
Run this once to set up all devices
"""

import subprocess
import sys
from pathlib import Path

def get_connected_devices():
    """Get list of all connected ADB devices"""
    try:
        result = subprocess.run(
            ['adb', 'devices'],
            capture_output=True,
            text=True,
            check=True
        )

        devices = []
        lines = result.stdout.strip().split('\n')[1:]  # Skip header

        for line in lines:
            if line.strip() and 'device' in line:
                serial = line.split()[0]
                devices.append(serial)

        return devices
    except Exception as e:
        print(f"Error getting devices: {e}")
        return []

def init_device(serial):
    """Initialize uiautomator2 on a specific device"""
    print(f"\n{'='*70}")
    print(f"Initializing device: {serial}")
    print('='*70)

    try:
        # Use the same Python executable that's running this script (venv)
        python_exe = sys.executable
        result = subprocess.run(
            [python_exe, '-m', 'uiautomator2', 'init', '--serial', serial],
            capture_output=True,
            text=True,
            timeout=120
        )

        print(result.stdout)
        if result.stderr:
            print(f"Errors: {result.stderr}")

        if result.returncode == 0:
            print(f"✅ Successfully initialized {serial}")
            return True
        else:
            print(f"❌ Failed to initialize {serial}")
            return False

    except subprocess.TimeoutExpired:
        print(f"⚠️ Timeout initializing {serial}")
        return False
    except Exception as e:
        print(f"❌ Error initializing {serial}: {e}")
        return False

def main():
    print("="*70)
    print("UIAUTOMATOR2 DEVICE INITIALIZATION")
    print("="*70)

    # Get all connected devices
    devices = get_connected_devices()

    if not devices:
        print("❌ No devices found!")
        print("\nMake sure devices are connected:")
        print("  adb devices")
        return

    print(f"\nFound {len(devices)} device(s):")
    for i, device in enumerate(devices, 1):
        print(f"  {i}. {device}")

    # Ask for confirmation
    response = input(f"\nInitialize uiautomator2 on all {len(devices)} device(s)? (y/n): ")

    if response.lower() != 'y':
        print("Cancelled.")
        return

    # Initialize each device
    success_count = 0
    failed_devices = []

    for device in devices:
        if init_device(device):
            success_count += 1
        else:
            failed_devices.append(device)

    # Summary
    print("\n" + "="*70)
    print("INITIALIZATION SUMMARY")
    print("="*70)
    print(f"✅ Successful: {success_count}/{len(devices)}")

    if failed_devices:
        print(f"❌ Failed: {len(failed_devices)}")
        for device in failed_devices:
            print(f"   - {device}")

    print("\n💡 Tip: You can now run test_profile_changes.py or use the dashboard")

if __name__ == "__main__":
    main()
