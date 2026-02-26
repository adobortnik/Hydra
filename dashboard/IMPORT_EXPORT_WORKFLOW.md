# Account Import → Export Workflow Guide

## Complete Workflow: Supplier Accounts → CSV Export

This guide explains how to import accounts from your supplier and export them to CSV for use in your automation system.

---

## 📥 Step 1: Import Accounts from Supplier

### Your Supplier Format
```
2gg.2.bt:123aaa:CHN4 4RHF YSYP FCKL L2C5 CFHN TY54 PYOD
aleex._.abd:123aaa:N635 HDUK FMID IJG7 QIEX VYB6 NJPS XR4I
mepp_thes_heep:123aaa:EVCC AY5U 3PYA UW2F 75N3 DM23 A6E3 UHVF
```

**Format**: `username:password:2FA_TOKEN`
- Username: Instagram username
- Password: Account password
- 2FA Token: 2fa.live token (with spaces - will be cleaned automatically)

### Import Process

1. **Go to Import Page**
   - Navigate to: `/import-accounts`
   - Or click "Account Inventory" → "Import Accounts" button

2. **Select Device**
   - Choose which device these accounts belong to from dropdown
   - Example: "Device 1 (10.1.10.183_5555)"

3. **Paste Accounts**
   - Copy accounts from your supplier
   - Paste into the textarea
   - System automatically:
     - Counts accounts (shows badge)
     - Removes spaces from 2FA tokens
     - Shows preview of first 5 accounts

4. **Import**
   - Click "Import Accounts" button
   - Confirm: "Import 20 accounts to device...?"
   - Wait for success message
   - Auto-redirects to Account Inventory

### What Happens During Import

The system:
1. ✅ Parses each line (`username:password:2fa`)
2. ✅ Removes spaces from 2FA tokens (`CHN4 4RHF` → `CHN44RHF`)
3. ✅ Stores in account_inventory database
4. ✅ Assigns to selected device
5. ✅ Marks as "available" status
6. ✅ Adds all attributes (Instagram package, etc.)

---

## 📤 Step 2: Export Accounts to CSV

### Export Process

1. **Go to Account Inventory**
   - Navigate to: `/account-inventory`
   - You'll see all imported accounts

2. **Select Accounts to Export**
   - Use checkboxes to select specific accounts
   - Or click "Select All" to export all

3. **Click "Export Selected"**
   - Button shows count: "Export Selected (20)"
   - Opens export modal

4. **Choose Export Options**
   - **Device**: Select device for CSV (or keep current assignments)
   - **Mark as Used**: Check to mark accounts as "used" after export
   - Click "Export" button

5. **Download CSV**
   - CSV file downloads automatically
   - Filename: `accounts_YYYYMMDD_HHMMSS.csv`

### CSV Format (Output)

The exported CSV includes ALL attributes:

```csv
device,username,password,instagram_package,two_factor_auth,starttime,endtime,follow,unfollow,...
10.1.10.183_5555,2gg.2.bt,123aaa,com.instagram.androim,CHN44RHFYSYPFCKLL2C5CFHNTY54PYOD,9,17,On,Off,...
10.1.10.183_5555,aleex._.abd,123aaa,com.instagram.androim,N635HDUKFMIDIJG7QIEXVYB6NJPSXR4I,9,17,On,Off,...
```

**Columns Include**:
- device (device serial)
- username
- password
- instagram_package (e.g., `com.instagram.androim`)
- two_factor_auth (2FA token, spaces removed)
- starttime, endtime (automation schedule)
- follow, unfollow, like, comment, story, mute (feature toggles)
- followmethod, unfollowmethod, mutemethod
- followaction, unfollowaction, likeaction
- followdelay, unfollowdelay, likedelay, randomdelay
- followlimitperday, unfollowlimitperday, likelimitperday, limitperday
- unfollowdelayday, switchmode
- randomaction, followlimit

---

## 🔄 Complete Workflow Example

### Scenario: Import 20 accounts from supplier, export to CSV

#### Step-by-Step:

**1. Copy from supplier (email/chat/file)**
```
2gg.2.bt:123aaa:CHN4 4RHF YSYP FCKL L2C5 CFHN TY54 PYOD
aleex._.abd:123aaa:N635 HDUK FMID IJG7 QIEX VYB6 NJPS XR4I
... (18 more)
```

**2. Open Import Page**
- URL: `http://localhost:5000/import-accounts`

**3. Select Device**
- Choose: "Device 1 (10.1.10.183_5555)"

**4. Paste Accounts**
- Paste into textarea
- See: "20 accounts" badge
- See preview showing first 5 with 2FA badges

**5. Click Import**
- Confirm dialog: "Import 20 accounts to device 10.1.10.183_5555?"
- Click "OK"
- Success: "Successfully imported 20 accounts"
- Auto-redirect to Account Inventory

**6. View in Account Inventory**
- See all 20 accounts listed
- Status: "Available" (green badge)
- Device: "10.1.10.183_5555"
- 2FA tokens visible (masked: ••••••••)

**7. Select Accounts for Export**
- Click "Select All" (selects all 20)
- Or manually check specific accounts

**8. Export to CSV**
- Click "Export Selected (20)"
- Modal opens
- Select device: "10.1.10.183_5555" (or change to different device)
- Check "Mark as used" (optional)
- Click "Export"

**9. CSV Downloaded**
- File: `accounts_20251121_143022.csv`
- Contains all 20 accounts with full attributes
- Ready to use in automation!

**10. Accounts Marked as Used**
- If you checked "Mark as used"
- Status changes: "Available" → "Used"
- Helps track which accounts have been exported

---

## 📋 Import Page Features

### Real-Time Features

#### ✅ Account Counter
- Shows count as you type: "20 accounts"
- Updates dynamically

#### ✅ Preview Panel
- Shows first 5 accounts
- Displays username + 2FA badge
- Shows "... and 15 more" for remaining

#### ✅ Auto-Cleanup
- Removes spaces from 2FA tokens automatically
- `CHN4 4RHF YSYP` → `CHN44RHFYSYP`

#### ✅ Validation
- Device selection required
- Accounts text required
- Import button disabled until both filled

#### ✅ Confirmation
- Shows count before importing
- Requires OK/Cancel

### UI Components

```
┌─────────────────────────────────────────┐
│ Import Instagram Accounts               │
├─────────────────────────────────────────┤
│ [Info Box: Format explanation]          │
│                                         │
│ Select Device: [Dropdown ▼]            │
│                                         │
│ Accounts: [20 accounts]                │
│ ┌─────────────────────────────────┐   │
│ │ 2gg.2.bt:123aaa:CHN4 4RHF...   │   │
│ │ aleex._.abd:123aaa:N635...     │   │
│ │ mepp_thes_heep:123aaa:EVCC...  │   │
│ └─────────────────────────────────┘   │
│                                         │
│ Import Preview:                         │
│ ┌─────────────────────────────────┐   │
│ │ 👤 2gg.2.bt [2FA]              │   │
│ │ 👤 aleex._.abd [2FA]           │   │
│ │ ... and 18 more                 │   │
│ └─────────────────────────────────┘   │
│                                         │
│ [◄ Back]              [Import ✓]      │
└─────────────────────────────────────────┘
```

---

## 📊 Account Inventory Page Features

### Filter & Search

- **Filter by Status**: All / Available / Used
- **Search**: By username
- **Device Filter**: Show accounts for specific device

### Bulk Operations

#### Select Multiple
- Individual checkboxes
- "Select All" button
- Shows count: "Export Selected (5)"

#### Export Modal
```
┌────────────────────────────────┐
│ Export Accounts                │
├────────────────────────────────┤
│ Device: [Select Device ▼]     │
│                                │
│ ☑ Mark exported as 'used'     │
│                                │
│ [Cancel]          [Export]     │
└────────────────────────────────┘
```

#### Mark as Used
- Bulk operation
- Changes status: Available → Used
- Helps track which accounts exported

---

## 🔐 2FA Token Handling

### Input Format (From Supplier)
```
CHN4 4RHF YSYP FCKL L2C5 CFHN TY54 PYOD
N635 HDUK FMID IJG7 QIEX VYB6 NJPS XR4I
EVCC AY5U 3PYA UW2F 75N3 DM23 A6E3 UHVF
```

**With spaces** - System handles this!

### Processed Format (Stored in DB)
```
CHN44RHFYSYPFCKLL2C5CFHNTY54PYOD
N635HDUKFMIDIJG7QIEXVYB6NJPSXR4I
EVCCAY5U3PYAUW2F75N3DM23A6E3UHVF
```

**No spaces** - Ready for automation!

### CSV Export Format
```csv
two_factor_auth
CHN44RHFYSYPFCKLL2C5CFHNTY54PYOD
N635HDUKFMIDIJG7QIEXVYB6NJPSXR4I
EVCCAY5U3PYAUW2F75N3DM23A6E3UHVF
```

**Clean tokens** - Works with 2fa.live API!

---

## 🎯 Use Cases

### Use Case 1: New Device Setup

1. **Import 50 accounts** from supplier
2. **Assign to new device** during import
3. **Export all 50** to CSV
4. **Import CSV** into device automation system
5. **Start automation** with all accounts

### Use Case 2: Selective Export

1. **Import 100 accounts** to inventory
2. **Filter** to show only "Available"
3. **Select 20 accounts** for Device 1
4. **Export** those 20 to CSV for Device 1
5. **Select 30 accounts** for Device 2
6. **Export** those 30 to CSV for Device 2
7. Remaining 50 stay in inventory for later

### Use Case 3: Account Rotation

1. **Import new batch** (20 accounts)
2. **Export to replace old accounts** on device
3. **Mark exported as "used"**
4. Old accounts now marked as "used"
5. New accounts ready for automation

---

## ⚙️ Technical Details

### Import API

**Endpoint**: `POST /api/inventory/accounts/import`

**Request**:
```json
{
  "accounts_text": "user1:pass1:TOKEN1\nuser2:pass2:TOKEN2",
  "device_id": "10.1.10.183_5555"
}
```

**Response**:
```json
{
  "message": "Successfully imported 2 accounts",
  "imported": 2,
  "failed": 0
}
```

### Export API

**Endpoint**: `POST /export_accounts`

**Request** (form data):
```
account_ids: [123, 124, 125]
device_id: "10.1.10.183_5555"
mark_as_used: true
```

**Response**: CSV file download

### Database Schema

**account_inventory table**:
```sql
CREATE TABLE account_inventory (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE,
    password TEXT,
    two_factor_auth TEXT,
    device TEXT,
    instagram_package TEXT DEFAULT 'com.instagram.android',
    status TEXT DEFAULT 'available',
    date_added TIMESTAMP,
    date_used TIMESTAMP,
    -- ... (26 more columns for automation settings)
)
```

---

## 🐛 Troubleshooting

### Import Issues

**Problem**: "Error: Invalid format"
- **Solution**: Ensure format is `username:password:2FA_TOKEN`
- Each line must have at least 2 colons

**Problem**: "Duplicate username"
- **Solution**: Username already exists in inventory
- Delete old entry or use different username

**Problem**: 2FA tokens not working in automation
- **Solution**: Check spaces were removed
- Verify token is valid on 2fa.live

### Export Issues

**Problem**: CSV not downloading
- **Solution**: Check browser popup blocker
- Try different browser

**Problem**: Accounts not in CSV
- **Solution**: Ensure accounts were selected (checkbox checked)
- Check device filter is correct

**Problem**: Wrong attributes in CSV
- **Solution**: Attributes come from default settings
- Modify in Account Inventory before export

---

## 📝 Best Practices

### Import Best Practices

1. ✅ **Always select device** before import
2. ✅ **Review preview** before importing
3. ✅ **Import in batches** (20-50 at a time)
4. ✅ **Verify 2FA tokens** after import
5. ✅ **Check for duplicates** before importing

### Export Best Practices

1. ✅ **Filter before selection** (by device, status)
2. ✅ **Mark as used** after export
3. ✅ **Download to organized folder** (`accounts/device1/`)
4. ✅ **Verify CSV** before using in automation
5. ✅ **Keep backup** of CSV files

### Workflow Best Practices

1. ✅ **Import → Review → Export** (don't rush)
2. ✅ **Use device naming** (Device 1, Device 2, etc.)
3. ✅ **Track which accounts used** (mark as used)
4. ✅ **Regular cleanup** (remove used accounts)
5. ✅ **Test with small batch** first (5-10 accounts)

---

## 🎉 Summary

### Complete Workflow

```
Supplier Accounts (with spaces in 2FA)
         ↓
  Import Page (paste, select device)
         ↓
  Account Inventory (stored, cleaned)
         ↓
  Select & Export (choose accounts)
         ↓
  CSV Download (all attributes included)
         ↓
  Use in Automation System ✓
```

### Key Features

- ✅ Handles 2FA tokens with spaces automatically
- ✅ Device assignment during import
- ✅ Real-time preview and validation
- ✅ Bulk export with all attributes
- ✅ Status tracking (available/used)
- ✅ Selective export (choose which accounts)

### Time Savings

- **Before**: Manually format 20 accounts → 30 minutes
- **After**: Paste 20 accounts → 30 seconds! 🚀

---

**Ready to use!** Your supplier accounts → CSV workflow is now complete and optimized! 🎯
