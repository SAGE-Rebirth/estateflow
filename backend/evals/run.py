"""Run the assistant against buyer scenarios and grade the results.

    uv run python -m evals.run                      # all scenarios, 3 trials each
    uv run python -m evals.run -s budget_search -n 5

Uses the real LLM/embedding providers from your .env (this spends inference credits) and a
separate database (EVAL_DB_NAME, default "estateflow_eval") that is wiped per trial. It
refuses to run against your main DB_NAME.
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


@dataclass
class Trial:
    scenario: str
    passed: bool
    failures: list[str]
    replies: list[str]
    tools: list[str]
    seconds: float
    error: str | None = None


@dataclass
class Report:
    model: str
    started: str
    trials: list[Trial] = field(default_factory=list)


def load_scenarios(names: list[str] | None = None) -> list[dict[str, Any]]:
    data = json.loads((HERE / "scenarios.json").read_text())["scenarios"]
    return [s for s in data if not names or s["name"] in names]


def grade(expect: dict[str, Any], state: dict[str, Any]) -> list[str]:
    """Returns failed checks (empty = pass). `state` is what the run produced."""
    failures: list[str] = []
    reply = state["final_reply"]
    tools = state["tools"]
    for t in expect.get("tools_called", []):
        if t not in tools:
            failures.append(f"tool not called: {t}")
    for t in expect.get("tools_not_called", []):
        if t in tools:
            failures.append(f"tool should not be called: {t}")
    for pat in expect.get("reply_matches", []):
        if not re.search(pat, reply, re.IGNORECASE):
            failures.append(f"reply missing /{pat}/")
    for pat in expect.get("reply_not_matches", []):
        if re.search(pat, reply, re.IGNORECASE | re.MULTILINE):
            failures.append(f"reply contains /{pat}/")
    if "appointment_status" in expect:
        want, got = expect["appointment_status"], state["appointment_status"] or "none"
        if want != got:
            failures.append(f"appointment {got}, expected {want}")
    if (
        "appointment_property" in expect
        and state["appointment_property"] != expect["appointment_property"]
    ):
        failures.append(f"appointment for {state['appointment_property']}")
    if "conversation_mode" in expect and state["conversation_mode"] != expect["conversation_mode"]:
        failures.append(f"conversation mode {state['conversation_mode']}")
    for key, want in expect.get("contact", {}).items():
        if key.endswith("_lte"):
            got = state["contact"].get(key[:-4])
            if got is None or got > want:
                failures.append(f"contact.{key[:-4]}={got}, expected <= {want}")
        elif state["contact"].get(key) != want:
            failures.append(f"contact.{key}={state['contact'].get(key)}, expected {want}")
    if state["photos_sent"] < expect.get("photos_sent_min", 0):
        failures.append(f"photos sent: {state['photos_sent']}")
    if alternatives := expect.get("one_of"):
        if all(grade(alt, state) for alt in alternatives):
            failures.append("none of the acceptable outcomes happened")
    return failures


async def run_trial(db, scenario: dict[str, Any], provider=None) -> Trial:
    from app.core.db import coll, find_one
    from app.models import Appointment, Contact, Conversation, Property
    from app.services.inbound import handle_inbound
    from app.services.whatsapp.webhook import InboundMessage
    from evals.fixture import BUYER_WA_ID, NOW, seed
    from tests.conftest import FakeWhatsApp

    for name in await db.list_collection_names():
        await db[name].delete_many({})
    tenant = await seed(db, with_appointment=scenario.get("seed_appointment", False))
    whatsapp = FakeWhatsApp()
    tools: list[str] = []
    replies: list[str] = []
    started = time.monotonic()

    for i, text in enumerate(scenario["turns"]):
        event = InboundMessage(
            "EVAL", f"wamid.eval.{i}", BUYER_WA_ID, "Kiran", NOW, "text", text, {}
        )
        wrapped = _Recorder(provider, tools)
        out = await handle_inbound(db, tenant, event, whatsapp=whatsapp, provider=wrapped, now=NOW)
        replies.append(out.body if out else "")

    contact = await find_one(db, Contact, {"wa_id": BUYER_WA_ID})
    appt = await find_one(db, Appointment, {"contact_id": contact.id}, sort=[("updated_at", -1)])
    prop = (
        await find_one(db, Property, {"_id": appt.property_id})
        if appt and appt.property_id
        else None
    )
    conv = await find_one(db, Conversation, {"contact_id": contact.id})
    state = {
        "final_reply": replies[-1],
        "tools": tools,
        "appointment_status": appt.status.value if appt else None,
        "appointment_property": prop.ref_code if prop else None,
        "conversation_mode": conv.mode.value if conv else None,
        "contact": contact.model_dump(),
        "photos_sent": len(whatsapp.images),
    }
    failures = grade(scenario["expect"], state)
    await coll(db, Contact).count_documents({})  # keep the connection warm between trials
    return Trial(
        scenario["name"],
        not failures,
        failures,
        replies,
        tools,
        round(time.monotonic() - started, 1),
    )


class _Recorder:
    """Wraps the real provider to record which tools it called."""

    def __init__(self, provider, tools: list[str]) -> None:
        from app.services.llm.factory import get_chat_provider

        self.inner = provider or get_chat_provider()
        self.tools = tools

    async def run(self, **kw):
        result = await self.inner.run(**kw)
        self.tools.extend(t.name for t in result.tool_calls)
        return result


async def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("-s", "--scenario", action="append", help="run only these scenarios")
    ap.add_argument("-n", "--trials", type=int, default=3)
    args = ap.parse_args(argv)

    eval_db = os.environ.get("EVAL_DB_NAME", "estateflow_eval")
    from app.core.config import get_settings

    if eval_db == get_settings().db_name:
        print(f"Refusing to run: EVAL_DB_NAME equals DB_NAME ({eval_db}).", file=sys.stderr)
        return 2
    os.environ["DB_NAME"] = eval_db
    get_settings.cache_clear()
    from app.core.db import close_client, ensure_indexes, get_database

    s = get_settings()
    db = get_database()
    await ensure_indexes(db)
    model = s.gemini_llm_model if s.llm_provider == "gemini" else s.anthropic_model
    report = Report(model=model, started=datetime.now(UTC).isoformat())
    scenarios = load_scenarios(args.scenario)
    try:
        for sc in scenarios:
            for _ in range(args.trials):
                try:
                    trial = await run_trial(db, sc)
                except Exception as exc:  # a crash is a failed trial, not a dead run
                    trial = Trial(sc["name"], False, ["crashed"], [], [], 0, repr(exc)[:300])
                report.trials.append(trial)
                mark = "✓" if trial.passed else "✗"
                print(f"{mark} {sc['name']:<34} {trial.seconds:>5}s  {'; '.join(trial.failures)}")
    finally:
        await close_client()

    print(f"\nModel: {model}")
    total = 0
    for sc in scenarios:
        runs = [t for t in report.trials if t.scenario == sc["name"]]
        passed = sum(t.passed for t in runs)
        total += passed
        print(f"  {sc['name']:<34} {passed}/{len(runs)}")
    print(f"  {'overall':<34} {total}/{len(report.trials)}")
    out = HERE / "results" / f"{datetime.now(UTC):%Y%m%dT%H%M%S}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False))
    print(f"\nDetails: {out}")
    return 0 if total == len(report.trials) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
