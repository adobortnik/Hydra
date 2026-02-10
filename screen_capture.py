"""
screen_capture.py — Quick Screen Capture Utility for Development
================================================================
Grab screenshots from any device for vision-assisted development.

Usage:
    python screen_capture.py <serial>                    # capture + save
    python screen_capture.py <serial> --name login_flow  # custom filename
    python screen_capture.py <serial> --open             # capture + open in viewer
    python screen_capture.py --list                      # list all devices
    python screen_capture.py --jack                      # shortcut for JACK 1 (10.1.11.4:5555)

Screenshots saved to: phone-farm/screenshots/
"""

import subprocess
import sys
import os
import time
from datetime import datetime

SCREENSHOTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
DEVICE_ALIASES = {
    "jack": "10.1.11.4:5555",
    "jack1": "10.1.11.4:5555",
    "jack2": "10.1.11.3:5555",
    "jack3": "10.1.11.2:5555",
}


def ensure_dir():
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


def normalize_serial(serial):
    """Resolve aliases and normalize serial format."""
    alias = serial.lower().replace("-", "").replace("_", "")
    if alias in DEVICE_ALIASES:
        return DEVICE_ALIASES[alias]
    return serial


def list_devices():
    """List all connected ADB devices."""
    result = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True, timeout=10)
    lines = result.stdout.strip().split("\n")[1:]  # skip header
    devices = []
    for line in lines:
        if not line.strip() or "offline" in line:
            continue
        parts = line.split()
        serial = parts[0]
        status = parts[1] if len(parts) > 1 else "unknown"
        model = ""
        for p in parts[2:]:
            if p.startswith("model:"):
                model = p.split(":", 1)[1]
        devices.append({"serial": serial, "status": status, "model": model})
    return devices


def capture_screenshot(serial, name=None):
    """Capture screenshot from device and save locally.
    
    Returns the local file path.
    """
    ensure_dir()
    
    serial = normalize_serial(serial)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    serial_clean = serial.replace(":", "_").replace(".", "-")
    
    if name:
        filename = f"{serial_clean}_{name}_{timestamp}.png"
    else:
        filename = f"{serial_clean}_{timestamp}.png"
    
    local_path = os.path.join(SCREENSHOTS_DIR, filename)
    
    # Method 1: Direct screencap to stdout (fastest, no temp file on device)
    try:
        result = subprocess.run(
            ["adb", "-s", serial, "exec-out", "screencap", "-p"],
            capture_output=True, timeout=15
        )
        if result.returncode == 0 and len(result.stdout) > 1000:
            with open(local_path, "wb") as f:
                f.write(result.stdout)
            size_kb = os.path.getsize(local_path) / 1024
            print(f"[OK] Screenshot saved: {local_path} ({size_kb:.0f} KB)")
            return local_path
    except subprocess.TimeoutExpired:
        print("[WARN] Direct capture timed out, trying fallback...")
    
    # Method 2: Capture on device, then pull (slower but more reliable)
    remote_path = "/sdcard/jarvis_screenshot.png"
    try:
        subprocess.run(
            ["adb", "-s", serial, "shell", "screencap", "-p", remote_path],
            capture_output=True, timeout=15
        )
        subprocess.run(
            ["adb", "-s", serial, "pull", remote_path, local_path],
            capture_output=True, timeout=15
        )
        subprocess.run(
            ["adb", "-s", serial, "shell", "rm", remote_path],
            capture_output=True, timeout=5
        )
        if os.path.exists(local_path):
            size_kb = os.path.getsize(local_path) / 1024
            print(f"[OK] Screenshot saved: {local_path} ({size_kb:.0f} KB)")
            return local_path
    except subprocess.TimeoutExpired:
        pass
    
    print(f"[FAIL] Failed to capture screenshot from {serial}")
    return None


def capture_multiple(serials, name=None):
    """Capture from multiple devices."""
    paths = []
    for serial in serials:
        path = capture_screenshot(serial, name)
        if path:
            paths.append(path)
    return paths


def get_current_app(serial):
    """Get the currently running foreground app."""
    serial = normalize_serial(serial)
    try:
        result = subprocess.run(
            ["adb", "-s", serial, "shell", "dumpsys", "activity", "activities"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.split("\n"):
            if "mResumedActivity" in line or "mFocusedActivity" in line:
                # Extract package name
                parts = line.strip().split()
                for p in parts:
                    if "/" in p and "." in p:
                        return p.split("/")[0].rstrip("}")
        return "unknown"
    except:
        return "unknown"


def get_screen_info(serial):
    """Get device screen resolution."""
    serial = normalize_serial(serial)
    try:
        result = subprocess.run(
            ["adb", "-s", serial, "shell", "wm", "size"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except:
        return "unknown"


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return
    
    if args[0] == "--list":
        devices = list_devices()
        print(f"\n{len(devices)} devices connected:\n")
        for d in devices:
            model = f" ({d['model']})" if d['model'] else ""
            print(f"  {d['serial']:30s}  {d['status']}{model}")
        print()
        print("Aliases:", ", ".join(f"{k}={v}" for k, v in DEVICE_ALIASES.items()))
        return
    
    # Parse args
    serial = args[0].lstrip("-")
    name = None
    do_open = False
    
    # Handle --jack shortcut
    if serial in DEVICE_ALIASES:
        serial = DEVICE_ALIASES[serial]
    
    i = 1
    while i < len(args):
        if args[i] == "--name" and i + 1 < len(args):
            name = args[i + 1]
            i += 2
        elif args[i] == "--open":
            do_open = True
            i += 1
        else:
            i += 1
    
    # Show device info
    app = get_current_app(serial)
    screen = get_screen_info(serial)
    print(f"[DEVICE] {serial}")
    print(f"  Screen: {screen}")
    print(f"  Foreground: {app}")
    print()
    
    # Capture
    path = capture_screenshot(serial, name)
    
    if path and do_open:
        os.startfile(path)


if __name__ == "__main__":
    main()
