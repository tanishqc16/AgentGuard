import asyncio
import os
import subprocess
import sys
from pathlib import Path

from backend.temporal.client import TASK_QUEUE
from backend.workflows.agentguard_workflow import AgentGuardWorkflow

ROOT = Path(__file__).resolve().parent.parent


def start_worker(host):
    return subprocess.Popen(
        [sys.executable, "-m", "backend.temporal.worker"], cwd=ROOT,
        env={**os.environ, "TEMPORAL_HOST": host},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def test_workflow_survives_worker_kill(env):
    host = env.client.service_client.config.target_host
    worker = start_worker(host)
    try:
        handle = await env.client.start_workflow(
            AgentGuardWorkflow.run, args=["Deployment is scheduled for Friday.", 30],
            id="crash-test", task_queue=TASK_QUEUE)

        # Wait until the agent activity is running and heartbeating on worker #1.
        for _ in range(150):
            pending = (await handle.describe()).raw_description.pending_activities
            if pending and pending[0].HasField("last_heartbeat_time"):
                break
            await asyncio.sleep(0.2)
        else:
            raise AssertionError("agent activity never started")

        worker.kill()  # SIGKILL: a real crash, no graceful shutdown
        worker.wait()
        worker = start_worker(host)

        result = await asyncio.wait_for(handle.result(), timeout=60)
    finally:
        worker.kill()

    assert result["status"] == "COMPLETED"
    # Retried attempts aren't separate history events; the last start records the attempt number.
    attempts = [e.activity_task_started_event_attributes.attempt
                async for e in handle.fetch_history_events() if e.HasField("activity_task_started_event_attributes")]
    assert max(attempts) >= 2  # the activity was rescheduled onto the restarted worker
