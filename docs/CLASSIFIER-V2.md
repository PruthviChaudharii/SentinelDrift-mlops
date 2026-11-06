# Classifier v2: fixing the homepage-path shortcut

## What changed

The former PhiUSIIL-only model gave Chelsea's official `/en` URL a 95.98/100 score. Its legitimate examples were all root pages and all HTTPS, creating strong source shortcuts. A good score within that collection was not evidence of arbitrary-URL reliability.

The replacement adds real URL paths from PhreshPhish (Dalton et al.) and Hannousse & Yahiouche; it includes only a limited sample of PhiUSIIL. Only URL/label columns are downloaded; HTML and pages named by the datasets are never fetched. URLs are canonicalized and deduplicated, conflicting labels removed, and domains capped at 25 examples. Model splits use registrable domains from the bundled Public Suffix List, including private suffixes.

The model combines structural URL features with a learned character 3–5-gram TF-IDF logistic signal. A Random Forest uses that signal and structural features, excluding HTTPS itself. RF training receives group-out-of-fold text predictions; the text vocabulary is fitted only on training domains. The final text model and forest are exported for browser inference, with parity tests against Python/scikit-learn outputs. There is no runtime company allowlist, no Chelsea exception and no website-identity lookup.

## Data partitions and selection

- Training: 35,822 rows.
- Validation for model/threshold selection: 9,121 rows.
- Separate recovery governance pool: 5,747 rows (400 are bundled for local adaptive checks).
- Domain-disjoint development holdout: 8,772 rows.
- Additional development source evaluation: 15,772 rows.
- Fresh, frozen-candidate audit: 8,082 rows from additional PhreshPhish test shards, excluding all development domains and smoke-test domains. No audit-driven threshold adjustment was made.

The development holdouts were inspected during this repair, so they are not presented as untouched final tests. The separate audit records the exact model checksum, dataset commit, shard hashes and exclusions in `dist/classifier-audit.json`. Threshold was selected on validation only, targeting <=0.5% false positives while maximizing strong-warning phishing recall.

## Verdict policy

- Score <=20: **Lower URL risk**, not verified safe.
- Score >20 and <90: **Uncertain — verify independently**, not safe.
- Score >=90: **Strong phishing indicators**, not proof of maliciousness.

Scores are uncalibrated model outputs, not real-world phishing probabilities. Users cannot lower the strong-warning threshold below the validated floor; raising it can miss more phishing. Recovery evaluation uses the same effective threshold as serving. Old-model local state is retained under its previous key and can be exported in Settings; new inference, feature monitoring and adaptive weights start in a separate workspace.

## Results and limits

All 32 development official-domain regression pages, whose domains were excluded from model development data, scored below 20. Chelsea `/en`: 0.3124/100; Microsoft `/en-us/`: 0.5034; Apple `/in/`: 16.8522; Syngenta `/en`: 0.3619. These are deliberately selected regression checks, not an unbiased accuracy estimate or safety verification.

The fresh audit contained 4,085 legitimate and 3,997 phishing URLs. There were **11 false strong warnings** on legitimate URLs (0.269%; 95% Wilson interval approximately 0.150–0.482%). Strong warnings identified **51.94%** of phishing URLs at the conservative threshold. **372 phishing URLs still received lower-risk scores**, while other non-warned phishing examples fell into uncertainty. Both false negatives and abstentions matter; uncertainty must not be treated as permission to visit a URL. Research-source base rates differ from ordinary browsing, and precision is not guaranteed under deployment base rates.

The model still cannot guarantee that every official URL passes or that every phishing URL is detected. It does not inspect content, redirects, current compromise, certificates or reputation feeds. The purpose of this repair is to remove a demonstrated shortcut, improve measured false-positive behavior, and make uncertainty and evaluation limits visible.

## Reproduce

1. Install `requirements-training.txt` in an isolated Python environment; Node.js is also required.
2. `python scripts/download_data.py`
3. `python scripts/collect_external.py` (reads URL/label columns with HTTP ranges; no dataset HTML is executed or downloaded).
4. `python scripts/train_v2.py` writes the candidate to ignored `.cache-data/candidate-v2`.
5. `python scripts/regress_v2.py` and `python scripts/audit_v2.py` generate evidence. Audit files are a one-time frozen evaluation, not a tuning loop.
6. Copy the accepted candidate's model, model card and recovery-data files to `dist/`, and numerical parity fixtures to `tests/`; verify the model checksum still matches the audit.
7. `node --test tests/model.test.cjs tests/recovery.test.cjs tests/classifier.test.cjs`

The legacy `scripts/train.py` reproduces the previous baseline; do not use it to replace this release.

## Attribution

- PhreshPhish: https://huggingface.co/datasets/phreshphish/phreshphish — Dalton et al., CC BY 4.0, anti-phishing research. Pinned dataset revision and exported-column hashes are in the model card.
- Hannousse & Yahiouche: https://data.mendeley.com/datasets/c2gw7fy2j4/3 — CC BY 4.0; URL/status columns obtained from the attributed `pirocheto/phishing-url` mirror, pinned in the card.
- PhiUSIIL: https://archive.ics.uci.edu/dataset/967/phiusiil+phishing+url+dataset — Prasad & Chandra, CC BY 4.0.
- Public Suffix List: https://publicsuffix.org/list/ — Mozilla Public License 2.0; rules from tldextract's bundled snapshot are redistributed in the model for consistent grouping.
