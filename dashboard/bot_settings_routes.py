"""
Bot Settings Routes - API for managing bot settings

All data is read/written from phone_farm.db (centralized database).
Tables used: accounts, account_settings, account_sources, account_text_configs
"""

from flask import Blueprint, request, jsonify
from phone_farm_db import get_conn, row_to_dict, rows_to_dicts, get_account_settings, upsert_account_settings
import json
from datetime import datetime

bot_settings_bp = Blueprint('bot_settings', __name__, url_prefix='/api/bot-settings')


# =============================================================================
# ACCOUNT LOOKUP
# =============================================================================

def get_account_id(device_serial, username):
    """Look up account ID from device_serial + username. Returns int or None."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM accounts WHERE device_serial = ? AND username = ?",
            (device_serial, username)
        ).fetchone()
        return row['id'] if row else None
    finally:
        conn.close()


# =============================================================================
# SETTINGS JSON  (account_settings table)
# =============================================================================

def read_settings_json(account_id):
    """Read and parse settings JSON for an account."""
    return get_account_settings(account_id)


def write_settings_json(account_id, settings):
    """Write settings JSON for an account (upsert)."""
    try:
        upsert_account_settings(account_id, settings)
        return True
    except Exception as e:
        print(f"Error writing settings: {e}")
        return False


# =============================================================================
# ACCOUNT TOGGLES  (accounts table)
# =============================================================================

TOGGLE_COLUMNS = [
    'follow_enabled', 'unfollow_enabled', 'mute_enabled',
    'like_enabled', 'comment_enabled', 'story_enabled', 'switchmode',
]

# UI field name  →  DB column name
TOGGLE_UI_TO_DB = {
    'enable_follow':       'follow_enabled',
    'enable_unfollow':     'unfollow_enabled',
    'enable_likepost':     'like_enabled',
    'enable_comment':      'comment_enabled',
    'enable_story_viewer': 'story_enabled',
    'enable_mute':         'mute_enabled',
    'enable_switchmode':   'switchmode',
}

# DB column  →  UI field name  (reverse)
TOGGLE_DB_TO_UI = {v: k for k, v in TOGGLE_UI_TO_DB.items()}


def _to_bool(val):
    """Convert DB string ('True'/'False'/'On'/'Off') to Python bool."""
    if val is None:
        return False
    return str(val).lower().strip() in ('on', 'true', '1', 'yes')


def read_account_toggles(account_id):
    """Read toggle booleans from the accounts table.

    Returns dict keyed by DB column name (e.g. 'follow_enabled': True).
    """
    conn = get_conn()
    try:
        cols_sql = ', '.join(TOGGLE_COLUMNS)
        row = conn.execute(
            f"SELECT {cols_sql} FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if not row:
            return {}
        return {col: _to_bool(row[col]) for col in TOGGLE_COLUMNS}
    finally:
        conn.close()


def write_account_toggles(account_id, toggles):
    """Write toggle values to the accounts table.

    *toggles* is keyed by **DB column names** (follow_enabled, etc.).
    """
    conn = get_conn()
    try:
        updates, values = [], []
        for col in TOGGLE_COLUMNS:
            if col in toggles:
                updates.append(f"{col} = ?")
                values.append('True' if toggles[col] else 'False')
        if updates:
            values.append(account_id)
            conn.execute(
                f"UPDATE accounts SET {', '.join(updates)}, updated_at = ? WHERE id = ?",
                [*values[:-1], datetime.utcnow().isoformat(), account_id]
            )
            conn.commit()
        return True
    except Exception as e:
        print(f"Error writing toggles: {e}")
        return False
    finally:
        conn.close()


def read_account_data(account_id):
    """Read full account row from the accounts table."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return row_to_dict(row) or {}
    finally:
        conn.close()


# =============================================================================
# TEXT LISTS  (account_sources table)
# =============================================================================

# Mapping of API list_type  →  old filename (kept for validation & source_type derivation)
LIST_FILE_MAPPING = {
    # Follow
    'sources':                   'sources.txt',
    'follow_specific_sources':   'follow-specific-sources.txt',
    'follow_likers_sources':     'follow-likers-sources.txt',
    'follow_keywords':           'follow_using_word_search.txt',
    # Unfollow
    'unfollow_specific':         'unfollow-specific-accounts.txt',
    # Like
    'like_sources':              'like-sources.txt',
    'like_keywords':             'like_post_likers_using_keyword_search.txt',
    'like_specific_accounts':    'like_posts_specific.txt',
    # Comment
    'comment_sources':           'comment-sources.txt',
    'comment_keywords':          'comment_using_keyword_search.txt',
    # Share
    'share_sources':             'share-sources.txt',
    # Story
    'story_followers_sources':   'storyviewer-user-followers-sources.txt',
    'story_likers_sources':      'storyviewer-user-likers-sources.txt',
    # DM
    'dm_specific_users':         'directmessagespecificuser.txt',
    'dm_specific_sources':       'directmessagespecificusersources.txt',
    # Reels
    'watch_reels_sources':       'watch_reels_sources.txt',
    # View
    'view_specific_users':       'view_specific_user.txt',
    'view_specific_highlights':  'view_specific_user_highlight.txt',
    # Filters
    'whitelist':                 'whitelist.txt',
    'name_must_include':         'name_must_include.txt',
    'name_must_not_include':     'name_must_not_include.txt',
    'name_must_include_likes':   'name_must_include_likes.txt',
    'name_must_not_include_likes': 'name_must_not_include_likes.txt',
    'close_friends':             'close-friends.txt',
}


def _get_source_type(list_type):
    """Derive DB source_type from API list_type (strip .txt, dashes → underscores)."""
    filename = LIST_FILE_MAPPING.get(list_type, '')
    return filename.replace('.txt', '').replace('-', '_')


def read_text_list(account_id, list_type):
    """Read a list of values from account_sources."""
    source_type = _get_source_type(list_type)
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT value FROM account_sources WHERE account_id = ? AND source_type = ? ORDER BY id",
            (account_id, source_type)
        ).fetchall()
        return [r['value'] for r in rows if r['value']]
    finally:
        conn.close()


def write_text_list(account_id, list_type, items):
    """Replace all values for a source_type in account_sources."""
    source_type = _get_source_type(list_type)
    conn = get_conn()
    try:
        now = datetime.utcnow().isoformat()
        conn.execute(
            "DELETE FROM account_sources WHERE account_id = ? AND source_type = ?",
            (account_id, source_type)
        )
        for item in items:
            stripped = item.strip()
            if stripped:
                conn.execute(
                    "INSERT INTO account_sources (account_id, source_type, value, created_at) VALUES (?, ?, ?, ?)",
                    (account_id, source_type, stripped, now)
                )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error writing list ({source_type}): {e}")
        return False
    finally:
        conn.close()


# =============================================================================
# TEXT FILES / PROMPTS  (account_text_configs table)
# =============================================================================

# API prompt_type key  ==  DB config_type (they match directly)
PROMPT_FILE_MAPPING = {
    'gpt_prompt':              'gpt_prompt.txt',
    'comment_gpt_prompt':      'comment_gpt_prompt.txt',
    'dm_new_followers_prompt':  'message_new_followers_gpt_prompt.txt',
    'dm_specific_users_prompt': 'message_specific_users_gpt_prompt.txt',
    'caption_prompt':          'caption_prompt.txt',
}


def read_text_file(account_id, config_type):
    """Read prompt/text content from account_text_configs."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT content FROM account_text_configs WHERE account_id = ? AND config_type = ?",
            (account_id, config_type)
        ).fetchone()
        return row['content'] if row else ""
    finally:
        conn.close()


def write_text_file(account_id, config_type, content):
    """Upsert prompt/text content in account_text_configs."""
    conn = get_conn()
    try:
        now = datetime.utcnow().isoformat()
        existing = conn.execute(
            "SELECT id FROM account_text_configs WHERE account_id = ? AND config_type = ?",
            (account_id, config_type)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE account_text_configs SET content = ?, updated_at = ? WHERE id = ?",
                (content, now, existing['id'])
            )
        else:
            conn.execute(
                "INSERT INTO account_text_configs (account_id, config_type, content, updated_at) VALUES (?, ?, ?, ?)",
                (account_id, config_type, content, now)
            )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error writing text config ({config_type}): {e}")
        return False
    finally:
        conn.close()


# =============================================================================
# API ENDPOINTS
# =============================================================================

@bot_settings_bp.route('/<device_serial>/<account>', methods=['GET'])
def get_settings(device_serial, account):
    """Get all settings for an account (settings JSON + toggles + account data)."""
    account_id = get_account_id(device_serial, account)
    if account_id is None:
        return jsonify({
            'success': False,
            'error': f'Account not found: {device_serial}/{account}'
        }), 404

    # Settings JSON from account_settings
    settings = read_settings_json(account_id)

    # Merge master toggles from accounts table into settings using UI field names
    toggles = read_account_toggles(account_id)
    for db_col, is_on in toggles.items():
        ui_field = TOGGLE_DB_TO_UI.get(db_col)
        if ui_field:
            settings[ui_field] = is_on

    # Full account row for Overview / Timer tabs
    account_data = read_account_data(account_id)

    return jsonify({
        'success': True,
        'device_serial': device_serial,
        'account': account,
        'settings': settings,
        'account_data': account_data,
    })


@bot_settings_bp.route('/<device_serial>/<account>', methods=['POST'])
def update_settings(device_serial, account):
    """Update settings for an account (partial update supported)."""
    account_id = get_account_id(device_serial, account)
    if account_id is None:
        return jsonify({
            'success': False,
            'error': f'Account not found: {device_serial}/{account}'
        }), 404

    try:
        new_settings = request.get_json()
        if not new_settings:
            return jsonify({'success': False, 'error': 'No settings provided'}), 400

        # ── 1. Extract & write master toggles to accounts table ──
        toggles_to_write = {}
        for ui_field, db_col in TOGGLE_UI_TO_DB.items():
            if ui_field in new_settings:
                toggles_to_write[db_col] = new_settings[ui_field]
        if toggles_to_write:
            write_account_toggles(account_id, toggles_to_write)

        # ── 1b. Sync start_time / end_time / instagram_package to accounts table ──
        time_fields = {}
        for field in ['start_time', 'end_time', 'instagram_package']:
            if field in new_settings:
                time_fields[field] = new_settings[field]
        if time_fields:
            conn = get_conn()
            try:
                updates = [f"{k} = ?" for k in time_fields.keys()]
                values = list(time_fields.values()) + [account_id]
                conn.execute(
                    f"UPDATE accounts SET {', '.join(updates)} WHERE id = ?",
                    values
                )
                conn.commit()
            finally:
                conn.close()

        # ── 2. Merge into settings JSON and write ──
        current_settings = read_settings_json(account_id)

        def deep_merge(base, updates):
            for key, value in updates.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    deep_merge(base[key], value)
                else:
                    base[key] = value
            return base

        merged = deep_merge(current_settings, new_settings)

        if write_settings_json(account_id, merged):
            return jsonify({
                'success': True,
                'message': 'Settings updated successfully',
                'settings': merged,
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to write settings'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# BULK COPY
# =============================================================================

# Category → settings-JSON fields (unchanged from original)
CATEGORY_FIELDS = {
    'like': [
        'enable_likepost', 'enable_like_reel', 'enable_like_exchange',
        'likepost_method', 'min_likepost_action', 'max_likepost_action',
        'like_limit_perday', 'enable_auto_increment_like_limit_perday',
        'auto_increment_like_limit_perday_increase',
        'auto_increment_like_limit_perday_increase_limit',
        'like_enable_filters', 'filters_like',
        'enable_dont_like_if_user_followed', 'enable_dont_like_sametag_accounts',
        'like_story_after_liking_post', 'like_reel_percent',
        'watch_reel_limit_perday', 'min_sec_reel_watch', 'max_sec_reel_watch',
        'min_post_to_like', 'max_post_to_like',
        'like_exchange_limit_perday',
        'enable_like_joborders',
        'enable_filter_seach_followers_like',
        'enable_delete_like_posts_specific_sources',
        'enable_random_like_post_after_follow_using_word_search',
        'story_like_peraccount_like_post',
    ],
    'comment': [
        'enable_comment', 'comment_method', 'comment_text',
        'min_comment', 'max_comment', 'comment_min_delay', 'comment_max_delay',
        'comment_limit_perday', 'enable_dont_comment_sametag_accounts',
        'enable_comment_joborders', 'follow_comment_text',
    ],
    'story': [
        'enable_story_viewer', 'view_method', 'story_viewer_min', 'story_viewer_max',
        'story_viewer_daily_limit', 'story_view_peraccount_view',
        'like_story_after_viewing', 'like_story_after_follow',
        'story_like_daily_limit', 'min_story_like_peraccount_view',
        'max_story_like_peraccount_view', 'story_like_peraccount',
        'dont_view_same_account_twice', 'view_highlight_if_no_story_viceversa',
        'enable_viewhomefeedstory', 'min_viewhomefeedstory', 'max_viewhomefeedstory',
        'percent_to_like_homefeedstory',
        'enable_filter_seach_followers_storyview',
        'enable_dont_delete_user_no_story',
        'view_story_directly_in_searchbox',
        'view_story_directly_in_searchbox_storyplus',
        'visit_profile_when_viewing_story_via_viewfollowers',
        'min_viewhomefeedstory_delay', 'max_viewhomefeedstory_delay',
    ],
    'dm': [
        'enable_directmessage', 'directmessage_method',
        'directmessage_min', 'directmessage_max',
        'directmessage_min_delay', 'directmessage_max_delay',
        'directmessage_daily_limit', 'message_check_delay',
        'enable_send_message_every_new_line',
        'enable_openai_dm', 'enable_cupidai_dm', 'enable_openai_assistant',
        'openai_assistant_id', 'directmessage_new_followers_limitperday',
        'directmessage_specific_user_limitperday',
        'dm_crm_limitperday',
        'enable_auto_increment_directmessage_daily_limit',
        'auto_increment_directmessage_daily_limit_increase',
        'auto_increment_directmessage_daily_limit_increase_limit',
        'enable_dm_requests',
        'enable_openai_assistant_dm_new_followers',
        'enable_openai_assistant_dm_reply',
        'enable_openai_assistant_dm_specific_user',
        'enable_send_dm_only_interacted_users',
        'enable_skip_if_dm_exists_directmessage_new_followers',
        'enable_skip_if_dm_exists_directmessage_specificuser',
    ],
    'follow': [
        'follow_method', 'default_action_limit_perday',
        'enable_auto_increment_follow_limit_perday',
        'auto_increment_action_limit_by', 'max_increment_action_limit',
        'last_increment_action_limit_date',
        'enable_random_action_limit_perday', 'random_action_limit_perday',
        'enable_reset_action_limit_perday_after_loli', 'reset_action_limit_perday_after_loli',
        'follow_timer_min_hour', 'follow_timer_max_hour',
        'follow_is_weekdays', 'enable_follow_is_weekdays',
        'enable_specific_follow_limit_perday', 'specific_follow_limit_perday',
        'mute_after_follow',
        'enable_filter_seach_followers_follow',
        'enable_name_must_include', 'enable_name_must_include_in_name',
        'enable_name_must_include_in_username', 'name_must_include_likes',
        'enable_name_must_not_include', 'name_must_not_include_likes',
        'enable_complete_follow_first_before_unfollowing',
        'enable_dont_follow_if_post_like',
        'enable_dont_follow_sametag_accounts',
        'enable_follow_only_if_story_exist',
        'enable_prioritize_follow_action',
        'like_story_after_follow',
        'enable_followings_limit', 'followings_limit',
        'dont_follow_private_accounts_using_followfollowers',
        'enable_random_like_when_following_using_followers',
        'enable_random_like_when_following_using_followspecificuser',
        'enable_random_like_when_follow_followers_own_followers',
        'scroll_profile_when_following_using_followfollowers',
        'scroll_profile_when_following_using_followspecificuser',
        'scroll_profile_when_follow_followers_own_followers',
        'visit_profile_when_following_using_followfollowers',
        'visit_profile_when_following_using_followlikers',
        'visit_profile_when_follow_followers_own_followers',
        'enable_follow_joborders',
        'follow_comment_text',
        'enable_random_comment_post_after_follow_using_word_search',
        'enable_random_like_post_after_follow_using_word_search',
    ],
    'unfollow': [
        'unfollow_method', 'unfollow_limit_perday',
        'enable_auto_increment_unfollow_limit_perday',
        'auto_increment_unfollow_limit_perday_increase',
        'auto_increment_unfollow_limit_perday_increase_limit',
        'unfollow_timer_min_hour', 'unfollow_timer_max_hour',
        'unfollow_is_weekdays', 'enable_specific_unfollow_limit_perday',
        'specific_unfollow_limit_perday', 'unfollow_delay_day',
        'dont_unfollow_followers',
        'enable_prioritize_unfollow_action',
        'enable_unfollow_specific_accounts',
        'enable_follow_if_no_users_to_unfollow',
        'enable_remove_followings',
        'remove_followers',
    ],
    'filters': [
        'enable_filters', 'filters',
    ],
    'reels': [
        'enable_watch_reels', 'min_reels_to_watch', 'max_reels_to_watch',
        'min_sec_reel_watch', 'max_sec_reel_watch',
        'watch_reel_limit_perday', 'enable_save_reels_after_watching',
        'enable_like_reel', 'like_reel_percent',
    ],
    'share': [
        'enable_shared_post', 'enable_share_post_to_story', 'enable_repost_post',
        'post_type_to_share', 'min_sec_share_reel_watch', 'max_sec_share_reel_watch',
        'enable_add_link_to_story', 'custom_link_text', 'link_to_story',
        'enable_mention_to_story', 'sharepost_mention',
        'shared_post_limit_persource_perday', 'shared_post_limit_perday',
    ],
    'hbe': [
        'enable_human_behaviour_emulation',
        'enable_viewhomefeedstory', 'min_viewhomefeedstory', 'max_viewhomefeedstory',
        'min_viewhomefeedstory_delay', 'max_viewhomefeedstory_delay',
        'percent_to_like_homefeedstory',
        'enable_scrollhomefeed', 'min_scrollhomefeed', 'max_scrollhomefeed',
        'min_scrollhomefeed_delay', 'max_scrollhomefeed_delay',
        'percent_to_like_homefeed',
        'enable_scrollexplorepage', 'min_scrollexplorepage', 'max_scrollexplorepage',
        'min_scrollexplorepage_delay', 'max_scrollexplorepage_delay',
        'percent_to_like_explorepagepost',
    ],
    'post': [
        'enable_scheduled_post',
    ],
}

# Category → which toggle DB columns to copy
CATEGORY_TOGGLES = {
    'like':     ['like_enabled'],
    'comment':  ['comment_enabled'],
    'story':    ['story_enabled'],
    'follow':   ['follow_enabled'],
    'unfollow': ['unfollow_enabled'],
}


@bot_settings_bp.route('/bulk', methods=['POST'])
def bulk_update_settings():
    """Copy settings from one account to multiple accounts."""
    try:
        data = request.get_json()
        source  = data.get('source')
        targets = data.get('targets', [])
        categories = data.get('categories', 'all')

        if not source or not targets:
            return jsonify({'success': False, 'error': 'Source and targets are required'}), 400

        src_id = get_account_id(source['device'], source['account'])
        if src_id is None:
            return jsonify({'success': False, 'error': 'Source account not found'}), 404

        source_settings = read_settings_json(src_id)
        source_toggles  = read_account_toggles(src_id)

        if not source_settings:
            return jsonify({'success': False, 'error': 'Could not read settings from source account'}), 404

        # Determine fields & toggles to copy
        if categories == 'all':
            fields_to_copy = set()
            for cat_fields in CATEGORY_FIELDS.values():
                fields_to_copy.update(cat_fields)
            toggles_to_copy = set(TOGGLE_COLUMNS)
        else:
            fields_to_copy = set()
            toggles_to_copy = set()
            for cat in categories:
                if cat in CATEGORY_FIELDS:
                    fields_to_copy.update(CATEGORY_FIELDS[cat])
                if cat in CATEGORY_TOGGLES:
                    toggles_to_copy.update(CATEGORY_TOGGLES[cat])

        results = []
        for target in targets:
            tgt_id = get_account_id(target['device'], target['account'])
            if tgt_id is None:
                results.append({'device': target['device'], 'account': target['account'],
                                'success': False, 'error': 'Account not found'})
                continue

            target_settings = read_settings_json(tgt_id)

            # Copy selected fields
            for field in fields_to_copy:
                if field in source_settings:
                    target_settings[field] = source_settings[field]

            settings_ok = write_settings_json(tgt_id, target_settings)

            # Copy toggles
            toggles_ok = True
            if toggles_to_copy and source_toggles:
                tgt_toggles = {col: source_toggles[col] for col in toggles_to_copy if col in source_toggles}
                if tgt_toggles:
                    toggles_ok = write_account_toggles(tgt_id, tgt_toggles)

            results.append({
                'device': target['device'],
                'account': target['account'],
                'success': settings_ok and toggles_ok,
                **({}  if (settings_ok and toggles_ok) else {'error': 'Failed to write settings or toggles'}),
            })

        successful = sum(1 for r in results if r['success'])
        return jsonify({
            'success': True,
            'message': f'Copied settings to {successful}/{len(targets)} accounts',
            'results': results,
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# LISTS  (account_sources)
# =============================================================================

@bot_settings_bp.route('/<device_serial>/<account>/lists/<list_type>', methods=['GET'])
def get_list(device_serial, account, list_type):
    """Get a text list for an account."""
    if list_type not in LIST_FILE_MAPPING:
        return jsonify({
            'success': False,
            'error': f'Unknown list type: {list_type}',
            'valid_types': list(LIST_FILE_MAPPING.keys()),
        }), 400

    account_id = get_account_id(device_serial, account)
    if account_id is None:
        return jsonify({'success': False, 'error': f'Account not found: {device_serial}/{account}'}), 404

    items = read_text_list(account_id, list_type)
    return jsonify({
        'success': True,
        'list_type': list_type,
        'filename': LIST_FILE_MAPPING[list_type],
        'items': items,
        'count': len(items),
    })


@bot_settings_bp.route('/<device_serial>/<account>/lists/<list_type>', methods=['POST'])
def update_list(device_serial, account, list_type):
    """Update a text list for an account.  Body: {"items": [...]}"""
    if list_type not in LIST_FILE_MAPPING:
        return jsonify({'success': False, 'error': f'Unknown list type: {list_type}'}), 400

    account_id = get_account_id(device_serial, account)
    if account_id is None:
        return jsonify({'success': False, 'error': f'Account not found: {device_serial}/{account}'}), 404

    try:
        items = request.get_json().get('items', [])
        if write_text_list(account_id, list_type, items):
            return jsonify({'success': True, 'message': f'Updated {list_type}', 'count': len(items)})
        return jsonify({'success': False, 'error': 'Failed to write list'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# PROMPTS  (account_text_configs)
# =============================================================================

@bot_settings_bp.route('/<device_serial>/<account>/prompts/<prompt_type>', methods=['GET'])
def get_prompt(device_serial, account, prompt_type):
    """Get a GPT prompt for an account."""
    if prompt_type not in PROMPT_FILE_MAPPING:
        return jsonify({
            'success': False,
            'error': f'Unknown prompt type: {prompt_type}',
            'valid_types': list(PROMPT_FILE_MAPPING.keys()),
        }), 400

    account_id = get_account_id(device_serial, account)
    if account_id is None:
        return jsonify({'success': False, 'error': f'Account not found: {device_serial}/{account}'}), 404

    content = read_text_file(account_id, prompt_type)
    return jsonify({
        'success': True,
        'prompt_type': prompt_type,
        'filename': PROMPT_FILE_MAPPING[prompt_type],
        'content': content,
    })


@bot_settings_bp.route('/<device_serial>/<account>/prompts/<prompt_type>', methods=['POST'])
def update_prompt(device_serial, account, prompt_type):
    """Update a GPT prompt.  Body: {"content": "..."}"""
    if prompt_type not in PROMPT_FILE_MAPPING:
        return jsonify({'success': False, 'error': f'Unknown prompt type: {prompt_type}'}), 400

    account_id = get_account_id(device_serial, account)
    if account_id is None:
        return jsonify({'success': False, 'error': f'Account not found: {device_serial}/{account}'}), 404

    try:
        content = request.get_json().get('content', '')
        if write_text_file(account_id, prompt_type, content):
            return jsonify({'success': True, 'message': f'Updated {prompt_type}'})
        return jsonify({'success': False, 'error': 'Failed to write prompt'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# METADATA ENDPOINTS
# =============================================================================

@bot_settings_bp.route('/list-types', methods=['GET'])
def get_list_types():
    return jsonify({'success': True, 'list_types': LIST_FILE_MAPPING})


@bot_settings_bp.route('/prompt-types', methods=['GET'])
def get_prompt_types():
    return jsonify({'success': True, 'prompt_types': PROMPT_FILE_MAPPING})


# =============================================================================
# ACCOUNTS TREE  (for bulk-selection UI)
# =============================================================================

@bot_settings_bp.route('/accounts-tree', methods=['GET'])
def get_accounts_tree():
    """Hierarchical list of all devices → accounts from phone_farm.db."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT device_serial, username FROM accounts ORDER BY device_serial, username"
        ).fetchall()

        devices = {}
        for r in rows:
            ds = r['device_serial']
            devices.setdefault(ds, []).append(r['username'])

        devices_tree = [{'device_serial': ds, 'accounts': accts} for ds, accts in devices.items()]

        return jsonify({
            'success': True,
            'devices': devices_tree,
            'total_devices': len(devices_tree),
            'total_accounts': sum(len(d['accounts']) for d in devices_tree),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


# =============================================================================
# DEBUG ENDPOINT
# =============================================================================

@bot_settings_bp.route('/debug/<device_serial>/<account>', methods=['GET'])
def debug_account_data(device_serial, account):
    """Debug endpoint – raw data from phone_farm.db."""
    account_id = get_account_id(device_serial, account)

    result = {
        'device_serial': device_serial,
        'account': account,
        'account_id': account_id,
    }

    if account_id is None:
        # List accounts on this device for troubleshooting
        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT username FROM accounts WHERE device_serial = ?", (device_serial,)
            ).fetchall()
            result['error'] = f'Account {account} not found'
            result['available_accounts'] = [r['username'] for r in rows]
        finally:
            conn.close()
        return jsonify(result), 404

    result['toggles'] = read_account_toggles(account_id)
    result['account_data'] = read_account_data(account_id)

    settings = read_settings_json(account_id)
    result['settings_key_count'] = len(settings)
    result['settings_sample_keys'] = sorted(settings.keys())[:20]

    return jsonify(result)
