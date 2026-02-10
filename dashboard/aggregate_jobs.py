import sqlite3
import os
from collections import defaultdict

# Base directory
BASE_DIR = '..'

# Find all device directories
devices = [d for d in os.listdir(BASE_DIR) if os.path.isdir(os.path.join(BASE_DIR, d)) and '.' in d]

# Store all jobs aggregated by job ID
jobs_by_id = defaultdict(lambda: {
    'job_id': None,
    'job_type': None,
    'target': None,
    'accounts': [],
    'completed_count': 0,
    'total_count': 0
})

print(f"Scanning {len(devices)} devices...")

for device in devices[:3]:  # Limit to first 3 devices for testing
    device_path = os.path.join(BASE_DIR, device)

    # Find all account directories in this device
    if not os.path.exists(device_path):
        continue

    try:
        accounts = [a for a in os.listdir(device_path) if os.path.isdir(os.path.join(device_path, a))]
    except:
        continue

    print(f"\n  Device: {device} ({len(accounts)} accounts)")

    for account in accounts[:5]:  # Limit to first 5 accounts for testing
        account_path = os.path.join(device_path, account)
        jobs_path = os.path.join(account_path, 'jobs')

        if not os.path.exists(jobs_path):
            continue

        # Check each job type
        for job_type in ['follow', 'like', 'comment']:
            db_path = os.path.join(jobs_path, f'{job_type}_jobs.db')

            if not os.path.exists(db_path):
                continue

            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                cursor.execute("SELECT * FROM job_orders")
                rows = cursor.fetchall()

                # Get column names
                cursor.execute("PRAGMA table_info(job_orders)")
                columns = [col[1] for col in cursor.fetchall()]

                for row in rows:
                    job_data = dict(zip(columns, row))
                    job_id = job_data.get('job')
                    target = job_data.get('target_username') or job_data.get('target')
                    is_done = job_data.get('is_done', 0)

                    if job_id:
                        job_key = f"{job_type}_{job_id}"

                        jobs_by_id[job_key]['job_id'] = job_id
                        jobs_by_id[job_key]['job_type'] = job_type
                        jobs_by_id[job_key]['target'] = target
                        jobs_by_id[job_key]['accounts'].append({
                            'device': device,
                            'account': account,
                            'is_done': is_done
                        })
                        jobs_by_id[job_key]['total_count'] += 1
                        if is_done:
                            jobs_by_id[job_key]['completed_count'] += 1

                conn.close()

            except Exception as e:
                print(f"    Error reading {job_type}_jobs.db for {account}: {e}")

# Print summary
print(f"\n{'='*80}")
print(f"AGGREGATED JOB ORDERS")
print(f"{'='*80}\n")

for job_key, job in sorted(jobs_by_id.items()):
    print(f"Job ID: {job['job_id']}")
    print(f"  Type: {job['job_type'].upper()}")
    print(f"  Target: {job['target']}")
    print(f"  Accounts: {job['total_count']}")
    print(f"  Progress: {job['completed_count']} / {job['total_count']} completed")
    print(f"  Sample accounts: {[a['account'] for a in job['accounts'][:3]]}")
    print()

print(f"Total unique jobs found: {len(jobs_by_id)}")
