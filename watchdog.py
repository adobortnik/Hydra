"""
Bot Watchdog
=============
Monitors bot processes and restarts them if they hang.
Checks the log file modification time — if no new log lines for X minutes,
the bot is considered hung and gets restarted.

Usage:
    python watchdog.py                    # Run once (check + restart)
    python watchdog.py --loop             # Run continuously (every 60s)
    python watchdog.py --loop --interval 120  # Custom interval in seconds
    python watchdog.py --dry-run          # Check only, don't restart
    python watchdog.py --status           # Print status table and exit
"""

import os
import sys
import time
import signal
import logging
import argparse
import subprocess
import datetime
import psutil

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
FARM_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(FARM_DIR, 'logs')
WATCHDOG_LOG = os.path.join(LOGS_DIR, 'watchdog.log')
HUNG_THRESHOLD_MINUTES = 10


def _set_threshold(val):
    global HUNG_THRESHOLD_MINUTES
    HUNG_THRESHOLD_MINUTES = val


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
os.makedirs(LOGS_DIR, exist_ok=True)

logger = logging.getLogger('watchdog')
logger.setLevel(logging.INFO)

# File handler
fh = logging.FileHandler(WATCHDOG_LOG, encoding='utf-8')
fh.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
))
logger.addHandler(fh)

# Console handler
ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(logging.Formatter(
    '\033[36m%(asctime)s\033[0m [%(levelname)s] %(message)s', datefmt='%H:%M:%S'
))
logger.addHandler(ch)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_bot_processes():
    """
    Find all running python processes that match 'run_device.py'.
    Returns dict: { device_serial: psutil.Process }
    """
    bots = {}
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline') or []
            cmd_str = ' '.join(cmdline)
            if 'run_device.py' in cmd_str:
                # Extract device serial from command line
                # Pattern: python run_device.py <serial>
                for i, arg in enumerate(cmdline):
                    if 'run_device.py' in arg and i + 1 < len(cmdline):
                        serial = cmdline[i + 1]
                        # Normalize serial: colon → underscore
                        serial = serial.replace(':', '_')
                        # Skip flags like --dry-run
                        if not serial.startswith('-'):
                            bots[serial] = proc
                            break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return bots


def get_log_file(serial, date_str=None):
    """Get the log file path for a device on a given date."""
    if not date_str:
        date_str = datetime.date.today().strftime('%Y-%m-%d')
    return os.path.join(LOGS_DIR, f'{serial}_{date_str}.log')


def check_log_freshness(serial, threshold_minutes=HUNG_THRESHOLD_MINUTES):
    """
    Check if the bot's log file has been modified recently.
    Returns (is_fresh, last_modified_time, age_minutes)
    """
    log_file = get_log_file(serial)
    if not os.path.exists(log_file):
        return False, None, float('inf')

    mtime = os.path.getmtime(log_file)
    last_mod = datetime.datetime.fromtimestamp(mtime)
    age = (datetime.datetime.now() - last_mod).total_seconds() / 60.0

    return age < threshold_minutes, last_mod, age


def kill_process(proc):
    """Kill a process and all its children."""
    try:
        children = proc.children(recursive=True)
        for child in children:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        proc.kill()
        proc.wait(timeout=10)
        return True
    except (psutil.NoSuchProcess, psutil.TimeoutExpired) as e:
        logger.warning(f"  Issue killing process {proc.pid}: {e}")
        return False


def restart_bot(serial):
    """Start the bot for a device serial."""
    script = os.path.join(FARM_DIR, 'run_device.py')
    # Use the colon format for ADB compatibility
    serial_colon = serial.replace('_', ':')

    logger.info(f"  Starting bot: python -u run_device.py {serial_colon}")
    try:
        proc = subprocess.Popen(
            [sys.executable, '-u', script, serial_colon],
            cwd=FARM_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
        )
        logger.info(f"  Bot started: PID {proc.pid}")
        return proc.pid
    except Exception as e:
        logger.error(f"  Failed to start bot: {e}")
        return None


# ---------------------------------------------------------------------------
# Main watchdog check
# ---------------------------------------------------------------------------

def watchdog_check(dry_run=False):
    """
    Perform one watchdog check cycle.
    1. Find running bot processes
    2. Check each bot's log freshness
    3. Restart hung bots
    """
    now = datetime.datetime.now()
    logger.info(f"=== Watchdog check at {now.strftime('%Y-%m-%d %H:%M:%S')} ===")

    bots = find_bot_processes()
    logger.info(f"Found {len(bots)} running bot process(es)")

    restarts = 0
    for serial, proc in bots.items():
        is_fresh, last_mod, age = check_log_freshness(serial)

        if is_fresh:
            logger.info(f"  [OK] {serial} (PID {proc.pid}) - log age: {age:.1f}min - OK")
        else:
            age_str = f'{age:.1f}min' if last_mod else 'no log today'
            logger.warning(f"  [!!] {serial} (PID {proc.pid}) - log age: {age_str} - HUNG!")

            if dry_run:
                logger.info(f"  [DRY RUN] Would kill PID {proc.pid} and restart")
            else:
                logger.info(f"  Killing PID {proc.pid}...")
                killed = kill_process(proc)
                if killed:
                    time.sleep(2)  # Brief pause before restart
                    new_pid = restart_bot(serial)
                    if new_pid:
                        restarts += 1
                        logger.info(f"  [OK] Restarted {serial} -> PID {new_pid}")
                    else:
                        logger.error(f"  [FAIL] Failed to restart {serial}")
                else:
                    logger.error(f"  [FAIL] Failed to kill hung process for {serial}")

    logger.info(f"Check complete: {len(bots)} bots checked, {restarts} restarted")
    return restarts


def print_status():
    """Print a status table of all known bots."""
    bots = find_bot_processes()
    now = datetime.datetime.now()

    print(f"\n{'='*70}")
    print(f" Bot Watchdog Status — {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")
    print(f" {'Serial':<25} {'PID':<8} {'Log Age':<12} {'Status':<10}")
    print(f" {'-'*25} {'-'*8} {'-'*12} {'-'*10}")

    if not bots:
        print(" (no running bot processes found)")
    else:
        for serial, proc in sorted(bots.items()):
            is_fresh, last_mod, age = check_log_freshness(serial)
            age_str = f'{age:.1f}min' if last_mod else 'no log'
            status = '[OK] Active' if is_fresh else '[!!] HUNG'
            print(f" {serial:<25} {proc.pid:<8} {age_str:<12} {status}")

    print(f"{'='*70}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Bot Watchdog — monitors and restarts hung bots')
    parser.add_argument('--loop', action='store_true', help='Run continuously')
    parser.add_argument('--interval', type=int, default=60, help='Check interval in seconds (default: 60)')
    parser.add_argument('--dry-run', action='store_true', help='Check only, do not restart')
    parser.add_argument('--status', action='store_true', help='Print status table and exit')
    parser.add_argument('--threshold', type=int, default=HUNG_THRESHOLD_MINUTES,
                        help=f'Hung threshold in minutes (default: {HUNG_THRESHOLD_MINUTES})')
    args = parser.parse_args()

    if args.threshold != HUNG_THRESHOLD_MINUTES:
        _set_threshold(args.threshold)

    if args.status:
        print_status()
        return

    logger.info(f"Bot Watchdog started (threshold={HUNG_THRESHOLD_MINUTES}min, "
                f"dry_run={args.dry_run}, loop={args.loop})")

    # Graceful shutdown
    running = [True]
    def signal_handler(sig, frame):
        logger.info("Watchdog shutting down...")
        running[0] = False
    signal.signal(signal.SIGINT, signal_handler)
    if sys.platform == 'win32':
        signal.signal(signal.SIGBREAK, signal_handler)

    if args.loop:
        logger.info(f"Loop mode: checking every {args.interval}s")
        while running[0]:
            try:
                watchdog_check(dry_run=args.dry_run)
            except Exception as e:
                logger.error(f"Watchdog error: {e}")
            # Sleep in small increments for responsive shutdown
            for _ in range(args.interval):
                if not running[0]:
                    break
                time.sleep(1)
    else:
        watchdog_check(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
