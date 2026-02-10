"""
Source Manager - Unified source file handling
===============================================
Manages per-account .txt source files (Onimator-compatible format).
Supports: follow, share-to-story, DM, story viewer, likes.

Source priority:
1. Action-specific .txt file in account folder
2. DB sources via get_account_sources()
3. Returns empty list if neither exists
"""

import os
import logging
from typing import List, Optional, Dict

log = logging.getLogger(__name__)

# Base directory for account folders (Onimator layout)
# Each device has: BASE_DIR/{device_id}/{account_name}/
# The BASE_DIR is set from settings or auto-detected
_BASE_DIR = None


def get_base_dir():
    """Get the base directory for device/account folders."""
    global _BASE_DIR
    if _BASE_DIR is None:
        # Default: phone-farm parent directory (same level as Onimator)
        _BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return _BASE_DIR


def set_base_dir(path: str):
    """Override the base directory."""
    global _BASE_DIR
    _BASE_DIR = path


# ---------------------------------------------------------------------------
# Action type → filename mapping
# ---------------------------------------------------------------------------
SOURCE_FILE_MAP = {
    # Action type key → filename
    # These match the dashboard manage_sources.py and Onimator conventions
    'follow': 'sources.txt',
    'sources': 'sources.txt',  # alias
    'follow_likers': 'follow-likers-sources.txt',
    'follow_specific': 'follow-specific-sources.txt',
    'share_to_story': 'shared_post_username_source.txt',  # matches dashboard Share Sources tab
    'share': 'shared_post_username_source.txt',            # alias — dashboard sends source_type='share'
    'shared_post': 'shared_post_username_source.txt',      # alias
    'dm': 'directmessagespecificusersources.txt',
    'dm_specific': 'directmessagespecificusersources.txt',
    'story_viewer_followers': 'storyviewer-user-followers-sources.txt',
    'story_viewer_likers': 'storyviewer-user-likers-sources.txt',
    'like_specific': 'like_posts_specific.txt',
    'view_specific': 'view_specific_user.txt',
}

# Legacy/alternative filenames to check as fallbacks
SOURCE_FILE_FALLBACKS = {
    'share_to_story': ['share-to-story-sources.txt'],
    'share': ['share-to-story-sources.txt'],
}

# Human-readable labels for the dashboard
# NOTE: The dashboard manage_sources_new.html already has tabs for
# 'follow' (sources.txt) and 'share' (shared_post_username_source.txt).
# Do NOT add new tabs — use the existing tab system.
SOURCE_TYPE_LABELS = {
    'follow': 'Follow Sources',
    'follow_likers': 'Follow Likers Sources',
    'follow_specific': 'Follow Specific Sources',
    'share_to_story': 'Share to Story Sources',
    'share': 'Share Sources',
    'dm': 'DM Sources',
    'story_viewer_followers': 'Story Viewer (Followers) Sources',
    'story_viewer_likers': 'Story Viewer (Likers) Sources',
    'like_specific': 'Like Specific Posts',
    'view_specific': 'View Specific Users',
}


def get_source_filename(action_type: str) -> str:
    """Get the .txt filename for a given action type."""
    return SOURCE_FILE_MAP.get(action_type, f'{action_type}-sources.txt')


def get_source_filepath(device_id: str, account_name: str, action_type: str) -> str:
    """Get the full path to a source .txt file."""
    filename = get_source_filename(action_type)
    return os.path.join(get_base_dir(), device_id, account_name, filename)


# ---------------------------------------------------------------------------
# Read sources
# ---------------------------------------------------------------------------

def read_sources_txt(device_id: str, account_name: str, action_type: str) -> Optional[List[str]]:
    """
    Read source usernames from a .txt file.
    Returns list of usernames, or None if file doesn't exist.
    """
    filepath = get_source_filepath(device_id, account_name, action_type)
    
    if not os.path.exists(filepath):
        return None
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse: one username per line, strip whitespace, skip empty/comments
        usernames = []
        for line in content.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                usernames.append(line)
        
        log.debug("Read %d sources from %s", len(usernames), filepath)
        return usernames
    
    except Exception as e:
        log.error("Failed to read sources from %s: %s", filepath, e)
        return None


def get_sources(device_id: str, account_name: str, action_type: str,
                account_id: int = None, db_source_type: str = None) -> List[str]:
    """
    Get sources with fallback: .txt file → DB → empty list.
    
    Args:
        device_id: Device serial in folder format (e.g., '10.1.11.4_5555')
        account_name: Account username
        action_type: Action type key (e.g., 'share_to_story', 'follow')
        account_id: DB account ID for fallback
        db_source_type: DB source_type for fallback (defaults to 'sources')
    
    Returns:
        List of source usernames
    """
    # 1. Try primary .txt file first
    txt_sources = read_sources_txt(device_id, account_name, action_type)
    if txt_sources is not None:
        log.info("[%s/%s] Using %d sources from %s",
                 device_id, account_name, len(txt_sources),
                 get_source_filename(action_type))
        return txt_sources
    
    # 2. Try fallback filenames (e.g. share-to-story-sources.txt for share actions)
    fallbacks = SOURCE_FILE_FALLBACKS.get(action_type, [])
    for fallback_filename in fallbacks:
        fallback_path = os.path.join(get_base_dir(), device_id, account_name, fallback_filename)
        if os.path.exists(fallback_path):
            try:
                with open(fallback_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                usernames = [l.strip() for l in content.split('\n') if l.strip() and not l.startswith('#')]
                if usernames:
                    log.info("[%s/%s] Using %d sources from fallback %s",
                             device_id, account_name, len(usernames), fallback_filename)
                    return usernames
            except Exception:
                pass
    
    # 3. Fall back to DB
    if account_id is not None:
        try:
            from automation.actions.helpers import get_account_sources
            src_type = db_source_type or 'sources'
            db_sources = get_account_sources(account_id, src_type)
            if db_sources:
                log.info("[%s/%s] Using %d sources from DB (type=%s)",
                         device_id, account_name, len(db_sources), src_type)
                return db_sources
        except Exception as e:
            log.error("DB source fallback failed: %s", e)
    
    log.warning("[%s/%s] No sources found for action '%s'",
                device_id, account_name, action_type)
    return []


# ---------------------------------------------------------------------------
# Write sources
# ---------------------------------------------------------------------------

def write_sources_txt(device_id: str, account_name: str, action_type: str,
                      usernames: List[str]) -> bool:
    """
    Write source usernames to a .txt file.
    Creates directory if needed.
    """
    filepath = get_source_filepath(device_id, account_name, action_type)
    
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # Clean and deduplicate
        clean = []
        seen = set()
        for u in usernames:
            u = u.strip()
            if u and u.lower() not in seen:
                clean.append(u)
                seen.add(u.lower())
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(clean))
        
        log.info("Wrote %d sources to %s", len(clean), filepath)
        return True
    
    except Exception as e:
        log.error("Failed to write sources to %s: %s", filepath, e)
        return False


def append_sources_txt(device_id: str, account_name: str, action_type: str,
                       usernames: List[str]) -> bool:
    """Append usernames to existing source file (deduplicates)."""
    existing = read_sources_txt(device_id, account_name, action_type) or []
    combined = existing + usernames
    return write_sources_txt(device_id, account_name, action_type, combined)


def remove_sources_txt(device_id: str, account_name: str, action_type: str,
                       usernames: List[str]) -> bool:
    """Remove specific usernames from source file."""
    existing = read_sources_txt(device_id, account_name, action_type) or []
    remove_set = {u.strip().lower() for u in usernames}
    filtered = [u for u in existing if u.lower() not in remove_set]
    return write_sources_txt(device_id, account_name, action_type, filtered)


# ---------------------------------------------------------------------------
# Source info (for dashboard)
# ---------------------------------------------------------------------------

def get_source_info(device_id: str, account_name: str, action_type: str) -> Dict:
    """Get info about a source file for the dashboard."""
    filepath = get_source_filepath(device_id, account_name, action_type)
    exists = os.path.exists(filepath)
    
    info = {
        'device_id': device_id,
        'account_name': account_name,
        'action_type': action_type,
        'filename': get_source_filename(action_type),
        'filepath': filepath,
        'exists': exists,
        'count': 0,
        'content': '',
    }
    
    if exists:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            info['content'] = content
            info['count'] = len([l for l in content.split('\n') if l.strip()])
        except Exception:
            pass
    
    return info


def list_all_source_types() -> List[Dict]:
    """List all available source types with labels."""
    return [
        {'key': k, 'label': v, 'filename': get_source_filename(k)}
        for k, v in SOURCE_TYPE_LABELS.items()
    ]
