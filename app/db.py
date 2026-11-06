import json
import os
import sqlite3
from pathlib import Path

# Vercel은 /tmp 만 쓰기 가능(인스턴스가 바뀌면 사라지는 임시 저장소)
_BASE = Path("/tmp") if os.getenv("VERCEL") else Path(__file__).resolve().parent.parent
DB_PATH = _BASE / "city_eye.db"


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            image_path TEXT,
            lat REAL, lng REAL,
            address TEXT,
            agency TEXT,
            analysis TEXT,
            title TEXT,
            description TEXT,
            status TEXT DEFAULT 'draft',
            receipt_no TEXT
        )""")


def _row(r) -> dict:
    d = dict(r)
    d["analysis"] = json.loads(d["analysis"]) if d["analysis"] else {}
    return d


def create_report(**f) -> int:
    f["analysis"] = json.dumps(f["analysis"], ensure_ascii=False)
    cols = ",".join(f)
    q = ",".join("?" * len(f))
    with _conn() as c:
        return c.execute(f"INSERT INTO reports ({cols}) VALUES ({q})", list(f.values())).lastrowid


def get_report(rid: int) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM reports WHERE id=?", (rid,)).fetchone()
    return _row(r) if r else None


def list_reports() -> list[dict]:
    with _conn() as c:
        return [_row(r) for r in c.execute("SELECT * FROM reports ORDER BY id DESC")]


def update_report(rid: int, **f):
    sets = ",".join(f"{k}=?" for k in f)
    with _conn() as c:
        c.execute(f"UPDATE reports SET {sets} WHERE id=?", [*f.values(), rid])
