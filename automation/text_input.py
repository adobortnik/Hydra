"""
Reliable Text Input Module
============================
Provides a fallback chain for typing text into Android fields via uiautomator2/ADB.

Fallback order:
    1. u2 set_text()   — fastest, works for simple text
    2. u2 send_keys()  — character by character
    3. adb shell input text  — with proper shell escaping
    4. ADB broadcast base64  — base64-encoded text as last resort

After each attempt the field text is read back and verified.
"""

import base64
import logging
import subprocess
import time

log = logging.getLogger(__name__)

# Characters that need escaping for `adb shell input text`
_SHELL_SPECIAL = set('()&;<>|$`\\!"\'{}[]~*?# ')


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
        # .text attribute
        txt = info.get('text', '') or ''
        return txt
    except Exception:
        return ''


def _clear_field(field):
    """Clear a u2 field."""
    try:
        field.clear_text()
        time.sleep(0.3)
    except Exception:
        pass


def reliable_type_text(device, adb_serial: str, field, text: str,
                       device_serial: str = '') -> bool:
    """
    Type *text* into *field* using a multi-method fallback chain.

    Args:
        device:        uiautomator2 device object
        adb_serial:    ADB serial  e.g. '10.1.10.183:5555'
        field:         u2 selector for the target EditText (already located)
        text:          The text to type
        device_serial: Human-readable serial for logging (optional)

    Returns True if the text was successfully entered and verified.
    """
    tag = device_serial or adb_serial

    methods = [
        ('u2_set_text',   _try_set_text),
        ('u2_send_keys',  _try_send_keys),
        ('adb_input_text', _try_adb_input),
        ('adb_base64',    _try_adb_base64),
    ]

    for method_name, method_fn in methods:
        # Clear before each attempt
        try:
            field.click()
            time.sleep(0.3)
        except Exception:
            pass
        _clear_field(field)

        try:
            method_fn(device, adb_serial, field, text)
        except Exception as exc:
            log.warning("[%s] %s raised: %s", tag, method_name, exc)
            continue

        # Small pause for UI to settle
        time.sleep(0.5)

        # Verify
        actual = _read_field_text(field)
        # For password fields the text may be masked as dots – accept if lengths match
        if actual == text:
            log.info("[%s] Text entered OK via %s", tag, method_name)
            return True

        # Length-based fallback check (masked password fields)
        if len(actual) == len(text) and actual != '':
            log.info("[%s] Text length matches (%d) via %s (possibly masked)",
                     tag, len(text), method_name)
            return True

        # Check for bullet chars (password masking)
        if actual and all(c in ('•', '●', '*', '⬤', '\u2022', '\u25CF') for c in actual) and len(actual) == len(text):
            log.info("[%s] Text masked (%d chars) via %s", tag, len(text), method_name)
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
