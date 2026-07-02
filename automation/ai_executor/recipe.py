"""
Recipe — record / replay layer for the AI executor.

Idea (John 2026-06-13): the FIRST time a task runs, the AI figures out each step
(expensive). We RECORD those steps keyed by a stable *screen signature*. On the
next run we REPLAY: at each screen, look up the recorded action for that signature
and execute it WITHOUT calling the LLM (free). If a screen has no recorded step
(IG changed the UI, a popup appeared) we fall back to the LLM for just that step
and LEARN it — so the recipe self-heals and gets cheaper over time.

Key design choices:
- A *signature* is the structural fingerprint of a screen: the package + the SET
  of interactive element identities (resource-id, else class). It ignores volatile
  content (counts, captions, timestamps) so the same screen TYPE matches across
  runs and accounts.
- A recorded action stores the target element's IDENTITY (rid/label/class), NOT
  pixel coords — coords are re-resolved from the live screen at replay time.
"""

import hashlib
import json
import os
import sqlite3
import time


def _db_path():
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, 'db', 'phone_farm.db')


# ──────────────────────────────────────────────────────────────────────────
#  Screen signature + element matching
# ──────────────────────────────────────────────────────────────────────────

def screen_signature(perception):
    """Stable fingerprint of a screen: package + sorted set of interactive
    element identities (rid preferred, else class). Volatile text is excluded
    so the same screen TYPE hashes the same across runs/accounts/content."""
    tokens = set()
    for e in perception.elements:
        tok = e.rid or e.cls
        if e.editable:
            tok = 'EDIT:' + tok
        if tok:
            tokens.add(tok)
    raw = (perception.current_pkg or '') + '|' + '\n'.join(sorted(tokens))
    return hashlib.md5(raw.encode('utf-8', 'ignore')).hexdigest()


def find_by_identity(perception, ident):
    """Re-find the element matching a recorded identity on the current screen.
    Priority: exact resource-id > exact label > class+nearest. Returns Element
    or None (None => deviation => let the LLM handle it)."""
    if not ident:
        return None
    rid = (ident.get('rid') or '').strip()
    label = (ident.get('label') or '').strip()
    cls = (ident.get('cls') or '').strip()

    if rid:
        matches = [e for e in perception.elements if e.rid == rid]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1 and label:
            for e in matches:
                if e.label == label:
                    return e
            return matches[0]
        if matches:
            return matches[0]
    if label:
        for e in perception.elements:
            if e.label == label:
                return e
        # volatile labels: dropdowns/fields show a changing placeholder/error
        # suffix (e.g. "Month Please fill in a complete birthday"). Match on the
        # FIRST WORD so the Month vs Gender spinner is still distinguishable.
        key = label.split()[0] if label.split() else ''
        if len(key) >= 3:
            cand = [e for e in perception.elements
                    if e.label and e.label.split() and e.label.split()[0] == key]
            if cls:
                cc = [e for e in cand if e.cls == cls]
                if len(cc) == 1:
                    return cc[0]
                if cc:
                    cand = cc
            if cand:
                return cand[0]
    if cls:
        same = [e for e in perception.elements if e.cls == cls]
        if len(same) == 1:
            return same[0]
    return None


# ──────────────────────────────────────────────────────────────────────────
#  Recipe object
# ──────────────────────────────────────────────────────────────────────────

class Recipe:
    """A learned task: ordered steps + a signature->action map for replay."""

    def __init__(self, rid=None, name='', goal='', app_package=None, steps=None,
                 run_count=0, success_count=0):
        self.id = rid
        self.name = name
        self.goal = goal
        self.app_package = app_package
        self.steps = steps or []        # ordered [{sig, action, llm, note}, ...]
        self.run_count = run_count
        self.success_count = success_count
        self.sig_map = self._build_map(self.steps)

    @staticmethod
    def _build_map(steps):
        """signature -> action template (first occurrence wins)."""
        m = {}
        for s in steps:
            sig = s.get('sig')
            if sig and sig not in m:
                m[sig] = s.get('action')
        return m

    def action_for(self, sig):
        return self.sig_map.get(sig)

    def coverage(self):
        return len(self.sig_map)

    def to_json(self):
        return json.dumps({'steps': self.steps})


# ──────────────────────────────────────────────────────────────────────────
#  Persistence
# ──────────────────────────────────────────────────────────────────────────

def ensure_tables(db_path=None):
    db = db_path or _db_path()
    c = sqlite3.connect(db)
    c.execute("""CREATE TABLE IF NOT EXISTS ai_recipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        goal TEXT,
        app_package TEXT,
        steps_json TEXT,
        run_count INTEGER DEFAULT 0,
        success_count INTEGER DEFAULT 0,
        created_at INTEGER,
        updated_at INTEGER
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS ai_schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipe_id INTEGER NOT NULL,
        name TEXT,
        device_serial TEXT NOT NULL,
        package TEXT,
        mode TEXT NOT NULL,            -- 'interval' | 'daily' | 'once'
        interval_minutes INTEGER,
        daily_time TEXT,               -- 'HH:MM' for daily
        jitter_minutes INTEGER DEFAULT 5,
        next_run_at INTEGER,
        last_run_at INTEGER,
        last_status TEXT,
        enabled INTEGER DEFAULT 1,
        created_at INTEGER
    )""")
    c.commit()
    c.close()


def save_recipe(name, goal, app_package, steps, db_path=None, now=None):
    db = db_path or _db_path()
    ensure_tables(db)
    ts = int(now if now is not None else time.time())
    c = sqlite3.connect(db)
    cur = c.execute(
        "INSERT INTO ai_recipes (name, goal, app_package, steps_json, "
        "run_count, success_count, created_at, updated_at) "
        "VALUES (?,?,?,?,0,0,?,?)",
        (name, goal, app_package, json.dumps({'steps': steps}), ts, ts))
    rid = cur.lastrowid
    c.commit()
    c.close()
    return rid


def update_recipe_steps(rid, steps, db_path=None, now=None):
    """Persist a (possibly self-healed/extended) step set back to a recipe."""
    db = db_path or _db_path()
    ts = int(now if now is not None else time.time())
    c = sqlite3.connect(db)
    c.execute("UPDATE ai_recipes SET steps_json=?, updated_at=? WHERE id=?",
              (json.dumps({'steps': steps}), ts, rid))
    c.commit()
    c.close()


def bump_recipe_stats(rid, success, db_path=None):
    db = db_path or _db_path()
    c = sqlite3.connect(db)
    if success:
        c.execute("UPDATE ai_recipes SET run_count=run_count+1, "
                  "success_count=success_count+1 WHERE id=?", (rid,))
    else:
        c.execute("UPDATE ai_recipes SET run_count=run_count+1 WHERE id=?", (rid,))
    c.commit()
    c.close()


def load_recipe(rid, db_path=None):
    db = db_path or _db_path()
    ensure_tables(db)
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    r = c.execute("SELECT * FROM ai_recipes WHERE id=?", (rid,)).fetchone()
    c.close()
    if not r:
        return None
    steps = (json.loads(r['steps_json'] or '{}') or {}).get('steps', [])
    return Recipe(rid=r['id'], name=r['name'], goal=r['goal'],
                  app_package=r['app_package'], steps=steps,
                  run_count=r['run_count'], success_count=r['success_count'])


def list_recipes(db_path=None):
    db = db_path or _db_path()
    ensure_tables(db)
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    rows = c.execute("SELECT id, name, goal, app_package, steps_json, run_count, "
                     "success_count, updated_at FROM ai_recipes "
                     "ORDER BY updated_at DESC").fetchall()
    c.close()
    out = []
    for r in rows:
        steps = (json.loads(r['steps_json'] or '{}') or {}).get('steps', [])
        out.append({'id': r['id'], 'name': r['name'], 'goal': r['goal'],
                    'app_package': r['app_package'], 'steps': len(steps),
                    'screens': len({s.get('sig') for s in steps if s.get('sig')}),
                    'run_count': r['run_count'], 'success_count': r['success_count'],
                    'updated_at': r['updated_at']})
    return out


def delete_recipe(rid, db_path=None):
    db = db_path or _db_path()
    c = sqlite3.connect(db)
    c.execute("DELETE FROM ai_recipes WHERE id=?", (rid,))
    c.execute("DELETE FROM ai_schedules WHERE recipe_id=?", (rid,))
    c.commit()
    c.close()
