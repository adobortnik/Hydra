"""
Login Automation Module
========================
Complete Instagram login flow with 2FA support.

Delegates to the single LoginAutomation class from
dashboard/uiAutomator/login_automation.py — ONE codebase for login,
used by both the dashboard UI and the bot engine.
"""

import logging
import os
import sys

log = logging.getLogger(__name__)

# Ensure dashboard/uiAutomator is importable (for LoginAutomation + TwoFALiveClient)
_DASHBOARD_UIAUTOMATOR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "dashboard", "uiAutomator"
)
if _DASHBOARD_UIAUTOMATOR not in sys.path:
    sys.path.insert(0, _DASHBOARD_UIAUTOMATOR)


def login_account(device_connection, username, password, instagram_package,
                  two_fa_token=None):
    """
    Complete login flow for an Instagram account.

    Uses LoginAutomation from dashboard/uiAutomator/login_automation.py
    with the already-connected device from DeviceConnection.

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
    from login_automation import LoginAutomation

    result = {
        'success': False,
        'login_type': 'unknown',
        'error': None,
        'two_fa_used': False,
        'challenge_encountered': False,
    }

    # Get the u2 device from our DeviceConnection
    device = device_connection.ensure_connected()
    if not device:
        result['error'] = "Device not connected"
        return result

    serial = device_connection.device_serial

    log.info("[%s] Starting login for %s on %s", serial, username, instagram_package)

    try:
        # Create LoginAutomation and inject the already-connected device
        # (skip connect_device() — bot engine already has a live connection)
        la = LoginAutomation(device_serial=serial)
        la.device = device

        # Enable AdbKeyboard IME (LoginAutomation.connect_device does this,
        # but we skipped it since device is already connected)
        try:
            device.set_input_ime(True)
            log.info("[%s] AdbKeyboard IME enabled", serial)
        except Exception as ime_err:
            log.warning("[%s] Failed to enable AdbKeyboard IME: %s", serial, ime_err)

        # Delegate to the full login flow — same code the dashboard v2 uses
        result = la.login_account(
            username=username,
            password=password,
            instagram_package=instagram_package,
            two_fa_token=two_fa_token,
        )

        if result.get('success'):
            log.info("[%s] Login successful for %s (type: %s)",
                     serial, username, result.get('login_type'))
        else:
            log.error("[%s] Login failed for %s: %s",
                      serial, username, result.get('error'))

        return result

    except Exception as e:
        log.error("[%s] Login exception: %s", serial, e)
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
