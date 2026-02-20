"""
Phase 2: Network Discovery + Device Sync
==========================================
Run this AFTER moving devices to a new network.
Scans a given IP range for ADB-enabled devices, reads their hardware serial,
matches them against stored fingerprints, and updates the database.

Usage:
    python sync_devices.py --range 192.168.1.1-254        # scan range
    python sync_devices.py --range 192.168.1.0/24          # CIDR notation
    python sync_devices.py --range 192.168.1.50,192.168.1.51  # specific IPs
    python sync_devices.py --range 192.168.1.0/24 --dry-run   # preview only
    python sync_devices.py --range 192.168.1.0/24 --apply      # auto-apply
"""

import os
import sys
import json
import sqlite3
import subprocess
import argparse
import time
import shutil
import datetime
import ipaddress
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

# Database path
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'db', 'phone_farm.db')
BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'db', 'backups')


def get_connection():
    """Thread-safe connection with Row factory."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def db_serial_to_adb(device_serial):
    """Convert DB format (10.1.10.192_5555) to ADB format (10.1.10.192:5555)."""
    return device_serial.replace('_', ':')


def adb_serial_to_db(adb_serial):
    """Convert ADB format (10.1.10.192:5555) to DB format (10.1.10.192_5555)."""
    return adb_serial.replace(':', '_')


def parse_ip_range(range_str):
    """
    Parse IP range string into list of IPs.
    Supports:
        - CIDR: 192.168.1.0/24
        - Range: 192.168.1.1-254 (last octet range)
        - Comma-separated: 192.168.1.50,192.168.1.51
    """
    range_str = range_str.strip()
    ips = []
    
    # Check for comma-separated IPs
    if ',' in range_str and '/' not in range_str:
        for ip_str in range_str.split(','):
            ip_str = ip_str.strip()
            if ip_str:
                try:
                    ipaddress.ip_address(ip_str)
                    ips.append(ip_str)
                except ValueError:
                    print(f"[!] Invalid IP: {ip_str}")
        return ips
    
    # Check for CIDR notation
    if '/' in range_str:
        try:
            network = ipaddress.ip_network(range_str, strict=False)
            for ip in network.hosts():
                ips.append(str(ip))
            return ips
        except ValueError as e:
            print(f"[!] Invalid CIDR: {range_str} ({e})")
            return []
    
    # Check for range notation: 192.168.1.1-254
    match = re.match(r'^(\d+\.\d+\.\d+\.)(\d+)-(\d+)$', range_str)
    if match:
        prefix = match.group(1)
        start = int(match.group(2))
        end = int(match.group(3))
        for i in range(start, end + 1):
            if 1 <= i <= 254:
                ips.append(f"{prefix}{i}")
        return ips
    
    # Single IP
    try:
        ipaddress.ip_address(range_str)
        return [range_str]
    except ValueError:
        print(f"[!] Could not parse IP range: {range_str}")
        return []


def try_adb_connect(ip, port=5555, timeout=3):
    """
    Try to connect to a device via ADB.
    Returns (ip, port, connected_bool).
    """
    adb_serial = f"{ip}:{port}"
    try:
        result = subprocess.run(
            f'adb connect {adb_serial}',
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True
        )
        output = result.stdout.strip().lower()
        connected = 'connected' in output or 'already' in output
        return (ip, port, connected)
    except subprocess.TimeoutExpired:
        return (ip, port, False)
    except Exception:
        return (ip, port, False)


def read_hardware_serial(ip, port=5555, timeout=10):
    """Read hardware serial from a connected ADB device."""
    adb_serial = f"{ip}:{port}"
    try:
        result = subprocess.run(
            f'adb -s {adb_serial} shell getprop ro.serialno',
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True
        )
        hw_serial = result.stdout.strip()
        if hw_serial and hw_serial != 'unknown' and hw_serial != '':
            return hw_serial
        
        # Try alternative
        result = subprocess.run(
            f'adb -s {adb_serial} shell getprop ro.boot.serialno',
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True
        )
        hw_serial = result.stdout.strip()
        if hw_serial and hw_serial != 'unknown' and hw_serial != '':
            return hw_serial
        
        return None
    except:
        return None


def scan_network(ip_range_str, port=5555, max_workers=50, progress_callback=None):
    """
    Scan an IP range for ADB-enabled devices.
    Returns list of dicts: {ip, port, hardware_serial}
    """
    ips = parse_ip_range(ip_range_str)
    if not ips:
        return []
    
    total = len(ips)
    discovered = []
    scanned = 0
    
    # Phase 1: Try connecting to all IPs in parallel
    connected_ips = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ip = {executor.submit(try_adb_connect, ip, port, 3): ip for ip in ips}
        
        for future in as_completed(future_to_ip):
            scanned += 1
            try:
                ip, p, connected = future.result()
                if connected:
                    connected_ips.append(ip)
                if progress_callback:
                    progress_callback(scanned, total, 'scanning', ip if connected else None)
            except Exception:
                pass
    
    if not connected_ips:
        return []
    
    # Phase 2: Read hardware serial from connected devices
    for ip in connected_ips:
        hw_serial = read_hardware_serial(ip, port)
        if hw_serial:
            discovered.append({
                'ip': ip,
                'port': port,
                'hardware_serial': hw_serial,
                'adb_serial': f"{ip}:{port}",
                'db_serial': f"{ip}_{port}"
            })
            if progress_callback:
                progress_callback(0, 0, 'identified', ip)
    
    return discovered


def match_devices(discovered_devices):
    """
    Match discovered devices against stored fingerprints in DB.
    Returns list of match results.
    """
    conn = get_connection()
    
    # Get all devices with hardware_serial from DB
    db_devices = conn.execute(
        "SELECT id, device_serial, device_name, hardware_serial, ip_address FROM devices WHERE hardware_serial IS NOT NULL AND hardware_serial != ''"
    ).fetchall()
    
    # Also get all devices (even without fingerprints) for reporting
    all_db_devices = conn.execute(
        "SELECT id, device_serial, device_name, hardware_serial, ip_address FROM devices"
    ).fetchall()
    conn.close()
    
    # Build lookup: hardware_serial → db device info
    hw_lookup = {}
    for dev in db_devices:
        hw_serial = dev['hardware_serial']
        if hw_serial:
            hw_lookup[hw_serial] = {
                'id': dev['id'],
                'device_serial': dev['device_serial'],
                'device_name': dev['device_name'],
                'ip_address': dev['ip_address']
            }
    
    # Match results
    results = {
        'matched': [],
        'unmatched_discovered': [],
        'not_found_in_scan': []
    }
    
    matched_hw_serials = set()
    
    for disc in discovered_devices:
        hw_serial = disc['hardware_serial']
        
        if hw_serial in hw_lookup:
            db_dev = hw_lookup[hw_serial]
            match_info = {
                'hardware_serial': hw_serial,
                'old_serial': db_dev['device_serial'],
                'new_serial': disc['db_serial'],
                'old_ip': db_dev['ip_address'],
                'new_ip': disc['ip'],
                'device_name': db_dev['device_name'],
                'device_id': db_dev['id'],
                'changed': db_dev['device_serial'] != disc['db_serial']
            }
            results['matched'].append(match_info)
            matched_hw_serials.add(hw_serial)
        else:
            results['unmatched_discovered'].append({
                'ip': disc['ip'],
                'db_serial': disc['db_serial'],
                'hardware_serial': hw_serial
            })
    
    # Find DB devices that weren't found in the scan
    for dev in all_db_devices:
        hw_serial = dev['hardware_serial']
        if hw_serial and hw_serial not in matched_hw_serials:
            results['not_found_in_scan'].append({
                'device_serial': dev['device_serial'],
                'device_name': dev['device_name'],
                'hardware_serial': hw_serial
            })
        elif not hw_serial:
            results['not_found_in_scan'].append({
                'device_serial': dev['device_serial'],
                'device_name': dev['device_name'],
                'hardware_serial': None,
                'reason': 'no_fingerprint'
            })
    
    return results


def create_backup():
    """Create a timestamped backup of the database."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f'phone_farm_pre_sync_{timestamp}.db')
    shutil.copy2(DB_PATH, backup_path)
    return backup_path


def get_tables_with_device_serial():
    """Find all tables that have a device_serial column."""
    conn = get_connection()
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    
    tables_with_serial = []
    for table in tables:
        cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if 'device_serial' in cols:
            tables_with_serial.append((table, 'device_serial'))
        elif 'deviceid' in cols:
            tables_with_serial.append((table, 'deviceid'))
        elif 'assigned_to_device_serial' in cols:
            tables_with_serial.append((table, 'assigned_to_device_serial'))
        elif 'assigned_device_serial' in cols:
            tables_with_serial.append((table, 'assigned_device_serial'))
    
    conn.close()
    return tables_with_serial


def apply_sync(match_results):
    """
    Apply the device serial updates to all relevant tables.
    Returns a detailed report of all changes made.
    """
    matched = [m for m in match_results['matched'] if m['changed']]
    
    if not matched:
        return {'success': True, 'message': 'No changes needed — all IPs unchanged', 'changes': []}
    
    # Create backup first
    backup_path = create_backup()
    
    # Find all tables that reference device_serial
    tables_with_serial = get_tables_with_device_serial()
    
    conn = get_connection()
    changes = []
    
    try:
        for match in matched:
            old_serial = match['old_serial']
            new_serial = match['new_serial']
            new_ip = match['new_ip']
            device_name = match['device_name']
            
            for table, column in tables_with_serial:
                # Count affected rows first
                count = conn.execute(
                    f"SELECT COUNT(*) as cnt FROM {table} WHERE {column} = ?",
                    (old_serial,)
                ).fetchone()['cnt']
                
                if count > 0:
                    conn.execute(
                        f"UPDATE {table} SET {column} = ? WHERE {column} = ?",
                        (new_serial, old_serial)
                    )
                    changes.append({
                        'table': table,
                        'column': column,
                        'old_value': old_serial,
                        'new_value': new_serial,
                        'rows_affected': count,
                        'device_name': device_name
                    })
            
            # Also update ip_address in devices table
            conn.execute(
                "UPDATE devices SET ip_address = ?, updated_at = ? WHERE device_serial = ?",
                (new_ip, datetime.datetime.now().isoformat(), new_serial)
            )
        
        conn.commit()
        
        return {
            'success': True,
            'backup_path': backup_path,
            'changes': changes,
            'devices_updated': len(matched),
            'message': f'Successfully synced {len(matched)} device(s)'
        }
    
    except Exception as e:
        conn.rollback()
        return {
            'success': False,
            'backup_path': backup_path,
            'error': str(e),
            'changes': [],
            'message': f'FAILED: {e}. Database rolled back. Backup at: {backup_path}'
        }
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='Scan network and sync device IPs')
    parser.add_argument('--range', required=True, help='IP range to scan (CIDR, range, or comma-separated)')
    parser.add_argument('--port', type=int, default=5555, help='ADB port (default: 5555)')
    parser.add_argument('--workers', type=int, default=50, help='Parallel scan workers (default: 50)')
    parser.add_argument('--dry-run', action='store_true', help='Scan and match but do not apply changes')
    parser.add_argument('--apply', action='store_true', help='Apply changes without confirmation prompt')
    args = parser.parse_args()
    
    print("=" * 70)
    print("  Device Network Discovery & Sync - Phase 2")
    print("=" * 70)
    print(f"  Database: {DB_PATH}")
    print(f"  IP Range: {args.range}")
    print(f"  Port: {args.port}")
    print(f"  Workers: {args.workers}")
    print()
    
    # Parse and validate IP range
    ips = parse_ip_range(args.range)
    if not ips:
        print("[!] No valid IPs to scan")
        sys.exit(1)
    
    print(f"[*] Scanning {len(ips)} IP address(es)...")
    print()
    
    # Scan network
    def progress(scanned, total, phase, ip=None):
        if phase == 'scanning' and scanned % 25 == 0:
            print(f"  Scanned {scanned}/{total}...")
        elif phase == 'identified' and ip:
            print(f"  [+] Device found at {ip}")
    
    discovered = scan_network(args.range, args.port, args.workers, progress)
    
    print()
    print(f"[*] Found {len(discovered)} ADB device(s)")
    
    if not discovered:
        print("[!] No devices found. Check that devices are powered on and ADB is enabled.")
        sys.exit(0)
    
    for d in discovered:
        print(f"  {d['ip']}:{d['port']} → hw_serial: {d['hardware_serial']}")
    
    print()
    
    # Match against database
    print("[*] Matching against database fingerprints...")
    results = match_devices(discovered)
    
    # Display results
    print()
    print("=" * 70)
    print("  MATCH RESULTS")
    print("=" * 70)
    
    if results['matched']:
        print(f"\n  ✓ MATCHED ({len(results['matched'])} devices):")
        for m in results['matched']:
            change_indicator = " → " + m['new_serial'] if m['changed'] else " (unchanged)"
            print(f"    {m['device_name'] or 'Unknown':<25} {m['old_serial']}{change_indicator}")
    
    if results['unmatched_discovered']:
        print(f"\n  ? UNMATCHED - New devices ({len(results['unmatched_discovered'])}):")
        for u in results['unmatched_discovered']:
            print(f"    {u['ip']}  hw_serial: {u['hardware_serial']}  (not in DB)")
    
    if results['not_found_in_scan']:
        print(f"\n  ✗ NOT FOUND in scan ({len(results['not_found_in_scan'])}):")
        for n in results['not_found_in_scan']:
            reason = n.get('reason', 'not_responding')
            print(f"    {n['device_name'] or 'Unknown':<25} {n['device_serial']:<25} ({reason})")
    
    # Check if any changes needed
    changes_needed = [m for m in results['matched'] if m['changed']]
    if not changes_needed:
        print("\n  No IP changes detected — all matched devices have the same IPs.")
        return results
    
    print(f"\n  {len(changes_needed)} device(s) need IP updates")
    
    if args.dry_run:
        print("\n  [DRY RUN] No changes applied.")
        return results
    
    # Apply changes
    if not args.apply:
        response = input("\n  Apply changes? (yes/no): ").strip().lower()
        if response not in ('yes', 'y'):
            print("  Aborted.")
            return results
    
    print("\n[*] Creating backup and applying changes...")
    apply_result = apply_sync(results)
    
    if apply_result['success']:
        print(f"\n  ✓ {apply_result['message']}")
        print(f"  Backup: {apply_result.get('backup_path', 'N/A')}")
        if apply_result['changes']:
            print(f"\n  Detailed changes:")
            for c in apply_result['changes']:
                print(f"    {c['table']}.{c['column']}: {c['old_value']} → {c['new_value']} ({c['rows_affected']} rows)")
    else:
        print(f"\n  ✗ {apply_result['message']}")
    
    return results


if __name__ == '__main__':
    main()
