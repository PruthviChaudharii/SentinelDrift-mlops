# SentinelDrift — Autonomous Self-Healing MLOps Platform

From-scratch rebuild for malicious URL defense. The first release is a functional demonstration website with eight connected screens: overview, URL analysis, monitoring, recovery, registry, data validation, audit and settings.

Run `python -m http.server 8173 --bind 127.0.0.1 --directory dist` and open http://127.0.0.1:8173.

**Current scope:** browser-local workflow simulation and transparent lexical URL rules. No trained ML backend or production deployment engine is connected. Simulated metrics are labeled throughout the website.

See [website guide and backend roadmap](docs/WEBSITE.md). Run `node --test tests/workflow.test.cjs` to verify the demo lifecycle.
