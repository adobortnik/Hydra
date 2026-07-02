"""
Bot Engine
===========
Main bot engine that orchestrates all actions for a single device + account pair.

For a given device + account:
1. Open the account's Instagram clone
2. Check if logged in
3. Run enabled actions (follow, unfollow, like, engage) based on settings
4. Respect time windows (starttime/endtime)
5. Cool down between actions
6. Handle errors gracefully (reconnect on UIAutomator disconnect)
"""

import logging
import os
import random
import time
import datetime
import json
import traceback

log = logging.getLogger(__name__)


def _blog(message, **kwargs):
    """Structured bot log entry. Fails silently if logger not ready."""
    try:
        from automation.bot_logger import log_bot_event
        log_bot_event(message, **kwargs)
    except Exception:
        pass


class BotEngine:
    """
    Core bot engine for a single device + account.

    Usage:
        engine = BotEngine(device_serial, account_id)
        engine.run()
    """

    def __init__(self, device_serial, account_id):
        """
        Args:
            device_serial: DB format serial (e.g. "10.1.11.4_5555")
            account_id: accounts.id
        """
        self.device_serial = device_serial
        self.account_id = account_id
        self.account = None
        self.settings = None
        self.session_id = None
        self._running = False
        self._device_conn = None
        self._device = None

    def _check_pending_login_tasks(self):
        """Check if there are pending login tasks for this device and execute them."""
        try:
            from automation.actions.helpers import get_db
            from automation.device_connection import get_connection
            from automation.login import login_account

            conn = get_db()
            tasks = conn.execute("""
                SELECT * FROM login_tasks
                WHERE device_serial = ? AND status = 'pending'
                ORDER BY priority DESC, created_at ASC
            """, (self.device_serial,)).fetchall()
            conn.close()

            if not tasks:
                return

            for task in tasks:
                task = dict(task)
                log.info("[%s] Processing login task #%d for %s",
                         self.device_serial, task['id'], task['username'])

                # Update task status to running
                conn = get_db()
                conn.execute("UPDATE login_tasks SET status='running', updated_at=? WHERE id=?",
                             (datetime.datetime.now().isoformat(), task['id']))
                conn.commit()
                conn.close()

                # Run login
                device_conn = get_connection(self.device_serial)
                result = login_account(
                    device_conn,
                    username=task['username'],
                    password=task['password'],
                    instagram_package=task['instagram_package'],
                    two_fa_token=task.get('two_fa_token'),
                )

                # Update task result
                conn = get_db()
                now = datetime.datetime.now().isoformat()
                if result.get('success'):
                    conn.execute("""UPDATE login_tasks
                        SET status='completed', completed_at=?, updated_at=? WHERE id=?""",
                        (now, now, task['id']))
                    # Also update the account status to active
                    conn.execute("""UPDATE accounts SET status='active', updated_at=?
                        WHERE device_serial=? AND username=?""",
                        (now, self.device_serial, task['username']))
                    log.info("[%s] Login task #%d SUCCEEDED for %s",
                             self.device_serial, task['id'], task['username'])
                else:
                    error = result.get('error', 'Unknown error')
                    retry = (task.get('retry_count') or 0) + 1
                    max_retries = task.get('max_retries') or 3
                    new_status = 'failed' if retry >= max_retries else 'pending'
                    conn.execute("""UPDATE login_tasks
                        SET status=?, error_message=?, retry_count=?, updated_at=? WHERE id=?""",
                        (new_status, error, retry, now, task['id']))
                    log.warning("[%s] Login task #%d FAILED for %s: %s (retry %d/%d)",
                                self.device_serial, task['id'], task['username'],
                                error, retry, max_retries)
                conn.commit()
                conn.close()

                # Small delay between login tasks
                time.sleep(5)
        except Exception as e:
            log.error("[%s] Error processing login tasks: %s", self.device_serial, e)

    def run(self):
        """
        Run the bot engine for this device + account.

        Returns dict: {success, actions_completed, errors, duration_sec}
        """
        start_time = time.time()
        result = {
            'success': False,
            'actions_completed': [],
            'errors': [],
            'duration_sec': 0,
        }

        try:
            self._running = True
            username = '?'
            log.info("[%s] Bot engine starting for account_id=%d",
                     self.device_serial, self.account_id)

            # Load account data
            if not self._load_account():
                result['errors'].append("Failed to load account data")
                return result

            username = self.account.get('username', '?')

            # ── Early skip for non-runnable account statuses ──
            # Opening IG on a challenged/suspended/2fa-required account each
            # cycle re-triggers IG's pattern detector and amplifies the
            # verification escalation. Just SKIP entirely.
            NON_RUNNABLE_STATUSES = {
                'verification_required',  # IG challenge — needs human
                '2fa_required',           # 2FA prompt — needs human
                'suspended',              # IG suspended — dead
                'banned',                 # IG banned — dead
                'login_failed',           # login worker gave up — let
                                          # login-automation-v2 retry, not bot
                'logged_out',             # similar — login-automation-v2 handles
                'replaced',               # account swapped out
                'disabled',               # operator manually paused
            }
            acc_status = (self.account.get('status') or '').strip().lower()
            if acc_status in NON_RUNNABLE_STATUSES:
                log.info("[%s] %s: status=%s — skipping cycle (non-runnable). "
                         "Resolve via login-automation-v2 or manual review.",
                         self.device_serial, username, acc_status)
                result['success'] = True  # Not an error, just a no-op
                result['skipped_reason'] = acc_status
                return result

            # Check time window
            if not self._is_within_time_window():
                msg = "Outside time window (%s-%s), skipping" % (
                    self.account.get('start_time', '0'),
                    self.account.get('end_time', '0'))
                log.info("[%s] %s: %s", self.device_serial, username, msg)
                result['success'] = True  # Not an error
                return result

            # Connect to device
            if not self._connect_device():
                result['errors'].append("Failed to connect to device")
                return result

            # Process any pending login tasks for this device
            self._check_pending_login_tasks()

            # Check proxy status (SuperProxy VPN must be running)
            skip_proxy = os.environ.get('HYDRA_SKIP_PROXY', '').lower() in ('1', 'true', 'yes')
            # Also check global_settings.json toggle
            if not skip_proxy:
                try:
                    _gs_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                            'dashboard', 'global_settings.json')
                    if os.path.exists(_gs_path):
                        import json as _json
                        with open(_gs_path, 'r') as _f:
                            _gs = _json.load(_f)
                        skip_proxy = bool(_gs.get('skip_proxy_check', False))
                except Exception:
                    pass
            proxy_ok = True if skip_proxy else self._check_proxy_status()
            if skip_proxy:
                log.info("[%s] Proxy check SKIPPED (setting or env)", self.device_serial)
            if not proxy_ok:
                # Try to reconnect Surfshark VPN automatically
                log.warning("[%s] %s: Proxy not active — attempting Surfshark reconnect...",
                            self.device_serial, username)
                reconnected = self._reconnect_surfshark()
                if reconnected:
                    log.info("[%s] %s: Surfshark reconnected successfully!",
                             self.device_serial, username)
                    _blog("VPN reconnected automatically via Surfshark", device=self.device_serial,
                          username=username, level='info', category='proxy')
                else:
                    msg = "Proxy not active on device — skipping to avoid running without proxy"
                    log.warning("[%s] %s: %s", self.device_serial, username, msg)
                    result['errors'].append(msg)
                    _blog(msg, device=self.device_serial, username=username,
                          level='warning', category='proxy')
                    return result

            # Open Instagram
            if not self._open_instagram():
                result['errors'].append("Failed to open Instagram")
                return result
            # Check login state
            if not self._ensure_logged_in():
                result['errors'].append("Not logged in and login failed")
                return result

            # Create session
            from automation.actions.helpers import create_session
            self.session_id = create_session(self.device_serial, username)

            # Update bot status
            self._update_bot_status('running')
            # Run enabled actions
            actions = self._determine_actions()
            action_names = [a[0] for a in actions]
            log.info("[%s] %s: Actions to run: %s",
                     self.device_serial, username, action_names)
            for action_name, action_func in actions:
                if not self._running:
                    log.info("[%s] Bot engine stopped", self.device_serial)
                    break

                try:
                    log.info("[%s] Running action: %s",
                             self.device_serial, action_name)
                    self._lock_portrait()   # re-assert portrait before each action
                    action_result = action_func()
                    result['actions_completed'].append({
                        'action': action_name,
                        'result': action_result,
                    })
                    self._broadcast_action(action_name, action_result)
                    # Cool down between actions
                    if self._running:
                        cooldown = random.randint(30, 90)
                        log.info("[%s] Cooling down for %ds before next action",
                                self.device_serial, cooldown)
                        time.sleep(cooldown)

                except Exception as e:
                    error_msg = "%s error: %s" % (action_name, str(e)[:200])
                    log.error("[%s] %s\n%s", self.device_serial, error_msg,
                             traceback.format_exc())
                    result['errors'].append(error_msg)
                    # Try to recover
                    if not self._recover():
                        log.error("[%s] Recovery failed, stopping", self.device_serial)
                        break

            result['success'] = True

        except Exception as e:
            log.error("[%s] Bot engine fatal error: %s\n%s",
                     self.device_serial, e, traceback.format_exc())
            result['errors'].append("Fatal: %s" % str(e)[:200])

        finally:
            self._running = False
            result['duration_sec'] = time.time() - start_time

            # End session
            if self.session_id:
                from automation.actions.helpers import end_session
                end_session(
                    self.session_id,
                    status='completed' if result['success'] else 'error',
                    actions_executed=json.dumps([a['action'] for a in result['actions_completed']]),
                    errors_count=len(result['errors']),
                    error_details='; '.join(result['errors'][:5]) if result['errors'] else None
                )

            # Update bot status
            self._update_bot_status('idle')

            _username = self.account.get('username', '?') if self.account else '?'
            log.info("[%s] Bot engine finished. Duration: %.0fs, Actions: %d, Errors: %d",
                     self.device_serial, result['duration_sec'],
                     len(result['actions_completed']), len(result['errors']))
        return result

    def stop(self):
        """Signal the engine to stop."""
        self._running = False
        log.info("[%s] Bot engine stop requested", self.device_serial)

    # ------------------------------------------------------------------
    # Internal Methods
    # ------------------------------------------------------------------

    def _load_account(self):
        """Load account and settings from DB."""
        try:
            from automation.actions.helpers import get_db, get_account_settings
            conn = get_db()
            row = conn.execute(
                "SELECT * FROM accounts WHERE id=?", (self.account_id,)
            ).fetchone()
            conn.close()

            if not row:
                log.error("[%s] Account %d not found in DB",
                         self.device_serial, self.account_id)
                return False

            self.account = dict(row)
            self.settings = get_account_settings(self.account_id)
            log.info("[%s] Loaded account: %s (pkg: %s)",
                     self.device_serial, self.account['username'],
                     self.account.get('instagram_package'))
            return True

        except Exception as e:
            log.error("[%s] Failed to load account: %s", self.device_serial, e)
            return False

    def _is_within_time_window(self):
        """
        Check if current local time is within account's active time window.

        Supports multiple time windows via comma-separated values:
        - start="2,16" end="4,18" → two windows: 2-4 AND 16-18
        - start="8"    end="20"   → single window: 8-20

        Rules per window:
        - start=0, end=0  → DISABLED (never run)
        - start=0, end=2  → midnight to 2am
        - start=22, end=4 → 10pm to 4am (wraps midnight)
        - start=X, end=X  → always active (same hour = 24h) where X != 0
        """
        try:
            start_str = str(self.account.get('start_time', '0'))
            end_str = str(self.account.get('end_time', '0'))

            # Parse comma-separated time windows
            start_parts = [s.strip() for s in start_str.split(',')]
            end_parts = [s.strip() for s in end_str.split(',')]

            # If unequal lengths, pad the shorter one with its last value
            while len(end_parts) < len(start_parts):
                end_parts.append(end_parts[-1] if end_parts else '0')
            while len(start_parts) < len(end_parts):
                start_parts.append(start_parts[-1] if start_parts else '0')

            current_hour = datetime.datetime.now().hour

            # Check each time window — if ANY matches, account is active
            all_disabled = True
            for s_str, e_str in zip(start_parts, end_parts):
                start_hour = int(s_str) if s_str.isdigit() else 0
                end_hour = int(e_str) if e_str.isdigit() else 0

                # 0,0 means this window is disabled
                if start_hour == 0 and end_hour == 0:
                    continue

                all_disabled = False

                # Same non-zero hour means always active (24h)
                if start_hour == end_hour:
                    return True

                if start_hour < end_hour:
                    # Normal range (e.g., 8-16)
                    if start_hour <= current_hour < end_hour:
                        return True
                else:
                    # Wraps midnight (e.g., 22-4)
                    if current_hour >= start_hour or current_hour < end_hour:
                        return True

            # If all windows were disabled (0,0), return False
            return not all_disabled if not all_disabled else False

        except Exception as e:
            log.warning("[%s] Time window check error: %s", self.device_serial, e)
            return True

    def _connect_device(self):
        """
        Use an already-connected device. Does NOT auto-connect.
        The user must manually connect devices first via the dashboard.
        """
        try:
            from automation.device_connection import get_connection
            self._device_conn = get_connection(self.device_serial)

            # Only use device if already connected — don't auto-connect
            if self._device_conn.status != 'connected' or not self._device_conn.device:
                log.warning("[%s] Device not connected. Connect it manually first.",
                            self.device_serial)
                return False

            self._device = self._device_conn.device
            log.info("[%s] Using existing device connection", self.device_serial)

            # Lock rotation to portrait (re-asserted before every action too —
            # see _lock_portrait; once-at-connect does NOT hold).
            self._lock_portrait()

            return True
        except Exception as e:
            log.error("[%s] Device connection error: %s", self.device_serial, e)
            return False

    def _lock_portrait(self):
        """Force + HOLD portrait. IG (reels/video/webview/camera) re-enables
        auto-rotate or forces landscape mid-session, so this is RE-ASSERTED before
        every action — locking once at connect does not hold. adb-only: u2
        freeze_rotation()/set_orientation() proved unreliable (don't stick, and
        set_orientation itself can trigger a rotation)."""
        try:
            d = self._device
            d.shell("settings put system accelerometer_rotation 0")  # kill auto-rotate
            d.shell("settings put system user_rotation 0")            # force portrait
            d.shell("wm set-user-rotation lock 0")                    # WM lock (older)
            d.shell("cmd window set-user-rotation lock 0")           # WM lock (newer)
        except Exception as e:
            log.debug("[%s] portrait re-lock failed: %s", self.device_serial, e)

    def _check_proxy_status(self):
        """
        Check if SuperProxy VPN is active on the device.
        Uses the notification bar content-desc to detect 'Proxy service is running'
        and system status icon 'VPN on.' — no need to open the app.

        Returns True if proxy appears active, False otherwise.
        """
        try:
            xml_dump = self._device.dump_hierarchy()

            # Check for VPN indicator in status bar
            vpn_active = 'VPN on' in xml_dump
            # Check for SuperProxy notification
            proxy_running = 'Proxy service is running' in xml_dump

            if vpn_active or proxy_running:
                log.info("[%s] Proxy check: OK (VPN=%s, SuperProxy=%s)",
                         self.device_serial, vpn_active, proxy_running)
                return True

            # Neither indicator found — proxy is likely down
            log.warning("[%s] Proxy check: FAILED — no VPN or SuperProxy indicators found",
                        self.device_serial)

            # Record health event for this device
            try:
                from automation.actions.helpers import get_db
                conn = get_db()
                now = datetime.datetime.now().isoformat()
                conn.execute("""
                    INSERT INTO device_proxy_history
                    (device_serial, proxy_id, proxy_host, proxy_port, action, timestamp)
                    VALUES (?, NULL, NULL, NULL, 'proxy_down_detected', ?)
                """, (self.device_serial, now))
                conn.commit()
                conn.close()
            except Exception as db_err:
                log.debug("[%s] Could not log proxy event: %s", self.device_serial, db_err)

            return False

        except Exception as e:
            log.warning("[%s] Proxy check error (allowing anyway): %s",
                        self.device_serial, e)
            # If we can't check, allow to proceed rather than blocking
            return True

    def _reconnect_surfshark(self, max_wait: int = 30) -> bool:
        """
        Reconnect Surfshark VPN on the device.
        Flow:
          1. Open Surfshark app
          2. If "VPN didn't connect" dialog → click Cancel
          3. Click the Connect button
          4. Wait for VPN to establish (check for 'VPN on' in status bar)
        Returns True if VPN reconnected, False otherwise.
        """
        SURFSHARK_PKG = 'com.surfshark.vpnclient.android'

        try:
            # Step 1: Open Surfshark
            log.info("[%s] Opening Surfshark VPN...", self.device_serial)
            self._device.app_start(SURFSHARK_PKG)
            time.sleep(3)

            # Step 2: Dismiss "VPN didn't connect" dialog if present
            xml = self._device.dump_hierarchy()
            if "VPN didn" in xml or "didn\u2019t connect" in xml or "didn't connect" in xml:
                log.info("[%s] Found 'VPN didn't connect' dialog — dismissing...", self.device_serial)
                cancel_btn = self._device(text='Cancel')
                if cancel_btn.exists(timeout=3):
                    cancel_btn.click()
                    time.sleep(2)
                else:
                    # Try X button
                    close_btn = self._device(description='Close')
                    if close_btn.exists(timeout=2):
                        close_btn.click()
                        time.sleep(2)

            # Step 3: Click Connect button
            log.info("[%s] Clicking Connect...", self.device_serial)
            connect_btn = self._device(text='Connect')
            if connect_btn.exists(timeout=5):
                connect_btn.click()
                time.sleep(2)

                # Handle Android VPN connection dialog if it appears
                ok_btn = self._device(text='OK')
                if ok_btn.exists(timeout=3):
                    ok_btn.click()
                    time.sleep(1)
            else:
                # Maybe already connected or different UI state
                log.warning("[%s] Connect button not found", self.device_serial)
                # Check if already connected
                xml = self._device.dump_hierarchy()
                if 'Connected' in xml and 'Not connected' not in xml:
                    log.info("[%s] Surfshark appears already connected", self.device_serial)
                    self._device.press('home')
                    time.sleep(1)
                    return True
                return False

            # Step 4: Wait for VPN to establish
            log.info("[%s] Waiting for VPN connection (up to %ds)...", self.device_serial, max_wait)
            for i in range(max_wait // 3):
                time.sleep(3)
                xml = self._device.dump_hierarchy()
                if 'VPN on' in xml or ('Connected' in xml and 'Not connected' not in xml):
                    log.info("[%s] Surfshark VPN connected!", self.device_serial)
                    # Go back to home screen
                    self._device.press('home')
                    time.sleep(1)
                    return True
                # Check if the error dialog appeared again
                if "VPN didn" in xml or "didn't connect" in xml:
                    log.warning("[%s] Surfshark failed to connect again", self.device_serial)
                    self._device.press('home')
                    time.sleep(1)
                    return False

            log.warning("[%s] Surfshark VPN did not connect within %ds", self.device_serial, max_wait)
            self._device.press('home')
            time.sleep(1)
            return False

        except Exception as e:
            log.error("[%s] Surfshark reconnect error: %s", self.device_serial, e)
            try:
                self._device.press('home')
            except Exception:
                pass
            return False

    def _open_instagram(self):
        """Open the correct Instagram clone for this specific account.

        Package comes from accounts.instagram_package column.
        Activity comes from account_settings.settings_json -> app_cloner field.
        Format: "com.instagram.androie/com.instagram.mainactivity.mainactivity"
        """
        try:
            from automation.instagram_actions import InstagramActions

            # Get package + activity from account table or app_cloner setting
            # Both may contain full format: "com.instagram.androif/com.instagram.mainactivity.MainActivity"
            account_package_raw = self.account.get('instagram_package', 'com.instagram.android')
            app_cloner = self.settings.get('app_cloner', '')

            # Try app_cloner first (source of truth), then instagram_package column
            raw = ''
            if app_cloner and '/' in str(app_cloner) and str(app_cloner) != 'None':
                raw = str(app_cloner)
            elif account_package_raw and '/' in str(account_package_raw):
                raw = str(account_package_raw)
            else:
                raw = str(account_package_raw) if account_package_raw else 'com.instagram.android'

            # Split into package + activity
            if '/' in raw:
                parts = raw.split('/', 1)
                package = parts[0]
                activity = parts[1] if len(parts) > 1 else None
            else:
                package = raw
                activity = None

            log.info("[%s] %s: Opening Instagram package=%s activity=%s",
                     self.device_serial, self.account.get('username', '?'),
                     package, activity or '(default)')

            # Force-kill the app first for a clean start
            # Prevents white screen bugs and stale state from previous sessions
            try:
                import subprocess
                adb_serial = self.device_serial.replace('_', ':')
                subprocess.run(
                    ['adb', '-s', adb_serial, 'shell', 'am', 'force-stop', package],
                    capture_output=True, timeout=5
                )
                time.sleep(1)
                log.debug("[%s] Force-stopped %s before launch", self.device_serial, package)
            except Exception as e:
                log.debug("[%s] Force-stop failed (non-critical): %s", self.device_serial, e)

            # Store the resolved package so action modules can use it via
            # account_info.get('package') — the DB column is 'instagram_package'
            # but all action modules look for 'package'
            self.account['package'] = package

            ig = InstagramActions(self._device, self.device_serial)
            success = ig.open_instagram(package, activity=activity)

            if success:
                log.info("[%s] Instagram opened: %s", self.device_serial, package)
            else:
                log.error("[%s] Failed to open Instagram: %s", self.device_serial, package)

            return success

        except Exception as e:
            log.error("[%s] Open Instagram error: %s", self.device_serial, e)
            return False

    def _ensure_logged_in(self):
        """
        Check if logged in, attempt login if not.

        When login check fails, updates the account's health status in DB
        and writes an account_health_events record. Accounts flagged as
        suspended/verification_required/2fa_required are skipped immediately.
        """
        try:
            from automation.instagram_actions import InstagramActions
            ig = InstagramActions(self._device, self.device_serial)
            state = ig.detect_screen_state()
            username = self.account.get('username', '?')

            if state == 'logged_in':
                log.info("[%s] Account is logged in", self.device_serial)
                # Dismiss any post-login modals
                ig.dismiss_post_login_modals(max_attempts=3)
                # A blocking modal can pop AFTER the initial detect ran on the
                # bare home feed — notably the "Choose a way to recover"
                # account-lockout modal, which overlays the logged-in UI. The
                # initial detect_screen_state saw home/profile nav and returned
                # 'logged_in' before the modal appeared. Re-detect once now so
                # we catch it and flag the account instead of marking active.
                state = ig.detect_screen_state()
                if state == 'logged_in':
                    # Ensure account status is active in DB
                    self._update_account_status('active')
                    return True
                log.warning("[%s] Post-dismiss re-detect changed state to '%s' "
                            "— routing to health flagging", self.device_serial, state)
                # fall through to STATE_TO_STATUS handling below

            # ── Map screen state → account status & health event ──
            # These states mean the account is unusable — flag and skip.
            STATE_TO_STATUS = {
                'login':                  'logged_out',
                'signup':                 'logged_out',
                'challenge':              'verification_required',
                '2fa':                    '2fa_required',
                'suspended':              'suspended',
                'verification_required':  'verification_required',
            }

            if state in STATE_TO_STATUS:
                new_status = STATE_TO_STATUS[state]
                log.warning(
                    "[%s] %s: Screen state '%s' → flagging account as '%s'",
                    self.device_serial, username, state, new_status)

                # Update account status in DB
                self._update_account_status(new_status)

                # Write health event
                self._record_health_event(
                    event_type=new_status,
                    details="Screen state detected: %s" % state,
                )

                _blog(
                    "Account flagged: %s → %s (screen: %s)" % (username, new_status, state),
                    device=self.device_serial,
                    account=username,
                    action='health_check',
                    level='WARNING',
                )

                # For login/signup we can still TRY to re-login
                if state in ('login', 'signup'):
                    return self._attempt_login()

                # For suspended, challenge, 2fa, verification — skip immediately
                return False

            # Unknown state — try to login anyway
            log.info("[%s] Not logged in (state: %s), attempting login",
                     self.device_serial, state)
            return self._attempt_login()

        except Exception as e:
            log.error("[%s] Login check error: %s", self.device_serial, e)
            return False

    def _attempt_login(self):
        """Attempt to log in with credentials. Returns True on success."""
        try:
            username = self.account.get('username', '?')
            log.info("[%s] %s: Attempting login...", self.device_serial, username)

            from automation.login import login_account
            from automation.device_connection import get_connection

            login_result = login_account(
                get_connection(self.device_serial),
                username=self.account['username'],
                password=self.account.get('password', ''),
                instagram_package=self.account.get('instagram_package', 'com.instagram.android'),
                two_fa_token=self.account.get('two_fa_token') or None,
            )

            if login_result.get('success'):
                log.info("[%s] %s: Login successful", self.device_serial, username)
                self._update_account_status('active')
                return True
            else:
                log.error("[%s] %s: Login failed: %s",
                         self.device_serial, username, login_result.get('error'))
                return False
        except Exception as e:
            log.error("[%s] Login attempt error: %s", self.device_serial, e)
            return False

    def _update_account_status(self, status):
        """Update the account's status field in the accounts table."""
        try:
            from automation.actions.helpers import get_db
            conn = get_db()
            now = datetime.datetime.now().isoformat()
            conn.execute(
                "UPDATE accounts SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, self.account_id)
            )
            conn.commit()
            conn.close()
            log.debug("[%s] Account %d status → %s",
                      self.device_serial, self.account_id, status)
        except Exception as e:
            log.error("[%s] Failed to update account status: %s",
                      self.device_serial, e)

    def _record_health_event(self, event_type, details=None):
        """
        Write a record to the account_health_events table.
        Avoids duplicate unresolved events of the same type.
        """
        try:
            from automation.actions.helpers import get_db
            conn = get_db()
            username = self.account.get('username', '?')

            # Check for existing unresolved event of same type
            existing = conn.execute(
                """SELECT id FROM account_health_events
                   WHERE account_id = ? AND event_type = ? AND resolved_at IS NULL
                   LIMIT 1""",
                (self.account_id, event_type)
            ).fetchone()

            if existing:
                log.debug("[%s] Health event '%s' already exists (unresolved) for account %d",
                          self.device_serial, event_type, self.account_id)
                conn.close()
                return

            # Truncate details to avoid bloating the DB
            if details and len(details) > 1000:
                details = details[:1000] + '...'

            conn.execute(
                """INSERT INTO account_health_events
                   (account_id, device_serial, username, event_type, details)
                   VALUES (?, ?, ?, ?, ?)""",
                (self.account_id, self.device_serial, username, event_type, details)
            )
            conn.commit()
            conn.close()
            log.info("[%s] Recorded health event: %s → %s",
                     self.device_serial, username, event_type)
        except Exception as e:
            log.error("[%s] Failed to record health event: %s",
                      self.device_serial, e)

    def _check_job_orders(self):
        """
        Check for active job order assignments for this account.
        Job orders take priority over regular settings-based actions.

        Returns list of (name, callable) tuples — one per active job.
        """
        actions = []
        try:
            from automation.actions.helpers import get_db
            conn = get_db()
            rows = conn.execute("""
                SELECT jo.*, ja.id AS assignment_id,
                       ja.completed_count AS assignment_completed,
                       ja.status AS assignment_status,
                       ja.device_serial AS assignment_device,
                       ja.username AS assignment_username
                FROM job_assignments ja
                JOIN job_orders jo ON ja.job_id = jo.id
                WHERE ja.account_id = ?
                  AND jo.status = 'active'
                  AND ja.status IN ('assigned', 'active')
                ORDER BY jo.priority DESC, jo.created_at ASC
            """, (self.account_id,)).fetchall()
            conn.close()

            if not rows:
                return actions

            for row in rows:
                job = dict(row)
                # Build separate assignment dict
                assignment = {
                    'id': job.pop('assignment_id'),
                    'completed_count': job.pop('assignment_completed'),
                    'status': job.pop('assignment_status'),
                    'device_serial': job.pop('assignment_device'),
                    'username': job.pop('assignment_username'),
                }

                job_id = job['id']
                job_type = job['job_type']
                job_name = job.get('job_name', 'unnamed')
                target = job.get('target', '?')

                # Skip if total target already reached
                if job['target_count'] and job['target_count'] > 0:
                    if job['completed_count'] >= job['target_count']:
                        log.debug("[%s] JOB #%d (%s): Target already reached, skipping",
                                  self.device_serial, job_id, job_type)
                        continue

                action_label = 'job_%d_%s' % (job_id, job_type)
                log.info("[%s] JOB #%d '%s' (%s → @%s): Queuing for execution",
                         self.device_serial, job_id, job_name, job_type, target)

                # Capture job/assignment in closure
                def make_job_action(j, a):
                    def _run():
                        return self._action_job_order(j, a)
                    return _run

                actions.append((action_label, make_job_action(job, assignment)))

        except Exception as e:
            log.error("[%s] Error checking job orders: %s", self.device_serial, e)

        return actions

    def _action_job_order(self, job, assignment):
        """Execute a single job order assignment."""
        from automation.actions.job_executor import JobExecutor
        executor = JobExecutor(
            self._device, self.device_serial,
            self.account, self.session_id,
            job, assignment
        )
        return executor.execute()

    def _check_scheduled_content(self):
        """Check if this account has content scheduled for now (or overdue)."""
        try:
            from automation.actions.helpers import get_db
            conn = get_db()
            now = datetime.datetime.now().isoformat()
            rows = conn.execute("""
                SELECT * FROM content_schedule
                WHERE username = ? AND device_serial = ?
                AND status = 'pending' AND scheduled_time <= ?
                ORDER BY scheduled_time ASC
                LIMIT 1
            """, (self.account['username'], self.device_serial, now)).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            log.error("[%s] Error checking scheduled content: %s",
                      self.device_serial, e)
            return []

    def _action_post_content(self, schedule_item):
        """
        Post scheduled content (feed post, reel, or story).

        Updates content_schedule status through the lifecycle:
        pending -> posting -> completed/failed
        Also updates content_batches counters if batch_id is present.
        """
        from automation.actions.helpers import get_db
        schedule_id = schedule_item['id']
        batch_id = schedule_item.get('batch_id')

        # Mark as 'posting'
        try:
            conn = get_db()
            conn.execute("""
                UPDATE content_schedule
                SET status = 'posting', updated_at = ?
                WHERE id = ?
            """, (datetime.datetime.now().isoformat(), schedule_id))
            conn.commit()
            conn.close()
        except Exception as e:
            log.warning("[%s] Failed to set posting status: %s",
                        self.device_serial, e)

        # Execute the posting action
        from automation.actions.post_content import PostContentAction
        action = PostContentAction(
            self._device, self.device_serial,
            self.account, self.session_id,
            schedule_item)
        result = action.execute()

        # Update status based on result
        now = datetime.datetime.now().isoformat()
        try:
            conn = get_db()
            if result.get('success'):
                conn.execute("""
                    UPDATE content_schedule
                    SET status = 'completed', posted_at = ?, updated_at = ?
                    WHERE id = ?
                """, (now, now, schedule_id))
                # Update batch counters
                if batch_id:
                    conn.execute("""
                        UPDATE content_batches
                        SET completed_items = completed_items + 1
                        WHERE batch_id = ?
                    """, (batch_id,))
            else:
                error_msg = result.get('error_message', 'Unknown error')
                conn.execute("""
                    UPDATE content_schedule
                    SET status = 'failed', error_message = ?, updated_at = ?
                    WHERE id = ?
                """, (error_msg, now, schedule_id))
                # Update batch counters
                if batch_id:
                    conn.execute("""
                        UPDATE content_batches
                        SET failed_items = failed_items + 1
                        WHERE batch_id = ?
                    """, (batch_id,))

            # Check if batch is complete
            if batch_id:
                batch = conn.execute("""
                    SELECT total_items, completed_items, failed_items
                    FROM content_batches WHERE batch_id = ?
                """, (batch_id,)).fetchone()
                if batch:
                    total = batch['total_items']
                    done = batch['completed_items'] + batch['failed_items']
                    if done >= total:
                        conn.execute("""
                            UPDATE content_batches SET status = 'completed'
                            WHERE batch_id = ?
                        """, (batch_id,))

            conn.commit()
            conn.close()
        except Exception as e:
            log.error("[%s] Failed to update schedule status: %s",
                      self.device_serial, e)

        return result

    def _is_warmup_mode(self):
        """
        Check if this account is in warmup mode.
        Also auto-expires warmup if the warmup_until date has passed.
        Returns True if currently warming up.
        """
        warmup = self.account.get('warmup', 0)
        warmup_until = self.account.get('warmup_until')

        if not warmup:
            return False

        # Check if warmup period has expired
        if warmup_until:
            try:
                expiry = datetime.datetime.strptime(warmup_until, '%Y-%m-%d').date()
                if datetime.datetime.now().date() >= expiry:
                    log.info("[%s] %s: Warmup period expired (%s), switching to normal mode",
                             self.device_serial, self.account.get('username', '?'), warmup_until)
                    # Auto-clear warmup in DB
                    try:
                        from automation.actions.helpers import get_db
                        conn = get_db()
                        now = datetime.datetime.now().isoformat()
                        conn.execute(
                            "UPDATE accounts SET warmup = 0, warmup_until = NULL, updated_at = ? WHERE id = ?",
                            (now, self.account_id))
                        conn.commit()
                        conn.close()
                    except Exception as e:
                        log.warning("[%s] Failed to auto-clear warmup: %s", self.device_serial, e)
                    return False
            except (ValueError, TypeError):
                pass

        log.info("[%s] %s: Account is in WARMUP mode (until %s)",
                 self.device_serial, self.account.get('username', '?'),
                 warmup_until or 'indefinite')
        return True

    def _warmup_actions(self):
        """
        Return the limited action set for warmup mode.
        Warmup does: watch reels + light scroll/view + browse profiles.
        NO follows, DMs, comments, story shares.

        Browse profiles is critical for niche signalling — when warmup
        accounts visit OF creator profiles, IG learns their content
        preference. Without this, the bot just consumes feed content
        without ever signalling intent to IG's algorithm.
        """
        actions = []

        # Reels watching (primary warmup activity)
        actions.append(('warmup_reels', self._action_reels))

        # Light engagement (scroll explore, view home feed) — gated by
        # individual enable_* toggles inside the action itself.
        actions.append(('warmup_engage', self._action_engage))

        # Browse profiles — visits source usernames, gives IG a niche signal.
        # Only adds the action if browse_profiles is enabled AND the account
        # has at least one browse_profiles_sources row (otherwise the action
        # would just exit immediately).
        if self.settings.get('enable_browse_profiles', False):
            actions.append(('warmup_browse_profiles', self._action_browse_profiles))

        return actions

    def _determine_actions(self):
        """
        Determine which actions to run based on account settings.
        Returns list of (name, callable) tuples.
        """
        # ── WARMUP MODE: restricted action set ──
        if self._is_warmup_mode():
            _blog(
                "Warmup mode active for %s — reels + explore only" % self.account.get('username', '?'),
                device=self.device_serial,
                account=self.account.get('username', '?'),
                action='warmup',
                level='INFO',
            )
            return self._warmup_actions()

        actions = []

        # Always check profile first for follower tracking
        actions.append(('check_profile', self._action_check_profile))

        # Scrape Account Status once per day (Settings → Account Status)
        # — cheap navigation, good early-warning signal for IG restrictions
        try:
            last = self.account.get('account_status_checked_at')
            stale = True
            if last:
                last_dt = datetime.datetime.strptime(last[:19], '%Y-%m-%d %H:%M:%S')
                stale = (datetime.datetime.now() - last_dt).total_seconds() > 86400  # >24h
            if stale:
                actions.append(('account_status', self._action_scrape_account_status))
        except Exception:
            pass

        # Switch to Business Profile (one-time action, if enabled)
        if (self.settings.get('auto_switch_business', False)
                and not self.account.get('is_business_profile')):
            actions.append(('switch_to_business', self._action_switch_to_business))

        # Switch to Private Profile (one-time action, if enabled)
        if (self.settings.get('auto_switch_private', False)
                and not self.account.get('is_private')):
            actions.append(('switch_to_private', self._action_switch_to_private))

        # Check scheduled content FIRST (time-sensitive, highest priority)
        scheduled = self._check_scheduled_content()
        if scheduled:
            item = scheduled[0]
            sched_time = item.get('scheduled_time', '?')
            caption_preview = (item.get('caption', '') or '')[:40]
            log.info("[%s] CONTENT: Found scheduled %s for @%s "
                     "(scheduled %s, caption: \"%s...\")",
                     self.device_serial, item.get('content_type', '?'),
                     self.account.get('username', '?'),
                     sched_time, caption_preview)
            # Use default-arg capture to bind 'item' in the lambda
            actions.append(('post_content',
                            lambda _item=item: self._action_post_content(_item)))

        # Check job orders (they take priority over regular actions)
        job_actions = self._check_job_orders()
        if job_actions:
            actions.extend(job_actions)

        # Engagement/warmup first (more natural behavior)
        if (self.settings.get('enable_human_behaviour_emulation', False) or
                self.settings.get('enable_viewhomefeedstory', False) or
                self.settings.get('enable_scrollhomefeed', False)):
            actions.append(('engage', self._action_engage))

        # Follow (from source accounts)
        if self.account.get('follow_enabled') == 'True':
            actions.append(('follow', self._action_follow))

        # Follow from list (if setting enabled or list assigned)
        if (self.settings.get('enable_follow_from_list', False) or
                self.settings.get('follow_list_id')):
            actions.append(('follow_from_list', self._action_follow_from_list))

        # Unfollow
        if self.account.get('unfollow_enabled') == 'True':
            actions.append(('unfollow', self._action_unfollow))

        # Like
        if self.settings.get('enable_likepost', False):
            actions.append(('like', self._action_like))

        # Comment
        if (self.account.get('comment_enabled') == 'True' or
                self.settings.get('enable_comment', False)):
            actions.append(('comment', self._action_comment))

        # DM
        if self.settings.get('enable_directmessage', False):
            actions.append(('dm', self._action_dm))

        # Story viewing (dedicated, not just warmup)
        if (self.account.get('story_enabled') == 'True' or
                self.settings.get('enable_story_viewer', False)):
            actions.append(('story_view', self._action_story_view))

        # Reels watching
        if self.settings.get('enable_watch_reels', False):
            actions.append(('reels', self._action_reels))

        # Share to story.
        #
        # SINGLE source of truth: the master "Share Post to Story" toggle
        # (key: enable_share_post_to_story). The legacy duplicate key
        # `enable_shared_post` — hidden inside the "Advanced Settings"
        # collapsible in the account-detail UI — is IGNORED. That removes
        # the dual-source-of-truth bug from incident 2026-06-01 where the
        # operator disabled the visible master toggle on @real_emiliorey
        # but the bot kept self-sharing because the legacy key was still
        # silently True under Advanced.
        #
        # Pre-deployment audit (2026-06-01): 0 accounts had ONLY the legacy
        # toggle on (i.e. nobody silently stops doing this action after the
        # change — every account that was sharing has the master ON too).
        if self.settings.get('enable_share_post_to_story', False):
            actions.append(('share_to_story', self._action_share_to_story))

        # Save post (bookmark)
        if self.settings.get('enable_save_post', False):
            actions.append(('save_post', self._action_save_post))

        # Browse profiles (organic profile visiting)
        if self.settings.get('enable_browse_profiles', False):
            actions.append(('browse_profiles', self._action_browse_profiles))

        # If no specific actions enabled, at least do engagement as fallback
        real_actions = [a for a in actions if a[0] not in ('check_profile',)]
        if not real_actions:
            actions.append(('engage', self._action_engage))

        # Order: check_profile -> job orders (by priority) -> regular actions (shuffled) -> engage/HBE last
        if len(actions) > 1:
            profile_actions = [a for a in actions if a[0] == 'check_profile']
            job_actions_list = [a for a in actions if a[0].startswith('job_')]
            engage_actions = [a for a in actions if a[0] in ('engage', 'browse_profiles')]
            other_actions = [a for a in actions if a[0] not in
                            ('check_profile', 'engage', 'browse_profiles')
                            and not a[0].startswith('job_')]
            random.shuffle(other_actions)
            random.shuffle(engage_actions)
            # job_actions_list already sorted by priority from _check_job_orders
            actions = profile_actions + job_actions_list + other_actions + engage_actions

        return actions

    def _action_check_profile(self):
        """Run profile check for follower tracking."""
        from automation.actions.check_profile import CheckProfileAction
        action = CheckProfileAction(
            self._device, self.device_serial,
            self.account, self.session_id,
            pkg=self.account.get('package', 'com.instagram.android'),
        )
        return action.execute()

    def _action_scrape_account_status(self):
        """Capture IG Account Status (Settings → Account Status). Cheap, useful health signal."""
        from automation.actions.scrape_account_status import ScrapeAccountStatusAction
        action = ScrapeAccountStatusAction(
            self._device, self.device_serial,
            self.account, self.session_id,
            pkg=self.account.get('package', 'com.instagram.android'),
        )
        return action.execute()

    def _action_switch_to_business(self):
        """Switch account to Business profile (one-time action)."""
        from automation.actions.switch_to_business import SwitchToBusinessAction
        category = self.settings.get('business_category', 'Digital creator')
        action = SwitchToBusinessAction(
            self._device, self.device_serial,
            self.account, self.session_id,
            pkg=self.account.get('package', 'com.instagram.android'),
            category=category,
        )
        result = action.execute()
        if result.get('success'):
            # Disable auto_switch so it doesn't run again
            self.settings['auto_switch_business'] = False
            # Reload account data to pick up is_business_profile=1
            self._load_account()
        else:
            # Mark attempted so we don't retry every session
            # (set a flag in settings_json)
            self.settings['auto_switch_business'] = False
            try:
                from automation.actions.helpers import get_db
                import json as _json
                conn = get_db()
                row = conn.execute(
                    "SELECT settings_json FROM account_settings WHERE account_id=?",
                    (self.account_id,)).fetchone()
                if row:
                    sj = _json.loads(row['settings_json'] or '{}')
                    sj['auto_switch_business'] = False
                    sj['switch_business_failed_at'] = datetime.datetime.now().isoformat()
                    conn.execute(
                        "UPDATE account_settings SET settings_json=? WHERE account_id=?",
                        (_json.dumps(sj), self.account_id))
                    conn.commit()
                conn.close()
            except Exception:
                pass
        return result

    def _action_switch_to_private(self):
        """Switch account to Private profile (one-time action)."""
        from automation.actions.switch_to_private import SwitchToPrivateAction
        action = SwitchToPrivateAction(
            self._device, self.device_serial,
            self.account, self.session_id,
            pkg=self.account.get('package', 'com.instagram.android'),
        )
        result = action.execute()
        if result.get('success'):
            self.settings['auto_switch_private'] = False
            self._load_account()
        else:
            self.settings['auto_switch_private'] = False
            try:
                from automation.actions.helpers import get_db
                import json as _json
                conn = get_db()
                row = conn.execute(
                    "SELECT settings_json FROM account_settings WHERE account_id=?",
                    (self.account_id,)).fetchone()
                if row:
                    sj = _json.loads(row['settings_json'] or '{}')
                    sj['auto_switch_private'] = False
                    sj['switch_private_failed_at'] = datetime.datetime.now().isoformat()
                    conn.execute(
                        "UPDATE account_settings SET settings_json=? WHERE account_id=?",
                        (_json.dumps(sj), self.account_id))
                    conn.commit()
                conn.close()
            except Exception:
                pass
        return result

    def _action_follow(self):
        """Run follow action."""
        from automation.actions.follow import FollowAction
        action = FollowAction(self._device, self.device_serial,
                             self.account, self.session_id)
        return action.execute()

    def _action_follow_from_list(self):
        """Run follow-from-list action."""
        from automation.actions.follow_from_list import FollowFromListAction

        # Get active follow list for this account
        list_id = self._get_active_follow_list()
        if not list_id:
            log.info("[%s] No active follow list for account %d",
                     self.device_serial, self.account_id)
            return {'success': True, 'follows_done': 0, 'skipped': 0, 'errors': 0,
                    'message': 'no_active_list'}

        action = FollowFromListAction(self._device, self.device_serial,
                                       self.account, self.session_id, list_id)
        return action.execute()

    def _get_active_follow_list(self):
        """
        Get the active follow list ID for this account.
        Checks account settings for 'follow_list_id', then falls back to
        finding any list with pending items.
        Returns list_id or None.
        """
        try:
            # Check settings first
            list_id = self.settings.get('follow_list_id')
            if list_id:
                return int(list_id)

            # Fallback: find any list that has pending items
            from automation.actions.helpers import get_db
            conn = get_db()
            row = conn.execute("""
                SELECT fl.id FROM follow_lists fl
                JOIN follow_list_items fli ON fli.list_id = fl.id
                WHERE fli.status = 'pending'
                GROUP BY fl.id
                ORDER BY fl.id ASC
                LIMIT 1
            """).fetchone()
            conn.close()
            return row['id'] if row else None
        except Exception as e:
            log.error("[%s] Error getting active follow list: %s",
                      self.device_serial, e)
            return None

    def _action_unfollow(self):
        """Run unfollow action."""
        from automation.actions.unfollow import UnfollowAction
        action = UnfollowAction(self._device, self.device_serial,
                               self.account, self.session_id)
        return action.execute()

    def _action_like(self):
        """Run like action."""
        from automation.actions.like import LikeAction
        action = LikeAction(self._device, self.device_serial,
                           self.account, self.session_id)
        return action.execute()

    def _action_engage(self):
        """Run engagement action."""
        from automation.actions.engage import EngageAction
        action = EngageAction(self._device, self.device_serial,
                             self.account, self.session_id)
        return action.execute()

    def _action_comment(self):
        """Run comment action."""
        from automation.actions.comment import CommentAction
        action = CommentAction(self._device, self.device_serial,
                              self.account, self.session_id)
        return action.execute()

    def _action_dm(self):
        """Run DM action."""
        from automation.actions.dm import DMAction
        action = DMAction(self._device, self.device_serial,
                         self.account, self.session_id)
        return action.execute()

    def _action_reels(self):
        """Run reels watching action."""
        from automation.actions.reels import ReelsAction
        action = ReelsAction(self._device, self.device_serial,
                            self.account, self.session_id)
        return action.execute()

    def _action_story_view(self):
        """Run dedicated story viewing action."""
        from automation.actions.engage import EngageAction
        action = EngageAction(self._device, self.device_serial,
                             self.account, self.session_id)
        # Force story viewing only
        return action._do_story_viewing()

    def _action_save_post(self):
        """Run save/bookmark post action."""
        from automation.actions.save_post import SavePostAction
        action = SavePostAction(self._device, self.device_serial,
                                self.account, self.session_id)
        return action.execute()

    def _action_browse_profiles(self):
        """Run browse profiles action (organic profile visiting)."""
        from automation.actions.browse_profiles import BrowseProfilesAction
        action = BrowseProfilesAction(
            self._device, self.device_serial,
            self.account, self.session_id,
            package=self.account.get('package', 'com.instagram.android'),
        )
        return action.execute()

    def _action_share_to_story(self):
        """Run share-to-story action."""
        from automation.actions.share_to_story import ShareToStoryAction
        action = ShareToStoryAction(self._device, self.device_serial,
                                    self.account, self.session_id)
        return action.execute()

    def _recover(self):
        """Try to recover from an error state."""
        try:
            log.info("[%s] Attempting recovery...", self.device_serial)

            # Check device connection
            if self._device_conn:
                self._device = self._device_conn.ensure_connected()
                if not self._device:
                    log.error("[%s] Could not reconnect device", self.device_serial)
                    return False

            # Dismiss known modals (e.g., "Discard story?", permission dialogs)
            try:
                for dismiss_text in ["While using the app", "WHILE USING THE APP",
                                     "Allow", "ALLOW",
                                     "Discard", "Not now", "Not Now", "Cancel",
                                     "OK", "Dismiss", "Close"]:
                    btn = self._device(text=dismiss_text)
                    if btn.exists(timeout=1):
                        btn.click()
                        time.sleep(1)
                        log.info("[%s] Recovery: dismissed modal via '%s'",
                                 self.device_serial, dismiss_text)
                        break
            except Exception:
                pass

            # Press back a few times
            for _ in range(3):
                try:
                    self._device.press("back")
                    time.sleep(1)
                    # Check for discard modal after each back
                    discard = self._device(text="Discard")
                    if discard.exists(timeout=0.5):
                        discard.click()
                        time.sleep(1)
                        log.info("[%s] Recovery: dismissed discard modal",
                                 self.device_serial)
                except Exception:
                    pass

            # Try to dismiss popups
            from automation.actions.helpers import IGNavigator
            nav = IGNavigator(self._device, self.device_serial)
            nav.dismiss_any_popup()

            # Verify Instagram is still open
            if not nav.is_on_instagram():
                self._open_instagram()
                time.sleep(5)

            log.info("[%s] Recovery successful", self.device_serial)
            return True

        except Exception as e:
            log.error("[%s] Recovery failed: %s", self.device_serial, e)
            return False

    def _update_bot_status(self, status):
        """Update bot_status table and broadcast via WebSocket."""
        try:
            from automation.actions.helpers import get_db
            conn = get_db()
            now = datetime.datetime.now().isoformat()

            conn.execute("""
                INSERT INTO bot_status (device_serial, status, started_at, last_check_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(device_serial) DO UPDATE SET
                    status=excluded.status,
                    last_check_at=excluded.last_check_at
            """, (self.device_serial, status, now, now))
            conn.commit()
            conn.close()
        except Exception as e:
            log.debug("[%s] bot_status update error: %s", self.device_serial, e)

        # Broadcast via WebSocket
        try:
            from automation.ws_server import broadcast_event
            broadcast_event('bot_status', {
                'device_serial': self.device_serial,
                'account_id': self.account_id,
                'username': self.account.get('username', '') if self.account else '',
                'status': status,
            })
        except Exception:
            pass

    def _broadcast_action(self, action_name, action_result):
        """Broadcast action completion via WebSocket."""
        try:
            from automation.ws_server import broadcast_event
            broadcast_event('action_event', {
                'device_serial': self.device_serial,
                'username': self.account.get('username', '') if self.account else '',
                'action': action_name,
                'result': action_result,
            })
        except Exception:
            pass


def run_bot(device_serial, account_id):
    """Convenience function to run the bot engine."""
    engine = BotEngine(device_serial, account_id)
    return engine.run()
