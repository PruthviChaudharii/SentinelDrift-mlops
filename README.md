# SentinelDrift — Autonomous Self-Healing MLOps Platform

A browser-local research workspace for URL assessment, measured feature drift, reviewed feedback, adaptive training, independent gates, actual canary inference and reversible model promotion. No shared cloud model fleet or unattended scheduler is claimed.

## Persistent local MLOps stack (v0.5)

The same website now supports a separate **persistent server** mode at http://localhost:8000, with FastAPI, SQLite, DVC data snapshots/pipelines, MLflow experiment tracking, Docker Compose, Airflow recovery scheduling, Prometheus/Grafana and on-demand numeric-model SHAP explanations. Run `powershell -ExecutionPolicy Bypass -File scripts/start.ps1` with Docker Desktop running. See [setup, controls and honest limits](docs/LOCAL-MLOPS.md).

The hosted static Site retains its browser-local mode; it does not run these containers. The following browser-local description still applies there. AWS SageMaker is excluded. Server recovery trains the same real residual correction rather than rebuilding the forest; sufficient independent reviews and passing gates remain required.

## Current classifier (v0.4)

The former homepage-only baseline has been replaced with `multisource-rf-v2`: a Random Forest using structural features and learned character-level URL-text evidence. It is trained on multiple attributed research sources and evaluated with registrable-domain separation. HTTPS alone is excluded from RF splits. No company allowlist or Chelsea exception is used.

Results use three bands: **Lower URL risk**, **Uncertain — verify independently**, and **Strong phishing indicators**. None verifies website identity or safety. Scores are not calibrated probabilities. The conservative policy reduces false strong warnings but misses some phishing; the interface reports this tradeoff explicitly.

Read [classifier repair, audit, limits and reproduction](docs/CLASSIFIER-V2.md). The [model card](dist/model-card.json), [frozen-model audit](dist/classifier-audit.json) and [official-domain regressions](dist/official-regressions.json) contain measured evidence. The audit found 11 false warnings among 4,085 legitimate URLs (0.269%), 51.94% strong-warning phishing recall, and 372 phishing URLs assigned lower risk. This is research evidence, not an arbitrary-URL guarantee.

## Run and test

Run `python -m http.server 8173 --bind 127.0.0.1 --directory dist` and open http://127.0.0.1:8173. No frontend build or Python model server is required for browser inference.

Run `node --test tests/model.test.cjs tests/recovery.test.cjs tests/classifier.test.cjs` for artifact parity, official-path regressions, normalization, three-way verdicts, grouping, frozen-audit integrity, actual learning, rejection, promotion, rollback and persistence. Legacy `tests/workflow.test.cjs` tests the earlier simulation helpers only.

## Recovery and state

One URL submission updates analysis, overview, monitoring, recovery and audit. Feature PSI compares the latest 200 distinct URLs to training reference histograms after a minimum of 30 URLs; this minimum is not statistical assurance. Batch shift is not individual-link danger.

Reviewer-attested feedback includes a label, evidence reference and reviewer ID. The site cannot authenticate reviewers or independently verify their evidence. Adaptive training learns a logistic residual correction on the frozen baseline; it does not rebuild RF trees or the text model. Training and governance records are separated. See [recovery policy and limits](docs/RECOVERY.md).

Version 2 inference uses a separate browser storage key so old feature vectors and adaptive weights are not silently reused. Settings can export previous-model history; it has not been deleted. Tabs share state notifications, but this remains a single-writer local workspace, not a multi-user backend. Raw training URLs and HTML are not published; only trained parameters, numeric recovery pools and public-domain regression examples are included.

## Sources

- [PhreshPhish](https://huggingface.co/datasets/phreshphish/phreshphish), Dalton et al., CC BY 4.0, anti-phishing research.
- [Web page phishing detection](https://data.mendeley.com/datasets/c2gw7fy2j4/3), Hannousse & Yahiouche, CC BY 4.0.
- [PhiUSIIL](https://archive.ics.uci.edu/dataset/967/phiusiil+phishing+url+dataset), Prasad & Chandra, CC BY 4.0.
- [Public Suffix List](https://publicsuffix.org/list/), MPL 2.0, bundled via tldextract for consistent grouping.

Old `scripts/train.py` and earlier scope documents reproduce prior releases; use the current classifier guide for v0.4.
