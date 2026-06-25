"""Regression tests: never leak raw tool-call markup to a customer.

DeepSeek/the proxy sometimes emits a tool call as text in message.content
instead of the structured tool_calls field. These tests cover the parser,
the stripper, and the final sanitizer that protect the customer-facing text.
"""
from app.engine.conversation import (
    _looks_like_leaked_toolcall,
    _parse_leaked_tool_calls,
    _strip_tool_markup,
    _sanitize_reply,
)

# The exact content that reached a real customer's phone.
LEAKED = (
    "Let me broaden that search a bit!\n"
    '<｜｜Dsml｜｜tool_calls>\n'
    '<｜｜Dsml｜｜invoke name="check_inventory">\n'
    '<｜｜Dsml｜｜parameter name="query" string="true">compact SUV</｜｜Dsml｜｜parameter>\n'
    '</｜｜Dsml｜｜invoke>\n'
    '</｜｜Dsml｜｜tool_calls>'
)


def test_detects_leaked_toolcall():
    assert _looks_like_leaked_toolcall(LEAKED) is True
    assert _looks_like_leaked_toolcall("Sure! We have a few SUVs in stock.") is False


def test_parses_leaked_invoke_format():
    calls = _parse_leaked_tool_calls(LEAKED)
    assert calls == [("check_inventory", {"query": "compact SUV"})]


def test_parses_deepseek_native_json_format():
    native = 'function<｜tool▁sep｜>check_inventory\n```json\n{"body": "SUV", "max_price": 30000}\n```'
    calls = _parse_leaked_tool_calls(native)
    assert calls and calls[0][0] == "check_inventory"
    assert calls[0][1].get("body") == "SUV"


def test_strip_keeps_prose_drops_markup():
    cleaned = _strip_tool_markup(LEAKED)
    assert cleaned == "Let me broaden that search a bit!"
    assert "invoke" not in cleaned
    assert "｜" not in cleaned
    assert "tool_calls" not in cleaned


def test_sanitize_never_leaks_markup():
    out = _sanitize_reply(LEAKED)
    for bad in ("invoke", "tool_calls", "｜", "parameter name", "<｜"):
        assert bad not in out
    assert len(out) >= 15


def test_sanitize_passes_clean_text_through():
    clean = "We have a 2023 Mazda CX-5 GX at $31,200. Want to come see it this week?"
    assert _sanitize_reply(clean) == clean


def test_sanitize_handles_empty():
    assert _sanitize_reply("") == "Thank you for your message!"
    assert _sanitize_reply(None) == "Thank you for your message!"
