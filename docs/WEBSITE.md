# SentinelDrift website — release 0.1

The current release is a functional, responsive **demonstration website**, not a production ML platform.

## Local setup

Run `python -m http.server 8173 --bind 127.0.0.1 --directory dist` and open http://127.0.0.1:8173. No build step is required.

## Working screens

- Overview: metrics, chart window controls, traffic generation and report export.
- URL analysis: batch HTTP/HTTPS validation, transparent lexical risk scoring, explanations, CSV history export.
- Drift monitoring: normal and attack-wave scenarios with explicitly simulated shift indicators.
- Recovery: no-action decision, successful and failed gates, cooldown and policy enforcement.
- Model registry: canary observations, promotion, rollback and version details.
- Data workspace: CSV parsing, schema, label, URL and duplicate checks; validation history.
- Audit: searchable event history and JSON export.
- Settings: persistent parameters, workspace export and reset.

## Walkthrough

1. Drift monitoring → Inject attack wave.
2. Recovery → Run failure scenario. Observe rejection and unchanged champion.
3. Run recovery → passed candidate → Start canary.
4. Observe 100 requests → Promote candidate.
5. Rollback → original champion restored.
6. Analyze URLs and validate a small `url,label` CSV.

All state is browser-local. The scorer does not fetch URLs. Metrics, models, traffic and deployments are deterministic simulations, labeled in the UI. CSV files are processed locally; only validation summaries are retained. This is single-browser state, not a shared database. No trained artifact, real monitoring, production authentication or training backend is included.

## Next backend milestones

1. Python 3.11 / uv locked environment; real dataset provenance and immutable split manifests.
2. Independent training, tuning, promotion-validation and untouched final evaluation; deduplication by URL/domain/campaign as available.
3. RF/XGBoost static and scheduled-retraining baselines; MLflow tracking and registry.
4. FastAPI prediction and verified feedback; PostgreSQL prediction and audit state.
5. Statistical monitoring plus performance measurements from delayed labels; drift alone is not concept drift.
6. Prefect recovery jobs, idempotency, budgets, cooldown and independent gates.
7. Shadow/canary serving, persistent promotion and rollback tied to exact model and threshold artifacts.
8. Docker/CI deployment, Prometheus/Grafana, measured accuracy, recovery time, false alarms and compute cost.

Sites hosting identity in `.openai/hosting.json` is not a credential. Never commit credentials or raw datasets.
