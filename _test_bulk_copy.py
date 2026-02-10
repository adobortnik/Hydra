"""Test the bulk copy by simulating what the UI does."""
import requests, json

BASE = 'http://localhost:5055'

# 1. Load settings for source account (harrer_private on JACK 1)
src_device = '10.1.11.4_5555'
src_account = 'harrer_private'

r = requests.get(f'{BASE}/api/bot-settings/{src_device}/{src_account}')
data = r.json()
print(f"Source loaded: success={data.get('success')}")
settings = data.get('settings', {})
print(f"  enable_shared_post = {settings.get('enable_shared_post')}")

# 2. Set enable_shared_post to True and save
settings['enable_shared_post'] = True
r = requests.post(
    f'{BASE}/api/bot-settings/{src_device}/{src_account}',
    json=settings,
    headers={'Content-Type': 'application/json'}
)
save_data = r.json()
print(f"Source saved: success={save_data.get('success')}")

# 3. Verify it was saved
r = requests.get(f'{BASE}/api/bot-settings/{src_device}/{src_account}')
verify = r.json()
print(f"  Verify: enable_shared_post = {verify['settings'].get('enable_shared_post')}")

# 4. Now do bulk copy to ONE target account
target_device = '10.1.11.4_5555'
target_account = 'harrer_real'

# Check target BEFORE
r = requests.get(f'{BASE}/api/bot-settings/{target_device}/{target_account}')
before = r.json()
print(f"\nTarget BEFORE copy: enable_shared_post = {before['settings'].get('enable_shared_post')}")

# Do bulk copy
payload = {
    'source': {'device': src_device, 'account': src_account},
    'targets': [{'device': target_device, 'account': target_account}],
    'categories': 'all'
}
r = requests.post(
    f'{BASE}/api/bot-settings/bulk',
    json=payload,
    headers={'Content-Type': 'application/json'}
)
bulk_data = r.json()
print(f"Bulk copy result: {bulk_data.get('message')}")
if bulk_data.get('results'):
    for res in bulk_data['results']:
        print(f"  {res['account']}: success={res['success']}")

# Check target AFTER
r = requests.get(f'{BASE}/api/bot-settings/{target_device}/{target_account}')
after = r.json()
print(f"\nTarget AFTER copy: enable_shared_post = {after['settings'].get('enable_shared_post')}")
