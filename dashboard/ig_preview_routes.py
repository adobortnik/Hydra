"""
Instagram preview proxy (RapidAPI instagram120).

Calls the third-party Instagram scraper API server-side, caches metadata
and thumbnails locally, and streams images back to the browser so we:
  - never expose the RapidAPI key in JS
  - dodge Instagram CDN hot-link / expiring-signature issues
  - amortize API calls (rapidapi has per-request cost / monthly quota)

Endpoints (all GET, JSON unless noted):
  /api/ig-preview/profile?username=...    profile info (bio, followers, pic)
  /api/ig-preview/posts?username=...      12 most recent feed posts
  /api/ig-preview/reels?username=...      reels list
  /api/ig-preview/thumb/<post_id>         image stream (cached on disk)

Cache TTL: 30 min for metadata, 7 days for thumbnails. _meta_cache is a
process-local dict — fine for our single-process dashboard. If we ever go
multi-worker, swap for a SQLite cache.
"""
import json
import logging
import os
import time

import requests
from flask import Blueprint, jsonify, request, send_file

log = logging.getLogger(__name__)
ig_preview_bp = Blueprint('ig_preview', __name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, 'runtime', 'ig-preview-cache')
os.makedirs(CACHE_DIR, exist_ok=True)

RAPIDAPI_HOST = 'instagram120.p.rapidapi.com'
RAPIDAPI_KEY = os.environ.get(
    'INSTAGRAM120_API_KEY',
    '28be02c206msha841c79ad0fc0adp1603d9jsn7ce3152d419b'
)

META_TTL = 30 * 60                  # 30 min metadata cache
THUMB_TTL = 7 * 24 * 60 * 60        # 7 days thumbnail cache on disk
REQUEST_TIMEOUT = 15                # seconds

# Process-local caches
_meta_cache = {}                    # {(endpoint, username): (ts, payload)}
_thumb_remote_by_id = {}            # post_id -> remote thumb URL (relative or absolute)


# ─────────────────────────────────────────────────────────────────
# Low-level helpers
# ─────────────────────────────────────────────────────────────────

def _rapid_post(path, payload):
    """POST to the RapidAPI host with our auth headers. Raises on error."""
    r = requests.post(
        f'https://{RAPIDAPI_HOST}{path}',
        headers={
            'x-rapidapi-host': RAPIDAPI_HOST,
            'x-rapidapi-key': RAPIDAPI_KEY,
            'Content-Type': 'application/json',
        },
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def _pick_thumb_candidate(image_versions2):
    """Pick the best small thumbnail from image_versions2.candidates.
    Aim ~320px wide (grid cell size). Returns the candidate dict or None."""
    cands = (image_versions2 or {}).get('candidates') or []
    if not cands:
        return None
    # Prefer widths closest to 320; fall back to first candidate.
    by_target = sorted(
        cands, key=lambda c: abs((c.get('width') or 9999) - 320)
    )
    return by_target[0] if by_target else cands[0]


def _simplify_post(node):
    """Reduce a fat IG post node to just what the preview grid needs."""
    pk = node.get('pk') or node.get('id', '')
    thumb = _pick_thumb_candidate(node.get('image_versions2'))
    # url_wrapped is RapidAPI's signed proxy URL (no Instagram-CDN expiry
    # weirdness). Falls back to raw url if the API didn't return wrapped.
    # Prefer raw CDN url — wrapped is 401-locked behind RapidAPI in a way that
    # doesn't accept the regular x-rapidapi-key header. Raw URLs are valid for
    # ~24h (oe= signature) — we cache the bytes on disk so expiry only hurts
    # uncached new fetches.
    thumb_remote = None
    if thumb:
        thumb_remote = thumb.get('url') or thumb.get('url_wrapped')

    cap = ''
    cap_obj = node.get('caption')
    if isinstance(cap_obj, dict):
        cap = cap_obj.get('text', '') or ''
    if len(cap) > 200:
        cap = cap[:200] + '…'

    return {
        'id': str(pk),
        'code': node.get('code'),
        'media_type': node.get('media_type'),     # 1=image, 2=video, 8=carousel
        'like_count': node.get('like_count'),
        'comment_count': node.get('comment_count'),
        'view_count': node.get('view_count'),
        'play_count': node.get('play_count'),
        'taken_at': node.get('taken_at'),
        'caption': cap,
        'carousel_count': node.get('carousel_media_count'),
        'thumb_remote': thumb_remote,
    }


def _cached_meta(key):
    """Return cached payload if fresh, else None."""
    hit = _meta_cache.get(key)
    if not hit:
        return None
    ts, payload = hit
    if (time.time() - ts) < META_TTL:
        return ts, payload
    return None


def _stash_post_thumbs(posts):
    """Remember post_id -> thumb_remote so /thumb/<id> can resolve it later
    without re-hitting the metadata API."""
    for p in posts:
        if p.get('id') and p.get('thumb_remote'):
            _thumb_remote_by_id[p['id']] = p['thumb_remote']


# ─────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────

@ig_preview_bp.route('/api/ig-preview/profile')
def api_profile():
    """Profile info for a username."""
    username = request.args.get('username', '').strip().lstrip('@')
    if not username:
        return jsonify({'error': 'username required'}), 400
    key = ('profile', username.lower())
    cached = _cached_meta(key)
    if cached:
        return jsonify({'cached': True, 'fetched_at': cached[0], **cached[1]})

    try:
        raw = _rapid_post('/api/instagram/profile', {'username': username})
    except requests.HTTPError as e:
        return jsonify({'error': 'upstream error: %s' % e.response.status_code,
                        'detail': e.response.text[:300]}), 502
    except Exception as e:
        log.warning("ig-preview profile %s failed: %s", username, e)
        return jsonify({'error': str(e)}), 502

    r = raw.get('result') or {}
    payload = {
        'username': r.get('username'),
        'full_name': r.get('full_name'),
        'biography': r.get('biography'),
        'profile_pic': r.get('profile_pic_url_hd') or r.get('profile_pic_url'),
        'follower_count': r.get('follower_count') or r.get('edge_followed_by', {}).get('count'),
        'following_count': r.get('following_count') or r.get('edge_follow', {}).get('count'),
        'media_count': r.get('media_count'),
        'is_private': r.get('is_private'),
        'is_verified': r.get('is_verified'),
        'category': r.get('category') or r.get('category_name'),
        'external_url': r.get('external_url'),
    }
    _meta_cache[key] = (time.time(), payload)
    return jsonify({'cached': False, 'fetched_at': time.time(), **payload})


@ig_preview_bp.route('/api/ig-preview/posts')
def api_posts():
    """12 most recent feed posts for a username."""
    username = request.args.get('username', '').strip().lstrip('@')
    if not username:
        return jsonify({'error': 'username required'}), 400
    key = ('posts', username.lower())
    cached = _cached_meta(key)
    if cached:
        _stash_post_thumbs(cached[1].get('posts', []))
        return jsonify({'cached': True, 'fetched_at': cached[0], **cached[1]})

    try:
        raw = _rapid_post('/api/instagram/posts', {'username': username})
    except requests.HTTPError as e:
        return jsonify({'error': 'upstream error: %s' % e.response.status_code,
                        'detail': e.response.text[:300]}), 502
    except Exception as e:
        log.warning("ig-preview posts %s failed: %s", username, e)
        return jsonify({'error': str(e)}), 502

    edges = (raw.get('result') or {}).get('edges') or []
    posts = [_simplify_post(e.get('node') or {}) for e in edges]
    payload = {'username': username, 'posts': posts}
    _stash_post_thumbs(posts)
    _meta_cache[key] = (time.time(), payload)
    return jsonify({'cached': False, 'fetched_at': time.time(), **payload})


@ig_preview_bp.route('/api/ig-preview/reels')
def api_reels():
    """Reels grid for a username."""
    username = request.args.get('username', '').strip().lstrip('@')
    if not username:
        return jsonify({'error': 'username required'}), 400
    key = ('reels', username.lower())
    cached = _cached_meta(key)
    if cached:
        _stash_post_thumbs(cached[1].get('posts', []))
        return jsonify({'cached': True, 'fetched_at': cached[0], **cached[1]})

    try:
        raw = _rapid_post('/api/instagram/reels', {'username': username})
    except Exception as e:
        log.warning("ig-preview reels %s failed: %s", username, e)
        return jsonify({'error': str(e)}), 502

    edges = (raw.get('result') or {}).get('edges') or []
    reels = []
    for e in edges:
        node = e.get('node') or {}
        # Reels nest the actual post under node.media
        m = node.get('media') or node
        reels.append(_simplify_post(m))
    payload = {'username': username, 'posts': reels}
    _stash_post_thumbs(reels)
    _meta_cache[key] = (time.time(), payload)
    return jsonify({'cached': False, 'fetched_at': time.time(), **payload})


@ig_preview_bp.route('/api/ig-preview/thumb/<post_id>')
def api_thumb(post_id):
    """Stream the thumbnail for a post id. Cached on disk for THUMB_TTL."""
    if not post_id or '/' in post_id or '\\' in post_id:
        return jsonify({'error': 'bad post id'}), 400
    cache_path = os.path.join(CACHE_DIR, post_id + '.jpg')

    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < THUMB_TTL:
            return send_file(cache_path, mimetype='image/jpeg')

    remote = _thumb_remote_by_id.get(post_id)
    if not remote:
        return jsonify({'error': 'unknown post id — call /posts for this '
                                 'username first'}), 404

    # url_wrapped is host-relative; raw url is absolute Instagram CDN.
    if remote.startswith('/'):
        url = f'https://{RAPIDAPI_HOST}{remote}'
        headers = {
            'x-rapidapi-host': RAPIDAPI_HOST,
            'x-rapidapi-key': RAPIDAPI_KEY,
        }
    else:
        url = remote
        headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        r = requests.get(url, headers=headers, timeout=20, stream=True)
        r.raise_for_status()
        with open(cache_path, 'wb') as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
    except Exception as e:
        log.warning("thumb fetch %s failed: %s", post_id, e)
        return jsonify({'error': 'fetch failed: %s' % e}), 502

    return send_file(cache_path, mimetype='image/jpeg')


@ig_preview_bp.route('/api/ig-preview/profile-pic')
def api_profile_pic():
    """Stream the profile picture for a username. Cached on disk for
    THUMB_TTL. Browsers can <img src> this freely (no CDN hotlink issues)."""
    username = request.args.get('username', '').strip().lstrip('@').lower()
    if not username:
        return jsonify({'error': 'username required'}), 400
    cache_path = os.path.join(CACHE_DIR, 'avatar__' + username + '.jpg')

    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < THUMB_TTL:
            return send_file(cache_path, mimetype='image/jpeg')

    # Need a profile fetch to get the current pic URL (signatures expire)
    cached = _cached_meta(('profile', username))
    pic_url = None
    if cached:
        pic_url = cached[1].get('profile_pic')
    if not pic_url:
        try:
            raw = _rapid_post('/api/instagram/profile', {'username': username})
        except Exception as e:
            log.warning("avatar fetch %s — profile call failed: %s", username, e)
            return jsonify({'error': str(e)}), 502
        r = raw.get('result') or {}
        pic_url = r.get('profile_pic_url_hd') or r.get('profile_pic_url')
        # Stash so subsequent calls don't re-fetch
        _meta_cache[('profile', username)] = (time.time(), {
            'username': r.get('username'),
            'full_name': r.get('full_name'),
            'biography': r.get('biography'),
            'profile_pic': pic_url,
            'follower_count': r.get('follower_count'),
            'following_count': r.get('following_count'),
            'media_count': r.get('media_count'),
            'is_private': r.get('is_private'),
            'is_verified': r.get('is_verified'),
            'category': r.get('category') or r.get('category_name'),
            'external_url': r.get('external_url'),
        })
    if not pic_url:
        return jsonify({'error': 'no profile pic available'}), 404

    try:
        r = requests.get(pic_url, headers={'User-Agent': 'Mozilla/5.0'},
                         timeout=20, stream=True)
        r.raise_for_status()
        with open(cache_path, 'wb') as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
    except Exception as e:
        log.warning("avatar bytes fetch %s failed: %s", username, e)
        return jsonify({'error': 'fetch failed'}), 502

    return send_file(cache_path, mimetype='image/jpeg')


@ig_preview_bp.route('/api/ig-preview/cache-clear', methods=['POST'])
def api_cache_clear():
    """Drop the in-process metadata cache (thumbnails on disk stay)."""
    n = len(_meta_cache)
    _meta_cache.clear()
    return jsonify({'cleared': n})
