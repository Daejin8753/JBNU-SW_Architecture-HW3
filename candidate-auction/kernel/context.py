"""플러그인에 주는 창구(ctx). 플러그인이 코어 밖과 닿는 길은 이것뿐이다."""


class Context:
    """코어가 요청마다 만든다. DB·레지스트리·커널 객체는 들고 있지 않고 함수 하나만 쥔다."""

    __slots__ = ("_call",)

    def __init__(self, call):
        self._call = call

    def log(self, msg):
        """코어 → 감사 로그 내부 서버(audit.write)."""
        self._call("audit", "write", {"msg": str(msg)})

    def internal(self, server, op, **args):
        """코어 → 내부 서버. 허용 목록 밖이면 PermissionError."""
        return self._call(server, op, args)
