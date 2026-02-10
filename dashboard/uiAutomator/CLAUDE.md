# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Instagram automation tool built with Python that uses uiautomator2 to control Instagram on Android devices via ADB. The script automates profile management tasks like navigating to profile pages, editing usernames, changing profile pictures, and updating bios.

**🔥 NEW: Tag-Based Batch Automation System** - Automate profile changes across multiple accounts by tagging them (e.g., "chantall", "anna"). Create campaigns to update all tagged accounts with one command. Includes AI integration for intelligent username/bio generation based on a "mother account". Fully integrated with the-livehouse-dashboard via REST API.

**🔥 NEW: Automatic Onimator Username Sync** - When profile automation successfully changes an Instagram username, the system automatically updates all Onimator files (accounts.db, stats.db, and renames the account folder). No manual intervention required to keep Onimator in sync with Instagram changes.

## Setup and Environment

### Initial Setup
```bash
# Run the setup script to create virtual environment and install dependencies
bash setup.sh

# Or manually:
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Prerequisites
- Android device with USB debugging enabled
- ADB installed and accessible in PATH
- Instagram app (original or clones) installed on device
- Device connected via USB or accessible via network IP

### Running the Script
```bash
# Activate virtual environment first
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Run with USB device (interactive selection)
python instagram_automation.py

# Run with specific device IP
python instagram_automation.py <device_ip>
```

## Architecture

### Main Components

**Device Connection & Selection** (`select_device()`, `connect_device()`)
- Lists all ADB-connected devices with details (serial, model, product)
- Interactive device selection menu
- Supports both USB and network (IP) connections
- Uses uiautomator2 for device control

**Instagram Package Management** (`select_instagram_package()`)
- Supports original Instagram app (`com.instagram.android`)
- Supports Instagram clones from `com.instagram.androide` through `com.instagram.androidp`
- Interactive package selection for multi-account management

**App Navigation** (`open_instagram()`, `navigate_to_profile()`)
- Launches Instagram with specific package name and activity path
- Navigates to profile tab using multiple selector strategies
- Falls back to coordinate-based clicking if UI elements not found

**Profile Editing Functions**
- `navigate_to_edit_profile()`: Opens edit profile screen
- `change_profile_picture()`: Initiates profile picture change flow
- `edit_username()`: Navigates to username edit screen and modifies username
- `edit_bio()`: Finds and edits bio field
- `save_profile_changes()`: Saves modifications

**Interactive Menu System** (`show_menu()`, `main()`)
- State-tracked menu system (knows if on edit profile screen)
- Six action modes: navigate to profile, edit profile, change picture, edit username, edit bio, full profile edit
- Ensures proper navigation flow between screens

### UI Element Selection Strategy

The script uses a robust multi-layered approach to find UI elements:

1. **Primary selectors**: Resource IDs, text matches, content descriptions
2. **XPath fallbacks**: When standard selectors fail
3. **Coordinate-based fallbacks**: Last resort using screen dimensions
4. **Context-aware clicking**: Uses element bounds to calculate relative click positions

This pattern repeats throughout all navigation functions to handle Instagram version differences.

### Username Edit Flow

The username editing is more complex than other fields:

1. Click on username field on edit profile screen (below "Username" label)
2. Wait for navigation to dedicated username edit screen
3. Find EditText field on new screen
4. Clear existing text via long-press + select all + delete
5. Input new username via ADB shell command
6. Navigate back and save

This multi-screen flow is unique to username editing in Instagram's UI.

## Key Implementation Notes

### ⚠️ CRITICAL: UIAutomator Service Connection and Startup

**The Problem: UIAutomator service stops and must be restarted programmatically**

When UIAutomator service is stopped (in ATX Agent app), all UI operations fail with "UiAutomation not connected" error. This includes `.exists()`, `.click()`, `.text()`, and any selector interactions.

**The Solution: Kill all processes, then let u2.connect() auto-start UIAutomator**

This was discovered after 3+ hours of debugging by analyzing the working GramAddict bot and testing various approaches.

**✅ WORKING CONNECTION PATTERN:**

```python
import subprocess
import time
import uiautomator2 as u2

# Convert folder naming (underscore) to ADB format (colon)
connection_serial = device_serial.replace('_', ':')  # "10.1.10.36_5555" → "10.1.10.36:5555"

# STEP 1: Kill ALL existing UIAutomator processes to start fresh
print("Cleaning up existing UIAutomator processes...")
try:
    # Kill all uiautomator processes
    subprocess.run(
        ['adb', '-s', connection_serial, 'shell', 'pkill', '-9', 'uiautomator'],
        capture_output=True, timeout=5
    )
    # Force stop the app
    subprocess.run(
        ['adb', '-s', connection_serial, 'shell', 'am', 'force-stop', 'com.github.uiautomator'],
        capture_output=True, timeout=5
    )
    # Kill any existing instrumentation processes
    subprocess.run(
        ['adb', '-s', connection_serial, 'shell', 'pkill', '-9', '-f', 'androidx.test.runner'],
        capture_output=True, timeout=5
    )
    print("Killed all UIAutomator-related processes")
    print("Waiting for complete shutdown...")
    time.sleep(5)  # CRITICAL: Wait for complete shutdown before connecting
except Exception as e:
    print(f"Warning during cleanup: {e}")

# STEP 2: Connect to device - u2.connect() will auto-start UIAutomator
print("Connecting to device...")
print("(uiautomator2 will automatically start UIAutomator service)")
device = u2.connect(connection_serial)  # ✅ This auto-starts UIAutomator
print(f"Connected (serial: {device.serial})")

# STEP 3: Wait for UIAutomator to be responsive
print("Waiting for UIAutomator to be responsive...")
max_wait = 45  # seconds
start_time = time.time()

while (time.time() - start_time) < max_wait:
    try:
        _ = device.info
        _ = device.window_size()
        elapsed = int(time.time() - start_time)
        print(f"SUCCESS! UIAutomator is responsive (took {elapsed}s)")
        break
    except Exception as e:
        elapsed = int(time.time() - start_time)
        if elapsed % 5 == 0:  # Print every 5 seconds
            print(f"Waiting... {elapsed}s / {max_wait}s")
        time.sleep(1)
```

**Why This Works:**

1. **Kill everything first**: Ensures no stale processes that could conflict
2. **Wait 5 seconds**: Critical for processes to fully terminate before reconnecting
3. **u2.connect() auto-starts**: The library has built-in logic to start UIAutomator when needed
4. **Don't manually start instrumentation**: Manually starting causes "UiAutomationService already registered!" error
5. **Wait for responsive**: UIAutomator can take 10-40 seconds to fully start

**❌ WHAT DOESN'T WORK:**

- `device.uiautomator.start()` - Attribute doesn't exist
- `device.reset_uiautomator()` - Takes no 'reason' parameter in some versions, and doesn't reliably start
- `device.healthcheck()` - Not available in all versions
- Manually starting instrumentation via `am instrument` before connecting - Causes "already registered" error
- HTTP POST to `http://device_ip:7912/uiautomator` - Port 7912 not accessible over network
- Using `u2.connect_adb_wifi()` - Method doesn't exist in current uiautomator2 versions

**Key Insight from GramAddict Bot Analysis:**

The working GramAddict bot uses the simple pattern:
1. Connect with `u2.connect()`
2. Call `device.info` multiple times to "wake up" the service
3. Let uiautomator2's built-in auto-start handle the rest

**Serial Format:**
- Device folders use underscore: `10.1.10.36_5555`
- ADB commands need colon: `10.1.10.36:5555`
- Always convert: `connection_serial = device_serial.replace('_', ':')`

**This issue cost 4+ hours of debugging** - the solution is counterintuitive (kill everything, don't manually start, just connect and wait).

### Selector Patterns
All automation functions use lists of potential selectors tried in sequence:
```python
selectors = [
    device(text="..."),
    device(description="..."),
    device(resourceId="..."),
    device.xpath('...'),
]
```

This pattern handles Instagram UI variations across versions and clones.

### Screen State Management
The main loop tracks `on_edit_profile_screen` boolean to:
- Prevent redundant navigation
- Ensure proper screen context for actions
- Guide menu flow logic

### Error Handling Philosophy
Functions return boolean success/failure but continue execution on errors, printing warnings. This allows partial automation success and manual intervention.

### Input Methods
- UI clicks: `device.click()`, `selector.click()`
- Text input: `device.shell('input text ...')` for reliability
- Keyboard: `device.press("back")`, `device.press("delete")`
- Selection: `long_click()` + "Select all" + delete pattern

## Testing Notes

Since this is automation code that requires physical device interaction:
- Test with actual Android device connected
- Test both USB and network connections
- Verify with original Instagram and at least one clone package
- Test username changes require sufficient wait times between API calls (Instagram rate limiting)
- Manual intervention may be required for gallery selection and confirmation dialogs

## Common Modifications

**Adding new profile fields**: Follow the pattern in existing edit functions - multiple selectors, timeout handling, fallback to coordinate clicking.

**Supporting new Instagram versions**: Add new resource IDs or selectors to existing selector lists in navigation functions.

**Adding new automation actions**: Ensure proper screen state validation before action execution, use selector list pattern, provide coordinate fallback.

---

## 🚀 TAG-BASED AUTOMATION SYSTEM (NEW)

### System Architecture

The tag-based automation system extends the basic profile automation with campaign management, AI generation, and dashboard integration.

#### Core Components

1. **profile_automation_db.py** - SQLite database layer
   - `profile_updates`: Task queue for profile changes
   - `profile_pictures`: Image library with metadata (gender, category, usage tracking)
   - `bio_templates`: Reusable bio text templates
   - `tags`: Tag definitions (e.g., "chantall", "anna")
   - `account_tags`: Maps accounts to tags
   - `tag_campaigns`: Campaign definitions with strategies
   - `profile_history`: Complete change audit log
   - `device_accounts`: Current state of each device/account

2. **tag_based_automation.py** - Tag & campaign management
   - `TagBasedAutomation` class - Main automation controller
   - `create_tag()`: Create account groupings
   - `tag_account()`, `bulk_tag_accounts()`: Assign tags to accounts
   - `get_accounts_by_tag()`: Query tagged accounts
   - `create_campaign()`: Define profile update campaigns
   - `execute_campaign()`: Generate tasks for all tagged accounts
   - Supports multiple strategies (rotate, random, AI-based)

3. **ai_profile_generator.py** - AI integration layer
   - `AIProfileGenerator` class - AI API wrapper
   - Supports OpenAI (GPT-4), Anthropic (Claude), custom endpoints
   - `generate_username()`: Create username variations based on mother account
   - `generate_bio()`: Create bio variations based on mother account's bio
   - Smart fallbacks when AI unavailable
   - Instagram rule validation (username constraints, bio length)

4. **automated_profile_manager.py** - Task processor
   - `AutomatedProfileManager` class - Batch execution engine
   - `transfer_image_to_device()`: ADB image transfer
   - `change_profile_picture_automated()`: Fully automated picture selection
   - `edit_bio_automated()`: Enhanced bio editing with fallbacks
   - `edit_username_automated()`: Uses existing username edit flow
   - `process_single_task()`: Complete task execution
   - `run_batch_processor()`: Process all pending tasks
   - `sync_username_with_onimator()`: Auto-sync username changes with Onimator (updates accounts.db, stats.db, renames folder)

5. **profile_task_manager.py** - Interactive CLI manager
   - Menu-driven task creation
   - Profile picture library management
   - Bio template management
   - View pending tasks and device info

6. **profile_automation_routes.py** (in the-livehouse-dashboard/)
   - Flask Blueprint for REST API
   - `/api/profile_automation/quick_campaign` - One-click automation
   - `/api/profile_automation/tags` - Tag management
   - `/api/profile_automation/accounts/tag` - Account tagging
   - `/api/profile_automation/campaigns` - Campaign CRUD
   - `/api/profile_automation/ai/generate/*` - AI generation endpoints
   - Integrated into `simple_app.py` via blueprint registration

### Data Flow

```
1. Tag accounts → tag_based_automation.tag_account()
2. Create campaign → tag_based_automation.create_campaign()
3. Execute campaign → Generates tasks in profile_updates table
4. Run processor → automated_profile_manager.run_batch_processor()
5. For each task:
   - Connect to device
   - Open Instagram
   - Navigate to edit profile
   - Change picture (transfer image, select from gallery)
   - Change username (navigate to username screen, edit)
     → If successful: Auto-sync with Onimator (update accounts.db, stats.db, rename folder)
   - Change bio (find field, update text)
   - Save changes
   - Update database (status, history, device state)
```

### Campaign Strategies

**Profile Picture Strategies:**
- `rotate`: Cycle through available pictures
- `random`: Random assignment
- `least_used`: Prioritize unused pictures

**Bio Strategies:**
- `template`: Use bio templates from database
- `ai`: AI-generated variations of mother account bio
- `fixed`: Same bio for all accounts

**Username Strategies:**
- `variation`: Algorithmic variations (username1, username.2, etc.)
- `ai`: AI-generated based on mother account style
- `manual`: Skip username changes

### AI Integration Details

When `use_ai=True` in a campaign:

1. **Username Generation:**
   - Analyzes mother account username style
   - Generates variations that match the pattern
   - Validates against Instagram rules (no consecutive periods, max 30 chars)
   - Example: "chantall.main" → "chantall.official", "chantall.style", "chantall.paris"

2. **Bio Generation:**
   - Uses mother account bio as template
   - Creates slight variations maintaining theme
   - Respects 150 character limit
   - Example: "✨ Fashion & Lifestyle | 📍 Paris" → "🌟 Style & Life | Paris based"

3. **Fallback Behavior:**
   - If AI fails or no API key: uses algorithmic generation
   - System always works, AI is enhancement not requirement

### Dashboard Integration

The system is integrated into the-livehouse-dashboard:

1. **simple_app.py** imports `profile_automation_bp`
2. All API endpoints available at `/api/profile_automation/*`
3. Frontend can:
   - Tag accounts by device or username
   - Create and execute campaigns
   - View pending tasks
   - Test AI generation
   - Quick campaign (one-click automation)

### File Organization

```
uiAutomator/
├── instagram_automation.py              # Original core automation
├── profile_automation_db.py             # Database layer
├── tag_based_automation.py              # Tag & campaign system
├── ai_profile_generator.py              # AI integration
├── automated_profile_manager.py         # Batch processor
├── profile_task_manager.py              # CLI manager
├── api_integration_example.py           # API usage examples
├── profile_automation.db                # SQLite database
├── profile_pictures/                    # Image library
│   ├── male/
│   ├── female/
│   ├── neutral/
│   └── uploaded/
├── CLAUDE.md                            # This file
├── PROFILE_AUTOMATION_README.md         # Full system documentation
├── TAG_AUTOMATION_GUIDE.md              # Tag-based automation guide
├── ONIMATOR_USERNAME_SYNC.md            # Onimator username sync documentation
└── test_onimator_sync.py                # Test script for Onimator sync

the-livehouse-dashboard/
├── simple_app.py                        # Main Flask app (MODIFIED)
└── profile_automation_routes.py         # Profile automation API (NEW)
```

### Quick Start for Tag Automation

```python
from tag_based_automation import TagBasedAutomation

automation = TagBasedAutomation()

# 1. Tag accounts
automation.bulk_tag_accounts("chantall", device_serials=["192.168.101.107_5555"])

# 2. Create campaign
campaign_id = automation.create_campaign(
    tag_name="chantall",
    campaign_name="Chantall Profile Update",
    mother_account="chantall.main",
    use_ai=False,
    strategies={'profile_picture': 'rotate', 'bio': 'template', 'username': 'variation'}
)

# 3. Execute
automation.execute_campaign(campaign_id)

# 4. Process
# Run: python automated_profile_manager.py
```

### Key Implementation Patterns

**Tag-based account grouping:**
- Accounts are tagged with labels (stored in `account_tags` table)
- Tags enable bulk operations (update all "chantall" accounts)
- Multiple tags per account supported

**Campaign execution:**
- Campaign defines strategies for picture/bio/username
- Execute creates one task per tagged account
- Tasks processed by `automated_profile_manager.py`

**AI generation:**
- Optional enhancement (works without AI)
- Mother account defines the style/theme
- Variations generated to look like related accounts
- Validates Instagram constraints

**Image transfer workflow:**
- Picture copied to device via ADB push
- Saved to `/sdcard/Pictures/profile_pic_{timestamp}.jpg`
- Media scanner triggered so gallery apps see it
- Automation clicks first image in gallery (newest)

### Testing Tag Automation

1. Initialize: `python profile_automation_db.py`
2. Tag 2-3 test accounts
3. Create campaign with strategies
4. Execute campaign
5. Run processor: `python automated_profile_manager.py`
6. Verify changes on devices

### Documentation Files

- **PROFILE_AUTOMATION_README.md**: Complete system documentation
- **TAG_AUTOMATION_GUIDE.md**: Tag-based automation guide with examples
- **ONIMATOR_USERNAME_SYNC.md**: Onimator username sync documentation
- **api_integration_example.py**: Python API usage examples

---

## 🔥 ONIMATOR USERNAME SYNC (NEW)

### Overview

When profile automation successfully changes an Instagram username, the system **automatically syncs** the change with Onimator's file structure. This eliminates the need to manually update account folders and databases.

### What Gets Updated

When a username changes from `jagger_boss` → `jagger.official`, the system updates **3 locations**:

1. **accounts.db** (device root) - Master account registry
   - Updates `accounts.account` field

2. **stats.db** (account folder) - Historical metrics
   - Updates `stats.account` field in all rows

3. **Account folder name** - Folder rename
   - Renames `{device_serial}/jagger_boss/` → `{device_serial}/jagger.official/`

### How It Works

```python
# Automatic sync after successful username change
if username_change_successful:
    sync_result = sync_username_with_onimator(
        device_serial="10.1.10.192_5555",
        old_username="jagger_boss",
        new_username="jagger.official"
    )
```

The function:
1. Updates `accounts.db` with SQL UPDATE
2. Updates `stats.db` with SQL UPDATE
3. Renames the account folder
4. Returns detailed success/error report

### Integration

Integrated into `automated_profile_manager.py` - runs automatically after any successful username change. No configuration needed.

### Example Output

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

### Testing

Test the sync function without running full automation:

```bash
# Verify preconditions only (safe, read-only)
python test_onimator_sync.py --device 10.1.10.192_5555 --old jagger_boss --new jagger.official --verify-only

# Execute sync (modifies Onimator files!)
python test_onimator_sync.py --device 10.1.10.192_5555 --old jagger_boss --new jagger.official
```

### Requirements

- Onimator device folder must exist (`{device_serial}/`)
- Account folder must exist (`{device_serial}/{old_username}/`)
- `accounts.db` should exist (but sync continues if missing)
- `stats.db` should exist (but sync continues if missing)

### Error Handling

The sync is **graceful** - if some files are missing, it updates what it can and logs warnings. Only critical errors (missing device folder, missing account folder, new username already exists) cause the sync to fail.

### See Also

- Full documentation: [ONIMATOR_USERNAME_SYNC.md](ONIMATOR_USERNAME_SYNC.md)
- Test script: [test_onimator_sync.py](test_onimator_sync.py)
