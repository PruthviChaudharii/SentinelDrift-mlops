"""Runs independently of the dashboard; no made-up predictions or labels."""
import json
import os
from datetime import datetime, timedelta
from urllib.request import Request, urlopen

from airflow.sdk import dag, task


def api(path, method="GET"):
    request = Request(os.environ.get("SENTINEL_API", "http://api:8000") + path,
                      data=b"{}" if method == "POST" else None, method=method,
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=300) as response:
        return json.load(response)


@dag(schedule="*/5 * * * *", start_date=datetime(2026, 1, 1), catchup=False,
     max_active_runs=1, default_args={"retries": 1, "retry_delay": timedelta(minutes=1)},
     tags=["reviewed-feedback", "self-healing"])
def sentineldrift_recovery():
    @task
    def inspect_evidence():
        return api("/api/recovery/check")

    @task
    def enforce_policy_and_recover(evidence):
        # The API rechecks readiness/degradation atomically. Insufficient evidence is a real skip.
        result = api("/api/recovery/tick", "POST")
        if result.get("status") == "Failed":
            raise RuntimeError(result.get("error", "Recovery failed"))
        return result

    enforce_policy_and_recover(inspect_evidence())


sentineldrift_recovery()
