#!/usr/bin/env python3
"""
SuperProxy UI Inspector
========================
Standalone script to discover SuperProxy's UI elements on a device.

Usage:
    python superproxy_inspect.py <device_serial>
    python superproxy_inspect.py 10.1.11.101:5555
    python superproxy_inspect.py --all   (inspect all connected devices)

What it does:
    1. Discovers the SuperProxy package name on the device
    2. Opens SuperProxy
    3. Dumps the full XML UI hierarchy
    4. Takes a screenshot
    5. Saves everything to phone-farm/automation/superproxy_dumps/

This data is essential for building the actual SuperProxy automation.
"""

import os
import sys
import time
import json
import subprocess
import argparse
import datetime

# Output directory for dumps
DUMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'superproxy_dumps')


def ensure_dump_dir():
    """Create dump directory if it doesn't exist."""
    os.makedirs(DUMP_DIR, exist_ok=True)


def adb_shell(serial, cmd, timeout=15):
    """Run an ADB shell command and return stdout."""
    full_cmd = ['adb', '-s', serial, 'shell'] + cmd.split()
    try:
        result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return ""
    except Exception as e:
        return f"ERROR: {e}"


# Confirmed SuperProxy package name
SUPERPROXY_PACKAGE = 'com.scheler.superproxy'


def discover_proxy_package(serial):
    """
    Get the SuperProxy package name.
    
    Uses the confirmed package (com.scheler.superproxy) directly.
    Verifies it's installed on the device, falls back to search if not.
    """
    print(f"  [*] Using confirmed package: {SUPERPROXY_PACKAGE}")
    
    # Quick verify it's installed
    check = adb_shell(serial, f'pm path {SUPERPROXY_PACKAGE}')
    if check and check.startswith('package:'):
        print(f"  [✓] Confirmed installed: {SUPERPROXY_PACKAGE}")
        return SUPERPROXY_PACKAGE
    
    # Fallback: search for it in case the package name differs on this device
    print(f"  [!] {SUPERPROXY_PACKAGE} not found, searching...")
    all_packages = adb_shell(serial, 'pm list packages')
    
    if not all_packages or all_packages.startswith('ERROR'):
        print(f"  [!] Failed to list packages: {all_packages}")
        return None
    
    package_list = [p.replace('package:', '') for p in all_packages.split('\n') if p.startswith('package:')]
    
    proxy_packages = [p for p in package_list if 'proxy' in p.lower()]
    print(f"  [*] Found {len(proxy_packages)} proxy-related packages:")
    for p in proxy_packages:
        print(f"      - {p}")
    
    if proxy_packages:
        return proxy_packages[0]
    
    print(f"  [!] No proxy package found on device.")
    return None


def open_app(serial, package):
    """Open an app via ADB monkey command."""
    print(f"  [*] Opening {package}...")
    result = adb_shell(serial, f'monkey -p {package} -c android.intent.category.LAUNCHER 1')
    time.sleep(3)  # Wait for app to launch
    return 'Events injected: 1' in result or 'injected' in result.lower()


def dump_ui_hierarchy(serial):
    """
    Dump the full UI XML hierarchy from the device.
    Returns the XML string.
    """
    print(f"  [*] Dumping UI hierarchy...")
    
    # Method 1: uiautomator dump
    adb_shell(serial, 'uiautomator dump /sdcard/ui_dump.xml')
    time.sleep(1)
    
    # Pull the file
    xml_content = adb_shell(serial, 'cat /sdcard/ui_dump.xml', timeout=30)
    
    # Cleanup
    adb_shell(serial, 'rm /sdcard/ui_dump.xml')
    
    return xml_content


def take_screenshot_adb(serial, output_path):
    """Take a screenshot via ADB and save to local path."""
    print(f"  [*] Taking screenshot...")
    
    # Take screenshot on device
    adb_shell(serial, 'screencap -p /sdcard/superproxy_screenshot.png')
    time.sleep(1)
    
    # Pull to local
    pull_cmd = ['adb', '-s', serial, 'pull', '/sdcard/superproxy_screenshot.png', output_path]
    try:
        subprocess.run(pull_cmd, capture_output=True, timeout=15)
        # Cleanup
        adb_shell(serial, 'rm /sdcard/superproxy_screenshot.png')
        return os.path.exists(output_path)
    except Exception as e:
        print(f"  [!] Screenshot pull failed: {e}")
        return False


def get_current_activity(serial):
    """Get the current foreground activity."""
    result = adb_shell(serial, 'dumpsys activity activities')
    for line in result.split('\n'):
        if 'mResumedActivity' in line or 'mFocusedActivity' in line:
            return line.strip()
    return "unknown"


def inspect_device(serial):
    """
    Full inspection of SuperProxy on a single device.
    Returns a dict with all findings.
    """
    ensure_dump_dir()
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_serial = serial.replace(':', '_').replace('.', '_')
    
    print(f"\n{'='*60}")
    print(f"  Inspecting device: {serial}")
    print(f"{'='*60}")
    
    result = {
        'serial': serial,
        'timestamp': timestamp,
        'package': None,
        'app_opened': False,
        'current_activity': None,
        'ui_xml_file': None,
        'screenshot_file': None,
        'ui_elements': [],
        'clickable_elements': [],
        'text_elements': [],
        'switches': [],
        'buttons': [],
    }
    
    # Step 1: Discover package
    package = discover_proxy_package(serial)
    result['package'] = package
    
    if not package:
        print(f"  [!] Cannot proceed without package name. Skipping device.")
        return result
    
    # Step 2: Open the app
    opened = open_app(serial, package)
    result['app_opened'] = opened
    
    if not opened:
        print(f"  [!] Failed to open {package}")
    
    time.sleep(2)  # Extra wait for UI to settle
    
    # Step 3: Check current activity
    activity = get_current_activity(serial)
    result['current_activity'] = activity
    print(f"  [*] Current activity: {activity}")
    
    # Step 4: Dump UI hierarchy
    xml_content = dump_ui_hierarchy(serial)
    
    if xml_content and not xml_content.startswith('ERROR'):
        # Save XML dump
        xml_filename = f"ui_dump_{safe_serial}_{timestamp}.xml"
        xml_path = os.path.join(DUMP_DIR, xml_filename)
        with open(xml_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)
        result['ui_xml_file'] = xml_path
        print(f"  [✓] UI hierarchy saved: {xml_filename}")
        
        # Parse interesting elements
        result.update(parse_ui_elements(xml_content))
    else:
        print(f"  [!] Failed to dump UI hierarchy")
    
    # Step 5: Take screenshot
    screenshot_filename = f"screenshot_{safe_serial}_{timestamp}.png"
    screenshot_path = os.path.join(DUMP_DIR, screenshot_filename)
    if take_screenshot_adb(serial, screenshot_path):
        result['screenshot_file'] = screenshot_path
        print(f"  [✓] Screenshot saved: {screenshot_filename}")
    
    # Step 6: Try uiautomator2 inspection if available
    try:
        import uiautomator2 as u2
        print(f"  [*] Attempting uiautomator2 inspection...")
        d = u2.connect(serial)
        
        # Get more detailed info
        info = d.info
        result['device_info'] = {
            'displayWidth': info.get('displayWidth'),
            'displayHeight': info.get('displayHeight'),
            'sdk': info.get('sdkInt'),
            'productName': info.get('productName'),
        }
        
        # Dump hierarchy via u2 (more detailed)
        xml_u2 = d.dump_hierarchy()
        if xml_u2:
            xml_u2_filename = f"ui_dump_u2_{safe_serial}_{timestamp}.xml"
            xml_u2_path = os.path.join(DUMP_DIR, xml_u2_filename)
            with open(xml_u2_path, 'w', encoding='utf-8') as f:
                f.write(xml_u2)
            result['ui_xml_u2_file'] = xml_u2_path
            print(f"  [✓] u2 UI hierarchy saved: {xml_u2_filename}")
            
            # Re-parse with u2 dump (usually more complete)
            result.update(parse_ui_elements(xml_u2))
        
    except ImportError:
        print(f"  [!] uiautomator2 not installed — ADB-only inspection")
    except Exception as e:
        print(f"  [!] uiautomator2 inspection failed: {e}")
    
    # Save result summary
    summary_filename = f"inspection_{safe_serial}_{timestamp}.json"
    summary_path = os.path.join(DUMP_DIR, summary_filename)
    
    # Make JSON-serializable
    json_result = {}
    for k, v in result.items():
        try:
            json.dumps(v)
            json_result[k] = v
        except (TypeError, ValueError):
            json_result[k] = str(v)
    
    with open(summary_path, 'w') as f:
        json.dump(json_result, f, indent=2)
    print(f"  [✓] Inspection summary saved: {summary_filename}")
    
    # Print summary
    print(f"\n  --- Summary ---")
    print(f"  Package:       {result['package']}")
    print(f"  App opened:    {result['app_opened']}")
    print(f"  Text elements: {len(result.get('text_elements', []))}")
    print(f"  Buttons:       {len(result.get('buttons', []))}")
    print(f"  Switches:      {len(result.get('switches', []))}")
    print(f"  Clickable:     {len(result.get('clickable_elements', []))}")
    
    return result


def parse_ui_elements(xml_content):
    """
    Parse the UI XML hierarchy and extract interesting elements.
    
    Returns a dict with categorized UI elements.
    """
    import xml.etree.ElementTree as ET
    
    elements = {
        'ui_elements': [],
        'clickable_elements': [],
        'text_elements': [],
        'switches': [],
        'buttons': [],
    }
    
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        print(f"  [!] XML parse error: {e}")
        return elements
    
    for node in root.iter('node'):
        attrs = node.attrib
        
        element_info = {
            'class': attrs.get('class', ''),
            'text': attrs.get('text', ''),
            'resource-id': attrs.get('resource-id', ''),
            'content-desc': attrs.get('content-desc', ''),
            'clickable': attrs.get('clickable', 'false'),
            'checked': attrs.get('checked', ''),
            'bounds': attrs.get('bounds', ''),
            'enabled': attrs.get('enabled', 'true'),
            'package': attrs.get('package', ''),
        }
        
        elements['ui_elements'].append(element_info)
        
        # Text elements (non-empty text)
        if element_info['text']:
            elements['text_elements'].append({
                'text': element_info['text'],
                'class': element_info['class'],
                'resource-id': element_info['resource-id'],
                'bounds': element_info['bounds'],
            })
        
        # Clickable elements
        if element_info['clickable'] == 'true':
            elements['clickable_elements'].append({
                'text': element_info['text'],
                'class': element_info['class'],
                'resource-id': element_info['resource-id'],
                'content-desc': element_info['content-desc'],
                'bounds': element_info['bounds'],
            })
        
        # Switches/toggles
        cls = element_info['class'].lower()
        if 'switch' in cls or 'toggle' in cls or 'checkbox' in cls:
            elements['switches'].append({
                'text': element_info['text'],
                'class': element_info['class'],
                'resource-id': element_info['resource-id'],
                'checked': element_info['checked'],
                'bounds': element_info['bounds'],
            })
        
        # Buttons
        if 'button' in cls:
            elements['buttons'].append({
                'text': element_info['text'],
                'class': element_info['class'],
                'resource-id': element_info['resource-id'],
                'content-desc': element_info['content-desc'],
                'bounds': element_info['bounds'],
            })
    
    return elements


def list_connected_devices():
    """Get list of ADB-connected devices."""
    try:
        result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=10)
        devices = []
        for line in result.stdout.strip().split('\n')[1:]:  # Skip header
            parts = line.split('\t')
            if len(parts) >= 2 and parts[1].strip() == 'device':
                devices.append(parts[0].strip())
        return devices
    except Exception as e:
        print(f"Error listing devices: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description='Inspect SuperProxy UI on Android devices')
    parser.add_argument('device', nargs='?', help='Device serial (e.g., 10.1.11.101:5555)')
    parser.add_argument('--all', action='store_true', help='Inspect all connected devices')
    parser.add_argument('--package', help='Force a specific package name instead of auto-discovering')
    args = parser.parse_args()
    
    print("╔══════════════════════════════════════════╗")
    print("║   SuperProxy UI Inspector v1.0           ║")
    print("╚══════════════════════════════════════════╝")
    
    if args.all:
        devices = list_connected_devices()
        if not devices:
            print("[!] No ADB-connected devices found.")
            sys.exit(1)
        print(f"[*] Found {len(devices)} connected device(s)")
        
        results = []
        for serial in devices:
            result = inspect_device(serial)
            results.append(result)
        
        print(f"\n{'='*60}")
        print(f"  Inspection complete. {len(results)} device(s) inspected.")
        print(f"  Dumps saved to: {DUMP_DIR}")
        print(f"{'='*60}")
        
    elif args.device:
        result = inspect_device(args.device)
        
        print(f"\n{'='*60}")
        print(f"  Inspection complete.")
        print(f"  Dumps saved to: {DUMP_DIR}")
        print(f"{'='*60}")
        
    else:
        # No args — list devices and ask
        devices = list_connected_devices()
        if not devices:
            print("[!] No ADB-connected devices found.")
            print("    Make sure devices are connected: adb devices")
            sys.exit(1)
        
        print(f"\n[*] Connected devices:")
        for i, d in enumerate(devices, 1):
            print(f"    {i}. {d}")
        
        print(f"\nUsage: python {sys.argv[0]} <device_serial>")
        print(f"       python {sys.argv[0]} --all")


if __name__ == '__main__':
    main()
