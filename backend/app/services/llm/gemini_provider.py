import asyncio
from typing import Any

from google.genai import types

from app.services.gemini import gemini_client
from app.services.llm.base import (
    AgentResult,
    ChatTurn,
    ToolExecutor,
    ToolSpec,
    run_tool,
)

# Thinking tokens count against max_output_tokens; keep room so the reply isn't starved.
THINKING_HEADROOM = 4096
BLOCKED = {
    types.FinishReason.SAFETY,
    types.FinishReason.PROHIBITED_CONTENT,
    types.FinishReason.BLOCKLIST,
    types.FinishReason.SPII,
}


class GeminiProvider:
    """Chat with function calling through the Gemini API."""

    def __init__(
        self, *, model: str, max_tokens: int, thinking_level: str, client: Any = None
    ) -> None:
        self._client = client or gemini_client()
        self._model = model
        self._max_tokens = max_tokens
        self._thinking_level = thinking_level

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
        config = types.GenerateContentConfig(
            system_instruction=f"{system_stable}\n\n{system_dynamic}",
            tools=[
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=t.name,
                            description=t.description,
                            parameters_json_schema=t.input_schema,
                        )
                        for t in tools
                    ]
                )
            ],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            thinking_config=types.ThinkingConfig(thinking_level=self._thinking_level),
            max_output_tokens=self._max_tokens + THINKING_HEADROOM,
        )
        contents: list[types.Content] = [
            types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[types.Part(text=m.content)],
            )
            for m in history
        ]
        result = AgentResult(text="")

        for _ in range(max_iterations):
            response = await self._client.aio.models.generate_content(
                model=self._model, contents=contents, config=config
            )
            if usage := response.usage_metadata:
                result.usage["input_tokens"] = result.usage.get("input_tokens", 0) + (
                    usage.prompt_token_count or 0
                )
                result.usage["output_tokens"] = result.usage.get("output_tokens", 0) + (
                    (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
                )
            candidate = response.candidates[0] if response.candidates else None
            if candidate is None or candidate.finish_reason in BLOCKED:
                result.refused = True
                return result

            calls = response.function_calls or []
            if not calls:
                result.text = "".join(
                    p.text
                    for p in (candidate.content.parts if candidate.content else None) or []
                    if p.text and not p.thought
                ).strip()
                return result

            # Echo the model's turn as-is: Gemini 3 needs its thought signatures back.
            contents.append(candidate.content)
            records = await asyncio.gather(
                *(run_tool(execute, c.name or "", dict(c.args or {})) for c in calls)
            )
            result.tool_calls.extend(records)
            # All function responses go back in a single user turn, in call order.
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                id=c.id,
                                name=c.name,
                                response={"error" if r.is_error else "output": r.output},
                            )
                        )
                        for c, r in zip(calls, records, strict=True)
                    ],
                )
            )

        result.hit_iteration_limit = True
        return result
