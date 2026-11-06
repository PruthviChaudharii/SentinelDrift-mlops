"""DVC's reproducible offline reviewed-data pipeline. Never invents training labels."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.engine import Engine, ROOT
from backend.service import digest

OUT = ROOT / "pipeline-output"


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def write(name, value):
    OUT.mkdir(exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2), encoding="utf-8")


def main(stage):
    engine = Engine()
    try:
        if stage == "features":
            dataset = json.loads((ROOT / "data/reviewed.json").read_text(encoding="utf-8"))
            records = dataset["feedback"]
            prepared = []
            seen = set()
            for r in records:
                if r["label"] not in (0, 1) or len(r["evidence"].strip()) < 8 or len(r["reviewer"].strip()) < 2:
                    raise ValueError("Reviewed records require a binary label, evidence and reviewer")
                row = engine.call("features", urls=[r["url"]])[0]
                if row["url"] in seen:
                    raise ValueError("Duplicate canonical URL in reviewed snapshot")
                seen.add(row["url"])
                prepared.append({**row, "y": r["label"], "evidence": r["evidence"], "reviewer": r["reviewer"]})
            write("features.json", {"feedback": prepared, "dataset_sha256": digest(dataset)})
        elif stage == "train":
            data = read("features.json")
            ready = engine.call("ready", feedback=data["feedback"])
            if not ready["ok"]:
                write("candidate.json", {"status": "skipped", "reason": "Insufficient independently reviewed labels", "readiness": ready})
            else:
                result = engine.call("train", feedback=data["feedback"], champion=None,
                                     threshold=engine.call("info")["policy"]["high"])
                write("candidate.json", {"status": "trained", **result, "dataset_sha256": data["dataset_sha256"]})
        elif stage == "evaluate":
            candidate = read("candidate.json")
            if candidate["status"] == "skipped":
                write("evaluation.json", candidate)
            else:
                result = engine.call("evaluate", feedback=read("features.json")["feedback"], champion=None,
                                     artifact=candidate["artifact"], threshold=engine.call("info")["policy"]["high"])
                write("evaluation.json", result)
        else:
            raise ValueError("Unknown pipeline stage")
    finally:
        engine.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["features", "train", "evaluate"])
    main(parser.parse_args().stage)
