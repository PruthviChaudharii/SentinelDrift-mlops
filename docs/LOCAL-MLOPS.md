# Running the persistent prototype (v0.5)

AWS SageMaker is deliberately excluded. Keep the beige website and audited baseline classifier.

## Start on this Windows computer

1. Open **Docker Desktop** and wait until the engine is running. It was already running during setup.
2. Open PowerShell in this repository and run `powershell -ExecutionPolicy Bypass -File scripts/start.ps1`.
3. Open **http://localhost:8000**. The header must say **Persistent server**.

The first build downloads images and Python packages. Later starts reuse them. Python, Node, MLflow, SHAP and Airflow dependencies are inside the containers; no separate manual installation is needed for the Docker demo. This machine's Docker engine reported roughly 8 GB of available RAM. Close unneeded applications if the full stack is slow.

Container versions are pinned: Python 3.11, Node 22, MLflow 2.22, Airflow 3.3.0, Grafana 13.2.3 and Prometheus 3.15.0. Monitoring/orchestration images use immutable digests. Python transitive versions are in `requirements.lock`; regenerate with `uv pip compile requirements.txt -c constraints.txt --universal -o requirements.lock`. The compatibility constraint prevents a tested DVC/pathspec import failure.

| Page | Address | Purpose |
| --- | --- | --- |
| Main website | http://localhost:8000 | Analyze URLs, submit checked feedback and operate recovery |
| API documentation | http://localhost:8000/docs | Inspect and call the real REST endpoints |
| MLflow | http://localhost:5000 | Training parameters, dataset hashes, metrics, evaluation and residual artifacts |
| Grafana | http://localhost:3000/d/sentineldrift | Live API and model-operation dashboard; local anonymous read-only access |
| Prometheus | http://localhost:9090/targets | Confirm that the API metrics target is UP |
| Airflow | http://localhost:8080 | Independently scheduled recovery checks every five minutes |

Airflow standalone creates an `admin` account and a generated local password. Retrieve it with:

```powershell
docker compose exec airflow cat /opt/airflow/simple_auth_manager_passwords.json.generated
```

This is a local development stack: all exposed ports bind to loopback. It has no multi-user authentication or internet deployment. The public/private hosted static Site remains browser-local; it cannot run these Python containers or automatically connect to a visitor's localhost server. Use the local website for the complete MLOps demo.

On its first successful start, the API imports the existing audited baseline artifact and measurements into the MLflow **SentinelDrift-baseline-evidence** experiment. That run is explicitly tagged as an evidence import, not new training. Actual recovery optimization creates separate runs in **SentinelDrift-reviewed-recovery**.

Stop the services with `powershell -ExecutionPolicy Bypass -File scripts/stop.ps1`. This preserves named volumes. Closing the browser does not stop Airflow. Closing Docker Desktop stops container operation. Do not use `docker compose down -v` unless you intend to delete stored databases and history.

## What each website control does

- **Analyze link:** validates up to 50 HTTP(S) URLs, computes the exact existing features/model and stores prediction-time scores, threshold and serving version in SQLite. Submitted URLs are never opened or fetched.
- **Explain latest result:** runs approximate Kernel SHAP against the saved prediction's numeric serving model, including any adaptive correction. Positive contributions raise the score; negative ones lower it. This does not explain individual URL characters or verify site identity. Feature perturbations may be unrealistic.
- **Save checked label / Import reviewed labels:** records independently reviewed legitimate/phishing labels, reviewer and evidence reference. Duplicate canonical URLs are locked; there is no reviewer authentication or independent evidence verification.
- **Train & evaluate:** manually requests real residual-logistic optimization, with historical replay and independent validation gates. It needs at least 20 training and 10 separate validation URLs, with both classes in each. MLflow failure makes the job fail; an untracked candidate cannot deploy.
- **Start canary:** routes the configured random share of actual new requests to a passed candidate.
- **Promote:** needs 20 fresh reviewed trial observations, both classes and passing paired error/FNR checks. It changes the actual persisted serving champion.
- **Rollback:** cancels a canary or restores the previous champion. Excess canary error triggers automatic rollback after at least 10 new reviewed observations.
- **Discard candidate:** removes a candidate awaiting canary; another training/evaluation run is then required.
- **Refresh:** reads the current backend state.
- **Export evidence:** downloads actual stored predictions, reviews, jobs, model artifacts and audit events. It can contain submitted URLs and reviewer-entered text; inspect before sharing.
- **Download CSV:** exports saved prediction results.
- **Save server policy:** controls threshold, canary share, cooldown, recovery enablement and automatic operation. The tested warning threshold floor cannot be lowered.
- **Load examples:** fills the input; it does not create traffic until Analyze is clicked.

## Actual recovery policy

Airflow inspects feedback and calls the server's atomic recovery policy every five minutes. Automatic training needs: enabled policy, automatic mode, no outstanding candidate/canary, expired cooldown, sufficient train/validation labels, and at least 30 previously scored champion predictions whose reviewed error exceeds `max(15%, governance error + 5 percentage points)`.

Feature PSI alone never starts training. Low/moderate/high shift describe batch distribution changes, not individual URL danger. The monitoring window is the latest 200 distinct retained URLs, with a 30-URL reporting minimum.

Training learns 21 residual weights plus bias over the frozen RF/text baseline (240 optimization epochs). It is not a full forest rebuild. Domain-group separation and governance exclusions reuse the tested engine. Historical F1, recent validation improvement, historical false-negative and false-positive guards must pass. Recent false-positive rate cannot increase; the historical FPR limit is max(0.5%, champion FPR + 0.25 percentage points). A separate 32-URL official-domain development regression suite must remain in the lower-risk band. It is a regression guard, not a random or untouched safety evaluation. A passing automatic job starts a real canary. New review evidence can automatically promote or roll it back. Promotion also forbids additional false warnings on reviewed legitimate trial URLs; at least five legitimate reviews are needed for the dedicated automatic false-warning rollback check. Small sample counts are demo guardrails, not production statistical confidence.

SQLite and artifact metadata live in the `workspace` Docker volume. API runs with **one worker**; the process lock and SQLite transaction serialize state changes. This prototype is not a horizontally scaled service.

## DVC data versions and reproducibility

The existing baseline inputs are snapshotted to `data/training-sources/`, tracked by a `.dvc` pointer. `checksums.json` records SHA-256 per file. The raw URLs are not tracked in Git or copied into the static website. DVC's local storage remote is configured only on this computer; teammates need a shared approved storage remote or a copy of these data objects.

To export a new version of actual feedback and reproduce its adaptive-training evaluation, activate Python 3.11 `.venv` (already prepared on this computer), then:

```powershell
.venv/Scripts/Activate.ps1
python scripts/export_reviews.py
dvc add data/reviewed.json
dvc repro
dvc push
git add data/reviewed.json.dvc dvc.lock
```

The initial reviewed dataset is deliberately empty. DVC completes feature generation and records a training/evaluation **skip**; it does not fabricate labels. Once sufficiently reviewed feedback is exported, the same pipeline trains and evaluates a real candidate. Offline DVC reproduction compares against the frozen baseline and does not deploy anything. Server training separately records each actual parent, immutable local snapshot hash and MLflow run.

The original baseline can be reproduced with `scripts/train_v2.py` and `requirements-training.txt` using its documented source cache. Restoring `data/training-sources/` from DVC provides those exact inputs; copy them into `.cache-data/` first. See CLASSIFIER-V2.md for attribution, splits and untouched audit details. Re-training a baseline is not permission to overwrite the served artifact without a new audit.

## Validation

```powershell
node --test tests/model.test.cjs tests/recovery.test.cjs tests/classifier.test.cjs
.venv/Scripts/python.exe -m pytest tests/test_backend.py -q
docker compose config --quiet
```

Backend tests use isolated temporary databases and synthetic fixtures explicitly marked as tests; they never seed the live workspace. They check parity, atomic validation, persistence, label locking, real tracked optimization, rejection/promotion guards, actual candidate routing, rollback, SHAP reconstruction and metrics.

GitHub Actions runs those checks and a Linux container health smoke test. It builds a deployable image but does not claim an unattended cloud deployment. Local delivery is `scripts/start.ps1`. No AWS credentials or services are needed.
