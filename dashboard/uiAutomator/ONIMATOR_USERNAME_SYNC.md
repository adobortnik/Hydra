# Onimator Username Sync

## Overview

When our profile automation successfully changes an Instagram username, the system automatically syncs this change with the Onimator file structure.

## What Gets Updated

When a username changes from `old_username` to `new_username`, the system updates **3 critical locations**:

### 1. accounts.db (Device Root)
**Location:** `{device_serial}/accounts.db`
**Table:** `accounts`
**Field:** `account`
**Purpose:** Master account registry containing credentials and automation settings

```sql
UPDATE accounts SET account = 'new_username' WHERE account = 'old_username'
```

### 2. stats.db (Account Folder)
**Location:** `{device_serial}/{old_username}/stats.db`
**Table:** `stats`
**Field:** `account`
**Purpose:** Historical metrics and statistics tracking

```sql
UPDATE stats SET account = 'new_username' WHERE account = 'old_username'
```

### 3. Account Folder Name
**Location:** `{device_serial}/{username}/`
**Action:** Rename folder from `old_username` to `new_username`
**Purpose:** All account-specific files are under this folder

```bash
mv {device_serial}/old_username/ {device_serial}/new_username/
```

## How It Works

1. **Profile automation runs** and successfully changes Instagram username
2. **SmartUsernameChanger** confirms the change was successful
3. **sync_username_with_onimator()** function is called automatically
4. Function updates all 3 locations
5. Returns success/failure status with detailed logs

## Function Signature

```python
def sync_username_with_onimator(device_serial, old_username, new_username):
    """
    Sync Instagram username change with Onimator system

    Args:
        device_serial: Device serial (e.g., "10.1.10.192_5555")
        old_username: Current Instagram username (before change)
        new_username: New Instagram username (after change)

    Returns:
        dict: {
            'success': bool,
            'updates': list,  # List of successful update messages
            'errors': list    # List of error messages if any
        }
    """
```

## Integration

The sync happens automatically in `automated_profile_manager.py` after a successful username change:

```python
if result['success']:
    final_username = result['final_username']

    # ... log change ...

    # Sync username change with Onimator
    old_username = task.get('username', 'unknown')
    if old_username != 'unknown':
        sync_result = sync_username_with_onimator(
            device_serial=device_serial,
            old_username=old_username,
            new_username=final_username
        )
        if sync_result['success']:
            print("✅ Onimator sync successful!")
        else:
            print(f"⚠ Onimator sync had errors: {sync_result['errors']}")
```

## What Doesn't Need Updating

These files/databases in the account folder reference OTHER accounts (not the account's own username), so they don't need updating:

- **data.db** - Tracks followed/liked users
- **comments.db** - Comments from/to other users
- **likes.db** - Liked posts by other users
- **directmessage.db** - Messages with other users
- **sent_message.db** - Sent messages to other users
- **shared_post.db** - Shared posts from other users
- **storyviewer.db** - Story interactions with other users
- **likeexchange.db** - Like exchange data
- **scheduled_post.db** - Post scheduling
- **2factorauthcodes.db** - Auth codes
- **filtersettings.db** - Filter settings
- **settings.db** - Account settings (JSON, doesn't reference username)
- **sources.txt** - Source usernames to follow from

## Error Handling

The function handles several error scenarios gracefully:

- **Device folder doesn't exist**: Returns error, sync fails
- **Account not found in accounts.db**: Logs warning, continues with other updates
- **stats.db doesn't exist**: Logs warning, continues
- **New username folder already exists**: Returns error, prevents overwrite
- **Folder rename fails**: Returns error with details

## Example Output

```
======================================================================
SYNCING USERNAME CHANGE WITH ONIMATOR
Device: 10.1.10.192_5555
Old Username: jagger_boss
New Username: jagger.official
======================================================================

✓ Updated accounts.db (account: jagger_boss → jagger.official)
✓ Updated stats.db (3 row(s): jagger_boss → jagger.official)
✓ Renamed folder: jagger_boss/ → jagger.official/

======================================================================
✅ ONIMATOR SYNC COMPLETE
Total updates: 3
======================================================================
```

## Manual Usage

You can also call the function manually if needed:

```python
from automated_profile_manager import sync_username_with_onimator

result = sync_username_with_onimator(
    device_serial="10.1.10.192_5555",
    old_username="jagger_boss",
    new_username="jagger.official"
)

if result['success']:
    print("Sync successful!")
    for update in result['updates']:
        print(f"  {update}")
else:
    print("Sync failed!")
    for error in result['errors']:
        print(f"  ERROR: {error}")
```

## Testing

To test the sync function without running full automation:

1. Create a test account folder with minimal structure
2. Add entry to accounts.db
3. Add stats.db with test data
4. Run sync function
5. Verify all 3 updates occurred

## Requirements

- SQLite3 (built-in with Python)
- Onimator file structure must exist
- Account must exist in accounts.db
- Account folder must exist with stats.db

## Notes

- Sync is **automatic** - no manual intervention required
- Safe to run even if some components are missing (graceful degradation)
- All operations are logged for debugging
- Folder rename is atomic (all-or-nothing)
- **Important**: Old username must be known (stored in task when campaign created)
