import asyncio
from typing import Any

import anthropic

from app.services.llm.base import (
    AgentResult,
    ChatTurn,
    ToolExecutor,
    ToolSpec,
    run_tool,
)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    def __init__(self, *, api_key: str | None, model: str, effort: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._effort = effort

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
        # Stable persona/tenant text first and cached; per-turn context after the breakpoint.
        system = [
            {"type": "text", "text": system_stable, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": system_dynamic},
        ]
        tool_defs = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in tools
        ]
        messages: list[dict[str, Any]] = [{"role": m.role, "content": m.content} for m in history]
        result = AgentResult(text="")

        for _ in range(max_iterations):
            response = await self._client.beta.messages.create(
                model=self._model,
                max_tokens=16000,
                system=system,
                tools=tool_defs,
                messages=messages,
                thinking={"type": "adaptive"},
                output_config={"effort": self._effort},
                # On a safety decline, re-run server-side on Anthropic's recommended fallback.
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
            self._add_usage(result, response.usage)

            if response.stop_reason == "refusal":
                result.refused = True
                return result

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "pause_turn":
                continue

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not tool_uses:
                result.text = "\n".join(
                    b.text for b in response.content if b.type == "text"
                ).strip()
                return result

            records = await asyncio.gather(
                *(run_tool(execute, b.name, dict(b.input)) for b in tool_uses)
            )
            result.tool_calls.extend(records)
            # All tool results go back in a single user message.
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": b.id,
                            "content": r.output,
                            "is_error": r.is_error,
                        }
                        for b, r in zip(tool_uses, records, strict=True)
                    ],
                }
            )

        result.hit_iteration_limit = True
        return result

    @staticmethod
    def _add_usage(result: AgentResult, usage: Any) -> None:
        for key in ("input_tokens", "output_tokens", "cache_read_input_tokens"):
            result.usage[key] = result.usage.get(key, 0) + (getattr(usage, key, 0) or 0)
