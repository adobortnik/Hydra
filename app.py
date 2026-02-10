"""
Phone Farm Platform — Standalone App Entry Point
=================================================
Clean Flask app that:
  - Uses our own DB layer (db/models.py), NOT Onimator's scattered files
  - Runs on port 5060 (avoids Onimator's 5050 / dashboard's 5000)
  - Registers all blueprint routes from the dashboard
  - Has /api/health for liveness checks
  - Initializes empty DB on first run

Usage:
    python app.py                   # Start on port 5060
    python app.py --port 5080       # Custom port
    python app.py --init-db         # Just create DB, don't start server
"""

import os
import sys
import json
import datetime
import argparse

# ---------------------------------------------------------------------------
#  Path setup — make dashboard modules importable
# ---------------------------------------------------------------------------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_DIR = os.path.join(APP_DIR, "dashboard")
DB_DIR = os.path.join(APP_DIR, "db")

# Add dashboard to sys.path so its blueprints & modules resolve
sys.path.insert(0, DASHBOARD_DIR)
sys.path.insert(0, os.path.join(DASHBOARD_DIR, "uiAutomator"))
sys.path.insert(0, APP_DIR)

from flask import Flask, jsonify, render_template, request

# Our own DB layer
from db.models import init_db, get_connection, row_to_dict, DB_PATH

# ---------------------------------------------------------------------------
#  Flask app factory
# ---------------------------------------------------------------------------

def create_app():
    """Create and configure the Flask app."""

    app = Flask(
        __name__,
        template_folder=os.path.join(DASHBOARD_DIR, "templates"),
        static_folder=os.path.join(DASHBOARD_DIR, "static"),
    )
    app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024  # 512 MB

    # ------------------------------------------------------------------
    #  Initialize database
    # ------------------------------------------------------------------
    db_path = init_db()
    print(f"[OK] Database ready: {db_path}")

    # ------------------------------------------------------------------
    #  Health check (always first)
    # ------------------------------------------------------------------
    @app.route("/api/health")
    def health():
        """Liveness / readiness probe."""
        try:
            conn = get_connection()
            tables = [
                r["name"] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
            conn.close()
            return jsonify({
                "status": "healthy",
                "database": str(DB_PATH),
                "tables": len(tables),
                "timestamp": datetime.datetime.now().isoformat(),
                "version": "1.0.0",
            })
        except Exception as e:
            return jsonify({"status": "unhealthy", "error": str(e)}), 503

    # ------------------------------------------------------------------
    #  Core API: Devices
    # ------------------------------------------------------------------
    @app.route("/api/devices")
    def api_devices():
        conn = get_connection()
        rows = conn.execute("SELECT * FROM devices ORDER BY device_serial").fetchall()
        devices = []
        for r in rows:
            d = row_to_dict(r)
            # Dashboard expects 'deviceid' and 'devicename'
            d["deviceid"] = d["device_serial"]
            d["devicename"] = d.get("device_name") or d["device_serial"]
            # Count accounts
            cnt = conn.execute(
                "SELECT COUNT(*) as c FROM accounts WHERE device_serial=?",
                (d["device_serial"],),
            ).fetchone()
            d["accounts_count"] = cnt["c"] if cnt else 0
            devices.append(d)
        conn.close()
        return jsonify(devices)

    # ------------------------------------------------------------------
    #  Core API: Accounts
    # ------------------------------------------------------------------
    @app.route("/api/accounts")
    def api_accounts():
        conn = get_connection()
        device_filter = request.args.get("device")

        q = "SELECT * FROM accounts"
        params = []
        if device_filter:
            q += " WHERE device_serial=?"
            params.append(device_filter)
        q += " ORDER BY device_serial, username"

        rows = conn.execute(q, params).fetchall()
        accounts = []
        for r in rows:
            a = row_to_dict(r)
            # Dashboard field compat
            a["account"] = a["username"]
            a["deviceid"] = a["device_serial"]
            a["follow"] = a.get("follow_enabled", "False")
            a["unfollow"] = a.get("unfollow_enabled", "False")
            a["like"] = a.get("like_enabled", "False")
            a["comment"] = a.get("comment_enabled", "False")
            a["story"] = a.get("story_enabled", "False")
            a["mute"] = a.get("mute_enabled", "False")
            a["starttime"] = a.get("start_time", "0")
            a["endtime"] = a.get("end_time", "0")

            # Get latest stats
            stat = conn.execute(
                "SELECT * FROM account_stats WHERE account_id=? ORDER BY date DESC LIMIT 1",
                (a["id"],),
            ).fetchone()
            a["stats"] = row_to_dict(stat) if stat else {
                "followers": "0", "following": "0", "posts": "0"
            }

            # Device name
            dev = conn.execute(
                "SELECT device_name FROM devices WHERE device_serial=?",
                (a["device_serial"],),
            ).fetchone()
            a["devicename"] = dev["device_name"] if dev else a["device_serial"]

            accounts.append(a)
        conn.close()
        return jsonify(accounts)

    @app.route("/api/account/<deviceid>/<account>")
    def api_account(deviceid, account):
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM accounts WHERE device_serial=? AND username=?",
            (deviceid, account),
        ).fetchone()
        conn.close()
        if not row:
            return jsonify({"error": "Account not found"}), 404
        a = row_to_dict(row)
        a["account"] = a["username"]
        a["deviceid"] = a["device_serial"]
        return jsonify(a)

    # ------------------------------------------------------------------
    #  Core API: Dashboard Stats
    # ------------------------------------------------------------------
    @app.route("/api/dashboard/stats")
    def api_dashboard_stats():
        conn = get_connection()
        total_devices = conn.execute("SELECT COUNT(*) as c FROM devices").fetchone()["c"]
        total_accounts = conn.execute("SELECT COUNT(*) as c FROM accounts").fetchone()["c"]
        active_accounts = conn.execute(
            "SELECT COUNT(*) as c FROM accounts WHERE start_time != '0' AND end_time != '0'"
        ).fetchone()["c"]
        follow_enabled = conn.execute(
            "SELECT COUNT(*) as c FROM accounts WHERE follow_enabled='True'"
        ).fetchone()["c"]
        unfollow_enabled = conn.execute(
            "SELECT COUNT(*) as c FROM accounts WHERE unfollow_enabled='True'"
        ).fetchone()["c"]
        conn.close()
        return jsonify({
            "total_devices": total_devices,
            "total_accounts": total_accounts,
            "active_accounts": active_accounts,
            "total_followers": 0,
            "total_following": 0,
            "follow_enabled": follow_enabled,
            "unfollow_enabled": unfollow_enabled,
            "accounts_by_device": {},
        })

    # ------------------------------------------------------------------
    #  API: Bot Settings — accounts tree (overrides blueprint)
    # ------------------------------------------------------------------
    @app.route("/api/bot-settings/accounts-tree")
    def api_bot_settings_accounts_tree():
        conn = get_connection()
        devices = conn.execute(
            "SELECT DISTINCT device_serial FROM devices ORDER BY device_serial"
        ).fetchall()
        tree = []
        for dev in devices:
            serial = dev["device_serial"]
            accts = conn.execute(
                "SELECT username FROM accounts WHERE device_serial=? ORDER BY username",
                (serial,),
            ).fetchall()
            if accts:
                tree.append({
                    "device_serial": serial,
                    "accounts": [a["username"] for a in accts],
                })
        conn.close()
        return jsonify({"success": True, "devices": tree})

    # ------------------------------------------------------------------
    #  API: Bot Settings — read settings for account
    #  Returns: { success, settings (JSON blob), account_data (accounts row) }
    #  The frontend Timer tab reads account_data.starttime / endtime.
    #  Toggles from accounts table are merged into settings for the UI.
    # ------------------------------------------------------------------
    @app.route("/api/bot-settings/<device_serial>/<account>", methods=["GET"])
    def api_bot_settings_get(device_serial, account):
        conn = get_connection()
        acct = conn.execute(
            "SELECT * FROM accounts WHERE device_serial=? AND username=?",
            (device_serial, account),
        ).fetchone()
        if not acct:
            conn.close()
            return jsonify({"success": False, "error": "Account not found"}), 404

        acct_dict = row_to_dict(acct)
        account_id = acct_dict["id"]

        # Load settings JSON blob
        settings_row = conn.execute(
            "SELECT settings_json FROM account_settings WHERE account_id=?",
            (account_id,),
        ).fetchone()
        conn.close()

        settings = json.loads(settings_row["settings_json"]) if settings_row else {}

        # Merge master toggles from accounts table into settings
        # so the frontend [data-setting] bindings find them
        toggle_map = {
            "enable_follow": "follow_enabled",
            "enable_unfollow": "unfollow_enabled",
            "enable_likepost": "like_enabled",
            "enable_comment": "comment_enabled",
            "enable_story_viewer": "story_enabled",
            "enable_mute": "mute_enabled",
            "enable_switchmode": "switchmode",
        }
        for settings_key, db_col in toggle_map.items():
            val = acct_dict.get(db_col, "False")
            settings[settings_key] = val in ("True", "true", "On", "on", "1", True)

        # Build account_data in the format the frontend expects
        # (uses Onimator field names: starttime, endtime, randomaction, randomdelay, etc.)
        account_data = {
            "account": acct_dict["username"],
            "password": acct_dict.get("password", ""),
            "email": acct_dict.get("email", ""),
            "starttime": acct_dict.get("start_time", "0"),
            "endtime": acct_dict.get("end_time", "0"),
            "randomaction": acct_dict.get("random_action", "0,0"),
            "randomdelay": acct_dict.get("random_delay", "0,0"),
            "follow": acct_dict.get("follow_enabled", "False"),
            "unfollow": acct_dict.get("unfollow_enabled", "False"),
            "like": acct_dict.get("like_enabled", "False"),
            "mute": acct_dict.get("mute_enabled", "False"),
            "comment": acct_dict.get("comment_enabled", "False"),
            "story": acct_dict.get("story_enabled", "False"),
            "switchmode": acct_dict.get("switchmode", "False"),
            "followmethod": acct_dict.get("follow_action", "0"),
            "unfollowmethod": acct_dict.get("unfollow_action", "0"),
            "followdelay": acct_dict.get("follow_delay", "0"),
            "unfollowdelay": acct_dict.get("unfollow_delay", "0"),
            "likedelay": acct_dict.get("like_delay", "0"),
            "followlimitperday": acct_dict.get("follow_limit_perday", "0"),
            "unfollowlimitperday": acct_dict.get("unfollow_limit_perday", "0"),
            "likelimitperday": acct_dict.get("like_limit_perday", "0"),
            "unfollowdelayday": acct_dict.get("unfollow_delay_day", "3"),
        }

        return jsonify({
            "success": True,
            "device_serial": device_serial,
            "account": account,
            "settings": settings,
            "account_data": account_data,
        })

    # ------------------------------------------------------------------
    #  API: Bot Settings — save settings for account
    #  Accepts the full settings dict. Extracts toggles → accounts table,
    #  and writes everything to account_settings.settings_json.
    # ------------------------------------------------------------------
    @app.route("/api/bot-settings/<device_serial>/<account>", methods=["POST"])
    def api_bot_settings_save(device_serial, account):
        conn = get_connection()
        acct = conn.execute(
            "SELECT id FROM accounts WHERE device_serial=? AND username=?",
            (device_serial, account),
        ).fetchone()
        if not acct:
            conn.close()
            return jsonify({"success": False, "error": "Account not found"}), 404

        data = request.json or {}
        now = datetime.datetime.now().isoformat()
        account_id = acct["id"]

        # Extract master toggles → update accounts table
        toggle_map = {
            "enable_follow": "follow_enabled",
            "enable_unfollow": "unfollow_enabled",
            "enable_likepost": "like_enabled",
            "enable_comment": "comment_enabled",
            "enable_story_viewer": "story_enabled",
            "enable_mute": "mute_enabled",
            "enable_switchmode": "switchmode",
        }
        toggle_updates = []
        toggle_params = []
        for settings_key, db_col in toggle_map.items():
            if settings_key in data:
                val = data[settings_key]
                toggle_updates.append(f"{db_col}=?")
                toggle_params.append("True" if val in (True, "true", "True") else "False")

        if toggle_updates:
            toggle_updates.append("updated_at=?")
            toggle_params.append(now)
            toggle_params.append(account_id)
            conn.execute(
                f"UPDATE accounts SET {', '.join(toggle_updates)} WHERE id=?",
                toggle_params,
            )

        # Merge with existing settings JSON (deep merge)
        existing_row = conn.execute(
            "SELECT settings_json FROM account_settings WHERE account_id=?",
            (account_id,),
        ).fetchone()
        existing = json.loads(existing_row["settings_json"]) if existing_row else {}

        def deep_merge(base, updates):
            for k, v in updates.items():
                if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                    deep_merge(base[k], v)
                else:
                    base[k] = v
            return base

        merged = deep_merge(existing, data)
        settings_json = json.dumps(merged)

        conn.execute(
            """INSERT INTO account_settings (account_id, settings_json, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(account_id) DO UPDATE SET settings_json=?, updated_at=?""",
            (account_id, settings_json, now, settings_json, now),
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "settings": merged})

    # ------------------------------------------------------------------
    #  API: Bot Settings — bulk copy from source to targets
    # ------------------------------------------------------------------
    @app.route("/api/bot-settings/bulk", methods=["POST"])
    def api_bot_settings_bulk():
        data = request.json or {}
        source = data.get("source")
        targets = data.get("targets", [])
        if not source or not targets:
            return jsonify({"success": False, "error": "source and targets required"}), 400

        conn = get_connection()
        src_acct = conn.execute(
            "SELECT * FROM accounts WHERE device_serial=? AND username=?",
            (source["device"], source["account"]),
        ).fetchone()
        if not src_acct:
            conn.close()
            return jsonify({"success": False, "error": "Source account not found"}), 404

        src_settings_row = conn.execute(
            "SELECT settings_json FROM account_settings WHERE account_id=?",
            (src_acct["id"],),
        ).fetchone()
        src_settings = json.loads(src_settings_row["settings_json"]) if src_settings_row else {}

        now = datetime.datetime.now().isoformat()
        results = []
        for t in targets:
            tgt = conn.execute(
                "SELECT id FROM accounts WHERE device_serial=? AND username=?",
                (t["device"], t["account"]),
            ).fetchone()
            if not tgt:
                results.append({"device": t["device"], "account": t["account"],
                                "success": False, "error": "Not found"})
                continue

            # Copy toggle columns from source
            toggle_cols = [
                "follow_enabled", "unfollow_enabled", "mute_enabled",
                "like_enabled", "comment_enabled", "story_enabled", "switchmode",
            ]
            sets = [f"{c}=?" for c in toggle_cols]
            params = [src_acct[c] for c in toggle_cols]
            sets.append("updated_at=?")
            params.append(now)
            params.append(tgt["id"])
            conn.execute(f"UPDATE accounts SET {', '.join(sets)} WHERE id=?", params)

            # Copy settings JSON
            settings_json = json.dumps(src_settings)
            conn.execute(
                """INSERT INTO account_settings (account_id, settings_json, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(account_id) DO UPDATE SET settings_json=?, updated_at=?""",
                (tgt["id"], settings_json, now, settings_json, now),
            )
            results.append({"device": t["device"], "account": t["account"], "success": True})

        conn.commit()
        conn.close()
        ok = sum(1 for r in results if r["success"])
        return jsonify({
            "success": True,
            "message": f"Copied settings to {ok}/{len(targets)} accounts",
            "results": results,
        })

    # ------------------------------------------------------------------
    #  API: Bot Settings — lists (sources, whitelist, etc.)
    # ------------------------------------------------------------------
    @app.route("/api/bot-settings/<device_serial>/<account>/lists/<list_type>", methods=["GET"])
    def api_bot_settings_list_get(device_serial, account, list_type):
        conn = get_connection()
        acct = conn.execute(
            "SELECT id FROM accounts WHERE device_serial=? AND username=?",
            (device_serial, account),
        ).fetchone()
        if not acct:
            conn.close()
            return jsonify({"success": False, "error": "Account not found"}), 404
        rows = conn.execute(
            "SELECT value FROM account_sources WHERE account_id=? AND source_type=?",
            (acct["id"], list_type),
        ).fetchall()
        conn.close()
        items = [r["value"] for r in rows]
        return jsonify({"success": True, "list_type": list_type, "items": items, "count": len(items)})

    @app.route("/api/bot-settings/<device_serial>/<account>/lists/<list_type>", methods=["POST"])
    def api_bot_settings_list_save(device_serial, account, list_type):
        conn = get_connection()
        acct = conn.execute(
            "SELECT id FROM accounts WHERE device_serial=? AND username=?",
            (device_serial, account),
        ).fetchone()
        if not acct:
            conn.close()
            return jsonify({"success": False, "error": "Account not found"}), 404
        data = request.json or {}
        items = data.get("items", [])
        now = datetime.datetime.now().isoformat()
        # Replace all entries for this type
        conn.execute(
            "DELETE FROM account_sources WHERE account_id=? AND source_type=?",
            (acct["id"], list_type),
        )
        for item in items:
            if item.strip():
                conn.execute(
                    "INSERT INTO account_sources (account_id, source_type, value, created_at) VALUES (?,?,?,?)",
                    (acct["id"], list_type, item.strip(), now),
                )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "count": len(items)})

    # ------------------------------------------------------------------
    #  API: Bot Settings — prompts (GPT prompts, etc.)
    # ------------------------------------------------------------------
    @app.route("/api/bot-settings/<device_serial>/<account>/prompts/<prompt_type>", methods=["GET"])
    def api_bot_settings_prompt_get(device_serial, account, prompt_type):
        conn = get_connection()
        acct = conn.execute(
            "SELECT id FROM accounts WHERE device_serial=? AND username=?",
            (device_serial, account),
        ).fetchone()
        if not acct:
            conn.close()
            return jsonify({"success": False, "error": "Account not found"}), 404
        row = conn.execute(
            "SELECT content FROM account_text_configs WHERE account_id=? AND config_type=?",
            (acct["id"], prompt_type),
        ).fetchone()
        conn.close()
        return jsonify({"success": True, "prompt_type": prompt_type, "content": row["content"] if row else ""})

    @app.route("/api/bot-settings/<device_serial>/<account>/prompts/<prompt_type>", methods=["POST"])
    def api_bot_settings_prompt_save(device_serial, account, prompt_type):
        conn = get_connection()
        acct = conn.execute(
            "SELECT id FROM accounts WHERE device_serial=? AND username=?",
            (device_serial, account),
        ).fetchone()
        if not acct:
            conn.close()
            return jsonify({"success": False, "error": "Account not found"}), 404
        data = request.json or {}
        content = data.get("content", "")
        now = datetime.datetime.now().isoformat()
        conn.execute(
            """INSERT INTO account_text_configs (account_id, config_type, content, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(account_id, config_type) DO UPDATE SET content=?, updated_at=?""",
            (acct["id"], prompt_type, content, now, content, now),
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True})

    # ------------------------------------------------------------------
    #  API: Automation Logs — real-time log panel
    # ------------------------------------------------------------------
    @app.route("/api/automation/logs")
    def api_automation_logs():
        conn = get_connection()
        device = request.args.get("device")
        username = request.args.get("username")
        level = request.args.get("level")
        limit = request.args.get("limit", 100, type=int)
        offset = request.args.get("offset", 0, type=int)

        q = "SELECT * FROM bot_logs WHERE 1=1"
        params = []
        if device:
            q += " AND device_serial=?"
            params.append(device)
        if username:
            q += " AND username=?"
            params.append(username)
        if level:
            q += " AND level=?"
            params.append(level.upper())
        q += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(q, params).fetchall()
        total = conn.execute("SELECT COUNT(*) as c FROM bot_logs").fetchone()["c"]
        conn.close()

        logs = [row_to_dict(r) for r in rows]
        return jsonify({"success": True, "logs": logs, "total": total})

    @app.route("/api/automation/logs", methods=["POST"])
    def api_automation_logs_add():
        """Add a log entry programmatically."""
        data = request.json or {}
        conn = get_connection()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """INSERT INTO bot_logs (timestamp, level, device_serial, username, action_type, message, success, error_detail, module, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                now,
                data.get("level", "INFO"),
                data.get("device_serial"),
                data.get("username"),
                data.get("action_type"),
                data.get("message", ""),
                data.get("success"),
                data.get("error_detail"),
                data.get("module", "api"),
                now,
            ),
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True})

    # ------------------------------------------------------------------
    #  API: Sources — accounts list  (overrides blueprint)
    # ------------------------------------------------------------------
    @app.route("/api/sources/accounts")
    def api_sources_accounts():
        conn = get_connection()
        devices = conn.execute("SELECT device_serial FROM devices ORDER BY device_serial").fetchall()
        result = []
        for dev in devices:
            serial = dev["device_serial"]
            accts = conn.execute(
                "SELECT username FROM accounts WHERE device_serial=? ORDER BY username",
                (serial,),
            ).fetchall()
            for a in accts:
                result.append({
                    "deviceid": serial,
                    "account": a["username"],
                })
        conn.close()
        return jsonify(result)

    # ------------------------------------------------------------------
    #  API: Media Library
    # ------------------------------------------------------------------
    @app.route("/api/media/items")
    def api_media_items():
        conn = get_connection()
        rows = conn.execute("SELECT * FROM media ORDER BY upload_date DESC").fetchall()
        items = [row_to_dict(r) for r in rows]
        conn.close()
        return jsonify(items)

    # ------------------------------------------------------------------
    #  API: Scheduled Posts
    # ------------------------------------------------------------------
    @app.route("/api/scheduled-posts")
    def api_scheduled_posts():
        conn = get_connection()
        rows = conn.execute("SELECT * FROM scheduled_posts ORDER BY scheduled_time").fetchall()
        posts = [row_to_dict(r) for r in rows]
        conn.close()
        return jsonify(posts)

    # ------------------------------------------------------------------
    #  API: Account Inventory
    # ------------------------------------------------------------------
    @app.route("/api/account-inventory")
    def api_account_inventory():
        conn = get_connection()
        rows = conn.execute("SELECT * FROM account_inventory ORDER BY id").fetchall()
        items = [row_to_dict(r) for r in rows]
        conn.close()
        return jsonify(items)

    # ------------------------------------------------------------------
    #  API: Account update (for dashboard JS)
    # ------------------------------------------------------------------
    @app.route("/api/account/update/<deviceid>/<account>", methods=["POST"])
    def api_account_update(deviceid, account):
        conn = get_connection()
        data = request.json or request.form.to_dict()
        now = datetime.datetime.now().isoformat()

        # Map fields from frontend to DB columns
        updates = []
        params = []
        field_map = {
            "follow": "follow_enabled",
            "unfollow": "unfollow_enabled",
            "like": "like_enabled",
            "comment": "comment_enabled",
            "story": "story_enabled",
            "mute": "mute_enabled",
            "starttime": "start_time",
            "endtime": "end_time",
            "followaction": "follow_action",
            "unfollowaction": "unfollow_action",
            "randomaction": "random_action",
            "randomdelay": "random_delay",
            "followdelay": "follow_delay",
            "unfollowdelay": "unfollow_delay",
            "likedelay": "like_delay",
            "followlimitperday": "follow_limit_perday",
            "unfollowlimitperday": "unfollow_limit_perday",
            "likelimitperday": "like_limit_perday",
            "unfollowdelayday": "unfollow_delay_day",
        }
        for frontend_key, db_col in field_map.items():
            if frontend_key in data:
                updates.append(f"{db_col}=?")
                params.append(str(data[frontend_key]))
        # Also accept direct DB column names
        for db_col in field_map.values():
            if db_col in data and f"{db_col}=?" not in " ".join(updates):
                updates.append(f"{db_col}=?")
                params.append(str(data[db_col]))

        if updates:
            updates.append("updated_at=?")
            params.append(now)
            params.extend([deviceid, account])
            conn.execute(
                f"UPDATE accounts SET {', '.join(updates)} WHERE device_serial=? AND username=?",
                params,
            )
            conn.commit()

        conn.close()
        return jsonify({"success": True})

    # ------------------------------------------------------------------
    #  API: Bulk update accounts
    # ------------------------------------------------------------------
    @app.route("/api/bulk_update", methods=["POST"])
    def api_bulk_update():
        data = request.json
        if not data:
            return jsonify({"error": "No data"}), 400
        conn = get_connection()
        now = datetime.datetime.now().isoformat()
        updated = 0
        accounts = data.get("accounts", [])
        settings = data.get("settings", {})
        for acct in accounts:
            did = acct.get("deviceid", "")
            uname = acct.get("account", "")
            if not did or not uname:
                continue
            sets = []
            params = []
            for key, val in settings.items():
                col = key
                sets.append(f"{col}=?")
                params.append(str(val))
            if sets:
                sets.append("updated_at=?")
                params.append(now)
                params.extend([did, uname])
                conn.execute(
                    f"UPDATE accounts SET {', '.join(sets)} WHERE device_serial=? AND username=?",
                    params,
                )
                updated += 1
        conn.commit()
        conn.close()
        return jsonify({"success": True, "updated": updated})

    # ------------------------------------------------------------------
    #  Register automation API blueprint
    # ------------------------------------------------------------------
    try:
        from automation.api import automation_bp
        app.register_blueprint(automation_bp)
        print("  [OK] Blueprint: automation_bp")
    except Exception as e:
        print(f"  [!] Blueprint automation_bp skipped: {e}")

    # ------------------------------------------------------------------
    #  Register dashboard blueprints
    # ------------------------------------------------------------------
    _register_blueprints(app)

    # ------------------------------------------------------------------
    #  Page routes (templates)
    # ------------------------------------------------------------------
    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/accounts")
    def accounts_page():
        return render_template("accounts.html")

    @app.route("/scheduled-posts")
    def scheduled_posts_page():
        return render_template("scheduled_posts.html")

    @app.route("/media-library")
    def media_library_page():
        return render_template("media_library.html")

    @app.route("/account-inventory")
    def account_inventory_page():
        return render_template("account_inventory.html")

    @app.route("/profile-automation")
    def profile_automation_page():
        return render_template("profile_automation.html")

    @app.route("/login-automation")
    def login_automation_page():
        return render_template("login_automation.html")

    @app.route("/bot-manager")
    def bot_manager_page():
        return render_template("bot_manager.html")

    @app.route("/bot-settings")
    def bot_settings_page():
        return render_template("bot_settings.html")

    @app.route("/caption-templates")
    def caption_templates_page():
        return render_template("caption_templates.html")

    @app.route("/manage_sources")
    def manage_sources_page():
        return render_template("manage_sources_new.html")

    @app.route("/bulk_operations")
    def bulk_operations_page():
        return render_template("bulk_operations.html")

    @app.route("/import-accounts")
    def import_accounts_page():
        return render_template("import_accounts.html")

    @app.route("/jap-settings")
    def jap_settings_page():
        return render_template("jap_settings.html")

    return app


def _register_blueprints(app):
    """Safely register dashboard blueprints, skipping any that fail to import."""
    blueprints = [
        ("settings_routes", "settings_bp", None),
        ("login_automation_routes", "login_bp", None),
        ("bot_manager_routes", "bot_manager_bp", None),
        ("bot_settings_routes", "bot_settings_bp", None),
        ("bulk_import_routes", "bulk_import_bp", None),
        ("job_orders_routes", "job_orders_bp", "/job-orders"),
        ("manage_sources", "sources_bp", None),
        ("caption_templates_routes", "caption_templates_bp", None),
        ("bot_launcher_routes", "bot_launcher_bp", None),
    ]

    for module_name, bp_name, url_prefix in blueprints:
        try:
            mod = __import__(module_name)
            bp = getattr(mod, bp_name)
            if url_prefix:
                app.register_blueprint(bp, url_prefix=url_prefix)
            else:
                app.register_blueprint(bp)
            print(f"  [OK] Blueprint: {bp_name}")
        except Exception as e:
            print(f"  [!] Blueprint {bp_name} skipped: {e}")


# ---------------------------------------------------------------------------
#  Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phone Farm Dashboard")
    parser.add_argument("--port", type=int, default=5060, help="Port (default: 5060)")
    parser.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    parser.add_argument("--init-db", action="store_true", help="Initialize DB and exit")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    if args.init_db:
        path = init_db()
        print(f"Database initialized at {path}")
        conn = get_connection()
        tables = [r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]
        print(f"Tables ({len(tables)}): {', '.join(tables)}")
        conn.close()
        sys.exit(0)

    app = create_app()
    print(f"\n{'='*50}")
    print(f"  Phone Farm Dashboard")
    print(f"  http://localhost:{args.port}")
    print(f"  Health: http://localhost:{args.port}/api/health")
    print(f"{'='*50}\n")
    app.run(host=args.host, port=args.port, debug=args.debug)
