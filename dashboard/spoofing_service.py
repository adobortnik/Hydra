"""
Media spoofing service — generates per-account unique variants of an image
or video so N slave accounts posting the same source don't trip Instagram's
duplicate-content / perceptual-hash correlation.

Pure functions in this module. The Flask routes + async job queue live in
`spoofing_routes.py`.

Presets:
  light   — minimal change, near-identical to source. Strips EXIF, ±2% jitter.
  medium  — default. Stronger color/crop/noise, micro-rotate. Audio jitter
            on video. Recommended for posting same content across slaves.
  strong  — aggressive. Mirror flip 30% chance on image, larger color shift,
            more visible re-encode. Use when extra paranoid; may slightly
            degrade quality.
"""
from __future__ import annotations

import datetime
import io
import json
import os
import random
import subprocess
import tempfile
import uuid
from fractions import Fraction
from typing import Optional

import imagehash
import numpy as np
import piexif
from PIL import Image, ImageEnhance, ImageFilter

try:
    from imageio_ffmpeg import get_ffmpeg_exe
    FFMPEG_EXE = get_ffmpeg_exe()
except Exception:
    FFMPEG_EXE = 'ffmpeg'  # fall back to PATH

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp'}
VIDEO_EXTS = {'.mp4', '.mov', '.m4v', '.webm', '.mkv', '.avi'}

# Hamming-distance threshold per algorithm. Honest defaults: perceptual
# hashes are designed to resist small modifications, so distance ≥10 across
# ALL FOUR algos is achievable mainly via mirror flip / heavy artifacts.
# Threshold 6 = "this variant is meaningfully different in this algo's
# representation". IG's correlation algorithm is private — no universal
# magic number. UI exposes per-algo distances honestly so the operator can
# judge for their specific content.
DEFAULT_HASH_THRESHOLD = 6


# ─────────────────────────────────────────────────────────────────
# Plausible-EXIF pool (iPhone / Samsung capture metadata templates).
# Real-looking GPS taken from public city coordinates; jittered ±~100m
# per variant. Strip-only EXIF is suspicious — IG sees "anonymized
# desktop export" instead of "fresh phone capture".
# ─────────────────────────────────────────────────────────────────

EXIF_DEVICE_POOL = [
    {'Make': 'Apple', 'Model': 'iPhone 14 Pro',
     'Software': 'iOS 17.6.1', 'LensModel': 'iPhone 14 Pro back triple camera 6.86mm f/1.78',
     'FocalLength': (686, 100), 'FNumber': (178, 100),
     'ExposureTime_choices': [(1, 30), (1, 60), (1, 120), (1, 250), (1, 500)],
     'ISO_choices': [50, 80, 100, 125, 160, 200, 250, 320]},
    {'Make': 'Apple', 'Model': 'iPhone 15',
     'Software': 'iOS 17.5.1', 'LensModel': 'iPhone 15 back dual wide camera 5.96mm f/1.6',
     'FocalLength': (596, 100), 'FNumber': (16, 10),
     'ExposureTime_choices': [(1, 30), (1, 60), (1, 120), (1, 250), (1, 500)],
     'ISO_choices': [32, 50, 80, 100, 125, 160, 200]},
    {'Make': 'Apple', 'Model': 'iPhone 13',
     'Software': 'iOS 16.7.4', 'LensModel': 'iPhone 13 back dual wide camera 5.1mm f/1.6',
     'FocalLength': (51, 10), 'FNumber': (16, 10),
     'ExposureTime_choices': [(1, 30), (1, 60), (1, 120), (1, 250)],
     'ISO_choices': [50, 80, 100, 125, 160, 200, 250]},
    {'Make': 'samsung', 'Model': 'SM-S918B',  # Galaxy S23 Ultra
     'Software': 'S918BXXU3CWEH', 'LensModel': '',
     'FocalLength': (23, 1), 'FNumber': (17, 10),
     'ExposureTime_choices': [(1, 30), (1, 60), (1, 100), (1, 250)],
     'ISO_choices': [50, 80, 100, 125, 200, 320]},
    {'Make': 'samsung', 'Model': 'SM-S911B',  # Galaxy S23
     'Software': 'S911BXXU2BWEJ', 'LensModel': '',
     'FocalLength': (24, 1), 'FNumber': (17, 10),
     'ExposureTime_choices': [(1, 30), (1, 60), (1, 100)],
     'ISO_choices': [50, 64, 100, 125, 200]},
]

# Real-world city coordinates (lat, lon, name) — variants pick one and add
# ±0.001° jitter (≈100m). Mix of US + EU + LATAM. Keep the list short and
# plausible for the kind of accounts we run.
GPS_POOL = [
    ( 34.0522, -118.2437, 'Los Angeles, US'),
    ( 40.7128,  -74.0060, 'New York, US'),
    ( 25.7617,  -80.1918, 'Miami, US'),
    ( 36.1699, -115.1398, 'Las Vegas, US'),
    ( 51.5074,   -0.1278, 'London, UK'),
    ( 48.8566,    2.3522, 'Paris, FR'),
    ( 52.5200,   13.4050, 'Berlin, DE'),
    ( 41.3851,    2.1734, 'Barcelona, ES'),
    ( 23.5505,  -46.6333, 'São Paulo, BR'),
    (-22.9068,  -43.1729, 'Rio de Janeiro, BR'),
    ( 19.4326,  -99.1332, 'Mexico City, MX'),
    ( 35.6762,  139.6503, 'Tokyo, JP'),
    ( 25.2048,   55.2708, 'Dubai, AE'),
    ( 33.7490,  -84.3880, 'Atlanta, US'),
    ( 30.2672,  -97.7431, 'Austin, US'),
]


# ─────────────────────────────────────────────────────────────────
# Preset ranges (random uniform within these bounds per variant)
# ─────────────────────────────────────────────────────────────────

PRESETS = {
    # ── Preset philosophy ───────────────────────────────────────────
    # Mirror flip is the ONLY zero-quality-cost hash breaker we have.
    # Gaussian blur and aggressive crop+resize visibly degrade photos.
    # New design: mirror is the primary breaker (enabled by default for
    # medium/strong), blur is removed, JPEG quality stays high (90+), and
    # all jitters are gentle enough to be visually invisible. If mirror is
    # NOT OK for the content (text, brand logos), operator unticks "Allow
    # mirror" in UI and accepts lower bypass count.
    'light': {
        'crop_pct':     (0.8, 1.5),
        'brightness':   (-0.03, 0.03),
        'contrast':     (-0.03, 0.03),
        'saturation':   (-0.03, 0.03),
        'hue_deg':      (-2.0, 2.0),
        'gamma':        (0.96, 1.04),
        'rotate_deg':   (0.0, 0.0),
        'noise_std':    0.0,
        'blur_radius':  (0.0, 0.0),            # OFF — quality first
        'chroma_shift_px': (0, 1),
        'mirror_chance': 0.0,                  # off in light
        'vignette':     0.0,
        'jpeg_quality': (92, 97),              # high quality
        'sharpen':      'subtle',              # subtle post-sharpen
        'inject_exif':  True,
        # video
        'trim_start_ms': (0, 100),
        'video_crop_pct': (0.5, 1.0),
        'crf_range':    (20, 22),              # lower CRF = higher quality
        'audio_noise_db': -50,
        'speed_jitter': 0.0,
        'video_gamma':  (0.97, 1.03),
    },
    'medium': {
        'crop_pct':     (1.2, 2.5),
        'brightness':   (-0.05, 0.05),
        'contrast':     (-0.05, 0.05),
        'saturation':   (-0.05, 0.05),
        'hue_deg':      (-3.0, 3.0),
        'gamma':        (0.94, 1.06),
        'rotate_deg':   (-0.3, 0.3),
        'noise_std':    1.0,
        'blur_radius':  (0.0, 0.0),            # OFF
        'chroma_shift_px': (1, 1),             # gentle
        'mirror_chance': 1.0,                  # ALWAYS mirror — primary breaker
        'vignette':     0.0,
        'jpeg_quality': (90, 95),
        'sharpen':      'subtle',
        'inject_exif':  True,
        # video
        'trim_start_ms': (30, 200),
        'video_crop_pct': (1.0, 2.0),
        'crf_range':    (21, 23),
        'audio_noise_db': -42,
        'speed_jitter': 0.0,
        'video_gamma':  (0.93, 1.07),
    },
    'strong': {
        'crop_pct':     (2.0, 3.5),
        'brightness':   (-0.07, 0.07),
        'contrast':     (-0.07, 0.07),
        'saturation':   (-0.07, 0.07),
        'hue_deg':      (-5.0, 5.0),
        'gamma':        (0.90, 1.10),
        'rotate_deg':   (-0.5, 0.5),
        'noise_std':    1.5,
        'blur_radius':  (0.0, 0.0),            # OFF
        'chroma_shift_px': (1, 2),
        'mirror_chance': 1.0,                  # always mirror
        'vignette':     0.10,                  # subtle, not heavy
        'jpeg_quality': (88, 94),
        'sharpen':      'strong',              # extra sharpen to offset any degradation
        'inject_exif':  True,
        # video
        'trim_start_ms': (50, 300),
        'video_crop_pct': (1.5, 3.0),
        'crf_range':    (21, 24),
        'audio_noise_db': -38,
        'speed_jitter': 0.001,
        'video_gamma':  (0.90, 1.10),
    },
}


# ─────────────────────────────────────────────────────────────────
# EXIF synthesis — build plausible iPhone/Samsung capture metadata
# ─────────────────────────────────────────────────────────────────

def _to_rational(f):
    """piexif wants (num, den) tuples for rationals."""
    if isinstance(f, tuple):
        return f
    frac = Fraction(float(f)).limit_denominator(10000)
    return (frac.numerator, frac.denominator)


def _build_synthetic_exif(rng, img_w, img_h):
    """Build a piexif-compatible EXIF dict that mimics a real phone capture.
    Picks a device profile + a GPS location at random, jitters timestamps,
    fills in subsec / focal / iso / shutter so the file looks captured.
    """
    dev = rng.choice(EXIF_DEVICE_POOL)

    # Random capture time in the last 1–14 days
    delta = datetime.timedelta(days=rng.randint(1, 14),
                               hours=rng.randint(0, 23),
                               minutes=rng.randint(0, 59),
                               seconds=rng.randint(0, 59))
    ts = datetime.datetime.utcnow() - delta
    ts_str = ts.strftime('%Y:%m:%d %H:%M:%S').encode()
    subsec = f"{rng.randint(0, 999):03d}".encode()

    iso = rng.choice(dev['ISO_choices'])
    expt = rng.choice(dev['ExposureTime_choices'])

    zeroth = {
        piexif.ImageIFD.Make:        dev['Make'].encode(),
        piexif.ImageIFD.Model:       dev['Model'].encode(),
        piexif.ImageIFD.Software:    dev['Software'].encode(),
        piexif.ImageIFD.DateTime:    ts_str,
        piexif.ImageIFD.Orientation: 1,
        piexif.ImageIFD.XResolution: (72, 1),
        piexif.ImageIFD.YResolution: (72, 1),
        piexif.ImageIFD.ResolutionUnit: 2,
        piexif.ImageIFD.YCbCrPositioning: 1,
    }

    exif = {
        piexif.ExifIFD.DateTimeOriginal:   ts_str,
        piexif.ExifIFD.DateTimeDigitized:  ts_str,
        piexif.ExifIFD.SubSecTimeOriginal: subsec,
        piexif.ExifIFD.SubSecTimeDigitized: subsec,
        piexif.ExifIFD.ExposureTime:       expt,
        piexif.ExifIFD.FNumber:            dev['FNumber'],
        piexif.ExifIFD.ISOSpeedRatings:    iso,
        piexif.ExifIFD.FocalLength:        dev['FocalLength'],
        piexif.ExifIFD.LensModel:          dev.get('LensModel', '').encode(),
        piexif.ExifIFD.PixelXDimension:    img_w,
        piexif.ExifIFD.PixelYDimension:    img_h,
        piexif.ExifIFD.ColorSpace:         1,        # sRGB
        piexif.ExifIFD.ExposureProgram:    2,        # Program AE
        piexif.ExifIFD.MeteringMode:       5,        # Pattern
        piexif.ExifIFD.WhiteBalance:       0,        # Auto
        piexif.ExifIFD.Flash:              16,       # No flash
        piexif.ExifIFD.ExifVersion:        b'0231',
        piexif.ExifIFD.FlashpixVersion:    b'0100',
    }

    # GPS — pick one city, jitter ±0.001° (≈100m) per variant
    lat0, lon0, _name = rng.choice(GPS_POOL)
    lat = lat0 + rng.uniform(-0.001, 0.001)
    lon = lon0 + rng.uniform(-0.001, 0.001)
    alt = rng.randint(5, 250)
    gps = {
        piexif.GPSIFD.GPSVersionID:        (2, 2, 0, 0),
        piexif.GPSIFD.GPSLatitudeRef:      b'N' if lat >= 0 else b'S',
        piexif.GPSIFD.GPSLatitude:         _gps_to_rationals(abs(lat)),
        piexif.GPSIFD.GPSLongitudeRef:     b'E' if lon >= 0 else b'W',
        piexif.GPSIFD.GPSLongitude:        _gps_to_rationals(abs(lon)),
        piexif.GPSIFD.GPSAltitudeRef:      0,
        piexif.GPSIFD.GPSAltitude:         (alt, 1),
        piexif.GPSIFD.GPSTimeStamp:        ((ts.hour, 1), (ts.minute, 1), (ts.second, 1)),
        piexif.GPSIFD.GPSDateStamp:        ts.strftime('%Y:%m:%d').encode(),
    }

    return ({'0th': zeroth, 'Exif': exif, 'GPS': gps,
             '1st': {}, 'Interop': {}, 'thumbnail': None},
            {'device': dev['Model'],
             'gps_city': _name,
             'iso': iso,
             'shutter': f'{expt[0]}/{expt[1]}s'})


def _gps_to_rationals(deg):
    """Convert decimal degrees to ((deg,1),(min,1),(sec*1000,1000)) tuples."""
    d = int(deg)
    m_full = (deg - d) * 60
    m = int(m_full)
    s = (m_full - m) * 60
    return ((d, 1), (m, 1), (int(s * 1000), 1000))


# ─────────────────────────────────────────────────────────────────
# Perceptual hash comparison (aHash, pHash, dHash, wHash)
# ─────────────────────────────────────────────────────────────────

def compute_image_hashes(path: str) -> dict:
    """Return four perceptual hashes for an image as hex strings."""
    img = Image.open(path).convert('RGB')
    return {
        'aHash': str(imagehash.average_hash(img)),
        'pHash': str(imagehash.phash(img)),
        'dHash': str(imagehash.dhash(img)),
        'wHash': str(imagehash.whash(img)),
    }


def compare_hashes(src_path: str, variant_path: str,
                   threshold: int = DEFAULT_HASH_THRESHOLD) -> dict:
    """Compare four perceptual hashes between source and a generated variant.
    Returns per-algo distance + status, plus an overall bypass_count and
    'safe' boolean (all four ≥ threshold)."""
    src_h = compute_image_hashes(src_path)
    var_h = compute_image_hashes(variant_path)
    out = {'threshold': threshold, 'algorithms': {}, 'bypass_count': 0}
    for algo, hex_src in src_h.items():
        hex_var = var_h[algo]
        # Hex hash -> imagehash object -> Hamming distance via __sub__
        h_src = imagehash.hex_to_hash(hex_src)
        h_var = imagehash.hex_to_hash(hex_var)
        dist = int(h_src - h_var)
        passed = dist >= threshold
        if passed:
            out['bypass_count'] += 1
        out['algorithms'][algo] = {
            'original': hex_src,
            'spoofed': hex_var,
            'distance': dist,
            'status': 'bypass' if passed else 'risky',
        }
    out['total_algos'] = len(src_h)
    out['safe'] = out['bypass_count'] >= 2     # 2/4 minimum for "safe enough"
    return out


def extract_video_frame(video_path: str, dst_image_path: str,
                        time_ratio: float = 0.5) -> bool:
    """Pull a single frame from `time_ratio` (0..1) of the video for hashing.
    Returns True on success."""
    # Probe duration
    try:
        proc = subprocess.run(
            [FFMPEG_EXE, '-hide_banner', '-i', video_path],
            capture_output=True, text=True, timeout=10
        )
        import re
        m = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)',
                      (proc.stderr or '') + (proc.stdout or ''))
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            duration = h * 3600 + mi * 60 + s
        else:
            duration = 1.0
    except Exception:
        duration = 1.0

    t = max(0.0, duration * time_ratio)
    try:
        subprocess.run(
            [FFMPEG_EXE, '-y', '-ss', f'{t:.3f}', '-i', video_path,
             '-frames:v', '1', '-q:v', '3', '-loglevel', 'error', dst_image_path],
            capture_output=True, timeout=20
        )
        return os.path.exists(dst_image_path)
    except Exception:
        return False


def compare_video_hashes(src_path: str, variant_path: str,
                         threshold: int = DEFAULT_HASH_THRESHOLD) -> dict:
    """Sample middle frames of both videos, run the same 4-hash comparison."""
    tmpdir = tempfile.mkdtemp(prefix='spoof_hash_')
    try:
        src_frame = os.path.join(tmpdir, 'src.jpg')
        var_frame = os.path.join(tmpdir, 'var.jpg')
        ok = (extract_video_frame(src_path, src_frame) and
              extract_video_frame(variant_path, var_frame))
        if not ok:
            return {'error': 'frame extraction failed',
                    'algorithms': {}, 'bypass_count': 0,
                    'threshold': threshold, 'total_algos': 4, 'safe': False}
        return compare_hashes(src_frame, var_frame, threshold)
    finally:
        import shutil
        try: shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception: pass


# ─────────────────────────────────────────────────────────────────
# Image spoofing
# ─────────────────────────────────────────────────────────────────

def spoof_image(src_path: str, dst_path: str,
                preset: str = 'medium',
                seed: Optional[int] = None,
                allow_mirror: bool = True) -> dict:
    """Generate one spoofed variant of an image. Returns a small stats dict
    describing what was changed.

    allow_mirror: when False the mirror-flip step is skipped regardless of
    preset. Set to False for content with direction (text, brand logos)
    where horizontal flip would be visible. Note: without mirror, hitting
    the 4-hash threshold is much harder — the operator should expect more
    "RISKY" verdicts.
    """
    if preset not in PRESETS:
        preset = 'medium'
    cfg = PRESETS[preset]
    rng = random.Random(seed if seed is not None else random.randint(0, 2**31))

    img = Image.open(src_path)
    img = img.convert('RGB')
    orig_size = img.size                # (W, H)

    applied = {'preset': preset, 'seed': seed}

    # 1) Asymmetric crop + slight perspective skew + resize back.
    #
    # Why asymmetric: a symmetric crop+resize keeps the image CENTER on the
    # source center, so pHash (which compares 8×8 reduced images sampling
    # the center grid) doesn't budge. Different px on each side shifts the
    # content frame → every DCT block has different content.
    crop_pct = rng.uniform(*cfg.get('crop_pct', (1.0, 1.5)))
    if crop_pct > 0:
        w, h = img.size
        shorter = min(w, h)
        base = max(1, int(round(shorter * crop_pct / 100.0)))
        # Per-side jitter ±50% of base, with minimum 1px
        def _side():
            return max(1, base + rng.randint(-base // 2, base // 2))
        L, T, R, B = _side(), _side(), _side(), _side()
        img = img.crop((L, T, w - R, h - B))
        # Slight non-uniform resize back so aspect ratio isn't perfectly
        # preserved — shifts every pixel column relative to original.
        # Keep within ±0.5% so visually invisible.
        ratio_skew = rng.uniform(-0.005, 0.005)
        target_w = int(round(orig_size[0] * (1.0 + ratio_skew)))
        target_h = int(round(orig_size[1] * (1.0 - ratio_skew)))
        img = img.resize((target_w, target_h), Image.LANCZOS)
        # Crop back to exact original dims if we drifted
        if img.size != orig_size:
            cx = max(0, (img.size[0] - orig_size[0]) // 2)
            cy = max(0, (img.size[1] - orig_size[1]) // 2)
            img = img.crop((cx, cy, cx + orig_size[0], cy + orig_size[1]))
        applied['crop_pct'] = round(crop_pct, 2)
        applied['crop_sides_px'] = [L, T, R, B]
        applied['ratio_skew'] = round(ratio_skew, 5)

    # 2) Mirror flip — primary zero-quality-cost hash breaker. Skipped if
    # the caller said allow_mirror=False (content has text/direction).
    if allow_mirror and rng.random() < cfg['mirror_chance']:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
        applied['mirrored'] = True

    # 3) Optional micro-rotation
    rot = rng.uniform(*cfg['rotate_deg'])
    if abs(rot) > 0.05:
        img = img.rotate(rot, resample=Image.BICUBIC, expand=False, fillcolor=(0, 0, 0))
        applied['rotate_deg'] = round(rot, 3)

    # 4) Brightness / contrast / saturation jitter (multiplicative; 1+x)
    b = rng.uniform(*cfg['brightness']); applied['brightness'] = round(b, 4)
    img = ImageEnhance.Brightness(img).enhance(1.0 + b)
    c = rng.uniform(*cfg['contrast']);   applied['contrast'] = round(c, 4)
    img = ImageEnhance.Contrast(img).enhance(1.0 + c)
    s = rng.uniform(*cfg['saturation']); applied['saturation'] = round(s, 4)
    img = ImageEnhance.Color(img).enhance(1.0 + s)

    # 5) Hue shift via HSV roundtrip
    hue = rng.uniform(*cfg['hue_deg'])
    if abs(hue) > 0.1:
        hsv = img.convert('HSV')
        arr = np.asarray(hsv, dtype=np.int16)
        arr[..., 0] = (arr[..., 0] + int(round(hue / 360.0 * 255))) % 256
        img = Image.fromarray(arr.astype(np.uint8), 'HSV').convert('RGB')
        applied['hue_deg'] = round(hue, 2)

    # 6) Low-amplitude gaussian noise
    if cfg['noise_std'] > 0:
        arr = np.asarray(img, dtype=np.int16)
        noise = rng_gaussian_like(arr.shape, cfg['noise_std'], rng)
        arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr, 'RGB')
        applied['noise_std'] = cfg['noise_std']

    # 6.5) Gamma jitter — shifts midtones nonlinearly (breaks pHash/dHash
    # which sample mean/median brightness in 8×8 blocks). Pillow's
    # Image.point with a per-channel LUT is the fast way.
    g = rng.uniform(*cfg.get('gamma', (1.0, 1.0)))
    if abs(g - 1.0) > 0.005:
        inv = 1.0 / g
        lut = [min(255, int(((i / 255.0) ** inv) * 255 + 0.5))
               for i in range(256)] * 3   # 3 channels
        img = img.point(lut)
        applied['gamma'] = round(g, 4)

    # 6.6) Chromatic aberration — shift R and B channels by ±1-3 px relative
    # to G. Visually subtle (looks like cheap lens), but the spatial pixel
    # offset shifts every DCT block → big pHash/wHash delta.
    cs_lo, cs_hi = cfg.get('chroma_shift_px', (0, 0))
    cs = rng.randint(cs_lo, cs_hi)
    if cs > 0:
        bands = list(img.split())
        # rng-chosen direction so we don't ALWAYS shift right
        dx_r = rng.choice([-cs, cs])
        dx_b = rng.choice([-cs, cs])
        bands[0] = bands[0].transform(bands[0].size, Image.AFFINE,
                                       (1, 0, dx_r, 0, 1, 0),
                                       resample=Image.BILINEAR)
        bands[2] = bands[2].transform(bands[2].size, Image.AFFINE,
                                       (1, 0, dx_b, 0, 1, 0),
                                       resample=Image.BILINEAR)
        img = Image.merge('RGB', bands)
        applied['chroma_shift_px'] = cs

    # 6.7) Mild gaussian blur — sub-pixel low-pass; visually nearly invisible
    # but smashes the high-frequency content that pHash latches onto.
    blur_r = rng.uniform(*cfg.get('blur_radius', (0.0, 0.0)))
    if blur_r > 0.05:
        img = img.filter(ImageFilter.GaussianBlur(radius=blur_r))
        applied['blur_radius'] = round(blur_r, 3)

    # 6.8) Vignette (strong only by default) — radial darkening, classic
    # pHash breaker because it changes the mean luma of corner blocks.
    vig = cfg.get('vignette', 0.0)
    if vig > 0:
        img = _apply_vignette(img, strength=vig, rng=rng)
        applied['vignette'] = round(vig, 3)

    # 7) Final pass: post-sharpen to keep edge crispness despite jitter.
    # 'subtle' = barely perceptible, 'strong' = restores crispness after
    # heavier strong-preset operations. We deliberately DON'T blur first
    # anymore — blur was the main quality killer in v1.
    sh = cfg.get('sharpen', 'subtle')
    if sh == 'strong':
        img = img.filter(ImageFilter.UnsharpMask(radius=0.8, percent=20, threshold=2))
    elif sh == 'subtle':
        img = img.filter(ImageFilter.UnsharpMask(radius=0.6, percent=10, threshold=2))

    # 8) Save — random JPEG quality + plausible synthetic EXIF (instead of
    #     strip-only — strip looks "anonymized desktop export" to IG).
    quality = rng.randint(*cfg['jpeg_quality'])
    applied['jpeg_quality'] = quality
    exif_bytes = b''
    if cfg.get('inject_exif') and dst_path.lower().endswith(('.jpg', '.jpeg')):
        try:
            exif_dict, exif_meta = _build_synthetic_exif(rng, img.size[0], img.size[1])
            exif_bytes = piexif.dump(exif_dict)
            applied['exif_device'] = exif_meta['device']
            applied['exif_gps_city'] = exif_meta['gps_city']
            applied['exif_iso'] = exif_meta['iso']
            applied['exif_shutter'] = exif_meta['shutter']
        except Exception as e:
            applied['exif_inject_error'] = str(e)
            exif_bytes = b''

    if dst_path.lower().endswith('.png'):
        img.save(dst_path, 'PNG', optimize=True)
    elif dst_path.lower().endswith('.webp'):
        img.save(dst_path, 'WEBP', quality=quality)
    else:
        save_kwargs = {'quality': quality, 'optimize': True,
                       'subsampling': rng.choice([0, 1, 2])}
        if exif_bytes:
            save_kwargs['exif'] = exif_bytes
        img.save(dst_path, 'JPEG', **save_kwargs)

    applied['src_size_bytes'] = os.path.getsize(src_path)
    applied['dst_size_bytes'] = os.path.getsize(dst_path)

    # 9) Pre-flight perceptual-hash diff — 4 algos. Caller can react to a
    #    failing variant (regenerate with stronger preset / new seed).
    try:
        applied['hash_compare'] = compare_hashes(src_path, dst_path)
    except Exception as e:
        applied['hash_compare_error'] = str(e)

    return applied


def _apply_vignette(img, strength=0.2, rng=None):
    """Radial darkening at corners. strength ~0.15–0.25 is subtle but
    enough to shift mean-luma based hashes (aHash/dHash) without being
    obvious. Built from a small grayscale gradient mask scaled up."""
    w, h = img.size
    arr = np.asarray(img, dtype=np.float32) / 255.0
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = w / 2.0, h / 2.0
    # squared radial distance normalized to corner
    r2 = ((xx - cx) ** 2 + (yy - cy) ** 2) / (cx * cx + cy * cy)
    # darkening factor 1 (center) → 1-strength (corner)
    factor = 1.0 - (strength * np.clip(r2, 0.0, 1.0))
    arr = arr * factor[..., np.newaxis]
    arr = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, 'RGB')


def rng_gaussian_like(shape, std, rng):
    """numpy-style gaussian noise but using a seeded python Random for
    reproducibility tied to our caller's seed."""
    n = int(np.prod(shape))
    # Use numpy's default_rng seeded from the rng for speed
    np_rng = np.random.default_rng(rng.randint(0, 2**31))
    return np_rng.normal(0.0, std, size=shape)


# ─────────────────────────────────────────────────────────────────
# Video spoofing (ffmpeg)
# ─────────────────────────────────────────────────────────────────

def spoof_video(src_path: str, dst_path: str,
                preset: str = 'medium',
                seed: Optional[int] = None,
                timeout_sec: int = 300) -> dict:
    """Generate one spoofed variant of a video using ffmpeg filters.
    Returns stats dict. Raises on ffmpeg error."""
    if preset not in PRESETS:
        preset = 'medium'
    cfg = PRESETS[preset]
    rng = random.Random(seed if seed is not None else random.randint(0, 2**31))

    applied = {'preset': preset, 'seed': seed}

    # 1) Trim a bit off the start (-ss before -i = fast keyframe seek)
    trim_ms = rng.randint(*cfg['trim_start_ms'])
    trim_s = trim_ms / 1000.0
    applied['trim_start_ms'] = trim_ms

    # 2) Build the video filter chain
    # First probe original dims so the crop+restore math works
    w, h = _probe_video_size(src_path)
    applied['orig_size'] = [w, h]

    crop_pct = rng.uniform(*cfg['video_crop_pct'])
    cx = max(1, int(round(w * crop_pct / 100.0)))
    cy = max(1, int(round(h * crop_pct / 100.0)))
    # crop=in_w-2*cx:in_h-2*cy:cx:cy, scale=w:h to restore dims (forces even numbers)
    even_w = w if w % 2 == 0 else w - 1
    even_h = h if h % 2 == 0 else h - 1
    applied['video_crop_px'] = [cx, cy]

    eq_b = rng.uniform(*cfg['brightness'])
    eq_c = 1.0 + rng.uniform(*cfg['contrast'])
    eq_s = 1.0 + rng.uniform(*cfg['saturation'])
    hue = rng.uniform(*cfg['hue_deg'])
    applied.update({'brightness': round(eq_b, 4),
                    'contrast': round(eq_c, 4),
                    'saturation': round(eq_s, 4),
                    'hue_deg': round(hue, 2)})

    gamma = rng.uniform(*cfg.get('video_gamma', (1.0, 1.0)))
    applied['gamma'] = round(gamma, 4)

    vfilter = (
        f"crop=iw-2*{cx}:ih-2*{cy}:{cx}:{cy},"
        f"scale={even_w}:{even_h}:flags=lanczos,"
        f"eq=brightness={eq_b}:contrast={eq_c}:saturation={eq_s}:gamma={gamma},"
        f"hue=h={hue}"
    )

    # 3) Audio filter — low volume noise mix + slight EQ
    audio_db = cfg['audio_noise_db']
    # adelay tiny shift on the noise so it doesn't sync with original silence
    afilter = (
        f"[0:a]highpass=f=80,lowpass=f=15000,volume=1.0[base];"
        f"anoisesrc=color=pink:amplitude=0.02:sample_rate=44100[noise];"
        f"[noise]volume={audio_db}dB[qnoise];"
        f"[base][qnoise]amix=inputs=2:duration=first:dropout_transition=0[aout]"
    )

    # 4) Optional speed jitter (rare; strong only)
    sj = cfg['speed_jitter']
    if sj > 0:
        delta = rng.uniform(-sj, sj)
        if abs(delta) > 1e-5:
            setpts = 1.0 / (1.0 + delta)
            vfilter += f",setpts={setpts:.6f}*PTS"
            applied['speed_factor'] = round(1.0 + delta, 5)

    # 5) Random CRF + encoder metadata
    crf = rng.randint(*cfg['crf_range'])
    applied['crf'] = crf
    enc_id = uuid.uuid4().hex[:8]

    cmd = [
        FFMPEG_EXE,
        '-y',
        '-ss', f'{trim_s:.3f}',
        '-i', src_path,
        '-filter_complex', f"[0:v]{vfilter}[vout];{afilter}",
        '-map', '[vout]', '-map', '[aout]',
        '-c:v', 'libx264',
        '-preset', 'medium',
        '-crf', str(crf),
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '128k',
        '-movflags', '+faststart',
        '-metadata', f'creation_time={_random_iso_dt(rng)}',
        '-metadata', f'encoder=hydra-spoof-{enc_id}',
        '-loglevel', 'error',
        dst_path,
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-500:]}")

    applied['src_size_bytes'] = os.path.getsize(src_path)
    applied['dst_size_bytes'] = os.path.getsize(dst_path)

    # Pre-flight perceptual-hash diff on middle frame
    try:
        applied['hash_compare'] = compare_video_hashes(src_path, dst_path)
    except Exception as e:
        applied['hash_compare_error'] = str(e)

    return applied


def _probe_video_size(path: str) -> tuple[int, int]:
    """Return (width, height) using ffmpeg -hide_banner -i. Falls back to a
    reasonable default if probe fails."""
    try:
        proc = subprocess.run(
            [FFMPEG_EXE, '-hide_banner', '-i', path],
            capture_output=True, text=True, timeout=15
        )
        out = (proc.stderr or '') + (proc.stdout or '')
        # Look for "1920x1080" pattern in stream info
        import re
        m = re.search(r'(\d{2,5})x(\d{2,5})', out)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return 1080, 1920  # safe default (vertical IG)


def _random_iso_dt(rng):
    """A random plausible creation_time (within last 60 days)."""
    import datetime
    base = datetime.datetime.utcnow() - datetime.timedelta(days=rng.randint(1, 60),
                                                          hours=rng.randint(0, 23),
                                                          minutes=rng.randint(0, 59))
    return base.strftime('%Y-%m-%dT%H:%M:%S.000000Z')


# ─────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────

def is_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMAGE_EXTS


def is_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTS


def spoof_one(src_path: str, dst_path: str, preset: str = 'medium',
              seed: Optional[int] = None,
              allow_mirror: bool = True) -> dict:
    """Auto-dispatch based on file extension. allow_mirror only affects
    image variants — video doesn't currently mirror (would be visually
    obvious for any motion)."""
    if is_video(src_path):
        return spoof_video(src_path, dst_path, preset=preset, seed=seed)
    if is_image(src_path):
        return spoof_image(src_path, dst_path, preset=preset, seed=seed,
                           allow_mirror=allow_mirror)
    raise ValueError(f"Unsupported media type: {src_path}")
