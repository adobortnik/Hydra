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

            # Update accounts.followers + accounts.following + accounts.posts
            self._update_account_metrics(followers, following, posts)

            # Detect business profile from current XML and sync DB flag
            try:
                xml = self.ctrl.dump_xml("check_profile_business")
                is_business = self._detect_business_profile(xml)
                self._update_business_flag(is_business)
            except Exception as e:
                log.warning("[%s] CHECK_PROFILE: business detection failed: %s",
                            self.device_serial, e)
                is_business = None

            # Log the action
            log_action(
                session_id=self.session_id,
                device_serial=self.device_serial,
                username=self.username,
                action_type='check_profile',
                success=True,
            )

            log.info("[%s] CHECK_PROFILE: @%s — %d followers, %d following, "
                     "%d posts, business=%s",
                     self.device_serial, snap_username,
                     followers, following, posts, is_business)

            return {
                'success': True,
                'username': snap_username,
                'followers': followers,
                'following': following,
                'posts': posts,
                'is_business_profile': is_business,
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

    def _update_account_metrics(self, followers, following=None, posts=None):
        """Update the accounts table with current followers/following/posts counts."""
        try:
            conn = get_db()
            cols = ['followers']
            vals = [followers]
            if following is not None:
                cols.append('following'); vals.append(following)
            if posts is not None:
                cols.append('posts'); vals.append(posts)
            set_clause = ', '.join(f'{c} = ?' for c in cols)
            vals.append(self.account_id)
            conn.execute(f"UPDATE accounts SET {set_clause} WHERE id = ?", vals)
            conn.commit()
            conn.close()
        except Exception as e:
            log.error("[%s] CHECK_PROFILE: Failed to update account metrics: %s",
                      self.device_serial, e)

    # Backwards-compat alias (kept in case anyone external calls it)
    def _update_account_followers(self, followers, following=None):
        self._update_account_metrics(followers, following, None)

    @staticmethod
    def _detect_business_profile(xml):
        """
        Detect business/professional profile from own profile screen XML.
        Returns True if at least 2 indicators present, False otherwise.
        Mirrors switch_to_business.py:_is_already_business logic.
        """
        if not xml:
            return False
        xml_lower = xml.lower()
        indicators = [
            'professional dashboard',
            'professional_dashboard',
            'switch to personal account',
            'switch account type',
        ]
        count = sum(1 for ind in indicators if ind in xml_lower)
        if 'insights' in xml_lower and 'professional' in xml_lower:
            count += 1
        if 'views in the last' in xml_lower:
            count += 1
        return count >= 2

    def _update_business_flag(self, is_business):
        """Update accounts.is_business_profile to reflect detected state."""
        if is_business is None:
            return
        try:
            conn = get_db()
            conn.execute(
                "UPDATE accounts SET is_business_profile = ? WHERE id = ?",
                (1 if is_business else 0, self.account_id)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            log.error("[%s] CHECK_PROFILE: Failed to update business flag: %s",
                      self.device_serial, e)
