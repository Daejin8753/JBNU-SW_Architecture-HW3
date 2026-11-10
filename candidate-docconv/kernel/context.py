"""플러그인에 주는 창구(ctx). 플러그인이 코어 밖과 닿는 길은 이것뿐이다."""
import json

# 후보 B 허용 목록: ctx.log → storage.log 만
ALLOWED_INTERNAL = frozenset({("storage", "log")})


class Context:
    def __init__(self, kernel, plugin_name, trace):
        self._kernel = kernel
        self._plugin = plugin_name
        self._trace = trace

    def log(self, msg):
        return self.internal("storage", "log", message=str(msg))

    def internal(self, server, op, **args):
        if (server, op) not in ALLOWED_INTERNAL:
            raise PermissionError(f"허용되지 않은 내부 서버 호출: {server}.{op}")
        if server == "storage" and op == "log":
            args = {"message": args.get("message", ""), "source": self._plugin,
                    "trace_id": self._trace.trace_id}
        with self._trace.hop(f"plugin:{self._plugin}", "kernel", op):
            result = self._kernel.call_internal(server, op, self._trace, **args)
        return json.loads(json.dumps(result))  # 복사본만 준다
