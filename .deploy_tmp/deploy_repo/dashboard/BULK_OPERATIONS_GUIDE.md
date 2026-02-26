# Bulk Operations Guide

## Overview

The **Bulk Operations** page provides powerful tools to manage multiple accounts efficiently through:
1. **Bulk Tagging** - Tag all accounts on one or more devices with a single tag
2. **Copy Settings** - Copy settings from one account to multiple accounts

---

## Features

### 1. Bulk Tagging

Tag all accounts on specific devices in one operation.

#### **Use Cases:**

- Tag all accounts on a device with a location tag (e.g., "Paris", "NewYork")
- Tag all accounts on a device with a campaign tag (e.g., "Q1_Campaign", "BlackFriday")
- Tag all accounts on multiple devices with a category tag (e.g., "Fashion", "Fitness")

#### **How It Works:**

1. **Select Devices**
   - Multi-select dropdown shows all connected devices
   - Hold Ctrl/Cmd to select multiple devices
   - Click "Select All Devices" button to select all at once

2. **Choose or Create Tag**
   - **Option A**: Select existing tag from dropdown
   - **Option B**: Enter new tag name to create it

3. **Execute**
   - Click "Tag Accounts" button
   - All accounts on selected devices will be tagged
   - Tag count is displayed in results

#### **Example Workflow:**

```
Scenario: Tag all accounts on 3 devices with "chantall" tag

1. Select Devices:
   - 10.1.10.36_5555 ✓
   - 10.1.10.37_5555 ✓
   - 10.1.10.38_5555 ✓

2. Enter Tag:
   - New Tag: "chantall"

3. Execute:
   - Result: "Successfully tagged 36 accounts with tag 'chantall'"
```

---

### 2. Copy Settings

Copy settings from a "mother account" to multiple target accounts.

#### **Use Cases:**

- Copy settings from main account to all clone accounts
- Standardize settings across all accounts with a specific tag
- Update settings for all accounts on specific devices

#### **How It Works:**

**Step 1: Select Source Account**
- Choose device from dropdown
- Choose account from dropdown
- Settings are loaded and previewed

**Step 2: Select Target Accounts**
- **Filter by Device**: Select one or more devices
- **Filter by Tag**: Select one or more tags
- Click "Load Accounts" to view filtered accounts
- Review the list of target accounts

**Step 3: Choose Settings to Copy**
- Share Post Mention ✓
- Post Type to Share ✓
- Enable Mention to Story ✓

**Step 4: Execute**
- Click "Copy Settings to Selected Accounts"
- Settings are applied to all target accounts
- Result count is displayed

#### **Example Workflow:**

```
Scenario: Copy settings from main account to all tagged accounts

1. Source Account:
   - Device: 10.1.10.36_5555
   - Account: chantall.main
   - (Settings loaded)

2. Target Accounts:
   - Filter by Tag: "chantall"
   - Load Accounts
   - Result: 30 accounts loaded

3. Settings to Copy:
   - ✓ Share Post Mention
   - ✓ Post Type to Share
   - ✓ Enable Mention to Story

4. Execute:
   - Result: "Successfully copied settings to 30 accounts"
```

---

## Backend API Endpoints

### Bulk Tagging

**Endpoint**: `POST /api/profile_automation/accounts/tag/bulk`

**Request Body**:
```json
{
  "tag": "chantall",
  "device_serials": ["10.1.10.36_5555", "10.1.10.37_5555"],
  "usernames": []  // Empty array means all accounts on those devices
}
```

**Response**:
```json
{
  "status": "success",
  "tagged_count": 24
}
```

### Create Tag

**Endpoint**: `POST /api/profile_automation/tags`

**Request Body**:
```json
{
  "name": "chantall",
  "description": "Chantall campaign accounts"
}
```

**Response**:
```json
{
  "status": "success",
  "tag_id": 5
}
```

### Get Tags

**Endpoint**: `GET /api/profile_automation/tags`

**Response**:
```json
{
  "status": "success",
  "tags": [
    {"id": 1, "name": "chantall", "description": "...", "account_count": 30},
    {"id": 2, "name": "anna", "description": "...", "account_count": 20}
  ]
}
```

### Bulk Settings

**Endpoint**: `POST /api/accounts/bulk-settings`

**Request Body**:
```json
{
  "accounts": [
    {"device_id": "10.1.10.36_5555", "account_name": "account1"},
    {"device_id": "10.1.10.36_5555", "account_name": "account2"}
  ],
  "settings": {
    "sharepost_mention": "@mainaccount",
    "enable_mention_to_story": "true",
    "post_type_to_share": "post_reels"
  }
}
```

**Response**:
```json
{
  "status": "success",
  "updated_accounts": 24,
  "failed_accounts": []
}
```

---

## Integration with Other Features

### Profile Automation

After tagging accounts, you can use the **Profile Automation** page to:
1. Create a campaign for the tagged accounts
2. Change profile pictures, bios, usernames for all tagged accounts
3. Execute the campaign

**Example**:
```
1. Bulk Operations → Tag 30 accounts with "chantall"
2. Profile Automation → Quick Campaign
   - Select Tag: "chantall"
   - Mother Account: "chantall.main"
   - Actions: Change picture, bio, username
3. Execute campaign → 30 tasks created
4. Run Batch Processor → All accounts updated
```

### Manage Sources

After tagging accounts, you can use **Manage Sources** with tag filtering:
1. Go to Manage Sources → Follow Sources
2. Filter by Tag: Select "chantall"
3. View only accounts with "chantall" tag
4. Select all and update sources

**Example**:
```
1. Bulk Operations → Tag accounts with "fashion"
2. Manage Sources → Follow Sources
3. Filter by Tag: "fashion"
4. Select All → Update Follow Sources
```

---

## Files

### Frontend

**[bulk_operations.html](templates/bulk_operations.html)**
- Two-panel interface (Bulk Tagging | Copy Settings)
- Multi-select device dropdowns
- Tag selection and creation
- Real-time preview of operations
- Results display

### Backend

**[simple_app.py](simple_app.py:2514-2517)**
- Route: `/bulk_operations`
- Renders: `bulk_operations.html`

**[profile_automation_routes.py](profile_automation_routes.py:117-142)**
- Bulk tagging endpoint
- Tag CRUD endpoints

**[base.html](templates/base.html:52-53)**
- Navigation link to Bulk Operations

---

## User Interface

### Bulk Tagging Section

```
┌─────────────────────────────────────────────────────────────┐
│                      BULK TAGGING                           │
├──────────────────────────┬──────────────────────────────────┤
│ Step 1: Select Devices   │ Step 2: Select or Create Tag     │
│                          │                                  │
│ ┌──────────────────────┐ │ Existing Tags:                   │
│ │ 10.1.10.36_5555     │ │ [Dropdown: chantall, anna, ...]  │
│ │ 10.1.10.37_5555     │ │                                  │
│ │ 10.1.10.38_5555     │ │ -- OR --                         │
│ │ 192.168.101.3_5555  │ │                                  │
│ └──────────────────────┘ │ New Tag:                         │
│                          │ [Input: _____________]           │
│ [Select All Devices]     │                                  │
│                          │ Preview:                         │
│ Selected Devices: 3      │ Tag "chantall" will be applied   │
│ • 10.1.10.36_5555       │ to all accounts on 3 device(s)   │
│ • 10.1.10.37_5555       │                                  │
│ • 10.1.10.38_5555       │                                  │
└──────────────────────────┴──────────────────────────────────┘
│                  [Tag Accounts]                             │
└─────────────────────────────────────────────────────────────┘
```

### Copy Settings Section

```
┌─────────────────────────────────────────────────────────────┐
│                    COPY SETTINGS                            │
├────────────────┬───────────────────┬────────────────────────┤
│ Step 1: Source │ Step 2: Target    │ Step 3: Review         │
│                │                   │                        │
│ Device:        │ Filter by Device: │ Target Accounts:       │
│ [Dropdown]     │ ┌───────────────┐ │ 30 accounts selected   │
│                │ │ 10.1.10.36   │ │                        │
│ Account:       │ │ 10.1.10.37   │ │ ┌────────────────────┐ │
│ [Dropdown]     │ └───────────────┘ │ │ account1           │ │
│                │                   │ │ 10.1.10.36_5555    │ │
│ Current        │ Filter by Tag:    │ │ account2           │ │
│ Settings:      │ ┌───────────────┐ │ │ 10.1.10.36_5555    │ │
│ • Mention:     │ │ chantall     │ │ │ ...                │ │
│   @main        │ └───────────────┘ │ └────────────────────┘ │
│ • Post Type:   │                   │                        │
│   Reels        │ [Load Accounts]   │ Settings to Copy:      │
│                │                   │ ☑ Share Post Mention   │
│                │                   │ ☑ Post Type to Share   │
│                │                   │ ☑ Enable Mention Story │
└────────────────┴───────────────────┴────────────────────────┘
│          [Copy Settings to Selected Accounts]               │
└─────────────────────────────────────────────────────────────┘
```

---

## Benefits

### 1. Time Savings

**Before**: Tag 30 accounts individually
- Select account 1 → Add tag → Save
- Select account 2 → Add tag → Save
- ... (repeat 30 times)
- **Time**: ~15 minutes

**After**: Bulk tag by device
- Select 3 devices → Enter tag → Execute
- **Time**: ~30 seconds
- **Savings**: 97% faster

### 2. Consistency

- All accounts on a device get the same tag
- No risk of missing accounts
- No typos in tag names

### 3. Organization

- Group accounts by device location
- Group accounts by campaign
- Group accounts by category/niche

### 4. Integration

- Tagged accounts can be used in Profile Automation
- Tagged accounts can be filtered in Manage Sources
- Tagged accounts can be bulk updated

---

## Best Practices

### Tagging Strategy

1. **Device-Based Tags**
   - Tag by physical location: "paris_office", "ny_office"
   - Tag by device type: "phone_1", "tablet_2"

2. **Campaign-Based Tags**
   - Tag by marketing campaign: "Q1_2025", "BlackFriday"
   - Tag by testing groups: "test_group_a", "test_group_b"

3. **Category-Based Tags**
   - Tag by niche: "fashion", "fitness", "food"
   - Tag by account type: "main_accounts", "backup_accounts"

### Settings Copy Strategy

1. **Standardization**
   - Copy from a "golden" account to all others
   - Ensure consistent behavior across accounts

2. **Testing**
   - Test settings on one account first
   - Copy to a small group for validation
   - Then copy to all accounts

3. **Documentation**
   - Document which settings were copied
   - Keep a record of "mother accounts"
   - Track when settings were last updated

---

## Troubleshooting

### Issue: Tag not created

**Symptom**: Error when trying to bulk tag
**Cause**: Tag name is empty or invalid
**Solution**: Enter a valid tag name (letters, numbers, underscores)

### Issue: No accounts found

**Symptom**: "0 accounts selected" when loading target accounts
**Cause**: Filters are too restrictive or no accounts match
**Solution**:
- Remove some filters
- Check that accounts actually have the tags you're filtering by
- Try filtering by device only first

### Issue: Settings not copying

**Symptom**: "Failed to update" error
**Cause**: Source account settings not loaded
**Solution**:
- Ensure source device and account are selected
- Check that source account exists
- Verify account folder structure

---

## Future Enhancements

### Planned Features:

1. **Preview Mode**
   - See which accounts will be affected before executing
   - Dry-run mode for testing

2. **Untag Bulk**
   - Remove tags from multiple accounts at once
   - Untag all accounts on a device

3. **Settings Comparison**
   - Compare settings between accounts
   - Highlight differences

4. **Schedule Operations**
   - Schedule bulk tagging for later
   - Schedule settings copy with delays

5. **Audit Log**
   - Track who tagged what and when
   - Track settings changes history

---

## Summary

The Bulk Operations page streamlines account management by:
- **Bulk Tagging**: Tag all accounts on devices in seconds
- **Settings Copy**: Standardize settings across accounts

These tools integrate seamlessly with:
- Profile Automation (use tags for campaigns)
- Manage Sources (filter by tags)
- Account Inventory (organize by tags)

Access the page from the navigation: **Dashboard → Bulk Operations**
