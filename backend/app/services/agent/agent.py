import structlog

from app.core.config import get_settings
from app.core.db import find, find_one
from app.models import Direction, Message, Property
from app.services.agent.prompts import dynamic_context, stable_system_prompt
from app.services.agent.tools import TOOL_SPECS, AgentContext, make_executor, request_human
from app.services.llm.base import AgentResult, ChatProvider, ChatTurn
from app.services.llm.factory import get_chat_provider

log = structlog.get_logger()

FALLBACK_REPLY = (
    "Thanks for your message! I'm passing this to our team and someone will get back to you "
    "here shortly."
)


async def load_history(ctx: AgentContext) -> list[ChatTurn]:
    rows = await find(
        ctx.db,
        Message,
        {"conversation_id": ctx.conversation.id, "body": {"$ne": ""}},
        sort=[("created_at", -1)],
        limit=get_settings().agent_history_turns,
    )
    turns: list[ChatTurn] = []
    for m in reversed(rows):
        role = "user" if m.direction == Direction.inbound else "assistant"
        # Merge consecutive same-role messages (e.g. several WhatsApp bubbles in a row).
        if turns and turns[-1].role == role:
            turns[-1] = ChatTurn(role, f"{turns[-1].content}\n{m.body}")
        else:
            turns.append(ChatTurn(role, m.body))
    while turns and turns[0].role != "user":
        turns.pop(0)
    return turns


async def run_agent(
    ctx: AgentContext, provider: ChatProvider | None = None
) -> tuple[str, AgentResult | None]:
    """Produce the assistant's reply to the latest inbound message. Never raises on LLM errors."""
    provider = provider or get_chat_provider()
    focus = (
        await find_one(ctx.db, Property, {"_id": ctx.conversation.focus_property_id})
        if ctx.conversation.focus_property_id
        else None
    )
    history = await load_history(ctx)
    if not history:
        return FALLBACK_REPLY, None
    try:
        result = await provider.run(
            system_stable=stable_system_prompt(ctx.tenant),
            system_dynamic=dynamic_context(ctx.tenant, ctx.contact, focus, ctx.now),
            history=history,
            tools=TOOL_SPECS,
            execute=make_executor(ctx),
            max_iterations=get_settings().llm_max_tool_iterations,
        )
    except Exception:
        log.exception("agent_failed", conversation_id=ctx.conversation.id)
        await request_human(ctx, {"reason": "The assistant hit an error answering."})
        return FALLBACK_REPLY, None

    log.info(
        "agent_turn",
        conversation_id=ctx.conversation.id,
        tools=[t.name for t in result.tool_calls],
        usage=result.usage,
        refused=result.refused,
    )
    if result.refused or result.hit_iteration_limit or not result.text:
        await request_human(ctx, {"reason": "The assistant couldn't answer this one."})
        return FALLBACK_REPLY, result
    return result.text, result
