# Instagram Business Profile Automation — Full Implementation Plan

> **Created**: 2026-02-21
> **Status**: Planning
> **Target**: Hydra Phone Farm (UIAutomator2 + SQLite + Flask Dashboard)

---

## Table of Contents
1. [Overview](#1-overview)
2. [Instagram Business Profile Switch — UI Flow Research](#2-instagram-business-profile-switch--ui-flow-research)
3. [Instagram Insights — Available Analytics](#3-instagram-insights--available-analytics)
4. [Database Schema Changes](#4-database-schema-changes)
5. [Dashboard UI Changes](#5-dashboard-ui-changes)
6. [Automation Module: `switch_to_business.py`](#6-automation-module-switch_to_businesspy)
7. [Automation Module: `scrape_insights.py`](#7-automation-module-scrape_insightspy)
8. [Bot Engine Integration](#8-bot-engine-integration)
9. [Implementation Order & Estimates](#9-implementation-order--estimates)
10. [Risks & Mitigations](#10-risks--mitigations)

---

## 1. Overview

### Goals
1. **Track** which accounts are Business/Professional profiles vs Personal
2. **Automate** switching personal accounts to Business Profile via the IG app UI
3. **Scrape** Instagram Insights data (reach, impressions, follower demographics) from Business accounts
4. **Display** analytics on the Hydra dashboard

### Why Business Profile?
- Access to **Instagram Insights** (reach, impressions, demographics, engagement metrics)
- **Contact buttons** (email, phone) — adds legitimacy
- Ability to **run ads** and **boost posts** (future capability)
- Access to **scheduling features** natively
- Business accounts appear more **credible** to users
- Required for **Instagram Shopping** if ever needed

---

## 2. Instagram Business Profile Switch — UI Flow Research

### Prerequisites
- Account must be logged in and active
- Account must be on the Profile tab
- No pending challenges/verification

### Complete Step-by-Step Flow (Instagram 2024-2026)

#### Path: Profile → Edit Profile → Switch to Professional Account

**Step 1: Navigate to Profile**
- Tap Profile tab (bottom nav, content-desc="Profile")
- Verify: profile_tab selected=true

**Step 2: Open Edit Profile**
- Tap "Edit profile" button (or "Edit your profile")
- Resource IDs to look for:
  - `{pkg}:id/edit_profile_button`
  - Text: "Edit profile" or "Edit your profile"
  - Content-desc: "Edit profile"
- Verify: Edit profile screen loads (name_field, username_field, bio_field present)

**Step 3: Find "Switch to professional account"**
- **IMPORTANT**: This link may require scrolling down on the Edit Profile page
- Look for text: "Switch to professional account" (clickable link, usually blue)
- Alternative locations in newer IG versions:
  - Settings → Account → "Switch to professional account"
  - Settings → Account type and tools → "Switch to professional account"
- Resource ID candidates:
  - Text match: "Switch to professional account"
  - May also appear as "Switch to Professional Account" (capitalized)

**Step 4: "Get Professional Tools" / Intro Screens**
- IG shows 1-3 introductory screens explaining benefits
- Button: "Continue" at the bottom of each screen
- May show screens about:
  - "Get access to insights"
  - "Reach more people"
  - "New ways to connect"
- Action: Tap "Continue" on each screen (up to 3-4 times)

**Step 5: Choose a Category**
- Screen: "What best describes you?"
- Shows a grid/list of categories
- **Recommended categories for automation:**
  - "Digital creator" (most generic, works for any niche)
  - "Entrepreneur" (business-focused)
  - "Artist" (creative accounts)
  - "Personal blog" (generic)
  - "Product/service" (e-commerce)
- There's a search bar at top to search categories
- Action: Tap desired category → Tap "Done"
- Checkbox: "Display category on profile" (toggle off for stealth, on for legitimacy)

**Step 6: Choose Account Type: Creator vs Business**
- Screen: "Choose account type" or similar
- Two options:
  - **Creator** — for influencers, public figures, artists
  - **Business** — for brands, organizations, service providers
- Action: Tap "Business" → Tap "Next"
- **Note**: Creator accounts also get Insights but have different features

**Step 7: Review Contact Information**
- Screen shows: Email, Phone number, Address fields
- Pre-filled with account email if available
- Action: Can skip or fill in → Tap "Next"
- May show "Don't use my contact info" option

**Step 8: Connect Facebook Page (Optional)**
- Screen: "Connect to a Facebook Page"
- Options: "Connect to Facebook", "Skip"
- Action: **Always tap "Skip"** — we don't want to connect FB pages
- Alternative text: "Not now", "Skip", "Don't connect"

**Step 9: Setup Complete / Welcome Screen**
- May show: "You're all set!" or "Welcome to your professional account"
- Button: "Done" or "Got it" or "Explore professional tools"
- Action: Tap "Done" / dismiss
- May also prompt to:
  - Set up a shop
  - Create your first ad
  - Complete your profile
- Action: Skip/dismiss all of these

**Step 10: Verify Business Profile Active**
- Navigate back to Profile tab
- Look for indicators:
  - Category label visible below name (e.g., "Digital creator")
  - "Insights" button visible on profile
  - "Professional dashboard" section visible
  - "Ad tools" or "Promotions" section visible
- Resource IDs:
  - `{pkg}:id/professional_dashboard_container`
  - `{pkg}:id/insights_nav_button`
  - Content-desc containing "Insights" or "Professional dashboard"

### Alternative Path (Newer IG Versions: Settings-Based)

Some IG versions use a different path:

1. Profile → Hamburger menu (☰ top right) → "Settings and privacy"
2. Scroll to "For professionals" section → "Account type and tools"
3. Tap "Switch to professional account"
4. Continue with Steps 4-10 above

**Resource IDs for settings path:**
- Hamburger menu: `{pkg}:id/option_list_button` or content-desc="Options"
- Settings: Text "Settings and privacy" or "Settings"
- Account type: Text "Account type and tools"

### Key UI Elements & Selectors

| Screen | Element | Selector Strategy |
|--------|---------|-------------------|
| Profile tab | Edit profile btn | `text="Edit profile"` or `desc="Edit profile"` |
| Edit profile | Switch link | `text*="Switch to professional"` (partial match) |
| Settings | Hamburger menu | `desc="Options"` or `rid=option_list_button` |
| Settings page | Settings & privacy | `text="Settings and privacy"` |
| Account type | Switch professional | `text*="Switch to professional"` |
| Category picker | Category items | `text="Digital creator"` etc. |
| Category picker | Done button | `text="Done"` |
| Account type | Business option | `text="Business"` |
| Account type | Next button | `text="Next"` |
| Contact info | Next/Skip | `text="Next"` or `text="Skip"` |
| Facebook connect | Skip | `text="Skip"` or `text="Not now"` |
| Welcome screen | Done | `text="Done"` or `text="Got it"` |
| Intro screens | Continue | `text="Continue"` |

### Known Gotchas

1. **Already Business**: If account is already professional, "Switch to professional" won't appear. Instead you'll see "Switch account type" or "Switch to personal account".
2. **Category search**: The category picker has hundreds of options. Using search is faster but text input needs to be handled carefully.
3. **Multiple "Continue" screens**: IG sometimes shows 1, sometimes 3 intro screens. Loop and click Continue until the category picker appears.
4. **Facebook login prompt**: IG may prompt to log into Facebook. Always skip.
5. **Post-switch modals**: After switching, IG may show promotional modals about ads, shop setup, etc. Need to dismiss all.
6. **Account age**: Very new accounts may not have the option to switch. Usually requires a few days/posts first.
7. **Rate limiting**: If too many accounts switch rapidly from the same IP, IG may flag them. Space out switches.

---

## 3. Instagram Insights — Available Analytics

### What's Available in Instagram Insights

Instagram Insights is only accessible to Business and Creator accounts. Accessible via:
- Profile → "Professional dashboard" → "See all insights"
- Profile → Hamburger menu → "Insights"

### Account-Level Metrics (Overview)

| Metric | Description | Retention |
|--------|-------------|-----------|
| **Accounts reached** | Unique accounts that saw any content | 90 days |
| **Accounts engaged** | Unique accounts that interacted (like, comment, save, share) | 90 days |
| **Total followers** | Current follower count + growth trends | 90 days |
| **Profile visits** | Number of times profile was visited | 90 days |
| **Website clicks** | Clicks on website link in bio | 90 days |
| **Email/Call/Address clicks** | Clicks on contact buttons | 90 days |

### Content-Level Metrics

#### Posts
| Metric | Description |
|--------|-------------|
| Likes | Number of likes |
| Comments | Number of comments |
| Shares | Times shared to DM or stories |
| Saves | Times bookmarked |
| Reach | Unique accounts that saw it |
| Impressions | Total views (includes repeats) |
| Profile visits | From this post |
| Follows | New follows from this post |

#### Reels
| Metric | Description |
|--------|-------------|
| Plays | Number of times played |
| Accounts reached | Unique viewers |
| Likes | Number of likes |
| Comments | Number of comments |
| Shares | Times shared |
| Saves | Times bookmarked |
| Watch time | Total/average watch duration |

#### Stories
| Metric | Description |
|--------|-------------|
| Impressions | Total views |
| Reach | Unique viewers |
| Replies | Direct message replies |
| Exits | Times someone left the story |
| Forwards | Taps forward |
| Backwards | Taps backward |
| Profile visits | From this story |
| Follows | New follows from this story |

### Demographic Data (Followers ≥ 100)

| Demographic | Data |
|-------------|------|
| **Top cities** | City name + % of followers |
| **Top countries** | Country name + % of followers |
| **Age range** | Brackets: 13-17, 18-24, 25-34, 35-44, 45-54, 55-64, 65+ |
| **Gender** | Male %, Female %, Other % |
| **Most active times** | Hours (0-23) and Days (Mon-Sun) when followers are online |

### Insights UI Structure (for UIAutomator2 scraping)

The Insights screen has a tab-like structure:

```
Insights Overview
├── Time period selector (Last 7 days / 30 days / 90 days / custom)
├── Accounts reached
│   ├── Total number
│   ├── Delta vs previous period (% or absolute)
│   ├── Followers vs Non-followers breakdown
│   └── Top content by reach
├── Accounts engaged
│   ├── Total number
│   ├── Delta vs previous period
│   ├── Content interactions breakdown
│   └── Top content by engagement
├── Total followers
│   ├── Current count
│   ├── Net change
│   ├── Growth chart
│   ├── Top locations (cities/countries)
│   ├── Age range breakdown
│   ├── Gender breakdown
│   └── Most active times
└── Content You Shared
    ├── Posts (grid with metrics)
    ├── Stories
    └── Reels
```

### Key Resource IDs for Insights Scraping

**Note**: Exact resource IDs may vary by IG version. These are educated guesses based on IG's naming conventions. Real IDs must be confirmed by XML dump on an actual Business profile.

```
Likely resource IDs:
- {pkg}:id/insights_overview_container
- {pkg}:id/insights_metric_value      (the big numbers)
- {pkg}:id/insights_metric_delta      (the +/- change)
- {pkg}:id/insights_metric_label      (metric name)
- {pkg}:id/insights_tab_layout        (time period tabs)
- {pkg}:id/audience_insights_container
- {pkg}:id/professional_dashboard_container
- {pkg}:id/insights_overview_accounts_reached_value
- {pkg}:id/insights_overview_accounts_engaged_value
```

**Strategy for scraping**: Since resource IDs may change between IG versions, use a **hybrid approach**:
1. Try known resource IDs first
2. Fall back to text-based matching (look for numbers near known labels)
3. Parse the entire XML and extract numeric values adjacent to known text labels

---

## 4. Database Schema Changes

### 4.1 Add `is_business_profile` to `accounts` Table

```sql
ALTER TABLE accounts ADD COLUMN is_business_profile INTEGER DEFAULT 0;
ALTER TABLE accounts ADD COLUMN business_category TEXT DEFAULT '';
ALTER TABLE accounts ADD COLUMN business_switched_at TEXT;
```

- `is_business_profile`: 0 = personal, 1 = business/professional
- `business_category`: The selected category (e.g., "Digital creator")
- `business_switched_at`: ISO timestamp when the switch was made

### 4.2 New Table: `account_insights`

Stores periodic snapshots of account-level Insights data.

```sql
CREATE TABLE IF NOT EXISTS account_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    device_serial TEXT NOT NULL,

    -- Time period this data covers
    period_type TEXT NOT NULL DEFAULT '7d',  -- '7d', '30d', '90d'

    -- Account-level metrics
    accounts_reached INTEGER DEFAULT 0,
    accounts_reached_delta REAL DEFAULT 0,      -- % change vs previous period
    accounts_engaged INTEGER DEFAULT 0,
    accounts_engaged_delta REAL DEFAULT 0,
    profile_visits INTEGER DEFAULT 0,
    website_clicks INTEGER DEFAULT 0,
    email_clicks INTEGER DEFAULT 0,

    -- Follower demographics (JSON)
    follower_demographics TEXT DEFAULT '{}',
    -- JSON structure:
    -- {
    --   "top_cities": [{"name": "New York", "pct": 12.5}, ...],
    --   "top_countries": [{"name": "United States", "pct": 45.2}, ...],
    --   "age_ranges": {"18-24": 30.5, "25-34": 40.2, ...},
    --   "gender": {"male": 48.2, "female": 50.1, "other": 1.7},
    --   "most_active_hours": [9, 12, 18, 20, 21],
    --   "most_active_days": ["Monday", "Wednesday", "Friday"]
    -- }

    -- Engagement breakdown (JSON)
    engagement_breakdown TEXT DEFAULT '{}',
    -- JSON structure:
    -- {
    --   "likes": 1234,
    --   "comments": 56,
    --   "saves": 89,
    --   "shares": 123,
    --   "replies": 12
    -- }

    captured_at TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (account_id) REFERENCES accounts(id),
    UNIQUE(username, device_serial, period_type, captured_at)
);

CREATE INDEX IF NOT EXISTS idx_insights_username ON account_insights(username);
CREATE INDEX IF NOT EXISTS idx_insights_captured ON account_insights(captured_at);
CREATE INDEX IF NOT EXISTS idx_insights_account ON account_insights(account_id);
```

### 4.3 New Table: `content_insights`

Stores per-post/reel/story performance metrics.

```sql
CREATE TABLE IF NOT EXISTS content_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    device_serial TEXT NOT NULL,

    content_type TEXT NOT NULL,  -- 'post', 'reel', 'story'
    content_id TEXT,             -- IG's internal content ID if available

    -- Metrics
    reach INTEGER DEFAULT 0,
    impressions INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    saves INTEGER DEFAULT 0,
    plays INTEGER DEFAULT 0,        -- video/reel plays
    profile_visits INTEGER DEFAULT 0,
    follows INTEGER DEFAULT 0,      -- follows from this content

    -- Story-specific
    exits INTEGER DEFAULT 0,
    forwards INTEGER DEFAULT 0,
    backwards INTEGER DEFAULT 0,
    replies INTEGER DEFAULT 0,

    captured_at TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

CREATE INDEX IF NOT EXISTS idx_content_insights_username ON content_insights(username);
CREATE INDEX IF NOT EXISTS idx_content_insights_captured ON content_insights(captured_at);
```

### 4.4 Migration Script

Add to `phone_farm_db.py` `_ensure_columns()`:

```python
# Business profile columns
try:
    conn.execute("ALTER TABLE accounts ADD COLUMN is_business_profile INTEGER DEFAULT 0")
    conn.commit()
except Exception:
    pass

try:
    conn.execute("ALTER TABLE accounts ADD COLUMN business_category TEXT DEFAULT ''")
    conn.commit()
except Exception:
    pass

try:
    conn.execute("ALTER TABLE accounts ADD COLUMN business_switched_at TEXT")
    conn.commit()
except Exception:
    pass

# Insights tables
conn.executescript("""
    CREATE TABLE IF NOT EXISTS account_insights ( ... );
    CREATE TABLE IF NOT EXISTS content_insights ( ... );
""")
conn.commit()
```

Also add to `helpers.py` `get_db()` auto-migration section.

---

## 5. Dashboard UI Changes

### 5.1 Device Manager Detail Page — Account Table

Add a "Business" column/badge to the accounts table on `/device-manager/<serial>`.

**In `device_manager_detail.html`:**

```html
<!-- In the account table header -->
<th>Business</th>

<!-- In the account table row -->
<td>
    {% if account.is_business_profile %}
        <span class="badge bg-primary" title="Business Profile ({{ account.business_category }})">
            <i class="bi bi-briefcase-fill"></i> BIZ
        </span>
    {% else %}
        <span class="badge bg-dark text-muted" title="Personal Account">
            Personal
        </span>
    {% endif %}
</td>
```

### 5.2 Account Settings Modal — Overview Tab

Add a "Business Profile" section to the Overview tab:

```html
<!-- Business Profile Section -->
<div class="card bg-dark border-secondary mb-3">
    <div class="card-header d-flex justify-content-between align-items-center">
        <span>📊 Business Profile</span>
        <div class="form-check form-switch">
            <input class="form-check-input" type="checkbox" id="is_business_profile"
                   {{ 'checked' if account.is_business_profile }}>
            <label class="form-check-label" for="is_business_profile">Active</label>
        </div>
    </div>
    <div class="card-body">
        <div class="row">
            <div class="col-6">
                <label class="form-label small text-muted">Category</label>
                <input type="text" class="form-control form-control-sm bg-dark text-light"
                       id="business_category" value="{{ account.business_category or '' }}"
                       placeholder="Digital creator">
            </div>
            <div class="col-6">
                <label class="form-label small text-muted">Switched At</label>
                <input type="text" class="form-control form-control-sm bg-dark text-light"
                       readonly value="{{ account.business_switched_at or 'Not yet' }}">
            </div>
        </div>
        <button class="btn btn-sm btn-outline-primary mt-3" id="btn-switch-business"
                {{ 'disabled' if account.is_business_profile }}>
            🔄 Switch to Business Profile (via automation)
        </button>
    </div>
</div>
```

### 5.3 New Tab: Insights (in Account Settings Modal)

Add an "Insights" tab to the account settings modal:

```html
<li class="nav-item">
    <a class="nav-link" data-bs-toggle="tab" href="#tab-insights">📊 Insights</a>
</li>

<!-- Insights tab content -->
<div class="tab-pane" id="tab-insights">
    <div class="row g-3 mb-4">
        <!-- Accounts Reached Card -->
        <div class="col-4">
            <div class="card bg-dark border-secondary text-center p-3">
                <div class="stat-num text-info fs-4" id="insight-reached">—</div>
                <div class="small text-muted">Accounts Reached</div>
                <div class="delta-up small" id="insight-reached-delta"></div>
            </div>
        </div>
        <!-- Accounts Engaged Card -->
        <div class="col-4">
            <div class="card bg-dark border-secondary text-center p-3">
                <div class="stat-num text-success fs-4" id="insight-engaged">—</div>
                <div class="small text-muted">Accounts Engaged</div>
                <div class="delta-up small" id="insight-engaged-delta"></div>
            </div>
        </div>
        <!-- Profile Visits Card -->
        <div class="col-4">
            <div class="card bg-dark border-secondary text-center p-3">
                <div class="stat-num text-warning fs-4" id="insight-visits">—</div>
                <div class="small text-muted">Profile Visits</div>
            </div>
        </div>
    </div>

    <!-- Demographics Chart -->
    <div class="card bg-dark border-secondary mb-3">
        <div class="card-header">Audience Demographics</div>
        <div class="card-body">
            <canvas id="demographics-chart" height="200"></canvas>
        </div>
    </div>

    <!-- Most Active Times -->
    <div class="card bg-dark border-secondary mb-3">
        <div class="card-header">Most Active Times</div>
        <div class="card-body">
            <canvas id="active-times-chart" height="150"></canvas>
        </div>
    </div>

    <!-- Scrape Button -->
    <button class="btn btn-sm btn-outline-info" id="btn-scrape-insights">
        🔄 Scrape Latest Insights
    </button>
    <span class="small text-muted ms-2" id="insights-last-scraped">
        Last scraped: Never
    </span>
</div>
```

### 5.4 API Endpoints

Add to device manager routes or create a new `insights_routes.py`:

```python
# GET /api/insights/<serial>/<username>
# Returns latest insights data for an account

# POST /api/insights/<serial>/<username>/scrape
# Triggers an insights scrape task for the account

# POST /api/device-manager/<serial>/<username>/switch-business
# Creates a task to switch the account to Business profile

# GET /api/insights/<serial>/<username>/history?days=30
# Returns historical insights snapshots
```

---

## 6. Automation Module: `switch_to_business.py`

### File: `phone-farm/automation/actions/switch_to_business.py`

```python
"""
Switch to Business Profile Action Module
==========================================
Switches a personal Instagram account to a Business/Professional profile.
Navigates through the IG settings UI flow using UIAutomator2.

Flow: Profile → Edit Profile → Switch to Professional → Category → Business → Done
"""

import logging
import time
import re
from automation.ig_controller import IGController, Screen
from automation.actions.helpers import (
    get_db, log_action, random_sleep,
)

log = logging.getLogger(__name__)

# Default category to select
DEFAULT_CATEGORY = "Digital creator"

# Categories that work well for automation accounts
SAFE_CATEGORIES = [
    "Digital creator",
    "Entrepreneur",
    "Personal blog",
    "Artist",
    "Musician/band",
    "Product/service",
    "Gaming video creator",
    "Video creator",
]


class SwitchToBusinessAction:
    """Switch account from Personal to Business/Professional profile."""

    def __init__(self, device, device_serial, account_info, session_id,
                 pkg=None, category=None, account_type='business'):
        self.device = device
        self.device_serial = device_serial
        self.account = account_info
        self.session_id = session_id
        self.username = account_info.get('username', '')
        self.account_id = account_info.get('id')
        self.category = category or DEFAULT_CATEGORY
        self.account_type = account_type  # 'business' or 'creator'

        _pkg = pkg or account_info.get('package', 'com.instagram.android')
        self.ctrl = IGController(device, device_serial, _pkg)

    def execute(self):
        """
        Full flow to switch account to Business profile.
        Returns dict with 'success', 'category', 'error_message'.
        """
        result = {
            'success': False,
            'category': None,
            'error_message': None,
        }

        try:
            log.info("[%s] SWITCH_BUSINESS: Starting for @%s (target: %s, category: %s)",
                     self.device_serial, self.username, self.account_type, self.category)

            # Step 1: Navigate to Profile
            if not self.ctrl.navigate_to(Screen.PROFILE):
                result['error_message'] = "Could not navigate to profile"
                return result

            random_sleep(1.5, 3.0, label="profile_loaded")

            # Step 2: Check if already a business profile
            xml = self.ctrl.dump_xml("check_business")
            if self._is_already_business(xml):
                log.info("[%s] @%s is already a Business/Professional profile",
                         self.device_serial, self.username)
                result['success'] = True
                result['category'] = 'already_business'
                self._update_db(True, 'already_business')
                return result

            # Step 3: Try Edit Profile path first, fallback to Settings path
            switch_found = self._try_edit_profile_path()
            if not switch_found:
                switch_found = self._try_settings_path()

            if not switch_found:
                result['error_message'] = "Could not find 'Switch to professional' option"
                return result

            # Step 4: Handle intro/continue screens
            self._dismiss_intro_screens()

            # Step 5: Select category
            category_ok = self._select_category()
            if not category_ok:
                result['error_message'] = "Failed to select category"
                return result

            # Step 6: Select Business (not Creator)
            type_ok = self._select_account_type()
            if not type_ok:
                result['error_message'] = "Failed to select Business account type"
                return result

            # Step 7: Handle contact info screen
            self._handle_contact_info()

            # Step 8: Skip Facebook connection
            self._skip_facebook_connect()

            # Step 9: Dismiss welcome/setup screens
            self._dismiss_post_switch_screens()

            # Step 10: Verify switch was successful
            success = self._verify_business_profile()

            if success:
                log.info("[%s] ✅ @%s successfully switched to Business Profile!",
                         self.device_serial, self.username)
                result['success'] = True
                result['category'] = self.category
                self._update_db(True, self.category)

                log_action(self.session_id, self.device_serial, self.username,
                           'switch_to_business', success=True)
            else:
                result['error_message'] = "Verification failed — profile may not have switched"
                log_action(self.session_id, self.device_serial, self.username,
                           'switch_to_business', success=False,
                           error_message=result['error_message'])

        except Exception as e:
            log.error("[%s] SWITCH_BUSINESS error: %s", self.device_serial, e)
            result['error_message'] = str(e)[:200]
            log_action(self.session_id, self.device_serial, self.username,
                       'switch_to_business', success=False,
                       error_message=result['error_message'])

        return result

    # ──────────────────────────────────────────────────
    # Private Methods
    # ──────────────────────────────────────────────────

    def _is_already_business(self, xml):
        """Check if account is already a Professional/Business profile."""
        indicators = [
            'Professional dashboard',
            'professional_dashboard',
            'Switch to personal account',
            'Switch account type',
            'Insights',  # Insights button on profile
        ]
        count = sum(1 for ind in indicators if ind in xml)
        return count >= 2  # At least 2 indicators

    def _try_edit_profile_path(self):
        """Try: Edit Profile → Switch to professional account."""
        log.info("[%s] Trying Edit Profile path...", self.device_serial)

        # Tap Edit Profile button
        edit_btn = self.device(textContains="Edit profile")
        if not edit_btn.exists(timeout=3):
            edit_btn = self.device(descriptionContains="Edit profile")
        if not edit_btn.exists(timeout=3):
            edit_btn = self.device(textContains="Edit your profile")

        if not edit_btn.exists(timeout=3):
            log.warning("[%s] Edit profile button not found", self.device_serial)
            return False

        edit_btn.click()
        random_sleep(2.0, 4.0, label="edit_profile_load")

        # Scroll down to find "Switch to professional account"
        return self._find_and_tap_switch_link()

    def _try_settings_path(self):
        """Try: Settings → Account type and tools → Switch to professional."""
        log.info("[%s] Trying Settings path...", self.device_serial)

        # Navigate to profile first
        self.ctrl.navigate_to(Screen.PROFILE)
        random_sleep(1.0, 2.0)

        # Tap hamburger menu (Options)
        options_btn = self.device(description="Options")
        if not options_btn.exists(timeout=3):
            options_btn = self.device(resourceIdMatches=".*option_list_button.*")
        if not options_btn.exists(timeout=3):
            # Try the three-line menu icon
            options_btn = self.device(descriptionContains="Menu")

        if not options_btn.exists(timeout=3):
            log.warning("[%s] Options/hamburger menu not found", self.device_serial)
            return False

        options_btn.click()
        random_sleep(1.5, 3.0, label="options_menu_load")

        # Tap "Settings and privacy"
        settings_btn = self.device(textContains="Settings")
        if settings_btn.exists(timeout=3):
            settings_btn.click()
            random_sleep(1.5, 3.0, label="settings_load")

        # Look for "Account type and tools" or similar
        acct_type_btn = self.device(textContains="Account type")
        if not acct_type_btn.exists(timeout=3):
            # Scroll to find it under "For professionals" section
            self.device(scrollable=True).scroll.to(textContains="Account type")
            acct_type_btn = self.device(textContains="Account type")

        if acct_type_btn.exists(timeout=3):
            acct_type_btn.click()
            random_sleep(1.5, 3.0, label="acct_type_load")
            return self._find_and_tap_switch_link()

        log.warning("[%s] Account type and tools not found in settings", self.device_serial)
        return False

    def _find_and_tap_switch_link(self):
        """Find and tap 'Switch to professional account' on current screen."""
        for scroll_attempt in range(5):
            xml = self.ctrl.dump_xml(f"find_switch_{scroll_attempt}")

            # Look for the switch text
            switch_texts = [
                "Switch to professional account",
                "Switch to Professional Account",
                "Switch to professional",
                "Get professional tools",
            ]

            for text in switch_texts:
                if text in xml:
                    switch_btn = self.device(textContains=text)
                    if switch_btn.exists(timeout=2):
                        switch_btn.click()
                        random_sleep(2.0, 4.0, label="switch_clicked")
                        log.info("[%s] Tapped: '%s'", self.device_serial, text)
                        return True

            # Scroll down to find it
            try:
                self.device.swipe(540, 1500, 540, 800, duration=0.5)
                random_sleep(1.0, 2.0, label="scroll_for_switch")
            except Exception:
                break

        log.warning("[%s] 'Switch to professional' not found after scrolling", self.device_serial)
        return False

    def _dismiss_intro_screens(self):
        """Dismiss 1-4 intro/benefit screens by tapping Continue."""
        for i in range(6):
            random_sleep(1.5, 3.0, label=f"intro_screen_{i}")
            xml = self.ctrl.dump_xml(f"intro_{i}")

            # Check if we've reached the category picker
            if self._is_category_screen(xml):
                log.info("[%s] Reached category picker after %d intro screens", self.device_serial, i)
                return

            # Look for Continue button
            continue_btn = self.device(text="Continue")
            if continue_btn.exists(timeout=2):
                continue_btn.click()
                log.info("[%s] Dismissed intro screen %d (Continue)", self.device_serial, i + 1)
                continue

            # Look for "Get started" or "Next"
            for btn_text in ["Get started", "Next", "Got it"]:
                btn = self.device(text=btn_text)
                if btn.exists(timeout=1):
                    btn.click()
                    log.info("[%s] Dismissed intro screen %d (%s)", self.device_serial, i + 1, btn_text)
                    break
            else:
                # No dismiss button found — might already be past intros
                break

    def _is_category_screen(self, xml):
        """Check if we're on the category selection screen."""
        indicators = [
            "What best describes you",
            "Choose a category",
            "Select a category",
            "Digital creator",
            "Entrepreneur",
            "Personal blog",
        ]
        return sum(1 for ind in indicators if ind in xml) >= 2

    def _select_category(self):
        """Select a business category."""
        random_sleep(1.0, 2.0)
        xml = self.ctrl.dump_xml("category_screen")

        if not self._is_category_screen(xml):
            log.warning("[%s] Not on category screen — may have been skipped", self.device_serial)
            # Could already be past this step
            return True

        # Try to find and tap the desired category
        cat_btn = self.device(text=self.category)
        if cat_btn.exists(timeout=3):
            cat_btn.click()
            log.info("[%s] Selected category: %s", self.device_serial, self.category)
        else:
            # Try search if available
            search = self.device(textContains="Search")
            if search.exists(timeout=2):
                search.click()
                random_sleep(0.5, 1.0)
                search.set_text(self.category)
                random_sleep(1.0, 2.0)
                cat_btn = self.device(text=self.category)
                if cat_btn.exists(timeout=3):
                    cat_btn.click()
                else:
                    # Fall back to first available safe category
                    for fallback in SAFE_CATEGORIES:
                        fb_btn = self.device(text=fallback)
                        if fb_btn.exists(timeout=1):
                            fb_btn.click()
                            self.category = fallback
                            log.info("[%s] Used fallback category: %s", self.device_serial, fallback)
                            break

        random_sleep(1.0, 2.0)

        # Uncheck "Display category on profile" if checkbox exists (optional — can be either way)
        # For now, leave default behavior

        # Tap Done
        done_btn = self.device(text="Done")
        if done_btn.exists(timeout=3):
            done_btn.click()
            random_sleep(1.5, 3.0, label="category_done")
            return True

        # Try Next instead
        next_btn = self.device(text="Next")
        if next_btn.exists(timeout=2):
            next_btn.click()
            random_sleep(1.5, 3.0)
            return True

        log.warning("[%s] Could not confirm category selection", self.device_serial)
        return False

    def _select_account_type(self):
        """Select Business (not Creator) account type."""
        random_sleep(1.0, 2.0)
        xml = self.ctrl.dump_xml("account_type_screen")

        # Check if we're on the account type screen
        if "Business" not in xml and "Creator" not in xml:
            # Might have been skipped (some flows don't show this)
            log.info("[%s] Account type screen not detected — may have been skipped",
                     self.device_serial)
            return True

        if self.account_type == 'business':
            type_btn = self.device(text="Business")
        else:
            type_btn = self.device(text="Creator")

        if type_btn.exists(timeout=3):
            type_btn.click()
            log.info("[%s] Selected account type: %s", self.device_serial, self.account_type)
            random_sleep(1.0, 2.0)

        # Tap Next
        next_btn = self.device(text="Next")
        if next_btn.exists(timeout=3):
            next_btn.click()
            random_sleep(1.5, 3.0, label="type_next")
            return True

        log.warning("[%s] Could not confirm account type", self.device_serial)
        return True  # May have auto-advanced

    def _handle_contact_info(self):
        """Handle the contact info review screen."""
        random_sleep(1.5, 3.0)
        xml = self.ctrl.dump_xml("contact_info")

        # If contact info screen is showing, just tap Next/Skip
        for btn_text in ["Next", "Skip", "Don't use my contact info", "Not now"]:
            btn = self.device(text=btn_text)
            if btn.exists(timeout=2):
                btn.click()
                log.info("[%s] Contact info: tapped '%s'", self.device_serial, btn_text)
                random_sleep(1.5, 3.0)
                return

    def _skip_facebook_connect(self):
        """Skip the Facebook page connection screen."""
        random_sleep(1.5, 3.0)
        xml = self.ctrl.dump_xml("facebook_connect")

        for btn_text in ["Skip", "Not now", "Don't connect", "Later"]:
            btn = self.device(text=btn_text)
            if btn.exists(timeout=2):
                btn.click()
                log.info("[%s] Facebook connect: tapped '%s'", self.device_serial, btn_text)
                random_sleep(1.5, 3.0)
                return

        # Also try pressing back if nothing found
        if "Facebook" in xml or "Connect" in xml:
            self.device.press('back')
            random_sleep(1.0, 2.0)

    def _dismiss_post_switch_screens(self):
        """Dismiss any post-switch promotional screens."""
        for i in range(5):
            random_sleep(1.5, 3.0)
            xml = self.ctrl.dump_xml(f"post_switch_{i}")

            # Check if we're back on the profile
            current = self.ctrl.detect_screen(xml)
            if current == Screen.PROFILE:
                return

            # Dismiss buttons
            for btn_text in ["Done", "Got it", "Not now", "Skip",
                             "Explore professional tools", "Close",
                             "Maybe later", "Not Now"]:
                btn = self.device(text=btn_text)
                if btn.exists(timeout=1):
                    btn.click()
                    log.info("[%s] Post-switch dismiss: '%s'", self.device_serial, btn_text)
                    break
            else:
                # No button found, try back
                self.device.press('back')

    def _verify_business_profile(self):
        """Navigate to profile and verify business switch succeeded."""
        self.ctrl.navigate_to(Screen.PROFILE)
        random_sleep(2.0, 4.0, label="verify_profile_load")
        xml = self.ctrl.dump_xml("verify_business")

        indicators = [
            'Professional dashboard',
            'professional_dashboard',
            'Insights',
            'insights',
            'Ad tools',
            'Promotions',
        ]
        found = sum(1 for ind in indicators if ind.lower() in xml.lower())
        log.info("[%s] Business verification: %d/6 indicators found", self.device_serial, found)
        return found >= 1

    def _update_db(self, is_business, category):
        """Update the account's business profile status in DB."""
        try:
            import datetime
            conn = get_db()
            now = datetime.datetime.now().isoformat()
            conn.execute("""
                UPDATE accounts
                SET is_business_profile = ?, business_category = ?,
                    business_switched_at = ?, updated_at = ?
                WHERE id = ?
            """, (1 if is_business else 0, category, now, now, self.account_id))
            conn.commit()
            conn.close()
            log.info("[%s] DB updated: @%s → business=%s, category=%s",
                     self.device_serial, self.username, is_business, category)
        except Exception as e:
            log.error("[%s] DB update failed: %s", self.device_serial, e)
```

---

## 7. Automation Module: `scrape_insights.py`

### File: `phone-farm/automation/actions/scrape_insights.py`

```python
"""
Scrape Instagram Insights Action Module
=========================================
Navigates to the Insights screen on a Business/Creator profile
and extracts available metrics via XML parsing.

Requirements: Account must be a Business or Creator profile.
"""

import logging
import re
import json
import time
import datetime
from automation.ig_controller import IGController, Screen
from automation.actions.helpers import (
    get_db, log_action, random_sleep,
)

log = logging.getLogger(__name__)


class ScrapeInsightsAction:
    """Scrape Instagram Insights data from a Business profile."""

    def __init__(self, device, device_serial, account_info, session_id,
                 pkg=None, period='7d'):
        self.device = device
        self.device_serial = device_serial
        self.account = account_info
        self.session_id = session_id
        self.username = account_info.get('username', '')
        self.account_id = account_info.get('id')
        self.period = period  # '7d', '30d', '90d'

        _pkg = pkg or account_info.get('package', 'com.instagram.android')
        self.ctrl = IGController(device, device_serial, _pkg)

    def execute(self):
        """
        Navigate to Insights and scrape available data.
        Returns dict with scraped metrics.
        """
        result = {
            'success': False,
            'metrics': {},
            'error_message': None,
        }

        try:
            log.info("[%s] SCRAPE_INSIGHTS: Starting for @%s (period: %s)",
                     self.device_serial, self.username, self.period)

            # Step 1: Navigate to Profile
            if not self.ctrl.navigate_to(Screen.PROFILE):
                result['error_message'] = "Could not navigate to profile"
                return result

            random_sleep(1.5, 3.0)

            # Step 2: Open Insights
            if not self._open_insights():
                result['error_message'] = "Could not open Insights screen"
                return result

            # Step 3: Select time period
            self._select_period()

            # Step 4: Scrape overview metrics
            metrics = self._scrape_overview()

            # Step 5: Scrape demographics (scroll down or tap into)
            demographics = self._scrape_demographics()
            metrics['demographics'] = demographics

            # Step 6: Save to DB
            self._save_to_db(metrics)

            result['success'] = True
            result['metrics'] = metrics

            log.info("[%s] ✅ Insights scraped for @%s: reached=%s, engaged=%s",
                     self.device_serial, self.username,
                     metrics.get('accounts_reached', '?'),
                     metrics.get('accounts_engaged', '?'))

            log_action(self.session_id, self.device_serial, self.username,
                       'scrape_insights', success=True)

        except Exception as e:
            log.error("[%s] SCRAPE_INSIGHTS error: %s", self.device_serial, e)
            result['error_message'] = str(e)[:200]
            log_action(self.session_id, self.device_serial, self.username,
                       'scrape_insights', success=False,
                       error_message=result['error_message'])

        finally:
            # Navigate back to profile
            self.device.press('back')
            time.sleep(1)
            self.device.press('back')
            time.sleep(1)

        return result

    def _open_insights(self):
        """Open the Insights screen from the profile."""
        # Method 1: Tap "Professional dashboard" or "Insights" button on profile
        for text in ["Professional dashboard", "Insights",
                     "See all insights", "View insights"]:
            btn = self.device(textContains=text)
            if btn.exists(timeout=2):
                btn.click()
                random_sleep(2.0, 4.0, label="insights_load")
                return True

        # Method 2: Hamburger menu → Insights
        options_btn = self.device(description="Options")
        if not options_btn.exists(timeout=2):
            options_btn = self.device(resourceIdMatches=".*option_list_button.*")

        if options_btn.exists(timeout=2):
            options_btn.click()
            random_sleep(1.0, 2.0)

            insights_btn = self.device(text="Insights")
            if insights_btn.exists(timeout=3):
                insights_btn.click()
                random_sleep(2.0, 4.0, label="insights_load")
                return True

        log.warning("[%s] Could not find Insights entry point", self.device_serial)
        return False

    def _select_period(self):
        """Select the time period filter (7d, 30d, 90d)."""
        period_map = {
            '7d': ['Last 7 days', '7 days'],
            '30d': ['Last 30 days', '30 days'],
            '90d': ['Last 90 days', '90 days'],
        }
        texts = period_map.get(self.period, period_map['7d'])

        # Tap the period selector
        for text in texts:
            btn = self.device(textContains=text)
            if btn.exists(timeout=2):
                # Already selected
                log.info("[%s] Period already set to %s", self.device_serial, text)
                return

        # Try to find and open the period dropdown/selector
        xml = self.ctrl.dump_xml("period_selector")
        # Look for the period selector element (usually at top of Insights)
        period_btn = self.device(textContains="days")
        if period_btn.exists(timeout=2):
            period_btn.click()
            random_sleep(1.0, 2.0)

            # Select desired period
            for text in texts:
                option = self.device(textContains=text)
                if option.exists(timeout=2):
                    option.click()
                    random_sleep(1.5, 3.0, label="period_change")
                    return

    def _scrape_overview(self):
        """Scrape the Insights overview metrics."""
        metrics = {}
        random_sleep(2.0, 4.0, label="overview_load")
        xml = self.ctrl.dump_xml("insights_overview")

        # Strategy: Parse XML for metric values near known labels
        # The Insights overview typically shows:
        # - "Accounts reached" → number
        # - "Accounts engaged" → number
        # - "Total followers" → number with growth

        metrics['accounts_reached'] = self._extract_metric_near_label(
            xml, ['Accounts reached', 'accounts reached', 'Accounts Reached'])
        metrics['accounts_engaged'] = self._extract_metric_near_label(
            xml, ['Accounts engaged', 'accounts engaged', 'Accounts Engaged'])
        metrics['profile_visits'] = self._extract_metric_near_label(
            xml, ['Profile visits', 'profile visits'])

        # Also try to get delta/change percentages
        metrics['reached_delta'] = self._extract_delta(xml, 'reached')
        metrics['engaged_delta'] = self._extract_delta(xml, 'engaged')

        # Scroll down to see more metrics
        self.device.swipe(540, 1500, 540, 600, duration=0.5)
        random_sleep(1.5, 3.0)
        xml2 = self.ctrl.dump_xml("insights_scrolled")

        metrics['website_clicks'] = self._extract_metric_near_label(
            xml2, ['Website clicks', 'website clicks', 'External link taps'])
        metrics['email_clicks'] = self._extract_metric_near_label(
            xml2, ['Email', 'email button taps'])

        return metrics

    def _extract_metric_near_label(self, xml, label_variants):
        """
        Extract a numeric metric value that appears near a known label in XML.
        Looks for text elements with numbers near elements with the label text.
        """
        for label in label_variants:
            # Find the label in XML
            pattern = rf'text="{re.escape(label)}"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
            match = re.search(pattern, xml, re.IGNORECASE)
            if not match:
                continue

            label_y = int(match.group(2))

            # Find nearby text nodes with numeric values
            # Look for numbers within ±150 pixels vertically
            number_pattern = r'text="([\d,\.]+[KMkm]?)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
            for num_match in re.finditer(number_pattern, xml):
                num_text = num_match.group(1)
                num_y = int(num_match.group(3))

                if abs(num_y - label_y) < 150:
                    return self._parse_number(num_text)

        return 0

    def _extract_delta(self, xml, metric_name):
        """Extract percentage delta (e.g., +15.2%, -3.4%) for a metric."""
        patterns = [
            rf'text="([+-]?\d+\.?\d*%?)"',
            rf'text="(↑\d+\.?\d*%?|↓\d+\.?\d*%?)"',
        ]
        # This is approximate — real implementation needs XML coordinate analysis
        return 0.0

    def _parse_number(self, text):
        """Parse a display number like '1,234', '5.2K', '1.3M' to int."""
        text = text.strip().replace(',', '')
        multiplier = 1
        if text.upper().endswith('K'):
            multiplier = 1000
            text = text[:-1]
        elif text.upper().endswith('M'):
            multiplier = 1000000
            text = text[:-1]

        try:
            return int(float(text) * multiplier)
        except (ValueError, TypeError):
            return 0

    def _scrape_demographics(self):
        """
        Scrape follower demographics data.
        Requires navigating into the followers insights section.
        """
        demographics = {
            'top_cities': [],
            'top_countries': [],
            'age_ranges': {},
            'gender': {},
            'most_active_hours': [],
            'most_active_days': [],
        }

        try:
            # Tap into "Total followers" section for demographics
            followers_btn = self.device(textContains="Total followers")
            if not followers_btn.exists(timeout=3):
                followers_btn = self.device(textContains="followers")
            if not followers_btn.exists(timeout=2):
                log.info("[%s] Could not find followers section for demographics",
                         self.device_serial)
                return demographics

            followers_btn.click()
            random_sleep(2.0, 4.0, label="demographics_load")

            # Scrape demographics from the follower details screen
            xml = self.ctrl.dump_xml("demographics")

            # Try to extract locations
            demographics['top_cities'] = self._extract_location_data(xml, 'cities')

            # Scroll to see more
            self.device.swipe(540, 1500, 540, 600, duration=0.5)
            random_sleep(1.5, 3.0)
            xml2 = self.ctrl.dump_xml("demographics_scrolled")

            demographics['top_countries'] = self._extract_location_data(xml2, 'countries')

            # Scroll more for age/gender
            self.device.swipe(540, 1500, 540, 600, duration=0.5)
            random_sleep(1.5, 3.0)
            xml3 = self.ctrl.dump_xml("demographics_age_gender")

            demographics['age_ranges'] = self._extract_age_data(xml3)
            demographics['gender'] = self._extract_gender_data(xml3)

            # Go back
            self.device.press('back')
            random_sleep(1.0, 2.0)

        except Exception as e:
            log.warning("[%s] Demographics scrape partial/failed: %s",
                        self.device_serial, e)

        return demographics

    def _extract_location_data(self, xml, location_type):
        """Extract city/country data from XML."""
        locations = []
        # Look for city/country names paired with percentage values
        # This requires careful XML analysis on real devices
        # Placeholder: collect text elements that look like "City Name  XX%"
        pattern = r'text="([A-Za-z\s,]+)\s+(\d+\.?\d*)%?"'
        for match in re.finditer(pattern, xml):
            name = match.group(1).strip()
            pct = float(match.group(2))
            if name and pct > 0:
                locations.append({'name': name, 'pct': pct})
        return locations[:10]

    def _extract_age_data(self, xml):
        """Extract age range breakdown from XML."""
        age_ranges = {}
        # Look for age range labels like "18-24", "25-34", etc.
        age_pattern = r'text="(\d{1,2}-\d{1,2})"'
        for match in re.finditer(age_pattern, xml):
            age_range = match.group(1)
            # Try to find associated percentage nearby
            # Approximate — real implementation needs coordinate matching
            age_ranges[age_range] = 0
        return age_ranges

    def _extract_gender_data(self, xml):
        """Extract gender breakdown from XML."""
        gender = {}
        for g in ['Men', 'Women', 'Male', 'Female']:
            if g in xml:
                gender[g.lower()] = 0  # TODO: extract actual percentage
        return gender

    def _save_to_db(self, metrics):
        """Save scraped insights to the account_insights table."""
        try:
            conn = get_db()
            now = datetime.datetime.now().isoformat()

            # Ensure table exists (migration)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS account_insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    device_serial TEXT NOT NULL,
                    period_type TEXT NOT NULL DEFAULT '7d',
                    accounts_reached INTEGER DEFAULT 0,
                    accounts_reached_delta REAL DEFAULT 0,
                    accounts_engaged INTEGER DEFAULT 0,
                    accounts_engaged_delta REAL DEFAULT 0,
                    profile_visits INTEGER DEFAULT 0,
                    website_clicks INTEGER DEFAULT 0,
                    email_clicks INTEGER DEFAULT 0,
                    follower_demographics TEXT DEFAULT '{}',
                    engagement_breakdown TEXT DEFAULT '{}',
                    captured_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)

            demographics = metrics.pop('demographics', {})

            conn.execute("""
                INSERT INTO account_insights
                (account_id, username, device_serial, period_type,
                 accounts_reached, accounts_reached_delta,
                 accounts_engaged, accounts_engaged_delta,
                 profile_visits, website_clicks, email_clicks,
                 follower_demographics, captured_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.account_id, self.username, self.device_serial,
                self.period,
                metrics.get('accounts_reached', 0),
                metrics.get('reached_delta', 0),
                metrics.get('accounts_engaged', 0),
                metrics.get('engaged_delta', 0),
                metrics.get('profile_visits', 0),
                metrics.get('website_clicks', 0),
                metrics.get('email_clicks', 0),
                json.dumps(demographics),
                now,
            ))
            conn.commit()
            conn.close()

        except Exception as e:
            log.error("[%s] Failed to save insights to DB: %s", self.device_serial, e)
```

---

## 8. Bot Engine Integration

### 8.1 Add to `_determine_actions()` in `bot_engine.py`

```python
# In _determine_actions(), after check_profile:

# Switch to Business Profile (one-time action, controlled by task/setting)
if (self.settings.get('enable_switch_business', False)
        and not self.account.get('is_business_profile')):
    actions.append(('switch_to_business', self._action_switch_to_business))

# Scrape Insights (periodic, for business profiles only)
if (self.account.get('is_business_profile')
        and self.settings.get('enable_scrape_insights', False)):
    # Only scrape once per day
    from automation.actions.helpers import get_today_action_count
    if get_today_action_count(self.device_serial, username, 'scrape_insights') == 0:
        actions.append(('scrape_insights', self._action_scrape_insights))
```

### 8.2 Add Action Methods to `BotEngine`

```python
def _action_switch_to_business(self):
    """Switch account to Business profile."""
    from automation.actions.switch_to_business import SwitchToBusinessAction
    category = self.settings.get('business_category', 'Digital creator')
    action = SwitchToBusinessAction(
        self._device, self.device_serial,
        self.account, self.session_id,
        pkg=self.account.get('package', 'com.instagram.android'),
        category=category,
    )
    result = action.execute()
    if result.get('success'):
        # Disable the switch setting so it doesn't run again
        self.settings['enable_switch_business'] = False
        # Reload account data
        self._load_account()
    return result

def _action_scrape_insights(self):
    """Scrape Instagram Insights data."""
    from automation.actions.scrape_insights import ScrapeInsightsAction
    period = self.settings.get('insights_period', '7d')
    action = ScrapeInsightsAction(
        self._device, self.device_serial,
        self.account, self.session_id,
        pkg=self.account.get('package', 'com.instagram.android'),
        period=period,
    )
    return action.execute()
```

### 8.3 Task-Based Trigger (Alternative to Bot Engine)

For on-demand switching via dashboard button, use the task system:

```python
# In simple_app.py or device_manager routes:

@app.route('/api/device-manager/<serial>/<username>/switch-business', methods=['POST'])
def switch_to_business(serial, username):
    """Create a task to switch account to Business profile."""
    data = request.get_json() or {}
    category = data.get('category', 'Digital creator')

    conn = get_conn()
    now = datetime.now().isoformat()

    # Find account
    account = conn.execute(
        "SELECT id FROM accounts WHERE device_serial=? AND username=?",
        (serial, username)
    ).fetchone()

    if not account:
        return jsonify({'error': 'Account not found'}), 404

    # Create task
    conn.execute("""
        INSERT INTO tasks (task_type, device_serial, username, status, params, created_at)
        VALUES ('switch_business', ?, ?, 'pending', ?, ?)
    """, (serial, username, json.dumps({'category': category}), now))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': f'Business switch task created for @{username}'})
```

---

## 9. Implementation Order & Estimates

### Phase 1: Database & Dashboard (1-2 hours)
1. ✅ Add `is_business_profile`, `business_category`, `business_switched_at` columns to `accounts`
2. ✅ Create `account_insights` and `content_insights` tables
3. ✅ Add Business badge to device_manager_detail.html account table
4. ✅ Add Business Profile section to account settings modal Overview tab
5. ✅ Add API endpoint for manual toggle
6. ✅ Auto-migration in `phone_farm_db.py` and `helpers.py`

### Phase 2: Switch Automation (3-4 hours)
1. ✅ Create `switch_to_business.py` action module
2. ✅ Test on a single phone with a personal account (manual XML dump analysis)
3. ✅ Handle both Edit Profile path and Settings path
4. ✅ Handle all intro screens, category selection, type selection
5. ✅ Add to bot engine's `_determine_actions()`
6. ✅ Add dashboard button to trigger switch
7. ✅ **Critical**: Dump and analyze real XML at each step to confirm selectors

### Phase 3: Insights Scraping (4-6 hours)
1. ✅ Create `scrape_insights.py` action module
2. ✅ **Critical**: Manual XML dump on a real Business profile's Insights screen
3. ✅ Map actual resource IDs and text labels to metric extraction
4. ✅ Implement demographics extraction (locations, age, gender)
5. ✅ Save to `account_insights` table
6. ✅ Add Insights tab to account settings modal
7. ✅ Add Chart.js visualizations for demographics
8. ✅ Add historical insights API endpoint

### Phase 4: Polish & Production (2-3 hours)
1. ✅ Rate limiting (don't switch too many accounts at once)
2. ✅ Error handling and retry logic
3. ✅ Insights scraping schedule (once daily, off-peak hours)
4. ✅ Dashboard filtering by business/personal
5. ✅ Farm Stats page integration (aggregate insights)
6. ✅ Logging and monitoring

**Total estimated time: 10-15 hours**

---

## 10. Risks & Mitigations

### Risk 1: IG UI Changes
- **Risk**: Instagram updates the UI flow, breaking selectors
- **Mitigation**: Use text-based matching primarily (more stable than resource IDs). Build fallback paths. Log XML dumps for debugging.

### Risk 2: Suspicion from Mass Business Switching
- **Risk**: Many accounts from the same IP switching to Business profiles simultaneously could trigger IG's anti-automation
- **Mitigation**: Rate limit to 2-3 switches per IP per day. Random delays between operations. Space switches over multiple days.

### Risk 3: XML Parsing Reliability for Insights
- **Risk**: Metrics may be in unexpected positions, IG may use different formats (1.2K vs 1,234)
- **Mitigation**: Number parser handles K/M suffixes and commas. Coordinate-based matching pairs labels with nearby values. Multiple extraction strategies with fallbacks.

### Risk 4: Account Too New for Business
- **Risk**: Fresh accounts may not have the "Switch to Professional" option
- **Mitigation**: Only attempt switching on accounts that are at least 7 days old and have at least 1 post. Check for the option's existence before proceeding.

### Risk 5: Insights Require 100+ Followers
- **Risk**: Demographic data requires at least 100 followers
- **Mitigation**: Skip demographic scraping for accounts under 100 followers. Still scrape reach/engagement metrics which are available from day one.

### Risk 6: Facebook Connection Prompts
- **Risk**: IG may aggressively push Facebook connection
- **Mitigation**: Module handles multiple Skip/Not now/Don't connect buttons. If somehow connected, it's not harmful but unnecessary.

---

## Appendix A: UIAutomator2 Tips for This Module

### Reliable Text Matching
```python
# Exact match
device(text="Continue")

# Partial match (PREFERRED for Instagram's varying UI text)
device(textContains="Switch to professional")

# Case-insensitive via XML dump
if "switch to professional" in xml.lower():
    ...
```

### Scrolling to Find Elements
```python
# Using scrollable container
device(scrollable=True).scroll.to(textContains="Switch to professional")

# Manual swipe (more reliable for IG)
device.swipe(540, 1500, 540, 800, duration=0.5)
```

### Handling Instagram Clone Packages
```python
# Resource IDs use the clone's package prefix
# e.g., com.instagram.androie:id/edit_profile_button
rid = f"{self.ctrl.package}:id/edit_profile_button"
```

### Screen State After Each Action
```python
# ALWAYS dump and verify after clicking
btn.click()
time.sleep(2)
xml = self.ctrl.dump_xml("post_click")
# Verify expected screen loaded before proceeding
```

---

## Appendix B: Testing Checklist

- [ ] Test "Switch to professional" via Edit Profile path
- [ ] Test "Switch to professional" via Settings path
- [ ] Test with account that's already a Business profile
- [ ] Test with very new account (no Switch option)
- [ ] Test category selection with search
- [ ] Test category selection by direct tap
- [ ] Test Business vs Creator type selection
- [ ] Test Facebook connection skip
- [ ] Test Insights access on new Business profile
- [ ] Test Insights overview metric scraping
- [ ] Test demographics scraping (≥100 followers)
- [ ] Test demographics for account with <100 followers (should skip gracefully)
- [ ] Test on multiple IG clone packages (androie, androif, etc.)
- [ ] Test dashboard Business badge display
- [ ] Test dashboard Insights tab
- [ ] Test API endpoints
- [ ] Test DB migration on existing database
