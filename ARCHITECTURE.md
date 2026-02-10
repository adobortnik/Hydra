# Phone Farm Automation Engine — Architecture

## Overview

The automation engine replaces Onimator (igbot.exe) with a Python-based system using `uiautomator2` for Instagram UI automation across a phone farm.

## Core Components

### 1. Database (`db/phone_farm.db`)
Single SQLite database with WAL mode. All state lives here.
- **devices** — device registry (50 devices)
- **accounts** — Instagram accounts with time windows and toggle flags
- **account_settings** — JSON blob per account (Onimator-compatible)
- **account_sources** — target accounts/hashtags for follow/like
- **account_stats** — daily snapshots
- **tasks** — automation task queue
- **bot_status** — per-device bot process state
- **account_sessions** — session tracking
- **action_history** — granular action log (every follow, unfollow, like, etc.)

### 2. Device Connection (`automation/device_connection.py`)
- Thread-safe connection pool (one u2 connection per device)
- Kill UIAutomator → wait → u2.connect() → poll until responsive (45s timeout)
- Auto-reconnect on UiAutomationNotConnectedError
- Screenshot capture (base64 and raw PNG)

### 3. Bot Engine (`automation/bot_engine.py`)
Core engine for one device + one account:
1. Load account data + settings from DB
2. Check time window (skip if outside hours)
3. Connect to device via u2
4. Open correct Instagram clone package
5. Verify login state (auto-login if needed)
6. Run enabled actions in sequence with cooldowns
7. Log everything to action_history
8. Handle errors with recovery (press back, dismiss popups, reconnect)

### 4. Action Modules (`automation/actions/`)

| Module | File | What it does |
|--------|------|-------------|
| **Follow** | `follow.py` | Follow users from source account follower lists |
| **Unfollow** | `unfollow.py` | Unfollow users after X days, respecting whitelist |
| **Like** | `like.py` | Like posts from feed, hashtags, or source followers |
| **Engage** | `engage.py` | Story viewing, feed scrolling, explore browsing (warmup) |
| **Comment** | `comment.py` | Post comments using templates or AI placeholders |
| **DM** | `dm.py` | Send direct messages to new followers or specific users |
| **Reels** | `reels.py` | Watch Instagram Reels with human-like behavior |
| **Helpers** | `helpers.py` | Random delays, DB logging, IGNavigator, profile parsing |

All actions:
- Respect daily limits (from DB)
- Track recently interacted users (avoid duplicates)
- Use human-like random delays
- Log every action to `action_history` table
- Use the `IGNavigator` class for UI navigation

### 5. Task Scheduler (`automation/scheduler.py`)
- Background thread polling `tasks` table every 10s
- Priority ordering, scheduled times, retry logic
- One task per device at a time (device-level locks)
- Dispatches: login, open_instagram, screenshot, bot_run, follow, unfollow, like, comment, dm

### 6. Device Orchestrator (`automation/device_orchestrator.py`)
- Manages bot engines across ALL devices
- Account rotation: picks the right account per device based on time windows
- Auto-starts/stops engines as time windows change
- One account active per device at any time
- Thread-per-device architecture

### 7. Profile Automation (`automation/profile.py`)
- Edit username, bio, and profile picture via uiautomator2
- Navigate to Edit Profile from anywhere in IG
- Challenge/verification detection
- Task-based: reads `profile_updates` table, executes, logs to `task_history`
- REST API for creating/executing tasks, managing pictures + bio templates

### 8. WebSocket Server (`automation/ws_server.py`)
- Real-time status updates for the dashboard (port 5056)
- Thread-safe event bus: `broadcast_event()` from any thread
- Events: `bot_status`, `action_event`, `device_status`, `stats_update`
- Client commands: `ping`, `get_status`, `get_history`
- Periodic stats broadcaster (every 10s)
- Auto-starts from `run.py` alongside Flask

### 9. REST API (`automation/api.py`)
Flask Blueprint with endpoints:

**Device Management:**
- `POST /api/automation/connect/<serial>` — Connect device
- `POST /api/automation/disconnect/<serial>` — Disconnect device
- `GET /api/automation/status` — All device statuses
- `GET /api/automation/screenshot/<serial>` — Device screenshot

**Bot Control:**
- `POST /api/automation/bot/start/<serial>` — Start bot on device
- `POST /api/automation/bot/stop/<serial>` — Stop bot on device
- `POST /api/automation/bot/start-all` — Start all devices
- `POST /api/automation/bot/stop-all` — Stop all devices
- `GET /api/automation/bot/status` — Bot status for all devices

**Orchestrator:**
- `POST /api/automation/orchestrator/start` — Start orchestrator
- `POST /api/automation/orchestrator/stop` — Stop orchestrator
- `GET /api/automation/orchestrator/status` — Orchestrator status

**Source Management:**
- `GET /api/automation/sources/<account_id>` — Get sources
- `POST /api/automation/sources/<account_id>` — Add sources
- `DELETE /api/automation/sources/<account_id>/<source_id>` — Delete source
- `POST /api/automation/sources/bulk` — Bulk set sources for multiple accounts

**Stats:**
- `GET /api/automation/stats/<account_id>` — Account stats + today's actions
- `GET /api/automation/stats/summary` — Farm-wide daily summary

**Scheduler:**
- `POST /api/automation/scheduler/start` — Start scheduler
- `POST /api/automation/scheduler/stop` — Stop scheduler
- `GET /api/automation/scheduler/status` — Scheduler status

**Profile Automation:**
- `POST /api/automation/profile/task` — Create profile update task
- `GET /api/automation/profile/tasks` — List profile tasks
- `POST /api/automation/profile/execute/<task_id>` — Execute a task
- `GET/POST /api/automation/profile/pictures` — Manage profile pictures
- `GET/POST /api/automation/profile/bio-templates` — Manage bio templates
- `GET /api/automation/profile/history` — Profile change history

**WebSocket:**
- `GET /api/automation/ws/status` — WS server status
- `POST /api/automation/ws/start` — Start WS server
- `POST /api/automation/ws/stop` — Stop WS server

## Running

```bash
cd phone-farm
.\venv\Scripts\python.exe run_server.py --port 5000
```

Options:
- `--auto-start-orchestrator` — Auto-start orchestrator on boot
- `--debug` — Flask debug mode
- `--port 5000` — Port number

## Instagram UI Selectors

The `IGNavigator` class uses content descriptions (`Home`, `Profile`, `Search and Explore`) and resource IDs from the GramAddict reference implementation. Key resource IDs are in `dashboard/uiAutomator/bot/GramAddict/core/resources.py`.

Instagram clone packages follow the pattern `com.instagram.androiX` where X = e, f, g, h, i, j, k, l (one per 2-hour time slot per device).

## Dev Device

Test device: `10.1.11.4:5555` (JACK 1, device_id=50)
