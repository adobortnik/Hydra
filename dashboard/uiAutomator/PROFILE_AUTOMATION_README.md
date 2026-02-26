# Instagram Profile Automation System

Automated database-driven profile management for Instagram accounts on Android devices via ADB and uiautomator2.

## Overview

This system automates Instagram profile changes (username, bio, profile picture) across multiple devices and accounts. It uses a task queue system where you can create profile update tasks via database or API, then process them automatically.

## Features

- **Database-Driven**: All tasks stored in SQLite database for reliable queue management
- **Batch Processing**: Process multiple profile updates automatically
- **Profile Picture Library**: Manage and auto-assign profile pictures from organized library
- **Bio Templates**: Create reusable bio templates
- **Change History**: Track all profile changes with full history
- **Device Management**: Track current state of each device/account
- **API Integration**: Ready-to-integrate with your admin dashboard
- **Automated Image Transfer**: Automatically transfers images to device and selects them

## Architecture

```
profile_automation_db.py          - Database schema and operations
automated_profile_manager.py      - Main automation engine (processes tasks)
profile_task_manager.py           - Interactive CLI for managing tasks
api_integration_example.py        - API examples for dashboard integration
instagram_automation.py           - Core Instagram UI automation functions
```

## Database Schema

### Tables

1. **profile_updates**: Task queue for profile changes
2. **profile_pictures**: Library of profile pictures with metadata
3. **bio_templates**: Reusable bio text templates
4. **profile_history**: Complete history of all changes
5. **device_accounts**: Current state tracking for each device

## Setup

### 1. Install Dependencies

```bash
pip install uiautomator2
```

### 2. Initialize Database

```bash
python profile_automation_db.py
```

This creates:
- `profile_automation.db` - SQLite database
- `profile_pictures/` - Directory structure for images
  - `profile_pictures/male/`
  - `profile_pictures/female/`
  - `profile_pictures/neutral/`
  - `profile_pictures/uploaded/`

### 3. Add Profile Pictures

Put your profile picture images in the `profile_pictures/` folder (organized by gender), or use the task manager:

```bash
python profile_task_manager.py
# Select option 3: Add profile picture to library
```

### 4. Add Bio Templates (Optional)

```bash
python profile_task_manager.py
# Select option 5: Add bio template
```

## Usage

### Method 1: Interactive Task Manager (Easiest)

```bash
python profile_task_manager.py
```

Menu options:
1. Add new profile update task (step-by-step wizard)
2. View pending tasks
3. Add profile picture to library
4. View profile pictures
5. Add bio template
6. View bio templates
7. View device account info
8. Initialize database

### Method 2: Python API (For Integration)

```python
from profile_automation_db import add_profile_update_task

# Create a task
task_id = add_profile_update_task(
    device_serial="192.168.101.107_5555",
    instagram_package="com.instagram.android",
    username="current_username",
    new_username="new_username_123",
    new_bio="My new Instagram bio text here",
    profile_picture_id=1  # ID from profile_pictures table
)

print(f"Task created: {task_id}")
```

### Method 3: Bulk Updates via API

```python
from api_integration_example import ProfileAutomationAPI

api = ProfileAutomationAPI()

# Create multiple tasks at once
devices_data = [
    {
        'device_serial': '192.168.101.107_5555',
        'instagram_package': 'com.instagram.android',
        'new_username': 'user1',
        'new_bio': 'Bio for user 1',
        'profile_picture_id': 1
    },
    {
        'device_serial': '192.168.101.108_5555',
        'instagram_package': 'com.instagram.androide',
        'new_username': 'user2',
        'new_bio': 'Bio for user 2',
        'profile_picture_id': 2
    }
]

results = api.create_bulk_update_tasks(devices_data)
print(f"Created {len(results['success'])} tasks")
```

### Method 4: Auto-Assign Random Profiles

```python
from api_integration_example import ProfileAutomationAPI

api = ProfileAutomationAPI()

# Automatically assign random profile pictures and bios
device_serials = [
    '192.168.101.115_5555',
    '192.168.101.116_5555',
    '192.168.101.155_5555'
]

results = api.create_random_profile_updates(device_serials)
```

## Processing Tasks

Once you've created tasks, run the automation processor:

```bash
python automated_profile_manager.py
```

This will:
1. Load all pending tasks from database
2. For each task:
   - Connect to the device
   - Open Instagram
   - Navigate to profile edit screen
   - Change profile picture (if specified)
   - Change username (if specified)
   - Change bio (if specified)
   - Save changes
   - Update database with results
3. Generate summary report

The processor handles each task completely automatically - no manual intervention required!

## Workflow Example

### Complete Automation Workflow

1. **Prepare Profile Pictures**
   ```bash
   # Copy images to profile_pictures/male/ or profile_pictures/female/
   # Or use task manager to add them
   python profile_task_manager.py  # Option 3
   ```

2. **Create Bio Templates**
   ```bash
   python profile_task_manager.py  # Option 5
   # Add templates like:
   # "🌟 Living my best life | 📸 Photography | ✨ DM for collabs"
   ```

3. **Create Tasks**
   ```bash
   # Option A: Interactive
   python profile_task_manager.py  # Option 1

   # Option B: Programmatic
   python api_integration_example.py  # See examples
   ```

4. **Process All Tasks**
   ```bash
   python automated_profile_manager.py
   ```

5. **Monitor Results**
   ```bash
   python profile_task_manager.py  # Option 2 (View pending tasks)
   ```

## Integration with Admin Dashboard

### Flask Route Example

Add to your `simple_app.py`:

```python
from api_integration_example import ProfileAutomationAPI

profile_api = ProfileAutomationAPI()

@app.route('/api/profile_automation/bulk_update', methods=['POST'])
def bulk_profile_update():
    data = request.get_json()
    devices_data = data.get('devices', [])

    results = profile_api.create_bulk_update_tasks(devices_data)

    return jsonify({
        'status': 'success',
        'results': results
    })

@app.route('/api/profile_automation/auto_update', methods=['POST'])
def auto_profile_update():
    data = request.get_json()
    device_serials = data.get('device_serials', [])

    results = profile_api.create_random_profile_updates(device_serials)

    return jsonify({
        'status': 'success',
        'results': results
    })
```

### Frontend Integration Example

```javascript
// One-click profile automation from your dashboard
async function automateProfiles(deviceSerials) {
    const response = await fetch('/api/profile_automation/auto_update', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            device_serials: deviceSerials
        })
    });

    const result = await response.json();
    console.log(`Created ${result.results.success.length} tasks`);

    // Then run the automation processor
    // You can trigger this via subprocess or manual run
}
```

## Advanced Features

### Change Tracking

All changes are logged in `profile_history` table:

```python
from profile_automation_db import get_db_connection

conn = get_db_connection("profile_automation.db")
cursor = conn.cursor()
cursor.execute("""
    SELECT * FROM profile_history
    WHERE device_serial = '192.168.101.107_5555'
    ORDER BY changed_at DESC
""")
history = cursor.fetchall()
```

### Device State Management

Track current username/bio/picture for each device:

```python
from profile_automation_db import get_device_account

account = get_device_account('192.168.101.107_5555')
print(f"Current username: {account['current_username']}")
print(f"Current bio: {account['current_bio']}")
```

### Smart Picture Assignment

Pictures track usage count, so you can prioritize unused or least-used pictures:

```python
from profile_automation_db import get_profile_pictures

# Get only unused pictures
pictures = get_profile_pictures(unused_only=True)

# Get female pictures, least used first
pictures = get_profile_pictures(gender='female')
```

## Troubleshooting

### Profile Picture Not Selecting

The automation clicks the first image in the gallery. If wrong image is selected:
- Make sure transferred image is the most recent (should appear first)
- Adjust click coordinates in `change_profile_picture_automated()` for your device
- Check gallery app layout on your device

### Username Change Failing

Instagram has strict username requirements:
- Must be unique
- Can only contain letters, numbers, periods, and underscores
- Cannot start/end with period
- Cannot have consecutive periods

### Bio Not Updating

Special characters may cause issues:
- Use plain text when possible
- Emojis usually work but test first
- Avoid quotes in bio text

### Device Connection Issues

- Ensure device is connected via ADB: `adb devices`
- Check device serial matches exactly
- For network devices: `adb connect IP:PORT`

## File Structure

```
uiAutomator/
├── instagram_automation.py          # Original automation functions
├── profile_automation_db.py         # Database layer
├── automated_profile_manager.py     # Batch processor
├── profile_task_manager.py          # Interactive manager
├── api_integration_example.py       # API integration examples
├── profile_automation.db            # SQLite database (created on init)
├── profile_pictures/                # Profile picture library
│   ├── male/
│   ├── female/
│   ├── neutral/
│   └── uploaded/
└── PROFILE_AUTOMATION_README.md     # This file
```

## Database Query Examples

### Get All Pending Tasks
```sql
SELECT * FROM profile_updates WHERE status = 'pending';
```

### Get Most Used Profile Pictures
```sql
SELECT * FROM profile_pictures ORDER BY times_used DESC LIMIT 10;
```

### Get Device Change History
```sql
SELECT * FROM profile_history
WHERE device_serial = '192.168.101.107_5555'
ORDER BY changed_at DESC;
```

### Get Failed Tasks
```sql
SELECT * FROM profile_updates WHERE status = 'failed';
```

## Best Practices

1. **Test First**: Test with 1-2 devices before batch processing
2. **Backup Database**: SQLite file is portable, backup before major changes
3. **Organize Pictures**: Use gender/category folders for easier management
4. **Monitor Logs**: Watch console output during processing for issues
5. **Rate Limiting**: Add delays between tasks if processing many accounts
6. **Username Pool**: Pre-generate username variations to avoid duplicates

## Future Enhancements

Possible additions:
- Web UI for task management
- Scheduled automation (cron/task scheduler)
- Proxy rotation for network changes
- Account verification handling
- Story/highlights automation
- Multi-threaded processing
- Email/webhook notifications

## Support

For issues or questions:
1. Check CLAUDE.md for codebase architecture
2. Review instagram_automation.py for selector patterns
3. Test selectors with `device.dump_hierarchy()` for debugging

## License

Internal tool for automation purposes.
