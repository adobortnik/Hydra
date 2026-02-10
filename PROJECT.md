# Phone Farm Automation Platform — Project Plan

## Overview

Build our own Instagram phone farm automation platform, replacing Onimator's scripts with our own automation layer. Uses uiautomator2 for direct phone control.

## Source: The Live House Dashboard

Forked from: `C:\Users\TheLiveHouse\Downloads\full_igbot_14.2.4\full_igbot_14.2.4\the-livehouse-dashboard`

**What it has (keeping):**
- Flask dashboard (Bootstrap 5, dark theme, Chart.js)
- Account management UI (view, filter, search, sort, bulk edit)
- Scheduled posts system
- Media library (upload, tag, anti-detection processing)
- Caption templates
- Bot manager UI
- Bot settings UI
- Profile automation UI
- Login automation UI
- Job orders system
- Manage sources UI
- Account inventory

**What it had (replacing/decoupling):**
- Onimator DB readers (`flask.databases_flask` imports in `app.py`)
- Direct reads of Onimator's `devices.db`, `{deviceid}/accounts.db`, `{deviceid}/account/stats.db`
- Onimator's scheduling/task system

## Architecture

```
phone-farm/
├── PROJECT.md              ← This file
├── dashboard/              ← Forked UI (Flask app)
│   ├── app.py              ← Main Flask app (decoupled from Onimator)
│   ├── simple_app.py       ← Self-contained app (our primary)
│   ├── templates/          ← Jinja2 HTML templates
│   ├── static/             ← CSS, JS, images
│   ├── data/               ← Local SQLite DBs, configs
│   └── routes/             ← Flask blueprints (reorganized)
├── automation/             ← Phone control layer (uiautomator2)
│   ├── core/               ← Base device connection, helpers
│   ├── instagram/          ← IG-specific automations
│   │   ├── login.py        ← Account login + 2FA
│   │   ├── profile.py      ← Username, bio, pfp changes
│   │   ├── follow.py       ← Follow/unfollow tasks
│   │   ├── post.py         ← Create posts/stories/reels
│   │   ├── engage.py       ← Like, comment, DM
│   │   └── scrape.py       ← Scrape followers, hashtags
│   ├── device_manager.py   ← Multi-device orchestrator
│   └── scheduler.py        ← Task scheduling engine
├── db/                     ← Our own database layer
│   ├── models.py           ← SQLAlchemy/SQLite models
│   ├── migrations/         ← Schema migrations
│   └── seed.py             ← Import existing data
├── api/                    ← REST API for dashboard↔automation
│   ├── routes.py           ← API endpoints
│   └── websocket.py        ← Real-time device status
└── config/                 ← Configuration
    ├── devices.json        ← Phone/device registry
    ├── accounts.json       ← Account configs
    └── proxies.json        ← Proxy assignments
```

## Existing uiAutomator Scripts (to refactor into automation/)

From the original `uiAutomator/` folder:
- `instagram_automation.py` — Core: connect device, open IG, navigate to profile/edit
- `login_automation.py` — Full login flow with 2FA, signup detection, credential entry
- `automated_profile_manager.py` — Batch profile updates (username, bio, pfp) with Onimator sync
- `onimator_reader.py` — Reads Onimator DBs (accounts, settings, sources)
- `parallel_login_processor.py` — Multi-device parallel login
- `parallel_profile_processor.py` — Multi-device parallel profile updates
- `smart_username_changer.py` — Smart username generation/changing
- `ai_profile_generator.py` — AI-generated profile content
- `tag_based_automation.py` — Tag/campaign-based task execution
- `two_fa_live_client.py` — 2FA code generation (TOTP)
- `bot_db.py` — Bot database operations
- `device_bot.py` — Per-device bot controller

## Key Technical Details

- **Phone connection:** ADB over network (IP:port, e.g., `10.1.10.183:5555`)
- **Device serial format:** `10.1.10.183_5555` (underscore in folders, colon for ADB)
- **Python library:** `uiautomator2` v3.4.2
- **UI selectors:** Multiple fallback strategy (resourceId → text → xpath → coordinates)
- **IG clones:** Multiple packages (`com.instagram.androie` through `...androip`)
- **Dashboard:** Flask on port 5050
- **DB:** SQLite (thread-safe)

## Phase 1: Foundation (COMPLETE)

1. ✅ Duplicate dashboard to `phone-farm/dashboard/`
2. ✅ Analyzed all Onimator dependencies (see ARCHITECTURE.md)
3. ✅ Created our own DB schema (`db/models.py`) — 28 tables in single `phone_farm.db`
4. ✅ Created import/seed script (`db/seed.py`) — imports from Onimator's scattered DBs
5. ✅ Created standalone entry point (`app.py`) — runs on port 5055 via run.py
6. ✅ Documented full architecture (`ARCHITECTURE.md`) — all routes, tables, dependencies
7. ✅ Dashboard loads: 50 devices, 602 accounts, all 9 blueprints, all page routes
8. ✅ Data imported: DB has 602 accounts across 50 devices with correct packages
9. ✅ Blueprint routes work with our DB layer (core API in app.py overrides Onimator paths)

## Phase 2: Automation Core (COMPLETE)

1. ✅ Refactored uiAutomator scripts into clean `automation/` module:
   - `device_connection.py` — Thread-safe connection manager with retry logic
   - `instagram_actions.py` — Full IG UI automation (open, detect, navigate, login helpers)
   - `login.py` — Complete login flow with 2FA support
   - `scheduler.py` — Priority-based task scheduler with retry logic
   - `api.py` — 20 REST endpoints registered as Flask blueprint
   - `profile.py` — Profile automation (username, bio, picture) with DB integration
2. ✅ Device connection manager — connects, screenshots, app_start, disconnect
3. ✅ Task scheduler — reads from tasks table, dispatches, retries, archives
4. ✅ Profile automation — change username/bio/picture via UI, task queue, 8 API endpoints
5. ☐ Wire dashboard UI → API → automation engine (frontend JS work remaining)

## Phase 3: Feature Parity with Onimator

1. ☐ Follow/unfollow automation
2. ☐ Post/story scheduling
3. ☐ Engagement automation (like, comment)
4. ☐ Source management (hashtags, users to scrape)
5. ☐ Account health monitoring

## Phase 4: Beyond Onimator

1. ☐ Real-time device status dashboard (WebSocket)
2. ☐ AI-powered caption generation
3. ☐ Smart scheduling (optimal times per account)
4. ☐ Proxy rotation and management
5. ☐ Analytics and reporting
