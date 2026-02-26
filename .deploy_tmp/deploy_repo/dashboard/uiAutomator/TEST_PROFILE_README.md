# Profile Changes Test Script

Simple test script to verify bio and profile picture changes work correctly.

## Setup

1. **Prepare the device**:
   - Device should be connected (check with `adb devices`)
   - Instagram app should be installed
   - Logged into an account you want to test with

2. **Add a test image** (for profile picture test):
   ```bash
   mkdir profile_pictures
   # Copy a JPG or PNG image into profile_pictures/
   ```

## Run the Test

```bash
cd uiAutomator
python test_profile_changes.py
```

## What the Script Does

The script will first prompt you to:
1. **Select a device** - Choose from connected ADB devices
2. **Select Instagram package** - Choose from original Instagram or clones (e-p)

Then it will run the following tests:

### Test 1: Bio Change ✍️
- Navigates to edit profile
- Changes the bio to: "🌟 Testing automation | 📱 Bot powered"
- You can confirm or skip

### Test 2: Profile Picture Change 📸
- Transfers test image to device
- Opens profile picture selector
- Selects the image from gallery
- You can confirm or skip

### Test 3: Save Changes 💾
- Saves all changes to Instagram profile

## Expected Output

```
======================================================================
INSTAGRAM PROFILE AUTOMATION - SETUP
======================================================================

======================================================================
CONNECTED DEVICES
======================================================================
1. Serial: 192.168.101.107_5555  Model: SM-G973F        Product: beyond1
======================================================================

Select device (1-1) or 'q' to quit: 1

Selected device: SM-G973F (192.168.101.107_5555)

======================================================================
INSTAGRAM PACKAGE SELECTION
======================================================================
0. com.instagram.android (Original Instagram)
1. com.instagram.androide (Clone E)
2. com.instagram.androidf (Clone F)
...
12. com.instagram.androidp (Clone P)
======================================================================

Select Instagram package (0-12) or 'q' to quit: 5

Selected: com.instagram.androidi

======================================================================
PROFILE CHANGES TEST
======================================================================

📋 Configuration:
Device: 192.168.101.107_5555
Instagram Package: com.instagram.androidi

======================================================================
STEP 1: FIND TEST IMAGE
======================================================================
✅ Found image: test.jpg

======================================================================
STEP 2: CONNECT TO DEVICE & OPEN INSTAGRAM
======================================================================
✅ Device connected
✅ Instagram opened
✅ On profile page
✅ On edit profile page

======================================================================
TEST 1: CHANGE BIO
======================================================================
Proceed with bio change? (y/n): y
✅ Bio changed successfully!

======================================================================
TEST 2: CHANGE PROFILE PICTURE
======================================================================
Proceed with profile picture change? (y/n): y
✅ Image transferred to: /sdcard/Pictures/profile_pic_1234567890.jpg
✅ Profile picture changed successfully!

======================================================================
SAVING CHANGES
======================================================================
Save profile changes? (y/n): y
✅ Changes saved successfully!
```

## Troubleshooting

**Device not connected:**
```bash
adb devices
# If not listed, reconnect device
```

**Instagram won't open:**
- Check if package name is correct
- Manually open Instagram first
- Make sure account is logged in

**Bio change fails:**
- Check if you're on edit profile screen
- Try manually to see if there are UI differences

**Profile picture fails:**
- Make sure test image exists in `profile_pictures/`
- Image should be JPG or PNG format
- Check if gallery permissions are granted

## Notes

- This is a **manual test script** - you control each step
- Changes are **real** - use a test account!
- You can skip any test by entering 'n'
- If you don't save, changes will be lost
