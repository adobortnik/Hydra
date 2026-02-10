"""Jarvis Dashboard API helper."""
import urllib.request
import json
import sys

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

def create_task(title, status='todo', category='Phone Farm'):
    return api({'action': 'create', 'title': title, 'status': status, 'category': category})

def update_task(task_id, status):
    return api({'action': 'update', 'id': task_id, 'status': status})

def add_activity(task_id, text):
    return api({'action': 'activity', 'id': task_id, 'text': text})

def get_all():
    return api()

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'list'
    
    if cmd == 'list':
        data = get_all()
        tasks = data.get('tasks', data.get('items', []))
        for t in tasks:
            print(f"[{t.get('status','?'):12s}] {t.get('id','?')[:8]}... {t.get('title','?')} ({t.get('category','')})")
    
    elif cmd == 'create':
        title = sys.argv[2]
        status = sys.argv[3] if len(sys.argv) > 3 else 'todo'
        r = create_task(title, status)
        print(json.dumps(r, indent=2))
    
    elif cmd == 'update':
        tid = sys.argv[2]
        status = sys.argv[3]
        r = update_task(tid, status)
        print(json.dumps(r, indent=2))
    
    elif cmd == 'activity':
        tid = sys.argv[2]
        text = sys.argv[3]
        r = add_activity(tid, text)
        print(json.dumps(r, indent=2))
