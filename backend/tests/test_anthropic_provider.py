"""Exercise AnthropicProvider through the real SDK against a mocked HTTP transport."""

import json

import httpx2

from app.services.llm.anthropic_provider import FALLBACK_BETA, AnthropicProvider
from app.services.llm.base import ChatTurn, ToolError, ToolSpec


def _message(content, stop_reason, msg_id="msg_1"):
    return {
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 80},
    }


def _provider(responses, requests):
    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json=responses.pop(0))

    p = AnthropicProvider(api_key="sk-test", model="claude-opus-5-5", effort="medium")
    import anthropic

    p._client = anthropic.AsyncAnthropic(
        api_key="sk-test",
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return p


TOOLS = [ToolSpec("search_properties", "Find listings", {"type": "object", "properties": {}})]


async def test_tool_loop_request_shape_and_results():
    requests = []
    responses = [
        _message(
            [
                {"type": "thinking", "thinking": "", "signature": "sig"},
                {
                    "type": "tool_use",
                    "id": "tu_1",
                    "name": "search_properties",
                    "input": {"min_bedrooms": 3},
                },
                {
                    "type": "tool_use",
                    "id": "tu_2",
                    "name": "search_properties",
                    "input": {"bad": True},
                },
            ],
            "tool_use",
        ),
        _message([{"type": "text", "text": "Here are 2 options."}], "end_turn", "msg_2"),
    ]
    p = _provider(responses, requests)

    async def execute(name, args):
        if args.get("bad"):
            raise ToolError("bad filter")
        return '{"matches": []}'

    result = await p.run(
        system_stable="STABLE",
        system_dynamic="DYNAMIC",
        history=[ChatTurn("user", "3bhk?")],
        tools=TOOLS,
        execute=execute,
        max_iterations=4,
    )
    assert result.text == "Here are 2 options."
    assert [r.is_error for r in result.tool_calls] == [False, True]
    assert result.usage == {
        "input_tokens": 200,
        "output_tokens": 40,
        "cache_read_input_tokens": 160,
    }

    first = json.loads(requests[0].content)
    assert requests[0].headers["anthropic-beta"] == FALLBACK_BETA
    assert first["model"] == "claude-opus-5-5"
    assert first["fallbacks"] == "default"
    assert first["thinking"] == {"type": "adaptive"}
    assert first["output_config"] == {"effort": "medium"}
    assert "tool_choice" not in first and "temperature" not in first
    assert first["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert first["system"][1] == {"type": "text", "text": "DYNAMIC"}

    second = json.loads(requests[1].content)
    assistant, tool_results = second["messages"][1], second["messages"][2]
    # The assistant turn is replayed unchanged, thinking block included.
    assert [b["type"] for b in assistant["content"]] == ["thinking", "tool_use", "tool_use"]
    assert [b["tool_use_id"] for b in tool_results["content"]] == ["tu_1", "tu_2"]
    assert tool_results["content"][1]["is_error"] is True


async def test_refusal_is_reported():
    requests = []
    p = _provider([_message([], "refusal")], requests)

    async def execute(name, args):
        return "{}"

    result = await p.run(
        system_stable="S",
        system_dynamic="D",
        history=[ChatTurn("user", "x")],
        tools=TOOLS,
        execute=execute,
        max_iterations=2,
    )
    assert result.refused and result.text == ""


async def test_iteration_limit():
    requests = []
    loop = _message(
        [{"type": "tool_use", "id": "t", "name": "search_properties", "input": {}}], "tool_use"
    )
    p = _provider([loop, loop], requests)

    async def execute(name, args):
        return "{}"

    result = await p.run(
        system_stable="S",
        system_dynamic="D",
        history=[ChatTurn("user", "x")],
        tools=TOOLS,
        execute=execute,
        max_iterations=2,
    )
    assert result.hit_iteration_limit and len(requests) == 2
