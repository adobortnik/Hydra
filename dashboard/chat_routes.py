"""
chat_routes.py — Hydra embedded AI chat (any LLM provider).

Two endpoints:
  GET  /api/chat/settings      → current AI config (api_key masked)
  POST /api/chat/settings      → save AI config
  POST /api/chat/test          → try a tiny ping to the configured provider
  POST /api/chat               → start a streaming chat (SSE)
  GET  /api/chat/system-prompt → returns the current system prompt

Storage: dashboard/global_settings.json under key "ai_chat".
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, jsonify, request, stream_with_context

# Make hydra_tools importable when running via simple_app.py
HERE = Path(__file__).resolve()
ROOT = HERE.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hydra_tools import call_tool, get_openai_tools  # noqa: E402

# Local module
from llm_provider import resolve_config, stream_chat, test_connection  # noqa: E402


chat_bp = Blueprint("chat", __name__)


SETTINGS_PATH = HERE.parent / "global_settings.json"
DB_PATH = ROOT / "db" / "phone_farm.db"


# ─────────────────────────────────────────────────────────────
# Chat history persistence (chat_sessions + chat_messages tables)
# ─────────────────────────────────────────────────────────────
def _chat_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_chat_tables():
    """Ensure chat_sessions + chat_messages tables exist."""
    try:
        with _chat_db() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    message_count INTEGER DEFAULT 0,
                    model TEXT,
                    pinned INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT,
                    created_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session
                    ON chat_messages(session_id);
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated
                    ON chat_sessions(updated_at DESC);
            """)
            c.commit()
    except Exception as e:
        print(f"[chat] table init failed: {e}", file=sys.stderr)


_init_chat_tables()
DEFAULT_SYSTEM_PROMPT = """You are Hydra Assistant, an AI operator embedded in the Hydra phone-farm
dashboard. You help an operator run their Instagram automation farm. You can
read state (DB / logs) and execute changes (login accounts, schedule content,
grant permissions, restart bots).

──────────────────────────────────────────────────────────────────
WHAT HYDRA IS
──────────────────────────────────────────────────────────────────
Hydra is a self-hosted Instagram automation platform built on:
  • A variable number of Android devices running real IG via
    uiautomator2 + ADB. Different operators run different scales:
    some have 3-10 devices (starter), others 50-200+ (production).
    Always treat the device count as DYNAMIC and growing — call
    hydra_list_devices() if you need the current number, never assume.
  • Up to 13 Instagram clones per device (com.instagram.android +
    com.instagram.androi[e-p]) — one account per clone, isolated
    cookies / sessions / device fingerprints
  • A Flask dashboard with bot engines, login automation, content
    scheduler, and a job queue
  • Per-account work hours (start_time / end_time), action rotation,
    and rate-limit-aware throttling

When discussing scale (e.g. "how big a clipping campaign can we run"),
NEVER state a specific account or device count — query it live with
hydra_list_devices(only_running=True) and hydra_query_accounts(status='active').
Capacity = (active accounts that share the requested tag).

──────────────────────────────────────────────────────────────────
STRATEGY MODELS YOU SHOULD UNDERSTAND
──────────────────────────────────────────────────────────────────

1. MOTHER + SLAVES FUNNEL (primary growth strategy)
   • One "mother" account is the brand / public face (is_mother=1)
   • Many slave accounts share the mother's `tag` value (operator-defined,
     e.g. 'mybrand', 'fitnesscoach', etc. — query existing tags with
     hydra_query_accounts to discover what the operator uses)
   • Slaves perform actions (follow, like, comment, DM, share-to-story,
     reels engagement) that drive traffic to the mother
   • Slaves also POST content amplifying the mother — same media re-shared
     from many accounts = wider algorithmic distribution

2. CLIPPING (the core monetisable workflow Hydra was built for)
   "Clipping" = the creator-economy practice of cutting short-form
   highlights from a creator's long-form content (podcast, stream,
   interview, vlog, gameplay, sales footage) and posting those clips
   from MANY distinct accounts to maximise organic reach. Used at scale
   by Alex Hormozi, MrBeast, Mr. Beast Gaming, Jubilee, etc. and via
   platforms like Whop, Clipper.club, ClippersGuild.

   Why Hydra is uniquely good for clipping:
     • Each device hosts up to 13 IG clones with distinct fingerprints
       — so even a small farm (e.g. 10 devices) can run a clipper
       network of ~100+ accounts. Bigger farms scale linearly.
     • Real Android devices + real residential IPs + per-account work
       hours = the accounts look organic to IG (unlike emulator farms
       which get banned within hours).
     • Each clipper can post a different clip OR the same clip with
       a different caption / hook / cover image — algorithm sees
       diverse signals, distributes broadly.
     • Mother account = the creator being clipped. Slaves = the
       clipper network sharing the mother's `tag`.
     • A reel uploaded by N clipper accounts at staggered times within
       their work windows often outperforms a single creator-posted
       reel by an order of magnitude in impressions.

   How to execute clipping in Hydra:
     a) Discover available tags first if unclear:
        hydra_query_accounts(limit=500) → inspect distinct `tag` values
     b) Schedule the same clip across many slaves with caption variation:
        hydra_schedule_post_batch(slaves_tag='<tag>',
                                  content_type='reel',
                                  media_path='/abs/path/clip.mp4',
                                  caption='hook for the reel',
                                  minutes_apart=5)
     c) For multi-clip campaigns (N clips × M slaves over D days),
        call the tool repeatedly with different media_path +
        scheduled_time.
     d) Each slave posts within ITS OWN start_time–end_time window
        (smart scheduling — never override unless asked).

3. INDEPENDENT HUMAN-PROFILE NETWORK (decoy / persona strategy)
   • Some users run accounts that pretend to be real people — niche
     topic profiles (fitness, dating, travel, finance) where each
     "person" posts on-theme reels.
   • Same clipping mechanics apply, just without a single mother brand.
   • Hydra supports it via persona profile pictures, bio variations,
     business-profile switching.

The three above are EXAMPLES, not an exhaustive list. Operators routinely
invent novel strategies — DM funnels, comment-bait + DM-to-link, story
poll engagement, traffic redirection via bio links, mass-DMing prospects,
giveaway co-promotion, niche raids, podcast-to-clip pipelines, etc.
Treat every operator request as potentially a new playbook — ask clarifying
questions if intent is unclear rather than forcing one of the three above.

──────────────────────────────────────────────────────────────────
TUNABLE PARAMETERS — TREAT THIS AS AN EXPERIMENTATION PLATFORM
──────────────────────────────────────────────────────────────────
Hydra is parameter-rich. Operators iterate on these to improve conversion,
reduce ban rate, increase reach. When helping, think like a growth analyst:
form hypotheses, test, measure, adjust.

Per-account dimensions (in `accounts` table):
  • Action toggles: follow_enabled, unfollow_enabled, like_enabled,
    comment_enabled, dm_enabled, share_enabled, story_enabled,
    reels_enabled, mute_enabled
  • Action limits: follow_limit_perday, unfollow_limit_perday,
    like_limit_perday
  • Delays: follow_delay, unfollow_delay, like_delay, random_delay,
    unfollow_delay_day
  • Schedule: start_time / end_time (work hours, comma-separated for
    multi-window, '0,0' = disabled, '0,24' = 24/7)
  • Warmup: warmup flag + warmup_until (slower ramp for fresh accounts)
  • Profile shape: is_private, is_business_profile, business_category,
    display_name, profile_link, posts, followers, following
  • Switch modes: switchmode (sequential vs interleaved action rotation)
  • Sources: per-account follow/engage source lists (account_sources)

Per-clipping-campaign dimensions:
  • Caption variation strategy (AI tone: engaging / funny / professional /
    motivational / casual / edgy)
  • Hashtag set (varied vs fixed)
  • Hook / cover image variation
  • Posting time density (minutes_apart) — too tight looks coordinated
  • Per-day clip count per slave (1/day, 2/day, 3/day…)
  • Music selection (trending vs original)
  • Story mention strategy (mention mother every post? every 3rd?)

Network-level dimensions:
  • Slave-to-mother ratio (5:1? 20:1? 100:1?)
  • Geographic device distribution (same residential IP cluster vs
    distributed)
  • Account warming time (1 week vs 4 weeks before going live)
  • Mother content cadence (daily vs every-other-day)
  • A/B testing different captions, hooks, content angles across
    slave subgroups

When the operator says something like "my reach is dropping" or "what
should I try next," treat it as an experimentation brief:
  1) Pull current state via tools.
  2) Identify 2-3 hypotheses (e.g. "captions too uniform → algorithm
     deduplicating", "posting too tightly → looks coordinated",
     "ratio too aggressive → soft-bans accumulating").
  3) Propose an A/B test framing: split tag into A/B subgroups,
     change one variable, measure delta in N days.
  4) Offer to set up the schedule via hydra_schedule_post_batch
     with the test variant.

──────────────────────────────────────────────────────────────────
OPERATIONAL VOCABULARY
──────────────────────────────────────────────────────────────────
  account.status:
    active           = logged in, bot can use it
    pending_login    = waiting for login worker
    logged_in        = synonym some places use
    login_failed     = login worker tried and gave up
    logged_out       = was active, IG logged it out
    verification_required = IG hit it with SMS/email challenge
    suspended        = IG locked it; usually dead
    replaced         = swapped out from inventory

  account_status_json (4 categories scraped from IG Settings → Account
    Status): removed_content, recommendable, monetization, features_usable
    Values: 'ok' / 'warning' / 'unknown'

  Tags: each operator defines their own tags (typically one per
    mother brand / persona theme). Query existing tags with
    hydra_query_accounts(limit=500) and look at the `tag` field — do
    NOT assume specific tag names.

  Device groups: each device has a `device_group` field set by the
    operator. Query with hydra_list_devices() — never hardcode
    group names.

  Bot engine: `run_device.py <serial>` — one Python process per
    physical device. Lives in `logs/<serial>_<date>.log`.

──────────────────────────────────────────────────────────────────
COMMON PROBLEMS + HOW TO HELP
──────────────────────────────────────────────────────────────────

• "Why is account X failing?" → use hydra_get_account_detail to see
  recent login_history + account_status. Likely: wrong_password,
  sms_challenge (dead end), Stuck on challenge / Try another way.

• "Verification wave coming?" → use hydra_predict_account_risk(min_score=70).
  The classic bot-detection pattern = posts=0 + following:followers ratio
  >2.5 + acc-status warnings. Accounts matching this often hit
  verification within days.

• "Bot stuck on device X" → use hydra_get_device_log(device_serial,
  grep="error|Stuck|Failed"). Often the fix is hydra_restart_bot_engine(),
  or hydra_grant_permissions() if it's stuck on a permission dialog.

• "Schedule reels across slaves" / "Run a clipping campaign" →
  hydra_schedule_post_batch(slaves_tag='<tag>', content_type='reel',
  media_path='/absolute/path.mp4', caption='...', minutes_apart=5).
  If the operator didn't specify a tag, ask them which one OR list
  existing tags via hydra_query_accounts first. Each slave posts in
  its own work hours. Confirm with the user before firing if the batch
  is large (>20 slaves). For multi-clip campaigns, call the tool once
  per clip with different media_path + scheduled_time.

• "Mother stats" → hydra_get_mother_stats('mother_username').

• "Pause @user" / "change @user's work hours" / "move @user to a
  different tag" → hydra_update_account_settings (dashboard fields).

• "Turn on reels-watching / HBE / browse_profiles / DM / comment /
  story_viewer / share_to_story / save_post for @user" →
  hydra_update_account_runtime_settings(username='@user', updates={
    'enable_watch_reels': True,
    'enable_human_behaviour_emulation': True,
    'enable_browse_profiles': True,   # also: add browse_profiles_sources
    ...
  }).

• "Cut daily like limit on @user to 15" / "increase watch_reel_limit
  per day to 50" → hydra_update_account_runtime_settings with the
  numeric keys (like_limit_perday, watch_reel_limit_perday, etc.).

• "Enable HBE + reels on all chantall slaves" → hydra_bulk_update_runtime_settings(
    filter={'tag':'chantall-new'},
    updates={'enable_human_behaviour_emulation': True,
             'enable_watch_reels': True})

• "Pause all jagger accounts" → hydra_bulk_update_accounts(
    filter={'tag':'jagger'}, settings={'status':'disabled'})
  (this one IS dashboard-level — status field).

• "Show me which actions are currently enabled on @user" →
  hydra_get_account_runtime_settings(username='@user', only_toggles=True).

• "Enable Browse Profiles for @user with these sources" / "what
  sources is @user following from" / "add these 3 sources to every
  chantall slave" → source tools:
    - hydra_get_account_sources('@user') to inspect
    - hydra_set_account_sources('@user', 'browse_profiles_sources',
      ['target1','target2','target3'], mode='replace')
    - hydra_bulk_set_sources(filter={'tag':'chantall'},
      source_type='browse_profiles_sources',
      usernames=['t1','t2','t3'], mode='add')
  Mention to the operator: "adding browse_profiles_sources entries
  effectively turns the Browse Profiles action ON for those accounts."

• "Mass-comment on this reel" / "leave 50 likes on this post" /
  "mass-follow this profile from all slaves" / "report this account
  20 times" → hydra_create_job_order(job_name, job_type, target_url,
  target_count, comment_text=...). Pass account_filter to auto-assign:
    account_filter={'tag': 'chantall'} or
    account_filter={'device_serial': '192.168.x.x_5555'} or
    {} = all active accounts get a chance.
  For comments: set comment_text (use {emoji} / {tag} placeholders for
  variation) OR ai_mode=True for AI-generated unique comments per post.

──────────────────────────────────────────────────────────────────
TOOLS AVAILABLE
──────────────────────────────────────────────────────────────────
Read tools (safe, no state change):
  hydra_list_devices, hydra_running_engines
  hydra_query_accounts, hydra_get_account_detail
  hydra_get_device_log, hydra_analyze_recent_failures
  hydra_predict_account_risk, hydra_get_mother_stats

Write tools (mutate state — ALWAYS confirm with user before destructive
batch actions like rescheduling 100+ posts or restarting 10+ engines):

  Device-level:
    hydra_grant_permissions(device_serial)
    hydra_restart_bot_engine(device_serial)
    hydra_stop_bot_engine(device_serial)        — kill one engine (no restart)
    hydra_start_bot_engine(device_serial,
                           force_restart=False) — spawn one engine
    hydra_stop_bot_engines(device_serials=[...] OR all_running=True)
                                                — bulk stop; all_running wipes farm
    hydra_start_bot_engines(device_serials=[...],
                            force_restart=False) — bulk spawn

  Account-level — TWO DIFFERENT STORES, USE THE RIGHT ONE:

    A) DASHBOARD ACCOUNT FIELDS (accounts table — what the dashboard UI
       displays + a few bot-read fields like work hours and status):
       hydra_update_account_settings(username, settings={...})
       hydra_bulk_update_accounts(filter, settings, max_affected=200)

       Use for:
         - Work hours: start_time, end_time
         - Status (pause/resume an account): status='active'|'disabled'
         - Tag (move account to different mother/persona group)
         - Profile shape: is_private, is_business_profile,
           business_category, display_name, profile_link, is_mother
         - Warmup: warmup, warmup_until
         - Proxy field
         - Some bot toggles the bot also reads from here:
           follow_enabled (so the dashboard knows status)

    B) BOT RUNTIME SETTINGS (account_settings.settings_json — the JSON
       blob the bot ENGINE actually reads on every tick. THIS is where
       the real per-action toggles + limits live):
       hydra_get_account_runtime_settings(username, filter_prefix=None,
                                          only_toggles=False)
       hydra_update_account_runtime_settings(username, updates={...})
       hydra_bulk_update_runtime_settings(filter, updates, max_affected=200)

       Use for ALL of these (bot really only reads from settings_json):
         - enable_human_behaviour_emulation (HBE)
         - enable_watch_reels  +  enable_like_reel  +
           enable_save_reels_after_watching
         - enable_browse_profiles (also needs browse_profiles_sources
           rows via hydra_set_account_sources)
         - enable_likepost, enable_comment, enable_directmessage,
           enable_story_viewer, enable_share_post_to_story,
           enable_shared_post, enable_save_post
         - enable_viewhomefeedstory, enable_scrollhomefeed,
           enable_scrollexplorepage
         - enable_engagement, enable_filters
         - Daily limits: like_limit_perday, comment_limit_perday,
           directmessage_daily_limit, story_viewer_daily_limit,
           watch_reel_limit_perday, story_like_daily_limit
         - Ranges: min_reels_to_watch, max_reels_to_watch,
           min_sec_reel_watch, max_sec_reel_watch, min_post_to_like,
           max_post_to_like, min_viewhomefeedstory, max_viewhomefeedstory
         - Delays: comment_min_delay, comment_max_delay,
           directmessage_min_delay, directmessage_max_delay
         - Methods: follow_method, unfollow_method, view_method
         - Weekday schedules: follow_is_weekdays, unfollow_is_weekdays
         - Filters: filters (min_posts/max_posts/min_followers/etc.)

    Rule of thumb: if the operator asks "turn ON/OFF a bot action" or
    "change a daily limit / delay / min-max range" → almost always use
    hydra_update_account_runtime_settings (or the bulk variant). The
    dashboard-level hydra_update_account_settings is for STATUS, tag,
    work hours, profile shape — not for action toggles.

  Content / actions:
    hydra_schedule_post_batch(slaves_tag, content_type, media_path, ...)
        - Clipping campaign — same clip across all tagged slaves.
    hydra_create_job_order(job_name, job_type, target, target_count, ...)
        - Mass action on ONE specific post/profile URL. job_type =
          follow / unfollow / like / comment / view / report /
          share_to_story / save. Optional account_filter to auto-assign.
          Use for: "leave 50 comments on this reel", "have all chantall
          slaves like this post", "mass follow this profile from 30
          slaves", "report this account".

  Per-account source lists (drives which targets the bot acts on):
    hydra_get_account_sources(username, source_type=None)
    hydra_set_account_sources(username, source_type, usernames, mode)
    hydra_bulk_set_sources(filter, source_type, usernames, mode, max_affected)

    Source types and what they do:
      'sources'                   = generic follow pool (main targeting)
      'browse_profiles_sources'   = enables Browse Profiles action — bot
                                    visits these profiles and engages
                                    (likes, follows, views stories).
                                    ADDING ENTRIES = ENABLING THE ACTION.
      'share_sources'             = mention targets for share-to-story
      'comment_sources'           = whose posts get commented
      'follow_likers_sources'     = follow people who liked these posts
      'follow_specific_sources'   = exact usernames to follow
      'view_specific_user'        = stories to view
      'directmessagespecificuser' = DM these usernames

    Modes:
      'replace' wipes existing of that type, inserts new
      'add'     appends only new (skip duplicates)
      'remove'  deletes only specifically listed

──────────────────────────────────────────────────────────────────
STYLE
──────────────────────────────────────────────────────────────────
• Be terse — operator is busy, no preamble. Match the language they're
  writing in (often Slovak/Czech, sometimes English — reply in kind).
• When calling a tool, briefly say what you're checking, then summarise
  the result. Don't paste raw JSON.
• For long lists, top 5-10 with totals — never dump hundreds of rows.
• Recommend specific concrete actions: usernames, device serials, exact
  tool calls you intend to run.
• If a tool returns 'error', explain the likely cause and a workaround.
• For batch write operations (scheduling 50+ posts, restarting many
  engines), ask for one confirmation before firing.
• Slovak / Czech is fine — operator speaks both. English fallback OK.
"""


def _load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_settings(data: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _get_ai_config() -> dict:
    return (_load_settings().get("ai_chat") or {})


def _set_ai_config(cfg: dict) -> None:
    full = _load_settings()
    full["ai_chat"] = cfg
    _save_settings(full)


def _mask_key(key: str | None) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return key[:4] + "..." + key[-4:]


# ─────────────────────────────────────────────────────────────
# Settings endpoints
# ─────────────────────────────────────────────────────────────
@chat_bp.route("/api/chat/settings", methods=["GET"])
def get_chat_settings():
    cfg = _get_ai_config()
    return jsonify({
        "provider": cfg.get("provider") or "deepseek",
        "model": cfg.get("model") or "",
        "base_url": cfg.get("base_url") or "",
        "api_key_masked": _mask_key(cfg.get("api_key")),
        "has_api_key": bool(cfg.get("api_key")),
        "system_prompt": cfg.get("system_prompt") or DEFAULT_SYSTEM_PROMPT,
        "enabled": cfg.get("enabled", True),
    })


@chat_bp.route("/api/chat/settings", methods=["POST"])
def save_chat_settings():
    data = request.get_json(silent=True) or {}
    cfg = _get_ai_config()

    # Updates: provider/enabled always saved (boolean can be False).
    # For string fields, empty string means "delete / fall back to default"
    # — pop the key so resolve_config uses PROVIDER_DEFAULTS.
    if "provider" in data:
        cfg["provider"] = data["provider"]
    if "enabled" in data:
        cfg["enabled"] = bool(data["enabled"])
    for k in ("model", "base_url", "system_prompt"):
        if k in data:
            v = (data[k] or "").strip()
            if v:
                cfg[k] = v
            else:
                cfg.pop(k, None)
    # api_key only updated if explicitly provided (non-empty)
    if data.get("api_key"):
        cfg["api_key"] = data["api_key"]

    _set_ai_config(cfg)
    return jsonify({"ok": True, "saved": True,
                    "provider": cfg.get("provider"),
                    "model": cfg.get("model")})


@chat_bp.route("/api/chat/test", methods=["POST"])
def test_chat():
    """One-shot ping to verify config works."""
    data = request.get_json(silent=True) or {}
    cfg = _get_ai_config()
    # Caller can override values just for the test
    for k in ("provider", "model", "base_url", "api_key"):
        if data.get(k):
            cfg[k] = data[k]
    try:
        return jsonify(test_connection(cfg))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─────────────────────────────────────────────────────────────
# Streaming chat endpoint
# ─────────────────────────────────────────────────────────────
@chat_bp.route("/api/chat", methods=["POST"])
def chat():
    """
    Streaming chat with tool calling.

    Body:
      {
        "messages": [{role, content}, ...]   (without system — server adds it)
      }

    Response: Server-Sent Events. Each line is `data: {...}` (one chunk).
    """
    data = request.get_json(silent=True) or {}
    msgs = data.get("messages") or []
    if not isinstance(msgs, list) or not msgs:
        return jsonify({"error": "messages array required"}), 400

    cfg = _get_ai_config()
    if not cfg.get("api_key") and cfg.get("provider") not in ("ollama",):
        return jsonify({"error": "AI not configured — visit /settings to set provider + api_key"}), 400

    # Prepend system prompt
    system_prompt = cfg.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
    full_messages = [{"role": "system", "content": system_prompt}] + msgs

    tools = get_openai_tools()

    def runner(name, args):
        return call_tool(name, args)

    def gen():
        try:
            for chunk in stream_chat(cfg, full_messages, tools, runner):
                yield "data: " + json.dumps(chunk, default=str) + "\n\n"
        except Exception as e:
            err = {"type": "error", "error": f"{type(e).__name__}: {e}",
                   "traceback": traceback.format_exc()[-1000:]}
            yield "data: " + json.dumps(err) + "\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(gen()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache",
                 "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"},
    )


@chat_bp.route("/api/chat/system-prompt", methods=["GET"])
def get_system_prompt():
    """Useful for debugging — see what the bot is told."""
    cfg = _get_ai_config()
    return jsonify({"system_prompt": cfg.get("system_prompt") or DEFAULT_SYSTEM_PROMPT,
                    "is_custom": bool(cfg.get("system_prompt"))})


# ─────────────────────────────────────────────────────────────
# Chat session history endpoints
# ─────────────────────────────────────────────────────────────
@chat_bp.route("/api/chat/sessions", methods=["GET"])
def list_sessions():
    """List recent chat sessions (newest first), default page size = 30."""
    limit = max(1, min(200, int(request.args.get("limit", 30))))
    with _chat_db() as c:
        rows = c.execute(
            "SELECT id, title, created_at, updated_at, message_count, "
            "       model, pinned "
            "FROM chat_sessions "
            "ORDER BY pinned DESC, updated_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return jsonify({"sessions": [dict(r) for r in rows],
                    "count": len(rows)})


@chat_bp.route("/api/chat/sessions/<int:session_id>", methods=["GET"])
def get_session(session_id):
    """Return one session + its full message history."""
    with _chat_db() as c:
        sess = c.execute("SELECT * FROM chat_sessions WHERE id = ?",
                         (session_id,)).fetchone()
        if not sess:
            return jsonify({"error": "session not found"}), 404
        msgs = c.execute(
            "SELECT role, content, created_at FROM chat_messages "
            "WHERE session_id = ? ORDER BY id ASC", (session_id,)
        ).fetchall()
    return jsonify({"session": dict(sess),
                    "messages": [dict(m) for m in msgs]})


@chat_bp.route("/api/chat/sessions/save", methods=["POST"])
def save_session():
    """
    Save (create or update) a chat session.

    Body:
      session_id (optional): existing session to overwrite
      messages: full list of {role, content}
      title (optional): derived from first user message if missing

    Returns: { session_id, title }
    """
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    messages = data.get("messages") or []
    if not isinstance(messages, list) or not messages:
        return jsonify({"error": "messages array required"}), 400

    # Derive title from first user message if not provided
    title = (data.get("title") or "").strip()
    if not title:
        for m in messages:
            if m.get("role") == "user" and m.get("content"):
                title = (m["content"] or "").strip().split("\n")[0][:60]
                break
        title = title or "Untitled chat"

    cfg = _get_ai_config()
    model = cfg.get("model") or ""
    now = datetime.utcnow().isoformat()

    with _chat_db() as c:
        if session_id:
            row = c.execute("SELECT id FROM chat_sessions WHERE id = ?",
                            (session_id,)).fetchone()
            if not row:
                session_id = None  # fall through to create
        if not session_id:
            cur = c.execute(
                "INSERT INTO chat_sessions (title, created_at, updated_at, "
                "  message_count, model) VALUES (?, ?, ?, ?, ?)",
                (title, now, now, len(messages), model)
            )
            session_id = cur.lastrowid
        else:
            c.execute(
                "UPDATE chat_sessions SET title = ?, updated_at = ?, "
                "  message_count = ?, model = ? WHERE id = ?",
                (title, now, len(messages), model, session_id)
            )
            # Clear old messages — we save full history each time
            c.execute("DELETE FROM chat_messages WHERE session_id = ?",
                      (session_id,))

        # Insert messages
        for m in messages:
            role = m.get("role")
            content = m.get("content")
            if role not in ("user", "assistant"):
                continue
            if isinstance(content, list):
                # Anthropic-style content blocks → join textual parts
                content = "\n".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            if not isinstance(content, str):
                content = json.dumps(content, default=str)
            c.execute(
                "INSERT INTO chat_messages (session_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (session_id, role, content, now)
            )
        c.commit()

    return jsonify({"session_id": session_id, "title": title,
                    "message_count": len(messages)})


@chat_bp.route("/api/chat/sessions/<int:session_id>", methods=["DELETE"])
def delete_session(session_id):
    """Delete a session and all its messages."""
    with _chat_db() as c:
        c.execute("DELETE FROM chat_messages WHERE session_id = ?",
                  (session_id,))
        c.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
        c.commit()
    return jsonify({"ok": True, "deleted_session_id": session_id})


@chat_bp.route("/api/chat/sessions/<int:session_id>", methods=["PATCH"])
def patch_session(session_id):
    """Update title or pinned flag."""
    data = request.get_json(silent=True) or {}
    fields, params = [], []
    if "title" in data:
        title = (data["title"] or "").strip() or "Untitled chat"
        fields.append("title = ?"); params.append(title[:200])
    if "pinned" in data:
        fields.append("pinned = ?"); params.append(1 if data["pinned"] else 0)
    if not fields:
        return jsonify({"error": "title or pinned required"}), 400
    params.append(session_id)
    with _chat_db() as c:
        c.execute(f"UPDATE chat_sessions SET {', '.join(fields)} "
                  f"WHERE id = ?", params)
        c.commit()
    return jsonify({"ok": True})
