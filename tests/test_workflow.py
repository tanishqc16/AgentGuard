from backend.agent import jarvis_agent
from backend.mock_data.emails import BY_ID, email_text
from backend.temporal.client import run_workflow
from backend.temporal.worker import make_worker


async def run(env, scenario):
    async with make_worker(env.client):
        return await run_workflow(email_text(BY_ID[scenario]), client=env.client)


async def test_safe_completes(env):
    r = await run(env, "deploy")
    assert r["status"] == "COMPLETED" and r["actions"] == [{"success": True, "action": "send_email"}]


async def test_prompt_injection_blocked_at_input(env):
    r = await run(env, "override")
    assert (r["status"], r["stage"]) == ("BLOCKED", "INPUT_GUARD")


async def test_propagation_blocked_at_output(env):
    r = await run(env, "backup")
    assert (r["status"], r["stage"]) == ("BLOCKED", "OUTPUT_GUARD")


async def test_agent_activity_is_retried(env, monkeypatch):
    calls = {"n": 0}
    real = jarvis_agent._mock_agent

    def flaky(message):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("model unavailable")
        return real(message)

    monkeypatch.setattr(jarvis_agent, "_mock_agent", flaky)
    r = await run(env, "deploy")
    assert r["status"] == "COMPLETED" and calls["n"] == 3
