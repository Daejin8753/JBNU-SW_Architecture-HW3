"""별도 프로세스 플러그인 ↔ 코어 계약. 코어에는 inproc 플러그인과 같은 handle 로 보인다."""
import json
import queue
import subprocess
import sys
import threading
import time

from kernel import contract

DEFAULT_TIMEOUT = 3.0
MAX_TIMEOUT = 30.0


class ChildError(Exception):
    """시간 초과·자식 종료·잘못된 응답. 장애로 센다."""


class ProcessPlugin:
    def __init__(self, path, manifest, base_dir):
        self.path = path
        self.base_dir = base_dir
        t = float(manifest.get("timeout_sec", DEFAULT_TIMEOUT))
        self.timeout = min(max(t, 0.1), MAX_TIMEOUT)
        self._lock = threading.Lock()   # 자식 하나에 잠금 하나
        self._proc = None
        self._lines = None
        self._reader = None
        self._next_id = 0
        self.last_startup_ms = None

    @property
    def busy(self):
        """시험용 읽기 전용: 자식 잠금이 잡혀 있음."""
        return self._lock.locked()

    @property
    def pid(self):
        p = self._proc
        return p.pid if p else None

    # ---- 자식 관리 ----
    def _spawn(self, deadline):
        start = time.perf_counter()
        proc = subprocess.Popen(
            [sys.executable, "-m", "kernel.plugin_host", self.path],
            cwd=self.base_dir, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL)
        lines = queue.Queue()

        def read():
            try:
                for line in iter(proc.stdout.readline, b""):
                    lines.put(line)
            except (OSError, ValueError):
                pass
            lines.put(None)  # EOF 표시

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        self._proc, self._lines, self._reader = proc, lines, reader
        msg = self._read_line(deadline)
        if msg.get("ready") is not True:
            raise ChildError(f"준비 실패: {msg.get('error', '알 수 없음')}")
        self.last_startup_ms = (time.perf_counter() - start) * 1000

    def _read_line(self, deadline):
        remain = deadline - time.monotonic()
        if remain <= 0:
            raise ChildError("시간 초과")
        try:
            line = self._lines.get(timeout=remain)
        except queue.Empty:
            raise ChildError("시간 초과")
        if line is None:
            raise ChildError("자식 프로세스 종료")
        try:
            msg = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ChildError("잘못된 JSON 응답")
        if not isinstance(msg, dict):
            raise ChildError("잘못된 응답 모양")
        return msg

    def _kill(self):
        """자기가 가진 Popen 으로만 끝낸다: kill → wait(2) → 파이프 닫기."""
        proc, self._proc = self._proc, None
        reader, self._reader = self._reader, None
        if proc is None:
            return
        try:
            proc.kill()
        except OSError:
            pass
        try:
            proc.wait(2)
        except subprocess.TimeoutExpired:
            pass
        for pipe in (proc.stdin, proc.stdout):
            try:
                pipe.close()
            except OSError:
                pass
        if reader is not None:
            reader.join(0.5)

    def start(self):
        """설치 때: 시간 제한 안에 준비 응답을 받는다."""
        with self._lock:
            try:
                self._spawn(time.monotonic() + self.timeout)
            except Exception:
                self._kill()
                raise

    def close(self):
        self._kill()

    # ---- 호출 ----
    def handle(self, op, payload, ctx):
        if not self._lock.acquire(timeout=self.timeout):
            raise contract.Busy("플러그인이 바쁨, 다시 시도")
        try:
            deadline = time.monotonic() + self.timeout  # 잠금을 얻은 뒤 새로 잰다
            try:
                if self._proc is None or self._proc.poll() is not None:
                    self._kill()
                    self._spawn(deadline)
                self._next_id += 1
                rid = self._next_id
                line = json.dumps({"id": rid, "op": op, "payload": payload}) + "\n"
                try:
                    self._proc.stdin.write(line.encode("utf-8"))
                    self._proc.stdin.flush()
                except OSError:
                    raise ChildError("요청 쓰기 실패")
                msg = self._read_line(deadline)
                if msg.get("id") != rid:
                    raise ChildError("응답 id 불일치")
            except Exception:
                self._kill()
                raise
            if msg.get("ok") is True:
                return msg.get("result")
            if msg.get("rejected"):
                raise contract.Rejected(msg.get("reason", "거부"))
            raise ChildError(f"플러그인 오류: {msg.get('error', '알 수 없음')}")
        finally:
            self._lock.release()
