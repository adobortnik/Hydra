"""Quick live test: connect to a device, open Instagram clone, take screenshot."""
import uiautomator2 as u2
import subprocess
import time
import sys

DEVICE = "10.1.11.4:5555"  # JACK 1 device
PACKAGE = "com.instagram.androie"  # First clone

print(f"=== QUICK LIVE TEST ===")
print(f"Device: {DEVICE}")
print(f"Package: {PACKAGE}")
print()

# Step 1: Kill existing UIAutomator
print("[1/5] Killing existing UIAutomator processes...")
for cmd in [
    ['adb', '-s', DEVICE, 'shell', 'pkill', '-9', 'uiautomator'],
    ['adb', '-s', DEVICE, 'shell', 'am', 'force-stop', 'com.github.uiautomator'],
    ['adb', '-s', DEVICE, 'shell', 'pkill', '-9', '-f', 'androidx.test.runner'],
]:
    try:
        subprocess.run(cmd, capture_output=True, timeout=5)
    except:
        pass
print("  Done. Waiting 5s...")
time.sleep(5)

# Step 2: Connect
print("[2/5] Connecting via u2.connect()...")
try:
    device = u2.connect(DEVICE)
    print(f"  Connected: serial={device.serial}")
except Exception as e:
    print(f"  FAILED: {e}")
    sys.exit(1)

# Step 3: Wait for responsiveness
print("[3/5] Waiting for UIAutomator responsiveness...")
start = time.time()
for i in range(45):
    try:
        info = device.info
        ws = device.window_size()
        elapsed = int(time.time() - start)
        print(f"  Responsive in {elapsed}s! Screen: {ws[0]}x{ws[1]}")
        print(f"  Display: {info.get('displayWidth')}x{info.get('displayHeight')}")
        break
    except Exception as e:
        if i % 5 == 0:
            print(f"  Waiting... {i}s")
        time.sleep(1)
else:
    print("  FAILED: Not responsive after 45s")
    sys.exit(1)

# Step 4: Open Instagram clone
print(f"[4/5] Opening {PACKAGE}...")
try:
    device.app_start(PACKAGE, use_monkey=True)
    print("  Launched with monkey")
    time.sleep(5)
    
    current = device.app_current()
    print(f"  Current app: {current.get('package')}")
    print(f"  Activity: {current.get('activity')}")
except Exception as e:
    print(f"  app_start failed: {e}")
    # Fallback
    try:
        subprocess.run(
            ['adb', '-s', DEVICE, 'shell', 'monkey', '-p', PACKAGE, '1'],
            capture_output=True, text=True, timeout=10
        )
        time.sleep(5)
        print("  Launched via ADB monkey fallback")
    except Exception as e2:
        print(f"  Fallback also failed: {e2}")

# Step 5: Screenshot
print("[5/5] Taking screenshot...")
try:
    img = device.screenshot()
    path = r'C:\Users\TheLiveHouse\clawd\phone-farm\test_screenshot.png'
    img.save(path)
    print(f"  Saved: {path}")
except Exception as e:
    print(f"  Screenshot failed: {e}")

print()
print("=== TEST COMPLETE ===")
