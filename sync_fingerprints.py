"""
Phase 1: Device Fingerprint Collection
========================================
Run this BEFORE moving devices to a new network.
Connects to each known device via ADB, reads hardware identifiers,
and stores them in the database for later matching.

Usage:
    python sync_fingerprints.py              # fingerprint all known devices
    python sync_fingerprints.py --device 10.1.10.192_5555   # single device
"""

import os
import sys
import json
import sqlite3
import subprocess
import argparse
import time
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Database path
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'db', 'phone_farm.db')


def get_connection():
    """Thread-safe connection with Row factory."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_columns():
    """Add hardware_serial and hardware_fingerprint columns if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check existing columns
    cols = [c[1] for c in cursor.execute("PRAGMA table_info(devices)").fetchall()]
    
    if 'hardware_serial' not in cols:
        cursor.execute("ALTER TABLE devices ADD COLUMN hardware_serial TEXT")
        print("[+] Added 'hardware_serial' column to devices table")
    
    if 'hardware_fingerprint' not in cols:
        cursor.execute("ALTER TABLE devices ADD COLUMN hardware_fingerprint TEXT")
        print("[+] Added 'hardware_fingerprint' column to devices table")
    
    conn.commit()
    conn.close()


def db_serial_to_adb(device_serial):
    """Convert DB format (10.1.10.192_5555) to ADB format (10.1.10.192:5555)."""
    return device_serial.replace('_', ':')


def adb_serial_to_db(adb_serial):
    """Convert ADB format (10.1.10.192:5555) to DB format (10.1.10.192_5555)."""
    return adb_serial.replace(':', '_')


def run_adb_command(adb_serial, command, timeout=10):
    """Run an ADB shell command against a device. Returns stdout or None on error."""
    try:
        full_cmd = f'adb -s {adb_serial} shell {command}'
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        return None


def ensure_connected(adb_serial, timeout=5):
    """Ensure the device is connected via ADB."""
    try:
        result = subprocess.run(
            f'adb connect {adb_serial}',
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True
        )
        output = result.stdout.strip()
        return 'connected' in output.lower() or 'already' in output.lower()
    except:
        return False


def collect_fingerprint(device_serial):
    """
    Collect hardware fingerprint from a single device.
    Returns dict with fingerprint data or error info.
    """
    adb_serial = db_serial_to_adb(device_serial)
    result = {
        'device_serial': device_serial,
        'adb_serial': adb_serial,
        'success': False,
        'hardware_serial': None,
        'fingerprint': {},
        'error': None
    }
    
    # Ensure connected
    if not ensure_connected(adb_serial):
        result['error'] = 'Could not connect to device'
        return result
    
    # Small delay after connect
    time.sleep(0.5)
    
    # Read primary hardware serial
    hw_serial = run_adb_command(adb_serial, 'getprop ro.serialno')
    if not hw_serial or hw_serial == '' or hw_serial == 'unknown':
        # Try alternative
        hw_serial = run_adb_command(adb_serial, 'getprop ro.boot.serialno')
    
    if not hw_serial or hw_serial == '' or hw_serial == 'unknown':
        result['error'] = 'Could not read hardware serial (ro.serialno)'
        return result
    
    result['hardware_serial'] = hw_serial
    
    # Collect backup identifiers
    fingerprint = {
        'ro_serialno': hw_serial,
        'ro_boot_serialnumber': run_adb_command(adb_serial, 'getprop ro.boot.serialnumber') or '',
        'ro_product_model': run_adb_command(adb_serial, 'getprop ro.product.model') or '',
        'ro_product_brand': run_adb_command(adb_serial, 'getprop ro.product.brand') or '',
        'ro_product_device': run_adb_command(adb_serial, 'getprop ro.product.device') or '',
        'ro_build_fingerprint': run_adb_command(adb_serial, 'getprop ro.build.fingerprint') or '',
        'wifi_mac': '',
        'bluetooth_mac': '',
        'android_id': '',
        'ig_packages': []
    }
    
    # WiFi MAC address
    wifi_mac = run_adb_command(adb_serial, 'cat /sys/class/net/wlan0/address')
    if wifi_mac and ':' in wifi_mac:
        fingerprint['wifi_mac'] = wifi_mac
    
    # Bluetooth MAC
    bt_mac = run_adb_command(adb_serial, 'settings get secure bluetooth_address')
    if bt_mac and bt_mac != 'null':
        fingerprint['bluetooth_mac'] = bt_mac
    
    # Android ID
    android_id = run_adb_command(adb_serial, 'settings get secure android_id')
    if android_id and android_id != 'null':
        fingerprint['android_id'] = android_id
    
    # IG clone packages
    pkg_output = run_adb_command(adb_serial, 'pm list packages | grep instagram')
    if pkg_output:
        packages = [line.replace('package:', '').strip() for line in pkg_output.split('\n') if line.strip()]
        fingerprint['ig_packages'] = packages
    
    result['fingerprint'] = fingerprint
    result['success'] = True
    
    return result


def store_fingerprint(device_serial, hardware_serial, fingerprint_data):
    """Store fingerprint data in the database."""
    conn = get_connection()
    cursor = conn.cursor()
    
    fingerprint_json = json.dumps(fingerprint_data, indent=2)
    
    cursor.execute(
        """UPDATE devices 
           SET hardware_serial = ?, hardware_fingerprint = ?, updated_at = ?
           WHERE device_serial = ?""",
        (hardware_serial, fingerprint_json, datetime.datetime.now().isoformat(), device_serial)
    )
    
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    
    return rows_affected > 0


def main():
    parser = argparse.ArgumentParser(description='Collect device hardware fingerprints')
    parser.add_argument('--device', help='Specific device serial (DB format: 10.1.10.192_5555)')
    parser.add_argument('--workers', type=int, default=10, help='Number of parallel workers (default: 10)')
    parser.add_argument('--dry-run', action='store_true', help='Collect but do not store in DB')
    args = parser.parse_args()
    
    print("=" * 60)
    print("  Device Fingerprint Collection - Phase 1")
    print("=" * 60)
    print(f"  Database: {DB_PATH}")
    print()
    
    # Ensure columns exist
    ensure_columns()
    
    # Get devices to fingerprint
    conn = get_connection()
    if args.device:
        devices = conn.execute(
            "SELECT device_serial, device_name FROM devices WHERE device_serial = ?",
            (args.device,)
        ).fetchall()
    else:
        devices = conn.execute(
            "SELECT device_serial, device_name FROM devices ORDER BY device_name"
        ).fetchall()
    conn.close()
    
    if not devices:
        print("[!] No devices found in database")
        return
    
    print(f"[*] Found {len(devices)} device(s) to fingerprint")
    print()
    
    # Collect fingerprints in parallel
    results = []
    success_count = 0
    fail_count = 0
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_device = {}
        for device in devices:
            future = executor.submit(collect_fingerprint, device['device_serial'])
            future_to_device[future] = device
        
        for future in as_completed(future_to_device):
            device = future_to_device[future]
            try:
                result = future.result()
                results.append(result)
                
                if result['success']:
                    success_count += 1
                    status_char = '✓'
                    detail = f"hw_serial={result['hardware_serial']}"
                    
                    # Store in DB
                    if not args.dry_run:
                        stored = store_fingerprint(
                            result['device_serial'],
                            result['hardware_serial'],
                            result['fingerprint']
                        )
                        if not stored:
                            detail += " (DB write FAILED)"
                    else:
                        detail += " (dry-run, not stored)"
                else:
                    fail_count += 1
                    status_char = '✗'
                    detail = result['error']
                
                name = device['device_name'] or device['device_serial']
                print(f"  [{status_char}] {name:<25} {device['device_serial']:<25} {detail}")
                
            except Exception as e:
                fail_count += 1
                print(f"  [✗] {device['device_serial']:<25} Exception: {e}")
    
    # Summary
    print()
    print("=" * 60)
    print(f"  Results: {success_count} success, {fail_count} failed, {len(devices)} total")
    print("=" * 60)
    
    if success_count > 0 and not args.dry_run:
        print()
        print("  Fingerprints stored in database. Ready for Phase 2 (sync after move).")
    
    return results


if __name__ == '__main__':
    main()
