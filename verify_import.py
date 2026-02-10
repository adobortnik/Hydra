"""
Verify import completeness: compare Onimator source files with our phone_farm.db.
Reports gaps and can re-import missing data.
"""
import sqlite3
import os
import json
from pathlib import Path

ONIMATOR_BASE = Path(r"C:\Users\TheLiveHouse\Downloads\full_igbot_14.2.4\full_igbot_14.2.4")
OUR_DB = Path(r"C:\Users\TheLiveHouse\clawd\phone-farm\db\phone_farm.db")


def get_onimator_data():
    """Scan all Onimator device folders and collect accounts."""
    data = {}  # device_serial -> {accounts: [...], settings: {...}, sources: {...}}
    
    if not ONIMATOR_BASE.exists():
        print(f"ERROR: Onimator base not found: {ONIMATOR_BASE}")
        return data
    
    for item in sorted(ONIMATOR_BASE.iterdir()):
        if not item.is_dir():
            continue
        # Check if it looks like a device folder (contains _)
        if '_' not in item.name:
            continue
        
        accounts_db = item / "accounts.db"
        if not accounts_db.exists():
            continue
        
        device_serial = item.name
        device_data = {"accounts": [], "settings_count": 0, "sources_count": 0}
        
        try:
            conn = sqlite3.connect(str(accounts_db))
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM accounts")
            for row in c.fetchall():
                acct = dict(row)
                device_data["accounts"].append(acct)
            conn.close()
        except Exception as e:
            print(f"  ERROR reading {accounts_db}: {e}")
            continue
        
        # Count per-account settings.db files
        for acct in device_data["accounts"]:
            username = acct.get("account", "")
            acct_folder = item / username
            settings_db = acct_folder / "settings.db"
            sources_txt = acct_folder / "sources.txt"
            
            if settings_db.exists():
                try:
                    conn = sqlite3.connect(str(settings_db))
                    c = conn.cursor()
                    c.execute("SELECT settings FROM accountsettings WHERE id=1")
                    row = c.fetchone()
                    conn.close()
                    if row and row[0]:
                        device_data["settings_count"] += 1
                except:
                    pass
            
            if sources_txt.exists():
                try:
                    with open(sources_txt, 'r', encoding='utf-8') as f:
                        lines = [l.strip() for l in f if l.strip()]
                        if lines:
                            device_data["sources_count"] += 1
                except:
                    pass
        
        data[device_serial] = device_data
    
    return data


def get_our_data():
    """Load data from our phone_farm.db."""
    conn = sqlite3.connect(str(OUR_DB))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Accounts by device
    c.execute("SELECT device_serial, username, id FROM accounts ORDER BY device_serial, username")
    accounts = {}
    account_ids = {}
    for row in c.fetchall():
        serial = row["device_serial"]
        if serial not in accounts:
            accounts[serial] = []
        accounts[serial].append(row["username"])
        account_ids[(serial, row["username"])] = row["id"]
    
    # Settings count by device
    c.execute("""
        SELECT a.device_serial, COUNT(*) as cnt
        FROM account_settings s
        JOIN accounts a ON a.id = s.account_id
        WHERE s.settings_json != '{}' AND length(s.settings_json) > 10
        GROUP BY a.device_serial
    """)
    settings_counts = {row["device_serial"]: row["cnt"] for row in c.fetchall()}
    
    # Sources count by device
    c.execute("""
        SELECT a.device_serial, COUNT(DISTINCT a.id) as cnt
        FROM account_sources src
        JOIN accounts a ON a.id = src.account_id
        GROUP BY a.device_serial
    """)
    sources_counts = {row["device_serial"]: row["cnt"] for row in c.fetchall()}
    
    # Total counts
    total_accounts = c.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    total_settings = c.execute("SELECT COUNT(*) FROM account_settings WHERE settings_json != '{}' AND length(settings_json) > 10").fetchone()[0]
    total_sources = c.execute("SELECT COUNT(DISTINCT account_id) FROM account_sources").fetchone()[0]
    
    conn.close()
    
    return {
        "accounts": accounts,
        "account_ids": account_ids,
        "settings_counts": settings_counts,
        "sources_counts": sources_counts,
        "total_accounts": total_accounts,
        "total_settings": total_settings,
        "total_sources": total_sources,
    }


def main():
    print("=" * 70)
    print("IMPORT COMPLETENESS VERIFICATION")
    print("=" * 70)
    
    print(f"\nOnimator base: {ONIMATOR_BASE}")
    print(f"Our DB: {OUR_DB}")
    
    print("\n--- Scanning Onimator source files ---")
    oni = get_onimator_data()
    
    print(f"\n--- Loading our DB ---")
    ours = get_our_data()
    
    total_oni_accounts = sum(len(d["accounts"]) for d in oni.values())
    total_oni_settings = sum(d["settings_count"] for d in oni.values())
    total_oni_sources = sum(d["sources_count"] for d in oni.values())
    
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"Onimator: {len(oni)} devices, {total_oni_accounts} accounts, {total_oni_settings} settings, {total_oni_sources} with sources")
    print(f"Our DB:   {len(ours['accounts'])} devices, {ours['total_accounts']} accounts, {ours['total_settings']} settings, {ours['total_sources']} with sources")
    
    # Detailed comparison
    missing_accounts = []
    missing_settings = []
    missing_sources = []
    
    print(f"\n{'='*70}")
    print(f"PER-DEVICE COMPARISON")
    print(f"{'='*70}")
    print(f"{'Device':<25} {'Oni Accts':>10} {'Our Accts':>10} {'Oni Sets':>10} {'Our Sets':>10} {'Match':>6}")
    print("-" * 80)
    
    for device_serial in sorted(oni.keys()):
        oni_device = oni[device_serial]
        oni_acct_count = len(oni_device["accounts"])
        our_acct_count = len(ours["accounts"].get(device_serial, []))
        oni_settings = oni_device["settings_count"]
        our_settings = ours["settings_counts"].get(device_serial, 0)
        
        match = "OK" if oni_acct_count == our_acct_count and oni_settings == our_settings else "MISS"
        
        print(f"{device_serial:<25} {oni_acct_count:>10} {our_acct_count:>10} {oni_settings:>10} {our_settings:>10} {match:>6}")
        
        # Check individual accounts
        oni_usernames = set(a["account"] for a in oni_device["accounts"])
        our_usernames = set(ours["accounts"].get(device_serial, []))
        
        for username in oni_usernames - our_usernames:
            missing_accounts.append((device_serial, username))
        
        if oni_settings > our_settings:
            missing_settings.append((device_serial, oni_settings - our_settings))
    
    # Check for devices in our DB but not in Onimator (probably fine)
    our_only = set(ours["accounts"].keys()) - set(oni.keys())
    if our_only:
        print(f"\nDevices in our DB but not in Onimator: {our_only}")
    
    print(f"\n{'='*70}")
    print(f"GAPS FOUND")
    print(f"{'='*70}")
    
    if missing_accounts:
        print(f"\nMissing accounts ({len(missing_accounts)}):")
        for dev, user in missing_accounts[:20]:
            print(f"  {dev} / {user}")
        if len(missing_accounts) > 20:
            print(f"  ... and {len(missing_accounts) - 20} more")
    else:
        print("\n[OK] All accounts imported!")
    
    if missing_settings:
        total_missing = sum(c for _, c in missing_settings)
        print(f"\nMissing settings JSON ({total_missing} accounts missing settings across {len(missing_settings)} devices):")
        for dev, cnt in missing_settings[:20]:
            print(f"  {dev}: {cnt} missing")
    else:
        print("[OK] All settings imported!")
    
    print(f"\nSource data: {ours['total_sources']} accounts have sources in our DB (Onimator: {total_oni_sources} have sources.txt)")
    
    return missing_accounts, missing_settings


if __name__ == "__main__":
    missing_accts, missing_settings = main()
    
    if missing_accts or missing_settings:
        print(f"\n{'='*70}")
        print("GAPS DETECTED — Run reimport to fix:")
        print(f"  python verify_import.py --reimport")
    else:
        print(f"\n{'='*70}")
        print("ALL DATA VERIFIED [OK]")
