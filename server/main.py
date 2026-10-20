"""Server nhỏ: trang game gọi vào đây, server giữ API key, gọi OpenAI và chạy bộ máy luật.

Chạy:  uvicorn server.main:app --reload    rồi mở http://localhost:8000
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from starlette.applications import Starlette  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import FileResponse, JSONResponse  # noqa: E402
from starlette.routing import Route  # noqa: E402

from . import llm  # noqa: E402
from .engine import CATALOG, is_blocked, measure, simulate  # noqa: E402
from .fallback import KNOWN, TEMPLATES, kinds_of, patch_fallback, redteam_fallback, translate_fallback  # noqa: E402
from .schema import Event, Exploit, Rule  # noqa: E402

CACHE_FILE = ROOT / "cache.json"
USE_CACHE = os.getenv("CACHE", "1") == "1"
_cache = json.loads(CACHE_FILE.read_text("utf-8")) if CACHE_FILE.exists() else {}
_lock = threading.Lock()


def _key(name: str, payload) -> str:
    raw = json.dumps([name, payload, llm.available()], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _cache_get(k):
    return _cache.get(k) if USE_CACHE else None


def _cache_put(k, v):
    if not USE_CACHE:
        return
    with _lock:
        _cache[k] = v
        CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False), "utf-8")


def _rules(data) -> list[Rule]:
    return [Rule.model_validate(r) for r in (data or [])]


def _err(msg: str, code=400):
    return JSONResponse({"error": msg}, status_code=code)


# ---------- endpoints ----------
async def index(request: Request):
    return FileResponse(ROOT / "static" / "index.html")


async def health(request: Request):
    return JSONResponse({"mode": "llm" if llm.available() else "fallback",
                         "model_fast": llm.MODEL_FAST, "model_strong": llm.MODEL_STRONG})


async def templates(request: Request):
    return JSONResponse([{"key": k, "name": r.name, "rule": r.model_dump(mode="json")} for k, r in TEMPLATES.items()])


async def known(request: Request):
    return JSONResponse([{"id": x["id"], "name": x["name"], "how": x["how"],
                          "needs": [TEMPLATES[n].name for n in x["needs"]]} for x in KNOWN])


async def catalog(request: Request):
    return JSONResponse(CATALOG)


async def translate(request: Request):
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return _err("Gõ một chính sách trước đã.")
    k = _key("translate", text)
    if hit := _cache_get(k):
        return JSONResponse({**hit, "source": "cache"})
    source, note = "fallback", None
    res = None
    if llm.available():
        try:
            res = await run_in_threadpool(llm.translate, text)
            source = "llm"
        except Exception as e:  # mạng lỗi, key sai, hết credit...
            note = f"Gọi OpenAI lỗi, dùng chế độ dự phòng: {type(e).__name__}: {e}"[:300]
    if res is None:
        res = translate_fallback(text)
    out = {**res.model_dump(mode="json"), "source": source, "note": note}
    if source == "llm":
        _cache_put(k, out)
    return JSONResponse(out)


def _verify(rules: list[Rule], x: Exploit) -> dict:
    m = measure(rules, x.events, x.honest_events)
    return {**x.model_dump(mode="json"), **m}


async def redteam(request: Request):
    body = await request.json()
    try:
        active = _rules(body.get("active"))
        new_rule = Rule.model_validate(body["new_rule"])
    except Exception as e:
        return _err(f"Luật không đúng khuôn: {e}")
    k = _key("redteam", [r.model_dump(mode="json") for r in active] + [new_rule.model_dump(mode="json")])
    if hit := _cache_get(k):
        return JSONResponse({**hit, "source": "cache"})
    source, note, proposed = "fallback", None, None
    if llm.available():
        try:
            proposed = (await run_in_threadpool(llm.redteam, active, new_rule)).exploits
            source = "llm"
        except Exception as e:
            note = f"Gọi OpenAI lỗi, dùng chế độ dự phòng: {type(e).__name__}: {e}"[:300]
    if proposed is None:
        proposed = redteam_fallback(active, new_rule)
    rules = active + [new_rule]
    checked = [_verify(rules, x) for x in proposed]
    out = {"source": source, "note": note, "proposed": len(checked),
           "exploits": [c for c in checked if c["verified"]],
           "rejected": [{"name": c["name"], "loss": c["loss"]} for c in checked if not c["verified"]]}
    if source == "llm":
        _cache_put(k, out)
    return JSONResponse(out)


async def patch(request: Request):
    body = await request.json()
    try:
        active = _rules(body.get("active"))
        rule = Rule.model_validate(body["new_rule"])
        exploits = [Exploit.model_validate({k: v for k, v in x.items() if k in Exploit.model_fields})
                    for x in body.get("exploits", [])]
    except Exception as e:
        return _err(f"Dữ liệu không đúng khuôn: {e}")
    if not exploits:
        return JSONResponse({"source": "none", "rule": rule.model_dump(mode="json"), "fixes": []})
    k = _key("patch", [[r.model_dump(mode="json") for r in active], rule.model_dump(mode="json"),
                       [x.model_dump(mode="json") for x in exploits]])
    if hit := _cache_get(k):
        return JSONResponse({**hit, "source": "cache"})
    source, note, patched, fixes = "fallback", None, None, []
    if llm.available():
        try:
            res = await run_in_threadpool(llm.patch, rule, active, [x.model_dump(mode="json") for x in exploits])
            patched, fixes = res.rule, res.fixes
            patched.id = rule.id
            source = "llm"
        except Exception as e:
            note = f"Gọi OpenAI lỗi, dùng chế độ dự phòng: {type(e).__name__}: {e}"[:300]
    if patched is None:
        patched, fixes = patch_fallback(rule, [x.id for x in exploits])
    fix_by = {f.exploit_id: f for f in fixes}
    report = []
    for x in exploits:
        before = measure(active + [rule], x.events, x.honest_events)
        after = measure(active + [patched], x.events, x.honest_events)
        f = fix_by.get(x.id)
        report.append({"exploit_id": x.id, "name": x.name,
                       "explanation": f.explanation if f else "Chưa có bản vá cho mẹo này.",
                       "tradeoff": f.tradeoff if f else "",
                       "loss_before": before["loss"], "loss_after": after["loss"],
                       "blocked": is_blocked(before["loss"], after["loss"]), "log": after["log"]})
    out = {"source": source, "note": note, "rule": patched.model_dump(mode="json"), "fixes": report}
    if source == "llm":
        _cache_put(k, out)
    return JSONResponse(out)


async def sim(request: Request):
    body = await request.json()
    try:
        rules = _rules(body.get("rules"))
        events = [Event.model_validate(e) for e in body.get("events", [])]
    except Exception as e:
        return _err(f"Dữ liệu không đúng khuôn: {e}")
    return JSONResponse(simulate(rules, events))


async def kinds(request: Request):
    body = await request.json()
    return JSONResponse(sorted(kinds_of(Rule.model_validate(body))))


app = Starlette(routes=[
    Route("/", index),
    Route("/api/health", health),
    Route("/api/templates", templates),
    Route("/api/known", known),
    Route("/api/catalog", catalog),
    Route("/api/translate", translate, methods=["POST"]),
    Route("/api/redteam", redteam, methods=["POST"]),
    Route("/api/patch", patch, methods=["POST"]),
    Route("/api/simulate", sim, methods=["POST"]),
    Route("/api/kinds", kinds, methods=["POST"]),
])
