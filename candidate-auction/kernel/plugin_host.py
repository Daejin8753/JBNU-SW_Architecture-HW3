"""별도 프로세스 쪽 실행기: 플러그인 적재 → JSON 한 줄 요청 처리.

실행: python -m kernel.plugin_host <플러그인 파일>
"""
import importlib.util
import json
import sys

from kernel import contract


def main():
    proto = sys.stdout.buffer
    sys.stdout = sys.stderr  # 플러그인의 print 가 프로토콜을 깨지 않게

    def send(obj):
        proto.write((json.dumps(obj) + "\n").encode("utf-8"))
        proto.flush()

    try:
        spec = importlib.util.spec_from_file_location("plugin_hosted", sys.argv[1])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        inst = module.Plugin()
    except BaseException as e:
        send({"ready": False, "error": f"{type(e).__name__}: {e}".splitlines()[0]})
        return
    send({"ready": True})

    for raw in sys.stdin.buffer:
        try:
            req = json.loads(raw.decode("utf-8"))
            rid = req["id"]
        except (ValueError, KeyError, TypeError):
            continue
        try:
            result = inst.handle(req.get("op"), req.get("payload") or {}, None)
            send({"id": rid, "ok": True, "result": result})
        except contract.Rejected as e:
            send({"id": rid, "ok": False, "rejected": True, "reason": e.reason})
        except Exception as e:
            send({"id": rid, "ok": False, "error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    main()
