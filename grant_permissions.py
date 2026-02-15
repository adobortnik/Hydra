"""
Grant all required permissions to Instagram clone apps on all connected devices.
Covers: Camera, Microphone, Storage/Files (including Android 13+ media permissions).

Usage: python grant_permissions.py [--device SERIAL] [--packages androie,androif,...]
  No args = all connected devices, all clone packages (androie-androip)
"""

import subprocess
import sys
import argparse
import concurrent.futures
import threading

# All Instagram clone packages (androie through androip = 12 clones)
ALL_PACKAGES = [
    f"com.instagram.androi{c}" for c in "efghijklmnop"
]

# All permissions to grant
PERMISSIONS = [
    # Camera + Microphone
    "android.permission.CAMERA",
    "android.permission.RECORD_AUDIO",
    # Storage (pre-Android 13)
    "android.permission.READ_EXTERNAL_STORAGE",
    "android.permission.WRITE_EXTERNAL_STORAGE",
    # Media (Android 13+ / API 33+)
    "android.permission.READ_MEDIA_IMAGES",
    "android.permission.READ_MEDIA_VIDEO",
    "android.permission.READ_MEDIA_AUDIO",
    "android.permission.ACCESS_MEDIA_LOCATION",
    # Location (prevents IG location prompt dialog)
    "android.permission.ACCESS_FINE_LOCATION",
    "android.permission.ACCESS_COARSE_LOCATION",
]

print_lock = threading.Lock()


def log(msg):
    with print_lock:
        print(msg, flush=True)


def get_connected_devices():
    result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=10)
    devices = []
    for line in result.stdout.strip().split("\n")[1:]:
        line = line.strip()
        if line and "\tdevice" in line:
            devices.append(line.split("\t")[0])
    return devices


def get_installed_packages(serial):
    """Get list of installed IG clone packages on a device."""
    try:
        result = subprocess.run(
            ["adb", "-s", serial, "shell", "pm", "list", "packages", "com.instagram.androi"],
            capture_output=True, text=True, timeout=15
        )
        installed = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line.startswith("package:"):
                pkg = line.replace("package:", "")
                if pkg in ALL_PACKAGES:
                    installed.append(pkg)
        return installed
    except Exception:
        return []


def grant_all_permissions(serial, package):
    """Grant all permissions to one package on one device using a single shell command."""
    # Build a one-liner that grants all permissions in one ADB shell call
    cmds = " ; ".join([f"pm grant {package} {p} 2>/dev/null" for p in PERMISSIONS])
    try:
        result = subprocess.run(
            ["adb", "-s", serial, "shell", cmds],
            capture_output=True, text=True, timeout=30
        )
        return True
    except Exception as e:
        return False


def process_device(serial, packages_filter=None):
    """Process a single device — find installed clones and grant permissions."""
    short_serial = serial if len(serial) < 20 else serial[:17] + "..."
    
    installed = get_installed_packages(serial)
    if packages_filter:
        installed = [p for p in installed if p in packages_filter]
    
    if not installed:
        log(f"  [{short_serial}] No IG clones found, skipping")
        return 0
    
    granted = 0
    for pkg in installed:
        short_pkg = pkg.replace("com.instagram.", "")
        if grant_all_permissions(serial, pkg):
            granted += 1
    
    log(f"  [{short_serial}] Done: {granted} clone(s) x {len(PERMISSIONS)} permissions")
    return granted


def main():
    parser = argparse.ArgumentParser(description="Grant permissions to IG clones")
    parser.add_argument("--device", "-d", help="Specific device serial")
    parser.add_argument("--packages", "-p", help="Comma-separated packages")
    parser.add_argument("--workers", "-w", type=int, default=10, help="Parallel workers (default: 10)")
    args = parser.parse_args()

    if args.device:
        devices = [args.device]
    else:
        devices = get_connected_devices()

    if not devices:
        print("[!] No connected devices found.")
        sys.exit(1)

    packages_filter = None
    if args.packages:
        packages_filter = [
            f"com.instagram.{p}" if not p.startswith("com.") else p 
            for p in args.packages.split(",")
        ]

    print(f"[*] {len(devices)} device(s) found, granting permissions with {args.workers} workers...")
    print(f"[*] Packages: {', '.join(packages_filter or ['all clones (androie-androip)'])}")
    print(f"[*] Permissions: {len(PERMISSIONS)} (camera, mic, storage, media, location)")
    print()

    total = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(process_device, dev, packages_filter): dev 
            for dev in devices
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                total += future.result()
            except Exception as e:
                dev = futures[future]
                log(f"  [{dev}] ERROR: {e}")

    print(f"\n{'='*50}")
    print(f"[*] DONE! Processed {len(devices)} devices, {total} clones updated")
    print(f"[*] Each clone got {len(PERMISSIONS)} permission grants")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
