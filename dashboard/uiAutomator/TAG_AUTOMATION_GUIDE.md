# Tag-Based Profile Automation Guide

Complete guide for automating Instagram profile changes across multiple accounts using tags and optional AI.

## Overview

This system allows you to:
1. **Tag accounts** with labels like "chantall", "anna", "campaign_q1"
2. **Create campaigns** that define how profiles should be updated
3. **Execute with one click** - all tagged accounts get automated profile updates
4. **Use AI** (optional) to generate usernames and bios based on a "mother account"

## Quick Start - One-Click Automation

### Step 1: Initialize Database

```bash
cd uiAutomator
python profile_automation_db.py
```

### Step 2: Tag Your Accounts

```python
from tag_based_automation import TagBasedAutomation

automation = TagBasedAutomation()

# Tag all accounts with "chantall"
automation.tag_account("192.168.101.107_5555", "anna.borli", "chantall")
automation.tag_account("192.168.101.107_5555", "anna.borsn", "chantall")
automation.tag_account("192.168.101.108_5555", "anna.darso", "chantall")
```

Or bulk tag all accounts on specific devices:

```python
# Tag all accounts on these devices with "chantall"
automation.bulk_tag_accounts(
    tag_name="chantall",
    device_serials=["192.168.101.107_5555", "192.168.101.108_5555"]
)
```

### Step 3: Add Profile Pictures (Optional)

```bash
# Copy images to profile_pictures folder
cp /path/to/pictures/*.jpg uiAutomator/profile_pictures/female/

# Or use task manager
python profile_task_manager.py  # Select option 3
```

### Step 4: Create & Execute Campaign

```python
from tag_based_automation import TagBasedAutomation

automation = TagBasedAutomation()

# Create campaign
campaign_id = automation.create_campaign(
    tag_name="chantall",
    campaign_name="Chantall Profile Update",
    mother_account="chantall.main",
    use_ai=False,  # Set to True to use AI
    strategies={
        'profile_picture': 'rotate',  # Rotate through available pictures
        'bio': 'template',           # Use bio templates
        'username': 'variation'      # Generate username variations
    }
)

# Execute campaign - creates tasks for ALL tagged accounts
result = automation.execute_campaign(campaign_id)

print(f"Created {result['tasks_created']} tasks!")
```

### Step 5: Run Automation

```bash
python automated_profile_manager.py
```

That's it! All accounts tagged with "chantall" will have their profiles updated automatically.

## Dashboard Integration (One-Click from Web UI)

### Add to simple_app.py

```python
# At the top
from profile_automation_routes import profile_automation_bp

# After app creation
app.register_blueprint(profile_automation_bp)
```

### API Endpoints

#### Quick Campaign (Recommended)
```javascript
// One-click automation from your dashboard
fetch('/api/profile_automation/quick_campaign', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        tag: "chantall",
        mother_account: "chantall.main",
        mother_bio: "✨ Fashion & Lifestyle | 📍 Paris | DM for collabs",
        use_ai: false  // or true with ai_api_key
    })
})
.then(r => r.json())
.then(data => {
    console.log(`Created ${data.tasks_created} tasks!`);
    // Show success message to user
});
```

#### Tag Accounts
```javascript
// Tag a single account
fetch('/api/profile_automation/accounts/tag', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        device_serial: "192.168.101.107_5555",
        username: "anna.borli",
        tag: "chantall"
    })
});

// Bulk tag by device
fetch('/api/profile_automation/accounts/tag/bulk', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        tag: "chantall",
        device_serials: ["192.168.101.107_5555", "192.168.101.108_5555"]
    })
});
```

#### Get Tagged Accounts
```javascript
fetch('/api/profile_automation/accounts/chantall')
    .then(r => r.json())
    .then(data => {
        console.log(`Accounts with 'chantall' tag:`, data.accounts);
    });
```

## AI Integration

### With AI API Key

```python
from tag_based_automation import TagBasedAutomation

automation = TagBasedAutomation()

# Create AI-powered campaign
campaign_id = automation.create_campaign(
    tag_name="chantall",
    campaign_name="Chantall AI Campaign",
    mother_account="chantall.main",
    use_ai=True,
    ai_config={
        'api_key': 'sk-your-openai-key',
        'endpoint': 'https://api.openai.com/v1/chat/completions',
        'provider': 'openai'  # or 'anthropic'
    },
    strategies={
        'profile_picture': 'rotate',
        'bio': 'ai',       # AI generates bios based on mother account
        'username': 'ai'   # AI generates usernames based on mother account
    }
)

automation.execute_campaign(campaign_id)
```

### Via Dashboard API

```javascript
fetch('/api/profile_automation/quick_campaign', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        tag: "chantall",
        mother_account: "chantall.main",
        mother_bio: "✨ Fashion & Lifestyle | 📍 Paris",
        use_ai: true,
        ai_api_key: "sk-your-openai-key"
    })
});
```

### Test AI Generation

```python
from ai_profile_generator import CampaignAIGenerator

# Initialize with API key
generator = CampaignAIGenerator(
    api_key="sk-your-openai-key",
    provider="openai"
)

# Generate 5 complete profiles
profiles = generator.generate_campaign_profiles(
    mother_account="chantall.main",
    mother_bio="✨ Fashion & Lifestyle | 📍 Paris | DM for collabs",
    account_count=5
)

for profile in profiles:
    print(f"Username: {profile['username']}")
    print(f"Bio: {profile['bio']}\n")
```

## Advanced Usage

### Multiple Campaigns

```python
# Campaign 1: Chantall accounts
automation.create_campaign(
    tag_name="chantall",
    campaign_name="Chantall Spring 2025",
    mother_account="chantall.main",
    strategies={'bio': 'template', 'username': 'variation'}
)

# Campaign 2: Anna accounts
automation.create_campaign(
    tag_name="anna",
    campaign_name="Anna Network Expansion",
    mother_account="anna.official",
    strategies={'bio': 'ai', 'username': 'ai'}
)
```

### Custom Bio Templates

```python
from profile_automation_db import add_bio_template

# Add custom bio templates
add_bio_template(
    name="Fashion Influencer",
    bio_text="✨ Fashion & Style | 📍 Paris | DM for collabs 💌",
    category="fashion"
)

add_bio_template(
    name="Lifestyle Creator",
    bio_text="🌟 Living my best life | Content creator | ✉️ DM for partnerships",
    category="lifestyle"
)
```

### Profile Picture Strategies

- `rotate`: Cycle through pictures (picture 1 → account 1, picture 2 → account 2, etc.)
- `random`: Random assignment
- `least_used`: Prioritize least-used pictures

### Bio Strategies

- `template`: Use bio templates from database
- `ai`: Generate unique bios using AI based on mother account
- `fixed`: Use same bio for all (specify in campaign)

### Username Strategies

- `variation`: Algorithmic variations (username1, username.2, username_3, etc.)
- `ai`: AI-generated variations based on mother account style
- `manual`: Skip username changes

## Complete Workflow Example

```python
from tag_based_automation import TagBasedAutomation
from profile_automation_db import add_bio_template, add_profile_picture
from pathlib import Path

automation = TagBasedAutomation()

# 1. Create tag
automation.create_tag("chantall_spring", "Chantall Spring Campaign 2025")

# 2. Bulk tag accounts
automation.bulk_tag_accounts(
    tag_name="chantall_spring",
    device_serials=[
        "192.168.101.107_5555",
        "192.168.101.108_5555",
        "192.168.101.115_5555"
    ]
)

# 3. Add bio templates
add_bio_template(
    "Spring Fashion",
    "🌸 Spring Vibes | Fashion & Lifestyle | 📍 Paris",
    "seasonal"
)

# 4. Add profile pictures
pics_dir = Path("profile_pictures/female")
for pic in pics_dir.glob("*.jpg"):
    add_profile_picture(
        filename=pic.name,
        original_path=str(pic),
        gender="female",
        category="spring"
    )

# 5. Create campaign
campaign_id = automation.create_campaign(
    tag_name="chantall_spring",
    campaign_name="Spring 2025 Launch",
    mother_account="chantall.main",
    use_ai=True,  # Use AI if you have API key
    ai_config={'api_key': 'sk-...'},
    strategies={
        'profile_picture': 'rotate',
        'bio': 'ai',
        'username': 'variation'
    }
)

# 6. Execute
result = automation.execute_campaign(campaign_id)
print(f"✓ Created {result['tasks_created']} profile update tasks")

# 7. View pending tasks
from profile_automation_db import get_pending_tasks
tasks = get_pending_tasks()
for task in tasks:
    print(f"  - {task['username']} on {task['device_serial']}")

# 8. Run automation
print("\nNow run: python automated_profile_manager.py")
```

## Dashboard UI Integration Example

### HTML/JavaScript Frontend

```html
<!-- Tag Management -->
<div class="tag-automation">
    <h3>Tag-Based Profile Automation</h3>

    <!-- Create Tag -->
    <input type="text" id="tagName" placeholder="Tag name (e.g., chantall)">
    <button onclick="createTag()">Create Tag</button>

    <!-- Tag Accounts -->
    <select id="deviceSelect" multiple>
        <!-- Populated from your device list -->
    </select>
    <button onclick="bulkTagDevices()">Tag All Accounts on Selected Devices</button>

    <!-- Quick Campaign -->
    <div class="quick-campaign">
        <h4>One-Click Campaign</h4>
        <input type="text" id="motherAccount" placeholder="Mother account (e.g., chantall.main)">
        <input type="text" id="motherBio" placeholder="Mother account bio">
        <label><input type="checkbox" id="useAI"> Use AI Generation</label>
        <input type="text" id="aiKey" placeholder="OpenAI API Key (if using AI)">
        <button onclick="runQuickCampaign()">🚀 Automate All Tagged Accounts</button>
    </div>

    <div id="results"></div>
</div>

<script>
function createTag() {
    const tagName = document.getElementById('tagName').value;

    fetch('/api/profile_automation/tags', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: tagName})
    })
    .then(r => r.json())
    .then(data => {
        alert(`Tag '${tagName}' created!`);
    });
}

function bulkTagDevices() {
    const tagName = document.getElementById('tagName').value;
    const devices = Array.from(document.getElementById('deviceSelect').selectedOptions)
        .map(opt => opt.value);

    fetch('/api/profile_automation/accounts/tag/bulk', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            tag: tagName,
            device_serials: devices
        })
    })
    .then(r => r.json())
    .then(data => {
        alert(`Tagged ${data.tagged_count} accounts!`);
    });
}

function runQuickCampaign() {
    const tag = document.getElementById('tagName').value;
    const motherAccount = document.getElementById('motherAccount').value;
    const motherBio = document.getElementById('motherBio').value;
    const useAI = document.getElementById('useAI').checked;
    const aiKey = document.getElementById('aiKey').value;

    fetch('/api/profile_automation/quick_campaign', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            tag: tag,
            mother_account: motherAccount,
            mother_bio: motherBio,
            use_ai: useAI,
            ai_api_key: useAI ? aiKey : null
        })
    })
    .then(r => r.json())
    .then(data => {
        document.getElementById('results').innerHTML = `
            <div class="success">
                ✓ Campaign created! ${data.tasks_created} profile update tasks queued.
                <br>Tasks will be executed when you run automated_profile_manager.py
            </div>
        `;
    });
}
</script>
```

## Troubleshooting

### No accounts found with tag
- Check if accounts are properly tagged: `automation.get_accounts_by_tag("chantall")`
- Verify device folders exist in your directory structure

### AI generation not working
- Verify API key is correct
- Check internet connection
- Falls back to algorithmic generation if AI fails

### Profile pictures not selecting correctly
- Ensure pictures are in `profile_pictures/` folder
- Check permissions on image files
- Add pictures to database using `add_profile_picture()`

### Tasks not executing
- Run `python automated_profile_manager.py`
- Check device connections: `adb devices`
- Review error logs in automation output

## Database Schema

```sql
-- Tags
tags (id, name, description, created_at)

-- Account-Tag mapping
account_tags (id, device_serial, username, tag_id, assigned_at)

-- Campaigns
tag_campaigns (id, tag_id, name, mother_account, use_ai, strategies, status)

-- Profile Pictures
profile_pictures (id, filename, original_path, gender, category, times_used)

-- Bio Templates
bio_templates (id, name, bio_text, category, times_used)

-- Profile Update Tasks
profile_updates (id, device_serial, instagram_package, new_username, new_bio, profile_picture_id, status)
```

## File Structure

```
uiAutomator/
├── tag_based_automation.py         # Tag system & campaigns
├── ai_profile_generator.py         # AI integration
├── automated_profile_manager.py    # Automation executor
├── profile_automation_db.py        # Database layer
├── profile_automation.db           # SQLite database
└── profile_pictures/               # Profile picture library
    ├── male/
    ├── female/
    └── neutral/

the-livehouse-dashboard/
└── profile_automation_routes.py    # Flask API routes
```

## Best Practices

1. **Test with small batches first** - Tag 2-3 accounts, run campaign, verify results
2. **Use descriptive tag names** - "chantall_spring_2025" instead of "cs"
3. **Organize profile pictures** - Use gender/category folders
4. **Keep mother account info updated** - Accurate bio helps AI generation
5. **Monitor task execution** - Watch console output during automation
6. **Backup database** - Copy `profile_automation.db` before major changes

## Next Steps

1. Set up your first tag and tag some accounts
2. Add profile pictures to the library
3. Create and execute a test campaign with 2-3 accounts
4. Integrate into your dashboard for one-click automation
5. (Optional) Add AI API key for intelligent username/bio generation

For the full system overview, see `PROFILE_AUTOMATION_README.md`.
