"""코어의 도메인 절차: 받기 → 안전 검사 → 형식 판별 → 변환기 선택 → 변환 → 후처리 → 저장 → 응답.

플러그인·내부 서버 호출은 모두 kernel.py 를 거친다.
"""
import secrets
import time
import unicodedata

from kernel.kernel import CallError

MAX_MARKDOWN = 20 * 1024 * 1024
TOO_LARGE = "결과가 20MB 를 넘음"


def safe_name(raw):
    """경로 구분자와 제어 문자를 빼고 마지막 부분만 남긴다(표시용)."""
    last = (raw or "").replace("\\", "/").split("/")[-1]
    name = "".join(c for c in last if not unicodedata.category(c).startswith("C")).strip()
    return name[:200] or "unnamed"


def _warn(warnings, plugin, code, message):
    warnings.append({"plugin": plugin, "code": code, "message": message})


def _too_large(md):
    return len(md.encode("utf-8")) > MAX_MARKDOWN


def _select_posts(kernel, names, warnings):
    """켠 후처리기를 order 순으로. 모르는 이름은 거부, active 가 아니면 경고(unavailable) 후 건너뜀."""
    chosen = []
    for n in names:
        info = kernel.plugin_info(n)
        if info is None or info["kind"] != "postprocessor":
            raise CallError("rejected", f"모르는 후처리기: {n[:40]}")
        if info["state"] != "active":
            _warn(warnings, n, "unavailable", f"{info['state']} 상태라 건너뜀")
            continue
        chosen.append((info["order"], n))
    return [n for _, n in sorted(chosen)]


def _save(kernel, trace, entry, data, md):
    """저장 + 성공 기록. 내부 서버가 실패하면 파일을 따로 지우고 실패 기록을 한 번 시도한 뒤 internal."""
    file_id = secrets.token_hex(6)
    try:
        kernel.call_internal("storage", "save", trace, file_id=file_id, raw=data, markdown=md)
        entry["id"] = file_id
        entry["ok"] = True
        kernel.call_internal("storage", "record", trace, entry=entry)
    except CallError as e:
        if e.code != "internal":
            raise
        left = []
        for ext in ("in", "md"):  # 파일마다 따로 지운다
            try:
                kernel.call_internal("storage", "remove_file", trace, file_id=file_id, ext=ext)
            except CallError:
                left.append(ext)
        entry.pop("id", None)
        entry["ok"] = False
        entry["reason"] = "internal: 저장 실패" + (", 파일 정리 실패" if left else "")
        try:
            kernel.call_internal("storage", "record", trace, entry=entry)
        except CallError:
            pass  # 기록도 실패하면 그대로 둔다
        e.recorded = True
        raise


def convert(kernel, data, raw_name, post_names, trace):
    t0 = time.perf_counter()
    entry = {"filename": safe_name(raw_name), "format": "", "converter": "",
             "warnings": [], "trace_id": trace.trace_id}
    warnings = entry["warnings"]
    try:
        posts = _select_posts(kernel, post_names, warnings)
        members = kernel.call_internal("inspector", "check", trace, data=data)["members"]  # None = ZIP 아님
        fmt = kernel.call_internal("inspector", "detect", trace, data=data, filename=entry["filename"],
                                   members=members, matchers=kernel.converter_matchers())["format"]
        members = members or {}  # 변환기 계약: ZIP 이 아니면 빈 dict
        entry["format"] = fmt
        conv = kernel.select_converter(fmt)
        entry["converter"] = conv
        payload = {"filename": entry["filename"], "format": fmt, "data": data, "members": members}
        md = kernel.call(conv, "convert", payload, trace)["markdown"]
        if _too_large(md):  # 변환기 결과 초과: 거부(장애 아님)
            raise CallError("rejected", TOO_LARGE)
        meta = {"filename": entry["filename"], "format": fmt, "converter": conv}
        for p in posts:  # 선택 단계: 실패는 code 무엇이든 경고로만
            try:
                out = kernel.call(p, "process", {"markdown": md, "meta": dict(meta)}, trace)["markdown"]
            except CallError as e:
                _warn(warnings, p, e.code, e.message)
                continue
            if _too_large(out):
                _warn(warnings, p, "rejected", TOO_LARGE)
                continue
            md = out
        entry["ms"] = round((time.perf_counter() - t0) * 1000, 3)
        _save(kernel, trace, entry, data, md)
        return {"id": entry["id"], "filename": entry["filename"], "format": fmt, "converter": conv,
                "markdown": md, "warnings": warnings, "ms": entry["ms"]}
    except CallError as e:
        if not getattr(e, "recorded", False):
            entry["ms"] = round((time.perf_counter() - t0) * 1000, 3)
            entry["ok"], entry["reason"] = False, f"{e.code}: {e.message}"
            try:
                kernel.call_internal("storage", "record", trace, entry=entry)
            except CallError:
                pass
        raise


def history(kernel, trace):
    return kernel.call_internal("storage", "history", trace, limit=100)


def download(kernel, file_id, trace):
    found = kernel.call_internal("storage", "read_md", trace, file_id=file_id)
    if found is None:
        raise CallError("not_found", "파일 없음")
    return found
