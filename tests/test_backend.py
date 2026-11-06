"""Isolated synthetic fixtures test mechanics; they are never production review evidence."""
import json
import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.engine import ROOT
from backend.service import Service, now


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "workspace", (tmp_path / "mlruns").as_uri())
    with TestClient(app) as c:
        yield c


def test_official_domains_match_frozen_classifier(client):
    result = client.post("/api/analyze", json={"urls": ["https://www.chelseafc.com/en", "https://www.microsoft.com/en-us/"]})
    assert result.status_code == 200
    predictions = result.json()["predictions"]
    assert all(p["score"] < 20 and p["model"] == "multisource-rf-v2" for p in predictions)
    s = client.app.state.service
    expected = s.engine.call("predict", rows=[p["features"] for p in predictions], artifact=None)
    assert [p["score"] / 100 for p in predictions] == pytest.approx(expected)
    assert client.get("/api/state").json()["requests"] == 2


def test_invalid_batch_is_atomic_and_cross_site_write_blocked(client):
    response = client.post("/api/analyze", json={"urls": ["https://example.com", "javascript:alert(1)"]})
    assert response.status_code == 400
    assert client.get("/api/state").json()["requests"] == 0
    assert client.post("/api/analyze", headers={"Origin": "https://untrusted.invalid"}, json={"urls": ["https://example.com"]}).status_code == 403


def test_predictions_and_reviews_survive_restart(tmp_path):
    path = tmp_path / "persistent"
    s = Service(path)
    p = s.analyze(["https://www.chelseafc.com/en"])[0]
    s.review([{"url": p["url"], "label": 0, "evidence": "Synthetic test attestation only", "reviewer": "Test"}])
    s.close()
    restored = Service(path)
    try:
        assert restored.s["requests"] == 1
        assert restored.s["feedback"][0]["prediction"]["id"] == p["id"]
        assert restored.performance()["error"] == 0
    finally:
        restored.close()


def test_database_rejects_a_different_baseline_artifact(tmp_path):
    s = Service(tmp_path)
    s.s["base_sha256"] = "wrong-baseline-sha"
    s.persist()
    s.close()
    with pytest.raises(RuntimeError, match="baseline mismatch"):
        Service(tmp_path)


def test_review_attestation_canonical_dedup_and_saved_decision(client):
    client.post("/api/analyze", json={"urls": ["https://example.com/#fragment"]})
    row = {"url": "https://example.com/", "label": 0, "evidence": "Independent fixture reference", "reviewer": "Test", "attested": True}
    bad = {**row, "attested": False}
    assert client.post("/api/feedback", json={"records": [bad]}).status_code == 422
    assert client.post("/api/feedback", json={"records": [row]}).status_code == 200
    assert client.post("/api/feedback", json={"records": [{**row, "url": "https://EXAMPLE.com/#another"}]}).status_code == 400
    state = client.get("/api/state").json()
    assert state["feedback"][0]["prediction"]["model"] == "multisource-rf-v2"
    assert not state["degradation"]["confirmed"]


def test_drift_requires_distinct_batch_not_one_suspicious_link(client):
    client.post("/api/analyze", json={"urls": ["https://example.com/"] * 30})
    assert client.get("/api/state").json()["drift"]["count"] == 1
    client.post("/api/analyze", json={"urls": [f"https://example.com/{i}" for i in range(30)]})
    drift = client.get("/api/state").json()["drift"]
    assert drift["ready"] and len(drift["features"]) == 21
    assert all(math.isfinite(f["psi"]) for f in drift["features"])
    assert client.post("/api/recovery/tick", json={}).json()["status"] == "skipped"


def test_real_training_logs_mlflow_and_never_bypasses_gate(client):
    import mlflow
    from mlflow.tracking import MlflowClient
    urls = [f"https://review-fixture-{i}.invalid/{i}" for i in range(100)]
    records = [{"url": u, "label": i % 2, "evidence": "SYNTHETIC TEST ONLY, not real evidence", "reviewer": "Test", "attested": True}
               for i, u in enumerate(urls)]
    assert client.post("/api/feedback", json={"records": records}).status_code == 200
    assert client.get("/api/state").json()["readiness"]["ok"]
    result = client.post("/api/recovery/train", json={}).json()
    assert result["status"] in ("Candidate", "Rejected"), result
    state = client.get("/api/state").json()
    v = state["versions"][result["id"]]
    assert v["loss"][1] < v["loss"][0]
    assert v["epochs"] == 240
    assert v["evaluation"]["official_regressions"]["n"] == 32
    assert any(c["name"] == "Historical false-positive guard" for c in v["evaluation"]["checks"])
    assert state["champion"] == "multisource-rf-v2"
    assert bool(state["candidate"]) == v["evaluation"]["pass"]
    run = MlflowClient().get_run(result["mlflow_run_id"])
    assert run.info.status == "FINISHED"
    assert run.data.params["dataset_sha256"] == v["dataset_sha256"]
    assert "recent_fpr" in run.data.metrics
    assert client.post("/api/recovery/promote", json={}).status_code == 400


def test_actual_canary_serves_candidate_and_rollback_restores_baseline(client):
    s = client.app.state.service
    a = s.info["assets"]
    s.s["versions"]["test-candidate"] = {"artifact": {"weights": [0] * 21, "bias": -25, "mean": a["mean"], "scale": a["scale"]},
                                           "evaluation": {"pass": True}, "threshold": s.s["settings"]["threshold"], "status": "Candidate"}
    s.s["candidate"] = "test-candidate"
    client.post("/api/recovery/canary", json={})
    s.s["canary"]["weight"] = 100  # Deterministic fixture; public policy caps at 50%.
    p = client.post("/api/analyze", json={"urls": ["http://account-verify.example.xyz/login"]}).json()["predictions"][0]
    assert p["model"] == "test-candidate" and p["score"] < .01
    assert client.post("/api/recovery/promote", json={}).status_code == 400
    assert client.post("/api/recovery/rollback", json={}).status_code == 200
    p = client.post("/api/analyze", json={"urls": ["http://account-verify.example.xyz/login"]}).json()["predictions"][0]
    assert p["model"] == "multisource-rf-v2" and p["score"] >= 90


def test_shap_explains_the_saved_serving_score(client):
    p = client.post("/api/analyze", json={"urls": ["https://www.chelseafc.com/en"]}).json()["predictions"][0]
    explanation = client.post("/api/explain", json={"prediction_id": p["id"]})
    assert explanation.status_code == 200
    e = explanation.json()
    assert len(e["features"]) == 21
    assert next(f for f in e["features"] if f["name"] == "HTTPS")["contribution"] == 0
    assert e["expected_value"] + sum(f["contribution"] for f in e["features"]) == pytest.approx(p["score"] / 100, abs=1e-6)
    assert client.get("/metrics").status_code == 200
    assert "sentinel_predictions_total_saved 1.0" in client.get("/metrics").text


def test_policy_protects_threshold_floor_and_markup_is_static(client):
    assert client.put("/api/settings", json={"threshold": .5, "canary": 10, "cooldown": 0, "enabled": True, "auto": False}).status_code == 422
    assert "backend.js" in client.get("/").text
    assert "SENTINEL_SERVER_MODE=true" in client.get("/").text
    assert client.get("/api/health").json()["scope"] == "persistent-server"


def test_promotion_and_safety_rollback_use_only_fresh_trial_reviews(client):
    s = client.app.state.service
    s.s["settings"]["auto"] = False
    s.s["versions"]["equal-candidate"] = {"artifact": None, "evaluation": {"pass": True},
                                             "threshold": s.s["settings"]["threshold"], "status": "Candidate"}
    s.s["candidate"] = "equal-candidate"
    s.start_canary()
    urls = [f"https://fresh-fixture-{i}.invalid/{i}" for i in range(20)]
    predictions = s.analyze(urls)
    s.review([{"url": p["url"], "label": i % 2, "evidence": "Synthetic trial fixture, not real evidence", "reviewer": "Test"}
              for i, p in enumerate(predictions)])
    assert s.canary_evidence()["pass"]
    s.promote()
    assert s.s["champion"] == "equal-candidate"
    s.rollback()
    assert s.s["champion"] == "multisource-rf-v2"

    # A candidate deliberately broken only in an isolated fixture is automatically removed.
    a = s.info["assets"]
    s.s["versions"]["bad-candidate"] = {"artifact": {"weights": [0]*21, "bias": -25, "mean": a["mean"], "scale": a["scale"]},
                                          "evaluation": {"pass": True}, "threshold": s.s["settings"]["threshold"], "status": "Candidate"}
    s.s["candidate"] = "bad-candidate"
    s.start_canary()
    urls = [f"http://account-verify.example.xyz/login?trial={i}" for i in range(10)]
    s.analyze(urls)
    s.review([{"url": u, "label": 1, "evidence": "Synthetic rollback fixture, not real evidence", "reviewer": "Test"} for u in urls])
    assert s.s["canary"] is None and s.s["candidate"] is None
    assert s.s["versions"]["bad-candidate"]["status"] == "Rolled back"


def test_better_overall_canary_error_cannot_hide_new_false_warnings(client, monkeypatch):
    s = client.app.state.service
    s.s["canary"] = {"startedAt": "2026-01-01T00:00:00+00:00", "threshold": .9}
    s.s["candidate"] = "fixture"
    s.s["feedback"] = [{"x": [i], "y": int(i >= 10), "createdAt": now(), "prediction": {"time": now()}}
                           for i in range(20)]
    old = [0.] * 20  # Ten false negatives, no false warnings.
    new = [.99] + [0.] * 9 + [.99] * 10  # Better overall error, but one new legitimate-site warning.
    monkeypatch.setattr(s, "probabilities", lambda rows, version=None: new if version else old)
    evidence = s.canary_evidence()
    assert evidence["candidate"]["error"] < evidence["old"]["error"]
    assert not evidence["pass"]


def test_mlflow_sqlite_backend_can_store_a_real_run(tmp_path):
    from mlflow.tracking import MlflowClient
    tracker = MlflowClient(tracking_uri="sqlite:///" + (tmp_path / "tracking.db").as_posix())
    experiment = tracker.create_experiment("sqlite-integration", artifact_location=(tmp_path / "artifacts").as_uri())
    run = tracker.create_run(experiment)
    tracker.log_param(run.info.run_id, "scope", "isolated integration fixture")
    tracker.log_metric(run.info.run_id, "measured_value", .25)
    tracker.set_terminated(run.info.run_id)
    assert tracker.get_run(run.info.run_id).data.metrics["measured_value"] == .25
