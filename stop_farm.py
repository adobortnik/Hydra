"""
Phone Farm — Stop all running bot processes.
=============================================
Finds and terminates all python processes running run_device.py.

Usage:
    python stop_farm.py              # graceful stop (SIGINT / Ctrl+C)
    python stop_farm.py --force      # hard kill
    python stop_farm.py --dry-run    # show what would be stopped
"""

import sys
import os
import argparse
import subprocess
import re
import signal

# Colors
CYAN    = "\033[96m"
YELLOW  = "\033[93m"
GREEN   = "\033[92m"
RED     = "\033[91m"
DIM     = "\033[2m"
BOLD    = "\033[1m"
RESET   = "\033[0m"

try:
    import colorama
    colorama.init(autoreset=True)
except ImportError:
    pass


def find_bot_processes():
    """
    Find all python processes running run_device.py.
    Returns list of dicts with pid, command line info.
    """
    processes = []

    try:
        # Use WMIC on Windows to get process details
        result = subprocess.run(
            ["wmic", "process", "where",
             "name like '%python%'",
             "get", "ProcessId,CommandLine", "/format:csv"],
            capture_output=True, text=True, timeout=15
        )

        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("Node,"):
                continue
            # CSV: Node,CommandLine,ProcessId
            parts = line.split(",")
            if len(parts) < 3:
                continue

            pid_str = parts[-1].strip()
            cmdline = ",".join(parts[1:-1]).strip()

            if "run_device.py" in cmdline and pid_str.isdigit():
                # Extract device serial from command line
                serial_match = re.search(r'run_device\.py\s+(\S+)', cmdline)
                serial = serial_match.group(1) if serial_match else "?"

                processes.append({
                    "pid": int(pid_str),
                    "serial": serial,
                    "cmdline": cmdline,
                })
    except Exception as e:
        print(f"{RED}Error scanning processes: {e}{RESET}")

    return processes


def stop_process(pid, force=False):
    """Stop a process by PID. Graceful (Ctrl+C event) or force (kill)."""
    try:
        if force:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                          capture_output=True, timeout=10)
        else:
            # Send Ctrl+C event via taskkill (graceful)
            # On Windows, CTRL_C_EVENT doesn't work cross-process easily,
            # so we use taskkill without /F which sends WM_CLOSE
            subprocess.run(["taskkill", "/PID", str(pid)],
                          capture_output=True, timeout=10)
        return True
    except Exception as e:
        print(f"{RED}  Failed to stop PID {pid}: {e}{RESET}")
        return False


def stop_console_windows():
    """
    Also stop the cmd/powershell windows that are hosting the bot processes.
    These have 'Phone Farm' in their window title.
    """
    try:
        result = subprocess.run(
            ["wmic", "process", "where",
             "name like '%cmd%' or name like '%powershell%'",
             "get", "ProcessId,CommandLine", "/format:csv"],
            capture_output=True, text=True, timeout=15
        )

        pids_to_kill = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("Node,"):
                continue
            parts = line.split(",")
            if len(parts) < 3:
                continue

            pid_str = parts[-1].strip()
            cmdline = ",".join(parts[1:-1]).strip()

            if ("run_device.py" in cmdline) and pid_str.isdigit():
                pids_to_kill.append(int(pid_str))

        return pids_to_kill
    except Exception:
        return []


def main():
    parser = argparse.ArgumentParser(description="Phone Farm — Stop all bot processes")
    parser.add_argument("--force", "-f", action="store_true", help="Force kill (taskkill /F)")
    parser.add_argument("--dry-run", action="store_true", help="Show processes without stopping")
    args = parser.parse_args()

    print(f"\n{BOLD}Phone Farm — Process Stopper{RESET}\n")

    processes = find_bot_processes()

    if not processes:
        print(f"{GREEN}No run_device.py processes found. Farm is already stopped.{RESET}\n")
        return

    print(f"Found {YELLOW}{len(processes)}{RESET} bot process(es):\n")
    for p in processes:
        print(f"  PID {CYAN}{p['pid']:<8}{RESET}  serial={YELLOW}{p['serial']}{RESET}")

    if args.dry_run:
        print(f"\n{DIM}--dry-run: would stop the above processes.{RESET}\n")
        return

    # Stop bot processes
    mode = "FORCE" if args.force else "GRACEFUL"
    print(f"\nStopping ({mode})...\n")

    stopped = 0
    for p in processes:
        print(f"  Stopping PID {p['pid']} ({p['serial']})...", end=" ")
        if stop_process(p["pid"], force=args.force):
            print(f"{GREEN}OK{RESET}")
            stopped += 1
        else:
            print(f"{RED}FAILED{RESET}")

    # Also clean up parent cmd/powershell windows
    parent_pids = stop_console_windows()
    if parent_pids:
        print(f"\n  Cleaning up {len(parent_pids)} hosting window(s)...")
        for pid in parent_pids:
            stop_process(pid, force=True)

    print(f"\n{GREEN}Stopped {stopped}/{len(processes)} bot processes.{RESET}\n")


if __name__ == "__main__":
    main()
