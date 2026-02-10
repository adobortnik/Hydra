"""
Phone Farm — Multi-device launcher (Python).
=============================================
Opens a new console window for each device and runs run_device.py in it.

Usage:
    python launch_farm.py                                   # launch ALL devices
    python launch_farm.py --devices 10.1.11.4:5555,10.1.11.3:5555
    python launch_farm.py --dry-run                         # preview only
    python launch_farm.py --once                            # pass --once to each runner
"""

import sys
import os
import argparse
import subprocess
import sqlite3
import time

FARM_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(FARM_DIR, "db", "phone_farm.db")
PYTHON = os.path.join(FARM_DIR, "venv", "Scripts", "python.exe")
if not os.path.exists(PYTHON):
    PYTHON = sys.executable

# Colors
CYAN    = "\033[96m"
YELLOW  = "\033[93m"
GREEN   = "\033[92m"
RED     = "\033[91m"
MAGENTA = "\033[95m"
DIM     = "\033[2m"
BOLD    = "\033[1m"
RESET   = "\033[0m"


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def get_all_devices():
    """Get all devices that have at least one active account."""
    conn = get_db()
    rows = conn.execute("""
        SELECT d.device_serial, d.device_name, d.ip_address,
               COUNT(a.id) as account_count
        FROM devices d
        JOIN accounts a ON a.device_serial = d.device_serial AND a.status = 'active'
        GROUP BY d.device_serial
        ORDER BY d.device_serial
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def launch_device(serial, device_name, extra_args=None):
    """
    Launch a new cmd window running run_device.py for this serial.
    Uses a .bat file for reliable output display in the new window.
    Returns the Popen object.
    """
    adb_serial = serial.replace("_", ":")
    title = f"Phone Farm - {device_name} ({serial})"

    run_script = os.path.join(FARM_DIR, "run_device.py")
    extra = ""
    if extra_args:
        extra = " " + " ".join(extra_args)

    # Write batch launcher for reliable console output
    bat_dir = os.path.join(FARM_DIR, "logs")
    os.makedirs(bat_dir, exist_ok=True)
    bat_file = os.path.join(bat_dir, f"_launch_{serial}.bat")
    with open(bat_file, "w") as f:
        f.write(f"@echo off\n")
        f.write(f"title {title}\n")
        f.write(f'cd /d "{FARM_DIR}"\n')
        f.write(f'echo Starting bot for {device_name} ({adb_serial})...\n')
        f.write(f"echo.\n")
        f.write(f'"{PYTHON}" -u "{run_script}" {adb_serial}{extra}\n')
        f.write(f"echo.\n")
        f.write(f"echo Bot exited. Press any key to close.\n")
        f.write(f"pause >nul\n")

    proc = subprocess.Popen(
        ['cmd', '/c', 'start', '', bat_file],
        shell=False, cwd=FARM_DIR
    )
    return proc


def main():
    parser = argparse.ArgumentParser(
        description="Phone Farm — Launch bot windows for multiple devices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--devices", "-d",
        help="Comma-separated device serials (10.1.11.4:5555,10.1.11.3:5555). Default: ALL.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show plan, don't launch")
    parser.add_argument("--once", action="store_true", help="Pass --once to each runner")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Seconds between launching windows (default: 2)")
    args = parser.parse_args()

    # Gather devices
    all_devices = get_all_devices()

    if args.devices:
        # Filter to requested serials
        requested = set()
        for s in args.devices.split(","):
            s = s.strip().replace(":", "_")
            requested.add(s)

        devices = [d for d in all_devices if d["device_serial"] in requested]
        # Warn about unknown serials
        found = {d["device_serial"] for d in devices}
        missing = requested - found
        if missing:
            print(f"{RED}Warning: these serials not found in DB: {', '.join(missing)}{RESET}")
    else:
        devices = all_devices

    if not devices:
        print(f"{RED}No devices to launch.{RESET}")
        sys.exit(1)

    # Display plan
    print(f"\n{BOLD}{GREEN}{'='*65}")
    print(f"  Phone Farm — Multi-Device Launcher")
    print(f"{'='*65}{RESET}")
    print(f"  Python  : {DIM}{PYTHON}{RESET}")
    print(f"  Devices : {CYAN}{len(devices)}{RESET}")
    print()

    for d in devices:
        serial = d["device_serial"]
        name = d["device_name"]
        count = d["account_count"]
        print(f"  {CYAN}{name:<25}{RESET}  {serial:<22}  {YELLOW}{count} accounts{RESET}")

    print()

    if args.dry_run:
        print(f"{MAGENTA}  --dry-run: would launch {len(devices)} windows. Exiting.{RESET}\n")
        return

    # Launch
    extra = []
    if args.once:
        extra.append("--once")

    print(f"{GREEN}Launching {len(devices)} device windows...{RESET}\n")

    launched = 0
    for d in devices:
        serial = d["device_serial"]
        name = d["device_name"]
        print(f"  Launching {CYAN}{name}{RESET} ({serial})...", end=" ")
        try:
            launch_device(serial, name, extra_args=extra)
            print(f"{GREEN}OK{RESET}")
            launched += 1
        except Exception as e:
            print(f"{RED}FAILED: {e}{RESET}")

        if args.delay > 0 and launched < len(devices):
            time.sleep(args.delay)

    print(f"\n{GREEN}Done. {launched}/{len(devices)} windows launched.{RESET}")
    print(f"{DIM}Use stop_farm.py to shut them all down.{RESET}\n")


if __name__ == "__main__":
    main()
