"""Jarvis Dashboard API helper - correct endpoints."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import urllib.request
import json

BASE = 'http://10.1.11.168:8888'

def get_data():
    """Get all dashboard data (tasks, columns, activity)."""
    r = urllib.request.urlopen(BASE + '/api/data', timeout=10)
    return json.loads(r.read())

def create_task(title, status='backlog', priority='medium', description='', tags=None):
    """Create a new task."""
    body = json.dumps({
        'title': title,
        'status': status,
        'priority': priority,
        'description': description,
        'tags': tags or [],
    }).encode()
    req = urllib.request.Request(BASE + '/api/task', data=body, method='POST',
                                 headers={'Content-Type': 'application/json'})
    r = urllib.request.urlopen(req, timeout=10)
    return json.loads(r.read())

def move_task(task_id, status):
    """Move a task to a new status column."""
    body = json.dumps({'status': status}).encode()
    req = urllib.request.Request(BASE + '/api/task/' + task_id + '/move',
                                 data=body, method='POST',
                                 headers={'Content-Type': 'application/json'})
    r = urllib.request.urlopen(req, timeout=10)
    return json.loads(r.read())

def add_activity(message, msg_type='update'):
    """Add an activity log entry."""
    body = json.dumps({'message': message, 'type': msg_type}).encode()
    req = urllib.request.Request(BASE + '/api/activity', data=body, method='POST',
                                 headers={'Content-Type': 'application/json'})
    r = urllib.request.urlopen(req, timeout=10)
    return json.loads(r.read())

if __name__ == '__main__':
    action = sys.argv[1] if len(sys.argv) > 1 else 'list'

    if action == 'list':
        data = get_data()
        tasks = data.get('tasks', [])
        print("Tasks (%d):" % len(tasks))
        for t in tasks:
            print("  [%-12s] %s - %s" % (t.get('status','?'), t.get('id','?'), t.get('title','?')))

    elif action == 'create':
        title = sys.argv[2]
        status = sys.argv[3] if len(sys.argv) > 3 else 'backlog'
        r = create_task(title, status)
        print(json.dumps(r, indent=2, ensure_ascii=True))

    elif action == 'move':
        tid = sys.argv[2]
        status = sys.argv[3]
        r = move_task(tid, status)
        print(json.dumps(r, indent=2, ensure_ascii=True))

    elif action == 'activity':
        msg = sys.argv[2]
        r = add_activity(msg)
        print(json.dumps(r, indent=2, ensure_ascii=True))
