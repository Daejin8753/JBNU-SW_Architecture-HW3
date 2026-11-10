"""시험용: handle 미구현."""
from kernel import contract

MANIFEST = {
    "name": "no_handle",
    "kind": "auction_type",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "handle 없음",
}


class Plugin(contract.Plugin):
    pass
