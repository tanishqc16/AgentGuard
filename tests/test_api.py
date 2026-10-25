from httpx import ASGITransport, AsyncClient

from backend.api.server import app, temporal_client
from backend.temporal.worker import make_worker


async def post(env, scenario):
    app.dependency_overrides[temporal_client] = lambda: env.client
    async with make_worker(env.client):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            return await c.post("/run", json={"scenario": scenario})


async def test_run_prompt_injection(env):
    body = (await post(env, "override")).json()
    assert body["workflow_id"].startswith("agentguard-")
    assert (body["status"], body["stage"], body["risk"]) == ("BLOCKED", "INPUT_GUARD", 85)
    assert body["agent"] is None


async def test_run_propagation_has_stage_details(env):
    body = (await post(env, "backup")).json()
    assert (body["status"], body["stage"]) == ("BLOCKED", "OUTPUT_GUARD")
    assert body["agent"]["actions"][0]["to"] == "backup@external-share.net"
    assert body["actions"] == []


async def test_unknown_scenario_404(env):
    assert (await post(env, "nope")).status_code == 404


async def test_run_safe_completes_with_mock_action(env):
    body = (await post(env, "deploy")).json()
    assert (body["status"], body["stage"]) == ("COMPLETED", "ACTION")
    assert body["actions"] == [{"success": True, "action": "send_email"}]


async def test_status_unknown_then_completed(env):
    app.dependency_overrides[temporal_client] = lambda: env.client
    async with make_worker(env.client):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            assert (await c.get("/status/agentguard-nope")).json()["status"] == "PENDING"
            await c.post("/run", json={"scenario": "deploy", "workflow_id": "agentguard-known"})
            s = (await c.get("/status/agentguard-known")).json()
    assert s["status"] == "COMPLETED" and s["worker_connected"]
