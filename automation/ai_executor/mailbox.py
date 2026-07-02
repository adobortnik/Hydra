"""
mailbox — provider-agnostic IMAP reader for email verification codes.

Strategy (John 2026-06-19): for SLAVE accounts we don't create a Gmail on the
device (2nd+ Gmail per device hits Google's phone wall, and the phones have no
SIM). Instead we use a CATCH-ALL DOMAIN: any address `whatever@ourdomain.com`
lands in one mailbox. IG is signed up with `name.x@ourdomain.com` and the
confirmation code is read HERE, from the server, over IMAP — never from the
phone. No Gmail app, no phone, no per-device limit.

Works with any IMAP provider that exposes the catch-all mailbox:
  - Migadu (real IMAP + catch-all, ~$19/yr)        host: imap.migadu.com
  - Cloudflare Email Routing -> forward to a Gmail  host: imap.gmail.com
  - Any standard IMAP server

Config lives in global_settings.json under "email_pool":
  {
    "domain":    "ourdomain.com",
    "imap_host": "imap.migadu.com",
    "imap_port": 993,
    "imap_user": "catchall@ourdomain.com",
    "imap_pass": "<app password>",
    "ssl":       true
  }

Pure-stdlib (imaplib + email). No external deps.
"""

import email
import imaplib
import json
import os
import re
import time
from email.header import decode_header
from email.utils import parsedate_to_datetime

_GS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'dashboard', 'global_settings.json')

# Senders that legitimately carry an IG / verification code.
_DEFAULT_SENDERS = ('instagram', 'facebookmail', 'mail.instagram.com')


def _decode(s):
    if not s:
        return ''
    out = []
    for part, enc in decode_header(s):
        if isinstance(part, bytes):
            try:
                out.append(part.decode(enc or 'utf-8', 'ignore'))
            except Exception:
                out.append(part.decode('utf-8', 'ignore'))
        else:
            out.append(part)
    return ''.join(out)


def _extract_code(subject, body):
    """IG verification codes are 6 standalone digits. Prefer the SUBJECT (IG puts
    the code there: '123456 is your Instagram code') then the body."""
    for text in (subject, body):
        if not text:
            continue
        # tolerate "123 456" spacing some clients introduce
        flat = re.sub(r'(?<=\d)\s(?=\d)', '', text)
        m = re.findall(r'(?<!\d)(\d{6})(?!\d)', flat)
        if m:
            return m[0]
    return None


def _body_text(msg):
    """Best-effort plain text of an email (prefers text/plain, falls back to
    stripped HTML)."""
    parts = []
    if msg.is_multipart():
        for p in msg.walk():
            ct = p.get_content_type()
            if ct in ('text/plain', 'text/html'):
                try:
                    payload = p.get_payload(decode=True) or b''
                    parts.append((ct, payload.decode(
                        p.get_content_charset() or 'utf-8', 'ignore')))
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True) or b''
            parts.append((msg.get_content_type(),
                          payload.decode(msg.get_content_charset() or 'utf-8',
                                         'ignore')))
        except Exception:
            pass
    plain = [t for ct, t in parts if ct == 'text/plain']
    if plain:
        return '\n'.join(plain)
    html = '\n'.join(t for ct, t in parts if ct == 'text/html')
    return re.sub(r'<[^>]+>', ' ', html)


class Mailbox:
    """Thin IMAP client tuned for fetching a verification code addressed to a
    specific catch-all recipient."""

    def __init__(self, host, user, password, port=993, ssl=True):
        self.host = host
        self.port = int(port or 993)
        self.user = user
        self.password = password
        self.ssl = bool(ssl)

    # ── connection ────────────────────────────────────────────────────────
    def _connect(self):
        if self.ssl:
            m = imaplib.IMAP4_SSL(self.host, self.port)
        else:
            m = imaplib.IMAP4(self.host, self.port)
        m.login(self.user, self.password)
        return m

    def check(self):
        """Verify credentials/connection. Returns (ok, message)."""
        try:
            m = self._connect()
            m.select('INBOX', readonly=True)
            m.logout()
            return True, 'connected'
        except Exception as e:
            return False, str(e)

    # ── code fetch ────────────────────────────────────────────────────────
    def _scan_once(self, to_address, senders, since_ts):
        """Return (code, msg_uid) for the newest matching message, or (None,None).
        Matches by recipient (To/Delivered-To/Cc contains to_address) AND, when
        senders is given, by From containing one of them."""
        to_address = (to_address or '').strip().lower()
        m = self._connect()
        try:
            m.select('INBOX')
            # Server-side narrow by recipient when possible; fall back to recent.
            typ, data = m.search(None, 'TO', to_address)
            ids = data[0].split() if (typ == 'OK' and data and data[0]) else []
            if not ids:
                typ, data = m.search(None, 'ALL')
                ids = data[0].split() if (typ == 'OK' and data and data[0]) else []
                ids = ids[-40:]                      # only recent
            best = None
            for num in reversed(ids):                # newest first
                typ, md = m.fetch(num, '(RFC822)')
                if typ != 'OK' or not md or not md[0]:
                    continue
                msg = email.message_from_bytes(md[0][1])
                # date filter
                if since_ts:
                    try:
                        dt = parsedate_to_datetime(msg.get('Date'))
                        if dt and dt.timestamp() < since_ts - 60:
                            continue
                    except Exception:
                        pass
                # recipient filter (catch-all: any header may carry it)
                rcpt = ' '.join(filter(None, [
                    msg.get('To', ''), msg.get('Delivered-To', ''),
                    msg.get('Cc', ''), msg.get('X-Original-To', '')])).lower()
                if to_address and to_address not in rcpt:
                    continue
                # sender filter
                frm = _decode(msg.get('From', '')).lower()
                if senders and not any(s in frm for s in senders):
                    continue
                subject = _decode(msg.get('Subject', ''))
                code = _extract_code(subject, _body_text(msg))
                if code:
                    best = (code, num)
                    break
            return best or (None, None)
        finally:
            try:
                m.logout()
            except Exception:
                pass

    def wait_for_code(self, to_address, timeout=180, poll=6, senders=None,
                      since_ts=None, mark_seen=True):
        """Poll the mailbox until a verification code addressed to `to_address`
        arrives (or timeout). Returns the code string or None.

        since_ts: ignore mail older than this epoch (defaults to now-120s so a
        stale code from a previous run isn't reused)."""
        senders = senders if senders is not None else _DEFAULT_SENDERS
        if since_ts is None:
            since_ts = time.time() - 120
        deadline = time.time() + max(10, timeout)
        while time.time() < deadline:
            try:
                code, uid = self._scan_once(to_address, senders, since_ts)
            except Exception as e:
                print('[mailbox] scan error:', e)
                code, uid = None, None
            if code:
                if mark_seen and uid:
                    try:
                        m = self._connect()
                        m.select('INBOX')
                        m.store(uid, '+FLAGS', '\\Seen')
                        m.logout()
                    except Exception:
                        pass
                return code
            time.sleep(poll)
        return None


def from_settings(path=None):
    """Build a Mailbox from global_settings.json 'email_pool'. Returns None if
    not configured."""
    p = path or _GS
    try:
        cfg = (json.load(open(p, encoding='utf-8')) or {}).get('email_pool') or {}
    except Exception:
        return None
    host = cfg.get('imap_host')
    user = cfg.get('imap_user')
    pw = cfg.get('imap_pass')
    if not (host and user and pw):
        return None
    return Mailbox(host, user, pw, port=cfg.get('imap_port', 993),
                   ssl=cfg.get('ssl', True))


def settings_domain(path=None):
    """The catch-all domain from settings (e.g. 'ourdomain.com'), or None."""
    p = path or _GS
    try:
        cfg = (json.load(open(p, encoding='utf-8')) or {}).get('email_pool') or {}
        return (cfg.get('domain') or '').strip() or None
    except Exception:
        return None
