# Current release: trained model and connected panels

This file describes v0.2. For the current reviewed-feedback, training and serving implementation, read [RECOVERY.md](RECOVERY.md). v0.3 adds actual browser-local adaptive training, reviewer-attested labels, independent evaluation and reversible serving; it does not claim external evidence verification or cloud model deployment.

Enter a URL once in URL analysis. The trained 48-tree Random Forest produces a score and assessment. The same URL, score, version and timestamp appear in monitoring and recovery. Analysis records a recovery assessment and audit event automatically; no extra refresh is required. Multiple open tabs on the same origin receive storage updates.

No fake traffic, attacks, candidates or deployments are used in the live workspace. After one URL, monitoring reports 1/30 distinct samples and recovery reports more traffic needed. After 30, the site computes PSI per feature against actual training histograms. A high PSI requests verified labels; it never silently treats predictions as labels or claims a performance improvement.

The settings risk threshold affects future model decisions. Legacy cooldown and canary percentage fields are reserved for future operations and do not change inference. The model registry shows actual offline benchmark metrics, not live accuracy. The CSV data screen validates a file but does not yet train on it.

Remaining: independently verified label ingestion, production performance evaluation, retraining, independent promotion gates, real canary serving, server-side shared history and automated recovery. The old WEBSITE.md documents the preceding simulation release.
