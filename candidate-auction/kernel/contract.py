"""플러그인 계약. 플러그인이 import 해도 되는 유일한 kernel 모듈이다."""
from abc import ABC, abstractmethod

CONTRACT_VERSION = "1.0"

_NONE = type(None)

# 확장점: kind → op → 입력·출력 최상위 필드와 타입
EXTENSION_POINTS = {
    "auction_type": {
        "validate_bid": {
            "in": {"auction": dict, "bids": list, "bid": dict, "now": (int, float)},
            "out": {"amount": int},
        },
        "view": {
            "in": {"auction": dict, "bids": list, "now": (int, float)},
            "out": {"price": (int, _NONE), "visible_bids": list, "bid_count": int},
        },
        "on_bid_accepted": {
            "in": {"auction": dict, "bids": list, "bid": dict},
            "out": {"close_now": bool, "outbid": (str, _NONE)},
        },
        "settle": {
            "in": {"auction": dict, "bids": list},
            "out": {"winner": (str, _NONE), "price": (int, _NONE)},
        },
    },
    "notifier": {
        "on_outbid": {
            "in": {"auction_id": str, "item": str, "user": str, "new_price": int},
            "out": {"notifications": list},
        },
    },
}


class Rejected(Exception):
    """입력·도메인 규칙 거부. 장애로 세지 않는다."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = str(reason)


class Busy(Exception):
    """별도 프로세스 플러그인이 다른 요청을 처리 중. 장애로 세지 않는다."""


class Plugin(ABC):
    """모든 플러그인의 부모. handle 하나만 구현한다."""

    @abstractmethod
    def handle(self, op, payload, ctx):
        raise NotImplementedError


def type_ok(value, types):
    """isinstance 검사. bool 은 int 로 치지 않는다(bool 을 명시한 경우만 허용)."""
    if not isinstance(types, tuple):
        types = (types,)
    if isinstance(value, bool) and bool not in types:
        return False
    return isinstance(value, types)


def check_fields(data, spec):
    """필수 필드 존재와 타입만 본다. 문제가 있으면 문장, 없으면 None."""
    if not isinstance(data, dict):
        return "dict 가 아님"
    for field, types in spec.items():
        if field not in data:
            return f"필드 없음: {field}"
        if not type_ok(data[field], types):
            return f"타입 불일치: {field}"
    return None


def describe(spec):
    """계약 표를 JSON 으로 보낼 수 있게 타입 이름으로 바꾼다."""
    def name(t):
        if isinstance(t, tuple):
            return "|".join("None" if x is _NONE else x.__name__ for x in t)
        return t.__name__
    return {op: {"in": {k: name(v) for k, v in io["in"].items()},
                 "out": {k: name(v) for k, v in io["out"].items()}}
            for op, io in spec.items()}
