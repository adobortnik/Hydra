"""
Auto-restart wrapper for the Hydra Dashboard.
Keeps the Flask server alive — if it crashes, logs the reason and restarts.

Usage:
    python run_dashboard.py
"""

import subprocess
import sys
import os
import time
import datetime

DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(DASHBOARD_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

SCRIPT = os.path.join(DASHBOARD_DIR, 'simple_app.py')
RESTART_DELAY = 5        # seconds between restarts
MAX_RAPID_RESTARTS = 5   # if it crashes this many times in RAPID_WINDOW, back off
RAPID_WINDOW = 60        # seconds — crashes within this window count as "rapid"
BACKOFF_DELAY = 120       # seconds to wait after too many rapid crashes


def log(msg):
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(os.path.join(LOG_DIR, 'watchdog.log'), 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def run():
    crash_times = []

    while True:
        log(f"Starting dashboard (PID will follow)...")
        start = time.time()

        try:
            proc = subprocess.Popen(
                [sys.executable, SCRIPT],
                cwd=DASHBOARD_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
            )
            log(f"Dashboard started (PID: {proc.pid})")

            # Stream output to console + log file
            log_path = os.path.join(LOG_DIR, 'dashboard_stdout.log')
            with open(log_path, 'a', encoding='utf-8') as out_log:
                for line in proc.stdout:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    out_log.write(line)
                    out_log.flush()

            proc.wait()
            exit_code = proc.returncode

        except Exception as e:
            exit_code = -1
            log(f"Exception launching dashboard: {e}")

        elapsed = time.time() - start
        log(f"Dashboard exited (code={exit_code}, ran for {elapsed:.0f}s)")

        # Track rapid crashes
        now = time.time()
        crash_times.append(now)
        crash_times = [t for t in crash_times if now - t < RAPID_WINDOW]

        if len(crash_times) >= MAX_RAPID_RESTARTS:
            log(f"Too many rapid crashes ({len(crash_times)} in {RAPID_WINDOW}s) — backing off {BACKOFF_DELAY}s")
            time.sleep(BACKOFF_DELAY)
            crash_times.clear()
        else:
            log(f"Restarting in {RESTART_DELAY}s...")
            time.sleep(RESTART_DELAY)


if __name__ == '__main__':
    log("=" * 60)
    log("Dashboard watchdog starting")
    log("=" * 60)
    try:
        run()
    except KeyboardInterrupt:
        log("Watchdog stopped (Ctrl+C)")
