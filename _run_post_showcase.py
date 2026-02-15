"""
Content Posting Showcase — full flow using existing BotEngine post_content action.
1. Push a test image to the device
2. Use PostContentAction to select it, add caption, and share
"""
import sys
import os
import logging
import time
import subprocess

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s', stream=sys.stdout)
log = logging.getLogger("showcase")

DEVICE_SERIAL = "10.1.11.4_5555"
ADB_SERIAL = "10.1.11.4:5555"
ACCOUNT_ID = 456  # uumi_lailaa, androil
PACKAGE = "com.instagram.androil"

def main():
    from automation.device_connection import get_connection
    from automation.actions.helpers import get_db, get_account_settings
    
    # 1. Load account
    log.info("=== Loading account ===")
    conn_db = get_db()
    account = dict(conn_db.execute("SELECT * FROM accounts WHERE id=?", (ACCOUNT_ID,)).fetchone())
    conn_db.close()
    account['package'] = PACKAGE
    log.info("Account: %s (pkg: %s)", account['username'], PACKAGE)
    
    # 2. Connect device
    log.info("=== Connecting device ===")
    device_conn = get_connection(DEVICE_SERIAL)
    if device_conn.status != 'connected':
        device_conn.connect()
        time.sleep(3)
    
    d = device_conn.device
    if not d:
        log.error("No device!")
        return
    log.info("Device connected: %dx%d", d.info['displayWidth'], d.info['displayHeight'])
    
    # 3. Push a test image (use an existing screenshot as test media)
    log.info("=== Pushing test media ===")
    test_images = [f for f in os.listdir(os.path.join(os.path.dirname(__file__), 'screenshots')) 
                   if f.endswith('.png')] if os.path.exists(os.path.join(os.path.dirname(__file__), 'screenshots')) else []
    
    # Use a simple approach - check if media already exists on device
    device_media_dir = "/sdcard/DCIM/PhoneFarm"
    subprocess.run(["adb", "-s", ADB_SERIAL, "shell", f"mkdir -p {device_media_dir}"], 
                   capture_output=True, timeout=10)
    
    # Check if there's already a test image
    check = subprocess.run(["adb", "-s", ADB_SERIAL, "shell", f"ls {device_media_dir}/"],
                          capture_output=True, text=True, timeout=10)
    log.info("Existing media on device: %s", check.stdout.strip())
    
    # Push a screenshot as test content if nothing exists
    if not check.stdout.strip() or 'No such file' in check.stdout:
        local_img = os.path.join(os.path.dirname(__file__), 'ss_now3.png')
        if os.path.exists(local_img):
            subprocess.run(["adb", "-s", ADB_SERIAL, "push", local_img, 
                          f"{device_media_dir}/test_post.png"],
                         capture_output=True, timeout=30)
            # Trigger media scan
            subprocess.run(["adb", "-s", ADB_SERIAL, "shell",
                          f"am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://{device_media_dir}/test_post.png"],
                         capture_output=True, timeout=10)
            log.info("Pushed test image to device")
            time.sleep(3)
    
    # 4. Now run the post creation flow manually using IGController
    log.info("=== Starting post creation flow ===")
    from automation.ig_controller import IGController
    
    ctrl = IGController(d, DEVICE_SERIAL, PACKAGE)
    
    # Tap the + (create) button on the bottom nav bar
    # The create button is typically the center button in the bottom nav
    w, h = d.info['displayWidth'], d.info['displayHeight']
    
    # First, let's make sure we're on the home feed
    log.info("Navigating to home feed...")
    home_btn = d(description="Home")
    if home_btn.exists(timeout=3):
        home_btn.click()
        time.sleep(2)
    
    # Tap the create/plus button
    log.info("Tapping create button...")
    create_btn = d(descriptionContains="New post")
    if not create_btn.exists(timeout=2):
        create_btn = d(descriptionContains="Create")
    if not create_btn.exists(timeout=2):
        # Try tapping the center bottom button (typical position for create)
        d.click(w // 2, h - 70)
        time.sleep(2)
    else:
        create_btn.click()
        time.sleep(2)
    
    # Check what screen we're on
    time.sleep(3)
    xml = d.dump_hierarchy()
    import re
    texts = [m.group(1) for m in re.finditer(r'text="([^"]+)"', xml) if m.group(1)]
    log.info("After create tap - texts: %s", texts[:15])
    
    # We should be on the gallery/create screen
    # Look for "POST" tab, "Next" button, or gallery grid
    if 'POST' in xml or 'Post' in xml or 'Gallery' in xml or 'GALLERY' in xml or 'Recents' in xml:
        log.info("On gallery screen!")
        
        # Tap "Next" or select first image
        next_btn = d(text="Next")
        if not next_btn.exists(timeout=2):
            next_btn = d(descriptionContains="Next")
        
        if next_btn.exists(timeout=3):
            next_btn.click()
            log.info("Tapped Next")
            time.sleep(3)
        else:
            # May need to select an image first - tap first grid item
            log.info("Looking for gallery items...")
            # Tap in the gallery grid area (below the preview, above bottom nav)
            d.click(w // 4, int(h * 0.7))
            time.sleep(2)
            
            # Now try Next again
            next_btn = d(text="Next")
            if next_btn.exists(timeout=3):
                next_btn.click()
                time.sleep(3)
    
    # Check filter/edit screen
    xml = d.dump_hierarchy()
    texts = [m.group(1) for m in re.finditer(r'text="([^"]+)"', xml) if m.group(1)]
    log.info("Current screen: %s", texts[:15])
    
    if 'Filter' in xml or 'Edit' in xml or 'Lux' in xml:
        log.info("On filter/edit screen - tapping Next...")
        next_btn = d(text="Next")
        if next_btn.exists(timeout=3):
            next_btn.click()
            time.sleep(3)
    
    # Now we should be on the "New post" caption screen  
    xml = d.dump_hierarchy()
    texts = [m.group(1) for m in re.finditer(r'text="([^"]+)"', xml) if m.group(1)]
    log.info("Caption screen: %s", texts[:15])
    
    if 'New post' in xml or 'caption' in xml.lower() or 'Write a caption' in xml or 'Share' in xml:
        log.info("On caption screen!")
        
        # Type caption
        caption_field = d(resourceIdMatches=".*caption_input.*")
        if not caption_field.exists(timeout=2):
            caption_field = d(textContains="Write a caption")
        if not caption_field.exists(timeout=2):
            caption_field = d(className="android.widget.EditText")
        
        if caption_field.exists(timeout=3):
            caption_field.click()
            time.sleep(1)
            caption_field.set_text("Testing post flow from Hydra 🚀 #automation #showcase")
            log.info("Caption typed!")
            time.sleep(2)
        
        # Tap Share
        share_btn = d(text="Share")
        if share_btn.exists(timeout=3):
            share_btn.click()
            log.info("SHARE TAPPED! Posting in progress...")
            time.sleep(15)
            
            # Check result
            xml_final = d.dump_hierarchy()
            texts_final = [m.group(1) for m in re.finditer(r'text="([^"]+)"', xml_final) if m.group(1)]
            log.info("Final screen: %s", texts_final[:15])
            log.info("✅ POST SHOWCASE COMPLETED!")
        else:
            log.warning("Share button not found!")
    else:
        log.info("Not on caption screen yet. Texts: %s", texts[:15])

if __name__ == '__main__':
    main()
