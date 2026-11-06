import os
import time
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, StringConstraints
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

from .engine import ROOT
from .service import Service

URLString = Annotated[str, StringConstraints(min_length=8, max_length=4096)]


class Analysis(BaseModel):
    urls: list[URLString] = Field(min_length=1, max_length=50)


class Review(BaseModel):
    url: URLString
    label: Literal[0, 1]
    evidence: str = Field(min_length=8, max_length=500)
    reviewer: str = Field(min_length=2, max_length=80)
    attested: Literal[True]


class Reviews(BaseModel):
    records: list[Review] = Field(min_length=1, max_length=1000)


class Policy(BaseModel):
    threshold: float = Field(ge=.9, le=.99)
    canary: int = Field(ge=1, le=50)
    cooldown: int = Field(ge=0, le=1440)
    enabled: bool
    auto: bool


class Explanation(BaseModel):
    prediction_id: str


def create_app(directory=None, tracking_uri=None):
    registry = CollectorRegistry()
    requests = Counter("sentinel_http_requests", "HTTP requests", ["method", "route", "status"], registry=registry)
    latency = Histogram("sentinel_http_seconds", "API request duration", ["route"], registry=registry)
    total = Gauge("sentinel_predictions_total_saved", "Persistent count of predictions", registry=registry)
    reviews = Gauge("sentinel_reviewed_labels", "Attested reviewed labels", registry=registry)
    error = Gauge("sentinel_reviewed_error_ratio", "Reviewed champion error; -1 when unavailable", registry=registry)
    drift = Gauge("sentinel_feature_psi", "Current window PSI", ["feature"], registry=registry)
    version = Gauge("sentinel_serving_model", "Current serving version", ["version"], registry=registry)
    jobs = Gauge("sentinel_recovery_jobs", "Persisted jobs by outcome", ["status"], registry=registry)

    @asynccontextmanager
    async def lifespan(app):
        app.state.service = Service(directory, tracking_uri)
        if os.environ.get("REGISTER_BASELINE") == "true":
            try:
                app.state.service.register_baseline()
            except Exception as exc:
                app.state.service.event("Baseline evidence import failed", str(exc))
                app.state.service.persist()
        yield
        app.state.service.close()

    app = FastAPI(title="SentinelDrift persistent MLOps API", version="0.5.0", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "api", "testserver"])

    @app.middleware("http")
    async def measurement(request: Request, call_next):
        # Loopback-only deployment; reject cross-site writes even though reads are not CORS-enabled.
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin and origin != str(request.base_url).rstrip("/"):
            return Response("Cross-origin writes are disabled", status_code=403)
        started = time.perf_counter()
        response = await call_next(request)
        route = getattr(request.scope.get("route"), "path", "static-or-unmatched")
        requests.labels(request.method, route, response.status_code).inc()
        latency.labels(route).observe(time.perf_counter() - started)
        return response

    def service():
        return app.state.service

    def attempt(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/health")
    def health():
        if service().engine.process.poll() is not None:
            raise HTTPException(503, "Classifier worker is unavailable")
        return {"status": "ok", "scope": "persistent-server", "model": service().info["id"], "version": "0.5.0"}

    @app.get("/api/state")
    def state():
        return service().state()

    @app.post("/api/analyze")
    def analyze(body: Analysis):
        return {"predictions": attempt(service().analyze, body.urls)}

    @app.post("/api/feedback")
    def feedback(body: Reviews):
        return {"accepted": attempt(service().review, [r.model_dump() for r in body.records])}

    @app.post("/api/recovery/train")
    def train():
        return service().train()

    @app.get("/api/recovery/check")
    def check():
        with service().lock:
            return {"readiness": service().readiness(), "degradation": service().degradation()}

    @app.post("/api/recovery/tick")
    def tick():
        with service().lock:
            service().check_canary()
            service().persist()
            return service().train(automatic=True)

    @app.post("/api/recovery/{operation}")
    def operate(operation: Literal["canary", "promote", "rollback", "discard"]):
        s = service()
        if operation == "discard":
            with s.lock:
                if not s.s["candidate"] or s.s["canary"]:
                    raise HTTPException(400, "A candidate outside canary is required")
                s.s["versions"][s.s["candidate"]]["status"] = "Discarded"
                s.s["candidate"] = None
                s.event("Candidate discarded", "Operator requested a fresh evaluation")
                s.persist()
        else:
            attempt({"canary": s.start_canary, "promote": s.promote, "rollback": s.rollback}[operation])
        return {"status": "ok"}

    @app.put("/api/settings")
    def settings(body: Policy):
        if body.threshold < service().info["policy"]["high"]:
            raise HTTPException(400, "Threshold cannot be below the validated baseline floor")
        attempt(service().settings, body.model_dump())
        return {"status": "ok"}

    @app.get("/api/export")
    def export():
        return service().state()

    @app.post("/api/explain")
    def explain(body: Explanation):
        # Keep serving version and artifact fixed throughout the explanation.
        import numpy as np
        import shap
        s = service()
        with s.lock:
            row = next((p for p in s.s["predictions"] if p["id"] == body.prediction_id), None)
            if row is None:
                raise HTTPException(404, "Prediction not found")
            model = __import__("json").loads((ROOT / "dist/model.json").read_text(encoding="utf-8"))
            active = {i for tree in model["trees"] for i in tree["feature"] if i >= 0}
            artifact = s.artifact(row["model"])
            if artifact:
                active.update(i for i, weight in enumerate(artifact["weights"]) if weight != 0)
            active = sorted(active)
            background = np.array([r["x"] for r in s.info["assets"]["replay"]][::20])[:, active]
            def predict(values):
                full = np.tile(np.array(row["features"]), (len(values), 1))
                full[:, active] = np.asarray(values)
                return np.array(s.probabilities(full.tolist(), row["model"]))
            explainer = shap.KernelExplainer(predict, background, link="identity")
            active_values = np.asarray(explainer.shap_values(np.array([row["features"]])[:, active], nsamples=256, l1_reg=0)).reshape(-1)
            values = np.zeros(len(s.info["names"]))
            values[active] = active_values
            return {"model": row["model"], "score": row["score"] / 100,
                    "expected_value": float(explainer.expected_value),
                    "features": [{"name": name, "value": row["features"][i], "contribution": float(values[i])}
                                 for i, name in enumerate(s.info["names"])],
                    "scope": "Approximate Kernel SHAP on the complete numeric serving model, including adaptive correction. The learned text score is one input; this does not explain individual URL characters. Perturbed feature combinations can be unrealistic. Contributions describe model behavior, not website safety."}

    @app.get("/metrics")
    def monitoring():
        s = service().state()
        total.set(s["requests"])
        reviews.set(len(s["feedback"]))
        e = s["degradation"]["observed"]["error"]
        error.set(e if e is not None else -1)
        drift.clear()
        for feature in s["drift"]["features"]:
            drift.labels(feature["name"]).set(feature["psi"])
        version.clear()
        version.labels(s["champion"]).set(1)
        jobs.clear()
        for status in {j["status"] for j in s["jobs"]}:
            jobs.labels(status).set(sum(j["status"] == status for j in s["jobs"]))
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def website():
        html = (ROOT / "dist/index.html").read_text(encoding="utf-8")
        return HTMLResponse(html.replace("<head>", "<head><script>window.SENTINEL_SERVER_MODE=true;</script>", 1))

    app.mount("/", StaticFiles(directory=ROOT / "dist", html=True), name="website")
    return app


app = create_app()
