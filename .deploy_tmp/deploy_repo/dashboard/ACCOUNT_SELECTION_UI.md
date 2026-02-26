# Account Selection UI - Quick Campaign Enhancement

## Overview
Enhanced the Quick Campaign modal with an interactive account selection UI that allows users to view and selectively choose which accounts to include in a campaign.

## Features Implemented

### 1. **Tag Account Count Display**
When a tag is selected in the Quick Campaign modal:
- Shows the total number of accounts (e.g., "144 accounts in this tag")
- Displays a "View & Select Accounts" button
- Updates the warning message dynamically

### 2. **Interactive Account Selection Panel**
Expandable section with:
- **Search Bar**: Filter accounts by username or device serial
- **Select All / Deselect All**: Quick selection controls
- **Account List**: Scrollable list (max 300px height) with checkboxes
- **Selection Counter**: Badge showing "X selected" in real-time

### 3. **Visual Feedback**
- Selected accounts have a green highlight and left border
- Check mark icon appears on selected accounts
- Hover effects on account items
- Smooth transitions and animations

### 4. **Smart Warning Messages**
The warning banner dynamically updates:
- **No selection**: "This will create tasks for ALL 144 accounts"
- **Partial selection**: "Campaign will run on 50 of 144 accounts (94 will be skipped)"
- **All selected**: "Campaign will run on all 144 accounts in this tag"

### 5. **Account Item Display**
Each account shows:
- Username (bold)
- Device serial (muted)
- Checkbox for selection
- Check icon when selected

## User Workflow

1. Open Quick Campaign modal
2. Select a tag from dropdown
3. See account count: "144 accounts in this tag"
4. Click "View & Select Accounts" button
5. Account selection panel expands with:
   - Search box to filter accounts
   - All accounts listed with checkboxes
   - Select All / None buttons
6. Search/filter accounts (e.g., type "chantall" to find matching usernames)
7. Check/uncheck specific accounts
8. See real-time counter: "50 selected"
9. Warning updates to show partial selection
10. Execute campaign with only selected accounts

## Code Changes

### HTML (`profile_automation.html`)
- Added account count badge after tag selector
- Added "View & Select Accounts" button
- Added expandable account selection section with:
  - Search input
  - Select All/None buttons
  - Account list container
  - Selection counter badge
- Made warning message dynamic (`id="campaignWarning"`)
- Added CSS for visual styling (hover effects, selected state, borders)

### JavaScript (`profile-automation.js`)
New variables:
- `campaignSelectedAccounts`: Set to track selected accounts in modal
- `campaignTagAccounts`: Array of all accounts for the tag

New functions:
- `loadTagAccountsForCampaign()`: Loads accounts when tag is selected
- `toggleAccountSelection()`: Shows/hides the account selection panel
- `renderCampaignAccounts()`: Renders the account list with checkboxes
- `selectAllCampaignAccounts()`: Selects all accounts
- `deselectAllCampaignAccounts()`: Deselects all accounts
- `updateCampaignSelectedCount()`: Updates counter and visual state
- `updateCampaignWarning()`: Updates warning message based on selection
- `filterCampaignAccounts()`: Filters accounts by search term

Updated functions:
- `executeQuickCampaign()`: Uses `campaignSelectedAccounts` for partial selection

## API Integration
No backend changes required! The existing `/api/profile_automation/quick_campaign` endpoint already supports the `selected_accounts` parameter:

```javascript
{
    "tag": "chantall",
    "mother_account": "chantall.rey",
    "selected_accounts": [
        {"device_serial": "192.168.1.100", "username": "chantall.1"},
        {"device_serial": "192.168.1.101", "username": "chantall.2"}
    ]
}
```

## Visual Design

### Colors
- **Selected accounts**: Green background (`rgba(72, 187, 120, 0.1)`) with green left border
- **Hover state**: Blue left border
- **Search/filter**: Dark theme consistent with dashboard

### Layout
- Responsive and fits within modal
- Scrollable list (max 300px) for large account sets
- Compact design with efficient space usage

## Benefits
1. **Selective Campaigns**: Run campaigns on specific accounts without tagging/untagging
2. **Testing**: Test campaigns on a few accounts before running on all
3. **Flexibility**: Exclude problematic accounts from batch operations
4. **Visibility**: See exactly which accounts will be affected
5. **Search**: Quickly find specific accounts in large tags

## Future Enhancements (Optional)
- Remember last selection per tag
- Save selection presets
- Bulk operations on filtered results
- Account grouping by device
- Multi-tag selection in one campaign
