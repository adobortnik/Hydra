# Hydra Phone Farm — Comprehensive Audit

**Date:** 2026-02-27
**Auditor:** Jarvis (subagent)

---

## 1. Manual / Documentation Audit

### What Exists

| Document | Location | Purpose | Quality |
|----------|----------|---------|---------|
| `SETUP.md` (root) | `/SETUP.md` | Setup guide, prerequisites, quick start | ✅ Good — covers Python, ADB, scrcpy, quick start, troubleshooting |
| User Guide (EN) | `/docs/index.html` → `/docs` route | Full user manual — 1800+ lines HTML | ✅ Comprehensive — covers all major features |
| Dev Docs | `/docs/dev.html` → `/docs-dev` route | Developer-facing docs | ⚠️ Not audited in depth |
| Slovak Docs | `/docs/sk.html` → `/docs-sk` route | Slovak translation | ⚠️ Not audited in depth |
| Manual Page | `/docs/manual.html` → `/manual` route | Alternative manual format | ⚠️ Exists but possibly redundant |
| Manual ZIP | `/docs/hydra-manual.zip` | Downloadable manual | ✅ Exists |
| `ARCHITECTURE.md` | `/ARCHITECTURE.md` | System architecture overview | ✅ Good |
| `PROJECT.md` | `/PROJECT.md` | Project overview | ✅ Exists |
| `PLAN.md` | `/PLAN.md` | Development plan/roadmap | ✅ Exists |
| `PROGRESS.md` | `/PROGRESS.md` | Development progress tracking | ✅ Detailed (49KB) |
| Dashboard README | `/dashboard/README.md` | Dashboard overview | ⚠️ Outdated — references port 5050 (actual is 5055), missing many features |
| Research docs | `/docs/account-creation-research.md`, `ai-personas-research.md`, `reel_posting_research.md` | Internal research | ℹ️ Dev-only, not client-facing |

### What's Missing for a Client

| Gap | Severity | Details |
|-----|----------|---------|
| **No root README.md** | 🔴 HIGH | Client who clones the repo sees no intro. Need a README.md with: what is this, requirements, quickstart link |
| **No INSTALL.md / QUICKSTART.md** | 🟡 MEDIUM | `SETUP.md` exists but a separate "5-minute quickstart" would help new clients |
| **First-run walkthrough** | 🟡 MEDIUM | No guide for "I just installed, now what?" — step 1 through 10 hand-holding |
| **How to add devices (detailed)** | 🟡 MEDIUM | SETUP.md mentions "Device Manager" but doesn't walk through WiFi ADB setup on phones, developer options, etc. |
| **How to import accounts (CSV/text format)** | 🟡 MEDIUM | Docs mention deploy wizard but don't show exact format examples for bulk import |
| **Proxy setup guide** | 🔴 HIGH | Proxy Management page exists (`/proxy-management`) but NO documentation on how to configure proxies, what format, SOCKS5 vs HTTP, etc. |
| **Account Health monitoring guide** | 🟡 MEDIUM | Page exists but no docs explaining what the health metrics mean or how to respond to issues |
| **Sync feature docs** | 🟡 MEDIUM | `/sync` page exists with no user-facing documentation |
| **Content scheduling workflow** | 🟡 MEDIUM | Docs section exists but lacks step-by-step: upload media → create caption → schedule → verify |
| **DM campaign setup** | 🟡 MEDIUM | DM is mentioned as a feature but no guide on how to configure DM templates, target lists |
| **Report job setup** | 🟡 MEDIUM | Report action exists but no guide on how to create report campaigns |
| **Comment list management** | 🟡 MEDIUM | Comment lists referenced but no guide on AI vs manual comments, list creation |
| **API keys setup** | 🟡 MEDIUM | Settings page handles this but no written guide for clients unfamiliar with OpenAI/Anthropic |
| **Dashboard `README.md` is outdated** | 🟡 MEDIUM | Still says port 5050, references old DB paths, missing >50% of current features |
| **No changelog for clients** | 🟡 MEDIUM | PROGRESS.md is dev-focused. Clients need a user-friendly CHANGELOG |
| **No FAQ page in docs** | 🟢 LOW | FAQ section exists in index.html but could be expanded |

---

## 2. Production Readiness Audit

### ✅ What Works Well

| Area | Status | Details |
|------|--------|---------|
| Auth on all routes | ✅ | `before_request` hook in `simple_app.py` enforces Basic Auth globally. Only `/api/auth/change-password` bypassed (by design) |
| Auth config auto-creation | ✅ | `auth_config.json` created with defaults if missing |
| Error handling (global) | ✅ | `@app.errorhandler(Exception)` catches unhandled exceptions, logs to `flask_errors.log` |
| 5xx logging | ✅ | `after_request` hook logs 5xx responses |
| Unhandled exception hook | ✅ | `sys.excepthook` catches crashes globally |
| Crash recovery (watchdog) | ✅ | `run_dashboard.py` is an excellent watchdog — auto-restarts, rapid-crash detection, backoff |
| Launcher.py | ✅ | Clean first-run experience — checks Python, deps, port-in-use, auto-opens browser |
| Logging to file | ✅ | RotatingFileHandler, 5MB max, 3 backups |
| DB directory creation | ✅ | `os.makedirs(..., exist_ok=True)` used for data directories |

### 🔴 Critical Issues

| Issue | Severity | Details | Fix |
|-------|----------|---------|-----|
| **DB migrations NOT run at dashboard startup** | 🔴 CRITICAL | `ensure_schema()` from `db/migrations.py` is only called in `device_manager_routes.py` import — NOT guaranteed to run before other routes access the DB. On a fresh install with no DB, routes that query `phone_farm.db` will crash. | Call `ensure_schema()` at the top of `simple_app.py` after imports, before any routes |
| **`global_settings.json` NOT created if missing** | 🔴 CRITICAL | The `/api/settings/ai` GET route returns empty defaults, but the POST route loads existing file. If file doesn't exist on first startup, features that read it (AI captions) silently fail. No auto-creation on startup. | Create a default `global_settings.json` on startup if missing |
| **API key leaked in `global_settings.json`** | 🔴 CRITICAL | File currently contains a real OpenAI API key (`sk-proj-w9z...`). While gitignored, if someone copies the project folder it's exposed. | Ensure the file in git is a template with empty keys. Add `.gitignore` check |
| **`devices.db` is 0 bytes** | 🟡 HIGH | The root `devices.db` is empty (0 bytes). If dashboard tries to query it before init, it'll error. | Initialize on startup or remove if unused (phone_farm.db is the real DB) |
| **Scrcpy path hardcoded** | 🟡 HIGH | `device_manager_routes.py` line 396: `scrcpy_path = r'C:\tools\scrcpy\scrcpy-win64-v3.1\scrcpy.exe'` — won't work on client machines | Make configurable via `global_settings.json` or search PATH |
| **Default password is "changeme" / "hydra2026"** | 🟡 MEDIUM | `SETUP.md` says default is `hydra2026` but code creates default as `changeme` (or `HYDRA_ADMIN_PASSWORD` env var). Inconsistency. | Sync docs with code, force password change on first login |
| **`phone_farm.db` in dashboard/ is 0 bytes** | 🟡 MEDIUM | `dashboard/phone_farm.db` is 0 bytes, real DB is at `db/phone_farm.db`. The empty file could cause confusion. | Remove the empty file or add comment |
| **No HTTPS / security headers** | 🟡 MEDIUM | Dashboard runs on plain HTTP. No CSRF, no security headers. Acceptable for LAN but risky if exposed to internet | Document as LAN-only, or add basic security headers |
| **`THELIVEHOUSE_DIR` variable name** | 🟢 LOW | Variable named `THELIVEHOUSE_DIR` at line 92 is confusing for clients — it's just the dashboard directory. | Rename to `DASHBOARD_DIR` |

### 🟡 Edge Cases & Missing Error Handling

| Issue | Details |
|-------|---------|
| Media upload with no DB | `init_media_library_db()` creates tables, but if `media_library/` dir doesn't exist, uploads fail silently |
| Scheduled posts with missing media | If media file is deleted after scheduling, the bot will crash at post time |
| Device disconnection mid-operation | No graceful handling in dashboard for devices that go offline during bot operations |
| DB locking under concurrent access | SQLite used with multiple threads; some routes don't use proper connection management |
| Export with empty selection | Some export routes don't validate empty `account_ids` arrays |

---

## 3. Refactoring Needs

### 🔴 `simple_app.py` is 4516 lines — needs splitting

This monolith contains:
- Media library CRUD (~400 lines)
- Account inventory CRUD (~500 lines)
- Scheduled posts CRUD (~300 lines)
- Caption templates CRUD (~200 lines)
- JAP API integration (~200 lines)
- Folder management (~200 lines)
- Batch scheduling (~200 lines)
- Auth system (~100 lines)
- Bulk settings (~100 lines)
- Export functions (~200 lines)
- 92 route definitions

**Recommendation:** Extract into:
- `media_library_routes.py` (already partially exists as functions)
- `inventory_routes.py`
- `scheduled_posts_routes.py`
- `caption_routes.py` (merge with existing `caption_templates_routes.py`)
- `auth_routes.py`

### V1/V2 Duplicate Pages (6 pairs)

| V1 File | V2 File | V1 Routes | V2 Routes |
|---------|---------|-----------|-----------|
| `login_automation_routes.py` (34KB) | `login_automation_v2_routes.py` (35KB) | `/login-automation` | `/login-automation-v2` |
| `login_automation.html` (33KB) | `login_automation_v2.html` (39KB) | — | — |
| `job_orders_routes.py` (16KB) | `job_orders_v2_routes.py` (20KB) | `/job-orders` | `/job-orders-v2` |
| `job_orders.html` (26KB) | `job_orders_v2.html` (82KB) | — | — |
| `import_accounts.html` (19KB) | `import_accounts_v2.html` (18KB) | — | — |
| `profile_automation.html` (28KB) | `profile_automation_v2.html` (125KB) | — | — |
| `account_inventory.html` (65KB) | `account_inventory_v2.html` (18KB) | — | — |

**Recommendation:** If V2 replaces V1, remove V1 files. If both are needed, document why. Currently ~250KB of potentially dead HTML.

### Large Route Files (should consider splitting)

| File | Size | Routes | Recommendation |
|------|------|--------|----------------|
| `content_schedule_routes.py` | 76KB | 23 | Split: API routes vs page routes |
| `profile_automation_routes.py` | 76KB | 48 | Split: profile tasks, batch ops, API |
| `device_manager_routes.py` | 65KB | 29 | Split: device CRUD, mirroring, scanning |
| `account_health_routes.py` | 51KB | 23 | Could be trimmed |

### Large HTML Templates

| Template | Size | Issue |
|----------|------|-------|
| `device_manager_detail.html` | 178KB | Enormous — likely contains inline JS that should be extracted |
| `bot_settings.html` | 141KB | Same issue |
| `content_schedule.html` | 135KB | Same issue |
| `profile_automation_v2.html` | 122KB | Same issue |
| `job_orders_v2.html` | 82KB | Large |
| `media-library.js` | 78KB | Massive JS file |

### Automation Module — Large Files

| File | Size | Consideration |
|------|------|---------------|
| `ig_controller.py` | 94KB | Core UI controller — complex but cohesive. Could split screen detection from action execution |
| `post_content.py` | 62KB | Post/Reel/Story — already action-specific, acceptable |
| `bot_engine.py` | 61KB | Core engine — complex but cohesive |
| `api.py` | 55KB | API module — could split by endpoint group |
| `share_to_story.py` | 54KB | Story sharing — complex Instagram flow |

### TODO/FIXME/HACK Comments

Only **1 TODO** found in the entire codebase:
- `profile_automation_routes.py:840` — `'is_running': False  # TODO: Check if process is actually running`

This is surprisingly clean. However, the lack of TODOs may also indicate that tech debt isn't being tracked in code.

### Dead/Duplicate Code

| Pattern | Files | Issue |
|---------|-------|-------|
| Dashboard utility scripts | 22 files in `dashboard/` (check_*, examine_*, fix_*, inspect_*, test_*, update_*) | One-off debug scripts mixed with production code |
| `caption_templates_api.py` + `caption_templates_integration.py` + `caption_templates_routes.py` + functions in `simple_app.py` | 4 files | Caption template code is scattered across 4 locations |
| `app.py` + `app_integration.py` + `simple_app.py` | 3 files | Multiple app entry points — `app.py` (37KB) may be a deprecated version |
| `manage_sources.py` (15KB) | Blueprint file | Clean, but some overlap with source management in `simple_app.py` |
| Duplicate error handlers | Lines 2514-2520 AND lines 4503-4512 in `simple_app.py` | Two `@app.errorhandler(Exception)` — second one overrides first |

### Import Organization

The `simple_app.py` file imports 26 blueprint modules at the top. This is reasonable but the sheer number suggests the app has grown beyond what a single entry point should manage. Consider:
- A `create_app()` factory pattern
- Blueprint registration in a separate `routes/__init__.py`

---

## 4. Cleanup — Unused Test/Debug Scripts

### Root `_*.py` Files (89 files total, ~113KB)

These are one-off test/debug scripts that should ALL be deleted from the release branch.

#### `_check_*.py` files (22 files)

| File | Size | Purpose | Recommendation |
|------|------|---------|----------------|
| `_check_accounts_jack1.py` | 831B | Check specific device accounts | 🗑 DELETE |
| `_check_active.py` | 284B | Check active status | 🗑 DELETE |
| `_check_copy.py` | 596B | Check copy operation | 🗑 DELETE |
| `_check_data.py` | 1.1KB | Check data integrity | 🗑 DELETE |
| `_check_db2.py` | 504B | Check DB | 🗑 DELETE |
| `_check_devices.py` | 895B | Check devices | 🗑 DELETE |
| `_check_dm_data.py` | 1.3KB | Check DM data | 🗑 DELETE |
| `_check_dm_data2.py` | 1.5KB | Check DM data v2 | 🗑 DELETE |
| `_check_filter_keys.py` | 568B | Check filter keys | 🗑 DELETE |
| `_check_filters.py` | 808B | Check filters | 🗑 DELETE |
| `_check_heart.py` | 591B | Check heartbeat | 🗑 DELETE |
| `_check_heart2.py` | 700B | Check heartbeat v2 | 🗑 DELETE |
| `_check_job3.py` | 1.4KB | Check job | 🗑 DELETE |
| `_check_media_db.py` | 769B | Check media DB | 🗑 DELETE |
| `_check_posts.py` | 332B | Check posts | 🗑 DELETE |
| `_check_replaced.py` | 344B | Check replaced accounts | 🗑 DELETE |
| `_check_results.py` | 268B | Check results | 🗑 DELETE |
| `_check_schema.py` | 1.3KB | Check schema | 🗑 DELETE |
| `_check_screen.py` | 1.1KB | Check screen | 🗑 DELETE |
| `_check_settings.py` | 1.2KB | Check settings | 🗑 DELETE |
| `_check_settings2.py` | 762B | Check settings v2 | 🗑 DELETE |
| `_check_share_sources.py` | 1.7KB | Check share sources | 🗑 DELETE |
| `_check_stats.py` | 636B | Check stats | 🗑 DELETE |
| `_check_story_settings.py` | 823B | Check story settings | 🗑 DELETE |
| `_check_tag_dedup.py` | 1.8KB | Check tag dedup | 🗑 DELETE |
| `_check_tags.py` | 873B | Check tags | 🗑 DELETE |
| `_check_tags2.py` | 1.7KB | Check tags v2 | 🗑 DELETE |
| `_check_untagged.py` | 1.2KB | Check untagged | 🗑 DELETE |
| `_check_warmup.py` | 280B | Check warmup | 🗑 DELETE |

#### `_fix_*.py` files (12 files)

| File | Size | Purpose | Recommendation |
|------|------|---------|----------------|
| `_fix_and_restart.py` | 619B | Fix and restart device | 🗑 DELETE |
| `_fix_encoding.py` | 4.2KB | Fix encoding issues | 🗑 DELETE |
| `_fix_encoding2.py` | 4.6KB | Fix encoding v2 | 🗑 DELETE |
| `_fix_filters.py` | 970B | Fix filters | 🗑 DELETE |
| `_fix_harrer.py` | 388B | Fix specific account | 🗑 DELETE |
| `_fix_heart.py` | 2.8KB | Fix heartbeat | 🗑 DELETE |
| `_fix_jaggerprime.py` | 1.2KB | Fix specific account | 🗑 DELETE |
| `_fix_replaced.py` | 531B | Fix replaced accounts | 🗑 DELETE |
| `_fix_status.py` | 368B | Fix status | 🗑 DELETE |
| `_fix_stuck.py` | 1.1KB | Fix stuck accounts | 🗑 DELETE |
| `_fix_times.py` | 530B | Fix time windows | 🗑 DELETE |

#### `_test_*.py` files (10 files)

| File | Size | Purpose | Recommendation |
|------|------|---------|----------------|
| `_test_api.py` | 443B | Test API | 🗑 DELETE |
| `_test_bulk_copy.py` | 2.1KB | Test bulk copy | 🗑 DELETE |
| `_test_gallery_click.py` | 1.5KB | Test gallery | 🗑 DELETE |
| `_test_gallery_click2.py` | 1.3KB | Test gallery v2 | 🗑 DELETE |
| `_test_gallery_click3.py` | 1.4KB | Test gallery v3 | 🗑 DELETE |
| `_test_job.py` | 2.5KB | Test job | 🗑 DELETE |
| `_test_pexels.py` | 464B | Test Pexels API | 🗑 DELETE |
| `_test_reel.py` | 1.8KB | Test reel | 🗑 DELETE |
| `_test_schedule_query.py` | 928B | Test schedule query | 🗑 DELETE |
| `_test_share_story.py` | 1.0KB | Test share story | 🗑 DELETE |
| `_test_share_story2.py` | 1.7KB | Test share story v2 | 🗑 DELETE |

#### Other `_*.py` files (remaining ~46 files)

| File | Size | Purpose | Recommendation |
|------|------|---------|----------------|
| `_add_mention_modeljagger.py` | 619B | One-off account fix | 🗑 DELETE |
| `_age_logs.py` | 466B | Log aging utility | 🗑 DELETE |
| `_apply_tags.py` | 4.6KB | Apply tags one-time | 🗑 DELETE |
| `_bump_share_limit.py` | 730B | Bump share limit | 🗑 DELETE |
| `_cleanup.py` | 207B | Cleanup script | 🗑 DELETE |
| `_connect_jack1.py` | 741B | Connect specific device | 🗑 DELETE |
| `_create_test_job.py` | 2.4KB | Create test job | 🗑 DELETE |
| `_disable_others.py` | 391B | Disable other accounts | 🗑 DELETE |
| `_dump_screen.py` | 317B | Dump screen | 🗑 DELETE |
| `_dump_screen2.py` | 1.2KB | Dump screen v2 | 🗑 DELETE |
| `_extend_window.py` | 538B | Extend time window | 🗑 DELETE |
| `_extract_tags.py` | 3.3KB | Extract tags | 🗑 DELETE |
| `_find_tags.py` | 2.2KB | Find tags | 🗑 DELETE |
| `_follow_timeline.py` | 1.1KB | Follow timeline test | 🗑 DELETE |
| `_inspect_tags.py` | 1.2KB | Inspect tags | 🗑 DELETE |
| `_log_check.py` | 2.4KB | Check logs | 🗑 DELETE |
| `_migrate_tags.py` | 1.7KB | Migrate tags one-time | 🗑 DELETE |
| `_reschedule.py` | 1.1KB | Reschedule tasks | 🗑 DELETE |
| `_restart4.py` | 476B | Restart device 4 | 🗑 DELETE |
| `_restart_all_jagger.py` | 898B | Restart jagger accounts | 🗑 DELETE |
| `_restart_jagger.py` | 1.0KB | Restart jagger | 🗑 DELETE |
| `_restore_accounts.py` | 1.2KB | Restore accounts | 🗑 DELETE |
| `_revert_windows.py` | 335B | Revert windows | 🗑 DELETE |
| `_run_post_showcase.py` | 7.8KB | Run post showcase | 🗑 DELETE |
| `_run_post_showcase2.py` | 2.8KB | Run post showcase v2 | 🗑 DELETE |
| `_schedule_reel_test.py` | 982B | Schedule reel test | 🗑 DELETE |
| `_set_active_story.py` | 1.1KB | Set active story | 🗑 DELETE |
| `_setup_schedule.py` | 717B | Setup schedule | 🗑 DELETE |
| `_setup_story_test.py` | 1.8KB | Setup story test | 🗑 DELETE |
| `_show_samples.py` | 1.0KB | Show samples | 🗑 DELETE |
| `_start4.py` | 348B | Start device 4 | 🗑 DELETE |
| `_tap_share.py` | 853B | Tap share button | 🗑 DELETE |
| `_tmp_comment.py` | 1.9KB | Temp comment test | 🗑 DELETE |
| `_tmp_post.py` | 1.0KB | Temp post test | 🗑 DELETE |
| `_update_jagger.py` | 2.7KB | Update jagger accounts | 🗑 DELETE |
| `_verify_changes.py` | 697B | Verify changes | 🗑 DELETE |
| `_verify_dedup.py` | 741B | Verify dedup | 🗑 DELETE |
| `_verify_jagger.py` | 462B | Verify jagger | 🗑 DELETE |
| `_watch_post.py` | 1.5KB | Watch post | 🗑 DELETE |

### Other Root Debug/Test Scripts (non-underscore, ~48 files)

| File | Size | Purpose | Recommendation |
|------|------|---------|----------------|
| `debug_dm_button.py` | 1.2KB | Debug DM | 🗑 DELETE |
| `debug_dm_button2.py` | 1.9KB | Debug DM v2 | 🗑 DELETE |
| `debug_dm_button3.py` | 1.9KB | Debug DM v3 | 🗑 DELETE |
| `debug_dm_button4.py` | 2.7KB | Debug DM v4 | 🗑 DELETE |
| `debug_post_author.py` | 2.3KB | Debug post author | 🗑 DELETE |
| `debug_profile.py` | 1.9KB | Debug profile | 🗑 DELETE |
| `debug_profile2.py` | 2.5KB | Debug profile v2 | 🗑 DELETE |
| `debug_profile3.py` | 2.2KB | Debug profile v3 | 🗑 DELETE |
| `debug_profile4.py` | 4.9KB | Debug profile v4 | 🗑 DELETE |
| `debug_start.py` | 1.1KB | Debug start | 🗑 DELETE |
| `do_dashboard_profile.py` | 444B | Dashboard profile test | 🗑 DELETE |
| `do_dashboard_profile_done.py` | 763B | Dashboard profile done | 🗑 DELETE |
| `do_dashboard_update.py` | 832B | Dashboard update test | 🗑 DELETE |
| `do_dashboard_update2.py` | 551B | Dashboard update v2 | 🗑 DELETE |
| `dump_all.py` | 6.0KB | Dump all data | 🗑 DELETE |
| `dump_db.py` | 784B | Dump database | 🗑 DELETE |
| `dump_schema.py` | 375B | Dump schema | 🗑 DELETE |
| `dump_screen.py` | 658B | Dump screen | 🗑 DELETE |
| `dump_step.py` | 9.4KB | Dump step | 🗑 DELETE |
| `dump_story_editor.py` | 2.5KB | Dump story editor | 🗑 DELETE |
| `extract_real_packages.py` | 5.3KB | Extract packages | 🗑 DELETE |
| `find_bounds.py` | 2.0KB | Find UI bounds | 🗑 DELETE |
| `find_logged_in.py` | 1.6KB | Find logged in | 🗑 DELETE |
| `find_old_packages.py` | 3.9KB | Find old packages | 🗑 DELETE |
| `investigate.py` | 4.4KB | Investigation 1 | 🗑 DELETE |
| `investigate2.py` | 1.8KB | Investigation 2 | 🗑 DELETE |
| `investigate3.py` | 4.0KB | Investigation 3 | 🗑 DELETE |
| `investigate4.py` | 2.6KB | Investigation 4 | 🗑 DELETE |
| `investigate5.py` | 4.1KB | Investigation 5 | 🗑 DELETE |
| `investigate6.py` | 3.1KB | Investigation 6 | 🗑 DELETE |
| `investigate7.py` | 2.9KB | Investigation 7 | 🗑 DELETE |
| `map_editor.py` | 1.4KB | Map editor test | 🗑 DELETE |
| `parse_editor.py` | 1.2KB | Parse editor | 🗑 DELETE |
| `parse_grid.py` | 1.9KB | Parse grid | 🗑 DELETE |
| `parse_xml.py` | 582B | Parse XML | 🗑 DELETE |
| `quick_check.py` | 2.3KB | Quick check | 🗑 DELETE |
| `quick_test.py` | 2.8KB | Quick test | 🗑 DELETE |
| `report_final.py` | 7.9KB | Report final test | 🗑 DELETE |
| `reset_and_report.py` | 6.8KB | Reset and report | 🗑 DELETE |
| `reset_device.py` | 1.0KB | Reset device | 🗑 DELETE |
| `screen_capture.py` | 7.2KB | Screen capture | 🗑 DELETE |
| `setup_all_tests.py` | 2.6KB | Setup all tests | 🗑 DELETE |
| `setup_report.py` | 1.5KB | Setup report | 🗑 DELETE |
| `setup_test.py` | 2.2KB | Setup test | 🗑 DELETE |
| `setup_test2.py` | 2.8KB | Setup test 2 | 🗑 DELETE |
| `tap_continue_report.py` | 5.5KB | Tap report button | 🗑 DELETE |
| `tap_report_account.py` | 4.6KB | Tap report account | 🗑 DELETE |
| `tap_report_full.py` | 5.5KB | Tap report full | 🗑 DELETE |
| `tap_report_now.py` | 4.6KB | Tap report now | 🗑 DELETE |
| `tap_something_else.py` | 3.1KB | Tap something else | 🗑 DELETE |
| `temp_add_sources.py` | 495B | Temp add sources | 🗑 DELETE |
| `tmp_check.py` | 670B | Temp check | 🗑 DELETE |
| `tmp_run_private.py` | 1.5KB | Temp run private | 🗑 DELETE |
| `tmp_step.py` | 8.0KB | Temp step | 🗑 DELETE |
| `tmp_sync.py` | 2.3KB | Temp sync | 🗑 DELETE |
| `tmp_test_comment.py` | 1.9KB | Temp test comment | 🗑 DELETE |
| `tmp_test_share.py` | 2.1KB | Temp test share | 🗑 DELETE |
| `tmp_xml.py` | 3.5KB | Temp XML | 🗑 DELETE |
| `verify_fixes.py` | 4.8KB | Verify fixes | 🗑 DELETE |
| `verify_import.py` | 8.8KB | Verify import | 🗑 DELETE |
| `verify_live.py` | 2.6KB | Verify live | 🗑 DELETE |
| `verify_offline.py` | 3.8KB | Verify offline | 🗑 DELETE |
| `verify_packages.py` | 644B | Verify packages | 🗑 DELETE |
| `verify_reels.py` | 1.5KB | Verify reels | 🗑 DELETE |

### Dashboard Debug Scripts (22 files in `/dashboard/`)

| File | Size | Recommendation |
|------|------|----------------|
| `_check_settings.py` | 1.1KB | 🗑 DELETE |
| `_check_stats.py` | 808B | 🗑 DELETE |
| `check_accounts_columns.py` | 594B | 🗑 DELETE |
| `check_single_settings_db.py` | 3.0KB | 🗑 DELETE |
| `examine_settings_db.py` | 4.3KB | 🗑 DELETE |
| `examine_specific_db.py` | 3.6KB — **contains hardcoded path to another user's PC** | 🗑 DELETE |
| `fix_captions.py` | 2.2KB | 🗑 DELETE |
| `fix_caption_templates.py` | 6.7KB | 🗑 DELETE |
| `caption_template_comprehensive_fix.py` | 4.8KB | 🗑 DELETE |
| `caption_template_fix.py` | 2.0KB | 🗑 DELETE |
| `inspect_all_jobs.py` | 1.7KB | 🗑 DELETE |
| `inspect_central_jobs.py` | 2.1KB | 🗑 DELETE |
| `inspect_job_config.py` | 3.4KB | 🗑 DELETE |
| `inspect_job_db.py` | 1.6KB | 🗑 DELETE |
| `integrate_caption_templates.py` | 1.0KB | 🗑 DELETE |
| `simple_caption_fix.py` | 3.7KB | 🗑 DELETE |
| `sync_captions_from_dashboard.py` | 6.2KB | 🗑 DELETE |
| `test_accounts_scan.py` | 2.2KB | 🗑 DELETE |
| `test_basedir.py` | 1.0KB | 🗑 DELETE |
| `update_account_captions.py` | 4.5KB | 🗑 DELETE (unless used by routes) |
| `update_account_settings.py` | 7.1KB | ⚠️ KEEP — imported by `simple_app.py` line 4454 |
| `update_bulk_settings.py` | 5.0KB | 🗑 DELETE (unless imported) |
| `update_captions.py` | 3.4KB | 🗑 DELETE |

### `test_results/` Directory

- **585 files, 114.7 MB**
- Contains XML dumps and PNG screenshots from development testing
- **ALL should be deleted** from release branch
- Already in `.gitignore` but exists on disk

### `screenshots/` Directory

- **135 files, 72 MB**
- Development screenshots from testing report/comment flows
- **ALL should be deleted** from release branch
- Already in `.gitignore`

### Root `.png` Files (63 files, ~46 MB)

- `screenshot_gallery.png`, `screenshot_post1.png` through `screenshot_post11.png`, etc.
- `ss_caption.png`, `ss_filter.png`, `ss_now.png`, `ss_now2.png`, `ss_now3.png`
- `tmp_after_private.png`, `tmp_camillo_deeplink.png`, `tmp_check_state.png`, etc.
- All development screenshots — **DELETE from release**

### `dist/` Directory (489 files, 109 MB)

- Contains obfuscated (PyArmor) build output
- Should NOT be in the repo — it's a build artifact
- Already in `.gitignore` but exists on disk

### Other Files to Review

| File | Purpose | Recommendation |
|------|---------|----------------|
| `dump.txt` | 100KB text dump | 🗑 DELETE |
| `ui_dump.xml` | UI dump | 🗑 DELETE |
| `tmp_after_private.xml` | Temp XML | 🗑 DELETE |
| `tmp_profile.xml` | Temp XML | 🗑 DELETE |
| `pyarmor.bug.log` | PyArmor debug log | 🗑 DELETE |
| `pyarmor-regcode-11432.txt` | PyArmor registration code | ⚠️ SENSITIVE — should not be in release |
| `pyarmor-regfile-11432.zip` | PyArmor registration file | ⚠️ SENSITIVE — should not be in release |
| `dev_phone_screenshot.png` | Dev screenshot | 🗑 DELETE |
| `hydra.ico` | Icon file | ✅ KEEP |
| `VERSION` | Version file | ✅ KEEP |
| `app.py` (37KB root) | Old/duplicate app entry point? | ⚠️ INVESTIGATE — may be unused |
| `dashboard_api.py` (1.8KB root) | Minimal API wrapper | ⚠️ INVESTIGATE — may be unused |
| `jarvis.py` | Jarvis integration | ⚠️ INVESTIGATE — may not be needed for clients |

---

## Summary Statistics

| Category | Count | Total Size | Action |
|----------|-------|------------|--------|
| Root `_*.py` scripts | 89 | ~113KB | 🗑 DELETE ALL |
| Root debug/test scripts | ~60 | ~200KB | 🗑 DELETE ALL |
| Root `.png` screenshots | 63 | ~46MB | 🗑 DELETE ALL |
| Dashboard debug scripts | 22 | ~60KB | 🗑 DELETE (except `update_account_settings.py`) |
| `test_results/` dir | 585 | 114.7MB | 🗑 DELETE ALL |
| `screenshots/` dir | 135 | 72MB | 🗑 DELETE ALL |
| `dist/` dir | 489 | 109MB | 🗑 DELETE ALL (build artifact) |
| Root XML/txt dumps | ~5 | ~210KB | 🗑 DELETE ALL |
| **Total cleanable** | **~1448 files** | **~342MB** | |

### Top 5 Priority Fixes

1. **🔴 Call `ensure_schema()` at dashboard startup** — prevents crash on fresh install
2. **🔴 Create default `global_settings.json` at startup** — with empty API keys
3. **🔴 Remove API key from `global_settings.json`** — it's leaked
4. **🔴 Add root `README.md`** — first thing a client sees
5. **🟡 Delete all test/debug scripts from release branch** — ~342MB of junk
