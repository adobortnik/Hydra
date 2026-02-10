"""Push dev device safety update to Jarvis."""
import sys, os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jarvis import add_activity

add_activity(
    "[Phone Farm] SAFETY: Dev device locked to JACK 1 (10.1.11.4:5555) only. "
    "connect-all endpoint disabled. All other devices are production. "
    "JACK 1 verified: connects in 7.2s, screenshot 740KB, running com.instagram.androie, 12 accounts.",
    "update"
)
print("Dashboard updated with dev device safety note")
