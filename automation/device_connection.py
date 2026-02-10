"""
Device Connection Manager
==========================
Manages uiautomator2 connections to Android devices with robust reconnect logic.

Uses the proven pattern from login_automation.py:
1. Kill UIAutomator processes first
2. Wait for shutdown
3. u2.connect()
4. Poll device.info + window_size() up to 45s
5. Reconnect on UiAutomationNotConnectedError

Thread-safe: each device gets its own connection tracked in a global registry.
"""

import subprocess
import threading
import time
import logging
import io
import base64

log = logging.getLogger(__name__)

# Global device registry: serial -> DeviceConnection
_connections = {}
_lock = threading.Lock()


class DeviceConnection:
    """Manages a single device's uiautomator2 connection."""

    # Connection states
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"

    def __init__(self, device_serial):
        """
        Args:
            device_serial: DB format e.g. "10.1.10.183_5555"
        """
        self.device_serial = device_serial
        self.adb_serial = device_serial.replace('_', ':')
        self.device = None
        self.status = self.DISCONNECTED
        self.error_message = None
        self.last_connected = None
        self.last_activity = None
        self._lock = threading.Lock()

    def connect(self, timeout=45, max_attempts=2):
        """
        Connect to device using the proven UIAutomator pattern.
        Retries once if the first attempt fails (handles stale UIAutomator).

        Returns:
            device object or None on failure
        """
        with self._lock:
            self.status = self.CONNECTING
            self.error_message = None

        for attempt in range(1, max_attempts + 1):
            try:
                # STEP 1: Kill all existing UIAutomator processes
                log.info("[%s] Attempt %d/%d: Cleaning UIAutomator processes...",
                         self.device_serial, attempt, max_attempts)
                self._kill_uiautomator()
                wait_time = 5 if attempt == 1 else 8  # Wait longer on retry
                time.sleep(wait_time)

                # STEP 2: Connect via uiautomator2
                log.info("[%s] Connecting via u2.connect(%s)...",
                         self.device_serial, self.adb_serial)
                import uiautomator2 as u2
                device = u2.connect(self.adb_serial)
                log.info("[%s] u2.connect() returned (serial: %s)",
                         self.device_serial, device.serial)

                # STEP 3: Poll until responsive
                log.info("[%s] Waiting for UIAutomator to be responsive...",
                         self.device_serial)
                start = time.time()

                while (time.time() - start) < timeout:
                    try:
                        _ = device.info
                        _ = device.window_size()
                        elapsed = int(time.time() - start)
                        log.info("[%s] UIAutomator responsive (took %ds)",
                                 self.device_serial, elapsed)

                        with self._lock:
                            self.device = device
                            self.status = self.CONNECTED
                            self.last_connected = time.time()
                            self.last_activity = time.time()

                        return device
                    except Exception as poll_err:
                        elapsed = int(time.time() - start)
                        if elapsed % 10 == 0 and elapsed > 0:
                            log.info("[%s] Still waiting... %ds/%ds (err: %s)",
                                     self.device_serial, elapsed, timeout,
                                     str(poll_err)[:80])
                        time.sleep(1)

                # Timeout on this attempt
                msg = "UIAutomator not responsive after %ds (attempt %d)" % (timeout, attempt)
                log.warning("[%s] %s", self.device_serial, msg)

                if attempt < max_attempts:
                    log.info("[%s] Retrying connection...", self.device_serial)
                    continue

                with self._lock:
                    self.status = self.ERROR
                    self.error_message = msg
                return None

            except Exception as e:
                msg = str(e)[:200]
                log.error("[%s] Connection attempt %d failed: %s",
                          self.device_serial, attempt, msg)

                if attempt < max_attempts:
                    log.info("[%s] Retrying after error...", self.device_serial)
                    continue

                with self._lock:
                    self.status = self.ERROR
                    self.error_message = msg
                return None

        return None

    def disconnect(self):
        """Disconnect from device, cleanup resources."""
        import gc

        with self._lock:
            device = self.device
            self.device = None
            self.status = self.DISCONNECTED

        if device is None:
            return

        try:
            log.info("[%s] Disconnecting...", self.device_serial)

            # Close HTTP sessions
            for attr in ('_reqsess', 'session', 'http'):
                obj = getattr(device, attr, None)
                if obj and hasattr(obj, 'close'):
                    try:
                        obj.close()
                    except Exception:
                        pass

            # Stop uiautomator
            if hasattr(device, 'stop_uiautomator'):
                try:
                    device.stop_uiautomator()
                except Exception:
                    pass

            # Clean ADB forwards
            try:
                subprocess.run(
                    ['adb', '-s', self.adb_serial, 'forward', '--remove-all'],
                    capture_output=True, timeout=5
                )
                subprocess.run(
                    ['adb', '-s', self.adb_serial, 'shell', 'am', 'force-stop', 'com.github.uiautomator'],
                    capture_output=True, timeout=5
                )
                subprocess.run(
                    ['adb', '-s', self.adb_serial, 'shell', 'am', 'force-stop', 'com.github.uiautomator.test'],
                    capture_output=True, timeout=5
                )
            except Exception:
                pass

            # Dereference and GC
            for attr in ('_reqsess', 'session', 'http'):
                try:
                    setattr(device, attr, None)
                except Exception:
                    pass

            gc.collect()
            log.info("[%s] Disconnected", self.device_serial)

        except Exception as e:
            log.warning("[%s] Disconnect warning: %s", self.device_serial, e)

    def reconnect(self, timeout=45):
        """Disconnect then reconnect."""
        self.disconnect()
        time.sleep(2)
        return self.connect(timeout=timeout)

    def ensure_connected(self):
        """
        Ensure device is connected, reconnecting if needed.
        Returns device or None.
        """
        if self.status == self.CONNECTED and self.device:
            try:
                _ = self.device.info
                self.last_activity = time.time()
                return self.device
            except Exception:
                log.warning("[%s] Connection lost, reconnecting...", self.device_serial)
                return self.reconnect()
        else:
            return self.connect()

    def screenshot(self):
        """
        Take a screenshot and return as base64-encoded PNG.
        Returns base64 string or None.
        """
        device = self.ensure_connected()
        if not device:
            return None

        try:
            img = device.screenshot()
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            self.last_activity = time.time()
            return base64.b64encode(buf.getvalue()).decode('ascii')
        except Exception as e:
            log.error("[%s] Screenshot failed: %s", self.device_serial, e)
            return None

    def screenshot_bytes(self):
        """Take screenshot and return raw PNG bytes."""
        device = self.ensure_connected()
        if not device:
            return None
        try:
            img = device.screenshot()
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            self.last_activity = time.time()
            return buf.getvalue()
        except Exception as e:
            log.error("[%s] Screenshot failed: %s", self.device_serial, e)
            return None

    def app_start(self, package, use_monkey=True):
        """Start an app on the device."""
        device = self.ensure_connected()
        if not device:
            return False

        try:
            device.app_start(package, use_monkey=use_monkey)
            self.last_activity = time.time()
            time.sleep(5)  # Let app launch
            return True
        except Exception as e:
            log.error("[%s] app_start(%s) failed: %s", self.device_serial, package, e)
            # Fallback to ADB monkey
            try:
                subprocess.run(
                    ['adb', '-s', self.adb_serial, 'shell', 'monkey', '-p', package, '1'],
                    capture_output=True, text=True, timeout=10
                )
                time.sleep(5)
                return True
            except Exception:
                return False

    def app_current(self):
        """Get current foreground app package name."""
        device = self.ensure_connected()
        if not device:
            return None
        try:
            return device.app_current().get('package')
        except Exception:
            return None

    def get_status_dict(self):
        """Get status as a dict for API responses."""
        return {
            "device_serial": self.device_serial,
            "adb_serial": self.adb_serial,
            "status": self.status,
            "error": self.error_message,
            "last_connected": self.last_connected,
            "last_activity": self.last_activity,
            "connected": self.status == self.CONNECTED,
        }

    def _kill_uiautomator(self):
        """Kill all UIAutomator processes on the device aggressively."""
        cmds = [
            # Kill uiautomator processes
            ['adb', '-s', self.adb_serial, 'shell', 'pkill', '-9', 'uiautomator'],
            # Force stop uiautomator app
            ['adb', '-s', self.adb_serial, 'shell', 'am', 'force-stop', 'com.github.uiautomator'],
            # Force stop uiautomator test
            ['adb', '-s', self.adb_serial, 'shell', 'am', 'force-stop', 'com.github.uiautomator.test'],
            # Kill instrumentation runner
            ['adb', '-s', self.adb_serial, 'shell', 'pkill', '-9', '-f', 'androidx.test.runner'],
            # Kill any atx-agent
            ['adb', '-s', self.adb_serial, 'shell', 'pkill', '-9', 'atx-agent'],
            # Kill any wetest processes (uia2 server)
            ['adb', '-s', self.adb_serial, 'shell', 'pkill', '-9', '-f', 'com.wetest.uia2'],
            # Remove ADB port forwards
            ['adb', '-s', self.adb_serial, 'forward', '--remove-all'],
        ]
        for cmd in cmds:
            try:
                subprocess.run(cmd, capture_output=True, timeout=5)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Module-level API (singleton registry)
# ---------------------------------------------------------------------------

def get_connection(device_serial):
    """Get or create a DeviceConnection for the given serial."""
    with _lock:
        if device_serial not in _connections:
            _connections[device_serial] = DeviceConnection(device_serial)
        return _connections[device_serial]


def connect_device(device_serial, timeout=45):
    """Connect to a device. Returns device object or None."""
    conn = get_connection(device_serial)
    return conn.connect(timeout=timeout)


def disconnect_device(device_serial):
    """Disconnect from a device."""
    with _lock:
        conn = _connections.get(device_serial)
    if conn:
        conn.disconnect()


def get_all_statuses():
    """Get status dicts for all tracked devices."""
    with _lock:
        return [c.get_status_dict() for c in _connections.values()]


def get_device_status(device_serial):
    """Get status dict for a specific device."""
    with _lock:
        conn = _connections.get(device_serial)
    if conn:
        return conn.get_status_dict()
    return {
        "device_serial": device_serial,
        "status": "unknown",
        "connected": False,
    }


def take_screenshot(device_serial):
    """Take screenshot, return base64 PNG or None."""
    conn = get_connection(device_serial)
    return conn.screenshot()


def take_screenshot_bytes(device_serial):
    """Take screenshot, return raw PNG bytes or None."""
    conn = get_connection(device_serial)
    return conn.screenshot_bytes()
