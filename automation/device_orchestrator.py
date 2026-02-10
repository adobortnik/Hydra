"""
Device Orchestrator
====================
Manages running bot_engine instances across multiple devices.

Responsibilities:
- Start/stop bots per device
- Rotate through accounts on each device based on their time windows
- Track which account is currently active on each device
- Handle device-level scheduling
"""

import logging
import threading
import time
import datetime
import json

log = logging.getLogger(__name__)


def _blog(message, **kwargs):
    """Structured bot log entry."""
    try:
        from automation.bot_logger import log_bot_event
        log_bot_event(message, module="orchestrator", **kwargs)
    except Exception:
        pass


class DeviceOrchestrator:
    """
    Orchestrates bot engines across multiple devices.

    Each device runs one account at a time. The orchestrator decides
    which account should be active based on time windows, then starts
    the bot engine for that device + account pair.
    """

    def __init__(self, poll_interval=60):
        """
        Args:
            poll_interval: Seconds between checks for account rotation
        """
        self.poll_interval = poll_interval
        self._running = False
        self._thread = None
        self._engines = {}       # device_serial -> BotEngine
        self._engine_threads = {}  # device_serial -> Thread
        self._active_accounts = {}  # device_serial -> account_id
        self._lock = threading.Lock()
        self._allowed_devices = None  # None = all, set() = only these serials

    def start(self, device_serials=None):
        """
        Start the orchestrator in a background thread.

        Args:
            device_serials: Optional list of device serials to manage.
                           None = manage ALL devices (production mode).
                           List = only manage these devices (dev/test mode).
        """
        if self._running:
            log.warning("Orchestrator already running")
            return

        if device_serials is not None:
            self._allowed_devices = set(device_serials)
            log.info("Orchestrator restricted to devices: %s", self._allowed_devices)
        else:
            self._allowed_devices = None

        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="DeviceOrchestrator")
        self._thread.start()
        log.info("Device orchestrator started (poll every %ds)", self.poll_interval)
        _blog("Orchestrator started (poll every %ds)" % self.poll_interval)

    def stop(self):
        """Stop the orchestrator and all running engines."""
        log.info("Stopping device orchestrator...")
        self._running = False

        # Stop all engines
        with self._lock:
            for serial, engine in self._engines.items():
                try:
                    engine.stop()
                except Exception as e:
                    log.error("[%s] Error stopping engine: %s", serial, e)
            self._engines.clear()
            self._active_accounts.clear()

        # Wait for main thread
        if self._thread:
            self._thread.join(timeout=30)

        # Wait for engine threads
        for serial, thread in list(self._engine_threads.items()):
            try:
                thread.join(timeout=10)
            except Exception:
                pass
        self._engine_threads.clear()

        log.info("Device orchestrator stopped")

    @property
    def is_running(self):
        return self._running

    def start_device(self, device_serial):
        """
        Start bot processing on a specific device.
        Finds the right account for the current time and starts the engine.
        """
        account = self._get_current_account(device_serial)
        if not account:
            log.info("[%s] No account active for current time", device_serial)
            return False

        return self._start_engine(device_serial, account['id'])

    def stop_device(self, device_serial):
        """Stop bot on a specific device."""
        with self._lock:
            engine = self._engines.get(device_serial)
            if engine:
                engine.stop()
                del self._engines[device_serial]
                self._active_accounts.pop(device_serial, None)
                log.info("[%s] Device stopped", device_serial)
                return True
        return False

    def get_status(self):
        """Get status of all managed devices."""
        with self._lock:
            status = {}
            for serial in set(list(self._engines.keys()) + list(self._active_accounts.keys())):
                engine = self._engines.get(serial)
                status[serial] = {
                    'device_serial': serial,
                    'running': engine is not None and engine._running,
                    'account_id': self._active_accounts.get(serial),
                    'thread_alive': (serial in self._engine_threads and
                                    self._engine_threads[serial].is_alive()),
                }
            return status

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_loop(self):
        """Main orchestrator loop."""
        while self._running:
            try:
                self._check_and_rotate()
            except Exception as e:
                log.error("Orchestrator loop error: %s", e)
            time.sleep(self.poll_interval)

    def _check_and_rotate(self):
        """
        Check devices and rotate accounts as needed.
        Only manages devices that are already manually connected (or in allowed list).
        Does NOT auto-connect devices.
        """
        devices = self._get_active_devices()

        # Filter to only devices already connected (don't auto-connect the farm)
        from automation.device_connection import get_all_statuses
        connected_serials = {s['device_serial'] for s in get_all_statuses()
                            if s.get('connected')}
        devices = [d for d in devices if d['device_serial'] in connected_serials]

        for device in devices:
            serial = device['device_serial']

            # Find the right account for this device at this time
            target_account = self._get_current_account(serial)

            with self._lock:
                current_account_id = self._active_accounts.get(serial)
                engine = self._engines.get(serial)
                thread = self._engine_threads.get(serial)

            # Check if engine thread has died
            if thread and not thread.is_alive():
                log.info("[%s] Engine thread finished, cleaning up", serial)
                with self._lock:
                    self._engines.pop(serial, None)
                    self._engine_threads.pop(serial, None)
                    self._active_accounts.pop(serial, None)
                engine = None
                current_account_id = None

            if target_account is None:
                # No account should be active right now
                if engine and engine._running:
                    log.info("[%s] No account for current time, stopping engine",
                            serial)
                    self.stop_device(serial)
                continue

            target_id = target_account['id']

            if current_account_id == target_id and engine and engine._running:
                # Correct account already running
                continue

            if current_account_id != target_id:
                # Need to switch accounts
                if engine and engine._running:
                    log.info("[%s] Switching account from %s to %s",
                            serial, current_account_id, target_id)
                    _blog("Switching account: %s → %s" % (current_account_id, target_account['username']),
                          device_serial=serial, username=target_account.get('username'))
                    self.stop_device(serial)
                    time.sleep(5)  # Let it clean up

                log.info("[%s] Starting engine for account %d (%s)",
                        serial, target_id, target_account['username'])
                _blog("Starting engine for %s" % target_account['username'],
                      device_serial=serial, username=target_account.get('username'))
                self._start_engine(serial, target_id)

            elif not engine or not engine._running:
                # Same account but engine stopped, restart
                log.info("[%s] Restarting engine for account %d",
                        serial, target_id)
                self._start_engine(serial, target_id)

    def _start_engine(self, device_serial, account_id):
        """Start a bot engine for a device + account."""
        from automation.bot_engine import BotEngine

        # Stop any existing engine
        with self._lock:
            existing = self._engines.get(device_serial)
            if existing and existing._running:
                existing.stop()
                time.sleep(2)

        engine = BotEngine(device_serial, account_id)

        def engine_wrapper():
            try:
                engine.run()
            except Exception as e:
                log.error("[%s] Engine thread error: %s", device_serial, e)
            finally:
                with self._lock:
                    if self._engines.get(device_serial) is engine:
                        self._engines.pop(device_serial, None)
                        self._active_accounts.pop(device_serial, None)

        thread = threading.Thread(
            target=engine_wrapper,
            daemon=True,
            name="BotEngine-%s" % device_serial
        )

        with self._lock:
            self._engines[device_serial] = engine
            self._engine_threads[device_serial] = thread
            self._active_accounts[device_serial] = account_id

        thread.start()
        log.info("[%s] Engine started for account %d", device_serial, account_id)
        return True

    def _get_current_account(self, device_serial):
        """
        Determine which account should be active on this device right now,
        based on time windows.

        Time window rules:
        - start=0, end=0  → always active (24h), lowest priority
        - start=X, end=X  → always active (same hour = 24h), lowest priority
        - start=0, end=2  → midnight to 2am
        - start=22, end=4 → 10pm to 4am (wraps midnight)

        Returns account dict or None.
        """
        try:
            from automation.actions.helpers import get_db
            conn = get_db()

            # Get all active accounts for this device
            rows = conn.execute("""
                SELECT * FROM accounts
                WHERE device_serial=? AND status='active'
                ORDER BY start_time ASC
            """, (device_serial,)).fetchall()
            conn.close()

            if not rows:
                return None

            current_hour = datetime.datetime.now().hour
            accounts = [dict(r) for r in rows]

            # First pass: find account with a specific time window that matches now
            for acct in accounts:
                start_str = str(acct.get('start_time', '0'))
                end_str = str(acct.get('end_time', '0'))

                start_hour = int(start_str) if start_str.isdigit() else 0
                end_hour = int(end_str) if end_str.isdigit() else 0

                # Skip always-active accounts (0,0 or same hour)
                if start_hour == end_hour:
                    continue

                if start_hour < end_hour:
                    # Normal range (e.g., 8-16)
                    if start_hour <= current_hour < end_hour:
                        return acct
                else:
                    # Wraps midnight (e.g., 22-4)
                    if current_hour >= start_hour or current_hour < end_hour:
                        return acct

            # Second pass: if no time-windowed account matches, use always-active
            for acct in accounts:
                start_str = str(acct.get('start_time', '0'))
                end_str = str(acct.get('end_time', '0'))
                start_hour = int(start_str) if start_str.isdigit() else 0
                end_hour = int(end_str) if end_str.isdigit() else 0
                if start_hour == end_hour:
                    return acct

            return None

        except Exception as e:
            log.error("[%s] Error getting current account: %s", device_serial, e)
            return None

    def _get_active_devices(self):
        """Get all devices that should have bots running."""
        try:
            from automation.actions.helpers import get_db
            conn = get_db()

            # Get devices that have at least one active account with ANY action enabled
            rows = conn.execute("""
                SELECT DISTINCT d.device_serial, d.device_name, d.status
                FROM devices d
                JOIN accounts a ON a.device_serial = d.device_serial
                WHERE a.status = 'active'
                ORDER BY d.device_serial
            """).fetchall()
            conn.close()

            devices = [dict(r) for r in rows]

            # Filter to allowed devices if restricted
            if self._allowed_devices is not None:
                devices = [d for d in devices
                           if d['device_serial'] in self._allowed_devices]

            return devices

        except Exception as e:
            log.error("Error getting active devices: %s", e)
            return []


# Module-level singleton
_orchestrator = None


def get_orchestrator():
    """Get the global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = DeviceOrchestrator()
    return _orchestrator
