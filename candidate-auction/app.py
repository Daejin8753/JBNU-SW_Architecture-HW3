"""시작점: 커널 생성 → 내부 서버 등록 → 플러그인 적재 → HTTP 서버 시작.

실행: python app.py [--port 8801] [--data data] [--plugins plugins]
"""
import argparse
import os
import sys
import threading

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from adapters.http_adapter import AuctionServer  # noqa: E402
from internal.audit import Audit  # noqa: E402
from internal.clock import Clock  # noqa: E402
from internal.storage import Storage  # noqa: E402
from kernel.flow import AuctionFlow  # noqa: E402
from kernel.kernel import Kernel  # noqa: E402
from kernel.trace import Tracer  # noqa: E402


class App:
    def __init__(self, data_dir, plugins_dir, port=0, heartbeat=15):
        os.makedirs(data_dir, exist_ok=True)
        self.tracer = Tracer()
        self.kernel = Kernel(data_dir, plugins_dir, BASE)
        k = self.kernel
        self.audit = Audit(os.path.join(data_dir, "audit.log"))
        k.register_internal("storage", Storage(os.path.join(data_dir, "auction.db")))
        k.register_internal("audit", self.audit)
        self.flow = AuctionFlow(k, self.tracer)
        self.clock = Clock(self.flow.close_due, self._clock_error)
        k.register_internal("clock", self.clock)
        self.clock.start()
        k.load_startup()
        self.flow.start()
        self.server = AuctionServer(port, k, self.flow, self.tracer,
                                    os.path.join(BASE, "ui"), heartbeat=heartbeat)
        self.port = self.server.server_address[1]
        self._thread = None
        self._stopped = False

    def _clock_error(self, auction_id, exc):
        self.audit.write(f"마감 처리 예외 {auction_id}: {type(exc).__name__}: {exc}", source="clock")

    def start_background(self):
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        if self._stopped:
            return
        self._stopped = True
        if self._thread:
            self.server.stop()  # shutdown 은 serve_forever 가 돌 때만 부른다
            self._thread.join(5)
        else:
            self.kernel.events.close_all()
            self.server.server_close()
        self.clock.stop()
        self.kernel.shutdown()


def main():
    p = argparse.ArgumentParser(description="온라인 경매(마이크로커널)")
    p.add_argument("--port", type=int, default=8801)
    p.add_argument("--data", default=os.path.join(BASE, "data"))
    p.add_argument("--plugins", default=os.path.join(BASE, "plugins"))
    a = p.parse_args()
    app = App(os.path.abspath(a.data), os.path.abspath(a.plugins), a.port)
    print(f"http://127.0.0.1:{app.port}", flush=True)
    try:
        app.server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.server.kernel.events.close_all()
        app.server.server_close()
        app.clock.stop()
        app.kernel.shutdown()


if __name__ == "__main__":
    main()
