#!/usr/bin/env python3
"""
SuperProxy Controller
======================
UI automation module for controlling the SuperProxy app on Android devices
via uiautomator2 / ADB.

Usage:
    from automation.superproxy import SuperProxyController
    from automation.device_connection import get_connection

    conn = get_connection("10.1.11.101_5555")
    device = conn.ensure_connected()

    sp = SuperProxyController(device, "10.1.11.101:5555")
    sp.open_app()
    sp.is_proxy_active()
    sp.set_proxy("1.2.3.4", 8080, username="user", password="pass")
    sp.toggle_proxy(enable=True)

Notes:
    - The exact UI element IDs/layout depend on the SuperProxy version installed.
    - Run superproxy_inspect.py first to discover the UI structure.
    - This module uses heuristic matching (text/class patterns) to be resilient
      across SuperProxy versions.
"""

import os
import re
import time
import json
import logging
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime

log = logging.getLogger(__name__)

# Directory for cached package names and UI dumps
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'superproxy_dumps')


class SuperProxyController:
    """
    Controls the SuperProxy Android app on a single device.

    Args:
        device:        uiautomator2 device object (from u2.connect())
        device_serial: ADB serial string, e.g. "10.1.11.101:5555"
    """

    # Confirmed package name
    PACKAGE_NAME = 'com.scheler.superproxy'

    # Fallback list (only used if the confirmed package isn't installed)
    KNOWN_PACKAGES = [
        'com.scheler.superproxy',
        'com.nickhurst.superproxy',
        'com.scheler.superproxy.paid',
        'org.nickhurst.superproxy',
        'com.superproxy',
        'com.superproxy.android',
    ]

    # Text patterns indicating proxy is active/connected
    ACTIVE_PATTERNS = [
        'connected', 'on', 'active', 'running', 'enabled',
        'vpn is on', 'proxy running', 'tap to disconnect',
    ]

    # Text patterns indicating proxy is inactive/disconnected
    INACTIVE_PATTERNS = [
        'disconnected', 'off', 'inactive', 'stopped', 'disabled',
        'not connected', 'tap to connect',
    ]

    def __init__(self, device, device_serial):
        self.device = device
        self.device_serial = device_serial
        self._package_name = None
        self._last_xml = None
        self._last_elements = None

    # ------------------------------------------------------------------
    # Package Discovery
    # ------------------------------------------------------------------

    def discover_package(self, force=False):
        """
        Get the SuperProxy package name for this device.

        Uses the confirmed package name (com.scheler.superproxy) directly.
        Only falls back to discovery if that package isn't installed on the device.

        Args:
            force: Re-discover even if cached.

        Returns:
            str: Package name, or None if not found.
        """
        if self._package_name and not force:
            return self._package_name

        # Use the confirmed package name directly
        self._package_name = self.PACKAGE_NAME
        return self._package_name

    # ------------------------------------------------------------------
    # App Control
    # ------------------------------------------------------------------

    def open_app(self):
        """
        Open the SuperProxy app on the device.

        Returns:
            dict: {success: bool, package: str, message: str}
        """
        package = self.discover_package()
        if not package:
            return {
                'success': False,
                'package': None,
                'message': 'SuperProxy package not found on device'
            }

        try:
            log.info("[%s] Opening SuperProxy (%s)...", self.device_serial, package)

            # Try u2 app_start first
            try:
                self.device.app_start(package)
                time.sleep(3)
            except Exception:
                # Fallback to monkey command
                self._adb_shell(f'monkey -p {package} -c android.intent.category.LAUNCHER 1')
                time.sleep(3)

            # Verify it opened
            current = self._get_current_package()
            if current == package:
                return {
                    'success': True,
                    'package': package,
                    'message': f'SuperProxy opened successfully'
                }
            else:
                # Sometimes the activity name differs but it still opened
                return {
                    'success': True,
                    'package': package,
                    'message': f'SuperProxy launched (foreground: {current})'
                }

        except Exception as e:
            log.error("[%s] Failed to open SuperProxy: %s", self.device_serial, e)
            return {
                'success': False,
                'package': package,
                'message': f'Failed to open: {str(e)}'
            }

    def close_app(self):
        """Force-stop the SuperProxy app."""
        package = self.discover_package()
        if package:
            try:
                self.device.app_stop(package)
            except Exception:
                self._adb_shell(f'am force-stop {package}')

    # ------------------------------------------------------------------
    # Proxy Status
    # ------------------------------------------------------------------

    def is_proxy_active(self):
        """
        Check if the proxy is currently active/connected.

        Analyzes the UI hierarchy for status indicators:
        - Text matching connected/active patterns
        - Switch/toggle state
        - VPN status bar indicator

        Returns:
            dict: {active: bool, confidence: str, indicators: list}
        """
        result = {
            'active': False,
            'confidence': 'low',
            'indicators': [],
            'raw_texts': [],
        }

        try:
            # Method 1: Check VPN interface (most reliable)
            vpn_check = self._adb_shell('ifconfig tun0 2>/dev/null || echo NO_VPN')
            if 'NO_VPN' not in vpn_check and vpn_check.strip():
                result['indicators'].append('VPN tun0 interface exists')
                result['active'] = True
                result['confidence'] = 'high'

            # Method 2: Check for VPN service
            vpn_service = self._adb_shell('dumpsys connectivity | grep -i vpn | head -5')
            if 'CONNECTED' in vpn_service.upper():
                result['indicators'].append('VPN connectivity: CONNECTED')
                result['active'] = True
                result['confidence'] = 'high'

            # Method 3: Analyze UI hierarchy
            elements = self._get_ui_elements()
            all_texts = [e.get('text', '').lower() for e in elements if e.get('text')]
            result['raw_texts'] = [e.get('text', '') for e in elements if e.get('text')]

            # Check text elements for status patterns
            for text in all_texts:
                for pattern in self.ACTIVE_PATTERNS:
                    if pattern in text:
                        result['indicators'].append(f'UI text match: "{text}" contains "{pattern}"')
                        result['active'] = True
                        if result['confidence'] == 'low':
                            result['confidence'] = 'medium'

                for pattern in self.INACTIVE_PATTERNS:
                    if pattern in text:
                        result['indicators'].append(f'UI text match: "{text}" contains "{pattern}"')
                        result['active'] = False
                        if result['confidence'] == 'low':
                            result['confidence'] = 'medium'

            # Check switches/toggles
            for elem in elements:
                cls = elem.get('class', '').lower()
                if 'switch' in cls or 'toggle' in cls:
                    checked = elem.get('checked', 'false')
                    result['indicators'].append(f'Switch found: checked={checked}')
                    if checked == 'true':
                        result['active'] = True
                        result['confidence'] = 'high'

        except Exception as e:
            log.error("[%s] Status check failed: %s", self.device_serial, e)
            result['error'] = str(e)

        return result

    def get_current_proxy(self):
        """
        Read the current proxy settings from the app UI.

        Returns:
            dict: {host, port, type, username, status, raw_data}
        """
        proxy_info = {
            'host': None,
            'port': None,
            'type': None,
            'username': None,
            'status': 'unknown',
            'raw_data': {},
        }

        try:
            elements = self._get_ui_elements()
            texts = [e.get('text', '') for e in elements if e.get('text')]

            # Look for IP:port patterns
            ip_port_pattern = re.compile(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})[:\s]+(\d{2,5})')
            for text in texts:
                match = ip_port_pattern.search(text)
                if match:
                    proxy_info['host'] = match.group(1)
                    proxy_info['port'] = int(match.group(2))
                    break

            # Look for proxy type
            for text in texts:
                text_lower = text.lower()
                if 'socks5' in text_lower:
                    proxy_info['type'] = 'SOCKS5'
                elif 'socks4' in text_lower:
                    proxy_info['type'] = 'SOCKS4'
                elif 'http' in text_lower and 'https' not in text_lower:
                    proxy_info['type'] = 'HTTP'
                elif 'https' in text_lower:
                    proxy_info['type'] = 'HTTPS'

            # Determine status from UI
            status_result = self.is_proxy_active()
            proxy_info['status'] = 'active' if status_result['active'] else 'inactive'
            proxy_info['raw_data'] = {
                'all_texts': texts,
                'status_indicators': status_result['indicators'],
            }

        except Exception as e:
            log.error("[%s] get_current_proxy failed: %s", self.device_serial, e)
            proxy_info['error'] = str(e)

        return proxy_info

    # ------------------------------------------------------------------
    # Proxy Control
    # ------------------------------------------------------------------

    def toggle_proxy(self, enable=True):
        """
        Turn proxy on or off.

        Finds the main toggle/connect button and clicks it.

        Args:
            enable: True to enable, False to disable.

        Returns:
            dict: {success: bool, message: str, was_active: bool, is_active: bool}
        """
        result = {
            'success': False,
            'message': '',
            'was_active': False,
            'is_active': False,
        }

        try:
            # Check current state
            status = self.is_proxy_active()
            was_active = status['active']
            result['was_active'] = was_active

            # If already in desired state, skip
            if (enable and was_active) or (not enable and not was_active):
                result['success'] = True
                result['is_active'] = was_active
                result['message'] = f'Proxy already {"active" if enable else "inactive"}'
                return result

            # Find and click the toggle
            clicked = False

            # Strategy 1: Find switch/toggle widget
            elements = self._get_ui_elements()
            for elem in elements:
                cls = elem.get('class', '').lower()
                if 'switch' in cls or 'toggle' in cls:
                    bounds = elem.get('bounds', '')
                    if bounds:
                        self._click_bounds(bounds)
                        clicked = True
                        break

            # Strategy 2: Find connect/disconnect button by text
            if not clicked:
                connect_texts = ['connect', 'start', 'enable', 'on', 'tap to connect']
                disconnect_texts = ['disconnect', 'stop', 'disable', 'off', 'tap to disconnect']
                target_texts = connect_texts if enable else disconnect_texts

                for elem in elements:
                    text = elem.get('text', '').lower()
                    if text and any(t in text for t in target_texts):
                        if elem.get('clickable') == 'true':
                            bounds = elem.get('bounds', '')
                            if bounds:
                                self._click_bounds(bounds)
                                clicked = True
                                break

            # Strategy 3: Find the main large button (often the connect button)
            if not clicked:
                for elem in elements:
                    cls = elem.get('class', '').lower()
                    if 'button' in cls and elem.get('clickable') == 'true':
                        text = elem.get('text', '').lower()
                        desc = elem.get('content-desc', '').lower()
                        combined = text + ' ' + desc
                        # Skip small utility buttons
                        if any(skip in combined for skip in ['settings', 'menu', 'back', 'close']):
                            continue
                        bounds = elem.get('bounds', '')
                        if bounds:
                            self._click_bounds(bounds)
                            clicked = True
                            break

            if not clicked:
                result['message'] = 'Could not find toggle/connect button'
                return result

            # Wait and verify
            time.sleep(3)
            new_status = self.is_proxy_active()
            result['is_active'] = new_status['active']
            result['success'] = new_status['active'] == enable
            result['message'] = f'Proxy toggled {"on" if enable else "off"}'

            # Handle VPN permission dialog
            if enable and not result['success']:
                # Check for VPN permission dialog
                vpn_ok = self._handle_vpn_dialog()
                if vpn_ok:
                    time.sleep(3)
                    new_status = self.is_proxy_active()
                    result['is_active'] = new_status['active']
                    result['success'] = new_status['active'] == enable

        except Exception as e:
            log.error("[%s] toggle_proxy failed: %s", self.device_serial, e)
            result['message'] = f'Error: {str(e)}'

        return result

    def set_proxy(self, host, port, proxy_type='HTTP', username=None, password=None):
        """
        Set a new proxy configuration in SuperProxy.

        This is the most complex operation — requires UI navigation.
        The exact steps depend on SuperProxy's version/layout, which is why
        the inspect script should be run first.

        Args:
            host:       Proxy IP or hostname
            port:       Proxy port (int)
            proxy_type: 'HTTP', 'SOCKS5', etc.
            username:   Auth username (optional)
            password:   Auth password (optional)

        Returns:
            dict: {success: bool, message: str, details: dict}
        """
        result = {
            'success': False,
            'message': '',
            'details': {
                'host': host,
                'port': port,
                'type': proxy_type,
                'username': username,
            }
        }

        try:
            # Ensure app is open
            open_result = self.open_app()
            if not open_result['success']:
                result['message'] = f'Could not open SuperProxy: {open_result["message"]}'
                return result

            time.sleep(2)

            # Get UI elements
            elements = self._get_ui_elements()

            # Look for input fields (EditText elements)
            edit_fields = [e for e in elements if 'edittext' in e.get('class', '').lower()]
            
            # Also look for elements with proxy-related resource IDs
            host_fields = [e for e in elements if any(
                kw in (e.get('resource-id', '') + e.get('text', '') + e.get('content-desc', '')).lower()
                for kw in ['host', 'server', 'ip', 'address']
            )]
            
            port_fields = [e for e in elements if any(
                kw in (e.get('resource-id', '') + e.get('text', '') + e.get('content-desc', '')).lower()
                for kw in ['port']
            )]

            # Strategy: Try to identify host and port fields
            host_set = False
            port_set = False

            # Try resource-ID matched fields first
            for field in host_fields:
                if 'edittext' in field.get('class', '').lower():
                    bounds = field.get('bounds', '')
                    if bounds:
                        self._click_bounds(bounds)
                        time.sleep(0.5)
                        self.device.clear_text()
                        self.device.send_keys(str(host))
                        host_set = True
                        break

            for field in port_fields:
                if 'edittext' in field.get('class', '').lower():
                    bounds = field.get('bounds', '')
                    if bounds:
                        self._click_bounds(bounds)
                        time.sleep(0.5)
                        self.device.clear_text()
                        self.device.send_keys(str(port))
                        port_set = True
                        break

            # Fallback: if we have EditText fields but couldn't match by ID,
            # assume first is host, second is port
            if not host_set and len(edit_fields) >= 1:
                bounds = edit_fields[0].get('bounds', '')
                if bounds:
                    self._click_bounds(bounds)
                    time.sleep(0.5)
                    self.device.clear_text()
                    self.device.send_keys(str(host))
                    host_set = True

            if not port_set and len(edit_fields) >= 2:
                bounds = edit_fields[1].get('bounds', '')
                if bounds:
                    self._click_bounds(bounds)
                    time.sleep(0.5)
                    self.device.clear_text()
                    self.device.send_keys(str(port))
                    port_set = True

            # Set credentials if provided
            if username and password:
                user_fields = [e for e in elements if any(
                    kw in (e.get('resource-id', '') + e.get('content-desc', '')).lower()
                    for kw in ['user', 'login', 'username']
                ) and 'edittext' in e.get('class', '').lower()]
                
                pass_fields = [e for e in elements if any(
                    kw in (e.get('resource-id', '') + e.get('content-desc', '')).lower()
                    for kw in ['pass', 'password']
                ) and 'edittext' in e.get('class', '').lower()]

                if user_fields:
                    bounds = user_fields[0].get('bounds', '')
                    if bounds:
                        self._click_bounds(bounds)
                        time.sleep(0.5)
                        self.device.clear_text()
                        self.device.send_keys(username)

                if pass_fields:
                    bounds = pass_fields[0].get('bounds', '')
                    if bounds:
                        self._click_bounds(bounds)
                        time.sleep(0.5)
                        self.device.clear_text()
                        self.device.send_keys(password)

            # Try to set proxy type
            self._set_proxy_type(proxy_type, elements)

            # Look for save/apply button
            save_clicked = False
            for elem in elements:
                text = (elem.get('text', '') + ' ' + elem.get('content-desc', '')).lower()
                if any(kw in text for kw in ['save', 'apply', 'ok', 'confirm', 'done']):
                    if elem.get('clickable') == 'true':
                        bounds = elem.get('bounds', '')
                        if bounds:
                            self._click_bounds(bounds)
                            save_clicked = True
                            break

            # Press back to dismiss keyboard if needed
            self.device.press('back')
            time.sleep(1)

            result['success'] = host_set or port_set
            if host_set and port_set:
                result['message'] = 'Proxy settings updated'
            elif host_set:
                result['message'] = 'Host set, but could not identify port field'
            elif port_set:
                result['message'] = 'Port set, but could not identify host field'
            else:
                result['message'] = 'Could not find any input fields — run inspect script to discover UI layout'

            result['details']['host_set'] = host_set
            result['details']['port_set'] = port_set
            result['details']['save_clicked'] = save_clicked

        except Exception as e:
            log.error("[%s] set_proxy failed: %s", self.device_serial, e)
            result['message'] = f'Error: {str(e)}'

        return result

    # ------------------------------------------------------------------
    # UI Inspection (for dashboard use)
    # ------------------------------------------------------------------

    def inspect_ui(self):
        """
        Dump the current UI hierarchy for inspection.

        Returns:
            dict with raw XML, parsed elements, screenshot info, etc.
        """
        result = {
            'package': self.discover_package(),
            'timestamp': datetime.now().isoformat(),
            'elements': [],
            'text_elements': [],
            'clickable_elements': [],
            'switches': [],
            'buttons': [],
            'edit_fields': [],
        }

        try:
            xml_content = self.device.dump_hierarchy()
            result['xml_length'] = len(xml_content) if xml_content else 0

            if xml_content:
                parsed = self._parse_xml(xml_content)
                result.update(parsed)

                # Extract edit fields specifically
                result['edit_fields'] = [
                    e for e in parsed.get('elements', [])
                    if 'edittext' in e.get('class', '').lower()
                ]
        except Exception as e:
            result['error'] = str(e)

        return result

    def take_screenshot(self):
        """
        Take a screenshot and return as base64 PNG.

        Returns:
            str: base64-encoded PNG, or None on failure.
        """
        try:
            import io
            import base64
            img = self.device.screenshot()
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            return base64.b64encode(buf.getvalue()).decode('ascii')
        except Exception as e:
            log.error("[%s] Screenshot failed: %s", self.device_serial, e)
            return None

    # ------------------------------------------------------------------
    # Private Helpers
    # ------------------------------------------------------------------

    def _adb_shell(self, cmd, timeout=15):
        """Run ADB shell command on this device."""
        full_cmd = ['adb', '-s', self.device_serial, 'shell'] + cmd.split()
        try:
            r = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)
            return r.stdout.strip()
        except Exception as e:
            return f"ERROR: {e}"

    def _get_current_package(self):
        """Get current foreground package."""
        try:
            return self.device.app_current().get('package', '')
        except Exception:
            return ''

    def _get_ui_elements(self, refresh=True):
        """Get parsed UI elements from the hierarchy."""
        if not refresh and self._last_elements:
            return self._last_elements

        try:
            xml = self.device.dump_hierarchy()
            if xml:
                parsed = self._parse_xml(xml)
                self._last_elements = parsed.get('elements', [])
                self._last_xml = xml
                return self._last_elements
        except Exception as e:
            log.error("[%s] UI dump failed: %s", self.device_serial, e)

        return self._last_elements or []

    def _parse_xml(self, xml_content):
        """Parse UI XML into categorized elements."""
        result = {
            'elements': [],
            'text_elements': [],
            'clickable_elements': [],
            'switches': [],
            'buttons': [],
        }

        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            return result

        for node in root.iter('node'):
            attrs = node.attrib
            elem = {
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
            result['elements'].append(elem)

            if elem['text']:
                result['text_elements'].append(elem)
            if elem['clickable'] == 'true':
                result['clickable_elements'].append(elem)

            cls = elem['class'].lower()
            if 'switch' in cls or 'toggle' in cls or 'checkbox' in cls:
                result['switches'].append(elem)
            if 'button' in cls:
                result['buttons'].append(elem)

        return result

    def _click_bounds(self, bounds_str):
        """
        Click at the center of a bounds string like "[0,0][100,200]".
        """
        match = re.findall(r'\[(\d+),(\d+)\]', bounds_str)
        if len(match) == 2:
            x1, y1 = int(match[0][0]), int(match[0][1])
            x2, y2 = int(match[1][0]), int(match[1][1])
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            self.device.click(cx, cy)
            return True
        return False

    def _handle_vpn_dialog(self):
        """
        Handle Android's VPN permission dialog ("Connection request").
        Automatically clicks OK/Allow if present.
        """
        try:
            elements = self._get_ui_elements(refresh=True)
            for elem in elements:
                text = elem.get('text', '').lower()
                if text in ['ok', 'allow', 'accept', 'connect']:
                    if elem.get('clickable') == 'true':
                        bounds = elem.get('bounds', '')
                        if bounds:
                            self._click_bounds(bounds)
                            log.info("[%s] Handled VPN permission dialog", self.device_serial)
                            return True
        except Exception:
            pass
        return False

    def _set_proxy_type(self, proxy_type, elements=None):
        """Try to set the proxy type (HTTP/SOCKS5) in the UI."""
        if elements is None:
            elements = self._get_ui_elements()

        # Look for a spinner/dropdown with proxy types
        for elem in elements:
            cls = elem.get('class', '').lower()
            text = elem.get('text', '').lower()
            if ('spinner' in cls or 'dropdown' in cls) and any(
                t in text for t in ['http', 'socks', 'proxy type']
            ):
                bounds = elem.get('bounds', '')
                if bounds:
                    self._click_bounds(bounds)
                    time.sleep(1)
                    # Now find and click the desired type
                    new_elements = self._get_ui_elements(refresh=True)
                    for ne in new_elements:
                        if proxy_type.lower() in ne.get('text', '').lower():
                            nb = ne.get('bounds', '')
                            if nb:
                                self._click_bounds(nb)
                                time.sleep(0.5)
                                return True
        return False

    def _load_cached_package(self):
        """Load cached package name for this device."""
        cache_file = os.path.join(CACHE_DIR, 'package_cache.json')
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    cache = json.load(f)
                return cache.get(self.device_serial)
            except Exception:
                pass
        return None

    def _cache_package(self, package_name):
        """Cache the discovered package name."""
        os.makedirs(CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(CACHE_DIR, 'package_cache.json')
        cache = {}
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    cache = json.load(f)
            except Exception:
                pass
        cache[self.device_serial] = package_name
        with open(cache_file, 'w') as f:
            json.dump(cache, f, indent=2)
