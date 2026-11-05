"""Hugging Face provider and embedder against a mocked inference client."""

import json
from types import SimpleNamespace as NS

import numpy as np

from app.services.llm.base import ChatTurn, ToolError, ToolSpec
from app.services.llm.huggingface_provider import HuggingFaceProvider
from app.services.rag.embeddings import HuggingFaceEmbedder


def _resp(content=None, tool_calls=None, finish="stop"):
    return NS(
        choices=[NS(message=NS(content=content, tool_calls=tool_calls), finish_reason=finish)],
        usage=NS(prompt_tokens=50, completion_tokens=10),
    )


def _tc(id_, name, args):
    return NS(id=id_, function=NS(name=name, arguments=args))


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def chat_completion(self, **kw):
        self.calls.append(json.loads(json.dumps(kw, default=str)))
        return self.responses.pop(0)


TOOLS = [ToolSpec("search_properties", "Find listings", {"type": "object", "properties": {}})]


async def test_tool_loop_handles_string_and_dict_arguments():
    client = FakeClient(
        [
            _resp(
                tool_calls=[
                    _tc("c1", "search_properties", '{"min_bedrooms": 3}'),
                    _tc("c2", "search_properties", {"bad": True}),
                    _tc("c3", "search_properties", "{not json"),
                ],
                finish="tool_calls",
            ),
            _resp(content="Two options for you."),
        ]
    )
    seen = []

    async def execute(name, args):
        seen.append(args)
        if args.get("bad"):
            raise ToolError("bad filter")
        return '{"matches": []}'

    p = HuggingFaceProvider(model="Qwen/Qwen3", max_tokens=512, client=client)
    result = await p.run(
        system_stable="S",
        system_dynamic="D",
        history=[ChatTurn("user", "3bhk")],
        tools=TOOLS,
        execute=execute,
        max_iterations=4,
    )
    assert result.text == "Two options for you."
    assert seen == [{"min_bedrooms": 3}, {"bad": True}]
    assert [r.is_error for r in result.tool_calls] == [False, True, True]
    assert result.usage == {"input_tokens": 100, "output_tokens": 20}

    first, second = client.calls
    assert first["model"] == "Qwen/Qwen3" and first["tool_choice"] == "auto"
    assert first["messages"][0] == {"role": "system", "content": "S\n\nD"}
    assert first["tools"][0]["function"]["name"] == "search_properties"
    assistant = second["messages"][2]
    assert [tc["function"]["arguments"] for tc in assistant["tool_calls"]] == [
        '{"min_bedrooms": 3}',
        '{"bad": true}',
        "{}",
    ]
    tool_msgs = second["messages"][3:]
    assert [m["tool_call_id"] for m in tool_msgs] == ["c1", "c2", "c3"]
    assert all(m["role"] == "tool" for m in tool_msgs)


async def test_iteration_limit_and_content_filter():
    loop = _resp(tool_calls=[_tc("c", "search_properties", "{}")], finish="tool_calls")
    p = HuggingFaceProvider(model="m", max_tokens=1, client=FakeClient([loop, loop]))

    async def execute(name, args):
        return "{}"

    r = await p.run(
        system_stable="S",
        system_dynamic="D",
        history=[ChatTurn("user", "x")],
        tools=TOOLS,
        execute=execute,
        max_iterations=2,
    )
    assert r.hit_iteration_limit
    p = HuggingFaceProvider(
        model="m", max_tokens=1, client=FakeClient([_resp(finish="content_filter")])
    )
    r = await p.run(
        system_stable="S",
        system_dynamic="D",
        history=[ChatTurn("user", "x")],
        tools=TOOLS,
        execute=execute,
        max_iterations=2,
    )
    assert r.refused


async def test_embedder_reduces_shapes_to_one_vector():
    class Client:
        async def feature_extraction(self, text, model, normalize):
            return {
                "pooled": np.array([0.1, 0.2, 0.3]),
                "batched": np.array([[0.1, 0.2, 0.3]]),
                "tokens": np.array([[[0.0, 0.2, 0.2], [0.2, 0.2, 0.4]]]),
            }[text]

    e = HuggingFaceEmbedder.__new__(HuggingFaceEmbedder)
    e._model, e._client = "m", Client()
    import asyncio

    e._sem = asyncio.Semaphore(2)
    vecs = await e.embed_documents(["pooled", "batched", "tokens"])
    assert [[round(x, 3) for x in v] for v in vecs] == [[0.1, 0.2, 0.3]] * 3
