# Login Automation - Dashboard Integration Guide

## Overview

The login automation system is **fully integrated** with your existing dashboard account loading system. It uses the same `get_devices()` and `get_accounts()` functions, reading from:

- `devices.db` - Central device registry
- `{device_serial}/accounts.db` - Account credentials per device
- `{device_serial}/{username}/settings.db` - Instagram package info per account

---

## How It Works

### 1. Dashboard Account Loading (Existing System)

Your dashboard already has these functions in [simple_app.py](simple_app.py:1531):

```python
def get_devices():
    # Returns: [{deviceid, devicename, status}, ...]
    # Reads from: devices.db

def get_accounts(deviceid):
    # Returns: [{account, password, starttime, ...}, ...]
    # Reads from: {deviceid}/accounts.db
```

### 2. Login Automation Integration (New)

The login automation **reuses** these functions via [login_automation_routes.py](login_automation_routes.py:59):

```python
def get_dashboard_devices():
    """Use dashboard's existing get_devices()"""
    from simple_app import get_devices
    return get_devices()

def get_dashboard_accounts(deviceid):
    """Use dashboard's existing get_accounts()"""
    from simple_app import get_accounts
    return get_accounts(deviceid)

def get_instagram_package_for_account(deviceid, username):
    """Read from {deviceid}/{username}/settings.db"""
    # Extracts package from settings.app_cloner field
    # Example: "com.instagram.androim/com.instagram.mainactivity.mainactivity"
    #          → "com.instagram.androim"
```

---

## Dashboard API Endpoints

### For UI Integration

#### 1. List All Devices
```bash
GET /api/login/devices
```

**Response:**
```json
{
  "status": "success",
  "devices": [
    {
      "deviceid": "10.1.10.183_5555",
      "devicename": "Device 1",
      "status": "active"
    },
    ...
  ]
}
```

**Usage:** Populate device dropdown in UI

---

#### 2. List Accounts for Device
```bash
GET /api/login/devices/10.1.10.183_5555/accounts
```

**Response:**
```json
{
  "status": "success",
  "device_serial": "10.1.10.183_5555",
  "accounts": [
    {
      "account": "testuser",
      "password": "testpass123",
      "instagram_package": "com.instagram.androim",
      "starttime": "9",
      "endtime": "17",
      ...
    },
    ...
  ]
}
```

**Usage:** Populate account list with checkboxes for selection

---

#### 3. Create Tasks for Selected Accounts (Primary Method)
```bash
POST /api/login/accounts/selected
Content-Type: application/json

{
  "accounts": [
    {
      "device_serial": "10.1.10.183_5555",
      "username": "user1"
    },
    {
      "device_serial": "10.1.10.183_5555",
      "username": "user2"
    }
  ],
  "two_fa_token": "CHN44RHFYSYPFCKLL2C5CFHNTY54PYOD",  // optional
  "priority": 0  // optional
}
```

**Response:**
```json
{
  "status": "success",
  "created": 2,
  "task_ids": [123, 124],
  "errors": null
}
```

**How it works:**
1. For each `{device_serial, username}` pair:
   - Reads password from `{device_serial}/accounts.db`
   - Reads instagram_package from `{device_serial}/{username}/settings.db`
   - Creates login task with all required info
2. Returns task IDs for tracking

**Usage:** User selects accounts in UI → sends to this endpoint

---

#### 4. Create Tasks for Entire Device
```bash
POST /api/login/tasks/device/10.1.10.183_5555
Content-Type: application/json

{
  "two_fa_token": "CHN44RHFYSYPFCKLL2C5CFHNTY54PYOD",  // optional
  "priority": 0  // optional
}
```

**Response:**
```json
{
  "status": "success",
  "created": 5,
  "task_ids": [125, 126, 127, 128, 129],
  "errors": []
}
```

**Usage:** "Login All Accounts on Device" button

---

#### 5. Process All Pending Tasks
```bash
POST /api/login/tasks/process
Content-Type: application/json

{
  "device_serial": "10.1.10.183_5555",  // optional filter
  "max_tasks": 10  // optional limit
}
```

**Response:**
```json
{
  "status": "success",
  "stats": {
    "total_tasks": 5,
    "successful": 4,
    "failed": 1,
    "needs_manual": 0,
    "duration": 320
  }
}
```

**Usage:** "Execute Login Tasks" button

---

#### 6. View Tasks
```bash
GET /api/login/tasks?status=pending
GET /api/login/tasks?device=10.1.10.183_5555
```

**Response:**
```json
{
  "status": "success",
  "tasks": [
    {
      "id": 123,
      "device_serial": "10.1.10.183_5555",
      "username": "testuser",
      "instagram_package": "com.instagram.androim",
      "status": "pending",
      "two_fa_token": "CHN44...",
      "priority": 0,
      "retry_count": 0,
      "created_at": "2025-11-21T10:30:00",
      "error_message": null
    },
    ...
  ]
}
```

**Usage:** Task queue display, status monitoring

---

#### 7. View Login History
```bash
GET /api/login/history?limit=50
GET /api/login/history?device=10.1.10.183_5555
GET /api/login/history?username=testuser
```

**Response:**
```json
{
  "status": "success",
  "history": [
    {
      "id": 456,
      "device_serial": "10.1.10.183_5555",
      "username": "testuser",
      "login_type": "2fa",
      "success": 1,
      "logged_in_at": "2025-11-21T10:35:00",
      "two_fa_used": 1,
      "challenge_encountered": 0
    },
    ...
  ]
}
```

**Usage:** Audit trail, success rate tracking

---

#### 8. View Statistics
```bash
GET /api/login/statistics
```

**Response:**
```json
{
  "status": "success",
  "statistics": {
    "tasks": {
      "pending": 5,
      "completed": 20,
      "failed": 2,
      "needs_manual": 1
    },
    "total_attempts": 28,
    "successful_attempts": 25,
    "success_rate": 89.29,
    "active_2fa_tokens": 3,
    "recent_logins_24h": 15
  }
}
```

**Usage:** Dashboard statistics display

---

## UI Workflow Examples

### Workflow 1: Select Specific Accounts

```javascript
// 1. User selects device from dropdown
GET /api/login/devices
// → User sees: Device 1, Device 2, Device 3

// 2. Load accounts for selected device
GET /api/login/devices/10.1.10.183_5555/accounts
// → User sees checkbox list: ☐ user1, ☐ user2, ☐ user3

// 3. User checks user1 and user3, optionally enters 2FA token
// 4. User clicks "Login Selected Accounts"
POST /api/login/accounts/selected
{
  "accounts": [
    {"device_serial": "10.1.10.183_5555", "username": "user1"},
    {"device_serial": "10.1.10.183_5555", "username": "user3"}
  ],
  "two_fa_token": "CHN44RHFY..."
}
// → Creates 2 tasks

// 5. User clicks "Execute Tasks"
POST /api/login/tasks/process
// → Processes all pending tasks
```

### Workflow 2: Login All on Device

```javascript
// 1. User selects device
GET /api/login/devices
// → User picks "Device 1" (10.1.10.183_5555)

// 2. User clicks "Login All Accounts on This Device"
POST /api/login/tasks/device/10.1.10.183_5555
{
  "two_fa_token": "CHN44RHFY..."  // optional
}
// → Creates tasks for all 5 accounts

// 3. User clicks "Execute Tasks"
POST /api/login/tasks/process
// → Processes all pending tasks
```

### Workflow 3: Tag-Based Login (Like Profile Automation)

```javascript
// 1. User selects tag (e.g., "chantall")
// (Your existing tag system from profile automation)

// 2. Get accounts with tag "chantall"
// (Use your existing tag_based_automation.get_accounts_by_tag())

// 3. Create login tasks for tagged accounts
POST /api/login/accounts/selected
{
  "accounts": [
    {"device_serial": "10.1.10.183_5555", "username": "chantall1"},
    {"device_serial": "192.168.101.107_5555", "username": "chantall2"},
    ...
  ]
}

// 4. Execute
POST /api/login/tasks/process
```

---

## Database Auto-Initialization

The login automation database (`login_automation.db`) is **automatically created** when the dashboard starts:

```python
# In login_automation_routes.py (line 48-52)
try:
    init_database()
except:
    pass  # Database may already exist
```

**Tables created:**
- `login_tasks` - Task queue
- `login_history` - Audit trail
- `two_factor_services` - 2FA token storage

**No manual initialization needed!** The database is created on first dashboard startup.

---

## Comparison with Profile Automation

| Feature | Profile Automation | Login Automation |
|---------|-------------------|------------------|
| **Account Source** | `tag_based_automation.get_accounts_by_tag()` | `simple_app.get_accounts(deviceid)` |
| **Device Source** | Device folders scan | `simple_app.get_devices()` |
| **Task Creation** | `/api/profile_automation/campaigns` | `/api/login/accounts/selected` |
| **Batch Processing** | `automated_profile_manager.py` | `automated_login_manager.py` |
| **Database** | `profile_automation.db` | `login_automation.db` |
| **UI Selection** | By tags or device | By device or specific accounts |

**Both systems:**
- Read from same `{device}/accounts.db` files
- Read from same `{device}/{username}/settings.db` files
- Use same device serial format (`10.1.10.183_5555`)
- Use same Instagram package detection
- Follow same Flask Blueprint patterns

---

## Example Frontend Code

### React/JavaScript Example

```javascript
class LoginAutomation {
  constructor(apiBaseUrl = 'http://localhost:5000/api/login') {
    this.api = apiBaseUrl;
  }

  // Get all devices
  async getDevices() {
    const res = await fetch(`${this.api}/devices`);
    return await res.json();
  }

  // Get accounts for device
  async getDeviceAccounts(deviceSerial) {
    const res = await fetch(`${this.api}/devices/${deviceSerial}/accounts`);
    return await res.json();
  }

  // Create tasks for selected accounts
  async createTasksForSelected(accounts, twoFaToken = null, priority = 0) {
    const res = await fetch(`${this.api}/accounts/selected`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({accounts, two_fa_token: twoFaToken, priority})
    });
    return await res.json();
  }

  // Create tasks for entire device
  async createTasksForDevice(deviceSerial, twoFaToken = null) {
    const res = await fetch(`${this.api}/tasks/device/${deviceSerial}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({two_fa_token: twoFaToken})
    });
    return await res.json();
  }

  // Execute all pending tasks
  async processTasks(deviceSerial = null, maxTasks = null) {
    const res = await fetch(`${this.api}/tasks/process`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({device_serial: deviceSerial, max_tasks: maxTasks})
    });
    return await res.json();
  }

  // Get pending tasks
  async getTasks(status = 'pending', deviceSerial = null) {
    let url = `${this.api}/tasks?status=${status}`;
    if (deviceSerial) url += `&device=${deviceSerial}`;
    const res = await fetch(url);
    return await res.json();
  }

  // Get statistics
  async getStatistics() {
    const res = await fetch(`${this.api}/statistics`);
    return await res.json();
  }
}

// Usage
const loginAuto = new LoginAutomation();

// 1. Load devices
const {devices} = await loginAuto.getDevices();
// Show in dropdown: devices.map(d => ({value: d.deviceid, label: d.devicename}))

// 2. Load accounts for selected device
const {accounts} = await loginAuto.getDeviceAccounts('10.1.10.183_5555');
// Show checkboxes: accounts.map(a => ({username: a.account, package: a.instagram_package}))

// 3. Create tasks for checked accounts
const selectedAccounts = [
  {device_serial: '10.1.10.183_5555', username: 'user1'},
  {device_serial: '10.1.10.183_5555', username: 'user3'}
];
const {created, task_ids} = await loginAuto.createTasksForSelected(
  selectedAccounts,
  'CHN44RHFY...'  // 2FA token
);

// 4. Execute tasks
const {stats} = await loginAuto.processTasks();
console.log(`Success: ${stats.successful}/${stats.total_tasks}`);
```

---

## Key Points

### ✅ No Separate Account Management
- Login automation **reads directly** from your existing dashboard account database
- No need to import/sync accounts
- Always up-to-date with dashboard

### ✅ Same Selection Patterns as Profile Automation
- Select by device (all accounts on device)
- Select specific accounts (checkboxes)
- Can integrate with tags (use your existing tag system)

### ✅ Auto-Initialization
- Database created automatically on dashboard startup
- No manual setup required

### ✅ Consistent with Existing System
- Uses same device serial format
- Uses same package detection
- Uses same file structure
- Uses same API patterns

---

## Testing

### 1. Verify Dashboard Integration
```bash
# Start dashboard
cd the-livehouse-dashboard
python simple_app.py

# Test device listing
curl http://localhost:5000/api/login/devices

# Test account listing
curl http://localhost:5000/api/login/devices/10.1.10.183_5555/accounts
```

### 2. Create and Execute Tasks
```bash
# Create tasks for selected accounts
curl -X POST http://localhost:5000/api/login/accounts/selected \
  -H "Content-Type: application/json" \
  -d '{
    "accounts": [
      {"device_serial": "10.1.10.183_5555", "username": "testuser"}
    ]
  }'

# Execute tasks
curl -X POST http://localhost:5000/api/login/tasks/process

# Check statistics
curl http://localhost:5000/api/login/statistics
```

---

## Summary

The login automation is **fully integrated** with your dashboard:

1. **Reads from existing account database** (no separate account management)
2. **Uses dashboard's device/account loading functions** (consistent behavior)
3. **Auto-initializes on startup** (no manual setup)
4. **Provides UI-friendly endpoints** (device list, account list, task creation)
5. **Follows profile automation patterns** (same selection methods)

You can now build your UI to:
- Show device dropdown (from `/api/login/devices`)
- Show account checkboxes (from `/api/login/devices/{serial}/accounts`)
- Create tasks for selected accounts (to `/api/login/accounts/selected`)
- Execute tasks (to `/api/login/tasks/process`)
- Monitor progress (from `/api/login/statistics` and `/api/login/tasks`)

**Just like the profile automation, but for logins!** 🎉
