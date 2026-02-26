# Hydra — Setup Guide

## Prerequisites

### Python
- **Python 3.13+** (Windows Store or python.org)
- Create venv: `python -m venv venv`
- Activate: `venv\Scripts\activate`
- Install deps: `pip install -r requirements.txt`

### ADB (Android Debug Bridge)
- Install via Android SDK Platform Tools
- Or standalone: https://developer.android.com/tools/releases/platform-tools
- Add to PATH so `adb` works from any terminal
- Verify: `adb version`

### scrcpy (Screen Mirroring)
- Download: https://github.com/Genymobile/scrcpy/releases
- Get the `scrcpy-win64-vX.X.zip` file
- Extract to: `C:\tools\scrcpy\scrcpy-win64-v3.1\`
- The dashboard "Mirror" button expects `scrcpy.exe` at that path
- Verify: `C:\tools\scrcpy\scrcpy-win64-v3.1\scrcpy.exe --version`

---

## Quick Start

### 1. Start the Dashboard
```batch
cd phone-farm\dashboard
..\venv\Scripts\python.exe run_dashboard.py
```
Or use the detached launcher (runs hidden):
```batch
wscript.exe dashboard\start_dashboard.vbs
```
- Dashboard URL: `http://localhost:5055`
- Default login: `admin` / `hydra2026`
- Change password in Settings page

### 2. Connect Devices
- Devices connect over WiFi ADB: `adb connect <IP>:5555`
- Use **Device Manager** to discover and add devices
- Each device needs USB debugging enabled + ADB over WiFi

### 3. Deploy Accounts
- Go to **Deploy Wizard** (`/deploy`)
- Paste accounts in format: `username:password:2fa_token`
- Select devices → Review → Deploy
- Accounts get assigned to clone slots automatically

### 4. Fix Package Names (one-time after fresh deploy)
```batch
venv\Scripts\python.exe fix_package_names.py
```
Ensures `instagram_package` has short format and `app_cloner` has full `package/activity` format.

### 5. Login Accounts
- Go to **Login Automation V2** (`/login-automation-v2`)
- Select device or "All devices"
- Click Start → runs in parallel across devices, sequential per device

### 6. Start the Bot Farm
```batch
cd phone-farm
venv\Scripts\python.exe launch_farm.py
```
Or start individual devices:
```batch
venv\Scripts\python.exe run_device.py --serial 10.1.9.71_5555
```

---

## Key Pages

| Page | URL | Purpose |
|------|-----|---------|
| Dashboard | `/` | Overview, stats |
| **Device Manager** | `/device-manager` | Manage devices, mirror screens, view accounts |
| Deploy Wizard | `/deploy` | Bulk deploy accounts to devices |
| Login Automation V2 | `/login-automation-v2` | Mass login accounts |
| Bot Settings | `/bot-settings` | Per-account action settings |
| Content Schedule | `/content-schedule` | Schedule posts, Test Post Now |
| Media Library | `/media-library` | Upload and manage media |
| Job Orders | `/job-orders-v2` | Follow/like/comment/report jobs |
| Farm Stats | `/farm-stats` | Analytics dashboard |
| Settings | `/settings` | API keys (OpenAI, Anthropic), auth |

---

## Configuration

### OpenAI API Key (for AI captions)
- Go to Settings page → AI Settings
- Or edit `dashboard/global_settings.json` directly
- **This file is gitignored** — each PC has its own key

### Bot Settings
- Per-account settings in Bot Settings page
- Select device → account → configure actions
- Key settings: follow, like, reels, story, comment limits

### Time Windows
- Each account has `start_time` / `end_time` (24h format)
- `0-0` = always active
- Comma-separated for multiple windows: `start="2,12" end="4,14"`
- Bot only runs accounts within their active window

---

## Troubleshooting

### Dashboard won't start
```powershell
# Kill zombie processes
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "run_dashboard|simple_app" -and $_.Name -match "python" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# Restart
cd phone-farm\dashboard
..\venv\Scripts\python.exe run_dashboard.py
```

### Bot can't open Instagram clone
- Check `instagram_package` is SHORT format: `com.instagram.androif` (not with `/activity`)
- Check `app_cloner` in account settings has FULL format: `com.instagram.androif/com.instagram.mainactivity.MainActivity`
- Run `fix_package_names.py` to fix both

### White screen / app stuck
- Bot now force-kills app before each launch (auto-recovery)
- If persistent: manually force-stop via `adb shell am force-stop com.instagram.androiX`

### Account detected as "not logged in" but it is
- Bot checks for Profile/Home/Search tabs on screen
- Post-login modals (contacts, notifications) are auto-dismissed
- If still failing, check if IG clone is actually in foreground

### Mirror button doesn't work
- Ensure scrcpy is installed at `C:\tools\scrcpy\scrcpy-win64-v3.1\scrcpy.exe`
- Device must be connected via ADB

---

## Architecture

```
phone-farm/
├── automation/
│   ├── bot_engine.py          — Single account engine (actions, login check)
│   ├── ig_controller.py       — Core UI controller (navigation, selectors)
│   ├── instagram_actions.py   — Screen detection, login, modals
│   ├── device_connection.py   — u2 device connections
│   └── actions/               — Action modules
│       ├── post_content.py    — Post/Reel/Story publishing
│       ├── follow_from_list.py
│       ├── share_to_story.py
│       ├── report.py
│       ├── save_post.py
│       └── ...
├── dashboard/
│   ├── simple_app.py          — Flask app entry point
│   ├── run_dashboard.py       — Watchdog wrapper (auto-restart)
│   ├── phone_farm_db.py       — DB helpers
│   └── templates/             — HTML pages
├── db/
│   └── phone_farm.db          — SQLite database (source of truth)
├── run_device.py              — Single device bot runner
├── launch_farm.py             — Multi-device launcher
└── fix_package_names.py       — One-time package name fixer
```

---

## Important Rules

- **`instagram_package`** = SHORT format (`com.instagram.androif`) — used as resource ID prefix
- **`app_cloner`** = FULL format (`com.instagram.androif/com.instagram.mainactivity.MainActivity`) — used for launching
- **Never commit API keys** — `global_settings.json` is gitignored
- **Kill ALL dashboard processes before restart** — zombie processes hold the port
- **Use venv Python** — not Windows Store Python: `venv\Scripts\python.exe`
