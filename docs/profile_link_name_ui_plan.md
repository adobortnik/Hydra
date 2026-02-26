# Profile Link & Name — Dashboard UI Plan

## 1. Account Modal (Per-Account)

Add two new buttons in the account detail modal, below existing actions like "Switch to Private":

```
┌─────────────────────────────────────┐
│  Account: @modeljagger              │
│  Device: SAMSUNG RENTED 2           │
│  ─────────────────────────────────  │
│  Current Name: Model Jagger         │
│  Current Link: (none)               │
│  ─────────────────────────────────  │
│  [📝 Set Name]  [🔗 Set Link]      │
│  [🔒 Switch to Private]            │
│  [▶️ Start Bot]  [⏹ Stop Bot]      │
└─────────────────────────────────────┘
```

### Set Name Flow:
1. Click "Set Name" → inline input appears (or small modal)
2. Type new name → Click "Apply"
3. Dashboard queues task → device navigates to Edit Profile → sets name
4. Status updates: "Setting name..." → "✓ Name set" or "✗ Failed: reason"

### Set Link Flow:
1. Click "Set Link" → inline inputs for URL + optional Title
2. Type URL (e.g. `https://linktr.ee/jagger`) + Title (e.g. "Linktree")
3. Dashboard queues task → device opens Edit Profile → Links → sets URL
4. Status updates similar to name

### DB Fields (accounts table):
- `display_name` TEXT — current display name
- `display_name_set_at` TEXT — when it was last set
- `profile_link` TEXT — current profile URL
- `profile_link_title` TEXT — link title
- `profile_link_set_at` TEXT — when link was last set

---

## 2. Bulk Operations

### Option A: Dedicated Bulk Modal (Recommended)
New button in Operations dropdown: **"Set Profile Info"**

```
┌──────────────────────────────────────────┐
│  Bulk Set Profile Info                   │
│  ────────────────────────────────────    │
│  Select Accounts:                        │
│  ┌──────────────────────────────────┐    │
│  │ ☑ modeljagger (SAMSUNG RENTED 2)│    │
│  │ ☑ jaggerdesire (SAMSUNG RENTED 2│    │
│  │ ☑ jaggerlifestyle (SAMSUNG R... │    │
│  │ ☐ callmejagger_ (SAMSUNG RE... │    │
│  └──────────────────────────────────┘    │
│  [Select All] [Select by Device]         │
│                                          │
│  ☑ Set Name:  [________________]         │
│  ☑ Set Link:  [________________]         │
│    Title:     [________________]         │
│                                          │
│  ⚠ This will run on X accounts           │
│    sequentially (one device at a time)   │
│                                          │
│  [Cancel]  [🚀 Apply to Selected]        │
└──────────────────────────────────────────┘
```

### Option B: CSV/Template Import
For setting different names/links per account:

```
┌──────────────────────────────────────────┐
│  Bulk Import Profile Info                │
│  ────────────────────────────────────    │
│  Upload CSV:                             │
│  [Choose File]                           │
│                                          │
│  Format: username, name, link, title     │
│  Example:                                │
│  modeljagger, Model Jagger, https://..   │
│  jaggerdesire, Jagger Desire, https://.. │
│                                          │
│  [Preview] [Apply]                       │
└──────────────────────────────────────────┘
```

---

## 3. Implementation Priority

1. **Phase 1**: Per-account buttons in account modal (quick wins)
2. **Phase 2**: Bulk modal with same-value-for-all
3. **Phase 3**: CSV import for different values per account

---

## 4. API Endpoints Needed

```
POST /api/account/<id>/set-name     { "name": "..." }
POST /api/account/<id>/set-link     { "url": "...", "title": "..." }
POST /api/bulk/set-profile-info     { "account_ids": [...], "name": "...", "url": "...", "title": "..." }
```

Each endpoint queues a task that runs on the device when available.
Tasks execute sequentially per device (can't have two automation tasks on same device simultaneously).

---

## 5. Task Queue Approach

- Tasks go into a queue table: `profile_tasks`
- Fields: `id, account_id, device_id, task_type (set_name|set_link), payload (JSON), status, created_at, completed_at, error_message`
- Dashboard polls task status and shows progress
- Device runner picks up pending tasks between bot cycles
