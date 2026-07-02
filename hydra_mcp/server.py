"""
Hydra MCP server — thin MCP wrapper around hydra_tools.

The actual implementation lives in `hydra_tools` so both the MCP server
(Claude Cowork / Code) and the embedded dashboard chat use the same code.

Run via:
    python -m hydra_mcp

Or register in Claude Code:
    claude mcp add hydra -- C:\\...\\python.exe -m hydra_mcp
"""
from __future__ import annotations

import sys

from mcp.server.fastmcp import FastMCP

from hydra_tools import (
    hydra_list_devices as _list_devices,
    hydra_running_engines as _running_engines,
    hydra_query_accounts as _query_accounts,
    hydra_get_account_detail as _get_account_detail,
    hydra_get_device_log as _get_device_log,
    hydra_analyze_recent_failures as _analyze_recent_failures,
    hydra_predict_account_risk as _predict_account_risk,
    hydra_get_mother_stats as _get_mother_stats,
    hydra_grant_permissions as _grant_permissions,
    hydra_restart_bot_engine as _restart_bot_engine,
    hydra_start_bot_engine as _start_bot_engine,
    hydra_stop_bot_engine as _stop_bot_engine,
    hydra_start_bot_engines as _start_bot_engines,
    hydra_stop_bot_engines as _stop_bot_engines,
    hydra_force_login_account as _force_login_account,
    hydra_schedule_post_batch as _schedule_post_batch,
    hydra_update_account_settings as _update_account_settings,
    hydra_bulk_update_accounts as _bulk_update_accounts,
    hydra_create_job_order as _create_job_order,
    hydra_get_account_sources as _get_account_sources,
    hydra_set_account_sources as _set_account_sources,
    hydra_bulk_set_sources as _bulk_set_sources,
    hydra_get_account_runtime_settings as _get_runtime_settings,
    hydra_update_account_runtime_settings as _update_runtime_settings,
    hydra_bulk_update_runtime_settings as _bulk_update_runtime_settings,
)


mcp = FastMCP(
    name="hydra",
    instructions=(
        "Hydra MCP — read-only access to a phone-farm dashboard's DB and logs.\n"
        "Use these tools when the user asks about Hydra accounts, devices, bot\n"
        "engine state, recent login attempts, or account risk."
    ),
)


@mcp.tool()
def hydra_list_devices(only_running: bool = False,
                       name_filter: str | None = None) -> dict:
    """List all devices with bot-engine running status. Optionally filter by name/group substring."""
    return _list_devices(only_running=only_running, name_filter=name_filter)


@mcp.tool()
def hydra_running_engines() -> dict:
    """Snapshot of run_device.py bot engines alive right now."""
    return _running_engines()


@mcp.tool()
def hydra_query_accounts(tag: str | None = None,
                         status: str | None = None,
                         device_serial: str | None = None,
                         username_like: str | None = None,
                         limit: int = 50) -> dict:
    """Query accounts with optional filters; includes last_action_at from action_history."""
    return _query_accounts(tag=tag, status=status, device_serial=device_serial,
                           username_like=username_like, limit=limit)


@mcp.tool()
def hydra_get_account_detail(username: str) -> dict:
    """Full info for one account: settings, account_status, and last 10 login attempts."""
    return _get_account_detail(username=username)


@mcp.tool()
def hydra_get_device_log(device_serial: str, tail_lines: int = 200,
                         date: str | None = None,
                         grep: str | None = None) -> dict:
    """Tail N lines of a device's bot-engine log with optional grep filter."""
    return _get_device_log(device_serial=device_serial, tail_lines=tail_lines,
                           date=date, grep=grep)


@mcp.tool()
def hydra_analyze_recent_failures(hours: int = 24) -> dict:
    """Bucket recent login failures by reason."""
    return _analyze_recent_failures(hours=hours)


@mcp.tool()
def hydra_predict_account_risk(min_score: int = 40, limit: int = 50,
                               tag: str | None = None) -> dict:
    """Heuristic ban-risk score per active account."""
    return _predict_account_risk(min_score=min_score, limit=limit, tag=tag)


@mcp.tool()
def hydra_get_mother_stats(mother_username: str) -> dict:
    """Mother + slaves performance summary."""
    return _get_mother_stats(mother_username=mother_username)


# ─── Write tools (phase 2) ───────────────────────────────────

@mcp.tool()
def hydra_grant_permissions(device_serial: str) -> dict:
    """Grant basic Android permissions (storage, camera, audio, location, contacts) to ALL IG clones on a device. Skips permission dialogs forever."""
    return _grant_permissions(device_serial=device_serial)


@mcp.tool()
def hydra_restart_bot_engine(device_serial: str) -> dict:
    """Kill run_device.py for a device and spawn a fresh one in a new console."""
    return _restart_bot_engine(device_serial=device_serial)


@mcp.tool()
def hydra_stop_bot_engine(device_serial: str) -> dict:
    """Stop (kill) the run_device.py process for one device. Does NOT restart."""
    return _stop_bot_engine(device_serial=device_serial)


@mcp.tool()
def hydra_start_bot_engine(device_serial: str,
                           force_restart: bool = False) -> dict:
    """Spawn a fresh run_device.py for one device. Skips if already running unless force_restart=true."""
    return _start_bot_engine(device_serial=device_serial,
                             force_restart=force_restart)


@mcp.tool()
def hydra_stop_bot_engines(device_serials: list | None = None,
                           all_running: bool = False) -> dict:
    """Stop run_device.py on many devices at once. Use all_running=true to wipe the entire farm."""
    return _stop_bot_engines(device_serials=device_serials,
                             all_running=all_running)


@mcp.tool()
def hydra_start_bot_engines(device_serials: list,
                            force_restart: bool = False) -> dict:
    """Spawn run_device.py on many devices at once. Skips already-running engines unless force_restart=true."""
    return _start_bot_engines(device_serials=device_serials,
                              force_restart=force_restart)


@mcp.tool()
def hydra_force_login_account(username: str) -> dict:
    """Reset account status to pending_login and trigger the login worker."""
    return _force_login_account(username=username)


@mcp.tool()
def hydra_schedule_post_batch(slaves_tag: str, content_type: str,
                              media_path: str, caption: str = "",
                              scheduled_time: str | None = None,
                              minutes_apart: int = 5,
                              hashtags: str | None = None) -> dict:
    """Schedule a content batch (post/reel/story) across all active slaves with a given tag — the core clipping workflow."""
    return _schedule_post_batch(slaves_tag=slaves_tag, content_type=content_type,
                                media_path=media_path, caption=caption,
                                scheduled_time=scheduled_time,
                                minutes_apart=minutes_apart,
                                hashtags=hashtags)


@mcp.tool()
def hydra_update_account_settings(username: str, settings: dict) -> dict:
    """Update settings on one account (action toggles, daily limits, work hours, status, profile shape, tag, etc.)."""
    return _update_account_settings(username=username, settings=settings)


@mcp.tool()
def hydra_bulk_update_accounts(filter: dict, settings: dict,
                               max_affected: int = 200) -> dict:
    """Apply the same settings change to many accounts at once (filter by tag/status/device/is_mother/username_like)."""
    return _bulk_update_accounts(filter=filter, settings=settings,
                                 max_affected=max_affected)


@mcp.tool()
def hydra_get_account_runtime_settings(username: str,
                                       filter_prefix: str | None = None,
                                       only_toggles: bool = False) -> dict:
    """Read the bot's REAL runtime settings JSON (HBE, watch_reels, browse_profiles, comment, DM, story_viewer, share, save toggles + daily limits + delays)."""
    return _get_runtime_settings(username=username,
                                 filter_prefix=filter_prefix,
                                 only_toggles=only_toggles)


@mcp.tool()
def hydra_update_account_runtime_settings(username: str, updates: dict) -> dict:
    """Merge changes into an account's runtime settings JSON — turn HBE/reels/browse_profiles/comment/DM/etc. on or off, change daily limits."""
    return _update_runtime_settings(username=username, updates=updates)


@mcp.tool()
def hydra_bulk_update_runtime_settings(filter: dict, updates: dict,
                                       max_affected: int = 200) -> dict:
    """Apply runtime-settings updates to many accounts at once (filter by tag/status/device)."""
    return _bulk_update_runtime_settings(filter=filter, updates=updates,
                                         max_affected=max_affected)


@mcp.tool()
def hydra_get_account_sources(username: str,
                              source_type: str | None = None) -> dict:
    """List source usernames currently configured for an account, grouped by source_type."""
    return _get_account_sources(username=username, source_type=source_type)


@mcp.tool()
def hydra_set_account_sources(username: str, source_type: str,
                              usernames: list, mode: str = "replace") -> dict:
    """Modify the source list for one account (browse_profiles, comment, follow, share, etc.). Mode: replace/add/remove."""
    return _set_account_sources(username=username, source_type=source_type,
                                usernames=usernames, mode=mode)


@mcp.tool()
def hydra_bulk_set_sources(filter: dict, source_type: str, usernames: list,
                           mode: str = "add",
                           max_affected: int = 200) -> dict:
    """Apply the same source-list change to many accounts at once (filter by tag/status/device)."""
    return _bulk_set_sources(filter=filter, source_type=source_type,
                             usernames=usernames, mode=mode,
                             max_affected=max_affected)


@mcp.tool()
def hydra_create_job_order(job_name: str, job_type: str, target: str,
                           target_count: int, limit_per_hour: int = 50,
                           limit_per_day: int = 200, comment_text: str = "",
                           account_filter: dict | None = None,
                           ai_mode: bool = False,
                           unique_comments: bool = True,
                           priority: int = 0) -> dict:
    """Create a mass-action job order (follow/like/comment/view/report/share_to_story/save) targeting a post or profile URL."""
    return _create_job_order(job_name=job_name, job_type=job_type,
                             target=target, target_count=target_count,
                             limit_per_hour=limit_per_hour,
                             limit_per_day=limit_per_day,
                             comment_text=comment_text,
                             account_filter=account_filter,
                             ai_mode=ai_mode, unique_comments=unique_comments,
                             priority=priority)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)  # type: ignore
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)  # type: ignore
    except Exception:
        pass
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
