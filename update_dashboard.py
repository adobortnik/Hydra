"""Update Jarvis Dashboard with Phone Farm progress."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import urllib.request
import json

DASHBOARD = 'http://10.1.11.168:8888/api/data'

def api(data=None):
    if data:
        body = json.dumps(data).encode()
        req = urllib.request.Request(DASHBOARD, data=body, method='POST',
                                     headers={'Content-Type': 'application/json'})
    else:
        req = urllib.request.Request(DASHBOARD)
    r = urllib.request.urlopen(req, timeout=10)
    return json.loads(r.read())

# Get existing tasks
all_data = api()
tasks = all_data.get('tasks', all_data.get('items', []))

# Find existing Phone Farm tasks by title
task_map = {}
for t in tasks:
    title = t.get('title', '')
    task_map[title] = t.get('id', '')

print("Existing tasks:")
for title, tid in task_map.items():
    print("  %s -> %s" % (tid[:12], title))

# --- Update existing tasks ---

# "Phone Farm: Dev Phone Setup & Connection Test" -> done
tid = task_map.get('Phone Farm: Dev Phone Setup & Connection Test', '')
if tid:
    api({'action': 'update', 'id': tid, 'status': 'done'})
    api({'action': 'activity', 'id': tid, 'text': 'Phase 1+2 complete. Dashboard on :5055. Device connection proven (10.1.10.180 connects in 7.8s). Screenshot + IG open working.'})
    print("Updated: Dev Phone Setup -> done")

# "Phone Farm: Build Core Automation Module" -> done
tid = task_map.get('Phone Farm: Build Core Automation Module', '')
if tid:
    api({'action': 'update', 'id': tid, 'status': 'done'})
    api({'action': 'activity', 'id': tid, 'text': 'Built automation/ module: device_connection.py, instagram_actions.py, login.py, scheduler.py, api.py. 12 REST endpoints. Full integration test passed.'})
    print("Updated: Build Core Automation -> done")

# "Phone Farm: Task Scheduler Engine" -> done
tid = task_map.get('Phone Farm: Task Scheduler Engine', '')
if tid:
    api({'action': 'update', 'id': tid, 'status': 'done'})
    api({'action': 'activity', 'id': tid, 'text': 'scheduler.py built - priority queue, one-task-per-device, retry logic, history archiving. API endpoints for start/stop/status.'})
    print("Updated: Task Scheduler -> done")

# "Phone Farm: Complete Dashboard Backend Rewiring" -> done
tid = task_map.get('Phone Farm: Complete Dashboard Backend Rewiring', '')
if tid:
    api({'action': 'update', 'id': tid, 'status': 'done'})
    api({'action': 'activity', 'id': tid, 'text': 'Dashboard fully rewired to phone_farm.db. 50 devices, 602 accounts. All 9 blueprints + automation_bp registered. 13/13 endpoint tests pass.'})
    print("Updated: Dashboard Rewiring -> done")

# --- Create new tasks for remaining work ---

# Dashboard frontend wiring
r = api({'action': 'create', 'title': 'Phone Farm: Wire Bot Manager Frontend to Automation API', 'status': 'todo', 'category': 'Phone Farm'})
new_id = r.get('id', r.get('task', {}).get('id', ''))
print("Created: Wire Bot Manager Frontend ->", new_id)

# Login flow E2E test
r = api({'action': 'create', 'title': 'Phone Farm: Test Login Flow E2E (with real 2FA)', 'status': 'todo', 'category': 'Phone Farm'})
new_id = r.get('id', r.get('task', {}).get('id', ''))
print("Created: Login E2E Test ->", new_id)

print("\nDashboard updated!")
