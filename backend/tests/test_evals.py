"""The eval harness itself: fixture loads, grading is right. No model calls."""

from evals.run import grade, load_scenarios, run_trial
from tests.test_inbound import ScriptedProvider


def _state(**kw):
    base = {
        "final_reply": "",
        "tools": [],
        "appointment_status": None,
        "appointment_property": None,
        "conversation_mode": "bot",
        "contact": {},
        "photos_sent": 0,
    }
    return {**base, **kw}


def test_scenarios_are_well_formed():
    scenarios = load_scenarios()
    assert len({s["name"] for s in scenarios}) == len(scenarios) >= 10
    assert all(s["turns"] and s["expect"] for s in scenarios)


def test_grading_rules():
    expect = {
        "tools_called": ["search_properties"],
        "reply_matches": ["PR-1001"],
        "reply_not_matches": ["PR-1003"],
        "contact": {"budget_max_lte": 10_000_000},
    }
    ok = _state(
        final_reply="PR-1001 fits", tools=["search_properties"], contact={"budget_max": 9_000_000}
    )
    assert grade(expect, ok) == []
    bad = _state(final_reply="PR-1003!", contact={"budget_max": 2e7})
    assert len(grade(expect, bad)) == 4
    one_of = {"one_of": [{"tools_called": ["request_human"]}, {"reply_matches": ["team"]}]}
    assert grade(one_of, _state(final_reply="I'll ask the team")) == []
    assert grade(one_of, _state(final_reply="Yes!")) == ["none of the acceptable outcomes happened"]


async def test_trial_runs_end_to_end_with_scripted_model(db):
    scenario = next(s for s in load_scenarios() if s["name"] == "send_photos")
    provider = ScriptedProvider(
        [("send_property_photos", {"ref_code": "PR-1001"})], reply="Here are the photos of PR-1001."
    )
    trial = await run_trial(db, scenario, provider=provider)
    assert trial.passed, trial.failures
    assert trial.tools == ["send_property_photos"]

    cancel = next(s for s in load_scenarios() if s["name"] == "cancel_visit")
    lister = ScriptedProvider([("list_my_appointments", {})], reply="Which one?")
    trial = await run_trial(db, cancel, provider=lister)
    assert not trial.passed
    assert "tool not called: cancel_appointment" in trial.failures
