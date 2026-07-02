"""
Actions — the low-level "clicker API" the AI drives, on top of uiautomator2.

Every action returns an ActionResult so the executor can tell whether the
screen actually changed (used for retry / stuck detection). This is where the
operator's "never give up" rules live:
  - a tap that does nothing is retried a few times (clone apps swallow taps)
  - recover_background(): go to recents, come back, so a stuck flow re-renders
  - reopen_app(): force-stop + relaunch the exact account's IG clone
"""

import time


class ActionResult:
    def __init__(self, ok, changed, note=''):
        self.ok = ok
        self.changed = changed
        self.note = note

    def __repr__(self):
        return f'<ActionResult ok={self.ok} changed={self.changed} {self.note}>'


def _screen_sig(device):
    try:
        import hashlib
        return hashlib.md5(device.dump_hierarchy().encode('utf-8', 'ignore')).hexdigest()
    except Exception:
        return None


class Actions:
    def __init__(self, device, package=None, log=print,
                 phone_client=None, phone_service=None, phone_mode='verification'):
        self.d = device
        self.package = package
        self.log = log
        # phone verification (TextVerified) — rent a number / read the SMS code
        self.phone_client = phone_client
        self.phone_service = phone_service
        self.phone_mode = phone_mode      # 'verification' (one-time, cheap) | 'rental' (long-term, mother)
        self.phone_rental = None

    # ── helper: run something then report if the screen changed ──
    # `before` lets the caller pass the perception's state_hash so we skip a
    # redundant dump_hierarchy (each dump is ~0.5-1.5s over network ADB).
    def _with_change(self, fn, settle=1.0, before=None):
        if before is None:
            before = _screen_sig(self.d)
        fn()
        time.sleep(settle)
        after = _screen_sig(self.d)
        return ActionResult(True, before != after)

    # ── tap an element by its real bounds, with retry (clone apps drop taps) ──
    def tap_element(self, element, retries=3, before=None):
        # tap a RANDOM point in the element's central area (a human finger never
        # hits the exact pixel-center every time; reduces the bot signature).
        import random as _r
        x1, y1, x2, y2 = element.bounds
        x = int(x1 + (x2 - x1) * _r.uniform(0.34, 0.66))
        y = int(y1 + (y2 - y1) * _r.uniform(0.34, 0.66))
        return self.tap_xy(x, y, retries=retries, label=element.label, before=before)

    def tap_xy(self, x, y, retries=3, label='', before=None):
        if before is None:
            before = _screen_sig(self.d)
        for attempt in range(1, retries + 1):
            try:
                self.d.click(x, y)
            except Exception as e:
                self.log(f'  tap error: {e}')
            time.sleep(0.8)
            after = _screen_sig(self.d)
            if after != before:
                return ActionResult(True, True, f'tap "{label}" (attempt {attempt})')
            # screen unchanged — the operator's rule: click again
            self.log(f'  tap "{label}" no change, retrying ({attempt}/{retries})')
            time.sleep(0.5)
        return ActionResult(True, False, f'tap "{label}" no change after {retries}')

    def double_tap(self, x, y):
        """Double-tap (IG like-by-double-tap on a photo/reel). Falls back to two
        quick coordinate taps if u2 double_click is unavailable."""
        try:
            self.d.double_click(x, y, 0.15)
        except Exception:
            try:
                self.d.click(x, y)
                time.sleep(0.08)
                self.d.click(x, y)
            except Exception:
                pass
        time.sleep(1.0)
        return ActionResult(True, True, f'double-tap ({x},{y})')

    def key(self, name):
        """Press a hardware/IME key (enter to submit search, back, home, ...)."""
        k = (name or 'enter').lower()
        return self._with_change(lambda: self.d.press(k))

    # ── phone verification (TextVerified) ──
    def get_phone(self, service=None, mode=None):
        """Get a real phone number for the service and type it into the focused
        field. mode='rental' rents a long-term number (MOTHER accounts you keep);
        'verification' (default) buys a cheap one-time number (slaves). Stores the
        reservation so get_sms_code can read the code later."""
        if not self.phone_client:
            return ActionResult(False, False, 'no phone provider configured')
        svc = service or self.phone_service or 'instagram'
        m = mode or self.phone_mode or 'verification'
        # REUSE an already-rented number instead of renting another (the LLM may
        # re-emit get_phone on a retry) — just re-type the existing one.
        existing = getattr(self, 'phone_rental', None)
        if existing and existing.get('phone_number'):
            num = self._format_phone(existing['phone_number'])
            r = self._type_into_focused(num)
            r.note = f'reused number {num} + typed'
            return r
        try:
            if m == 'rental':
                rental = self.phone_client.create_rental(svc)
            else:
                rental = self.phone_client.create_verification(svc)
        except Exception as e:
            return ActionResult(False, False, f'get number ({m}) failed: {e}')
        self.phone_rental = rental
        raw = rental.get('phone_number')
        if not raw:
            return ActionResult(False, False, 'no number assigned (timeout/stock)')
        num = self._format_phone(raw)
        self.log(f'  got {m} number {num} for {svc} (id {rental.get("id")})')
        r = self._type_into_focused(num)
        r.note = f'{m} number {num} + typed'
        return r

    @staticmethod
    def _format_phone(num):
        """Apps (IG) need the number WITH country code or they parse it against the
        default country selector and reject it. TextVerified gives bare US numbers
        (10 digits) — prefix +1 so it's unambiguous regardless of the UI default."""
        n = str(num).strip()
        if n.startswith('+'):
            return n
        digits = ''.join(c for c in n if c.isdigit())
        if len(digits) == 10:
            return '+1' + digits
        if len(digits) == 11 and digits.startswith('1'):
            return '+' + digits
        return '+' + digits

    def get_sms_code(self, timeout=180):
        """Wait for the SMS on the active rental and type the code into the
        focused field."""
        if not self.phone_client or not self.phone_rental:
            return ActionResult(False, False, 'no active phone rental')
        vid = self.phone_rental.get('id')
        self.log(f'  waiting for SMS code on rental {vid}…')
        code = None
        try:
            code = self.phone_client.wait_for_code(vid, timeout=timeout)
        except Exception as e:
            return ActionResult(False, False, f'sms wait failed: {e}')
        if not code:
            return ActionResult(False, False, 'no SMS code received (timeout)')
        self.log(f'  got SMS code {code}')
        r = self._type_into_focused(code)
        r.note = f'SMS code {code} typed'
        return r

    _MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
               'jul', 'aug', 'sep', 'oct', 'nov', 'dec']

    def set_date(self, year=None, month=None, day=None, min_age=20):
        """Set a native Android 3-wheel date picker (IG 'What's your birthday?' ->
        'Set date' dialog: Month | Day | Year NumberPickers + SET). Detects each
        column by its current value (month name / 4-digit year / 1-31 day) so it's
        independent of locale column order, steps each wheel to target with 1-step
        swipes (down=lower, up=higher), then taps SET. GUARANTEES age >= min_age by
        clamping the birth year."""
        import re as _re
        import time as _time
        cols = self._picker_inputs()
        if len(cols) < 3:
            return ActionResult(False, False, f'date picker not found ({len(cols)} wheels)')
        roles = {}
        for e in cols:
            txt = (e.text or '').strip()
            cx = e.rect[0] + e.rect[2] // 2
            cy = e.rect[1] + e.rect[3] // 2
            if txt[:3].lower() in self._MONTHS:
                roles['month'] = (cx, cy)
            elif _re.fullmatch(r'\d{4}', txt):
                roles['year'] = (cx, cy)
            elif _re.fullmatch(r'\d{1,2}', txt):
                roles['day'] = (cx, cy)
        if 'year' not in roles:
            return ActionResult(False, False, 'date picker: no year wheel detected')

        cur_year = _time.localtime().tm_year
        ty = int(_re.sub(r'\D', '', str(year))) if year else (cur_year - 22)
        ty = min(ty, cur_year - min_age)        # enforce age >= min_age
        ty = max(ty, 1940)
        tm = self._month_num(month) if month else 6
        td = int(_re.sub(r'\D', '', str(day))) if day else 15
        td = min(max(td, 1), 28)                # 28 is valid for every month

        ok = self._set_wheel(*roles['year'], ty, 'num')
        if 'month' in roles:
            ok = self._set_wheel(*roles['month'], tm, 'month') and ok
        if 'day' in roles:
            ok = self._set_wheel(*roles['day'], td, 'num') and ok

        for label in ('SET', 'Set', 'DONE', 'Done', 'OK', 'Ok'):
            try:
                btn = self.d(text=label)
                if btn.exists:
                    btn.click()
                    break
            except Exception:
                pass
        time.sleep(0.8)
        return ActionResult(True, True, f'set date {ty}-{tm:02d}-{td:02d} (age>={min_age})')

    def _picker_inputs(self):
        try:
            els = self.d.xpath('//*[@resource-id="android:id/numberpicker_input"]').all()
        except Exception:
            els = []
        return sorted(els, key=lambda e: e.rect[0])

    def _set_wheel(self, cx, cy, target, kind, max_steps=80):
        """Step one NumberPicker column to `target` (down swipe = decrease, up =
        increase), reading the centered numberpicker_input after each 1-step swipe."""
        import re as _re
        for _ in range(max_steps):
            cur = None
            for e in self._picker_inputs():
                if abs((e.rect[0] + e.rect[2] // 2) - cx) < 60:
                    cur = (e.text or '').strip()
                    break
            if cur is None:
                return False
            if kind == 'month':
                key = cur[:3].lower()
                cv = (self._MONTHS.index(key) + 1) if key in self._MONTHS else None
            else:
                digits = _re.sub(r'\D', '', cur)
                cv = int(digits) if digits else None
            if cv is None:
                return False
            if cv == target:
                return True
            if cv > target:
                self.d.swipe(cx, cy - 100, cx, cy + 100, 0.15)   # down -> decrease
            else:
                self.d.swipe(cx, cy + 100, cx, cy - 100, 0.15)   # up -> increase
            time.sleep(0.4)
        return False

    def _month_num(self, month):
        import re as _re
        if month is None:
            return 6
        s = str(month).strip().lower()
        if s[:3] in self._MONTHS:
            return self._MONTHS.index(s[:3]) + 1
        digits = _re.sub(r'\D', '', s)
        return min(max(int(digits), 1), 12) if digits else 6

    def set_username(self, username, max_tries=6):
        """IG 'Create a username' screen: clear IG's suggested handle, type OUR
        scheme username, tap Next. If it stays on the username screen (taken /
        invalid), retry with a digit-suffixed variant until one is accepted. Keeps
        the naming scheme — never leaves IG's random suggestion."""
        import re as _re
        import random as _r
        base = _re.sub(r'[^a-z0-9._]', '', (username or '').lower()).strip('._') or 'user'

        def on_username_screen():
            try:
                return (self.d(textContains='a username').exists or
                        self.d(textContains='Create a username').exists)
            except Exception:
                return False

        last = base
        for attempt in range(max_tries):
            last = base if attempt == 0 else (base[:24] + str(_r.randint(10, 99999)))
            last = last[:30].strip('._')
            try:
                f = self.d(className='android.widget.EditText')
                if f.exists:
                    f.click()
                    time.sleep(0.4)
            except Exception:
                pass
            self._type_into_focused(last)
            time.sleep(0.6)
            try:
                nx = self.d(text='Next')
                if nx.exists:
                    nx.click()
                else:
                    self.d.click(540, 902)
            except Exception:
                self.d.click(540, 902)
            time.sleep(2.5)
            if not on_username_screen():
                return ActionResult(True, True, f'username set: {last}')
            self.log(f'  username "{last}" not accepted, trying a variant')
        return ActionResult(False, True, f'username not set after {max_tries} tries (last {last})')

    def type_text(self, element, text):
        try:
            x, y = element.center()
            self.d.click(x, y)
            time.sleep(0.4)
        except Exception:
            pass
        return self._type_into_focused(text)

    def _type_into_focused(self, text):
        """Type into the (already focused) field, mirroring the bot engine's
        battle-tested `reliable_type_text` (automation/text_input.py):
          1. thorough clear: clear_text + adb MOVE_END + 30x DEL (clone fields
             ignore a single clear),
          2. adb `input text` PRIMARY (u2 set_text/send_keys are unreliable on
             clone packages); unicode/emoji -> u2 send_keys (adb can't type it),
          3. RELAXED verify: IG EditTexts report hint/placeholder text even after
             typing, so a missing probe is NOT a failure — trust a successful
             input (returncode 0). This stops the false 're-type' loop."""
        import re
        import subprocess
        serial = getattr(self.d, 'serial', None)

        # 1. thorough clear of the focused field
        try:
            self.d.clear_text()
        except Exception:
            pass
        if serial:
            try:
                subprocess.run(['adb', '-s', serial, 'shell', 'input', 'keyevent',
                                'KEYCODE_MOVE_END'], capture_output=True, timeout=5)
                subprocess.run(['adb', '-s', serial, 'shell', 'input', 'keyevent',
                                '--longpress'] + ['KEYCODE_DEL'] * 30,
                               capture_output=True, timeout=10)
            except Exception:
                pass
        time.sleep(0.3)

        # 2. type CHAR-BY-CHAR with a human rhythm (NOT an instant paste of the
        #    whole string — pasting a full password/field looks bot-ish and helps
        #    trigger phone challenges; typing letter-by-letter passes more often).
        import random as _rnd
        has_unicode = any(ord(c) > 0x7e for c in text)
        typed = False
        if serial and not has_unicode:
            try:
                from automation.text_input import _escape_for_adb
                ok_all = True
                for ch in text:
                    rr = subprocess.run(['adb', '-s', serial, 'shell', 'input',
                                         'text', _escape_for_adb(ch)],
                                        capture_output=True, timeout=10)
                    if rr.returncode != 0:
                        ok_all = False
                        break
                    time.sleep(_rnd.uniform(0.05, 0.16))   # human typing speed
                typed = ok_all
            except Exception:
                typed = False
        if not typed:
            try:
                self.d.send_keys(text, clear=False)   # handles unicode/emoji
                typed = True
            except Exception:
                pass
        if not typed:
            try:
                self.d.set_text(text)                 # last resort
                typed = True
            except Exception:
                pass
        time.sleep(0.7)

        # 3. RELAXED verify — trust a successful input; only UPGRADE confidence if
        #    we can actually see the text (IG often hides it behind a hint).
        confirmed = typed
        try:
            probe = re.sub(r'[^A-Za-z0-9 ]', '', text).strip()[:12]
            if probe and probe in self.d.dump_hierarchy():
                confirmed = True
        except Exception:
            pass
        note = f'typed "{text[:24]}"' + ('' if confirmed else ' (sent; IG may hide field text)')
        return ActionResult(typed, confirmed, note)

    def swipe(self, direction='up', dist=0.6):
        """Vertical swipes use the bot engine's proven 'safe zone' (see
        ig_controller.swipe_to_next_reel): x left-of-center at ~0.40w to DODGE
        the right-side action-button column (like/comment/share) on reels, and a
        clean fast FLING over the video area — not over the caption/controls at
        the bottom. This is what actually advances a reel (and scrolls a feed)."""
        import random as _rand
        w, h = self.d.window_size()
        cx = int(w * 0.40) + _rand.randint(-12, 12)   # off-center: avoid buttons
        if direction == 'up':       # advance: next reel / further down the feed
            a, b = int(h * 0.62), int(h * 0.12)
        elif direction == 'down':   # go back up
            a, b = int(h * 0.30), int(h * 0.80)
        elif direction == 'left':
            return self._with_change(lambda: self.d.swipe(int(w * 0.8), h // 2, int(w * 0.2), h // 2, 0.25))
        else:  # right
            return self._with_change(lambda: self.d.swipe(int(w * 0.2), h // 2, int(w * 0.8), h // 2, 0.25))
        dur = _rand.uniform(0.20, 0.35)               # fast = fling that snaps
        return self._with_change(lambda: self.d.swipe(cx, a, cx, b, dur))

    def scroll(self, direction='up'):
        r = self.swipe(direction=direction)
        r.note = f'scroll {direction}'
        return r

    def pick_dropdown(self, element, before_perception=None, option_index=0):
        """Open a dropdown/spinner and tap an OPTION deterministically by POSITION
        (the options are usually UNLABELLED buttons that can't be re-found by
        identity — this is what broke replay on Month/Gender). Opens the dropdown,
        diffs the screen to find the NEW clickable option rows, taps the
        option_index-th (default the first). For a birthday month / gender the
        exact value doesn't matter, so the first option is fine."""
        from .perception import perceive
        before = set()
        if before_perception is not None:
            before = {e.bounds for e in before_perception.elements}
        # open the dropdown
        self.tap_element(element)
        time.sleep(1.0)
        p2 = perceive(self.d)
        dz = element.bounds
        # options = NEW clickable elements that appeared below the dropdown
        opts = [e for e in p2.elements
                if e.bounds not in before and e.clickable
                and e.bounds[1] >= dz[1] - 5]
        opts.sort(key=lambda e: e.bounds[1])   # topmost first
        if not opts:
            # fallback: any clickable row just below the dropdown
            opts = sorted([e for e in p2.elements
                           if e.clickable and e.bounds[1] > dz[1] + 5],
                          key=lambda e: e.bounds[1])
        if not opts:
            return ActionResult(False, False, 'dropdown opened but no options found')
        target = opts[min(option_index, len(opts) - 1)]
        x, y = target.center()
        self.d.click(x, y)
        time.sleep(0.8)
        return ActionResult(True, True, f'picked dropdown option @y={target.bounds[1]}')

    def scroll_to_bottom(self, max_swipes=8):
        """Fling to the BOTTOM of a long page (Terms / consent) in ONE action —
        several big fast swipes, stopping as soon as the screen stops changing
        (bottom reached). Saves the slow 'scroll a little, ask AI, repeat' loop."""
        import random as _r
        w, h = self.d.window_size()
        cx = int(w * 0.5) + _r.randint(-10, 10)
        n = 0
        for _ in range(max_swipes):
            before = _screen_sig(self.d)
            self.d.swipe(cx, int(h * 0.86), cx, int(h * 0.14),
                         _r.uniform(0.12, 0.22))   # big fast fling
            time.sleep(0.5)
            n += 1
            if _screen_sig(self.d) == before:       # nothing moved -> at bottom
                break
        return ActionResult(True, True, f'scrolled to bottom ({n} swipes)')

    def back(self):
        return self._with_change(lambda: self.d.press('back'))

    def wait(self, seconds=2):
        time.sleep(min(float(seconds), 15))
        return ActionResult(True, True, f'wait {seconds}s')

    def force_portrait(self, full=True):
        """Lock the device to portrait so a stray gesture / WebView (e.g. Google
        MinuteMaid sign-in) can't flip it to landscape mid-run. The reliable
        mechanism is the adb system settings (accelerometer_rotation=0 +
        user_rotation=0 = portrait on a portrait-natural phone); u2
        freeze_rotation did NOT hold (auto-rotate got re-enabled). So we re-assert
        the adb settings every step (cheap, idempotent); `full` also nudges u2."""
        import subprocess
        serial = getattr(self.d, 'serial', None)
        if serial:
            cmds = [['settings', 'put', 'system', 'accelerometer_rotation', '0'],
                    ['settings', 'put', 'system', 'user_rotation', '0'],
                    # Android 12+ window-manager lock (more authoritative than the
                    # settings when an app keeps re-enabling auto-rotate)
                    ['cmd', 'window', 'set-user-rotation', 'lock', '0']]
            for cmd in cmds:
                try:
                    subprocess.run(['adb', '-s', serial, 'shell'] + cmd,
                                   capture_output=True, timeout=5)
                except Exception:
                    pass
        if full:
            try:
                self.d.set_orientation('natural')
            except Exception:
                pass
            try:
                self.d.freeze_rotation(True)
            except Exception:
                pass
        return ActionResult(True, False, 'portrait locked')

    # ── recovery: go to background and return (operator's trick) ──
    def recover_background(self):
        """Recents -> back to the app. Forces a re-render of a stuck screen."""
        self.log('  recovery: background -> return')
        try:
            self.d.press('recent')
            time.sleep(1.5)
            self.d.press('back')  # close recents, return to app
            time.sleep(1.5)
        except Exception as e:
            self.log(f'  recover_background error: {e}')
        return ActionResult(True, True, 'background/return')

    def reopen_app(self):
        """Force-stop + relaunch the exact package (last-resort recovery)."""
        if not self.package:
            return ActionResult(False, False, 'no package to reopen')
        self.log(f'  recovery: reopen {self.package}')
        try:
            self.d.app_stop(self.package)
            time.sleep(1.5)
            self.d.app_start(self.package)
            time.sleep(4)
            self.force_portrait()   # relaunch can reset orientation
        except Exception as e:
            self.log(f'  reopen_app error: {e}')
        return ActionResult(True, True, f'reopened {self.package}')

    # ── dispatch a structured action dict from the LLM ──
    def execute(self, action, perception):
        """action = {"type": "...", ...}.  perception gives element lookup."""
        t = action.get('type')
        # safety net: the model sometimes emits get_phone / get_sms_code as a
        # TYPE action whose text is the literal "get_phone" instead of using the
        # action type. Catch that and dispatch the real phone action.
        if t == 'type':
            _t = (action.get('text') or '').strip().lower().replace(' ', '_')
            if _t in ('get_phone', 'getphone'):
                return self.get_phone()
            if _t in ('get_sms_code', 'get_code', 'getsmscode'):
                return self.get_sms_code()
        if t == 'tap':
            idx = action.get('index')
            el = perception.by_idx(idx) if idx is not None else None
            if el:
                return self.tap_element(el)
            if 'x' in action and 'y' in action:
                return self.tap_xy(int(action['x']), int(action['y']), label='xy')
            return ActionResult(False, False, f'tap: no element #{idx}')
        if t == 'type':
            idx = action.get('index')
            el = perception.by_idx(idx) if idx is not None else None
            text = action.get('text', '')
            if el:
                return self.type_text(el, text)
            return self._type_into_focused(text)
        if t == 'pick_dropdown':
            idx = action.get('index')
            el = perception.by_idx(idx) if idx is not None else None
            if el:
                return self.pick_dropdown(el, before_perception=perception,
                                          option_index=int(action.get('option', 0) or 0))
            return ActionResult(False, False, f'pick_dropdown: no element #{idx}')
        if t == 'double_tap':
            idx = action.get('index')
            el = perception.by_idx(idx) if idx is not None else None
            if el:
                x, y = el.center()
                return self.double_tap(x, y)
            if 'x' in action and 'y' in action:
                return self.double_tap(int(action['x']), int(action['y']))
            # no target -> center-upper (the photo/reel area) to like current media
            w, h = self.d.window_size()
            return self.double_tap(w // 2, int(h * 0.40))
        if t == 'key':
            return self.key(action.get('key', 'enter'))
        if t == 'get_phone':
            return self.get_phone(action.get('service'))
        if t == 'get_sms_code':
            return self.get_sms_code()
        if t == 'set_date':
            return self.set_date(year=action.get('year'), month=action.get('month'),
                                 day=action.get('day'))
        if t == 'set_username':
            return self.set_username(action.get('username') or action.get('text') or '')
        if t == 'swipe':
            return self.swipe(action.get('direction', 'up'))
        if t == 'scroll':
            return self.scroll(action.get('direction', 'up'))
        if t == 'scroll_to_bottom':
            return self.scroll_to_bottom()
        if t == 'back':
            return self.back()
        if t == 'wait':
            return self.wait(action.get('seconds', 2))
        if t == 'recover':
            return self.recover_background()
        if t == 'reopen':
            return self.reopen_app()
        if t == 'done':
            return ActionResult(True, False, 'done')
        return ActionResult(False, False, f'unknown action {t}')
