import sqlite3, os

conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row

rows = conn.execute("SELECT device_serial, status, pid FROM bot_status WHERE status != 'stopped'").fetchall()
print(f"Non-stopped bot_status entries: {len(rows)}")

for r in rows:
    serial = r['device_serial']
    pid = r['pid']
    alive = False
    
    if pid:
        try:
            # Windows: check if process exists
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if handle:
                kernel32.CloseHandle(handle)
                alive = True
        except:
            pass
    
    status_str = "ALIVE" if alive else "DEAD"
    print(f"  {serial}: status={r['status']}, pid={pid}, process={status_str}")
    
    if not alive:
        conn.execute("UPDATE bot_status SET status='stopped', pid=NULL WHERE device_serial=?", (serial,))
        print(f"    -> Fixed: set to stopped")

conn.commit()
conn.close()
print("Done")
