"""
Perception — turn the live device screen into something an LLM can reason about.

Hybrid strategy (cheaper + more reliable than pure vision):
  1. PRIMARY: uiautomator2 XML hierarchy -> a compact, NUMBERED list of
     interactive elements (clickable / editable / scrollable) with their real
     bounds. Most steps need only this TEXT -> cheap, precise (no pixel guessing).
  2. FALLBACK: when the tree is sparse (Jetpack Compose / WebView / icon-only
     screens) we render a Set-of-Marks screenshot: the numbered boxes drawn on
     the real screenshot so a vision model just picks a NUMBER, not raw pixels.

This module is provider-agnostic — it only produces the perception payload.
"""

import hashlib
import io
import re
import xml.etree.ElementTree as ET


# Attributes that mean "the user can interact with this node"
def _is_interactive(attrib):
    return (
        attrib.get('clickable') == 'true'
        or attrib.get('long-clickable') == 'true'
        or attrib.get('checkable') == 'true'
        or attrib.get('scrollable') == 'true'
        or attrib.get('focusable') == 'true' and attrib.get('class', '').endswith('EditText')
        or attrib.get('class', '').endswith('EditText')
    )


def _parse_bounds(b):
    m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', b or '')
    if not m:
        return None
    x1, y1, x2, y2 = map(int, m.groups())
    return (x1, y1, x2, y2)


def _label_for(attrib):
    """Best human label for an element."""
    for k in ('text', 'content-desc', 'resource-id', 'hint'):
        v = (attrib.get(k) or '').strip()
        if v:
            # shorten resource-id to its tail
            if k == 'resource-id' and ':id/' in v:
                v = v.split(':id/')[-1]
            return v[:80]
    return ''


class Element:
    __slots__ = ('idx', 'cls', 'label', 'rid', 'bounds', 'editable',
                 'scrollable', 'clickable', 'checked', 'pkg')

    def __init__(self, idx, attrib, bounds):
        cls = attrib.get('class', '')
        rid = (attrib.get('resource-id') or '')
        self.idx = idx
        self.cls = cls.split('.')[-1] if cls else '?'
        self.label = _label_for(attrib)
        self.rid = rid.split(':id/')[-1] if ':id/' in rid else rid  # stable id tail
        self.bounds = bounds  # (x1,y1,x2,y2)
        self.editable = cls.endswith('EditText')
        self.scrollable = attrib.get('scrollable') == 'true'
        self.clickable = attrib.get('clickable') == 'true'
        self.checked = attrib.get('checked')
        self.pkg = attrib.get('package', '')

    def center(self):
        x1, y1, x2, y2 = self.bounds
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    def identity(self):
        """Stable identity used to re-find this element on replay (coords drift,
        rid/label/class don't)."""
        return {'rid': self.rid, 'label': self.label, 'cls': self.cls}

    def describe(self):
        kind = ('EDIT' if self.editable
                else 'SCROLL' if self.scrollable
                else 'BTN' if self.clickable
                else self.cls)
        chk = '' if self.checked in (None, '') else f' checked={self.checked}'
        lab = f' "{self.label}"' if self.label else ''
        # disambiguate the like affordances (model kept tapping the count / the
        # already-'Liked' button / a comment-screen heart instead of liking)
        hint = ''
        low = (self.label or '').lower().strip()
        rl = (self.rid or '').lower()
        if self.cls == 'Spinner':
            # tell the model whether the dropdown is already SET (so it stops
            # re-opening it and moves on) or still empty.
            kind = 'DROPDOWN'
            if self.label:
                hint = (f'  <<DROPDOWN already SELECTED="{self.label}" — it is SET,'
                        f' do NOT tap it again, move to the NEXT field>>')
            else:
                hint = '  <<DROPDOWN empty — tap to open, then tap an option>>'
        elif low in ('like', 'liked', 'unlike') or rl.endswith('button_like'):
            hint = f'  <<POST LIKE BUTTON state="{self.label or "?"}">>'
        elif re.search(r'\d[\d.,]*\s*likes?\b', low) or low.endswith('others'):
            hint = '  <<LIKE COUNT — opens likes list, NOT a like button>>'
        return f'[{self.idx}] {kind}{lab}{chk}{hint}'


class Perception:
    """One snapshot of the screen."""

    def __init__(self, xml, current_pkg, elements, screen_size, texts=None):
        self.xml = xml
        self.current_pkg = current_pkg
        self.elements = elements           # list[Element]
        self.screen_size = screen_size     # (w, h)
        self.texts = texts or []           # visible non-interactive text snippets
        self._hash = hashlib.md5((xml or '').encode('utf-8', 'ignore')).hexdigest()

    @property
    def state_hash(self):
        """Stable id of the screen — used to detect 'nothing changed' / stuck."""
        return self._hash

    def is_sparse(self):
        """Few interactive elements but a real screen -> likely Compose/WebView
        -> we should attach a vision screenshot."""
        return len(self.elements) < 3

    def by_idx(self, idx):
        for e in self.elements:
            if e.idx == idx:
                return e
        return None

    def all_text(self):
        return ' '.join(
            (e.label for e in self.elements if e.label)
        ).lower()

    def to_prompt(self, max_elems=60):
        """Compact text the LLM reads to choose an action."""
        lines = [f'Screen of app: {self.current_pkg}',
                 f'Size: {self.screen_size[0]}x{self.screen_size[1]}',
                 'Interactive elements:']
        for e in self.elements[:max_elems]:
            lines.append('  ' + e.describe())
        if not self.elements:
            lines.append('  (none detected — use the screenshot + tap_xy)')
        if self.texts:
            lines.append('Visible text on screen (read-only, for context — '
                         'e.g. post captions, names, codes, messages):')
            for t in self.texts[:18]:
                lines.append('  • ' + t)
        return '\n'.join(lines)


def perceive(device):
    """Capture the current screen as a Perception. `device` is a u2 device."""
    try:
        xml = device.dump_hierarchy()
    except Exception:
        xml = ''
    try:
        cur = device.app_current()
        pkg = cur.get('package', '') if isinstance(cur, dict) else ''
    except Exception:
        pkg = ''
    try:
        w, h = device.window_size()
    except Exception:
        w, h = (1080, 1920)

    elements = []
    texts = []
    seen_text = set()
    if xml:
        try:
            root = ET.fromstring(xml)
            idx = 0
            for node in root.iter('node'):
                a = node.attrib
                if _is_interactive(a):
                    npkg = a.get('package', '')
                    # drop status-bar / nav-bar / edge-panel buttons (systemui) so
                    # the model doesn't mis-tap Recents/Back/Home/Edge panels.
                    # Keep permission dialogs (different package) — those are real.
                    if (npkg.startswith('com.android.systemui')
                            or 'cocktailbar' in npkg):
                        continue
                    b = _parse_bounds(a.get('bounds'))
                    if not b or (b[2] - b[0]) < 2 or (b[3] - b[1]) < 2:
                        continue
                    elements.append(Element(idx, a, b))
                    idx += 1
                else:
                    # non-interactive but visible text (captions, names, codes,
                    # error/info messages) -> context for the model to reason on.
                    # SKIP system-UI text (status bar, notifications, nav, edge
                    # panels) — it made the model think a notification shade was
                    # open and press BACK, exiting the flow.
                    npkg = a.get('package', '')
                    if npkg and (npkg.startswith('com.android.systemui')
                                 or npkg.startswith('com.samsung.android.app')
                                 or (pkg and npkg != pkg)):
                        continue
                    for k in ('text', 'content-desc'):
                        v = (a.get(k) or '').strip()
                        if 1 < len(v) <= 120 and v.lower() not in seen_text:
                            seen_text.add(v.lower())
                            texts.append(v)
                            break
        except ET.ParseError:
            pass
    return Perception(xml, pkg, elements, (w, h), texts=texts)


def grab_png(device):
    """Robust screenshot as valid PNG bytes. adb `exec-out screencap -p` is the
    most reliable (u2's screenshot(format='raw') returned non-PNG/black on some
    devices). Falls back to u2 PIL screenshot. Returns None on failure."""
    serial = getattr(device, 'serial', None)
    if serial:
        try:
            import subprocess
            out = subprocess.run(['adb', '-s', serial, 'exec-out', 'screencap', '-p'],
                                 capture_output=True, timeout=15)
            data = out.stdout
            if out.returncode == 0 and data[:8] == b'\x89PNG\r\n\x1a\n':
                return data
        except Exception:
            pass
    try:
        im = device.screenshot()  # u2 default = PIL.Image
        buf = io.BytesIO()
        im.save(buf, format='PNG')
        return buf.getvalue()
    except Exception:
        return None


def set_of_marks(device, perception):
    """Render the screenshot with numbered boxes over each interactive element
    (Set-of-Marks). Returns PNG bytes, or None if Pillow/screenshot unavailable.
    A vision model then just picks a number instead of guessing pixels."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return None
    png = grab_png(device)
    if not png:
        return None
    try:
        img = Image.open(io.BytesIO(png)).convert('RGB')
    except Exception:
        return None

    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype('arial.ttf', 28)
    except Exception:
        font = ImageFont.load_default()

    for e in perception.elements:
        x1, y1, x2, y2 = e.bounds
        color = (255, 64, 64) if e.editable else (64, 160, 255)
        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
        tag = str(e.idx)
        tw = draw.textlength(tag, font=font) if hasattr(draw, 'textlength') else 14
        draw.rectangle([x1, y1, x1 + tw + 8, y1 + 30], fill=color)
        draw.text((x1 + 4, y1 + 2), tag, fill=(0, 0, 0), font=font)

    out = io.BytesIO()
    img.save(out, format='PNG')
    return out.getvalue()
