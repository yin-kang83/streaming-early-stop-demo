# -*- coding: utf-8 -*-
"""code/llm_protocols.py 离线测试（task-180）：0 API、0 网络。

覆盖：三种请求构造（URL/headers/body）、三种 SSE 流式解析、usage/finish/terminator 提取、
统一结果与错误分类、模型映射、mock 端到端、预算守卫、40 题确定性抽样。
"""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

import llm_protocols as llm  # noqa: E402


@pytest.fixture(autouse=True)
def _fake_key(monkeypatch):
    monkeypatch.setattr(llm, "_read_key", lambda: "fake")


# ---------------------------------------------------------------------------
# 1) 请求构造
# ---------------------------------------------------------------------------


def test_build_chat_request_url_headers_body():
    req = llm.build_chat_request("SYS", "USER", model="deepseek-chat")
    assert req["protocol"] == "chat"
    assert req["method"] == "POST"
    assert req["url"] == "https://api.deepseek.com/chat/completions"
    assert req["headers"]["Authorization"] == "Bearer fake"
    body = req["body"]
    assert body["model"] == "deepseek-chat"
    assert body["messages"][0] == {"role": "system", "content": "SYS"}
    assert body["messages"][1] == {"role": "user", "content": "USER"}
    assert body["stream"] is True
    assert body["stream_options"] == {"include_usage": True}
    assert body["temperature"] == 0.0
    assert body["max_tokens"] == 2000


def test_build_responses_request_semantic_fields():
    req = llm.build_responses_request("SYS", "USER", model="deepseek-flash")
    assert req["url"] == "https://api.deepseek.com/responses"
    body = req["body"]
    assert body["model"] == "deepseek-flash"
    assert body["instructions"] == "SYS"
    assert body["input"] == "USER"
    assert body["max_output_tokens"] == 2000
    assert body["stream"] is True
    # 官方文档：store/previous_response_id/metadata 等会被静默忽略 → 不发送
    for ignored in ("store", "previous_response_id", "metadata"):
        assert ignored not in body


def test_build_anthropic_request_url_headers_body():
    req = llm.build_anthropic_request("SYS", "USER", model="claude-3-5-sonnet-20241022")
    assert req["url"] == "https://api.deepseek.com/anthropic/v1/messages"
    assert req["headers"]["x-api-key"] == "fake"
    assert req["headers"]["anthropic-version"] == llm.ANTHROPIC_VERSION
    body = req["body"]
    assert body["model"] == "claude-3-5-sonnet-20241022"
    assert body["system"] == "SYS"
    assert body["messages"] == [{"role": "user", "content": "USER"}]
    assert body["max_tokens"] == 2000
    assert body["stream"] is True


# ---------------------------------------------------------------------------
# 2) 三种 SSE 解析
# ---------------------------------------------------------------------------


def test_parse_chat_sse_text_usage_finish_and_done():
    lines = [
        'data: {"id":"chat-1","model":"deepseek-chat","choices":[{"delta":{"role":"assistant"},"finish_reason":null}],"usage":null}',
        'data: {"choices":[{"delta":{"content":"答"},"finish_reason":null}],"usage":null}',
        'data: {"choices":[{"delta":{"content":"案"},"finish_reason":"stop"}],"usage":{"prompt_tokens":11,"completion_tokens":7}}',
        "data: [DONE]",
    ]
    state = llm.parse_chat_sse(lines)
    assert state.text == "答案"
    assert state.terminator is True
    assert state.finish_reason == "stop"
    assert state.usage == {"input": 11, "output": 7}
    assert state.events == 4
    assert state.raw_id == "chat-1"
    assert state.returned_model == "deepseek-chat"


def test_parse_responses_sse_semantic_events_no_done():
    lines = [
        'event: response.created',
        'data: {"type":"response.created","response":{"id":"resp-1","model":"deepseek-flash"}}',
        'event: response.output_text.delta',
        'data: {"type":"response.output_text.delta","delta":"hello"}',
        'data: {"type":"response.output_text.delta","delta":" world"}',
        'event: response.completed',
        'data: {"type":"response.completed","response":{"id":"resp-1","model":"deepseek-flash","status":"completed","usage":{"input_tokens":5,"output_tokens":2}}}',
    ]
    state = llm.parse_responses_sse(lines)
    assert state.text == "hello world"
    assert state.terminator is True  # 无 [DONE]，靠 response.completed
    assert state.finish_reason == "completed"
    assert state.usage == {"input": 5, "output": 2}
    assert state.raw_id == "resp-1"
    assert state.sse_format == "semantic-sse"


def test_parse_anthropic_sse_message_events():
    lines = [
        'event: message_start',
        'data: {"type":"message_start","message":{"id":"msg-1","model":"claude-x","usage":{"input_tokens":9,"output_tokens":0}}}',
        'event: content_block_delta',
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hel"}}',
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"lo"}}',
        'event: message_delta',
        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":6}}',
        'event: message_stop',
        'data: {"type":"message_stop"}',
    ]
    state = llm.parse_anthropic_sse(lines)
    assert state.text == "Hello"
    assert state.terminator is True
    assert state.finish_reason == "end_turn"
    assert state.usage == {"input": 9, "output": 6}
    assert state.raw_id == "msg-1"
    assert state.sse_format == "event-sse"


def test_parse_anthropic_ignores_tool_use_delta():
    lines = [
        'data: {"type":"content_block_delta","delta":{"type":"input_json_delta","partial_json":"{\\"a\\":1}"}}',
        'data: {"type":"message_stop"}',
    ]
    state = llm.parse_anthropic_sse(lines)
    assert state.text == ""
    assert state.terminator is True


# ---------------------------------------------------------------------------
# 3) 统一结果 / 错误分类 / 模型映射
# ---------------------------------------------------------------------------


def test_finalize_unified_result_fields():
    t0 = 100.0
    state = llm.StreamState(protocol="chat", _t0=t0, text="abc", usage={"input": 1, "output": 2},
                            finish_reason="stop", raw_id="id", returned_model="m", terminator=True)
    state._first_token_at = t0 + 0.25
    result = llm.finalize(state, protocol="chat", requested_model="deepseek-chat", latency_s=1.5)
    assert result["success"] is True
    assert result["text"] == "abc"
    assert result["first_token_s"] == 0.25
    assert result["latency_s"] == 1.5
    assert result["usage"] == {"input": 1, "output": 2}
    for key in ("protocol", "requested_model", "returned_model", "raw_id", "finish_reason",
                "stream_terminator", "sse_format", "error_class"):
        assert key in result


def test_classify_error_categories():
    assert llm.classify_error(status=429) == "HTTP_429"
    assert llm.classify_error(status=500) == "HTTP_500"
    assert llm.classify_error(socket.timeout()) == "TIMEOUT"
    assert llm.classify_error(TimeoutError()) == "TIMEOUT"
    assert llm.classify_error(Exception("boom")) == "ERROR_Exception"
    assert llm.classify_error(text="ok", terminator=True) == ""
    assert llm.classify_error(text="ok", terminator=False) == "STREAM_INCOMPLETE"
    assert llm.classify_error(text="") == "EMPTY_TEXT"
    assert llm.classify_error(text="", parse_errors=2) == "PARSE_ERROR"


def test_protocol_model_mapping():
    assert llm.PROTOCOL_MODELS["chat"] == "deepseek-chat"
    assert llm.PROTOCOL_MODELS["responses"] == "deepseek-flash"
    assert llm.PROTOCOL_MODELS["anthropic"].startswith("claude-")
    # Anthropic 映射由服务端完成：claude-opus*→v4-pro，其它 claude*→flash（文档口径，仅记录）
    assert llm.PROTOCOL_MODELS["anthropic"].count("-") >= 2


def test_call_protocol_offline_mock(monkeypatch):
    lines = [
        b'data: {"id":"x","model":"deepseek-chat","choices":[{"delta":{"content":"42"},"finish_reason":"stop"}],"usage":{"prompt_tokens":3,"completion_tokens":1}}\n',
        b"data: [DONE]\n",
    ]

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            return iter(lines)

    monkeypatch.setattr(llm.urllib.request, "urlopen", lambda req, timeout=None: FakeResponse())
    result = llm.call_protocol("chat", "SYS", "U", model="deepseek-chat")
    assert result["success"] is True
    assert result["text"] == "42"
    assert result["usage"]["output"] == 1
    assert result["stream_terminator"] is True
    assert result["first_token_s"] is not None and result["first_token_s"] >= 0


def test_call_protocol_http_error_classified(monkeypatch):
    import urllib.error

    def _raise(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 400, "bad request", hdrs=None, fp=None)

    monkeypatch.setattr(llm.urllib.request, "urlopen", _raise)
    result = llm.call_protocol("responses", "SYS", "U", model="deepseek-flash")
    assert result["success"] is False
    assert result["error_class"] == "HTTP_400"


# ---------------------------------------------------------------------------
# 4) 抽样与预算守卫
# ---------------------------------------------------------------------------
