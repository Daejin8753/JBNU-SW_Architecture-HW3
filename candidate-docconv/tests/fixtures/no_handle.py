"""시험용: handle 미구현."""
from kernel import contract

MANIFEST = {
    "name": "no_handle",
    "kind": "converter",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "formats": ["nohandlefmt"],
}


class Plugin(contract.Plugin):
    pass
