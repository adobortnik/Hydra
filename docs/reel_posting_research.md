# Instagram Reel Posting — Android Automation Research

**Date:** February 2026  
**Context:** Phone farm with 100+ Android devices, IG clone apps (com.instagram.androie etc), ADB/UIAutomator2 automation  
**Goal:** Reliable end-to-end Reel posting: push video → verify indexed → navigate IG UI → post with caption

---

## Table of Contents

1. [Supported Video Formats on Instagram Android](#1-supported-video-formats-on-instagram-android)
2. [ADB Media Upload Best Practices](#2-adb-media-upload-best-practices)
3. [Gallery Visibility Verification](#3-gallery-visibility-verification)
4. [Complete Reel Creation UI Flow](#4-complete-reel-creation-ui-flow)
5. [.mov to .mp4 Conversion](#5-mov-to-mp4-conversion)
6. [Existing Codebase Integration Notes](#6-existing-codebase-integration-notes)
7. [Recommended Pipeline](#7-recommended-pipeline)

---

## 1. Supported Video Formats on Instagram Android

### 1.1 Container Formats

| Format | Extension | Supported? | Notes |
|--------|-----------|-----------|-------|
| **MP4 (MPEG-4 Part 14)** | `.mp4` | ✅ **Best choice** | The only officially recommended format. Universal support. |
| **MOV (QuickTime)** | `.mov` | ⚠️ **Partially** | Android's MediaStore can index it, but IG's gallery picker may show it without duration/thumbnail. The IG app internally re-encodes on upload, but the gallery picker experience is unreliable. **MOV with H.264 codec usually works, but H.265/ProRes MOV often fails.** IG on iOS handles .mov natively; Android is a second-class citizen for .mov. |
| **WebM** | `.webm` | ❌ **No** | Instagram does not accept WebM containers at all. The gallery picker won't display them, and even if force-fed, the upload fails. |
| **AVI** | `.avi` | ❌ **No** | Legacy format. Not supported by IG gallery picker on Android. |
| **MKV** | `.mkv` | ❌ **No** | Not supported. |
| **3GP** | `.3gp` | ⚠️ **Legacy** | Android can play it but IG won't pick it up reliably. Don't use. |

### 1.2 Video Codecs

| Codec | Supported? | Notes |
|-------|-----------|-------|
| **H.264 (AVC)** | ✅ **Best choice** | Universal compatibility. Baseline/Main/High profiles all work. IG re-encodes to H.264 on upload regardless. |
| **H.265 (HEVC)** | ⚠️ **Risky** | Newer Android devices (8.0+) can decode it, and IG *can* upload HEVC videos, but: (a) older devices may not show thumbnails, (b) some IG versions choke on HEVC in the trimmer, (c) MediaStore indexing of HEVC duration can be slow/broken. **Not recommended for automation.** |
| **VP9** | ❌ **No** | VP9 is a WebM codec. IG doesn't support it. |
| **AV1** | ❌ **No** | Too new. Not supported. |
| **ProRes** | ❌ **No** | Apple-specific. Doesn't work on Android at all. |

### 1.3 Audio Codecs

| Codec | Supported? | Notes |
|-------|-----------|-------|
| **AAC** | ✅ **Best** | Standard for MP4 containers. Use this. |
| **MP3** | ⚠️ | Works in some MP4 containers but non-standard. |
| **Opus** | ❌ | WebM audio codec. Not in MP4. |
| **PCM** | ❌ | Uncompressed. Too large, not supported. |

### 1.4 Reel Specifications

| Parameter | Value | Notes |
|-----------|-------|-------|
| **Max duration** | **3 minutes** (180 seconds) | Extended from 90s in January 2025. Reels < 15s can't use trending audio. |
| **Min duration** | **3 seconds** | IG rejects anything shorter. |
| **Aspect ratio** | **9:16 (vertical)** preferred | Supports 1.91:1 to 9:16. Non-9:16 gets letterboxed. For automation, always use 9:16. |
| **Resolution** | **1080×1920** recommended | Minimum 720p. IG downscales anything above 1080p. Max accepted is roughly 4K but it gets re-encoded to 1080p. |
| **Frame rate** | **30 FPS** recommended | Minimum 30 FPS per IG guidelines. 24 FPS works but may look choppy. 60 FPS is accepted but re-encoded to 30. |
| **File size** | **~250 MB max** | No official limit documented, but uploads above ~250 MB reliably fail. For a 3-min 1080p H.264 reel, target 50-100 MB. |
| **Bitrate** | **3.5-5 Mbps** recommended | H.264, 1080×1920, 30fps at 3.5 Mbps → ~80 MB for 3 min. Sweet spot for quality/size. |
| **Caption length** | **2,200 characters** | Same as feed posts. Hashtags count toward this limit. |

### 1.5 Summary: Ideal Format for Automation

```
Container:  MP4
Video codec: H.264 (Main or High profile)
Audio codec: AAC (128-192 kbps)
Resolution:  1080×1920 (9:16)
Frame rate:  30 FPS
Bitrate:     3.5-5 Mbps
Duration:    3-180 seconds
File size:   < 100 MB
```

**Always convert to MP4/H.264/AAC before pushing to device.** This eliminates all codec-related failures.

---

## 2. ADB Media Upload Best Practices

### 2.1 Methods Compared

#### Method A: `adb push` + `MEDIA_SCANNER_SCAN_FILE` Broadcast (✅ RECOMMENDED)

```bash
# Push file to device
adb -s <serial> push video.mp4 /sdcard/Pictures/video.mp4

# Trigger media scanner for the specific file
adb -s <serial> shell am broadcast \
  -a android.intent.action.MEDIA_SCANNER_SCAN_FILE \
  -d file:///sdcard/Pictures/video.mp4
```

**Pros:**
- Simple and reliable
- Media scanner reads actual file metadata (duration, resolution, codec)
- Duration is correctly populated in MediaStore
- Thumbnails are generated by the system
- Works on Android 7-14 (all our devices)
- **This is what our existing `post_content.py` uses and it works**

**Cons:**
- Media scanner is async — takes 1-5 seconds to complete indexing
- On heavily loaded devices, can take up to 10 seconds
- No confirmation callback via ADB (need to poll MediaStore)

**Android 10+ Scoped Storage Note:** The `MEDIA_SCANNER_SCAN_FILE` broadcast was **deprecated** in Android 10 (API 29) but still works on most devices through Android 14 because:
1. The broadcast receiver is still present in the MediaProvider
2. Files pushed to `/sdcard/Pictures/` (a standard public directory) are accessible
3. ADB operations run as `shell` user which has elevated storage permissions

If it ever stops working, fall back to Method B.

#### Method B: `content insert` into MediaStore

```bash
# Insert a row into MediaStore
adb -s <serial> shell content insert \
  --uri content://media/external/video/media \
  --bind _display_name:s:video.mp4 \
  --bind mime_type:s:video/mp4 \
  --bind _data:s:/storage/emulated/0/Pictures/video.mp4 \
  --bind duration:i:30000
```

**Pros:**
- Immediately creates a MediaStore entry (no async wait)
- Can set duration explicitly

**Cons:**
- ⚠️ **Creates a BROKEN entry** if the file doesn't exist yet or metadata is wrong
- Duration set manually may not match actual video (IG reads its own)
- **Thumbnail is NOT generated** — IG gallery shows a blank/black tile
- On Android 10+, the `_data` column is read-only for apps; ADB shell can write it but MediaProvider may not respect it
- Our testing showed this creates entries that IG's gallery picker cannot read properly
- **NOT RECOMMENDED** — our `post_content.py` explicitly avoids this: *"No content insert — it creates broken entries without metadata"*

#### Method C: Direct File Copy + `MediaScannerConnection` (App-Side)

```bash
# Push file
adb -s <serial> push video.mp4 /sdcard/Pictures/video.mp4

# Trigger full volume scan (HEAVY — scans everything)
adb -s <serial> shell am broadcast \
  -a android.intent.action.MEDIA_MOUNTED \
  -d file:///sdcard
```

**Pros:**
- Guaranteed to index everything

**Cons:**
- **Extremely slow** — rescans ALL media on the device (minutes on devices with lots of files)
- Can interfere with running apps
- **Never use this in automation**

#### Method D: `adb shell cmd media.session` / MediaStore via `content` provider

```bash
# Android 11+ alternative: use MediaStore content provider directly
adb -s <serial> shell content insert \
  --uri content://media/external/video/media \
  --bind _display_name:s:video.mp4 \
  --bind relative_path:s:Pictures \
  --bind mime_type:s:video/mp4 \
  --bind is_pending:i:1

# Then write file content to the returned URI... 
# (Not practical via ADB — requires app-level code)
```

**Verdict:** Not practical for ADB-only automation. This is the "proper" Android 10+ approach but requires an app running on the device to handle the file writing through content resolver.

### 2.2 Recommended Approach (What We Use)

```python
def push_media_to_device(adb_serial, local_path, remote_dir="/sdcard/Pictures"):
    """Push video and register in MediaStore. Returns remote path."""
    filename = os.path.basename(local_path)
    remote_path = f"{remote_dir}/{filename}"
    
    # 1. Create directory
    subprocess.run(['adb', '-s', adb_serial, 'shell', 'mkdir', '-p', remote_dir],
                   capture_output=True, timeout=10)
    
    # 2. Push file
    result = subprocess.run(['adb', '-s', adb_serial, 'push', local_path, remote_path],
                           capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"ADB push failed: {result.stderr}")
    
    # 3. Trigger media scanner
    subprocess.run(['adb', '-s', adb_serial, 'shell',
                   'am', 'broadcast', '-a',
                   'android.intent.action.MEDIA_SCANNER_SCAN_FILE',
                   '-d', f'file://{remote_path}'],
                   capture_output=True, timeout=10)
    
    # 4. Wait for indexing
    time.sleep(3)
    
    return remote_path
```

### 2.3 Push Location Best Practices

| Directory | Works? | Notes |
|-----------|--------|-------|
| `/sdcard/Pictures/` | ✅ Best | Standard media directory. IG gallery always scans here. |
| `/sdcard/DCIM/` | ✅ Good | Camera directory. Also reliably scanned. |
| `/sdcard/Movies/` | ✅ Good | Video directory. Works for video files. |
| `/sdcard/Download/` | ⚠️ | Some IG versions don't show Download folder in gallery picker. |
| `/sdcard/Documents/` | ❌ | Not a media directory. Won't appear in gallery. |
| `/data/local/tmp/` | ❌ | Not accessible to apps (no MediaStore entry). |

**Recommendation:** Use `/sdcard/Pictures/` — it's what we currently use and it's reliable across all Android versions and IG clone apps.

### 2.4 File Naming

- Use unique filenames to avoid collisions: `reel_{account_id}_{timestamp}.mp4`
- Avoid spaces and special characters in filenames
- Keep filenames short (< 50 chars)
- Always use `.mp4` extension

---

## 3. Gallery Visibility Verification

### 3.1 Query MediaStore via ADB

The key verification is: **Is the video indexed in MediaStore with a non-null, non-zero duration?**

Without duration, the IG gallery picker will show the video but with:
- `0:00` duration badge → IG may reject it or show an error on upload
- No thumbnail → user sees a blank tile
- Broken trimmer → IG can't calculate timeline

#### Basic Query

```bash
# Check if video is indexed at all
adb -s <serial> shell content query \
  --uri content://media/external/video/media \
  --projection _display_name:duration:_size:date_modified \
  --where "_display_name='video.mp4'"
```

**Expected output (good):**
```
Row: 0 _display_name=video.mp4, duration=30000, _size=5242880, date_modified=1708300000
```

**Bad outputs:**
```
# Not indexed yet:
No result found.

# Indexed but no duration (media scanner still processing):
Row: 0 _display_name=video.mp4, duration=NULL, _size=5242880, date_modified=1708300000

# Indexed with zero duration (corrupt file or wrong codec):
Row: 0 _display_name=video.mp4, duration=0, _size=5242880, date_modified=1708300000
```

#### Full Verification Query

```bash
# Get all relevant metadata
adb -s <serial> shell content query \
  --uri content://media/external/video/media \
  --projection "_display_name:duration:width:height:mime_type:_size" \
  --where "_display_name='video.mp4'"
```

**Expected for a good reel video:**
```
Row: 0 _display_name=video.mp4, duration=30000, width=1080, height=1920, mime_type=video/mp4, _size=5242880
```

### 3.2 Python Verification Function

This is already implemented in our `post_content.py` (`_verify_media_indexed` method), but here's the improved version:

```python
import subprocess
import re
import time

def verify_video_indexed(adb_serial, filename, min_duration_ms=1000, max_wait=15):
    """
    Wait until pushed video appears in MediaStore with valid duration.
    
    Args:
        adb_serial: Device serial (e.g., '10.1.11.4:5555')
        filename: Video filename (e.g., 'reel_123_1708300000.mp4')
        min_duration_ms: Minimum expected duration in ms (default 1s)
        max_wait: Max seconds to wait for indexing
    
    Returns:
        dict: {indexed: bool, duration_ms: int, width: int, height: int}
    """
    result = {'indexed': False, 'duration_ms': 0, 'width': 0, 'height': 0}
    
    for attempt in range(max_wait // 2):
        proc = subprocess.run(
            ['adb', '-s', adb_serial, 'shell', 'content', 'query',
             '--uri', 'content://media/external/video/media',
             '--projection', '_display_name:duration:width:height',
             '--where', f"_display_name='{filename}'"],
            capture_output=True, text=True, timeout=10)
        
        output = proc.stdout.strip()
        
        if output and 'No result' not in output:
            # Parse duration
            dur_match = re.search(r'duration=(\d+)', output)
            w_match = re.search(r'width=(\d+)', output)
            h_match = re.search(r'height=(\d+)', output)
            
            duration = int(dur_match.group(1)) if dur_match else 0
            width = int(w_match.group(1)) if w_match else 0
            height = int(h_match.group(1)) if h_match else 0
            
            if duration >= min_duration_ms:
                return {
                    'indexed': True,
                    'duration_ms': duration,
                    'width': width,
                    'height': height
                }
            elif duration == 0:
                # Indexed but duration not yet populated — scanner still working
                pass
        
        time.sleep(2)
    
    return result
```

### 3.3 Verification Checklist Before Starting IG Flow

1. ✅ File exists on device: `adb shell ls -la /sdcard/Pictures/video.mp4`
2. ✅ MediaStore entry exists: `content query` returns a row
3. ✅ Duration > 0: `duration=NNNNN` in query output
4. ✅ Dimensions are correct: `width=1080, height=1920`
5. ✅ MIME type is `video/mp4`

If any check fails after `max_wait`, log a warning and proceed anyway — IG's gallery picker has its own metadata reader and sometimes works even when MediaStore is incomplete.

### 3.4 Force Re-scan If Duration Is Missing

If the video is indexed but has `duration=NULL` or `duration=0`, you can force a re-scan:

```bash
# Delete the broken MediaStore entry
adb -s <serial> shell content delete \
  --uri content://media/external/video/media \
  --where "_display_name='video.mp4'"

# Re-trigger scan
adb -s <serial> shell am broadcast \
  -a android.intent.action.MEDIA_SCANNER_SCAN_FILE \
  -d file:///sdcard/Pictures/video.mp4
```

This forces MediaProvider to re-read the file from scratch.

---

## 4. Complete Reel Creation UI Flow

### 4.1 Flow Overview

```
HOME_FEED
  │
  ├── Tap "+" / Create button (bottom nav center)
  │
  ├── Content type picker appears
  │   └── Select "REEL" tab
  │
  ├── Gallery picker opens (Reel camera mode)
  │   ├── [Optional] Dismiss album picker if shown
  │   └── Tap first thumbnail (most recent = our pushed video)
  │
  ├── Video trimmer / preview screen
  │   └── Tap "Next" or "Add"
  │
  ├── Reel editor (effects, music, text overlays)
  │   ├── [Optional] Add music
  │   └── Tap "Next"
  │
  ├── Caption / share screen
  │   ├── Enter caption text
  │   ├── [Optional] Add location
  │   ├── [Optional] Add hashtags
  │   └── Tap "Share"
  │
  └── Upload progress → Return to HOME_FEED
```

### 4.2 Step-by-Step UI Elements

#### Step 1: Tap Create Button

The "+" button is in the bottom navigation bar, typically the center icon.

| Selector | Type | Value | Notes |
|----------|------|-------|-------|
| content-desc | `"Create"` | Most common on newer IG versions | ✅ Primary selector |
| content-desc | `"New post"` / `"New Post"` | Older IG versions | |
| resource-id | `*creation_tab*` | Pattern match | |
| resource-id | `*tab_create*` | Pattern match | |
| resource-id | `*compose_tab*` | Some clone versions | |
| text | `"+"` | Rare, some IG versions | |
| position | Center of bottom nav | Fallback | ≈ (screen_width/2, screen_height×0.95) |

#### Step 2: Select "Reel" Content Type

After tapping "+", a content type picker appears (bottom sheet or tab bar).

| Selector | Type | Value | Notes |
|----------|------|-------|-------|
| text | `"Reel"` | ✅ Primary | |
| text | `"REEL"` | Uppercase variant | |
| text | `"Reels"` | Plural variant | |
| text | `"Short video"` | Rare, localized | |
| content-desc | `"Reel"` | Description variant | |

**Important:** The content type picker may appear as:
- **Bottom sheet** with POST / REEL / STORY tabs (newer IG versions)
- **Horizontal tab bar** at the bottom of camera view (older versions)
- **Swipeable pager** (some IG versions use swipe left/right between Post/Reel/Story)

#### Step 3: Gallery Picker — Select Video

The gallery opens showing recent media. Our pushed video should be the **first item** (most recent).

| Selector | Type | Value | Notes |
|----------|------|-------|-------|
| resource-id | `*gallery_grid_item_thumbnail*` | ✅ Primary (IG clones) | Uses `android.view.View`, not `ImageView` |
| resource-id | `*gallery_grid_item_image*` | Alternative | |
| resource-id | `*media_thumbnail*` | Generic | |
| resource-id | `*gallery_image_view*` | Older IG | |
| class + clickable | `android.view.View[clickable=true]` | XML fallback | Filter by size > 100px and position |
| position | First grid cell | Fallback | ≈ (screen_width×0.16, screen_height×0.5) |

**Album Picker Interference:** Some IG versions show an "Select album" bottom sheet or "Recents" dropdown when entering the gallery. Must be dismissed:

| Selector | Type | Value | Action |
|----------|------|-------|--------|
| resource-id + text | `*title_text_view*`, "Select album" | Press back to dismiss |
| resource-id | `*album_filter_title*` | Press back |
| resource-id + text | `*context_menu_item_label*`, "Recents" | Click to select Recents album |

#### Step 4: Video Trimmer / Preview — Tap "Next"

After selecting the video, IG shows a trimmer/preview screen. User can trim the video start/end.

| Selector | Type | Value | Notes |
|----------|------|-------|-------|
| text | `"Next"` | ✅ Primary | textContains to catch "Next →" |
| text | `"NEXT"` | Uppercase | |
| text | `"Add"` | Some IG versions | Used instead of "Next" |
| content-desc | `"Next"` | Description | |
| resource-id | `*next_button*` | Pattern | |
| resource-id | `*next_button_textview*` | Pattern | |
| resource-id | `*action_bar_button_action*` | Generic action bar button | |
| position | Top-right | Fallback | "Next" is typically at top-right |

**Gotcha — Recents/App Switcher:** If the "Next" button is near the bottom nav bar, a misclick can hit the Android Recents button. Our code checks for `com.android.launcher` or `RecentTask` in XML and recovers by pressing Home and re-opening IG.

#### Step 5: Reel Editor — Add Music (Optional) → "Next"

The editor screen allows adding music, effects, text overlays, stickers.

**Music button:**

| Selector | Type | Value | Notes |
|----------|------|-------|-------|
| content-desc | `"Music"` / `"Audio"` / `"Add music"` | Varies by version |
| text | `"Music"` / `"Audio"` / `"♪"` | Text variants |

**Music search flow:**
1. Tap music button → music picker opens
2. Find EditText (search bar) → type search query via ADB `input text`
3. Wait 3s for results → tap first result row
4. Tap "Done" to confirm

**Then tap "Next" again** (same selectors as Step 4) to proceed to caption screen.

#### Step 6: Caption Screen — Enter Caption → "Share"

**Caption field:**

| Selector | Type | Value | Notes |
|----------|------|-------|-------|
| resource-id | `*caption_text_view*` | ✅ Primary | |
| resource-id | `*caption_edit_text*` | Alternative | |
| resource-id | `*caption_input*` | Alternative | |
| resource-id | `*caption_text*` | Alternative | |
| resource-id | `*write_a_caption*` | Some versions | |
| text hint | `"Write a caption..."` | Text-based fallback | |
| class | `android.widget.EditText` | Generic fallback | |

**Caption entry method** (in order of reliability):
1. `el.set_text(caption)` — uiautomator2 native, works for simple ASCII
2. ADB clipboard paste — for emoji/special chars: `adb shell am broadcast -a clipper.set -e text "caption"` + paste event
3. ADB `input text` — for simple text only (can't handle newlines, emoji)

**Share button:**

| Selector | Type | Value | Notes |
|----------|------|-------|-------|
| text | `"Share"` | ✅ Primary | |
| text | `"Post"` | Alternative | |
| text | `"SHARE"` / `"POST"` | Uppercase | |
| text | `"Publish"` | Rare | |
| content-desc | `"Share"` / `"Post"` | Description | |
| resource-id | `*share_button*` | Pattern | |
| resource-id | `*post_button*` | Pattern | |
| resource-id | `*action_bar_button_action*` | Generic | |

#### Step 7: Wait for Upload

After tapping "Share", IG uploads the video. Detection:

| State | How to Detect | Action |
|-------|---------------|--------|
| Uploading | Text "Uploading" / "Sharing" in XML | Wait |
| Success | Screen returns to HOME_FEED or PROFILE | Done ✅ |
| Success | Text "has been shared" / "posted" / "Your reel" in XML | Done ✅ |
| Failure | Text "couldn't share" / "try again" / "something went wrong" | Report error ❌ |
| Timeout | 60 seconds elapsed | Check if on HOME_FEED, assume success |

### 4.3 Official IG vs Clone App Differences

Our clone apps (`com.instagram.androie`, `com.instagram.androif`, etc.) are patched versions of the official APK with different package names. The UI is virtually identical because:

- Same APK base, just repackaged
- Same resource IDs (prefixed with clone package instead of `com.instagram.android`)
- Same content descriptions
- Same text labels
- Same layout/hierarchy structure

**Key differences:**

| Aspect | Official IG | Clone Apps |
|--------|-------------|------------|
| Package | `com.instagram.android` | `com.instagram.androie`, `androif`, etc. |
| Resource ID prefix | `com.instagram.android:id/` | `com.instagram.androie:id/` etc. |
| Behavior | Identical | Identical (same bytecode) |
| Updates | Auto-updates via Play Store | Manual update (we control version) |
| Permissions | Standard | Same (granted via ADB at install time) |

**Our `IGController` handles this automatically** — it uses `resourceIdMatches` with wildcards (`.*pattern.*`) instead of full resource IDs, so it works with any clone package.

### 4.4 Complete Resource ID Reference

These are confirmed from XML dumps of IG clone apps on our devices:

```
# Bottom navigation
{pkg}:id/feed_tab                    → Home tab
{pkg}:id/search_tab                  → Search/Explore tab
{pkg}:id/creation_tab                → Create/+ button
{pkg}:id/clips_tab                   → Reels tab
{pkg}:id/profile_tab                 → Profile tab

# Gallery picker
{pkg}:id/gallery_grid_item_thumbnail → Gallery grid thumbnails
{pkg}:id/gallery_grid_item_image     → Alternative thumbnail ID
{pkg}:id/album_filter_title          → Album filter title
{pkg}:id/title_text_view             → Title in album selector
{pkg}:id/context_menu_item_label     → Album dropdown items

# Navigation buttons
{pkg}:id/next_button_textview        → "Next" button text
{pkg}:id/action_bar_button_action    → Generic action bar button (Next/Share)

# Caption screen
{pkg}:id/caption_text_view           → Caption input field
{pkg}:id/caption_edit_text           → Caption edit field (some versions)

# Share screen
{pkg}:id/share_button                → Share/Post button
{pkg}:id/post_button                 → Alternative share button ID

# Reel-specific
{pkg}:id/clips_save                  → Save reel button
{pkg}:id/save_button                 → Alternative save button
```

---

## 5. .mov to .mp4 Conversion

### 5.1 Why Convert?

- Instagram Android's gallery picker is unreliable with .mov files
- MediaStore may not index .mov duration correctly on some Android versions  
- H.265/ProRes .mov files are completely unsupported
- MP4/H.264/AAC is the only format guaranteed to work 100% of the time

### 5.2 With FFmpeg (Recommended)

FFmpeg is the gold standard. It should be installed on the automation server.

#### Simple Remux (If Source is Already H.264/AAC)

```python
import subprocess
import os

def convert_mov_to_mp4(input_path, output_path=None):
    """
    Convert .mov to .mp4. If source is already H.264/AAC, just remux (fast).
    Otherwise, re-encode to H.264/AAC.
    
    Returns output path.
    """
    if output_path is None:
        output_path = os.path.splitext(input_path)[0] + '.mp4'
    
    # First try fast remux (copy streams, just change container)
    result = subprocess.run([
        'ffmpeg', '-y', '-i', input_path,
        '-c:v', 'copy', '-c:a', 'copy',
        '-movflags', '+faststart',  # Enable streaming-friendly layout
        output_path
    ], capture_output=True, text=True, timeout=300)
    
    if result.returncode == 0:
        return output_path
    
    # If remux failed (incompatible codec), re-encode
    result = subprocess.run([
        'ffmpeg', '-y', '-i', input_path,
        '-c:v', 'libx264', '-preset', 'medium',
        '-crf', '23',                 # Good quality
        '-c:a', 'aac', '-b:a', '128k',
        '-vf', 'scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:-1:-1:color=black',
        '-r', '30',                    # 30 FPS
        '-movflags', '+faststart',
        output_path
    ], capture_output=True, text=True, timeout=600)
    
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg conversion failed: {result.stderr[-500:]}")
    
    return output_path
```

#### Full Re-encode (Guaranteed Compatible)

```python
def ensure_reel_format(input_path, output_path=None):
    """
    Ensure video is in perfect Reel format: MP4/H.264/AAC, 1080x1920, 30fps.
    Always re-encodes for consistency (slower but guaranteed).
    """
    if output_path is None:
        base = os.path.splitext(input_path)[0]
        output_path = f"{base}_reel.mp4"
    
    subprocess.run([
        'ffmpeg', '-y', '-i', input_path,
        '-c:v', 'libx264',
        '-profile:v', 'high',
        '-level:v', '4.1',
        '-preset', 'medium',
        '-crf', '23',
        '-maxrate', '5M',
        '-bufsize', '10M',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-ar', '44100',
        '-ac', '2',
        '-vf', 'scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black',
        '-r', '30',
        '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart',
        '-t', '180',  # Max 3 minutes
        output_path
    ], capture_output=True, text=True, timeout=600, check=True)
    
    return output_path
```

### 5.3 Without FFmpeg (Python-Only)

#### Using `moviepy` (Requires pip install)

```python
# pip install moviepy
from moviepy.editor import VideoFileClip

def convert_mov_to_mp4_moviepy(input_path, output_path=None):
    """Convert using moviepy (uses ffmpeg under the hood, but simpler API)."""
    if output_path is None:
        output_path = os.path.splitext(input_path)[0] + '.mp4'
    
    clip = VideoFileClip(input_path)
    
    # Resize to 1080x1920 if needed
    if clip.size != [1080, 1920]:
        clip = clip.resize((1080, 1920))
    
    clip.write_videofile(
        output_path,
        codec='libx264',
        audio_codec='aac',
        fps=30,
        preset='medium',
        bitrate='4000k'
    )
    clip.close()
    return output_path
```

**Note:** `moviepy` still requires `ffmpeg` installed on the system. There is no pure-Python video transcoding library that's production-ready.

#### Pure Python? No.

There is **no viable pure-Python solution** for video transcoding. Video encoding requires:
- H.264 codec implementation (extremely complex, patent-encumbered)
- AAC audio encoding
- MP4 container muxing

Libraries like `av` (PyAV) wrap FFmpeg's libav* and still require the C libraries.

**Bottom line:** Install FFmpeg. On Windows: `choco install ffmpeg` or download from https://ffmpeg.org/download.html.

### 5.4 Batch Pre-Processing Script

```python
"""
Pre-process all videos in content queue to ensure they're in reel-ready format.
Run as a pre-step before the posting automation starts.
"""
import os
import subprocess
import glob

CONTENT_DIR = r"C:\Users\TheLiveHouse\clawd\phone-farm\content\videos"
PROCESSED_DIR = r"C:\Users\TheLiveHouse\clawd\phone-farm\content\videos_processed"

def probe_video(filepath):
    """Get video info using ffprobe."""
    result = subprocess.run([
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_streams', '-show_format', filepath
    ], capture_output=True, text=True, timeout=30)
    
    if result.returncode == 0:
        import json
        return json.loads(result.stdout)
    return None

def needs_conversion(filepath):
    """Check if video needs conversion."""
    ext = os.path.splitext(filepath)[1].lower()
    
    # Non-MP4 always needs conversion
    if ext != '.mp4':
        return True, f"non-mp4 extension: {ext}"
    
    # Check codec
    info = probe_video(filepath)
    if not info:
        return True, "cannot probe"
    
    for stream in info.get('streams', []):
        if stream.get('codec_type') == 'video':
            codec = stream.get('codec_name', '')
            if codec not in ('h264', 'avc'):
                return True, f"non-h264 codec: {codec}"
            
            width = int(stream.get('width', 0))
            height = int(stream.get('height', 0))
            if width > 1080 or height > 1920:
                return True, f"oversized: {width}x{height}"
    
    return False, "already compatible"

def process_all():
    """Process all videos in content directory."""
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    
    for filepath in glob.glob(os.path.join(CONTENT_DIR, '*')):
        ext = os.path.splitext(filepath)[1].lower()
        if ext not in ('.mp4', '.mov', '.avi', '.mkv', '.webm'):
            continue
        
        needs_conv, reason = needs_conversion(filepath)
        filename = os.path.splitext(os.path.basename(filepath))[0] + '.mp4'
        output = os.path.join(PROCESSED_DIR, filename)
        
        if needs_conv:
            print(f"Converting {filepath} ({reason})")
            ensure_reel_format(filepath, output)
        else:
            print(f"Copying {filepath} (already compatible)")
            import shutil
            shutil.copy2(filepath, output)

if __name__ == '__main__':
    process_all()
```

---

## 6. Existing Codebase Integration Notes

### 6.1 Current State

Our `post_content.py` already implements the full reel posting flow:

- ✅ `_push_media_to_device()` — ADB push + MEDIA_SCANNER_SCAN_FILE
- ✅ `_verify_media_indexed()` — MediaStore query with retry loop
- ✅ `_post_reel()` — Full UI flow: create → reel → gallery → next → caption → share
- ✅ `_select_media_from_gallery()` — Multiple selector strategies
- ✅ `_tap_next()`, `_tap_share()`, `_enter_caption()` — UI interactions
- ✅ `_wait_for_upload_complete()` — Upload detection
- ✅ Recents/app-switcher recovery
- ✅ Album picker dismissal

### 6.2 What's Missing / Can Be Improved

1. **Video format pre-validation**: No check that the video is MP4/H.264 before pushing. Should add `ensure_reel_format()` as a pre-step.

2. **MediaStore verification is basic**: Current `_verify_media_indexed()` only checks for existence, not duration validity. The improved `verify_video_indexed()` in Section 3 adds duration/dimensions checks.

3. **No .mov/.avi conversion**: If `media_path` points to a .mov file, it gets pushed as-is. Should convert first.

4. **Caption entry for Unicode/emoji**: Current approach uses `set_text()` and `adb input text`, both of which fail for emoji. Need clipboard-based approach for rich captions.

5. **No video duration validation before push**: Should check local file duration (3s-180s) before pushing to device.

6. **Cleanup could be more thorough**: Should also delete the MediaStore entry, not just the file:
   ```bash
   adb shell content delete --uri content://media/external/video/media --where "_display_name='video.mp4'"
   ```

### 6.3 Suggested Improvements for `post_content.py`

```python
# Add to __init__ or execute():
def _prepare_video(self):
    """Pre-process video to ensure Reel compatibility."""
    ext = os.path.splitext(self.media_path)[1].lower()
    
    # Check if conversion needed
    if ext != '.mp4':
        log.info("[%s] CONTENT: Converting %s to MP4", self.device_serial, ext)
        converted = convert_mov_to_mp4(self.media_path)
        self.media_path = converted
    
    # Validate duration
    duration_ms = self._get_video_duration_ms(self.media_path)
    if duration_ms:
        if duration_ms < 3000:
            raise ValueError(f"Video too short: {duration_ms}ms (min 3s)")
        if duration_ms > 180000:
            raise ValueError(f"Video too long: {duration_ms}ms (max 180s)")
```

---

## 7. Recommended Pipeline

### Complete Flow for Posting a Reel

```
1. PREPARE VIDEO
   ├── Check format: is it MP4/H.264/AAC?
   ├── If not → convert with FFmpeg (ensure_reel_format)
   ├── Validate: duration 3-180s, resolution ≤ 1080x1920
   └── Generate unique filename: reel_{account_id}_{timestamp}.mp4

2. PUSH TO DEVICE
   ├── adb push to /sdcard/Pictures/
   ├── Trigger MEDIA_SCANNER_SCAN_FILE broadcast
   └── Wait 3 seconds

3. VERIFY INDEXED
   ├── Query MediaStore: content query --uri content://media/external/video/media
   ├── Check: duration > 0, width/height present
   ├── Retry up to 15 seconds (poll every 2s)
   └── If still not indexed → force re-scan, wait more

4. OPEN IG & NAVIGATE
   ├── Stop other IG clones (isolation)
   ├── Ensure target IG app is running
   ├── Dismiss any popups
   └── Navigate to HOME_FEED

5. CREATE REEL
   ├── Tap "+" (Create) button
   ├── Select "Reel" content type
   ├── Select video from gallery (first/most recent item)
   ├── Tap "Next" (past trimmer)
   ├── [Optional] Add music
   ├── Tap "Next" (past editor)
   ├── Enter caption + hashtags
   ├── Dismiss keyboard
   └── Tap "Share"

6. WAIT FOR UPLOAD
   ├── Monitor for upload progress/completion
   ├── Timeout: 60 seconds
   └── Verify return to HOME_FEED

7. CLEANUP
   ├── Delete video from device: adb shell rm
   ├── Delete MediaStore entry: content delete
   └── Log success/failure
```

### Error Recovery

| Error | Recovery |
|-------|----------|
| ADB push fails | Retry once; check device connection |
| Video not indexed after 15s | Force re-scan; if still fails, push to /sdcard/DCIM/ instead |
| Create button not found | Navigate to HOME_FEED first; dismiss popups |
| Gallery empty / video not shown | Check album selection; try scrolling gallery; verify MediaStore |
| "Next" button not found | Try "Add" text; check for different screen state |
| Hit app switcher by mistake | Press Home → re-open IG → retry from step 5 |
| Caption entry fails | Try set_text, then ADB input text, then clipboard |
| Share button not found | Look for "Post"/"Publish"; check XML dump |
| Upload fails / "try again" | Wait 30s, navigate home, retry entire flow |
| Upload timeout | Check if on home screen (may have succeeded silently) |

---

## References

- Hootsuite: Instagram Reels specs (max 3 min, 720p min, 30fps min)
- Android MediaStore documentation: content://media/external/video/media
- Our codebase: `phone-farm/automation/actions/post_content.py`
- Our codebase: `phone-farm/automation/ig_controller.py`
- Tested on: Android 10-13 devices, IG clone packages com.instagram.androie-p
