"""내부 서버: sqlite3 저장소(auctions, bids, notifications).

호출마다 새 연결을 열고 닫는다. 쓰기는 내부 Lock 으로 하나씩 한다.
"""
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS auctions (
  id TEXT PRIMARY KEY, item TEXT NOT NULL, start_price INTEGER NOT NULL,
  duration_sec INTEGER NOT NULL, type TEXT NOT NULL, status TEXT NOT NULL,
  created_at REAL NOT NULL, ends_at REAL NOT NULL,
  winner TEXT, price INTEGER, reason TEXT, closed_at REAL
);
CREATE TABLE IF NOT EXISTS bids (
  id TEXT PRIMARY KEY, auction_id TEXT NOT NULL, bidder TEXT NOT NULL,
  amount INTEGER, created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS bids_auction ON bids(auction_id, created_at, id);
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT NOT NULL, message TEXT NOT NULL,
  auction_id TEXT, created_at REAL NOT NULL
);
"""

AUCTION_COLS = ("id", "item", "start_price", "duration_sec", "type", "status",
                "created_at", "ends_at", "winner", "price", "reason", "closed_at")


class Storage:
    def __init__(self, path):
        self.path = path
        self._wlock = threading.Lock()
        with self._wlock:
            conn = self._connect()
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.executescript(SCHEMA)
                conn.commit()
            finally:
                conn.close()

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _read(self, sql, args=()):
        conn = self._connect()
        try:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]
        finally:
            conn.close()

    def _write(self, fn):
        with self._wlock:
            conn = self._connect()
            try:
                with conn:  # 트랜잭션 하나
                    fn(conn)
            finally:
                conn.close()

    # ---- 경매 ----
    def create_auction(self, auction):
        cols = [c for c in AUCTION_COLS if c in auction]
        sql = f"INSERT INTO auctions ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
        self._write(lambda c: c.execute(sql, [auction[k] for k in cols]))

    def get_auction(self, auction_id):
        rows = self._read("SELECT * FROM auctions WHERE id=?", (auction_id,))
        return rows[0] if rows else None

    def list_auctions(self):
        return self._read("SELECT * FROM auctions ORDER BY created_at DESC")

    def auctions_by_status(self, statuses, type_name=None):
        marks = ",".join("?" * len(statuses))
        sql = f"SELECT * FROM auctions WHERE status IN ({marks})"
        args = list(statuses)
        if type_name is not None:
            sql += " AND type=?"
            args.append(type_name)
        return self._read(sql + " ORDER BY ends_at", args)

    def list_bids(self, auction_id):
        return self._read("SELECT id, bidder, amount, created_at FROM bids "
                          "WHERE auction_id=? ORDER BY created_at, id", (auction_id,))

    def _apply_change(self, conn, auction_id, change):
        keys = [k for k in ("status", "winner", "price", "reason", "closed_at") if k in change]
        sets = ",".join(f"{k}=?" for k in keys)
        conn.execute(f"UPDATE auctions SET {sets} WHERE id=?",
                     [change[k] for k in keys] + [auction_id])

    def save_bid(self, auction_id, bid, change=None):
        """새 입찰 저장과 경매 상태 변경을 트랜잭션 하나로 한다."""
        def fn(conn):
            conn.execute("INSERT INTO bids (id, auction_id, bidder, amount, created_at) "
                         "VALUES (?,?,?,?,?)",
                         (bid["id"], auction_id, bid["bidder"], bid["amount"], bid["created_at"]))
            if change:
                self._apply_change(conn, auction_id, change)
        self._write(fn)

    def update_auction(self, auction_id, change):
        self._write(lambda c: self._apply_change(c, auction_id, change))

    # ---- 알림 ----
    def add_notifications(self, items):
        def fn(conn):
            for n in items:
                conn.execute("INSERT INTO notifications (user, message, auction_id, created_at) "
                             "VALUES (?,?,?,?)",
                             (n["user"], n["message"], n.get("auction_id"), n["created_at"]))
        self._write(fn)

    def list_notifications(self, user, limit=50):
        return self._read("SELECT user, message, auction_id, created_at FROM notifications "
                          "WHERE user=? ORDER BY id DESC LIMIT ?", (user, limit))
