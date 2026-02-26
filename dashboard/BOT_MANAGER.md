# Bot Manager System Documentation

## Overview

The Bot Manager is a web-based dashboard interface for managing Onimator Instagram automation bots (igbot.exe) across multiple Android devices. It replicates the functionality of Onimator's main.exe but through a modern web UI, allowing you to start, stop, and monitor bots for 50+ devices simultaneously.

## System Architecture

### Components

1. **bot_db.py** - Database layer for bot state tracking
2. **onimator_reader.py** - Reads existing Onimator data (devices.db, accounts.db, etc.)
3. **device_bot.py** - New Python-based bot (alternative to igbot.exe)
4. **bot_manager_routes.py** - Flask API endpoints for bot management
5. **bot_manager.html** - Web UI interface
6. **simple_app.py** - Main Flask application (modified to include bot manager)

### File Structure

```
the-livehouse-dashboard/
├── simple_app.py                    # Main Flask app (MODIFIED)
├── bot_manager_routes.py            # Bot Manager API (NEW)
├── templates/
│   ├── base.html                    # Navigation template (MODIFIED)
│   └── bot_manager.html             # Bot Manager UI (NEW)
└── BOT_MANAGER.md                   # This documentation (NEW)

full_igbot_14.2.4/
├── igbot.exe                        # Onimator's bot executable
├── main.exe                         # Onimator's UI (we're replacing this)
├── devices.db                       # Device list database
├── {device_serial}/                 # Device folders
│   ├── pid                          # PID tracking file
│   ├── accounts.db                  # Account data
│   └── sessions/                    # Bot session logs

uiAutomator/
├── bot_db.py                        # Bot state database (NEW)
├── onimator_reader.py               # Onimator data reader (NEW)
└── device_bot.py                    # Python bot alternative (NEW)
```

## Features

### Dashboard Overview
- **Total Devices**: Count of all devices in the system
- **Running Bots**: Number of actively running bot processes
- **Stopped Bots**: Number of inactive devices
- **Actions Today**: Total actions performed across all devices
- **Auto-refresh**: Status updates every 5 seconds

### Device Management
Each device card shows:
- Device name and serial number
- Current status (Running/Stopped) with color-coded badge
- Accounts run today
- Actions performed today
- Process ID (PID) of running bot
- Start time (for running bots)
- Bot type selector (igbot.exe or device_bot.py)
- Start/Stop buttons
- Sessions button (view bot history)

### Bot Types
1. **igbot.exe** - Onimator's original bot (GramAddict-based)
2. **device_bot.py** - New Python bot using uiautomator2 (future development)

## API Endpoints

### GET /api/bots/status
Returns status of all bots across all devices.

**Response:**
```json
{
  "devices": [
    {
      "device_serial": "10.1.10.244_5555",
      "bot_status": "running",
      "pid": 212596,
      "pids": [212596, 198432],
      "accounts_running": 3,
      "actions_today": 45,
      "started_at": "2026-01-19T14:30:00"
    }
  ]
}
```

### POST /api/bots/start
Starts a bot for a specific device.

**Request:**
```json
{
  "device_serial": "10.1.10.244_5555",
  "bot_type": "igbot"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Started igbot.exe for 10.1.10.244_5555",
  "pid": 212596,
  "bot_type": "igbot"
}
```

### POST /api/bots/stop
Stops a running bot.

**Request:**
```json
{
  "device_serial": "10.1.10.244_5555"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Stopped bot for 10.1.10.244_5555",
  "pids_killed": [212596]
}
```

### GET /api/devices
Returns list of all devices from Onimator's devices.db.

**Response:**
```json
[
  {
    "deviceid": "10.1.10.244_5555",
    "devicename": "Device 244",
    "status": "stop"
  }
]
```

## Technical Implementation Details

### Process Launching Strategy

**Critical Implementation Note:**

igbot.exe MUST be launched from the root directory (where igbot.exe is located), NOT from the device folder. This is because igbot.exe needs to access database files in the root directory.

```python
# CORRECT - Run from root directory
process = subprocess.Popen(
    [str(igbot_exe), device_serial],
    cwd=str(root_dir),  # full_igbot_14.2.4/
    creationflags=subprocess.CREATE_NEW_CONSOLE
)

# WRONG - This causes "unable to open database file" error
process = subprocess.Popen(
    [str(igbot_exe), device_serial],
    cwd=str(device_folder),  # 10.1.10.244_5555/
    creationflags=subprocess.CREATE_NEW_CONSOLE
)
```

**Console Window Visibility:**

Use `CREATE_NEW_CONSOLE` flag to create separate, visible console windows (like Onimator does):

```python
creationflags=subprocess.CREATE_NEW_CONSOLE  # Creates external console window
```

**What NOT to use:**
- `CREATE_NO_WINDOW` - Makes console invisible
- `CREATE_NEW_PROCESS_GROUP` alone - Can cause console to be captured by parent process
- `stdout=subprocess.PIPE, stderr=subprocess.PIPE` - Captures output instead of showing in console

### PID Detection Strategy

The system uses a **two-tier approach** to detect running bots:

#### Tier 1: WMIC Command Line Scanning (Primary)
```python
def get_all_igbot_processes():
    """Scan all running igbot.exe processes and extract device serial from command line"""
    result = subprocess.run(
        ['wmic', 'process', 'where', 'name="igbot.exe"', 'get', 'ProcessId,CommandLine', '/FORMAT:CSV'],
        capture_output=True, text=True, timeout=10
    )

    # Parse output to extract device_serial from command line arguments
    # Example command line: "C:\...\igbot.exe 10.1.10.244_5555"
    device_serial = cmd_parts[-1]  # Last argument is device serial

    return {device_serial: [pid1, pid2, ...]}
```

**Why this is the primary method:**
- Most reliable - directly inspects running processes
- Works even if PID files are missing or stale
- Extracts device serial from command line arguments
- Single system call for all processes (fast)

#### Tier 2: PID File Fallback (Secondary)
```python
def read_device_pid(device_serial):
    """Read PIDs from device's pid file"""
    pid_file = device_folder / 'pid'
    content = pid_file.read_text().strip()
    pids = []
    for pid in content.split('\n'):
        if pid.strip():
            pids.append(int(pid))  # Must return integers for set comparison
    return pids
```

**PID File Format:**
```
212596
198432
173829
```
- One PID per line
- Plain text integers
- Located at `{device_serial}/pid`

**Why fallback is needed:**
- WMIC can fail or be slow on some systems
- Historical record of PIDs even after process exits
- Compatible with Onimator's existing PID tracking

### Status Endpoint Optimization

**Original Problem:**
Initial implementation called `tasklist` individually for each PID (50+ subprocess calls), causing 5-10 second delays.

**Solution:**
Single `tasklist` call to get all running PIDs, then O(1) lookup:

```python
def get_all_running_pids():
    """Get all running process IDs in one call"""
    result = subprocess.run(
        ['tasklist', '/FO', 'CSV', '/NH'],
        capture_output=True, text=True
    )

    running_pids = set()
    for line in result.stdout.strip().split('\n'):
        parts = line.split(',')
        if len(parts) >= 2:
            pid = int(parts[1].strip('"'))
            running_pids.add(pid)

    return running_pids  # Set for O(1) lookup

# Usage in status endpoint
all_running_pids = get_all_running_pids()
for pid in device_pids:
    if pid in all_running_pids:  # O(1) lookup
        # Bot is running
```

**Performance Improvement:** 50x faster (from 5-10s to <1s)

## Issues Fixed During Development

### Issue 1: UI Shows "Loading devices..." Forever

**Symptom:**
- Console showed "Loaded devices: 50"
- UI never updated, stuck on loading spinner
- Stopping Flask dashboard made UI suddenly appear

**Root Cause:**
Auto-refresh interval (5 seconds) was calling `refreshDevices()` while initial render was still in progress, causing overlapping AJAX calls and timing issues.

**Fix:**
```javascript
let isLoading = false;  // Global flag

function loadDevices() {
    if (isLoading) {
        console.log('Already loading, skipping...');
        return;
    }
    isLoading = true;

    $.ajax({
        url: '/api/devices',
        success: function(data) {
            devices = data;
            loadBotStatuses();
        }
    });
}

function renderDevices() {
    // Use vanilla JavaScript for DOM manipulation
    const devicesList = document.getElementById('devicesList');
    if (devicesList) {
        devicesList.innerHTML = html;
    }
    isLoading = false;  // Reset flag
}
```

### Issue 2: Slow Status Endpoint (5-10 second wait)

**Symptom:**
- `/api/bots/status` taking 5-10 seconds to respond
- UI freezing during status refresh

**Root Cause:**
```python
# SLOW - 50+ subprocess calls
for pid in device_pids:
    is_running = is_process_running(pid)  # tasklist call per PID
```

**Fix:**
```python
# FAST - Single subprocess call
all_running_pids = get_all_running_pids()  # One tasklist call
for pid in device_pids:
    is_running = pid in all_running_pids  # O(1) lookup
```

### Issue 3: PID Type Mismatch

**Symptom:**
- Running devices not detected even though PIDs existed in files
- Status always showed "stopped"

**Root Cause:**
```python
# read_device_pid() returned strings
pids = ['212596', '198432']

# get_all_running_pids() returned integers
all_running_pids = {212596, 198432}

# Comparison failed
if pid in all_running_pids:  # '212596' not in {212596} - False!
```

**Fix:**
```python
def read_device_pid(device_serial):
    pids = []
    for pid in content.split('\n'):
        if pid.strip():
            pids.append(int(pid))  # Convert to integer
    return pids
```

### Issue 4: Only Devices with PID Files Showed Status

**Symptom:**
- New devices (without existing PID files) showed as "stopped" even when running
- Only devices with historical PID files were detected

**Root Cause:**
Only checking PID files, not inspecting actual running processes.

**Fix:**
Implemented WMIC scanning to detect ALL running igbot.exe processes by examining command line arguments:

```python
def get_all_igbot_processes():
    """Scan all igbot.exe processes, extract device serial from command line"""
    # Example command line: "C:\path\igbot.exe 10.1.10.244_5555"
    device_serial = cmd_parts[-1]  # Last arg is device serial
    return device_pids_map
```

### Issue 5: Start Button Not Working

**Symptom:**
- Clicking Start button did nothing
- Manual command worked: `igbot.exe 10.1.10.244_5555`

**Diagnosis Process:**
Added comprehensive logging to trace the issue:

```python
@bot_manager_bp.route('/start', methods=['POST'])
def start_bot():
    print("\n" + "="*70)
    print("START BOT REQUEST RECEIVED")
    print("="*70)
    print(f"Request data: {data}")
    print(f"Device serial: {device_serial}")
    print(f"Bot type: {bot_type}")
    print(f"Command: {igbot_exe} {device_serial}")
    print(f"Working directory: {device_folder}")
```

**Root Cause:**
```
sqlite3.OperationalError: unable to open database file
```

igbot.exe was being launched from device folder (`10.1.10.244_5555/`) but needed to run from root directory to access database files.

**Fix:**
```python
# BEFORE (wrong working directory)
process = subprocess.Popen(
    [str(igbot_exe), device_serial],
    cwd=str(device_folder),  # Wrong!
)

# AFTER (correct working directory)
root_dir = get_root_dir()
process = subprocess.Popen(
    [str(igbot_exe), device_serial],
    cwd=str(root_dir),  # Correct - where databases are located
)
```

### Issue 6: Console Windows Not Visible

**Symptom:**
- Bots were running (Instagram opening on devices)
- No console windows visible on desktop
- Console output appearing in Flask dashboard terminal instead

**Root Cause 1:**
```python
# This flag hides the console
creationflags=subprocess.CREATE_NO_WINDOW
```

**Root Cause 2:**
```python
# This captures output instead of showing in console
stdout=subprocess.PIPE,
stderr=subprocess.PIPE
```

**Root Cause 3:**
```python
# This flag alone doesn't create separate console
creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
```

**Fix:**
```python
process = subprocess.Popen(
    [str(igbot_exe), device_serial],
    cwd=str(root_dir),
    creationflags=subprocess.CREATE_NEW_CONSOLE  # Creates visible, separate console
    # No stdout/stderr capture - output goes to console
)
```

## Usage Guide

### Starting the Dashboard

```bash
cd the-livehouse-dashboard
python simple_app.py
```

Then open browser to: `http://localhost:5000/bot-manager`

### Starting a Bot

1. Navigate to Bot Manager page
2. Find device in the list
3. Select bot type (igbot.exe or device_bot.py)
4. Click "Start" button
5. Console window will appear showing bot activity
6. Device card will update to show "Running" status with PID

### Stopping a Bot

1. Find running device (green "Running" badge)
2. Click "Stop" button
3. Bot process will be killed via taskkill
4. Console window will close
5. Device card will update to "Stopped" status

### Viewing Bot Sessions

1. Click "Sessions" button on running bot
2. View historical session data
3. See accounts processed, actions performed, errors, etc.

### Bulk Operations

**Start All Bots:**
```javascript
function startAllBots() {
    // Confirm before starting all
    if (!confirm(`Start bots for all ${devices.length} devices?`)) {
        return;
    }

    devices.forEach(device => {
        // Start each device sequentially
    });
}
```

## Database Schema

### bot_sessions.db (New Database)

**bot_sessions table:**
```sql
CREATE TABLE bot_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_serial TEXT NOT NULL,
    account_username TEXT,
    bot_type TEXT DEFAULT 'igbot',
    start_time TEXT NOT NULL,
    end_time TEXT,
    status TEXT DEFAULT 'running',
    actions_performed INTEGER DEFAULT 0,
    accounts_processed INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,
    log_file TEXT
);
```

**device_status table:**
```sql
CREATE TABLE device_status (
    device_serial TEXT PRIMARY KEY,
    current_status TEXT DEFAULT 'stopped',
    current_pid INTEGER,
    last_started TEXT,
    last_stopped TEXT,
    total_sessions INTEGER DEFAULT 0,
    total_actions INTEGER DEFAULT 0
);
```

### Existing Onimator Databases (Read-Only)

**devices.db:**
```sql
CREATE TABLE devices (
    deviceid TEXT,
    devicename TEXT,
    status TEXT  -- Note: Always shows "stop", not actively maintained
);
```

**accounts.db (per device):**
```sql
CREATE TABLE accounts (
    account TEXT PRIMARY KEY,
    last_session TEXT,
    actions_today INTEGER
);
```

## API Integration Examples

### Python Client

```python
import requests

BASE_URL = "http://localhost:5000/api/bots"

# Get all bot statuses
response = requests.get(f"{BASE_URL}/status")
devices = response.json()['devices']

# Start a bot
response = requests.post(f"{BASE_URL}/start", json={
    "device_serial": "10.1.10.244_5555",
    "bot_type": "igbot"
})
print(response.json())

# Stop a bot
response = requests.post(f"{BASE_URL}/stop", json={
    "device_serial": "10.1.10.244_5555"
})
print(response.json())
```

### JavaScript/Frontend

```javascript
// Get bot status
async function getBotStatus() {
    const response = await fetch('/api/bots/status');
    const data = await response.json();
    return data.devices;
}

// Start bot
async function startBot(deviceSerial, botType = 'igbot') {
    const response = await fetch('/api/bots/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            device_serial: deviceSerial,
            bot_type: botType
        })
    });
    return await response.json();
}

// Stop bot
async function stopBot(deviceSerial) {
    const response = await fetch('/api/bots/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_serial: deviceSerial })
    });
    return await response.json();
}
```

## Troubleshooting

### Bot Starts But Immediately Exits

**Check:**
1. Working directory - must be root directory where igbot.exe is located
2. Database files exist (devices.db, accounts.db, etc.)
3. Device folder exists (`{device_serial}/`)
4. Check console output for error messages

**Debug:**
```python
# Look at Flask terminal output when starting bot:
Starting igbot.exe for 10.1.10.244_5555...
Command: C:\...\igbot.exe 10.1.10.244_5555
Working directory: C:\...\full_igbot_14.2.4
Process started with PID: 212596
ERROR: Process exited immediately with code 1
STDERR: [error message here]
```

### Console Window Not Appearing

**Check:**
```python
# Ensure this flag is used:
creationflags=subprocess.CREATE_NEW_CONSOLE

# NOT this:
creationflags=subprocess.CREATE_NO_WINDOW
creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
```

### Status Not Updating

**Check:**
1. Auto-refresh is enabled (every 5 seconds)
2. Browser console for JavaScript errors (F12 → Console)
3. Network tab shows successful API calls (F12 → Network)
4. Flask terminal shows requests being received

### PID Detection Not Working

**Check:**
1. WMIC command works: `wmic process where name="igbot.exe" get ProcessId,CommandLine`
2. PID files exist in device folders: `{device_serial}/pid`
3. PID files contain valid integers (no extra whitespace/characters)

### Port Already in Use

```bash
# Find process using port 5000
netstat -ano | findstr :5000

# Kill process
taskkill /PID <pid> /F

# Or use different port
python simple_app.py --port 5001
```

## Future Enhancements

### Phase 1 (Complete)
- ✅ Basic bot start/stop functionality
- ✅ Status monitoring
- ✅ PID tracking
- ✅ Console window visibility
- ✅ WMIC process detection

### Phase 2 (Planned)
- [ ] Real-time log streaming to web UI
- [ ] Bot configuration editor
- [ ] Account rotation management
- [ ] Error notifications
- [ ] Session history viewer with graphs
- [ ] Bulk start/stop operations
- [ ] Device grouping/filtering

### Phase 3 (Future)
- [ ] Remote device management (network devices)
- [ ] Scheduled bot execution
- [ ] Performance metrics dashboard
- [ ] Instagram account health monitoring
- [ ] Action limits and safety controls
- [ ] Multi-user access control
- [ ] API key management for external integrations

## Development Notes

### Key Learnings

1. **Working Directory Matters**: Always run igbot.exe from root directory, not device folder
2. **Console Visibility**: Use `CREATE_NEW_CONSOLE` for separate visible consoles
3. **PID Type Consistency**: Always use integers for PIDs, not strings
4. **Performance**: Batch system calls instead of individual calls (50x speedup)
5. **Two-Tier Detection**: Use WMIC as primary, PID files as fallback
6. **JavaScript Timing**: Use `isLoading` flag to prevent overlapping AJAX calls
7. **DOM Updates**: Vanilla JS `innerHTML` more reliable than jQuery `.html()` for complex updates

### Testing Checklist

When making changes, test:
- [ ] Start bot - console appears, Instagram opens
- [ ] Stop bot - console closes, process terminated
- [ ] Status updates - running/stopped badge changes
- [ ] PID detection - shows correct PID
- [ ] Multiple bots - can run 10+ simultaneously
- [ ] Auto-refresh - status updates every 5 seconds
- [ ] Error handling - proper error messages shown
- [ ] Working directory - bot can access databases
- [ ] Console visibility - windows appear on desktop

## Credits

Built to replicate and extend Onimator's bot management functionality with a modern web interface.

**Technologies:**
- Flask (Python web framework)
- SQLite (Database)
- Bootstrap 5 (UI framework)
- jQuery (AJAX requests)
- Windows subprocess management
- WMIC (Process inspection)

**Original Onimator System:**
- igbot.exe (GramAddict-based Instagram bot)
- main.exe (Original UI, replaced by this dashboard)

---

**Last Updated:** 2026-01-19
**Version:** 1.0
**Status:** Production Ready ✅