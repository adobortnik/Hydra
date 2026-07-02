"""
cloudphone_routes.py — live multi-device viewer/controller that bridges the
browser to the CC智控 (CC Smart Control / "cloudphone") app's LOCAL WebSocket
API (ws://127.0.0.1:33332). The browser can't reach that local socket (it's on
the farm PC, the operator is remote via Cloudflare), so Hydra relays:

    browser  ──HTTP/JSON──►  Hydra (this blueprint)  ──WS──►  cloudphone (127.0.0.1:33332)

cloudphone API is request/response JSON. Screens are JPEG base64 (poll-based —
no push stream, so we poll getscreen). One `getscreen` with serial:[] returns
EVERY device's frame in a single call → cheap grid. Control = mouseevents
(normalized 0–1 coords) / textinput / adbcmd (keyevents).

⚠️ HARD-WON LESSONS (2026-06-29):
- `getscreen` REQUIRES `data.path` (a Windows dir) even for action 0 (base64
  return). Omitting it CRASHES the whole cloudphone app. Always send it.
- The app dislikes rapid reconnects (refuses new sockets). We keep ONE
  persistent connection and multiplex requests by `id` instead of connect-per-call.

Routes:
  GET  /cloudphone                         -> the page
  GET  /api/cloudphone/devices             -> device list (merged with Hydra names/groups)
  POST /api/cloudphone/screens             -> {serial: jpeg_b64} for given serials (or all)
  POST /api/cloudphone/tap                 -> {serial,x,y} normalized press+release
  POST /api/cloudphone/swipe               -> {serial,x1,y1,x2,y2}
  POST /api/cloudphone/text                -> {serial,text}
  POST /api/cloudphone/key                 -> {serial,key} (back/home/recents/enter/backspace)
"""

import asyncio
import json
import os
import sqlite3
import sys
import threading
import uuid

from flask import Blueprint, jsonify, render_template, request

cloudphone_bp = Blueprint('cloudphone', __name__)

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)
_DB = os.path.join(_BASE, 'db', 'phone_farm.db')

CP_WS_URL = os.environ.get('CLOUDPHONE_WS', 'ws://127.0.0.1:33332/')
# getscreen needs a (required) save dir even for base64 action; must exist.
CP_SCREEN_PATH = os.environ.get('CLOUDPHONE_SCREEN_PATH', 'C:\\Windows\\Temp\\')

# Android keyevent codes for the on-screen nav buttons
_KEYMAP = {'back': 4, 'home': 3, 'recents': 187, 'enter': 66,
           'backspace': 67, 'power': 26, 'volup': 24, 'voldown': 25}


# ── Persistent WebSocket bridge (one connection, multiplexed by id) ───────
class _CloudphoneClient:
    """Keeps a single long-lived WS connection to cloudphone, dispatched on its
    own asyncio loop in a background thread. Sync callers use request()/
    request_seq(); responses are routed back by the echoed `id`. Reconnects
    lazily after a drop. Gentle on the app (no reconnect storms)."""

    def __init__(self, url):
        self.url = url
        self.loop = asyncio.new_event_loop()
        self.ws = None
        self.pending = {}
        self._connect_lock = None  # created on the loop
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self._connect_lock = asyncio.Lock()
        self.loop.run_forever()

    async def _ensure(self):
        if self.ws is not None:
            return
        async with self._connect_lock:
            if self.ws is not None:
                return
            import websockets
            self.ws = await websockets.connect(self.url, max_size=None,
                                               open_timeout=15, ping_interval=None)
            self.loop.create_task(self._reader())

    async def _reader(self):
        try:
            async for raw in self.ws:
                try:
                    msg = json.loads(raw if isinstance(raw, str)
                                     else raw.decode('utf-8', 'replace'))
                except Exception:
                    continue
                fut = self.pending.pop(msg.get('id'), None)
                if fut and not fut.done():
                    fut.set_result(msg)
        except Exception:
            pass
        finally:
            self.ws = None
            for fut in list(self.pending.values()):
                if not fut.done():
                    fut.set_exception(ConnectionError('cloudphone connection closed'))
            self.pending.clear()

    async def _do(self, payloads, timeout, gap):
        await self._ensure()
        out = []
        for p in payloads:
            p.setdefault('id', uuid.uuid4().hex[:10])
            fut = self.loop.create_future()
            self.pending[p['id']] = fut
            try:
                await self.ws.send(json.dumps(p))
                out.append(await asyncio.wait_for(fut, timeout=timeout))
            except Exception:
                self.pending.pop(p['id'], None)
                out.append(None)
            if gap:
                await asyncio.sleep(gap)
        return out

    def request(self, payload, timeout=30):
        fut = asyncio.run_coroutine_threadsafe(
            self._do([payload], timeout, 0.0), self.loop)
        res = fut.result(timeout=timeout + 5)
        return res[0] if res else None

    def request_seq(self, payloads, timeout=15, gap=0.0):
        fut = asyncio.run_coroutine_threadsafe(
            self._do(payloads, timeout, gap), self.loop)
        return fut.result(timeout=timeout * max(1, len(payloads)) + 5)


_client = _CloudphoneClient(CP_WS_URL)


def _to_db_serial(s):
    return (s or '').replace(':', '_')


def _norm(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, v))


# ── Routes ───────────────────────────────────────────────────────────────
@cloudphone_bp.route('/cloudphone')
def page():
    return render_template('cloudphone.html')


# Port where ws-scrcpy-web (native H.264 mirror) listens on the farm PC.
WS_SCRCPY_PORT = int(os.environ.get('WS_SCRCPY_PORT', '8000'))


@cloudphone_bp.route('/cloudphone-mirror')
def mirror_page():
    """Alternative live view: native H.264 mirroring via ws-scrcpy-web (smooth +
    sharp + control), embedded. Kept separate from /cloudphone (getscreen) so we
    don't lose that solution. ws-scrcpy runs locally on the farm PC :8000."""
    return render_template('cloudphone_mirror.html', ws_port=WS_SCRCPY_PORT)


@cloudphone_bp.route('/api/cloudphone/devices')
def devices():
    """cloudphone's connected devices, enriched with Hydra device_name + group
    (so we can label and filter by group, e.g. 'jagger'). Serials may be IP:port
    or USB serials; we match Hydra rows by the IP form when possible."""
    try:
        res = _client.request({'type': 'list'}, timeout=15)
    except Exception as e:
        return jsonify({'success': False, 'error': 'cloudphone not reachable: %s' % e,
                        'devices': [], 'groups': []}), 200
    if not res or res.get('state') != 0:
        return jsonify({'success': False,
                        'error': (res or {}).get('message') or 'no response',
                        'devices': [], 'groups': []}), 200
    cp_serials = res.get('data') or []

    meta = {}
    try:
        c = sqlite3.connect(_DB)
        c.row_factory = sqlite3.Row
        for r in c.execute("SELECT device_serial, device_name, device_group FROM devices"):
            meta[r['device_serial']] = (r['device_name'], r['device_group'])
        c.close()
    except Exception:
        pass

    out, groups = [], set()
    for cps in cp_serials:
        name, group = meta.get(_to_db_serial(cps), (None, None))
        if group:
            groups.add(group)
        out.append({'serial': cps, 'db_serial': _to_db_serial(cps),
                    'name': name or cps, 'group': group or ''})
    out.sort(key=lambda d: (d['group'] or 'zzz', d['name']))
    return jsonify({'success': True, 'devices': out, 'groups': sorted(groups)})


@cloudphone_bp.route('/api/cloudphone/screens', methods=['POST'])
def screens():
    """One getscreen call -> JPEG base64 for the requested serials (or ALL when
    none given). Returns {serial: b64}. data.path is REQUIRED by cloudphone even
    for base64 (action 0) — omitting it crashes the app."""
    d = request.get_json() or {}
    serials = d.get('serials') or []   # cloudphone serials; [] = all
    # action 0 = ~180x360 thumbnail (tiny, fast) for the grid; action 2 = full
    # original resolution (big, ~3.5MB) for an HD snapshot in the detail view.
    action = 2 if d.get('hd') else 0
    payload = {'type': 'getscreen', 'serial': serials, 'action': action,
               'data': {'path': CP_SCREEN_PATH}}
    try:
        res = _client.request(payload, timeout=30)
    except Exception as e:
        return jsonify({'success': False, 'error': 'cloudphone not reachable: %s' % e}), 200
    if not res or res.get('state') != 0:
        return jsonify({'success': False,
                        'error': (res or {}).get('message') or 'no response'}), 200
    return jsonify({'success': True, 'frames': res.get('data') or {}})


@cloudphone_bp.route('/api/cloudphone/stream/<path:serial>')
def stream(serial):
    """MJPEG stream of ONE device — much smoother than polling getscreen per
    frame: one open HTTP connection, frames pushed as fast as cloudphone serves
    them, JPEG decoded from base64 server-side (no +33% base64 to the browser).
    <img src> consumes it directly. ?hd=1 = original quality (action 2)."""
    import base64
    import io
    import time
    from flask import Response
    hd = request.args.get('hd') == '1'
    # FAST = action 0: tiny ~180×360 thumbnail served from cloudphone's internal
    #   buffer ~instantly (≈unlimited fps) → smooth 25fps, but low-res.
    # HD   = action 2: full-resolution PNG (~2-3MB) captured on demand at only
    #   ~0.7-2.5 fps. We DOWNSCALE it server-side to a crisp width + JPEG (≈80KB)
    #   so it's sharp AND light enough to stream smoothly over the network — as
    #   fast as the API's capture rate allows (the real ceiling for sharp).
    action = 2 if hd else 0
    try:
        fps = float(request.args.get('fps', 5 if hd else 25))
    except ValueError:
        fps = 5.0 if hd else 25.0
    target_dt = 1.0 / max(0.5, min(40.0, fps))
    try:
        maxw = max(240, min(1080, int(request.args.get('w', 720))))
    except ValueError:
        maxw = 720
    # FAST sharpen: the thumbnail is a tiny ~200×360 JPEG; the browser just
    # blur-upscales it. We upscale server-side with Lanczos + an unsharp mask so
    # it LOOKS markedly sharper (less blocky) — no real detail added, but the
    # perceived pixelation drops a lot. Cheap (~1-2ms/frame) so 25fps holds.
    sharpen = request.args.get('sharpen', '1') != '0'
    try:
        up = max(1.0, min(3.0, float(request.args.get('up', 2.0))))
    except ValueError:
        up = 2.0

    def _shrink(raw):
        try:
            from PIL import Image
            im = Image.open(io.BytesIO(raw))
            if im.width > maxw:
                im.thumbnail((maxw, maxw * 4), Image.LANCZOS)
            out = io.BytesIO()
            im.convert('RGB').save(out, 'JPEG', quality=74)
            return out.getvalue()
        except Exception:
            return raw

    def _enhance(raw):
        try:
            from PIL import Image, ImageFilter
            im = Image.open(io.BytesIO(raw)).convert('RGB')
            if up > 1.01:
                im = im.resize((int(im.width * up), int(im.height * up)), Image.LANCZOS)
            im = im.filter(ImageFilter.UnsharpMask(radius=1.4, percent=115, threshold=2))
            out = io.BytesIO()
            im.save(out, 'JPEG', quality=84)
            return out.getvalue()
        except Exception:
            return raw

    def gen():
        miss = 0
        while True:
            t0 = time.time()
            try:
                res = _client.request({'type': 'getscreen', 'serial': [serial],
                                       'action': action, 'data': {'path': CP_SCREEN_PATH}},
                                      timeout=20)
            except Exception:
                break
            data = (res or {}).get('data') if res else None
            b64 = None
            if isinstance(data, dict) and data:
                b64 = data.get(serial) or next(iter(data.values()))
            if not b64:
                miss += 1
                if miss > 20:
                    break
                time.sleep(0.1)
                continue
            miss = 0
            try:
                jpg = base64.b64decode(b64)
            except Exception:
                jpg = None
            if jpg:
                if hd:
                    jpg = _shrink(jpg)
                elif sharpen:
                    jpg = _enhance(jpg)
            if jpg:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '
                       + str(len(jpg)).encode() + b'\r\n\r\n' + jpg + b'\r\n')
            dt = time.time() - t0
            if dt < target_dt:
                time.sleep(target_dt - dt)

    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')


_CP_ADB = os.environ.get('CLOUDPHONE_ADB', r'C:\Program Files (x86)\CloudPhone\adb.exe')
import re as _re
_SERIAL_OK = _re.compile(r'^[A-Za-z0-9_.:\-]{4,64}$')
_SCRCPY_JAR = os.environ.get('SCRCPY_JAR',
                             os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scrcpy-server.jar'))
_SCRCPY_VER = os.environ.get('SCRCPY_VERSION', '2.4')


@cloudphone_bp.route('/api/cloudphone/h264/<path:serial>')
def h264(serial):
    """NATIVE-quality mirror: adb screenrecord streams H.264 (full motion, full
    res), we decode it with PyAV and re-emit as MJPEG. Smooth + sharp — far beyond
    what getscreen can do — over our own Flask pipeline (works via Cloudflare, no
    ws-scrcpy). Control still goes through the cloudphone WS endpoints.
    ?size=720x1560 (downscale on device) · ?br=6000000 (bit-rate) · ?q=72 (jpeg)."""
    import io
    import subprocess
    import av
    from PIL import Image  # noqa: F401 (PyAV frame.to_image needs Pillow)
    from flask import Response

    if not _SERIAL_OK.match(serial or ''):
        return jsonify({'error': 'bad serial'}), 400
    size = request.args.get('size', '720x1560')
    if not _re.match(r'^\d{2,5}x\d{2,5}$', size):
        size = '720x1560'
    br = request.args.get('br', '6000000')
    if not br.isdigit():
        br = '6000000'
    try:
        q = max(40, min(92, int(request.args.get('q', 72))))
    except ValueError:
        q = 72

    def gen():
        while True:                       # screenrecord caps at 180s → restart
            p = subprocess.Popen(
                [_CP_ADB, '-s', serial, 'exec-out', 'screenrecord',
                 '--output-format=h264', '--size', size, '--bit-rate', br,
                 '--time-limit', '170', '-'],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
            codec = av.CodecContext.create('h264', 'r')
            try:
                while True:
                    chunk = p.stdout.read(65536)
                    if not chunk:
                        break
                    for pkt in codec.parse(chunk):
                        for fr in codec.decode(pkt):
                            buf = io.BytesIO()
                            fr.to_image().save(buf, 'JPEG', quality=q)
                            jpg = buf.getvalue()
                            yield (b'--frame\r\nContent-Type: image/jpeg\r\n'
                                   b'Content-Length: ' + str(len(jpg)).encode()
                                   + b'\r\n\r\n' + jpg + b'\r\n')
            except (GeneratorExit, Exception):
                try:
                    p.kill()
                except Exception:
                    pass
                return
            finally:
                try:
                    p.kill()
                except Exception:
                    pass

    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')


@cloudphone_bp.route('/api/cloudphone/scrcpy/<path:serial>')
def scrcpy_stream(serial):
    """TRUE scrcpy-smooth mirror: run scrcpy-server on the device (real-time,
    low-latency H.264 — ~30fps, ~140ms first frame) and decode it with PyAV →
    MJPEG. This is what makes scrcpy fluid where getscreen/screenrecord lag
    (screenrecord buffers; scrcpy's server streams frames immediately). Control
    still goes through the cloudphone WS. ?size=720 ?q=75 ?br=8000000 ?fps=30."""
    import io
    import random
    import select
    import socket
    import struct
    import subprocess
    import time
    import av
    from flask import Response

    if not _SERIAL_OK.match(serial or ''):
        return jsonify({'error': 'bad serial'}), 400
    try:
        max_size = max(320, min(1280, int(request.args.get('size', 720))))
    except ValueError:
        max_size = 720
    try:
        q = max(40, min(92, int(request.args.get('q', 75))))
    except ValueError:
        q = 75
    br = request.args.get('br', '8000000')
    if not br.isdigit():
        br = '8000000'
    fps = request.args.get('fps', '30')
    if not fps.isdigit():
        fps = '30'
    scid = format(random.randint(0, 0x7fffffff), '08x')

    def gen():
        srv = sock = None
        port = None
        try:
            subprocess.run([_CP_ADB, '-s', serial, 'push', _SCRCPY_JAR,
                            '/data/local/tmp/scrcpy-server.jar'],
                           capture_output=True, timeout=25)
            r = subprocess.run([_CP_ADB, '-s', serial, 'forward', 'tcp:0',
                                f'localabstract:scrcpy_{scid}'],
                               capture_output=True, text=True, timeout=10)
            port = int((r.stdout or '').strip() or 0)
            if not port:
                return
            srv = subprocess.Popen(
                [_CP_ADB, '-s', serial, 'shell',
                 'CLASSPATH=/data/local/tmp/scrcpy-server.jar', 'app_process', '/',
                 'com.genymobile.scrcpy.Server', _SCRCPY_VER,
                 f'scid={scid}', 'log_level=error', 'audio=false', 'control=false',
                 'video=true', f'max_size={max_size}', f'video_bit_rate={br}',
                 f'max_fps={fps}', 'tunnel_forward=true'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # connect once the server has bound its abstract socket
            for _ in range(120):
                try:
                    s = socket.create_connection(('127.0.0.1', port), timeout=1)
                    s.settimeout(6)
                    if s.recv(1):          # dummy byte → server is up
                        sock = s
                        break
                    s.close()
                except Exception:
                    pass
                time.sleep(0.1)
            if not sock:
                return

            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            except Exception:
                pass

            class _Idle(Exception):
                pass

            def rx(n, idle_ok=False):
                b = b''
                while len(b) < n:
                    try:
                        c = sock.recv(n - len(b))
                    except socket.timeout:
                        if idle_ok and not b:
                            raise _Idle        # timed out at a clean frame boundary
                        continue               # mid-frame → keep waiting
                    if not c:
                        raise EOFError
                    b += c
                return b

            rx(64)   # device name
            rx(12)   # codec id + width + height
            sock.settimeout(2.0)   # short → lets us detect an idle screen for keepalive
            codec = av.CodecContext.create('h264', 'r')
            # LOW LATENCY: single-thread (no frame-threading pipeline delay) +
            # AV_CODEC_FLAG_LOW_DELAY (emit each frame immediately, no reorder buffer).
            try:
                codec.thread_count = 1
            except Exception:
                pass
            try:
                codec.flags |= 0x00080000   # AV_CODEC_FLAG_LOW_DELAY
            except Exception:
                pass

            def _part(jpg):
                return (b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '
                        + str(len(jpg)).encode() + b'\r\n\r\n' + jpg + b'\r\n')

            def _decode(data):
                last = None
                for pkt in codec.parse(data):
                    for fr in codec.decode(pkt):
                        last = fr
                return last

            last_jpg = None
            while True:
                # Read the next frame header. If the screen is idle (scrcpy sends
                # nothing while nothing changes) we time out at a clean boundary →
                # RESEND the last frame so the stream never goes silent. Silence is
                # what let a proxy/adb idle-timeout kill the connection → the
                # "frozen, won't refresh" bug. Keepalive keeps it warm so new frames
                # flow the instant activity resumes.
                try:
                    _pts, size = struct.unpack('>QI', rx(12, idle_ok=True))
                except _Idle:
                    if last_jpg:
                        yield _part(last_jpg)
                    continue
                latest = _decode(rx(size))
                # DROP-TO-LATEST: drain any already-buffered frames (slow client/link)
                # and keep only the freshest → latency stays ~1 frame, no pile-up.
                drained = 0
                while drained < 120 and select.select([sock], [], [], 0)[0]:
                    try:
                        _p, sz = struct.unpack('>QI', rx(12))
                        fr = _decode(rx(sz))
                        if fr is not None:
                            latest = fr
                    except Exception:
                        break
                    drained += 1
                if latest is not None:
                    buf = io.BytesIO()
                    latest.to_image().save(buf, 'JPEG', quality=q)
                    last_jpg = buf.getvalue()
                    yield _part(last_jpg)
        except (GeneratorExit, Exception):
            pass
        finally:
            try:
                if sock:
                    sock.close()
            except Exception:
                pass
            try:
                if srv:
                    srv.kill()
            except Exception:
                pass
            try:
                if port:
                    subprocess.run([_CP_ADB, '-s', serial, 'forward', '--remove',
                                    f'tcp:{port}'], capture_output=True, timeout=5)
            except Exception:
                pass

    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')


@cloudphone_bp.route('/api/cloudphone/tap', methods=['POST'])
def tap():
    d = request.get_json() or {}
    s = d.get('serial')
    if not s:
        return jsonify({'success': False, 'error': 'serial required'}), 400
    x, y = _norm(d.get('x')), _norm(d.get('y'))
    _client.request_seq([
        {'type': 'mouseevents', 'serial': [s], 'action': 0, 'data': {'x': x, 'y': y}},
        {'type': 'mouseevents', 'serial': [s], 'action': 1, 'data': {'x': x, 'y': y}},
    ], timeout=8, gap=0.04)
    return jsonify({'success': True})


@cloudphone_bp.route('/api/cloudphone/swipe', methods=['POST'])
def swipe():
    d = request.get_json() or {}
    s = d.get('serial')
    if not s:
        return jsonify({'success': False, 'error': 'serial required'}), 400
    x1, y1 = _norm(d.get('x1')), _norm(d.get('y1'))
    x2, y2 = _norm(d.get('x2')), _norm(d.get('y2'))
    steps = max(2, min(12, int(d.get('steps') or 6)))
    seq = [{'type': 'mouseevents', 'serial': [s], 'action': 0, 'data': {'x': x1, 'y': y1}}]
    for i in range(1, steps + 1):
        t = i / steps
        seq.append({'type': 'mouseevents', 'serial': [s], 'action': 2,
                    'data': {'x': x1 + (x2 - x1) * t, 'y': y1 + (y2 - y1) * t}})
    seq.append({'type': 'mouseevents', 'serial': [s], 'action': 1, 'data': {'x': x2, 'y': y2}})
    _client.request_seq(seq, timeout=8, gap=0.02)
    return jsonify({'success': True})


@cloudphone_bp.route('/api/cloudphone/text', methods=['POST'])
def text():
    d = request.get_json() or {}
    s = d.get('serial')
    txt = d.get('text', '')
    if not s:
        return jsonify({'success': False, 'error': 'serial required'}), 400
    res = _client.request({'type': 'textinput', 'serial': [s], 'data': {'Text': txt}}, timeout=10)
    return jsonify({'success': bool(res and res.get('state') == 0),
                    'error': (res or {}).get('message')})


@cloudphone_bp.route('/api/cloudphone/key', methods=['POST'])
def key():
    """Nav buttons via adbcmd `input keyevent <code>` (deterministic Android codes)."""
    d = request.get_json() or {}
    s = d.get('serial')
    k = (d.get('key') or '').lower()
    if not s or k not in _KEYMAP:
        return jsonify({'success': False, 'error': 'serial + valid key required'}), 400
    res = _client.request({'type': 'adbcmd', 'serial': [s],
                           'data': {'cmd': 'input keyevent %d' % _KEYMAP[k]}}, timeout=10)
    return jsonify({'success': bool(res and res.get('state') == 0),
                    'error': (res or {}).get('message')})
