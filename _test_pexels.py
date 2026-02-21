import requests
r = requests.get('https://api.pexels.com/v1/search', 
    headers={'Authorization': 'ebmsOppQZafQBGgdDnhk518wY1TWmOmfeNXzzaePiSduDM71jeYm1cTQ'}, 
    params={'query': 'young woman selfie', 'per_page': 3})
d = r.json()
print(f"Status: {r.status_code}")
print(f"Photos found: {d.get('total_results', 0)}")
for p in d.get('photos', []):
    alt = (p.get('alt') or 'no alt')[:60]
    print(f"  {alt}")
    print(f"    {p['src']['medium']}")
