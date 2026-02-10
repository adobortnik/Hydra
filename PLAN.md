# Phone Farm Automation — Build Plan

## Current Status (2026-01-31)
- ✅ Dashboard (Flask on 5055, 29 tables, 603 accounts, 50 devices)
- ✅ IGController: XML-based screen detection, navigation, popup dismiss
- ✅ All action modules wired: engage, follow, unfollow, like, reels (13/13 tests pass)
- ✅ search_user(), follow_from_source(), like_post(), like_reel() all verified live
- ✅ Data imported from Onimator (accounts, settings, sources)
- ✅ WebSocket server (port 5056) for real-time status

## Architecture: XML Hierarchy-Driven (COMPLETED)
- `IGController` is the core — XML dumps for element detection, screen state machine
- All actions verify screen state before/after
- scrcpy for live viewing: `C:\Users\TheLiveHouse\Desktop\full_igbot_14.8.6\scrcpy\scrcpy.exe`
- DB at: `db/phone_farm.db` (SQLite, 29 tables)

## NOT IN SCOPE (per John)
- ❌ Proxy rotation — not needed
- ❌ Unfollow — not important right now

## Revised Build Priorities

### Phase 1: Tag System + Follow Dedup (NEXT)
Account tagging with cross-account duplicate follow prevention.

**DB Changes:**
- `account_tags` table: `account_id INT, tag_id INT` (many-to-many junction)
- Settings flag per account: `dont_follow_already_followed_by_tag` (boolean)

**Existing tables we use:**
- `tags` (id, name) — already exists, has "farmers"
- `action_history` — already tracks (device_serial, username, action_type='follow', target_username)

**Dedup Logic:**
Before following @target_user:
1. Get this account's tags → e.g., ["Spencer"]
2. Get ALL accounts with same tag(s) → 24 accounts
3. Check action_history: has ANY of those 24 accounts already followed @target_user?
4. If yes AND `dont_follow_already_followed_by_tag` is enabled → SKIP

**API Endpoints:**
- `GET/POST /api/tags` — CRUD for tags
- `POST /api/accounts/<id>/tags` — assign/remove tags from account
- `GET /api/accounts?tag=Spencer` — list accounts by tag
- Settings checkbox in account settings UI

### Phase 2: Follow from List
In addition to "follow from source's followers" (already built), add follow from explicit username list.

**DB Changes:**
- `follow_lists` table: `id, name, tag_id (nullable), created_at`
- `follow_list_items` table: `id, list_id, username, status (pending/followed/skipped), followed_by_account_id`

**Flow:**
1. Create/import a list of usernames (manual entry, CSV, or pasted)
2. Assign list to a tag group (optional)
3. Bot picks next un-followed username from list
4. Visits profile → follows
5. Tag dedup applies: if same-tag account already followed this user, skip
6. Marks item as followed + who followed them

**API Endpoints:**
- `GET/POST /api/follow-lists` — CRUD for lists
- `POST /api/follow-lists/<id>/import` — bulk import usernames
- `GET /api/follow-lists/<id>/items` — list items with status

### Phase 3: Share to Story
Go to specific user profile → open their content → share to our story.

**Flow:**
1. Navigate to target user profile (via search_user)
2. Open their latest reel/video/photo (click first grid item)
3. Tap share button (send_post or share button in post UI)
4. Select "Add to Your Story" option
5. Confirm/customize story post
6. Verify story was posted

**New IGController methods:**
- `open_user_grid_item(index)` — tap Nth post in profile grid
- `share_to_story()` — share current content to story
- `detect_story_editor()` — verify we're in story editor

### Phase 4: Multi-Window Launcher
Each device gets its own console window with live logs.

**How it works:**
- PowerShell launcher script: `launch_farm.ps1`
- For each device, opens a new `cmd.exe` / PowerShell window
- Window title = device name (e.g., "JACK 1 - 10.1.11.4:5555")
- Script runs the bot loop for that device in that window
- John sees 20 windows, each with scrolling logs
- Uses `Start-Process` to spawn separate windows

**Single device script:** `run_device.py <device_serial>`
- Connects to device, rotates through accounts, runs actions
- Colored console output (device name, account, action, results)
- Graceful shutdown on Ctrl+C

## Verified UI Selectors (from XML dumps + live testing)
| Element | Resource ID Pattern | Notes |
|---------|-------------------|-------|
| Home tab | `feed_tab` | content-desc="Home" |
| Search tab | `search_tab` | content-desc="Search and explore" |
| Profile tab | `profile_tab` | content-desc="Profile" |
| Reels tab | `clips_tab` | content-desc="Reels" |
| Like button | `row_feed_button_like` | content-desc="Like"/"Liked" |
| Media container | `media_group` | For double-tap fallback |
| Story tray | `reels_tray_container` | Horizontal RecyclerView |
| Story item | `outer_container` | desc matches "story.*Unseen" |
| Followers click | `profile_header_followers_stacked_familiar` | |
| Following click | `profile_header_following_stacked_familiar` | |
| Follow btn (profile) | `profile_header_follow_button` | text="Follow"/"Following" |
| Follow btn (list) | `follow_list_row_large_follow_button` | text="Follow"/"Message" |
| Search bar | `action_bar_search_edit_text` | EditText |
| Search result | `row_search_user_username` | Username text |

## Agent Instructions Template
Each agent must:
1. Read this PLAN.md first
2. Use ONLY device 10.1.11.4:5555
3. Take screenshots before/after each code change test
4. Save screenshots to test_results/ with descriptive names
5. Dump XML hierarchy when elements aren't found
6. Update PROGRESS.md with what was done
7. Test with real account: pratiwipahllewi (pkg: com.instagram.androie)

## Dev Device Info
- Serial: 10.1.11.4:5555 (DB format: 10.1.11.4_5555)
- Name: JACK 1
- 12 accounts assigned
- scrcpy: C:\Users\TheLiveHouse\Desktop\full_igbot_14.8.6\scrcpy\scrcpy.exe
- Dashboard: http://10.1.11.168:5055
