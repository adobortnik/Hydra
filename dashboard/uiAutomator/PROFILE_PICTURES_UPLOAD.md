# Profile Pictures - Simple Upload System

## Quick Start

### 1. **Drop images into the upload folder**
```
uiAutomator/profile_pictures/uploaded/
```

### 2. **Run your campaign**
The system automatically:
- Scans the upload folder
- Imports new images to database
- Assigns them to accounts
- Uploads them to devices

**That's it!** No manual importing needed.

---

## How It Works

### Upload Folder Location

```
full_igbot_14.2.4/
└── uiAutomator/
    └── profile_pictures/
        ├── male/           (optional - manual organization)
        ├── female/         (optional - manual organization)
        ├── neutral/        (optional - manual organization)
        └── uploaded/       ← DROP YOUR IMAGES HERE
```

### Supported Formats

- ✅ `.jpg` / `.jpeg`
- ✅ `.png`
- ✅ `.gif`
- ✅ `.webp`

### Auto-Import Process

**When you run a campaign**, the system automatically:

1. **Scans** `profile_pictures/uploaded/` folder
2. **Checks** database for existing images (by filename)
3. **Imports** new images not yet in database
4. **Assigns** to accounts based on campaign strategy
5. **Uploads** to devices and sets as profile picture

### Import Output

```
======================================================================
AUTO-IMPORTING PROFILE PICTURES
======================================================================

Scanning profile_pictures/uploaded/ for images...
Found 5 image file(s)

  ⊗ Skipping pic1.jpg (already imported)
  ✓ Imported pic2.jpg (ID: 42)
  ✓ Imported pic3.png (ID: 43)
  ⊗ Skipping pic4.jpg (already imported)
  ✓ Imported pic5.jpg (ID: 44)

Import complete: 3 new, 2 skipped, 5 total
✓ Imported 3 new profile picture(s)
```

---

## Complete Workflow

### Step 1: Add Images

**Option A: Direct drop**
```bash
# Just copy your images
cp /path/to/your/images/*.jpg uiAutomator/profile_pictures/uploaded/
```

**Option B: Windows drag-and-drop**
- Open `uiAutomator/profile_pictures/uploaded/` folder
- Drag images from your computer
- Done!

### Step 2: Create Campaign (Dashboard)

1. Go to Profile Automation page
2. Click "Quick Campaign"
3. Fill in:
   - Tag: `chantall`
   - Mother account: `chantie.rey`
   - Mother bio: `backup acc @chantie.rey`
4. Check **"Change Picture"**
5. Click "Execute Campaign"

### Step 3: Run Processor

```bash
cd uiAutomator
python automated_profile_manager.py
```

**What happens:**
```
AUTO-IMPORTING PROFILE PICTURES
Found 3 new images, importing...
✓ Imported 3 new profile picture(s)

Processing Task ID: 123
  Profile picture: Transferring pic2.jpg to device...
  ✓ Uploaded to device
  ✓ Set as profile picture
  ✓ Username changed
  ✓ Bio updated
```

---

## Manual Import (Optional)

If you want to import images **without running a campaign**:

```bash
cd uiAutomator
python profile_automation_db.py
```

Output:
```
Database initialized at: profile_automation.db
Profile pictures directory: profile_pictures

Checking for new profile pictures...
Scanning profile_pictures/uploaded/ for images...
Found 5 image file(s)
  ✓ Imported pic1.jpg (ID: 1)
  ✓ Imported pic2.jpg (ID: 2)
  ✓ Imported pic3.png (ID: 3)

Import complete: 3 new, 0 skipped, 3 total
```

---

## How Images Are Assigned

### Campaign Strategy: `rotate`

Images are distributed evenly:

```
Account 1 → Image 1 (pic1.jpg)
Account 2 → Image 2 (pic2.jpg)
Account 3 → Image 3 (pic3.png)
Account 4 → Image 1 (pic1.jpg)  ← cycles back
Account 5 → Image 2 (pic2.jpg)
...
```

### Campaign Strategy: `random`

Images are assigned randomly:
```
Account 1 → Image 3 (random)
Account 2 → Image 1 (random)
Account 3 → Image 3 (random)
Account 4 → Image 2 (random)
...
```

### Campaign Strategy: `least_used`

Images that have been used the least get priority:
```
Account 1 → Image 1 (used 0 times)
Account 2 → Image 2 (used 0 times)
Account 3 → Image 3 (used 0 times)
Account 4 → Image 1 (used 1 time) ← least used
...
```

---

## Database Storage

Imported images are tracked in `profile_automation.db`:

```sql
SELECT id, filename, category, times_used, last_used
FROM profile_pictures;
```

Example:
```
| id | filename  | category | times_used | last_used           |
|----|-----------|----------|------------|---------------------|
| 1  | pic1.jpg  | uploaded | 2          | 2025-11-02 14:30:00 |
| 2  | pic2.jpg  | uploaded | 1          | 2025-11-02 14:25:00 |
| 3  | pic3.png  | uploaded | 0          | NULL                |
```

- `category`: Always `"uploaded"` for auto-imported images
- `times_used`: How many times this image has been used
- `last_used`: When it was last assigned

---

## Best Practices

### 1. **Name your images descriptively**
```
✓ Good: blonde_girl_1.jpg, brunette_casual_2.jpg
✗ Bad: IMG_1234.jpg, DSC_5678.png
```

### 2. **Don't delete images from upload folder**
Once imported, images can stay in the folder. They'll be skipped on next import.

### 3. **Add images before creating campaign**
For best results:
1. Drop images in `uploaded/` folder
2. Then create and execute campaign
3. System auto-imports on execution

### 4. **Check image quality**
- Use clear, high-quality images
- Instagram profile pictures should be at least 110x110 pixels
- Recommended: 500x500 or larger

---

## Troubleshooting

### Q: Images not being imported

**Check:**
1. Images are in correct folder: `uiAutomator/profile_pictures/uploaded/`
2. File extensions are supported (jpg, png, gif, webp)
3. Run manual import to see errors:
   ```bash
   python profile_automation_db.py
   ```

### Q: Same image being used for all accounts

**Cause:** Only one image in database, or `rotate` strategy with one image.

**Fix:** Add more images to `uploaded/` folder.

### Q: "No profile pictures found" error

**Cause:** Database has no images, and upload folder is empty.

**Fix:**
1. Add at least one image to `profile_pictures/uploaded/`
2. Run campaign (auto-imports)
3. Or run `python profile_automation_db.py`

### Q: Want to remove an imported image

```python
# In Python:
import sqlite3
conn = sqlite3.connect('profile_automation.db')
cursor = conn.cursor()

# Delete by filename
cursor.execute('DELETE FROM profile_pictures WHERE filename = ?', ('unwanted.jpg',))
conn.commit()
conn.close()
```

---

## Advanced: Organizing by Gender/Category

If you want to organize images manually:

```
profile_pictures/
├── male/
│   ├── guy1.jpg
│   └── guy2.jpg
├── female/
│   ├── girl1.jpg
│   └── girl2.jpg
└── uploaded/      ← Auto-import from here
    └── mixed_pics.jpg
```

**Manual import with category:**
```python
from profile_automation_db import add_profile_picture

# Male images
add_profile_picture(
    filename='guy1.jpg',
    original_path='profile_pictures/male/guy1.jpg',
    gender='male',
    category='professional'
)

# Female images
add_profile_picture(
    filename='girl1.jpg',
    original_path='profile_pictures/female/girl1.jpg',
    gender='female',
    category='casual'
)
```

**But** for simplicity, just use the `uploaded/` folder and let the system handle it!

---

## Summary

### ✅ Simple Workflow

1. **Drop images** in `profile_pictures/uploaded/`
2. **Create campaign** in dashboard
3. **Run processor**: `python automated_profile_manager.py`
4. **Done!** Images automatically imported and assigned

### ✅ Features

- **Auto-import** on campaign execution
- **Duplicate detection** (skips already imported files)
- **Usage tracking** (knows which images are least used)
- **Rotate/random/least-used** assignment strategies
- **Multiple formats** supported (jpg, png, gif, webp)

### ✅ No Manual Work Needed

Just drop images in the folder and run your campaign. The system handles everything else automatically!

---

## Files Modified

1. **[profile_automation_db.py](profile_automation_db.py)**
   - Lines 431-497: `auto_import_profile_pictures()` function
   - Lines 504-506: Auto-import on database initialization

2. **[tag_based_automation.py](tag_based_automation.py)**
   - Lines 442-448: Auto-import before campaign execution

## Example: Complete Campaign with Images

```bash
# Step 1: Add 10 images
cp ~/Downloads/profile_pics/*.jpg uiAutomator/profile_pictures/uploaded/

# Step 2: Tag accounts (dashboard or CLI)
# Dashboard → Tags → Select devices → Tag as "chantall"

# Step 3: Create campaign (dashboard)
# Profile Automation → Quick Campaign
# - Tag: chantall
# - Mother: chantie.rey
# - Mother Bio: backup acc @chantie.rey
# - ✓ Change Picture
# - ✓ Change Bio
# - ✓ Change Username

# Step 4: Run processor
cd uiAutomator
python automated_profile_manager.py
```

**Output:**
```
AUTO-IMPORTING PROFILE PICTURES
Found 10 image file(s)
  ✓ Imported pic1.jpg (ID: 1)
  ✓ Imported pic2.jpg (ID: 2)
  ...
  ✓ Imported pic10.jpg (ID: 10)
Import complete: 10 new, 0 skipped, 10 total

Processing 10 tasks...

Task 1: ✓ SUCCESS (pic1.jpg assigned)
Task 2: ✓ SUCCESS (pic2.jpg assigned)
...
Task 10: ✓ SUCCESS (pic10.jpg assigned)

All tasks completed!
```

**Perfect!** All 10 accounts now have different profile pictures, all automatically.
