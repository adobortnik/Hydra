"""
Shared Helpers for Bot Actions
================================
Common utilities: random delays, DB logging, UI navigation, profile parsing.
"""

import logging
import random
import re
import subprocess
import time
import datetime
import json

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DB_PATH = None  # Set at module load

def _get_db_path():
    import os
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "db", "phone_farm.db")


# ---------------------------------------------------------------------------
# Random Delays (human-like)
# ---------------------------------------------------------------------------

def random_sleep(min_sec=2.0, max_sec=5.0, label=""):
    """Sleep for a random duration between min and max seconds."""
    duration = random.uniform(min_sec, max_sec)
    if label:
        log.debug("[delay] %s: %.1fs", label, duration)
    time.sleep(duration)
    return duration


def action_delay(action_type="default"):
    """Human-like delay between major actions."""
    delays = {
        "follow": (8, 20),
        "unfollow": (5, 15),
        "like": (3, 8),
        "story_view": (4, 10),
        "scroll": (2, 5),
        "navigate": (1.5, 3),
        "default": (3, 8),
    }
    lo, hi = delays.get(action_type, delays["default"])
    return random_sleep(lo, hi, label=action_type)


# ---------------------------------------------------------------------------
# DB Helpers
# ---------------------------------------------------------------------------

def get_db():
    """Get a thread-safe DB connection."""
    import sqlite3
    path = _get_db_path()
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def log_action(session_id, device_serial, username, action_type,
               target_username=None, target_post_id=None, success=True,
               error_message=None):
    """Log an action to action_history table."""
    try:
        conn = get_db()
        now = datetime.datetime.now().isoformat()
        conn.execute("""
            INSERT INTO action_history
                (session_id, device_serial, username, action_type,
                 target_username, target_post_id, success, timestamp, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, device_serial, username, action_type,
              target_username, target_post_id, 1 if success else 0,
              now, error_message))
        conn.commit()
        conn.close()
    except Exception as e:
        log.error("Failed to log action: %s", e)


def create_session(device_serial, username):
    """Create a new bot session, return session_id."""
    try:
        conn = get_db()
        now = datetime.datetime.now().isoformat()
        cursor = conn.execute("""
            INSERT INTO account_sessions
                (device_serial, username, session_start, status)
            VALUES (?, ?, ?, 'running')
        """, (device_serial, username, now))
        conn.commit()
        session_id = cursor.lastrowid
        conn.close()
        return session_id
    except Exception as e:
        log.error("Failed to create session: %s", e)
        return None


def end_session(session_id, status="completed", actions_executed=None, errors_count=0,
                error_details=None):
    """End a bot session."""
    try:
        conn = get_db()
        now = datetime.datetime.now().isoformat()
        conn.execute("""
            UPDATE account_sessions
            SET session_end=?, status=?, actions_executed=?,
                errors_count=?, error_details=?
            WHERE id=?
        """, (now, status, actions_executed, errors_count, error_details, session_id))
        conn.commit()
        conn.close()
    except Exception as e:
        log.error("Failed to end session: %s", e)


def get_account_settings(account_id):
    """Get parsed settings JSON for an account."""
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT settings_json FROM account_settings WHERE account_id=?",
            (account_id,)
        ).fetchone()
        conn.close()
        if row:
            return json.loads(row['settings_json'])
        return {}
    except Exception as e:
        log.error("Failed to get account settings: %s", e)
        return {}


def get_account_sources(account_id, source_type='sources'):
    """Get source values for an account."""
    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT value FROM account_sources WHERE account_id=? AND source_type=?",
            (account_id, source_type)
        ).fetchall()
        conn.close()
        return [r['value'] for r in rows]
    except Exception as e:
        log.error("Failed to get account sources: %s", e)
        return []


def get_today_action_count(device_serial, username, action_type):
    """Count actions of a given type done today."""
    try:
        conn = get_db()
        today = datetime.date.today().isoformat()
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM action_history
            WHERE device_serial=? AND username=? AND action_type=?
              AND timestamp >= ? AND success=1
        """, (device_serial, username, action_type, today)).fetchone()
        conn.close()
        return row['cnt'] if row else 0
    except Exception as e:
        log.error("Failed to get action count: %s", e)
        return 0


def get_recently_interacted(device_serial, username, action_type, days=7):
    """Get target usernames we've already interacted with recently."""
    try:
        conn = get_db()
        since = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT DISTINCT target_username FROM action_history
            WHERE device_serial=? AND username=? AND action_type=?
              AND timestamp >= ? AND success=1
              AND target_username IS NOT NULL
        """, (device_serial, username, action_type, since)).fetchall()
        conn.close()
        return {r['target_username'] for r in rows}
    except Exception as e:
        log.error("Failed to get recently interacted: %s", e)
        return set()


# ---------------------------------------------------------------------------
# Dead Source Tracking
# ---------------------------------------------------------------------------

def check_dead_source(account_username, source_username):
    """
    Check if a source is marked dead (fail_count >= 3, status='dead').
    Returns the row dict if dead, None otherwise.
    Also implements weekly auto-retry: if last_failed_at > 7 days ago, allow retry.
    """
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM dead_sources WHERE account_username=? AND source_username=? AND status='dead'",
            (account_username, source_username)
        ).fetchone()
        conn.close()
        if row:
            # Check weekly auto-retry: if last_failed_at > 7 days ago, allow retry
            last_failed = row['last_failed_at']
            if last_failed:
                from datetime import datetime, timedelta
                try:
                    last_dt = datetime.fromisoformat(last_failed)
                    if datetime.now() - last_dt > timedelta(days=7):
                        log.info("Dead source @%s eligible for weekly retry (last failed: %s)",
                                 source_username, last_failed)
                        return None  # Allow retry
                except (ValueError, TypeError):
                    pass
            return dict(row)
        return None
    except Exception as e:
        log.error("Failed to check dead source: %s", e)
        return None


def record_dead_source(account_username, source_username):
    """
    Record a failed source search. Upserts into dead_sources.
    If fail_count reaches 3, sets status to 'dead'.
    """
    try:
        conn = get_db()
        now = datetime.datetime.now().isoformat()
        # Try to upsert
        conn.execute("""
            INSERT INTO dead_sources (account_username, source_username, fail_count,
                                      first_failed_at, last_failed_at, status)
            VALUES (?, ?, 1, ?, ?, 'suspect')
            ON CONFLICT(account_username, source_username) DO UPDATE SET
                fail_count = fail_count + 1,
                last_failed_at = ?,
                status = CASE WHEN fail_count + 1 >= 3 THEN 'dead' ELSE status END
        """, (account_username, source_username, now, now, now))
        conn.commit()

        # Check current state for logging
        row = conn.execute(
            "SELECT fail_count, status FROM dead_sources WHERE account_username=? AND source_username=?",
            (account_username, source_username)
        ).fetchone()
        conn.close()

        if row:
            if row['status'] == 'dead':
                log.warning("Source @%s is now DEAD for @%s (failed %d times)",
                            source_username, account_username, row['fail_count'])
            else:
                log.info("Source @%s failed for @%s (%d/3 before dead)",
                         source_username, account_username, row['fail_count'])
    except Exception as e:
        log.error("Failed to record dead source: %s", e)


def clear_dead_source(account_username, source_username):
    """
    Remove a source from dead_sources (it's alive again).
    Called when a previously-failed source is found successfully.
    """
    try:
        conn = get_db()
        deleted = conn.execute(
            "DELETE FROM dead_sources WHERE account_username=? AND source_username=?",
            (account_username, source_username)
        ).rowcount
        conn.commit()
        conn.close()
        if deleted:
            log.info("Source @%s is ALIVE again for @%s — removed from dead sources",
                     source_username, account_username)
    except Exception as e:
        log.error("Failed to clear dead source: %s", e)


# ---------------------------------------------------------------------------
# Instagram UI Navigation Helpers
# ---------------------------------------------------------------------------

class IGNavigator:
    """
    Instagram UI navigation via uiautomator2.
    Works with any IG clone package.
    """

    def __init__(self, device, device_serial):
        self.device = device
        self.device_serial = device_serial
        self.adb_serial = device_serial.replace('_', ':')

    def go_home(self):
        """Navigate to home feed tab. Uses confirmed resource IDs from XML."""
        selectors = [
            self.device(resourceIdMatches=".*feed_tab$"),
            self.device(description="Home"),
        ]
        for sel in selectors:
            if sel.exists(timeout=3):
                sel.click()
                time.sleep(2)
                return True
        return False

    def go_profile(self):
        """Navigate to profile tab. Uses confirmed resource IDs from XML."""
        selectors = [
            self.device(resourceIdMatches=".*profile_tab$"),
            self.device(description="Profile"),
        ]
        for sel in selectors:
            if sel.exists(timeout=3):
                sel.click()
                time.sleep(2)
                return True
        # Fallback: bottom-right corner
        try:
            w, h = self.device.window_size()
            self.device.click(int(w * 0.9), int(h * 0.95))
            time.sleep(2)
            return True
        except Exception:
            return False

    def go_search(self):
        """Navigate to search/explore tab. Uses confirmed resource IDs from XML."""
        selectors = [
            self.device(resourceIdMatches=".*search_tab$"),
            self.device(description="Search and explore"),
            self.device(descriptionContains="Search"),
        ]
        for sel in selectors:
            if sel.exists(timeout=2):
                sel.click()
                time.sleep(2)
                return True
        return False

    def search_user(self, username):
        """
        Search for a user and open their profile.
        Returns True if profile opened successfully.
        """
        if not self.go_search():
            log.warning("[%s] Could not navigate to search", self.device_serial)
            return False

        time.sleep(1)

        # Click on search bar - try package-agnostic patterns
        search_bar = self.device(resourceIdMatches=".*action_bar_search_edit_text.*")
        if not search_bar.exists(timeout=3):
            search_bar = self.device(resourceIdMatches=".*search_edit_text.*")
        if not search_bar.exists(timeout=3):
            search_bar = self.device(className="android.widget.EditText")
        if not search_bar.exists(timeout=3):
            # Click on top area where search bar usually is
            w, h = self.device.window_size()
            self.device.click(w // 2, int(h * 0.08))
            time.sleep(1)
            search_bar = self.device(className="android.widget.EditText")

        if search_bar.exists(timeout=3):
            search_bar.click()
            time.sleep(1)
            search_bar.clear_text()
            time.sleep(0.5)

            # Type username via ADB for reliability
            subprocess.run(
                ['adb', '-s', self.adb_serial, 'shell', 'input', 'text', username],
                capture_output=True, timeout=10
            )
            time.sleep(3)

            # Find and click the user in results - try specific IG resource IDs first
            user_row = self.device(resourceIdMatches=".*row_search_user_username.*",
                                   textContains=username)
            if user_row.exists(timeout=3):
                user_row.click()
                time.sleep(3)
                return True

            # Fallback: any text containing the username
            user_row = self.device(textContains=username)
            if user_row.exists(timeout=5):
                user_row.click()
                time.sleep(3)
                return True

            # Try matching exact username in the search results
            user_exact = self.device(text=username)
            if user_exact.exists(timeout=3):
                user_exact.click()
                time.sleep(3)
                return True

            log.warning("[%s] User '%s' not found in search results",
                       self.device_serial, username)
            return False

        log.warning("[%s] Could not find search bar", self.device_serial)
        return False

    def open_followers_list(self):
        """
        From a profile page, open the followers list.
        Uses confirmed selectors from XML dumps.
        Returns True on success.
        """
        selectors = [
            # CONFIRMED working: stacked familiar layout (content-desc="7.3Mfollowers")
            self.device(resourceIdMatches=".*profile_header_followers_stacked_familiar.*"),
            # Followers value text (clickable parent)
            self.device(resourceIdMatches=".*profile_header_familiar_followers_value.*"),
            # Content-desc based (matches "698Mfollowers" etc)
            self.device(descriptionMatches=".*\\d+.*follower.*"),
            # Classic GramAddict patterns
            self.device(resourceIdMatches=".*row_profile_header_followers_container.*"),
            self.device(resourceIdMatches=".*row_profile_header_textview_followers_count.*"),
            # Text-based fallbacks
            self.device(textContains="followers"),
        ]
        for sel in selectors:
            if sel.exists(timeout=2):
                sel.click()
                time.sleep(3)
                return True

        return False

    def open_following_list(self):
        """
        From a profile page, open the following list.
        Uses confirmed selectors from XML dumps.
        Returns True on success.
        """
        selectors = [
            # CONFIRMED working: stacked familiar layout (content-desc="8following")
            self.device(resourceIdMatches=".*profile_header_following_stacked_familiar.*"),
            # Following value text
            self.device(resourceIdMatches=".*profile_header_familiar_following_value.*"),
            # Content-desc based
            self.device(descriptionMatches=".*\\d+.*following.*"),
            # Text-based fallbacks
            self.device(textContains="following"),
        ]
        for sel in selectors:
            if sel.exists(timeout=3):
                sel.click()
                time.sleep(3)
                # If unified tab layout, click the "following" tab
                title_btns = self.device(resourceIdMatches=".*title$")
                if title_btns.exists(timeout=2):
                    for i in range(min(title_btns.count, 6)):
                        try:
                            text = title_btns[i].get_text() or ""
                            if "following" in text.lower():
                                title_btns[i].click()
                                time.sleep(2)
                                break
                        except Exception:
                            continue
                return True
        return False

    def press_back(self):
        """Press back button."""
        try:
            self.device.press("back")
            time.sleep(1)
            return True
        except Exception:
            return False

    def scroll_down(self, duration=0.5):
        """Scroll down the current view."""
        try:
            w, h = self.device.window_size()
            sx = w // 2
            sy = int(h * 0.7)
            ey = int(h * 0.3)
            self.device.swipe(sx, sy, sx, ey, duration=duration)
            time.sleep(1)
            return True
        except Exception:
            return False

    def scroll_up(self, duration=0.5):
        """Scroll up the current view."""
        try:
            w, h = self.device.window_size()
            sx = w // 2
            sy = int(h * 0.3)
            ey = int(h * 0.7)
            self.device.swipe(sx, sy, sx, ey, duration=duration)
            time.sleep(1)
            return True
        except Exception:
            return False

    def is_on_instagram(self, package=None):
        """Check if Instagram is currently in foreground."""
        try:
            current = self.device.app_current().get('package', '')
            if package:
                return current == package
            return current.startswith('com.instagram.')
        except Exception:
            return False

    def dismiss_any_popup(self):
        """Try to dismiss any popup/dialog that might appear.
        
        Includes Android permission dialog buttons (from permissioncontroller).
        """
        dismiss_texts = ["While using the app", "WHILE USING THE APP",
                        "Allow", "ALLOW",
                        "Not Now", "Not now", "Cancel", "Skip", "OK",
                        "Dismiss", "Close", "No Thanks", "Maybe Later"]
        for text in dismiss_texts:
            btn = self.device(text=text)
            if btn.exists(timeout=1):
                try:
                    btn.click()
                    time.sleep(1)
                    return True
                except Exception:
                    continue
        return False


# ---------------------------------------------------------------------------
# Profile Info Parsing
# ---------------------------------------------------------------------------

def parse_number(text):
    """Parse Instagram-style numbers like '1.2K', '3.4M', '500'."""
    if not text:
        return 0
    text = text.strip().replace(',', '').replace(' ', '')
    try:
        if text.upper().endswith('K'):
            return int(float(text[:-1]) * 1000)
        elif text.upper().endswith('M'):
            return int(float(text[:-1]) * 1000000)
        elif text.upper().endswith('B'):
            return int(float(text[:-1]) * 1000000000)
        return int(text)
    except (ValueError, TypeError):
        return 0


def get_profile_info(device, device_serial):
    """
    Extract profile info from current profile screen.
    Returns dict with: posts, followers, following, is_private, username, bio
    """
    info = {
        'posts': 0,
        'followers': 0,
        'following': 0,
        'is_private': False,
        'username': '',
        'bio': '',
        'has_story': False,
    }

    try:
        xml = device.dump_hierarchy()
        xml_lower = xml.lower()

        # Detect private account
        info['is_private'] = ('this account is private' in xml_lower or
                              'private account' in xml_lower)

        # Try to find username from action bar
        action_bar_title = device(resourceId="com.instagram.android:id/action_bar_title")
        if action_bar_title.exists(timeout=2):
            info['username'] = action_bar_title.get_text() or ''

        # Parse followers/following/posts counts
        # They often appear as: "X posts  Y followers  Z following"
        count_pattern = re.compile(
            r'(\d[\d,.]*[KkMmBb]?)\s*(?:posts?|followers?|following)',
            re.IGNORECASE
        )

        matches = count_pattern.findall(xml)
        # Usually in order: posts, followers, following
        if len(matches) >= 3:
            info['posts'] = parse_number(matches[0])
            info['followers'] = parse_number(matches[1])
            info['following'] = parse_number(matches[2])
        elif len(matches) >= 1:
            # Try individual parsing
            for m in re.finditer(
                r'(\d[\d,.]*[KkMmBb]?)\s*(posts?|followers?|following)',
                xml, re.IGNORECASE
            ):
                val = parse_number(m.group(1))
                label = m.group(2).lower()
                if 'post' in label:
                    info['posts'] = val
                elif 'follower' in label and 'following' not in label:
                    info['followers'] = val
                elif 'following' in label:
                    info['following'] = val

        # Story ring detection
        info['has_story'] = ('story_ring' in xml_lower or
                            'reel_ring' in xml_lower)

    except Exception as e:
        log.debug("[%s] Profile info parse error: %s", device_serial, e)

    return info


def check_filters(profile_info, filters_config):
    """
    Check if a profile passes the configured filters.
    Returns (passed: bool, reason: str).
    """
    if not filters_config:
        return True, ""

    followers = profile_info.get('followers', 0)
    following = profile_info.get('following', 0)
    posts = profile_info.get('posts', 0)
    is_private = profile_info.get('is_private', False)

    # Follower filters
    if filters_config.get('enable_followers_filter', False):
        min_f = int(filters_config.get('min_followers', 0))
        max_f = int(filters_config.get('max_followers', 999999999))
        if followers < min_f:
            return False, "too_few_followers (%d < %d)" % (followers, min_f)
        if followers > max_f:
            return False, "too_many_followers (%d > %d)" % (followers, max_f)

    # Following filters
    if filters_config.get('enable_followings_filter', False):
        min_fg = int(filters_config.get('min_followings', 0))
        max_fg = int(filters_config.get('max_followings', 999999999))
        if following < min_fg:
            return False, "too_few_following (%d < %d)" % (following, min_fg)
        if following > max_fg:
            return False, "too_many_following (%d > %d)" % (following, max_fg)

    # Posts filter
    if filters_config.get('enable_posts_filter', False):
        min_p = int(filters_config.get('min_posts', 0))
        max_p = int(filters_config.get('max_posts', 999999))
        if posts < min_p:
            return False, "too_few_posts (%d < %d)" % (posts, min_p)
        if posts > max_p:
            return False, "too_many_posts (%d > %d)" % (posts, max_p)

    # Private account filter
    if filters_config.get('only_public_accounts', False) and is_private:
        return False, "private_account"

    # Profile picture filter
    if filters_config.get('only_has_profile_pict', False):
        # We can't reliably detect this from XML, so skip
        pass

    return True, ""
