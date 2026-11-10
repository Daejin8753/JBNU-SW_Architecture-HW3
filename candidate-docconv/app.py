"""시작점: 커널 생성 → 내부 서버 등록 → 플러그인 적재 → HTTP 서버 시작."""
import argparse
import os

from adapters.http_adapter import make_server
from adapters.process_adapter import ProcessAdapter
from internal.inspector import Inspector
from internal.storage import Storage
from kernel.kernel import Kernel

BASE = os.path.dirname(os.path.abspath(__file__))


def process_factory(path, manifest):
    """별도 프로세스 어댑터를 만든다. 커널은 이 함수만 받는다."""
    return ProcessAdapter(path, manifest, BASE)


def build_kernel(data_dir, plugins_dir):
    os.makedirs(data_dir, exist_ok=True)
    k = Kernel(data_dir, plugins_dir, process_factory)
    k.register_internal("inspector", Inspector())
    k.register_internal("storage", Storage(data_dir))
    k.start()
    return k


def main():
    ap = argparse.ArgumentParser(description="문서 → Markdown 변환기 (마이크로커널)")
    ap.add_argument("--port", type=int, default=8802)
    ap.add_argument("--data", default=os.path.join(BASE, "data"))
    ap.add_argument("--plugins", default=os.path.join(BASE, "plugins"))
    args = ap.parse_args()
    kernel = build_kernel(os.path.abspath(args.data), os.path.abspath(args.plugins))
    server = make_server(kernel, args.port, os.path.join(BASE, "ui"))
    print(f"http://127.0.0.1:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        kernel.shutdown()


if __name__ == "__main__":
    main()
