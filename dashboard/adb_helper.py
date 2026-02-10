"""
adb_helper.py - ADB utility functions for device discovery and management.

Wraps subprocess calls to `adb` for use by the dashboard blueprints.
"""

import subprocess
import re
from typing import List, Dict, Tuple


def _run_adb(args: list, timeout: int = 15) -> Tuple[str, str, int]:
    """Run an adb command and return (stdout, stderr, returncode)."""
    cmd = ['adb'] + args
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=0x08000000  # CREATE_NO_WINDOW on Windows
        )
        return proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        return '', 'Timeout', -1
    except FileNotFoundError:
        return '', 'adb not found in PATH', -2
    except Exception as e:
        return '', str(e), -99


def serial_db_to_adb(db_serial: str) -> str:
    """Convert DB serial (10.1.10.177_5555) to ADB format (10.1.10.177:5555)."""
    return db_serial.replace('_', ':')


def serial_adb_to_db(adb_serial: str) -> str:
    """Convert ADB serial (10.1.10.177:5555) to DB format (10.1.10.177_5555)."""
    return adb_serial.replace(':', '_')


def ip_from_serial(serial: str) -> str:
    """Extract IP address from a serial (either format)."""
    clean = serial.replace('_', ':')
    return clean.split(':')[0] if ':' in clean else clean


def discover_devices() -> List[Dict]:
    """
    Run `adb devices` and return list of connected device dicts.

    Returns:
        [
            {
                "adb_serial": "10.1.10.177:5555",
                "db_serial": "10.1.10.177_5555",
                "ip_address": "10.1.10.177",
                "adb_port": 5555,
                "adb_status": "device"  # or "offline", "unauthorized"
            },
            ...
        ]
    """
    stdout, stderr, rc = _run_adb(['devices'])
    if rc != 0:
        return []

    devices = []
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line or line.startswith('List of devices'):
            continue
        # Expected format: "10.1.10.177:5555\tdevice"
        parts = line.split('\t')
        if len(parts) < 2:
            parts = line.split()
        if len(parts) < 2:
            continue

        adb_serial = parts[0].strip()
        adb_status = parts[1].strip()

        # We only care about network devices (IP:port)
        if ':' not in adb_serial:
            continue

        ip_port = adb_serial.split(':')
        ip_addr = ip_port[0]
        try:
            port = int(ip_port[1])
        except (IndexError, ValueError):
            port = 5555

        devices.append({
            'adb_serial': adb_serial,
            'db_serial': serial_adb_to_db(adb_serial),
            'ip_address': ip_addr,
            'adb_port': port,
            'adb_status': adb_status,
        })

    return devices


def check_device_reachable(db_serial: str) -> bool:
    """Check if a specific device is reachable via adb."""
    adb_serial = serial_db_to_adb(db_serial)
    stdout, stderr, rc = _run_adb(['-s', adb_serial, 'shell', 'echo', 'ok'], timeout=8)
    return rc == 0 and 'ok' in stdout


def connect_device(ip_address: str, port: int = 5555) -> Tuple[bool, str]:
    """Connect to a device via adb connect."""
    target = f"{ip_address}:{port}"
    stdout, stderr, rc = _run_adb(['connect', target], timeout=15)
    output = (stdout + stderr).strip()
    success = 'connected' in output.lower() and 'unable' not in output.lower()
    return success, output


def disconnect_device(db_serial: str) -> Tuple[bool, str]:
    """Disconnect a device."""
    adb_serial = serial_db_to_adb(db_serial)
    stdout, stderr, rc = _run_adb(['disconnect', adb_serial], timeout=10)
    return rc == 0, (stdout + stderr).strip()


def get_device_model(db_serial: str) -> str:
    """Get device model name."""
    adb_serial = serial_db_to_adb(db_serial)
    stdout, _, rc = _run_adb(['-s', adb_serial, 'shell', 'getprop', 'ro.product.model'], timeout=8)
    return stdout.strip() if rc == 0 else ''


def get_installed_packages(db_serial: str, filter_str: str = 'instagram') -> List[str]:
    """List installed packages matching a filter."""
    adb_serial = serial_db_to_adb(db_serial)
    stdout, _, rc = _run_adb(
        ['-s', adb_serial, 'shell', 'pm', 'list', 'packages'],
        timeout=15
    )
    if rc != 0:
        return []
    packages = []
    for line in stdout.strip().splitlines():
        pkg = line.replace('package:', '').strip()
        if filter_str.lower() in pkg.lower():
            packages.append(pkg)
    return packages
