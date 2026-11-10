"""내부 서버: 파일 저장(<data>/files)과 sqlite3 기록·로그(<data>/history.db)."""
import json
import os
import re
import sqlite3
import threading
import time

ID_RE = re.compile(r"^[0-9a-f]{12}$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT, filename TEXT, format TEXT,
  converter TEXT, ms REAL, ok INTEGER, reason TEXT, warnings TEXT, trace_id TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS logs (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, message TEXT, trace_id TEXT, at TEXT);
"""


class Storage:
    def __init__(self, data_dir):
        self.files_dir = os.path.join(data_dir, "files")
        self.db_path = os.path.join(data_dir, "history.db")
        os.makedirs(self.files_dir, exist_ok=True)
        self._lock = threading.Lock()
        with self._lock:
            con = self._connect()
            try:
                con.execute("PRAGMA journal_mode=WAL")
                con.executescript(SCHEMA)
                con.commit()
            finally:
                con.close()

    def _connect(self):
        return sqlite3.connect(self.db_path, timeout=5)

    def _write(self, sql, args):
        with self._lock:
            con = self._connect()
            try:
                con.execute(sql, args)
                con.commit()
            finally:
                con.close()

    # ops (코어만 부른다) ---------------------------------------------------
    def log(self, message, source="", trace_id=""):
        self._write("INSERT INTO logs(source, message, trace_id, at) VALUES (?,?,?,?)",
                    (source, message[:2000], trace_id, time.strftime("%Y-%m-%d %H:%M:%S")))
        return {"ok": True}

    def _path(self, file_id, ext):
        if not ID_RE.match(file_id) or ext not in ("in", "md"):
            raise ValueError("잘못된 파일 ID")
        return os.path.join(self.files_dir, f"{file_id}.{ext}")

    @staticmethod
    def _write_file(path, data):
        with open(path, "wb") as f:
            f.write(data)

    def save(self, file_id, raw, markdown):
        """입력과 결과를 코어가 만든 ID 로 저장한다."""
        with self._lock:
            self._write_file(self._path(file_id, "in"), raw)
            self._write_file(self._path(file_id, "md"), markdown.encode("utf-8"))
        return {"id": file_id}

    def remove_file(self, file_id, ext):
        """저장 실패 정리용. 없는 파일은 성공으로 본다."""
        try:
            os.remove(self._path(file_id, ext))
        except FileNotFoundError:
            pass
        return {"ok": True}

    def record(self, entry):
        self._write(
            "INSERT INTO history(id, filename, format, converter, ms, ok, reason, warnings, trace_id, at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (entry.get("id"), entry.get("filename"), entry.get("format"), entry.get("converter"),
             entry.get("ms"), 1 if entry.get("ok") else 0, entry.get("reason", ""),
             json.dumps(entry.get("warnings", []), ensure_ascii=False), entry.get("trace_id"),
             time.strftime("%Y-%m-%d %H:%M:%S")))
        return {"ok": True}

    def history(self, limit=100):
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT id, filename, format, converter, ms, ok, reason, warnings, trace_id, at"
                " FROM history ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
        finally:
            con.close()
        keys = ("id", "filename", "format", "converter", "ms", "ok", "reason", "warnings", "trace_id", "at")
        out = []
        for r in rows:
            d = dict(zip(keys, r))
            d["ok"] = bool(d["ok"])
            d["warnings"] = json.loads(d["warnings"] or "[]")
            out.append(d)
        return {"items": out}

    def read_md(self, file_id):
        """내려받기: (표시 이름, 바이트). 없으면 None."""
        if not ID_RE.match(file_id):
            return None
        path = os.path.join(self.files_dir, file_id + ".md")
        if not os.path.exists(path):
            return None
        con = self._connect()
        try:
            row = con.execute("SELECT filename FROM history WHERE id=?", (file_id,)).fetchone()
        finally:
            con.close()
        with open(path, "rb") as f:
            body = f.read()
        name = os.path.splitext(row[0] if row else file_id)[0] + ".md"
        return {"filename": name, "body": body}

    def count_logs(self):
        con = self._connect()
        try:
            return con.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
        finally:
            con.close()
