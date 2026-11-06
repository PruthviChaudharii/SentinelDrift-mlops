# Reviewed-data recovery — v0.3

This release provides actual browser-local adaptive training and serving, not cloud model deployment. Treat this as a single-writer research workspace, not a production multi-user platform. Data and model versions persist in the browser; export evidence before clearing storage. No external phishing-label authority is connected.

## Workflow

1. Analyze URLs. Each saved prediction retains its model version, decision threshold and time.
2. Data workspace → Save reviewed label, or import a CSV with `url,label,evidence,reviewer`. Independent review attestation and evidence references are mandatory. The application records them; it cannot authenticate the reviewer or verify the evidence. Do not use the model's own output as ground truth.
3. URL hostname groups deterministically assign feedback to training or validation. Historical gate groups are always validation. Labels are locked per exact URL. Duplicate imports reject the entire batch. At least 20 training and 10 validation URLs with both classes are required.
4. Observed error is computed from pre-review predictions served by the current champion only. At least 30 labeled predictions and error > max(15%, historical gate error + 5 percentage points) qualify as degradation under the prototype policy. This is an operational trigger, not a significance test.
5. With automatic mode and recovery policy enabled, qualifying new feedback starts training after cooldown. Manual Train & evaluate can also start an eligible job without degradation. Training fits a logistic residual correction on top of the frozen RF, using 400 historical replay examples and reviewed training data weighted 5x. It does not rebuild RF trees. Optimization loss and learned weights are real.
6. Gates compare the fitted candidate and champion on a separate 400-row historical gate and held-out recent validation groups. F1 on history may drop at most 0.02; recent error must strictly improve and F1 must not fall; historical FNR must stay within max(8%, champion FNR + 2 percentage points). Failure leaves serving unchanged.
7. Automatic mode starts a real local canary for passed candidates. A random configured share of subsequent URL requests executes the candidate classifier. Saved predictions record the served version. All new reviewed observations are also scored against both models for paired evaluation; these are not artificial traffic.
8. After 10 new reviewed observations, candidate error > champion error + 5 percentage points triggers rollback. At least 20 new reviewed observations with both classes, error no worse than champion and FNR <= max(10%, champion FNR) permit promotion. Automatic mode promotes; manual mode enables the Promote button.
9. Promotion changes the artifact used by subsequent analysis requests and retains the previous champion. Rollback actually restores the prior serving artifact; reloads preserve the selected version. Policy threshold changes during canary cancel it.

## Evaluation limits

The historical governance pool is taken from the original RF holdout, so its baseline score is no longer an untouched final test for adaptive models. Repeated validation can overfit selection. Splits use last-two-hostname-label groups (heuristic, not Public Suffix List); duplicate campaigns across unrelated domains are not necessarily removed. Minimum counts and canary gates are small-sample prototype controls, not production assurance. Labels are human-attested, not independently verified by the application. All operations require the website to be open; no unattended cloud scheduler or shared API fleet is claimed.

## Evidence and tests

Recovery → Export evidence downloads reviewed records, partition assignments, model weights, optimization loss, gate results, jobs and canary state. The ordinary workspace export also includes recovery state. Exports currently have no restore/import-model operation.

Run `node --test tests/model.test.cjs tests/recovery.test.cjs`. Tests cover independent data pools, learned parameters, validation-label exclusion from training, rejection, reviewer validation, real canary classifier selection, evidence-based promotion blocking, automatic rollback, automatic training and persistence. Synthetic unit-test fixtures are not loaded as production feedback.
