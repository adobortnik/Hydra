# Username Change - Database Sync Implementation Complete

## Summary

When a username changes on Instagram, the bot's database and folder structure are now **automatically synchronized**.

---

## What Happens When Username Changes

### **On Instagram:**
```
Old username: anna.blnaa
New username: anna.newname
```

### **In Bot's System (Automatic):**

1. **✓ Folder renamed:**
   ```
   10.1.10.36_5555/anna.blnaa/  →  10.1.10.36_5555/anna.newname/
   ```

2. **✓ accounts.db updated:**
   ```sql
   UPDATE accounts SET account = 'anna.newname' WHERE account = 'anna.blnaa'
   ```

3. **✓ Profile automation database updated:**
   ```sql
   UPDATE device_accounts SET username = 'anna.newname' WHERE device_serial = '10.1.10.36_5555'
   ```

---

## Files Created

### **1. update_username_in_bot.py** (New)
**Purpose:** Core logic for database and folder synchronization

**What it does:**
- Updates `accounts.db` (account column)
- Renames account folder
- Validates changes
- Rolls back on failure

**Usage:**
```python
from update_username_in_bot import update_username_in_bot

result = update_username_in_bot(
    device_serial="10.1.10.36_5555",
    old_username="anna.blnaa",
    new_username="anna.newname"
)

if result['success']:
    print(f"Folder renamed to: {result['renamed_folder']}")
```

---

### **2. smart_username_changer.py** (Modified)
**Changes:**
- Added `device_serial` and `old_username` parameters to `__init__`
- Calls `update_username_in_bot()` after successful Instagram username change
- Automatically syncs bot database

**New behavior:**
```python
def _attempt_username_change(self, username):
    # ... change username on Instagram ...

    if success:
        # NEW: Sync bot database
        if self.device_serial and self.old_username:
            update_username_in_bot(
                self.device_serial,
                self.old_username,
                username
            )
```

---

### **3. batch_profile_manager.py** (Modified)
**Changes:**
- Passes `device_serial` and `old_username` to `SmartUsernameChanger`

**New behavior:**
```python
smart_changer = SmartUsernameChanger(
    device=self.device,
    ai_api_key=task.get('ai_api_key'),
    ai_provider=task.get('ai_provider', 'openai'),
    device_serial=device_serial,        # NEW
    old_username=task.get('username')    # NEW
)
```

---

## Console Output Example

### **Old (Before Sync):**
```
SUCCESS! Username changed to: anna.newname

✓ Username changed
Changes: username
```

### **New (With Sync):**
```
SUCCESS! Username changed to: anna.newname

  --- Synchronizing Bot Database ---

======================================================================
UPDATING BOT DATABASE: anna.blnaa → anna.newname
======================================================================

✓ Found old account folder: 10.1.10.36_5555/anna.blnaa

--- Updating accounts.db ---
✓ Updated 1 row(s) in accounts.db

--- Renaming Account Folder ---
From: anna.blnaa
To:   anna.newname
✓ Folder renamed successfully!
✓ Verified: New folder exists, old folder gone

======================================================================
SUCCESS: Bot database synchronized with Instagram
======================================================================
Username: anna.blnaa → anna.newname
Folder:   anna.blnaa → anna.newname
Database: Updated
======================================================================

  ✓ Bot database synchronized
  ✓ Folder renamed: anna.blnaa → anna.newname

✓ Username changed
Changes: username
```

---

## Testing

### **Test Scenario:**
1. Create task to change username from `test.old` to `test.new`
2. Run batch processor
3. Verify:
   - ✓ Instagram username changed
   - ✓ Folder renamed: `10.1.10.36_5555/test.old` → `test.new`
   - ✓ `accounts.db` updated
   - ✓ All files inside folder intact

---

## Error Handling

### **Case 1: Username Change Succeeds, Folder Rename Fails**
```
✓ Instagram username changed
✗ Error renaming folder: Permission denied
⚠ Warning: Username changed on Instagram but bot folder not renamed!
```

**What happens:**
- Instagram username is changed
- Database NOT updated (avoids desync)
- Task marked as partial success
- User warned to manually rename folder

---

### **Case 2: Folder Already Exists**
```
✓ Instagram username changed
✗ New account folder already exists: 10.1.10.36_5555/test.new
⚠ Warning: Database sync failed
```

**What happens:**
- Instagram username is changed
- Folder NOT renamed (would overwrite existing)
- User warned about collision

---

### **Case 3: accounts.db Doesn't Exist**
```
✓ Instagram username changed
⚠ accounts.db not found - skipping database update
✓ Folder renamed successfully!
```

**What happens:**
- Instagram username is changed
- Folder IS renamed (this is critical)
- Database update skipped (not critical)
- Still considered success

---

## Benefits

### **1. Automatic Synchronization**
- ✅ No manual folder renaming needed
- ✅ No manual database updates needed
- ✅ Everything stays in sync

### **2. Bot Continues Working**
- ✅ Bot can still find account folder (uses new username)
- ✅ Settings, data, stats all preserved
- ✅ Scheduled posts continue working

### **3. Dashboard Integration**
- ✅ Profile automation tracks username changes
- ✅ Device accounts table updated automatically
- ✅ Tag associations maintained

---

## What Gets Updated

| Component | Before | After | Status |
|-----------|--------|-------|--------|
| **Instagram username** | anna.blnaa | anna.newname | ✅ Changed |
| **Folder name** | anna.blnaa/ | anna.newname/ | ✅ Renamed |
| **accounts.db** | account='anna.blnaa' | account='anna.newname' | ✅ Updated |
| **settings.db** | (no username stored) | (no username stored) | ✅ N/A |
| **data.db, stats.db** | (account-specific) | (account-specific) | ✅ Intact |
| **Profile automation DB** | username='anna.blnaa' | username='anna.newname' | ✅ Updated |

---

## Migration for Existing Accounts

If you have accounts with mismatched usernames/folders, you can manually sync them:

```python
from update_username_in_bot import update_username_in_bot

# Sync one account
result = update_username_in_bot(
    device_serial="10.1.10.36_5555",
    old_username="old_folder_name",
    new_username="current_instagram_username"
)

print(result['message'])
```

---

## Summary

**Implemented:**
1. ✅ `update_username_in_bot.py` - Core sync logic
2. ✅ `smart_username_changer.py` - Auto-calls sync after Instagram change
3. ✅ `batch_profile_manager.py` - Passes device/username info

**Result:**
- ✅ Bot folder structure stays synchronized with Instagram
- ✅ Bot database stays synchronized with Instagram
- ✅ All account data preserved during username change
- ✅ Automatic, no manual intervention needed

**The bot's database and Instagram are now always in sync!** 🎉
