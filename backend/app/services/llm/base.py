from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ChatTurn:
    role: Literal["user", "assistant"]
    content: str


@dataclass
class ToolCallRecord:
    name: str
    input: dict[str, Any]
    output: str
    is_error: bool = False


@dataclass
class AgentResult:
    text: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    refused: bool = False
    hit_iteration_limit: bool = False
    usage: dict[str, int] = field(default_factory=dict)


class ToolError(Exception):
    """Raised by a tool to report a recoverable problem back to the model."""


ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[str]]


class ChatProvider(Protocol):
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
        """Run one agent turn: call the model, execute tools until it answers."""
        ...


async def run_tool(execute: ToolExecutor, name: str, args: dict[str, Any]) -> ToolCallRecord:
    try:
        return ToolCallRecord(name, args, await execute(name, args))
    except ToolError as exc:
        return ToolCallRecord(name, args, f"Error: {exc}", is_error=True)
