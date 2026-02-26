# Manage Sources - Device and Tag Filtering Improvements

## Summary

Enhanced the Manage Sources page with multi-select device and tag filtering capabilities across all three tabs (Follow Sources, Share Sources, and Bulk Settings).

---

## Changes Made

### 1. Frontend Changes ([manage_sources_new.html](templates/manage_sources_new.html))

#### **HTML Structure Updates**

Added filtering UI for all three tabs:

- **Device Filter**: Multi-select dropdown showing all available devices
- **Tag Filter**: Multi-select dropdown showing all tags from profile automation system
- **Clear Filters Button**: Resets all filters with one click

```html
<div class="mb-3">
    <label for="followDeviceSelect" class="form-label">Filter by Device:</label>
    <select class="form-select bg-dark text-white border-secondary" id="followDeviceSelect" multiple size="3">
        <!-- Device options will be populated dynamically -->
    </select>
    <small class="text-white-50">Hold Ctrl/Cmd to select multiple devices</small>
</div>

<div class="mb-3">
    <label for="followTagSelect" class="form-label">Filter by Tag:</label>
    <select class="form-select bg-dark text-white border-secondary" id="followTagSelect" multiple size="3">
        <!-- Tag options will be populated dynamically -->
    </select>
    <small class="text-white-50">Hold Ctrl/Cmd to select multiple tags</small>
</div>

<div class="mb-2">
    <button class="btn btn-sm btn-outline-secondary w-100" id="followClearFiltersBtn">
        <i class="fas fa-filter-circle-xmark me-1"></i> Clear Filters
    </button>
</div>
```

#### **JavaScript Enhancements**

**Global Helper Functions:**

1. **`populateDeviceDropdown(dropdownId, accounts)`**
   - Extracts unique device IDs from accounts
   - Populates dropdown with sorted device list
   - Supports multi-select

2. **`populateTagDropdown(dropdownId)`**
   - Fetches tags from `/api/profile_automation/tags`
   - Populates dropdown with tag names
   - Supports multi-select

3. **`applyFilters(accounts, deviceSelect, tagSelect, searchTerm)`**
   - Applies device filter (if devices selected)
   - Applies tag filter (if tags selected)
   - Applies search term filter
   - Returns filtered account list

**Per-Tab Enhancements (Follow, Share, Settings):**

1. **State Management:**
   ```javascript
   let currentSearchTerm = '';  // Track search input
   ```

2. **`applyAllFilters()` Function:**
   ```javascript
   function applyAllFilters() {
       filteredAccounts = applyFilters(accounts, deviceSelect, tagSelect, currentSearchTerm);
       renderAccounts();
   }
   ```

3. **Event Listeners:**
   - Search input: Updates `currentSearchTerm` and calls `applyAllFilters()`
   - Device select change: Calls `applyAllFilters()`
   - Tag select change: Calls `applyAllFilters()`
   - Clear filters button: Resets all filters and calls `applyAllFilters()`

4. **Filter Clearing Logic:**
   ```javascript
   clearFiltersBtn.addEventListener('click', function() {
       accountSearch.value = '';
       currentSearchTerm = '';
       deviceSelect.selectedIndex = -1;  // Clear multi-select
       tagSelect.selectedIndex = -1;     // Clear multi-select
       applyAllFilters();
   });
   ```

---

### 2. Backend Changes ([manage_sources.py](manage_sources.py))

#### **New Function: `get_account_tags(device_id, account_name)`**

Fetches tags associated with an account from the profile automation database:

```python
def get_account_tags(device_id, account_name):
    try:
        # Path to profile automation database
        profile_db_path = os.path.join(BASE_DIR, 'uiAutomator', 'profile_automation.db')
        if not os.path.exists(profile_db_path):
            return []

        conn = get_db_connection(profile_db_path)
        cursor = conn.cursor()

        # Query account_tags table
        cursor.execute('''
            SELECT t.name
            FROM account_tags at
            JOIN tags t ON at.tag_id = t.id
            WHERE at.device_serial = ? AND at.username = ?
        ''', (device_id, account_name))

        tags = [row[0] for row in cursor.fetchall()]
        conn.close()

        return tags
    except Exception as e:
        print(f"Error getting tags for {device_id}/{account_name}: {e}")
        return []
```

#### **Updated Function: `get_all_accounts_with_sources(source_type)`**

Enhanced to include account tags in the response:

```python
# Get tags for this account
account_tags = get_account_tags(device_id, account_name)

# Add account info with sources status
all_accounts.append({
    'device_id': device_id,
    'account_name': account_name,
    'sources_exists': sources_exists,
    'sources_content': sources_content,
    'sources_path': sources_path,
    'usernames_count': len(sources_content.strip().split('\n')) if sources_content.strip() else 0,
    'source_type': source_type,
    'file_name': file_name,
    'tags': account_tags  # NEW: Include tags
})
```

---

## Features

### 1. **Multi-Device Filtering**

- Select one or multiple devices from the dropdown
- Only shows accounts from selected devices
- Works in combination with search and tag filters

**Example Use Case:**
- User has 10 devices with 120 total accounts
- Selects devices `10.1.10.36_5555` and `10.1.10.37_5555`
- Only sees accounts from those 2 devices (24 accounts)

### 2. **Tag-Based Filtering**

- Select one or multiple tags from the dropdown
- Only shows accounts that have at least one of the selected tags
- Works in combination with search and device filters

**Example Use Case:**
- User has tagged 30 accounts with "chantall" and 20 with "anna"
- Selects tag "chantall"
- Only sees the 30 accounts tagged with "chantall"

### 3. **Combined Filtering**

All filters work together:

**Example:**
- Device filter: `10.1.10.36_5555`
- Tag filter: `chantall`
- Search: `main`
- Result: Shows only accounts from device `10.1.10.36_5555` that are tagged `chantall` and contain "main" in username or device ID

### 4. **Clear All Filters**

Single button to reset:
- Clears device selection
- Clears tag selection
- Clears search input
- Shows all accounts again

### 5. **Select All with Filters**

The "Select All Accounts" checkbox now respects filters:
- Only selects accounts that match current filters
- Useful for bulk operations on filtered subsets

---

## User Workflow

### Scenario 1: Update sources for specific devices

1. Go to Manage Sources → Follow Sources tab
2. Click device dropdown and select 2-3 devices (Ctrl+Click)
3. View filtered list of accounts from those devices
4. Click "Select All Accounts" to select all filtered accounts
5. Optional: Uncheck specific accounts
6. Enter usernames in the editor
7. Click "Update Follow Sources"

### Scenario 2: Update sources for tagged accounts

1. Go to Manage Sources → Share Sources tab
2. Click tag dropdown and select "chantall" tag
3. View all accounts tagged with "chantall"
4. Select specific accounts or "Select All"
5. Enter usernames to share from
6. Click "Update Share Sources"

### Scenario 3: Combined filtering

1. Go to Manage Sources → Bulk Settings tab
2. Select multiple devices from device dropdown
3. Select multiple tags from tag dropdown
4. Type partial username in search box
5. Result: Accounts matching ALL criteria
6. Select accounts and update settings

---

## Technical Details

### Multi-Select Dropdown Behavior

- **HTML**: `<select multiple size="3">`
- **Clearing**: `dropdown.selectedIndex = -1` (clears all selections)
- **Reading selections**: `Array.from(dropdown.selectedOptions).map(opt => opt.value)`

### Filter Logic Flow

```
User Action → Event Listener → applyAllFilters() → applyFilters() → renderAccounts()
```

1. User changes filter (device, tag, or search)
2. Event listener captures change
3. `applyAllFilters()` called
4. `applyFilters()` applies all three filter types
5. `renderAccounts()` updates the UI

### Backend Integration

- Fetches tags from `uiAutomator/profile_automation.db`
- Joins `account_tags` and `tags` tables
- Returns tag names as array in account object
- If database doesn't exist, returns empty tags array

---

## Files Modified

1. **`templates/manage_sources_new.html`**
   - Added device/tag filter UI for all 3 tabs
   - Added helper functions for filtering
   - Added event listeners for filters
   - Enhanced `loadAccounts()` to populate tag dropdown

2. **`manage_sources.py`**
   - Added `get_account_tags()` function
   - Modified `get_all_accounts_with_sources()` to include tags
   - Database query joins `account_tags` and `tags` tables

---

## Testing

### Manual Testing Steps:

1. **Device Filter Test:**
   - Select 1-2 devices
   - Verify only accounts from selected devices appear
   - Clear filters and verify all accounts return

2. **Tag Filter Test:**
   - Tag some accounts using Profile Automation
   - Select tag from dropdown
   - Verify only tagged accounts appear

3. **Combined Filter Test:**
   - Apply device + tag + search filters together
   - Verify results match all criteria

4. **Clear Filters Test:**
   - Apply multiple filters
   - Click "Clear Filters"
   - Verify all filters reset and all accounts shown

5. **Multi-Tab Test:**
   - Test filtering in Follow Sources tab
   - Test filtering in Share Sources tab
   - Test filtering in Bulk Settings tab

---

## Benefits

1. **Faster Account Selection:**
   - Filter by device to see only relevant accounts
   - Filter by tag to work with grouped accounts
   - Combine filters for precise selection

2. **Bulk Operations Made Easy:**
   - Select all accounts from specific devices
   - Select all accounts with specific tags
   - Apply changes to filtered subset

3. **Improved UX:**
   - No more scrolling through hundreds of accounts
   - Clear visual feedback on filter state
   - One-click filter clearing

4. **Integration with Profile Automation:**
   - Tags from profile automation system
   - Consistent tagging across features
   - Centralized account organization

---

## Future Enhancements

1. **Filter Presets:**
   - Save common filter combinations
   - Quick access to favorite filters

2. **Account Count Badge:**
   - Show filtered count / total count
   - Example: "24 / 120 accounts"

3. **Filter Chips:**
   - Visual representation of active filters
   - Click to remove individual filters

4. **Advanced Tag Filtering:**
   - AND/OR logic for multiple tags
   - "Has all tags" vs "Has any tag"

---

## Conclusion

The enhanced filtering system provides powerful and flexible account selection capabilities, making bulk operations on large account sets significantly easier and more intuitive. The multi-select device and tag filters work seamlessly together, giving users precise control over which accounts they work with.
