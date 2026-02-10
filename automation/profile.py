"""
Profile Automation Module
==========================
Change Instagram username, bio, and profile picture via uiautomator2.

Ported from automated_profile_manager.py (51KB), cleaned up and wired
to phone_farm.db (profile_updates, profile_pictures, bio_templates tables).

Key patterns (from old code):
  - Edit profile fields: click label -> opens sub-screen -> EditText -> type -> back
  - Text input: long_click -> Select All -> delete -> adb shell input text
  - Profile picture: "Edit picture or avatar" -> "Choose from library" -> pick image
  - Save: click "Done" / checkmark at top right
  - Modals: dismiss "Create avatar", "Not now", etc. before editing

CRITICAL: Only use device 10.1.11.4_5555 (JACK 1) for testing.
"""

import subprocess
import time
import logging
import os

log = logging.getLogger(__name__)


class ProfileAutomation:
    """
    Instagram profile editor via uiautomator2.

    Requires the device to already have Instagram open and be on the
    edit-profile screen (or navigable to it).
    """

    def __init__(self, device, device_serial):
        """
        Args:
            device: uiautomator2 device object (connected)
            device_serial: DB-format serial "10.1.11.4_5555"
        """
        self.device = device
        self.device_serial = device_serial
        self.adb_serial = device_serial.replace('_', ':')

    # ==================================================================
    #  Navigation helpers
    # ==================================================================

    def navigate_to_edit_profile(self):
        """
        From anywhere inside Instagram, get to the Edit Profile screen.
        Returns True if we land on the edit-profile screen.
        """
        # Step 1 – go to profile tab
        for sel in [self.device(description="Profile"),
                    self.device(description="profile"),
                    self.device(text="Profile")]:
            if sel.exists(timeout=3):
                sel.click()
                time.sleep(2)
                break
        else:
            # coordinate fallback – bottom-right
            w, h = self.device.window_size()
            self.device.click(int(w * 0.9), int(h * 0.95))
            time.sleep(2)

        # Step 2 – tap "Edit profile"
        for sel in [self.device(text="Edit profile"),
                    self.device(text="Edit Profile"),
                    self.device(description="Edit profile"),
                    self.device(textContains="Edit profile")]:
            if sel.exists(timeout=4):
                sel.click()
                time.sleep(2)
                break
        else:
            log.warning("[%s] Could not find 'Edit profile' button", self.device_serial)
            return False

        # Step 3 – dismiss any modals (avatar, etc.)
        self.dismiss_modals()

        return self.is_on_edit_profile()

    def is_on_edit_profile(self):
        """Check if we're on the edit profile screen."""
        for label in ("Name", "Username", "Bio"):
            if self.device(text=label).exists(timeout=2):
                return True
        return False

    def dismiss_modals(self, max_rounds=5):
        """Dismiss common Instagram popups (avatar, notifications, etc.)."""
        dismissed = 0
        for _ in range(max_rounds):
            found = False
            # Check XML once per round for avatar/photo keywords
            try:
                xml = self.device.dump_hierarchy().lower()
                if any(kw in xml for kw in ('avatar', 'create your', 'profile photo')):
                    for txt in ("Not now", "Skip", "Cancel", "Maybe Later", "Later"):
                        if self.device(text=txt).exists(timeout=0.5):
                            self.device(text=txt).click()
                            dismissed += 1
                            found = True
                            time.sleep(1)
                            break
                    if found:
                        continue
            except Exception:
                pass

            # Generic dismiss buttons
            for txt in ("Not now", "Not Now", "Skip", "Cancel", "Maybe Later",
                        "Later", "Dismiss", "Close"):
                if self.device(text=txt).exists(timeout=0.3):
                    self.device(text=txt).click()
                    dismissed += 1
                    found = True
                    time.sleep(1)
                    break
            if not found:
                break

        if dismissed:
            log.info("[%s] Dismissed %d modal(s)", self.device_serial, dismissed)
        return dismissed

    def save_changes(self):
        """Tap Done/Save to commit profile edits. Returns True on success."""
        for sel in [self.device(text="Done"),
                    self.device(text="Save"),
                    self.device(description="Done"),
                    self.device(resourceId="com.instagram.android:id/action_bar_button_text")]:
            if sel.exists(timeout=5):
                sel.click()
                time.sleep(2)
                return True
        log.warning("[%s] Could not find save/done button", self.device_serial)
        return False

    def detect_challenge(self):
        """
        Fast XML-based check for challenge/verification screens.
        Returns dict {is_challenge, challenge_type, text}.
        """
        try:
            xml = self.device.dump_hierarchy().lower()
            keywords = [
                ("confirm", "verification"),
                ("verify", "verification"),
                ("security check", "security"),
                ("unusual activity", "suspicious_activity"),
                ("confirmation code", "code_verification"),
                ("automated behavior", "automation_detected"),
                ("try again later", "rate_limit"),
            ]
            for kw, ctype in keywords:
                if kw in xml:
                    return {'is_challenge': True, 'challenge_type': ctype, 'text': kw}
        except Exception:
            pass
        return {'is_challenge': False, 'challenge_type': None, 'text': None}

    # ==================================================================
    #  Username
    # ==================================================================

    def change_username(self, new_username):
        """
        Change the account username.
        Must already be on the Edit Profile screen.

        Flow: tap "Username" label area -> sub-screen -> clear -> type -> back

        Returns True on success.
        """
        log.info("[%s] Changing username to: %s", self.device_serial, new_username)

        # Navigate into the username sub-screen by clicking below the label
        if not self._tap_label_row("Username"):
            return False
        time.sleep(2)

        # Find the EditText on the username screen
        edit_field = self._find_edit_text()
        if not edit_field:
            log.error("[%s] Username EditText not found", self.device_serial)
            self.device.press("back")
            return False

        # Clear and type
        if not self._clear_and_type(edit_field, new_username):
            self.device.press("back")
            return False

        time.sleep(1)

        # Check for availability indicator (red text = taken)
        time.sleep(2)
        xml = self.device.dump_hierarchy().lower()
        if "isn't available" in xml or "not available" in xml:
            log.warning("[%s] Username '%s' is not available", self.device_serial, new_username)
            self.device.press("back")
            return False

        # Confirm (some versions use a checkmark/Done on the sub-screen)
        for sel in [self.device(description="Done"),
                    self.device(text="Done"),
                    self.device(resourceId="com.instagram.android:id/action_bar_button_text")]:
            if sel.exists(timeout=2):
                sel.click()
                time.sleep(2)
                break
        else:
            # No explicit confirm — press back to return to edit profile
            self.device.press("back")
            time.sleep(2)

        log.info("[%s] Username change submitted: %s", self.device_serial, new_username)
        return True

    # ==================================================================
    #  Bio
    # ==================================================================

    def change_bio(self, new_bio):
        """
        Change the account bio.
        Must already be on the Edit Profile screen.

        Flow: tap "Bio" label area -> sub-screen -> clear -> type -> back

        Returns True on success.
        """
        log.info("[%s] Changing bio (%d chars)", self.device_serial, len(new_bio))

        # Navigate into the bio sub-screen
        if not self._tap_label_row("Bio"):
            # Fallback: look for placeholder text
            for sel in [self.device(textContains="Add Bio"),
                        self.device(textContains="Tell people"),
                        self.device(resourceId="com.instagram.android:id/bio")]:
                if sel.exists(timeout=2):
                    sel.click()
                    time.sleep(2)
                    break
            else:
                log.error("[%s] Cannot navigate to bio edit screen", self.device_serial)
                return False

        time.sleep(2)

        # Find EditText
        edit_field = self._find_edit_text()
        if not edit_field:
            log.error("[%s] Bio EditText not found", self.device_serial)
            self.device.press("back")
            return False

        # Clear and type
        if not self._clear_and_type(edit_field, new_bio, use_char_input=True):
            self.device.press("back")
            return False

        time.sleep(1)

        # Go back to edit profile screen (auto-saves in bio sub-screen)
        self.device.press("back")
        time.sleep(2)

        log.info("[%s] Bio change submitted", self.device_serial)
        return True

    # ==================================================================
    #  Profile Picture
    # ==================================================================

    def change_profile_picture(self, image_local_path=None):
        """
        Change the profile picture.
        Must already be on the Edit Profile screen.

        If image_local_path is given, pushes it to the device first.
        Otherwise picks the first (newest) image from the device gallery.

        Returns True on success.
        """
        log.info("[%s] Changing profile picture", self.device_serial)

        # If we have a local image, push it to the device
        if image_local_path and os.path.exists(image_local_path):
            device_path = self._push_image_to_device(image_local_path)
            if not device_path:
                log.error("[%s] Failed to push image to device", self.device_serial)
                return False
            time.sleep(3)

        # Step 1: Tap the profile picture / "Edit picture or avatar" area
        pic_clicked = False
        for sel in [self.device(text="Edit picture or avatar"),
                    self.device(text="Edit picture"),
                    self.device(text="Change profile photo"),
                    self.device(text="Change Profile Photo"),
                    self.device(description="Edit picture or avatar"),
                    self.device(textContains="Edit picture"),
                    self.device(textContains="avatar")]:
            if sel.exists(timeout=4):
                sel.click()
                pic_clicked = True
                break

        if not pic_clicked:
            # Coordinate fallback: top-center where the avatar circle is
            w, h = self.device.window_size()
            self.device.click(w // 2, 250)
            log.info("[%s] Clicked avatar area (coordinate fallback)", self.device_serial)

        time.sleep(2)

        # Step 2: Choose from gallery/library
        gallery_clicked = False
        for txt in ("New profile picture", "Choose from library", "Choose from Library",
                     "Select from gallery", "Select from Gallery", "Gallery",
                     "Library", "Photos"):
            if self.device(text=txt).exists(timeout=2):
                self.device(text=txt).click()
                gallery_clicked = True
                log.info("[%s] Selected gallery option: %s", self.device_serial, txt)
                break
        if not gallery_clicked:
            for kw in ("library", "gallery"):
                if self.device(textContains=kw).exists(timeout=2):
                    self.device(textContains=kw).click()
                    gallery_clicked = True
                    break

        if not gallery_clicked:
            # Coordinate fallback: first option in the modal (center, ~45% height)
            w, h = self.device.window_size()
            self.device.click(w // 2, int(h * 0.45))
            log.info("[%s] Gallery coordinate fallback", self.device_serial)

        time.sleep(3)

        # Step 3: Pick the first image (top-left, newest photo)
        w, h = self.device.window_size()
        self.device.click(int(w * 0.25), int(h * 0.3))
        log.info("[%s] Selected first gallery image", self.device_serial)
        time.sleep(2)

        # Step 4: Confirm / crop
        for sel in [self.device(text="Done"), self.device(text="OK"),
                    self.device(text="Crop"), self.device(text="Next"),
                    self.device(text="Confirm"), self.device(description="Done"),
                    self.device(resourceId="com.instagram.android:id/next_button")]:
            if sel.exists(timeout=3):
                sel.click()
                time.sleep(1)
                break

        # Possible second confirmation
        for sel in [self.device(text="Done"), self.device(text="OK"),
                    self.device(text="Confirm")]:
            if sel.exists(timeout=2):
                sel.click()
                time.sleep(1)
                break

        time.sleep(2)
        log.info("[%s] Profile picture change submitted", self.device_serial)
        return True

    # ==================================================================
    #  Full task processor (reads from phone_farm.db)
    # ==================================================================

    def process_task(self, task_row):
        """
        Process a profile_updates row dict from phone_farm.db.

        Expected keys: id, device_serial, instagram_package, username,
                       new_username, new_bio, profile_picture_id

        Returns dict {success, changes, error}.
        """
        from automation.instagram_actions import InstagramActions

        task_id = task_row['id']
        package = task_row.get('instagram_package', 'com.instagram.android')
        changes = []

        log.info("[%s] Processing profile task %d", self.device_serial, task_id)

        ig = InstagramActions(self.device, self.device_serial)

        # Open Instagram
        if not ig.open_instagram(package):
            return {'success': False, 'changes': changes,
                    'error': 'Failed to open Instagram'}

        time.sleep(3)

        # Challenge check
        challenge = self.detect_challenge()
        if challenge['is_challenge']:
            return {'success': False, 'changes': changes,
                    'error': 'Challenge screen: %s' % challenge['challenge_type']}

        # Navigate to edit profile
        if not self.navigate_to_edit_profile():
            return {'success': False, 'changes': changes,
                    'error': 'Cannot reach edit profile screen'}

        # --- Profile picture ---
        if task_row.get('profile_picture_id'):
            pic_path = self._resolve_picture_path(task_row['profile_picture_id'])
            if self.change_profile_picture(pic_path):
                changes.append('profile_picture')
                self._log_change(task_row, 'profile_picture', None,
                                 str(task_row['profile_picture_id']))
            # Return to edit profile
            if not self.is_on_edit_profile():
                self.navigate_to_edit_profile()
            time.sleep(1)

        # --- Username ---
        if task_row.get('new_username'):
            if not self.is_on_edit_profile():
                self.navigate_to_edit_profile()
            if self.change_username(task_row['new_username']):
                changes.append('username')
                self._log_change(task_row, 'username',
                                 task_row.get('username'), task_row['new_username'])
                # Update account username in main DB
                self._update_account_username(task_row)
            # Ensure we're back on edit profile
            if not self.is_on_edit_profile():
                self.navigate_to_edit_profile()
            time.sleep(1)

        # --- Bio ---
        if task_row.get('new_bio'):
            if not self.is_on_edit_profile():
                self.navigate_to_edit_profile()
            if self.change_bio(task_row['new_bio']):
                changes.append('bio')
                self._log_change(task_row, 'bio', None, task_row['new_bio'])
            time.sleep(1)

        # Save
        if changes and self.is_on_edit_profile():
            self.save_changes()

        return {'success': len(changes) > 0 or not any([
            task_row.get('new_username'), task_row.get('new_bio'),
            task_row.get('profile_picture_id')
        ]), 'changes': changes, 'error': None}

    # ==================================================================
    #  Private helpers
    # ==================================================================

    def _tap_label_row(self, label_text):
        """
        Tap the row below a label (e.g. 'Username', 'Bio') on edit profile.
        Instagram edit profile layout: label on top, editable value below.
        """
        try:
            if self.device(text=label_text).exists(timeout=3):
                bounds = self.device(text=label_text).info['bounds']
                x = bounds['left'] + 50
                y = bounds['bottom'] + 30
                self.device.click(x, y)
                return True
        except Exception as e:
            log.warning("[%s] _tap_label_row(%s) failed: %s",
                        self.device_serial, label_text, e)
        return False

    def _find_edit_text(self):
        """Find an EditText field on the current screen."""
        for sel in [self.device(className="android.widget.EditText"),
                    self.device.xpath('//android.widget.EditText')]:
            if sel.exists(timeout=5):
                sel.click()
                time.sleep(0.5)
                return sel
        return None

    def _clear_and_type(self, field, text, use_char_input=False):
        """
        Clear an EditText and type new text.
        use_char_input=True types character-by-character (needed for bio
        with special chars / newlines).
        """
        try:
            # Select all -> delete
            field.long_click()
            time.sleep(0.5)
            if self.device(text="Select all").exists(timeout=1):
                self.device(text="Select all").click()
                time.sleep(0.3)
            self.device.press("delete")
            time.sleep(0.5)

            if use_char_input:
                # Character-by-character for bios with special chars
                for ch in text:
                    if ch == '\n':
                        self.device.press("enter")
                    elif ch == ' ':
                        subprocess.run(
                            ['adb', '-s', self.adb_serial, 'shell', 'input', 'text', '%s'],
                            capture_output=True, timeout=5)
                    elif ch in '|&<>(){}[]$`"\';*?!#':
                        subprocess.run(
                            ['adb', '-s', self.adb_serial, 'shell', 'input', 'text',
                             '"%s"' % ch],
                            capture_output=True, timeout=5)
                    else:
                        subprocess.run(
                            ['adb', '-s', self.adb_serial, 'shell', 'input', 'text', ch],
                            capture_output=True, timeout=5)
                    time.sleep(0.03)
            else:
                # Whole string via ADB — works for simple ASCII usernames
                subprocess.run(
                    ['adb', '-s', self.adb_serial, 'shell', 'input', 'text', text],
                    capture_output=True, timeout=10)

            time.sleep(0.5)
            return True

        except Exception as e:
            log.error("[%s] _clear_and_type failed: %s", self.device_serial, e)
            # Fallback: set_text
            try:
                field.set_text(text)
                return True
            except Exception:
                return False

    def _push_image_to_device(self, local_path):
        """Push an image file to the device via ADB. Returns device path or None."""
        try:
            ts = int(time.time())
            filename = "profile_pic_%d.jpg" % ts
            device_path = "/sdcard/DCIM/Camera/%s" % filename

            subprocess.run(
                ['adb', '-s', self.adb_serial, 'push', str(local_path), device_path],
                capture_output=True, text=True, check=True, timeout=30)

            # Trigger media scanner
            subprocess.run(
                ['adb', '-s', self.adb_serial, 'shell', 'am', 'broadcast',
                 '-a', 'android.intent.action.MEDIA_SCANNER_SCAN_FILE',
                 '-d', 'file://%s' % device_path],
                capture_output=True, timeout=10)

            time.sleep(3)
            log.info("[%s] Pushed image to %s", self.device_serial, device_path)
            return device_path
        except Exception as e:
            log.error("[%s] _push_image_to_device failed: %s", self.device_serial, e)
            return None

    def _resolve_picture_path(self, picture_id):
        """Look up a profile_pictures row and return the local file path (or None)."""
        try:
            from db.models import get_connection
            conn = get_connection()
            row = conn.execute(
                "SELECT original_path FROM profile_pictures WHERE id=?",
                (picture_id,)).fetchone()
            conn.close()
            if row and os.path.exists(row['original_path']):
                return row['original_path']
        except Exception:
            pass
        return None

    def _log_change(self, task_row, change_type, old_val, new_val):
        """Write to profile_updates history columns / profile_history."""
        try:
            from db.models import get_connection
            import datetime, json
            conn = get_connection()
            conn.execute("""
                INSERT INTO task_history
                    (account_id, device_serial, task_type, status,
                     completed_at, params_json, result_json)
                VALUES (?, ?, ?, 'completed', ?, ?, ?)
            """, (
                task_row.get('account_id'),
                task_row.get('device_serial', self.device_serial),
                'profile_%s' % change_type,
                datetime.datetime.now().isoformat(),
                json.dumps({'old': old_val}),
                json.dumps({'new': new_val}),
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            log.warning("_log_change error: %s", e)

    def _update_account_username(self, task_row):
        """Update the username in the accounts table after a successful change."""
        try:
            from db.models import get_connection
            import datetime
            conn = get_connection()
            conn.execute(
                "UPDATE accounts SET username=?, updated_at=? WHERE device_serial=? AND username=?",
                (task_row['new_username'],
                 datetime.datetime.now().isoformat(),
                 task_row['device_serial'],
                 task_row.get('username', '')))
            conn.commit()
            conn.close()
        except Exception as e:
            log.warning("_update_account_username error: %s", e)


# ======================================================================
#  Convenience functions for API / scheduler use
# ======================================================================

def run_profile_task(device_serial, task_id):
    """
    Execute a profile_updates task by ID.

    Connects to the device, runs the task, disconnects.
    Returns result dict.
    """
    from automation.device_connection import get_connection as get_dev
    from db.models import get_connection as db_conn, row_to_dict
    import datetime, json

    conn = db_conn()
    row = conn.execute("SELECT * FROM profile_updates WHERE id=?", (task_id,)).fetchone()
    conn.close()

    if not row:
        return {'success': False, 'error': 'Task %d not found' % task_id}

    task = row_to_dict(row)

    # Mark running
    conn = db_conn()
    conn.execute(
        "UPDATE profile_updates SET status='in_progress', updated_at=? WHERE id=?",
        (datetime.datetime.now().isoformat(), task_id))
    conn.commit()
    conn.close()

    # Connect
    dev = get_dev(device_serial)
    device = dev.connect(timeout=45, max_attempts=2)
    if not device:
        _mark_task(task_id, 'failed', 'Device connection failed')
        dev.disconnect()
        return {'success': False, 'error': 'Device connection failed'}

    try:
        pa = ProfileAutomation(device, device_serial)
        result = pa.process_task(task)

        status = 'completed' if result['success'] else 'failed'
        _mark_task(task_id, status, result.get('error'))

        return result

    except Exception as e:
        _mark_task(task_id, 'failed', str(e))
        return {'success': False, 'error': str(e)}

    finally:
        dev.disconnect()


def _mark_task(task_id, status, error=None):
    """Update profile_updates row status."""
    from db.models import get_connection
    import datetime
    conn = get_connection()
    now = datetime.datetime.now().isoformat()
    if status == 'completed':
        conn.execute(
            "UPDATE profile_updates SET status=?, completed_at=?, updated_at=?, error_message=? WHERE id=?",
            (status, now, now, error, task_id))
    else:
        conn.execute(
            "UPDATE profile_updates SET status=?, updated_at=?, error_message=? WHERE id=?",
            (status, now, error, task_id))
    conn.commit()
    conn.close()
