# Instagram Login Automation System

Complete automation system for Instagram account logins with 2FA support, batch processing, and dashboard integration.

**Created:** 2025-11-21
**Version:** 1.0.0

---

## Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Architecture](#architecture)
4. [Installation](#installation)
5. [Quick Start](#quick-start)
6. [Components](#components)
7. [Usage Guide](#usage-guide)
8. [API Reference](#api-reference)
9. [Database Schema](#database-schema)
10. [Troubleshooting](#troubleshooting)

---

## Overview

The Instagram Login Automation System automates the login process for Instagram accounts across multiple devices and packages (including clones). It handles:

- **Signup vs. Login Screen Detection**: Automatically detects and navigates between screens
- **Credential Entry**: Robust username/password input with retry logic
- **2FA Support**: Integrates with 2fa.live for SMS code retrieval
- **Post-Login Prompts**: Handles "Save Login Info" and notification prompts
- **Challenge Detection**: Identifies when manual intervention is needed
- **Batch Processing**: Process multiple accounts across multiple devices
- **Dashboard Control**: Full REST API for UI integration

This system follows the **exact same patterns** as the profile automation system, ensuring consistency and maintainability.

---

## Features

### Core Features

- ✅ **Multi-Device Support**: Process accounts on multiple devices simultaneously
- ✅ **Instagram Clone Support**: Works with com.instagram.android, androide-androidp, etc.
- ✅ **2FA Integration**: Automatic SMS code retrieval from 2fa.live
- ✅ **Smart Screen Detection**: Handles signup screens, login screens, already-logged-in states
- ✅ **Challenge Detection**: Identifies verification screens requiring manual intervention
- ✅ **Batch Processing**: Queue-based system for automated login of many accounts
- ✅ **Retry Logic**: Configurable retry attempts for transient failures
- ✅ **Audit Trail**: Complete history of all login attempts
- ✅ **Dashboard Integration**: Full REST API for UI control
- ✅ **CLI Management**: Interactive command-line interface

### Advanced Features

- **Priority Queue**: Higher priority tasks execute first
- **Device Grouping**: Tasks automatically grouped by device for efficient processing
- **2FA Token Management**: Store and reuse tokens for multiple accounts
- **Statistics Dashboard**: Success rates, recent activity, task counts
- **Error Categorization**: Failed vs. needs manual intervention
- **Automatic Cleanup**: Clear old completed tasks

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                   LOGIN AUTOMATION SYSTEM                    │
└─────────────────────────────────────────────────────────────┘

┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  Database Layer  │  │  Core Logic      │  │  2FA Client      │
│                  │  │                  │  │                  │
│  login_          │  │  login_          │  │  two_fa_live_    │
│  automation_db   │  │  automation      │  │  client          │
└──────────────────┘  └──────────────────┘  └──────────────────┘

┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  Batch Processor │  │  CLI Manager     │  │  API Routes      │
│                  │  │                  │  │                  │
│  automated_      │  │  login_task_     │  │  login_          │
│  login_manager   │  │  manager         │  │  automation_     │
│                  │  │                  │  │  routes          │
└──────────────────┘  └──────────────────┘  └──────────────────┘

                    ┌──────────────────┐
                    │  Dashboard UI    │
                    │                  │
                    │  simple_app.py   │
                    └──────────────────┘
```

### Data Flow

```
1. Create Tasks
   ├─ Manual (CLI)
   ├─ API (Dashboard)
   └─ Bulk (Device/Tags)
        ↓
2. Task Queue (pending status)
        ↓
3. Batch Processor
   ├─ Connect to device
   ├─ Open Instagram
   ├─ Detect screen state
   ├─ Handle signup screen (if needed)
   ├─ Enter credentials
   ├─ Handle 2FA (if needed)
   ├─ Handle post-login prompts
   └─ Verify login success
        ↓
4. Update Task Status
   ├─ completed
   ├─ failed
   └─ needs_manual
        ↓
5. Log to History (audit trail)
```

---

## Installation

### Prerequisites

- Python 3.8+
- Android device with USB debugging enabled
- ADB installed and accessible
- Instagram app(s) installed on device
- uiautomator2 installed on device

### Install Dependencies

```bash
cd uiAutomator
pip install -r requirements.txt
```

**Required packages:**
- `uiautomator2` (UIAutomator device control)
- `requests` (HTTP client for 2fa.live)
- `sqlite3` (built-in, database)
- `flask` (for dashboard API)

### Initialize Database

```bash
python login_automation_db.py
```

This creates `login_automation.db` with all required tables.

### Verify Installation

```bash
# Test device connection
python login_automation.py 10.1.10.183_5555 testuser testpass

# Test 2FA client
python two_fa_live_client.py YOUR_2FA_TOKEN

# Launch CLI manager
python login_task_manager.py
```

---

## Quick Start

### Method 1: CLI (Interactive)

```bash
# Launch interactive CLI
python login_task_manager.py

# Follow menu:
# 1. Create login task
# 2. View tasks
# 3. Process tasks
```

### Method 2: Python Script

```python
from login_automation_db import create_login_task
from automated_login_manager import AutomatedLoginManager

# Create a task
task_id = create_login_task(
    device_serial="10.1.10.183_5555",
    instagram_package="com.instagram.androim",
    username="testuser",
    password="testpass123",
    two_fa_token="CHN44RHFYSYPFCKLL2C5CFHNTY54PYOD"  # Optional
)

# Process all pending tasks
manager = AutomatedLoginManager()
stats = manager.run_batch_processor()

print(f"Successful: {stats['successful']}")
print(f"Failed: {stats['failed']}")
```

### Method 3: Dashboard API

```bash
# Create task
curl -X POST http://localhost:5000/api/login/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "device_serial": "10.1.10.183_5555",
    "instagram_package": "com.instagram.androim",
    "username": "testuser",
    "password": "testpass123",
    "two_fa_token": "CHN44RHFY..."
  }'

# Process all tasks
curl -X POST http://localhost:5000/api/login/tasks/process
```

### Method 4: Direct Login (No Task)

```bash
python login_automation.py 10.1.10.183_5555 testuser testpass123 com.instagram.androim CHN44RHFY...
```

---

## Components

### 1. Database Layer (`login_automation_db.py`)

Manages all database operations.

**Key Functions:**
- `init_database()` - Initialize database schema
- `create_login_task()` - Create new task
- `get_pending_login_tasks()` - Get tasks to process
- `update_task_status()` - Update task state
- `log_login_attempt()` - Record to history
- `add_2fa_token()` - Store 2FA token
- `get_statistics()` - Get system stats

**Database Tables:**
- `login_tasks` - Task queue
- `login_history` - Audit trail
- `two_factor_services` - 2FA token storage

### 2. Core Logic (`login_automation.py`)

Handles the actual login automation.

**Key Methods:**
- `connect_device()` - Connect using proven UIAutomator pattern
- `open_instagram()` - Launch Instagram app
- `detect_screen_state()` - Identify current screen
- `handle_signup_screen()` - Navigate to login from signup
- `enter_credentials()` - Input username/password
- `detect_two_factor_screen()` - Check if 2FA required
- `handle_two_factor()` - Fetch and enter 2FA code
- `handle_save_login_info()` - Handle save prompt
- `dismiss_notification_prompt()` - Skip notifications
- `verify_logged_in()` - Confirm success
- `login_account()` - Complete login flow

**Screen States:**
- `signup` - Signup screen (need to click "Log In")
- `login` - Login screen (username/password fields)
- `logged_in` - Already logged in
- `challenge` - Verification/challenge screen
- `unknown` - Cannot determine

### 3. 2FA Client (`two_fa_live_client.py`)

Fetches SMS codes from 2fa.live.

**Usage:**
```python
from two_fa_live_client import TwoFALiveClient

client = TwoFALiveClient("CHN44RHFYSYPFCKLL2C5CFHNTY54PYOD")
code = client.get_code()  # Returns "123456"
```

**Features:**
- Automatic retry (SMS may take 10-60 seconds)
- Timeout handling (configurable)
- Code validation (ensures 6 digits)
- Connection testing

**API Pattern:**
```
GET https://2fa.live/tok/{TOKEN}
Response: {"token": "123456"}
```

### 4. Batch Processor (`automated_login_manager.py`)

Processes tasks from the queue.

**Usage:**
```bash
# Process all pending tasks
python automated_login_manager.py

# Process specific device
python automated_login_manager.py --device 10.1.10.183_5555

# Process single task
python automated_login_manager.py --task-id 123
```

**Features:**
- Device grouping (process one device at a time)
- Retry logic (configurable max attempts)
- Error categorization (failed vs. needs_manual)
- Progress logging
- Statistics reporting

**Processing Flow:**
1. Get pending tasks from database
2. Group by device
3. Connect to each device
4. Process all tasks for that device sequentially
5. Update task status and log results
6. Move to next device

### 5. CLI Manager (`login_task_manager.py`)

Interactive command-line interface.

**Features:**
- Create tasks manually or from device accounts
- View tasks (all, pending, completed, failed)
- Process tasks (launch batch processor)
- Manage 2FA tokens
- View statistics
- Delete tasks
- Test 2FA integration

**Usage:**
```bash
python login_task_manager.py
```

### 6. API Routes (`login_automation_routes.py`)

Flask Blueprint for dashboard integration.

**Base URL:** `/api/login`

**Key Endpoints:**
- `POST /tasks` - Create task
- `POST /tasks/bulk` - Create multiple tasks
- `POST /tasks/device/<serial>` - Create tasks for device
- `GET /tasks` - List tasks
- `POST /tasks/<id>/execute` - Execute specific task
- `POST /tasks/process` - Process all tasks
- `POST /quick_login` - Direct login (no task)
- `GET /history` - Login history
- `GET /statistics` - System stats
- `POST /2fa/tokens` - Add 2FA token
- `POST /2fa/test` - Test 2FA token

---

## Usage Guide

### Creating Login Tasks

#### From Device Accounts (Recommended)

Automatically reads accounts from device folders:

```python
from login_automation_db import create_login_task
import sqlite3
import json

device_serial = "10.1.10.183_5555"
device_path = f"../{device_serial}"

# Read accounts.db
conn = sqlite3.connect(f"{device_path}/accounts.db")
cursor = conn.cursor()
cursor.execute("SELECT account, password FROM accounts")

for username, password in cursor.fetchall():
    # Get Instagram package from settings.db
    settings_db = f"{device_path}/{username}/settings.db"
    settings_conn = sqlite3.connect(settings_db)
    settings_cursor = settings_conn.cursor()
    settings_cursor.execute("SELECT settings FROM accountsettings WHERE id = 1")
    settings_json = json.loads(settings_cursor.fetchone()[0])

    instagram_package = settings_json['app_cloner'].split('/')[0]

    # Create task
    create_login_task(
        device_serial=device_serial,
        instagram_package=instagram_package,
        username=username,
        password=password
    )
```

#### Manual Task Creation

```python
from login_automation_db import create_login_task

task_id = create_login_task(
    device_serial="10.1.10.183_5555",
    instagram_package="com.instagram.androim",
    username="testuser",
    password="testpass123",
    two_fa_token="CHN44RHFY...",  # Optional
    priority=5  # Higher = processed sooner
)
```

### Processing Tasks

#### Batch Process (All Pending)

```bash
python automated_login_manager.py
```

Or via API:
```bash
curl -X POST http://localhost:5000/api/login/tasks/process
```

#### Process Specific Device

```bash
python automated_login_manager.py --device 10.1.10.183_5555
```

#### Process Single Task

```bash
python automated_login_manager.py --task-id 123
```

### 2FA Integration

#### Add Token

```python
from login_automation_db import add_2fa_token

add_2fa_token(
    token="CHN44RHFYSYPFCKLL2C5CFHNTY54PYOD",
    username="testuser",  # Optional
    device_serial="10.1.10.183_5555",  # Optional
    phone_number="+1234567890",  # Optional
    notes="Main account 2FA"  # Optional
)
```

#### Test Token

```bash
python two_fa_live_client.py CHN44RHFYSYPFCKLL2C5CFHNTY54PYOD
```

Or via API:
```bash
curl -X POST http://localhost:5000/api/login/2fa/test \
  -H "Content-Type: application/json" \
  -d '{"token": "CHN44RHFY..."}'
```

### Viewing Tasks and History

#### CLI

```bash
python login_task_manager.py
# Select: 2. View tasks
# Select: 5. View statistics
```

#### Python

```python
from login_automation_db import get_all_login_tasks, get_login_history, get_statistics

# Get pending tasks
tasks = get_all_login_tasks(status='pending')

# Get history
history = get_login_history(limit=50)

# Get stats
stats = get_statistics()
print(f"Success rate: {stats['success_rate']}%")
```

#### API

```bash
# Get tasks
curl http://localhost:5000/api/login/tasks?status=pending

# Get history
curl http://localhost:5000/api/login/history

# Get statistics
curl http://localhost:5000/api/login/statistics
```

---

## API Reference

### Task Management

#### POST `/api/login/tasks`
Create a login task.

**Request:**
```json
{
  "device_serial": "10.1.10.183_5555",
  "instagram_package": "com.instagram.androim",
  "username": "testuser",
  "password": "testpass123",
  "two_fa_token": "CHN44RHFY...",
  "priority": 0
}
```

**Response:**
```json
{
  "status": "success",
  "task_id": 123
}
```

#### POST `/api/login/tasks/bulk`
Create multiple tasks.

**Request:**
```json
{
  "accounts": [
    {
      "device_serial": "10.1.10.183_5555",
      "username": "user1",
      "password": "pass1",
      "instagram_package": "com.instagram.androim"
    },
    ...
  ]
}
```

#### POST `/api/login/tasks/device/<device_serial>`
Create tasks for all accounts on a device.

**Request:**
```json
{
  "two_fa_token": "CHN44RHFY...",
  "priority": 0
}
```

#### GET `/api/login/tasks`
List tasks.

**Query Params:**
- `?status=pending|completed|failed|needs_manual`
- `?device=10.1.10.183_5555`

#### POST `/api/login/tasks/<id>/execute`
Execute a specific task.

#### POST `/api/login/tasks/process`
Process all pending tasks.

**Request:**
```json
{
  "device_serial": "10.1.10.183_5555",
  "max_tasks": 10
}
```

### Quick Login

#### POST `/api/login/quick_login`
Direct login without creating a task.

**Request:**
```json
{
  "device_serial": "10.1.10.183_5555",
  "instagram_package": "com.instagram.androim",
  "username": "testuser",
  "password": "testpass123",
  "two_fa_token": "CHN44RHFY..."
}
```

### History and Statistics

#### GET `/api/login/history`
Get login history.

**Query Params:**
- `?device=10.1.10.183_5555`
- `?username=testuser`
- `?limit=50`

#### GET `/api/login/statistics`
Get system statistics.

**Response:**
```json
{
  "status": "success",
  "statistics": {
    "tasks": {
      "pending": 5,
      "completed": 20,
      "failed": 2
    },
    "total_attempts": 27,
    "successful_attempts": 25,
    "success_rate": 92.59,
    "active_2fa_tokens": 3,
    "recent_logins_24h": 15
  }
}
```

### 2FA Management

#### POST `/api/login/2fa/tokens`
Add a 2FA token.

#### GET `/api/login/2fa/tokens/<token>`
Get token details.

#### POST `/api/login/2fa/test`
Test a token.

**Request:**
```json
{
  "token": "CHN44RHFY..."
}
```

---

## Database Schema

### login_tasks

Task queue for login operations.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Task ID |
| device_serial | TEXT | Device identifier (e.g., "10.1.10.183_5555") |
| instagram_package | TEXT | Package name (e.g., "com.instagram.androim") |
| username | TEXT | Instagram username |
| password | TEXT | Instagram password |
| two_fa_token | TEXT | 2fa.live token (optional) |
| status | TEXT | pending/processing/completed/failed/needs_manual |
| created_at | TIMESTAMP | Task creation time |
| updated_at | TIMESTAMP | Last update time |
| completed_at | TIMESTAMP | Completion time |
| error_message | TEXT | Error details if failed |
| retry_count | INTEGER | Number of retry attempts |
| max_retries | INTEGER | Maximum retry attempts (default 3) |
| priority | INTEGER | Task priority (higher = sooner) |

**Indexes:**
- `idx_login_tasks_status` on status
- `idx_login_tasks_device` on device_serial
- `idx_login_tasks_username` on username

### login_history

Audit trail of all login attempts.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | History ID |
| device_serial | TEXT | Device identifier |
| instagram_package | TEXT | Package name |
| username | TEXT | Instagram username |
| login_type | TEXT | normal/2fa/challenge/already_logged_in |
| success | INTEGER | 1 if successful, 0 if failed |
| logged_in_at | TIMESTAMP | Attempt timestamp |
| error_details | TEXT | Error message if failed |
| two_fa_used | INTEGER | 1 if 2FA was used |
| challenge_encountered | INTEGER | 1 if challenge screen detected |

**Indexes:**
- `idx_login_history_device` on device_serial
- `idx_login_history_username` on username
- `idx_login_history_timestamp` on logged_in_at

### two_factor_services

2FA token storage.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Token ID |
| service_name | TEXT | Service name (default "2fa.live") |
| token | TEXT UNIQUE | 2fa.live token |
| phone_number | TEXT | Associated phone number |
| username | TEXT | Associated username |
| device_serial | TEXT | Associated device |
| created_at | TIMESTAMP | Token creation time |
| last_used | TIMESTAMP | Last usage time |
| usage_count | INTEGER | Number of times used |
| status | TEXT | active/inactive |
| notes | TEXT | Additional notes |

**Indexes:**
- `idx_2fa_token` on token

---

## Troubleshooting

### Common Issues

#### 1. "Failed to connect to device"

**Symptoms:**
- Task fails with "Failed to connect to device"
- UIAutomator not responsive

**Solution:**
```bash
# Check ADB connection
adb devices

# Reconnect device
adb connect 10.1.10.183:5555

# Kill and restart UIAutomator (automatic on next connection)
adb -s 10.1.10.183:5555 shell pkill -9 uiautomator
```

**Note:** The system automatically handles UIAutomator cleanup and restart using the proven pattern from `instagram_automation.py`.

#### 2. "Could not find username field"

**Symptoms:**
- Login fails at credential entry
- Cannot locate UI elements

**Solution:**
- Instagram version may have changed UI
- Add new selectors to `enter_credentials()` in `login_automation.py`
- Use `device.dump_hierarchy()` to inspect current screen

#### 3. "2FA timeout"

**Symptoms:**
- Task fails with "Could not retrieve 2FA code"
- SMS not arriving in time

**Solution:**
- Increase retry attempts in `TwoFALiveClient.get_code()`
- Check 2fa.live token is valid
- Verify phone number is correct

```python
# Test token manually
python two_fa_live_client.py YOUR_TOKEN
```

#### 4. "Challenge screen detected"

**Symptoms:**
- Task marked as "needs_manual"
- Instagram showing verification screen

**Solution:**
- This requires manual intervention
- Log into Instagram manually on the device
- Complete verification
- Retry the task

#### 5. "Already logged in" but not working

**Symptoms:**
- System reports "already logged in" but app shows login screen

**Solution:**
- Clear Instagram app data/cache
- Force stop Instagram
- Retry login task

### Debug Mode

Enable verbose logging:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
```

### Inspect Screen State

```python
from login_automation import LoginAutomation

login = LoginAutomation("10.1.10.183_5555")
login.connect_device()
login.open_instagram("com.instagram.androim")

# Check screen state
state = login.detect_screen_state()
print(f"Screen state: {state}")

# Dump hierarchy for inspection
xml = login.device.dump_hierarchy()
print(xml)
```

---

## Best Practices

### 1. Task Priority

Use priority to control execution order:
- High priority (10+): Important accounts
- Normal priority (0): Regular accounts
- Low priority (-1 to -10): Test accounts

### 2. Retry Configuration

Adjust max_retries based on error type:
- Network issues: 3-5 retries
- Wrong credentials: 0 retries (will always fail)
- 2FA timeout: 2-3 retries

### 3. Batch Processing

Group tasks by device for efficiency:
```python
# Process one device at a time
python automated_login_manager.py --device 10.1.10.183_5555
```

### 4. 2FA Token Management

Store tokens with clear notes:
```python
add_2fa_token(
    token="CHN44RHFY...",
    username="testuser",
    notes="Main account - expires 2025-12-31"
)
```

### 5. Error Monitoring

Regularly check failed tasks:
```python
failed_tasks = get_all_login_tasks(status='failed')
manual_tasks = get_all_login_tasks(status='needs_manual')
```

---

## Integration with Profile Automation

The login automation integrates seamlessly with the existing profile automation system:

1. **Login accounts first** using login automation
2. **Create profile update campaign** using tag-based automation
3. **Execute profile changes** using profile automation

**Example workflow:**
```python
# Step 1: Login all accounts on a device
from login_automation_db import create_login_task
# ... create tasks ...

# Step 2: Process logins
from automated_login_manager import AutomatedLoginManager
manager = AutomatedLoginManager()
manager.run_batch_processor()

# Step 3: Create profile campaign
from tag_based_automation import TagBasedAutomation
automation = TagBasedAutomation()
campaign_id = automation.create_campaign(
    tag_name="chantall",
    campaign_name="Chantall Profile Update",
    # ...
)

# Step 4: Execute profile changes
automation.execute_campaign(campaign_id)
```

---

## Support and Maintenance

### Files and Locations

```
uiAutomator/
├── login_automation_db.py          # Database layer
├── login_automation.py             # Core logic
├── two_fa_live_client.py           # 2FA client
├── automated_login_manager.py      # Batch processor
├── login_task_manager.py           # CLI manager
├── LOGIN_AUTOMATION_README.md      # This file
└── login_automation.db             # SQLite database

the-livehouse-dashboard/
├── simple_app.py                   # Flask app (modified)
└── login_automation_routes.py      # API routes
```

### Version History

- **v1.0.0** (2025-11-21): Initial release
  - Complete login automation
  - 2FA integration
  - Batch processing
  - Dashboard API
  - CLI manager

---

## License

Part of the Instagram Automation Suite.
Created by Claude Code for TheLiveHouse.

---

**End of Documentation**
