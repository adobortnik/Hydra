import requests

r = requests.get('http://localhost:5055/api/device-manager/accounts/10.1.10.192_5555', 
                 auth=('admin','hydra2026'), timeout=5)

if r.status_code != 200:
    print(f"Error: {r.status_code} {r.text[:500]}")
else:
    data = r.json()
    for a in data.get('accounts', []):
        print(f"  {a['username']:25s} F={a.get('followers',0)} FG={a.get('following',0)} delta={a.get('followers_delta','?')}")
