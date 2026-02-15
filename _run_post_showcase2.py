"""
Content Posting Showcase v2 — pick up from current state.
The phone should now be on Processing/New post screen.
Wait for caption screen, type caption, tap Share.
"""
import sys
import re
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s', stream=sys.stdout)
log = logging.getLogger("showcase")

DEVICE_SERIAL = "10.1.11.4_5555"
PACKAGE = "com.instagram.androil"

def main():
    from automation.device_connection import get_connection
    
    log.info("Connecting...")
    conn = get_connection(DEVICE_SERIAL)
    if conn.status != 'connected':
        conn.connect()
        time.sleep(3)
    d = conn.device
    
    # Wait for caption screen to appear (Processing may take a few seconds)
    log.info("Waiting for caption screen...")
    for i in range(15):
        xml = d.dump_hierarchy()
        texts = [m.group(1) for m in re.finditer(r'text="([^"]+)"', xml) if m.group(1)]
        log.info("  [%d] texts: %s", i, texts[:10])
        
        if 'New post' in xml and ('Share' in xml or 'caption' in xml.lower()):
            log.info("Caption screen ready!")
            break
        if 'Share' in xml:
            log.info("Share button found!")
            break
        time.sleep(2)
    
    # Type caption
    caption_field = d(resourceIdMatches=".*caption_input.*")
    if not caption_field.exists(timeout=2):
        caption_field = d(className="android.widget.EditText")
    
    if caption_field.exists(timeout=5):
        caption_field.click()
        time.sleep(1)
        d.clear_text()
        time.sleep(0.5)
        caption_field.set_text("Testing post flow from Hydra #automation #showcase")
        log.info("Caption set!")
        time.sleep(2)
    else:
        log.warning("No caption field found. Checking texts...")
        texts = [m.group(1) for m in re.finditer(r'text="([^"]+)"', d.dump_hierarchy()) if m.group(1)]
        log.info("Texts: %s", texts[:20])
    
    # Tap Share
    share_btn = d(text="Share")
    if share_btn.exists(timeout=5):
        share_btn.click()
        log.info("SHARE TAPPED! Post being shared...")
        time.sleep(15)
        
        xml_final = d.dump_hierarchy()
        texts_final = [m.group(1) for m in re.finditer(r'text="([^"]+)"', xml_final) if m.group(1)]
        log.info("Final: %s", texts_final[:15])
        log.info("✅ POST SHOWCASE DONE!")
    else:
        log.warning("No Share button. Checking screen...")
        xml = d.dump_hierarchy()
        texts = [m.group(1) for m in re.finditer(r'text="([^"]+)"', xml) if m.group(1)]
        log.info("Current texts: %s", texts[:20])

if __name__ == '__main__':
    main()
