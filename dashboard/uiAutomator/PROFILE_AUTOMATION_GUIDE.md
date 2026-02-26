# Profile Automation System - Complete Guide

## 🎯 Overview

The profile automation system allows you to:
- **Tag accounts** with custom tags (e.g., "chantall", "brand1", etc.)
- **Create campaigns** to automate profile changes for all tagged accounts
- **Process multiple devices** efficiently (same device: sequential, different devices: parallel)
- **Select which actions** to perform: profile picture, bio, username

---

## ✅ Key Features

### 1. **No Manual Confirmations**
- All changes are saved automatically
- No "Press y/n to continue" prompts
- Fully automated from start to finish

### 2. **Smart Device Handling**
- **Same Device**: Tasks run one after another (can't do 2 things at once on 1 phone)
- **Different Devices**: Tasks can run in parallel (multiple phones work simultaneously)

### 3. **Action Checkboxes**
In the dashboard UI, you can select which changes to make:
- ☑️ Change Profile Picture
- ☑️ Change Bio
- ☑️ Change Username

### 4. **Instagram Package Support**
- Supports original Instagram: `com.instagram.android`
- Supports clones: `com.instagram.androi` + letter (e.g., `androie`, `androif`, `androig`)

---

## 📋 How It Works

### Step 1: Tag Your Accounts
```
Dashboard → Profile Automation → Select Tag → Bulk Tag Devices
```

This tags all accounts on selected devices with your chosen tag (e.g., "chantall")

### Step 2: Create a Campaign
```
Dashboard → Profile Automation → Quick Campaign
```

Fill in:
- **Tag**: Which accounts to target (e.g., "chantall")
- **Mother Account**: Reference account (e.g., "chantall.main")
- **Mother Bio**: Reference bio
- **Name Shortcuts**: Variations for usernames (e.g., "chantall, chantie, chan")
- **Actions**: Check which changes to make
  - ☑️ Change Profile Picture
  - ☑️ Change Bio
  - ☑️ Change Username

### Step 3: Execute the Campaign

**Option A: Sequential Mode (Safer, Recommended)**
```bash
cd uiAutomator
python parallel_profile_processor.py --mode sequential
```

**Option B: Parallel Mode (Faster, for many devices)**
```bash
cd uiAutomator
python parallel_profile_processor.py --mode parallel

# Or limit simultaneous devices:
python parallel_profile_processor.py --mode parallel --max-devices 5
```

---

## 📊 How Tasks Are Processed

### Example: 12 Accounts on 3 Devices

**Device A (192.168.101.107)**: 5 accounts
**Device B (192.168.101.115)**: 4 accounts
**Device C (192.168.101.130)**: 3 accounts

### Sequential Mode:
```
Process Device A (5 accounts) → one by one → wait 5 sec between
↓ (after Device A done)
Process Device B (4 accounts) → one by one → wait 5 sec between
↓ (after Device B done)
Process Device C (3 accounts) → one by one → wait 5 sec between
```

**Total Time**: ~60-120 seconds per account × 12 accounts = **12-24 minutes**

### Parallel Mode:
```
Process Device A (5 accounts) ┐
Process Device B (4 accounts) ├─ All at the same time
Process Device C (3 accounts) ┘
```

**Total Time**: Max of (5, 4, 3) accounts × ~60-120 sec = **5-10 minutes**

---

## 🎨 Dashboard UI Changes Needed

Add checkboxes to `profile_automation.html` in the Quick Campaign modal:

```html
<div class="mb-3">
    <label class="form-label">Actions to Perform</label>
    <div class="form-check">
        <input class="form-check-input" type="checkbox" id="changePicture" checked>
        <label class="form-check-label" for="changePicture">
            Change Profile Picture
        </label>
    </div>
    <div class="form-check">
        <input class="form-check-input" type="checkbox" id="changeBio" checked>
        <label class="form-check-label" for="changeBio">
            Change Bio
        </label>
    </div>
    <div class="form-check">
        <input class="form-check-input" type="checkbox" id="changeUsername" checked>
        <label class="form-check-label" for="changeUsername">
            Change Username
        </label>
    </div>
</div>
```

Update `profile-automation.js` to send actions:

```javascript
async function executeQuickCampaign() {
    const changePicture = document.getElementById('changePicture').checked;
    const changeBio = document.getElementById('changeBio').checked;
    const changeUsername = document.getElementById('changeUsername').checked;

    const response = await fetch('/api/profile_automation/quick_campaign', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            tag: tag,
            mother_account: motherAccount,
            mother_bio: motherBio,
            name_shortcuts: shortcuts,
            use_ai: useAI,
            ai_api_key: aiApiKey,
            selected_accounts: selectedAccountsList,
            actions: {
                change_picture: changePicture,
                change_bio: changeBio,
                change_username: changeUsername
            }
        })
    });
}
```

---

## 🔧 Technical Details

### Files Changed:
1. **`instagram_automation.py`**:
   - ✅ Fixed Instagram package names (`androi` instead of `android`)
   - ✅ Improved `open_instagram()` to force-open apps
   - ✅ Fixed `edit_bio()` to work like username editing
   - ✅ Character-by-character bio input for special chars/emojis

2. **`automated_profile_manager.py`**:
   - ✅ No confirmations - auto-saves everything
   - ✅ Processes tasks sequentially
   - ✅ Bio editing uses same method as username

3. **`parallel_profile_processor.py`** (NEW):
   - ✅ Groups tasks by device
   - ✅ Sequential processing per device
   - ✅ Optional parallel processing across devices
   - ✅ Thread-safe with locks

4. **`profile_automation_routes.py`**:
   - ✅ Added `actions` parameter to `quick_campaign`
   - ✅ Builds strategies based on checkboxes
   - ✅ Returns actions in response

---

## 📝 Usage Examples

### Example 1: Change Only Bio
```bash
# In dashboard:
# ☐ Change Profile Picture
# ☑ Change Bio
# ☐ Change Username

# Creates tasks that only change bio
```

### Example 2: Change Everything
```bash
# In dashboard:
# ☑ Change Profile Picture
# ☑ Change Bio
# ☑ Change Username

# Creates tasks that change all 3
```

### Example 3: 50 Accounts on 10 Devices
```bash
# Sequential mode: ~50 accounts × 90 sec = 75 minutes
python parallel_profile_processor.py --mode sequential

# Parallel mode (5 devices at once): ~10 devices × 90 sec = 15 minutes
python parallel_profile_processor.py --mode parallel --max-devices 5
```

---

## 🚀 Quick Start

1. **Tag accounts** in dashboard
2. **Create campaign** with action checkboxes
3. **Run processor**:
   ```bash
   cd uiAutomator
   python parallel_profile_processor.py --mode sequential
   ```
4. **Monitor progress** in terminal
5. **Done!** All profiles updated automatically

---

## 📸 Profile Pictures

Put your profile pictures in:
```
uiAutomator/profile_pictures/
  ├── female/
  ├── male/
  ├── neutral/
  └── uploaded/
```

System automatically:
- Selects pictures based on strategy
- Transfers to device
- Sets as profile picture
- Tracks usage count

---

## ⚠️ Important Notes

1. **Same device = Sequential only**: Can't process 2 accounts simultaneously on 1 device
2. **Different devices = Can be parallel**: Multiple devices work at the same time
3. **5-second wait between tasks**: Prevents Instagram rate limiting
4. **Auto-saves everything**: No manual confirmations
5. **Instagram package names**: Uses `androi` + letter for clones

---

## 🎯 Summary

✅ **Fully automated** - no confirmations
✅ **Smart device handling** - sequential same device, parallel different devices
✅ **Action checkboxes** - select what to change
✅ **Scales well** - handles 100+ accounts efficiently
✅ **Package support** - works with Instagram clones
✅ **Bio/Username input** - handles emojis and special characters

Run with:
```bash
python parallel_profile_processor.py --mode sequential
```

That's it! 🎉
