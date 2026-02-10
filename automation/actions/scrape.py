"""
Scrape Action Module
=====================
Scrape follower lists from target accounts for follow targeting.

Saves scraped usernames to a local DB table (scraped_users)
so the follow action can use them as targets.
"""

import logging
import random
import time
import datetime

from automation.actions.helpers import (
    IGNavigator, random_sleep, get_db, log_action,
    get_account_sources
)

log = logging.getLogger(__name__)

# Ensure scraped_users table exists
SCRAPED_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS scraped_users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER NOT NULL,
    source_username TEXT NOT NULL,
    scraped_username TEXT NOT NULL,
    scraped_at      TEXT DEFAULT (datetime('now')),
    used            INTEGER DEFAULT 0,
    UNIQUE(account_id, scraped_username)
);
CREATE INDEX IF NOT EXISTS idx_scraped_account ON scraped_users(account_id, used);
"""


def ensure_scraped_table():
    """Create scraped_users table if it doesn't exist."""
    try:
        conn = get_db()
        conn.executescript(SCRAPED_TABLE_SQL)
        conn.commit()
        conn.close()
    except Exception as e:
        log.error("Failed to create scraped_users table: %s", e)


class ScrapeAction:
    """
    Scrape follower lists from target/source accounts.
    """

    def __init__(self, device, device_serial, account_info, session_id):
        self.device = device
        self.device_serial = device_serial
        self.account = account_info
        self.session_id = session_id
        self.nav = IGNavigator(device, device_serial)
        self.username = account_info['username']
        self.account_id = account_info['id']

        ensure_scraped_table()

    def execute(self, max_per_source=100):
        """
        Scrape followers from source accounts.
        Returns: {success, total_scraped, sources_processed}
        """
        result = {
            'success': False,
            'total_scraped': 0,
            'sources_processed': 0,
        }

        sources = get_account_sources(self.account_id, 'sources')
        if not sources:
            log.warning("[%s] %s: No sources to scrape",
                       self.device_serial, self.username)
            return result

        # Pick a subset of sources to scrape this session
        random.shuffle(sources)
        sources_to_scrape = sources[:3]  # Max 3 sources per session

        for source_username in sources_to_scrape:
            log.info("[%s] Scraping followers from @%s",
                     self.device_serial, source_username)

            try:
                scraped = self._scrape_followers(source_username, max_per_source)
                result['total_scraped'] += scraped
                result['sources_processed'] += 1

                log_action(
                    self.session_id, self.device_serial, self.username,
                    'scrape', target_username=source_username,
                    success=True)

            except Exception as e:
                log.error("[%s] Error scraping @%s: %s",
                         self.device_serial, source_username, e)
                self._recover()

            random_sleep(5, 10, label="between_scrape_sources")

        result['success'] = True
        log.info("[%s] %s: Scrape complete. Sources: %d, Users scraped: %d",
                 self.device_serial, self.username,
                 result['sources_processed'], result['total_scraped'])
        return result

    def _scrape_followers(self, source_username, max_count):
        """
        Navigate to source user's followers and collect usernames.
        Returns count of newly scraped users.
        """
        scraped_count = 0

        # Navigate to source profile
        if not self.nav.search_user(source_username):
            log.warning("[%s] Could not find @%s for scraping",
                       self.device_serial, source_username)
            return 0

        random_sleep(2, 4)

        # Open followers list
        if not self.nav.open_followers_list():
            log.warning("[%s] Could not open followers for @%s",
                       self.device_serial, source_username)
            self.nav.press_back()
            return 0

        random_sleep(2, 4, label="followers_loaded")

        # Scroll through and collect usernames
        all_usernames = set()
        scroll_count = 0
        max_scrolls = 20
        no_new_count = 0

        while len(all_usernames) < max_count and scroll_count < max_scrolls:
            visible = self._get_visible_usernames()
            new_users = set(visible) - all_usernames

            if not new_users:
                no_new_count += 1
                if no_new_count >= 3:
                    log.info("[%s] No more new users from @%s after %d scrolls",
                            self.device_serial, source_username, scroll_count)
                    break
            else:
                no_new_count = 0
                all_usernames.update(new_users)
                log.debug("[%s] Scraped %d new users (total: %d)",
                         self.device_serial, len(new_users), len(all_usernames))

            self.nav.scroll_down()
            random_sleep(1, 2)
            scroll_count += 1

        # Save to DB
        if all_usernames:
            scraped_count = self._save_scraped_users(source_username, all_usernames)

        # Navigate back
        self.nav.press_back()
        time.sleep(1)
        self.nav.press_back()
        time.sleep(1)

        return scraped_count

    def _get_visible_usernames(self):
        """Extract usernames from the visible follower list."""
        usernames = []
        try:
            for res_suffix in ['follow_list_username', 'row_user_primary_name',
                                'row_user_textview', 'username']:
                views = self.device(resourceIdMatches=".*" + res_suffix)
                if views.exists(timeout=1):
                    for i in range(min(views.count, 20)):
                        try:
                            text = views[i].get_text()
                            if text and text.strip():
                                usernames.append(text.strip())
                        except Exception:
                            continue
                    if usernames:
                        return usernames

            # Fallback
            all_texts = self.device(className="android.widget.TextView")
            if all_texts.exists(timeout=2):
                for i in range(min(all_texts.count, 30)):
                    try:
                        text = all_texts[i].get_text()
                        if text and len(text) > 1 and len(text) < 40:
                            if (text.replace('.', '').replace('_', '').isalnum() and
                                    not text.isdigit() and
                                    text.lower() not in ('follow', 'following', 'followers',
                                                        'remove', 'message',
                                                        'suggested for you')):
                                usernames.append(text.strip())
                    except Exception:
                        continue
        except Exception as e:
            log.debug("[%s] Error getting usernames: %s", self.device_serial, e)

        return usernames

    def _save_scraped_users(self, source_username, usernames):
        """Save scraped usernames to DB. Returns count of newly inserted."""
        saved = 0
        try:
            conn = get_db()
            now = datetime.datetime.now().isoformat()
            for u in usernames:
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO scraped_users
                            (account_id, source_username, scraped_username, scraped_at)
                        VALUES (?, ?, ?, ?)
                    """, (self.account_id, source_username, u, now))
                    if conn.execute("SELECT changes()").fetchone()[0] > 0:
                        saved += 1
                except Exception:
                    continue
            conn.commit()
            conn.close()
            log.info("[%s] Saved %d new scraped users from @%s",
                     self.device_serial, saved, source_username)
        except Exception as e:
            log.error("[%s] Error saving scraped users: %s", self.device_serial, e)
        return saved

    def _recover(self):
        """Navigate back to a safe state."""
        try:
            for _ in range(3):
                self.nav.press_back()
                time.sleep(1)
            self.nav.dismiss_any_popup()
            self.nav.go_home()
        except Exception:
            pass


def execute_scrape(device, device_serial, account_info, session_id):
    """Convenience function to run scrape action."""
    action = ScrapeAction(device, device_serial, account_info, session_id)
    return action.execute()
