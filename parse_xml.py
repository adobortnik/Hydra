"""Parse XML from dump."""
import re
with open("test_results/current_screen.xml", "r", encoding="utf-8") as f:
    xml = f.read()

# Find all instagram resource IDs
resids = re.findall(r'resource-id="(com\.instagram[^"]*)"', xml)
print("=== Instagram Resource IDs ===")
for r in sorted(set(resids)):
    print(f"  {r}")

# Find bottom navigation elements
print("\n=== Bottom nav / action bar elements ===")
nav_elements = re.findall(r'content-desc="([^"]*)"[^>]*resource-id="(com\.instagram[^"]*)"', xml)
for desc, rid in nav_elements:
    print(f"  {rid}: {desc}")
