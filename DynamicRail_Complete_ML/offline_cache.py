import json
from pathlib import Path

def save_cache(payload, path="offline_cache.json"):
    Path(path).write_text(json.dumps(payload,indent=2,default=str),encoding="utf-8")

def load_cache(path="offline_cache.json"):
    p=Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
