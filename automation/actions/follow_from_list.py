"""
Follow From List Action Module
================================
Follow users from a pre-built follow list.
Each username is searched individually, profile visited, then followed.

Flow:
1. Check daily follow limit
2. Get next N pending items from follow_list_items WHERE list_id=X AND status='pending'
3. For each username:
   a. Tag dedup check (if enabled): skip if same-tag account already followed
   b. Recently followed check: skip if in action_history last 14 days
   c. search_user(username) via IGController
   d. If found: check filters, then follow_user_from_profile()
   e. Update follow_list_items status (followed/skipped/error)
   f. Log to action_history
   g. Human-like delay between follows
4. Return results dict
"""

import logging
import random
import time
import datetime

from automation.actions.helpers import (
    action_delay, random_sleep, log_action, get_db,
    get_account_settings, get_today_action_count,
    get_recently_interacted, check_filters
)
from automation.ig_controller import IGController, Screen
from automation.tag_dedup import is_tag_dedup_enabled, get_same_tag_followed_set

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB Helpers for follow lists
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# CRUD helpers (used by dashboard/follow_list_routes.py)
# ---------------------------------------------------------------------------

def create_follow_list(name, description=''):
    """Create a new follow list. Returns list_id."""
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO follow_lists (name, description) VALUES (?, ?)",
            (name, description))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_follow_lists():
    """Get all follow lists with item counts."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT fl.*,
                   COUNT(fli.id) AS total_items,
                   SUM(CASE WHEN fli.status = 'pending' THEN 1 ELSE 0 END) AS pending,
                   SUM(CASE WHEN fli.status = 'followed' THEN 1 ELSE 0 END) AS followed,
                   SUM(CASE WHEN fli.status = 'skipped' THEN 1 ELSE 0 END) AS skipped
            FROM follow_lists fl
            LEFT JOIN follow_list_items fli ON fli.list_id = fl.id
            GROUP BY fl.id
            ORDER BY fl.created_at DESC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_follow_list(list_id):
    """Get a single follow list with stats. Returns dict or None."""
    conn = get_db()
    try:
        row = conn.execute("""
            SELECT fl.*,
                   COUNT(fli.id) AS total_items,
                   SUM(CASE WHEN fli.status = 'pending' THEN 1 ELSE 0 END) AS pending,
                   SUM(CASE WHEN fli.status = 'followed' THEN 1 ELSE 0 END) AS followed
            FROM follow_lists fl
            LEFT JOIN follow_list_items fli ON fli.list_id = fl.id
            WHERE fl.id = ?
            GROUP BY fl.id
        """, (list_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_follow_list(list_id, name=None, description=None):
    """Update a follow list's name/description. Returns True on success."""
    conn = get_db()
    try:
        parts, params = [], []
        if name is not None:
            parts.append("name = ?"); params.append(name)
        if description is not None:
            parts.append("description = ?"); params.append(description)
        if not parts:
            return False
        parts.append("updated_at = datetime('now')")
        params.append(list_id)
        conn.execute(f"UPDATE follow_lists SET {', '.join(parts)} WHERE id = ?", params)
        conn.commit()
        return True
    except Exception as e:
        log.error("Failed to update follow list %d: %s", list_id, e)
        return False
    finally:
        conn.close()


def delete_follow_list(list_id):
    """Delete a follow list and all its items."""
    conn = get_db()
    try:
        conn.execute("DELETE FROM follow_list_items WHERE list_id = ?", (list_id,))
        conn.execute("DELETE FROM follow_lists WHERE id = ?", (list_id,))
        conn.commit()
    finally:
        conn.close()


def get_list_items(list_id, status=None):
    """Get items from a follow list, optionally filtered by status."""
    conn = get_db()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM follow_list_items WHERE list_id = ? AND status = ? ORDER BY id",
                (list_id, status)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM follow_list_items WHERE list_id = ? ORDER BY id",
                (list_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_list_items(list_id, usernames):
    """Add usernames to a follow list. Strips @, deduplicates. Returns count actually inserted."""
    conn = get_db()
    added = 0
    try:
        for u in usernames:
            clean = u.strip().lstrip('@').strip()
            if not clean:
                continue
            try:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO follow_list_items (list_id, username) VALUES (?, ?)",
                    (list_id, clean))
                if cur.rowcount > 0:
                    added += 1
            except Exception:
                pass
        conn.commit()
        return added
    finally:
        conn.close()


def remove_list_item(item_id):
    """Remove a single item from a list."""
    conn = get_db()
    try:
        conn.execute("DELETE FROM follow_list_items WHERE id = ?", (item_id,))
        conn.commit()
    finally:
        conn.close()


def clear_list_items(list_id):
    """Delete all items from a list."""
    conn = get_db()
    try:
        conn.execute("DELETE FROM follow_list_items WHERE list_id = ?", (list_id,))
        conn.commit()
    finally:
        conn.close()


def reset_list_items(list_id):
    """Reset all items in a list back to 'pending' status."""
    conn = get_db()
    try:
        conn.execute("""
            UPDATE follow_list_items 
            SET status = 'pending', followed_by_account_id = NULL, 
                followed_at = NULL, skip_reason = NULL
            WHERE list_id = ?
        """, (list_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Action helpers (used by FollowFromListAction internally)
# ---------------------------------------------------------------------------

def get_pending_items(list_id, limit=50):
    """Get pending items from a follow list."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT id, username FROM follow_list_items
            WHERE list_id = ? AND status = 'pending'
            ORDER BY id ASC
            LIMIT ?
        """, (list_id, limit)).fetchall()
        return [{'id': r['id'], 'username': r['username']} for r in rows]
    except Exception as e:
        log.error("Failed to get pending items for list %d: %s", list_id, e)
        return []
    finally:
        conn.close()


def update_item_status(item_id, status, account_id=None, skip_reason=None):
    """Update a follow_list_items row after processing."""
    conn = get_db()
    try:
        now = datetime.datetime.now().isoformat()
        if status == 'followed':
            conn.execute("""
                UPDATE follow_list_items
                SET status = ?, followed_by_account_id = ?, followed_at = ?, skip_reason = NULL
                WHERE id = ?
            """, (status, account_id, now, item_id))
        else:
            conn.execute("""
                UPDATE follow_list_items
                SET status = ?, skip_reason = ?
                WHERE id = ?
            """, (status, skip_reason, item_id))
        conn.commit()
    except Exception as e:
        log.error("Failed to update item %d status: %s", item_id, e)
    finally:
        conn.close()


def get_follow_list_info(list_id):
    """Get basic info about a follow list. Returns dict or None."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM follow_lists WHERE id = ?", (list_id,)
        ).fetchone()
        return dict(row) if row else None
    except Exception as e:
        log.error("Failed to get follow list %d: %s", list_id, e)
        return None
    finally:
        conn.close()


class FollowFromListAction:
    """
    Follow users from a follow list.
    Searches each user individually, visits their profile, and follows.
    """

    def __init__(self, device, device_serial, account_info, session_id,
                 list_id, package='com.instagram.androie'):
        self.device = device
        self.device_serial = device_serial
        self.account = account_info
        self.session_id = session_id
        self.username = account_info['username']
        self.account_id = account_info['id']
        self.list_id = list_id

        # IGController for reliable UI
        pkg = account_info.get('package', package)
        self.ctrl = IGController(device, device_serial, pkg)

        # Load settings
        self.settings = get_account_settings(self.account_id)
        self.filters = self.settings.get('filters', {})
        self.use_filters = self.settings.get('enable_filters', False)

        # Tag-based follow dedup (same pattern as FollowAction)
        # Uses tag_dedup.py — reads enable_tags + enable_dont_follow_sametag_accounts
        # + tags from settings_json
        self.tag_dedup_enabled = is_tag_dedup_enabled(self.account_id)
        self.tag_already_followed = set()
        if self.tag_dedup_enabled:
            self.tag_already_followed = get_same_tag_followed_set(self.account_id)
            log.info("[%s] Tag dedup ON — %d targets already followed by same-tag peers",
                     self.device_serial, len(self.tag_already_followed))

        # Limits (same pattern as FollowAction)
        self._init_limits()

    def _init_limits(self):
        """Initialize follow limits from account settings."""
        raw_limit = self.account.get('follow_limit_perday', '0')
        if raw_limit and raw_limit not in ('deprecated', 'None', ''):
            self.daily_limit = int(raw_limit) if str(raw_limit).isdigit() else 0
        else:
            self.daily_limit = 0

        if self.daily_limit <= 0:
            self.daily_limit = int(self.settings.get('default_action_limit_perday', '28'))

        follow_action = self.account.get('follow_action', '10,20')
        if ',' in str(follow_action):
            parts = str(follow_action).split(',')
            try:
                self.session_min = int(parts[0])
                self.session_max = int(parts[1])
            except (ValueError, IndexError):
                self.session_min = 10
                self.session_max = 20
        else:
            self.session_min = 10
            self.session_max = 20

        if self.session_min <= 0:
            self.session_min = 10
        if self.session_max <= 0:
            self.session_max = 20

        self.session_target = random.randint(self.session_min, self.session_max)
        log.info("[%s] FollowFromList limits: daily=%d, session_target=%d (range %d-%d), list_id=%d",
                 self.device_serial, self.daily_limit, self.session_target,
                 self.session_min, self.session_max, self.list_id)

    def execute(self):
        """
        Execute the follow-from-list action.
        Returns dict: {success, follows_done, errors, skipped, list_id, list_name}
        """
        result = {
            'success': False,
            'follows_done': 0,
            'errors': 0,
            'skipped': 0,
            'list_id': self.list_id,
            'list_name': '',
        }

        # Validate the list exists
        list_info = get_follow_list_info(self.list_id)
        if not list_info:
            log.error("[%s] Follow list %d not found", self.device_serial, self.list_id)
            return result
        result['list_name'] = list_info['name']

        # Ensure Instagram is running
        self.ctrl.ensure_app()
        self.ctrl.dismiss_popups()

        # Check daily limit (shared with regular follow action)
        done_today = get_today_action_count(
            self.device_serial, self.username, 'follow')
        remaining = self.daily_limit - done_today
        if remaining <= 0:
            log.info("[%s] %s: Daily follow limit reached (%d/%d)",
                     self.device_serial, self.username, done_today, self.daily_limit)
            result['success'] = True
            return result

        target = min(self.session_target, remaining)
        log.info("[%s] %s: Will follow up to %d users from list '%s' (done today: %d, daily limit: %d)",
                 self.device_serial, self.username, target,
                 list_info['name'], done_today, self.daily_limit)

        # Get recently followed users to skip
        recently_followed = get_recently_interacted(
            self.device_serial, self.username, 'follow', days=14)
        log.info("[%s] Recently followed: %d users (will skip)",
                 self.device_serial, len(recently_followed))

        # Get pending items from the list
        pending_items = get_pending_items(self.list_id, limit=target + 20)
        if not pending_items:
            log.info("[%s] No pending items in list '%s'",
                     self.device_serial, list_info['name'])
            result['success'] = True
            return result

        log.info("[%s] Loaded %d pending items from list '%s'",
                 self.device_serial, len(pending_items), list_info['name'])

        # Process each pending item
        for item in pending_items:
            if result['follows_done'] >= target:
                break

            item_id = item['id']
            target_user = item['username'].strip().lower()

            if not target_user:
                update_item_status(item_id, 'error', skip_reason='empty_username')
                continue

            # Skip own username
            if target_user == self.username.lower():
                update_item_status(item_id, 'skipped', skip_reason='own_account')
                result['skipped'] += 1
                continue

            # Recently followed check
            if target_user in recently_followed:
                log.debug("[%s] Skip @%s (recently followed)",
                          self.device_serial, target_user)
                update_item_status(item_id, 'skipped', skip_reason='recently_followed')
                result['skipped'] += 1
                continue

            # Tag dedup check (same pattern as FollowAction)
            if self.tag_dedup_enabled and target_user in self.tag_already_followed:
                log.debug("[%s] Skip @%s (tag dedup — already followed by same-tag peer)",
                          self.device_serial, target_user)
                update_item_status(item_id, 'skipped', skip_reason='tag_dedup')
                result['skipped'] += 1
                continue

            # Search and follow this user
            try:
                follow_result = self._search_and_follow(target_user)

                if follow_result is True:
                    # Success
                    update_item_status(item_id, 'followed',
                                       account_id=self.account_id)
                    log_action(
                        self.session_id, self.device_serial, self.username,
                        'follow', target_username=target_user, success=True)
                    result['follows_done'] += 1
                    recently_followed.add(target_user)
                    # Also add to tag dedup set for this session
                    if self.tag_dedup_enabled:
                        self.tag_already_followed.add(target_user)
                    log.info("[%s] Followed @%s from list (%d/%d)",
                             self.device_serial, target_user,
                             result['follows_done'], target)
                    action_delay("follow")

                elif follow_result is False:
                    # Skipped (already following, filtered, etc.)
                    update_item_status(item_id, 'skipped',
                                       skip_reason='filtered_or_already_following')
                    result['skipped'] += 1

                else:  # None = error
                    update_item_status(item_id, 'error',
                                       skip_reason='user_not_found_or_ui_error')
                    log_action(
                        self.session_id, self.device_serial, self.username,
                        'follow', target_username=target_user, success=False,
                        error_message='search_or_follow_failed')
                    result['errors'] += 1

            except Exception as e:
                log.error("[%s] Error following @%s from list: %s",
                          self.device_serial, target_user, e)
                update_item_status(item_id, 'error',
                                   skip_reason=str(e)[:200])
                log_action(
                    self.session_id, self.device_serial, self.username,
                    'follow', target_username=target_user, success=False,
                    error_message=str(e)[:200])
                result['errors'] += 1
                self._recover()

        result['success'] = True
        log.info("[%s] %s: FollowFromList complete. Followed: %d, Skipped: %d, Errors: %d",
                 self.device_serial, self.username,
                 result['follows_done'], result['skipped'], result['errors'])
        return result

    def _search_and_follow(self, target_username):
        """
        Search for a user, visit their profile, optionally apply filters, and follow.

        Returns:
            True  = followed successfully
            False = skipped (already following, filtered out)
            None  = error (user not found, UI issue)
        """
        # Dismiss any lingering popups
        self.ctrl.dismiss_popups()

        # Search for user
        if not self.ctrl.search_user(target_username):
            log.warning("[%s] Could not find @%s via search",
                        self.device_serial, target_username)
            return None

        random_sleep(2, 4, label="on_target_profile")

        # Dismiss any popups on profile
        screen = self.ctrl.detect_screen()
        if screen == Screen.POPUP:
            self.ctrl.dismiss_popups()
            time.sleep(1)

        # Check filters if enabled
        if self.use_filters and self.filters:
            profile_info = self.ctrl.get_profile_info()
            passed, reason = check_filters(profile_info, self.filters)
            if not passed:
                log.debug("[%s] @%s filtered: %s",
                          self.device_serial, target_username, reason)
                self.ctrl.press_back()
                time.sleep(1)
                return False

        # Follow from profile
        result = self.ctrl.follow_user_from_profile()

        # Navigate back to clean state
        self.ctrl.press_back()
        time.sleep(1)

        if result is True:
            return True
        elif result is False:
            return False

        # Could not find follow button
        log.debug("[%s] Follow button not found for @%s",
                  self.device_serial, target_username)
        self.ctrl.dump_xml("follow_from_list_btn_missing_" + target_username)
        return None

    def _recover(self):
        """Try to recover to a known UI state."""
        try:
            self.ctrl.recover_to_home()
        except Exception:
            pass


def execute_follow_from_list(device, device_serial, account_info, session_id, list_id):
    """Convenience function to run follow-from-list action."""
    action = FollowFromListAction(device, device_serial, account_info,
                                   session_id, list_id)
    return action.execute()
