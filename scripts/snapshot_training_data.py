"""Version the exact downloaded baseline inputs without publishing raw URL datasets in Git."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / ".cache-data"
manifest = json.loads((source / "phresh-manifest.json").read_text(encoding="utf-8"))
files = ["phresh-manifest.json", "mendeley.csv", "phiusiil.zip"] + [r["file"] for r in manifest["files"]]
target = ROOT / "data/training-sources"
target.mkdir(parents=True, exist_ok=True)
checksums = {}
for name in files:
    if Path(name).name != name:
        raise ValueError("Source filename must be a basename")
    data = (source / name).read_bytes()
    checksums[name] = hashlib.sha256(data).hexdigest()
    shutil.copyfile(source / name, target / name)
(target / "checksums.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")
print(f"Snapshotted {len(files)} existing research input files. No URLs were visited.")
