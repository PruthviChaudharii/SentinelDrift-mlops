# SentinelDrift — Autonomous Self-Healing MLOps Platform

From-scratch rebuild for malicious URL defense. The current release runs an actual trained Random Forest in the browser. A submitted URL updates analysis, overview, monitoring, recovery assessment, and audit together.

Run `python -m http.server 8173 --bind 127.0.0.1 --directory dist` and open http://127.0.0.1:8173.

**Current scope (v0.3):** real URL inference, measured PSI, reviewer-attested feedback, measured errors, actual adaptive training, independent gates, random canary inference, promotion and rollback, all in a browser-local workspace. Adaptive training fits a logistic residual on the frozen Random Forest; it does not rebuild RF trees. Evidence is reviewer-attested, not automatically verified. No shared cloud model fleet or unattended scheduler is claimed. See [recovery guide and limits](docs/RECOVERY.md).

`app.js` contains legacy UI helpers; `live.js` replaces the prior simulation with real inference and monitoring; `operations.js` connects reviewed feedback and actual recovery operations. The old simulation actions remain disabled. `recovery-engine.js` contains the testable learning and evaluation implementation.

Run `node --test tests/model.test.cjs tests/recovery.test.cjs` for model parity, synchronized state, sample gating, PSI, data separation, actual training, measured errors, automatic recovery, canary selection, promotion, rollback and persistence. `tests/workflow.test.cjs` tests the older simulation helpers only.

## Training and attribution

Source: [UCI PhiUSIIL, Prasad & Chandra](https://archive.ics.uci.edu/dataset/967/phiusiil+phishing+url+dataset), CC BY 4.0. Original labels are inverted so phishing=1. Raw URLs are not included in the published model or test fixtures. We sample 80,000 unique URLs deterministically, extract 20 URL-only features through the same JavaScript extractor used in serving, and split by hostname last-two-label groups. This grouping is a heuristic rather than a Public Suffix List split. No exact group overlaps the holdout. No temporal generalization is claimed.

The checked-in [model card](dist/model-card.json) records metrics and dataset checksum. Held-out F1 is 0.96696; this historical dataset has collection bias and does not establish production performance. Model scores are not calibrated probabilities. The model never opens submitted links or inspects web page content.

To reproduce: install the pinned training dependencies in an isolated environment, then run `python scripts/download_data.py` and `python scripts/train.py` from the repository root. Node.js is also required. Training writes the serving artifact, model card and 50 numerical parity fixtures.

Browser history is retained locally (latest 500 predictions). PSI uses the latest 200 distinct URL strings, quantile-derived training reference bins and additive smoothing; the minimum of 30 is an operational guardrail, not a statistical guarantee. Reloaded browser tabs share updates through storage events. Clearing old demo data is not required: this release uses a new workspace storage key.
