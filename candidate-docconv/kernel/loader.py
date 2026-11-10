"""plugins/ 검색, 정적 검사, MANIFEST 검사, 적재·해제."""
import importlib.util
import inspect
import os
import re
import sys

from kernel import constraints, contract

NAME_RE = re.compile(r"^[a-z0-9_]{1,40}$")
REQUIRED_KEYS = ("name", "kind", "contract", "version", "description")


class LoadError(Exception):
    """적재 거부 사유. 레코드는 rejected 가 된다."""


def scan(plugins_dir):
    """이름 → 파일 경로."""
    found = {}
    if not os.path.isdir(plugins_dir):
        return found
    for fn in sorted(os.listdir(plugins_dir)):
        name, ext = os.path.splitext(fn)
        if ext == ".py" and NAME_RE.match(name):
            found[name] = os.path.join(plugins_dir, fn)
    return found


def static_check(path):
    """정적 검사. 위반이 있으면 LoadError. 통과하면 manifest."""
    manifest, bad = constraints.check_file(path)
    if bad:
        raise LoadError("정적 검사 위반: " + "; ".join(f"{ln}행 {msg}" for ln, msg in bad))
    return manifest


def _str_list(v):
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_manifest(manifest, name):
    if manifest is None:
        raise LoadError("MANIFEST 가 없거나 리터럴 dict 가 아님")
    missing = [k for k in REQUIRED_KEYS if k not in manifest]
    if missing:
        raise LoadError(f"MANIFEST 필수 키 없음: {', '.join(missing)}")
    for k in REQUIRED_KEYS:
        if not isinstance(manifest[k], str):
            raise LoadError(f"MANIFEST {k} 가 str 이 아님")
    if not NAME_RE.match(manifest["name"]):
        raise LoadError("MANIFEST name 형식 위반")
    if manifest["name"] != name:
        raise LoadError(f"MANIFEST name({manifest['name']}) 이 파일 이름과 다름")
    want = contract.CONTRACT_VERSION.split(".")[0]
    got = str(manifest["contract"]).split(".")[0]
    if got != want:
        raise LoadError(f"계약 버전 불일치: 플러그인 {manifest['contract']}, 코어 {contract.CONTRACT_VERSION}")
    if manifest["kind"] not in contract.EXTENSION_POINTS:
        raise LoadError(f"모르는 확장점: {manifest['kind']}")
    runtime = manifest.get("runtime", "inproc")
    if runtime not in ("inproc", "process"):
        raise LoadError(f"모르는 runtime: {runtime}")
    if runtime == "inproc" and ("requires" in manifest or "timeout_sec" in manifest):
        raise LoadError("requires·timeout_sec 는 runtime process 일 때만 쓴다")
    if "requires" in manifest:
        if not _str_list(manifest["requires"]):
            raise LoadError("MANIFEST requires 가 str 목록이 아님")
        for x in manifest["requires"]:
            problem = constraints.requires_problem(x)
            if problem:
                raise LoadError(problem)
    if "timeout_sec" in manifest:
        t = manifest["timeout_sec"]
        if not (_is_number(t) and 0 < t <= 30):
            raise LoadError("MANIFEST timeout_sec 는 0 초과 30 이하의 수")
    if manifest["kind"] == "converter":
        formats = manifest.get("formats")
        if not (_str_list(formats) and formats):
            raise LoadError("converter 는 formats(str 목록, 1개 이상) 가 필요함")
        if "match" in manifest:
            m = manifest["match"]
            if not isinstance(m, dict):
                raise LoadError("MANIFEST match 가 dict 가 아님")
            ext = m.get("extensions", [])
            if not (_str_list(ext) and all(e.startswith(".") for e in ext)):
                raise LoadError("match.extensions 는 . 으로 시작하는 str 목록")
            if not isinstance(m.get("text", False), bool):
                raise LoadError("match.text 는 bool")
            if len(formats) != 1:
                raise LoadError("match 가 있으면 formats 는 정확히 1개")
    if manifest["kind"] == "postprocessor":
        order = manifest.get("order")
        if not (isinstance(order, int) and not isinstance(order, bool)):
            raise LoadError("postprocessor 는 order(int, bool 아님) 가 필요함")


def load_inproc(path, name, generation):
    """모듈을 실행해 Plugin 인스턴스를 만든다. sys.modules 에 남기지 않는다."""
    mod_name = f"plugin_{name}_{generation}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod  # dataclass 등이 실행 중 모듈을 찾을 수 있게 잠깐만 둔다
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        raise LoadError(f"적재 중 예외: {type(e).__name__}: {e}") from None
    finally:
        sys.modules.pop(mod_name, None)
    cls = getattr(mod, "Plugin", None)
    if not (isinstance(cls, type) and issubclass(cls, contract.Plugin)):
        raise LoadError("Plugin(contract.Plugin) 클래스 없음")
    if inspect.isabstract(cls):
        raise LoadError("handle 미구현")
    try:
        return cls()
    except Exception as e:
        raise LoadError(f"생성 중 예외: {type(e).__name__}: {e}") from None


def load(path, name, manifest, generation, process_factory):
    """process 는 app 이 넘긴 process_factory 로 어댑터를 만든다(kernel 은 adapters 를 모른다)."""
    if manifest.get("runtime", "inproc") == "process":
        adapter = process_factory(path, manifest)
        try:
            adapter.start()
        except Exception as e:
            raise LoadError(f"자식 기동 실패: {e}") from None
        return adapter
    return load_inproc(path, name, generation)


def unload(instance):
    close = getattr(instance, "close", None)
    if callable(close):
        close()
