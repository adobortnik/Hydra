"""
Check Profile Action Module
=============================
Navigate to own profile and capture follower/following/posts snapshot.
Runs once per session at the start to track growth over time.

Saves data to follower_snapshots table and updates accounts.followers.
"""

import logging
import datetime

from automation.ig_controller import IGController, Screen
from automation.actions.helpers import (
    get_profile_info, get_db, log_action, random_sleep,
)

log = logging.getLogger(__name__)


class CheckProfileAction:
    """Check own profile stats and save a snapshot for growth tracking."""

    def __init__(self, device, device_serial, account_info, session_id,
                 pkg=None):
        """
        Args:
            device: uiautomator2 device object
            device_serial: e.g. '10.1.11.4_5555'
            account_info: dict with 'username', 'id', etc.
            session_id: current session ID
            pkg: IG clone package name
        """
        self.device = device
        self.device_serial = device_serial
        self.account = account_info
        self.session_id = session_id
        self.username = account_info.get('username', '')
        self.account_id = account_info.get('id')

        _pkg = pkg or account_info.get('package', 'com.instagram.android')
        self.ctrl = IGController(device, device_serial, _pkg)

    def execute(self):
        """
        Navigate to profile, capture stats, save snapshot.
        Returns dict with results or None on failure.
        """
        try:
            log.info("[%s] CHECK_PROFILE: Capturing stats for @%s",
                     self.device_serial, self.username)

            # Navigate to profile tab
            nav_ok = self.ctrl.navigate_to(Screen.PROFILE)
            if not nav_ok:
                log.warning("[%s] CHECK_PROFILE: Could not navigate to profile "
                            "for @%s — skipping snapshot",
                            self.device_serial, self.username)
                return None

            # Small delay to let profile load
            random_sleep(1.5, 3.0, label="profile_load")

            # Extract profile info using existing helper
            info = get_profile_info(self.device, self.device_serial)

            followers = info.get('followers', 0)
            following = info.get('following', 0)
            posts = info.get('posts', 0)
            detected_username = info.get('username', '')

            # Use detected username if available, fall back to account username
            snap_username = detected_username or self.username

            if followers == 0 and following == 0 and posts == 0:
                log.warning("[%s] CHECK_PROFILE: All counts are 0 for @%s — "
                            "profile may not have loaded properly",
                            self.device_serial, snap_username)
                # Still save the snapshot (could be a brand new account)

            # Save snapshot to DB
            self._save_snapshot(snap_username, followers, following, posts)

            # Update accounts.followers
            self._update_account_followers(followers)

            # Log the action
            log_action(
                session_id=self.session_id,
                device_serial=self.device_serial,
                username=self.username,
                action_type='check_profile',
                success=True,
            )

            log.info("[%s] CHECK_PROFILE: @%s — %d followers, %d following, "
                     "%d posts",
                     self.device_serial, snap_username,
                     followers, following, posts)

            return {
                'success': True,
                'username': snap_username,
                'followers': followers,
                'following': following,
                'posts': posts,
            }

        except Exception as e:
            log.error("[%s] CHECK_PROFILE: Error for @%s: %s",
                      self.device_serial, self.username, e, exc_info=True)
            return None

    def _save_snapshot(self, username, followers, following, posts):
        """Save a follower snapshot to the DB."""
        try:
            conn = get_db()
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
            conn.execute("""
                INSERT OR REPLACE INTO follower_snapshots
                    (account_id, username, device_serial, followers,
                     following, posts_count, captured_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (self.account_id, username, self.device_serial,
                  followers, following, posts, now))
            conn.commit()
            conn.close()
        except Exception as e:
            log.error("[%s] CHECK_PROFILE: Failed to save snapshot: %s",
                      self.device_serial, e)

    def _update_account_followers(self, followers):
        """Update the accounts table with the current follower count."""
        try:
            conn = get_db()
            conn.execute("""
                UPDATE accounts SET followers = ? WHERE id = ?
            """, (followers, self.account_id))
            conn.commit()
            conn.close()
        except Exception as e:
            log.error("[%s] CHECK_PROFILE: Failed to update account followers: %s",
                      self.device_serial, e)
