"""A persistent Node worker avoids maintaining two subtly different URL parsers."""
import json
import subprocess
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Engine:
    def __init__(self):
        self.lock = threading.Lock()
        self.process = subprocess.Popen(
            ["node", "backend/worker.cjs"], cwd=ROOT, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, text=True, encoding="utf-8",
        )

    def call(self, op, **kwargs):
        with self.lock:
            if self.process.poll() is not None:
                raise RuntimeError("Classifier worker stopped")
            self.process.stdin.write(json.dumps({"op": op, **kwargs}) + "\n")
            self.process.stdin.flush()
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError("Classifier worker disconnected")
            result = json.loads(line)
            if "error" in result:
                raise ValueError(result["error"])
            return result["result"]

    def close(self):
        self.process.terminate()
        self.process.wait(timeout=10)
