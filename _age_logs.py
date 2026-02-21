import os, time
from datetime import datetime

logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
today = datetime.utcnow().strftime('%Y-%m-%d')
old_time = time.time() - 3600  # 1 hour ago
count = 0

for f in os.listdir(logs_dir):
    if today in f and f.endswith('.log'):
        path = os.path.join(logs_dir, f)
        os.utime(path, (old_time, old_time))
        count += 1

print(f"Aged {count} log files to 1 hour ago")
