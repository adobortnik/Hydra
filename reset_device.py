"""Quick reset: go back to home feed."""
import uiautomator2 as u2, time, re

d = u2.connect('10.1.11.4:5555')

# Press back several times to exit any deep screen
for i in range(8):
    d.press('back')
    time.sleep(1)

# Dismiss any popups/dialogs
for text in ['Not Now', 'Not now', 'Cancel', 'Skip', 'OK', 'Discard', 'Dismiss', 'Delete']:
    btn = d(text=text)
    if btn.exists(timeout=0.5):
        btn.click()
        time.sleep(1)
        print(f'Dismissed: {text}')

time.sleep(2)

# Click home tab
home = d(resourceIdMatches='.*feed_tab$')
if home.exists(timeout=3):
    home.click()
    print('Clicked home tab')
else:
    print('Home tab not found')

time.sleep(2)
cur = d.app_current()
print(f'Current app: {cur}')

xml = d.dump_hierarchy()
texts = [m for m in re.findall(r'text="([^"]+)"', xml) if m.strip()][:10]
descs = [m for m in re.findall(r'content-desc="([^"]{1,60})"', xml) if m.strip()][:10]
print(f'Texts: {texts}')
print(f'Descs: {descs}')
print('READY')
