"""
Reliable Text Input Module
============================
Provides a fallback chain for typing text into Android fields via uiautomator2/ADB.

Strategy (matches dashboard login_automation.py v1 approach):
    1. Click field, clear thoroughly (select-all + delete via ADB)
    2. Type via adb shell input text (most reliable on our devices)
    3. Trust it worked — Instagram EditText fields return hint text from .info['text'],
       NOT the actual typed content, so strict verification is unreliable.
    4. Fallback to u2 set_text, send_keys, base64 broadcast only if adb input fails.
"""

import base64
import logging
import subprocess
import time

log = logging.getLogger(__name__)

# Characters that need escaping for `adb shell input text`
_SHELL_SPECIAL = set('()&;<>|$`\\!"\'{}[]~*?# ')

# Common hint/placeholder texts that Instagram fields return from .info['text']
# even when actual text has been typed — do NOT treat these as "no text entered"
_KNOWN_HINTS = {
    'username', 'username, email or mobile number', 'phone number, username, or email',
    'phone number, username or email', 'password', 'email', 'phone',
    'email or phone number', 'search', 'write a message...',
    'add a comment...', 'add a caption...', 'name', 'bio', 'website',
}


def _escape_for_adb(text: str) -> str:
    """Escape text for adb shell input text command."""
    out = []
    for ch in text:
        if ch == ' ':
            out.append('%s')
        elif ch in _SHELL_SPECIAL:
            out.append(f'\\{ch}')
        else:
            out.append(ch)
    return ''.join(out)


def _read_field_text(field) -> str:
    """Read current text from a u2 field selector, return '' on failure."""
    try:
        info = field.info
        txt = info.get('text', '') or ''
        return txt
    except Exception:
        return ''


def _is_hint_text(text: str) -> bool:
    """Check if the read-back text is a known Instagram hint/placeholder."""
    return text.lower().strip() in _KNOWN_HINTS


def _clear_field_thorough(field, adb_serial: str):
    """
    Thoroughly clear an EditText field using multiple methods.
    Matches the approach from dashboard login_automation.py.
    """
    # Method 1: u2 clear_text
    try:
        field.clear_text()
        time.sleep(0.3)
    except Exception:
        pass

    # Method 2: ADB select-all + delete (handles Instagram's stubborn fields)
    try:
        subprocess.run(
            ['adb', '-s', adb_serial, 'shell', 'input', 'keyevent', 'KEYCODE_MOVE_END'],
            capture_output=True, timeout=5
        )
        # Rapid delete keys to clear any remaining text
        del_keys = ['KEYCODE_DEL'] * 30
        subprocess.run(
            ['adb', '-s', adb_serial, 'shell', 'input', 'keyevent', '--longpress'] + del_keys,
            capture_output=True, timeout=10
        )
        time.sleep(0.3)
    except Exception:
        pass


def reliable_type_text(device, adb_serial: str, field, text: str,
                       device_serial: str = '') -> bool:
    """
    Type *text* into *field* using a multi-method fallback chain.

    Primary method is adb shell input text (most reliable on our devices).
    Verification is relaxed for Instagram fields which return hint text
    from .info['text'] instead of actual typed content.

    Args:
        device:        uiautomator2 device object
        adb_serial:    ADB serial  e.g. '10.1.10.183:5555'
        field:         u2 selector for the target EditText (already located)
        text:          The text to type
        device_serial: Human-readable serial for logging (optional)

    Returns True if the text was successfully entered (or trusted).
    """
    tag = device_serial or adb_serial

    # ── Method 1: adb shell input text (primary — most reliable) ──
    try:
        field.click()
        time.sleep(0.5)
    except Exception:
        pass
    _clear_field_thorough(field, adb_serial)

    try:
        escaped = _escape_for_adb(text)
        result = subprocess.run(
            ['adb', '-s', adb_serial, 'shell', 'input', 'text', escaped],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0:
            time.sleep(0.5)
            actual = _read_field_text(field)
            # Strict match
            if actual == text:
                log.info("[%s] Text entered OK via adb_input_text", tag)
                return True
            # Length match (masked password)
            if len(actual) == len(text) and actual != '':
                log.info("[%s] Text length matches (%d) via adb_input_text (possibly masked)", tag, len(text))
                return True
            # Bullet chars (password masking)
            if actual and all(c in ('•', '●', '*', '⬤', '\u2022', '\u25CF') for c in actual) and len(actual) == len(text):
                log.info("[%s] Text masked (%d chars) via adb_input_text", tag, len(text))
                return True
            # Instagram hint text — field still shows placeholder, but text was likely entered
            if _is_hint_text(actual) or actual == '':
                log.info("[%s] adb_input_text completed (field shows hint/empty — trusting input for IG field)", tag)
                return True
            # If read-back is different but not a hint, it might be concatenated junk — log but trust
            log.info("[%s] adb_input_text completed, readback=%r (trusting)", tag, actual[:50])
            return True
    except Exception as exc:
        log.warning("[%s] adb_input_text raised: %s", tag, exc)

    # ── Fallback methods (only if adb input text failed outright) ──
    fallbacks = [
        ('u2_set_text',   _try_set_text),
        ('u2_send_keys',  _try_send_keys),
        ('adb_base64',    _try_adb_base64),
    ]

    for method_name, method_fn in fallbacks:
        try:
            field.click()
            time.sleep(0.3)
        except Exception:
            pass
        _clear_field_thorough(field, adb_serial)

        try:
            method_fn(device, adb_serial, field, text)
        except Exception as exc:
            log.warning("[%s] %s raised: %s", tag, method_name, exc)
            continue

        time.sleep(0.5)

        # Relaxed verification
        actual = _read_field_text(field)
        if actual == text:
            log.info("[%s] Text entered OK via %s", tag, method_name)
            return True
        if len(actual) == len(text) and actual != '':
            log.info("[%s] Text length matches (%d) via %s (possibly masked)", tag, len(text), method_name)
            return True
        if actual and all(c in ('•', '●', '*', '⬤', '\u2022', '\u25CF') for c in actual) and len(actual) == len(text):
            log.info("[%s] Text masked (%d chars) via %s", tag, len(text), method_name)
            return True
        # For IG hint fields — trust the input
        if _is_hint_text(actual) or actual == '':
            log.info("[%s] %s completed (field shows hint/empty — trusting input)", tag, method_name)
            return True

        log.warning("[%s] %s verification failed: expected %r (len=%d), got %r (len=%d)",
                    tag, method_name, text, len(text), actual, len(actual))

    log.error("[%s] ALL text input methods failed for text of length %d", tag, len(text))
    return False


# ---------------------------------------------------------------------------
#  Individual methods
# ---------------------------------------------------------------------------

def _try_set_text(device, adb_serial, field, text):
    """Method 1: u2 set_text()."""
    field.set_text(text)


def _try_send_keys(device, adb_serial, field, text):
    """Method 2: u2 send_keys() — character by character."""
    # send_keys types into currently focused element
    device.send_keys(text, clear=True)


def _try_adb_input(device, adb_serial, field, text):
    """Method 3: adb shell input text with proper escaping."""
    escaped = _escape_for_adb(text)
    result = subprocess.run(
        ['adb', '-s', adb_serial, 'shell', 'input', 'text', escaped],
        capture_output=True, timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"adb input text returned {result.returncode}: {result.stderr.decode(errors='replace')}")


def _try_adb_base64(device, adb_serial, field, text):
    """Method 4: ADB broadcast with base64 encoding as last resort."""
    encoded = base64.b64encode(text.encode('utf-8')).decode('ascii')
    # Use shell pipeline: decode base64, then pass to input text
    cmd = f'echo {encoded} | base64 -d | xargs -0 input text'
    result = subprocess.run(
        ['adb', '-s', adb_serial, 'shell', cmd],
        capture_output=True, timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"adb base64 method returned {result.returncode}: {result.stderr.decode(errors='replace')}")
