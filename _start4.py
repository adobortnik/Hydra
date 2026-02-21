import requests, time

auth = ('admin', 'hydra2026')
serials = ['10.1.10.184_5555','10.1.10.190_5555','10.1.10.192_5555','10.1.10.199_5555']

for s in serials:
    r = requests.post(f'http://localhost:5055/api/bot/launch/{s}', auth=auth, timeout=15)
    print(f"  START {s}: {r.json().get('success')}")
    time.sleep(2)

print("Done!")
