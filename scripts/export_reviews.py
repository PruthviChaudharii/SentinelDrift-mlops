"""Export actual server reviews for DVC; run dvc add afterward to record the new version."""
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
with urlopen("http://localhost:8000/api/export", timeout=30) as response:
    state = json.load(response)
rows = [{"url": r["url"], "label": r["y"], "evidence": r["evidence"], "reviewer": r["reviewer"]}
        for r in state["feedback"]]
(ROOT / "data/reviewed.json").write_text(json.dumps({"feedback": rows}, indent=2), encoding="utf-8")
print(f"Exported {len(rows)} actual reviewed labels to data/reviewed.json")
