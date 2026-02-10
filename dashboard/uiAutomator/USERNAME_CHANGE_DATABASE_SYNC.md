# Username Change - Database & Folder Synchronization

## Current System Architecture

### **Folder Structure:**
```
10.1.10.36_5555/                    (Device folder)
├── accounts.db                      (Device-level database)
├── anna.blnaa/                      (Account folder - FOLDER NAME = USERNAME)
│   ├── settings.db
│   ├── data.db
│   ├── stats.db
│   ├── sources.txt
│   └── ...
├── anna.bloof/                      (Another account)
│   └── ...
└── anna.bloopp/                     (Another account)
    └── ...
```

**Key Finding:** **FOLDER NAME = USERNAME**
- ✓ Each account has a folder named exactly as the Instagram username
- ✓ When username changes from `anna.blnaa` to `anna.newname`, the folder must be renamed

---

## Database Analysis

### **1. accounts.db (Device-Level)**

**Location:** `{device_serial}/accounts.db`

**Table:** `accounts`

**Schema:**
```
starttime (TEXT)
endtime (TEXT)
account (TEXT)          ← STORES USERNAME
password (TEXT)
follow (TEXT)
unfollow (TEXT)
mute (TEXT)
like (TEXT)
followmethod (TEXT)
unfollowmethod (TEXT)
limitperday (TEXT)
followaction (TEXT)
unfollowaction (TEXT)
likeaction (TEXT)
randomaction (TEXT)
randomdelay (TEXT)
switchmode (TEXT)
followdelay (TEXT)
unfollowdelay (TEXT)
likedelay (TEXT)
followlimitperday (TEXT)
unfollowlimitperday (TEXT)
likelimitperday (TEXT)
unfollowdelayday (TEXT)
mutemethod (TEXT)
email (TEXT)
```

**Sample Data:**
```sql
('0', '2', 'anna.blvv', 'Naa@#595Evth//246', 'True', ...)
('2', '4', 'anna.bloopp', 'Naa@#5ZCth//46', 'True', ...)
('4', '6', 'anna.gkdd', 'Guthgmp877_', 'False', ...)
```

**Key Column:** `account` - Stores the username

**Action Needed:**
- ✓ Update `account` column when username changes

---

### **2. settings.db (Account-Level)**

**Location:** `{device_serial}/{username}/settings.db`

**Table:** `accountsettings`

**Schema:**
```
id (INTEGER)
settings (TEXT)    ← JSON blob containing all settings
```

**Finding:**
- ✗ Does NOT store username directly
- ✓ All settings are in a JSON object
- ✓ No explicit username field in JSON (tested - only tag/filter related fields)

**Action Needed:**
- ✗ No update needed - settings.db doesn't store username

---

## What Needs to Be Updated When Username Changes

### **1. Rename Account Folder** ✓ CRITICAL
```python
# Old: 10.1.10.36_5555/anna.blnaa/
# New: 10.1.10.36_5555/anna.newname/

import os
old_folder = f"{device_serial}/{old_username}"
new_folder = f"{device_serial}/{new_username}"
os.rename(old_folder, new_folder)
```

**Why:** The folder name IS the username identifier for the bot

---

### **2. Update accounts.db** ✓ CRITICAL
```python
import sqlite3

conn = sqlite3.connect(f"{device_serial}/accounts.db")
cursor = conn.cursor()

# Update username in accounts table
cursor.execute('''
    UPDATE accounts
    SET account = ?
    WHERE account = ?
''', (new_username, old_username))

conn.commit()
conn.close()
```

**Why:** The `account` column stores scheduling/settings per username

---

### **3. Profile Automation Database** ✓ ALREADY DONE
Your profile automation system in `profile_automation_db.py` already has:
- `device_accounts` table with `username` column
- `update_device_account()` function that updates username

**Example:**
```python
from profile_automation_db import update_device_account

update_device_account(
    device_serial,
    username=new_username,  # Already updates this!
    bio=new_bio,
    profile_picture_id=pic_id,
    instagram_package=package
)
```

---

## Implementation Plan

### **Step 1: Create Username Update Function**

```python
# File: uiAutomator/update_username_in_bot.py

import sqlite3
import shutil
from pathlib import Path

def update_username_in_bot(device_serial, old_username, new_username):
    """
    Update username across all bot databases and rename folder

    Args:
        device_serial: Device ID (e.g., "10.1.10.36_5555")
        old_username: Current username
        new_username: New username

    Returns:
        dict: {'success': bool, 'message': str}
    """
    try:
        base_dir = Path(__file__).parent.parent
        device_dir = base_dir / device_serial

        # 1. Check if old folder exists
        old_folder = device_dir / old_username
        if not old_folder.exists():
            return {
                'success': False,
                'message': f'Old account folder not found: {old_folder}'
            }

        # 2. Check if new folder already exists
        new_folder = device_dir / new_username
        if new_folder.exists():
            return {
                'success': False,
                'message': f'New account folder already exists: {new_folder}'
            }

        # 3. Update accounts.db
        accounts_db = device_dir / "accounts.db"
        if accounts_db.exists():
            conn = sqlite3.connect(accounts_db)
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE accounts
                SET account = ?
                WHERE account = ?
            ''', (new_username, old_username))

            rows_updated = cursor.rowcount
            conn.commit()
            conn.close()

            print(f"  Updated {rows_updated} row(s) in accounts.db")
        else:
            print(f"  Warning: accounts.db not found, skipping")

        # 4. Rename folder
        print(f"  Renaming folder: {old_username} -> {new_username}")
        old_folder.rename(new_folder)

        return {
            'success': True,
            'message': f'Successfully updated username from {old_username} to {new_username}',
            'renamed_folder': str(new_folder)
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'Error updating username: {e}'
        }
```

---

### **Step 2: Integrate into Smart Username Changer**

```python
# File: uiAutomator/smart_username_changer.py

def _attempt_username_change(self, username):
    """
    Attempt to change username and detect if it's taken
    """
    try:
        # ... existing code to navigate and enter username ...

        if result['success']:
            # NEW: Update bot database and rename folder
            from update_username_in_bot import update_username_in_bot

            # Get old username from device (need to pass this in)
            if hasattr(self, 'old_username') and hasattr(self, 'device_serial'):
                print(f"  Updating bot database and folder...")
                db_result = update_username_in_bot(
                    self.device_serial,
                    self.old_username,
                    username
                )

                if db_result['success']:
                    print(f"  ✓ Bot database updated")
                    print(f"  ✓ Folder renamed: {self.old_username} -> {username}")
                else:
                    print(f"  ⚠ Warning: {db_result['message']}")

            return {'success': True, 'reason': 'Username changed'}

        # ... rest of code ...
```

---

### **Step 3: Update Batch Profile Manager**

```python
# File: uiAutomator/batch_profile_manager.py

# In process_single_task(), after successful username change:

if task['new_username']:
    print(f"\n--- Changing Username to: {task['new_username']} ---")

    smart_changer = SmartUsernameChanger(
        device=self.device,
        ai_api_key=task.get('ai_api_key'),
        ai_provider=task.get('ai_provider', 'openai')
    )

    # NEW: Pass old username and device serial for database update
    smart_changer.old_username = task.get('username')  # Current username
    smart_changer.device_serial = device_serial

    result = smart_changer.change_username_with_retry(
        target_username=task['new_username'],
        mother_account=task.get('mother_account'),
        max_attempts=5
    )

    if result['success']:
        final_username = result['final_username']
        print(f"✓ Username changed to: {final_username}")

        # Database and folder are already updated in smart_changer!
        changes_made.append("username")
```

---

## Testing Checklist

### **Before Username Change:**
```
10.1.10.36_5555/
├── accounts.db (account='anna.blnaa')
└── anna.blnaa/
    ├── settings.db
    └── ...
```

### **After Username Change:**
```
10.1.10.36_5555/
├── accounts.db (account='anna.newname')  ← UPDATED
└── anna.newname/                          ← RENAMED
    ├── settings.db
    └── ...
```

### **Verification:**
1. ✓ Folder renamed from `anna.blnaa` to `anna.newname`
2. ✓ `accounts.db` updated: `account` column = `anna.newname`
3. ✓ All files inside folder intact (settings.db, data.db, etc.)
4. ✓ Bot can still access account settings
5. ✓ Profile automation database updated (already handled)

---

## Edge Cases to Handle

### **1. Username Change Fails on Instagram**
```python
# If Instagram rejects username:
# - Don't rename folder
# - Don't update database
# - Try next variation
```

### **2. Folder Rename Fails**
```python
# If folder rename fails:
# - Rollback accounts.db update
# - Log error
# - Mark task as failed
```

### **3. accounts.db Doesn't Exist**
```python
# If accounts.db missing:
# - Still rename folder
# - Log warning
# - Continue (not critical)
```

### **4. Account Not in accounts.db**
```python
# If username not found in accounts.db:
# - Still rename folder
# - Log warning (might be manual account)
# - Continue
```

---

## Summary

### **What Needs Updating:**
1. ✓ **Folder name** (10.1.10.36_5555/old_username → new_username)
2. ✓ **accounts.db** (`account` column)
3. ✓ **profile_automation.db** (already handled by update_device_account)

### **What Doesn't Need Updating:**
- ✗ settings.db (doesn't store username)
- ✗ data.db, stats.db, etc. (account-specific, folder-independent)

### **Implementation:**
1. Create `update_username_in_bot.py` with rename + DB update logic
2. Integrate into `SmartUsernameChanger` after successful username change
3. Test with one account before batch operations

**The bot's folder structure and database will stay synchronized with Instagram usernames!**
