"""Single-process, persistent local MLOps service. No submitted URL is fetched."""
import hashlib
import json
import math
import os
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .engine import Engine, ROOT


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def metrics(rows, probabilities, threshold):
    tp = tn = fp = fn = 0
    for row, probability in zip(rows, probabilities):
        flag = probability >= threshold
        tp += int(flag and row["y"] == 1)
        fp += int(flag and row["y"] == 0)
        tn += int(not flag and row["y"] == 0)
        fn += int(not flag and row["y"] == 1)
    return {"n": len(rows), "error": (fp + fn) / len(rows) if rows else None,
            "fnr": fn / (tp + fn) if tp + fn else None, "tp": tp, "tn": tn, "fp": fp, "fn": fn}


class Service:
    def __init__(self, directory=None, tracking_uri=None):
        self.directory = Path(directory or os.environ.get("SENTINEL_DATA", ROOT / "runtime"))
        self.directory.mkdir(parents=True, exist_ok=True)
        self.engine = Engine()
        self.info = self.engine.call("info")
        self.base_sha256 = hashlib.sha256((ROOT / "dist/model.json").read_bytes()).hexdigest()
        self.lock = threading.RLock()
        self.tracking_uri = tracking_uri or os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")
        self.db = sqlite3.connect(self.directory / "workspace.sqlite", check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS workspace (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        row = self.db.execute("SELECT value FROM workspace WHERE id=1").fetchone()
        self.s = json.loads(row[0]) if row else {
            "schema": 1, "base": self.info["id"], "champion": self.info["id"],
            "candidate": None, "previous": None, "canary": None, "versions": {},
            "predictions": [], "feedback": [], "events": [], "jobs": [], "requests": 0,
            "settings": {"threshold": self.info["policy"]["high"], "canary": 10,
                         "cooldown": 30, "enabled": True, "auto": True}, "last_attempt": None,
        }
        if self.s["base"] != self.info["id"] or self.s.get("base_sha256", self.base_sha256) != self.base_sha256:
            self.close()
            raise RuntimeError("Database baseline mismatch; migrate explicitly before serving")
        self.s["base_sha256"] = self.base_sha256
        self.persist()

    def close(self):
        self.engine.close()
        self.db.close()

    def persist(self):
        self.db.execute("INSERT OR REPLACE INTO workspace VALUES (1,?)", (json.dumps(self.s),))
        self.db.commit()

    def event(self, title, detail):
        self.s["events"].insert(0, {"time": now(), "title": title, "detail": detail, "id": uuid.uuid4().hex})
        self.s["events"] = self.s["events"][:2000]

    def artifact(self, version):
        return self.s["versions"].get(version, {}).get("artifact")

    def probabilities(self, rows, version=None):
        return self.engine.call("predict", rows=rows, artifact=self.artifact(version or self.s["champion"]))

    def analyze(self, urls):
        with self.lock:
            rows = self.engine.call("features", urls=urls)  # Validate entire batch before any writes.
            results = []
            for row in rows:
                version = self.s["champion"]
                canary = self.s["canary"]
                if canary:
                    canary["requests"] += 1
                    if secrets.randbelow(100) < canary["weight"]:
                        version = self.s["candidate"]
                        canary["candidate_requests"] += 1
                score = self.probabilities([row["x"]], version)[0]
                high = self.s["settings"]["threshold"]
                p = {"id": uuid.uuid4().hex, "url": row["url"], "features": row["x"],
                     "score": score * 100, "flag": score >= high, "threshold": high * 100,
                     "model": version, "time": now(), "servedBy": "candidate" if version == self.s["candidate"] else "champion",
                     "signals": [f"{self.info['names'][i]}: {row['x'][i]:.3f}" for i in
                                 sorted(range(len(row["x"])), key=lambda j: self.info["importances"][j], reverse=True)[:5]],
                     "caution": row.get("caution")}
                self.s["predictions"].insert(0, p)
                self.s["requests"] += 1
                results.append(p)
            self.s["predictions"] = self.s["predictions"][:10000]
            self.event("URLs analyzed", f"{len(results)} real server predictions; links were not opened.")
            self.persist()
            return results

    def review(self, records):
        with self.lock:
            if len(self.s["feedback"]) + len(records) > 5000:
                raise ValueError("Workspace limit is 5,000 reviewed URLs")
            rows = self.engine.call("features", urls=[r["url"] for r in records])
            seen = {r["url"] for r in self.s["feedback"]}
            pending = []
            for record, row in zip(records, rows):
                if type(record["label"]) is not int or record["label"] not in (0, 1):
                    raise ValueError("Label must be the integer 0 or 1")
                if len(record["evidence"].strip()) < 8 or len(record["reviewer"].strip()) < 2:
                    raise ValueError("A meaningful evidence reference and reviewer name are required")
                if row["url"] in seen:
                    raise ValueError("This canonical URL already has a locked review")
                seen.add(row["url"])
                observed = next((p for p in self.s["predictions"] if p["url"] == row["url"]), None)
                pending.append({**row, "id": uuid.uuid4().hex, "y": record["label"],
                                "evidence": record["evidence"], "reviewer": record["reviewer"], "createdAt": now(),
                                "prediction": observed})
            self.s["feedback"].extend(pending)
            self.event("Reviewed feedback saved", f"{len(pending)} attested labels. Evidence authenticity is not independently verified.")
            self.check_canary()
            self.persist()
            return len(pending)

    def performance(self):
        rows = [r for r in self.s["feedback"] if r["prediction"] and r["prediction"]["model"] == self.s["champion"]]
        return metrics(rows, [1.0 if r["prediction"]["flag"] else 0.0 for r in rows], .5)

    def readiness(self):
        return self.engine.call("ready", feedback=self.s["feedback"])

    def degradation(self):
        p = self.performance()
        # Compare against the same serving model and threshold on governance rows.
        gate = self.info["assets"]["historical_gate"]
        historical = metrics(gate, self.probabilities([r["x"] for r in gate]), self.s["settings"]["threshold"])
        limit = max(.15, historical["error"] + .05)
        return {"confirmed": p["n"] >= 30 and p["error"] > limit, "minimum": 30,
                "error_limit": limit, "observed": p}

    def drift(self):
        rows = list({p["url"]: p for p in reversed(self.s["predictions"])}.values())
        rows.sort(key=lambda p: p["time"], reverse=True)
        rows = rows[:200]
        if len(rows) < 30:
            return {"ready": False, "count": len(rows), "features": [], "status": "Collecting traffic"}
        features = []
        for j, ref in enumerate(self.info["reference"]):
            counts = [0] * len(ref["counts"])
            for row in rows:
                index = sum(row["features"][j] >= edge for edge in ref["edges"])
                counts[index] += 1
            n = len(counts)
            psi = 0
            for a, b in zip(ref["counts"], counts):
                a = (a + .5) / (sum(ref["counts"]) + .5 * n)
                b = (b + .5) / (len(rows) + .5 * n)
                psi += (b - a) * math.log(b / a)
            features.append({"name": self.info["names"][j], "psi": psi})
        high = sum(f["psi"] > .25 for f in features)
        return {"ready": True, "count": len(rows), "features": features, "high": high,
                "mean": sum(f["psi"] for f in features) / len(features),
                "status": "Distribution shift detected" if high else "No high feature shift"}

    def snapshot(self):
        payload = {"base": self.info["id"], "base_sha256": self.base_sha256, "feedback": self.s["feedback"]}
        sha = digest(payload)
        folder = self.directory / "snapshots"
        folder.mkdir(exist_ok=True)
        path = folder / f"{sha}.json"
        if not path.exists():
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return sha, path

    def register_baseline(self):
        """Import measured existing evidence; explicitly not a new training run."""
        if self.s.get("baseline_evidence_run"):
            return
        import mlflow
        mlflow.set_tracking_uri(self.tracking_uri)
        mlflow.set_experiment("SentinelDrift-baseline-evidence")
        card = json.loads((ROOT / "dist/model-card.json").read_text(encoding="utf-8"))
        with mlflow.start_run(run_name="Imported audited multisource-rf-v2") as run:
            mlflow.set_tags({"run_type": "existing-baseline-evidence-import", "new_training_performed": "false"})
            mlflow.log_params({"model_id": self.info["id"], "training_rows": card["train_rows"],
                               "feature_count": len(self.info["names"]),
                               "model_sha256": hashlib.sha256((ROOT / "dist/model.json").read_bytes()).hexdigest()})
            mlflow.log_metrics({"holdout_" + k: float(card["metrics"][k]) for k in ("f1", "precision", "recall", "fpr", "fnr")})
            for name in ("model.json", "model-card.json", "classifier-audit.json"):
                mlflow.log_artifact(str(ROOT / "dist" / name), "baseline")
            self.s["baseline_evidence_run"] = run.info.run_id
        self.event("Baseline evidence imported into MLflow", "Existing audited classifier and metrics registered; no new training is claimed.")
        self.persist()

    def train(self, automatic=False):
        with self.lock:
            if not self.s["settings"]["enabled"]:
                return {"status": "skipped", "reason": "Recovery policy is paused"}
            if self.s["candidate"] or self.s["canary"]:
                return {"status": "skipped", "reason": "A candidate already awaits review or canary"}
            if automatic and not self.s["settings"]["auto"]:
                return {"status": "skipped", "reason": "Automatic recovery is disabled"}
            if not self.readiness()["ok"]:
                return {"status": "skipped", "reason": "Need 20 training and 10 validation labels, both classes in each"}
            if automatic and not self.degradation()["confirmed"]:
                return {"status": "skipped", "reason": "Measured degradation is not established"}
            last = self.s["last_attempt"]
            if last and (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() < self.s["settings"]["cooldown"] * 60:
                return {"status": "skipped", "reason": "Training cooldown is active"}
            sha, path = self.snapshot()
            if automatic and self.s.get("last_dataset_sha256") == sha:
                return {"status": "skipped", "reason": "No new reviewed evidence since the last training attempt"}
            identifier = "adaptive-" + uuid.uuid4().hex[:12]
            self.s["last_attempt"] = now()
            job = {"id": identifier, "time": now(), "status": "Running", "automatic": automatic}
            self.s["jobs"].insert(0, job)
            self.persist()
            try:
                import mlflow
                mlflow.set_tracking_uri(self.tracking_uri)
                mlflow.set_experiment("SentinelDrift-reviewed-recovery")
                with mlflow.start_run(run_name=identifier) as run:
                    job["mlflow_run_id"] = run.info.run_id
                    mlflow.log_params({"base": self.info["id"], "parent": self.s["champion"],
                                       "base_sha256": self.base_sha256,
                                       "dataset_sha256": sha, "epochs": 240,
                                       "threshold": self.s["settings"]["threshold"], "algorithm": "frozen-base residual logistic"})
                    result = self.engine.call("train", feedback=self.s["feedback"],
                                              champion=self.artifact(self.s["champion"]), threshold=self.s["settings"]["threshold"])
                    evaluation = result["evaluation"]
                    for prefix in ("historical", "recent", "championHistorical", "championRecent"):
                        mlflow.log_metrics({f"{prefix}_{k}": float(v) for k, v in evaluation[prefix].items() if v is not None})
                    mlflow.log_metrics({"initial_loss": result["loss"][0], "final_loss": result["loss"][1], "gate_pass": int(evaluation["pass"])})
                    mlflow.log_dict(result["artifact"], "model/residual.json")
                    mlflow.log_dict(evaluation, "evaluation.json")
                    mlflow.log_dict({"sha256": sha, "review_count": len(self.s["feedback"]), "note": "Raw review URLs remain in local snapshot, not MLflow artifacts."}, "dataset.json")
                    version = {**result, "id": identifier, "createdAt": job["time"], "parent": self.s["champion"],
                               "threshold": self.s["settings"]["threshold"], "dataset_sha256": sha,
                               "mlflow_run_id": run.info.run_id, "status": "Candidate" if evaluation["pass"] else "Rejected"}
                self.s["versions"][identifier] = version
                self.s["last_dataset_sha256"] = sha
                job["status"] = version["status"]
                if evaluation["pass"]:
                    self.s["candidate"] = identifier
                self.event("Recovery evaluated", f"{identifier}: {job['status']}; dataset {sha[:12]}")
                if automatic and self.s["candidate"]:
                    self.start_canary()
            except Exception as exc:
                job["status"] = "Failed"
                job["error"] = str(exc)
                self.event("Recovery failed", str(exc))
            self.persist()
            return job

    def start_canary(self):
        with self.lock:
            if not self.s["settings"]["enabled"]:
                raise ValueError("Recovery policy is paused")
            candidate = self.s["candidate"]
            if not candidate or self.s["canary"]:
                raise ValueError("A passed candidate without an active canary is required")
            version = self.s["versions"][candidate]
            if not version["evaluation"]["pass"] or version["threshold"] != self.s["settings"]["threshold"]:
                raise ValueError("Candidate gates or threshold no longer match")
            self.s["canary"] = {"startedAt": now(), "weight": self.s["settings"]["canary"],
                                "threshold": version["threshold"], "requests": 0, "candidate_requests": 0}
            version["status"] = "Canary"
            self.event("Canary started", f"{candidate} receives {self.s['settings']['canary']}% of new real requests")
            self.persist()

    def canary_evidence(self):
        canary = self.s["canary"]
        if not canary:
            return None
        # No previously reviewed or previously predicted URL can count as fresh trial evidence.
        rows = [r for r in self.s["feedback"] if r["prediction"] and r["createdAt"] >= canary["startedAt"]
                and r["prediction"]["time"] >= canary["startedAt"]]
        x = [r["x"] for r in rows]
        old = metrics(rows, self.probabilities(x), canary["threshold"])
        candidate = metrics(rows, self.probabilities(x, self.s["candidate"]), canary["threshold"])
        both = len({r["y"] for r in rows}) == 2
        passed = len(rows) >= 20 and both and candidate["error"] <= old["error"] and candidate["fnr"] <= max(.1, old["fnr"] or 0)
        return {"rows": len(rows), "both": both, "old": old, "candidate": candidate, "pass": passed}

    def check_canary(self):
        e = self.canary_evidence()
        if not e:
            return
        if e["rows"] >= 10 and e["candidate"]["error"] > e["old"]["error"] + .05:
            self.rollback("Automatic rollback: candidate reviewed error increased by over 5 percentage points")
        elif e["pass"] and self.s["settings"]["auto"] and self.s["settings"]["enabled"]:
            self.promote()

    def promote(self):
        with self.lock:
            if not self.s["settings"]["enabled"]:
                raise ValueError("Recovery policy is paused")
            e = self.canary_evidence()
            if not e or not e["pass"]:
                raise ValueError("Need 20 new reviewed canary observations, both classes, and passing guards")
            self.s["previous"] = self.s["champion"]
            if self.s["previous"] in self.s["versions"]:
                self.s["versions"][self.s["previous"]]["status"] = "Archived"
            self.s["champion"] = self.s["candidate"]
            self.s["versions"][self.s["champion"]]["status"] = "Champion"
            self.s["versions"][self.s["champion"]]["canary_result"] = e
            self.s["candidate"] = self.s["canary"] = None
            self.event("Champion promoted", self.s["champion"])
            self.persist()

    def rollback(self, reason="Operator requested rollback"):
        with self.lock:
            if self.s["canary"]:
                self.s["versions"][self.s["candidate"]]["status"] = "Rolled back"
                self.s["candidate"] = self.s["canary"] = None
            elif self.s["previous"]:
                self.s["versions"][self.s["champion"]]["status"] = "Rolled back"
                self.s["champion"] = self.s["previous"]
                if self.s["champion"] in self.s["versions"]:
                    self.s["versions"][self.s["champion"]]["status"] = "Champion"
                self.s["previous"] = None
            else:
                raise ValueError("No canary or previous champion exists")
            self.event("Model rolled back", reason)
            self.persist()

    def settings(self, changes):
        with self.lock:
            if self.s["candidate"] and changes["threshold"] != self.s["settings"]["threshold"]:
                raise ValueError("Finish or discard the candidate before changing the threshold")
            self.s["settings"].update(changes)
            self.event("Policy saved", "Server policy updated")
            self.persist()

    def state(self):
        with self.lock:
            snapshot = {**self.s, "scope": "persistent-server", "readiness": self.readiness(),
                    "degradation": self.degradation(), "drift": self.drift(),
                    "canary_evidence": self.canary_evidence()}
            return json.loads(json.dumps(snapshot))
