"""
TextVerified v2 client — rent phone numbers + pull SMS codes for account
creation / phone challenges (Gmail or IG asking for a number).

Thin urllib client (no extra dependency -> clean PyArmor build). Endpoints
(from the v2 OpenAPI spec, base https://www.textverified.com/api/pub/v2):
  POST /auth                       X-API-USERNAME + X-API-KEY -> {token, expiresAt}
  GET  /account/me                 -> {username, balance}
  GET  /services?numberType&reservationType -> [{serviceName, displayName}]
  POST /verifications              {serviceName, capability, numberType} -> 201 + href
  GET  /verifications/{id}         -> {id, phoneNumber, state, smsResults[], links}
  GET  /sms?reservationId={id}     -> {data:[{content, from, receivedAt}]}
  POST /verifications/{id}/cancel
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request


class TextVerifiedError(Exception):
    pass


# Cloudflare in front of textverified.com bans the default urllib User-Agent
# (HTTP 403 "error code: 1010"). A normal browser UA passes the integrity check.
_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')


class TextVerified:
    def __init__(self, api_key, username,
                 base_url='https://www.textverified.com/api/pub/v2'):
        if not api_key or not username:
            raise TextVerifiedError('api_key and username (account email) required')
        self.api_key = api_key
        self.username = username
        self.base = base_url.rstrip('/')
        self._token = None
        self._token_exp = 0  # epoch seconds

    # ── low level ──
    def _now(self):
        return time.time()

    def _auth(self):
        req = urllib.request.Request(
            self.base + '/auth', data=b'', method='POST',
            headers={'X-API-USERNAME': self.username, 'X-API-KEY': self.api_key,
                     'User-Agent': _UA, 'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            raise TextVerifiedError(f'auth failed: {e.code} {e.read().decode("utf-8", "ignore")[:200]}')
        self._token = d.get('token')
        # expiresAt is an ISO timestamp; just cache for ~50 min to be safe
        self._token_exp = self._now() + 50 * 60
        if not self._token:
            raise TextVerifiedError(f'auth returned no token: {d}')
        return self._token

    def _bearer(self):
        if not self._token or self._now() >= self._token_exp:
            self._auth()
        return self._token

    def _req(self, method, path, body=None, query=None, _retry=True):
        url = self.base + path
        if query:
            url += '?' + urllib.parse.urlencode(query)
        data = json.dumps(body).encode('utf-8') if body is not None else None
        headers = {'Authorization': f'Bearer {self._bearer()}',
                   'Content-Type': 'application/json', 'Accept': 'application/json',
                   'User-Agent': _UA}
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                raw = r.read().decode('utf-8')
                loc = r.headers.get('Location')
                out = json.loads(raw) if raw.strip() else {}
                if isinstance(out, dict) and loc and 'href' not in out:
                    out['href'] = loc
                return out
        except urllib.error.HTTPError as e:
            if e.code == 401 and _retry:
                self._token = None
                return self._req(method, path, body, query, _retry=False)
            raise TextVerifiedError(f'{method} {path} -> {e.code} '
                                    f'{e.read().decode("utf-8", "ignore")[:200]}')

    # ── public ──
    def balance(self):
        d = self._req('GET', '/account/me')
        return d.get('balance', d.get('currentBalance'))

    def account(self):
        return self._req('GET', '/account/me')

    def list_services(self, number_type='mobile', reservation_type='verification'):
        return self._req('GET', '/services',
                         query={'numberType': number_type,
                                'reservationType': reservation_type})

    def find_service(self, keyword, number_type='mobile'):
        """Return the serviceName whose name/displayName matches keyword
        (e.g. 'instagram', 'google'). None if not found."""
        kw = keyword.lower()
        try:
            services = self.list_services(number_type=number_type) or []
        except Exception:
            return None
        items = services if isinstance(services, list) else services.get('data', [])
        for s in items:
            name = (s.get('serviceName') or '').lower()
            disp = (s.get('displayName') or '').lower()
            if kw == name or kw == disp:
                return s.get('serviceName')
        for s in items:
            if kw in (s.get('serviceName') or '').lower() or kw in (s.get('displayName') or '').lower():
                return s.get('serviceName')
        return None

    def _id_from_href(self, href):
        if not href:
            return None
        return href.rstrip('/').split('/')[-1]

    def create_verification(self, service_name, capability='sms',
                            number_type='mobile', max_price=None,
                            wait_for_number=120):
        """Rent a number for `service_name`. Returns {id, phone_number, state}.
        Polls until a phone number is assigned (up to wait_for_number sec)."""
        body = {'serviceName': service_name, 'capability': capability,
                'numberType': number_type}
        if max_price is not None:
            body['maxPrice'] = max_price
        created = self._req('POST', '/verifications', body=body)
        vid = self._id_from_href(created.get('href'))
        if not vid:
            raise TextVerifiedError(f'create returned no id/href: {created}')
        deadline = self._now() + wait_for_number
        details = {}
        while self._now() < deadline:
            details = self.get_verification(vid)
            # API populates the assigned number in `number` (phoneNumber stays null
            # in v2); accept either so we don't poll forever on an empty field.
            if details.get('number') or details.get('phoneNumber'):
                break
            time.sleep(3)
        return {'id': vid,
                'phone_number': details.get('number') or details.get('phoneNumber'),
                'state': details.get('state'),
                'raw': details}

    def get_verification(self, vid):
        return self._req('GET', f'/verifications/{vid}')

    # ── RENTAL (long-term number — for MOTHER accounts you want to keep) ──
    # one-time verification ≈ $0.36 (slaves); rental ≈ long-term (mother).
    def _rentals(self, renewable=True):
        path = ('/reservations/rental/renewable' if renewable
                else '/reservations/rental/nonrenewable')
        d = self._req('GET', path)
        return d.get('data', d if isinstance(d, list) else [])

    def get_rental(self, rid, renewable=True):
        path = ('/reservations/rental/renewable/' if renewable
                else '/reservations/rental/nonrenewable/') + str(rid)
        return self._req('GET', path)

    def create_rental(self, service_name, duration='oneYear', renewable=True,
                      number_type='mobile', max_price=None, wait_for_number=180):
        """Rent a long-term number. duration: oneDay|threeDay|sevenDay|
        fourteenDay|thirtyDay|ninetyDay|oneYear. Resolves the new number by
        diffing the rental list before/after (create returns a SALE href, not
        the number directly). Returns {id, phone_number, state, rental:True}."""
        before = {r.get('id') for r in self._rentals(renewable)}
        body = {'serviceName': service_name, 'isRenewable': renewable,
                'rentalDuration': duration, 'numberType': number_type}
        if max_price is not None:
            body['maxPrice'] = max_price
        self._req('POST', '/reservations/rental', body=body)
        deadline = self._now() + wait_for_number
        while self._now() < deadline:
            for r in self._rentals(renewable):
                num = r.get('phoneNumber') or r.get('number')
                if r.get('id') not in before and num:
                    return {'id': r.get('id'), 'phone_number': num,
                            'state': r.get('state'), 'rental': True, 'raw': r}
            time.sleep(4)
        return {'id': None, 'phone_number': None, 'state': 'pending', 'rental': True}

    def get_sms(self, reservation_id):
        d = self._req('GET', '/sms', query={'reservationId': reservation_id})
        return d.get('data', d if isinstance(d, list) else [])

    def wait_for_code(self, vid, timeout=180):
        """Poll until an SMS arrives, return the extracted numeric code (digits
        only, str) or None on timeout. Checks both verification.smsResults and /sms.
        Handles spaced codes — IG sends 'parsedCode' like '326 417' and content
        '326 417 is your Instagram code', so we strip the space and pull the digits."""
        deadline = self._now() + timeout
        while self._now() < deadline:
            try:
                det = self.get_verification(vid)
                msgs = list(det.get('smsResults') or []) + list(self.get_sms(vid) or [])
                for m in msgs:
                    pc = m.get('parsedCode')
                    if pc:
                        digits = ''.join(c for c in str(pc) if c.isdigit())
                        if 4 <= len(digits) <= 8:
                            return digits
                    txt = m.get('smsContent') or m.get('content') or ''
                    # collapse spaces BETWEEN digits ('326 417' -> '326417'), then
                    # grab the first 4-8 digit run.
                    flat = re.sub(r'(?<=\d)\s+(?=\d)', '', txt)
                    mm = re.search(r'(\d{4,8})', flat)
                    if mm:
                        return mm.group(1)
            except Exception:
                pass
            time.sleep(4)
        return None

    def cancel(self, vid):
        try:
            return self._req('POST', f'/verifications/{vid}/cancel')
        except Exception:
            return None


def from_settings(settings_path=None):
    """Build a client from global_settings.json -> textverified {api_key, username}."""
    import os
    if not settings_path:
        # this file: automation/ai_executor/textverified.py -> repo root is 3 up
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        settings_path = os.path.join(root, 'dashboard', 'global_settings.json')
    with open(settings_path, encoding='utf-8') as f:
        cfg = json.load(f).get('textverified', {})
    if not cfg.get('api_key') or not cfg.get('username'):
        return None
    return TextVerified(cfg['api_key'], cfg['username'],
                        base_url=cfg.get('base_url') or 'https://www.textverified.com/api/pub/v2')
