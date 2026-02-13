"""
Single-device bot runner.
=========================
Runs the bot loop for ONE device, rotating through its assigned accounts.

Usage:
    python run_device.py <device_serial>
    python run_device.py 10.1.11.4:5555
    python run_device.py 10.1.11.4_5555
    python run_device.py 10.1.11.4:5555 --dry-run
    python run_device.py 10.1.11.4:5555 --once

Serials: accepts both ':' (ADB style) and '_' (DB style) — auto-converts.

Features:
    - Colored console output (device=cyan, account=yellow, actions=green, errors=red)
    - Dual logging: console + file (logs/<device_serial>_<date>.log)
    - Account rotation based on time windows
    - Graceful shutdown on Ctrl+C (SIGINT)
    - Auto-reconnect on device disconnect
    - Summary on exit (actions, errors, runtime)
"""

import sys
import os

# Force unbuffered stdout/stderr so console window shows output immediately
# This is critical on Windows when running in a subprocess (cmd /k)
os.environ['PYTHONUNBUFFERED'] = '1'
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(line_buffering=True)

import re
import signal
import time
import datetime
import logging
import argparse
import sqlite3
import traceback

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
FARM_DIR = os.path.dirname(os.path.abspath(__file__))
if FARM_DIR not in sys.path:
    sys.path.insert(0, FARM_DIR)

DB_PATH = os.path.join(FARM_DIR, "db", "phone_farm.db")
LOG_DIR = os.path.join(FARM_DIR, "logs")

# ---------------------------------------------------------------------------
# ANSI colors (works on Windows 10+ with ENABLE_VIRTUAL_TERMINAL_PROCESSING)
# ---------------------------------------------------------------------------
try:
    import colorama
    colorama.init(autoreset=True)
except ImportError:
    pass

# Colors
CYAN    = "\033[96m"
YELLOW  = "\033[93m"
GREEN   = "\033[92m"
RED     = "\033[91m"
MAGENTA = "\033[95m"
DIM     = "\033[2m"
BOLD    = "\033[1m"
RESET   = "\033[0m"
WHITE   = "\033[97m"


def _ts():
    """Short timestamp for console lines."""
    return datetime.datetime.now().strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# Custom colored console formatter
# ---------------------------------------------------------------------------
class ColoredFormatter(logging.Formatter):
    """Log formatter with colors for console output."""

    LEVEL_COLORS = {
        logging.DEBUG:    DIM,
        logging.INFO:     WHITE,
        logging.WARNING:  YELLOW,
        logging.ERROR:    RED,
        logging.CRITICAL: RED + BOLD,
    }

    def __init__(self, device_tag):
        self.device_tag = device_tag
        super().__init__()

    def format(self, record):
        ts = datetime.datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        lvl_color = self.LEVEL_COLORS.get(record.levelno, WHITE)
        level = record.levelname[0]  # I, W, E, D, C
        msg = record.getMessage()
        return f"{DIM}{ts}{RESET} {CYAN}{self.device_tag}{RESET} {lvl_color}{level} {msg}{RESET}"


class PlainFormatter(logging.Formatter):
    """Plain formatter for file logs — strips ANSI escape codes."""

    ANSI_RE = re.compile(r'\033\[[0-9;]*m')

    def __init__(self, device_tag):
        self.device_tag = device_tag
        fmt = f"%(asctime)s [{device_tag}] %(levelname)-7s %(message)s"
        super().__init__(fmt=fmt, datefmt="%Y-%m-%d %H:%M:%S")

    def format(self, record):
        result = super().format(record)
        return self.ANSI_RE.sub('', result)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_device_info(serial):
    """Get device row from DB. serial is DB format (underscore)."""
    conn = get_db()
    row = conn.execute("SELECT * FROM devices WHERE device_serial=?", (serial,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_device_accounts(serial):
    """Get all active accounts for a device, ordered by start_time."""
    conn = get_db()
    rows = conn.execute("""
        SELECT id, username, status, start_time, end_time, instagram_package
        FROM accounts
        WHERE device_serial=? AND status='active'
        ORDER BY start_time ASC
    """, (serial,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _parse_time_windows(start_str, end_str):
    """
    Parse start_time/end_time into list of (start, end) tuples.
    Supports comma-separated multi-windows: start="2,12" end="4,14" -> [(2,4), (12,14)]
    Single window: start="8" end="16" -> [(8,16)]
    Always-active: start="0" end="0" -> [(0,0)]
    """
    starts = [int(x.strip()) for x in str(start_str or "0").split(",") if x.strip().isdigit()]
    ends = [int(x.strip()) for x in str(end_str or "0").split(",") if x.strip().isdigit()]

    if not starts:
        starts = [0]
    if not ends:
        ends = [0]

    # Pad shorter list to match longer
    while len(ends) < len(starts):
        ends.append(ends[-1])
    while len(starts) < len(ends):
        starts.append(starts[-1])

    return list(zip(starts, ends))


def _is_in_window(now_hour, windows):
    """Check if now_hour falls within any of the time windows."""
    for start, end in windows:
        if start == end:
            continue  # always-active, handled separately
        if start < end:
            if start <= now_hour < end:
                return True
        else:  # wraps midnight
            if now_hour >= start or now_hour < end:
                return True
    return False


def _is_always_active(windows):
    """Check if all windows are always-active (start==end)."""
    return all(s == e for s, e in windows)


def get_current_account(accounts):
    """
    Pick the account whose time window covers the current hour.

    Rules:
        start == end        -> always-active (lowest priority)
        start < end         -> normal range (e.g. 8-16)
        start > end         -> wraps midnight (e.g. 22-4)
        Comma-separated     -> multiple windows (e.g. start="2,12" end="4,14")

    Returns the account dict, or None.
    """
    now_hour = datetime.datetime.now().hour

    # First pass: accounts with specific time windows
    for acct in accounts:
        windows = _parse_time_windows(acct.get("start_time"), acct.get("end_time"))
        if _is_always_active(windows):
            continue  # check later
        if _is_in_window(now_hour, windows):
            return acct

    # Second pass: always-active (start==end, typically 0-0)
    for acct in accounts:
        windows = _parse_time_windows(acct.get("start_time"), acct.get("end_time"))
        if _is_always_active(windows):
            return acct

    return None


# ---------------------------------------------------------------------------
# Setup logging for this device
# ---------------------------------------------------------------------------
def setup_logging(device_serial, device_name):
    """Configure dual logging: colored console + daily file."""
    os.makedirs(LOG_DIR, exist_ok=True)

    tag = f"{device_name} ({device_serial})"
    today = datetime.date.today().strftime("%Y-%m-%d")
    log_file = os.path.join(LOG_DIR, f"{device_serial}_{today}.log")

    # Root logger for this process
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Remove existing handlers
    root.handlers.clear()

    # Console handler (colored, flush after each line)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(ColoredFormatter(tag))

    # Ensure each log line flushes immediately to console
    _orig_emit = ch.emit
    def _flushing_emit(record, _emit=_orig_emit):
        _emit(record)
        ch.flush()
    ch.emit = _flushing_emit

    root.addHandler(ch)

    # File handler (plain)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(PlainFormatter(tag))
    root.addHandler(fh)

    return logging.getLogger("run_device")


# ---------------------------------------------------------------------------
# The main bot loop
# ---------------------------------------------------------------------------
class DeviceRunner:
    """Runs the bot loop for a single device, rotating accounts."""

    def __init__(self, device_serial, device_name, accounts, dry_run=False, once=False):
        self.device_serial = device_serial   # DB format (underscore)
        self.device_name = device_name
        self.accounts = accounts
        self.dry_run = dry_run
        self.once = once
        self._running = True
        self._start_time = time.time()

        # Stats
        self.total_actions = 0
        self.total_errors = 0
        self.accounts_run = set()
        self.action_log = []  # list of (account, action_name, success)

        self.log = logging.getLogger("run_device")

    def stop(self):
        """Signal graceful stop."""
        self._running = False

    def run(self):
        """Main bot loop — keep rotating accounts until stopped."""
        adb_serial = self.device_serial.replace("_", ":")

        self.log.info(f"{GREEN}{'='*60}")
        self.log.info(f"{GREEN}  Phone Farm — Device Runner")
        self.log.info(f"{GREEN}  Device : {CYAN}{self.device_name}")
        self.log.info(f"{GREEN}  Serial : {CYAN}{self.device_serial}")
        self.log.info(f"{GREEN}  ADB    : {CYAN}{adb_serial}")
        self.log.info(f"{GREEN}  Accounts: {YELLOW}{len(self.accounts)}")
        self.log.info(f"{GREEN}{'='*60}")

        # Show accounts
        for acct in self.accounts:
            s, e = acct.get("start_time", "0"), acct.get("end_time", "0")
            windows = _parse_time_windows(s, e)
            if _is_always_active(windows):
                window = "always"
            else:
                window = " + ".join(f"{ws}h-{we}h" for ws, we in windows if ws != we)
            self.log.info(f"  {YELLOW}{acct['username']:<30}{RESET} window={window}  pkg={acct.get('instagram_package','default')}")

        if self.dry_run:
            self.log.info(f"\n{MAGENTA}  --dry-run: would launch bot loop for the above. Exiting.{RESET}")
            return

        # Connect to device first
        self.log.info(f"\n{CYAN}Connecting to device {adb_serial}...{RESET}")
        try:
            from automation.device_connection import get_connection
            conn = get_connection(self.device_serial)

            if conn.status != 'connected' or not conn.device:
                self.log.info(f"{YELLOW}Device not yet connected, attempting connection...{RESET}")
                device = conn.connect(timeout=45, max_attempts=2)
                if not device:
                    self.log.error(f"{RED}Failed to connect to device. Ensure it's on the network.{RESET}")
                    return
            else:
                device = conn.device

            self.log.info(f"{GREEN}Connected! Screen: {device.window_size()}{RESET}")
        except Exception as e:
            self.log.error(f"{RED}Connection error: {e}{RESET}")
            return

        # Lock screen to portrait mode (prevents UIAutomator from flipping to landscape)
        try:
            import subprocess as _sp
            _sp.run(['adb', '-s', adb_serial, 'shell', 'settings', 'put', 'system',
                     'accelerometer_rotation', '0'], capture_output=True, timeout=5)
            _sp.run(['adb', '-s', adb_serial, 'shell', 'settings', 'put', 'system',
                     'user_rotation', '0'], capture_output=True, timeout=5)
            self.log.info(f"{GREEN}Screen locked to portrait mode{RESET}")
        except Exception as e:
            self.log.warning(f"{YELLOW}Could not lock portrait: {e}{RESET}")

        # Main loop
        cycle = 0
        while self._running:
            cycle += 1
            self.log.info(f"\n{BOLD}{'─'*50}")
            self.log.info(f"{BOLD}  Cycle #{cycle}  |  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.log.info(f"{BOLD}{'─'*50}{RESET}")

            # Pick account for current time
            acct = get_current_account(self.accounts)
            if not acct:
                self.log.info(f"{YELLOW}No account active for hour {datetime.datetime.now().hour}. Sleeping 5 min...{RESET}")
                self._sleep(300)
                continue

            username = acct["username"]
            self.accounts_run.add(username)
            self.log.info(f"{YELLOW}Account: {username}{RESET} (id={acct['id']})")

            # Run bot engine
            try:
                from automation.bot_engine import BotEngine
                engine = BotEngine(self.device_serial, acct["id"])
                result = engine.run()

                # Tally stats
                actions_done = result.get("actions_completed", [])
                errors = result.get("errors", [])
                duration = result.get("duration_sec", 0)

                for a in actions_done:
                    action_name = a.get("action", "?")
                    self.total_actions += 1
                    self.action_log.append((username, action_name, True))
                    self.log.info(f"  {GREEN}✓ {action_name}{RESET}")

                for err in errors:
                    self.total_errors += 1
                    self.action_log.append((username, "error", False))
                    self.log.error(f"  {RED}✗ {err}{RESET}")

                self.log.info(
                    f"  Cycle result: {GREEN}{len(actions_done)} actions{RESET}, "
                    f"{RED}{len(errors)} errors{RESET}, "
                    f"{DIM}{duration:.0f}s{RESET}"
                )

            except Exception as e:
                self.total_errors += 1
                self.log.error(f"{RED}Engine error: {e}{RESET}")
                self.log.debug(traceback.format_exc())

                # Try to reconnect
                try:
                    self.log.info(f"{YELLOW}Attempting reconnect...{RESET}")
                    from automation.device_connection import get_connection
                    conn = get_connection(self.device_serial)
                    dev = conn.connect(timeout=45, max_attempts=2)
                    if dev:
                        self.log.info(f"{GREEN}Reconnected.{RESET}")
                    else:
                        self.log.error(f"{RED}Reconnect failed. Will retry next cycle.{RESET}")
                except Exception as re:
                    self.log.error(f"{RED}Reconnect error: {re}{RESET}")

            if self.once:
                self.log.info(f"{MAGENTA}--once mode: exiting after one cycle.{RESET}")
                break

            # Cool down between cycles
            if self._running:
                cooldown = 120  # 2 minutes between full cycles
                self.log.info(f"{DIM}Cooling down {cooldown}s before next cycle...{RESET}")
                self._sleep(cooldown)

    def _sleep(self, seconds):
        """Sleep that respects _running flag (checks every second)."""
        for _ in range(int(seconds)):
            if not self._running:
                break
            time.sleep(1)

    def print_summary(self):
        """Print exit summary."""
        elapsed = time.time() - self._start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        secs = int(elapsed % 60)

        self.log.info(f"\n{BOLD}{'='*60}")
        self.log.info(f"{BOLD}  Session Summary")
        self.log.info(f"{BOLD}{'='*60}{RESET}")
        self.log.info(f"  Device   : {CYAN}{self.device_name} ({self.device_serial}){RESET}")
        self.log.info(f"  Runtime  : {hours}h {minutes}m {secs}s")
        self.log.info(f"  Actions  : {GREEN}{self.total_actions}{RESET}")
        self.log.info(f"  Errors   : {RED}{self.total_errors}{RESET}")
        self.log.info(f"  Accounts : {YELLOW}{len(self.accounts_run)}{RESET} ({', '.join(sorted(self.accounts_run))})")

        if self.action_log:
            self.log.info(f"\n  Action breakdown:")
            from collections import Counter
            counter = Counter(a[1] for a in self.action_log if a[2])
            for action, count in counter.most_common():
                self.log.info(f"    {GREEN}{action:<20}{RESET} x{count}")

        error_count = sum(1 for a in self.action_log if not a[2])
        if error_count:
            self.log.info(f"    {RED}{'errors':<20}{RESET} x{error_count}")

        self.log.info(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Phone Farm — Single Device Bot Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run_device.py 10.1.11.4:5555
    python run_device.py 10.1.11.4_5555 --dry-run
    python run_device.py 10.1.11.4:5555 --once
        """,
    )
    parser.add_argument("device_serial", help="Device serial (e.g. 10.1.11.4:5555 or 10.1.11.4_5555)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run, don't actually start")
    parser.add_argument("--once", action="store_true", help="Run one cycle then exit")
    args = parser.parse_args()

    # Normalize serial to DB format (underscore)
    serial = args.device_serial.replace(":", "_")

    # Get device info
    device = get_device_info(serial)
    if not device:
        print(f"{RED}Error: Device '{serial}' not found in database.{RESET}")
        print(f"{DIM}Available devices:{RESET}")
        conn = get_db()
        rows = conn.execute("SELECT device_serial, device_name FROM devices ORDER BY device_serial").fetchall()
        conn.close()
        for r in rows:
            print(f"  {r['device_serial']}  —  {r['device_name']}")
        sys.exit(1)

    device_name = device["device_name"]

    # Set window title
    os.system(f'title Phone Farm - {device_name} ({serial})')

    # Setup logging
    log = setup_logging(serial, device_name)

    # Get accounts
    accounts = get_device_accounts(serial)
    if not accounts:
        log.error(f"{RED}No active accounts found for {serial}{RESET}")
        sys.exit(1)

    # Create runner
    runner = DeviceRunner(serial, device_name, accounts, dry_run=args.dry_run, once=args.once)

    # Graceful shutdown
    def shutdown_handler(sig, frame):
        log.info(f"\n{YELLOW}Ctrl+C received — stopping gracefully...{RESET}")
        runner.stop()

    signal.signal(signal.SIGINT, shutdown_handler)

    try:
        runner.run()
    except KeyboardInterrupt:
        runner.stop()
    finally:
        runner.print_summary()


if __name__ == "__main__":
    main()
