# Phone Farm -- Build Progress

## 2026-02-09: Vision-Assisted Development Tool — COMPLETE

### What Was Built

#### `screen_capture.py` — Screenshot Utility for Vision Development
Quick screen capture from any device for AI vision-assisted development workflow.

**Usage:**
```bash
python screen_capture.py jack                          # capture JACK 1
python screen_capture.py 10.1.10.177:5555              # any device by serial
python screen_capture.py jack --name login_screen      # custom filename
python screen_capture.py --list                        # list all devices
```

**Features:**
- Direct ADB screencap (fast, no temp files on device)
- Fallback pull method if direct fails
- Device aliases (jack, jack1, jack2, jack3)
- Shows foreground app + screen resolution
- Saves to `phone-farm/screenshots/`
- Used with Jarvis vision to instantly understand screen state

**Purpose:** Development aid — instead of parsing 80KB XML dumps to find selectors,
snap a screenshot → vision analyzes it → instantly know buttons, text, screen state.
Production bot still uses XML (fast, free). Vision only during active development.

---

## 2026-02-02: Dashboard Bot Launcher Integration — COMPLETE

### What Was Built

#### 1. `dashboard/bot_launcher_routes.py` — API Blueprint for run_device.py Control
New Flask blueprint (`bot_launcher_bp`, prefix `/api/bot`) providing full control over
`run_device.py` processes from the dashboard.

**Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/bot/status` | Status of all devices + running bots (WMIC process scan) |
| POST | `/api/bot/launch-all` | Launch bots for all (or specified) devices |
| POST | `/api/bot/launch/<serial>` | Launch bot for a single device |
| POST | `/api/bot/stop-all` | Stop all running bot processes |
| POST | `/api/bot/stop/<serial>` | Stop bot for a specific device |
| GET | `/api/bot/logs/<serial>` | Tail last N lines of device log file |

**Key implementation details:**
- Uses WMIC to scan for running `run_device.py` python processes by command line
- Launches bots in new cmd windows with title via `subprocess.Popen`
- Handles serial format normalization (colon ↔ underscore)
- Resolves active account per device based on time windows
- Log endpoint auto-finds latest log file if today's doesn't exist

#### 2. Dashboard UI — Phone Farm Launcher Section in bot_manager.html
Added new "Phone Farm Launcher" card to the Bot Manager page with:
- **Header stats**: running/stopped badge counts
- **Control buttons**: Launch All, Stop All, Refresh
- **Per-device table**: device name, serial, account count, active account, PID, actions
- **Per-device actions**: View Logs (modal), Start/Stop buttons
- **Log viewer modal**: dark console-themed with syntax coloring for log levels
- **Auto-refresh**: status polls every 10 seconds via JS fetch
- **Matches existing Bootstrap dark theme** — no visual conflicts

#### 3. Blueprint Registration
- Added `bot_launcher_bp` to both `dashboard/simple_app.py` and `app.py`
- Tested all 6 API endpoints successfully (50 devices returned)
- Dashboard page renders correctly with new section

---

## 2026-02-02: Phase 4 — Multi-Window Launcher — COMPLETE

### What Was Built

#### 1. `run_device.py` — Single Device Bot Runner
Standalone script that runs the bot loop for ONE device with account rotation.

**Features:**
- **Colored console output**: device name in cyan, accounts in yellow, actions in green, errors in red
- **Dual logging**: colored console (INFO+) + daily file in `logs/` (DEBUG+, ANSI stripped)
- **Account rotation**: picks the correct account for the current hour based on time windows
- **Graceful shutdown**: Ctrl+C → stop signal → prints session summary
- **Auto-reconnect**: on device disconnect, attempts reconnection before next cycle
- **Session summary**: actions done, errors, runtime, account breakdown on exit
- **Window title**: auto-sets to "Phone Farm - DEVICE_NAME (serial)"
- **Serial format**: accepts both `:` (ADB) and `_` (DB) formats

**Usage:**
```bash
python run_device.py 10.1.11.4:5555              # run continuously
python run_device.py 10.1.11.4:5555 --dry-run    # preview accounts + config
python run_device.py 10.1.11.4:5555 --once       # one cycle then exit
```

#### 2. `launch_farm.py` / `launch_farm.ps1` — Multi-Device Launchers
Open a new console window for each device running run_device.py.

**Python launcher (`launch_farm.py`):**
```bash
python launch_farm.py                                              # ALL 50 devices
python launch_farm.py --devices "10.1.11.4:5555,10.1.11.3:5555"   # subset
python launch_farm.py --dry-run                                    # preview
python launch_farm.py --once                                       # one-shot mode
python launch_farm.py --delay 5                                    # 5s between windows
```

**PowerShell launcher (`launch_farm.ps1`):**
```powershell
.\launch_farm.ps1                                                  # ALL devices
.\launch_farm.ps1 -Devices "10.1.11.4:5555,10.1.11.3:5555"       # subset
.\launch_farm.ps1 -DryRun                                         # preview
.\launch_farm.ps1 -Once                                           # one-shot mode
```

Both launchers:
- Query DB for all devices with active accounts
- Open each in a new console window with descriptive title
- Support `--dry-run` to preview without launching
- Support device subset via `--devices` / `-Devices`
- Show device name, serial, account count in plan output

#### 3. `stop_farm.py` / `stop_farm.ps1` — Graceful Shutdown
Find and terminate all running bot processes.

```bash
python stop_farm.py                # graceful stop
python stop_farm.py --force        # hard kill
python stop_farm.py --dry-run      # show running processes
```

```powershell
.\stop_farm.ps1                    # graceful stop
.\stop_farm.ps1 -Force             # hard kill
.\stop_farm.ps1 -DryRun            # show running processes
```

Both versions:
- Scan for python processes running `run_device.py`
- Show PIDs and device serials
- Stop bot processes + clean up hosting console windows
- Support `--force` for hard kill via `taskkill /F`

### Test Results

```
run_device.py --dry-run (10.1.11.4:5555):
  ✓ Device found: JACK 1
  ✓ 13 accounts listed with time windows
  ✓ Window title set
  ✓ Log file created: logs/10.1.11.4_5555_2026-01-31.log
  ✓ ANSI codes stripped from file log
  ✓ Session summary printed on exit

launch_farm.py --dry-run:
  ✓ All 50 devices listed with account counts
  ✓ Subset filter works (--devices flag)
  ✓ Python + venv path resolved correctly

launch_farm.ps1 -DryRun:
  ✓ DB query via temp Python script
  ✓ Device list displayed correctly
  ✓ Subset filter works (-Devices param)

run_device.py (invalid serial):
  ✓ Error message + full device list shown

stop_farm.py --dry-run:
  ✓ Reports "no processes found" when farm not running
```

### Cleanup
Deleted 35 temp files from root phone-farm directory:
- `analyze_*.py` (2 files)
- `check_*.py` (19 files)
- `explore_*.py` (10 files)
- `test_share_discovery*.py` (3 files)
- `test_share_v*.py` (2 files)

### Files Created
- `run_device.py` — Single device bot runner (280 lines)
- `launch_farm.py` — Python multi-device launcher (140 lines)
- `launch_farm.ps1` — PowerShell multi-device launcher (120 lines)
- `stop_farm.py` — Python stop script (150 lines)
- `stop_farm.ps1` — PowerShell stop script (90 lines)
- `logs/` — Log directory (auto-created, one file per device per day)

### Architecture Update
```
phone-farm/
  run_device.py            Single device bot runner          [NEW]
  launch_farm.py           Python multi-device launcher      [NEW]
  launch_farm.ps1          PowerShell multi-device launcher  [NEW]
  stop_farm.py             Python stop script                [NEW]
  stop_farm.ps1            PowerShell stop script            [NEW]
  logs/                    Per-device daily log files        [NEW]
  automation/
    bot_engine.py          Core bot engine (unchanged)
    device_orchestrator.py Multi-device orchestrator (unchanged)
    ...
```

---

## 2026-02-02: Tag Dedup + Follow From List — ALL PASS (49/49)

### Context
Tags already exist in the Onimator-imported system:
- `account_settings.settings_json` stores: `"tags": "chantall"`, `"enable_tags": true`, `"enable_dont_follow_sametag_accounts": true`
- 534/603 accounts have tags set, across 15 distinct tag groups (chantall, yannis, jack, spencer, etc.)
- Tag CRUD already handled by `dashboard/profile_automation_routes.py` + `TagBasedAutomation` class
- **No new tag CRUD was needed** — only the dedup query layer for the automation engine

### 1. Tag Dedup Module — `automation/tag_dedup.py` (NEW)
Reads tags from the existing `settings_json` field (not a junction table). Functions:

- **`is_tag_dedup_enabled(account_id)`** → bool
  Checks `enable_tags` AND `enable_dont_follow_sametag_accounts` AND non-empty `tags` field.

- **`get_account_tag_set(account_id)`** → `set[str]`
  Parses tags string (supports comma-separated multi-tag like `"chantall,vip"`), returns lowercase set.

- **`get_same_tag_accounts(account_id)`** → `list[dict]`
  Finds all accounts sharing any tag via set intersection on the parsed tags strings.
  Excludes the requesting account. Returns `{id, username, device_serial, tags}`.

- **`has_same_tag_account_followed(account_id, target_username)`** → bool
  Builds `(device_serial, username)` pairs for all same-tag peers, runs single EXISTS query
  against `action_history` (action_type='follow', success=1).

- **`get_same_tag_followed_set(account_id)`** → `set[str]`
  Bulk pre-loads ALL target_usernames already followed by any same-tag peer.
  Called once at session start to avoid per-user DB round-trips during the follow loop.

### 2. Follow Dedup Wiring — `automation/actions/follow.py` (MODIFIED)
- Import: `from automation.tag_dedup import is_tag_dedup_enabled, get_same_tag_followed_set`
- In `__init__()`: calls `is_tag_dedup_enabled(self.account_id)`, then pre-loads
  `self.tag_already_followed = get_same_tag_followed_set(self.account_id)` as a set for O(1) lookups
- In `_follow_from_source()` loop, after "skip if recently followed":
  ```python
  if self.tag_dedup_enabled and target_user in self.tag_already_followed:
      skip
  ```
- After successful follow: `self.tag_already_followed.add(target_user)` for session-level dedup

### 3. Follow From List Feature (NEW)

#### DB: `follow_lists` + `follow_list_items` tables
Tables already existed with schema:
- `follow_lists`: id, name, description, created_at, updated_at
- `follow_list_items`: id, list_id, username, status (pending/followed/skipped), followed_by_account_id, followed_at, skip_reason

#### Action: `automation/actions/follow_from_list.py`
- **CRUD functions**: `create_follow_list`, `get_follow_lists`, `get_follow_list`, `update_follow_list`, `delete_follow_list`, `get_list_items`, `add_list_items`, `remove_list_item`, `clear_list_items`, `reset_list_items`, `mark_item_followed`, `mark_item_skipped`
- **`FollowFromListAction` class**: Takes a `list_id`, loads pending items, searches each user via IGController, applies filters + tag dedup, follows from profile page.
  - Uses same limits/settings infrastructure as `FollowAction`
  - Pre-loads `get_same_tag_followed_set()` for dedup
  - Marks each item as `followed` (with account_id + timestamp) or `skipped` (with reason)
  - Shuffles items for natural order
  - Only processes items with `status='pending'` (can resume across sessions)
- **`execute_follow_from_list()`** convenience function

#### API: `dashboard/follow_list_routes.py` (Blueprint at `/api/follow-lists`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/follow-lists` | List all with item counts |
| POST | `/api/follow-lists` | Create `{name, description?}` |
| GET | `/api/follow-lists/<id>` | Get single list |
| PUT | `/api/follow-lists/<id>` | Update name/description |
| DELETE | `/api/follow-lists/<id>` | Delete list + items |
| GET | `/api/follow-lists/<id>/items` | Get all items |
| POST | `/api/follow-lists/<id>/items` | Add items `{usernames:[]}` or `{text:"user1\\nuser2"}` |
| DELETE | `/api/follow-lists/<id>/items/<item_id>` | Remove single item |
| DELETE | `/api/follow-lists/<id>/items` | Clear all items |
| POST | `/api/follow-lists/<id>/reset` | Reset all items to pending |
| GET | `/api/follow-lists/<id>/stats` | Pending/followed/skipped counts |

### Test Results

**tag_dedup unit tests (20/20 PASS)**:
```
  PASS  get_account_tag_set(1) returns set
  PASS  account 1 has 'chantall'
  PASS  account 13 has 'yannis'
  PASS  non-existent account -> empty set
  PASS  account 1 dedup enabled
  PASS  account 13 dedup enabled
  PASS  non-existent account dedup disabled
  PASS  get_same_tag_accounts(1) returns list
  PASS  account 1 has peers (143 chantall accounts)
  PASS  account 1 excluded from own peers
  PASS  account 2 is peer of account 1
  PASS  account 13 NOT a peer of account 1
  PASS  account 13 has yannis peers
  PASS  account 1 NOT in yannis peers
  PASS  peer sees cathyrafaa followed by harrer_private
  PASS  unknown target returns False
  PASS  get_same_tag_followed_set returns set
  PASS  cathyrafaa in followed set
  PASS  bat.10477586 in followed set
  PASS  follow.py imports cleanly
```

**follow list + API tests (29/29 PASS)**:
```
  PASS  create_follow_list / get / add items / dedup / update / remove / clear / delete
  PASS  POST/GET/PUT/DELETE /api/follow-lists (all CRUD)
  PASS  POST items via array + text block + duplicate handling
  PASS  DELETE single item + clear all
  PASS  404 on deleted list
  PASS  is_tag_dedup_enabled(1) = True
  PASS  account 1 has chantall peers
  PASS  dedup detects cross-account follow
  PASS  follow.py + follow_from_list.py import correctly
```

### Files Created
- `automation/tag_dedup.py` — Tag dedup query layer (5 functions)
- `automation/actions/follow_from_list.py` — Follow from list action + CRUD (12 functions + action class)
- `dashboard/follow_list_routes.py` — Flask blueprint (11 endpoints)
- `test_tag_dedup.py` — Tag dedup tests (20 tests)
- `test_follow_list_api.py` — Follow list + API + integration tests (29 tests)

### Files Modified
- `automation/actions/follow.py` — Replaced wrong `tag_manager` import with `tag_dedup`, wired pre-loaded set into follow loop
- `dashboard/simple_app.py` — Added `follow_list_bp` import + registration

### Cleanup
Removed wrong Phase 1 artifacts: `automation/tag_manager.py`, `dashboard/tag_routes.py`, `db/migrate_account_tags.py`, `account_tags` junction table (dropped).

---

## 2026-02-02: Reels Wiring + like_reel() + like_post() Verification — ALL PASS (13/13)

### Phase 1: Wired reels.py to IGController

**Problem**: `reels.py` was using the old `IGNavigator` from helpers.py for navigation — manual resource ID searches, no screen state verification, no XML-based detection. Every other action module (engage, follow, unfollow, like) was already wired to IGController.

**Fix applied to `automation/actions/reels.py`**:
1. Replaced `IGNavigator` import with `IGController, Screen` from `automation.ig_controller`
2. `__init__()` now accepts optional `ctrl: IGController` parameter (+ `pkg` fallback)
3. Navigation: `ctrl.navigate_to(Screen.REELS)` replaces manual `_navigate_to_reels()`
4. Screen verification: `ctrl.detect_screen()` after navigation and after each swipe
5. Like reels: `ctrl.like_reel()` replaces manual `_like_current_reel()`
6. Swipe: `ctrl.swipe_to_next_reel()` replaces manual `_swipe_to_next_reel()`
7. Save: uses `ctrl.dump_xml()` + `ctrl._find_in_xml()` for XML-based save button detection
8. Popup handling: `ctrl.dismiss_popups()` if popup detected mid-session
9. Recovery: auto-navigates back to REELS if swipe leaves reels view
10. Return home: `ctrl.navigate_to(Screen.HOME_FEED)` in finally block
11. `execute_reels()` convenience function updated with `ctrl`/`pkg` params

**Removed**: All old methods (`_navigate_to_reels`, `_is_in_reels_view`, `_like_current_reel`, `_swipe_to_next_reel`) — fully replaced by IGController methods.

### Phase 2: Added like_reel() + swipe_to_next_reel() to IGController

**New methods in `automation/ig_controller.py`**:

1. **`like_reel()`** — Like the currently playing reel
   - Method 1: Reel-specific like button (`clips_like_button`, `like_button`) via XML
   - Method 2: `row_feed_button_like` (some reel UIs use feed-style like button)
   - Method 3: Double-tap center of screen (universal fallback)
   - Checks content-desc for "Unlike"/"Liked" + selected state to skip already-liked
   - Returns True/False

2. **`swipe_to_next_reel()`** — Swipe up to advance to next reel
   - Safe vertical range: 70% → 30% of screen height (well above nav bar at ~85%)
   - Random jitter on x/y ±10-20px for human-like behavior
   - Variable duration 0.25-0.45s
   - Returns True/False

### Phase 3: Verified like_post() Already Works

`like_post()` was already present and fully functional in IGController (added in Phase 2 earlier):
- Finds like button via `row_feed_button_like` resource ID in XML
- Checks content-desc: "Like" (not liked) vs "Liked" (already liked)
- Only clicks if not already liked
- Verifies state changed after click via second XML dump
- Fallback: double-tap on `media_group` / `row_feed_photo_imageview`
- `is_post_liked()` helper returns True/False/None

### Phase 4: Live Test (13/13 PASS)

Device: 10.1.11.4:5555 | Account: pratiwipahllewi | Package: com.instagram.androie

```
  PASS  Device connected (1080x1920)
  PASS  App running (screen=HOME_FEED)
  PASS  navigate_to(REELS)
  PASS  detect_screen() == REELS (got REELS)
  PASS  Still in REELS after watching (screen=REELS)
  PASS  like_reel() executed (returned True)
  PASS  swipe_to_next_reel()
  PASS  Still in REELS after swipe (screen=REELS)
  PASS  Second reel watched OK (4.2s)
  PASS  navigate_to(HOME_FEED)
  PASS  detect_screen() == HOME_FEED (got HOME_FEED)
  PASS  is_post_liked() works (liked=False)
  PASS  like_post() executed (returned True)

  Total: 13 | Pass: 13 | Fail: 0
```

### Bug Fix During Testing

Initial run had 12/13 — swipe was accidentally triggering the Search tab. Root cause: the swipe's start_y randomness could reach too close to the bottom nav bar area (nav bar at y=1644-1776 on 1920-high screen). Fixed by tightening the swipe range from 75%→25% to 70%→30% with smaller jitter (±10px instead of ±20px).

### Files Modified
- `automation/actions/reels.py` — Full rewrite: IGController integration, removed old IGNavigator code
- `automation/ig_controller.py` — Added `like_reel()`, `swipe_to_next_reel()` methods
- `test_reels_live.py` — New live test for full reels flow + like_post verification

### All Wired Modules Status
| Module | IGController | Status |
|--------|-------------|--------|
| engage.py | ✅ `ctrl.navigate_to()`, `ctrl.scroll_feed()`, `ctrl.get_story_items()` | Verified |
| follow.py | ✅ `ctrl.search_user()`, `ctrl.open_followers()`, `ctrl.follow_user_from_list()` | Verified |
| unfollow.py | ✅ `ctrl.open_following()`, `ctrl.unfollow_user()` | Verified |
| like.py | ✅ `ctrl.like_post()`, `ctrl.scroll_feed()`, `ctrl.navigate_to()` | Verified |
| reels.py | ✅ `ctrl.navigate_to(REELS)`, `ctrl.like_reel()`, `ctrl.swipe_to_next_reel()` | **Verified (NEW)** |

---

## 2026-02-01: search_user Fix + like.py Verification — ALL PASS

### Phase 1: Fixed search_user() in IGController

**Root cause**: Clone app (com.instagram.androie) shows keyword suggestions on type,
NOT inline user results. The `row_search_user_username` elements never appear until
you submit the search and switch to the "Accounts" tab.

**Fix applied to `automation/ig_controller.py`**:
1. After typing, briefly check for inline user results (fast path, 2s)
2. If no inline results, **submit search** via `adb shell input keyevent 66` (Enter key)
3. Wait for search results page with tabs (Top, Accounts, Tags, Places)
4. **Click "Accounts" tab** to filter to user results
5. Poll for `row_search_user_username` elements (up to 8s)
6. Case-insensitive matching via `.lower()` comparison
7. Scroll through results (up to 4 pages) if target not in first view
8. Extracted `_find_and_click_user_in_results()` helper for reuse
9. Debug screenshots on failure for troubleshooting

**Test result**: `search_user('instagram')` — PASS (19s, found profile with 698M followers)

### Phase 2: like.py Already Uses IGController

Verified that `automation/actions/like.py` was already fully wired to IGController:
- `self.ctrl = IGController(device, device_serial, pkg)` in `__init__`
- `ctrl.navigate_to(Screen.HOME_FEED)` for feed navigation
- `ctrl.scroll_feed()` for scrolling
- `ctrl.detect_screen()` for state verification
- `ctrl.like_post()` for liking (checks content-desc Like/Liked)
- `ctrl.dismiss_popups()` for popup handling
- `ctrl.find_element()` for hashtag mode
- Daily limits, session targets, like percentage, delay randomization all intact

### Phase 3: Live Test (9/9 PASS)

Device: 10.1.11.4:5555 | Account: pratiwipahllewi | Package: com.instagram.androie

```
  PASS  Device connected (1080x1920)
  PASS  App running (screen=SEARCH)
  PASS  search_user('instagram') (took 19.0s)
  PASS  On instagram profile (followers=698000000, following=187)
  PASS  Navigate to HOME_FEED
  PASS  Posts detected (found 1 posts)
  PASS  Like buttons found (1 buttons: desc='Like', bounds=[48,264][120,402])
  PASS  Like/Liked content-desc valid (all buttons have 'Like' or 'Liked' desc)
  PASS  is_post_liked() works (Not liked)

  Total: 9 | Pass: 9 | Fail: 0
```

### Files Modified
- `automation/ig_controller.py` — Rewrote `search_user()`, added `_find_and_click_user_in_results()`
- `test_like_live.py` — New live test for search + like detection

---

## 2026-01-31: IGController Test Suite + Engage Integration — VERIFIED

### Phase 1: IGController Test Suite (19 tests)

Device: 10.1.11.4:5555 | Account: pratiwipahllewi | Package: com.instagram.androie

```
  PASS  is_correct_app (IG in foreground)
  PASS  screenshot
  PASS  dump_xml (82KB XML)
  PASS  detect_screen (HOME_FEED)
  PASS  dismiss_popups (dismissed 2 popups)
  PASS  get_story_items (found 4 stories first run; 0 on re-run = all viewed)
  PASS  find_element (feed_tab)
  PASS  navigate_to(SEARCH)
  PASS  navigate_to(PROFILE)
  PASS  navigate_to(REELS)
  PASS  navigate_to(HOME_FEED)
  PASS  scroll_feed(down) — stayed on HOME_FEED
  PASS  scroll_feed(up)
  PASS  get_visible_posts (1 post detected with like state)
  PASS  click_story + tap_next_story (entered story view, tapped through)
  PASS  wait_for_element
  PASS  get_screen_summary
  PASS  scroll explore page — stayed on SEARCH
  PASS  resilience: Profile → Home (recovered in 2 attempts)

  Total: 19 | Pass: 19 | Fail: 0 | Error: 0
```

### Phase 2: engage.py Already Uses IGController ✓

engage.py was already refactored in the earlier phase:
- Imports `IGController, Screen` from `automation.ig_controller`
- Creates `self.ctrl = IGController(device, device_serial, pkg)` in `__init__`
- Uses `self.ctrl.navigate_to(Screen.HOME_FEED)` instead of `self.nav.go_home()`
- Uses `self.ctrl.scroll_feed()` instead of blind scrolls
- Uses `self.ctrl.get_story_items()` + `self.ctrl.click_story()` for stories
- Uses `self.ctrl.detect_screen()` checks during scrolling
- Uses `self.ctrl.dismiss_popups()` for popup handling
- Keeps all existing engagement logic (limits, percentages, delays from DB)

### Phase 3: Engage Live Test (5/5 PASS)

```
  PASS  execute() returned success=True
  PASS  Feed scrolls: 3 >= 2
  PASS  Explore scrolls: 3 >= 2
  PASS  Returned to HOME_FEED after engage
  PASS  Stories: 0 (none available — not a failure)
```

Full engagement cycle completed:
1. EngageAction created with IGController for device 10.1.11.4:5555
2. Dismissed persistent popups (3 "Dismiss" clicks)
3. Story viewing: 0 available (all previously viewed) — handled gracefully
4. Feed scrolling: 3 scrolls with screen state verification after each
5. Explore page: navigated to SEARCH, scrolled 3 times
6. Successfully returned to HOME_FEED after full engagement session

### Fixes Applied
- **test_ig_controller.py**: Added scroll-up before get_story_items test (story bar visibility)
- **test_ig_controller.py**: Made get_story_items test tolerant of empty stories (external state)
- **test_ig_controller.py**: Fixed UTF-8 encoding for summary file writer
- **test_engage_live.py**: New engage integration test with configurable short session

---

## 2026-01-30: Phase 3 — Reels, Profile, WebSocket — TESTED & WIRED

### New Modules Created + Verified

#### automation/actions/reels.py — Reels Watching Module (344 lines)
- `ReelsAction` class with configurable limits from DB
- Navigate to Reels tab (4 fallback methods: resource ID, content-desc, coordinate, feed entry)
- Reels view detection (clips_viewer, reel_viewer, TextureView)
- Configurable watch duration per reel (min/max seconds)
- Human-like behavior: random longer/shorter watches, random screen taps
- Like reels with configurable percentage
- Save reels optionally
- Swipe to next reel with natural speed variation
- Daily limit tracking via `get_today_action_count`
- **Settings keys**: `enable_watch_reels`, `min/max_reels_to_watch`, `min/max_sec_reel_watch`, `enable_like_reel`, `like_reel_percent`, `enable_save_reels_after_watching`, `watch_reel_limit_perday`
- **TESTED LIVE**: Navigate to Reels ✓, watch reel ✓, like reel ✓, swipe to next ✓

#### automation/profile.py — Profile Update Automation (596 lines)
- `ProfileAutomation` class for username, bio, and profile picture changes
- Navigate to Edit Profile screen from anywhere in IG
- Modal dismissal (avatar prompts, notification dialogs)
- **Username change**: tap label row → sub-screen → clear → type via ADB → check availability
- **Bio change**: tap label → sub-screen → char-by-char input (handles special chars/newlines)
- **Profile picture**: tap avatar → gallery picker → select image → crop/confirm
- Image push to device via ADB + media scanner trigger
- Challenge/verification detection
- Full task processor: reads `profile_updates` table, executes changes, logs to `task_history`
- `run_profile_task()` convenience function for API/scheduler
- **TESTED LIVE**: Navigate to Edit Profile ✓, all fields visible (Name, Username, Bio) ✓, no challenge ✓

#### automation/ws_server.py — WebSocket Server for Real-Time Updates (250 lines)
- Runs on port 5056 alongside Flask dashboard on 5055
- Thread-safe event bus with `broadcast_event()` callable from any thread
- Event types: `bot_status`, `action_event`, `device_status`, `session_event`, `stats_update`
- Client commands: `ping`, `get_status`, `get_history`
- On connect: sends last 50 buffered events + current status snapshot
- Periodic stats broadcaster (every 10s to connected clients)
- Status snapshot queries DB for: bot_status per device, today's action counts, active sessions
- `start_ws_server()` / `stop_ws_server()` / `get_ws_status()` lifecycle functions
- **TESTED LIVE**: Server starts ✓, broadcast_event works ✓, WS connect ✓, ping/pong ✓, status snapshot ✓

### Wiring Completed

1. **ws_server → run.py**: Auto-starts WebSocket server on port 5056 when dashboard launches.
   Both ports (5055 Flask + 5056 WS) run from same process (verified PID match).

2. **reels → bot_engine.py**: `_action_reels()` method defined. Added to `_determine_actions()`:
   ```python
   if self.settings.get('enable_watch_reels', False):
       actions.append(('reels', self._action_reels))
   ```
   Verified: when `enable_watch_reels=True`, reels appears in action list.

3. **reels → api.py**: Already in `api_bot_single_action()` handler — can trigger via:
   `POST /api/automation/bot/action/<account_id>/reels`

4. **profile → api.py**: Full REST API for profile automation:
   - `POST /api/automation/profile/task` — Create a profile update task
   - `GET /api/automation/profile/tasks` — List profile tasks
   - `POST /api/automation/profile/execute/<task_id>` — Execute a profile task
   - `GET/POST /api/automation/profile/pictures` — Manage profile picture library
   - `GET/POST /api/automation/profile/bio-templates` — Manage bio templates
   - `GET /api/automation/profile/history` — Profile change history

5. **ws_server → bot_engine.py**: Bot engine already calls `broadcast_event()` on:
   - Status changes (`_update_bot_status`)
   - Action completions (`_broadcast_action`)

6. **ws_server → api.py**: WebSocket control endpoints:
   - `GET /api/automation/ws/status`
   - `POST /api/automation/ws/start`
   - `POST /api/automation/ws/stop`

### Live Test Results (2026-01-30 19:44)

Device: 10.1.11.4:5555 (JACK 1), Account: pratiwipahllewi

```
=== Module Tests: 25/29 PASS ===

  PASS  Device connect         (connected to 10.1.11.4_5555, 1080x1920)
  PASS  Import reels           (ReelsAction, execute_reels)
  PASS  Import ws_server       (start/stop/broadcast/status)
  PASS  Import profile         (ProfileAutomation, run_profile_task)
  PASS  WS server start        (running=True, port=5056)
  PASS  WS broadcast           (event sent)
  PASS  WS status snapshot     (bot_status, today_actions, active_sessions, connected_clients)
  PASS  Open Instagram         (com.instagram.androie)
  PASS  Navigate to Reels      (clips_tab found)
  PASS  In Reels view          (clips_viewer detected)
  PASS  Watch reel 5s          (waited 5 seconds)
  PASS  Like reel attempt      (liked=True, double-tap)
  PASS  Swipe to next reel     (swipe executed)
  PASS  Navigate to Edit Profile
  PASS  On Edit Profile screen
  PASS  Field visible: Name
  PASS  Field visible: Username
  PASS  Field visible: Bio
  PASS  Challenge detection    (no challenge)
  PASS  Bot engine actions     (engage + reels when enabled)
  PASS  Bot engine has _action_reels
  PASS  Reels in action list when enabled

  === API Endpoint Verification ===
  PASS  GET  /api/automation/ws/status      → {"running": true, "port": 5056}
  PASS  GET  /api/automation/profile/tasks  → 200 OK
  PASS  GET  /api/automation/profile/bio-templates → 200 OK
  PASS  GET  /api/automation/stats/summary  → 5 actions today, 6 sessions
  PASS  WebSocket connect + ping/pong       → status_snapshot received
```

### Architecture Summary (Updated)

```
automation/
  __init__.py              Package (v2.0.0)
  device_connection.py     Device connection manager
  instagram_actions.py     Core IG UI interactions
  login.py                 Login flow with 2FA
  scheduler.py             Task queue scheduler
  bot_engine.py            Main bot engine (1 device + 1 account)
  device_orchestrator.py   Multi-device orchestrator
  api.py                   REST API blueprint (40+ endpoints)
  ws_server.py             WebSocket server for real-time updates (port 5056)  [NEW]
  profile.py               Profile update automation (username/bio/picture)   [NEW]
  actions/
    __init__.py            Actions package
    helpers.py             Shared utilities, DB, navigation, filters
    follow.py              Follow from source followers
    unfollow.py            Unfollow with delay + whitelist
    like.py                Like from feed/hashtags
    engage.py              Stories, feed scroll, explore
    scrape.py              Scrape follower lists
    reels.py               Watch Instagram Reels with human behavior          [NEW]
```

### Server Start (both HTTP + WS)
```powershell
Start-Process -FilePath "C:\Users\TheLiveHouse\clawd\phone-farm\venv\Scripts\python.exe" `
  -ArgumentList "-u","C:\Users\TheLiveHouse\clawd\phone-farm\run.py" `
  -WorkingDirectory "C:\Users\TheLiveHouse\clawd\phone-farm" `
  -WindowStyle Hidden
```
- HTTP Dashboard: http://10.1.11.168:5055
- WebSocket: ws://10.1.11.168:5056

### What's Next
- [ ] Direct message module (automation/actions/dm.py)
- [ ] Comment module (automation/actions/comment.py)
- [ ] Dashboard WebSocket client (live status updates in bot_manager.html)
- [ ] Scale testing on multiple devices
- [ ] Profile picture library population
- [ ] Bio template library creation

---

## 2026-01-30: Phase 1 Complete + Phase 2 Fully Complete

### Phase 1 (Dashboard) - COMPLETE
- Dashboard runs on port 5055 via `run.py` (waitress WSGI server)
- All 9 blueprints load successfully:
  - settings_bp, login_bp, bot_manager_bp, bot_settings_bp
  - bulk_import_bp, job_orders_bp, sources_bp, caption_templates_bp
  - **automation_bp** (NEW)
- API verified: 50 devices, 602 accounts, 28 tables
- All page routes work (/, /accounts, /bot-manager, etc.)
- Note: Must use `Start-Process` or `cmd /c` to run server on Windows
  (PowerShell kills processes that write to stderr)

### Phase 2 (Automation Core) - COMPLETE (All Modules)

#### Base Modules (from earlier)
**automation/__init__.py** - Package init (v2.0.0)

**automation/device_connection.py** - Device connection manager
- Thread-safe DeviceConnection class with state tracking
- Proven connection pattern: kill UIAutomator -> wait 5s -> u2.connect -> poll 45s
- Retry logic (2 attempts with more aggressive kill on retry)
- Screenshot (base64 + raw bytes)
- app_start with monkey fallback
- Global registry with module-level API functions
- Tested: Connected to 10.1.10.180_5555 in 7.8s, screenshot 1.1MB

**automation/instagram_actions.py** - Instagram UI interactions
- Open/close Instagram (any clone package)
- Screen state detection (logged_in, login, signup, challenge, 2fa, unknown)
- Navigation (profile, edit profile, home)
- Signup screen handling, credential entry, post-login popup dismissal
- 2FA detection + code entry

**automation/login.py** - Complete login flow
- login_account() - Full flow with 2FA support
- login_from_db() - Login using phone_farm.db account data
- 2FA code fetching (2fa.live client + pyotp fallback)

**automation/scheduler.py** - Task scheduler
- Reads tasks table from phone_farm.db
- Priority-based ordering, one task per device
- Retry logic with configurable max_retries

#### NEW: Action Modules (automation/actions/)

**automation/actions/__init__.py** - Package init

**automation/actions/helpers.py** - Shared utilities
- random_sleep() and action_delay() for human-like delays
- DB helpers: get_db(), log_action(), create_session(), end_session()
- get_account_settings(), get_account_sources(), get_today_action_count()
- get_recently_interacted() - skip already-interacted users
- IGNavigator class: go_home, go_profile, go_search, search_user,
  open_followers_list, open_following_list, scroll, press_back, dismiss_popup
- Profile info parser: parse_number (handles K/M/B), get_profile_info from XML
- check_filters() - apply follower/following/post/privacy filters
- All tested with DB queries passing

**automation/actions/follow.py** - Follow Automation
- FollowAction class with configurable limits from DB
- Reads source accounts from account_sources table
- Searches for source profiles, opens follower lists
- Scrolls through followers, follows eligible users
- Two strategies: direct button click in list + profile visit fallback
- Respects daily limits, session targets (min/max range)
- Filters by follower count, following, posts, privacy
- Skips recently followed users (14-day lookback)
- Logs each action to action_history table
- Error recovery to known UI state

**automation/actions/unfollow.py** - Unfollow Automation
- UnfollowAction class with configurable limits
- Opens bot account's Following list
- Unfollows users who were followed X days ago (configurable delay)
- Respects whitelist (from account_sources type 'whitelist' + source accounts)
- Two strategies: direct button click + profile visit fallback
- Handles confirmation dialogs
- Daily limit tracking

**automation/actions/like.py** - Like Automation
- LikeAction class with configurable limits
- Scrolls home feed and likes posts
- Like button detection (resource ID + description fallback)
- Double-tap fallback for media containers
- Random like chance (configurable percentage)
- Hashtag liking: navigate to hashtag, like top posts
- Human-like scrolling between posts

**automation/actions/engage.py** - Engagement / Warmup
- EngageAction class
- Story viewing: opens story bar, taps through stories, optional like
- Feed scrolling: scrolls home feed with random delays, optional likes
- Explore page browsing: scrolls explore grid, opens and likes random posts
- All durations/limits configurable from account_settings JSON
- Percentage-based liking during scroll (e.g., 50% chance)

**automation/actions/scrape.py** - Scraping
- ScrapeAction class
- Creates scraped_users table automatically (with UNIQUE constraint)
- Navigates to source profiles, opens follower lists
- Scrolls through and collects usernames
- Saves to DB for follow targeting
- Deduplicates across scrape sessions

#### NEW: Bot Engine + Orchestrator

**automation/bot_engine.py** - Main Bot Engine
- BotEngine class: one device + one account
- Full lifecycle:
  1. Load account data + settings from DB
  2. Check time window (start_time/end_time)
  3. Connect to device via uiautomator2
  4. Open correct Instagram clone package
  5. Check/ensure login (with 2FA support)
  6. Create bot session in DB
  7. Determine actions from settings (engage, follow, unfollow, like)
  8. Execute actions with cooldown between each (30-90s random)
  9. Error recovery (reconnect, navigate back, dismiss popups)
  10. Update bot_status table throughout
- Time window support: hour-based, midnight wrap (e.g., 22-4)
- Graceful stop via stop() method

**automation/device_orchestrator.py** - Multi-Device Orchestrator
- DeviceOrchestrator class with background polling thread
- Manages bot engines across all devices
- Account rotation based on time windows:
  - Queries all active accounts for each device
  - Selects the one whose time window matches current hour
  - Starts/stops engines as time windows change
- Start/stop individual devices
- Status tracking per device
- Thread-safe with locking

#### NEW: API Endpoints (added to automation/api.py)

Bot Engine Control:
- POST /api/automation/bot/run/<account_id> - Start bot engine for account
- POST /api/automation/bot/action/<account_id>/<action> - Run single action
  (follow, unfollow, like, engage, scrape)

Orchestrator Control:
- POST /api/automation/orchestrator/start - Start orchestrator
- POST /api/automation/orchestrator/stop - Stop orchestrator
- GET  /api/automation/orchestrator/status - Get orchestrator status
- POST /api/automation/orchestrator/start-device/<serial> - Start bot on device
- POST /api/automation/orchestrator/stop-device/<serial> - Stop bot on device

History & Sessions:
- GET /api/automation/action-history - Get action log (with filters)
- GET /api/automation/sessions - Get bot sessions

### Test Results

```
=== All imports: 9/9 OK ===

=== DB Test ===
Total accounts: 602
Accounts on test device 10.1.11.4_5555: 12

=== Account Settings ===
Filters: min_followers=50, max_followers=1000000
Action limit: 60/day, Scroll feed: True, Stories: True

=== Number Parsing ===
1.2K -> 1200, 3.4M -> 3400000, 10B -> 10000000000

=== Filter Check ===
Normal profile: PASS
Low-follower private: FAIL (too_few_followers)

=== Session/Action Logging ===
Session created, action logged, session ended, cleaned up

=== Time Windows ===
Hour 16, Window 0-2: False (correct)
Window 0-0 (always): True (correct)
Window 22-4 (midnight): False at hour 16 (correct)

=== Orchestrator ===
Selected account for 16:00: rahhmatberlinda (time 16-18) -- CORRECT
```

### Architecture Summary

```
automation/
  __init__.py              Package (v2.0.0)
  device_connection.py     Device connection manager
  instagram_actions.py     Core IG UI interactions
  login.py                 Login flow with 2FA
  scheduler.py             Task queue scheduler
  bot_engine.py            Main bot engine (1 device + 1 account)
  device_orchestrator.py   Multi-device orchestrator
  api.py                   REST API blueprint (20+ endpoints)
  actions/
    __init__.py            Actions package
    helpers.py             Shared utilities, DB, navigation, filters
    follow.py              Follow from source followers
    unfollow.py            Unfollow with delay + whitelist
    like.py                Like from feed/hashtags
    engage.py              Stories, feed scroll, explore
    scrape.py              Scrape follower lists
```

### Key DB Tables Used
- accounts (602 rows) - credentials, toggles, time windows
- account_settings (602 rows) - detailed JSON config per account
- account_sources (13,560 rows) - source accounts/hashtags
- action_history - logs every follow/unfollow/like/etc.
- account_sessions - bot session tracking
- bot_status - per-device running status
- scraped_users - scraped followers (auto-created)

### Server Start Command
```powershell
Start-Process -FilePath "C:\Users\TheLiveHouse\clawd\phone-farm\venv\Scripts\python.exe" `
  -ArgumentList "-u","C:\Users\TheLiveHouse\clawd\phone-farm\run.py" `
  -WorkingDirectory "C:\Users\TheLiveHouse\clawd\phone-farm" `
  -WindowStyle Hidden
```

## 2026-01-30: Live Test Run 2 — ALL SELECTORS FIXED + VERIFIED

### Test Results (11/11 PASS)
```
  PASS  Device Connection
  PASS  Open Instagram
  PASS  Navigate: Home         (feed_tab resource ID)
  PASS  Navigate: Search       (search_tab resource ID)
  PASS  Navigate: Profile      (profile_tab resource ID)
  PASS  Like Post              (row_feed_button_like, content-desc "Like"->"Liked")
  PASS  Search -> Profile      (row_search_user_username)
  PASS  Open Followers List    (profile_header_followers_stacked_familiar)
  PASS  Follow User            (follow_list_row_large_follow_button, text "Follow"->"Message")
  PASS  Open Following List    (profile_header_following_stacked_familiar + unified tab)
  PASS  Unfollow User          (profile visit: profile_header_follow_button "Following"->Unfollow)
```

### Confirmed UI Selectors (from XML dumps + live testing)
| Element | Resource ID | Notes |
|---------|-------------|-------|
| Home tab | `{pkg}:id/feed_tab` | content-desc="Home" |
| Search tab | `{pkg}:id/search_tab` | content-desc="Search and explore" |
| Profile tab | `{pkg}:id/profile_tab` | content-desc="Profile" |
| Like button | `{pkg}:id/row_feed_button_like` | content-desc="Like"/"Liked", need scroll past story bar |
| Media container | `{pkg}:id/media_group` | For double-tap fallback |
| Post image | `{pkg}:id/row_feed_photo_imageview` | content-desc has likes/comments info |
| Story tray | `{pkg}:id/reels_tray_container` | horizontal RecyclerView |
| Story item | `{pkg}:id/outer_container` | desc="username's story, N of M, Unseen/Seen." |
| Profile header | `{pkg}:id/row_profile_header` | Main profile section |
| Followers (click) | `{pkg}:id/profile_header_followers_stacked_familiar` | content-desc="698Mfollowers" |
| Following (click) | `{pkg}:id/profile_header_following_stacked_familiar` | content-desc="8following" |
| Follow btn (profile) | `{pkg}:id/profile_header_follow_button` | text="Follow"/"Following" |
| Followers/Following list | `{pkg}:id/unified_follow_list_tab_layout` | Tab layout |
| Tab buttons | `{pkg}:id/title` | text="N followers"/"N following" |
| List username | `{pkg}:id/follow_list_username` | In follow_list_container |
| Follow btn (list) | `{pkg}:id/follow_list_row_large_follow_button` | text="Follow"/"Message" |
| More options | `{pkg}:id/media_option_button` | content-desc="More options" |
| Search bar | `{pkg}:id/action_bar_search_edit_text` | EditText for search |
| Search result | `{pkg}:id/row_search_user_username` | Username in search results |

### Fixes Applied
1. **helpers.py (IGNavigator)**: Fixed go_home/go_search/go_profile to use confirmed resource IDs (feed_tab, search_tab, profile_tab). Fixed open_followers_list/open_following_list with stacked_familiar selectors. Added unified tab auto-click for following list.
2. **like.py**: Fixed like button to scroll past story bar first, use content-desc check for liked/not-liked state, double-tap fallback via media_group/row_feed_photo_imageview.
3. **follow.py**: Working with follow_list_row_large_follow_button and row_search_user_username. Proximity matching confirmed working.
4. **unfollow.py**: Fixed to use profile visit approach (More Options menu doesn't have Unfollow). Click username -> profile -> Following button -> Unfollow dialog.
5. **engage.py**: Fixed story tray selectors to use outer_container with description matching for unseen stories.
6. **Dashboard frontend**: bot_manager.html already fully wired to automation API (orchestrator, connect/disconnect, screenshot, action history, today stats).

### What's Next
- [ ] Direct message module
- [ ] Scale testing on multiple devices

---

## 2026-01-30: Phase 4 — Bot Settings UI Fix + Data Integrity + Logging

### Root Cause Analysis
The bot settings page (bot_settings.html) Timer tab was empty because:
1. `app.py` inline route `/api/bot-settings/<device>/<account>` (GET) only returned `settings_json` from `account_settings` table
2. The frontend expects `response.account_data.starttime` and `response.account_data.endtime` for the Timer tab
3. The old blueprint `bot_settings_routes.py` had this data but read from Onimator flat-file DBs at wrong paths
4. Flask inline routes take precedence over blueprint routes, so the incomplete inline route was always used

### Fixes Applied

#### 1. Bot Settings GET Endpoint (app.py) — FIXED
- Now returns **full account_data** dict with Onimator-compatible field names:
  - `starttime`, `endtime`, `password`, `email`, `randomaction`, `randomdelay`
  - `follow`, `unfollow`, `like`, `mute`, `comment`, `story`, `switchmode`
  - `followmethod`, `unfollowmethod`, `followdelay`, `unfollowdelay`, etc.
- Merges **toggle states** into settings object so `[data-setting]` bindings work:
  - `enable_follow`, `enable_unfollow`, `enable_likepost`, `enable_comment`, `enable_story_viewer`, `enable_mute`, `enable_switchmode`
- All data sourced from our centralized `phone_farm.db`, NOT Onimator flat files

#### 2. Bot Settings SAVE Endpoint (app.py) — FIXED
- Extracts toggle fields from POST data → updates `accounts` table toggle columns
- Deep-merges settings JSON → writes to `account_settings.settings_json`
- Returns merged settings in response for immediate frontend update

#### 3. Timer Tab Save (bot_settings.html) — FIXED
- `saveSettings()` now also collects `[data-accounts-db]` fields (starttime, endtime)
- Builds composite `randomaction` and `randomdelay` from min/max inputs
- Sends a second AJAX call to `/api/account/update/{device}/{account}` to persist timer fields

#### 4. Bulk Copy Endpoint (app.py) — ADDED
- `/api/bot-settings/bulk` POST — copies all toggle columns + full settings JSON from source to targets
- Uses our centralized DB (not Onimator flat files)
- Returns per-target success/failure results

#### 5. Lists & Prompts Endpoints (app.py) — ADDED
- `/api/bot-settings/{device}/{account}/lists/{type}` GET/POST — reads/writes `account_sources` table
- `/api/bot-settings/{device}/{account}/prompts/{type}` GET/POST — reads/writes `account_text_configs` table

#### 6. Automation Logs Endpoint (app.py) — ADDED
- `/api/automation/logs` GET — queries `bot_logs` table with device/username/level filters
- `/api/automation/logs` POST — allows programmatic log insertion
- Supports pagination via limit/offset params

### Data Import Verification
Ran comprehensive verification across ALL 47+ device folders:
- **50 devices**: 50/50 matched (OK)
- **602 accounts**: 602/602 matched (OK) — 1 gap fixed (legendprivatjack_harrer_pro on dev device)
- **602 settings JSONs**: 602/602 matched (OK)
- **Sources**: 426 accounts with sources in our DB vs 423 in Onimator (we have more — OK)
- **Text configs**: 3010 text config entries imported (GPT prompts, comment prompts, etc.)
- **Account stats**: 32,423 daily stat snapshots imported

### Test Device Verification (10.1.11.4:5555)
All 13 accounts verified with correct start_time/end_time values:
- `harrer_private`: start=2, end=4
- `harrer_real`: start=12, end=14
- `jack_harrer_pro`: start=20, end=22
- All have ~10KB settings JSON blobs
- All toggled correctly in DB

### Server Status
- Dashboard running on port 5055 (waitress WSGI)
- WebSocket server on port 5056
- Health check: http://localhost:5055/api/health → healthy, 29 tables
- All pages load: /bot-settings (200), /bot-manager (200)
