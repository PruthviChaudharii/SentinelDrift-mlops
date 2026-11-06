"""Download the public, CC-BY-4.0 UCI archive without visiting any contained URL."""
from pathlib import Path
import hashlib
import urllib.request
p=Path(__file__).resolve().parents[1]/'.cache-data/phiusiil.zip'
p.parent.mkdir(exist_ok=True)
if not p.exists():
    urllib.request.urlretrieve('https://archive.ics.uci.edu/static/public/967/phiusiil+phishing+url+dataset.zip',p)
expected='0a639fd03aea6308c5b1c10c92aa23c2ce1505447a9137271865cd0badc9a59a'
if hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
    raise RuntimeError('Dataset checksum differs. Review source before using it.')
print('Dataset checksum verified; see model card for attribution.')
