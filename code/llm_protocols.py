# -*- coding: utf-8 -*-
"""DeepSeek 官方 API 协议适配对照（task-180，G5）：chat / Responses / Anthropic Messages。

纯标准库 urllib 实现（无需第三方 SDK）；统一返回：

    {text, usage:{input,output}, finish_reason, latency_s, first_token_s,
     protocol, raw_id, stream_events, stream_terminator, sse_format,
     requested_model, returned_model, success, error_class, error_detail}

三种协议的流式差异：
- chat/completions：SSE ``data: {...}`` 增量 + 终止符 ``data: [DONE]``；usage 在最后一个 chunk（需 stream_options）；
- Responses API：**语义事件**（``response.output_text.delta`` / ``response.completed``；**无 [DONE]**）；
  部分参数（store/previous_response_id/metadata 等）会被静默忽略；
- Anthropic Messages：``message_start`` / ``content_block_delta``（text_delta）/ ``message_delta``（usage/stop_reason）/
  ``message_stop``；模型映射 claude-opus*→v4-pro、其它 claude*→flash；thinking/tool_use 另有限制。

CLI（小样对照，120 API 内；raw 写 a private archive不入 git）::

    python code/llm_protocols.py compare            # 40 题 × 3 协议（API 120）
    python code/llm_protocols.py self-check         # 0 API：构造/解析自检

纪律：**不宣称性能优劣**；本工具只报协议可用性与工程差异，不改变生产评测路径。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"
ARCHIVE_DIR = DATA_ROOT / "private-archive-not-included"
DEFAULT_RAW = ARCHIVE_DIR / "protocol_archive.jsonl"
KEY_FILE = Path(os.environ.get("DEEPSEEK_API_KEY_FILE", ""))
RESULTS_JSON = DATA_ROOT / "g5_summary.json"
PUBLIC = DATA_ROOT

CHAT_BASE = "https://api.deepseek.com"
CHAT_PATH = "/chat/completions"
RESPONSES_BASE = "https://api.deepseek.com"
RESPONSES_PATH = "/responses"
ANTHROPIC_BASE = "https://api.deepseek.com/anthropic"
ANTHROPIC_PATH = "/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

DEFAULT_TIMEOUT = 120.0
MAX_TOKENS = 2000
TEMPERATURE = 0.0
COMPARE_SEED = 20261116
GSM_COUNT = 20
MATH_COUNT = 20
API_BUDGET = 120

# 协议 → 请求模型名（记录 requested/returned；映射依据官方文档，见 the protocol notes）
PROTOCOL_MODELS = {
    "chat": "deepseek-chat",  # 现有生产路径（历史实验口径）
    "responses": "deepseek-flash",  # Responses API：flash 模型
    "anthropic": "claude-3-5-sonnet-20241022",  # 其它 claude* → flash（映射由服务端完成）
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def _read_key() -> str:
    if not KEY_FILE.exists():
        raise SystemExit(f"缺少 API key：{KEY_FILE}")
    return KEY_FILE.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# 请求构造（可离线测试）
# ---------------------------------------------------------------------------


def build_chat_request(
    system: str, user: str, *, model: str, max_tokens: int = MAX_TOKENS,
    temperature: float = TEMPERATURE, stream: bool = True,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if stream:
        body["stream_options"] = {"include_usage": True}
    return {
        "protocol": "chat",
        "method": "POST",
        "url": f"{CHAT_BASE}{CHAT_PATH}",
        "headers": {"Content-Type": "application/json", "Authorization": f"Bearer {_read_key()}"},
        "body": body,
    }


def build_responses_request(
    system: str, user: str, *, model: str, max_tokens: int = MAX_TOKENS,
    temperature: float = TEMPERATURE, stream: bool = True,
) -> dict[str, Any]:
    # Responses API 使用 instructions + input；参数（store/previous_response_id/metadata）会被静默忽略（不发送）
    body: dict[str, Any] = {
        "model": model,
        "instructions": system,
        "input": user,
        "max_output_tokens": max_tokens,
        "temperature": temperature,
        "stream": stream,
    }
    return {
        "protocol": "responses",
        "method": "POST",
        "url": f"{RESPONSES_BASE}{RESPONSES_PATH}",
        "headers": {"Content-Type": "application/json", "Authorization": f"Bearer {_read_key()}"},
        "body": body,
    }


def build_anthropic_request(
    system: str, user: str, *, model: str, max_tokens: int = MAX_TOKENS,
    temperature: float = TEMPERATURE, stream: bool = True,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": stream,
    }
    return {
        "protocol": "anthropic",
        "method": "POST",
        "url": f"{ANTHROPIC_BASE}{ANTHROPIC_PATH}",
        "headers": {
            "Content-Type": "application/json",
            "x-api-key": _read_key(),
            "anthropic-version": ANTHROPIC_VERSION,
        },
        "body": body,
    }


def build_request(protocol: str, system: str, user: str, *, model: str | None = None) -> dict[str, Any]:
    model = model or PROTOCOL_MODELS[protocol]
    if protocol == "chat":
        return build_chat_request(system, user, model=model)
    if protocol == "responses":
        return build_responses_request(system, user, model=model)
    if protocol == "anthropic":
        return build_anthropic_request(system, user, model=model)
    raise ValueError(f"未知协议：{protocol}")


# ---------------------------------------------------------------------------
# SSE 解析（纯函数，离线测试用）
# ---------------------------------------------------------------------------


@dataclass
class StreamState:
    protocol: str
    text: str = ""
    usage: dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0})
    finish_reason: str = ""
    raw_id: str = ""
    returned_model: str = ""
    events: int = 0
    terminator: bool = False
    sse_format: str = "sse"
    parse_errors: int = 0
    error_class: str = ""
    error_detail: str = ""
    _t0: float = 0.0
    _first_token_at: float | None = None


def _add_usage(state: StreamState, usage: Mapping[str, Any] | None) -> None:
    if not isinstance(usage, Mapping):
        return
    inp = usage.get("input_tokens", usage.get("prompt_tokens", usage.get("input", 0)))
    out = usage.get("output_tokens", usage.get("completion_tokens", usage.get("output", 0)))
    try:
        state.usage["input"] = int(inp or state.usage["input"] or 0)
        state.usage["output"] = int(out or state.usage["output"] or 0)
    except (TypeError, ValueError):
        pass


def parse_chat_sse(lines: Iterable[str], *, t0: float | None = None) -> StreamState:
    """chat/completions SSE：data: JSON（增量）+ data: [DONE]。"""
    state = StreamState(protocol="chat", _t0=t0 or time.perf_counter())
    for line in lines:
        line = line.strip()
        if not line or line.startswith(":"):
            continue
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        state.events += 1
        if payload == "[DONE]":
            state.terminator = True
            continue
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            state.parse_errors += 1
            continue
        state.raw_id = state.raw_id or str(chunk.get("id") or "")
        state.returned_model = state.returned_model or str(chunk.get("model") or "")
        _add_usage(state, chunk.get("usage"))
        choices = chunk.get("choices") or []
        if choices:
            choice = choices[0]
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if isinstance(content, str) and content:
                if state._first_token_at is None:
                    state._first_token_at = time.perf_counter()
                state.text += content
            finish = choice.get("finish_reason")
            if finish:
                state.finish_reason = str(finish)
    return state


def parse_responses_sse(lines: Iterable[str], *, t0: float | None = None) -> StreamState:
    """Responses API SSE：语义事件（response.output_text.delta/.../response.completed；无 [DONE]）。"""
    state = StreamState(protocol="responses", _t0=t0 or time.perf_counter())
    for line in lines:
        line = line.strip()
        if not line or line.startswith(":"):
            continue
        if line.startswith("event:"):
            state.sse_format = "semantic-sse"
            continue
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        state.events += 1
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            state.parse_errors += 1
            continue
        etype = str(event.get("type") or "")
        if etype == "response.output_text.delta":
            delta = event.get("delta")
            if isinstance(delta, str) and delta:
                if state._first_token_at is None:
                    state._first_token_at = time.perf_counter()
                state.text += delta
        elif etype in ("response.completed", "response.done"):
            state.terminator = True
            response = event.get("response") or {}
            state.raw_id = state.raw_id or str(response.get("id") or event.get("id") or "")
            state.returned_model = state.returned_model or str(response.get("model") or "")
            _add_usage(state, response.get("usage"))
            state.finish_reason = str(response.get("status") or "completed")
        elif etype in ("response.failed", "error"):
            state.error_class = "PROTOCOL_ERROR"
            state.error_detail = json.dumps(event, ensure_ascii=False)[:200]
        else:
            # 其它事件只计数（response.created/in_progress 等）
            pass
    return state


def parse_anthropic_sse(lines: Iterable[str], *, t0: float | None = None) -> StreamState:
    """Anthropic Messages SSE：message_start/content_block_delta/message_delta/message_stop。"""
    state = StreamState(protocol="anthropic", _t0=t0 or time.perf_counter())
    for line in lines:
        line = line.strip()
        if not line or line.startswith(":"):
            continue
        if line.startswith("event:"):
            state.sse_format = "event-sse"
            continue
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        state.events += 1
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            state.parse_errors += 1
            continue
        etype = str(event.get("type") or "")
        if etype == "message_start":
            message = event.get("message") or {}
            state.raw_id = state.raw_id or str(message.get("id") or "")
            state.returned_model = state.returned_model or str(message.get("model") or "")
            _add_usage(state, message.get("usage"))
        elif etype == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") in ("text_delta", None) and isinstance(delta.get("text"), str):
                if delta["text"]:
                    if state._first_token_at is None:
                        state._first_token_at = time.perf_counter()
                    state.text += delta["text"]
        elif etype == "message_delta":
            delta = event.get("delta") or {}
            if delta.get("stop_reason"):
                state.finish_reason = str(delta["stop_reason"])
            _add_usage(state, event.get("usage"))
        elif etype == "message_stop":
            state.terminator = True
        elif etype == "error":
            state.error_class = "PROTOCOL_ERROR"
            state.error_detail = json.dumps(event, ensure_ascii=False)[:200]
    return state


PARSERS = {
    "chat": parse_chat_sse,
    "responses": parse_responses_sse,
    "anthropic": parse_anthropic_sse,
}


# ---------------------------------------------------------------------------
# 统一结果 / 错误分类
# ---------------------------------------------------------------------------


def classify_error(exc: BaseException | None = None, *, status: int | None = None,
                   text: str = "", terminator: bool = True, parse_errors: int = 0) -> str:
    """错误分类（HTTP/TIMEOUT/NETWORK/PARSE/EMPTY/INCOMPLETE）。"""
    if status is not None and status >= 400:
        return f"HTTP_{status}"
    if exc is not None:
        if isinstance(exc, (socket.timeout, TimeoutError)):
            return "TIMEOUT"
        if isinstance(exc, urllib.error.HTTPError):
            return f"HTTP_{exc.code}"
        if isinstance(exc, urllib.error.URLError):
            return "NETWORK"
        return f"ERROR_{type(exc).__name__}"
    if parse_errors and not text:
        return "PARSE_ERROR"
    if not str(text or "").strip():
        return "EMPTY_TEXT"
    if not terminator:
        return "STREAM_INCOMPLETE"
    return ""


def finalize(
    state: StreamState, *, protocol: str, requested_model: str, latency_s: float,
    error_class: str = "", error_detail: str = "",
) -> dict[str, Any]:
    first = state._first_token_at
    first_token_s = round(first - state._t0, 4) if first is not None else None
    success = not error_class and bool(str(state.text or "").strip())
    return {
        "protocol": protocol,
        "requested_model": requested_model,
        "returned_model": state.returned_model,
        "raw_id": state.raw_id,
        "success": success,
        "text": state.text,
        "text_chars": len(state.text),
        "usage": dict(state.usage),
        "finish_reason": state.finish_reason,
        "latency_s": round(latency_s, 3),
        "first_token_s": first_token_s,
        "stream_events": state.events,
        "stream_terminator": bool(state.terminator),
        "sse_format": state.sse_format,
        "parse_errors": state.parse_errors,
        "error_class": error_class,
        "error_detail": str(error_detail or "")[:300],
    }


def _iter_sse_lines(response: Any) -> Iterable[str]:
    for raw_line in response:
        if isinstance(raw_line, bytes):
            yield raw_line.decode("utf-8", errors="replace")
        else:
            yield str(raw_line)


def call_protocol(
    protocol: str, system: str, user: str, *, model: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """执行一次协议调用（流式）；统一返回。HTTP/网络异常也返回统一结构（不抛出）。"""
    request = build_request(protocol, system, user, model=model)
    requested_model = str(request["body"].get("model"))
    t0 = time.perf_counter()
    state = StreamState(protocol=protocol, _t0=t0)
    data = json.dumps(request["body"]).encode("utf-8")
    req = urllib.request.Request(
        request["url"], data=data, headers=request["headers"], method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            state = PARSERS[protocol](_iter_sse_lines(response), t0=t0)
        latency = time.perf_counter() - t0
        error = classify_error(
            text=state.text, terminator=state.terminator, parse_errors=state.parse_errors
        )
        if state.error_class:
            error = state.error_class
        return finalize(
            state, protocol=protocol, requested_model=requested_model,
            latency_s=latency, error_class=error, error_detail=state.error_detail,
        )
    except urllib.error.HTTPError as exc:
        latency = time.perf_counter() - t0
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        return finalize(
            StreamState(protocol=protocol, _t0=t0), protocol=protocol,
            requested_model=requested_model, latency_s=latency,
            error_class=f"HTTP_{exc.code}", error_detail=detail,
        )
    except Exception as exc:  # noqa: BLE001 - 统一错误分类，不抛出
        latency = time.perf_counter() - t0
        return finalize(
            StreamState(protocol=protocol, _t0=t0), protocol=protocol,
            requested_model=requested_model, latency_s=latency,
            error_class=classify_error(exc), error_detail=f"{type(exc).__name__}: {exc}",
        )


# 别名（任务要求的函数名）
def call_chat(messages: Any = None, model: str | None = None, *, system: str = "",
              user: str = "", timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    if not user and isinstance(messages, list):
        user = next((m.get("content") for m in messages if m.get("role") == "user"), "")
    return call_protocol("chat", system, user, model=model or PROTOCOL_MODELS["chat"], timeout=timeout)


def call_responses(system: str = "", user: str = "", model: str | None = None,
                   timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    return call_protocol("responses", system, user, model=model or PROTOCOL_MODELS["responses"], timeout=timeout)


def call_anthropic(messages: Any = None, model: str | None = None, *, system: str = "",
                   user: str = "", max_tokens: int = MAX_TOKENS,
                   timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    if not user and isinstance(messages, list):
        user = next((m.get("content") for m in messages if m.get("role") == "user"), "")
    return call_protocol("anthropic", system, user, model=model or PROTOCOL_MODELS["anthropic"], timeout=timeout)


# ---------------------------------------------------------------------------
# 小样对照（40 题 × 3 协议 = 120 API）
# ---------------------------------------------------------------------------


def _load_build() -> Any:
    spec = importlib.util.spec_from_file_location("public_build_samples_g5", PUBLIC / "build_samples.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["public_build_samples_g5"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _stable_rank(seed: int, key: str) -> str:
    return hashlib.sha256(f"{seed}:{key}".encode("utf-8")).hexdigest()


def select_40_problems(seed: int = COMPARE_SEED) -> list[dict[str, Any]]:
    """固定 seed 抽 20 GSM + 20 MATH（题目文本只在内存；不写题干）。"""
    builder = _load_build()
    gsm_meta = _read_jsonl(PUBLIC / "gsm8k_250.jsonl")
    math_meta = _read_jsonl(PUBLIC / "math_250.jsonl")
    selected: list[dict[str, Any]] = []
    for dataset, meta, count in (("gsm8k", gsm_meta, GSM_COUNT), ("math-hendrycks", math_meta, MATH_COUNT)):
        ordered = sorted(meta, key=lambda row: _stable_rank(seed, str(row["id"])))
        for row in ordered[:count]:
            selected.append({"dataset": dataset, "id": str(row["id"]), "meta": row})
    return selected


def _problem_text(builder: Any, item: Mapping[str, Any]) -> tuple[str, str]:
    dataset = str(item["dataset"])
    row_index = int(str(item["id"]).rsplit(":", 1)[1])
    if dataset == "gsm8k":
        rows = builder.read_parquet_rows(builder.GSM_FILE, ["question", "answer"])
        row = rows[row_index]
        problem = str(row.get("question") or "")
        reference = builder.gsm8k_final_answer(row.get("answer") or "")
    else:
        rows = builder.read_parquet_rows(builder.MATH_FILE, ["problem", "solution"])
        row = rows[row_index]
        problem = str(row.get("problem") or "")
        reference = builder.math_boxed_answer(row.get("solution") or "")
    return problem, reference


def _answer_status(final_answer: str, reference: str) -> str:
    from author_engine.answer_norm import compare_answers

    if not str(final_answer or "").strip():
        return "missing"
    if not str(reference or "").strip():
        return "unknown"
    try:
        verdict = str(compare_answers(str(final_answer), str(reference)).get("verdict") or "unknown")
    except Exception:  # noqa: BLE001 - fail-closed
        return "unknown"
    return {"equivalent": "consistent", "not_equivalent": "inconsistent"}.get(verdict, "unknown")


def _aggregate(records: Sequence[Mapping[str, Any]], protocol: str) -> dict[str, Any]:
    rows = [row for row in records if row["protocol"] == protocol]
    n = len(rows)
    success = sum(1 for row in rows if row["success"])
    parsable = sum(1 for row in rows if row["final_answer_parsable"])
    answered = [row for row in rows if row["final_answer_parsable"]]
    consistent = sum(1 for row in answered if row["answer_status"] == "consistent")
    failure = {}
    for row in rows:
        if row["error_class"]:
            failure[row["error_class"]] = failure.get(row["error_class"], 0) + 1
    def pct(values: list[float], q: float) -> float | None:
        if not values:
            return None
        values = sorted(values)
        index = min(len(values) - 1, max(0, int(round(q * (len(values) - 1)))))
        return round(values[index], 3)
    latencies = [float(row["latency_s"]) for row in rows]
    first_tokens = [float(row["first_token_s"]) for row in rows if row.get("first_token_s") is not None]
    input_tokens = sum(int(row["usage"].get("input") or 0) for row in rows)
    output_tokens = sum(int(row["usage"].get("output") or 0) for row in rows)
    return {
        "protocol": protocol,
        "requested_model": rows[0]["requested_model"] if rows else None,
        "returned_models": sorted({str(row.get("returned_model") or "") for row in rows if row.get("returned_model")}),
        "calls": n,
        "success": success,
        "success_rate": round(success / n, 4) if n else 0.0,
        "final_answer_parsable": parsable,
        "final_answer_parsable_rate": round(parsable / n, 4) if n else 0.0,
        "answer_status": {
            "consistent": consistent,
            "inconsistent": sum(1 for row in answered if row["answer_status"] == "inconsistent"),
            "unknown": sum(1 for row in answered if row["answer_status"] == "unknown"),
            "missing": sum(1 for row in answered if row["answer_status"] == "missing"),
        },
        "answer_consistency_rate": round(consistent / parsable, 4) if parsable else 0.0,
        "stream_terminator_rate": round(sum(1 for row in rows if row["stream_terminator"]) / n, 4) if n else 0.0,
        "stream_events_mean": round(sum(int(row["stream_events"]) for row in rows) / n, 2) if n else 0.0,
        "latency_s": {
            "mean": round(sum(latencies) / n, 3) if n else None,
            "p50": pct(latencies, 0.5),
            "p95": pct(latencies, 0.95),
        },
        "first_token_s": {
            "n": len(first_tokens),
            "mean": round(sum(first_tokens) / len(first_tokens), 3) if first_tokens else None,
            "p50": pct(first_tokens, 0.5),
            "p95": pct(first_tokens, 0.95),
        },
        "tokens": {"input": input_tokens, "output": output_tokens},
        "failures": failure,
    }


def compare_command(args: argparse.Namespace) -> int:
    """40 题 × 3 协议（默认 API 120 ≤120；raw 写 a private archive）。"""
    from local_engine.corpus import coverage_baseline as cb  # 复用覆盖评测 v2 prompt（同一 prompt 跨协议）

    protocol_list = args.protocols.split(",")
    problems = select_40_problems(args.seed)
    budget = args.budget
    planned = len(problems) * len(protocol_list)
    if planned > budget:
        raise SystemExit(f"计划调用 {planned} 超出预算 {budget}（失败即停）")
    builder = _load_build()
    system = cb.STEP157_SYSTEM_V2
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = Path(args.raw)
    records: list[dict[str, Any]] = []
    calls = 0
    started = time.time()
    for item in problems:
        problem, reference = _problem_text(builder, item)
        prompt_sha = _sha256_text(problem)
        for protocol in protocol_list:
            if calls >= budget:
                raise SystemExit(f"达到 API 上限 {budget}（失败即停）")
            result = call_protocol(protocol, system, problem)
            calls += 1
            from author_engine.answer_norm import normalize_answer as _normalize

            parsed_final = ""
            try:
                payload_text = result["text"]
                from local_engine.corpus import coverage_baseline as _cb
                parsed = _cb.parse_payload_with_final_answer(payload_text)
                parsed_final = str(parsed["final_answer"] or "")
            except Exception:  # noqa: BLE001 - 解析失败计 missing
                parsed_final = ""
            answer_status = _answer_status(parsed_final, reference)
            record = {
                "protocol": result["protocol"],
                "requested_model": result["requested_model"],
                "returned_model": result["returned_model"],
                "dataset": item["dataset"],
                "problem_id": item["id"],
                "prompt_sha256": prompt_sha,
                "reference_answer_sha256": _sha256_text(reference),
                "success": result["success"],
                "error_class": result["error_class"],
                "error_detail": result["error_detail"],
                "text_chars": result["text_chars"],
                "final_answer_parsable": bool(parsed_final),
                "final_answer_sha256": _sha256_text(parsed_final),
                "answer_status": answer_status,
                "usage": result["usage"],
                "finish_reason": result["finish_reason"],
                "latency_s": result["latency_s"],
                "first_token_s": result["first_token_s"],
                "stream_events": result["stream_events"],
                "stream_terminator": result["stream_terminator"],
                "sse_format": result["sse_format"],
                "parse_errors": result["parse_errors"],
                "raw_id": result["raw_id"],
                "created": _now(),
            }
            records.append(record)
            with raw_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({**record, "raw_text": result["text"]}, ensure_ascii=False) + "\n")
                handle.flush()
            print(
                f"[{calls}/{planned}] {protocol:9s} {item['id']} success={result['success']} "
                f"lat={result['latency_s']}s first={result['first_token_s']} "
                f"term={result['stream_terminator']} err={result['error_class'] or '-'}",
                flush=True,
            )
    aggregates = {protocol: _aggregate(records, protocol) for protocol in protocol_list}
    results = {
        "schema": "api-protocol-comparison/v1",
        "created": _now(),
        "task": "task-180",
        "seed": args.seed,
        "problems": len(problems),
        "protocols": protocol_list,
        "calls_total": calls,
        "api_budget": budget,
        "elapsed_s": round(time.time() - started, 1),
        "protocol_models": PROTOCOL_MODELS,
        "prompt_template": "local_corpus/coverage_baseline.py#STEP157_SYSTEM_V2（coverage-step/v2+final_answer；跨协议同一 prompt）",
        "raw_path": "local-archive git）",
        "data_note": "无题干/答案原文；逐题仅 id/hash/统计/判定状态；raw 文本（模型输出）只在 a private archive。",
        "protocols_result": aggregates,
        "records": records,
        "limitations": [
            "小样本：40 题（GSM 20 + MATH 20）/协议；单模型目标（flash 映射）、单次运行；不宣称性能优劣。",
            "chat 走现有模型名 deepseek-chat；Responses 用 deepseek-flash；Anthropic 用 claude-3-5-sonnet*（服务端映射 flash）——"
            "模型路由由服务端决定，结果不代表同参数同模型绝对对照。",
            "Responses API 部分参数会被静默忽略、且无 [DONE]；以 response.completed 判定流式完整性。",
            "Anthropic 部分字段有限制；thinking/tool_use 未在本实验使用。",
            "答案一致性用 answer_norm vs 公开集参考答案；参考答案未人工全检，一致≠正确。",
            "不改变生产评测路径。",
        ],
    }
    RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已写：{RESULTS_JSON}", flush=True)
    for protocol, agg in aggregates.items():
        print(
            f"{protocol}: success={agg['success_rate']} parsable={agg['final_answer_parsable_rate']} "
            f"consistent={agg['answer_consistency_rate']} first_token_p50={agg['first_token_s']['p50']} "
            f"latency_p50={agg['latency_s']['p50']} term={agg['stream_terminator_rate']} failures={agg['failures']}",
            flush=True,
        )
    return 0


def self_check_command(args: argparse.Namespace) -> int:
    del args
    checks = 0
    for protocol in ("chat", "responses", "anthropic"):
        req = build_request(protocol, "system", "user")
        assert req["url"].startswith("https://api.deepseek.com"), req["url"]
        assert req["body"]["model"] == PROTOCOL_MODELS[protocol]
        checks += 1
    # 解析自检
    chat_state = parse_chat_sse([
        'data: {"id":"x","model":"m","choices":[{"delta":{"content":"hi"},"finish_reason":null}],"usage":null}',
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":3,"completion_tokens":5}}',
        "data: [DONE]",
    ])
    assert chat_state.text == "hi" and chat_state.terminator and chat_state.usage["output"] == 5
    resp_state = parse_responses_sse([
        'data: {"type":"response.output_text.delta","delta":"ok"}',
        'data: {"type":"response.completed","response":{"id":"r","model":"m","status":"completed","usage":{"input_tokens":3,"output_tokens":4}}}',
    ])
    assert resp_state.text == "ok" and resp_state.terminator and resp_state.usage["input"] == 3
    anth_state = parse_anthropic_sse([
        'data: {"type":"message_start","message":{"id":"a","model":"m","usage":{"input_tokens":2,"output_tokens":0}}}',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"yo"}}',
        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":6}}',
        'data: {"type":"message_stop"}',
    ])
    assert anth_state.text == "yo" and anth_state.terminator and anth_state.usage["output"] == 6
    assert classify_error(status=429) == "HTTP_429"
    assert classify_error(text="x", terminator=False) == "STREAM_INCOMPLETE"
    assert classify_error(text="") == "EMPTY_TEXT"
    print(f"self-check OK：{checks} 请求构造 + 3 种 SSE 解析 + 错误分类")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DeepSeek 协议对照（chat/responses/anthropic；task-180）")
    sub = parser.add_subparsers(dest="command", required=True)
    compare = sub.add_parser("compare", help="40 题 × 3 协议（API 120；raw 写 a private archive）")
    compare.add_argument("--protocols", default="chat,responses,anthropic")
    compare.add_argument("--seed", type=int, default=COMPARE_SEED)
    compare.add_argument("--budget", type=int, default=API_BUDGET)
    compare.add_argument("--raw", default=str(DEFAULT_RAW))
    sub.add_parser("self-check", help="0 API 自检")
    args = parser.parse_args(argv)
    if args.command == "compare":
        return compare_command(args)
    if args.command == "self-check":
        return self_check_command(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
