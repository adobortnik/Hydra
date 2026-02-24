"""
comment_routes.py - Comment Management Blueprint

Manage comment template lists with AI-powered generation capabilities.
Uses phone_farm.db as the single source of truth.
"""

import json
import re
import os
import random
import base64
import logging
import traceback
from flask import Blueprint, render_template, request, jsonify
from phone_farm_db import get_conn, row_to_dict, rows_to_dicts
from datetime import datetime

log = logging.getLogger(__name__)

comment_bp = Blueprint('comments', __name__)


# ─────────────────────────────────────────────
# TABLE INIT — runs on import
# ─────────────────────────────────────────────

def init_comment_tables():
    """Create comment_lists table if it doesn't exist."""
    conn = get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS comment_lists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                comments_json TEXT NOT NULL DEFAULT '[]',
                ai_enabled INTEGER DEFAULT 0,
                ai_style TEXT,
                ai_sample_count INTEGER DEFAULT 10,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
    finally:
        conn.close()

    # Also ensure job_orders has the new columns
    _migrate_job_orders()


def _migrate_job_orders():
    """Add comment_list_id, ai_mode, vision_ai columns to job_orders if missing."""
    conn = get_conn()
    try:
        # Check existing columns
        cursor = conn.execute("PRAGMA table_info(job_orders)")
        existing = {row['name'] for row in cursor.fetchall()}

        migrations = []
        if 'comment_list_id' not in existing:
            migrations.append("ALTER TABLE job_orders ADD COLUMN comment_list_id INTEGER")
        if 'ai_mode' not in existing:
            migrations.append("ALTER TABLE job_orders ADD COLUMN ai_mode INTEGER DEFAULT 0")
        if 'vision_ai' not in existing:
            migrations.append("ALTER TABLE job_orders ADD COLUMN vision_ai INTEGER DEFAULT 0")

        for sql in migrations:
            try:
                conn.execute(sql)
            except Exception:
                pass  # column already exists

        conn.commit()
    finally:
        conn.close()


# Run on import
init_comment_tables()


# ─────────────────────────────────────────────
# SPINTAX HELPERS
# ─────────────────────────────────────────────

def resolve_spintax(text):
    """Resolve {option1|option2|option3} spintax in a string."""
    pattern = r'\{([^{}]+)\}'
    while re.search(pattern, text):
        def replace_match(match):
            options = match.group(1).split('|')
            return random.choice(options)
        text = re.sub(pattern, replace_match, text)
    return text


# ─────────────────────────────────────────────
# AI COMMENT GENERATION (pattern-based for now)
# ─────────────────────────────────────────────

# Emoji groups for variation
EMOJI_GROUPS = {
    'fire': ['🔥', '💥', '⚡', '✨', '🌟'],
    'love': ['❤️', '💕', '💖', '💗', '💓', '🥰', '😍'],
    'praise': ['👏', '🙌', '💯', '🎯', '👑', '🏆'],
    'happy': ['😊', '😄', '🤩', '😁', '🥳'],
    'cool': ['😎', '🤘', '💪', '🆒', '👌'],
    'nature': ['🌈', '☀️', '🌸', '🌺', '🍀'],
}

# Synonym maps for variation
SYNONYM_MAP = {
    'amazing': ['incredible', 'stunning', 'gorgeous', 'phenomenal', 'breathtaking', 'magnificent'],
    'beautiful': ['gorgeous', 'stunning', 'lovely', 'pretty', 'exquisite', 'elegant'],
    'love': ['adore', 'am obsessed with', 'can\'t get enough of', 'am in love with', 'absolutely love'],
    'great': ['fantastic', 'wonderful', 'awesome', 'excellent', 'superb', 'brilliant'],
    'nice': ['lovely', 'wonderful', 'delightful', 'charming', 'splendid'],
    'good': ['great', 'excellent', 'fantastic', 'wonderful', 'superb'],
    'cool': ['awesome', 'epic', 'sick', 'rad', 'fire', 'dope'],
    'perfect': ['flawless', 'impeccable', 'ideal', 'spotless', 'divine'],
    'best': ['finest', 'greatest', 'top-tier', 'supreme', 'ultimate'],
    'wow': ['omg', 'whoa', 'oh my', 'no way', 'insane'],
}

# Comment structure templates
STRUCTURE_TEMPLATES = [
    "{exclamation} {adjective}! {emoji}",
    "{emoji} {adjective} {noun}!",
    "This is so {adjective} {emoji}{emoji}",
    "I {verb} this! {emoji}",
    "{exclamation}! {emoji} So {adjective}",
    "Absolutely {adjective} {emoji}",
    "{emoji} {exclamation}! This is {adjective}",
    "Can't stop looking at this {emoji} {adjective}!",
    "{adjective} content as always {emoji}",
    "Keep it up! {emoji} So {adjective}",
    "This made my day {emoji} {adjective}!",
    "{exclamation} {emoji} You're the {superlative}!",
    "Literally the {superlative} thing I've seen today {emoji}",
    "{emoji} Goals!! So {adjective}",
    "Need more of this {emoji}{emoji}",
]

EXCLAMATIONS = ['Wow', 'OMG', 'Whoa', 'Yesss', 'No way', 'Insane', 'Sheesh', 'Damn', 'Bruh']
ADJECTIVES = ['amazing', 'beautiful', 'stunning', 'incredible', 'gorgeous', 'perfect', 'fire', 'sick', 'epic', 'dope']
NOUNS = ['content', 'vibes', 'energy', 'aesthetic', 'post', 'pic', 'shot']
VERBS = ['love', 'adore', 'dig', 'vibe with', 'appreciate']
SUPERLATIVES = ['best', 'coolest', 'most amazing', 'most beautiful', 'most fire', 'greatest']


def _analyze_patterns(existing_comments):
    """Analyze existing comments to understand patterns."""
    if not existing_comments:
        return {
            'avg_length': 30,
            'emoji_density': 0.3,
            'exclamation_rate': 0.5,
            'has_questions': False,
            'common_emojis': ['🔥', '❤️', '😍'],
            'tone': 'casual',
        }

    import unicodedata

    total_len = 0
    emoji_count = 0
    char_count = 0
    exclamation_count = 0
    question_count = 0
    found_emojis = []

    for comment in existing_comments:
        resolved = resolve_spintax(comment)
        total_len += len(resolved)
        char_count += len(resolved)

        if '!' in resolved:
            exclamation_count += 1
        if '?' in resolved:
            question_count += 1

        for ch in resolved:
            if unicodedata.category(ch).startswith('So'):
                emoji_count += 1
                found_emojis.append(ch)

    n = len(existing_comments)
    return {
        'avg_length': total_len // max(n, 1),
        'emoji_density': emoji_count / max(char_count, 1),
        'exclamation_rate': exclamation_count / max(n, 1),
        'has_questions': question_count > 0,
        'common_emojis': list(set(found_emojis))[:10] if found_emojis else ['🔥', '❤️', '😍', '👏', '💯'],
        'tone': 'enthusiastic' if exclamation_count > n * 0.5 else 'casual',
    }


def _swap_synonyms(text):
    """Replace words with random synonyms."""
    words = text.split()
    result = []
    for word in words:
        lower = word.lower().strip('!.,?')
        if lower in SYNONYM_MAP and random.random() > 0.5:
            replacement = random.choice(SYNONYM_MAP[lower])
            # Preserve original capitalization
            if word[0].isupper():
                replacement = replacement.capitalize()
            result.append(replacement)
        else:
            result.append(word)
    return ' '.join(result)


def _swap_emojis(text, available_emojis):
    """Replace emojis with similar ones."""
    import unicodedata
    result = []
    for ch in text:
        if unicodedata.category(ch).startswith('So') and available_emojis and random.random() > 0.4:
            result.append(random.choice(available_emojis))
        else:
            result.append(ch)
    return ''.join(result)


def generate_comments_from_patterns(existing_comments, style_description='', count=10):
    """
    Generate new comments by analyzing patterns in existing ones.
    This is the smart pattern-based generator — will be replaced with real AI later.
    """
    patterns = _analyze_patterns(existing_comments)
    generated = []

    # Strategy 1: Mutate existing comments (synonym + emoji swap)
    if existing_comments:
        for _ in range(count // 3 + 1):
            base = random.choice(existing_comments)
            resolved = resolve_spintax(base)
            mutated = _swap_synonyms(resolved)
            mutated = _swap_emojis(mutated, patterns['common_emojis'])
            if mutated not in generated and mutated not in existing_comments:
                generated.append(mutated)

    # Strategy 2: Generate from structure templates
    emojis = patterns['common_emojis'] if patterns['common_emojis'] else ['🔥', '❤️', '😍']
    for _ in range(count // 3 + 1):
        template = random.choice(STRUCTURE_TEMPLATES)
        comment = template.format(
            exclamation=random.choice(EXCLAMATIONS),
            adjective=random.choice(ADJECTIVES),
            noun=random.choice(NOUNS),
            verb=random.choice(VERBS),
            superlative=random.choice(SUPERLATIVES),
            emoji=random.choice(emojis),
        )
        if comment not in generated:
            generated.append(comment)

    # Strategy 3: Create spintax combinations from existing if they have spintax
    spintax_comments = [c for c in existing_comments if '{' in c and '|' in c]
    if spintax_comments:
        for _ in range(count // 3 + 1):
            base = random.choice(spintax_comments)
            resolved = resolve_spintax(base)
            if resolved not in generated and resolved not in existing_comments:
                generated.append(resolved)

    # Strategy 4: Combine parts of existing comments
    if len(existing_comments) >= 2:
        for _ in range(count // 4 + 1):
            c1 = resolve_spintax(random.choice(existing_comments))
            c2 = resolve_spintax(random.choice(existing_comments))
            # Take first half of c1 and second half of c2
            mid1 = len(c1) // 2
            mid2 = len(c2) // 2
            combined = c1[:mid1].rstrip() + ' ' + c2[mid2:].lstrip()
            combined = combined.strip()
            if combined and combined not in generated and len(combined) > 5:
                generated.append(combined)

    # Trim to requested count
    random.shuffle(generated)
    return generated[:count]


# ─────────────────────────────────────────────
# PAGE ROUTE
# ─────────────────────────────────────────────

@comment_bp.route('/comments')
def comments_page():
    return render_template('comments.html')


# ─────────────────────────────────────────────
# API: LIST ALL COMMENT LISTS
# ─────────────────────────────────────────────

@comment_bp.route('/api/comments/lists', methods=['GET'])
def api_list_comment_lists():
    conn = get_conn()
    try:
        lists = rows_to_dicts(conn.execute("""
            SELECT * FROM comment_lists ORDER BY updated_at DESC
        """).fetchall())

        # Add comment_count to each list
        for cl in lists:
            try:
                comments = json.loads(cl.get('comments_json', '[]'))
                cl['comment_count'] = len(comments)
            except (json.JSONDecodeError, TypeError):
                cl['comment_count'] = 0

        return jsonify({'lists': lists})
    finally:
        conn.close()


# ─────────────────────────────────────────────
# API: GET SINGLE LIST
# ─────────────────────────────────────────────

@comment_bp.route('/api/comments/lists/<int:list_id>', methods=['GET'])
def api_get_comment_list(list_id):
    conn = get_conn()
    try:
        cl = row_to_dict(conn.execute(
            "SELECT * FROM comment_lists WHERE id = ?", (list_id,)
        ).fetchone())
        if not cl:
            return jsonify({'error': 'Comment list not found'}), 404

        try:
            cl['comments'] = json.loads(cl.get('comments_json', '[]'))
        except (json.JSONDecodeError, TypeError):
            cl['comments'] = []
        cl['comment_count'] = len(cl['comments'])

        return jsonify(cl)
    finally:
        conn.close()


# ─────────────────────────────────────────────
# API: CREATE LIST
# ─────────────────────────────────────────────

@comment_bp.route('/api/comments/lists', methods=['POST'])
def api_create_comment_list():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400

    # Accept comments as array or newline-separated text
    comments = data.get('comments', [])
    if isinstance(comments, str):
        comments = [c.strip() for c in comments.split('\n') if c.strip()]

    conn = get_conn()
    try:
        now = datetime.utcnow().isoformat()
        cursor = conn.execute("""
            INSERT INTO comment_lists (name, description, comments_json, ai_enabled, ai_style, ai_sample_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name,
            data.get('description', ''),
            json.dumps(comments),
            1 if data.get('ai_enabled') else 0,
            data.get('ai_style', ''),
            int(data.get('ai_sample_count', 10)),
            now, now
        ))
        list_id = cursor.lastrowid
        conn.commit()
        return jsonify({'id': list_id, 'success': True}), 201
    finally:
        conn.close()


# ─────────────────────────────────────────────
# API: UPDATE LIST
# ─────────────────────────────────────────────

@comment_bp.route('/api/comments/lists/<int:list_id>', methods=['PUT'])
def api_update_comment_list(list_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    conn = get_conn()
    try:
        existing = conn.execute("SELECT id FROM comment_lists WHERE id = ?", (list_id,)).fetchone()
        if not existing:
            return jsonify({'error': 'Comment list not found'}), 404

        fields = {}
        if 'name' in data:
            fields['name'] = data['name'].strip()
        if 'description' in data:
            fields['description'] = data['description']
        if 'comments' in data:
            comments = data['comments']
            if isinstance(comments, str):
                comments = [c.strip() for c in comments.split('\n') if c.strip()]
            fields['comments_json'] = json.dumps(comments)
        if 'ai_enabled' in data:
            fields['ai_enabled'] = 1 if data['ai_enabled'] else 0
        if 'ai_style' in data:
            fields['ai_style'] = data['ai_style']
        if 'ai_sample_count' in data:
            fields['ai_sample_count'] = int(data['ai_sample_count'])

        if not fields:
            return jsonify({'error': 'No valid fields to update'}), 400

        fields['updated_at'] = datetime.utcnow().isoformat()
        set_clause = ', '.join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [list_id]

        conn.execute(f"UPDATE comment_lists SET {set_clause} WHERE id = ?", values)
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()


# ─────────────────────────────────────────────
# API: DELETE LIST
# ─────────────────────────────────────────────

@comment_bp.route('/api/comments/lists/<int:list_id>', methods=['DELETE'])
def api_delete_comment_list(list_id):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT id FROM comment_lists WHERE id = ?", (list_id,)).fetchone()
        if not existing:
            return jsonify({'error': 'Comment list not found'}), 404

        conn.execute("DELETE FROM comment_lists WHERE id = ?", (list_id,))
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()


# ─────────────────────────────────────────────
# API: PREVIEW (resolve spintax for a list)
# ─────────────────────────────────────────────

@comment_bp.route('/api/comments/lists/<int:list_id>/preview', methods=['GET'])
def api_preview_comments(list_id):
    count = request.args.get('count', 10, type=int)
    conn = get_conn()
    try:
        cl = conn.execute("SELECT comments_json FROM comment_lists WHERE id = ?", (list_id,)).fetchone()
        if not cl:
            return jsonify({'error': 'Comment list not found'}), 404

        try:
            comments = json.loads(cl['comments_json'])
        except (json.JSONDecodeError, TypeError):
            comments = []

        # Generate resolved previews
        previews = []
        for _ in range(min(count, max(len(comments) * 3, 20))):
            if comments:
                raw = random.choice(comments)
                resolved = resolve_spintax(raw)
                previews.append({'raw': raw, 'resolved': resolved})

        return jsonify({'previews': previews})
    finally:
        conn.close()


# ─────────────────────────────────────────────
# API: GENERATE AI COMMENTS
# ─────────────────────────────────────────────

@comment_bp.route('/api/comments/lists/<int:list_id>/generate-ai', methods=['POST'])
def api_generate_ai_comments(list_id):
    data = request.get_json() or {}

    conn = get_conn()
    try:
        cl = conn.execute("SELECT * FROM comment_lists WHERE id = ?", (list_id,)).fetchone()
        if not cl:
            return jsonify({'error': 'Comment list not found'}), 404

        cl = row_to_dict(cl)
        try:
            existing = json.loads(cl.get('comments_json', '[]'))
        except (json.JSONDecodeError, TypeError):
            existing = []

        style = data.get('style', cl.get('ai_style', ''))
        count = int(data.get('count', cl.get('ai_sample_count', 10)))
        count = max(1, min(count, 100))  # Clamp

        # Generate using pattern-based approach
        generated = generate_comments_from_patterns(existing, style, count)

        # Option to auto-append
        if data.get('append', False):
            new_comments = existing + generated
            now = datetime.utcnow().isoformat()
            conn.execute(
                "UPDATE comment_lists SET comments_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(new_comments), now, list_id)
            )
            conn.commit()

        return jsonify({
            'generated': generated,
            'count': len(generated),
            'appended': data.get('append', False)
        })
    finally:
        conn.close()


# ─────────────────────────────────────────────
# VISION AI HELPERS
# ─────────────────────────────────────────────

def _get_openai_api_key():
    """Get OpenAI API key from global_settings.json or data/api_keys.json."""
    # Try global_settings.json first
    settings_path = os.path.join(os.path.dirname(__file__), 'global_settings.json')
    try:
        with open(settings_path, 'r') as f:
            settings = json.load(f)
        key = settings.get('ai', {}).get('openai_api_key', '')
        if key and key.startswith('sk-'):
            return key
    except Exception:
        pass

    # Fallback to data/api_keys.json
    api_keys_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'api_keys.json')
    try:
        with open(api_keys_path, 'r') as f:
            keys = json.load(f)
        key = keys.get('openai', '')
        if key and key.startswith('sk-'):
            return key
    except Exception:
        pass

    return None


def _fetch_post_image(post_url):
    """
    Fetch Instagram post image. Returns (image_base64, image_url, content_type) or raises.
    Strategy 1: IG oembed API -> thumbnail_url
    Strategy 2: Fetch post page -> extract og:image meta tag
    """
    import urllib.request
    import urllib.error

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    image_url = None

    # Strategy 0: Direct /media/ endpoint (most reliable, no auth needed)
    try:
        # Extract shortcode from URL and build /media/ URL
        clean = post_url.split('?')[0].rstrip('/')
        media_url = clean + '/media/?size=l'
        req = urllib.request.Request(media_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            image_data = resp.read()
            content_type = resp.headers.get('Content-Type', 'image/jpeg')
            image_url = resp.url  # Final redirected CDN URL
            if len(image_data) > 1000:  # Valid image
                image_b64 = base64.b64encode(image_data).decode('utf-8')
                log.info(f"Vision AI: Got image via /media/ ({len(image_data)} bytes)")
                return image_b64, image_url, content_type
    except Exception as e:
        log.warning(f"Vision AI: /media/ endpoint failed: {e}")

    # Strategy 1: IG oembed API
    try:
        oembed_url = f'https://api.instagram.com/oembed?url={post_url}'
        req = urllib.request.Request(oembed_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            oembed_data = json.loads(resp.read().decode())
            image_url = oembed_data.get('thumbnail_url')
            log.info(f"Vision AI: Got image from oembed: {image_url[:80] if image_url else 'None'}...")
    except Exception as e:
        log.warning(f"Vision AI: oembed failed: {e}")

    # Strategy 2: Fetch page and extract og:image
    if not image_url:
        try:
            req = urllib.request.Request(post_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
            # Extract og:image
            og_match = re.search(r'<meta\s+(?:property|name)=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html)
            if not og_match:
                og_match = re.search(r'content=["\']([^"\']+)["\']\s+(?:property|name)=["\']og:image["\']', html)
            if og_match:
                image_url = og_match.group(1).replace('&amp;', '&')
                log.info(f"Vision AI: Got image from og:image: {image_url[:80]}...")
            else:
                raise ValueError("Could not find og:image in post page")
        except Exception as e:
            log.warning(f"Vision AI: og:image extraction failed: {e}")
            raise ValueError(f"Could not fetch post image. oembed and og:image both failed: {e}")

    if not image_url:
        raise ValueError("No image URL found for this post")

    # Download the image
    try:
        req = urllib.request.Request(image_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            image_data = resp.read()
            content_type = resp.headers.get('Content-Type', 'image/jpeg')
        image_b64 = base64.b64encode(image_data).decode('utf-8')
        log.info(f"Vision AI: Downloaded image ({len(image_data)} bytes)")
        return image_b64, image_url, content_type
    except Exception as e:
        raise ValueError(f"Failed to download image from {image_url[:80]}: {e}")


# ─────────────────────────────────────────────
# API: VISION COMMENT GENERATION
# ─────────────────────────────────────────────

@comment_bp.route('/api/comments/generate-vision', methods=['POST'])
def api_generate_vision_comment():
    """
    Generate comments using OpenAI GPT-4o vision.
    Fetches the post image, sends to GPT-4o with a prompt, returns generated comments.
    """
    data = request.get_json() or {}
    post_url = data.get('post_url', '').strip()
    comment_count = min(max(int(data.get('comment_count', 50)), 1), 200)
    style = data.get('style', 'casual, emoji-heavy, short').strip()
    language = data.get('language', 'en').strip()

    if not post_url:
        return jsonify({'success': False, 'error': 'post_url is required'}), 400

    # Validate it looks like an IG post/reel URL
    if 'instagram.com/p/' not in post_url and 'instagram.com/reel/' not in post_url:
        return jsonify({'success': False, 'error': 'URL must be an Instagram post or reel URL'}), 400

    # Get API key
    api_key = _get_openai_api_key()
    if not api_key:
        return jsonify({'success': False, 'error': 'OpenAI API key not configured. Check global_settings.json'}), 500

    # Fetch the post image
    try:
        image_b64, image_url, content_type = _fetch_post_image(post_url)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    # Determine media type for data URL
    if 'png' in content_type:
        media_type = 'image/png'
    elif 'webp' in content_type:
        media_type = 'image/webp'
    elif 'gif' in content_type:
        media_type = 'image/gif'
    else:
        media_type = 'image/jpeg'

    # Build the prompt
    lang_instruction = f"\nIMPORTANT: Write ALL comments in {language} language." if language != 'en' else ''
    prompt = f"""Look at this Instagram post image. Generate {comment_count} unique, natural Instagram comments.

Style: {style}
{lang_instruction}
Rules:
- Each comment on its own line
- Vary length (some short like "🔥🔥", some 1-2 sentences)
- Mix emoji usage (some with, some without)
- Sound like real different people commenting
- No hashtags in comments
- Never repeat the same comment
- Make comments relevant to what you see in the image
- Output ONLY the comments, one per line, no numbering, no quotes"""

    # Call OpenAI GPT-4o with vision
    try:
        import urllib.request
        import urllib.error

        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{image_b64}",
                                "detail": "low"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": min(comment_count * 40, 4096),
            "temperature": 0.9
        }

        req_data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            'https://api.openai.com/v1/chat/completions',
            data=req_data,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())

        # Parse response
        content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        usage = result.get('usage', {})

        # Parse comments from response (one per line)
        comments = []
        for line in content.split('\n'):
            line = line.strip()
            # Remove any numbering like "1. " or "1) " or "- "
            line = re.sub(r'^\d+[\.\)]\s*', '', line)
            line = re.sub(r'^[-•]\s*', '', line)
            # Remove surrounding quotes
            line = line.strip('"\'')
            line = line.strip()
            if line and len(line) >= 2:
                comments.append(line)

        # Estimate cost (GPT-4o: ~$2.50/1M input, $10/1M output; image ~85 tokens at low detail)
        input_tokens = usage.get('prompt_tokens', 0)
        output_tokens = usage.get('completion_tokens', 0)
        cost = (input_tokens * 2.5 / 1_000_000) + (output_tokens * 10.0 / 1_000_000)
        cost_str = f"${cost:.4f}"

        log.info(f"Vision AI: Generated {len(comments)} comments for {post_url[:60]}. "
                 f"Tokens: {input_tokens}in/{output_tokens}out. Cost: {cost_str}")

        return jsonify({
            'success': True,
            'comments': comments,
            'comment_count': len(comments),
            'image_url': image_url,
            'cost_estimate': cost_str,
            'tokens': {'input': input_tokens, 'output': output_tokens}
        })

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='ignore')
        log.error(f"Vision AI OpenAI API error {e.code}: {error_body}")
        try:
            err_json = json.loads(error_body)
            err_msg = err_json.get('error', {}).get('message', error_body[:200])
        except Exception:
            err_msg = error_body[:200]
        return jsonify({'success': False, 'error': f'OpenAI API error ({e.code}): {err_msg}'}), 502
    except Exception as e:
        log.error(f"Vision AI error: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': f'Vision AI generation failed: {str(e)}'}), 500
