import asyncio
import json
from typing import Any

from app.services.hf import hf_client
from app.services.llm.base import (
    AgentResult,
    ChatTurn,
    ToolCallRecord,
    ToolExecutor,
    ToolSpec,
    run_tool,
)


class HuggingFaceProvider:
    """Chat with tool calling through HF Inference Providers (OpenAI-style messages)."""

    def __init__(self, *, model: str, max_tokens: int, client: Any = None) -> None:
        self._client = client or hf_client()
        self._model = model
        self._max_tokens = max_tokens

    async def run(
        self,
        *,
        system_stable: str,
        system_dynamic: str,
        history: list[ChatTurn],
        tools: list[ToolSpec],
        execute: ToolExecutor,
        max_iterations: int,
    ) -> AgentResult:
        tool_defs = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in tools
        ]
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": f"{system_stable}\n\n{system_dynamic}"},
            *({"role": m.role, "content": m.content} for m in history),
        ]
        result = AgentResult(text="")

        for _ in range(max_iterations):
            response = await self._client.chat_completion(
                messages=messages,
                model=self._model,
                tools=tool_defs,
                tool_choice="auto",
                max_tokens=self._max_tokens,
            )
            if response.usage:
                for ours, theirs in (
                    ("input_tokens", "prompt_tokens"),
                    ("output_tokens", "completion_tokens"),
                ):
                    result.usage[ours] = result.usage.get(ours, 0) + (
                        getattr(response.usage, theirs, 0) or 0
                    )
            choice = response.choices[0]
            msg = choice.message
            if choice.finish_reason == "content_filter":
                result.refused = True
                return result
            calls = msg.tool_calls or []
            if not calls:
                result.text = (msg.content or "").strip()
                return result

            # Providers return arguments as a JSON string or an already-parsed object.
            parsed: list[tuple[Any, dict[str, Any] | None]] = []
            for tc in calls:
                raw = tc.function.arguments
                if isinstance(raw, dict):
                    parsed.append((tc, raw))
                else:
                    try:
                        parsed.append((tc, json.loads(raw or "{}")))
                    except json.JSONDecodeError:
                        parsed.append((tc, None))

            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": json.dumps(args or {}),
                            },
                        }
                        for tc, args in parsed
                    ],
                }
            )

            async def _call(tc: Any, args: dict[str, Any] | None) -> ToolCallRecord:
                if args is None:
                    return ToolCallRecord(tc.function.name, {}, "Error: invalid JSON", True)
                return await run_tool(execute, tc.function.name, args)

            records = await asyncio.gather(*(_call(tc, a) for tc, a in parsed))
            result.tool_calls.extend(records)
            for (tc, _), rec in zip(parsed, records, strict=True):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.function.name,
                        "content": rec.output,
                    }
                )

        result.hit_iteration_limit = True
        return result
