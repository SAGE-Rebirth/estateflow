"""Gemini provider and embedder against a mocked google-genai client."""

from types import SimpleNamespace as NS

import pytest
from google.genai import types

from app.services.llm.base import ChatTurn, ToolError, ToolSpec
from app.services.llm.gemini_provider import GeminiProvider
from app.services.rag.embeddings import GeminiEmbedder


def _resp(text=None, calls=None, finish=types.FinishReason.STOP):
    parts = [types.Part(text=text)] if text else []
    parts += [types.Part(function_call=c, thought_signature=b"sig") for c in calls or []]
    content = types.Content(role="model", parts=parts)
    return NS(
        candidates=[NS(content=content, finish_reason=finish)],
        function_calls=calls or None,
        usage_metadata=NS(prompt_token_count=50, candidates_token_count=10, thoughts_token_count=5),
    )


def _call(id_, name, args):
    return types.FunctionCall(id=id_, name=name, args=args)


class FakeClient:
    def __init__(self, chat=None, embed=None):
        self.chat, self.embed = chat or [], embed
        self.calls = []
        self.aio = NS(models=self)

    async def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": list(contents), "config": config})
        return self.chat.pop(0)

    async def embed_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        return self.embed(contents, config)


TOOLS = [ToolSpec("search_properties", "Find listings", {"type": "object", "properties": {}})]


def _provider(client):
    return GeminiProvider(model="gemini-x", max_tokens=512, thinking_level="low", client=client)


async def _run(p, execute, iterations=4):
    return await p.run(
        system_stable="S",
        system_dynamic="D",
        history=[ChatTurn("user", "3bhk"), ChatTurn("assistant", "Sure"), ChatTurn("user", "go")],
        tools=TOOLS,
        execute=execute,
        max_iterations=iterations,
    )


async def test_tool_loop_echoes_model_turn_and_returns_results_in_order():
    client = FakeClient(
        [
            _resp(
                calls=[
                    _call("c1", "search_properties", {"min_bedrooms": 3}),
                    _call("c2", "search_properties", {"bad": True}),
                ]
            ),
            _resp(text="Two options for you."),
        ]
    )
    seen = []

    async def execute(name, args):
        seen.append(args)
        if args.get("bad"):
            raise ToolError("bad filter")
        return '{"matches": []}'

    result = await _run(_provider(client), execute)
    assert result.text == "Two options for you."
    assert seen == [{"min_bedrooms": 3}, {"bad": True}]
    assert [r.is_error for r in result.tool_calls] == [False, True]
    assert result.usage == {"input_tokens": 100, "output_tokens": 30}

    first, second = client.calls
    cfg = first["config"]
    assert first["model"] == "gemini-x" and cfg.system_instruction == "S\n\nD"
    assert cfg.tools[0].function_declarations[0].name == "search_properties"
    assert cfg.max_output_tokens > 512  # headroom for thinking tokens
    assert [c.role for c in first["contents"]] == ["user", "model", "user"]
    # The model's own turn goes back untouched (thought signatures included).
    echoed = second["contents"][3]
    assert echoed.role == "model" and echoed.parts[0].thought_signature == b"sig"
    responses = [p.function_response for p in second["contents"][4].parts]
    assert [r.id for r in responses] == ["c1", "c2"]
    assert responses[0].response == {"output": '{"matches": []}'}
    assert responses[1].response == {"error": "Error: bad filter"}


async def test_iteration_limit_and_safety_block():
    async def execute(name, args):
        return "{}"

    loop = [_resp(calls=[_call("c", "search_properties", {})]) for _ in range(2)]
    assert (await _run(_provider(FakeClient(loop)), execute, iterations=2)).hit_iteration_limit

    blocked = FakeClient([_resp(finish=types.FinishReason.SAFETY)])
    assert (await _run(_provider(blocked), execute)).refused
    empty = FakeClient([NS(candidates=[], function_calls=None, usage_metadata=None)])
    assert (await _run(_provider(empty), execute)).refused


async def test_thought_parts_are_not_sent_to_the_buyer():
    resp = _resp(text="Here you go.")
    resp.candidates[0].content.parts.insert(0, types.Part(text="planning...", thought=True))

    async def execute(name, args):
        return "{}"

    assert (await _run(_provider(FakeClient([resp])), execute)).text == "Here you go."


async def test_embedder_batches_and_normalizes():
    def embed(contents, config):
        assert config.output_dimensionality == 3
        # Each text is its own Content; a bare string list would be merged into one vector.
        assert all(isinstance(c, types.Content) for c in contents)
        return NS(embeddings=[NS(values=[3.0, 0.0, 4.0]) for _ in contents])

    client = FakeClient(embed=embed)
    e = GeminiEmbedder(client=client)
    e._dim = 3
    vecs = await e.embed_documents([f"t{i}" for i in range(150)])
    assert len(vecs) == 150 and vecs[0] == [0.6, 0.0, 0.8]
    assert [len(c["contents"]) for c in client.calls] == [100, 50]
    assert client.calls[0]["config"].task_type == "RETRIEVAL_DOCUMENT"
    await e.embed_query("q")
    assert client.calls[-1]["config"].task_type == "RETRIEVAL_QUERY"


async def test_embedder_rejects_short_response():
    e = GeminiEmbedder(client=FakeClient(embed=lambda c, cfg: NS(embeddings=[NS(values=[1.0])])))
    e._dim = 1
    with pytest.raises(RuntimeError):
        await e.embed_documents(["a", "b"])
