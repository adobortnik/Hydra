"""
Login Automation Module
========================
Complete Instagram login flow with 2FA support.

Adapted from the original login_automation.py, now using:
    - DeviceConnection manager for connections
    - InstagramActions for UI interactions
    - phone_farm.db for account data
"""

import time
import logging
import os
import sys

log = logging.getLogger(__name__)

# Add path for TwoFALiveClient
_DASHBOARD_UIAUTOMATOR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "dashboard", "uiAutomator"
)
if _DASHBOARD_UIAUTOMATOR not in sys.path:
    sys.path.insert(0, _DASHBOARD_UIAUTOMATOR)


def get_2fa_code(two_fa_token, max_retries=20, retry_interval=3, timeout=60):
    """
    Fetch a 2FA code from 2fa.live.

    Args:
        two_fa_token: The TOTP secret key
        max_retries: Maximum fetch attempts
        retry_interval: Seconds between retries
        timeout: Total timeout in seconds

    Returns:
        str: 6-digit code, or None on failure
    """
    try:
        from two_fa_live_client import TwoFALiveClient
        client = TwoFALiveClient(two_fa_token, timeout=timeout)
        code = client.get_code(max_retries=max_retries, retry_interval=retry_interval)
        return code
    except ImportError:
        log.error("two_fa_live_client not available - trying pyotp")
        try:
            import pyotp
            totp = pyotp.TOTP(two_fa_token)
            return totp.now()
        except ImportError:
            log.error("Neither two_fa_live_client nor pyotp available for 2FA")
            return None
    except Exception as e:
        log.error("2FA code retrieval failed: %s", e)
        return None


def login_account(device_connection, username, password, instagram_package,
                  two_fa_token=None):
    """
    Complete login flow for an Instagram account.

    Args:
        device_connection: DeviceConnection instance (already connected)
        username: Instagram username
        password: Instagram password
        instagram_package: Package name (e.g. "com.instagram.androim")
        two_fa_token: Optional TOTP secret for 2FA

    Returns:
        dict with keys:
            success (bool)
            login_type (str): 'already_logged_in', 'normal', '2fa', 'challenge', 'unknown'
            error (str or None)
            two_fa_used (bool)
            challenge_encountered (bool)
    """
    from automation.instagram_actions import InstagramActions

    result = {
        'success': False,
        'login_type': 'unknown',
        'error': None,
        'two_fa_used': False,
        'challenge_encountered': False,
    }

    device = device_connection.ensure_connected()
    if not device:
        result['error'] = "Device not connected"
        return result

    ig = InstagramActions(device, device_connection.device_serial)

    log.info("[%s] Starting login for %s on %s",
             device_connection.device_serial, username, instagram_package)

    try:
        # Step 1: Open Instagram
        if not ig.open_instagram(instagram_package):
            result['error'] = "Failed to open Instagram"
            return result

        # Step 2: Detect screen state
        screen = ig.detect_screen_state()
        log.info("[%s] Screen state: %s", device_connection.device_serial, screen)

        if screen == 'logged_in':
            result['success'] = True
            result['login_type'] = 'already_logged_in'
            return result

        if screen == 'challenge':
            result['error'] = "Challenge screen - manual intervention required"
            result['challenge_encountered'] = True
            result['login_type'] = 'challenge'
            return result

        if screen == 'signup':
            if not ig.handle_signup_screen():
                result['error'] = "Failed to navigate from signup to login"
                return result
            time.sleep(2)

        # Step 3: Enter credentials
        if not ig.enter_credentials(username, password):
            result['error'] = "Failed to enter credentials"
            return result

        # Step 4: Check for 2FA
        time.sleep(6)
        two_fa_detected = ig.detect_two_factor_screen()

        if two_fa_detected:
            log.info("[%s] 2FA screen detected", device_connection.device_serial)
            result['two_fa_used'] = True

            if not two_fa_token:
                result['error'] = "2FA required but no token provided"
                return result

            code = get_2fa_code(two_fa_token)
            if not code:
                result['error'] = "Could not retrieve 2FA code"
                return result

            log.info("[%s] Got 2FA code: %s", device_connection.device_serial, code)

            if not ig.enter_2fa_code(code):
                result['error'] = "Failed to enter 2FA code"
                return result

            result['login_type'] = '2fa'
            time.sleep(6)
        else:
            result['login_type'] = 'normal'
            time.sleep(3)

        # Step 5: Double-check for 2FA (sometimes detection misses)
        if ig.detect_two_factor_screen():
            if two_fa_token and not two_fa_detected:
                log.info("[%s] 2FA detected on second check", device_connection.device_serial)
                result['two_fa_used'] = True
                code = get_2fa_code(two_fa_token)
                if code and ig.enter_2fa_code(code):
                    result['login_type'] = '2fa'
                    time.sleep(6)
                else:
                    result['error'] = "Failed 2FA on second attempt"
                    return result
            else:
                result['error'] = "Stuck on 2FA screen"
                return result

        # Step 6: Handle post-login prompts
        ig.handle_save_login_info()
        time.sleep(2)
        ig.dismiss_notification_prompt()
        time.sleep(2)

        # Step 7: Verify login
        if ig.verify_logged_in():
            ig.dismiss_post_login_modals()
            result['success'] = True
            log.info("[%s] Login successful for %s", device_connection.device_serial, username)
        else:
            ig.dismiss_post_login_modals()
            # Still mark success if no errors occurred
            result['success'] = True
            log.info("[%s] Login verification inconclusive for %s",
                     device_connection.device_serial, username)

        return result

    except Exception as e:
        log.error("[%s] Login exception: %s", device_connection.device_serial, e)
        result['error'] = str(e)
        return result


def login_from_db(device_serial, account_id):
    """
    Login an account using data from phone_farm.db.

    Args:
        device_serial: Device serial from DB
        account_id: accounts.id from DB

    Returns:
        dict with login result
    """
    from automation.device_connection import get_connection
    from db.models import get_connection as db_conn, row_to_dict

    # Fetch account from DB
    conn = db_conn()
    row = conn.execute(
        "SELECT * FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    conn.close()

    if not row:
        return {'success': False, 'error': 'Account not found in DB'}

    acct = row_to_dict(row)

    username = acct['username']
    password = acct.get('password', '')
    package = acct.get('instagram_package', 'com.instagram.android')
    two_fa = acct.get('two_fa_token', '')

    if not password:
        return {'success': False, 'error': 'No password stored for account'}

    # Get device connection
    dev_conn = get_connection(device_serial)

    return login_account(
        dev_conn,
        username=username,
        password=password,
        instagram_package=package,
        two_fa_token=two_fa if two_fa else None,
    )
