"""Connect JACK 1 device via device_connection module."""
from automation.device_connection import get_connection
import time

serial = "10.1.11.4_5555"
print(f"Connecting to {serial}...")
conn = get_connection(serial)
print(f"Status: {conn.status}")
print(f"Device: {conn.device}")

if conn.status != 'connected':
    print("Attempting connect...")
    device = conn.connect()
    print(f"After connect - Status: {conn.status}, Device: {device}")
    time.sleep(2)
else:
    print("Already connected!")

# Verify
print(f"Final status: {conn.status}")
print(f"Device object: {conn.device}")
if conn.device:
    info = conn.device.info
    print(f"Device info: {info.get('displayWidth')}x{info.get('displayHeight')}")
