"""Push updates to Jarvis Dashboard."""
import sys, os
os.environ['PYTHONIOENCODING'] = 'utf-8'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jarvis import add_activity, move_task

# Log the session activity
add_activity(
    "[Phone Farm] Sprint complete: Phase 1 (Dashboard) + Phase 2 (Automation Core) done. "
    "Dashboard on :5055 with 50 devices, 602 accounts. automation/ module: "
    "device_connection, instagram_actions, login, scheduler, api (12 REST endpoints). "
    "Live test: device connects in 7.8s, screenshot 1.1MB, Instagram opens, screen=logged_in.",
    "milestone"
)
print("Added activity log")

# Move JARVIS-012 to in-progress (wiring the bot manager page)
move_task("JARVIS-012", "in-progress")
print("JARVIS-012 -> in-progress")

print("Dashboard updated!")
