"""feature_flags.py — runtime feature gating.

DEV DEFAULT (this committed copy) = everything ON, so running from source/master
has the full toolset. The CLIENT distribution gets a regenerated copy with the
flags from build_config.json baked in (deploy_release.py rewrites this during the
build, then restores this dev default afterwards so source stays all-on).
"""

FEATURES = {
    "account_factory": True,
    "ai_executor": True,
    "assistant_chat": True,
    "cloudphone": True,
    "content_schedule": True,
    "login_automation_v2": True,
    "mcp_server": True,
    "mother_dashboard": True,
    "profile_automation": True,
}


def is_enabled(name: str) -> bool:
    return bool(FEATURES.get(name, True))
