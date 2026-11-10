"""별도 프로세스 쪽 실행기. 사용: python -m kernel.plugin_host <플러그인 파일>

플러그인을 적재하고 표준 입력의 JSON 한 줄 요청을 하나씩 처리한다.
코어 코드라 정적 검사 대상이 아니다.
"""
import base64
import importlib.util
import inspect
import json
import os
import sys

from kernel import contract


MARKS = ("$b64", "$esc")


def encode(value):
    """bytes 는 {"$b64": ...}, 키가 $b64·$esc 하나뿐인 dict 는 {"$esc": ...} 로 바꾼다."""
    if isinstance(value, bytes):
        return {"$b64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        enc = {k: encode(v) for k, v in value.items()}
        if len(value) == 1 and next(iter(value)) in MARKS:
            return {"$esc": enc}
        return enc
    if isinstance(value, list):
        return [encode(v) for v in value]
    return value


def decode(value):
    if isinstance(value, dict):
        if len(value) == 1 and "$b64" in value:
            return base64.b64decode(value["$b64"])
        if len(value) == 1 and "$esc" in value and isinstance(value["$esc"], dict):
            return {k: decode(v) for k, v in value["$esc"].items()}
        return {k: decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [decode(v) for v in value]
    return value


def _one_line(e):
    return f"{type(e).__name__}: {e}".replace("\n", " ")[:300]


def _load(path):
    spec = importlib.util.spec_from_file_location("plugin_host_target", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cls = getattr(mod, "Plugin", None)
    if not (isinstance(cls, type) and issubclass(cls, contract.Plugin)):
        raise TypeError("Plugin(contract.Plugin) 클래스 없음")
    if inspect.isabstract(cls):
        raise TypeError("handle 미구현")
    return cls()


def main():
    # 원래 stdout 은 프로토콜에만 쓴다. print 와 C 수준 출력은 stderr 로 보낸다.
    proto = os.fdopen(os.dup(1), "wb", buffering=0)
    os.dup2(2, 1)
    sys.stdout = sys.stderr

    def send(obj):
        proto.write((json.dumps(obj, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))

    try:
        plugin = _load(sys.argv[1])
    except BaseException as e:  # 적재 실패는 모두 보고한다
        send({"ready": False, "error": _one_line(e)})
        return
    send({"ready": True})

    for raw in sys.stdin.buffer:
        try:
            req = json.loads(raw.decode("utf-8"))
        except ValueError:
            send({"id": None, "ok": False, "error": "잘못된 요청"})
            continue
        rid = req.get("id")
        try:
            result = plugin.handle(req.get("op"), decode(req.get("payload") or {}), None)
            bad = contract.check_values(result)
            if bad is None:
                try:
                    send({"id": rid, "ok": True, "result": encode(result)})
                    continue
                except (TypeError, ValueError, RecursionError) as e:
                    bad = _one_line(e)
            send({"id": rid, "ok": False, "error": f"출력 값 위반: {bad}"})
        except contract.Rejected as e:
            send({"id": rid, "ok": False, "rejected": True, "reason": e.reason})
        except Exception as e:
            send({"id": rid, "ok": False, "error": _one_line(e)})


if __name__ == "__main__":
    main()
