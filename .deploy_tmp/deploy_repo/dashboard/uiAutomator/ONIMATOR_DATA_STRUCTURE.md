# Onimator Data Structure Manual

A comprehensive reference for all Onimator database structures, file locations, and field mappings.

---

## Table of Contents

1. [Directory Structure](#directory-structure)
2. [Database Files Overview](#database-files-overview)
3. [devices.db](#devicesdb)
4. [accounts.db](#accountsdb)
5. [settings.db](#settingsdb)
6. [stats.db](#statsdb)
7. [Other Database Files](#other-database-files)
8. [Text Configuration Files](#text-configuration-files)
9. [Field Mappings (UI to Database)](#field-mappings-ui-to-database)
10. [Data Type Conventions](#data-type-conventions)

---

## Directory Structure

```
full_igbot_14.2.4/
├── devices.db                          # Master device registry
├── {device_serial}/                    # One folder per device (e.g., "10.1.10.244_5555")
│   ├── accounts.db                     # Device's account registry + master toggles
│   └── {account_username}/             # One folder per account
│       ├── settings.db                 # Detailed bot settings (JSON)
│       ├── stats.db                    # Statistics and metrics
│       ├── data.db                     # Followed/liked users tracking
│       ├── comments.db                 # Comment history
│       ├── likes.db                    # Like history
│       ├── directmessage.db            # DM conversations
│       ├── sent_message.db             # Sent message log
│       ├── shared_post.db              # Shared posts log
│       ├── storyviewer.db              # Story view history
│       ├── likeexchange.db             # Like exchange data
│       ├── scheduled_post.db           # Scheduled posts
│       ├── 2factorauthcodes.db         # 2FA backup codes
│       ├── filtersettings.db           # Filter configurations
│       ├── sources.txt                 # Source accounts for follow/like
│       ├── whitelist.txt               # Unfollow whitelist
│       ├── gpt_prompt.txt              # General GPT prompt
│       ├── comment_gpt_prompt.txt      # Comment-specific GPT prompt
│       └── ... (more text files)
└── the-livehouse-dashboard/            # Dashboard application
```

---

## Database Files Overview

| Database | Location | Purpose |
|----------|----------|---------|
| `devices.db` | Root folder | Master list of all connected devices |
| `accounts.db` | `{device}/` | Account registry + master ON/OFF toggles |
| `settings.db` | `{device}/{account}/` | Detailed JSON settings for bot behavior |
| `stats.db` | `{device}/{account}/` | Historical statistics and metrics |
| `data.db` | `{device}/{account}/` | Tracks followed/liked users |

---

## devices.db

**Location:** `full_igbot_14.2.4/devices.db`

**Purpose:** Master registry of all Android devices connected to the system.

### Table: `devices`

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `deviceid` | TEXT | Device serial/IP:port | `"10.1.10.244_5555"` |
| `devicename` | TEXT | Friendly device name | `"Pixel 4a"` |
| `status` | TEXT | Connection status | `"connected"`, `"disconnected"` |

### SQL Example:
```sql
SELECT deviceid, devicename, status FROM devices;
```

---

## accounts.db

**Location:** `{device_serial}/accounts.db`

**Purpose:**
1. Registry of all Instagram accounts on this device
2. **Master ON/OFF toggles** for each automation feature
3. Account credentials and status

### Table: `accounts`

| Column | Type | Values | Description |
|--------|------|--------|-------------|
| `starttime` | TEXT | `'0'`-`'23'` | Automation start hour |
| `endtime` | TEXT | `'0'`-`'23'` | Automation end hour |
| `account` | TEXT | username | Instagram username (PRIMARY KEY) |
| `password` | TEXT | encrypted | Account password |
| `follow` | TEXT | `'True'` / `'False'` | Master toggle: Follow automation |
| `unfollow` | TEXT | `'True'` / `'False'` | Master toggle: Unfollow automation |
| `mute` | TEXT | `'True'` / `'False'` | Master toggle: Mute feature |
| `like` | TEXT | `'deprecated'` | (Deprecated - moved to settings.db) |
| `followmethod` | TEXT | `'deprecated'` | (Deprecated) |
| `unfollowmethod` | TEXT | `'deprecated'` | (Deprecated) |
| `limitperday` | TEXT | `'deprecated'` | (Deprecated) |
| `followaction` | TEXT | `'min,max'` | Follow actions per operation |
| `unfollowaction` | TEXT | `'min,max'` | Unfollow actions per operation |
| `likeaction` | TEXT | `'deprecated'` | (Deprecated) |
| `randomaction` | TEXT | `'min,max'` | Random action delays |
| `randomdelay` | TEXT | `'min,max'` | Random delays |
| `switchmode` | TEXT | `'True'` / `'False'` | Account switching mode |
| `followdelay` | TEXT | `'min,max'` | Delay after follow |
| `unfollowdelay` | TEXT | `'min,max'` | Delay after unfollow |
| `likedelay` | TEXT | `'min,max'` | Delay after like |
| `followlimitperday` | TEXT | `'deprecated'` | (Deprecated) |
| `unfollowlimitperday` | TEXT | number or `'None'` | Unfollow daily limit |
| `likelimitperday` | TEXT | number or `'None'` | Like daily limit |
| `unfollowdelayday` | TEXT | number | Days before unfollowing |
| `mutemethod` | TEXT | `'random'` | Mute method |
| `email` | TEXT | email | Associated email |

### Important Notes:
- **Toggle values are STRINGS**: `'True'` or `'False'` (capital T/F)
- **NOT** `'On'`/`'Off'` as originally thought
- Many columns are `'deprecated'` - settings moved to settings.db JSON
- `like`, `comment`, `story` toggles are now controlled via settings.db, not accounts.db
- Only `follow`, `unfollow`, `mute`, `switchmode` are active toggles in accounts.db

### SQL Examples:
```sql
-- Get all accounts with their toggles
SELECT account, follow, unfollow, `like`, comment, story
FROM accounts;

-- Update follow toggle
UPDATE accounts SET follow = 'On' WHERE account = 'myusername';

-- Note: 'like' is a reserved word, use backticks
SELECT `like` FROM accounts WHERE account = 'myusername';
```

---

## settings.db

**Location:** `{device_serial}/{account_username}/settings.db`

**Purpose:** Stores detailed configuration for all bot behaviors as a single JSON string.

### Table: `accountsettings`

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Always 1 (single row) |
| `settings` | TEXT | JSON string containing all settings |

### JSON Structure Overview:

```json
{
    // ===== LIKE SETTINGS =====
    "enable_likepost": true,
    "likepost_method": {
        "enable_likepost_sources_followers": true,
        "enable_likepost_via_keywords": false,
        "enable_likepost_specific_accounts": false
    },
    "min_likepost_action": "10",
    "max_likepost_action": "20",
    "like_limit_perday": "50",
    "enable_auto_increment_like_limit_perday": false,
    "auto_increment_like_limit_perday_increase": "5",
    "auto_increment_like_limit_perday_increase_limit": "100",
    "like_enable_filters": false,
    "enable_dont_like_if_user_followed": false,
    "enable_dont_like_sametag_accounts": false,
    "like_story_after_liking_post": false,
    "min_post_to_like": "1",
    "max_post_to_like": "3",

    // ===== COMMENT SETTINGS =====
    "enable_comment": true,
    "comment_method": {
        "comment_using_keyword_search": false
    },
    "comment_text": "[AI]",
    "min_comment": "5",
    "max_comment": "10",
    "comment_min_delay": "5",
    "comment_max_delay": "15",
    "comment_limit_perday": "25",
    "enable_dont_comment_sametag_accounts": false,

    // ===== STORY SETTINGS =====
    "enable_story_viewer": true,
    "view_method": {
        "view_followers": true,
        "view_likers": false,
        "view_specific_user": false,
        "view_specific_user_highlight": false
    },
    "story_viewer_min": "10",
    "story_viewer_max": "20",
    "story_viewer_daily_limit": "800",
    "story_view_peraccount_view": "3",
    "like_story_after_viewing": false,
    "story_like_daily_limit": "200",
    "min_story_like_peraccount_view": "1",
    "max_story_like_peraccount_view": "3",
    "dont_view_same_account_twice": true,
    "view_highlight_if_no_story_viceversa": false,

    // ===== DM SETTINGS =====
    "enable_directmessage": true,
    "directmessage_method": {
        "directmessage_new_followers": true,
        "directmessage_specificuser": false,
        "directmessage_reply": false,
        "enable_dm_crm": false
    },
    "directmessage_min": "3",
    "directmessage_max": "5",
    "directmessage_min_delay": "10",
    "directmessage_max_delay": "30",
    "directmessage_daily_limit": "20",
    "message_check_delay": "60",
    "enable_send_message_every_new_line": false,
    "enable_openai_dm": true,
    "enable_cupidai_dm": false,
    "enable_openai_assistant": false,
    "openai_assistant_id": "",

    // ===== FOLLOW SETTINGS =====
    "follow_method": {
        "follow_followers": true,
        "follow_likers": false,
        "follow_specific_sources": false,
        "follow_using_word_search": false
    },
    "default_action_limit_perday": "30",
    "enable_auto_increment_follow_limit_perday": false,
    "follow_timer_min_hour": "0",
    "follow_timer_max_hour": "24",
    "follow_is_weekdays": false,

    // ===== UNFOLLOW SETTINGS =====
    "unfollow_method": {
        "unfollow_using_profile": true,
        "unfollow_using_following_list": false,
        "unfollow_specific_accounts": false
    },
    "unfollow_limit_perday": "30",
    "enable_auto_increment_unfollow_limit_perday": false,
    "unfollow_delay_day": "3",

    // ===== FILTER SETTINGS =====
    "enable_filters": false,
    "filters": {
        "min_followers": "0",
        "max_followers": "999999",
        "min_following": "0",
        "max_following": "999999",
        "min_posts": "0",
        "max_posts": "999999",
        "must_have_profile_pic": false,
        "must_be_business": false,
        "must_be_verified": false,
        "must_be_public": true,
        "skip_if_bio_contains": "",
        "must_bio_contain": ""
    },

    // ===== REELS SETTINGS =====
    "enable_watch_reels": false,
    "min_reels_to_watch": "10",
    "max_reels_to_watch": "20",
    "watch_reels_duration_min": "5",
    "watch_reels_duration_max": "15",
    "watch_reels_daily_limit": "100",
    "enable_save_reels_while_watching": false,
    "save_reels_percent": "10",
    "enable_like_reels_while_watching": false,
    "like_reels_percent": "20",
    "enable_comment_reels_while_watching": false,
    "comment_reels_percent": "5",

    // ===== SHARE TO STORY SETTINGS =====
    "enable_shared_post": false,
    "post_type_to_share": "post",          // "post", "reel", or "both"
    "shared_post_limit_perday": "5",
    "enable_add_mention_shared_post": false,
    "enable_add_hashtag_shared_post": false,
    "enable_add_sticker_shared_post": false,
    "enable_add_music_shared_post": false,
    "enable_repost_shared_post": false,
    "repost_limit_perday": "3",

    // ===== HUMAN BEHAVIOUR EMULATION (HBE) SETTINGS =====
    "enable_human_behaviour_emulation": false,
    "enable_viewhomefeedstory": false,
    "viewhomefeedstory_min": "3",
    "viewhomefeedstory_max": "10",
    "viewhomefeedstory_daily_limit": "50",
    "enable_scrollhomefeed": false,
    "scrollhomefeed_min": "5",
    "scrollhomefeed_max": "15",
    "scrollhomefeed_duration_min": "30",
    "scrollhomefeed_duration_max": "120",
    "enable_scrollexplorepage": false,
    "scrollexplorepage_min": "5",
    "scrollexplorepage_max": "15",
    "scrollexplorepage_duration_min": "30",
    "scrollexplorepage_duration_max": "120"
}
```

### SQL Examples:
```sql
-- Read settings JSON
SELECT settings FROM accountsettings WHERE id = 1;

-- Update settings (must write entire JSON)
UPDATE accountsettings SET settings = '{"enable_likepost": true, ...}' WHERE id = 1;
```

### Important Notes:
- **Numeric values are stored as STRINGS** (e.g., `"50"` not `50`)
- **Booleans are actual booleans** in JSON (`true`/`false`)
- Nested objects for method selections (e.g., `likepost_method`)
- Single row with `id = 1`

---

## stats.db

**Location:** `{device_serial}/{account_username}/stats.db`

**Purpose:** Historical tracking of automation activities and metrics.

### Table: `stats`

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Auto-increment primary key |
| `account` | TEXT | Instagram username |
| `date` | TEXT | Date (YYYY-MM-DD) |
| `follows` | INTEGER | Follows performed that day |
| `unfollows` | INTEGER | Unfollows performed that day |
| `likes` | INTEGER | Likes given that day |
| `comments` | INTEGER | Comments made that day |
| `stories_viewed` | INTEGER | Stories viewed that day |
| `dms_sent` | INTEGER | DMs sent that day |
| `followers_gained` | INTEGER | Net followers change |

### SQL Example:
```sql
-- Get stats for last 7 days
SELECT date, follows, unfollows, likes, comments
FROM stats
WHERE account = 'myusername'
ORDER BY date DESC
LIMIT 7;
```

---

## Other Database Files

### data.db
**Purpose:** Tracks users that have been interacted with (to avoid duplicates).

| Table | Purpose |
|-------|---------|
| `followed_users` | Users that have been followed |
| `liked_users` | Users whose posts were liked |
| `unfollowed_users` | Users that have been unfollowed |

### comments.db
**Purpose:** Log of comments made.

### likes.db
**Purpose:** Log of posts liked.

### directmessage.db
**Purpose:** DM conversation history.

### sent_message.db
**Purpose:** Outgoing message log.

### storyviewer.db
**Purpose:** Story view history.

---

## Text Configuration Files

Located in `{device_serial}/{account_username}/`

| Filename | Purpose | Format |
|----------|---------|--------|
| `sources.txt` | Source accounts for follow/like | One username per line |
| `whitelist.txt` | Don't unfollow these accounts | One username per line |
| `like_post_likers_using_keyword_search.txt` | Keywords for like targeting | One keyword per line |
| `comment_using_keyword_search.txt` | Keywords for comment targeting | One keyword per line |
| `view_specific_user.txt` | Specific users for story viewing | One username per line |
| `view_specific_user_highlight.txt` | Specific users for highlight viewing | One username per line |
| `directmessagespecificuser.txt` | Specific users to DM | One username per line |
| `follow-specific-sources.txt` | Specific sources for following | One username per line |
| `follow-likers-sources.txt` | Sources for follow-likers | One username per line |
| `follow_using_word_search.txt` | Keywords for follow targeting | One keyword per line |
| `unfollow-specific-accounts.txt` | Specific accounts to unfollow | One username per line |
| `storyviewer-user-followers-sources.txt` | Sources for story viewer (followers) | One username per line |
| `storyviewer-user-likers-sources.txt` | Sources for story viewer (likers) | One username per line |
| `name_must_include.txt` | Filter: name must include | One term per line |
| `name_must_not_include.txt` | Filter: name must not include | One term per line |
| `close-friends.txt` | Close friends list | One username per line |
| `watch_reels_sources.txt` | Reel watching sources | One username per line |

### GPT Prompt Files

| Filename | Purpose |
|----------|---------|
| `gpt_prompt.txt` | General AI prompt |
| `comment_gpt_prompt.txt` | Comment generation prompt |
| `message_new_followers_gpt_prompt.txt` | DM prompt for new followers |
| `message_specific_users_gpt_prompt.txt` | DM prompt for specific users |
| `caption_prompt.txt` | Post caption generation prompt |

---

## Field Mappings (UI to Database)

### Master Toggles (accounts.db)

**Note:** Only some toggles exist in accounts.db. Others are stored in settings.db JSON.

| Dashboard UI Field | Storage Location | Column/Key | Values |
|-------------------|-----------------|-----------|--------|
| `enable_follow` | accounts.db | `follow` | `'True'` / `'False'` |
| `enable_unfollow` | accounts.db | `unfollow` | `'True'` / `'False'` |
| `enable_mute` | accounts.db | `mute` | `'True'` / `'False'` |
| `enable_switchmode` | accounts.db | `switchmode` | `'True'` / `'False'` |
| `enable_likepost` | settings.db JSON | `enable_likepost` | `true` / `false` |
| `enable_comment` | settings.db JSON | `enable_comment` | `true` / `false` |
| `enable_story_viewer` | settings.db JSON | `enable_story_viewer` | `true` / `false` |
| `enable_directmessage` | settings.db JSON | `enable_directmessage` | `true` / `false` |

### Like Settings (settings.db JSON)

| UI Field ID | JSON Key | Type |
|-------------|----------|------|
| `enable_likepost_sources_followers` | `likepost_method.enable_likepost_sources_followers` | boolean |
| `enable_likepost_via_keywords` | `likepost_method.enable_likepost_via_keywords` | boolean |
| `enable_likepost_specific_accounts` | `likepost_method.enable_likepost_specific_accounts` | boolean |
| `min_likepost_action` | `min_likepost_action` | string |
| `max_likepost_action` | `max_likepost_action` | string |
| `like_limit_perday` | `like_limit_perday` | string |
| `enable_auto_increment_like_limit_perday` | `enable_auto_increment_like_limit_perday` | boolean |
| `like_enable_filters` | `like_enable_filters` | boolean |
| `enable_dont_like_if_user_followed` | `enable_dont_like_if_user_followed` | boolean |
| `enable_dont_like_sametag_accounts` | `enable_dont_like_sametag_accounts` | boolean |
| `like_story_after_liking_post` | `like_story_after_liking_post` | boolean |

### Comment Settings (settings.db JSON)

| UI Field ID | JSON Key | Type |
|-------------|----------|------|
| `comment_using_keyword_search` | `comment_method.comment_using_keyword_search` | boolean |
| `comment_text` | `comment_text` | string |
| `min_comment` | `min_comment` | string |
| `max_comment` | `max_comment` | string |
| `comment_min_delay` | `comment_min_delay` | string |
| `comment_max_delay` | `comment_max_delay` | string |
| `comment_limit_perday` | `comment_limit_perday` | string |
| `enable_dont_comment_sametag_accounts` | `enable_dont_comment_sametag_accounts` | boolean |

### Story Settings (settings.db JSON)

| UI Field ID | JSON Key | Type |
|-------------|----------|------|
| `view_followers` | `view_method.view_followers` | boolean |
| `view_likers` | `view_method.view_likers` | boolean |
| `view_specific_user` | `view_method.view_specific_user` | boolean |
| `view_specific_user_highlight` | `view_method.view_specific_user_highlight` | boolean |
| `story_viewer_min` | `story_viewer_min` | string |
| `story_viewer_max` | `story_viewer_max` | string |
| `story_viewer_daily_limit` | `story_viewer_daily_limit` | string |
| `story_view_peraccount_view` | `story_view_peraccount_view` | string |
| `like_story_after_viewing` | `like_story_after_viewing` | boolean |
| `story_like_daily_limit` | `story_like_daily_limit` | string |
| `min_story_like_peraccount_view` | `min_story_like_peraccount_view` | string |
| `max_story_like_peraccount_view` | `max_story_like_peraccount_view` | string |
| `dont_view_same_account_twice` | `dont_view_same_account_twice` | boolean |
| `view_highlight_if_no_story_viceversa` | `view_highlight_if_no_story_viceversa` | boolean |

### DM Settings (settings.db JSON)

| UI Field ID | JSON Key | Type |
|-------------|----------|------|
| `directmessage_new_followers` | `directmessage_method.directmessage_new_followers` | boolean |
| `directmessage_specificuser` | `directmessage_method.directmessage_specificuser` | boolean |
| `directmessage_reply` | `directmessage_method.directmessage_reply` | boolean |
| `enable_dm_crm` | `directmessage_method.enable_dm_crm` | boolean |
| `directmessage_min` | `directmessage_min` | string |
| `directmessage_max` | `directmessage_max` | string |
| `directmessage_min_delay` | `directmessage_min_delay` | string |
| `directmessage_max_delay` | `directmessage_max_delay` | string |
| `directmessage_daily_limit` | `directmessage_daily_limit` | string |
| `message_check_delay` | `message_check_delay` | string |
| `enable_send_message_every_new_line` | `enable_send_message_every_new_line` | boolean |
| `enable_openai_dm` | `enable_openai_dm` | boolean |
| `enable_cupidai_dm` | `enable_cupidai_dm` | boolean |
| `enable_openai_assistant` | `enable_openai_assistant` | boolean |

### Follow Settings (settings.db JSON)

| UI Field ID | JSON Key | Type |
|-------------|----------|------|
| `follow_followers` | `follow_method.follow_followers` | boolean |
| `follow_likers` | `follow_method.follow_likers` | boolean |
| `follow_specific_sources` | `follow_method.follow_specific_sources` | boolean |
| `follow_using_word_search` | `follow_method.follow_using_word_search` | boolean |
| `default_action_limit_perday` | `default_action_limit_perday` | string |
| `enable_auto_increment_follow_limit_perday` | `enable_auto_increment_follow_limit_perday` | boolean |
| `follow_timer_min_hour` | `follow_timer_min_hour` | string |
| `follow_timer_max_hour` | `follow_timer_max_hour` | string |
| `follow_is_weekdays` | `follow_is_weekdays` | boolean |

### Unfollow Settings (settings.db JSON)

| UI Field ID | JSON Key | Type |
|-------------|----------|------|
| `unfollow_using_profile` | `unfollow_method.unfollow_using_profile` | boolean |
| `unfollow_using_following_list` | `unfollow_method.unfollow_using_following_list` | boolean |
| `unfollow_specific_accounts` | `unfollow_method.unfollow_specific_accounts` | boolean |
| `unfollow_limit_perday` | `unfollow_limit_perday` | string |
| `enable_auto_increment_unfollow_limit_perday` | `enable_auto_increment_unfollow_limit_perday` | boolean |
| `unfollow_delay_day` | `unfollow_delay_day` | string |

### Filter Settings (settings.db JSON)

| UI Field ID | JSON Key | Type |
|-------------|----------|------|
| `min_followers` | `filters.min_followers` | string |
| `max_followers` | `filters.max_followers` | string |
| `min_following` | `filters.min_following` | string |
| `max_following` | `filters.max_following` | string |
| `min_posts` | `filters.min_posts` | string |
| `max_posts` | `filters.max_posts` | string |
| `must_have_profile_pic` | `filters.must_have_profile_pic` | boolean |
| `must_be_business` | `filters.must_be_business` | boolean |
| `must_be_verified` | `filters.must_be_verified` | boolean |
| `must_be_public` | `filters.must_be_public` | boolean |

### Reels Settings (settings.db JSON)

| UI Field ID | JSON Key | Type |
|-------------|----------|------|
| `enable_watch_reels` | `enable_watch_reels` | boolean |
| `min_reels_to_watch` | `min_reels_to_watch` | string |
| `max_reels_to_watch` | `max_reels_to_watch` | string |
| `watch_reels_duration_min` | `watch_reels_duration_min` | string |
| `watch_reels_duration_max` | `watch_reels_duration_max` | string |
| `watch_reels_daily_limit` | `watch_reels_daily_limit` | string |
| `enable_save_reels_while_watching` | `enable_save_reels_while_watching` | boolean |
| `save_reels_percent` | `save_reels_percent` | string |
| `enable_like_reels_while_watching` | `enable_like_reels_while_watching` | boolean |
| `like_reels_percent` | `like_reels_percent` | string |
| `enable_comment_reels_while_watching` | `enable_comment_reels_while_watching` | boolean |
| `comment_reels_percent` | `comment_reels_percent` | string |

### Share to Story Settings (settings.db JSON)

| UI Field ID | JSON Key | Type |
|-------------|----------|------|
| `enable_shared_post` | `enable_shared_post` | boolean |
| `post_type_to_share` | `post_type_to_share` | string (`"post"`, `"reel"`, `"both"`) |
| `shared_post_limit_perday` | `shared_post_limit_perday` | string |
| `enable_add_mention_shared_post` | `enable_add_mention_shared_post` | boolean |
| `enable_add_hashtag_shared_post` | `enable_add_hashtag_shared_post` | boolean |
| `enable_add_sticker_shared_post` | `enable_add_sticker_shared_post` | boolean |
| `enable_add_music_shared_post` | `enable_add_music_shared_post` | boolean |
| `enable_repost_shared_post` | `enable_repost_shared_post` | boolean |
| `repost_limit_perday` | `repost_limit_perday` | string |

### Human Behaviour Emulation (HBE) Settings (settings.db JSON)

| UI Field ID | JSON Key | Type |
|-------------|----------|------|
| `enable_human_behaviour_emulation` | `enable_human_behaviour_emulation` | boolean |
| `enable_viewhomefeedstory` | `enable_viewhomefeedstory` | boolean |
| `viewhomefeedstory_min` | `viewhomefeedstory_min` | string |
| `viewhomefeedstory_max` | `viewhomefeedstory_max` | string |
| `viewhomefeedstory_daily_limit` | `viewhomefeedstory_daily_limit` | string |
| `enable_scrollhomefeed` | `enable_scrollhomefeed` | boolean |
| `scrollhomefeed_min` | `scrollhomefeed_min` | string |
| `scrollhomefeed_max` | `scrollhomefeed_max` | string |
| `scrollhomefeed_duration_min` | `scrollhomefeed_duration_min` | string |
| `scrollhomefeed_duration_max` | `scrollhomefeed_duration_max` | string |
| `enable_scrollexplorepage` | `enable_scrollexplorepage` | boolean |
| `scrollexplorepage_min` | `scrollexplorepage_min` | string |
| `scrollexplorepage_max` | `scrollexplorepage_max` | string |
| `scrollexplorepage_duration_min` | `scrollexplorepage_duration_min` | string |
| `scrollexplorepage_duration_max` | `scrollexplorepage_duration_max` | string |

### Timer/Schedule Settings (accounts.db)

These settings are stored in `accounts.db` table, **not** in settings.db JSON.

| UI Field ID | Column Name | Type | Format |
|-------------|-------------|------|--------|
| `starttime` | `starttime` | TEXT | `'0'`-`'23'` (hour) |
| `endtime` | `endtime` | TEXT | `'0'`-`'23'` (hour) |
| `randomaction_min` / `randomaction_max` | `randomaction` | TEXT | `'min,max'` (comma-separated) |
| `randomdelay_min` / `randomdelay_max` | `randomdelay` | TEXT | `'min,max'` (comma-separated) |

**Example:** `randomaction = '30,60'` means random action between 30-60 minutes.

---

## Data Type Conventions

### In accounts.db (SQLite columns):
- **Toggles:** String values `'True'` or `'False'` (capital T/F)
- **Comma-separated values:** Format `'min,max'` for ranges (e.g., `'30,60'`)
- **Text fields:** Regular strings
- **Dates:** ISO format `YYYY-MM-DD`

### In settings.db JSON:
- **Numeric values:** Stored as **strings** (e.g., `"50"`, `"100"`)
- **Booleans:** Actual JSON booleans (`true`/`false`)
- **Nested settings:** Objects for method selections

### Converting Between Dashboard and Database:

```python
# Dashboard boolean → accounts.db string
db_value = 'True' if dashboard_value else 'False'

# accounts.db string → Dashboard boolean
def to_bool(val):
    if val is None:
        return False
    val_str = str(val).lower().strip()
    return val_str in ('on', 'true', '1', 'yes')

# Dashboard number → settings.db JSON
json_value = str(dashboard_number)

# settings.db JSON → Dashboard number
dashboard_number = int(json_value) if json_value else 0
```

---

## Quick Reference: Two-Tier Storage

**CRITICAL CONCEPT:** Onimator uses TWO storage locations:

| What | Where | Format |
|------|-------|--------|
| Master ON/OFF toggles | `accounts.db` | String: `'True'`/`'False'` |
| Timer/Schedule settings | `accounts.db` | String or comma-separated |
| Detailed settings | `settings.db` | JSON string |

When reading settings for UI:
1. Read JSON from `settings.db`
2. Read toggles from `accounts.db`
3. Merge them together

When writing settings from UI:
1. Extract toggle fields → write to `accounts.db`
2. Write all settings (including toggles) → write to `settings.db`

---

## Username Change Sync

When an Instagram username changes, update these locations:

1. **accounts.db** - `UPDATE accounts SET account = 'new' WHERE account = 'old'`
2. **stats.db** - `UPDATE stats SET account = 'new' WHERE account = 'old'`
3. **Folder name** - Rename `{device}/old_username/` → `{device}/new_username/`

See `ONIMATOR_USERNAME_SYNC.md` for full details.

---

## Version History

- **v1.1** (2025-01-20): Added Reels, Share, HBE settings; Timer/Schedule settings from accounts.db; corrected toggle format to `'True'`/`'False'`
- **v1.0** (2025-01-20): Initial documentation based on Onimator 14.2.4
